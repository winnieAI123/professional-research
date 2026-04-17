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
    'gemini-3-pro-preview',
    'gemini-2.5-flash',
    'gemini-3.1-pro-preview',
    'gemini-2.5-pro',
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



# ── Per-chapter PR keyword map ──────────────────────────
# Each chapter only receives relevant PR paragraphs (~6k chars), not the full 30k+
# This prevents context overflow on fallback models (3.1-pro/3-pro/flash)
CHAPTER_PR_KEYWORDS = {
    1: ['revenue', 'net income', 'eps', 'ebita', 'profit', 'loss', 'free cash flow',
        'operating income', 'non-gaap', 'adjusted'],
    2: [],    # Thesis — primarily transcript analysis
    3: ['revenue', 'segment', 'cloud', 'commerce', 'cmr', 'customer management',
        'international', 'wholesale', 'million', 'billion', 'increased', 'decreased'],
    4: ['ebita', 'margin', 'expense', 'cost', 'operating', 'r&d', 'research',
        'sales', 'general', 'administrative', 'share-based'],
    5: [],    # Strategy — primarily transcript
    6: ['user', 'mau', 'dau', 'customer', '88vip', 'app', 'active', 'qwen',
        'monthly', 'member', 'subscriber', 'retention'],
    7: ['outlook', 'guidance', 'forecast', 'next quarter', 'fiscal year', 'expect',
        'target', 'growth', 'trend'],
    8: [],    # Valuation — yfinance only
}


def _extract_chapter_pr(pr_content, chapter_num, max_chars=7000):
    """Extract chapter-relevant paragraphs from press release to keep prompts small."""
    if not pr_content:
        return ''
    keywords = CHAPTER_PR_KEYWORDS.get(chapter_num, [])
    if not keywords:
        return pr_content[:max_chars]

    lines = pr_content.split('\n')

    # Always include the leading financial highlights (usually first ~2500 chars)
    # This ensures KPI table and summary numbers are present
    HEADER_CHARS = 2500
    header = pr_content[:HEADER_CHARS]
    seen = set(header.split('\n'))
    relevant_parts = [header]
    total = len(header)

    for i, line in enumerate(lines):
        if total >= max_chars:
            break
        line_lower = line.lower()
        if any(k in line_lower for k in keywords):
            # Include 1 line of context on each side
            chunk_lines = lines[max(0, i - 1): i + 3]
            chunk = '\n'.join(chunk_lines)
            if chunk in seen:
                continue
            seen.add(chunk)
            relevant_parts.append(chunk)
            total += len(chunk)

    return ('\n'.join(relevant_parts))[:max_chars]


def _prior_quarter_label(current_quarter):
    """
    Given "Q3 2026" or "Q3 FY2026", return ("Q2 2026", "September quarter 2025").
    Also returns a human-readable calendar description for search queries.
    """
    m = re.search(r'Q(\d)\s*(?:FY)?(\d{4})', current_quarter, re.IGNORECASE)
    if not m:
        return None, None
    q = int(m.group(1))
    fy = int(m.group(2))
    if q == 1:
        pq, pfy = 4, fy - 1
    else:
        pq, pfy = q - 1, fy

    prior_label = f"Q{pq} {pfy}"

    # Build calendar quarter description (approximate; enough for search)
    # Assume standard quarter mapping: Q1=Apr-Jun, Q2=Jul-Sep, Q3=Oct-Dec, Q4=Jan-Mar
    # For the prior quarter end month/year:
    # pfy is fiscal year; actual calendar year depends on company convention
    # We just construct a secondary search phrase
    QUARTER_MONTHS = {1: 'June', 2: 'September', 3: 'December', 4: 'March'}
    cal_month = QUARTER_MONTHS.get(pq, '')
    # Q4 of FY{pfy} ends in March of the *calendar* year = pfy (fiscal year end)
    # Q1/Q2/Q3 of FY{pfy} end in June/Sep/Dec of pfy-1
    cal_year = pfy if pq == 4 else pfy - 1
    cal_desc = f"{cal_month} quarter {cal_year}" if cal_month else ''

    return prior_label, cal_desc


def _fetch_prior_quarter_data(ticker, current_quarter, tavily_key, cn_name=''):
    """
    Fetch prior quarter key metrics for QoQ calculation.

    Strategy:
    1. Determine prior quarter label (e.g. Q3 2026 → Q2 2026)
    2. Search Tavily / businesswire for prior quarter results
    3. LLM-extract key metrics: revenue, adjusted EBITA, cloud revenue, etc.
    4. Return dict ready to inject into chapter prompts

    Returns: dict with keys 'quarter', 'metrics' (dict of field→value), or None on failure.
    """
    prior_label, cal_desc = _prior_quarter_label(current_quarter)
    if not prior_label:
        return None

    print(f"    [QoQ] Fetching prior quarter: {prior_label} ({cal_desc}) for {ticker}...")

    content = ''
    source_url = ''

    # Attempt 1: Tavily search
    if tavily_key:
        try:
            queries = [
                f'site:businesswire.com "{ticker}" "{cal_desc}" earnings results',
                f'"{ticker}" "{prior_label}" earnings revenue results financial highlights',
            ]
            for query in queries:
                resp = requests.post(
                    'https://api.tavily.com/search',
                    json={'api_key': tavily_key, 'query': query, 'max_results': 3,
                          'include_answer': True, 'search_depth': 'basic'},
                    timeout=25
                )
                data = resp.json()
                content = data.get('answer', '')
                for r in data.get('results', [])[:3]:
                    content += '\n' + r.get('content', '')
                    if not source_url and any(k in r.get('url', '').lower()
                                               for k in ['businesswire', 'prnewswire', 'ir.']):
                        source_url = r.get('url', '')
                if len(content) > 100:
                    break
        except Exception as e:
            print(f"    [QoQ] Tavily search error: {e}")

    if not content:
        print(f"    [QoQ] No prior quarter data found, skipping QoQ")
        return None

    # LLM-extract key metrics from the prior quarter content
    extract_prompt = f"""从以下{ticker} {prior_label}季度财报相关内容中，提取关键财务指标。
只输出JSON格式，key为指标中文名，value为数值字符串（如"RMB 247,795 Mn"）。
如某指标未提及则不输出该key（不要写"未找到"）。

需要提取（如原文有）：
- 总营收
- 经调整EBITA（或经调整营业利润）
- 非GAAP净利润
- 自由现金流
- 云智能集团营收（如适用）
- 中国电商集团营收（如适用）
- 国际商业零售营收（如适用）

内容：
{content[:5000]}"""

    prior_metrics = _llm_json(extract_prompt, tag="PriorQ")
    if prior_metrics and len(prior_metrics) >= 1:
        print(f"    [QoQ] Found {len(prior_metrics)} prior-quarter metrics: "
              f"{list(prior_metrics.keys())}")
        return {
            'quarter': prior_label,
            'cal_desc': cal_desc,
            'metrics': prior_metrics,
            'source_url': source_url,
        }

    print(f"    [QoQ] LLM extraction returned empty, skipping QoQ")
    return None


def _fetch_consensus_yf(ticker, quarter):
    """
    Fetch analyst consensus vs actual for the target quarter using yfinance.
    Returns a formatted string ready to inject into Ch1 data_section.
    Falls back gracefully if yfinance returns nothing.
    """
    try:
        import yfinance as yf
        stock = yf.Ticker(ticker)

        lines = [f"\n=== 市场共识预期 vs 实际（来源: Yahoo Finance / yfinance）==="]

        # 1. Earnings history: find the row matching the target quarter
        hist = stock.earnings_history
        if hist is not None and not hist.empty:
            # quarters are stored as period-end dates, e.g. 2025-12-31
            # match by finding the most recent row
            hist = hist.sort_index()
            latest = hist.iloc[-1]
            lines.append(f"  EPS（最近已报季度）:")
            lines.append(f"    实际 EPS: {latest.get('epsActual', 'N/A')}")
            lines.append(f"    共识预期 EPS: {latest.get('epsEstimate', 'N/A')}")
            diff = latest.get('epsDifference', None)
            pct  = latest.get('surprisePercent', None)
            if diff is not None:
                direction = "BEAT" if float(diff) > 0 else "MISS"
                lines.append(f"    差异: {diff:+.2f}  →  {direction} {abs(float(pct)*100):.1f}%")

        # 2. Revenue estimate: current quarter (0q row)
        rev_est = stock.revenue_estimate
        if rev_est is not None and not rev_est.empty and '0q' in rev_est.index:
            row = rev_est.loc['0q']
            lines.append(f"  营收共识预期（当前季度）:")
            lines.append(f"    分析师均值: {row.get('avg', 'N/A'):,.0f}")
            lines.append(f"    分析师数量: {int(row.get('numberOfAnalysts', 0))}")

        # 3. Earnings estimate: current quarter (0q row) and next year (0y)
        eps_est = stock.earnings_estimate
        if eps_est is not None and not eps_est.empty:
            if '0q' in eps_est.index:
                row = eps_est.loc['0q']
                lines.append(f"  下季度 EPS 共识预期: {row.get('avg', 'N/A')} "
                             f"（{int(row.get('numberOfAnalysts', 0))} 家机构）")
            if '0y' in eps_est.index:
                row = eps_est.loc['0y']
                lines.append(f"  本财年 EPS 共识预期: {row.get('avg', 'N/A')} "
                             f"（{int(row.get('numberOfAnalysts', 0))} 家机构）")

        lines.append("  注意：请在第一章KPI表格的「市场预期」和「Beat/Miss」列中填入以上数据。")
        result = '\n'.join(lines)
        print(f"    [Consensus] yfinance OK: {len(lines)-2} data points")
        return result

    except Exception as e:
        print(f"    [Consensus] yfinance failed: {e}")
        return ''


def _parse_rmb_mn(val_str):
    """Parse various revenue/profit formats → float in Mn RMB.
    Handles: 'RMB 247,795 Mn', '¥2,477.95亿', 'RMB284,843 million', '284843'.
    Returns None if unparseable.
    """
    if not val_str:
        return None
    s = str(val_str).replace(',', '').strip()
    # 亿 → Mn (1亿 = 100Mn)
    m = re.search(r'[¥￥]?\s*([\d.]+)\s*亿', s)
    if m:
        return float(m.group(1)) * 100
    # RMB/CNY xxx Mn/million/million RMB
    m = re.search(r'(?:RMB|CNY)?\s*([\d.]+)\s*(?:Mn|mn|million)', s, re.IGNORECASE)
    if m:
        return float(m.group(1))
    # Billion
    m = re.search(r'(?:RMB|CNY)?\s*([\d.]+)\s*(?:Bn|bn|billion)', s, re.IGNORECASE)
    if m:
        return float(m.group(1)) * 1000
    # Plain number
    m = re.search(r'^([\d.]+)$', s.strip())
    if m:
        return float(m.group(1))
    return None


def _compute_margin_pct(ebita_str, revenue_str):
    """Compute EBITA/operating margin from two value strings.
    Returns formatted string like '19.3%' or None if either is unparseable / revenue is 0.
    """
    ebita = _parse_rmb_mn(ebita_str)
    rev = _parse_rmb_mn(revenue_str)
    if ebita is None or rev is None or rev == 0:
        return None
    pct = ebita / rev * 100
    return f"{pct:.1f}%"


def _build_multi_quarter_context(prior1_data, prior2_data=None):
    """
    Build multi-quarter context string (Q-1 and Q-2) for injection into Ch1/Ch3/Ch4.
    Both prior1_data and prior2_data are return values of _fetch_prior_quarter_data().
    Automatically computes margin% = EBITA / Revenue for each quarter.
    Works for any company/ticker — no YTD arithmetic, just direct search results.
    """
    if not prior1_data:
        return ''

    sections = []

    def _format_quarter_block(qdata, label):
        pq = qdata['quarter']
        pm = qdata['metrics']
        block = [f"\n=== {label} ({pq}) 关键数据（用于计算 QoQ 和利润率趋势）==="]
        for k, v in pm.items():
            block.append(f"  {k}: {v}")
        # Auto-compute margin if revenue + EBITA both present
        rev_key = next((k for k in pm if '营收' in k and '集团' not in k and '云' not in k
                        and '国际' not in k and '电商' not in k), None)
        ebita_key = next((k for k in pm if 'ebita' in k.lower() or '调整' in k), None)
        if rev_key and ebita_key:
            margin = _compute_margin_pct(pm[ebita_key], pm[rev_key])
            if margin:
                block.append(f"  （自动计算）经调整EBITA利润率: {margin}")
        return '\n'.join(block)

    sections.append(_format_quarter_block(prior1_data, "上季度 Q-1"))

    if prior2_data:
        sections.append(_format_quarter_block(prior2_data, "上上季度 Q-2"))

    sections.append(
        "\n  注意：请用以上数据计算 QoQ% = (本季 - 上季) / 上季 × 100%，"
        "并在第三章收入表格和第四章利润率表格的 QoQ变化 列中填入计算结果。"
        "利润率 = 经调整EBITA / 总营收 × 100%。"
    )
    return '\n'.join(sections)


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
# Step 3: Quarterly Data (IR Scraper → Tavily → yfinance)
# ============================================================
def collect_quarterly_data(company_name, ticker, quarter, sa_items=None):
    print(f"    [Data] Collecting quarterly financials for {ticker}...")
    result = {'data': {}, 'metadata': {}, 'press_release_url': '', 'raw_pr_content': ''}
    
    pr_content = ""

    
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
                    # The user suggests /html/body/main/div[2] and [4] but we can just use bs4 to extract all text or common tags
                    soup = BeautifulSoup(html, 'html.parser')
                    main_content = soup.find('main')
                    if main_content:
                        pr_content = main_content.get_text(separator='\n', strip=True)
                        result['press_release_url'] = url
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
                        result['press_release_url'] = pdf_url
                except Exception as e:
                    print(f"    [IR] Euroland PDF fetch failed: {e}")

    # Source 1 (Priority): Direct IR page scraper
    if not pr_content and ticker in _IR_CONFIGS:
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
                    # Also capture businesswire/prnewswire URL specifically (for report footer)
                    if any(k in url.lower() for k in ['businesswire', 'prnewswire', 'globenewswire', 'stocktitan']):
                        result.setdefault('businesswire_url', url)
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

    # ── QoQ: Fetch prior quarter data for QoQ calculations ────────────────────
    # Determines previous quarter automatically, searches via Tavily, calculates QoQ %
    # This runs for any ticker - works universally for US/HK/A-share companies
    prior_quarter_data = None
    if quarter:
        try:
            prior_quarter_data = _fetch_prior_quarter_data(
                ticker, quarter, TAVILY_API_KEY,
                cn_name=_ADR_TO_CN.get(ticker, company_name)
            )
        except Exception as _qoq_err:
            print(f"    [QoQ] Skipped: {_qoq_err}")

    # Fetch Q-2 by calling the same function once more, treating Q-1 as "current"
    # e.g. current=Q3 2026 → Q-1=Q2 2026 → calling again with Q2 2026 → Q-2=Q1 2026
    # Universal: works for any company, no YTD arithmetic needed
    prior2_quarter_data = None
    if prior_quarter_data:
        try:
            prior2_quarter_data = _fetch_prior_quarter_data(
                ticker, prior_quarter_data['quarter'], TAVILY_API_KEY,
                cn_name=_ADR_TO_CN.get(ticker, company_name)
            )
        except Exception as _q2_err:
            print(f"    [QoQ] Q-2 fetch skipped: {_q2_err}")

    qoq_context = _build_multi_quarter_context(prior_quarter_data, prior2_quarter_data)

    # ── Track businesswire URL separately for authoritative footer links ──────
    bw_url = (quarterly_data.get('businesswire_url', '') if quarterly_data else '') or pr_url
    
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
        print(f"    yfinance market data: {e}")

    # ── Consensus estimates via yfinance (Beat/Miss, next-quarter EPS/Rev) ─────
    consensus_str = _fetch_consensus_yf(ticker, quarter)

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
    # Use compressed transcript analysis (not raw transcript) to keep prompt short
    transcript_summary_for_exec = (transcript_analysis.get('analysis', '') if transcript_analysis else '') or transcript_for_chapters[:3000]
    exec_summary_prompt = f"""{SYS}

请用一段自然语言（250-350字）概括{company_name} {quarter}本季度最核心的信息。
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
财报/新闻稿摘要:
{fin_data[:5000]}

电话会分析摘要:
{transcript_summary_for_exec}"""

    print(f"    [Report] Executive Summary...")
    exec_summary = _llm_call(exec_summary_prompt, max_tokens=3000, tag="ExecSummary")
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
        
        # Build data section — chapter-specific extraction to keep prompts manageable
        # Full PR (~30k) + full transcript (~36k) = ~70k chars → overwhelms fallback models
        # Instead, each chapter gets only relevant PR paragraphs (~6-7k) + focused transcript
        if ch_num == 8:
            # Valuation: yfinance market data only
            data_section = f"\nyfinance市场数据: {yf_str}\n\n财报/新闻稿原文(摘要):\n{fin_data[:2000]}"
        elif ch_num in (2, 5):
            # Thesis & Strategy: primarily transcript, brief PR context
            data_section = (f"\n财报/新闻稿原文(摘要):\n{fin_data[:2500]}"
                           f"\n\n电话会实录:\n{transcript_for_chapters}")
        else:
            # Other chapters: targeted PR extraction + full transcript
            ch_pr = _extract_chapter_pr(fin_data, ch_num, max_chars=6500)
            ch_transcript_len = 6000 if ch_num == 5 else 4000
            data_section = (f"\n财报/新闻稿原文（相关段落）:\n{ch_pr}"
                           f"\n\n电话会实录:\n{transcript_for_chapters[:ch_transcript_len]}")

        # Inject multi-quarter context for chapters with QoQ/trend tables
        # Ch1=KPI summary, Ch3=Revenue trend, Ch4=Profit margin trend
        if ch_num in (1, 3, 4) and qoq_context:
            data_section += qoq_context

        # Inject consensus estimates into Ch1 (KPI table) and Ch8 (valuation)
        if ch_num in (1, 8) and consensus_str:
            data_section += consensus_str

        prompt = f"""

请严格按照以下模板结构撰写本章内容。用提供的财报原文和电话会数据替换所有 [placeholder]。
保留所有表格结构，填入实际数据。不要改变章节编号和标题。

{template_section}

--- 以下是数据源 ---
{data_section}"""
        
        result = _llm_call(prompt, CH_TOKENS[ch_num], tag=CH_TAGS[ch_num])
        
        if not result:
            # Condensed fallback: strip down to just the most critical data and retry
            # This fires when ALL models failed (usually due to large prompt on fallback models)
            print(f"    [Report] {ch_num}/8: condensed fallback attempt...")
            short_pr = fin_data[:3000]
            condensed_prompt = (
                f"{SYS}\n\n"
                f"请撰写本季度经营报告的「{CH_LABELS[ch_num]}」章节。"
                f"使用 ## {ch_names_map[ch_num]}、{CH_LABELS[ch_num]} 作为标题，"
                f"包含至少1个数据表格和简短分析段落。直接输出Markdown，不要前言。\n\n"
                f"数据：\n{short_pr}"
            )
            result = _llm_call(condensed_prompt, 2000, tag=f"{CH_TAGS[ch_num]}_condensed")

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
| 1 | {company_name} {quarter} Earnings Release (BusinessWire) | {bw_url or pr_url or '未获取'} |
| 2 | {company_name} {quarter} Earnings Call Transcript (Seeking Alpha) | https://seekingalpha.com/symbol/{ticker}/earnings/transcripts |
| 3 | IR Press Release PDF | {pr_url or '未获取'} |
| 4 | 上市公司SEC/港交所公告 | https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={ticker} |

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
    print(f"    [Report] Saved MD: {md_fname} ({len(full_md)} chars)")

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
            print(f"    [Report] Saved DOCX: {docx_fname}")
        else:
            print(f"    [Report] md_to_word.py not found, skipping Word conversion")
    except Exception as e:
        print(f"    [Report] Word conversion failed: {e}")
    
    return docx_path if os.path.exists(docx_path) else md_path


# ============================================================
# Post-report: Supplement Undisclosed Fields
# ============================================================

def _reconv_to_word(md_path):
    """Re-convert MD to Word after patching."""
    docx_path = md_path.replace('.md', '.docx')
    try:
        md_to_word_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'md_to_word.py')
        if os.path.exists(md_to_word_path):
            import importlib.util
            spec = importlib.util.spec_from_file_location("md_to_word", md_to_word_path)
            md_to_word_mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(md_to_word_mod)
            md_to_word_mod.convert_md_to_word(md_path, docx_path)
            print(f"  [Supplement] Re-converted to Word: {os.path.basename(docx_path)}")
    except Exception as e:
        print(f"  [Supplement] Word re-conversion failed: {e}")


def _get_undisclosed_rows(lines):
    """Return list of (line_idx, field_name, original_line) for rows with '未披露'."""
    rows = []
    for i, line in enumerate(lines):
        if '未披露' not in line or '|' not in line:
            continue
        cells = [c.strip() for c in line.split('|')]
        cells = [c for c in cells if c]
        if cells:
            rows.append((i, cells[0], line))
    return rows


def _apply_patches(lines, undisclosed_rows, extracted):
    """Apply extracted values to undisclosed rows. Returns (lines, count_patched, still_missing)."""
    patched = 0
    still_missing = []
    for i, field, original_line in undisclosed_rows:
        value = str(extracted.get(field, '')).strip()
        if not value or value in ('未找到', '未披露', 'null', 'None', '-', '', 'N/A'):
            still_missing.append((i, field, original_line))
            continue
        new_line = original_line.replace('未披露', value, 1)
        if new_line != original_line:
            lines[i] = new_line
            patched += 1
            print(f"    ✓ {field}: → {value}")
        else:
            still_missing.append((i, field, original_line))
    return lines, patched, still_missing


def supplement_from_press_release(md_path, pr_path, company_name, quarter):
    """
    Phase 1: Extract ALL objectively-disclosed financial data from the local press release
    and patch the MD report. No external API calls needed.
    Returns (lines, remaining_undisclosed_rows, total_patched).
    """
    with open(md_path, 'r', encoding='utf-8') as f:
        lines = f.read().split('\n')

    undisclosed_rows = _get_undisclosed_rows(lines)
    if not undisclosed_rows:
        return lines, [], 0

    # Read press release (may be large; truncate to 40k chars which covers all tables)
    try:
        with open(pr_path, 'r', encoding='utf-8') as f:
            pr_text = f.read(40000)
    except FileNotFoundError:
        print(f"  [Phase1] Press release not found: {pr_path}")
        return lines, undisclosed_rows, 0

    fields_list = '\n'.join([f"- {f}" for _, f, _ in undisclosed_rows])

    extract_prompt = f"""你是财报数据提取专家。以下是{company_name} {quarter}季度财报原文（英文）。

任务：从原文中找出以下字段的具体数值，并以JSON格式输出。

需要提取的字段（中文名称）：
{fields_list}

财报原文：
{pr_text}

输出规则：
1. 只输出JSON对象，key为字段中文名，value为从原文中提取的简洁数值
2. 数值格式：金额用"¥/RMB/US$"前缀+数字+单位（如"¥2,972亿"），增速用百分比（如"+1.5%"），利润率用百分比
3. 如果原文中明确有该数据，必须填入——禁止把原文中存在的数据写成"未找到"
4. 原文中确实没有提及的字段才写"未找到"
5. QoQ变化：若原文有上季度对比数据则计算，否则写"未找到"
6. 只输出JSON，不要任何其他文字或解释"""

    print(f"  [Phase1] Extracting {len(undisclosed_rows)} fields from press release...")
    extracted = _llm_json(extract_prompt, tag="PR_Extract")
    if not extracted:
        print(f"  [Phase1] LLM extraction failed")
        return lines, undisclosed_rows, 0

    lines, patched, still_missing = _apply_patches(lines, undisclosed_rows, extracted)
    print(f"  [Phase1] Patched {patched}/{len(undisclosed_rows)} fields from press release. "
          f"{len(still_missing)} still missing.")
    return lines, still_missing, patched


def supplement_from_web(lines, undisclosed_rows, ticker, company_name, quarter):
    """
    Phase 2: For fields still missing after Phase 1, search the web.
    Targets externally-sourced data: Beat/Miss consensus, analyst targets, historical quarters.
    Returns (lines, total_patched).
    """
    if not undisclosed_rows:
        return lines, 0

    if not TAVILY_API_KEY:
        print(f"  [Phase2] No TAVILY_API_KEY, skipping web supplement")
        return lines, 0

    cn_name = _ADR_TO_CN.get(ticker, company_name)

    # Group fields into batches — use targeted queries for known external-data categories
    BEAT_MISS_KEYWORDS = {'市场预期', 'Beat', 'Miss', '共识', '分析师预期', 'EPS共识', '营收共识'}
    ANALYST_KEYWORDS = {'目标价', '评级', '分析师', 'Price Target'}
    HIST_KEYWORDS = {'Q1', 'Q2', 'Q3', '上季', '历史', '季度趋势', 'QoQ'}

    def _field_matches(field, keywords):
        return any(k.lower() in field.lower() for k in keywords)

    # Build targeted query groups
    beat_fields = [(i, f, l) for i, f, l in undisclosed_rows if _field_matches(f, BEAT_MISS_KEYWORDS)]
    analyst_fields = [(i, f, l) for i, f, l in undisclosed_rows if _field_matches(f, ANALYST_KEYWORDS)]
    hist_fields = [(i, f, l) for i, f, l in undisclosed_rows if _field_matches(f, HIST_KEYWORDS)]
    other_fields = [r for r in undisclosed_rows
                    if r not in beat_fields and r not in analyst_fields and r not in hist_fields]

    query_groups = []
    if beat_fields:
        query_groups.append((
            f'"{ticker}" {quarter} earnings beat miss analyst consensus EPS revenue estimate',
            beat_fields
        ))
    if analyst_fields:
        query_groups.append((
            f'"{ticker}" stock analyst price target rating {quarter} 2026',
            analyst_fields
        ))
    if hist_fields:
        query_groups.append((
            f'"{cn_name}" OR "{ticker}" quarterly revenue Q1 Q2 Q3 2025 results financial',
            hist_fields
        ))
    # Remaining fields: one broad query
    if other_fields:
        fields_str = ' '.join([f for _, f, _ in other_fields[:5]])
        query_groups.append((
            f'"{cn_name}" OR "{ticker}" {quarter} {fields_str} earnings results',
            other_fields
        ))

    # Execute queries and collect content
    search_data = {}  # field → content
    for query_str, field_rows in query_groups:
        try:
            resp = requests.post(
                'https://api.tavily.com/search',
                json={'api_key': TAVILY_API_KEY, 'query': query_str,
                      'max_results': 5, 'search_depth': 'basic'},
                timeout=15
            )
            resp.raise_for_status()
            data = resp.json()
            content = data.get('answer', '') or ''
            for r in data.get('results', [])[:3]:
                content += f"\n{r.get('content', '')[:600]}"
            for _, field, _ in field_rows:
                search_data[field] = content[:2000]
        except Exception as e:
            print(f"    [Phase2] Search failed: {e}")

    if not search_data:
        return lines, 0

    fields_list = '\n'.join([f"- {f}" for f in search_data.keys()])
    search_text = '\n\n'.join([f"[{f}]\n{v}" for f, v in search_data.items()])

    extract_prompt = f"""从以下搜索结果中，为{company_name} {quarter}的各财务指标提取具体数值。

需要提取的指标：
{fields_list}

搜索结果：
{search_text[:10000]}

请输出JSON，格式：{{"指标名": "具体数值", ...}}

规则：
- 只输出找到的具体数值，确实找不到就写"未找到"
- 数值要简洁（如"$50.22B"、"BEAT +14%"、"Moderate Buy / 均价$36"）
- 必须确认数值来自{company_name}，不是其他公司的数据
- 只输出JSON，不要任何其他文字"""

    extracted = _llm_json(extract_prompt, tag="WebExtract")
    if not extracted:
        return lines, 0

    lines, patched, _ = _apply_patches(lines, undisclosed_rows, extracted)
    print(f"  [Phase2] Patched {patched} additional fields from web search.")
    return lines, patched


def supplement_undisclosed(md_path, ticker, company_name, quarter, output_dir):
    """
    Two-phase supplement after report generation:
      Phase 1 — read local _press_release.txt (no API quota consumed, covers all objectively disclosed data)
      Phase 2 — web search for externally-sourced data (Beat/Miss, analyst targets, historical quarters)
    Patches MD in-place and re-converts to Word.
    """
    with open(md_path, 'r', encoding='utf-8') as f:
        initial_lines = f.read().split('\n')

    undisclosed_rows = _get_undisclosed_rows(initial_lines)
    if not undisclosed_rows:
        print(f"  [Supplement] ✓ No undisclosed fields — report complete!")
        return False

    print(f"\n  [Supplement] Found {len(undisclosed_rows)} undisclosed field(s):")
    for _, field, _ in undisclosed_rows:
        print(f"    - {field}")

    total_patched = 0

    # --- Phase 1: local press release ---
    pr_path = os.path.join(output_dir, f"{ticker}_press_release.txt")
    lines, remaining, p1_count = supplement_from_press_release(md_path, pr_path, company_name, quarter)
    total_patched += p1_count

    # --- Phase 2: web search for remaining fields ---
    if remaining:
        lines, p2_count = supplement_from_web(lines, remaining, ticker, company_name, quarter)
        total_patched += p2_count

    if total_patched == 0:
        print(f"  [Supplement] No patches applied.")
        return False

    # Save patched MD
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print(f"  [Supplement] Total patches: {total_patched}. MD saved.")

    _reconv_to_word(md_path)
    return True


# ============================================================
# Main Pipeline
# ============================================================
def run_earnings_pipeline(companies, query="", output_dir=None, transcript_file=None, press_release_file=None, override_quarter=None):
    if not output_dir:
        output_dir = os.path.join(SCRIPT_DIR, "..", "data", "earnings_results")
    os.makedirs(output_dir, exist_ok=True)

    print("=" * 60)
    print("QUARTERLY EARNINGS ANALYSIS")
    print(f"  Companies: {companies}")
    print(f"  LLM Chain: {' > '.join(MODEL_CHAIN)}")
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
        
        # Resolve proper US ADR ticker for Seeking Alpha + reporting currency
        sa_ticker, reporting_currency = _resolve_sa_ticker(name, detect_ticker)
        ticker = sa_ticker  # Use resolved ticker throughout
        print(f"  Ticker: {ticker} (detect: {detect_ticker}, currency: {reporting_currency})")
        
        # Step 0: Quarter Discovery
        print(f"\n  [0/4] Quarter Discovery...")
        target_quarter, sa_has_transcript, sa_items = discover_latest_quarter(sa_ticker, name)

        # Override quarter if user specified (prevents SA mislabeling)
        if override_quarter:
            if target_quarter and target_quarter != override_quarter:
                print(f"  [Step 0] Quarter override: SA={target_quarter} → user={override_quarter}")
            else:
                print(f"  [Step 0] Quarter override: {override_quarter}")
            target_quarter = override_quarter
            sa_has_transcript = False  # Re-check SA for overridden quarter

        print(f"  [Step 0] Target quarter: {target_quarter}, SA transcript: {'yes' if sa_has_transcript else 'no'}")

        # Step 1: Fetch Transcript
        print(f"\n  [1/4] Transcript...")
        transcript = None
        
        # Priority A: User-provided transcript file
        if transcript_file and os.path.exists(transcript_file):
            with open(transcript_file, 'r', encoding='utf-8') as f:
                content = f.read()
            transcript = {
                'title': f'{name} {target_quarter} Earnings Call (user-provided)',
                'date': datetime.now().strftime('%Y-%m-%d'),
                'quarter': target_quarter,
                'content': content,
            }
            print(f"  ✓ Using user-provided transcript ({len(content):,} chars)")
        
        # Priority B: SA API (target quarter only)
        if not transcript:
            transcript = fetch_transcript(sa_ticker, target_quarter=target_quarter, sa_items=sa_items)
        
        # Priority C: Tavily search for transcript (when SA doesn't have it yet)
        if not transcript and target_quarter and TAVILY_API_KEY:
            print(f"  [1/4] Tavily fallback: searching for {target_quarter} transcript...")
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
                        # Company-aware filter: skip results that don't mention the target company
                        company_terms = [t for t in [ticker, name, cn_name] if len(t) > 2]
                        combined_text = (content + ' ' + title).lower()
                        if not any(t.lower() in combined_text for t in company_terms):
                            print(f"    [Transcript] Skip unrelated: {title[:60]}")
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
                print(f"  ✓ Tavily found transcript content ({len(combined):,} chars from {len(tavily_texts)} sources)")
            else:
                print(f"  ⚠ Tavily also found no transcript for {target_quarter}")
        
        if not transcript and target_quarter:
            print(f"  ℹ No transcript for {target_quarter}. Report will rely on IR press release / PDF data.")
        
        # Step 2
        ta = None
        if transcript:
            print(f"\n  [2/4] Transcript Analysis...")
            ta = analyze_transcript(transcript, name)
        
        # Use target quarter as the report quarter (not transcript quarter)
        # This prevents mixing: e.g. Q3 transcript + Q4 IR PDF
        quarter = target_quarter or (transcript.get('quarter', '') if transcript else '')
        
        # Step 3
        print(f"\n  [3/4] Financial Data (Press Release)...")
        # Priority A: User-provided press release file
        if press_release_file and os.path.exists(press_release_file):
            with open(press_release_file, 'r', encoding='utf-8') as f:
                pr_content = f.read()
            print(f"  ✓ Using user-provided press release ({len(pr_content):,} chars)")
            qd = collect_quarterly_data(name, ticker, quarter, sa_items)
            if qd:
                qd['raw_pr_content'] = pr_content
            else:
                qd = {'data': {}, 'raw_pr_content': pr_content, 'metadata': {'source': 'user_press_release'}}
        else:
            qd = collect_quarterly_data(name, ticker, quarter, sa_items)
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
            # Post-generation: supplement any '未披露' fields via Tavily search
            md_path = path.replace('.docx', '.md') if path.endswith('.docx') else path
            if os.path.exists(md_path):
                supplement_undisclosed(md_path, ticker, name, quarter, output_dir)
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
    parser.add_argument('--quarter', default=None,
                        help='强制指定目标季度，如 "Q4 2025"（覆盖SA自动发现，解决季度标注错误问题）')
    parser.add_argument('--transcript-file', default=None,
                        help='手动提供 transcript 文件路径（txt/md），跳过 SA 获取')
    parser.add_argument('--press-release-file', default=None,
                        help='手动提供业绩新闻稿文件路径（txt），跳过 IR 抓取')
    args = parser.parse_args()
    output_dir = args.output or os.path.join(os.path.expanduser('~/clauderesult'), f'claude{datetime.now().strftime("%m%d")}', f'earnings_{args.ticker.lower()}')
    run_earnings_pipeline([args.ticker], args.query, output_dir,
                          transcript_file=args.transcript_file,
                          press_release_file=args.press_release_file,
                          override_quarter=args.quarter)
