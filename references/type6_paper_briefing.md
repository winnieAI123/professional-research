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

## Report Output — 🛑 MANDATORY

**报告必须输出 Word 格式（.docx），不能只输出 Markdown。**

### Step 6: Save JSON Data

Agent 必须将筛选+摘要后的论文数据保存为 JSON，格式如下：

```python
import json

data = {
    "date": "2026-03-18",          # 当天日期 YYYY-MM-DD
    "total_papers": len(all_filtered_papers),  # 匹配论文总数
    "total_directions": len(used_categories),   # 有论文的研究方向数
    "total_arxiv": len(all_raw_papers),         # arXiv 原始论文总数
    "categories": [
        {
            "name": "计算架构",     # 研究方向名（不带"类"字）
            "papers": [
                {
                    "title": "English Paper Title",        # 原英文标题
                    "authors": "Author1, Author2",          # 作者
                    "link": "https://arxiv.org/abs/xxxx",   # 链接
                    "keywords": ["Neuromorphic", "PIM"],    # 匹配到的关键词
                    "summary": "中文摘要（200-400字）...",   # LLM 生成的摘要
                    "hardware_specs": ["energy efficiency"]  # 硬件规格（可为空 []）
                }
            ]
        }
    ],
    "blog_updates": [
        {
            "source": "Google AI",
            "articles": [
                {"title_zh": "中文标题", "summary": "一句话", "link": "https://..."}
            ]
        }
    ]
}

# 保存 JSON
json_path = os.path.join(output_dir, f"学术简报_{date_str.replace('-','')}.json")
with open(json_path, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
```

### Step 7: Generate Word Report

```bash
cd "C:/Users/wangtian/.claude/skills/professional-research" && python scripts/generate_paper_briefing.py --input "[JSON文件路径]" --output "[输出目录]/学术简报_YYYYMMDD.docx"
```

脚本自动生成专业格式的 Word 文档：
- 标题居中、深蓝色
- 分类标题带篇数
- 每篇论文：编号标题 + 作者 + 链接 + 蓝色匹配关键词 + "摘要："标签 + 蓝色硬件规格
- 真正的 Word 分隔线（不是文本 ────）
- 博客更新板块

### Step 8 (Optional): Save Markdown Copy

如果用户需要 Markdown 版本，也生成一份 .md 文件。但 **Word 是主要输出**。

## 🛑 Quick Reference — Agent 执行摘要

```
收到 Type 6 请求 →
  1. fetch_arxiv_rss()          → ~1800 篇
  2. fetch_blog_feeds(days=1)   → ~10-30 篇
  3. 关键词匹配 + LLM 筛选     → ~20-50 篇
  4. LLM 生成摘要（纯文本）     → 每篇 200-400 字
  5. 保存 JSON 到输出目录
  6. 运行 generate_paper_briefing.py → .docx
  7. 向用户报告：论文数量 / 研究方向 / 文件路径
```

## Style Rules (摘要风格)

- 标题用**原英文标题**，不要翻译成花哨中文标题
- 摘要是**忠实翻译**（200-400字），保留技术术语和实验数字
- 每篇必须有：作者、链接、匹配关键词
- 按研究方向分组，不按 arXiv 分类分组
- 每组论文数量不设上限，有多少收录多少
- ❌ 不要写开头寒暄（"各位同仁早上好"）
- ❌ 不要写空洞的"趋势洞察"段落

## Model Selection

| Task | Model | Reason |
|------|-------|--------|
| Keyword matching (Step 3a) | Python code | Fast, no LLM cost |
| LLM filtering (Step 3b) | gemini-2.0-flash | Fast, cheap, judging relevance is simple |
| Summaries (Step 4) | gemini-3-pro-preview | Needs accurate technical translation |

