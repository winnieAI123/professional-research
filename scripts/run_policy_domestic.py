"""
Domestic Policy Research — Runner Script
==========================================
Type 5 (domestic sub-type) of Professional Research Skill.

End-to-end pipeline:
  1. Multi-layer search (Central Ministries → Financial Regulators → Local Governments)
  2. LLM filtering (relevance + policy type)
  3. Full-text extraction (Tavily Extract)
  4. LLM structured analysis (per-document)
  5. LLM report generation (6-section format)
  6. Word report output

Usage:
  python run_policy_domestic.py
  python run_policy_domestic.py --domain "AI与机器人" --period "2026年3月"
  python run_policy_domestic.py --domain "金融科技与消费信贷" --focus "数字人民币信贷政策"
  python run_policy_domestic.py --output ~/clauderesult/claude0326/policy
  python run_policy_domestic.py --skip-search   (复用已有数据，重新生成报告)
  python run_policy_domestic.py --force-search  (强制重新搜索，忽略缓存)

Auto-cache: If analyses.json exists for the same domain and is <72h old,
            Steps 1-4 are automatically skipped. Use --force-search to override.
"""
import argparse
import os
import sys
import json
import time
import re
from datetime import datetime

# Ensure scripts/ is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils import read_config, get_output_dir
from collect_search import search_site, tavily_extract, multi_query_search
from llm_client import generate_content

CACHE_EXPIRY_HOURS = 72  # Auto-skip search if data is less than 72h old


def _load_cache_metadata(output_dir: str) -> dict:
    """Load metadata.json from output directory."""
    path = os.path.join(output_dir, "metadata.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_cache_metadata(output_dir: str, domain: str, focus: str, analyses_count: int):
    """Save metadata.json to track when data was collected."""
    meta = {
        "domain": domain,
        "focus": focus,
        "collected_at": datetime.now().isoformat(),
        "analyses_count": analyses_count,
        "cache_expiry_hours": CACHE_EXPIRY_HOURS,
    }
    path = os.path.join(output_dir, "metadata.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print(f"  💾 缓存元数据已保存: {path}")


def _is_cache_valid(output_dir: str, domain: str) -> bool:
    """Check if cached data is valid (same domain, not expired)."""
    meta = _load_cache_metadata(output_dir)
    if not meta:
        return False
    # Domain must match
    if meta.get("domain") != domain:
        print(f"  🔄 缓存领域不匹配: {meta.get('domain')} ≠ {domain}")
        return False
    # Check expiry
    collected = datetime.fromisoformat(meta["collected_at"])
    age_hours = (datetime.now() - collected).total_seconds() / 3600
    if age_hours > CACHE_EXPIRY_HOURS:
        print(f"  ⏰ 缓存已过期: {age_hours:.1f}h > {CACHE_EXPIRY_HOURS}h")
        return False
    # Check analyses exist
    analyses_path = os.path.join(output_dir, "analyses.json")
    if not os.path.exists(analyses_path):
        return False
    print(f"  ✅ 缓存有效: {meta.get('analyses_count', '?')}条分析, 采集于 {age_hours:.1f}h 前")
    return True


def step1_search(domestic: dict, domain: str) -> list:
    """Multi-layer search across ministries, regulators, and local governments."""
    print(f"\n{'='*60}")
    print(f"  STEP 1: 多层搜索（全量）")
    print(f"{'='*60}")

    keywords = domestic["keywords"].get(domain, ["人工智能", "AI"])[:3]
    policy_words = domestic["policy_type_words"]
    all_results = []

    # Layer 1: All Central Ministries
    print("\n--- Layer 1: 中央部委 ---")
    for key, info in domestic["ministry_level"].items():
        print(f"  [{info['name']}] site:{info['site']}")
        results = search_site(site=info["site"], keywords=keywords,
                             policy_type_words=policy_words, max_results=5)
        print(f"    → {len(results)} results")
        all_results.extend(results)
        time.sleep(1)

    # Layer 2: All Financial Regulators
    print("\n--- Layer 2: 金融监管 ---")
    fin_kw = domestic["keywords"].get("金融科技与消费信贷", ["金融科技", "消费信贷"])[:2]
    for key, info in domestic["financial_regulators"].items():
        print(f"  [{info['name']}] site:{info['site']}")
        results = search_site(site=info["site"], keywords=fin_kw,
                             policy_type_words=policy_words, max_results=5)
        print(f"    → {len(results)} results")
        all_results.extend(results)
        time.sleep(1)

    # Layer 3: All Local Governments
    print("\n--- Layer 3: 地方政府 ---")
    for city_key, city_info in domestic["local_level"].items():
        print(f"  [{city_info['name']}] site:{city_info['site']}")
        results = search_site(site=city_info["site"], keywords=keywords[:2],
                             policy_type_words=policy_words, max_results=5)
        print(f"    → {len(results)} results")
        all_results.extend(results)
        time.sleep(1)

    # Supplementary: Media interpretations
    print("\n--- 辅助: 媒体解读 ---")
    media_domains = ["caixin.com", "yicai.com", "36kr.com", "huxiu.com",
                    "xinhuanet.com", "21jingji.com"]
    media_results = multi_query_search(
        queries=[
            f"{keywords[0]} 政策 解读 2026",
            f"{keywords[1] if len(keywords) > 1 else keywords[0]} 政策 补贴 2026",
        ],
        max_results_per_query=5,
        include_domains=media_domains,
    )
    all_results.extend(media_results)

    # Dedup
    seen = set()
    unique = []
    for r in all_results:
        url = r.get("url", "")
        if url and url not in seen:
            seen.add(url)
            unique.append(r)

    print(f"\n  合计: {len(all_results)} → 去重后 {len(unique)} 条")
    return unique


def step2_filter(results: list, domain: str) -> tuple:
    """LLM-based filtering for policy relevance."""
    print(f"\n{'='*60}")
    print(f"  STEP 2: LLM 过滤")
    print(f"{'='*60}")

    items_text = "\n".join([
        f"[{i+1}] {r['title']} | {r['url'][:100]} | {r.get('content', '')[:120]}"
        for i, r in enumerate(results[:40])
    ])

    prompt = f"""你是政策分析助手。从以下搜索结果中筛选出与"{domain}"相关的**真正的政策文件或重要政策解读**。

筛选标准:
✅ 政府部委/监管机构发布的正式政策文件(通知/意见/办法/指导意见/实施细则/行动方案)
✅ 权威媒体/智库对重大政策的深度解读
✅ 地方政府的专项支持政策、试点通知、资金申报指南
❌ 排除: 目录页、列表页、过旧政策(2024年前)、企业案例、会议纪要

搜索结果:
{items_text}

返回JSON数组:
[{{"index": 编号, "title": "标题", "type": "policy/interpretation/local", "relevance": "high/medium", "reason": "简要说明"}}]

只返回JSON，不要其他内容。"""

    raw = generate_content(prompt, use_fast_model=True, temperature=0.1)
    json_match = re.search(r'\[.*\]', raw, re.DOTALL)
    if json_match:
        filtered = json.loads(json_match.group())
        print(f"  筛选: {len(filtered)} / {min(len(results), 40)}")
        for item in filtered:
            idx = item.get("index", 0) - 1
            if 0 <= idx < len(results):
                print(f"    [{item.get('type','?')}] {results[idx]['title'][:55]}")
        return filtered, results
    else:
        print(f"  [!] LLM返回无法解析，使用前8条")
        return [{"index": i+1, "type": "unknown", "relevance": "medium"}
                for i in range(min(8, len(results)))], results


def step3_extract(filtered: list, all_results: list) -> list:
    """Extract full text from filtered URLs via Tavily Extract.
    Falls back to search snippets if extract fails."""
    print(f"\n{'='*60}")
    print(f"  STEP 3: 全文提取 (Tavily Extract)")
    print(f"{'='*60}")

    # Collect URLs and their original search data
    url_to_search = {}  # url -> search result dict (for fallback)
    urls = []
    for item in filtered:
        idx = item.get("index", 0) - 1
        if 0 <= idx < len(all_results):
            r = all_results[idx]
            url = r["url"]
            if not url.endswith(".pdf"):
                urls.append(url)
                url_to_search[url] = r

    print(f"  提取 {len(urls)} 条 URL...")
    extracted = tavily_extract(urls[:10])
    print(f"  成功提取: {len(extracted)} 条")

    for e in extracted:
        content = e.get("raw_content", "")
        print(f"    [{len(content)} chars] {e.get('url', '?')[:70]}")

    # FALLBACK: if Tavily Extract returned fewer results than expected,
    # use search snippets for the missing URLs
    extracted_urls = {e.get("url", "") for e in extracted}
    fallback_count = 0
    for url in urls[:10]:
        if url not in extracted_urls and url in url_to_search:
            r = url_to_search[url]
            snippet = r.get("content", "")
            if snippet and len(snippet) > 50:
                extracted.append({
                    "url": url,
                    "raw_content": f"标题: {r.get('title', '')}\n\n{snippet}",
                    "_source": "search_snippet",
                })
                fallback_count += 1

    if fallback_count > 0:
        print(f"  ⚠️ Fallback: 用搜索摘要补充了 {fallback_count} 条（全文提取失败的URL）")

    if not extracted:
        print(f"  ❌ 全文提取和搜索摘要均无数据!")

    return extracted


def step4_analyze(extracted: list, output_dir: str) -> list:
    """LLM structured analysis per document."""
    print(f"\n{'='*60}")
    print(f"  STEP 4: LLM 结构化分析")
    print(f"{'='*60}")

    analyses = []
    for i, doc_item in enumerate(extracted):
        content = doc_item.get("raw_content", "")[:8000]
        url = doc_item.get("url", "")

        if len(content) < 200:
            print(f"  [{i+1}] 内容过短，跳过: {url[:60]}")
            continue

        prompt = f"""你是资深政策分析师。请对以下政策文件/解读进行结构化分析。

来源URL: {url}

文件内容:
{content}

请返回JSON:
{{
  "title": "政策名称",
  "issuer": "发布机构",
  "date": "发布日期(如有)",
  "type": "policy/interpretation/local",
  "domain": "所属领域(AI/云计算/金融科技/数据安全)",
  "key_points": ["要点1", "要点2", "要点3"],
  "impact": "影响评估(2-3句话)",
  "relevance_to_business": "对科技企业的启示(1-2句话)",
  "url": "{url}"
}}

只返回JSON，不要其他内容。"""

        print(f"  [{i+1}/{len(extracted)}] 分析中...")
        try:
            raw = generate_content(prompt, use_fast_model=False, temperature=0.1)
            json_match = re.search(r'\{.*\}', raw, re.DOTALL)
            if json_match:
                analysis = json.loads(json_match.group())
                analyses.append(analysis)
                print(f"    ✓ {analysis.get('title', '?')[:50]}")
            else:
                print(f"    ✗ 无法解析JSON")
        except Exception as e:
            print(f"    ✗ 错误: {e}")
        time.sleep(2)

    print(f"\n  完成分析: {len(analyses)} 条")

    with open(os.path.join(output_dir, "analyses.json"), "w", encoding="utf-8") as f:
        json.dump(analyses, f, ensure_ascii=False, indent=2)

    return analyses


def step5_generate_report_content(
    analyses: list,
    output_dir: str,
    report_period: str,
    domain: str,
    focus_theme: str,
) -> str:
    """LLM generates 6-section report content."""
    print(f"\n{'='*60}")
    print(f"  STEP 5: 生成报告内容")
    print(f"{'='*60}")

    analyses_text = json.dumps(analyses, ensure_ascii=False, indent=2)

    prompt = f"""你是资深政策分析师。请严格根据以下分析数据，生成一份政策月报。

⚠️ 铁律（违反即为失败）:
1. 所有政策名称、机构、日期必须100%来自下方数据，严禁编造
2. 数据中没有的领域写"本期暂无相关政策数据"
3. 每条政策标注来源URL

报告周期: {report_period} | 领域: {domain} | 焦点: {focus_theme}

分析数据（共{len(analyses)}条，唯一数据来源）:
{analyses_text}

⚠️ 输出格式要求（极其重要！）:
你必须输出完整的6个板块，每个板块都必须用 [SECTION_XXX] 和 [/SECTION_XXX] 标签包裹。
缺少任何一个标签对都是失败。不要使用**加粗语法。

请严格按以下格式输出:

[SECTION_COVER]
（3-5句话概括本月政策动向，仅基于上方数据）
[/SECTION_COVER]

[SECTION_1_MACRO]
（国家战略层面的重大政策总结，仅引用数据中的政策）
[/SECTION_1_MACRO]

[SECTION_2_DOMAIN]
（按领域分类列出每条政策，格式如下：
子领域名称:

- 政策名称: xxx
- 发布机构: xxx
- 日期: xxx
- 核心要点: xxx
- 影响评估: xxx
- 来源: URL
）
[/SECTION_2_DOMAIN]

[SECTION_3_LOCAL]
（地方政策汇总，必须使用markdown表格格式：
| 区域 | 核心政策 | 资金规模/关键数据 | 来源 |
|------|---------|----------------|------|
| xx | xxx | xxx | URL |
如果没有地方政策数据，写"本期暂无地方政策数据"）
[/SECTION_3_LOCAL]

[SECTION_4_DATA]
（关键数据汇总，必须使用markdown表格格式：
| 指标 | 数值 | 出处政策 | 解读 |
|------|------|---------|------|
| xx | xx | xx | xx |
然后补充1-2段综合分析）
[/SECTION_4_DATA]

[SECTION_5_DEEP]
（围绕"{focus_theme}"做200-300字深度分析，只分析有数据支撑的内容）
[/SECTION_5_DEEP]

[SECTION_6_STRATEGY]
（业务影响与策略建议：
- 机遇识别(2-3条，对应具体政策)
- 风险提示(1-2条)
- 行动建议(2-3条)）
[/SECTION_6_STRATEGY]

再次强调：必须输出完整的6对标签！"""

    print("  生成中...")
    report_text = generate_content(prompt, use_fast_model=False, temperature=0.3,
                                  max_output_tokens=8000)
    print(f"  生成完成: {len(report_text)} 字")

    # Validate all sections are present
    for marker in ["SECTION_COVER", "SECTION_1_MACRO", "SECTION_2_DOMAIN",
                    "SECTION_3_LOCAL", "SECTION_4_DATA", "SECTION_5_DEEP",
                    "SECTION_6_STRATEGY"]:
        if f"[{marker}]" not in report_text or f"[/{marker}]" not in report_text:
            print(f"  ⚠️ 缺少标签: [{marker}] — 将进行修补")

    with open(os.path.join(output_dir, "report_content.txt"), "w", encoding="utf-8") as f:
        f.write(report_text)

    return report_text


def main():
    parser = argparse.ArgumentParser(description="国内政策研究月报 — Type 5")
    parser.add_argument(
        "--domain", "-d",
        default="AI与机器人",
        help="研究领域 (default: AI与机器人)",
    )
    parser.add_argument(
        "--period", "-p",
        default=None,
        help="报告周期, e.g. '2026年3月' (default: 当月)",
    )
    parser.add_argument(
        "--focus", "-f",
        default=None,
        help="本期焦点主题 (default: 基于领域自动生成)",
    )
    parser.add_argument(
        "--output", "-o",
        default=None,
        help="输出目录 (default: 自动选择)",
    )
    parser.add_argument(
        "--skip-search",
        action="store_true",
        help="跳过搜索，使用已有数据重新生成报告",
    )
    parser.add_argument(
        "--force-search",
        action="store_true",
        help="强制重新搜索，忽略缓存",
    )
    args = parser.parse_args()

    # Defaults
    now = datetime.now()
    report_period = args.period or f"{now.year}年{now.month}月"
    domain = args.domain
    focus_theme = args.focus or f"{domain}政策追踪与机会分析"

    if args.output:
        output_dir = args.output
    else:
        base_dir = get_output_dir()
        output_dir = os.path.join(base_dir, "policy_domestic")
    os.makedirs(output_dir, exist_ok=True)

    config = read_config("policy_sources.json")
    domestic = config["domestic"]

    print(f"{'='*60}")
    print(f"  国内政策研究月报 — Type 5")
    print(f"{'='*60}")
    print(f"  📋 领域: {domain}")
    print(f"  📅 周期: {report_period}")
    print(f"  🎯 焦点: {focus_theme}")
    print(f"  📁 输出: {output_dir}")
    print()

    if args.skip_search or (not args.force_search and _is_cache_valid(output_dir, domain)):
        # Load saved analyses only (Steps 1-4 cached)
        # Steps 5-6 (report generation + Word) always re-run
        if not args.skip_search:
            print("[自动缓存] 数据未过期，跳过搜索，直接重新生成报告...")
        else:
            print("[手动跳过] 使用已有分析数据，重新生成报告...")
        with open(os.path.join(output_dir, "analyses.json"), "r", encoding="utf-8") as f:
            analyses = json.load(f)
        if not analyses:
            print("  ❌ analyses.json 为空，无法生成报告")
            sys.exit(1)
        report_text = step5_generate_report_content(
            analyses, output_dir, report_period, domain, focus_theme
        )
    else:
        # Full pipeline
        results = step1_search(domestic, domain)

        # Save raw results
        with open(os.path.join(output_dir, "raw_results.json"), "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        filtered, all_results = step2_filter(results, domain)

        with open(os.path.join(output_dir, "filtered_results.json"), "w", encoding="utf-8") as f:
            json.dump(filtered, f, ensure_ascii=False, indent=2)

        extracted = step3_extract(filtered, all_results)

        if not extracted:
            print(f"\n  ❌ 中断: 没有可分析的内容（全文提取和搜索摘要均失败）")
            print(f"  请检查网络连接后重试。")
            sys.exit(1)

        analyses = step4_analyze(extracted, output_dir)

        if not analyses:
            print(f"\n  ❌ 中断: LLM分析全部失败，没有可用数据生成报告")
            print(f"  请检查 Gemini API 状态后重试。")
            sys.exit(1)

        report_text = step5_generate_report_content(
            analyses, output_dir, report_period, domain, focus_theme
        )

        # Save cache metadata after successful Steps 1-4
        _save_cache_metadata(output_dir, domain, focus_theme, len(analyses))

    # Step 6: Word report
    from report_policy import generate_policy_report
    filepath = generate_policy_report(
        report_text=report_text,
        analyses=analyses,
        output_dir=output_dir,
        report_period=report_period,
        domain=domain,
        focus_theme=focus_theme,
    )

    print(f"\n{'='*60}")
    print(f"  ✅ 完成!")
    print(f"{'='*60}")
    print(f"  📊 报告: {filepath}")
    print(f"  📁 分析: {os.path.join(output_dir, 'analyses.json')}")
    print(f"  📁 内容: {os.path.join(output_dir, 'report_content.txt')}")

    return filepath


if __name__ == "__main__":
    main()
