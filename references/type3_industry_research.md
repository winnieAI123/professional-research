# Type 3: Industry Research Pipeline

Two-part industry research: Commercial (always) + Technical (when user mentions technical routes/architecture/papers).

## Determining Scope

| Scope | When | Templates |
|-------|------|-----------|
| **Commercial Only** | Consumer/traditional industries (smart glasses, fintech, retail) | `industry_research_commercial.md` |
| **Commercial + Technical** | User mentions: 技术路线, 架构, 论文, algorithm, technical comparison | Both `industry_research_commercial.md` AND `industry_research_technical.md` |

## Part 1: Commercial Research Pipeline

### Search Keyword Generation (4 Major Sections)

**Section 1 — Market Opportunity:**
- `"[industry]" market size 2024 2025 forecast billion`
- `"[industry]" CAGR growth rate market forecast [target year]`
- `"[industry]" growth drivers demand supply trend`
- `"[industry]" value chain supply chain BOM cost breakdown`
- `"[industry]" barriers to entry capital technology patent`

**Section 2 — Competitive Landscape:**
- `"[industry]" market share top companies players leading`
- `"[company1]" vs "[company2]" comparison revenue product`
- `"[industry]" new entrants startup funding 2024 2025`
- `"[industry]" substitute products alternatives threat`
- `"[industry]" success factors competitive advantage`

**Section 3 — Development Trends:**
- `"[industry]" future trends forecast prediction [year]`
- `"[industry]" technology roadmap evolution direction`
- `"[industry]" beneficiary companies opportunities`

**Section 4 — Risk Factors:**
- `"[industry]" risks challenges regulatory policy threat`

### BOM Cost Analysis (Special)
The template includes a BOM cost waterfall comparison for two products. Search queries:
- `"[product name]" teardown BOM cost component breakdown`
- `"[product name]" bill of materials cost analysis iFixit`
- `"[industry]" manufacturing cost margin analysis supply chain`

### Data Sources
- `collect_search.py`: Tavily search with advanced depth
- `collect_search.py`: Tavily extract for detailed report pages

---

## Part 2: Technical Research Pipeline

### Step 1: arXiv Paper Search

Generate English search queries with boolean operators:
```
"[tech area]" AND ("[approach 1]" OR "[approach 2]" OR "[approach 3]")
```

Example:
```
"embodied intelligence" AND ("policy learning" OR "VLA" OR "world model" OR "modular")
```

### Step 2: Download & Extract

Use `collect_arxiv.py`:
```python
from collect_arxiv import fetch_and_analyze_papers
papers = fetch_and_analyze_papers(
    query='"embodied AI" AND ("VLA" OR "world model")',
    output_dir="./papers",
    max_results=5,
    sort_by="relevance"
)
```

### Step 3: LLM Deep Analysis

For each paper with full text, call `llm_client.analyze_paper()` to get structured analysis:
- Core problem & motivation
- Proposed method/architecture
- Key innovations
- Experiment results vs baselines
- Limitations
- Industry implications

### Step 4: Technology Route Comparison

After analyzing 5 papers, synthesize into a technology route comparison table:

| Dimension | Route 1 | Route 2 | Route 3 |
|-----------|---------|---------|---------|
| Core idea | | | |
| Architecture | | | |
| Data requirements | | | |
| Advantages | | | |
| Disadvantages | | | |
| Key players | | | |
| Representative paper | | | |

### Step 5: Trend Conclusions

Synthesize technical trends from papers and web search:
- What's been solved
- What's being worked on
- What's still unsolved
- Short/mid/long-term route predictions

### Important: 503 Error Handling
arXiv PDF processing + Gemini analysis may trigger 503 errors. The `llm_client.py` automatically tries fallback models. If one model gives 503, it switches to the next — do NOT stop the pipeline.

---

## Report Generation — Agent-Driven Per-Chapter

> **Important**: Do NOT use `run_report_gen.py` for industry research.
> Use the per-chapter workflow defined in `skill.md` Type 3 section.

The Agent should:
1. Read the template and split by `## 一、` / `## 二、` etc. to isolate each chapter's template section
2. For EACH chapter: feed that chapter's template + that chapter's collected data → `generate_content()` → get chapter output
3. After ALL chapters: concatenate in order → `save_report()` for MD + Word

**Why per-chapter**: A single prompt with both templates (~270 lines) + all data causes Gemini to truncate output and lose data. Per-chapter generation ensures each section gets full context and max_output_tokens.

**If Commercial + Technical**:
1. Generate all 4 commercial chapters first
2. Then generate all 4 technical chapters
3. Merge with `---` separator between the two parts
4. Save as one combined report

