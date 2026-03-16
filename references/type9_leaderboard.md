# Type 9: LLM Leaderboard Analysis Pipeline

Multi-source AI model leaderboard scraping → cross-platform comparison → 8-dimension Word report.

## Data Sources

| Source | Method | Content |
|--------|--------|---------|
| LMArena (arena.ai) | HTML table parsing (BeautifulSoup) | Elo ratings for Text / Text-to-Image / Text-to-Video / Image-to-Video |
| ArtificialAnalysis.ai | Next.js RSC flight request (`RSC: 1` header) | Elo ratings + pricing + open_weights flag |
| SuperCLUE (superclueai.com) | Vue JS bundle inline data extraction | Median scores for 7 tracks (text-to-image/video, image edit, TTS, etc.) |

### Shared Tracks (3 sources all cover)

| Track | LMArena key | AA key | SuperCLUE key |
|-------|-------------|--------|---------------|
| 文生图 (Text-to-Image) | `text_to_image` | `text_to_image` | `text_to_image` |
| 文生视频 (Text-to-Video) | `text_to_video` | `text_to_video` | `text_to_video` |
| 图生视频 (Image-to-Video) | `image_to_video` | `image_to_video` | `image_to_video` |

### Exclusive Tracks

- **LMArena only**: Text (文本对话)
- **SuperCLUE only**: Image Edit, TTS, Ref-to-Video, Web Coding

## Pipeline

### Step 1: Scrape All Sources

```python
from collect_leaderboard import scrape_all_sources

# Scrape all 3 sources, save CSV files to data/ directory
results = scrape_all_sources(date_str="20260312")
# results = {"lm": {track: [rows]}, "aa": {...}, "sc": {...}}
```

Each scraper module handles its source independently:

1. **LMArena**: `GET https://arena.ai/leaderboard/{category}` → BeautifulSoup parse `<table>` rows
2. **ArtificialAnalysis**: `GET` with `RSC: 1` + `Next-Url` headers → parse RSC flight JSON → deduplicate by `values.id`
3. **SuperCLUE**: GET homepage → extract `vue-vendor-{hash}.js` URL → download JS → regex extract inline data → split by `rank=1` into 7 tracks

### Step 2: Cross-Source Analysis

```python
from analyze_leaderboard import run_analysis

analysis = run_analysis(date_str="20260312")
```

Analysis produces 6 dimensions from the raw data:

1. **Cross-source comparison**: For each shared track, match models across sources via fuzzy name matching (`SequenceMatcher > 0.8`), produce unified ranking
2. **Vendor panorama**: Aggregate all vendors across all tracks/sources, count entries and best ranks
3. **Exclusive track summary**: Top 10 for each source-exclusive track
4. **Tech barriers**: Open-source vs closed-source breakdown (uses AA's `is_open_weights` field)
5. **Opportunity screening**: Score vendors by: Chinese vendor (+3), multi-track coverage (+2), top rank (+3/+2), high entry count (+2). Threshold ≥ 3
6. **Gemini narrative insights**: Feed all data to Gemini for structured analysis output

### Step 3: Generate Charts

```python
from charts_leaderboard import generate_charts

chart_paths = generate_charts(analysis)
# {"track_charts": {track: path}, "vendor_chart": path, "scatter_chart": path}
```

3 chart types:
- **Track Top10 bar charts**: Horizontal bars, 3 sources side-by-side
- **Vendor entry bar chart**: Entries vs track coverage dual bars
- **Cross-source scatter plot**: LMArena rank vs AA rank, diagonal = consistency

### Step 4: Generate Word Report

```python
from report_leaderboard import generate_report

report_path = generate_report(analysis, chart_paths)
```

## Report Structure (8 Dimensions)

| # | Dimension | Source | Method |
|---|-----------|--------|--------|
| 1 | 宏观格局 | Vendor panorama + cross-source comparison | Gemini `[MACRO_LANDSCAPE]` |
| 2 | 核心洞察 | All data | Gemini `[INSIGHT_1..5]` |
| 3 | 赛道分析 | 3 shared tracks × 3 sources | Cross-table + Top10 charts + Gemini `[TRACK_xxx]` |
| 4 | 跨平台排名一致性 | Cross-source model matching | Scatter plot (LM vs AA) |
| 5 | 厂商全景 | All sources combined | Vendor table + entry chart |
| 6 | 技术壁垒 | AA `is_open_weights` | Open/closed stats + Gemini `[TECH_BARRIERS]` |
| 7 | 机会筛选 | Chinese vendors + ranks + coverage | Scored table + Gemini `[OPPORTUNITY]` |
| 8 | 结论 | All | Gemini `[CONCLUSION]` 3 key judgments |

## Config

Configuration file: `config/leaderboard.json`

```json
{
  "sources": {
    "lmarena": {
      "base_url": "https://arena.ai/leaderboard",
      "categories": ["text", "text-to-image", "text-to-video", "image-to-video"]
    },
    "artificial_analysis": {
      "base_url": "https://artificialanalysis.ai",
      "rsc_pages": ["/image/leaderboard/text-to-image", "/video/leaderboard/text-to-video", "/video/leaderboard/image-to-video"]
    },
    "superclue": {
      "base_url": "https://www.superclueai.com",
      "category_order": ["text_to_image", "text_to_video", "image_to_video", "image_edit", "text_to_speech", "ref_to_video", "web_coding"]
    }
  },
  "chinese_vendors": [
    "ByteDance", "Alibaba", "Kuaishou", "Tencent", "Baidu",
    "Zhipu", "MiniMax", "Moonshot", "StepFun", "01.AI",
    "Shengshu", "Xiaomi"
  ],
  "analysis": {
    "top_n_display": 10,
    "top_n_vendor": 20,
    "opportunity_threshold": 3,
    "gemini_temperature": 0.4,
    "gemini_max_tokens": 8192
  },
  "report": {
    "style": {
      "header_bg": "#1B3A5C",
      "accent": "#2563EB",
      "row_alt": "#F2F7FB",
      "font_cn": "微软雅黑",
      "font_en": "Arial"
    }
  }
}
```

## Gemini Prompt Markers

All markers MUST appear in Gemini output for report parsing:

```
[MACRO_LANDSCAPE]  — 宏观格局（150-200字）
[INSIGHT_1..5]     — 核心洞察（每条 标题+正文）
[TRACK_xxx]        — 赛道分析（每赛道 50-100字）
[EXCLUSIVE_TRACKS] — 独有赛道亮点（100-150字）
[TECH_BARRIERS]    — 技术壁垒（100-150字）
[OPPORTUNITY]      — 机会筛选（150-200字）
[CONCLUSION]       — 3 条结论判断
```

## Key Implementation Notes

### Source-Specific Gotchas

1. **ArtificialAnalysis RSC**: MUST set `RSC: 1` header. Without it, only HTML shell is returned.
2. **ArtificialAnalysis dedup**: RSC data contains multiple tab copies (All/Current/Open weights). MUST deduplicate by `values.id`.
3. **SuperCLUE JS hash changes**: The `vue-vendor-{hash}.js` filename changes on every deploy. MUST dynamically extract from homepage HTML.
4. **SuperCLUE 1.5MB JS**: Use `stream=True` + chunked download to avoid encoding errors.
5. **SuperCLUE track order**: Categories are split by `rank=1` delimiters. Order is hardcoded and must be verified if site updates.

### Model Name Normalization

Cross-source matching uses fuzzy matching:
1. Lowercase + strip
2. Remove parenthetical content
3. Remove version suffixes (`-v1.0`, `_v2`)
4. Remove special characters
5. `SequenceMatcher > 0.8` → merge as same model

### Vendor Identification

Uses `identify_vendor()` function with pattern matching against known vendor prefixes/keywords. Unmatched models fall into "Other" (sorted last).

## Dependencies

- `requests`, `beautifulsoup4`: HTTP + HTML parsing
- `python-docx`: Word report
- `matplotlib`: Charts (Agg backend, headless)
- `google-genai` or direct API: Gemini narrative generation

## Runner Script

```bash
# Full pipeline: scrape + analyze + report
python scripts/run_leaderboard.py

# Specify date
python scripts/run_leaderboard.py --date 20260312

# Skip scraping (use existing CSVs)
python scripts/run_leaderboard.py --skip-scrape --date 20260312

# Custom output directory
python scripts/run_leaderboard.py --output D:\reports\leaderboard
```
