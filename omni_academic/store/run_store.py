"""런 단위 산출물 영속화.

한 번의 가동 결과를 typed JSON 아티팩트로 `runs/<id>/` 에 떨군다.
manifest는 자기검증적이어야 한다 — mock 여부·git commit·audit 평결을
박아넣어, --mock 결과가 검증된 결과인 양 위장하는 것을 차단한다(헌법:
무손실·환각 차단). 외부 의존성 0개(stdlib json/sqlite3/subprocess).
"""

import hashlib
import json
import re
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional


def _git_commit() -> Optional[str]:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=False, timeout=5,
        )
        return out.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return (s[:40] or "run")


def _dump(obj: Any) -> Any:
    """Pydantic/리스트/집합을 JSON 직렬화 가능 형태로."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if isinstance(obj, (set, frozenset)):
        return sorted(obj)
    if isinstance(obj, list):
        return [_dump(x) for x in obj]
    return obj


def _field(obj: Any, name: str, default: Any = "") -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _value(obj: Any) -> str:
    val = getattr(obj, "value", obj)
    return "" if val is None else str(val)


def _truncate(text: Any, limit: int = 180) -> str:
    s = " ".join(str(text or "").split())
    if len(s) <= limit:
        return s
    return s[: max(0, limit - 3)].rstrip() + "..."


def _authors(paper: Any) -> str:
    authors = _field(paper, "authors", []) or []
    return ", ".join(str(a) for a in authors) if authors else "저자 미상"


def _paper_title(paper: Any) -> str:
    return _field(paper, "title", str(paper))


def _finding_line(finding: Any) -> str:
    severity = _value(_field(finding, "severity", "")).upper() or "INFO"
    code = _value(_field(finding, "code", ""))
    message = _field(finding, "message", "")
    source_ref = _field(finding, "source_ref", "")
    ref = f" (`{source_ref}`)" if source_ref else ""
    return f"- **{severity}** `{code}`: {message}{ref}"


def _artifact_link(name: str) -> str:
    return f"- [`{name}`](./{name})"


def _failure_diagnostic(status: str, meta: dict) -> list[str]:
    diagnostics = {
        "failed": "Unhandled exception. Check `error_message`, traceback in terminal logs, and the git commit recorded below.",
        "no_papers_found": "Recon completed but returned no candidates. Try a broader query, a different lens, or `--no-cache` if stale cache is suspected.",
        "cancelled_by_user": "The run stopped at HITL selection. No deep-dive scrape or ontology extraction was attempted.",
        "invalid_choice": "The HITL paper selection did not match an available digest index. Re-run and choose a listed number.",
        "scraper_detection_failed": "ScraperFactory could not select a supported scraper for the selected URL. Check the URL and content type.",
        "scraping_failed": "A scraper was selected, but no Markdown full text was produced. Check source access, PDF extraction, or external tool configuration.",
        "analysis_failed": "Lens briefing failed before artifact creation. Check that the requested lens exists under `lenses/`.",
    }
    message = diagnostics.get(str(status or ""))
    if not message:
        return []
    lines = [f"- **Likely Cause**: {message}"]
    if meta.get("error_message"):
        lines.append(f"- **Recorded Error**: `{meta['error_message']}`")
    if meta.get("forensic_blocked_count"):
        lines.append(
            f"- **Forensic Blocks**: `{meta['forensic_blocked_count']}` paper(s) "
            "were removed before HITL selection."
        )
    return lines


def _file_integrity(path: Path) -> dict:
    if not path.is_file():
        return {"exists": False, "bytes": 0, "sha256": None}
    data = path.read_bytes()
    return {
        "exists": True,
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def verify_artifact_manifest(run_dir: Path, artifact_manifest: dict) -> list[str]:
    if not artifact_manifest:
        return ["manifest에 artifact_manifest가 없습니다."]

    issues: list[str] = []
    for name, expected in artifact_manifest.items():
        current = _file_integrity(run_dir / name)
        if bool(current.get("exists")) != bool(expected.get("exists")):
            issues.append(
                f"{name}: exists mismatch expected={expected.get('exists')} "
                f"actual={current.get('exists')}"
            )
            continue
        if not current.get("exists"):
            continue
        if int(current.get("bytes") or 0) != int(expected.get("bytes") or 0):
            issues.append(
                f"{name}: byte size mismatch expected={expected.get('bytes')} "
                f"actual={current.get('bytes')}"
            )
        if current.get("sha256") != expected.get("sha256"):
            issues.append(f"{name}: sha256 mismatch")
    return issues


class RunStore:
    def __init__(self, run_dir: Path, meta: dict, base: Path):
        self.dir = run_dir
        self._meta = meta
        self._base = base
        self._artifacts: List[str] = []
        # 리포트 생성을 위한 데이터 수집 버퍼
        self._papers = []
        self._ontology = None
        self._audit = None
        self._forensic = []
        self._lens_audit = None
        self._lens_critic_audit = None
        self._draft_audit = None
        self._review = None

    @classmethod
    def create(cls, query: str, lens: str, *, mock: bool = False,
               base: str = "runs") -> "RunStore":
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        prefix = "MOCK-" if mock else ""
        query_slug = _slug(query)
        run_id = f"{query_slug}/{prefix}{ts}"
        base_path = Path(base)
        run_dir = base_path / query_slug / f"{prefix}{ts}"
        run_dir.mkdir(parents=True, exist_ok=True)

        # 최신 실행 디렉터리를 가리키는 "latest" 심볼릭 링크 생성
        latest_link = base_path / query_slug / "latest"
        try:
            if latest_link.is_symlink() or latest_link.exists():
                latest_link.unlink()
            latest_link.symlink_to(Path(f"{prefix}{ts}"))
        except Exception:
            pass

        meta = {
            "run_id": run_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "query": query,
            "lens": lens,
            "mock": mock,
            "git_commit": _git_commit(),
            "audit_passed": None,
        }
        return cls(run_dir, meta, base_path)

    def note(self, key: str, value: Any):
        """manifest에 부가 프로비넌스 기록(예: recon 캐시 적중/나이)."""
        self._meta[key] = value

    def _write_json(self, name: str, obj: Any):
        path = self.dir / name
        path.write_text(
            json.dumps(_dump(obj), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._artifacts.append(name)

    def write_digest(self, papers: list):
        self._papers = papers
        self._write_json("digest.json", papers)

    def write_fulltext(self, markdown: str):
        (self.dir / "fulltext.md").write_text(markdown or "", encoding="utf-8")
        self._artifacts.append("fulltext.md")

    def write_paragraphs(self, manifest):
        if isinstance(manifest, dict):
            self._write_json("paragraphs.json", manifest)
        else:
            self._write_json("paragraphs.json", sorted(manifest))

    def write_ontology(self, ontology):
        self._ontology = ontology
        self._write_json("ontology.json", ontology)

    def write_audit(self, report):
        self._audit = report
        self._write_json("audit.json", report)
        self._meta["audit_passed"] = bool(getattr(report, "passed", False))

    def write_forensic(self, findings: list):
        self._forensic = findings
        self._write_json("forensic.json", findings)

    def write_failure_artifact(self, data: dict):
        """현장 복구용 실패 진단 JSON. 어떤 단계에서, 어떤 scraper로,
        어떤 HTTP status/content-type/raw 응답을 만났는지 별도 보존한다."""
        from datetime import datetime, timezone

        payload = {"recorded_at": datetime.now(timezone.utc).isoformat(), **data}
        raw = payload.get("raw_excerpt")
        if isinstance(raw, str) and len(raw) > 800:
            payload["raw_excerpt"] = raw[:800] + "...(truncated)"
        self._write_json("failure.json", payload)
        self._meta["has_failure_artifact"] = True

    def write_lens_brief(self, markdown: str):
        (self.dir / "lens_brief.md").write_text(markdown or "", encoding="utf-8")
        self._artifacts.append("lens_brief.md")

    def write_draft(self, report, markdown: str):
        self._write_json("draft.json", report)
        (self.dir / "draft.md").write_text(markdown or "", encoding="utf-8")
        self._artifacts.append("draft.md")

    def write_draft_audit(self, report):
        self._draft_audit = report
        self._write_json("draft_audit.json", report)
        self._meta["draft_passed"] = bool(getattr(report, "passed", False))

    def write_review(self, report, markdown: str):
        self._review = report
        self._write_json("review.json", report)
        (self.dir / "review.md").write_text(markdown or "", encoding="utf-8")
        self._artifacts.append("review.md")
        self._meta["review_passed"] = bool(_field(report, "editor_decision", "Reject") in ("Accept", "Major Revision"))
        self._meta["review_score"] = int(_field(report, "final_score", 0))

    def write_lens_analysis(self, report, markdown: str):
        self._write_json("lens_analysis.json", report)
        (self.dir / "lens_analysis.md").write_text(markdown or "", encoding="utf-8")
        self._artifacts.append("lens_analysis.md")

    def write_lens_audit(self, report):
        self._lens_audit = report
        self._write_json("lens_audit.json", report)
        self._meta["lens_audit_passed"] = bool(getattr(report, "passed", False))

    def write_lens_critic(self, report, markdown: str, audit_report):
        self._write_json("lens_critic.json", report)
        (self.dir / "lens_critic.md").write_text(markdown or "", encoding="utf-8")
        self._artifacts.append("lens_critic.md")
        self._lens_critic_audit = audit_report
        self._write_json("lens_critic_audit.json", audit_report)
        self._meta["lens_critic_passed"] = bool(getattr(report, "passed", False))
        self._meta["lens_critic_audit_passed"] = bool(
            getattr(audit_report, "passed", False)
        )

    def _generate_markdown_report(self):
        status = self._meta.get("status", "unknown")
        audit_passed = self._meta.get("audit_passed")
        forensic_passed = self._meta.get("forensic_passed", None)
        artifacts = list(dict.fromkeys(self._artifacts))
        lines = [
            "# Omni-Academic Run Report",
            "",
            "## Executive Summary",
            f"- **Status**: `{str(status).upper()}`",
            f"- **Query / Document**: {self._meta['query']}",
            f"- **Lens**: `{self._meta['lens']}`",
            f"- **Mode**: {'Mock / offline ontology provider' if self._meta['mock'] else 'Live providers enabled'}",
            f"- **Audit**: `{str(audit_passed).upper()}`",
            f"- **Forensic Gate**: `{str(forensic_passed).upper() if forensic_passed is not None else 'NOT_RUN'}`",
        ]
        if self._meta.get("error_message"):
            lines.append(f"- **Error Message**: `{self._meta['error_message']}`")
        diagnostic = _failure_diagnostic(str(status), self._meta)
        if diagnostic:
            lines.extend(["", "## Failure Diagnostics"])
            lines.extend(diagnostic)
            if self._meta.get("has_failure_artifact"):
                lines.append(
                    "- **Raw Diagnostic**: see `failure.json` "
                    "(stage/scraper/HTTP status/content-type/raw excerpt)"
                )
        lines.extend([
            "",
            "## Provenance",
            f"- **Run ID**: `{self._meta['run_id']}`",
            f"- **Created At**: {self._meta['created_at']}",
            f"- **Git Commit**: `{self._meta.get('git_commit') or 'Unknown'}`",
            f"- **Run Directory**: `{self.dir}`",
            "",
            "### Artifacts",
        ])
        if artifacts:
            lines.extend(_artifact_link(name) for name in artifacts)
        else:
            lines.append("- No typed artifacts were written before report generation.")

        cache = self._meta.get("recon_cache") or {}
        if cache:
            lines.append("\n### Recon Cache")
            for client, info in cache.items():
                hit = bool((info or {}).get("hit"))
                age = (info or {}).get("age_sec")
                age_text = f", age={age}s" if age is not None else ""
                lines.append(f"- `{client}`: {'HIT' if hit else 'MISS'}{age_text}")

        lines.append("\n## Recon & Papers")
        if self._papers:
            for idx, p in enumerate(self._papers, 1):
                p_title = _paper_title(p)
                p_url = _field(p, "url", "")
                p_doi = _field(p, "doi", "")
                p_venue = _field(p, "venue", "")
                p_citations = _field(p, "citation_count", 0)
                p_abstract = _field(p, "abstract", "")
                lines.append(f"### [{idx}] {p_title}")
                lines.append(f"- **Authors**: {_authors(p)}")
                if p_venue:
                    lines.append(f"- **Venue**: {p_venue}")
                lines.append(f"- **Citations**: {p_citations}")
                if p_doi:
                    lines.append(f"- **DOI**: `{p_doi}`")
                if p_url:
                    lines.append(f"- **URL**: {p_url}")
                if p_abstract:
                    lines.append(f"- **Abstract**: {_truncate(p_abstract, 300)}")
        else:
            lines.append("No paper recon data captured in this run.")

        lines.append("\n## Ontology Map")
        if self._ontology:
            nodes = _field(self._ontology, "nodes", []) or []
            edges = _field(self._ontology, "edges", []) or []
            lines.append(f"Total Nodes: **{len(nodes)}** | Total Edges: **{len(edges)}**\n")
            
            lines.append("### Nodes")
            for n in nodes:
                n_id = _field(n, "id", "")
                n_label = _field(n, "label", "")
                n_class = _value(_field(n, "entity_class", ""))
                n_para = _field(n, "paragraph_id", "")
                n_quote = _field(n, "source_quote", "")
                line = f"- `[{n_id}]` **{n_label}** (Class: `{n_class}`, Paragraph: `{n_para}`)"
                if n_quote:
                    line += f" — \"{_truncate(n_quote, 140)}\""
                lines.append(line)

            lines.append("\n### Edges (Relations)")
            for e in edges:
                e_src = _field(e, "source_id", "")
                e_tgt = _field(e, "target_id", "")
                e_pred = _value(_field(e, "predicate", ""))
                e_reason = _field(e, "reasoning", "")
                e_quote = _field(e, "source_quote", "")
                lines.append(f"- `[{e_src}]` --(`{e_pred}`)--> `[{e_tgt}]`: {_truncate(e_reason, 220)}")
                if e_quote:
                    lines.append(f"  - Quote: \"{_truncate(e_quote, 160)}\"")
        else:
            lines.append("No ontology map generated in this run.")

        lines.append("\n## Audit & Forensics")
        if self._audit:
            passed = _field(self._audit, "passed", False)
            score = _field(self._audit, "score", 0)
            findings = _field(self._audit, "findings", []) or []
            lines.append(f"- **Status**: {'✅ PASSED' if passed else '❌ FAILED'}")
            lines.append(f"- **Audit Score**: `{score}/100`")
            if findings:
                lines.append("\n### Audit Findings")
                for finding in findings:
                    lines.append(_finding_line(finding))
            else:
                lines.append("- No audit findings.")
        else:
            lines.append("No audit report was run.")

        if self._forensic:
            lines.append("\n### Forensics (Gate 2)")
            for find in self._forensic:
                lines.append(_finding_line(find))
        else:
            lines.append("\n### Forensics (Gate 2)")
            lines.append("- Not run.")

        if self._lens_audit:
            passed = _field(self._lens_audit, "passed", False)
            score = _field(self._lens_audit, "score", 0)
            findings = _field(self._lens_audit, "findings", []) or []
            lines.append("\n### Lens Compliance (Gate 3)")
            lines.append(f"- **Status**: {'✅ PASSED' if passed else '❌ FAILED'}")
            lines.append(f"- **Score**: `{score}/100`")
            if findings:
                for finding in findings:
                    lines.append(_finding_line(finding))
            else:
                lines.append("- No lens compliance findings.")
        else:
            lines.append("\n### Lens Compliance (Gate 3)")
            lines.append("- Not run.")

        if self._lens_critic_audit:
            passed = _field(self._lens_critic_audit, "passed", False)
            score = _field(self._lens_critic_audit, "score", 0)
            findings = _field(self._lens_critic_audit, "findings", []) or []
            lines.append("\n### Lens Critic Audit")
            lines.append(f"- **Status**: {'✅ PASSED' if passed else '❌ FAILED'}")
            lines.append(f"- **Score**: `{score}/100`")
            if findings:
                for finding in findings:
                    lines.append(_finding_line(finding))
            else:
                lines.append("- No lens critic audit findings.")

        if self._draft_audit:
            passed = _field(self._draft_audit, "passed", False)
            score = _field(self._draft_audit, "score", 0)
            findings = _field(self._draft_audit, "findings", []) or []
            lines.append("\n### Draft Compliance")
            lines.append(f"- **Status**: {'✅ PASSED' if passed else '❌ FAILED'}")
            lines.append(f"- **Score**: `{score}/100`")
            if findings:
                for finding in findings:
                    lines.append(_finding_line(finding))
            else:
                lines.append("- No draft compliance findings.")

        if self._review:
            decision = _field(self._review, "editor_decision", "Reject")
            score = _field(self._review, "final_score", 0)
            summary = _field(self._review, "editor_summary", "")
            lines.append("\n### Peer Review Panel")
            lines.append(f"- **Verdict**: `{decision}`")
            lines.append(f"- **Score**: `{score}/100`")
            if summary:
                lines.append(f"- **Summary Synthesis**:\n  {_truncate(summary, 250)}")
            reviews = _field(self._review, "reviews", []) or []
            if reviews:
                for rev in reviews:
                    rev_name = _field(rev, "panelist", "")
                    rev_score = _field(rev, "score", 0)
                    lines.append(f"  - **{rev_name}**: `{rev_score}/100`")

        report_path = self.dir / "report.md"
        report_path.write_text("\n".join(lines), encoding="utf-8")
        self._artifacts.append("report.md")

    def finalize(self) -> Path:
        """manifest.json 기록 + SQLite 인덱스 등재. 런 디렉터리 경로 반환."""
        self._generate_markdown_report()
        artifacts = list(dict.fromkeys(self._artifacts))
        self._artifacts = artifacts
        self._meta["artifacts"] = artifacts
        self._meta["artifact_manifest"] = {
            name: _file_integrity(self.dir / name)
            for name in artifacts
        }
        manifest_path = self.dir / "manifest.json"
        manifest_path.write_text(
            json.dumps(self._meta, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._index()
        return self.dir

    def _index(self):
        db = self._base / "index.db"
        conn = sqlite3.connect(db)
        try:
            self._ensure_index_schema(conn)
            forensic = self._meta.get("forensic_passed")
            conn.execute(
                "INSERT OR REPLACE INTO runs ("
                "run_id, created_at, query, lens, mock, audit_passed, dir, "
                "status, forensic_passed, artifacts_count"
                ") VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    self._meta["run_id"],
                    self._meta["created_at"],
                    self._meta["query"],
                    self._meta["lens"],
                    1 if self._meta["mock"] else 0,
                    None if self._meta["audit_passed"] is None
                    else (1 if self._meta["audit_passed"] else 0),
                    str(self.dir),
                    self._meta.get("status", "unknown"),
                    None if forensic is None else (1 if forensic else 0),
                    len(self._artifacts),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _ensure_index_schema(conn: sqlite3.Connection):
        conn.execute(
            "CREATE TABLE IF NOT EXISTS runs ("
            "run_id TEXT PRIMARY KEY, created_at TEXT, query TEXT, "
            "lens TEXT, mock INTEGER, audit_passed INTEGER, dir TEXT)"
        )
        existing = {
            row[1] for row in conn.execute("PRAGMA table_info(runs)").fetchall()
        }
        additions = {
            "status": "TEXT",
            "forensic_passed": "INTEGER",
            "artifacts_count": "INTEGER",
        }
        for name, typ in additions.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE runs ADD COLUMN {name} {typ}")

