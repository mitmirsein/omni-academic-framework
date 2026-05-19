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
        run_id = f"{prefix}{ts}-{_slug(query)}"
        base_path = Path(base)
        run_dir = base_path / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
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
        lines = [
            "# Omni-Academic Run Report",
            f"- **Run ID**: `{self._meta['run_id']}`",
            f"- **Query / Document**: {self._meta['query']}",
            f"- **Lens**: `{self._meta['lens']}`",
            f"- **Mock Mode**: {'Yes (Offline Mock)' if self._meta['mock'] else 'No (Live API/LLM)'}",
            f"- **Run Status**: `{self._meta.get('status', 'unknown').upper()}`",
        ]
        if self._meta.get("error_message"):
            lines.append(f"- **Error Message**: `{self._meta['error_message']}`")
        lines.extend([
            f"- **Created At**: {self._meta['created_at']}",
            f"- **Git Commit**: `{self._meta.get('git_commit') or 'Unknown'}`",
            f"- **Audit Passed**: **{str(self._meta.get('audit_passed')).upper()}**",
            "",
            "## 🔍 Recon & Papers Summary",
        ])
        if self._papers:
            for idx, p in enumerate(self._papers, 1):
                p_title = getattr(p, "title", p.get("title") if isinstance(p, dict) else str(p))
                p_authors = getattr(p, "authors", p.get("authors") if isinstance(p, dict) else [])
                p_url = getattr(p, "url", p.get("url") if isinstance(p, dict) else "")
                p_doi = getattr(p, "doi", p.get("doi") if isinstance(p, dict) else "")
                lines.append(f"### [{idx}] {p_title}")
                lines.append(f"- **Authors**: {', '.join(p_authors) if p_authors else '저자 미상'}")
                if p_doi:
                    lines.append(f"- **DOI**: `{p_doi}`")
                if p_url:
                    lines.append(f"- **URL**: {p_url}")
        else:
            lines.append("No paper recon data captured in this run.")

        lines.append("\n## 🕸️ Extracting Ontology Map")
        if self._ontology:
            nodes = getattr(self._ontology, "nodes", []) or (self._ontology.get("nodes", []) if isinstance(self._ontology, dict) else [])
            edges = getattr(self._ontology, "edges", []) or (self._ontology.get("edges", []) if isinstance(self._ontology, dict) else [])
            lines.append(f"Total Nodes: **{len(nodes)}** | Total Edges: **{len(edges)}**\n")
            
            lines.append("### Nodes")
            for n in nodes:
                n_id = getattr(n, "id", n.get("id") if isinstance(n, dict) else "")
                n_label = getattr(n, "label", n.get("label") if isinstance(n, dict) else "")
                n_class = getattr(n, "entity_class", n.get("entity_class") if isinstance(n, dict) else "")
                n_para = getattr(n, "paragraph_id", n.get("paragraph_id") if isinstance(n, dict) else "")
                lines.append(f"- `[{n_id}]` **{n_label}** (Class: `{n_class}`, Paragraph: `{n_para}`)")

            lines.append("\n### Edges (Relations)")
            for e in edges:
                e_src = getattr(e, "source_id", e.get("source_id") if isinstance(e, dict) else "")
                e_tgt = getattr(e, "target_id", e.get("target_id") if isinstance(e, dict) else "")
                e_pred = getattr(e, "predicate", e.get("predicate") if isinstance(e, dict) else "")
                e_reason = getattr(e, "reasoning", e.get("reasoning", "") if isinstance(e, dict) else "")
                lines.append(f"- `[{e_src}]` --(`{e_pred}`)--> `[{e_tgt}]` : {e_reason}")
        else:
            lines.append("No ontology map generated in this run.")

        lines.append("\n## 🛡️ Audit & Forensics Report")
        if self._audit:
            passed = getattr(self._audit, "passed", self._audit.get("passed", False) if isinstance(self._audit, dict) else False)
            score = getattr(self._audit, "score", self._audit.get("score", 0) if isinstance(self._audit, dict) else 0)
            logs = getattr(self._audit, "logs", self._audit.get("logs", []) if isinstance(self._audit, dict) else [])
            lines.append(f"- **Status**: {'✅ PASSED' if passed else '❌ FAILED'}")
            lines.append(f"- **Audit Score**: `{score}/100`")
            if logs:
                lines.append("\n### Audit Logs")
                for log in logs:
                    lines.append(f"- {log}")
        else:
            lines.append("No audit report was run.")

        if self._forensic:
            lines.append("\n### Forensics (Gate 2)")
            for find in self._forensic:
                f_idx = find.get("index") if isinstance(find, dict) else getattr(find, "index", "")
                f_title = find.get("title") if isinstance(find, dict) else getattr(find, "title", "")
                f_status = find.get("status") if isinstance(find, dict) else getattr(find, "status", "")
                f_err = find.get("error") if isinstance(find, dict) else getattr(find, "error", "")
                lines.append(f"- Paper `[{f_idx}]` **{f_title}**: Status `{f_status}` {f'({f_err})' if f_err else ''}")

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
            conn.execute(
                "CREATE TABLE IF NOT EXISTS runs ("
                "run_id TEXT PRIMARY KEY, created_at TEXT, query TEXT, "
                "lens TEXT, mock INTEGER, audit_passed INTEGER, dir TEXT)"
            )
            conn.execute(
                "INSERT OR REPLACE INTO runs VALUES (?,?,?,?,?,?,?)",
                (
                    self._meta["run_id"],
                    self._meta["created_at"],
                    self._meta["query"],
                    self._meta["lens"],
                    1 if self._meta["mock"] else 0,
                    None if self._meta["audit_passed"] is None
                    else (1 if self._meta["audit_passed"] else 0),
                    str(self.dir),
                ),
            )
            conn.commit()
        finally:
            conn.close()


def export_to_vault(store: RunStore, vault_path: str, *, ontology=None,
                     audit_report=None) -> Optional[Path]:
    """검증·승인된 산출물만 볼트 Inbox/Drafts에 Markdown draft로 export.

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
        raise ValueError(f"export-vault: 볼트 경로가 존재하지 않습니다: {vault}")
    if store._meta["mock"]:
        raise ValueError("export-vault 거부: mock 런은 볼트에 승격 불가.")
    if store._meta.get("audit_passed") is not True:
        raise ValueError("export-vault 거부: audit 미통과 산출물은 승격 불가.")
    if store._meta.get("forensic_passed") is False:
        raise ValueError(
            "export-vault 거부: Gate 2 forensic 실패(유령 인용) 산출물은 승격 불가."
        )

    drafts.mkdir(parents=True, exist_ok=True)
    n_nodes = len(getattr(ontology, "nodes", []) or [])
    n_edges = len(getattr(ontology, "edges", []) or [])
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
        f"- Ontology: {n_nodes} nodes / {n_edges} edges",
        f"- 원본 아티팩트: `{store.dir}`",
        "",
        "> [!note] 자동 생성 draft. 검토 후 볼트 정식 위치로 승격하십시오.",
    ]
    out = drafts / f"{store._meta['run_id']}.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    return out
