# Type 6: Academic Briefing Pipeline

Daily/periodic tracking of AI academic papers and lab blog posts, producing professional research briefings.

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

### Step 3: LLM Filtering — 按研究方向匹配筛选

Daily arXiv produces hundreds of papers. Use focus-area keyword matching + LLM filtering:

**Step 3a — 定义研究方向关键词**:

根据用户兴趣定义研究方向。以下是默认配置，Agent 可根据用户需求调整:
```python
focus_areas = {
    "计算架构": ["AI chip", "NPU", "edge AI", "on-device", "Processing-in-Memory", "PIM",
                 "FPGA", "accelerator", "ASIC", "neuromorphic", "dataflow", "hardware"],
    "大模型优化": ["KV Cache", "quantization", "pruning", "distillation", "inference optimization",
                   "MoE", "speculative decoding", "model compression", "TinyML", "GGUF",
                   "flash attention", "sparse attention", "long context"],
    "多模态AI":  ["multimodal", "vision-language", "VLM", "MLLM", "image generation",
                  "video understanding", "audio-language"],
    "AI Agent":  ["agent", "tool use", "planning", "reasoning", "code generation",
                  "function calling", "ReAct", "chain-of-thought"],
    "具身智能":  ["embodied AI", "robot learning", "VLA", "manipulation",
                  "locomotion", "sim-to-real", "world model"],
    "基础模型":  ["foundation model", "LLM", "pre-training", "RLHF", "alignment",
                  "scaling law", "architecture", "transformer"],
}
```

**Step 3b — 两步筛选**:

1. **关键词预筛选**: 对每篇论文的 title + abstract 做关键词匹配，记录匹配到的研究方向和关键词
2. **LLM 精筛** (Flash model): 对关键词命中的论文批量确认相关性

```python
from llm_client import filter_items

# Batch filter 15 papers at a time
# Only papers marked relevant=true proceed to Step 4
```

**筛选后的论文按研究方向分组，而不是按 arXiv 原始分类分组。**
一篇论文可能属于多个研究方向，取最佳匹配的那个。
每个研究方向的论文数量不设上限，有多少收录多少。

### Step 4: 摘要生成 — 忠实翻译，保留技术细节

**🛑 摘要风格规则（必须严格遵守）**:

```python
from llm_client import generate_content

prompt = f"""你是一位资深AI研究员，负责为技术团队撰写论文追踪简报。
请为以下论文生成中文摘要。

写作要求：
- 忠实翻译 abstract 的核心内容，不要重新编写或"讲故事"
- 保留所有技术术语，在首次出现时括号附上英文原文
- 保留关键数字和实验结果（如"准确率提升4.5%"、"推理速度提高3倍"）
- 长度: 200-400字，不做过度压缩
- 语气: 专业简洁，类似研究简报而非科普文章
- 必须包含: 问题是什么 → 方法是什么 → 效果如何

❌ 禁止:
- "各位分析师同仁早上好" 之类的寒暄
- "AI闯祸了谁该背锅？" 之类的公众号标题
- "像给不懂AI的人讲故事" 的风格
- 删除作者信息
- 删除关键数字和实验结果

✅ 正面示例:
"提出 ARKV 框架，通过基于注意力统计（熵、方差、峰度）的动态精度分配，
为 KV Cache 中的 token 分配三种状态（原始/量化/驱逐）。在 LLaMA3 和
Qwen3 上测试，长上下文基准保留约97%基线精度，KV 内存使用减少4倍。"

❌ 反面示例:
"这篇论文提出了一种聪明的方法来帮助AI记住更多东西。想象一下你的大脑
在考试时能自动忘掉不重要的知识——这个技术就是这个原理。"

论文：
Title: {{paper['title']}}
Authors: {{paper['authors']}}
Abstract: {{paper['abstract']}}
匹配关键词: {{paper['matched_keywords']}}

请直接输出以下格式的纯文本（不要输出 JSON，不要加任何包裹）：

[中文摘要正文，200-400字，忠实翻译 abstract]

注意：
- 只输出摘要正文，不要输出标题、作者、链接（这些由系统自动填充）
- 不要用 JSON 格式，不要用 ```代码块``` 包裹
- 直接输出纯文本段落
"""
```

**🛑 关键：Agent 处理 LLM 输出的方式**

LLM 只返回摘要正文（纯文本），Agent 负责组装完整的论文条目：

```
### [序号]. [原英文标题]
**作者：** [从 paper dict 取]
**链接：** [从 paper dict 取]
**匹配关键词：** [从 paper dict 取]

[LLM 返回的纯文本摘要]

涉及硬件规格：[如有，从匹配关键词中提取]
```

Agent 不要直接粘贴 LLM 的原始输出。必须按上述模板格式组装每篇论文。

### Step 5: Blog Post Processing

For blog posts, keep it simple:
1. Translate title to Chinese
2. Generate one-line summary (保留技术细节)
3. Categorize by topic

## Report Structure

简报严格按以下格式输出：

```markdown
# 学术论文追踪简报 — YYYY年MM月DD日

共 N 篇匹配论文 | M 个研究方向
数据来源：arXiv RSS 当日新论文（共 X 篇），经关键词预筛选 + LLM 精选

────────────────────────────────────────────────────────────

## [研究方向名]类（N 篇）

### 1. [原英文标题]
**作者：** [Authors]
**链接：** https://arxiv.org/abs/[id]
**匹配关键词：** [keyword1, keyword2]

[200-400字中文摘要，忠实翻译，保留技术细节]

涉及硬件规格：[如有]

────────────────────────────────────────────────────────────

### 2. [原英文标题]
...

────────────────────────────────────────────────────────────

## AI Lab 博客更新

### [源名称]
- [中文标题] | [一句话摘要] | [链接]
```

**🛑 格式规则**:
- 标题用**原英文标题**，不要翻译成中文花哨标题
- 每篇论文必须包含: 作者、链接、匹配关键词
- 按研究方向分组，不按 arXiv 分类分组
- 每组论文数量不设上限，有多少收录多少
- 不要写开头寒暄语
- 不要写空洞的"趋势洞察"段落
- 分隔线用 ──── (40个)

## Model Selection

| Task | Model | Reason |
|------|-------|--------|
| Keyword matching (Step 3a) | Python code | Fast, no LLM cost |
| LLM filtering (Step 3b) | gemini-2.0-flash | Fast, cheap, judging relevance is simple |
| Summaries (Step 4) | gemini-3-pro-preview | Needs accurate technical translation |

## Report Output

```python
from utils import read_template
template = read_template("paper_briefing.md")
```
