import sys, json, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from llm_client import generate_content

output_dir = "data"
os.makedirs(output_dir, exist_ok=True)

with open("data/all_data_summary.json", "r", encoding="utf-8") as f:
    all_data = json.load(f)

twitter_text = str(all_data["twitter"][:40])[:3000]
substack_text = str(all_data["substack"][:8])[:4000]
web_text = str(all_data["web"][:20])[:3000]

print("=== Generating Chapter 1 ===")
p1 = f"""撰写AI Coding前沿趋势研判报告第一章研究背景。

Twitter数据:{twitter_text[:2000]}
Web数据:{web_text[:2000]}

输出完整章节内容：

## 一、研究背景

> 关键发现：[2句核心结论，引用具体数据]

### 1.1 主题定义

[3段：AI Coding定义→从代码补全到Agentic Coding的演进→本报告核心研究问题。引用Karpathy "80% agent coding"、Greg Brockman "renaissance"等观点]

### 1.2 关键玩家生态图

| 类型 | 玩家 | 核心产品 | 市场定位 |
|------|-----|---------|---------|
[至少12行，涵盖：AI原生IDE(Cursor/Windsurf)、平台级(GitHub Copilot/MS)、底层模型(OpenAI/Anthropic/Google/Meta)、云厂商(Amazon Q)、垂直工具(Devin/Replit/v0)]

### 1.3 当前发展阶段

[2-3段：用Gartner曲线定位AI coding现状。引用Greg Brockman"软件开发正经历文艺复兴"原文。说明自2025年12月起的阶跃式能力提升]

---

输出中文，有具体数据和引用"""

ch1 = generate_content(prompt=p1, max_output_tokens=3500)
with open(f"{output_dir}/ch1.md", "w", encoding="utf-8") as f:
    f.write(ch1)
print(f"Ch1: {len(ch1)} chars")

print("\n=== Generating Chapter 2 ===")
p2 = f"""撰写AI Coding前沿趋势研判报告第二章：KOL与行业观点图谱。

Twitter数据:{twitter_text[:4000]}
Substack全文:{substack_text[:5000]}

输出：

## 二、KOL 与行业观点图谱

> 关键发现：[2句，涵盖：乐观派主要观点 + 质疑派主要担忧]

### 2.1 观点分布总览

| 立场 | 代表人物 | 核心观点 | 来源 |
|------|---------|---------|------|
[至少6行]

### 2.2 高互动Twitter推文精选

| 作者 | 推文核心内容（中英对照） | 点赞数 | 立场 |
|------|----------------------|--------|------|
[至少6条，从数据中提取@karpathy, @gdb, @AndrewYNg等]

### 2.3 看好派深度观点

#### Andrej Karpathy (@karpathy)
**来源：** Twitter/X
**核心观点：** [一段话概括]
**原文引用：**
> "[英文原文]"
**中文翻译：** [翻译]
**分析：** [2段分析其论点含义]

#### Greg Brockman (@gdb)  
[同上格式]

#### Andrew Ng (@AndrewYNg)
[同上格式]

### 2.4 质疑与谨慎派观点

#### Gergely Orosz (The Pragmatic Engineer)
**来源：** Substack — "Are AI agents actually slowing us down?"
**核心顾虑：** [概括]
**原文引用：**
> "[英文引用]"
**分析：** [2段]

#### Addy Osmani
**来源：** Substack — "The 80% Problem in Agentic Coding"
**核心顾虑：** [概括]
**原文引用：**
> "[英文引用 - Karpathy引用]"
**分析：** [2段]

---
输出中文（原文保留英文），不编造，只用数据中的真实内容"""

ch2 = generate_content(prompt=p2, max_output_tokens=5000)
with open(f"{output_dir}/ch2.md", "w", encoding="utf-8") as f:
    f.write(ch2)
print(f"Ch2: {len(ch2)} chars")

print("\n=== Generating Chapters 4+5 ===")
p45 = f"""撰写AI Coding前沿趋势研判报告第四章（时间线预判）和第五章（竞争格局分析）。

Web数据:{web_text[:3000]}
Twitter:{twitter_text[:2000]}

输出：

## 四、时间线预判

> 关键发现：[2句核心预判]

### 4.1 预判矩阵

| 时间维度 | 核心预判 | 置信度 | 支撑依据 |
|---------|---------|--------|---------|
| 短期（2026年） | [具体预判3-4条] | 高 | [来源] |
| 中期（2027-2028年） | [具体预判3-4条] | 中 | [来源] |
| 长期（2029-2030年） | [具体预判3-4条] | 低 | [来源] |

### 4.2 2026年关键里程碑

[3段：长周期Agent成熟、多Agent协作框架、IDE演进方向。引用"2026 Agentic Coding Trends Report"的预测]

### 4.3 开发者角色演变路径

[2段：短期角色升级（"10x工程师"概念），中期专业分工变化（初级工程师被压缩），长期：AI原生软件公司]

---

## 五、竞争格局分析

> 关键发现：[2句核心判断]

### 5.1 主战场竞争矩阵

| 公司/产品 | 定位层次 | 核心优势 | 当前进度 | 主要风险 |
|---------|---------|---------|---------|---------|
| GitHub Copilot | 平台级 | 生态整合 | 企业最高采用率 | 产品同质化 |
| Cursor | AI原生IDE | 开发者体验 | 快速增长 | 商业模式待验证 |
| Claude Code (Anthropic) | Agentic工具 | 长任务执行 | Karpathy等头部KOL推荐 | 企业渗透率低 |
| Windsurf (Codeium) | AI原生IDE | Flow模式 | 估值$1.25B | 被Copilot收购传言 |
| Amazon Q Developer | 企业级 | AWS生态 | 企业客户渗透 | 开发者口碑弱 |
| Google Gemini Code | 平台级 | 多模态能力 | 追赶阶段 | 产品节奏慢 |
| Devin (Cognition) | AI工程师 | 全自主能力 | 商业化初期 | 可靠性问题 |
| Replit Agent | 低代码 | 非开发者市场 | 快速增长 | 专业开发者不满足 |

### 5.2 三层竞争结构深度分析

[3段：工具层（IDE/插件）、平台层（云厂商）、底层模型层，分析各层竞争动态和格局趋势]

### 5.3 格局预判：谁将胜出？

[3段：分析胜出路径——AI原生IDE vs 平台整合者，模型能力与产品体验的权衡，网络效应与数据飞轮的积累]

---
输出中文，有具体数据"""

ch45 = generate_content(prompt=p45, max_output_tokens=5000)
with open(f"{output_dir}/ch4_5.md", "w", encoding="utf-8") as f:
    f.write(ch45)
print(f"Ch4+5: {len(ch45)} chars")

print("\nAll chapters generated!")
