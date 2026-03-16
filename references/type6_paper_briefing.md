# Type 6: Academic Briefing Pipeline

Daily/periodic tracking of AI academic papers and lab blog posts, producing concise briefings for non-technical stakeholders.

## Data Sources

| Source | Method | Content |
|--------|--------|---------|
| arXiv RSS | Daily RSS feeds | New papers (title + abstract) |
| AI Lab Blogs | RSS feeds | Google AI, OpenAI, DeepMind, HuggingFace, Anthropic, 机器之心 |

## Pipeline

### Step 1: Collect arXiv Papers via RSS

```python
from collect_rss import fetch_arxiv_rss

# Use default categories or configure custom ones
papers = fetch_arxiv_rss()
# Returns papers with: arxiv_id, title, abstract, link, category
```

To customize categories, modify `config/blog_feeds.json` → `arxiv_categories`.

### Step 2: Collect Blog Posts via RSS

```python
from collect_rss import fetch_blog_feeds

articles = fetch_blog_feeds(days=7)  # Last 7 days
# Returns: title, abstract, link, source, date
```

### Step 3: LLM Filtering (Two-Step Strategy)

Daily arXiv produces hundreds of papers. Use two-step filtering:

**Step 3a — Batch relevance filtering** (fast model):

Define focus areas based on user's interests:
```python
focus_areas = {
    "AI硬件与边缘计算":  ["AI chip", "NPU", "edge AI", "on-device"],
    "端侧模型与推理优化": ["model compression", "quantization", "TinyML"],
    "多模态AI":         ["multimodal", "vision-language", "VLM"],
    "AI Agent":         ["agent", "tool use", "planning", "reasoning"],
    "基础模型":         ["foundation model", "LLM", "pre-training"],
    "具身智能":         ["embodied AI", "robot learning", "VLA"],
}
```

Use `llm_client.filter_items()` to batch-filter 15 papers at a time. Only papers marked `relevant=true` proceed to Step 3b.

**Step 3b — Summary generation** (pro model):

For papers that pass filtering (~20-50), generate 通俗中文摘要 (plain-language Chinese summaries):

```python
from llm_client import generate_content

prompt = f"""你是一位擅长把复杂技术讲得通俗易懂的科技记者。
请为以下论文生成中文摘要，目标读者是聪明但非技术背景的行业分析师。

写作要求：
- 用大白话写，像给不懂AI的人讲故事
- 专业术语后紧跟括号解释
- 不要写"本文提出""实验表明"这种学术腔
- 每篇3-5句话，150-200字
- 结尾点明"这意味着什么"（对产业的启示）

反面示例（不要）："本文提出了一种基于Transformer的编码器-解码器架构"
正面示例（要）："用了一种主流的AI翻译模型结构，让AI先理解输入再生成输出"

论文：
Title: {paper['title']}
Abstract: {paper['abstract']}

输出JSON：{{"summary_zh": "...", "one_liner": "一句话概括"}}
"""
```

### Step 4: Trend Insights (per category)

For each arXiv category with ≥3 papers, generate a trend insight paragraph:

```python
prompt = f"""你是一位面向行业读者写日报的科技分析师。
以下是今天{category_name}领域的{len(papers)}篇新论文标题。

{titles_list}

请写一段100-150字的趋势洞察，像"每日快报"的开头段落。
要求：
- 不要罗列论文标题
- 读完后读者应该能回答"今天这个领域有啥新鲜事？"
- 概括2-3个主要趋势
- 中文输出，语气轻松专业
"""
```

### Step 5: Blog Post Processing

For blog posts, they are typically already summaries. Use LLM to:
1. Translate title to Chinese
2. Generate one-line summary
3. Categorize by topic

## Report Structure

The briefing follows this format:

```markdown
# AI 前沿论文追踪简报 — YYYY年MM月DD日
共 N 篇 | cs.AI X篇 | cs.CL X篇 | ... | 生成于 HH:MM

## cs.AI — 人工智能（本日 X 篇）

**趋势洞察**：[100-150字段落]

---

### 1. [论文标题中文翻译]
**原标题**：[English Title]
**链接**：https://arxiv.org/abs/[id]
**关注领域**：[AI Agent / 基础模型 / ...]

[3-5句通俗摘要]

---

## AI Lab 博客更新

### [源名称]
- [标题中文] | [一句话摘要] | [链接]
```

## Model Selection

| Task | Model | Reason |
|------|-------|--------|
| Filtering (Step 3a) | gemini-2.0-flash | Fast, cheap, judging relevance is simple |
| Summaries (Step 3b) | gemini-3-pro-preview | Needs strong Chinese writing + popularization |
| Trend insights (Step 4) | gemini-2.0-flash | Short paragraph, flash is sufficient |

## Report Output

```python
from utils import read_template
template = read_template("paper_briefing.md")
```
