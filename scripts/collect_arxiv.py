"""
arXiv paper collection: keyword search, PDF download, and full-text extraction.
Used by Industry Research (Type 3, tech part) and Academic Briefing (Type 6).
"""

import os
import time

try:
    import arxiv
except ImportError:
    arxiv = None
    print("  [Warning] 'arxiv' package not installed. Run: python -m pip install arxiv")

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None
    print("  [Warning] 'PyMuPDF' package not installed. Run: python -m pip install PyMuPDF")


# ============================================================
# arXiv Search
# ============================================================

def search_arxiv(
    query: str,
    max_results: int = 5,
    sort_by: str = "relevance",
) -> list:
    """
    Search arXiv for papers matching a query.
    
    Args:
        query: English search query with boolean operators (AND/OR)
               Example: '"embodied AI" AND ("VLA" OR "world model")'
        max_results: Number of top results to return
        sort_by: "relevance" or "submitted_date"
    
    Returns:
        List of paper metadata dicts
    """
    if arxiv is None:
        print("  [Error] arxiv package required. Install: python -m pip install arxiv")
        return []
    
    sort_criterion = (
        arxiv.SortCriterion.Relevance
        if sort_by == "relevance"
        else arxiv.SortCriterion.SubmittedDate
    )
    
    search = arxiv.Search(
        query=query,
        max_results=max_results,
        sort_by=sort_criterion,
    )
    
    papers = []
    try:
        for result in arxiv.Client().results(search):
            papers.append({
                "arxiv_id": result.get_short_id(),
                "title": result.title,
                "abstract": result.summary,
                "authors": [a.name for a in result.authors],
                "published": result.published.strftime("%Y-%m-%d"),
                "link": result.entry_id,
                "pdf_url": result.pdf_url,
                "categories": result.categories,
                "source": "arxiv",
            })
            print(f"  [arXiv] {result.title[:60]}... ({result.published.date()})")
    
    except Exception as e:
        print(f"  [arXiv Search Error] {e}")
    
    return papers


# ============================================================
# PDF Download
# ============================================================

def download_papers(
    papers: list,
    output_dir: str,
) -> list:
    """
    Download PDF files for arXiv papers.
    
    Args:
        papers: List of paper dicts from search_arxiv()
        output_dir: Directory to save PDFs
    
    Returns:
        Updated paper list with 'pdf_path' field added
    """
    if arxiv is None:
        return papers
    
    os.makedirs(output_dir, exist_ok=True)
    
    for paper in papers:
        try:
            arxiv_id = paper["arxiv_id"]
            filename = f"{arxiv_id.replace('/', '_')}.pdf"
            pdf_path = os.path.join(output_dir, filename)
            
            if os.path.exists(pdf_path):
                print(f"  [PDF] Already exists: {filename}")
                paper["pdf_path"] = pdf_path
                continue
            
            # Download using arxiv library
            search = arxiv.Search(id_list=[arxiv_id])
            result = next(arxiv.Client().results(search))
            result.download_pdf(dirpath=output_dir, filename=filename)
            
            paper["pdf_path"] = pdf_path
            print(f"  [PDF] Downloaded: {filename}")
            time.sleep(1)
            
        except Exception as e:
            print(f"  [PDF Download Error] {arxiv_id}: {e}")
    
    return papers


# ============================================================
# PDF Text Extraction
# ============================================================

def extract_pdf_text(
    pdf_path: str,
    max_chars: int = 40000,
) -> str:
    """
    Extract text content from a PDF file using PyMuPDF.
    
    Args:
        pdf_path: Path to the PDF file
        max_chars: Maximum characters to extract (truncate if longer)
    
    Returns:
        Extracted text string
    """
    if fitz is None:
        print("  [Error] PyMuPDF required. Install: python -m pip install PyMuPDF")
        return ""
    
    try:
        doc = fitz.open(pdf_path)
        text = ""
        
        for page in doc:
            text += page.get_text()
            if len(text) > max_chars:
                text = text[:max_chars] + "\n[...content truncated...]"
                break
        
        doc.close()
        return text
    
    except Exception as e:
        print(f"  [PDF Extract Error] {pdf_path}: {e}")
        return ""


def extract_all_papers(papers: list, max_chars: int = 40000) -> list:
    """
    Extract text from all downloaded papers.
    
    Args:
        papers: List of paper dicts (must have 'pdf_path')
        max_chars: Max chars per paper
    
    Returns:
        Updated paper list with 'full_text' field added
    """
    for paper in papers:
        pdf_path = paper.get("pdf_path")
        if pdf_path and os.path.exists(pdf_path):
            paper["full_text"] = extract_pdf_text(pdf_path, max_chars)
            char_count = len(paper["full_text"])
            print(f"  [Text] {paper['arxiv_id']}: {char_count:,} chars")
        else:
            paper["full_text"] = ""
            print(f"  [Text] {paper.get('arxiv_id', '?')}: No PDF available")
    
    return papers


# ============================================================
# Combined Pipeline: Search → Download → Extract
# ============================================================

def fetch_and_analyze_papers(
    query: str,
    output_dir: str,
    max_results: int = 5,
    sort_by: str = "relevance",
) -> list:
    """
    Complete pipeline: search arXiv → download PDFs → extract text.
    
    Args:
        query: arXiv search query
        output_dir: Directory for PDFs
        max_results: Number of papers
        sort_by: Sort criterion
    
    Returns:
        List of paper dicts with full_text populated
    """
    print(f"\n  === arXiv Pipeline: '{query[:50]}...' ===")
    
    # Step 1: Search
    papers = search_arxiv(query, max_results, sort_by)
    if not papers:
        print("  [Warning] No papers found for query")
        return []
    
    # Step 2: Download PDFs
    papers = download_papers(papers, output_dir)
    
    # Step 3: Extract text
    papers = extract_all_papers(papers)
    
    papers_with_text = sum(1 for p in papers if p.get("full_text"))
    print(f"  === Pipeline complete: {papers_with_text}/{len(papers)} papers with text ===\n")
    
    return papers
