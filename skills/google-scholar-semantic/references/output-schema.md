# Google Scholar Semantic Output Schema

`scholar_runner.py` writes one JSON object per line. Fields may be empty when Scholar Labs omits metadata or citation extraction fails.

## Required Fields

- `id`: stable 16-character SHA-1 prefix from query, title, and URL.
- `record_type`: always `scholar_result`.
- `source`: always `google_scholar_labs`.
- `query`: normalized query that produced the result.
- `rank`: result rank within parsed records.
- `title`: result title.
- `url`: result URL, if available.
- `authors_text`: raw author string from Scholar metadata.
- `authors`: parsed author list when available.
- `year`: publication year as integer or `null`.
- `venue`: venue/journal/book metadata when parseable.
- `publisher`: publisher metadata when parseable.
- `raw_meta`: raw Scholar metadata line.
- `snippet`: Scholar snippet or parsed text excerpt.
- `citation_count`: integer count parsed from `Cited by` / `인용`.
- `document_type`: Scholar document type label without brackets.
- `source_file`: HTML/text capture file that produced the record.
- `retrieved_at`: parser timestamp in ISO format.
- `parser`: parser path used for the record.

## Citation Fields

- `citation`: primary formatted citation, usually APA when Scholar provides the standard row order.
- `citation_variants`: all formatted citation rows captured from the citation modal.
- `citation_links`: citation export links such as BibTeX, EndNote, RefMan, or RefWorks.
- `citation_status`: `ok`, `empty`, `missing_button`, or `error:<ExceptionName>`.

Treat records with `citation_status != "ok"` as incomplete bibliography evidence and retry or flag them in the final report.
