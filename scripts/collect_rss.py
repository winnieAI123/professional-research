"""
RSS feed collection for AI lab blogs and news sources.
Used by Academic Briefing (Type 6) pipeline.
"""

import time
import json
import os
import socket
from datetime import datetime, timedelta

# Prevent RSS feeds from hanging on slow/proxy networks
socket.setdefaulttimeout(15)

try:
    import feedparser
except ImportError:
    feedparser = None
    print("  [Warning] 'feedparser' not installed. Run: python -m pip install feedparser")

from utils import get_config_path


# ============================================================
# Default Blog Feeds (fallback if config not found)
# ============================================================

DEFAULT_FEEDS = {
    "Google AI":           "https://blog.google/technology/ai/rss/",
    "OpenAI":              "https://openai.com/blog/rss.xml",
    "Microsoft Research":  "https://www.microsoft.com/en-us/research/feed/",
    "DeepMind":            "https://deepmind.google/blog/rss.xml",
    "Hugging Face":        "https://huggingface.co/blog/feed.xml",
    "Anthropic":           "https://www.anthropic.com/rss.xml",
    "机器之心":            "https://plink.anyfeeder.com/weixin/almosthuman2014",
}


# ============================================================
# Load Feed Configuration
# ============================================================

def load_feed_config() -> dict:
    """
    Load RSS feed URLs from config file.
    Falls back to DEFAULT_FEEDS if config not found.
    """
    config_path = get_config_path("blog_feeds.json")
    
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"  [Config Warning] {e}. Using defaults.")
    
    return DEFAULT_FEEDS


# ============================================================
# RSS Collection
# ============================================================

def fetch_blog_feeds(
    feeds: dict = None,
    days: int = 7,
) -> list:
    """
    Fetch articles from AI lab blog RSS feeds.
    
    Args:
        feeds: Dict of {name: rss_url}. If None, loads from config.
        days: Only include articles from the last N days
    
    Returns:
        List of article dicts with title, abstract, link, source, date
    """
    if feedparser is None:
        print("  [Error] feedparser required. Install: python -m pip install feedparser")
        return []
    
    if feeds is None:
        feeds = load_feed_config()
    
    cutoff = datetime.now() - timedelta(days=days)
    articles = []
    
    for name, url in feeds.items():
        try:
            feed = feedparser.parse(url)
            count = 0
            
            for entry in feed.entries:
                # Try to parse publication date
                pub_date = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    try:
                        pub_date = datetime(*entry.published_parsed[:6])
                    except Exception:
                        pass
                
                # Date filtering (if we can determine the date)
                if pub_date and pub_date < cutoff:
                    continue
                
                articles.append({
                    "title": entry.get("title", "").strip(),
                    "abstract": (entry.get("summary", "") or "")[:500],
                    "link": entry.get("link", ""),
                    "source": name,
                    "date": pub_date.strftime("%Y-%m-%d") if pub_date else "",
                    "source_type": "blog_rss",
                })
                count += 1
            
            print(f"  [RSS] {name}: {count} articles (last {days} days)")
            time.sleep(0.5)
            
        except Exception as e:
            print(f"  [RSS Error] {name}: {e}")
    
    print(f"  [RSS Total] {len(articles)} articles from {len(feeds)} sources")
    return articles


# ============================================================
# arXiv RSS (Daily new paper tracking)
# ============================================================

# Default arXiv categories to monitor
DEFAULT_ARXIV_CATEGORIES = {
    "cs.AI":   "人工智能",
    "cs.LG":   "机器学习",
    "cs.CL":   "自然语言处理",
    "cs.CV":   "计算机视觉",
    "cs.RO":   "机器人学",
    "cs.AR":   "计算机体系结构",
}


def fetch_arxiv_rss(
    categories: dict = None,
) -> list:
    """
    Fetch today's new papers from arXiv RSS feeds.
    
    arXiv publishes new paper announcements on business days via RSS.
    This captures the daily firehose for filtering.
    
    Args:
        categories: Dict of {arxiv_category: chinese_name}.
                    If None, uses DEFAULT_ARXIV_CATEGORIES.
    
    Returns:
        List of paper dicts with title, abstract, link, category
    """
    if feedparser is None:
        print("  [Error] feedparser required")
        return []
    
    if categories is None:
        categories = DEFAULT_ARXIV_CATEGORIES
    
    all_papers = []
    seen_ids = set()  # Cross-category dedup
    
    for cat, cat_name in categories.items():
        url = f"http://export.arxiv.org/rss/{cat}"
        
        try:
            feed = feedparser.parse(url)
            count = 0
            
            for entry in feed.entries:
                # Extract arXiv ID
                arxiv_id = entry.link.split("/abs/")[-1] if "/abs/" in entry.link else ""
                
                if arxiv_id in seen_ids:
                    continue
                seen_ids.add(arxiv_id)
                
                # Clean title (remove arXiv metadata suffix)
                title = entry.title
                if ". (arXiv" in title:
                    title = title.split(". (arXiv")[0].strip()
                
                # Extract authors (RSS provides author/dc:creator)
                authors = ''
                if hasattr(entry, 'author'):
                    authors = entry.author
                elif hasattr(entry, 'authors'):
                    authors = ', '.join(a.get('name', '') for a in entry.authors if a.get('name'))
                
                all_papers.append({
                    "arxiv_id": arxiv_id,
                    "title": title,
                    "authors": authors,
                    "abstract": entry.summary,
                    "link": entry.link,
                    "category": cat,
                    "category_name": cat_name,
                    "source": "arxiv_rss",
                })
                count += 1
            
            print(f"  [arXiv RSS] {cat} ({cat_name}): {count} new papers")
            time.sleep(0.5)
            
        except Exception as e:
            print(f"  [arXiv RSS Error] {cat}: {e}")
    
    print(f"  [arXiv RSS Total] {len(all_papers)} papers (deduplicated)")
    return all_papers
