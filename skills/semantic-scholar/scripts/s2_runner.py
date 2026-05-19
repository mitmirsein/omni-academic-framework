import argparse
import requests
import time
import json
import os
from datetime import datetime
from dotenv import load_dotenv
from pathlib import Path

# .env 경로 규약: OMNI_ENV_FILE > repo 루트 .env > 기본 탐색 (하드코딩 금지)
_env = os.environ.get("OMNI_ENV_FILE", "").strip()
if not _env:
    _repo_env = Path(__file__).resolve().parents[3] / ".env"
    _env = str(_repo_env) if _repo_env.is_file() else ""
load_dotenv(_env) if _env else load_dotenv()
API_KEY = os.getenv("SEMANTIC_SCHOLAR_API_KEY")
BASE_URL = "https://api.semanticscholar.org/graph/v1"

def authenticated_get(url, params):
    """Semantic Scholar API 호출 (인증 포함)"""
    headers = {}
    if API_KEY:
        headers['x-api-key'] = API_KEY
    
    response = requests.get(url, headers=headers, params=params)
    
    if response.status_code == 429:
        print("[!] Rate limit exceeded. Waiting 3 seconds...")
        time.sleep(3)
        return authenticated_get(url, params)
    elif response.status_code != 200:
        print(f"[!] Error {response.status_code}: {response.text}")
        return None
    
    return response.json()

def search_papers(query, limit=10, silent=False, fields_of_study=None):
    """키워드 검색. silent=True 시 진단 메시지를 stderr로 라우팅 (JSON 모드 연동용).
    
    Args:
        fields_of_study: S2 fieldsOfStudy 필터 (예: "Philosophy,Religious Studies").
                         지정 시 해당 분야 논문만 반환하여 무관 도메인 유입 차단.
    """
    import sys as _sys
    url = f"{BASE_URL}/paper/search"
    params = {
        "query": query,
        "limit": limit,
        "fields": "title,authors,year,abstract,citationCount,venue,url,openAccessPdf"
    }
    # 도메인 필터: 법률·의학 등 무관 분야 논문 유입 차단
    if fields_of_study:
        params["fieldsOfStudy"] = fields_of_study
    
    filter_msg = f" [domain: {fields_of_study}]" if fields_of_study else ""
    msg = f"[*] Searching Semantic Scholar for: '{query}'{filter_msg}"
    if silent:
        print(msg, file=_sys.stderr)
    else:
        print(msg)
    data = authenticated_get(url, params)
    
    if data and 'data' in data:
        return data['data']
    return []

def format_report(results, query):
    """마크다운 리포트 생성"""
    date_str = datetime.now().strftime("%Y-%m-%d")
    
    md_content = f"# 🔬 Semantic Scholar Recon: {query}\n\n"
    md_content += f"> **Query**: {query}\n"
    md_content += f"> **Date**: {date_str}\n"
    md_content += f"> **Results**: {len(results)} papers found.\n\n"
    md_content += "---\n\n"
    
    for paper in results:
        title = paper.get('title', 'Unknown Title')
        year = paper.get('year', 'Unknown Year')
        authors = ", ".join([a['name'] for a in paper.get('authors', [])]) if paper.get('authors') else "Unknown"
        venue = paper.get('venue', 'N/A')
        citations = paper.get('citationCount', 0)
        url = paper.get('url', '')
        abstract = paper.get('abstract', 'No abstract available.')
        
        pdf_info = paper.get('openAccessPdf')
        pdf_link = pdf_info.get('url') if pdf_info else ""
        
        md_content += f"### {title} ({year})\n"
        md_content += f"- **Authors**: {authors}\n"
        md_content += f"- **Citations**: {citations}\n"
        md_content += f"- **Venue**: {venue}\n"
        md_content += f"- **Link**: [Semantic Scholar]({url})\n"
        md_content += f"- **PDF**: [Open Access]({pdf_link})\n"
        md_content += f"#### Abstract\n{abstract}\n\n"
        md_content += "---\n\n"
        
    return md_content

def main():
    parser = argparse.ArgumentParser(description="Semantic Scholar API Recon Tool")
    parser.add_argument("--query", "-q", required=True, help="Search query string")
    parser.add_argument("--limit", "-l", type=int, default=10, help="Maximum number of results to fetch")
    parser.add_argument("--output", "-o", help="Output Markdown file path (optional)")
    parser.add_argument("--format", "-f", choices=["markdown", "json"], default="markdown",
                        help="출력 형식: markdown(기본) 또는 json(프로그래밍 연동용)")
    parser.add_argument("--fields", default=None,
                        help="S2 fieldsOfStudy 필터 (예: 'Philosophy,Religious Studies'). 무관 도메인 차단용.")

    args = parser.parse_args()
    
    if not API_KEY:
        print("[!] WARNING: SEMANTIC_SCHOLAR_API_KEY is not set in .env")
        print("    Requests will be rate-limited to 1 per 3 seconds.")
    
    results = search_papers(args.query, args.limit, silent=(args.format == "json"),
                            fields_of_study=args.fields)

    if not results:
        if args.format == "json":
            # JSON 모드: 빈 배열 출력 (연동 에러 방지)
            print(json.dumps({"query": args.query, "results": [], "count": 0}, ensure_ascii=False))
        else:
            print("[-] No results found.")
        return

    # --- JSON 출력 모드 (review_engine.py 등 프로그래밍 연동용) ---
    if args.format == "json":
        output_data = {
            "query": args.query,
            "count": len(results),
            "results": [
                {
                    "title":        p.get("title", ""),
                    "year":         p.get("year"),
                    "authors":      [a["name"] for a in p.get("authors", [])],
                    "venue":        p.get("venue", ""),
                    "citations":    p.get("citationCount", 0),
                    "url":          p.get("url", ""),
                    "abstract":     p.get("abstract", ""),
                    "pdf_url":      (p.get("openAccessPdf") or {}).get("url", "")
                }
                for p in results
            ]
        }
        print(json.dumps(output_data, ensure_ascii=False, indent=2))
        return

    # --- Markdown 출력 모드 (기본) ---
    report_md = format_report(results, args.query)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(report_md)
        print(f"[+] Report saved to: {out_path}")
    else:
        print("\n" + "="*50)
        print(report_md)
        print("="*50)

if __name__ == "__main__":
    main()
