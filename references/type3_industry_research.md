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

## Report Generation

```python
from utils import read_template

# Always generate commercial part
commercial_template = read_template("industry_research_commercial.md")

# Generate technical part only if scope includes it
if needs_technical:
    technical_template = read_template("industry_research_technical.md")
```

For industry reports, it often helps to generate the report in sections rather than all at once, because the template is large. Call `generate_report_section()` per major section, then concatenate.

## Proven Technique: Section-by-Section Generation

When combining Commercial + Technical parts, generate them as **separate Gemini calls**, then merge:

1. **Call 1**: Feed commercial template + web data → generate commercial report (~6000-8000 chars)
2. **Call 2**: Feed technical template + arXiv data → generate technical report (~8000-10000 chars)
3. **Merge**: Concatenate with `---` separator
4. **Save**: Pass merged content to `save_report()`

**Why**: A single prompt with both templates (~270 lines) + data often causes Gemini to truncate the output. Section-by-section generation ensures each part gets full attention and max_output_tokens.

**Prompt tips**:
- Set `max_output_tokens=8000` per section
- Include the full template text in each prompt
- Explicitly list which companies/papers to cover
- BOM data: if not found, say "公开数据有限", don't fabricate
