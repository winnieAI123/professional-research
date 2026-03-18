# -*- coding: utf-8 -*-
"""
Type 6: Academic Paper Briefing — One-Click Pipeline

Collects arXiv papers + AI lab blog posts, filters by research focus areas,
generates Chinese summaries, and produces a formatted Word report.

Usage:
    python run_paper_briefing.py --output D:/clauderesult/claude0318/
    python run_paper_briefing.py  # Uses default output dir

Takes ~3-5 minutes total. Outputs:
    - 学术简报_YYYYMMDD.json  (structured data)
    - 学术简报_YYYYMMDD.docx  (formatted Word report)
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from collections import defaultdict

# Add scripts/ to path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from collect_rss import fetch_arxiv_rss, fetch_blog_feeds
from llm_client import generate_content
from generate_paper_briefing import generate_paper_briefing_word


# ============================================================
# LaTeX Cleanup
# ============================================================

def _clean_latex(text: str) -> str:
    """Strip LaTeX math notation from text for clean Word output."""
    import re
    # Remove $...$ inline math markers, keep content
    text = re.sub(r'\$([^$]+)\$', r'\1', text)
    # Remove common LaTeX commands
    text = re.sub(r'\\mathbb\{([^}]+)\}', r'\1', text)
    text = re.sub(r'\\mathcal\{([^}]+)\}', r'\1', text)
    text = re.sub(r'\\text\{([^}]+)\}', r'\1', text)
    text = re.sub(r'\\textit\{([^}]+)\}', r'\1', text)
    text = re.sub(r'\\textbf\{([^}]+)\}', r'\1', text)
    text = re.sub(r'\\[a-zA-Z]+\{([^}]+)\}', r'\1', text)  # generic \cmd{content}
    text = re.sub(r'\\[a-zA-Z]+', '', text)  # standalone \commands
    # Clean up extra spaces
    text = re.sub(r'  +', ' ', text)
    return text.strip()


# ============================================================
# Research Focus Areas & Keywords
# ============================================================

FOCUS_AREAS = {
    "计算架构": [
        "Processing-in-Memory", "PIM", "Near-Memory Computing", "Near-Memory",
        "3D-NAND", "3D NAND", "3D-SRAM", "3D SRAM",
        "Neuromorphic", "neuromorphic computing",
        "Processing-Near-Memory", "Processing-Using-Memory",
    ],
    "大模型优化": [
        "LLM Quantization", "quantization", "Model Compression", "model compression",
        "KV Cache", "KV-Cache", "key-value cache",
        "MoE", "Mixture of Experts", "mixture-of-experts",
        "Self-Evolution", "self-evolution",
        "Continual Learning", "continual learning",
        "Multimodal Large Language Model", "MLLM",
    ],
    "系统/互联": [
        "CXL", "Compute Express Link",
        "HBM", "High Bandwidth Memory",
        "HBF",
        "Optical Interconnect", "optical interconnect", "photonic interconnect",
        "Chiplet", "chiplet",
    ],
}


# ============================================================
# Step 0: Fetch Full Abstracts from arXiv API
# ============================================================

ARXIV_API_URL = "http://export.arxiv.org/api/query"

def _extract_arxiv_id(link: str) -> str:
    """Extract arXiv ID from URL like https://arxiv.org/abs/2603.15886"""
    m = re.search(r'(\d{4}\.\d{4,5})', link)
    return m.group(1) if m else ""


def fetch_full_abstracts(papers: list, batch_size: int = 20):
    """Fetch complete abstracts from arXiv API, replacing truncated RSS ones.
    
    arXiv API: http://export.arxiv.org/api/query?id_list=2603.15886,2603.15987,...
    """
    # Collect arXiv IDs
    id_map = {}  # arxiv_id -> paper index
    for i, p in enumerate(papers):
        aid = _extract_arxiv_id(p.get("link", ""))
        if aid:
            id_map[aid] = i
    
    if not id_map:
        return
    
    print(f"\n=== Step 4.5: 获取完整摘要（{len(id_map)} 篇）===")
    
    fetched = 0
    ids_list = list(id_map.keys())
    
    for batch_start in range(0, len(ids_list), batch_size):
        batch_ids = ids_list[batch_start:batch_start + batch_size]
        id_str = ",".join(batch_ids)
        url = f"{ARXIV_API_URL}?id_list={id_str}&max_results={len(batch_ids)}"
        
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "PaperBriefing/1.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                xml_data = resp.read().decode("utf-8")
            
            root = ET.fromstring(xml_data)
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            
            for entry in root.findall("atom:entry", ns):
                # Extract ID
                id_elem = entry.find("atom:id", ns)
                if id_elem is None:
                    continue
                aid = _extract_arxiv_id(id_elem.text or "")
                if aid not in id_map:
                    continue
                
                # Extract full abstract
                summary_elem = entry.find("atom:summary", ns)
                if summary_elem is not None and summary_elem.text:
                    full_abstract = summary_elem.text.strip()
                    if full_abstract:
                        idx = id_map[aid]
                        papers[idx]["abstract"] = full_abstract
                        fetched += 1
            
            time.sleep(1)  # Be polite to arXiv API
            
        except Exception as e:
            print(f"  [API batch error] {e}")
    
    print(f"  完整摘要获取: {fetched}/{len(id_map)} 篇已更新")


# ============================================================
# Step 1: Keyword Matching
# ============================================================

def match_keywords(papers: list) -> list:
    """Match papers to focus areas by keyword. Returns papers with area + keywords."""
    matched = []
    for paper in papers:
        text = (paper.get("title", "") + " " + paper.get("abstract", "")).lower()
        best_area = None
        best_keywords = []
        best_count = 0

        for area, keywords in FOCUS_AREAS.items():
            hits = [kw for kw in keywords if kw.lower() in text]
            if len(hits) > best_count:
                best_count = len(hits)
                best_area = area
                best_keywords = hits

        if best_area:
            paper["area"] = best_area
            paper["keywords"] = best_keywords
            matched.append(paper)

    return matched


# ============================================================
# Step 2: LLM Filtering (Fast model)
# ============================================================

FILTER_CRITERIA = """判断这篇论文是否具有较高的技术研究价值，符合以下任一条件即保留：
1. 提出了新的模型架构、训练方法或优化技术
2. 在重要基准上取得了显著性能提升
3. 解决了LLM/多模态/具身智能/计算效率领域的实际问题
4. 具有工程实践意义（部署优化、硬件加速等）
排除：仅综述/调研性质的论文，或纯数学理论无实验验证的论文。"""


def llm_filter_batch(papers: list, batch_size: int = 15) -> list:
    """Use flash model to filter papers by research value."""
    if not papers:
        return []

    filtered = []
    total_batches = (len(papers) + batch_size - 1) // batch_size
    print(f"\n=== LLM 精筛（{len(papers)} 篇，{total_batches} 批）===")

    for i in range(0, len(papers), batch_size):
        batch = papers[i:i + batch_size]
        batch_num = i // batch_size + 1

        items_text = "\n".join([
            f"{j+1}. Title: {p['title']}\nAbstract: {p['abstract'][:300]}"
            for j, p in enumerate(batch)
        ])

        prompt = f"""请判断以下论文的研究价值。

{FILTER_CRITERIA}

论文列表：
{items_text}

请只输出保留的论文编号（1-based），用JSON数组格式，例如 [1, 3, 5]。
只输出JSON数组，不要其他内容。"""

        try:
            result = generate_content(prompt, use_fast_model=True, return_json=True)
            if isinstance(result, list):
                for idx in result:
                    if isinstance(idx, int) and 1 <= idx <= len(batch):
                        filtered.append(batch[idx - 1])
                    elif isinstance(idx, dict) and "index" in idx:
                        real_idx = idx["index"]
                        if isinstance(real_idx, int) and 1 <= real_idx <= len(batch):
                            filtered.append(batch[real_idx - 1])
        except Exception as e:
            print(f"  [Batch {batch_num} error] {e} — keeping all")
            filtered.extend(batch)

        if batch_num % 5 == 0 or batch_num == total_batches:
            print(f"  Progress: {batch_num}/{total_batches}, kept {len(filtered)}")

    print(f"  精筛结果: {len(filtered)} / {len(papers)}")
    return filtered


# ============================================================
# Step 3: Summary Generation (Pro model)
# ============================================================

SUMMARY_PROMPT_PREFIX = """请将以下英文论文摘要翻译为中文。

翻译要求：
- 忠实翻译原文，不要删减、改写或"总结"
- 保留所有技术术语，首次出现时括号附上英文原文
- 保留所有数字、百分比和实验结果
- 数学公式用纯文本表达，禁止输出任何 LaTeX 符号（如 $ 或 \\）
- 直接输出翻译正文，不要加"摘要："等前缀

"""


def generate_summaries(papers: list) -> list:
    """Generate Chinese summaries for each paper."""
    print(f"\n=== 生成中文摘要（{len(papers)} 篇）===")

    for i, paper in enumerate(papers):
        title = paper.get("title", "")
        abstract = paper.get("abstract", "")
        prompt = (
            SUMMARY_PROMPT_PREFIX
            + f"论文标题: {title}\n"
            + f"英文摘要:\n{abstract}\n\n"
            + "中文翻译："
        )

        try:
            summary = generate_content(
                prompt,
                model="models/gemini-3-flash-preview",
                max_output_tokens=2048,
            )
            paper["summary"] = _clean_latex(summary.strip()) if summary else ""
        except Exception as e:
            print(f"  [Paper {i+1}] Summary failed: {e}")
            paper["summary"] = f"[摘要生成失败] {paper.get('abstract', '')[:300]}"

        if (i + 1) % 10 == 0 or (i + 1) == len(papers):
            print(f"  Progress: {i+1}/{len(papers)}")

    good = sum(1 for p in papers if len(p.get("summary", "")) > 100)
    print(f"  摘要质量: {good}/{len(papers)} 篇 > 100字")
    return papers


# ============================================================
# Step 4: Assemble JSON
# ============================================================

def assemble_json(papers: list, blogs: list, total_arxiv: int) -> dict:
    """Assemble the final JSON structure for Word generation."""
    by_area = defaultdict(list)
    hw_words = ["bandwidth", "latency", "flops", "energy", "throughput",
                "dram", "gpu", "tpu", "fpga", "sram", "npu"]

    for p in papers:
        area = p.get("area", "基础模型")
        by_area[area].append({
            "title": p.get("title", ""),
            "authors": p.get("authors", ""),
            "link": p.get("link", ""),
            "keywords": p.get("keywords", []),
            "summary": p.get("summary", ""),
            "hardware_specs": [kw for kw in p.get("keywords", [])
                              if any(hw in kw.lower() for hw in hw_words)],
        })

    area_order = ["计算架构", "大模型优化", "系统/互联"]
    categories = []
    for area in area_order:
        if area in by_area:
            categories.append({"name": area, "papers": by_area[area]})
    for area in by_area:
        if area not in area_order:
            categories.append({"name": area, "papers": by_area[area]})

    blog_by_source = defaultdict(list)
    for b in blogs:
        blog_by_source[b.get("source", "其他")].append({
            "title_zh": b.get("title", ""),
            "summary": b.get("abstract", "")[:200],
            "link": b.get("link", ""),
        })

    return {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "total_papers": len(papers),
        "total_directions": len(categories),
        "total_arxiv": total_arxiv,
        "categories": categories,
        "blog_updates": [{"source": s, "articles": a}
                         for s, a in blog_by_source.items()],
    }


# ============================================================
# Main Pipeline
# ============================================================

def run_pipeline(output_dir: str = None):
    """Run the full paper briefing pipeline."""
    start = time.time()
    today = datetime.now().strftime("%Y%m%d")

    if output_dir is None:
        output_dir = os.path.join("D:/clauderesult", f"claude{today[4:]}")
    os.makedirs(output_dir, exist_ok=True)

    print("=" * 60)
    print(f"  学术论文追踪简报 — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    # Step 1: Collect arXiv
    print("\n=== Step 1: 收集 arXiv ===")
    arxiv_papers = fetch_arxiv_rss()
    total_arxiv = len(arxiv_papers)
    print(f"  共 {total_arxiv} 篇")

    # Step 2: Collect blogs
    print("\n=== Step 2: 收集博客 ===")
    blogs = fetch_blog_feeds(days=1)
    print(f"  共 {len(blogs)} 篇")

    # Step 3: Keyword matching
    print("\n=== Step 3: 关键词预筛选 ===")
    matched = match_keywords(arxiv_papers)
    print(f"  命中: {len(matched)} / {total_arxiv}")
    area_counts = defaultdict(int)
    for p in matched:
        area_counts[p["area"]] += 1
    for area, cnt in sorted(area_counts.items(), key=lambda x: -x[1]):
        print(f"    {area}: {cnt}")

    # Step 4: Cap per area (top MAX_PER_AREA by keyword match count)
    MAX_PER_AREA = 20
    by_area = defaultdict(list)
    for p in matched:
        by_area[p["area"]].append(p)
    filtered = []
    for area, papers in by_area.items():
        papers.sort(key=lambda x: len(x.get("keywords", [])), reverse=True)
        filtered.extend(papers[:MAX_PER_AREA])
    print(f"\n=== Step 4: 按关键词命中数排序，每方向最多 {MAX_PER_AREA} 篇 ===")
    print(f"  筛后: {len(filtered)} 篇")

    # Step 4.5: Fetch full abstracts from arXiv API
    fetch_full_abstracts(filtered)

    # Step 5: Generate summaries
    summarized = generate_summaries(filtered)

    # Step 6: Assemble + save JSON
    print("\n=== Step 6: 保存数据 ===")
    data = assemble_json(summarized, blogs, total_arxiv)
    json_path = os.path.join(output_dir, f"学术简报_{today}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  JSON: {json_path}")

    # Step 7: Word report
    print("\n=== Step 7: 生成 Word ===")
    docx_path = os.path.join(output_dir, f"学术简报_{today}.docx")
    generate_paper_briefing_word(data, docx_path)

    elapsed = time.time() - start
    print(f"\n{'=' * 60}")
    print(f"  ✅ 完成！耗时 {elapsed:.0f} 秒")
    print(f"  论文: {data['total_papers']} 篇 | 方向: {data['total_directions']} 个")
    for cat in data["categories"]:
        print(f"    {cat['name']}: {len(cat['papers'])} 篇")
    print(f"  Word: {docx_path}")
    print(f"  JSON: {json_path}")
    print(f"{'=' * 60}")

    return docx_path, json_path


def main():
    parser = argparse.ArgumentParser(description="学术论文追踪简报 — 一键生成")
    parser.add_argument("--output", "-o", help="输出目录")
    args = parser.parse_args()
    run_pipeline(args.output)


if __name__ == "__main__":
    main()
