import argparse
import asyncio
import csv
import hashlib
import json
import os
import random
import re
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    from bs4 import BeautifulSoup
except ModuleNotFoundError:  # optional extra; --self-test는 없이도 안내
    BeautifulSoup = None
_BS4_HINT = (
    "beautifulsoup4 미설치 — `uv sync --extra scholar-browser` 또는 "
    "`uv run --extra scholar-browser python skills/google-scholar-semantic/"
    "scripts/scholar_runner.py ...` 로 실행하세요."
)
_STEALTH_HINT = (
    "[LEGACY] 이 브라우저 모드는 repo에 미포함된 외부 모듈 "
    "`agents.stealth_browser`(MoltbotBrowser)를 요구합니다. 번들된 지원 "
    "경로는 src/recon/engine.py 의 SerpApiScholarClient(+Lightpanda fallback) "
    "입니다. self-test / HTML 파싱 경로는 이 모듈 없이도 동작합니다."
)

# 외부 `agents` 패키지가 repo 인접에 존재하는 환경(레거시)에서만 import 가능.
# 번들되지 않으므로 일반 클론에서는 비활성(아래 fetch 함수에서 정직하게 실패).
DEV_ROOT = Path(__file__).resolve().parents[3]
sys.path.append(str(DEV_ROOT))

SCHOLAR_URL = "https://scholar.google.com/scholar_labs/search?hl=ko"
DEFAULT_WAIT_SECONDS = 40
DEFAULT_MAX_QUERIES_PER_SESSION = 4
DEFAULT_CITATION_DEPTH = "all"
DEFAULT_TRE_TERMS = DEV_ROOT / "data" / "tre_terms.csv"
CONFIG_SCHEMA_VERSION = 1
CITATION_DEPTH_CHOICES = {"all", "top5", "none"}
DOMAIN_CHOICES = {"general", "theology"}
CONFIG_KEYS = {
    "schema_version",
    "queries",
    "query_file",
    "html",
    "text",
    "output_dir",
    "jsonl",
    "report",
    "domain",
    "tre_expand",
    "no_expand",
    "tre_terms",
    "max_queries",
    "max_results",
    "max_queries_per_session",
    "citation_depth",
    "wait_seconds",
    "headless",
}

CLASSICAL_EQUIVALENTS = {
    "sabbath": ["šabbāt", "שבת", "sabbaton"],
    "안식일": ["šabbāt", "שבת", "sabbaton"],
    "jubilee": ["yovel", "יובל"],
    "희년": ["yovel", "יובל"],
    "holiness": ["qodesh", "קדש"],
    "거룩": ["qodesh", "קדש"],
    "atonement": ["kipper", "כפר"],
    "속죄": ["kipper", "כפר"],
    "covenant": ["berit", "ברית", "diathēkē"],
    "언약": ["berit", "ברית", "diathēkē"],
}

INTERROGATIVE_STARTERS = (
    "how ", "what ", "which ", "when ", "where ", "why ", "whether ",
    "does ", "do ", "did ", "is ", "are ", "was ", "were ",
    "has ", "have ", "can ", "could ", "should ", "would ",
    "to what extent ", "in what ways ",
)


# ==========================================
# PART 1: Query Expansion
# ==========================================

def _as_path(value: object | None) -> Path | None:
    if value in (None, ""):
        return None
    return Path(str(value)).expanduser()


def _as_str_list(value: object, key: str) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value if _clean_text(item)]
    raise ValueError(f"Config key '{key}' must be a string or list of strings.")


def _as_int(value: object, key: str, minimum: int = 1) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Config key '{key}' must be an integer.") from exc
    if result < minimum:
        raise ValueError(f"Config key '{key}' must be >= {minimum}.")
    return result


def load_runner_config(config_path: Path | None) -> dict[str, object]:
    if not config_path:
        return {}
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    raw = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Config root must be a JSON object.")

    unknown = sorted(set(raw) - CONFIG_KEYS)
    if unknown:
        raise ValueError(f"Unknown config key(s): {', '.join(unknown)}")

    schema_version = raw.get("schema_version", CONFIG_SCHEMA_VERSION)
    if int(schema_version) != CONFIG_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported config schema_version={schema_version}; "
            f"expected {CONFIG_SCHEMA_VERSION}."
        )

    domain = raw.get("domain")
    if domain is not None and str(domain) not in DOMAIN_CHOICES:
        raise ValueError(f"Config key 'domain' must be one of {sorted(DOMAIN_CHOICES)}.")

    citation_depth = raw.get("citation_depth")
    if citation_depth is not None and str(citation_depth) not in CITATION_DEPTH_CHOICES:
        raise ValueError(
            f"Config key 'citation_depth' must be one of {sorted(CITATION_DEPTH_CHOICES)}."
        )

    return raw


def _config_bool(config: dict[str, object], key: str, default: bool = False) -> bool:
    value = config.get(key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        if value.casefold() in {"true", "1", "yes", "y"}:
            return True
        if value.casefold() in {"false", "0", "no", "n"}:
            return False
    raise ValueError(f"Config key '{key}' must be boolean.")


def apply_runner_config(args: argparse.Namespace, config: dict[str, object]) -> argparse.Namespace:
    args.query = _as_str_list(config.get("queries"), "queries") + list(args.query or [])
    args.html = _as_str_list(config.get("html"), "html") + list(args.html or [])
    args.text = _as_str_list(config.get("text"), "text") + list(args.text or [])

    for key in ("query_file", "output_dir", "jsonl", "report", "tre_terms"):
        cli_value = getattr(args, key)
        config_value = _as_path(config.get(key))
        setattr(args, key, cli_value if cli_value is not None else config_value)

    args.domain = args.domain or str(config.get("domain", "general"))
    args.tre_expand = bool(args.tre_expand) or _config_bool(config, "tre_expand", False)
    args.no_expand = bool(args.no_expand) or _config_bool(config, "no_expand", False)
    args.headless = bool(args.headless) or _config_bool(config, "headless", False)

    args.max_queries = (
        args.max_queries if args.max_queries is not None
        else _as_int(config.get("max_queries", 12), "max_queries")
    )
    args.max_results = (
        args.max_results if args.max_results is not None
        else _as_int(config.get("max_results", 10), "max_results")
    )
    args.max_queries_per_session = (
        args.max_queries_per_session if args.max_queries_per_session is not None
        else _as_int(config.get("max_queries_per_session", DEFAULT_MAX_QUERIES_PER_SESSION), "max_queries_per_session")
    )
    args.wait_seconds = (
        args.wait_seconds if args.wait_seconds is not None
        else _as_int(config.get("wait_seconds", DEFAULT_WAIT_SECONDS), "wait_seconds", minimum=0)
    )
    args.citation_depth = args.citation_depth or str(config.get("citation_depth", DEFAULT_CITATION_DEPTH))

    args.output_dir = args.output_dir or Path.cwd()
    args.tre_terms = args.tre_terms or DEFAULT_TRE_TERMS
    return args


def _clean_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def is_semantic_sentence_query(query: str) -> bool:
    q = _clean_text(query)
    if not q:
        return False
    return is_interrogative_query(q)


def is_interrogative_query(query: str) -> bool:
    q = _clean_text(query).casefold()
    return q.endswith("?") or q.startswith(INTERROGATIVE_STARTERS)


def ensure_semantic_question(query: str) -> str:
    """Convert keyword bags into Scholar Labs-friendly natural-language questions."""
    q = _clean_text(query).rstrip(".")
    if not q:
        return q
    if is_interrogative_query(q):
        return q if q.endswith("?") else f"{q}?"

    lower = q.casefold()
    m = re.match(r"find papers from (.+?) about (.+)", q, flags=re.IGNORECASE)
    if m:
        return f"Which papers from {m.group(1)} address {m.group(2)}?"
    if lower.startswith("find papers about "):
        return f"Which papers are about {q[len('find papers about '):]}?"
    if lower.startswith("find papers "):
        return f"Which papers {q[len('find papers '):]}?"
    if lower.startswith("find recent papers about "):
        return f"Which recent papers are about {q[len('find recent papers about '):]}?"

    return f"What does recent scholarship say about {q}?"


def expand_question_with_headwords(query: str, headwords: list[str]) -> str:
    clean_headwords = list(dict.fromkeys(_clean_text(h) for h in headwords if _clean_text(h)))
    if not clean_headwords:
        return ensure_semantic_question(query)

    base = ensure_semantic_question(query).rstrip("?")
    headword_text = ", ".join(clean_headwords)
    return f"{base}, especially in relation to {headword_text}?"


def load_queries(query_file: Path | None = None, inline_queries: list[str] | None = None) -> list[str]:
    queries: list[str] = []
    if inline_queries:
        queries.extend(q for q in inline_queries if q.strip())

    if query_file and query_file.exists():
        raw = query_file.read_text(encoding="utf-8")
        if query_file.suffix.lower() == ".json":
            data = json.loads(raw)
            if isinstance(data, list):
                queries.extend(str(q) for q in data)
            else:
                queries.extend(str(q) for q in data.get("queries", []))
        else:
            queries.extend(line.strip() for line in raw.splitlines() if line.strip())

    if not queries:
        local_default = Path("queries.json")
        script_default = Path(__file__).resolve().parent / "queries.json"
        default_path = local_default if local_default.exists() else script_default
        if default_path.exists():
            data = json.loads(default_path.read_text(encoding="utf-8"))
            queries.extend(str(q) for q in data.get("queries", []))

    return list(dict.fromkeys(ensure_semantic_question(q) for q in queries if _clean_text(q)))


def load_tre_terms(csv_path: Path = DEFAULT_TRE_TERMS) -> list[dict[str, str]]:
    if not csv_path.exists():
        return []

    rows: list[dict[str, str]] = []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append({
                "de": _clean_text(row.get("독일어")),
                "en": _clean_text(row.get("영어")),
                "fr": _clean_text(row.get("프랑스어")),
                "ko": _clean_text(row.get("한국어")),
                "description": _clean_text(row.get("설명")),
            })
    return rows


def _term_matches_query(row: dict[str, str], query: str) -> bool:
    q = query.casefold()
    candidates: list[str] = []
    for key in ("de", "en", "ko"):
        value = row.get(key, "")
        candidates.append(value)
        candidates.extend(part.strip() for part in value.split("/"))

    for candidate in candidates:
        candidate = _clean_text(candidate)
        compact = re.sub(r"\W+", "", candidate, flags=re.UNICODE)
        if len(compact) < 2:
            continue

        # CJK/Hebrew/Greek terms are usually not whitespace-tokenized, so substring
        # matching is acceptable. Latin-script headwords need word boundaries to
        # avoid false positives such as "Mary" inside "summary".
        if re.search(r"[가-힣א-תἀ-῿\u0370-\u03ff]", candidate):
            if candidate.casefold() in q:
                return True
            continue

        pattern = rf"(?<![A-Za-z]){re.escape(candidate.casefold())}(?![A-Za-z])"
        if re.search(pattern, q):
            return True

    return False


def _classical_terms_for(query: str) -> list[str]:
    q = query.casefold()
    terms: list[str] = []
    for key, values in CLASSICAL_EQUIVALENTS.items():
        if key.casefold() in q:
            terms.extend(values)
    return list(dict.fromkeys(terms))


def expand_queries_with_tre(
    queries: list[str],
    tre_terms_path: Path = DEFAULT_TRE_TERMS,
    max_terms_per_query: int = 3,
    max_queries: int = 12,
) -> tuple[list[str], list[dict[str, object]]]:
    """Expand queries with TRE German/English/Korean and classical headwords."""
    tre_terms = load_tre_terms(tre_terms_path)
    expanded: list[str] = []
    expansion_log: list[dict[str, object]] = []

    for query in queries:
        query = ensure_semantic_question(query)
        expanded.append(query)
        matches = [row for row in tre_terms if _term_matches_query(row, query)]
        matches = matches[:max_terms_per_query]
        classical = _classical_terms_for(query)

        for row in matches:
            headwords = [row.get("en"), row.get("de"), row.get("ko")]
            headwords = [h for h in headwords if h]
            if classical:
                headwords.extend(classical[:4])
            if not headwords:
                continue

            expanded_query = expand_question_with_headwords(query, headwords)
            expanded.append(expanded_query)
            expansion_log.append({
                "base_query": query,
                "tre_term": row,
                "classical_terms": classical,
                "expanded_query": expanded_query,
            })

        if classical and not matches:
            expanded_query = expand_question_with_headwords(query, classical[:4])
            expanded.append(expanded_query)
            expansion_log.append({
                "base_query": query,
                "tre_term": None,
                "classical_terms": classical,
                "expanded_query": expanded_query,
            })

    unique = list(dict.fromkeys(q for q in expanded if q))[:max_queries]
    return unique, expansion_log


# ==========================================
# PART 2: Stealth Crawler Logic
# ==========================================

async def _run_semantic_crawl_session(
    queries: list[str],
    output_dir: Path,
    wait_seconds: int = DEFAULT_WAIT_SECONDS,
    headless: bool = False,
    start_query_index: int = 0,
    total_queries: int | None = None,
    max_results: int = 10,
    citation_depth: str = DEFAULT_CITATION_DEPTH,
) -> list[tuple[int, str]]:
    try:
        from agents.stealth_browser import MoltbotBrowser
    except ModuleNotFoundError as e:
        raise RuntimeError(_STEALTH_HINT) from e

    bot = MoltbotBrowser(headless=headless)
    captured_files: list[tuple[int, str]] = []
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        print("Moltbot v2 (Scholar Semantic) launching...")
        await bot.start()
        await bot.browse(SCHOLAR_URL)

        print("ACTION REQUIRED: Please log in manually if not already logged in.")
        print("Waiting for valid Scholar URL (scholar.google.com)...")

        login_success = False
        for _ in range(300):  # Wait up to 5 min
            current_url = bot.page.url
            if "scholar.google" in current_url and "accounts.google" not in current_url:
                login_success = True
                print("Login detected. Resuming mission...")
                break
            await asyncio.sleep(2)

        if not login_success:
            print("Login timeout.")
            return []

        if "scholar_labs" not in bot.page.url:
            await bot.browse(SCHOLAR_URL)
            await asyncio.sleep(5)

        total = total_queries or len(queries)
        for local_i, query in enumerate(queries, 1):
            global_i = start_query_index + local_i
            print(f"\n[Query {global_i}/{total}] Processing...")
            print(f"   Q: {query[:80]}...")

            try:
                input_selector = None
                candidates = [
                    "textarea#gs_as_i_t",
                    "textarea[name='q']",
                    "textarea",
                    "input[type='text']",
                    "div[contenteditable='true']",
                    "#gs_hdr_tsi",
                    "[aria-label='Search']",
                ]
                for sel in candidates:
                    locator = bot.page.locator(sel)
                    if await locator.count() > 0 and await locator.first.is_visible():
                        input_selector = sel
                        break

                if not input_selector:
                    print(f"Input missing for Query {global_i}")
                    continue

                await bot.mouse.click_element(selector=input_selector)
                await bot.page.keyboard.press("Meta+A")
                await bot.page.keyboard.press("Backspace")
                await asyncio.sleep(0.5)
                await bot.page.keyboard.type(query, delay=random.randint(20, 50))
                await bot.page.keyboard.press("Enter")

                started_at = time.monotonic()
                print("Monitoring Scholar Labs status...")
                status_pattern = re.compile(r"(?:관련 검색 결과|Related search results).*?(\d+)")
                found_results = False

                for _ in range(120):  # 2 mins max
                    content = await bot.page.content()
                    matches = status_pattern.findall(content)

                    if matches:
                        print(f"Result signal detected ({matches[-1]} results).")
                        found_results = True
                        break

                    if "평가됨" in content or "Evaluat" in content:
                        sys.stdout.write(".")
                        sys.stdout.flush()

                    await asyncio.sleep(2)

                elapsed = time.monotonic() - started_at
                remaining = max(0, wait_seconds - int(elapsed))
                if remaining:
                    print(f"\nWait Protocol: sleeping {remaining}s to satisfy {wait_seconds}s minimum.")
                    await asyncio.sleep(remaining)

                if not found_results:
                    print("Completion signal not found. Proceeding with visible results.")

                if citation_depth == "none":
                    citation_limit = 0
                elif citation_depth == "top5":
                    citation_limit = min(5, max_results)
                else:
                    citation_limit = max_results

                print(f"Attempting citation extraction ({citation_depth}, up to {citation_limit})...")
                results = await bot.page.locator(".gs_r").all()
                for idx, res in enumerate(results[:citation_limit]):
                    try:
                        cite_btn = (
                            res.locator(".gs_or_cit")
                            .or_(res.locator('a:has-text("인용")'))
                            .or_(res.locator('a:has-text("Cite")'))
                            .first
                        )
                        if await cite_btn.count() > 0 and await cite_btn.is_visible():
                            await cite_btn.click()
                            modal = bot.page.locator("#gs_cit")
                            await modal.wait_for(state="visible", timeout=4000)

                            cit_rows = bot.page.locator("#gs_citt .gs_citr")
                            formatted_citations: list[str] = []
                            for row_i in range(await cit_rows.count()):
                                row_text = await cit_rows.nth(row_i).text_content()
                                row_text = _clean_text(row_text)
                                if row_text:
                                    formatted_citations.append(row_text)

                            cit_links = bot.page.locator("#gs_citi a")
                            citation_links: list[dict[str, str]] = []
                            for link_i in range(await cit_links.count()):
                                link = cit_links.nth(link_i)
                                label = _clean_text(await link.text_content())
                                href = _clean_text(await link.get_attribute("href"))
                                if label or href:
                                    citation_links.append({"label": label, "url": href})

                            citation_payload = {
                                "formatted": formatted_citations,
                                "links": citation_links,
                            }
                            # Scholar usually orders rows as MLA, APA, Chicago, Harvard, Vancouver.
                            primary = formatted_citations[1] if len(formatted_citations) > 1 else (
                                formatted_citations[0] if formatted_citations else ""
                            )

                            await bot.page.locator("#gs_cit-x").click(force=True)
                            await modal.wait_for(state="hidden", timeout=3000)

                            await res.evaluate(
                                """(el, payload) => {
                                    el.setAttribute("data-extracted-citation", payload.primary);
                                    el.setAttribute("data-extracted-citation-json", payload.json);
                                    el.setAttribute("data-citation-status", payload.status);
                                }""",
                                {
                                    "primary": primary,
                                    "json": json.dumps(citation_payload, ensure_ascii=False),
                                    "status": "ok" if formatted_citations or citation_links else "empty",
                                },
                            )
                            sys.stdout.write(f" [{idx + 1}:OK] ")
                        else:
                            await res.evaluate(
                                """(el) => el.setAttribute("data-citation-status", "missing_button")"""
                            )
                            sys.stdout.write(f" [{idx + 1}:NoBtn] ")
                    except Exception as e:
                        try:
                            await res.evaluate(
                                """(el, status) => el.setAttribute("data-citation-status", status)""",
                                f"error:{type(e).__name__}",
                            )
                        except Exception:
                            pass
                        sys.stdout.write(f" [{idx + 1}:Err] ")
                        try:
                            await bot.page.locator("#gs_cit-x").click()
                        except Exception:
                            pass
                print("")

                timestamp = datetime.now().strftime("%H%M%S")
                filename = output_dir / f"scholar_result_{global_i}_{timestamp}.html"
                content = await bot.page.content()
                filename.write_text(content, encoding="utf-8")
                captured_files.append((global_i, str(filename)))
                print(f"Saved: {filename}")

                await asyncio.sleep(random.uniform(5, 10))

            except Exception as e:
                print(f"Error Query {global_i}: {e}")

    finally:
        await bot.close()

    return captured_files


def session_batches(queries: list[str], max_queries_per_session: int) -> list[list[str]]:
    batch_size = min(DEFAULT_MAX_QUERIES_PER_SESSION, max(1, max_queries_per_session))
    return [queries[start:start + batch_size] for start in range(0, len(queries), batch_size)]


async def run_semantic_crawl(
    queries: list[str],
    output_dir: Path,
    wait_seconds: int = DEFAULT_WAIT_SECONDS,
    headless: bool = False,
    max_queries_per_session: int = DEFAULT_MAX_QUERIES_PER_SESSION,
    max_results: int = 10,
    citation_depth: str = DEFAULT_CITATION_DEPTH,
) -> list[tuple[int, str]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    if max_queries_per_session > DEFAULT_MAX_QUERIES_PER_SESSION:
        print(
            f"max_queries_per_session={max_queries_per_session} exceeds Scholar Labs guardrail; "
            f"clamping to {DEFAULT_MAX_QUERIES_PER_SESSION}."
        )
    captured_files: list[tuple[int, str]] = []
    batches = session_batches(queries, max_queries_per_session)
    for session_no, batch in enumerate(batches, 1):
        start = sum(len(prior) for prior in batches[:session_no - 1])
        session_count = len(batches)
        print(f"\n=== Scholar Labs session {session_no}/{session_count}: {len(batch)} query(ies) ===")
        captured_files.extend(
            await _run_semantic_crawl_session(
                batch,
                output_dir=output_dir,
                wait_seconds=wait_seconds,
                headless=headless,
                start_query_index=start,
                total_queries=len(queries),
                max_results=max_results,
                citation_depth=citation_depth,
            )
        )
        if session_no < session_count:
            print("Rotating browser session to avoid Scholar Labs query lock.")
            await asyncio.sleep(random.uniform(10, 20))

    return captured_files


# ==========================================
# PART 3: Parser, JSONL, Reporter Logic
# ==========================================

def _stable_id(*parts: object) -> str:
    raw = "||".join(_clean_text(p) for p in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _parse_citation_count(text: str) -> int:
    text = _clean_text(text)
    patterns = [
        r"인용\s*(\d+)\s*회",
        r"(\d+)\s*회\s*인용",
        r"Cited by\s*(\d+)",
        r"(\d+)\s*citations?",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return int(m.group(1))
    return 0


def _parse_meta(meta: str) -> dict[str, object]:
    meta = _clean_text(meta)
    year_match = re.search(r"\b(1[5-9]\d{2}|20\d{2})\b", meta)
    parts = [p.strip() for p in re.split(r"\s+-\s+", meta) if p.strip()]
    return {
        "authors_text": parts[0] if parts else "",
        "venue": parts[1] if len(parts) > 1 else "",
        "publisher": parts[2] if len(parts) > 2 else "",
        "year": int(year_match.group(1)) if year_match else None,
    }


def _parse_json_attr(value: str) -> dict[str, object]:
    value = _clean_text(value)
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _record_from_element(
    res,
    query: str,
    rank: int,
    source_file: str,
    retrieved_at: str,
) -> dict[str, object] | None:
    title_tag = res.select_one(".gs_rt a, h3 a, a[data-clk], a[id][href]")
    if not title_tag:
        return None

    title = _clean_text(title_tag.get_text(" "))
    if not title or len(title) < 4:
        return None

    link = _clean_text(title_tag.get("href"))
    meta = _clean_text(res.select_one(".gs_a").get_text(" ") if res.select_one(".gs_a") else "")
    snippet = _clean_text(res.select_one(".gs_rs").get_text(" ") if res.select_one(".gs_rs") else "")
    type_text = _clean_text(res.select_one(".gs_ctg2").get_text(" ") if res.select_one(".gs_ctg2") else "")
    citation_payload = _parse_json_attr(str(res.attrs.get("data-extracted-citation-json", "")))
    citation_variants = citation_payload.get("formatted", [])
    citation_links = citation_payload.get("links", [])
    if not isinstance(citation_variants, list):
        citation_variants = []
    if not isinstance(citation_links, list):
        citation_links = []
    full_citation = _clean_text(res.attrs.get("data-extracted-citation", ""))
    if not full_citation and citation_variants:
        full_citation = _clean_text(citation_variants[1] if len(citation_variants) > 1 else citation_variants[0])
    fl_text = _clean_text(res.select_one(".gs_fl").get_text(" ") if res.select_one(".gs_fl") else res.get_text(" "))
    meta_data = _parse_meta(meta)

    return {
        "id": _stable_id(query, title, link),
        "record_type": "scholar_result",
        "source": "google_scholar_labs",
        "query": query,
        "rank": rank,
        "title": title,
        "url": link,
        "authors_text": meta_data["authors_text"],
        "authors": [a.strip() for a in re.split(r",|;|\band\b", str(meta_data["authors_text"])) if a.strip()],
        "year": meta_data["year"],
        "venue": meta_data["venue"],
        "publisher": meta_data["publisher"],
        "raw_meta": meta,
        "snippet": snippet,
        "citation": full_citation,
        "citation_variants": citation_variants,
        "citation_links": citation_links,
        "citation_status": _clean_text(res.attrs.get("data-citation-status", "")),
        "citation_count": _parse_citation_count(fl_text),
        "document_type": type_text.replace("[", "").replace("]", ""),
        "source_file": source_file,
        "retrieved_at": retrieved_at,
        "parser": "scholar_runner.parse_labs_html",
    }


def parse_labs_html(html: str, query: str, source_file: str = "", max_results: int = 10) -> list[dict[str, object]]:
    soup = BeautifulSoup(html, "html.parser")
    retrieved_at = datetime.now().isoformat()
    records: list[dict[str, object]] = []
    seen: set[str] = set()

    turns = soup.select(".gs_as_cp_tr")
    containers = turns if turns else [soup]
    for turn in containers:
        turn_query_el = turn.select_one(".gs_as_cp_tq")
        turn_query = _clean_text(turn_query_el.get_text(" ")) if turn_query_el else query
        if not turn_query:
            turn_query = query

        elements = turn.select(".gs_r.gs_or.gs_scl, .gs_as_r .gs_r, .gs_as_r .gs_or, .gs_r[data-cid], .gs_r")
        if not elements:
            elements = turn.select(".gs_as_r")

        for el in elements:
            record = _record_from_element(el, turn_query, len(records) + 1, source_file, retrieved_at)
            if not record:
                continue
            key = str(record["id"])
            if key in seen:
                continue
            seen.add(key)
            records.append(record)
            if len(records) >= max_results:
                return records

    if records:
        return records

    # Last-resort fallback for pasted/simplified Labs DOM snapshots.
    for link in soup.select("a[href]"):
        title = _clean_text(link.get_text(" "))
        href = _clean_text(link.get("href"))
        if len(title) < 12 or "scholar.google" in href:
            continue
        parent = link.find_parent(["div", "article", "section"]) or link.parent
        text = _clean_text(parent.get_text(" ") if parent else "")
        meta_data = _parse_meta(text)
        record = {
            "id": _stable_id(query, title, href),
            "record_type": "scholar_result",
            "source": "google_scholar_labs",
            "query": query,
            "rank": len(records) + 1,
            "title": title,
            "url": href,
            "authors_text": meta_data["authors_text"],
            "authors": [],
            "year": meta_data["year"],
            "venue": meta_data["venue"],
            "publisher": meta_data["publisher"],
            "raw_meta": text[:300],
            "snippet": text[:500],
            "citation": "",
            "citation_count": _parse_citation_count(text),
            "document_type": "",
            "source_file": source_file,
            "retrieved_at": retrieved_at,
            "parser": "scholar_runner.parse_labs_html_fallback",
        }
        if record["id"] not in seen:
            seen.add(str(record["id"]))
            records.append(record)
        if len(records) >= max_results:
            break
    return records


def parse_labs_text(text: str, query: str, source_file: str = "", max_results: int = 10) -> list[dict[str, object]]:
    retrieved_at = datetime.now().isoformat()
    blocks = re.split(r"\n\s*\n|(?=\n?\s*(?:\d+\.|#{2,3}\s+|\*\*\d+\.))", text)
    records: list[dict[str, object]] = []
    for block in blocks:
        lines = [_clean_text(line.strip("*# >-")) for line in block.splitlines()]
        lines = [line for line in lines if line]
        if not lines:
            continue

        title = re.sub(r"^\d+\.\s*", "", lines[0]).strip()
        if len(title) < 8:
            continue

        meta_line = next((line for line in lines[1:] if re.search(r"\b(1[5-9]\d{2}|20\d{2})\b", line)), "")
        snippet = " ".join(line for line in lines[1:] if line != meta_line)
        meta_data = _parse_meta(meta_line)

        records.append({
            "id": _stable_id(query, title, meta_line),
            "record_type": "scholar_result",
            "source": "google_scholar_labs",
            "query": query,
            "rank": len(records) + 1,
            "title": title,
            "url": "",
            "authors_text": meta_data["authors_text"],
            "authors": [],
            "year": meta_data["year"],
            "venue": meta_data["venue"],
            "publisher": meta_data["publisher"],
            "raw_meta": meta_line,
            "snippet": snippet[:800],
            "citation": "",
            "citation_count": _parse_citation_count(block),
            "document_type": "",
            "source_file": source_file,
            "retrieved_at": retrieved_at,
            "parser": "scholar_runner.parse_labs_text",
        })
        if len(records) >= max_results:
            break
    return records


def parse_files_to_records(
    file_list: list[tuple[int, str]],
    query_texts: list[str],
    max_results: int = 10,
) -> list[dict[str, object]]:
    all_records: list[dict[str, object]] = []
    for q_num, filepath in file_list:
        q_text = query_texts[q_num - 1] if (q_num - 1) < len(query_texts) else f"Query {q_num}"
        path = Path(filepath)
        raw = path.read_text(encoding="utf-8", errors="ignore")
        if path.suffix.lower() in {".html", ".htm"}:
            records = parse_labs_html(raw, q_text, str(path), max_results=max_results)
        else:
            records = parse_labs_text(raw, q_text, str(path), max_results=max_results)
        all_records.extend(records)
    return all_records


def write_jsonl(records: list[dict[str, object]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def parse_and_report(file_list: list[tuple[int, str]], query_texts: list[str]) -> str:
    records = parse_files_to_records(file_list, query_texts)
    if not records:
        return "No files captured."

    md = "# Theology Research Report: Semantic Synthesis\n\n"
    md += f"**Date**: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
    md += "**Source**: Google Scholar Labs\n\n"

    current_query = None
    for item in records:
        if item["query"] != current_query:
            current_query = item["query"]
            md += f"## {current_query}\n"
            md += f"`source: {item['source_file']}`\n\n"

        md += f"### {item['rank']}. {item['title']}\n"
        if item.get("citation"):
            md += f"> {item['citation']}\n\n"
        elif item.get("raw_meta"):
            md += f"- **Metadata**: {item['raw_meta']}\n"

        md += f"- **Citations**: {item.get('citation_count', 0)}\n"
        md += f"- **Link**: {item.get('url') or '#'}\n"
        md += f"- **Snippet**: {item.get('snippet', '')}\n\n"

    return md


def _sample_scholar_html() -> str:
    payload = {
        "formatted": [
            "Doe, Jane. Sample Article. Journal of Tests, 2024.",
            "Doe, J. (2024). Sample Article. Journal of Tests.",
        ],
        "links": [{"label": "BibTeX", "url": "https://scholar.google.com/scholar.bib?q=sample"}],
    }
    payload_json = json.dumps(payload, ensure_ascii=False).replace("'", "&#39;")
    return f"""
    <html><body>
      <div class="gs_r gs_or gs_scl"
           data-extracted-citation="Doe, J. (2024). Sample Article. Journal of Tests."
           data-extracted-citation-json='{payload_json}'
           data-citation-status="ok">
        <h3 class="gs_rt"><a href="https://example.org/sample">Sample Article</a></h3>
        <div class="gs_a">Jane Doe - Journal of Tests - Example Press, 2024</div>
        <div class="gs_rs">A controlled sample result for parser validation.</div>
        <div class="gs_fl">Cited by 12</div>
      </div>
      <div class="gs_r gs_or gs_scl" data-citation-status="missing_button">
        <h3 class="gs_rt"><a href="https://example.org/second">Second Sample Article</a></h3>
        <div class="gs_a">John Smith - Testing Quarterly - 2023</div>
        <div class="gs_rs">A second controlled sample result.</div>
        <div class="gs_fl">Cited by 3</div>
      </div>
    </body></html>
    """


def run_self_test() -> int:
    if BeautifulSoup is None:
        print(json.dumps(
            {"self_test": "skipped", "reason": _BS4_HINT}, ensure_ascii=False, indent=2
        ), file=sys.stderr)
        return 2
    errors: list[str] = []

    def check(condition: bool, message: str) -> None:
        if not condition:
            errors.append(message)

    normalized = ensure_semantic_question("LLM summary grounding evaluation")
    check(
        normalized == "What does recent scholarship say about LLM summary grounding evaluation?",
        "keyword query normalization failed",
    )

    batches = session_batches([str(i) for i in range(9)], max_queries_per_session=99)
    check([len(batch) for batch in batches] == [4, 4, 1], "session batching did not clamp to 4 queries")

    records = parse_labs_html(_sample_scholar_html(), normalized, "selftest.html", max_results=2)
    check(len(records) == 2, "HTML parser did not return 2 records")
    if records:
        first = records[0]
        check(first.get("citation_status") == "ok", "citation_status was not preserved")
        check(len(first.get("citation_variants", [])) == 2, "citation_variants were not preserved")
        check(len(first.get("citation_links", [])) == 1, "citation_links were not preserved")
        check(first.get("citation_count") == 12, "citation_count parsing failed")

    config_args = argparse.Namespace(
        query=[],
        html=[],
        text=[],
        query_file=None,
        output_dir=None,
        jsonl=None,
        report=None,
        domain=None,
        tre_expand=False,
        no_expand=False,
        headless=False,
        max_queries=None,
        max_results=None,
        max_queries_per_session=None,
        wait_seconds=None,
        citation_depth=None,
        tre_terms=None,
    )
    configured = apply_runner_config(config_args, {
        "queries": ["justification"],
        "domain": "theology",
        "max_queries_per_session": 4,
        "citation_depth": "all",
        "max_results": 7,
    })
    check(configured.domain == "theology", "config domain was not applied")
    check(configured.max_queries_per_session == 4, "config max_queries_per_session was not applied")
    check(configured.citation_depth == "all", "config citation_depth was not applied")
    check(configured.max_results == 7, "config max_results was not applied")

    if errors:
        print(json.dumps({"self_test": "failed", "errors": errors}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1

    print(json.dumps({
        "self_test": "ok",
        "checks": [
            "query_normalization",
            "session_batching_clamps_to_4",
            "html_parser_preserves_citation_fields",
            "config_application",
        ],
    }, ensure_ascii=False, indent=2))
    return 0


# ==========================================
# MAIN EXECUTION
# ==========================================

def main() -> int:
    parser = argparse.ArgumentParser(description="Google Scholar Labs semantic crawler/parser")
    parser.add_argument("--config", type=Path, help="Runner config JSON. CLI arguments override config values.")
    parser.add_argument("--self-test", action="store_true", help="Run offline checks without opening a browser.")
    parser.add_argument("--query", action="append", default=[], help="Query string. Can be used multiple times.")
    parser.add_argument("--query-file", type=Path, help="JSON QuerySet or newline query file.")
    parser.add_argument("--html", nargs="*", default=[], help="Existing Scholar Labs HTML files to parse.")
    parser.add_argument("--text", nargs="*", default=[], help="Existing raw text files to parse.")
    parser.add_argument("--output-dir", type=Path, help="Output directory.")
    parser.add_argument("--jsonl", type=Path, help="JSONL output path.")
    parser.add_argument("--report", type=Path, help="Markdown report output path.")
    parser.add_argument("--expand-only", action="store_true", help="Only print normalized QuerySet JSON.")
    parser.add_argument("--tre-expand", action="store_true", help="Enable TRE theology-term expansion. Default is off.")
    parser.add_argument("--no-expand", action="store_true", help="Force-disable TRE query expansion.")
    parser.add_argument("--domain", choices=["general", "theology"],
                        help="Search domain. 'theology' enables TRE expansion unless --no-expand is set.")
    parser.add_argument("--tre-terms", type=Path, help="TRE terms CSV path.")
    parser.add_argument("--max-queries", type=int, help="Maximum expanded queries.")
    parser.add_argument("--max-results", type=int, help="Maximum parsed results per query/file.")
    parser.add_argument("--max-queries-per-session", type=int,
                        help="Scholar Labs browser-session query cap. Values above 4 are clamped to 4.")
    parser.add_argument("--citation-depth", choices=["all", "top5", "none"],
                        help="How many visible references should receive citation-modal extraction.")
    parser.add_argument("--wait-seconds", type=int, help="Minimum wait after each Labs query.")
    parser.add_argument("--headless", action="store_true", help="Run browser headless.")
    args = parser.parse_args()

    try:
        config = load_runner_config(args.config)
        args = apply_runner_config(args, config)
    except Exception as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 1

    if args.self_test:
        return run_self_test()

    queries = load_queries(args.query_file, args.query)
    if not queries and not args.html and not args.text:
        print("No queries found. Provide --query, --query-file, or queries.json.", file=sys.stderr)
        return 1

    expansion_log: list[dict[str, object]] = []
    tre_enabled = bool(args.tre_expand or args.domain == "theology")
    if args.no_expand:
        tre_enabled = False

    if queries and tre_enabled:
        queries, expansion_log = expand_queries_with_tre(
            queries,
            tre_terms_path=args.tre_terms,
            max_queries=args.max_queries,
        )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    expansion_path = args.output_dir / "QueryExpansion.json"
    if queries:
        expansion_path.write_text(
            json.dumps({
                "queries": queries,
                "expanded_at": datetime.now().isoformat(),
                "domain": args.domain,
                "tre_expansion_enabled": tre_enabled,
                "tre_terms_path": str(args.tre_terms),
                "expansion_log": expansion_log,
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    if args.expand_only:
        print(expansion_path.read_text(encoding="utf-8"))
        return 0

    captured: list[tuple[int, str]] = []
    for idx, html_path in enumerate(args.html, 1):
        captured.append((idx, html_path))
    offset = len(captured)
    for idx, text_path in enumerate(args.text, 1):
        captured.append((offset + idx, text_path))

    if not captured:
        captured = asyncio.run(
            run_semantic_crawl(
                queries,
                output_dir=args.output_dir,
                wait_seconds=args.wait_seconds,
                headless=args.headless,
                max_queries_per_session=args.max_queries_per_session,
                max_results=args.max_results,
                citation_depth=args.citation_depth,
            )
        )

    if not captured:
        print("Extraction incomplete; no files captured.", file=sys.stderr)
        return 2

    records = parse_files_to_records(captured, queries, max_results=args.max_results)
    jsonl_path = args.jsonl or (args.output_dir / f"scholar_labs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl")
    report_path = args.report or (args.output_dir / f"Research_Report_{datetime.now().strftime('%Y%m%d_%H%M')}.md")
    write_jsonl(records, jsonl_path)
    report_path.write_text(parse_and_report(captured, queries), encoding="utf-8")

    print(f"JSONL generated: {jsonl_path} ({len(records)} records)")
    print(f"Report generated: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
