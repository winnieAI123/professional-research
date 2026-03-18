# Type 5: Policy Research Pipeline

Two sub-types: Domestic (Chinese government policies) and Overseas (financial regulators).

## Sub-Type Classification

| Sub-Type | Trigger Keywords | Template | Config |
|----------|-----------------|----------|--------|
| **Domestic** | 国内, 部委, 工信部, 央行, 网信办, 中国政策, 政策月报 | `policy_research_domestic.md` | `policy_sources.json` → domestic |
| **Overseas** | 海外, FCA, BaFin, SEC, 牌照申请, 国际监管 | `policy_research_overseas.md` | `policy_sources.json` → overseas |

## Absolute Rule: Source Original Documents

> Policy documents MUST be traced to their original government source. News articles about policies are NOT sufficient — you must find the actual policy document (通知/意见/办法) on the official government website.

---

## Pipeline: Domestic Policy Research (6-Section Monthly Report)

### Step 1: Load Source Configuration & Determine Scope

```python
from utils import read_config
config = read_config("policy_sources.json")
domestic = config["domestic"]

# Determine which domains are relevant to user's query
domains = domestic["domains"]  # AI与机器人, 云计算与算力, 数据安全, 金融科技与消费信贷
keywords = domestic["keywords"]  # per-domain keywords

# Determine search time range (default: last 30 days for monthly report)
```

### Step 2: Multi-Layer Search (Central → Financial → Local)

Three layers of government sites to search, in order:

**Layer 1: Central Ministries (宏观政策要览)**
```python
# Search 7 ministries with domain-specific keywords
ministries = domestic["ministry_level"]
# gov_cn, ndrc, miit, most, nda, cac, sac

for ministry_key, ministry_info in ministries.items():
    results = search_site(
        site=ministry_info["site"],
        keywords=keywords[relevant_domain],
        policy_type_words=domestic["policy_type_words"],
        max_results=10,
    )
```

**Layer 2: Financial Regulators (金融领域)**
```python
# Search 3 financial regulators
fin_regs = domestic["financial_regulators"]
# pbc, nfra, sasac

for reg_key, reg_info in fin_regs.items():
    results = search_site(
        site=reg_info["site"],
        keywords=keywords["金融科技与消费信贷"],
        policy_type_words=domestic["policy_type_words"],
        max_results=10,
    )
```

**Layer 3: Local Governments (地方动态)**
```python
# Search 6 cities: both main site and department-level sites
local = domestic["local_level"]
# beijing, shanghai, guangzhou, shenzhen, hangzhou, hainan

for city_key, city_info in local.items():
    # Main government site
    results = search_site(site=city_info["site"], ...)
    
    # Department-level sites (more targeted)
    for dept_key, dept_site in city_info["departments"].items():
        results = search_site(site=dept_site, ...)
```

### Step 3: LLM Filtering (Critical!)

Raw search results contain noise. Use LLM to filter with STRICT criteria:

```python
from llm_client import generate_content

criteria = """
INCLUDE only if ALL conditions met:
- Published by government ministry or regulator
- Is a formal policy document (通知/意见/办法/指导意见/实施细则/管理规定/标准/行动方案)
- Directly related to the research domain
- Published within the target date range

EXCLUDE:
- Enterprise case studies / digital transformation examples
- News reports / media commentary (save for Step 6)
- Enterprise announcements / platform pages
- Meeting/training notices
- PDF industry reports or case compilations
"""
```

### Step 4: Extract Full Text & Generate Structured Summaries

For each filtered policy document:
1. Use Tavily extract to get full policy text
2. Use LLM to generate structured summary:
   - 政策名称、发布机构、发布日期、文号
   - 政策类型（通知/意见/办法...）
   - 核心要点（3-5条）
   - 关键条款解读
   - 影响评估（受益方、承压方、合规要求、时间节点）
   - 原文URL

### Step 4b: 🛑 原文链接验证与补搜 (MANDATORY)

**禁止在报告中出现"待提供"、"链接待补充"等占位符。**

对每条政策检查是否有有效的原文 URL。如果缺失，执行以下补救流程：

**第一轮：定向补搜**
```python
# 用政策全名 + 发布机构域名做精确搜索
search_query = f'site:{ministry_site} "{policy_full_name}"'
# 例如：site:sz.gov.cn "打造人工智能OPC创业生态引领地行动计划"
```

**第二轮：扩大搜索**
```python
# 如果第一轮没结果，去掉 site: 限制，用全网搜索
search_query = f'"{policy_full_name}" {issuing_authority} 原文'
```

**最终降级处理**：
如果两轮补搜仍找不到原文链接，按以下规则处理：

| 情况 | 处理方式 |
|------|---------|
| 找到了政府官网原文 | 填原文 URL（最佳） |
| 只找到新闻报道 | 填新闻 URL + 标注 `[新闻来源]` |
| 什么都找不到 | 填搜索得到的最佳来源 URL + 标注 `[间接来源]` |

> ❌ **绝对禁止**：填写"待提供"、"（链接待补充）"、留空。
> ✅ 必须至少提供一个可访问的 URL，哪怕是间接来源。

### Step 5: Supplementary Searches (辅助分析)

**5a. Policy Interpretations (解读)**
For major policies, search expert interpretations:
```python
# Search thinktanks and finance media
media_sources = domestic["media_thinktanks"]
for source in media_sources["finance_media"] + media_sources["tech_media"]:
    results = search_site(
        site=source["site"],
        keywords=[policy_title, "解读", "分析", "影响"],
        max_results=5,
    )
```

**5b. Market Data & Enterprise Dynamics (数据与市场)**
```python
# Search for related market data, enterprise announcements, funding events
search_queries = [
    f"{domain} 市场规模 数据",
    f"{domain} 企业 战略 发布",
    f"{domain} 融资 投资",
]
```

**5c. Government Procurement Opportunities (项目机会)**
```python
# Search government procurement platforms
procurement_sites = [
    "ccgp.gov.cn",      # 中国政府采购网
    "ggzy.gov.cn",      # 全国公共资源交易平台
]
for site in procurement_sites:
    results = search_site(
        site=site,
        keywords=keywords[relevant_domain],
        max_results=10,
    )
```

**5d. Local Governance Dynamics (政务动态)**
Focus on publicly available information about government priorities:
```python
# Search local government activity pages
for city_key, city_info in local.items():
    results = search_site(
        site=city_info["site"],
        keywords=["政务活动", "调研", "试点", relevant_domain],
        max_results=5,
    )
```

### Step 6: Deep-Dive Topic (深度专题)

Select one high-impact topic for deep analysis. Reference template structure:

1. **背景与政策脉络** — policy timeline, evolution from 意见→办法→实施细则
2. **市场格局与数据** — market scale, competition, key metrics (from public sources)
3. **头部玩家对比** — strategy comparison using public announcements, earnings calls, media reports
4. **机会与风险** — data-backed opportunity identification

Data sources for deep-dive (public only):
- Government policy documents (original text)
- Company official announcements and press releases
- Financial reports and earnings call transcripts (for listed companies)
- Industry association reports
- Think tank publications
- Analyst reports (publicly available summaries)

> Note: Do NOT rely on interview transcripts or non-public information.

### Step 7: Fill Template & Generate Report

```python
from utils import read_template
template = read_template("policy_research_domestic.md")
```

Fill all 6 sections with structured data from Steps 2-6.

### Step 8: Quality Checklist

Before finalizing, verify:
- [ ] Every policy cited has original government URL
- [ ] 核心提要 covers the most important 3-5 developments
- [ ] 本期焦点 is a specific, well-defined theme
- [ ] Deep-dive topic has concrete data points (numbers, percentages, comparisons)
- [ ] 业务建议 section has actionable items with priority ratings
- [ ] All dates are within the target reporting period

---

## Pipeline: Overseas Policy Research

[Unchanged — see original reference]

### Step 1: Identify Target Regulators

From user's query, determine which countries/regulators to investigate. Load from config:

```python
from utils import read_config
config = read_config("policy_sources.json")
regulators = config["overseas"]["regulators"]
```

### Step 2: Search Regulator Websites

For each relevant regulator, search their official site:

```python
from collect_search import search_site, tavily_extract

results = search_site(
    site="fca.org.uk",
    keywords=["consumer credit", "authorisation", "license application"],
    policy_type_words="",
    max_results=10,
)
```

### Step 3: Extract & Structure License Information

Extract structured info per country:
```json
{
  "country": "",
  "regulator": "",
  "license_name": "",
  "application_fee": "",
  "annual_fee": "",
  "approval_timeline": "",
  "team_requirements": "",
  "office_requirements": "",
  "minimum_capital": "",
  "required_documents": "",
  "application_page_url": "",
  "total_licensed": "",
  "register_url": "",
  "source_url": ""
}
```

### Step 4: Cross-Country Comparison

If researching multiple countries, generate a comparison table.

### Important: Language Handling

- European regulator sites may have pages in local languages only
- Always try English pages first
- If only local language available, Gemini can translate and extract

## Report Output

```python
from utils import read_template
# Domestic
template = read_template("policy_research_domestic.md")
# Overseas
template = read_template("policy_research_overseas.md")
```
