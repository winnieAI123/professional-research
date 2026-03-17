# Type 2: Company Research Pipeline

Detailed guide for conducting company research. Covers Tech companies (Part 1) and Finance companies (Part 2).

## Sub-Type Classification

| Sub-Type | Trigger Keywords | Template |
|----------|-----------------|----------|
| **Tech Company** | AI, SaaS, 互联网, 硬件, 软件, 芯片, cloud | `company_research_tech.md` |
| **Finance Company** | 银行, 保险, 支付, 牌照, 合规, 信贷, 资管 | `company_research_finance.md` |

---

## 写作风格总则（Tech Company — 每次 LLM 调用必须附带）

以下指令必须在每个章节的 LLM prompt 中作为 system-level 指令出现：

```
你是一位服务于投资机构的资深行业研究分析师，拥有10年以上科技行业研究经验。

【写作风格要求】
1. 叙事优先：用流畅的段落讲述和分析，不要用 bullet list 罗列信息。数据和事实应自然嵌入叙述中，服务于你的分析论点。
2. 有观点、有判断：每个章节都应有明确的分析结论，不要只是中立地堆砌信息。
3. 表格配合叙述使用：以下场景应主动使用表格——
   - 产品矩阵对比（多代产品演进、多条产品线对比）
   - 竞品多维度横向对比
   - 多年财务数据趋势
   - 供应链关键节点映射
   表格前后必须有分析叙述，表格不能孤立存在。叙述是主体，表格是辅助。
4. 避免机械化表述：不要写"该公司成立于X年，总部位于X市"这类简历式句子。用更自然的叙事过渡。
5. 数据来源自然嵌入：正文中用简短标注（如"据管理层在2025科技日披露"、"据CEO在媒体采访中表示"），URL 和详细出处集中在文末"数据来源"章节。
6. 管理层/专家原话增强可信度：如果搜索到管理层或行业专家的原话/观点，优先在分析中引用——这比二手总结更有说服力。
7. 找不到的数据如实处理：不编造、不推测。可以写"截至研究日期，该数据尚未公开披露"，然后继续分析已知信息。
8. 禁止使用以下套话：综上所述、值得注意的是、不可忽视的是、毋庸置疑、众所周知。

【篇幅与深度要求 — 极其重要！】
9. 整篇报告的总篇幅不设硬上限，但至少 10000 字起步。技术壁垒是核心竞争力的公司（如AI、芯片、机器人），报告总篇幅可达20000-25000字甚至更多。篇幅服从于分析深度，不要为了凑字注水，也不要为了压缩而牺牲分析质量。
10. 章节篇幅按重要性弹性分配：
    - 产品与技术分析：基础 3000-5000 字，技术驱动型公司可扩展至 8000-12000 字
    - 竞争分析：2000-4000 字
    - 商业模式与财务：1500-3000 字
    - 公司概况 / 团队 / 风险 / 前瞻：各 800-2000 字
11. 每个分析要点都要展开论述：不能只给结论，必须给出支撑结论的证据链和推理过程。
    - ❌ "核心技术壁垒：自研ABI架构，与Transformer不同" → 这只是一句话标注
    - ✅ 用2-3段话解释：架构设计思路、为什么构成壁垒、壁垒持久性、竞争对手复制难度
12. 严禁使用"一句话+bullet list"的偷懒格式。如果某个话题值得提及，就值得用至少一段话展开。
    - ❌ "核心产品矩阵：• GLM模型系列 • 智谱清言 • AutoGLM • 清影"
    - ✅ 按产品线分段叙述，每个重要产品独立分析其市场定位、用户规模、竞争力和发展前景
13. 核心技术的子系统深挖框架（适用于产品技术章节的关键技术分析）：
    对公司最核心的2-3项技术，按以下4层结构展开深度分析——
    ① 定位与目标：这项技术解决什么问题？在整体架构中的位置？
    ② 方案与实现：技术路线选择、关键设计决策（不需要工程实现细节，聚焦"为什么这么选"）
    ③ 性能表现与商业影响：这项技术带来了什么商业价值？量化成果如何？
    ④ 工程挑战与风险：量产/规模化的主要障碍是什么？

【语气参考】
写出来的文章应该像一位资深分析师在向基金经理做口头汇报时的语气：专业但不学术化，有洞察但不武断，用证据说话但不堆砌数据。避免纯工程化的技术细节（如公式推导、热力学参数），聚焦于"so what"——这个技术选择对商业前景意味着什么。

【视觉层次要求 — 防止文字墙】
14. 子标题必须有：每个 ## 章节下至少用 2-4 个 ### 子标题划分内容块（如"### 3.1 产品矩阵"、"### 3.2 技术架构"）。超过 2000 字的章节还应使用 #### 做更细分的块。绝对不要输出一大段没有子标题的纯文字。
15. 关键发现开头：每章第一段用引用块（>）写 1-2 句核心发现/结论（如"> 关键发现：公司自研 ABI 架构构成核心壁垒，但量产规模化仍面临成本挑战"），让读者快速抓住本章要点后再展开阅读。
16. 有限加粗：允许对关键数字和结论性判断加粗（如"营收达到 **12.8 亿元**"），但每段最多 1-2 处，禁止整行加粗，禁止滥用。加粗是为了引导读者视线，不是装饰。
17. 禁止扁平 bullet list：绝对不要输出一长串同级缩进的无分组列表。如果需要罗列信息，必须用加粗分类标题分组（如 **B 端机构用户**、**C 端零售用户**），每组前有 1-2 句说明，列表前后有分析段落。一坨扁平 bullet = 不合格。
```

---

## Pipeline: Tech Company

### 章节与搜索策略（7 章 + 核心判断）

核心判断不需要单独搜索，在所有章节写完后综合提炼。

| 章节 | 搜索 Query 策略 | 搜索重点 |
|------|----------------|---------|
| **一、公司概况与发展脉络** | `"[company]" founded history timeline milestones` / `"[公司]" 发展历程 创立 融资` | 创立故事、关键转折、融资轮次、战略变更 |
| **二、核心团队与组织能力** | `"[company]" CEO founder CTO management team background` / `"[CEO名字]" 背景 经历` | 核心人物背景、团队变动、组织架构 |
| **三、产品与技术分析** | `"[company]" products technology architecture` / `"[公司]" 产品 技术路线 核心技术` | 产品矩阵、技术架构、供应链、技术壁垒 |
| **四、商业模式与财务表现** | `"[company]" revenue business model pricing` / `"[公司]" 营收 商业模式 盈利` | 收入结构、定价、盈利能力、现金流 |
| **五、行业格局与竞争分析** | `"[industry]" market size landscape competitors` / `"[行业]" 市场规模 竞争格局 竞品` | 市场规模、竞品对比、竞争壁垒、行业趋势 |
| **六、风险与挑战** | `"[company]" risks challenges regulatory` / `"[公司]" 风险 挑战 监管` | 经营风险、竞争威胁、监管环境 |
| **七、前瞻与展望** | `"[company]" outlook strategy roadmap 2025 2026` / `"[公司]" 规划 展望 下一步` | 战略规划、里程碑事件、管理层指引 |

### 每章搜索深度指南

- 每章至少 2-3 组 query（中英文各一组 + 按需追加）
- 每组 query 取最相关的 2-3 条结果做全文提取
- **第三章（产品与技术）通常是最重的章节**：可能需要 4-6 组 query，覆盖产品线、技术架构、供应链等多个子话题
- **第五章（竞争分析）**：需要额外搜索 2-3 家主要竞品的信息

### 特殊搜索策略

- **上市公司**：必须调用 `collect_financials.py` 获取结构化财务数据，用于第四章
- **有 Crunchbase/PitchBook 条目的公司**：`site:crunchbase.com "[company]"` 获取融资历史
- **有学术论文的技术公司**：搜索 arXiv/Google Scholar 获取技术论文
- **中国公司**：优先使用中文 query 搜索，补充英文 query 获取国际视角

### Key Data Fields（搜索时关注，但不强制全部找到）

- 创立时间、总部、员工规模、融资历史、估值
- 核心管理层背景和关键变动
- 产品线、技术路线、供应链关键节点
- 收入规模、增长率、毛利率、盈利状态
- 市场规模、主要竞品、市场份额
- 商业化进展、量产计划、合作伙伴

---

## Pipeline: Finance Company

### Search Keyword Generation (12 Chapters)

| Chapter | Search Queries |
|---------|---------------|
| 1. Success Factors | `"[company]" success competitive advantage why growth` |
| 2. Basic Info | `"[company]" founded headquarters employees team structure` |
| 3. Funding | `"[company]" funding rounds investors valuation IPO` |
| 4. Founders | `"[CEO name]" background career experience previous company` |
| 5. Users & Market | `"[company]" users market region country user growth demographics` |
| 6. Compliance | `"[company]" license compliance regulation authorized KYC AML` |
| 7. Products | `"[company]" products services card payment wallet lending` |
| 8. Partners | `"[company]" partners Visa Mastercard bank custody KYC provider` |
| 9. Pricing | `"[company]" fees pricing commission subscription charges` |
| 10. Growth | `"[company]" user acquisition growth referral KOL marketing` |
| 11. Business Model | `"[company]" revenue business model TPV transaction volume` |
| 12. Risks | `"[company]" risks regulatory compliance market competition` |

### Special: License Verification
For finance companies, license data is critical. Search strategy:
1. Search `site:[regulator_site] "[company name]"` to verify licenses
2. Cross-reference with `config/policy_sources.json` for regulator sites
3. Always include the regulator's public register URL as source

### Key Data Fields (Finance-specific)
- License types and jurisdictions
- User scale and geographic distribution
- Product matrix (C-end vs B-end)
- Partner ecosystem (issuing banks, KYC providers, custody)
- Fee structure (transaction fees, subscription, spreads)
- Growth strategy (referral tiers, incentive system)
- Revenue breakdown
- Compliance risks

---

## Report Generation — Agent-Driven Per-Chapter

> **Important**: Do NOT use `run_report_gen.py` for company research.
> Use the per-chapter workflow defined in `skill.md` Type 2 section (Phase 1-4).

The Agent should:
1. Read the template and split by `## 一、` / `## 二、` etc. to isolate each chapter's template section
2. For EACH chapter: prepend "写作风格总则" + feed that chapter's template + that chapter's collected data → `generate_content()` → get chapter output
3. After ALL chapters, write 核心判断 (Key Takeaways) based on the full content
4. Concatenate in order → `save_report()` for MD + Word

**Tech company 特别注意**：每次调用 LLM 生成章节时，必须在 prompt 前附加上述"写作风格总则"。这是确保报告读起来像分析师写的（而非机器填充的）的关键。

