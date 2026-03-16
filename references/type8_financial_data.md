# Type 8: Financial Data Extraction (财务数据提取) — Reference Guide

## Overview

Type 8 is designed for users who want **precise financial numbers** (revenue, profit, balance by product, multi-year trends) for **one or more companies**, rather than a full narrative company report (Type 2).

## When to Use Type 8 (vs Type 2)

| Signal | Type 2 (Company Research) | Type 8 (Financial Data) |
|--------|--------------------------|------------------------|
| User intent | "研究一下MongoDB" | "蚂蚁和微众过去5年收入利润" |
| Keywords | "研究", "分析", "deep dive" | "过去N年", "分产品", "收入利润", "余额" |
| Output | 9-chapter narrative report | Data tables + brief analysis |
| Companies | Single | **Multiple** supported |
| Depth | Wide (qualitative + quantitative) | **Deep** (numbers only) |

## Dynamic Data Source Routing

The script auto-detects the best data source for each company:

```
For each company name in user query:
  1. Try US ticker resolution (yfinance + LLM)
     → If US-listed → SEC EDGAR (20-F or 10-K)
  
  2. Try CN ticker resolution (EastMoney search API)
     → If CN-listed → EastMoney F10 + akshare + Sina
  
  3. Ask LLM: is this a bank/institution with public annual reports?
     → If yes → Tavily PDF search → download → LLM extract
  
  4. Fallback → Web search → LLM summarize
```

**No hardcoded company config** — works for any company the user names.

## Data Extraction Methods

### Path A: SEC EDGAR (US-listed companies)
- **How**: Download 20-F/10-K HTML → parse all `<table>` → Flash filter → Pro extract
- **Precision**: Highest (official SEC filings)
- **Examples**: QFIN, FINV, LU, MDB, AAPL

### Path B: CN-listed (A-stock / HK-stock)
- **How**: Uses existing `collect_financials.py` (EastMoney F10 + Sina)
- **Precision**: High (income statement, indicators, market data)
- **Examples**: 300418 (昆仑万维), 601398 (工商银行)

### Path C: PDF Annual Reports (non-listed institutions)
- **How**: Tavily search PDF → download → pdfplumber extract → LLM extract
- **Precision**: Medium-high (depends on PDF quality)
- **Examples**: 微众银行, 网商银行, 消费金融公司

### Path D: Web Search (no public filings)
- **How**: Multi-query Tavily → LLM summarize with reliability tags
- **Precision**: Low-medium (scattered public data)
- **Examples**: 蚂蚁集团, ByteDance (pre-IPO)

## Unit Normalization

Critical for multi-PDF extraction where different years use different units:
- LLM returns original units in metadata
- Python does deterministic multiplication: 万元→千元 (×10), 亿元→千元 (×100000)
- Final output unified to 千元RMB

## Output Format

```
Word Report:
  一、核心发现与分析
    - Per company: facts only (balance CAGR, revenue growth, profit margin)
    - No cross-comparison, no editorial opinions
  
  二、详细数据附录
    附录A: Company1 (multi-year tables per data group)
    附录B: Company2
    ...
```

## Anti-Fabrication Rules

1. LLM extraction: "找不到的年份不要编造"
2. Web search: reliability tagged as high/medium/low
3. Analysis paragraphs: "只描述事实和数据变化, 不写启示, 不编造"
