"""
Type 8 Submodule: Quarterly Earnings Data Collector (季度业绩数据采集)

Pure data fetcher — no LLM calls. Outputs transcript + press release files.
Agent reads these files and writes the report using the earnings_quarterly.md template.

Data Sources:
  1. SA Premium transcript (cookie-based API) — highest priority
  2. SA RapidAPI transcript — fallback
  3. Press Release: IR page scraper (大厂) → Tavily search (其他)
"""

import os
import re
import json
import sys
import time
import requests
from datetime import datetime
from bs4 import BeautifulSoup

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from collect_financial_deep import get_api_key, detect_data_source

RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY", "")
TAVILY_API_KEY = get_api_key("TAVILY_API_KEY")




# ============================================================
# Ticker Resolution for Seeking Alpha (Chinese ADR support)
# ============================================================
# Chinese company → US ADR ticker + reporting currency
_CN_ADR_MAP = {
    '美团': {'t': 'MPNGY', 'c': 'RMB'}, '拼多多': {'t': 'PDD', 'c': 'USD'},
    '阿里巴巴': {'t': 'BABA', 'c': 'USD'}, '京东': {'t': 'JD', 'c': 'USD'},
    '百度': {'t': 'BIDU', 'c': 'USD'}, '网易': {'t': 'NTES', 'c': 'USD'},
    '哔哩哔哩': {'t': 'BILI', 'c': 'RMB'}, 'B站': {'t': 'BILI', 'c': 'RMB'},
    '腾讯': {'t': 'TCEHY', 'c': 'RMB'}, '小鹏': {'t': 'XPEV', 'c': 'USD'},
    '蔚来': {'t': 'NIO', 'c': 'USD'}, '理想': {'t': 'LI', 'c': 'USD'},
    '携程': {'t': 'TCOM', 'c': 'USD'}, '爱奇艺': {'t': 'IQ', 'c': 'USD'},
    '微博': {'t': 'WB', 'c': 'USD'}, '新东方': {'t': 'EDU', 'c': 'USD'},
    '好未来': {'t': 'TAL', 'c': 'USD'}, '唯品会': {'t': 'VIPS', 'c': 'USD'},
    '瑞幸': {'t': 'LKNCY', 'c': 'USD'}, '满帮': {'t': 'YMM', 'c': 'USD'},
    '知乎': {'t': 'ZH', 'c': 'USD'}, '达达': {'t': 'DADA', 'c': 'USD'},
    '贝壳': {'t': 'BEKE', 'c': 'USD'}, '逸仙电商': {'t': 'YSG', 'c': 'USD'},
    '富途': {'t': 'FUTU', 'c': 'USD'}, '老虎证券': {'t': 'TIGR', 'c': 'USD'},
    '台积电': {'t': 'TSM', 'c': 'USD'},
    '奇富科技': {'t': 'QFIN', 'c': 'USD'}, '360数科': {'t': 'QFIN', 'c': 'USD'},
    '信也科技': {'t': 'FINV', 'c': 'USD'},
    '陆金所': {'t': 'LU', 'c': 'USD'}, '小赢科技': {'t': 'XYF', 'c': 'USD'},
    '乐信': {'t': 'LX', 'c': 'USD'},
    '名创优品': {'t': 'MNSO', 'c': 'USD'}, '极氪': {'t': 'ZK', 'c': 'USD'},
    '小米': {'t': 'XIACY', 'c': 'USD'},
    '中通快递': {'t': 'ZTO', 'c': 'USD'}, '金山云': {'t': 'KC', 'c': 'USD'},
    '声网': {'t': 'API', 'c': 'USD'},
    'BOSS直聘': {'t': 'BZ', 'c': 'USD'}, '高途': {'t': 'GOTU', 'c': 'USD'},
    '趣头条': {'t': 'QTT', 'c': 'USD'},
    '快手': {'t': 'KUASF', 'c': 'RMB'},
    'MiniMax': {'t': 'MNMXF', 'c': 'USD'},
    '智谱AI': {'t': 'KATJF', 'c': 'USD'},
}

# Reverse map: ADR ticker → Chinese name (for better Tavily search fallback)
_ADR_TO_CN = {info['t']: cn_name for cn_name, info in _CN_ADR_MAP.items()}

# HK ticker → US ADR ticker (for inputs like 0700.HK, 9988.HK)
_HK_TO_ADR = {
    '0700.HK': 'TCEHY', '700.HK': 'TCEHY',
    '9988.HK': 'BABA', '9618.HK': 'JD',
    '9999.HK': 'NTES', '9888.HK': 'BIDU',
    '3690.HK': 'MPNGY', '9626.HK': 'BILI',
    '1810.HK': 'XIACY',
    '1024.HK': 'KUASF', '01024.HK': 'KUASF',
}

def _resolve_sa_ticker(company_name, detect_ticker):
    """
    Resolve the correct Seeking Alpha ticker for transcript search.
    Returns (ticker, reporting_currency).
    """
    # Highest priority: company_name itself looks like a US ticker (TSM, AAPL, ...).
    # detect_ticker may have been polluted by EastMoney fuzzy match (TSM → 600091),
    # so trust the original input over the detected ticker for pure-English input.
    if company_name and re.match(r'^[A-Z]{1,6}$', company_name):
        for cn_name, info in _CN_ADR_MAP.items():
            if info['t'] == company_name:
                return company_name, info['c']
        return company_name, 'USD'

    # If detect_ticker is already a valid US ticker (alphabetic), use it
    if detect_ticker and re.match(r'^[A-Z]{1,6}$', detect_ticker):
        # Check if we have currency info
        for cn_name, info in _CN_ADR_MAP.items():
            if info['t'] == detect_ticker:
                return detect_ticker, info['c']
        return detect_ticker, 'USD'
    
    # Check if detect_ticker is a HK stock code → map to US ADR
    if detect_ticker and detect_ticker in _HK_TO_ADR:
        adr = _HK_TO_ADR[detect_ticker]
        for cn_name, info in _CN_ADR_MAP.items():
            if info['t'] == adr:
                print(f"    [Ticker] {detect_ticker} → {adr} (HK→ADR map, {info['c']})")
                return adr, info['c']
        return adr, 'RMB'
    
    # Check hardcoded Chinese name map
    for cn_name, info in _CN_ADR_MAP.items():
        if cn_name in company_name:
            print(f"    [Ticker] {company_name} → {info['t']} (ADR map, {info['c']})")
            return info['t'], info['c']
    
    print(f"    [Ticker] Could not resolve US ticker for {company_name}, using {detect_ticker or company_name}")
    return detect_ticker or company_name, 'USD'


def _discover_minimax():
    headers = {
        'accept': 'application/json, text/plain, */*',
        'referer': 'https://ir.minimax.io/',
        'user-agent': 'Mozilla/5.0'
    }
    target_quarter = ''
    try:
        resp = requests.get('https://ir.minimax.io/nezha/en/news?page=1', headers=headers, timeout=15)
        if resp.status_code == 200:
            items = resp.json().get('data', [])
            for item in items:
                title = item.get('title', '')
                qm = re.search(r'(Q\d|Full\s*Year)\s+(\d{4})', title, re.IGNORECASE)
                if qm:
                    if 'full' in qm.group(1).lower():
                        target_quarter = f"FY {qm.group(2)}"
                    else:
                        target_quarter = f"{qm.group(1).upper()} {qm.group(2)}"
                    return target_quarter, True, [{'title': title, 'date': item.get('publishDate', '')[:10], 'slug': item.get('slug'), 'is_minimax': True, 'attributes': {'publishOn': item.get('publishDate', '')[:10], 'title': title}}]
    except Exception as e:
        print(f"    [Minimax IR] API check failed: {e}")
    return '', False, []


def _discover_euroland(companycode):
    headers = {
        'accept': 'application/json',
        'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
        'origin': 'https://asia.tools.euroland.com',
        'referer': f'https://asia.tools.euroland.com/tools/pressreleases/?companycode={companycode}&lang=zh-tw',
        'user-agent': 'Mozilla/5.0'
    }
    data = f'strDateFrom=19%2F12%2F2025&strDateTo=&typeFilter=&orderBy=0&pageIndex=0&pageJummp=10&hasTypeFilter=false&searchPhrase=&companyCode={companycode}&onlyInsiderInfo=false&lang=zh-TW&v=&alwaysIncludeInsiders=false&strYears='
    try:
        resp = requests.post('https://asia.tools.euroland.com/tools/Pressreleases/Main/GetNews/', headers=headers, data=data, timeout=15)
        if resp.status_code == 200:
            js = resp.json()
            items = js.get('News', [])
            attachments = js.get('Attachments', [])
            for item in items:
                title = item.get('title', '')
                if '業績' in title or 'Financial Results' in title:
                    pr_id = item.get('ID')
                    at_id = None
                    filename = None
                    for at in attachments:
                        if at.get('prID') == pr_id:
                            at_id = at.get('atID')
                            filename = at.get('filename')
                            break
                    term = 'FY '
                    qm = re.search(r'(20\d{2})', title)
                    year = qm.group(1) if qm else '2026'
                    if any(x in title for x in ['第一季度', '一季度', 'Q1']):
                        term = 'Q1 '
                    elif any(x in title for x in ['第二季度', '半年度', '中期', 'Q2']):
                        term = 'Q2 '
                    elif any(x in title for x in ['第三季度', '三季度', 'Q3']):
                        term = 'Q3 '
                    target_quarter = f"{term}{year}"
                    download_url = f"https://ea-cdn.eurolandir.com/press-releases-attachments./{at_id}/{filename}" if at_id else ""
                    return target_quarter, True, [{'title': title, 'date': item.get('formatedDate', '')[:10], 'download_url': download_url, 'is_euroland': True, 'attributes': {'publishOn': item.get('formatedDate', ''), 'title': title}}]
    except Exception as e:
        print(f"    [Euroland IR] API check failed: {e}")
    return '', False, []

# ============================================================
# Step 0: Quarter Discovery — determine latest earnings quarter
# ============================================================
def discover_latest_quarter(ticker, company_name):
    """
    Determine the latest earnings quarter by checking SA API + IR page.
    Returns (target_quarter, sa_transcript_available, sa_items).
    
    target_quarter: e.g. "Q4 2025"
    sa_transcript_available: True if SA has the transcript for target_quarter
    sa_items: raw SA API items for reuse by fetch_transcript()
    """
    print(f"  [Step 0] Discovering latest quarter for {ticker}...")
    
    if ticker.upper() == '0100.HK':
        return _discover_minimax()
    elif ticker.upper() == '2513.HK':
        return _discover_euroland('hk-2513')
    

    headers = {
        'x-rapidapi-host': 'seeking-alpha.p.rapidapi.com',
        'x-rapidapi-key': RAPIDAPI_KEY,
    }
    
    sa_items = []
    sa_quarters = []  # [(quarter_str, title, date, is_transcript), ...]
    
    # 1. Check SA API for all recent items
    if RAPIDAPI_KEY:
        try:
            resp = requests.get(
                'https://seeking-alpha.p.rapidapi.com/transcripts/v2/list',
                params={'id': ticker.lower(), 'size': '10'},
                headers=headers, timeout=20
            )
            resp.raise_for_status()
            sa_items = resp.json().get('data', [])
            
            for item in sa_items:
                attrs = item.get('attributes', {})
                title = attrs.get('title', '')
                pub_date = attrs.get('publishOn', '')[:10]
                qm = re.search(r'Q(\d)\s+(\d{4})', title)
                if qm:
                    q_str = f"Q{qm.group(1)} {qm.group(2)}"
                    is_transcript = 'transcript' in title.lower()
                    sa_quarters.append((q_str, title, pub_date, is_transcript))
            
            if sa_quarters:
                print(f"    [SA] Found {len(sa_quarters)} items, quarters: {list(set(q[0] for q in sa_quarters))}")
        except Exception as e:
            print(f"    [SA] API check failed: {e}")
    
    # 2. Determine the latest quarter from SA data
    # SA items are ordered by publish date (newest first)
    # The latest quarter is whatever appears first, regardless of type
    latest_from_sa = None
    transcript_available = False
    
    if sa_quarters:
        latest_from_sa = sa_quarters[0][0]  # e.g. "Q4 2025"
        # Check if transcript (not just presentation) exists for this quarter
        transcript_available = any(
            q[0] == latest_from_sa and q[3]  # q[3] = is_transcript
            for q in sa_quarters
        )
        
        if transcript_available:
            print(f"    ✓ Latest quarter: {latest_from_sa} (transcript available on SA)")
        else:
            print(f"    ⚠ Latest quarter: {latest_from_sa} (presentation only, transcript NOT yet on SA)")
            # Check if there's a transcript for an older quarter
            older_transcripts = [q for q in sa_quarters if q[3]]
            if older_transcripts:
                print(f"    ℹ Latest available transcript: {older_transcripts[0][0]} ({older_transcripts[0][2]})")
    
    # 3. Fallback: use Tavily to discover if SA check failed
    if not latest_from_sa and TAVILY_API_KEY:
        print(f"    [Tavily] Searching for latest quarter...")
        try:
            cn_name = _ADR_TO_CN.get(ticker, company_name)
            query = f"{cn_name} OR {company_name} latest quarterly earnings results 2025 2026"
            tavily_resp = requests.post(
                'https://api.tavily.com/search',
                json={'api_key': TAVILY_API_KEY, 'query': query,
                      'max_results': 3, 'search_depth': 'basic'},
                timeout=15
            )
            tavily_resp.raise_for_status()
            answer = tavily_resp.json().get('answer', '') or ''
            # Try to extract quarter from answer + results
            search_text = answer
            for r in tavily_resp.json().get('results', [])[:3]:
                search_text += ' ' + r.get('title', '') + ' ' + r.get('content', '')[:200]
            qm = re.search(r'Q(\d)\s+(\d{4})', search_text)
            if qm:
                latest_from_sa = f"Q{qm.group(1)} {qm.group(2)}"
                print(f"    ✓ Tavily suggests latest quarter: {latest_from_sa}")
        except Exception as e:
            print(f"    [Tavily] Quarter discovery failed: {e}")
    
    target_quarter = latest_from_sa or ''
    print(f"  [Step 0] Target quarter: {target_quarter or 'unknown'}, "
          f"SA transcript: {'yes' if transcript_available else 'no'}")
    
    return target_quarter, transcript_available, sa_items


SA_PREMIUM_COOKIE = os.environ.get("SA_PREMIUM_COOKIE", "")


def _fetch_sa_premium_html(transcript_id):
    """Fetch full transcript HTML directly from SA website using Premium cookies.

    Requires SA_PREMIUM_COOKIE env var. The sa-mpw-data header unlocks paywalled content.
    Cookie _px3 expires in ~15 min, so this only works shortly after browser export.
    """
    if not SA_PREMIUM_COOKIE:
        return None
    cookies = {}
    for pair in SA_PREMIUM_COOKIE.split(";"):
        pair = pair.strip()
        if "=" in pair:
            k, v = pair.split("=", 1)
            cookies[k.strip()] = v.strip()
    article_path = f"/article/{transcript_id}"
    try:
        resp = requests.get(
            f"https://seekingalpha.com/api/v3/articles/{transcript_id}",
            params={"include": "author,primaryTickers,secondaryTickers", "lang": "en"},
            headers={
                "accept": "application/json",
                "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
                "referer": f"https://seekingalpha.com{article_path}",
                "sa-mpw-data": f'{{"url":"{article_path}","query":"","page_key":"auto"}}',
                "sec-fetch-dest": "empty",
                "sec-fetch-mode": "cors",
                "sec-fetch-site": "same-origin",
            },
            cookies=cookies,
            timeout=30,
        )
        if resp.status_code != 200:
            print(f"    [SA Premium] returned {resp.status_code} (cookie likely expired)")
            return None
        html = resp.json().get("data", {}).get("attributes", {}).get("content", "")
        if html and len(html) >= 10000:
            print(f"    [SA Premium] got {len(html)} chars (full transcript)")
            return html
        print(f"    [SA Premium] content too short ({len(html)} chars), skipping")
        return None
    except Exception as e:
        print(f"    [SA Premium] failed: {e}")
        return None


def _parse_sa_html(soup):
    """Parse SA transcript HTML (BeautifulSoup object) into speaker-tagged plain text."""
    parts = []
    speaker = None
    for el in soup.find_all(['p', 'h2', 'h3', 'strong']):
        txt = el.get_text(strip=True)
        if not txt:
            continue
        if el.name == 'strong' or (el.name == 'p' and el.find('strong')):
            s = el.find('strong') if el.name == 'p' else el
            if s and len(s.get_text(strip=True)) < 100:
                speaker = s.get_text(strip=True)
                continue
        if el.name in ['h2', 'h3']:
            parts.append(f"\n=== {txt} ===\n")
            continue
        if speaker:
            parts.append(f"\n{speaker}: {txt}")
            speaker = None
        else:
            parts.append(txt)
    return '\n'.join(parts)


# ============================================================
# Step 1: Fetch Transcript (Seeking Alpha)
# ============================================================
def fetch_transcript(ticker, target_quarter='', sa_items=None):
    """Fetch transcript from SA, prioritizing target_quarter if specified.
    
    Args:
        ticker: SA ticker symbol
        target_quarter: e.g. "Q4 2025" — if set, only return transcript matching this quarter
        sa_items: pre-fetched SA API items from discover_latest_quarter() to avoid duplicate API call
    """
    if sa_items and len(sa_items) > 0:
        first = sa_items[0]
        if first.get('is_minimax') or first.get('is_euroland'):
            cn_map = {'0100.HK': 'MiniMax', '2513.HK': '智谱AI'}
            name = cn_map.get(ticker.upper(), ticker)
            print(f"    [Custom IR] Fetching {name} '{target_quarter}' transcript proxy via Tavily...")
            
            if TAVILY_API_KEY:
                query = f'"{name}" "业绩会" OR "电话会议" OR "会议纪要" "{target_quarter}"'
                try:
                    tavily_resp = requests.post(
                        'https://api.tavily.com/search',
                        json={'api_key': TAVILY_API_KEY, 'query': query,
                              'max_results': 5, 'search_depth': 'advanced', 'include_answer': True},
                        timeout=20
                    )
                    tavily_resp.raise_for_status()
                    answer = tavily_resp.json().get('answer', '')
                    content = "【TAVILY SEARCH PROXY TRANSCRIPT】\n本部分为网页搜索合成的管理层问答与战略视角纪要：\n" + answer + "\n\n"
                    for r in tavily_resp.json().get('results', []):
                        content += f"Source: {r.get('title')}\n{r.get('content')}\n\n"
                    
                    print(f"    [Custom IR] Fetched {len(content)} chars via Tavily proxy.")
                    return {
                        'title': first.get('title', ''), 
                        'date': first.get('date', ''), 
                        'quarter': target_quarter, 
                        'content': content, 
                        'id': f"proxy_{ticker}"
                    }
                except Exception as e:
                    print(f"    [Custom IR] Tavily search proxy failed: {e}")
                    
            print("    [Custom IR] Returning empty proxy transcript.")
            return {
                'title': first.get('title', ''), 
                'date': first.get('date', ''), 
                'quarter': target_quarter, 
                'content': "【系统提示】没有找到该公司的详细文字实录或代理搜索失败。", 
                'id': f"proxy_{ticker}"
            }

    headers = {
        'x-rapidapi-host': 'seeking-alpha.p.rapidapi.com',
        'x-rapidapi-key': RAPIDAPI_KEY,
    }
    
    # Use pre-fetched items if available, otherwise fetch
    if sa_items is not None:
        items = sa_items
        print(f"    [SA] Using pre-fetched {len(items)} items for {ticker}")
    else:
        print(f"    [SA] Searching transcripts for {ticker}...")
        try:
            resp = requests.get(
                'https://seeking-alpha.p.rapidapi.com/transcripts/v2/list',
                params={'id': ticker.lower(), 'size': '10'},
                headers=headers, timeout=20
            )
            resp.raise_for_status()
            items = resp.json().get('data', [])
        except Exception as e:
            print(f"    x Transcript list failed: {e}")
            return None
    
    if not items:
        return None
    
    # Filter to actual transcripts (not presentations)
    transcript_items = [
        item for item in items
        if 'transcript' in item.get('attributes', {}).get('title', '').lower()
    ]
    
    latest = None
    
    if target_quarter:
        # Priority: find transcript matching target_quarter
        for item in transcript_items:
            title = item.get('attributes', {}).get('title', '')
            qm = re.search(r'Q(\d)\s+(\d{4})', title)
            if qm and f"Q{qm.group(1)} {qm.group(2)}" == target_quarter:
                latest = item
                print(f"    ✓ Found transcript matching target {target_quarter}")
                break
        
        if not latest:
            # Target quarter transcript not available
            print(f"    ⚠ No transcript for {target_quarter} on SA yet")
            
            # Check: is there an older transcript available?
            if transcript_items:
                older = transcript_items[0]
                older_title = older.get('attributes', {}).get('title', '')
                older_qm = re.search(r'Q(\d)\s+(\d{4})', older_title)
                older_q = f"Q{older_qm.group(1)} {older_qm.group(2)}" if older_qm else '?'
                print(f"    ℹ Latest available transcript is {older_q}: {older_title}")
                print(f"    ❌ Skipping — would mix {older_q} transcript with {target_quarter} IR data")
            return None
    else:
        # No target quarter specified — fallback to original behavior
        if transcript_items:
            latest = transcript_items[0]
        elif items:
            latest = items[0]
        else:
            return None
    
    attrs = latest.get('attributes', {})
    title = attrs.get('title', '')
    publish_date = attrs.get('publishOn', '')[:10]
    tid = latest['id']
    
    qm = re.search(r'Q(\d)\s+(\d{4})', title)
    quarter = f"Q{qm.group(1)} {qm.group(2)}" if qm else ""
    
    print(f"    OK: {title} ({publish_date})")
    print(f"    [SA] Fetching content (id={tid})...")

    # Priority 1: SA Premium cookie-based API
    premium_html = _fetch_sa_premium_html(tid)
    if premium_html and len(premium_html) >= 10000:
        soup = BeautifulSoup(premium_html, 'html.parser')
        text = _parse_sa_html(soup)
        if len(text) >= 5000:
            print(f"    ✓ Using SA Premium API transcript ({len(text)} chars)")
            return {'title': title, 'date': publish_date, 'quarter': quarter, 'content': text, 'id': tid}

    # Priority 2: RapidAPI (often truncated)
    html = ''
    try:
        resp = requests.get(
            'https://seeking-alpha.p.rapidapi.com/transcripts/v2/get-details',
            params={'id': tid}, headers=headers, timeout=30
        )
        resp.raise_for_status()
        html = resp.json().get('data', {}).get('attributes', {}).get('content', '')
    except Exception as e:
        print(f"    x RapidAPI fetch failed: {e}")

    if not html:
        return None

    soup = BeautifulSoup(html, 'html.parser')
    text = _parse_sa_html(soup)
    print(f"    OK: {len(text)} chars (RapidAPI — may be truncated)")
    return {'title': title, 'date': publish_date, 'quarter': quarter, 'content': text, 'id': tid}


# ============================================================
# Step 2: IR Direct Scraper (大厂专用)
# ============================================================
_IR_CONFIGS = {
    'BABA': {
        'listing_url': 'https://www.alibabagroup.com/en-US/ir-financial-reports-quarterly-results',
        'doc_pattern': r'alibabagroup\.com/en-US/document-(\d+)',
        'pdf_domain': 'https://data.alibabagroup.com',
        'type': 'baba',
    },
    'PDD': {
        'listing_url': 'https://investor.pddholdings.com/financial-information/quarterly-results',
        'doc_pattern': r'static-files/([a-f0-9-]+)',
        'pdf_base': 'https://investor.pddholdings.com/static-files/',
        'type': 'nasdaq_ir_cffi',
    },
    'NTES': {
        'listing_url': 'https://ir.netease.com/zh-hans/financial-information/quarterly-results',
        'doc_pattern': r'static-files/([a-f0-9-]+)',
        'pdf_base': 'https://ir.netease.com/static-files/',
        'type': 'nasdaq_ir_cffi',
    },
    'JD': {
        'listing_url': 'https://ir.jd.com/zh-hans/quarterly-results',
        'doc_pattern': r'system/files-encrypted/[^"\'>\s]+\.pdf',
        'pdf_base': 'https://ir.jd.com/',
        'type': 'nasdaq_ir_cffi',
    },
    'MPNGY': {
        'listing_url': 'https://www.meituan.com/investor-relations',
        'pdf_pattern': r'media-meituan\.todayir\.com/[^"\'>\s]+\.pdf',
        'type': 'meituan',
    },
    'BILI': {
        'listing_url': 'https://ir.bilibili.com/cn/financial-information/#quarterly-results',
        'prefix': 'https://ir.bilibili.com',
        'type': 'bilibili',
    },
    'TCEHY': {
        'listing_url': 'https://www.tencent.com/zh-cn/investors/quarter-result.html',
        'type': 'tencent',
    },
    'BIDU': {
        'listing_url': 'https://baidu.gcs-web.com/press-releases',
        'detail_prefix': 'https://baidu.gcs-web.com',
        'type': 'baidu_gcs',
    },
    'KUASF': {
        'listing_url': 'https://ir.kuaishou.com/zh-hans/corporate-filings/quarterly-results',
        'doc_pattern': r'system/files-encrypted/[^"\'\'\>\s]+\.pdf',
        'pdf_base': 'https://ir.kuaishou.com/',
        'type': 'nasdaq_ir_cffi',
    },
}


def fetch_ir_press_release(ticker):
    """
    Fetch full press release text directly from company IR page.
    Returns (pr_text, pr_url) or (None, None).
    """
    config = _IR_CONFIGS.get(ticker)
    if not config:
        return None, None
    
    print(f"    [IR] Fetching from {ticker} IR page...")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    }
    
    try:
        # Step 1: Fetch listing page (use cloudscraper for CF-protected sites)
        if config['type'] == 'meituan':
            try:
                import cloudscraper
                scraper = cloudscraper.create_scraper()
                resp = scraper.get(config['listing_url'], timeout=20)
            except ImportError:
                resp = requests.get(config['listing_url'], headers=headers, timeout=20)
        elif config['type'] in ('baidu_gcs', 'nasdaq_ir_cffi'):
            # These sites are slow/require curl_cffi TLS fingerprint
            try:
                from curl_cffi import requests as cffi_requests
                _sess = cffi_requests.Session(impersonate='chrome120')
                resp = _sess.get(config['listing_url'], timeout=60)
            except ImportError:
                resp = requests.get(config['listing_url'], headers=headers, timeout=60)
        else:
            resp = requests.get(config['listing_url'], headers=headers, timeout=20)
        resp.raise_for_status()
        html = resp.text
        
        pdf_url = None
        
        if config['type'] == 'baba':
            # BABA: PDF URLs are directly in listing page JSON/HTML
            # Find all ecms-files PDF URLs (press releases)
            pdf_matches = re.findall(
                r'ecms-files/[^"\'\\>\s]+\.pdf',
                html
            )
            if pdf_matches:
                # Filter for earnings/results PDFs, skip presentation slides
                for pdf_path in pdf_matches:
                    decoded = requests.utils.unquote(pdf_path)
                    if any(kw in decoded.lower() for kw in ['announces', 'results', 'earnings']):
                        pdf_url = f'https://data.alibabagroup.com/{pdf_path}'
                        print(f"    [IR] Found earnings PDF: ...{decoded[-60:]}")
                        break
                if not pdf_url and pdf_matches:
                    # Fallback: first PDF if no keyword match
                    pdf_url = f'https://data.alibabagroup.com/{pdf_matches[0]}'
                    print(f"    [IR] Using first PDF: ...{pdf_matches[0][-60:]}")
            else:
                print(f"    [IR] No PDF links found on listing page")
                return None, None
        
        elif config['type'] == 'meituan':
            # Meituan: listing page has PDF URLs, but PDFs are CF-protected
            # Extract PR URL for reference, text will come from Tavily fallback
            pdf_matches = re.findall(config['pdf_pattern'], html)
            if pdf_matches:
                # Deduplicate and sort by timestamp (newest first)
                unique_pdfs = list(dict.fromkeys(pdf_matches))
                def _ts(u):
                    m = re.search(r'todayir\.com/(\d{8,})', u)
                    return m.group(1) if m else '0'
                unique_pdfs.sort(key=_ts, reverse=True)
                latest = unique_pdfs[0]
                pdf_url = f'https://{latest}'
                print(f"    [IR] Meituan latest PR: ts={_ts(latest)[:8]} ...{latest[-40:]}")
                print(f"    [IR] PDF is CF-protected, will use Tavily for text")
                return None, pdf_url
            else:
                print(f"    [IR] No PDF links found on Meituan page")
                return None, None
        
        elif config['type'] == 'bilibili':
            # Bilibili: static HTML, all PDF links directly available, no anti-scraping
            # Pattern: /media/{hash}/{Nq}YY-业绩报告.pdf (e.g. 4q25-业绩报告.pdf)
            import html as html_lib
            # Unescape HTML entities (B站用 &#x4E1A; 格式编码中文)
            clean_html = html_lib.unescape(html)
            # Find all 业绩报告 PDFs
            pr_pattern = r'href=["\'](/media/[^"\']+(\d)q(\d{2})-[^"\']*.pdf)["\']'
            pr_matches = re.findall(pr_pattern, clean_html)
            if pr_matches:
                # Sort by year desc then quarter desc (e.g. 4q25 > 3q25 > 4q24)
                pr_matches.sort(key=lambda m: (int(m[2]), int(m[1])), reverse=True)
                latest_path = pr_matches[0][0]
                pdf_url = f"{config['prefix']}{latest_path}"
                qtr = f"{pr_matches[0][1]}Q{pr_matches[0][2]}"
                print(f"    [IR] Bilibili latest PR: {qtr} → ...{latest_path[-40:]}")
            else:
                # Fallback: find any 业绩报告 link
                fb = re.findall(r'href=["\'](/media/[^"\']+-(?:业绩报告|earnings)[^"\']*.pdf)', clean_html, re.I)
                if fb:
                    pdf_url = f"{config['prefix']}{fb[0]}"
                    print(f"    [IR] Bilibili fallback PR: ...{fb[0][-40:]}")
                else:
                    print(f"    [IR] No 业绩报告 PDF found on Bilibili page")
                    return None, None
        
        elif config['type'] == 'tencent':
            # Tencent: static HTML, 3 PDFs per quarter (news/presentation/HKEX)
            # All links are absolute URLs on static.www.tencent.com
            # Note: <a> tags have line breaks inside, so use re.S for multiline matching
            pdf_a_pat = r'<a\s+[^>]*href=["\']([^"\']*\.pdf)["\'][^>]*>([\s\S]*?)</a>'
            pdf_a_matches = re.findall(pdf_a_pat, html)
            if pdf_a_matches:
                # First match with "业绩新闻" label = latest quarter's earnings PR
                for href, label in pdf_a_matches:
                    if '业绩新闻' in label or '新闻稿' in label or '业绩' in label:
                        pdf_url = href
                        print(f"    [IR] Tencent latest PR: [{label.strip()}] ...{href[-40:]}")
                        break
                # Fallback: just take first PDF
                if not pdf_url:
                    pdf_url = pdf_a_matches[0][0]
                    print(f"    [IR] Tencent (fallback): ...{pdf_url[-40:]}")
            else:
                print(f"    [IR] No PDF links found on Tencent page")
                return None, None
        
        elif config['type'] == 'baidu_gcs':
            # Baidu GCS-Web: 2-hop HTML scraper (no PDF)
            # Step A: Find latest earnings link from listing page
            import html as html_lib
            news_links = re.findall(r'href=["\']([^"\']*/news-release-details/[^"\']*/)["\']', html)
            if not news_links:
                news_links = re.findall(r'href=["\']([^"\']*/news-release-details/[^"\']*)["\']', html)
            earnings_kw = ['result', 'quarter', 'annual', 'fiscal']
            earnings_links = [l for l in news_links if any(k in l.lower() for k in earnings_kw)]
            if not earnings_links:
                print(f"    [IR] No earnings links found on Baidu listing")
                return None, None
            
            latest_path = earnings_links[0]
            detail_url = f"{config['detail_prefix']}{latest_path}" if latest_path.startswith('/') else latest_path
            print(f"    [IR] Baidu latest: ...{detail_url.split('/')[-1][:50]}")
            
            # Step B: Fetch detail page and extract <p> text
            try:
                from curl_cffi import requests as cffi_requests
                _sess = cffi_requests.Session(impersonate='chrome120')
                detail_resp = _sess.get(detail_url, timeout=60)
            except ImportError:
                detail_resp = requests.get(detail_url, headers=headers, timeout=60)
            
            if detail_resp.status_code != 200:
                print(f"    [IR] Baidu detail page: {detail_resp.status_code}")
                return None, None
            
            p_tags = re.findall(r'<p[^>]*>([\s\S]*?)</p>', detail_resp.text)
            texts = []
            for p in p_tags:
                t = re.sub(r'<[^>]+>', '', p)
                t = html_lib.unescape(t).strip()
                if t and len(t) > 10:
                    texts.append(t)
            
            if texts:
                pr_text = '\n'.join(texts)
                print(f"    OK: IR press release {len(pr_text)} chars ({len(texts)} paragraphs)")
                return pr_text, detail_url
            else:
                print(f"    [IR] No text extracted from Baidu detail page")
                return None, detail_url
        
        elif config['type'] in ('nasdaq_ir', 'nasdaq_ir_cffi'):
            # NASDAQ IR platform: static-files or files-encrypted links
            matches = re.findall(config['doc_pattern'], html)
            if matches:
                # Deduplicate
                matches = list(dict.fromkeys(matches))
                # Prefer earnings PDFs (filter by keyword)
                # 'hkex' and 'eps' added for HK-listed companies like Kuaishou
                pr_keywords = ['announces', 'results', 'earnings', 'hkex', 'eps']
                for m in matches:
                    decoded = requests.utils.unquote(m)
                    if any(kw in decoded.lower() for kw in pr_keywords):
                        pdf_url = m if m.startswith('http') else f"{config['pdf_base']}{m}"
                        print(f"    [IR] Found PDF: ...{decoded[-60:]}")
                        break
                # Fallback: first match
                if not pdf_url:
                    m = matches[0]
                    pdf_url = m if m.startswith('http') else f"{config['pdf_base']}{m}"
                    print(f"    [IR] Found PDF (fallback): ...{requests.utils.unquote(m)[-60:]}")
        
        if not pdf_url:
            print(f"    [IR] Could not find PDF URL")
            return None, None
        
        # Step 2: Download PDF (use curl_cffi for slow/TLS-sensitive sites)
        print(f"    [IR] Downloading PDF...")
        if config['type'] == 'nasdaq_ir_cffi':
            try:
                from curl_cffi import requests as cffi_requests
                _dl = cffi_requests.Session(impersonate='chrome120')
                pdf_resp = _dl.get(pdf_url, timeout=60)
            except ImportError:
                pdf_resp = requests.get(pdf_url, headers=headers, timeout=60)
        else:
            pdf_resp = requests.get(pdf_url, headers=headers, timeout=30)
        pdf_resp.raise_for_status()
        
        if len(pdf_resp.content) < 1000:
            print(f"    [IR] PDF too small ({len(pdf_resp.content)} bytes), likely error")
            return None, None
        
        # Step 3: Extract text from PDF
        import pdfplumber
        import io
        
        with pdfplumber.open(io.BytesIO(pdf_resp.content)) as pdf:
            text_parts = []
            for i, page in enumerate(pdf.pages[:20]):  # First 20 pages
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
            full_text = '\n\n'.join(text_parts)
        
        if len(full_text) < 500:
            print(f"    [IR] Extracted text too short ({len(full_text)} chars)")
            return None, None
        
        print(f"    OK: IR press release {len(full_text)} chars from PDF ({len(pdf.pages)} pages)")
        return full_text, pdf_url
        
    except Exception as e:
        print(f"    [IR] Failed: {e}")
        return None, None


# ============================================================
# Step 2b: Fetch Press Release (IR Scraper → Tavily)
# ============================================================
def fetch_press_release(company_name, ticker, quarter, sa_items=None):
    """Fetch press release text. Returns (pr_text, pr_url) or (None, None)."""
    print(f"    [PR] Fetching press release for {ticker}...")
    pr_content = ""
    pr_url = ""

    # Source 0: Custom APIs from Step 0
    if sa_items and len(sa_items) > 0:
        first = sa_items[0]
        if first.get('is_minimax'):
            slug = first.get('slug')
            if slug:
                url = f"https://www.minimax.io/news/{slug}"
                print(f"    [IR] Scraping Minimax PR from {url}...")
                try:
                    resp = requests.get(url, timeout=15)
                    resp.raise_for_status()
                    html = resp.text
                    soup = BeautifulSoup(html, 'html.parser')
                    main_content = soup.find('main')
                    if main_content:
                        pr_content = main_content.get_text(separator='\n', strip=True)
                        pr_url = url
                except Exception as e:
                    print(f"    [IR] Minimax fetch failed: {e}")
        elif first.get('is_euroland'):
            pdf_url = first.get('download_url')
            if pdf_url:
                print(f"    [IR] Downloading Euroland PDF from {pdf_url}...")
                try:
                    import pdfplumber
                    import io
                    resp = requests.get(pdf_url, timeout=20)
                    resp.raise_for_status()
                    with pdfplumber.open(io.BytesIO(resp.content)) as pdf:
                        text_parts = []
                        for page in pdf.pages:
                            text = page.extract_text()
                            if text:
                                text_parts.append(text)
                        pr_content = '\n'.join(text_parts)
                        pr_url = pdf_url
                except Exception as e:
                    print(f"    [IR] Euroland PDF fetch failed: {e}")

    # Source 1 (Priority): Direct IR page scraper (大厂专用 — 不可动！)
    if not pr_content and ticker in _IR_CONFIGS:
        ir_text, ir_url = fetch_ir_press_release(ticker)
        if ir_text:
            pr_content = ir_text
        if ir_url:
            pr_url = ir_url

    # Source 2 (Fallback): Tavily press release search
    if not pr_content and TAVILY_API_KEY:
        print(f"    [Tavily] Searching press release...")
        cn_name = _ADR_TO_CN.get(ticker, company_name)
        queries = [
            f'{company_name} {ticker} {quarter} earnings results revenue net income EPS',
        ]
        if cn_name != company_name:
            queries.append(f'{cn_name} {quarter or "最新"} 财报 业绩公告 收入 利润')
        else:
            queries.append(f'{company_name} {quarter or "latest"} quarterly results press release')

        for q_idx, query in enumerate(queries):
            if pr_content:
                break
            try:
                tavily_resp = requests.post(
                    'https://api.tavily.com/search',
                    json={
                        'api_key': TAVILY_API_KEY,
                        'query': query,
                        'max_results': 5, 'include_answer': True, 'search_depth': 'advanced',
                    }, timeout=30
                )
                tavily_resp.raise_for_status()
                tavily_data = tavily_resp.json()

                pr_content = tavily_data.get('answer', '')
                for r in tavily_data.get('results', [])[:3]:
                    pr_content += f"\n\n--- {r.get('url', '')} ---\n{r.get('content', '')}"
                    url = r.get('url', '')
                    if not pr_url and any(k in url.lower() for k in ['investor', 'earnings', 'press', 'newswire', 'businesswire', 'prnewswire']):
                        pr_url = url

                if not pr_url and tavily_data.get('results'):
                    pr_url = tavily_data['results'][0].get('url', '')

                if pr_content:
                    print(f"    OK: Press release {len(pr_content)} chars (query #{q_idx+1})")
            except Exception as e:
                print(f"    Warning: Tavily query #{q_idx+1} failed: {e}")

    if pr_content:
        print(f"    ✓ PR content: {len(pr_content)} chars")
        return pr_content, pr_url
    print(f"    ⚠ No press release found")
    return None, None


def run_earnings_pipeline(companies, query="", output_dir=None, transcript_file=None, press_release_file=None, override_quarter=None):
    """Data-only pipeline: fetch transcript + press release, save to files. No LLM calls."""
    if not output_dir:
        output_dir = os.path.join(SCRIPT_DIR, "..", "data", "earnings_results")
    os.makedirs(output_dir, exist_ok=True)

    print("=" * 60)
    print("QUARTERLY EARNINGS DATA COLLECTOR (no LLM)")
    print(f"  Companies: {companies}")
    if transcript_file:
        print(f"  Manual transcript: {transcript_file}")
    if press_release_file:
        print(f"  Manual press release: {press_release_file}")
    print("=" * 60)

    for name in companies:
        print(f"\n{'=' * 50}")
        print(f"  {name}")
        print(f"{'=' * 50}")

        company = detect_data_source(name)
        detect_ticker = company.get('ticker', '') or name.upper()

        sa_ticker, reporting_currency = _resolve_sa_ticker(name, detect_ticker)
        ticker = sa_ticker
        print(f"  Ticker: {ticker} (detect: {detect_ticker}, currency: {reporting_currency})")

        # Step 0: Quarter Discovery
        print(f"\n  [Step 0] Quarter Discovery...")
        target_quarter, sa_has_transcript, sa_items = discover_latest_quarter(sa_ticker, name)

        if override_quarter:
            if target_quarter and target_quarter != override_quarter:
                print(f"  [Step 0] Quarter override: SA={target_quarter} → user={override_quarter}")
            else:
                print(f"  [Step 0] Quarter override: {override_quarter}")
            target_quarter = override_quarter
            sa_has_transcript = False

        print(f"  [Step 0] Target quarter: {target_quarter}, SA transcript: {'yes' if sa_has_transcript else 'no'}")

        # Step 0.5: CDP Transcript Gate — 必须先通过 CDP MCP 获取完整 SA transcript
        # Agent 应在调用本脚本之前，用 chrome-devtools MCP 导出完整 transcript 到:
        #   {output_dir}/{TICKER}_transcript_full.txt
        # 本步骤检查该文件是否存在且内容充分（>5000 chars）
        CDP_TRANSCRIPT_MIN_CHARS = 5000
        cdp_transcript_path = os.path.join(output_dir, f"{ticker}_transcript_full.txt")
        cdp_transcript_found = False

        if os.path.exists(cdp_transcript_path):
            with open(cdp_transcript_path, 'r', encoding='utf-8') as f:
                cdp_content = f.read()
            if len(cdp_content) >= CDP_TRANSCRIPT_MIN_CHARS:
                cdp_transcript_found = True
                print(f"  ✓ CDP transcript found: {cdp_transcript_path} ({len(cdp_content):,} chars)")
            else:
                print(f"  ⚠ CDP transcript too short ({len(cdp_content):,} chars < {CDP_TRANSCRIPT_MIN_CHARS}), treating as missing")

        if not cdp_transcript_found and not transcript_file:
            print(f"\n  🚨 BLOCKED: 完整 SA transcript 未找到！")
            print(f"  请先通过 CDP MCP 获取完整 Seeking Alpha transcript 并保存到:")
            print(f"    {cdp_transcript_path}")
            print(f"  或使用 --transcript-file 参数手动提供 transcript 文件。")
            print(f"  RapidAPI 截断版本（~2000 chars）不足以支撑高质量财报分析。")
            print(f"  ❌ 脚本已中止。请完成 CDP 获取后重新运行。\n")
            continue

        # Step 1: Fetch Transcript
        print(f"\n  [Step 1] Transcript...")
        transcript = None

        # Priority 1: CDP MCP pre-fetched full transcript
        if cdp_transcript_found:
            with open(cdp_transcript_path, 'r', encoding='utf-8') as f:
                content = f.read()
            transcript = {
                'title': f'{name} {target_quarter} Earnings Call (CDP full transcript)',
                'date': datetime.now().strftime('%Y-%m-%d'),
                'quarter': target_quarter,
                'content': content,
            }
            print(f"  ✓ Using CDP full transcript ({len(content):,} chars)")

        # Priority 2: User-provided transcript file
        if not transcript and transcript_file and os.path.exists(transcript_file):
            with open(transcript_file, 'r', encoding='utf-8') as f:
                content = f.read()
            transcript = {
                'title': f'{name} {target_quarter} Earnings Call (user-provided)',
                'date': datetime.now().strftime('%Y-%m-%d'),
                'quarter': target_quarter,
                'content': content,
            }
            print(f"  ✓ Using user-provided transcript ({len(content):,} chars)")

        # Priority 3: SA API (only as last resort, usually truncated)
        if not transcript:
            transcript = fetch_transcript(sa_ticker, target_quarter=target_quarter, sa_items=sa_items)

        if not transcript and target_quarter and TAVILY_API_KEY:
            print(f"  [Step 1] Tavily fallback: searching for {target_quarter} transcript...")
            cn_name = _ADR_TO_CN.get(ticker, name)
            queries = [
                f'{name} {ticker} {target_quarter} earnings call transcript full text',
                f'{cn_name} {target_quarter} 业绩电话会议 实录 全文',
            ]
            tavily_texts = []
            for q in queries:
                try:
                    tavily_resp = requests.post(
                        'https://api.tavily.com/search',
                        json={'api_key': TAVILY_API_KEY, 'query': q,
                              'max_results': 3, 'search_depth': 'advanced'},
                        timeout=20
                    )
                    tavily_resp.raise_for_status()
                    for r in tavily_resp.json().get('results', []):
                        content = r.get('content', '')
                        title = r.get('title', '')
                        company_terms = [t for t in [ticker, name, cn_name] if len(t) > 2]
                        combined_text = (content + ' ' + title).lower()
                        if not any(t.lower() in combined_text for t in company_terms):
                            continue
                        if len(content) > 500:
                            tavily_texts.append(content)
                except Exception as e:
                    print(f"    Tavily query failed: {e}")

            if tavily_texts:
                combined = '\n\n---\n\n'.join(tavily_texts)
                transcript = {
                    'title': f'{name} {target_quarter} Earnings Call (Tavily search)',
                    'date': datetime.now().strftime('%Y-%m-%d'),
                    'quarter': target_quarter,
                    'content': combined,
                }
                print(f"  ✓ Tavily found transcript ({len(combined):,} chars)")
            else:
                print(f"  ⚠ Tavily also found no transcript for {target_quarter}")

        if not transcript and target_quarter:
            print(f"  ℹ No transcript for {target_quarter}.")

        quarter = target_quarter or (transcript.get('quarter', '') if transcript else '')

        # Step 2: Fetch Press Release
        print(f"\n  [Step 2] Press Release...")
        pr_content = None
        pr_url = None

        if press_release_file and os.path.exists(press_release_file):
            with open(press_release_file, 'r', encoding='utf-8') as f:
                pr_content = f.read()
            print(f"  ✓ Using user-provided press release ({len(pr_content):,} chars)")
        else:
            pr_content, pr_url = fetch_press_release(name, ticker, quarter, sa_items)

        # Save output files
        print(f"\n  [Output] Saving files...")

        if transcript and transcript.get('content'):
            path = os.path.join(output_dir, f"{ticker}_transcript.txt")
            with open(path, 'w', encoding='utf-8') as f:
                f.write(transcript['content'])
            print(f"  ✓ {ticker}_transcript.txt ({len(transcript['content']):,} chars)")

        if pr_content:
            path = os.path.join(output_dir, f"{ticker}_press_release.txt")
            with open(path, 'w', encoding='utf-8') as f:
                f.write(pr_content)
            print(f"  ✓ {ticker}_press_release.txt ({len(pr_content):,} chars)")

        # Save metadata JSON
        meta = {
            'company': name,
            'ticker': ticker,
            'quarter': quarter,
            'reporting_currency': reporting_currency,
            'transcript': {
                'available': bool(transcript),
                'title': transcript.get('title', '') if transcript else '',
                'date': transcript.get('date', '') if transcript else '',
                'chars': len(transcript.get('content', '')) if transcript else 0,
                'source': 'SA Premium' if transcript and len(transcript.get('content', '')) > 20000 else 'RapidAPI/Tavily',
            },
            'press_release': {
                'available': bool(pr_content),
                'url': pr_url or '',
                'chars': len(pr_content) if pr_content else 0,
            },
        }
        with open(os.path.join(output_dir, f"{ticker}_meta.json"), 'w', encoding='utf-8') as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        print(f"  ✓ {ticker}_meta.json")

        # Summary
        print(f"\n  {'=' * 40}")
        print(f"  SUMMARY: {name} ({ticker}) {quarter}")
        print(f"    Transcript: {'✓ ' + str(len(transcript.get('content', ''))) + ' chars' if transcript else '✗ not found'}")
        print(f"    Press Release: {'✓ ' + str(len(pr_content)) + ' chars' if pr_content else '✗ not found'}")
        print(f"    Output: {output_dir}")
        print(f"  {'=' * 40}")

    print(f"\n{'=' * 60}\nDATA COLLECTION COMPLETE\n{'=' * 60}")


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Quarterly Earnings Data Collector')
    parser.add_argument('--ticker', '-t', required=True)
    parser.add_argument('--query', '-q', default='')
    parser.add_argument('--output', '-o', default=None)
    parser.add_argument('--quarter', default=None,
                        help='强制指定目标季度，如 "Q4 2025"')
    parser.add_argument('--transcript-file', default=None,
                        help='手动提供 transcript 文件路径')
    parser.add_argument('--press-release-file', default=None,
                        help='手动提供业绩新闻稿文件路径')
    args = parser.parse_args()
    output_dir = args.output or os.path.join(os.path.expanduser('~/clauderesult'), f'claude{datetime.now().strftime("%m%d")}', f'earnings_{args.ticker.lower()}')
    run_earnings_pipeline([args.ticker], args.query, output_dir,
                          transcript_file=args.transcript_file,
                          press_release_file=args.press_release_file,
                          override_quarter=args.quarter)
