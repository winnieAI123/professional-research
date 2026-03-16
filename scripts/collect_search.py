"""
Web search data collection using Tavily API.
Supports keyword search, domain-restricted search, and full-text extraction.
Auto-rotates API keys on 429 quota errors.
"""

import time
import requests
from utils import get_api_key, deduplicate_results, normalize_url


# ============================================================
# Tavily API Key Rotation
# ============================================================

class TavilyQuotaExhausted(Exception):
    """Raised when ALL Tavily API keys have hit their quota limit.
    
    Agent should catch this and fallback to:
    1. Web search MCP tools (e.g., Google Search)
    2. Other search APIs available in the Agent environment
    """
    pass


# Track which keys have been exhausted (persists within a single script run)
_exhausted_keys = set()


def _get_tavily_keys() -> list:
    """Get all available Tavily API keys, primary first."""
    keys = []
    try:
        keys.append(get_api_key("TAVILY_API_KEY"))
    except EnvironmentError:
        pass
    
    # Try backup key
    try:
        import os
        from utils import _load_dotenv
        _load_dotenv()
        backup = os.environ.get("TAVILY_API_KEY_BACKUP", "").strip()
        if backup:
            keys.append(backup)
    except Exception:
        pass
    
    # Filter out exhausted keys
    available = [k for k in keys if k not in _exhausted_keys]
    return available


def _is_quota_error(resp_or_exception) -> bool:
    """Check if the error is a quota/rate limit error (429, 402, or 432)."""
    if isinstance(resp_or_exception, requests.Response):
        return resp_or_exception.status_code in (429, 402, 432)
    if isinstance(resp_or_exception, requests.exceptions.HTTPError):
        if hasattr(resp_or_exception, 'response') and resp_or_exception.response is not None:
            return resp_or_exception.response.status_code in (429, 402, 432)
    return False


# ============================================================
# Tavily Search
# ============================================================

def tavily_search(
    query: str,
    max_results: int = 10,
    search_depth: str = "advanced",
    include_domains: list = None,
    exclude_domains: list = None,
) -> list:
    """
    Search using Tavily API. Auto-rotates keys on 429 quota errors.
    
    Args:
        query: Search query string
        max_results: Maximum results to return (default 10)
        search_depth: "basic" or "advanced" (more precise but slower)
        include_domains: List of domains to restrict search to
        exclude_domains: List of domains to exclude
    
    Returns:
        List of result dicts with keys: title, url, content, score
    
    Raises:
        TavilyQuotaExhausted: When ALL API keys are exhausted.
            Agent should fallback to web search / MCP search tools.
    """
    available_keys = _get_tavily_keys()
    
    if not available_keys:
        raise TavilyQuotaExhausted(
            "所有 Tavily API key 配额已用完！\n"
            "⚠️ Agent 应改用以下替代方案继续搜索：\n"
            "  1. 使用 web_search / search_web 等 MCP 搜索工具\n"
            "  2. 使用 read_url_content 直接读取已知 URL\n"
            "  3. 使用 Google Search API 等其他搜索工具"
        )
    
    for api_key in available_keys:
        payload = {
            "api_key": api_key,
            "query": query,
            "max_results": max_results,
            "search_depth": search_depth,
        }
        
        if include_domains:
            payload["include_domains"] = include_domains
        if exclude_domains:
            payload["exclude_domains"] = exclude_domains
        
        try:
            resp = requests.post(
                "https://api.tavily.com/search",
                json=payload,
                timeout=30,
            )
            
            if _is_quota_error(resp):
                key_suffix = api_key[-8:]
                _exhausted_keys.add(api_key)
                print(f"  [Tavily] Key ...{key_suffix} 配额用完 (HTTP {resp.status_code})，切换下一个 key...")
                continue  # Try next key
            
            resp.raise_for_status()
            data = resp.json()
            
            results = []
            for r in data.get("results", []):
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "content": r.get("content", ""),
                    "score": r.get("score", 0),
                    "published_date": r.get("published_date", ""),
                })
            
            return results
        
        except requests.exceptions.HTTPError as e:
            if _is_quota_error(e):
                _exhausted_keys.add(api_key)
                print(f"  [Tavily] Key 配额用完，切换下一个 key...")
                continue
            print(f"  [Tavily Search Error] {e}")
            return []
        
        except Exception as e:
            print(f"  [Tavily Search Error] {e}")
            return []
    
    # All keys exhausted
    raise TavilyQuotaExhausted(
        "所有 Tavily API key 配额已用完！Agent 应改用 web_search 等替代搜索工具。"
    )


def tavily_extract(urls: list) -> list:
    """
    Extract full-text content from URLs using Tavily extract API.
    Auto-rotates keys on 429 quota errors.
    
    Args:
        urls: List of URLs to extract content from
    
    Returns:
        List of dicts with keys: url, raw_content, title
    
    Raises:
        TavilyQuotaExhausted: When ALL API keys are exhausted.
    """
    if not urls:
        return []
    
    available_keys = _get_tavily_keys()
    
    if not available_keys:
        raise TavilyQuotaExhausted(
            "所有 Tavily API key 配额已用完！Agent 应改用 read_url_content 等工具提取网页内容。"
        )
    
    for api_key in available_keys:
        try:
            from tavily import TavilyClient
            client = TavilyClient(api_key=api_key)
            result = client.extract(urls=urls[:20])
            return result.get("results", [])
        
        except ImportError:
            print("  [Warning] tavily-python not installed. Using raw API.")
            return _tavily_extract_raw(api_key, urls)
        
        except Exception as e:
            err_str = str(e).lower()
            if "429" in err_str or "402" in err_str or "432" in err_str or "quota" in err_str or "rate" in err_str:
                _exhausted_keys.add(api_key)
                print(f"  [Tavily] Extract key 配额用完，切换下一个 key...")
                continue
            print(f"  [Tavily Extract Error] {e}")
            return []
    
    raise TavilyQuotaExhausted(
        "所有 Tavily API key 配额已用完！Agent 应改用 read_url_content 等工具提取网页内容。"
    )


def _tavily_extract_raw(api_key: str, urls: list) -> list:
    """Fallback extraction using raw HTTP API."""
    try:
        resp = requests.post(
            "https://api.tavily.com/extract",
            json={"api_key": api_key, "urls": urls[:20]},
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json().get("results", [])
    except Exception as e:
        print(f"  [Tavily Raw Extract Error] {e}")
        return []


# ============================================================
# Site-Restricted Search (for Policy Research)
# ============================================================

def search_site(
    site: str,
    keywords: list,
    policy_type_words: str = "通知 意见 办法 指导意见 实施细则 管理规定",
    max_results: int = 10,
) -> list:
    """
    Search within a specific website domain.
    Useful for policy research (ministry/regulator websites).
    
    Args:
        site: Domain to search within (e.g., "miit.gov.cn")
        keywords: List of search keywords
        policy_type_words: Additional filter words for policy documents
        max_results: Max results per query
    
    Returns:
        Deduplicated list of search results
    """
    all_results = []
    
    for kw in keywords[:3]:  # Max 3 keyword queries per site
        # Query 1: broad search
        query1 = f"site:{site} {kw} {policy_type_words}"
        results = tavily_search(query1, max_results=max_results)
        all_results.extend(results)
        time.sleep(1)
        
        # Query 2: narrower with year
        import datetime
        year = datetime.datetime.now().year
        query2 = f"site:{site} {kw} {year}"
        results = tavily_search(query2, max_results=5)
        all_results.extend(results)
        time.sleep(1)
    
    return deduplicate_results(all_results)


# ============================================================
# Multi-Query Search (for comprehensive data collection)
# ============================================================

def multi_query_search(
    queries: list,
    max_results_per_query: int = 10,
    include_domains: list = None,
    delay: float = 1.0,
) -> list:
    """
    Execute multiple search queries and merge results.
    
    Args:
        queries: List of search query strings
        max_results_per_query: Max results per query
        include_domains: Optional domain restriction
        delay: Delay between queries in seconds
    
    Returns:
        Deduplicated merged results sorted by score
    """
    all_results = []
    
    for query in queries:
        results = tavily_search(
            query=query,
            max_results=max_results_per_query,
            include_domains=include_domains,
        )
        all_results.extend(results)
        print(f"  [Search] '{query[:60]}...' → {len(results)} results")
        time.sleep(delay)
    
    # Deduplicate and sort by score
    unique = deduplicate_results(all_results)
    unique.sort(key=lambda x: x.get("score", 0), reverse=True)
    
    print(f"  [Total] {len(all_results)} raw → {len(unique)} unique results")
    return unique
