"""런 단위 산출물 영속화.

한 번의 가동 결과를 typed JSON 아티팩트로 `runs/<id>/` 에 떨군다.
manifest는 자기검증적이어야 한다 — mock 여부·git commit·audit 평결을
박아넣어, --mock 결과가 검증된 결과인 양 위장하는 것을 차단한다(헌법:
무손실·환각 차단). 외부 의존성 0개(stdlib json/sqlite3/subprocess).
"""

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

        report_path = self.dir / "report.md"
        report_path.write_text("\n".join(lines), encoding="utf-8")
        self._artifacts.append("report.md")

    def finalize(self) -> Path:
        """manifest.json 기록 + SQLite 인덱스 등재. 런 디렉터리 경로 반환."""
        self._generate_markdown_report()
        self._meta["artifacts"] = self._artifacts
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


def export_to_vault(store: RunStore, vault_path: str, *, ontology=None,
                     audit_report=None) -> Optional[Path]:
    """검증·승인된 산출물만 로컬 지식 저장소 Inbox/Drafts에 Markdown draft로 export.

    경로 추측 금지(헌법: 잘못된 위치 오염 방지) — vault_path 미지정/부재 시
    거부. mock이거나 audit 미통과면 거부(자기검증 원칙).
    """
    if not vault_path:
        raise ValueError(
            "export-vault: --vault-path 또는 ACADEMIC_VAULT_PATH가 필요합니다 "
            "(경로 추측 금지)."
        )
    vault = Path(vault_path)
    drafts = vault / "000 System" / "Inbox" / "Drafts"
    if not vault.is_dir():
        raise ValueError(f"export-vault: 로컬 저장소 경로가 존재하지 않습니다: {vault}")
    if store._meta["mock"]:
        raise ValueError("export-vault 거부: mock 런은 로컬 저장소에 승격 불가.")
    if store._meta.get("audit_passed") is not True:
        raise ValueError("export-vault 거부: audit 미통과 산출물은 승격 불가.")
    if store._meta.get("forensic_passed") is False:
        raise ValueError(
            "export-vault 거부: Gate 2 forensic 실패(유령 인용) 산출물은 승격 불가."
        )

    drafts.mkdir(parents=True, exist_ok=True)
    nodes = list(getattr(ontology, "nodes", []) or [])
    edges = list(getattr(ontology, "edges", []) or [])
    audit = audit_report or store._audit
    findings = _field(audit, "findings", []) if audit else []
    lines = [
        "---",
        "tags: [omni-academic, recon-output, draft]",
        f"created: {store._meta['created_at']}",
        f"run_id: {store._meta['run_id']}",
        f"git_commit: {store._meta.get('git_commit')}",
        "---",
        "",
        f"# Omni-Academic 산출물: {store._meta['query']}",
        "",
        f"- Lens: `{store._meta['lens']}`",
        f"- Audit: **{'PASSED' if store._meta.get('audit_passed') else 'N/A'}**",
        f"- Forensic: `{str(store._meta.get('forensic_passed', 'NOT_RUN')).upper()}`",
        f"- Ontology: {len(nodes)} nodes / {len(edges)} edges",
        f"- 원본 아티팩트: `{store.dir}`",
        "",
        "> [!note] 자동 생성 draft. 검토 후 로컬 지식 저장소의 정식 위치로 승격하십시오.",
    ]
    if nodes:
        lines.extend(["", "## Ontology Nodes"])
        for n in nodes[:20]:
            n_label = _field(n, "label", "")
            n_class = _value(_field(n, "entity_class", ""))
            n_para = _field(n, "paragraph_id", "")
            n_quote = _field(n, "source_quote", "")
            line = f"- **{n_label}** (`{n_class}`, `{n_para}`)"
            if n_quote:
                line += f": \"{_truncate(n_quote, 160)}\""
            lines.append(line)
        if len(nodes) > 20:
            lines.append(f"- ... {len(nodes) - 20} more nodes in `ontology.json`")

    if edges:
        lines.extend(["", "## Ontology Relations"])
        for e in edges[:20]:
            e_src = _field(e, "source_id", "")
            e_tgt = _field(e, "target_id", "")
            e_pred = _value(_field(e, "predicate", ""))
            e_reason = _field(e, "reasoning", "")
            lines.append(f"- `[{e_src}]` --(`{e_pred}`)--> `[{e_tgt}]`: {_truncate(e_reason, 180)}")
        if len(edges) > 20:
            lines.append(f"- ... {len(edges) - 20} more edges in `ontology.json`")

    lines.extend(["", "## Audit Findings"])
    if findings:
        lines.extend(_finding_line(f) for f in findings[:20])
        if len(findings) > 20:
            lines.append(f"- ... {len(findings) - 20} more findings in `audit.json`")
    else:
        lines.append("- No audit findings.")

    lines.extend([
        "",
        "## Source Artifacts",
        f"- Report: `{store.dir / 'report.md'}`",
        f"- Manifest: `{store.dir / 'manifest.json'}`",
        f"- Ontology: `{store.dir / 'ontology.json'}`",
        f"- Audit: `{store.dir / 'audit.json'}`",
    ])
    safe_run_id = re.sub(r"[\\/]+", "__", store._meta["run_id"])
    out = drafts / f"{safe_run_id}.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    return out
