"""
Report Generation Script — Section-by-Section with Anti-Fabrication Rules
Usage:
    python run_report_gen.py --template industry_research_commercial.md --data collected_data.json --output report.md
    python run_report_gen.py --template kol_weekly_digest.md --data kol_data.json --output report.md

This script MUST be called for final report generation.
It guarantees: anti-fabrication prompts + section-by-section generation + source citation rules.
"""

import sys, os, json, argparse
from datetime import datetime

os.environ["PYTHONIOENCODING"] = "utf-8"

SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SKILL_DIR)

from utils import read_template
from llm_client import generate_content
from generate_report import save_report

# ============================================================
# Anti-Fabrication Rules (hardcoded, Agent cannot bypass)
# ============================================================
SOURCE_CITATION_RULES = """
⚠️ 信息溯源红线（最高优先级，违反即为不合格报告）：
1. 每个市场规模、增长率、融资金额等数据必须标注来源机构或URL（如 "来源: Fortune Business Insights"）
2. 每个论文实验结果必须标注来源论文和具体 Table/Figure（如 "来源: MetaWorld-X, Table 2"）
3. 每个推文观点必须标注 @用户名和推文链接
4. 搜索数据中找不到的信息，必须写"未找到相关公开数据（截至搜索日期）"，绝不可推测编造
5. 禁止编造任何融资金额、市场份额、增长率、实验结果、提升幅度
6. 禁止根据论文摘要推断具体实验数值——必须读全文后引用
7. 如果论文全文中找不到具体数字，写"原文未披露具体数据"
"""

NO_PLACEHOLDER_RULE = """
⚠️ 无数据处理规则：
- 如果某个章节完全没有对应数据，用一句话说明"本次搜索中未找到相关数据"，不要展开占位符模板
- 不要写 "[数据来源有限]" 或类似占位符
"""


def generate_report(
    template_names: list,
    data_sources: dict,
    topic: str,
    output_path: str = None,
    max_tokens_per_section: int = 12000,
) -> str:
    """
    Section-by-section report generation with anti-fabrication rules.
    
    Args:
        template_names: List of template filenames (e.g., ["industry_research_commercial.md", "industry_research_technical.md"])
        data_sources: Dict of data, e.g. {"web": [...], "arxiv": [...], "twitter": [...]}
        topic: Research topic
        output_path: Output file path (optional, if None returns MD content)
        max_tokens_per_section: Max output tokens per Gemini call
    
    Returns:
        Full MD report content
    """
    date_str = datetime.now().strftime('%Y年%m月%d日')
    report_sections = []
    
    for template_name in template_names:
        print(f"\n  [Generating] {template_name}...")
        template = read_template(template_name)
        
        # Select relevant data for this template
        data_block = _prepare_data_for_template(template_name, data_sources)
        
        prompt = f"""你是一位顶级行业分析师。请根据模板和数据撰写"{topic}"的研究报告。

## 模板（严格遵循结构）
{template}

## 可用数据
{data_block}

{SOURCE_CITATION_RULES}

{NO_PLACEHOLDER_RULE}

## 其他要求
- 研究日期：{date_str}
- 纯Markdown输出，不要包含```markdown```代码块标记
- 如果数据不足以填充模板的某个章节，如实说明，不要编造

直接输出完整报告："""
        
        try:
            section = generate_content(
                prompt=prompt,
                max_output_tokens=max_tokens_per_section,
            )
            report_sections.append(section.strip())
            print(f"  [Done] {template_name}: {len(section)} chars")
        except Exception as e:
            print(f"  [Error] {template_name}: {e}")
            report_sections.append(f"# {topic}\n\n报告生成失败: {e}")
    
    # Merge sections
    full_report = "\n\n---\n\n".join(report_sections)
    
    # Save
    if output_path:
        result = save_report(
            md_content=full_report,
            topic=output_path.replace(".md", "").replace("_report", ""),
        )
        print(f"\n  [Saved] MD: {result['md_path']}")
        print(f"  [Saved] Word: {result['docx_path']}")
        return full_report
    
    return full_report


def _prepare_data_for_template(template_name: str, data_sources: dict) -> str:
    """Select and format data relevant to a specific template."""
    parts = []
    
    # Web data — always include if available
    if data_sources.get("web"):
        web_items = data_sources["web"]
        web_data = []
        for item in web_items[:25]:
            entry = {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "snippet": item.get("content", item.get("snippet", ""))[:500],
            }
            if item.get("full_content"):
                entry["full_text_excerpt"] = item["full_content"][:3000]
            web_data.append(entry)
        web_json = json.dumps(web_data, ensure_ascii=False, indent=2)[:15000]
        parts.append(f"### Web搜索数据（共{len(web_items)}条）\n{web_json}")
    
    # arXiv data — only for technical templates
    if "technical" in template_name or "paper" in template_name or "trend" in template_name:
        if data_sources.get("arxiv"):
            arxiv_items = data_sources["arxiv"]
            arxiv_data = [
                {
                    "title": p.get("title", ""),
                    "abstract": p.get("abstract", "")[:600],
                    "full_text": p.get("full_text", "")[:5000],
                    "authors": p.get("authors", [])[:5],
                    "link": p.get("link", ""),
                    "date": p.get("published", ""),
                }
                for p in arxiv_items
            ]
            arxiv_json = json.dumps(arxiv_data, ensure_ascii=False, indent=2)[:25000]
            parts.append(f"### arXiv论文数据（共{len(arxiv_items)}篇，含PDF全文）\n{arxiv_json}")
    
    # Twitter data
    if data_sources.get("twitter"):
        tweets = data_sources["twitter"]
        tweet_data = [
            {
                "kol": t.get("username", t.get("author_username", "")),
                "text": t.get("text", t.get("content", ""))[:400],
                "likes": t.get("likes", 0),
                "retweets": t.get("retweets", 0),
                "url": t.get("url", ""),
                "date": t.get("created_at", t.get("date", "")),
            }
            for t in tweets[:30]
        ]
        tweet_json = json.dumps(tweet_data, ensure_ascii=False, indent=2)[:10000]
        parts.append(f"### Twitter推文数据（共{len(tweets)}条）\n{tweet_json}")
    
    # Substack data
    if data_sources.get("substack"):
        articles = data_sources["substack"]
        sub_data = [
            {
                "title": a.get("title", ""),
                "url": a.get("url", ""),
                "content_excerpt": a.get("full_content", a.get("content", ""))[:3000],
            }
            for a in articles[:8]
        ]
        sub_json = json.dumps(sub_data, ensure_ascii=False, indent=2)[:10000]
        parts.append(f"### Substack文章数据（共{len(articles)}篇）\n{sub_json}")
    
    if not parts:
        return "（无可用数据）"
    
    return "\n\n".join(parts)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Report Generation with Anti-Fabrication Rules")
    parser.add_argument("--templates", nargs="+", required=True, 
                        help="Template filenames (e.g., industry_research_commercial.md industry_research_technical.md)")
    parser.add_argument("--data", required=True, help="Path to collected data JSON")
    parser.add_argument("--topic", required=True, help="Research topic")
    parser.add_argument("--output", default=None, help="Output report path (base name)")
    parser.add_argument("--max-tokens", type=int, default=12000, help="Max tokens per section")
    
    args = parser.parse_args()
    
    # Load data
    with open(args.data, "r", encoding="utf-8") as f:
        data_sources = json.load(f)
    
    report = generate_report(
        template_names=args.templates,
        data_sources=data_sources,
        topic=args.topic,
        output_path=args.output,
        max_tokens_per_section=args.max_tokens,
    )
    
    print(f"\n{'=' * 60}")
    print(f"Report generated: {len(report)} chars")
    print(f"{'=' * 60}")
