# Type 8: Financial Data Extraction (财务数据提取) — Reference Guide

## Overview

Type 8 is designed for users who want **precise financial numbers** (revenue, profit, balance by product, multi-year trends) for **one or more companies**, rather than a full narrative company report (Type 2).

**设计原则**: 快速获取数据、清晰呈现数字。报告只有数据表格，零 LLM 叙事分析。

## When to Use Type 8 (vs Type 2)

| Signal | Type 2 (Company Research) | Type 8 (Financial Data) |
|--------|--------------------------|------------------------|
| User intent | "研究一下MongoDB" | "蚂蚁和微众过去5年收入利润" |
| Keywords | "研究", "分析", "deep dive" | "过去N年", "分产品", "收入利润", "余额" |
| Output | 9-chapter narrative report | **Data tables only** |
| Companies | Single | **Multiple** supported |
| Depth | Wide (qualitative + quantitative) | **Deep** (numbers only) |

## Dynamic Data Source Routing

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

## Data Coverage

### Annual Data
- SEC: 20-F/10-K → HTML table parsing → LLM extraction
- CN-listed: EastMoney F10 (income statement, indicators)
- PDF: Annual reports → pdfplumber → LLM extraction
- Web: Tavily multi-query → LLM summarization

### Quarterly Data (SEC companies only)
- Automatically collects **last 5 quarters** (10-Q or 6-K)
- Critical for timeliness: annual reports lag 3-6 months

### Latest Year Fallback
- If annual report not yet published, auto-supplements with web search
- Tagged with `web_supplemented_years` in metadata

## Output Format

```
Word Report (pure data tables, zero narrative):
  一、年度数据
    A. Company1（SEC）
      - Group1 table (指标 × 年份)
      - Group2 table
    B. Company2（PDF年报）
      - Group1 table
  
  二、最近季度数据（if available）
    Company1
      - Quarterly table (指标 × YYYY-QN)
  
  三、数据来源
    Per-company: source type, unit, reliability
```

## Anti-Fabrication Rules

1. LLM extraction: "找不到的年份不要编造"
2. Web search: reliability tagged as high/medium/low
3. Report: **no narrative analysis, no editorial opinions, just data tables**
