# 🔬 Professional Research Skill

A template-driven, multi-source research framework that produces **institutional-grade reports** across 9 research types. Designed as a skill for AI coding assistants (Claude Code, etc.) to automate end-to-end research workflows.

> **Template-driven means zero code changes** — edit a Markdown template to reshape your report's structure, sections, and style.

## ✨ Features

| Type | Name | Description | Data Sources |
|:----:|------|-------------|:------------:|
| 1 | **Product Research** | Hardware / Software / Service competitive analysis | 🌐 Tavily |
| 2 | **Company Research** | Deep-dive with financials (tech & finance sub-types) | 🌐 Tavily, 📊 yfinance, 📊 akshare |
| 3 | **Industry Panorama** | Market sizing, competitive landscape, value chain | 🌐 Tavily, 📄 arXiv |
| 4 | **Trend Analysis** | Emerging trend identification with KOL opinions | 🌐 Tavily, 🐦 Twitter/X, 📰 Substack |
| 5 | **Policy Research** | Domestic & overseas regulatory tracking | 🌐 Tavily (site-restricted) |
| 6 | **Academic Briefing** | arXiv paper summaries + AI lab blog monitoring | 📄 arXiv RSS, 📰 Blog RSS |
| 7 | **KOL Weekly Digest** | Tech leader tweet aggregation & analysis | 🐦 Twitter/X |
| 8 | **Financial Data & Earnings** | Multi-source quarterly earnings analysis | 📊 SEC EDGAR, 📊 EastMoney, 🎙️ Seeking Alpha |
| 9 | **LLM Leaderboard** | Cross-platform AI model ranking comparison | 🏆 LMArena, ArtificialAnalysis |

## 🏗️ Architecture

```
professional-research/
├── skill.md                  # AI agent instructions (intent classification + workflow)
├── config/                   # Runtime configurations
│   ├── kols.json             #   KOL/influencer list for Twitter collection
│   ├── blog_feeds.json       #   RSS feed URLs for academic monitoring
│   ├── policy_sources.json   #   Government portal URLs for policy tracking
│   └── leaderboard.json      #   Leaderboard data source configs
├── templates/                # Report templates (edit these to customize output!)
│   ├── product_research_hardware.md
│   ├── company_research_tech.md
│   ├── earnings_quarterly.md
│   └── ... (15 templates)
├── references/               # Per-type methodology guides
│   ├── type1_product_research.md
│   └── ... (9 reference docs)
├── scripts/                  # Python execution scripts
│   ├── collect_search.py     #   Tavily search + extract (multi-key rotation)
│   ├── collect_earnings.py   #   Seeking Alpha transcript + IR scraper
│   ├── collect_financials.py #   yfinance / akshare financial data
│   ├── collect_twitter.py    #   Twitter/X API collection
│   ├── llm_client.py         #   Gemini API with 4-model fallback chain
│   ├── generate_report.py    #   Section-by-section report generation
│   ├── md_to_word.py         #   Markdown → Word conversion (宋体 + Arial)
│   └── ... (23 scripts total)
├── .env.example              # API key template
└── requirements.txt          # Python dependencies
```

## 🚀 Quick Start

### 1. Clone & Install

```bash
git clone https://github.com/winnieAI123/professional-research.git
cd professional-research
python -m pip install -r requirements.txt
```

### 2. Configure API Keys

```bash
cp .env.example .env
# Edit .env with your actual API keys
```

| Variable | Required For | How to Get |
|----------|:------------:|------------|
| `GEMINI_API_KEY` | All types | [Google AI Studio](https://aistudio.google.com/) |
| `TAVILY_API_KEY` | All types | [Tavily](https://app.tavily.com/home) |
| `TWITTER_API_KEY` | Type 4 & 7 | [TwitterAPI.io](https://twitterapi.io/dashboard) |
| `RAPIDAPI_KEY` | Type 8 (Earnings) | [RapidAPI](https://rapidapi.com/) — subscribe to [Seeking Alpha API](https://rapidapi.com/belchiorarkad-FqvHs2EDOtP/api/seeking-alpha.p.rapidapi.com) |

### 3. Run a Research Pipeline

```bash
# Company financial data
python scripts/collect_financials.py --ticker BABA --output data/fin.json

# Quarterly earnings analysis (end-to-end: transcript → analysis → Word report)
python scripts/collect_earnings.py --ticker BILI --output ./output/

# Academic paper briefing
python scripts/run_arxiv_pipeline.py --topic "multimodal LLM" --output data/arxiv.json

# LLM leaderboard analysis
python scripts/run_leaderboard.py

# Full report generation (template-driven)
python scripts/run_report_gen.py --templates templates/trend_analysis.md --data data/collected.json --topic "AI Agents" --output report
```

## 🔑 Core Design Principles

### Template-Driven Reports
Every report type maps to a Markdown template in `templates/`. The system reads the template, identifies placeholder fields, collects targeted data, and feeds everything to Gemini for generation. **Want a different report format? Just edit the template.**

### Multi-Model Fallback
LLM calls automatically cascade through 4 Gemini models:
```
gemini-2.5-pro → gemini-3.1-pro-preview → gemini-3-pro-preview → gemini-2.5-flash
```
If a model returns 503 or quota errors, the next model picks up seamlessly.

### Anti-Fabrication Guardrails
- Every data point requires a source URL
- Missing data is explicitly marked as `"未找到相关公开数据（截至搜索日期）"`
- Full-text extraction before analysis (never rely on search snippets alone)
- Per-chapter generation prevents context truncation

### Multi-Key Rotation
`collect_search.py` supports automatic Tavily API key rotation — when one key hits rate limits (429/402), it switches to the backup key transparently.

## 📄 Output Format

Reports are generated in both formats:
- **Markdown** (`.md`) — for version control and further editing
- **Word** (`.docx`) — professional formatting with 宋体 + Arial fonts, styled tables, deep-blue headers

## 📜 License

MIT

---

*Built for researchers who demand institutional-grade output without institutional-grade effort.*
