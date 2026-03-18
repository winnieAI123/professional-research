# Type 4: Trend Analysis Pipeline

Multi-source trend research: Twitter/X KOL opinions + Substack deep analysis + Tavily web search + arXiv (optional).

## Core Principle: Three-Source Cross-Validation

Every trend conclusion must be supported by at least 2 of the 3 primary sources. No single-source conclusions.

## Data Collection Pipeline

### Source 1: Twitter/X KOL Opinions

**Step 1**: Load KOL list from `config/kols.json`

**Step 2**: Generate search queries:
- Topic query: `"[topic in English]" future trend prediction`
- KOL-specific: `from:[username] [topic keywords]`
- Time-filtered: Add `since:YYYY-MM-DD` for recency

**Step 3**: Run collection:
```python
from collect_twitter import search_kol_tweets, search_topic_tweets
from utils import read_config

kols = read_config("kols.json")
kol_usernames = [k["username"] for k in kols["kols"]]

# KOL-specific search
kol_tweets = search_kol_tweets(kol_usernames, "[topic]", tweets_per_kol=10)

# Broad topic search
topic_tweets = search_topic_tweets("[topic] trend", total_count=30)
```

**Step 4**: Tweets are already full-text (short by nature). Feed directly to `llm_client.extract_opinions()`.

### Source 2: Substack Deep Articles

**Step 1**: Search Substack:
```python
from collect_substack import search_substack, get_full_articles

posts = search_substack("[topic] analysis", max_pages=3)
```

**Step 2**: Get full text via Tavily extract (search API only returns 500-char previews):
```python
posts = get_full_articles(posts, max_articles=10)
```

**Step 3**: For each article with full_content, call `llm_client.extract_opinions()` to get structured opinion data. This is the MANDATORY full-text reading step — never skip this.

### Source 3: Tavily Web Search

**Step 1**: Search for industry reports and analysis:
```python
from collect_search import multi_query_search, tavily_extract

results = multi_query_search(
    queries=[
        "[topic] trend forecast analysis 2025",
        "[topic] market prediction future opportunity",
        "[topic] expert opinion industry outlook",
    ],
    include_domains=["techcrunch.com", "venturebeat.com", "ieee.org",
                     "theinformation.com", "thenewstack.io"],
)
```

**Step 2**: Extract full text for top results:
```python
urls = [r["url"] for r in results[:10]]
full_content = tavily_extract(urls)
```

**Step 3**: Feed each to `llm_client.extract_opinions()`.

### Source 4: arXiv (Optional, when topic involves technical paradigm shifts)

Only use when the topic involves technical route changes (e.g., "Will Transformers be replaced?").
Follow the arXiv pipeline from `type3_industry_research.md`.

## Data Standardization

All opinions (from any source) are normalized to:
```json
{
  "author": "Name",
  "stance": "看好/看衰/中立",
  "core_opinion": "One-line summary",
  "key_arguments": ["arg1", "arg2", "arg3"],
  "original_quotes": ["quote1", "quote2"],
  "time_predictions": {
    "short_term": "1-3 year prediction",
    "mid_term": "3-5 year prediction",
    "long_term": "5-10 year prediction"
  },
  "relevance_score": 8,
  "source_url": "https://...",
  "source_type": "twitter/substack/web/arxiv"
}
```

## Data Persistence (Mandatory)

After all opinions are extracted, save them to a JSON file in the output directory **before** generating the report:

```python
import json
from datetime import datetime

opinions_data = {
    "topic": "[研究主题]",
    "date": datetime.now().strftime("%Y-%m-%d"),
    "sources": {
        "twitter": len(twitter_opinions),
        "substack": len(substack_opinions),
        "web": len(web_opinions),
    },
    "opinions": all_opinions,  # List of standardized opinion dicts
}

with open(f"{output_dir}/opinions_{topic_short}_{date}.json", "w", encoding="utf-8") as f:
    json.dump(opinions_data, f, ensure_ascii=False, indent=2)
```

This file serves as:
1. **Audit trail** — verify which sources were actually read
2. **Debug tool** — check if stance classification is accurate
3. **Reuse** — regenerate report without re-collecting data

## Report Generation

### Key Sections in Template

1. **Topic Background**: Use web search data for market size, current players
2. **KOL Opinion Map**: Group opinions by stance (bullish/bearish/neutral), present as structured table
3. **Deep Analysis**: For top 2-3 opinions per stance, provide full argument chain with original quotes
4. **Core Disputes**: Cross-reference opposing views, identify root disagreements
5. **Timeline Predictions**: Synthesize time predictions across sources into short/mid/long term
6. **Competitive Landscape**: Companies/teams positioned in this trend
7. **Opportunities**: Map opportunities by time window, required capabilities, competition intensity
8. **Signal Monitoring**: Identify verifiable signals to watch

### Critical Rule
Every opinion in Section 2-3 MUST have:
- An `original_quote` from the actual article/tweet (read by LLM)
- A `source_url` that is traceable
- Author identification with their role/title

No fabricated quotes. No paraphrased-as-quoted content. If the LLM didn't read the full text, that opinion may NOT appear in the report.

## Report Output — Agent-Driven Per-Chapter

> **Important**: Do NOT use `run_report_gen.py` for trend analysis.
> Use the per-chapter workflow defined in `skill.md` Type 4 section (Phase 1-4).

The Agent should:
1. Collect data from all 4 sources (Phase 2)
2. For EACH of the 8 chapters: feed that chapter's template + relevant data subset → `generate_content()` → get chapter output
3. Concatenate in order → `save_report()` for MD + Word

