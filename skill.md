---
name: professional-research
description: Professional industry research system supporting 9 research types - product research, company research, industry panorama, trend analysis, policy research, academic briefing, KOL weekly digest, financial data extraction, and LLM leaderboard analysis. Generates standardized high-quality reports using template-driven workflows. Use this skill whenever the user asks about industry research, competitive analysis, company deep dives, trend forecasting, policy tracking, academic paper summaries, KOL opinions, tech leader weekly updates, market analysis, AI model rankings, leaderboard comparison, or any structured research that requires data collection and report generation. Also triggers on requests mentioning "研究报告", "行业分析", "竞品分析", "公司研究", "趋势研判", "政策追踪", "论文简报", "KOL周报", "大佬推文", "科技领袖", "排行榜", "榜单分析", "模型对比", "arena", "leaderboard", "market research", "industry report", or similar research-oriented phrases.
---

# Professional Research Skill

A template-driven, multi-source research framework that produces institutional-grade reports across 9 research types.

## 🛑 Global Execution Rules (MUST FOLLOW)

> **Rule 1: NEVER pause mid-research to ask the user if they want to continue.**
> Once the user initiates a research request, execute ALL phases (data collection → ALL chapters → Word output) **autonomously from start to finish**. Do NOT stop after any chapter to ask "要继续吗？" or "篇幅较长，是否继续？". The user expects a COMPLETE report, not partial output.

> **Rule 2: ALWAYS generate Word (.docx) output automatically.**
> After assembling the full Markdown report, you MUST call `save_report()` or `md_to_word.py` to produce the Word document. This is NOT optional. Do NOT ask the user whether they want a Word version — they always do.

> **Rule 3: No confirmation needed between phases.**
> Phase 1 (data collection) → Phase 2 (chapter writing) → Phase 3 (Word output) should flow continuously without any user interaction. If you encounter errors, handle them silently (retry, fallback, or mark as "数据未找到") and keep going.

> **Rule 4: Report content goes to FILES, not chat.**
> Do NOT print the full report text in the chat window. Write each chapter's output to a file (or accumulate in memory), then assemble into a final `.md` file and convert to `.docx`. The user should receive **files**, not walls of Markdown text in the conversation.

> **Rule 5: Use `md_to_word.py` for Word conversion — no DIY.**
> You MUST call `python scripts/md_to_word.py --input report.md --output report.docx` for Word conversion. Do NOT write your own python-docx code. The standard script handles Markdown syntax cleanup (`**`, `##`, backticks, etc.) automatically. If `md_to_word.py` fails, use `save_report()` from `generate_report.py` as fallback.

> **Rule 6: LLM-generated report text must be CLEAN prose.**
> When generating chapter content via LLM, instruct the model to output **plain structured text** using Chinese numbering (一、二、三) and natural prose. Minimize Markdown syntax: use `##` ONLY for chapter headings (so `md_to_word.py` can parse them), but do NOT use `**bold**` markers in body text. Bold emphasis should be achieved through natural writing (e.g., explicit phrases like "关键发现：" or "核心指标："), not Markdown formatting.

## Core Mechanism

**Templates drive everything.** Each research type has a dedicated MD template in `templates/`. Every run:
1. Read the template fresh (user can modify templates anytime)
2. Parse placeholder fields to determine what data to search
3. Collect data from type-specific sources
4. Feed template + collected data to Gemini API
5. Output MD report → convert to Word

This means users only need to edit template MD files to change report format/structure — no code changes needed.

## Prerequisites

### API Keys (via Environment Variables — NEVER hardcode)

| Variable | Required For | How to Get |
|----------|-------------|------------|
| `GEMINI_API_KEY` | All types | Google AI Studio |
| `TAVILY_API_KEY` | All types | tavily.com |
| `TWITTER_API_KEY` | Type 4 (Trend), Type 7 (KOL Digest) | twitterapi.io |

### Python Dependencies

```bash
python -m pip install tavily-python google-genai arxiv PyMuPDF feedparser python-docx requests
```

## Pre-flight Check (执行前检查) — 🚨 MANDATORY FIRST STEP

> **核心原则：让用户始终觉得可控。任何功能降级必须用户知情并确认，禁止静默降级。**

在执行任何研究类型之前，Agent **必须**先完成以下检查流程：

### Step 1: 检查 API Key 配置

读取 `.env` 文件（位于 skill 根目录），检查以下 key 是否已配置：

| Key | 影响范围 | 缺失后果 |
|-----|---------|---------|
| `GEMINI_API_KEY` | 所有 Type 的 LLM 分析 | 无法调用脚本中的 Gemini 模型，报告质量严重下降 |
| `TAVILY_API_KEY` | 搜索 + 全文提取 | 降级为 Agent 原生搜索工具，效果接近但部分全文提取受限 |
| `RAPIDAPI_KEY` | Type 8B Earnings Call Transcript | 无法获取 Seeking Alpha 完整文稿 |
| `TWITTER_API_KEY` | Type 4, Type 7 KOL 数据 | 无法采集 Twitter/X 推文 |

### Step 2: 缺失时的用户交互流程

如果检测到任何 **关键 key 缺失**，Agent 必须按以下模板向用户说明：

```
我检查了研究技能的 API 配置，发现以下 key 未配置：

❌ GEMINI_API_KEY — 用于 LLM 分析（所有报告类型必需）
   → 申请地址：https://aistudio.google.com/apikey（免费）

❌ TAVILY_API_KEY — 用于高质量搜索和全文提取
   → 申请地址：https://tavily.com（有免费额度）

如果您愿意配置，我可以指导您完成设置（只需在 .env 文件中添加一行）。
如果暂时不配置，我将使用替代方案继续工作，但以下功能会受限：
- [具体说明受影响的功能]

请问您希望？
1. 现在配置（我来指导）
2. 暂时跳过，使用替代方案继续
```

### Step 3: 用户选择后的行为

| 用户选择 | Agent 行为 |
|---------|-----------|
| **愿意配置** | 指导用户打开申请页面、获取 key → 编辑 `.env` 文件 → 重新检查确认 → 正常执行 |
| **拒绝配置** | 明确说明降级策略（如 "将使用内置搜索替代 Tavily"），然后继续执行 |
| **部分配置** | 仅对已配置的 key 走正常流程，未配置的走降级路径 |

### 各 Key 的降级策略

| 缺失 Key | 降级方案 | 质量影响 |
|----------|---------|---------|
| `GEMINI_API_KEY` | ⚠️ **严重降级** — Agent 用自身能力直接撰写，无法调用脚本内的 Gemini pipeline | 报告质量大幅下降，建议强烈推荐用户配置 |
| `TAVILY_API_KEY` | 使用 Agent 原生 `search_web` + `read_url_content` 替代 | 质量接近，可接受 |
| `RAPIDAPI_KEY` | 改用网页搜索获取 Earnings Call 摘要（非完整文稿） | 第五章质量下降，需标注 |
| `TWITTER_API_KEY` | 使用网页搜索 `site:x.com` 替代，覆盖面有限 | KOL 覆盖率下降约 50% |

> **⚠️ 禁止行为**：
> - ❌ 禁止在没有告知用户的情况下跳过或替代任何数据源
> - ❌ 禁止在 key 缺失时直接开始写报告而不先沟通
> - ❌ 禁止用 Agent 自身的搜索能力替代脚本而不说明差异

## Intent Classification

When user submits a research request, classify into one of 7 types using this decision tree:

### Type 1: Product Research (产品研究)
**Triggers**: User mentions a specific product name, product category, "竞品", "产品分析", "product analysis"
**Sub-types**:
- **Hardware**: Robot, device, terminal, wearable, IoT → read `references/type1_product_research.md`, use template `templates/product_research_hardware.md`
- **Software**: App, platform, SaaS, tool → use template `templates/product_research_software.md`
- **Service**: Insurance, lending, financial service, consulting → use template `templates/product_research_service.md`
**Data sources**: Web search, Tavily

**🚨 MANDATORY: Hardware Sub-type — Agent-Driven 逐章写作工作流**

> **NEVER** batch all chapters into one `run_report_gen.py` call for Hardware product research.
> Hardware research **MUST** use the per-chapter workflow below (same pattern as Type 2 Company Research).

**Phase 1: 模板解析与维度确定**

1. 读取 `templates/product_research_hardware.md` 模板
2. 根据用户指定的研究功能/特性，确定 3-6 个分析维度
3. 通过初步搜索识别产品品类分组

**Phase 2: 逐章数据采集 + 写作**

对模板中的 8 个章节（一→七），逐章执行：
1. **搜索**: 按模板中每章的"Agent 搜索策略"提示，生成 2-3 个针对性 query
2. **全文提取**: 对最相关的 2-3 个结果，调用 `tavily_extract()` 获取全文
3. **写作**: 该章节单独一次 LLM 调用，传入章节模板片段 + 所有数据（无截断）
4. **Key Takeaways 最后写**：综合前 7 章内容，不额外搜索，在报告中放最前面（无编号）

> **Key**: 第五章"产品详细扫描表"是最重的，需要按品类分组、逐产品搜索。
> Agent 应灵活适应：消费级产品搜用户评价，工业级搜技术规格，概念产品搜发布信息。

**Phase 3: 拼接 + Word 输出**

按最终报告顺序（Key Takeaways → 一 → 二 → 三 → 四 → 五 → 六 → 七 → 附录）合并所有章节 →
调用 `save_report()` 输出 MD + Word。

### Type 2: Company Research (公司研究)
**Triggers**: User mentions a specific company name + "研究"/"分析"/"deep dive"
**Sub-types**:
- **Tech company**: AI, SaaS, hardware, internet company → read `references/type2_company_research.md`, use template `templates/company_research_tech.md`
- **Finance company**: Has keywords like 牌照/合规/支付/保险/银行/lending → use template `templates/company_research_finance.md`
**Data sources**: Web search, Tavily, **`collect_financials.py`** (MUST for listed companies)

**🚨 MANDATORY: Agent-Driven Chapter-by-Chapter Workflow**

> **NEVER** batch all chapters into one `run_report_gen.py` call. This causes catastrophic data loss:
> `run_report_gen.py` truncates to 15 items / 8000 chars → most search data is discarded → report full of "未找到数据".
> Company research **MUST** use the per-chapter workflow below.

**Phase 1: Per-Chapter Data Collection**

For EACH chapter in the template (7 for tech, 12 for finance), do ALL of the following:
1. **Search**: Generate 2-3 targeted queries (English + Chinese). Call `tavily_search()` from `collect_search.py`
2. **Read full text**: For 2-3 most relevant results, call `tavily_extract()` to get the full article
3. **Extract data points**: Read the full text yourself, extract specific facts/numbers with source URLs
4. **Adapt if needed**: If a search returns nothing useful, try different keywords, add site-specific searches (e.g., `site:crunchbase.com`, `site:pitchbook.com`), or search in a different language
5. **Move to next chapter only after** you have data points OR confirmed this data is not publicly available

> **Key principle**: You are the orchestrator. You decide what to search, how many results to read, and when to try alternative queries. This flexibility is WHY we don't use a pipeline script for company research.

> **第三章（产品与技术分析）通常是最重的章节**，可能需要 4-6 组 query；**第五章（竞争分析）** 需要额外搜索 2-3 家主要竞品。Agent 应按章节重要性灵活分配搜索深度。

**Phase 2: Financial Data (listed companies only)**
```bash
python scripts/collect_financials.py --ticker 300418 --output data/fin.json
# Or: python scripts/collect_financials.py --company "昆仑万维" --output data/fin.json
```
This gives you structured income statements, balance sheets, market data in seconds. **DO NOT skip this for listed companies** — web search cannot match this precision.

**Phase 3: Per-Chapter Report Generation（写作风格是关键！）**

For EACH chapter, call `generate_content()` separately with:
- **写作风格指令（MUST prepend!）**: 从 `references/type2_company_research.md` 的"写作风格总则"复制完整的风格指令，作为每次 LLM 调用的 system prompt 或 prompt 前缀。**这是确保报告像分析师写的（而非机器填充的）的关键。**
- The specific chapter's template section (including the `<!-- 写作指引 -->` comments — these guide the LLM's analytical thinking)
- ALL data points you collected for that chapter (no truncation because you feed directly)
- Anti-fabrication rules: no data = "截至研究日期，该数据尚未公开披露"（但不要因为个别数据缺失就停止分析）
- Key facts should cite sources naturally in prose (e.g., "据管理层在2025科技日披露"), URLs collected in the 数据来源 section

> **NEVER generate the entire 7-chapter report in one LLM call.** One call per chapter ensures each chapter gets full context and sufficient output tokens.

> **核心判断（Key Takeaways）最后写**：在所有 7 个章节生成完毕后，综合全文提炼核心判断，放在报告最前面。

**Phase 4: Assembly & Word Output (MANDATORY — DO NOT SKIP)**
按最终报告顺序（核心判断 → 一 → 二 → 三 → 四 → 五 → 六 → 七 → 数据来源）合并所有章节 → call `save_report()` from `generate_report.py` for MD + Word.

> 🛑 **This phase is NOT optional.** You MUST produce both `.md` and `.docx` files. Do NOT stop after generating Markdown and ask the user if they want Word — just generate it.


### Type 3: Industry Panorama (行业全景研究)
**Triggers**: "行业", "赛道", "市场", "industry", "market overview", macro-level perspective
**Sub-types**:
- **Commercial only**: Consumer/traditional industries (smart glasses, fintech, etc.) → use template `templates/industry_research_commercial.md`
- **Commercial + Technical**: User mentions technical routes/architecture/papers → ALSO use template `templates/industry_research_technical.md` and search arXiv
**Data sources**: Web search, Tavily, arXiv (for technical part)
**Read**: `references/type3_industry_research.md`

### Type 4: Trend Analysis (趋势研判与机会发现)
**Triggers**: "趋势", "预判", "机会", "trend", "forecast", "大佬观点", "KOL opinions"
**Data sources**: Web search, Tavily, Twitter/X, Substack
**Read**: `references/type4_trend_analysis.md`
**Template**: `templates/trend_analysis.md`
**Special**: Load `config/kols.json` for KOL list

### Type 5: Policy Research (政策研究)
**Triggers**: "政策", "监管", "法规", "牌照", "regulation", "policy", "compliance"
**Sub-types**:
- **Domestic**: Chinese ministry/local government policies → use template `templates/policy_research_domestic.md`, load `config/policy_sources.json`
- **Overseas**: Foreign regulators (FCA, BaFin, etc.) → use template `templates/policy_research_overseas.md`
**Data sources**: Web search, Tavily (with site: restriction to official domains)
**Read**: `references/type5_policy_research.md`

### Type 6: Academic Briefing (学术简报)
**Triggers**: "论文", "paper", "arXiv", "学术", "前沿技术", "academic", "research papers"
**Data sources**: arXiv RSS, AI Lab blogs (Google AI, OpenAI, DeepMind, HuggingFace, Anthropic, 机器之心)
**Read**: `references/type6_paper_briefing.md`
**Template**: `templates/paper_briefing.md`
**Special**: Load `config/blog_feeds.json` for RSS URLs

### Type 7: KOL Weekly Digest (KOL科技领袖周报)
**Triggers**: "KOL周报", "大佬推文", "科技领袖观点", "最近大佬说了什么", "tech leader tweets"
**Data sources**: Twitter/X only
**Read**: `references/type7_kol_digest.md`
**Template**: `templates/kol_weekly_digest.md`
**Special**: Load `config/kols.json` for full KOL list, fixed 7-day window

### Type 8: Financial Data & Earnings Analysis (财务数据与业绩分析)

**Sub-type A: Financial Data Extraction (财务数据提取)**
**Triggers**: User focuses on **specific numbers** across multiple companies/years. Key phrases:
- "过去N年", "分产品", "余额", "收入利润", "财务数据对比", "年报数据"
- Multiple company names + financial metrics in one query
**Sub-types**: Auto-detected per company (no hardcoded config)
- US-listed → SEC EDGAR (20-F/10-K) → LLM two-round extraction
- CN-listed → EastMoney F10 (reuses `collect_financials.py`)
- Non-listed with annual reports (banks) → Tavily PDF search → download → LLM extract
- No public filings → Web search → LLM summarize
**Data sources**: SEC EDGAR, EastMoney, PDF search, Web search (auto-routed)
**Read**: `references/type8_financial_data.md`
**Template**: `templates/financial_data_report.md`
**Script**: `scripts/collect_financial_deep.py` (MUST use this script)

**Sub-type B: Quarterly Earnings Analysis (季度业绩分析)**
**Triggers**: User asks about **a single company's latest quarterly results**. Key phrases:
- "财报分析", "季度业绩", "earnings", "Q1/Q2/Q3/Q4 results"
- "[公司名] 最新财报", "earnings update", "post-earnings", "业绩会"
- Company name + any quarter/fiscal year reference
**Template**: `templates/earnings_quarterly.md`
**Data sources**: Earnings Call Transcript + Press Release + SEC/交易所公告 + Web search

**🛑🛑🛑 MANDATORY: 必须运行 collect_earnings.py 🛑🛑🛑**

> ❌ **FORBIDDEN**: 禁止在运行脚本之前调用 yfinance、Tavily、Google Search 或任何 MCP 搜索工具获取财报数据。
> ❌ **FORBIDDEN**: 禁止在脚本运行前或运行中开始写报告。
> ❌ **FORBIDDEN**: 禁止用二手新闻摘要替代 Earnings Call Transcript 原文。
> ✅ **FIRST ACTION**: 收到请求后，你的第一个动作必须是运行 `collect_earnings.py`。不要做任何 yfinance 查询、不要做任何搜索、不要获取股价。脚本内部会自动完成所有数据收集。
> ✅ **SUPPLEMENTARY SEARCH**: 只有在脚本运行完成且数据不足时，才可以用搜索工具补充。

**为什么不能手动搜？**
脚本获取的 Transcript (41K+ chars) 和 PR PDF (完整财务表格) 远优于 Google 搜索摘要 (300 chars)。手动搜 = 数据质量降 90%。脚本内部已包含 IR 官网爬取 → Tavily 搜索 → yfinance 补充的完整数据链。

---

**Phase 1: Data Collection — 脚本必须先跑！**

**Step 1.1: 运行脚本（FIRST STEP, NON-NEGOTIABLE）**
```bash
cd "C:/Users/wangtian/.claude/skills/professional-research" && python scripts/collect_earnings.py --ticker [TICKER] --output "D:/clauderesult/claudeMMDD/"
```

> ⚠️ 用 `D:/clauderesult/claudeMMDD/` 替换为当天日期的实际路径。

脚本会自动执行 4 步:
1. 获取 Seeking Alpha Transcript（含重试），保存 `{TICKER}_transcript.txt`
2. LLM 分析 Transcript，生成摘要
3. 下载 IR 官网 PR PDF + yfinance，保存:
   - `{TICKER}_press_release.txt` (提取的纯文本)
   - `{TICKER}_press_release.pdf` (PDF 原件)
   - `{TICKER}_extracted_data.json` (LLM 提取的结构化数据)
4. 运行 Data Quality 检查 → 逐章生成报告 (8 次 LLM) → 输出 .md + .docx

**预计耗时**: 5-7 分钟。**必须等脚本完成**。

- ✅ 如果成功: output 目录下有完整文件集
- ❌ 如果超时/失败: 转 Step 1.2

**Step 1.2: 手动搜索 Transcript（仅在脚本完全失败时）**

> 🚨 **MUST DO** — 没有 Transcript 就不能写第五章（Earnings Call 摘录）。绝不可用新闻摘要替代。

搜索顺序：
1. **Seeking Alpha**: 搜索 `"[Company] latest earnings call transcript"` → 提取全文
2. **公司 IR 官网**: `investor.[company].com` → 找 "Earnings Call Transcript"
3. **AlphaStreet / Motley Fool**: 搜索 `"[Company] Q[X] [Year] earnings call transcript"`

对于中国公司（如阿里巴巴/拼多多/京东/B站）：
- 搜索 `"[Company] [报告期] earnings call transcript site:seekingalpha.com"` 
- IR 官网通常有英文 Transcript PDF

**Step 1.3: 获取官方 Press Release（仅在脚本未获取到时）**
- 搜索 `"[Company] [quarter] earnings press release"`
- **必须获取官方数字** — 不能只依赖新闻报道的数字

**Step 1.4: 补充数据（仅补充脚本未覆盖的内容）**
- 搜索行业竞品数据（用于第五章竞争格局）
- 搜索共识预期（用于 Beat/Miss 分析）

---

**⛔ Phase 1 完成检查 — 必须满足以下条件才能进入 Phase 2：**

- [ ] ✅ 有完整的 **Earnings Call Transcript**（不是新闻摘要）
- [ ] ✅ 有官方 **Press Release / 财报** 中的核心财务数据
- [ ] ✅ 知道 **报告期**（FY/Q几、起止月份）
- [ ] ✅ 有 **共识预期** 数据（用于 Beat/Miss）

**如果缺少 Transcript**：在报告中第五章明确标注"Earnings Call 完整文稿未公开获取，以下引述来自新闻报道摘要，可能不完整"。**绝不伪造管理层原话。**

---

**Phase 2: 逐章判断数据 → 不够就搜 → 够了才写**

> 🛑 核心原则：**先判断，再搜索，最后写。没有数据就不要写！**

**Step 2.0: 读取脚本保存的数据文件（官方原文优先！）**

> 🛑 **核心原则**: `_press_release.txt` 和 `_transcript.txt` 是**最高质量的官方原文**。
> `_extracted_data.json` 可能提取不完整（LLM 提取会丢数据），所以 **CC 必须自己读原文找数据**。

**必须读的文件（按优先级）：**
1. 📄 `{TICKER}_press_release.txt` — **PR 原文（最重要！）** 分业务收入、费用、KPI 都在这里
2. 📄 `{TICKER}_transcript.txt` — **电话会原文（第二重要！）** 管理层原话和 Q&A
3. 📊 `{TICKER}_extracted_data.json` — LLM 自动提取的结构化数据（**仅作参考**，可能不完整）
4. 📊 `{TICKER}_data.json` — 合并后数据

**CC 工作流**: 读原文 → 自己从原文中提取每章需要的数据 → 数据不够再搜网上

**Step 2.1-2.8: 逐章判断 + 按需搜索 + 写作**

对每一章执行：
```
① 判断: 该章节需要哪些数据？已有数据够不够？
② 搜索: 不够 → 针对性搜索（见下表）
   够了 → 跳过搜索
③ 写作: 数据就绪 → 该章节单独一次 LLM 生成
```

| 章节 | 必要数据 | 判断标准（够=有数字） | 不够时搜什么 |
|------|---------|-------------------|------------|
| 一 KPI | 营收/利润/EPS | extracted_data 有 revenue + net_income | `"[Company] Q[X] earnings beat miss consensus"` |
| 二 Thesis | 综合判断 | 有至少 3 个核心指标 | 一般不需要额外搜 |
| 三 收入 | **分业务收入** | segments 数量 ≥ 2 | `"[Company] revenue by segment breakdown Q[X]"` |
| 四 盈利 | 利润率 + 费用 | margins 有 gross + expenses 非空 | `"[Company] operating expenses R&D SG&A Q[X]"` |
| **五 战略** | **Transcript** | transcript.txt 存在且 > 5000 chars | `"[Company] earnings call transcript Q[X]"` |
| 六 运营 | DAU/MAU/ARPU | kpis 数量 ≥ 2 | `"[Company] DAU MAU ARPU user metrics Q[X]"` |
| 七 前瞻 | Guidance | guidance 非空 | `"[Company] guidance outlook FY[YYYY]"` |
| 八 估值 | P/E P/S | yfinance 或 web 有估值 | `"[Company] valuation PE PS ratio peers"` |

> **每个章节单独一次 LLM 调用**。NEVER 把 8 个章节塞进一次 LLM 调用。
> **如果某章数据搜索后仍不足**：写明"该数据未公开获取"，绝不伪造。

---

**Phase 3: Assembly & Word Output**

> ⚠️ `md_to_word.py` 在 bash 中可能超时。推荐以下备选方案：

**方案 A（推荐）：直接用 Python 代码转换**
```python
import subprocess
result = subprocess.run(
    ["python", "scripts/md_to_word.py", "--input", "report.md", "--output", "report.docx"],
    capture_output=True, text=True, timeout=300
)
```

**方案 B：手动使用 python-docx 生成**
如果 md_to_word.py 不可用，Agent 可以直接用 python-docx 代码生成 Word。参考本文件末尾的"Word 文档格式规范"。

**方案 C：只输出 MD**
如果 Word 转换反复失败，先交付 MD 报告，告知用户后续手动转换。

> **Key**: Agent flexibility means you can adapt search queries per company. Cloud companies need GPU/AI metrics; e-commerce needs GMV/take-rate; social media needs DAU/ARPU. The template's Section 5 (战略专项) is intentionally flexible for this.

### Type 9: LLM Leaderboard Analysis (大模型榜单分析)
**Triggers**: "排行榜", "榜单", "模型对比", "Arena", "Leaderboard", "AI模型排名", "哪个模型最强"
**Data sources**: LMArena (arena.ai), ArtificialAnalysis.ai, SuperCLUE (superclueai.com)
**Read**: `references/type9_leaderboard.md`
**Template**: `templates/leaderboard_analysis.md`
**Script**: `scripts/run_leaderboard.py` (MUST use this script)
**Special**: Multi-source cross-platform comparison with 8-dimension analysis framework

---

### NAS Knowledge Base Search (内部资料搜索)

> **独立工具** — 不属于任何 Type，用户明确要求时单独调用。

**Triggers**: "搜搜NAS", "内部资料", "NAS里有没有", "搜一下存储", "查查内部文档"
**Script**: `scripts/collect_nas.py`
**NAS Path**: `\\NASONE\Data\wechat_info_diary2` (QNAP NAS)
**Index**: `D:\nas_search_index\` (本地 whoosh 全文索引，秒级搜索)

**Agent 工作流：**

```
用户: "帮我搜搜NAS里有没有关于DeepSeek的资料"
  ↓
Step 1: python collect_nas.py --keyword "DeepSeek"
  → 返回匹配文件列表 + 预览片段
  ↓
Step 2: 告诉用户找到了什么，询问是否需要读取/下载/总结
  ↓
Step 3 (按需): python collect_nas.py --read "[文件路径]"
  → 读取完整内容 → LLM 总结
```

**索引管理：**
```bash
# 首次建索引（或新增大量文件后）
python collect_nas.py --build-index

# 强制全量重建
python collect_nas.py --force-rebuild

# 搜索自动用索引（瞬时），无索引则暴力扫描（慢）
python collect_nas.py --keyword "AI" --after 20260301
```

---

## Universal Execution Pipeline

After classifying intent, execute these 8 steps:

### Step 1: Route & Load
- Classify research type (above decision tree)
- Read the matching reference guide from `references/`
- Read the matching template from `templates/` (MUST read fresh every time)

### Step 2: Template-Driven Search Planning
- Parse the template to identify all `[placeholder]` fields
- For each placeholder that needs external data, generate targeted search queries
- Search queries should be in English for maximum coverage; report output in Chinese
- Example: If template has `[当前全球市场规模]`, generate query: `"[industry name] global market size 2025 2026 billion"`

### Step 3: Data Collection
You may use any combination of tools for web data (Tavily, web search, etc.).

**⚠️ For Type 2 (Company Research) with listed companies, you MUST call the financial data script:**
```bash
python scripts/collect_financials.py --ticker 300418 --output data/financial_data.json
# Or use company name (auto-resolves to ticker):
python scripts/collect_financials.py --company "昆仑万维" --output data/financial_data.json
```
This script guarantees: auto stock-type routing (A-stock/US/HK) → structured financial data (income statement, financial indicators, market data) in **seconds**.
- A-stock: akshare (company info) + Sina/Tencent (market data) + EastMoney F10 (financials)
- US/HK: yfinance (all-in-one)
- Every data source has independent try/except — **pipeline never crashes** even if individual APIs fail.
**DO NOT skip this step for listed companies** — web search alone cannot provide precise financial figures.

**⚠️ For arXiv/technical research, you MUST call the fixed pipeline script:**
```bash
python scripts/run_arxiv_pipeline.py --topic "[research topic]" --output data/arxiv_results.json
```
This script guarantees: LLM keyword generation → arXiv search → PDF download → full text extraction.
**DO NOT call `search_arxiv()` directly** — it skips PDF download and full text extraction.

Other data collection scripts:
- `collect_financial_deep.py` — Multi-company financial data extraction (Type 8, SEC/PDF/Web)
- `collect_financials.py` — Structured financial data for listed companies (Type 2)
- `collect_search.py` — Tavily search + web search (all types)
- `collect_twitter.py` — Twitter/X KOL collection (Type 4, 7)
- `collect_substack.py` — Substack article search (Type 4)
- `collect_rss.py` — Blog RSS feeds (Type 6)

**🔄 搜索工具 Fallback 策略（Tavily 不可用时）**

**场景 A：用户未配置 TAVILY_API_KEY**

> 如果 `.env` 中没有 `TAVILY_API_KEY`，Agent **不应报错或中断**，而应直接使用原生工具完成所有搜索和全文提取：
> - **搜索**: 使用 Agent 环境中的 `search_web` / `web_search` 等 MCP 搜索工具
> - **全文提取**: 使用 `read_url_content` 工具直接读取搜索结果的 URL
> - **数据质量几乎等效**，报告不应因此降质

**场景 B：Tavily 配额用完**

`collect_search.py` 支持多 API key 自动轮换（429/402/432 自动切换备用 key）。当所有 key 均耗尽时，脚本会抛出 `TavilyQuotaExhausted` 异常并明确提示。

**两种场景下 Agent 的行为完全一致——无缝切换到原生工具：**

1. **搜索替代**: 改用 Agent 环境中的 `search_web` / `web_search` 等 MCP 搜索工具
2. **全文提取替代**: 改用 `read_url_content` 工具直接读取已知 URL 的页面内容
3. **继续正常写作**: 用替代工具获取的数据质量与 Tavily 基本等效，报告不应因此降质

**⚠️ 替代搜索工具的质量保障规则（MUST FOLLOW）**

替代搜索工具（Google CSE 等）的语义理解能力远弱于 Tavily，容易返回大量不相关结果。Agent 必须执行以下质量保障措施：

1. **Query 拆分**: 长 query 在替代工具上效果极差，必须拆成多个短 query：
   - ❌ `"projector robot with projection capabilities consumer products 2024 2025"`
   - ✅ `"robot projector"` + `"投影机器人 产品"` + `"projection robot consumer 2025"`
2. **结果过滤**: 拿到搜索结果后，必须先扫一遍标题和 snippet，**丢弃明显不相关的结果**（如标题中不含任何目标关键词的学校报告、课程目录、无关 App 等）
3. **URL 优先策略**: 如果已知目标产品/公司的官网 URL，优先用 `read_url_content` 直接读取，而非搜索
4. **中英文双搜**: 中文产品用中文 query 搜效果通常更好，英文产品用英文 query

### Step 4: Full-Text Reading (Critical!)
For articles/papers found in Step 3:
- Use Tavily extract to get full text of web articles/Substack posts
- arXiv papers: `run_arxiv_pipeline.py` already handles PDF download + text extraction
- Feed full text to Gemini for structured extraction
- **NEVER write report content based on search snippets alone**

### Step 5: Data Normalization
Standardize collected data into uniform fields per type (defined in each reference guide).

### Step 6: Quality Check
- Verify data sources are authoritative
- For numbers/statistics: max 3 search attempts. If not found after 3 tries, mark as "未找到相关公开数据（截至搜索日期）"
- For policy documents: MUST find original text or authoritative source before citing
- **ABSOLUTELY NO FABRICATION** of data, quotes, case studies, or sources

### Step 7: Report Generation

**⚠️ You MUST use the fixed report generation script:**
```bash
python scripts/run_report_gen.py --templates template1.md template2.md --data collected_data.json --topic "[topic]" --output report_name
```
This script guarantees:
- Section-by-section generation (one Gemini call per template, avoids truncation)
- Anti-fabrication prompt rules hardcoded into every prompt
- Mandatory source citation format
- Proper handling of missing data (no placeholders)

**DO NOT generate reports by manually calling generate_content()** — the anti-fabrication rules may be missed.

### Step 8: MD → Word Conversion
Handled automatically by `run_report_gen.py` via `save_report()`.

## Gemini Model Fallback Chain

When encountering 503 errors, automatically try models in this order:
1. `models/gemini-2.5-pro`
2. `models/gemini-3.1-pro-preview`
3. `models/gemini-3-pro-preview`
4. `models/gemini-2.5-flash`

Implementation details in `scripts/llm_client.py`.

## Quality Red Lines

1. **ZERO Fabrication (最高优先级)**: 绝对禁止编造任何数据、引用、公司名、案例、实验结果。商业数据和技术数据同等要求。
2. **Mandatory Source Citation**: 报告中每一个数据点、观点、引用都必须标注来源：
   - 商业数据：标注来源URL或机构名（如 "来源: Fortune Business Insights"）
   - 论文数据：标注论文标题和具体 Table/Figure（如 "来源: MetaWorld-X, Table 2"）
   - 推文观点：标注@用户名和推文链接
3. **Data Not Found Rule**: 搜索3次仍找不到的数据，必须如实标注"未找到相关公开数据（截至搜索日期）"，绝不可推测填充
4. **Full-Text Before Analysis**: arXiv论文必须下载PDF提取全文后再分析，禁止仅凭摘要推断实验结果
5. **Policy Originals**: Policy research MUST locate original government documents, not just news reports
6. **Overseas Data**: First identify the authoritative source (which regulator/agency), THEN search that source
7. **Full-Text Reading**: All opinions/quotes must come from LLM reading the full article, not snippets

## Per-Type Quick Reference

| Type | Reference Guide | Template(s) | Data Sources | Special Config |
|------|----------------|-------------|--------------|----------------|
| 1. Product | `references/type1_product_research.md` | `product_research_{hardware,software,service}.md` | Web, Tavily | — |
| 2. Company | `references/type2_company_research.md` | `company_research_{tech,finance}.md` | Web, Tavily | — |
| 3. Industry | `references/type3_industry_research.md` | `industry_research_{commercial,technical}.md` | Web, Tavily, arXiv | — |
| 4. Trend | `references/type4_trend_analysis.md` | `trend_analysis.md` | Web, Tavily, X, Substack | `config/kols.json` |
| 5. Policy | `references/type5_policy_research.md` | `policy_research_{domestic,overseas}.md` | Web, Tavily (site:) | `config/policy_sources.json` |
| 6. Academic | `references/type6_paper_briefing.md` | `paper_briefing.md` | arXiv RSS, Blog RSS | `config/blog_feeds.json` |
| 7. KOL Digest | `references/type7_kol_digest.md` | `kol_weekly_digest.md` | Twitter/X | `config/kols.json` |
| 8A. Financial Data | `references/type8_financial_data.md` | `financial_data_report.md` | SEC, EastMoney, PDF | `collect_financial_deep.py` |
| 8B. Earnings | `references/type8_financial_data.md` | `earnings_quarterly.md` | Transcript, Press, SEC | `collect_earnings.py` (data) |
| 9. Leaderboard | `references/type9_leaderboard.md` | `leaderboard_analysis.md` | LMArena, ArtificialAnalysis | `run_leaderboard.py` |

## Output

All reports are saved to user's workspace directory (`D:\clauderesult\claudeMMDD\`):
- `{topic}_report.md` — Markdown version
- `{topic}_report.docx` — Word version (auto-converted)

### 🚨 强制使用标准化转换脚本

生成 Word 文档时，**必须**使用标准化脚本：

```bash
python scripts/md_to_word.py --input {topic}_report.md --output {topic}_report.docx
```

**禁止**手动用 python-docx 生成 Word，必须调用 `md_to_word.py` 以确保：
- ✅ 字体统一：宋体 + Arial
- ✅ Markdown 符号自动清理
- ✅ 表格样式统一

### Word 文档格式规范（强制执行）

生成 Word 文档时 **必须严格遵循** 以下规范：

#### 字体规范
| 内容类型 | 中文字体 | 英文/数字字体 | 字号 |
|----------|----------|---------------|------|
| 正文 | 宋体 (SimSun) | Arial | 11pt |
| 标题1 | 宋体 (SimSun) | Arial | 16pt 加粗 |
| 标题2 | 宋体 (SimSun) | Arial | 14pt 加粗 |
| 标题3 | 宋体 (SimSun) | Arial | 12pt 加粗 |
| 表格表头 | 宋体 (SimSun) | Arial | 11pt 加粗 白字 |
| 表格内容 | 宋体 (SimSun) | Arial | 10pt |

#### python-docx 字体设置代码
```python
from docx.oxml.ns import qn

# 正文默认字体
style = doc.styles['Normal']
font = style.font
font.name = 'Arial'  # 英文字体
font.size = Pt(11)
style.element.rPr.rFonts.set(qn('w:eastAsia'), '宋体')  # 中文字体

# 每个Run都要设置
run.font.name = 'Arial'
run.element.rPr.rFonts.set(qn('w:eastAsia'), '宋体')
```

#### Markdown 符号清理
在转换 Word 前 **必须清理** 以下 Markdown 语法符号：
- `**粗体**` → 转为 Word 真正的粗体格式，删除 `**` 符号
- `*斜体*` → 转为 Word 斜体格式，删除 `*` 符号
- `` `代码` `` → 删除反引号，可保留为等宽字体
- `[链接文字](URL)` → 保留文字，可添加超链接
- `<br>` → 替换为换行符 `\n`

#### 表格样式
- 表头背景色：`#1B3A5C`（深蓝色）
- 表头文字：白色加粗
- 表格边框：`Table Grid` 样式

#### 禁止事项
- ❌ 禁止在 Word 中保留任何 Markdown 语法符号（`**`、`*`、`` ` ``、`[]()`）
- ❌ 禁止使用 Microsoft YaHei（微软雅黑）作为正文字体
- ❌ 禁止表格单元格内出现 `<br>` 标签

## Python Dependencies

安装命令统一使用 `python -m pip install <package>`

| 包名 | 用途 | 使用脚本 |
|------|------|---------|
| `google-generativeai` | Gemini LLM API | `llm_client.py`, `generate_report.py` 等 |
| `python-docx` | Word 报告生成 | `generate_report.py`, `collect_earnings.py` |
| `requests` | HTTP 请求 | 多个脚本 |
| `beautifulsoup4` | HTML 解析 | `collect_earnings.py`, `collect_financial_deep.py` |
| `pdfplumber` | PDF 文本提取 | `collect_financial_deep.py`, `collect_nas.py` |
| `PyPDF2` | PDF 文本提取 (备选) | `collect_nas.py` (fallback) |
| `akshare` | A股财务数据 | `collect_financials.py` |
| `yfinance` | 美股/港股数据 | `collect_financials.py`, `collect_earnings.py` |
| `whoosh` | NAS 全文搜索索引 | `collect_nas.py` |
| `tavily-python` | Tavily 搜索/提取 API | `collect_search.py` |
| `feedparser` | RSS 解析 | `run_arxiv_pipeline.py` |
| `matplotlib` | 图表生成 (可选) | 报告图表 |
| `pandas` | 数据处理 (可选) | 财务数据分析 |

