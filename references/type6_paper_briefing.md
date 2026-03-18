# Type 6: Academic Briefing — 一键脚本

## 🛑 执行方式

**Agent 只需要运行一条命令：**

```bash
cd "C:/Users/wangtian/.claude/skills/professional-research" && python scripts/run_paper_briefing.py --output "[用户指定的输出目录]"
```

如果用户没指定输出目录，脚本会自动使用 `D:/clauderesult/claudeMMDD/`。

脚本自动完成全部 7 步：
1. fetch_arxiv_rss() → 收集 arXiv 论文
2. fetch_blog_feeds(days=1) → 收集 AI Lab 博客
3. 关键词匹配 → 按研究方向预筛选
4. gemini-2.0-flash 精筛 → 批量过滤低价值论文
5. gemini-3-pro-preview 摘要 → 生成 200-400 字中文摘要
6. 保存 JSON 数据
7. 生成 Word 报告（.docx）

**输出文件：**
- `学术简报_YYYYMMDD.docx` — Word 报告（主要输出）
- `学术简报_YYYYMMDD.json` — 结构化数据

**预计耗时：3-5 分钟**

---

## ❌ Agent 禁止事项

- ❌ 不要写 inline Python 来做筛选/摘要 — 脚本已封装好
- ❌ 不要用 `generate_content()` 直接调 LLM — 脚本内部处理
- ❌ 不要手动组装 JSON — 脚本自动组装
- ❌ 不要单独调 `generate_paper_briefing.py` — 脚本最后自动调用

## ✅ Agent 只需要做

1. 确定输出目录
2. 运行上面那条命令
3. 等待完成（看终端日志）
4. 向用户报告：论文数量 / 研究方向 / 文件路径

---

## Data Sources

| Source | Method | Content |
|--------|--------|---------|
| arXiv RSS | Daily RSS feeds | 6 categories (cs.AI/LG/CL/CV/RO/AR) |
| AI Lab Blogs | RSS feeds | Google AI, OpenAI, DeepMind, HuggingFace, Anthropic, 机器之心 |

## Research Focus Areas (6 directions)

脚本内置 6 个研究方向，每个有关键词列表用于自动分类：
- **计算架构**: AI chip, NPU, PIM, FPGA, accelerator, neuromorphic...
- **大模型优化**: KV Cache, quantization, pruning, MoE, flash attention...
- **多模态AI**: vision-language, VLM, MLLM, image/video generation...
- **AI Agent**: tool use, planning, reasoning, multi-agent, ReAct...
- **具身智能**: robot learning, VLA, manipulation, sim-to-real, humanoid...
- **基础模型**: LLM, pre-training, RLHF, alignment, scaling law...

如需修改关键词，编辑 `scripts/run_paper_briefing.py` 的 `FOCUS_AREAS` 字典。

## Model Selection (已固化在脚本中)

| Task | Model | Reason |
|------|-------|--------|
| 关键词匹配 | Python code | 无 LLM 成本 |
| LLM 精筛 | gemini-2.0-flash | 快、便宜、503 少 |
| 摘要生成 | gemini-3-pro-preview | 翻译质量高 |

## Style Rules (摘要风格，已固化在脚本 prompt 中)

- 标题用**原英文标题**
- 摘要是**忠实翻译**（200-400字），保留技术术语
- 每篇包含：作者、链接、匹配关键词
- 按研究方向分组，每组不设上限
- ❌ 不要写开头寒暄 ❌ 不要写"趋势洞察"
