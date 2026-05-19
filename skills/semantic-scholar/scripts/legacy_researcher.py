import os
import json
import re
import time
import requests
from pathlib import Path
from typing import List, Dict, Any, Optional
import chromadb
from sentence_transformers import SentenceTransformer

class ResearcherAgent:
    """
    수석연구원 (Researcher)
    - ChromaDB 기반 의미 검색 (Semantic Search)
    - JSON Archive 기반 표제어 검색 (Lemma Search)
    - Semantic Scholar 기반 외부 학술 검색 (External Search)
    - Triple-Search 프로토콜 통합 보고
    """
    
    def __init__(self, db_path: Optional[str] = None, archive_path: Optional[str] = None):
        self.name = "Researcher"
        
        # 경로 설정
        self.db_path = db_path or self._discover_db_path()
        self.archive_path = archive_path or self._discover_archive_path()
        
        # 모델 로딩 (DB 차원 384 매칭, 다국어 지원)
        self.model = SentenceTransformer('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')
        
        # ChromaDB 클라이언트 초기화
        self.collection = None
        self._init_chroma()
        
        # 신학 용어 사전 로딩
        self.glossary = self._load_glossary()

    def _discover_db_path(self):
        script_dir = Path(__file__).parent.parent
        rel_path = script_dir.parent / "Theology_Project.nosync" / "vector_db"
        if rel_path.exists():
            return str(rel_path.absolute())
        return "/Users/msn/Desktop/MS_Dev.nosync/data/Theology_Project.nosync/vector_db"

    def _discover_archive_path(self):
        script_dir = Path(__file__).parent.parent
        rel_path = script_dir.parent / "Theology_Project.nosync" / "archive"
        if rel_path.exists():
            return rel_path
        return Path("/Users/msn/Desktop/MS_Dev.nosync/data/Theology_Project.nosync/archive")

    def _init_chroma(self):
        if os.path.exists(self.db_path):
            try:
                client = chromadb.PersistentClient(path=self.db_path)
                self.collection = client.get_collection(name="theology_library")
                print(f"✅ [{self.name}] ChromaDB 연결 성공")
            except Exception as e:
                print(f"⚠️ [{self.name}] ChromaDB 연결 실패: {e}")

    def _retry_request(self, url: str, params: Dict[str, Any], max_retries: int = 3) -> Optional[Dict[str, Any]]:
        """API 요청 재시도 헬퍼"""
        for i in range(max_retries):
            try:
                response = requests.get(url, params=params, timeout=10)
                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 429:
                    wait_time = (i + 1) * 2  # 짧은 백오프
                    print(f"⏳ [{self.name}] API Rate Limit (429). 대기 {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    print(f"⚠️ [{self.name}] API Error {response.status_code}: {response.text}")
                    return None
            except Exception as e:
                print(f"⚠️ [{self.name}] Request Exception: {e}")
                time.sleep(1)
        return None

    def search_semantic_scholar(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Semantic Scholar 외부 학술 검색"""
        print(f"🌐 [{self.name}] Semantic Scholar 검색 중: {query}")
        
        # 1. Paper Search
        url = "https://api.semanticscholar.org/graph/v1/paper/search"
        params = {
            "query": query,
            "fields": "paperId,title,authors,year,citationCount,abstract",
            "limit": 5
        }
        data = self._retry_request(url, params)
        
        results = []
        if not data or data['total'] == 0:
            return results

        candidates = data['data']
        selected_seed = candidates[0] # 가장 상위 결과 사용
        
        # Seed 논문 결과 추가
        results.append({
            "title": selected_seed.get('title'),
            "year": selected_seed.get('year'),
            "authors": [a['name'] for a in selected_seed.get('authors', [])],
            "abstract": selected_seed.get('abstract'),
            "citations": selected_seed.get('citationCount'),
            "type": "semantic_scholar_seed",
            "paperId": selected_seed['paperId']
        })

        # 2. Recommendations (유사 논문 확장)
        recs_url = f"https://api.semanticscholar.org/recommendations/v1/papers/forpaper/{selected_seed['paperId']}"
        recs_params = {
            "fields": "paperId,title,authors,year,citationCount,abstract",
            "limit": limit
        }
        recs_data = self._retry_request(recs_url, recs_params)
        
        if recs_data and 'recommendedPapers' in recs_data:
            print(f"✨ [{self.name}] 추천 논문 {len(recs_data['recommendedPapers'])}개 발견")
            for paper in recs_data['recommendedPapers']:
                results.append({
                    "title": paper.get('title'),
                    "year": paper.get('year'),
                    "authors": [a['name'] for a in paper.get('authors', [])],
                    "citations": paper.get('citationCount'),
                    "type": "semantic_scholar_recommendation",
                    "paperId": paper['paperId']
                })
                
        return results

    def search_semantic(self, query: str, n_results: int = 5, source_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """ChromaDB 의미 검색"""
        if not self.collection:
            return []
            
        print(f"🔍 [{self.name}] 의미 검색 중: {query} (Source: {source_filter or 'All'})")
        query_vec = self.model.encode([query]).tolist()
        
        where_clause = {}
        if source_filter:
            # ChromaDB where filter
            where_clause = {"source": {"$contains": source_filter}} if "$" not in source_filter else {"source": source_filter}
            # Note: ChromaDB basic filtering. Assuming exact match or simpler logic.
            # Using simple exact match or $eq is safer if metadata is clean.
            # Let's try simple exact match logic first, or allow users to pass partial?
            # Creating a robust filter: if "RGG" is passed, we might want contains logic if keys are "RGG_Vol1".
            # However, Chroma current version might be strict.
            # safe assumption: use the filter dictionary directly if provided.
            where_clause = {"source": source_filter}

        # If source filter is partial (like "RGG"), but data is "RGG_Vol7", exact match fails.
        # But for now let's implement exact match or let the user handle it.
        # Upgrading simple implementation to accept where clause logic if complicated? 
        # No, let's keep it simple: Exact match on 'source' field often expected.
        # But wait, earlier rgg_rag.py analysis showed "source": "RGG_Vol7".
        # So "RGG" query won't match "RGG_Vol7" with simple {"source": "RGG"}.
        # We need processing.
        
        # NOTE: ChromaDB filter operators: $eq, $ne, $gt, $gte, $lt, $lte, $in, $nin
        # It does NOT verify substring ($contains) in standard release easily without special config or $like (some versions).
        # Let's do post-filtering if metadata is complex, or rely on $in if we can guess.
        # Actually, let's try WITHOUT the where clause first for broad fetch, OR use the logic from rgg_rag.py (fetch more, filter python side) 
        # to ensure we don't break on specific version limitations.
        # BUT efficiency matters. 
        # Better strategy: Fetch more results, then filter in Python if filter is requested.
        
        if source_filter:
             # Fetch more to allow for filtering
             n_results_fetch = n_results * 5
        else:
             n_results_fetch = n_results

        try:
            results = self.collection.query(
                query_embeddings=query_vec,
                n_results=n_results_fetch,
                # where=where_clause if source_filter else None # Skip DB-side filter to be safe against partial matches
            )
        except Exception as e:
            print(f"⚠️ Chroma Query Error: {e}")
            return []
        
        formatted = []
        if results['documents'] and results['documents'][0]:
            for i, doc in enumerate(results['documents'][0]):
                meta = results['metadatas'][0][i]
                
                # Manual Filter Logic
                if source_filter:
                    src = meta.get("source", "")
                    if source_filter.upper() not in src.upper():
                        continue
                        
                formatted.append({
                    "text": doc,
                    "metadata": meta,
                    "type": "semantic"
                })
                if len(formatted) >= n_results:
                    break
                    
        return formatted

    def search_lemma(self, lemma: str, dict_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """JSON Archive 표제어 검색"""
        print(f"📖 [{self.name}] 표제어 검색 중: {lemma}")
        # ... (Legacy logic maintained, but not heavily used here)
        # Using dict_query tool might be better, but implementing basic fallback:
        results = []
        
        index_file = self.archive_path / "lemma_index.json"
        if index_file.exists():
            with open(index_file, "r", encoding="utf-8") as f:
                index = json.load(f)
            
            query_norm = lemma.strip().lower()
            matches = index.get(query_norm, [])
            
            for match in matches:
                # Filter by dict_name if provided
                if dict_name:
                    if dict_name.lower() not in match["file"].lower():
                         continue

                results.append({
                    "lemma": lemma,
                    "source": match["file"],
                    "page": match.get("page", "?"),
                    "type": "lemma",
                    "file_path": str(self.archive_path / match["file"])
                })
        
        return results[:10]

    
    # 3중 언어 확장을 위한 신학 용어 사전 (PoC)
    def _load_glossary(self) -> Dict[str, Dict[str, str]]:
        """신학 용어 사전 로딩 (JSON)"""
        # 경로 탐색
        script_dir = Path(__file__).parent.parent
        # 우선순위 1: 상대 경로 (MS_Dev/data/...)
        candidates = [
            script_dir / "data" / "Theology_Project.nosync" / "theological_glossary.json",
            # 우선순위 2: 절대 경로 (Fallback)
            Path("/Users/msn/Desktop/MS_Dev.nosync/data/Theology_Project.nosync/theological_glossary.json")
        ]
        
        for p in candidates:
            if p.exists():
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        print(f"📚 [{self.name}] 신학 용어 사전 로드: {p.name}")
                        return json.load(f)
                except Exception as e:
                    print(f"⚠️ [{self.name}] 용어 사전 로드 실패: {e}")
                    return {}
        
        print(f"⚠️ [{self.name}] 신학 용어 사전을 찾을 수 없습니다.")
        return {}

    def _expand_query(self, query: str) -> List[str]:
        """한국어 쿼리를 3개국어로 확장 (JSON 사전 기반)"""
        if not self.glossary:
            return [query]

        # 1. 사전에 있는 정확한 키워드 매칭 확인
        for key, langs in self.glossary.items():
            if key in query:
                # 쿼리에 키워드가 포함된 경우 (예: "바르트의 칭의론")
                # 단순 치환으로 확장 시도 (간이 로직)
                # 정밀 로직: "칭의" -> ["칭의", "Justification", "Rechtfertigung"]
                # 복합어 처리는 복잡하므로, 우선 키워드 자체만 확장해서 리스트업
                return [query, langs['en'], langs['de']]
        
        # 매칭되는 게 없으면 원본만 반환
        return [query]

    def unified_search(self, query: str, source: Optional[str] = None, include_external: bool = False) -> Dict[str, Any]:
        """
        통합 Triple-Search (Semantic + Lemma + External)
        + Tri-lingual Strategy (3중 언어 확장)
        """
        queries = self._expand_query(query)
        print(f"🚀 [{self.name}] Unified Search 수행 (확장됨): {queries} (Source: {source}, External: {include_external})")
        
        all_results = {
            "query": query,
            "expanded_queries": queries,
            "semantic": [],
            "lemma": [],
            "external_scholar": []
        }
        
        # 결과 중복 방지를 위한 ID 추적
        seen_semantic = set()
        seen_lemma = set()
        seen_external = set()

        for q in queries:
            print(f"  👉 Sub-query: '{q}'")
            
            # 1. Semantic Search
            sem_res = self.search_semantic(q, source_filter=source)
            for r in sem_res:
                # ChromaDB ID가 있으면 좋지만 현재 로직상 메타데이터 텍스트 해시 등을 써야 함.
                # 간단히 title or unique snippet prefix로 중복 체크
                sig = r['metadata'].get('source', '') + str(r['metadata'].get('page', ''))
                if sig not in seen_semantic:
                    all_results["semantic"].append(r)
                    seen_semantic.add(sig)

            # 2. Lemma Search (한국어 아니면 효과 적을 수 있으나 수행)
            lem_res = self.search_lemma(q, dict_name=source)
            for r in lem_res:
                sig = r['source'] + str(r['page'])
                if sig not in seen_lemma:
                    all_results["lemma"].append(r)
                    seen_lemma.add(sig)

            # 3. External Search (한 번에 3개 언어 다 던지면 API 호출량 증가하므로 중요)
            if include_external:
                ext_res = self.search_semantic_scholar(q)
                for r in ext_res:
                    pid = r.get('paperId')
                    if pid and pid not in seen_external:
                        all_results["external_scholar"].append(r)
                        seen_external.add(pid)
        
        return all_results

if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="ARC Secretariat - Researcher Agent")
    parser.add_argument("--query", "-q", type=str, required=False, help="Unified Search Query")
    parser.add_argument("--file", "-f", type=str, help="Load queries from a file (one query per line)")
    parser.add_argument("--source", "-s", type=str, help="Filter by Source (e.g., RGG, KD)")
    parser.add_argument("--semantic", action="store_true", help="Perform semantic search only")
    parser.add_argument("--lemma", action="store_true", help="Perform lemma search only")
    parser.add_argument("--external", action="store_true", help="Include Semantic Scholar external results")
    parser.add_argument("--semantic-api", action="store_true", help="Alias for --external")
    
    args = parser.parse_args()
    
    if not args.query and not args.file:
        print("❌ Error: Either --query or --file must be provided.")
        exit(1)

    res = ResearcherAgent()
    include_ext = args.external or args.semantic_api
    
    # 쿼리 리스트 준비
    queries = []
    if args.file:
        fpath = Path(args.file)
        if fpath.exists():
            with open(fpath, "r", encoding="utf-8") as f:
                queries = [line.strip() for line in f if line.strip() and not line.startswith("#")]
            print(f"📂 [{res.name}] Loading {len(queries)} queries from {fpath.name}")
        else:
            print(f"❌ Error: File not found: {args.file}")
            exit(1)
    
    if args.query:
        queries.insert(0, args.query)
        
    # 배치 실행
    final_results = {}
    
    for i, q in enumerate(queries):
        if len(queries) > 1:
            print(f"\n🔹 Processing [{i+1}/{len(queries)}]: {q}")
            
        if args.semantic and not args.lemma:
            r = {"semantic": res.search_semantic(q, source_filter=args.source)}
        elif args.lemma and not args.semantic:
            r = {"lemma": res.search_lemma(q, dict_name=args.source)}
        else:
            r = res.unified_search(q, source=args.source, include_external=include_ext)
            
        final_results[q] = r
        
    print(json.dumps(final_results, ensure_ascii=False, indent=2))
