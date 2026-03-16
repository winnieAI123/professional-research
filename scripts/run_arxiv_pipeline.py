"""
arXiv Research Pipeline — Fixed Script
Usage:
    python run_arxiv_pipeline.py --topic "具身智能/人形机器人" --output data/arxiv_results.json
    python run_arxiv_pipeline.py --keywords "humanoid robot VLA world model" --output data/arxiv_results.json

This script MUST be called whenever research involves technical/academic content.
It guarantees: keyword generation → arXiv search → PDF download → full text extraction.
Agent CANNOT skip PDF download by calling search_arxiv() directly.
"""

import sys, os, json, argparse, socket
from datetime import datetime

os.environ["PYTHONIOENCODING"] = "utf-8"
socket.setdefaulttimeout(30)

# Ensure scripts are importable
SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SKILL_DIR)

from collect_arxiv import fetch_and_analyze_papers
from llm_client import generate_search_keywords


def run_pipeline(topic: str, keywords: str = None, output_path: str = None,
                 max_papers: int = 5, sort_by: str = "submitted_date") -> dict:
    """
    Complete arXiv research pipeline.
    
    Args:
        topic: Research topic (Chinese or English)
        keywords: Optional pre-generated English keywords. If None, LLM generates them.
        output_path: Path to save JSON output. If None, prints to stdout.
        max_papers: Number of papers to fetch (default 5)
        sort_by: "submitted_date" or "relevance"
    
    Returns:
        Dict with papers data and metadata
    """
    print(f"\n{'=' * 60}")
    print(f"arXiv Pipeline: {topic}")
    print(f"{'=' * 60}")
    
    # Step 1: Generate search keywords if not provided
    if not keywords:
        print("\n[Step 1] Generating arXiv search keywords via LLM...")
        try:
            kw_list = generate_search_keywords(topic)
            # Build arXiv boolean query from keywords
            if len(kw_list) >= 2:
                # Use first keyword as main, rest as OR alternatives
                main_kw = kw_list[0]
                alternatives = '" OR "'.join(kw_list[1:])
                keywords = f'"{main_kw}" AND ("{alternatives}")'
            else:
                keywords = f'"{kw_list[0]}"' if kw_list else topic
            print(f"  Generated query: {keywords}")
        except Exception as e:
            print(f"  [Warning] Keyword generation failed ({e}), using topic directly")
            keywords = topic
    else:
        print(f"\n[Step 1] Using provided keywords: {keywords}")
    
    # Step 2: Search + Download PDF + Extract Full Text
    print(f"\n[Step 2] arXiv search + PDF download + text extraction...")
    papers_dir = os.path.join(os.path.dirname(output_path) if output_path else ".", "arxiv_papers")
    os.makedirs(papers_dir, exist_ok=True)
    
    papers = fetch_and_analyze_papers(
        query=keywords,
        output_dir=papers_dir,
        max_results=max_papers,
        sort_by=sort_by,
    )
    
    # Step 3: Structure output
    with_text = sum(1 for p in papers if p.get("full_text"))
    
    result = {
        "metadata": {
            "topic": topic,
            "query": keywords,
            "timestamp": datetime.now().isoformat(),
            "total_papers": len(papers),
            "papers_with_fulltext": with_text,
            "papers_dir": papers_dir,
        },
        "papers": [
            {
                "title": p.get("title", ""),
                "abstract": p.get("abstract", ""),
                "full_text": p.get("full_text", ""),
                "authors": p.get("authors", []),
                "link": p.get("link", ""),
                "published": p.get("published", ""),
                "categories": p.get("categories", []),
                "pdf_path": p.get("pdf_path", ""),
            }
            for p in papers
        ],
    }
    
    # Step 4: Save output
    if output_path:
        os.makedirs(os.path.dirname(output_path), exist_ok=True) if os.path.dirname(output_path) else None
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"\n[Output] Saved to: {output_path}")
    
    print(f"\n{'=' * 60}")
    print(f"Pipeline complete: {len(papers)} papers, {with_text} with full text")
    print(f"{'=' * 60}\n")
    
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="arXiv Research Pipeline")
    parser.add_argument("--topic", required=True, help="Research topic (Chinese or English)")
    parser.add_argument("--keywords", default=None, help="Pre-generated English search keywords")
    parser.add_argument("--output", default="arxiv_results.json", help="Output JSON path")
    parser.add_argument("--max-papers", type=int, default=5, help="Number of papers")
    parser.add_argument("--sort-by", default="submitted_date", choices=["submitted_date", "relevance"])
    
    args = parser.parse_args()
    
    result = run_pipeline(
        topic=args.topic,
        keywords=args.keywords,
        output_path=args.output,
        max_papers=args.max_papers,
        sort_by=args.sort_by,
    )
    
    # Print summary
    for i, p in enumerate(result["papers"]):
        has_text = "✓" if p.get("full_text") else "✗"
        print(f"  [{i+1}] [{has_text}] {p['title'][:80]}")
