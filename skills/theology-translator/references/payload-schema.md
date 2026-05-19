# Reformed Translation Pipeline: Payload Schema (Author Mode)

> **출처**: `reformed-translation-pipeline` v3.1에서 이식 (2026-04-17)
> theology-translator의 "Author Mode" 활성화 시 사용하는 입력 스키마.

신학적 고위험 텍스트(바르트, 본회퍼 등 특정 저자의 1차 문헌) 번역의 정밀도를 보장하기 위해 다음 JSON 구조를 입력으로 사용합니다.

```json
{
  "project_id": "string (e.g., barth_cd_1_1)",
  "metadata": {
    "author": "string (e.g., 'Karl Barth')",
    "book_title": "string (e.g., 'Der Römerbrief')",
    "edition": "string (optional, e.g., '2nd Edition 1922')",
    "year": "integer (e.g., 1922)",
    "category": "string (e.g., 'Dogmatics', 'Sermon', 'Letters')",
    "historical_context": "string (Optional: e.g., 'Dialogue with Liberal Theology')",
    "style_tuner": {
        "fidelity_level": "string (Literal | Liberal)",
        "tone_weight": "string (Heavy | Light)",
        "vocabulary_set": "string (Dogmatics | Pastoral)",
        "sentence_length": "string (Preserve | Break)"
    }
  },
  "source_text": "string (The raw text to translate)",
  "source_image": "string (Optional: Path to image for OCR-ready translation)",
  "multimodal_mode": "boolean",
  "output_format": {
      "include_page_numbers": "boolean",
      "page_marker_style": "string (default: '[p. {n}]')"
  }
}
```

## Field Descriptions
- **historical_context**: 번역 시 단어의 뉘앙스를 결정하는 핵심 지표 (예: 'Dialectical Crisis').
- **style_tuner**: 원문의 문장 구조를 보존할지(`Preserve`), 가독성을 위해 끊어 읽을지(`Break`) 결정.
- **multimodal_mode**: `true`일 경우 `source_image`로부터 OCR 추출 후 번역을 수행.

---
*Migrated from reformed-translation-pipeline v3.1 → theology-translator v5.1*
