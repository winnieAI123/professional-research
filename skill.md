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
> You MUST use one of these two methods for Word conversion:
>
> **Method A (CLI — preferred):**
> ```bash
> python scripts/md_to_word.py report.md --output report.docx
> ```
> **Method B (Python import):**
> ```python
> from md_to_word import convert_md_to_word
> convert_md_to_word("report.md", "report.docx")
> ```
> **Or use `save_report()` which calls the same conversion internally:**
> ```python
> from generate_report import save_report
> save_report(md_content=report_text, topic="Topic_Name")
> ```
>
> ⛔ Do NOT write your own python-docx code. Do NOT use subprocess to call md_to_word.py. Just call the script directly or import the function.
> The script includes automatic table repair (`repair_markdown_tables`) that fixes common LLM output issues (missing `|`, mismatched columns, orphaned rows, unclosed `**`).
>
> **If `md_to_word.py` still fails**: Do NOT fall back to writing your own python-docx code. Instead:
> 1. Read the error message to identify which table/line is malformed
> 2. Fix the Markdown source file (repair the broken table syntax)
> 3. Re-run `md_to_word.py`
> 4. Only if all retries fail: use `save_report()` from `generate_report.py` as final fallback

> **Rule 6: LLM-generated report must have CLEAR VISUAL HIERARCHY.**
> When generating chapter content via LLM:
> - **子标题（MUST）**：每个 `## 章节标题` 下必须有 2-4 个 `###` 子标题划分内容块（如 `### 3.1 产品矩阵`、`### 3.2 技术架构`）。长章节（>2000字）还应使用 `####` 做更细分的块。**不要输出一大段没有子标题的纯文字墙。**
> - **关键发现引用块（MUST）**：每章开头用 `>` 引用块写 1-2 句核心结论（如 `> 关键发现：公司 2025 年营收增长 47%，主要受 API 业务驱动`），让读者快速抓住本章要点。
> - **有限加粗（ALLOWED）**：允许对关键数字和结论性判断使用 `**bold**`（如"营收达到 **12.8 亿元**"），但每段最多 1-2 处，禁止整行加粗，禁止滥用。
> - **章节标题**：使用 `##` 格式（`md_to_word.py` 依赖此解析）。
> - **中文编号**：章节使用中文编号（一、二、三），子标题可用阿拉伯数字（3.1、3.2）。

> **Rule 7: All LLM calls MUST go through `scripts/llm_client.py` — no inline Gemini SDK code.**
> You MUST use one of these functions for all LLM calls:
> ```bash
> cd "C:/Users/wangtian/.claude/skills/professional-research" && python -c "
> import sys; sys.path.insert(0, 'scripts')
> from llm_client import generate_content, generate_report_section, extract_opinions
>
> # For chapter generation:
> result = generate_content(prompt='...', max_output_tokens=8000)
>
> # For report section with template:
> result = generate_report_section(template_content='...', collected_data='...', section_prompt='...')
>
> # For opinion extraction (Type 4):
> opinions = extract_opinions(text='...', topic='...')
> "
> ```
> ⛔ Do NOT write inline `google.genai` / `client.models.generate_content()` code. `llm_client.py` has a **4-model fallback chain** (gemini-2.5-pro → 3.1-pro → 3-pro → 2.5-flash) that automatically handles 503/429 errors. Bypassing it = no fallback = crash on any API hiccup.

> **Rule 8: Do NOT create custom generation scripts — follow the Phase workflow INLINE.**
> 你不能自己写 `generate_xxx_chapters.py` 之类的自定义脚本来生成报告。必须按 Phase 1→2→2.5→3→4 工作流**逐步执行**：
> - Phase 2: 每章逐个搜索 + 收集数据
> - Phase 3: 每章**单独一次** `generate_content()` 调用，直接在 Agent 会话中 inline 执行
> - **绝对不要**把多章打包到一个脚本里一次性跑（如把 1-2 章或 3-6 章合并到一个 LLM 调用）
>
> 原因：多章合并 = 共享 token 预算 = 每章内容被压缩 = 报告质量下降。1 章 1 次 LLM 调用是硬性要求。

## Core Mechanism

**Templates drive everything.** Each research type has a dedicated MD template in `templates/`. Every run:
1. Read the template fresh (user can modify templates anytime)
2. Parse placeholder fields to determine what data to search
3. Collect data from type-specific sources
4. Feed template + collected data to Gemini API
5. Output MD report → convert to Word

This means users only need to edit template MD files to change report format/structure — no code changes needed.

**Search Priority Chain（通用搜索优先级）：**

> Agent 在执行搜索时，按以下优先级选择搜索工具：
>
> 1. **Tavily MCP** ← 首选（搜索质量高 + 支持 `tavily_extract` 全文提取）
> 2. **Google Search MCP** ← Tavily 不可用时 fallback
> 3. **原生 web search** ← 以上 MCP 都不可用时的兜底
>
> **专用数据源（与上述并行，不是 fallback）：**
> - Twitter 数据 → 必须用 `collect_twitter.py` 脚本（无 MCP 替代）
> - Substack 数据 → 必须用 `collect_substack.py` 脚本（无 MCP 替代）
> - arXiv 论文 → 必须用 `collect_arxiv.py` 脚本
> - 上市公司财务 → 必须用 `collect_financials.py` 脚本
> - 财报 Transcript → 必须用 `collect_earnings.py` 脚本（Seeking Alpha API）

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

**🚨 MANDATORY: Software Sub-type — Agent-Driven 逐章写作工作流**

> **NEVER** batch all 15 chapters into one `run_report_gen.py` call for Software product research.
> 15 章共享 token 预算 = 每章内容被压缩 = 扁平 bullet list 泛滥。Software research **MUST** use the per-chapter workflow below.

**Phase 1: 模板解析与产品定位**

1. 读取 `templates/product_research_software.md` — 15 章模板
2. 读取 `references/type1_product_research.md` — 获取搜索关键词模板
3. 识别产品类型（社交 / AI / 工具 / 内容 / 游戏）→ 影响搜索策略

**Phase 2: 逐章数据采集**

按以下搜索策略表，对每章生成针对性 query 并收集数据：

> **基础九维度（1-9）：**

| 章节 | 搜索重点 | 示例 query | 搜索深度 |
|------|---------|-----------|----------|
| 1. 产品定位 | 产品简介、核心用户、场景 | `"[product]" "what is" core users scenario`, `"[产品]" 定位 用户 场景` | 轻（1-2组） |
| 2. 核心玩法 | 核心功能、产品循环 | `"[product]" features functionality "how it works"`, `"[产品]" 核心功能 使用流程` | 中（2-3组） |
| 3. 上瘾机制 | 用户粘性、Hook 模型 | `"[product]" engagement retention habit hook`, `"[产品]" 用户粘性 打开频次` | 轻（1-2组） |
| 4. 增长机制 | 获客渠道、裂变传播 | `"[product]" user growth download "app store"`, `"[产品]" 用户增长 获客 裂变` | 中（2-3组） |
| 5. 留存机制 | 留存数据、社区运营 | `"[product]" retention churn community`, `"[产品]" 留存率 用户流失` | 中（2-3组） |
| 6. 商业模式 | 收入来源、定价策略 | `"[product]" revenue business model pricing subscription`, `"[产品]" 盈利 商业模式` | 中（2-3组） |
| 7. 关键指标 | MAU/DAU/ARR/留存率 | `"[product]" MAU DAU revenue growth rate 2025`, `site:questmobile.com.cn "[产品]"` | 中（2-3组） |
| 8. 护城河 | 竞争壁垒、网络效应 | `"[product]" competitive advantage moat network effect`, `"[产品]" 竞争壁垒` | 轻-中（1-2组） |
| 9. 最终判断 | 最后写，无需搜索 | — | 无 |

> **深度分析六维度（10-15）— 必须全部覆盖：**

| 章节 | 搜索重点 | 示例 query | 搜索深度 |
|------|---------|-----------|----------|
| **10. 营销策略** | 营销案例、CAC、渠道 | `"[product]" marketing campaign strategy CAC`, `"[产品]" 营销 投放 获客成本` | **中-重（3-4组）** |
| **11. 产品创新** | 功能更新、差异化玩法 | `"[product]" new features update changelog`, `"[产品]" 功能更新 创新 差异化` | **重（3-5组）** |
| **12. 用户洞察** | 用户评论、留存驱动 | `"[product]" user reviews feedback "app store review"`, `"[产品]" 用户评价 口碑 吐槽` | **中-重（2-3组）** |
| 13. 商业化深度 | 付费墙、广告、生态 | `"[product]" subscription pricing paywall "ad revenue"`, `"[产品]" 付费 订阅 广告` | 中（2-3组） |
| 14. 行业动态 | 融资、合作、政策 | `"[product]" funding investment valuation`, `site:itjuzi.com "[产品]"` | 中（2-3组） |
| 15. 风险与机会 | 监管、竞争、市场机会 | `"[product]" privacy regulation risk opportunity`, `"[产品]" 风险 监管` | 轻-中（1-2组） |

每章数据收集规则：
1. **Search**: 英文 + 中文各 1-2 条 query
2. **Read full text**: 对 2-3 条最相关结果调用 `tavily_extract()` 获取全文
3. **Extract**: 自己阅读全文，提取具体数字/事实 + 来源 URL
4. **Move on**: 有数据 OR 确认不可得后才移下一章

> **第 11 章（产品创新）通常是最重的**，需要搜产品更新日志、媒体评测、竞品对比。**第 12 章（用户洞察）** 需要搜 App Store 评论和社交媒体反馈。

**Phase 2.5: Gap Analysis & Supplementary Search**

> 15 章数据收集完成后，检查完整性：
>
> 1. **对照模板**：检查每章关键字段（MAU/DAU、营收、留存率、CAC、核心功能清单、竞品列表等）是否已有数据
> 2. **判断缺失严重性**：
>    - 缺失 ≥3 个关键字段 → 做 1-2 轮补充搜索
>    - 缺失 <3 个 → 直接进 Phase 3
> 3. **补充搜索最多 2 轮**，不要无限重试

**Phase 3: Per-Chapter Report Generation（15 次独立 LLM 调用）**

For EACH chapter, call `generate_content()` separately.每次调用必须附带以下写作风格指令：

> **软件产品写作风格指令（Software 每次 LLM 调用必须附带）：**
>
> 你是一位资深互联网产品分析师，擅长新产品拆解与增长策略研究。请以分析师视角撰写产品研究报告，遵守以下风格：
>
> 1. **叙述分析为主，表格为辅**：模板中的表格是数据组织参考，不是必须填的空白表。每章先用 2-3 段分析性文字阐述核心洞察，再用表格呈现结构化数据。
> 2. **子标题必须有**：每个章节下至少 2-3 个 `###` 子标题划分内容块。
> 3. **关键发现开头**：每章第一段用 `>` 引用块写 1-2 句核心发现。
> 4. **禁止扁平 bullet list**：如需列举，必须用加粗分类标题分组，每组前有说明性文字。
> 5. **有限加粗**：关键数字和结论可加粗，每段最多 1-2 处。
> 6. **Hook / 增长 / 留存分析要有框架感**：用 Nir Eyal Hook 模型（触发→行动→奖励→投入）或 AARRR 等框架组织分析，不要散点罗列。
> 7. **用户洞察要引原话**：App Store/社媒评论直接引用用户原话增强可信度。
> 8. **商业模式要算账**：付费率 × ARPU × MAU = 营收估算，不要只列定价。
> 9. **竞品对比要有洞察**：不要做功能对比表就完事，分析差异化定位和护城河。
> 10. **禁止空洞措辞**：不要"前景广阔"、"潜力巨大"，所有判断有数据支撑。
> 11. **自然引用来源**：如"据 QuestMobile 数据"、"App Store 用户评论显示"。

> **15 次调用，1 章 1 次。第 9 章（最终判断）最后写**，综合前 14 章提炼。

**Phase 4: Assembly & Word Output (MANDATORY)**

按模板顺序（1→2→…→15→数据来源→附录）合并所有章节 →
调用 `save_report()` 输出 MD + Word。

> 🛑 **This phase is NOT optional.** MUST produce both `.md` and `.docx`.

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

**Phase 1: Template Parsing & Scope Decision**

1. Read the appropriate template:
   - Tech: `templates/company_research_tech.md` — 7 chapters + 核心判断
   - Finance: `templates/company_research_finance.md` — 12 chapters
2. Read `references/type2_company_research.md` — 获取写作风格总则（Phase 3 每次 LLM 调用必须附带）
3. 判断公司是否上市 → 如果是，Phase 2 中的第四章必须调用 `collect_financials.py`

**Phase 2: Per-Chapter Data Collection**

For EACH chapter, generate targeted queries and collect data.参考下表确定每章的搜索策略和搜索深度：

> **Tech 公司搜索策略（7 章）：**

| 章节 | 搜索重点 | 示例 query | 搜索深度 |
|------|---------|-----------|----------|
| 一、公司概况与发展脉络 | 创立故事、融资轮次、战略变更、关键转折 | `"[company]" founded history milestones`, `"[公司]" 发展历程 创立 融资` | 中（2-3组query） |
| 二、核心团队与组织能力 | 核心人物背景、团队变动、组织架构 | `"[company]" CEO founder CTO management`, `"[CEO名]" 背景 经历` | 轻-中（2组query） |
| 三、产品与技术分析 | 产品矩阵、技术架构、供应链、技术壁垒 | `"[company]" products technology architecture`, `"[公司]" 产品 技术路线`, `site:arxiv.org "[company]"` | **重（4-6组query）** |
| 四、商业模式与财务表现 | 收入结构、定价、盈利、现金流 | `"[company]" revenue business model pricing`, `"[公司]" 营收 盈利`; **上市公司另加** `collect_financials.py` | 中-重（2-3组query + 财务脚本） |
| 五、行业格局与竞争分析 | 市场规模、竞品对比、行业趋势 | `"[industry]" market size competitors`, `site:crunchbase.com "[competitor]"` | **重（3-4组query + 逐竞品搜索）** |
| 六、风险与挑战 | 经营/竞争/监管/执行风险 | `"[company]" risks challenges regulatory`, `"[公司]" 风险 挑战` | 轻-中（1-2组query） |
| 七、前瞻与展望 | 战略规划、里程碑、管理层指引 | `"[company]" outlook strategy roadmap 2025 2026`, `"[公司]" 规划 展望` | 轻（1-2组query） |

> **Finance 公司搜索策略（12 章）：**

| 章节 | 搜索重点 | 示例 query | 搜索深度 |
|------|---------|-----------|----------|
| 1. 成功要素一句话 | 公司定位、核心叙事 | 最后写，无需单独搜索 | 无 |
| 2. 公司基本信息 | 成立时间、总部、规模 | `"[company]" fintech founded headquarters`, `"[公司]" 成立 总部` | 轻（1-2组） |
| 3. 融资历史 | 轮次、估值、投资者 | `site:crunchbase.com "[company]"`, `"[company]" funding series valuation` | 中（2-3组） |
| 4. 创始团队 | 核心人物、背景 | `"[company]" CEO founder background`, `"[CEO名]" 经历` | 轻-中（2组） |
| 5. 用户与市场 | MAU、覆盖地区、画像 | `"[company]" users MAU markets`, `"[公司]" 用户量 覆盖` | 中（2-3组） |
| **6. 合规与牌照** | **监管牌照、KYC/AML** | `site:fca.org.uk "[company]"`, `site:finma.ch "[company]"`, `"[company]" license compliance` | **重（3-5组，逐监管机构验证）** |
| 7. 产品矩阵 | C端/B端产品功能 | `"[company]" products features app`, `"[公司]" 产品 服务` | 中-重（2-4组） |
| **8. 合作伙伴生态** | **卡组织、BIN Sponsor、托管** | `"[company]" partner Visa Mastercard issuer`, `"[company]" BIN sponsor custody` | **中-重（2-3组）** |
| **9. 定价策略** | **费率、手续费、会员** | `"[company]" pricing fees charges`, `"[company]" fee schedule` | 中（2-3组） |
| 10. 增长策略 | 获客、推荐、社群 | `"[company]" growth referral program`, `"[公司]" 增长 获客` | 轻-中（1-2组） |
| 11. 商业模式 | TPV、营收、成本 | `"[company]" revenue business model TPV`, `"[公司]" 营收 模式` | 中-重（2-3组） |
| 12. 风险评估 | 合规/业务/市场风险 | `"[company]" risks regulatory challenges`, `"[公司]" 风险` | 中（2-3组） |

> **Finance 特殊搜索要求**：
> - **第 6 章（合规与牌照）是最关键的章节** — 必须逐个监管机构做 `site:` 验证（FCA, BaFin, FINMA, MAS, SEC, CSRC 等），不能靠公司自述
> - **第 8 章（合作伙伴）** — 卡组织合作关系直接决定业务可行性，必须验证真实性
> - **第 1 章（成功要素）最后写** — 类似 Tech 的"核心判断"，等全部章节完成后综合提炼

每章数据收集规则：
1. **Search**: 英文 + 中文各 1-2 条 query。Call `tavily_search()` from `collect_search.py`
2. **Read full text**: 对 2-3 条最相关结果，call `tavily_extract()` 获取全文
3. **Extract data points**: 自己阅读全文，提取具体数字/事实 + 来源 URL
4. **Adapt**: 搜不到有用结果？换关键词、加 `site:` 限定（如 `site:crunchbase.com`、`site:pitchbook.com`）、或换语言重试
5. **Move on**: 有了数据 OR 确认数据不可得后，才移到下一章

> **Key principle**: You are the orchestrator. You decide what to search, how many results to read, and when to try alternative queries. This flexibility is WHY we don't use a pipeline script for company research.

> **第三章（产品与技术）通常是最重的章节**，可能需要 4-6 组 query，覆盖产品线、技术架构、供应链等多个子话题。**第五章（竞争分析）** 需要额外搜索 2-3 家主要竞品的各自信息。Agent 应按章节重要性灵活分配搜索深度。

**特殊搜索策略**（根据公司类型追加）：
- **上市公司**：第四章必须调用 `collect_financials.py` 获取结构化财务数据
  ```bash
  python scripts/collect_financials.py --ticker 300418 --output data/fin.json
  # Or: python scripts/collect_financials.py --company "昆仑万维" --output data/fin.json
  ```
  Web 搜索无法替代这个脚本的精度。**DO NOT skip this for listed companies.**
- **有 Crunchbase/PitchBook 条目**：`site:crunchbase.com "[company]"` 获取融资历史
- **有学术论文的技术公司**：搜索 `site:arxiv.org "[company]"` 或 Google Scholar
- **中国公司**：优先使用中文 query，补充英文获取国际视角

**Phase 2.5: Gap Analysis & Supplementary Search**

> 所有章节的 Phase 2 数据收集完成后，在进入 Phase 3 之前，做一次数据完整性检查：
>
> 1. **对照模板**：读取模板中每个章节的关键字段（如“营收”“用户量”“融资历史”“产品线”“竞品”等），检查哪些已有数据、哪些缺失
> 2. **判断缺失严重性**：
>    - 缺失 ≥3 个关键字段 → 做 1-2 轮补充搜索（用 web search MCP 或 tavily）
>    - 缺失 <3 个关键字段 → 直接进 Phase 3，在报告中标注“截至研究日期，未公开披露”
> 3. **补充搜索策略**：针对缺失字段生成定向 query（如缺融资数据 → `site:crunchbase.com “[company]”`，缺用户量 → `“[company]” MAU users 2025`）
> 4. **不要过度搜索**：补充搜索最多 2 轮，每轮 2-3 条 query。真找不到就接受数据缺失，不要无限重试

**Phase 3: Per-Chapter Report Generation（写作风格是关键！）**

For EACH chapter, call `generate_content()` separately with:
- **写作风格指令（MUST prepend!）**:
  - **Tech 公司**：从 `references/type2_company_research.md` 的"写作风格总则"复制完整风格指令作为 prompt 前缀
  - **Finance 公司**：使用下方的"金融公司写作风格指令"
- The specific chapter's template section (including the `<!-- 写作指引 -->` comments)
- ALL data points you collected for that chapter (no truncation because you feed directly)
- 反编造规则：没数据 = "截至研究日期，该数据尚未公开披露"（但不要因为个别数据缺失就停止分析）
- 关键数据必须自然引用来源（如"据管理层在2025科技日披露"），URL 和详细出处集中在文末数据来源章节

> **金融公司写作风格指令（Finance 公司每次 LLM 调用必须附带）：**
>
> 你是一位资深金融科技行业分析师。请以分析师视角撰写研究报告，遵守以下风格：
>
> 1. **像分析师写报告，不是填表**：模板中的表格是数据组织的参考结构，但你的输出应该以**叙述性分析为主，表格为辅**。每个章节先用 2-3 段分析性文字阐述关键发现和判断，再用表格呈现结构化数据。纯表格堆砌 = 不合格。
> 2. **合规与牌照要有深度**：不要简单罗列牌照清单。分析牌照布局的战略意图（为什么选这些地区？），合规成本对商业模式的影响，以及监管风险的具体传导路径。
> 3. **商业模式要算账**：TPV -> Take Rate -> Revenue -> 成本结构 -> 盈利路径，形成完整的经济模型叙事，不要只列数字。
> 4. **竞品对比要有洞察**：不要做功能对比表就完事，要分析差异化定位、目标客群区隔、护城河来源。
> 5. **风险分析要具体**：每个风险要有触发条件 -> 影响路径 -> 量化影响估计 -> 缓解措施的完整逻辑链。
> 6. **禁止空洞措辞**：不要用"具有较大发展潜力"、"市场前景广阔"。所有判断必须有数据支撑或逻辑推导。
> 7. **自然引用来源**：关键数据在正文中自然注明（如"据 Crunchbase 数据"、"FCA 注册记录确认"），URL 集中在末尾 DATA SOURCES。
> 8. **子标题必须有**：每个 `##` 章节下至少用 2-4 个 `###` 子标题划分内容块。不要输出一大段没有子标题的文字墙。
> 9. **关键发现开头**：每章第一段用 `>` 引用块写 1-2 句核心结论（如 `> 关键发现：公司已获 FCA 和 MAS 双牌照，合规成本占运营支出约 15%`），让读者快速抓住要点。
> 10. **有限加粗**：允许对关键数字和结论性判断加粗（如"TPV 达到 **28 亿美元**"），每段最多 1-2 处，禁止整行加粗。
> 11. **禁止扁平 bullet list**：绝对不要输出一长串同级缩进的无分组列表。如果需要罗列信息，必须：(a) 用加粗分类标题分组（如 **B 端机构用户**、**C 端零售用户**、**开发者生态**），(b) 每组前用 1-2 句话说明这类用户的特征和战略意义，(c) 列表前后必须有分析性段落。一坨扁平 bullet = 不合格。

> **NEVER generate the entire report in one LLM call.** Tech = 7 calls, Finance = 12 calls. One call per chapter.

> **核心判断 / 成功要素一句话 — 最后写**：所有章节完成后综合提炼。Tech 放报告最前面（核心判断），Finance 放第 1 章（成功要素一句话）。不另外搜索数据。

**Phase 4: Assembly & Word Output (MANDATORY — DO NOT SKIP)**

按最终报告顺序合并所有章节：
- Tech: 核心判断 → 一 → 二 → 三 → 四 → 五 → 六 → 七 → 数据来源
- Finance: 一 → 二 → … → 十二 → 数据来源

Call `save_report()` from `generate_report.py` for MD + Word.

> 🛑 **This phase is NOT optional.** You MUST produce both `.md` and `.docx` files. Do NOT stop after generating Markdown and ask the user if they want Word — just generate it.



### Type 3: Industry Panorama (行业全景研究)
**Triggers**: "行业", "赛道", "市场", "industry", "market overview", macro-level perspective
**Sub-types**:
- **Commercial only**: Consumer/traditional industries (smart glasses, fintech, etc.) → use template `templates/industry_research_commercial.md`
- **Commercial + Technical**: User mentions technical routes/architecture/papers → ALSO use template `templates/industry_research_technical.md` and search arXiv
**Data sources**: Web search, Tavily, arXiv (for technical part)
**Read**: `references/type3_industry_research.md`

**🚨 MANDATORY: Agent-Driven Chapter-by-Chapter Workflow**

> **NEVER** batch all chapters into one `run_report_gen.py` call.
> `run_report_gen.py` truncates data to 15000 chars → most search data discarded → report filled with generic statements.
> Industry research **MUST** use the per-chapter workflow below.

**Phase 1: Template Parsing & Scope Decision**

1. Read `templates/industry_research_commercial.md` — identify 4 chapters (市场机会 / 竞争格局 / 发展趋势 / 风险因素)
2. Decide if Technical part is needed (user mentions 技术路线/架构/论文/algorithm)
   - If yes: also read `templates/industry_research_technical.md` — 4 additional chapters (技术路线概览 / 核心论文分析 / 技术趋势洞察 / 技术壁垒与投资启示)
3. Total chapters: 4 (commercial only) or 8 (commercial + technical)

**Phase 2: Per-Chapter Data Collection**

For EACH chapter, generate 2-4 targeted queries (English + Chinese) and collect data:

> **商业篇搜索策略（参考 `references/type3_industry_research.md` 获取完整 query 模板）：**

| 章节 | 搜索重点 | 示例 query | 搜索深度 |
|------|---------|-----------|----------|
| 一、市场机会 | 市场规模、CAGR、增长驱动力、价值链、BOM成本 | `"[industry] market size 2025 2026 forecast billion"`, `"[行业] 市场规模 增长率"` | 重（3-4组query） |
| 二、竞争格局 | 行业玩家、份额、融资、新进入者、替代品 | `"[industry] market share top companies"`, `site:crunchbase.com "[company]"` | 重（3-4组query + 逐竞品搜索） |
| 三、发展趋势 | 短中长期趋势、受益企业 | `"[industry] future trends forecast 2026"` | 中（2-3组query） |
| 四、风险因素 | 技术/政策/竞争/市场风险 | `"[industry] risks challenges regulatory"` | 轻（1-2组query） |

> **技术篇数据收集（如需要）：**

| 章节 | 数据来源 | 方法 |
|------|---------|------|
| 一、技术路线概览 | Tavily + arXiv | 先 Web 搜各技术路线概况，再调用 `run_arxiv_pipeline.py` 获取论文 |
| 二、核心论文深度分析 | arXiv 全文 | 用 Phase 2 获取的论文全文，逐篇提取方法/结果/启示 |
| 三、技术趋势洞察 | 综合分析 | 无需额外搜索，基于前两章数据综合判断 |
| 四、技术壁垒与投资启示 | Tavily | 搜索 `"[industry] technology barriers moat investment"` |

每章数据收集规则：
1. **Search**: 英文 + 中文各 1-2 条 query。Call `tavily_search()` from `collect_search.py`
2. **Read full text**: 对 2-3 条最相关结果，call `tavily_extract()` 获取全文
3. **Extract data points**: 自己阅读全文，提取具体数字/事实 + 来源 URL
4. **Adapt**: 搜不到有用结果？换关键词、加 `site:` 限定、或换语言重试
5. **Move on**: 有了数据 OR 确认数据不可得后，才移到下一章

> **第二章（竞争格局）通常是最重的章节**，需要搜索 3-5 家主要玩家的各自信息。Agent 应按章节重要性灵活分配搜索深度。

**Phase 2.5: Gap Analysis & Supplementary Search**

> Phase 2 全部章节数据收集完成后，检查数据完整性：
>
> 1. **对照模板**：检查每章的关键字段（市场规模、竞品名单、价值链数据、政策文件、技术路线等）是否已有数据
> 2. **判断缺失严重性**：
>    - 缺失 ≥3 个关键字段 → 做 1-2 轮补充搜索（web search MCP 或 tavily）
>    - 缺失 <3 个 → 直接进 Phase 3，在报告中标注“未找到相关数据（截至搜索日期）”
> 3. **补充搜索策略**：针对缺失字段生成定向 query，最多 2 轮，每轮 2-3 条
> 4. **不要无限重试**：真找不到就接受数据缺失

**Phase 3: Per-Chapter Report Generation**

For EACH chapter, call `generate_content()` separately with:
- 该章的模板 section（包含表格结构和占位符）
- 该章收集到的所有数据（不截断，直接喂入）
- 反编造规则：没数据 = "截至研究日期，该信息尚未公开披露"
- 关键数据必须自然引用来源（如"据 Grand View Research 预测"），所有 URL 汇总到末尾数据来源部分

> **NEVER generate the entire report in one LLM call.** One call per chapter ensures each chapter gets full context.

> **写作风格**：行业分析师视角，用数据说话，避免空洞描述。表格中的数据格式统一（如"$12.5B"、"23.4%"），避免使用 `**` 等 Markdown 格式符号。

**Phase 4: Assembly & Word Output (MANDATORY — DO NOT SKIP)**

1. 如果只有商业篇：按顺序（一 → 二 → 三 → 四 → 数据来源）合并
2. 如果有商业 + 技术：先合并商业篇，用 `---` 分隔，再合并技术篇
3. Call `save_report()` from `generate_report.py` for MD + Word

> 🛑 **This phase is NOT optional.** You MUST produce both `.md` and `.docx` files.


### Type 4: Trend Analysis (趋势研判与机会发现)
**Triggers**: "趋势", "预判", "机会", "trend", "forecast", "大佬观点", "KOL opinions"
**Data sources**: Web search, Tavily, Twitter/X, Substack, arXiv (optional)
**Read**: `references/type4_trend_analysis.md`
**Template**: `templates/trend_analysis.md`
**Special**: Load `config/kols.json` for KOL list

**🚨 MANDATORY: Agent-Driven Workflow (Multi-Source → Per-Chapter Generation)**

> **NEVER** batch all data into one `run_report_gen.py` call.
> Trend analysis has data from 4 sources (Twitter + Substack + Web + arXiv). A one-shot generation truncates most of it.
> Trend analysis **MUST** use the workflow below.

> **Core Principle**: Every trend conclusion must be supported by at least 2 of the 3 primary sources (Twitter, Substack, Web). No single-source conclusions.

**Phase 1: Template Parsing & Data Source Preparation**

1. Read `templates/trend_analysis.md` — identify 8 chapters (研究背景 / KOL观点图谱 / 核心分歧 / 时间线预判 / 竞争格局 / 机会窗口 / 信号监测 / 学术论文)
2. Read `references/type4_trend_analysis.md` — 获取数据采集管线详细说明和标准化格式
3. Load `config/kols.json` — 获取 KOL 用户名列表
4. 判断是否需要 arXiv（用户话题涉及技术范式变化时才需要）

**Phase 2: Multi-Source Data Collection（先按数据源收集，不按章节）**

> **与 Type 2/3 的关键区别**：趋势分析的数据源是异构的（推文 / 长文 / 搜索 / 论文），先收集所有源的数据，Phase 3 再按章节分配。

> ⛔ **Twitter 和 Substack 没有 MCP 工具替代品！** 你不能用 `tavily-search` 或 `google-search` MCP 替代。必须运行以下 Python 脚本。Web 搜索可以用 MCP 工具或脚本，但 Twitter 和 Substack 只能用脚本。

所有脚本调用的工作目录：`C:/Users/wangtian/.claude/skills/professional-research`

**Source 1: Twitter/X KOL 观点** ← 最重要的数据源，不可跳过
```bash
cd "C:/Users/wangtian/.claude/skills/professional-research" && python -c "
import sys, json
sys.path.insert(0, 'scripts')
from collect_twitter import search_kol_tweets, search_topic_tweets
from utils import read_config

kols = read_config('kols.json')
kol_usernames = [k['username'] for k in kols['kols']]

# 如果话题涉及具身智能/机器人，追加 robotics KOL 列表
# 触发词：robot, humanoid, embodied, 具身, 人形, 机器人
if any(w in '[TOPIC]'.lower() for w in ['robot', 'humanoid', 'embodied', '具身', '人形', '机器人']):
    kol_usernames += [k['username'] for k in kols.get('robotics', [])]
    print(f'Robotics topic detected, added {len(kols.get(\"robotics\", []))} robotics KOLs')

# KOL 定向搜索
kol_tweets = search_kol_tweets(kol_usernames, '[TOPIC_ENGLISH]', tweets_per_kol=10)
print(f'KOL tweets: {len(kol_tweets)}')

# 话题广播搜索
topic_tweets = search_topic_tweets('[TOPIC_ENGLISH] trend prediction', total_count=30)
print(f'Topic tweets: {len(topic_tweets)}')

# 保存结果
all_tweets = kol_tweets + topic_tweets
with open('data/twitter_data.json', 'w', encoding='utf-8') as f:
    json.dump(all_tweets, f, ensure_ascii=False, indent=2)
print(f'Saved {len(all_tweets)} tweets to data/twitter_data.json')
"
```

**Source 2: Substack 深度文章** ← 不可跳过
```bash
cd "C:/Users/wangtian/.claude/skills/professional-research" && python -c "
import sys, json
sys.path.insert(0, 'scripts')
from collect_substack import search_substack, get_full_articles

posts = search_substack('[TOPIC_ENGLISH] analysis', max_pages=3)
posts = get_full_articles(posts, max_articles=10)  # Tavily 全文提取
print(f'Substack articles: {len(posts)}, with full text: {sum(1 for p in posts if p.get(\"full_content\"))}')

with open('data/substack_data.json', 'w', encoding='utf-8') as f:
    json.dump(posts, f, ensure_ascii=False, indent=2)
print(f'Saved to data/substack_data.json')
"
```
> ⚠️ `search_substack()` 只返回 500 字预览，必须调用 `get_full_articles()` 获取全文。只有读了全文的文章才能出现在报告中。

**Source 3: Web 搜索**
可以用 Tavily MCP 工具，也可以用脚本：
```bash
cd "C:/Users/wangtian/.claude/skills/professional-research" && python -c "
import sys, json
sys.path.insert(0, 'scripts')
from collect_search import multi_query_search, tavily_extract

results = multi_query_search(
    queries=[
        '[TOPIC] trend forecast analysis 2025 2026',
        '[TOPIC] market prediction future opportunity',
        '[TOPIC] 趋势 预测 行业分析',
    ],
    max_results_per_query=5,
)
# 全文提取 top 5
urls = [r['url'] for r in results[:5]]
full_content = tavily_extract(urls)

with open('data/web_data.json', 'w', encoding='utf-8') as f:
    json.dump({'search': results, 'full_text': full_content}, f, ensure_ascii=False, indent=2)
print(f'Saved {len(results)} results + {len(full_content)} full texts')
"
```

**Source 4: arXiv（可选，仅当话题涉及技术范式变化时）**
```bash
cd "C:/Users/wangtian/.claude/skills/professional-research" && python -c "
import sys, json
sys.path.insert(0, 'scripts')
from collect_arxiv import fetch_and_analyze_papers
papers = fetch_and_analyze_papers(query='\"[TOPIC]\" AND (\"trend\" OR \"benchmark\")', max_results=5)
with open('data/arxiv_data.json', 'w', encoding='utf-8') as f:
    json.dump(papers, f, ensure_ascii=False, indent=2)
print(f'Saved {len(papers)} papers')
"
```

**🚨 Phase 2.5: Data Source Validation + Gap Analysis (MANDATORY CHECKPOINT)**

> **步骤 A: 数据源校验**
> 1. ✅ Twitter data exists (`data/twitter_data.json` OR you have tweet data in memory)
> 2. ✅ Substack data exists (`data/substack_data.json` OR you have article data in memory)
> 3. ✅ Web search data exists
>
> **如果 Twitter 或 Substack 数据缺失 → 停下！回到 Phase 2 执行对应的 Python 脚本。**
> **用 Tavily/Google MCP 搜到的结果不能算作 Twitter 或 Substack 数据。**
>
> **步骤 B: 字段完整性检查**
> 对照模板 8 章的关键字段（关键玩家、KOL 观点分布、争议焦点、时间线预判、竞争格局等），检查哪些已有数据、哪些薄弱：
> - 缺失 ≥3 个关键字段 → 用 web search MCP 或 tavily 做 1-2 轮补充搜索
> - 缺失 <3 个 → 直接进 Phase 3，报告中标注“本次数据中未发现相关信息”
> - 补充搜索最多 2 轮，每轮 2-3 条 query，不要无限重试

**Phase 3: Per-Chapter Report Generation**

每章单独一次 LLM 调用，喂入该章所需的数据子集：

| 章节 | 主要数据来源 | LLM 任务 |
|------|------------|---------|
| 一、研究背景 | Web 搜索结果 | 定义主题 + 关键玩家梳理 |
| 二、KOL 与行业观点图谱 | **Twitter + Substack 全文** | 按 看好/看衰/中立 分类，提取原文引用。**必须标注每条观点的来源URL和作者** |
| 三、核心分歧点 | Twitter + Substack + Web | 交叉对比正反方论据，识别根本分歧 |
| 四、时间线预判 | 综合所有来源 | 短/中/长期预判 + 置信度 + 支撑来源 |
| 五、竞争格局分析 | Web 搜索 + Twitter | 各公司/团队布局、进度、优势 |
| 六、机会窗口 | 综合所有来源 | 时间窗口 + 所需能力 + 竞争烈度 + 风险 |
| 七、信号监测清单 | 综合分析（无需额外数据） | 可验证的正/负面信号 |
| 八、相关学术论文 | arXiv 数据（如有） | 论文标题 + 中文摘要 + 链接 |

每章 LLM 调用规则：
- 传入该章的模板 section + 对应数据子集（无截断）
- 反编造规则：没有看衰派数据就写"本次数据中未发现明确看衰观点"，不要编造
- **第二章（KOL 观点图谱）是最核心的章节**：每条观点必须有 `original_quote`（原文引用）、`source_url`、`author`。Agent 未读全文的文章，其观点不得出现在报告中
- 写作风格：分析师视角，避免 `**bold**` 等 Markdown 格式

> **NEVER generate the entire 8-chapter report in one LLM call.** One call per chapter.

**Phase 4: Assembly & Word Output (MANDATORY — DO NOT SKIP)**

按顺序合并（一 → 二 → 三 → 四 → 五 → 六 → 七 → 八 → DATA SOURCES），call `save_report()` from `generate_report.py` for MD + Word.

> 🛑 **This phase is NOT optional.** You MUST produce both `.md` and `.docx` files.


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

