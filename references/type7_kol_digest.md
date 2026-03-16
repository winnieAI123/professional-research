# Type 7: KOL Weekly Digest — Pipeline Reference

## Overview

People-centric research type: track what specific tech leaders are saying
on Twitter/X in the last 7 days. Produces a concise digest for quick reading.

**Trigger keywords:** "KOL周报", "大佬推文", "科技领袖观点", "最近大佬说了什么",
"KOL digest", "tech leader tweets"

## Pipeline Steps

### Step 1: Load KOL List
- Read `config/kols.json` → get all KOL usernames (all categories)
- Expected: 10-20 KOLs

### Step 2: Fetch Recent Tweets (7 days)
- For each KOL, use `search_kol_tweets(kol_usernames=[username], topic_query="", tweets_per_kol=10)`
- Time filter: only tweets from last 7 days (client-side filter by `created_at`)
- Add 1s delay between KOLs to avoid rate limiting
- If KOL has 0 tweets in 7 days, note as "本周无新推文"

### Step 3: LLM Summarize Per-KOL
- For each KOL with tweets, batch their tweet texts
- Use fast model to generate 2-3 bullet point summaries
- Keep summaries SHORT (each bullet ≤ 30 words)
- Attach original tweet URLs to each bullet

### Step 4: LLM Cross-KOL Theme Extraction
- Feed all KOL summaries to LLM
- Extract 3-5 common themes/hot topics
- Note which KOLs mentioned each theme

### Step 5: Assemble Report
- Use template `kol_weekly_digest.md`
- Section 1: Hot topics from Step 4
- Section 2: Per-KOL summaries from Step 3
- Section 3: Full tweet data table (all tweets, Likes desc)

### Step 6: Save Report
- Save as MD + Word via `save_report()`

## Quality Rules

1. **Brevity**: This report is for QUICK reading. No deep analysis needed.
2. **Links**: Every opinion must have a clickable link to the original tweet.
3. **No fabrication**: If data is missing, say so briefly.
4. **Engagement data**: Always show Likes and RT counts.
5. **Sort by activity**: KOLs with more engagement ranked first.

## Data Source

- **Primary**: Twitter/X via twitterapi.io
- **KOL list**: `config/kols.json` (all categories)
- **Time window**: Fixed 7 days
