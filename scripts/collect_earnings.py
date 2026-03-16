"""
Type 8 Submodule: Quarterly Earnings Analysis (季度业绩分析)
High-standard earnings update following JPMorgan/Goldman Sachs institutional format.

Data Sources:
  1. Seeking Alpha Transcript (RapidAPI) -> 管理层分析
  2. Press Release (Tavily search) -> 季度财务数据 (structured JSON)
  3. yfinance quarterly_financials -> 备选

LLM Fallback: gemini-2.5-pro -> gemini-3.1-pro-preview -> gemini-3-pro-preview -> gemini-2.5-flash
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
GEMINI_API_KEY = get_api_key("GEMINI_API_KEY")
TAVILY_API_KEY = get_api_key("TAVILY_API_KEY")

from google import genai
gemini_client = genai.Client(api_key=GEMINI_API_KEY)


# ============================================================
# LLM Call with 4-Model Fallback
# ============================================================
MODEL_CHAIN = [
    'gemini-2.5-pro',
    'gemini-3.1-pro-preview',
    'gemini-3-pro-preview',
    'gemini-2.5-flash',
]

def _fmt_num(val, currency=''):
    """Format raw numbers: 17200000000 -> $17.2B, 8900000000 -> $8.9B"""
    if not val or val == '-' or val == 'null':
        return '-'
    try:
        num = float(str(val).replace(',', ''))
    except (ValueError, TypeError):
        return str(val)
    
    prefix = '$' if currency.upper() == 'USD' else ('RMB ' if currency.upper() == 'RMB' else '')
    
    abs_num = abs(num)
    sign = '-' if num < 0 else ''
    if abs_num >= 1e9:
        return f"{sign}{prefix}{abs_num/1e9:.1f}B"
    elif abs_num >= 1e6:
        return f"{sign}{prefix}{abs_num/1e6:.1f}M"
    elif abs_num >= 1e3:
        return f"{sign}{prefix}{abs_num/1e3:.1f}K"
    else:
        return f"{sign}{prefix}{num:,.2f}" if isinstance(num, float) and num != int(num) else f"{sign}{prefix}{int(num):,}"


def _clean_llm(text):
    """Remove LLM roleplay preambles and Markdown artifacts."""
    text = re.sub(r'\*\*', '', text)
    # Note: do NOT strip ## heading prefixes — they are needed for Word conversion
    # Remove common roleplay preambles
    preamble_patterns = [
        r'^(?:好的|以下是|根据您|作为|这是|我将|让我|请参考|基于)[^\n]*(?:分析[：:]|报告[：:]|如下[：:]|供参考[：:。])[^\n]*\n*',
        r'^(?:To:|From:|Subject:|Date:)\s+[^\n]*\n*',
        r'^\*[^\n]*\n*',
    ]
    for pat in preamble_patterns:
        text = re.sub(pat, '', text, flags=re.MULTILINE)
    return text.strip()


def _llm_call(prompt, max_tokens=8000, temperature=0.2, tag=""):
    for model in MODEL_CHAIN:
        for attempt in range(2):
            try:
                resp = gemini_client.models.generate_content(
                    model=model, contents=prompt,
                    config={'temperature': temperature, 'max_output_tokens': max_tokens}
                )
                if resp and resp.text:
                    # Check finish_reason for truncation/safety issues
                    finish_reason = None
                    try:
                        if resp.candidates and resp.candidates[0].finish_reason:
                            finish_reason = str(resp.candidates[0].finish_reason)
                    except Exception:
                        pass
                    
                    text = _clean_llm(resp.text.strip())
                    
                    # Detect truncated output
                    is_truncated = False
                    if finish_reason and 'STOP' not in finish_reason and 'stop' not in finish_reason:
                        print(f"      [{tag}] {model}: finish_reason={finish_reason}, output={len(text)} chars — TRUNCATED, retrying...")
                        is_truncated = True
                    elif len(text) < 200 and max_tokens >= 1000:
                        print(f"      [{tag}] {model}: output only {len(text)} chars — suspiciously short, retrying...")
                        is_truncated = True
                    
                    if is_truncated:
                        if attempt == 0:
                            time.sleep(1)
                            continue  # Retry same model
                        else:
                            break  # Next model
                    
                    if tag:
                        print(f"      [{tag}] OK via {model} ({len(text)} chars)")
                    return text
            except Exception as e:
                err = str(e).lower()
                if any(k in err for k in ['503', 'resource', 'unavailable', 'quota', 'overloaded']):
                    print(f"      [{tag}] {model} #{attempt+1}: 503/quota, next...")
                    time.sleep(3)
                else:
                    print(f"      [{tag}] {model} err: {e}")
                    time.sleep(2)
    print(f"      [{tag}] ALL MODELS FAILED")
    return ""


def _llm_json(prompt, tag=""):
    """Call LLM expecting JSON output. Retries with simplified prompt on parse failure."""
    raw = _llm_call(prompt, max_tokens=4000, tag=tag)
    if not raw:
        return None
    
    # Try to find JSON in response
    json_match = re.search(r'\{[\s\S]*\}', raw)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass
    
    # Retry: ask LLM to fix the JSON
    fix_prompt = f"""The following text should be valid JSON but has errors. Fix it and return ONLY valid JSON, nothing else:

{raw[:3000]}"""
    
    fixed = _llm_call(fix_prompt, max_tokens=3000, tag=f"{tag}_fix")
    if fixed:
        json_match = re.search(r'\{[\s\S]*\}', fixed)
        if json_match:
            try:
                return json.loads(json_match.group())
            except:
                pass
    return None


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
}

def _resolve_sa_ticker(company_name, detect_ticker):
    """
    Resolve the correct Seeking Alpha ticker for transcript search.
    Returns (ticker, reporting_currency).
    """
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
    
    # LLM fallback: ask for US ADR ticker
    prompt = f"""What is the US stock ticker (NYSE/NASDAQ/OTC) for "{company_name}"?
Return ONLY the ticker symbol (e.g. "BABA", "PDD", "MPNGY"). If not US-listed, return "NONE".
Just the ticker, nothing else."""
    
    result = _llm_call(prompt, max_tokens=20, tag="TickerResolve")
    if result:
        ticker = result.strip().upper().replace('"', '').replace("'", '')
        if re.match(r'^[A-Z]{1,6}$', ticker) and ticker != 'NONE':
            print(f"    [Ticker] {company_name} → {ticker} (LLM)")
            return ticker, 'USD'
    
    print(f"    [Ticker] Could not resolve US ticker for {company_name}")
    return detect_ticker or company_name, 'USD'


# ============================================================
# Step 1: Fetch Transcript (Seeking Alpha)
# ============================================================
def fetch_transcript(ticker):
    headers = {
        'x-rapidapi-host': 'seeking-alpha.p.rapidapi.com',
        'x-rapidapi-key': RAPIDAPI_KEY,
    }
    print(f"    [SA] Searching transcripts for {ticker}...")
    try:
        resp = requests.get(
            'https://seeking-alpha.p.rapidapi.com/transcripts/v2/list',
            params={'id': ticker.lower(), 'size': '5'},
            headers=headers, timeout=20
        )
        resp.raise_for_status()
        items = resp.json().get('data', [])
    except Exception as e:
        print(f"    x Transcript list failed: {e}")
        return None
    
    if not items:
        return None
    
    latest = None
    for item in items:
        title = item.get('attributes', {}).get('title', '')
        if 'earnings call transcript' in title.lower():
            latest = item
            break
    if not latest:
        latest = items[0]
    
    attrs = latest.get('attributes', {})
    title = attrs.get('title', '')
    publish_date = attrs.get('publishOn', '')[:10]
    tid = latest['id']
    
    qm = re.search(r'Q(\d)\s+(\d{4})', title)
    quarter = f"Q{qm.group(1)} {qm.group(2)}" if qm else ""
    
    print(f"    OK: {title} ({publish_date})")
    print(f"    [SA] Fetching content (id={tid})...")
    
    try:
        resp = requests.get(
            'https://seeking-alpha.p.rapidapi.com/transcripts/v2/get-details',
            params={'id': tid}, headers=headers, timeout=30
        )
        resp.raise_for_status()
        html = resp.json().get('data', {}).get('attributes', {}).get('content', '')
    except Exception as e:
        print(f"    x Fetch failed: {e}")
        return None
    
    if not html:
        return None
    
    soup = BeautifulSoup(html, 'html.parser')
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
    
    text = '\n'.join(parts)
    print(f"    OK: {len(text)} chars")
    return {'title': title, 'date': publish_date, 'quarter': quarter, 'content': text, 'id': tid}


# ============================================================
# Step 2: Transcript Analysis
# ============================================================
def analyze_transcript(transcript, company_name):
    if not transcript or not transcript.get('content'):
        return None
    content = transcript['content'][:100000]
    quarter = transcript.get('quarter', '')
    
    prompt = f"""分析{company_name} {quarter}业绩电话会议，用中文完成以下分析。
严格要求：只使用电话会记录中出现的数据和原话，禁止编造任何不在记录中的数字或事实。

一、管理层核心观点（5-8条）
每条：一句话标题 + 100-150字解释（带具体数据），区分CEO/CFO表态。

二、Q&A环节关键问答（5-8条，按重要性排序）
每条严格按以下格式：
Q[编号]: [分析师提出的核心问题，一句话]
• 分析师关注点：[1-2句说明]
• 管理层回应：[2-3句，引用具体数据和原话]
• 信号解读：[1-2句投资含义]

三、前瞻指引（Guidance）
管理层对下季度/全年预期（引用数字），与上季变化，关键假设。
如果电话会中没有提供具体指引数字，请明确写"未提供具体量化指引"。

四、管理层语气评估
整体语气判断 + 最自信和回避的话题。

五、关键风险提示（3-5个）
每个：一句话标题 + 两句说明。

纯文本，不要Markdown。用"一、""二、"编号。不要写开场白。

{content}"""

    print(f"    [LLM] Transcript analysis ({len(content)} chars)...")
    analysis = _llm_call(prompt, max_tokens=8000, tag="Transcript")
    if analysis:
        print(f"    OK: {len(analysis)} chars")
        return {'analysis': analysis, 'quarter': quarter, 'date': transcript.get('date', '')}
    return None


# ============================================================
# Step 3a: IR Direct Scraper (大厂专用)
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
                # Prefer earnings PDFs (filter by 'Announces' keyword)
                for m in matches:
                    decoded = requests.utils.unquote(m)
                    if any(kw in decoded.lower() for kw in ['announces', 'results', 'earnings']):
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
# Step 3: Quarterly Data (IR Scraper → Tavily → yfinance)
# ============================================================
def collect_quarterly_data(company_name, ticker, quarter):
    print(f"    [Data] Collecting quarterly financials for {ticker}...")
    result = {'data': {}, 'metadata': {}, 'press_release_url': '', 'raw_pr_content': ''}
    
    pr_content = ""
    
    # Source 1 (Priority): Direct IR page scraper
    if ticker in _IR_CONFIGS:
        ir_text, ir_url = fetch_ir_press_release(ticker)
        if ir_text:
            pr_content = ir_text
        if ir_url:
            result['press_release_url'] = ir_url
    
    # Source 2 (Fallback): Tavily press release search with multi-query strategy
    if not pr_content:
        print(f"    [Tavily] Searching press release (multi-query)...")
        cn_name = _ADR_TO_CN.get(ticker, company_name)
        # Build multiple targeted queries (English + Chinese)
        queries = [
            f'{company_name} {ticker} {quarter} earnings results revenue net income EPS',
        ]
        # Add Chinese query for better coverage of HK/CN companies
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
                    if not result['press_release_url'] and any(k in url.lower() for k in ['investor', 'earnings', 'press', 'newswire', 'meituan', 'tencent']):
                        result['press_release_url'] = url
                
                if not result['press_release_url'] and tavily_data.get('results'):
                    result['press_release_url'] = tavily_data['results'][0].get('url', '')
                
                if pr_content:
                    print(f"    OK: Press release {len(pr_content)} chars (query #{q_idx+1})")
            except Exception as e:
                print(f"    Warning: Tavily query #{q_idx+1} failed: {e}")
    
    # Store raw PR content for direct use by report generator
    if pr_content:
        result['raw_pr_content'] = pr_content
        result['metadata']['source'] = 'press_release'
        print(f"    OK: Raw PR content stored ({len(pr_content)} chars)")
    
    # Source 2: yfinance — always run to fill gaps (not just fallback)
    print(f"    [yfinance] Supplementing data...")
    try:
        import yfinance as yf
        stock = yf.Ticker(ticker)
        
        # Get quarterly financials
        qf = stock.quarterly_financials
        if qf is not None and not qf.empty:
            latest = qf.columns[0]
            yf_data = {}
            for idx in qf.index:
                v = qf.loc[idx, latest]
                if v is not None and str(v) != 'nan':
                    yf_data[str(idx)] = float(v)
            
            d = result.get('data', {})
            
            # Determine reporting currency: use press release currency if available, else from ADR map
            report_currency = 'USD'
            existing_rev = d.get('revenue', {})
            if isinstance(existing_rev, dict) and existing_rev.get('currency'):
                report_currency = existing_rev['currency']
            elif isinstance(existing_rev, dict) and existing_rev.get('value'):
                val = str(existing_rev['value'])
                if 'RMB' in val or 'CNY' in val or '¥' in val:
                    report_currency = 'RMB'
                elif 'HKD' in val or 'HK$' in val:
                    report_currency = 'HKD'
            currency = report_currency
            
            # Fill null fields from yfinance
            field_map = {
                'net_income': ['Net Income', 'Net Income Common Stockholders', 'Net Income From Continuing Operations'],
                'operating_income': ['Operating Income', 'Operating Revenue', 'EBIT'],
                'revenue': ['Total Revenue', 'Revenue'],
            }
            
            for our_key, yf_keys in field_map.items():
                existing = d.get(our_key, {})
                if isinstance(existing, dict) and (not existing.get('value') or existing.get('value') in (None, 'null', '-')):
                    for yf_key in yf_keys:
                        if yf_key in yf_data:
                            d.setdefault(our_key, {})['value'] = _fmt_num(yf_data[yf_key], currency)
                            d[our_key]['currency'] = currency
                            break
            
            # Fill EPS
            eps = d.get('eps', {})
            if isinstance(eps, dict) and (not eps.get('gaap') or eps.get('gaap') in (None, 'null', '-')):
                prefix = '$' if currency == 'USD' else f'{currency} '
                if 'Basic EPS' in yf_data:
                    d.setdefault('eps', {})['gaap'] = f"{prefix}{yf_data['Basic EPS']:.2f}"
                    d['eps']['currency'] = currency
                elif 'Diluted EPS' in yf_data:
                    d.setdefault('eps', {})['gaap'] = f"{prefix}{yf_data['Diluted EPS']:.2f}"
                    d['eps']['currency'] = currency
            
            # Fill margins from financials
            if 'Total Revenue' in yf_data and yf_data['Total Revenue'] > 0:
                rev = yf_data['Total Revenue']
                margins = d.get('margins', {})
                if isinstance(margins, dict):
                    if (not margins.get('gross') or margins.get('gross') in (None, 'null', '-')) and 'Gross Profit' in yf_data:
                        d.setdefault('margins', {})['gross'] = f"{yf_data['Gross Profit']/rev*100:.1f}%"
                    if (not margins.get('operating') or margins.get('operating') in (None, 'null', '-')) and 'Operating Income' in yf_data:
                        d.setdefault('margins', {})['operating'] = f"{yf_data['Operating Income']/rev*100:.1f}%"
                    if (not margins.get('net') or margins.get('net') in (None, 'null', '-')) and 'Net Income' in yf_data:
                        d.setdefault('margins', {})['net'] = f"{yf_data['Net Income']/rev*100:.1f}%"
            
            filled = sum(1 for k in ['net_income', 'operating_income'] 
                        if isinstance(d.get(k, {}), dict) and d.get(k, {}).get('value') and d[k]['value'] not in (None, '-'))
            print(f"    OK: yfinance filled {filled} gaps, {len(yf_data)} metrics available")
            
            if not result['data']:
                result['data'] = d
                result['metadata']['source'] = 'yfinance'
            else:
                result['data'] = d
                result['metadata']['source'] = f"press_release + yfinance"
    except Exception as e:
        print(f"    Warning: yfinance failed: {e}")
    
    return result if (result['data'] or result.get('raw_pr_content')) else None


# ============================================================
# Step 4: Generate Report (Template-driven Markdown → Word)
# ============================================================
def generate_earnings_report(quarterly_data, transcript_analysis, company_name, ticker, output_dir):
    """Generate 8-chapter earnings report by reading template, filling with LLM, and converting to Word."""
    quarter = transcript_analysis.get('quarter', '') if transcript_analysis else ''
    report_date = datetime.now().strftime('%Y-%m-%d')
    pr_url = quarterly_data.get('press_release_url', '') if quarterly_data else ''
    
    # Prepare raw data for LLM
    raw_transcript = transcript_analysis.get('raw_transcript', '') if transcript_analysis else ''
    pr_content = quarterly_data.get('raw_pr_content', '') if quarterly_data else ''
    
    # Fallback: use structured data string if no raw PR content
    if not pr_content:
        q_data = quarterly_data.get('data', {}) if quarterly_data else {}
        pr_content = json.dumps(q_data, ensure_ascii=False, default=str) if q_data else ''
    
    # Fallback: use analysis text if no raw transcript
    if not raw_transcript:
        raw_transcript = transcript_analysis.get('analysis', '') if transcript_analysis else ''
    
    fin_data = pr_content
    transcript_for_chapters = raw_transcript
    
    # yfinance basic market data for Ch8
    yf_str = ""
    try:
        import yfinance as yf
        stock = yf.Ticker(ticker)
        info = stock.info or {}
        yf_str = json.dumps({
            'price': info.get('currentPrice') or info.get('regularMarketPrice'),
            'marketCap': info.get('marketCap'),
            'trailingPE': info.get('trailingPE'),
            'forwardPE': info.get('forwardPE'),
            'priceToSalesTrailing12Months': info.get('priceToSalesTrailing12Months'),
            'priceToBook': info.get('priceToBook'),
        }, ensure_ascii=False, default=str)
    except Exception as e:
        _log(f"    yfinance market data: {e}")
    
    SYS = f"你是专业买方分析师，正在撰写{company_name} {quarter}季度经营分析报告。不要写开场白。直接输出Markdown。严格使用提供的数据，你必须仔细阅读提供的财报原文和电话会实录，从中提取具体数字填入表格。只有当原文中确实完全没有提及某个指标时，才写\"未披露\"。禁止编造。"
    
    md_sections = []
    
    # ═══════════════════════════════════════════════════════
    # HEADER
    # ═══════════════════════════════════════════════════════
    header = f"""# {company_name} ({ticker})

## 季度经营分析报告

**报告期**: {quarter}
**数据来源**: {company_name} {quarter} 财报 & Earnings Call 实录
**报告生成日期**: {report_date} ｜ **分析师**: AI Research Assistant

---"""
    md_sections.append(header)
    
    # ═══════════════════════════════════════════════════════
    # EXECUTIVE SUMMARY (before chapters)
    # ═══════════════════════════════════════════════════════
    exec_summary_prompt = f"""{SYS}

请用一段自然语言（200-300字）概括{company_name} {quarter}本季度最核心的信息。
不要用表格，不要用bullet point，用流畅的段落叙述。直接输出段落文字，不要写标题。

必须覆盖以下维度（按重要性排列）：
1. 营收规模 + YoY增速 + 是否Beat/Miss预期
2. 核心利润指标（经调整营业利润/利润率/净利润）
3. CapEx资本支出（科技公司必提，未披露则注明"CapEx未单独披露"）
4. 核心增长驱动力 & 主要拖累（各1-2个）
5. 管理层指引/展望（下季度或全年预期，有数字引数字，无则写"未给出具体量化指引"）
6. 整体基调判断（在段落末尾用一个词总结：Confident/Cautious/Defensive）

风格参考:
"本季度实现营收¥83.2亿（YoY +8%），Non-GAAP净利润¥8.78亿（YoY +94%），经营利润率改善至6.1%。广告业务增长27%成为核心驱动力，但游戏业务下滑14%。CapEx方面未单独披露。管理层将AI定位为2026年核心战略，计划审慎配置资本投入；未给出具体量化指引。整体基调Confident。"

--- 以下是数据源 ---
财报/新闻稿原文:
{fin_data}

电话会实录:
{transcript_for_chapters}"""

    print(f"    [Report] Executive Summary...")
    exec_summary = _llm_call(exec_summary_prompt, max_tokens=1500, tag="ExecSummary")
    if exec_summary:
        md_sections.append(f"## Executive Summary\n\n{exec_summary.strip()}\n\n---")
    else:
        md_sections.append("## Executive Summary\n\n（摘要生成失败）\n\n---")
    
    # ═══════════════════════════════════════════════════════
    # CHAPTERS 1-8: Template-driven generation
    # ═══════════════════════════════════════════════════════
    
    # Read and parse the template file
    template_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'templates', 'earnings_quarterly.md')
    chapter_templates = {}
    try:
        with open(template_path, 'r', encoding='utf-8') as f:
            template_content = f.read()
        
        ch_names = ['一', '二', '三', '四', '五', '六', '七', '八']
        chapter_splits = re.split(r'(?=^## [一二三四五六七八]、)', template_content, flags=re.MULTILINE)
        
        for section in chapter_splits:
            for idx, name in enumerate(ch_names):
                if section.strip().startswith(f'## {name}、'):
                    section_clean = re.sub(r'\n---\s*$', '', section.strip())
                    chapter_templates[idx + 1] = section_clean
                    break
        
        print(f"    [Template] Loaded {len(chapter_templates)} chapters")
    except Exception as e:
        print(f"    [Template] ERROR: {e}")
    
    # Per-chapter output token limits
    CH_TOKENS = {1: 3000, 2: 4000, 3: 4000, 4: 4000, 5: 5000, 6: 3000, 7: 4000, 8: 3000}
    CH_TAGS = {1: 'Ch1_KPI', 2: 'Ch2_Thesis', 3: 'Ch3_Revenue', 4: 'Ch4_Profit',
               5: 'Ch5_Strategy', 6: 'Ch6_Ops', 7: 'Ch7_Outlook', 8: 'Ch8_Valuation'}
    CH_LABELS = {1: '核心 KPI 速览', 2: 'Thesis & Takeaways', 3: '收入分析', 4: '盈利能力分析',
                 5: '战略专项分析', 6: '客户与运营指标', 7: '前瞻分析与风险', 8: '估值与预测'}
    ch_names_map = {1: '一', 2: '二', 3: '三', 4: '四', 5: '五', 6: '六', 7: '七', 8: '八'}
    
    for ch_num in range(1, 9):
        template_section = chapter_templates.get(ch_num, '')
        print(f"    [Report] {ch_num}/8: {CH_LABELS[ch_num]}...")
        
        # Build data section — full text, no slicing
        if ch_num == 8:
            data_section = f"\nyfinance市场数据: {yf_str}\n\n财报/新闻稿原文:\n{fin_data}"
        else:
            data_section = f"\n财报/新闻稿原文:\n{fin_data}\n\n电话会实录:\n{transcript_for_chapters}"
        
        prompt = f"""{SYS}

请严格按照以下模板结构撰写本章内容。用提供的财报原文和电话会数据替换所有 [placeholder]。
保留所有表格结构，填入实际数据。不要改变章节编号和标题。

{template_section}

--- 以下是数据源 ---
{data_section}"""
        
        result = _llm_call(prompt, CH_TOKENS[ch_num], tag=CH_TAGS[ch_num])
        
        if result:
            md_sections.append(result.strip())
        else:
            md_sections.append(f"## {ch_names_map[ch_num]}、{CH_LABELS[ch_num]}\n\n（数据获取失败）")
        
        md_sections.append("---")
    
    # ═══════════════════════════════════════════════════════
    # FOOTER: Sources & Disclaimer
    # ═══════════════════════════════════════════════════════
    sources = f"""---

## 数据来源与声明

### 数据来源

| 序号 | 材料 | 链接 |
|------|------|------|
| 1 | {company_name} {quarter} Earnings Release | {pr_url or '未获取'} |
| 2 | {company_name} {quarter} Earnings Call Transcript | https://seekingalpha.com/symbol/{ticker}/earnings/transcripts |
| 3 | SEC/港交所/上交所公告 | https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={ticker} |

### 声明

本报告中标注"估算""估""约""AI估"等字样的数据，均为基于公开信息的推算，非官方披露数字。使用时请以官方财报数据为最终依据。本报告由AI自动生成，不构成投资建议。

Report Date: {report_date} | LLM: Gemini Multi-model Fallback

**— END OF REPORT —**"""
    md_sections.append(sources)
    
    # ═══════════════════════════════════════════════════════
    # ASSEMBLE & SAVE
    # ═══════════════════════════════════════════════════════
    full_md = "\n\n".join(md_sections)
    
    os.makedirs(output_dir, exist_ok=True)
    qc = quarter.replace(' ', '_') if quarter else 'latest'
    
    # Save Markdown
    md_fname = f"{ticker}_{qc}_Earnings_Update.md"
    md_path = os.path.join(output_dir, md_fname)
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(full_md)
    _log(f"    [Report] Saved MD: {md_fname} ({len(full_md)} chars)")
    
    # Convert to Word via md_to_word
    docx_fname = f"{ticker}_{qc}_Earnings_Update.docx"
    docx_path = os.path.join(output_dir, docx_fname)
    try:
        md_to_word_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'md_to_word.py')
        if os.path.exists(md_to_word_path):
            import importlib.util
            spec = importlib.util.spec_from_file_location("md_to_word", md_to_word_path)
            md_to_word = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(md_to_word)
            md_to_word.convert_md_to_word(md_path, docx_path)
            _log(f"    [Report] Saved DOCX: {docx_fname}")
        else:
            _log(f"    [Report] md_to_word.py not found, skipping Word conversion")
    except Exception as e:
        _log(f"    [Report] Word conversion failed: {e}")
    
    return docx_path if os.path.exists(docx_path) else md_path


# ============================================================
# Main Pipeline
# ============================================================
def run_earnings_pipeline(companies, query="", output_dir=None):
    if not output_dir:
        output_dir = os.path.join(SCRIPT_DIR, "..", "data", "earnings_results")
    os.makedirs(output_dir, exist_ok=True)
    
    print("=" * 60)
    print("QUARTERLY EARNINGS ANALYSIS")
    print(f"  Companies: {companies}")
    print(f"  LLM Chain: {' > '.join(MODEL_CHAIN)}")
    print("=" * 60)
    
    for name in companies:
        print(f"\n{'=' * 50}")
        print(f"  {name}")
        print(f"{'=' * 50}")
        
        company = detect_data_source(name)
        detect_ticker = company.get('ticker', '') or name.upper()
        
        # Resolve proper US ADR ticker for Seeking Alpha + reporting currency
        sa_ticker, reporting_currency = _resolve_sa_ticker(name, detect_ticker)
        ticker = sa_ticker  # Use resolved ticker throughout
        print(f"  Ticker: {ticker} (detect: {detect_ticker}, currency: {reporting_currency})")
        
        # Step 1
        print(f"\n  [1/4] Transcript...")
        transcript = fetch_transcript(sa_ticker)
        
        # Transcript freshness check: warn if transcript seems outdated
        if transcript:
            t_date = transcript.get('date', '')
            if t_date:
                try:
                    t_age_days = (datetime.now() - datetime.strptime(t_date, '%Y-%m-%d')).days
                    if t_age_days > 120:
                        print(f"  ⚠️  Transcript is {t_age_days} days old ({t_date}). A newer quarter may exist but is not yet on Seeking Alpha.")
                        print(f"      Will supplement with Tavily search for latest data.")
                except ValueError:
                    pass
        
        # Step 2
        ta = None
        if transcript:
            print(f"\n  [2/4] Transcript Analysis...")
            ta = analyze_transcript(transcript, name)
        
        quarter = transcript.get('quarter', '') if transcript else ''
        
        # Step 3
        print(f"\n  [3/4] Financial Data (Press Release)...")
        qd = collect_quarterly_data(name, ticker, quarter)
        if qd and qd.get('data'):
            print(f"  Data source: {qd.get('metadata', {}).get('source', '?')}")
        
        # Save raw source files for review
        if transcript and transcript.get('content'):
            with open(os.path.join(output_dir, f"{ticker}_transcript.txt"), 'w', encoding='utf-8') as f:
                f.write(transcript['content'])
            print(f"  Saved: {ticker}_transcript.txt ({len(transcript['content']):,} chars)")
        
        if qd and qd.get('raw_pr_content'):
            with open(os.path.join(output_dir, f"{ticker}_press_release.txt"), 'w', encoding='utf-8') as f:
                f.write(qd['raw_pr_content'])
            print(f"  Saved: {ticker}_press_release.txt ({len(qd['raw_pr_content']):,} chars)")
        
        # Step 4
        print(f"\n  [4/4] Report Generation...")
        try:
            path = generate_earnings_report(qd, ta, name, ticker, output_dir)
            print(f"\n  DONE: {path}")
            print(f"  Size: {os.path.getsize(path):,} bytes")
        except Exception as e:
            print(f"  FAILED: {e}")
            import traceback; traceback.print_exc()
        
        # Raw JSON
        raw = {'company': name, 'ticker': ticker, 'quarterly_data': qd,
               'transcript': {k: v for k, v in (transcript or {}).items() if k != 'content'},
               'transcript_analysis': ta}
        with open(os.path.join(output_dir, f"{ticker}_data.json"), 'w', encoding='utf-8') as f:
            json.dump(raw, f, ensure_ascii=False, indent=2, default=str)
    
    print(f"\n{'=' * 60}\nCOMPLETE\n{'=' * 60}")


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Quarterly Earnings Analysis')
    parser.add_argument('--ticker', '-t', required=True)
    parser.add_argument('--query', '-q', default='')
    parser.add_argument('--output', '-o', default=None)
    args = parser.parse_args()
    output_dir = args.output or os.path.join('D:\\clauderesult', f'claude{datetime.now().strftime("%m%d")}', f'earnings_{args.ticker.lower()}')
    run_earnings_pipeline([args.ticker], args.query, output_dir)
