"""
LLM Leaderboard Analysis — Runner Script
==========================================
Type 9 of Professional Research Skill.

End-to-end pipeline:
  1. Scrape 3 sources (LMArena, ArtificialAnalysis, SuperCLUE)
  2. Multi-source analysis (cross-comparison, vendor panorama, tech barriers, opportunity screening)
  3. Generate charts (matplotlib)
  4. Generate Word report with Gemini narrative insights

Usage:
  python run_leaderboard.py
  python run_leaderboard.py --date 20260312
  python run_leaderboard.py --skip-scrape --date 20260312
  python run_leaderboard.py --output ~/clauderesult/claude0326/leaderboard
"""
import argparse
import os
import sys
from datetime import datetime

# Ensure scripts/ is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils import get_output_dir


def main():
    parser = argparse.ArgumentParser(description="大模型榜单分析 — 多源对比报告")
    parser.add_argument(
        "--date", "-d",
        default=None,
        help="日期 (YYYYMMDD), 默认今天",
    )
    parser.add_argument(
        "--output", "-o",
        default=None,
        help="输出目录, 默认自动选择",
    )
    parser.add_argument(
        "--skip-scrape",
        action="store_true",
        help="跳过采集，使用已有 CSV 数据",
    )
    parser.add_argument(
        "--source", "-s",
        default="all",
        choices=["all", "lm", "aa", "sc"],
        help="数据源: all=全部, lm=LMArena, aa=ArtificialAnalysis, sc=SuperCLUE",
    )
    args = parser.parse_args()

    date_str = args.date or datetime.now().strftime("%Y%m%d")

    # Output directory
    if args.output:
        output_dir = args.output
    else:
        base_dir = get_output_dir()
        output_dir = os.path.join(base_dir, "leaderboard")
    os.makedirs(output_dir, exist_ok=True)

    data_dir = os.path.join(output_dir, "data")
    os.makedirs(data_dir, exist_ok=True)

    print(f"{'='*60}")
    print(f"  大模型榜单分析 — Type 9")
    print(f"{'='*60}")
    print(f"  📅 日期: {date_str}")
    print(f"  📁 输出: {output_dir}")
    print(f"  📁 数据: {data_dir}")
    print()

    # Step 1: Scrape
    if not args.skip_scrape:
        from collect_leaderboard import scrape_all_sources

        sources = None if args.source == "all" else [args.source]
        scrape_all_sources(date_str, data_dir, sources=sources)
    else:
        print("[跳过] 使用已有 CSV 数据")

    # Step 2: Analyze
    from analyze_leaderboard import run_analysis
    analysis = run_analysis(date_str, data_dir)

    # Step 3: Charts
    from charts_leaderboard import generate_charts
    chart_paths = generate_charts(analysis, output_dir)

    # Step 4: Report
    from report_leaderboard import generate_report
    report_path = generate_report(analysis, chart_paths, output_dir)

    # Summary
    print(f"\n{'='*60}")
    print(f"  ✅ 完成!")
    print(f"{'='*60}")
    print(f"  📊 报告: {report_path}")
    print(f"  📁 图表: {os.path.join(output_dir, 'charts')}")
    print(f"  📁 数据: {data_dir}")

    return report_path


if __name__ == "__main__":
    main()
