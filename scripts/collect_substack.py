"""
Substack article collection using public search API.
Full-text extraction via Tavily extract.
"""

import time
import requests


# ============================================================
# Substack Search (Public API, no auth needed)
# ============================================================

def search_substack(
    query: str,
    max_pages: int = 3,
) -> list:
    """
    Search Substack articles using the public search API.
    
    Args:
        query: Search query (English recommended for broader results)
        max_pages: Number of result pages to fetch
    
    Returns:
        List of article dicts with title, author, url, date, preview
    """
    base_url = "https://substack.com/api/v1/top/search"
    headers = {
        "accept": "*/*",
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
    }
    
    all_posts = []
    
    for page in range(max_pages):
        params = {
            "query": query,
            "fromSuggestedSearch": "false",
        }
        if page > 0:
            params["page"] = page
        
        try:
            resp = requests.get(
                base_url,
                params=params,
                headers=headers,
                timeout=30,
            )
            resp.raise_for_status()
            items = resp.json().get("items", [])
            
            for item in items:
                if item.get("type") == "post" and "post" in item:
                    post = item["post"]
                    
                    # Extract author
                    author = ""
                    if post.get("publishedBylines"):
                        author = post["publishedBylines"][0].get("name", "")
                    
                    # Get content preview
                    content = (
                        post.get("truncated_body_text", "")
                        or post.get("description", "")
                    )
                    
                    all_posts.append({
                        "title": post.get("title", ""),
                        "subtitle": post.get("subtitle", ""),
                        "url": post.get("canonical_url", ""),
                        "author": author,
                        "date": post.get("post_date", ""),
                        "content_preview": content[:500],
                        "word_count": post.get("wordcount", 0),
                        "source": "substack",
                    })
            
            if not items:
                break
                
        except Exception as e:
            print(f"  [Substack Search Error] Page {page}: {e}")
        
        time.sleep(1)
    
    print(f"  [Substack] Found {len(all_posts)} articles for '{query[:40]}'")
    return all_posts


# ============================================================
# Full-Text Extraction (via Tavily)
# ============================================================

def get_full_articles(posts: list, max_articles: int = 10) -> list:
    """
    Get full text content of Substack articles using Tavily extract.
    
    Substack search API only returns ~500 char previews.
    For report writing, we need full article text.
    
    Args:
        posts: List of post dicts from search_substack()
        max_articles: Maximum articles to extract full text for
    
    Returns:
        List of dicts with full content added
    """
    from collect_search import tavily_extract
    
    urls = [p["url"] for p in posts[:max_articles] if p.get("url")]
    
    if not urls:
        return posts
    
    try:
        extracted = tavily_extract(urls)
        
        # Map extracted content back to posts
        url_to_content = {
            e["url"]: e.get("raw_content", "")
            for e in extracted
        }
        
        for post in posts:
            if post["url"] in url_to_content:
                post["full_content"] = url_to_content[post["url"]]
        
        extracted_count = sum(1 for p in posts if p.get("full_content"))
        print(f"  [Substack Full-Text] Extracted {extracted_count}/{len(urls)} articles")
        
    except Exception as e:
        print(f"  [Substack Full-Text Error] {e}")
    
    return posts
