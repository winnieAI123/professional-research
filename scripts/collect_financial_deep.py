"""
Type 8: Financial Data Extraction (财务数据提取)
Dynamic multi-company financial data collection pipeline.

Usage:
  python collect_financial_deep.py --companies "蚂蚁集团,微众银行,奇富科技" \
    --query "分产品余额、收入和利润" --years 5 --output results/report

No hardcoded company config — auto-detects data source for each company.
"""

import argparse
import json
import os
import re
import sys
import time
import requests
from datetime import datetime
from bs4 import BeautifulSoup

# Add scripts dir to path for sibling imports
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from llm_client import generate_content, get_client, FAST_MODEL

# Fast model fallback chain (for table filtering / classification)
FAST_MODEL_CHAIN = [
    "models/gemini-2.0-flash",
    "models/gemini-2.5-flash",
    "models/gemini-2.0-flash-lite",
]
from utils import get_api_key

# ============================================================
# Constants
# ============================================================
SEC_USER_AGENT = "CompanyResearch research@example.com"
SEC_RATE_LIMIT = 0.15  # seconds between SEC requests
TAVILY_API_KEY = get_api_key("TAVILY_API_KEY")


# ============================================================
# JSON Normalization Helpers
# ============================================================
def _normalize_extracted_json(parsed: dict) -> dict:
    """
    Normalize LLM output to standard format: {"data": {...}, "metadata": {...}}.
    Handles cases where LLM uses custom top-level keys or array-based data.
    """
    if not parsed or not isinstance(parsed, dict):
        return parsed
    
    # Case 1: Already has "data" key with dict value
    if "data" in parsed and isinstance(parsed["data"], dict):
        return parsed
    
    # Case 2: LLM used a custom key (e.g., "蚂蚁集团财务数据")
    # Find the first key that looks like a data container (not "metadata")
    metadata = parsed.get("metadata", {})
    data_candidates = {}
    
    for key, value in parsed.items():
        if key == "metadata":
            continue
        if isinstance(value, dict):
            # Check if this dict contains year-keyed data or nested metrics
            has_metrics = False
            normalized_group = {}
            for sub_key, sub_val in value.items():
                if isinstance(sub_val, dict):
                    # Check if it's {year: value} format
                    if any(str(y).isdigit() and len(str(y)) == 4 for y in sub_val.keys()):
                        has_metrics = True
                        normalized_group[sub_key] = sub_val
                    else:
                        # Nested group — recurse one level
                        inner_metrics = {}
                        for inner_k, inner_v in sub_val.items():
                            if isinstance(inner_v, dict):
                                inner_metrics[inner_k] = inner_v
                            elif isinstance(inner_v, list):
                                # Convert array format to {year: value} dict
                                converted = _array_to_year_dict(inner_v)
                                if converted:
                                    inner_metrics[inner_k] = converted
                            elif isinstance(inner_v, (int, float, str)):
                                # Skip metadata-like fields (unit, notes, etc.)
                                pass
                        if inner_metrics:
                            has_metrics = True
                            normalized_group[sub_key] = inner_metrics
                elif isinstance(sub_val, list):
                    converted = _array_to_year_dict(sub_val)
                    if converted:
                        has_metrics = True
                        normalized_group[sub_key] = converted
                elif isinstance(sub_val, str):
                    # Data not found message — skip
                    pass
            
            if has_metrics:
                data_candidates[key] = normalized_group
    
    if data_candidates:
        return {"data": data_candidates, "metadata": metadata}
    
    return parsed


def _array_to_year_dict(arr: list) -> dict:
    """Convert [{年份: 2020, 指标: 值}, ...] array to {2020: 值, ...} dict."""
    if not arr or not isinstance(arr, list):
        return {}
    
    result = {}
    for item in arr:
        if not isinstance(item, dict):
            continue
        # Find year field
        year = None
        value = None
        for k, v in item.items():
            k_lower = k.lower()
            if '年' in k or 'year' in k_lower:
                year = str(v)
            elif '利润' in k or 'profit' in k_lower or '收入' in k_lower or 'revenue' in k_lower or 'income' in k_lower:
                value = v
        
        if year and value is not None:
            result[year] = value
    
    return result


def _try_reformat_response(raw_text: str) -> dict:
    """Ask LLM to reformat a non-JSON response into standard format."""
    try:
        prompt = f"""以下文本包含财务数据但格式不标准。请将其转换为以下JSON格式:
{{
  "data": {{
    "数据组名": {{
      "指标名": {{"2020": 值, "2021": 值}}
    }}
  }},
  "metadata": {{"unit": "单位", "notes": ""}}
}}

原始文本:
{raw_text[:10000]}"""
        
        result = generate_content(prompt=prompt, max_output_tokens=4000, model=FAST_MODEL)
        if result:
            parsed = json.loads(result.strip().strip('```json').strip('```').strip())
            return _normalize_extracted_json(parsed)
    except Exception:
        pass
    return None


# ============================================================
# Dynamic Company Detection (NO hardcoded config)
# ============================================================
def detect_data_source(company_name: str) -> dict:
    """
    Auto-detect best data source for a company.
    Returns: {"name": ..., "source": "sec_edgar"|"cn_listed"|"pdf_search"|"web_search", ...}
    """
    print(f"\n  [Detect] Analyzing data source for '{company_name}'...")
    
    # 1. Try US stock ticker resolution
    us_info = _try_resolve_us_ticker(company_name)
    if us_info:
        print(f"    ✓ US-listed: {us_info['ticker']} → SEC EDGAR")
        return {
            "name": company_name,
            "source": "sec_edgar",
            "ticker": us_info["ticker"],
            "filing_type": us_info.get("filing_type", "20-F"),
        }
    
    # 2. Try CN-listed stock (EastMoney search)
    cn_ticker = _try_resolve_cn_ticker(company_name)
    if cn_ticker:
        print(f"    ✓ CN-listed: {cn_ticker} → EastMoney F10")
        return {
            "name": company_name,
            "source": "cn_listed",
            "ticker": cn_ticker,
        }
    
    # 3. Ask LLM: is this a bank/financial institution with public annual reports?
    if _is_likely_public_reporter(company_name):
        print(f"    → Non-listed institution with annual reports → PDF search")
        return {
            "name": company_name,
            "source": "pdf_search",
            "search_name": company_name,
        }
    
    # 4. Fallback: web search
    print(f"    → No public filings detected → Web search")
    return {
        "name": company_name,
        "source": "web_search",
        "search_name": company_name,
    }


def _try_resolve_us_ticker(company_name: str) -> dict:
    """Check if company is US-listed via yfinance."""
    try:
        import yfinance as yf
        # If input looks like a ticker already (all uppercase alpha)
        if re.match(r'^[A-Z]{1,5}$', company_name):
            t = yf.Ticker(company_name)
            info = t.info
            if info.get("regularMarketPrice"):
                country = info.get("country", "")
                filing = "10-K" if country == "United States" else "20-F"
                return {"ticker": company_name, "filing_type": filing}
        
        # Try common Chinese fintech → US ticker mappings via web search
        prompt = f"""Given the company name "{company_name}", if it is listed on a US stock exchange (NYSE/NASDAQ), 
return ONLY its ticker symbol (e.g., "QFIN"). If it is NOT US-listed, return "NONE".
Just the ticker or NONE, nothing else."""
        result = generate_content(prompt=prompt, max_output_tokens=20, model=FAST_MODEL)
        if result and result.strip() != "NONE" and re.match(r'^[A-Z]{1,5}$', result.strip()):
            ticker = result.strip()
            t = yf.Ticker(ticker)
            info = t.info
            if info.get("regularMarketPrice"):
                country = info.get("country", "")
                filing = "10-K" if country == "United States" else "20-F"
                return {"ticker": ticker, "filing_type": filing}
    except Exception as e:
        print(f"    US ticker check failed: {e}")
    return None


def _try_resolve_cn_ticker(company_name: str) -> str:
    """Check if company is CN-listed via EastMoney search."""
    try:
        url = "https://searchapi.eastmoney.com/api/suggest/get"
        params = {
            "input": company_name,
            "type": "14",
            "token": "D43BF722C8E33BDC906FB84D85E326E8",
            "count": "5",
        }
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        if data.get("QuotationCodeTable", {}).get("Data"):
            for item in data["QuotationCodeTable"]["Data"]:
                code = item.get("Code", "")
                market = item.get("MktNum", "")
                if market in ("0", "1") and re.match(r'^\d{6}$', code):
                    return code
    except Exception:
        pass
    return None


def _is_likely_public_reporter(company_name: str) -> bool:
    """Ask LLM if this company likely publishes annual reports (banks, etc)."""
    try:
        prompt = f"""Is "{company_name}" a licensed financial institution (bank, consumer finance company, 
insurance company) in China that is required to publish annual reports publicly?
Answer ONLY "YES" or "NO"."""
        result = generate_content(prompt=prompt, max_output_tokens=10, model=FAST_MODEL)
        return result and "YES" in result.upper()
    except Exception:
        return False


# ============================================================
# Path A: SEC EDGAR (US-listed)
# ============================================================
class SECCollector:
    """Lightweight SEC EDGAR collector."""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': SEC_USER_AGENT,
            'Accept-Encoding': 'gzip, deflate',
        })
        self._last_request = 0
    
    def _rate_limit(self):
        elapsed = time.time() - self._last_request
        if elapsed < SEC_RATE_LIMIT:
            time.sleep(SEC_RATE_LIMIT - elapsed)
        self._last_request = time.time()
    
    def _get(self, url):
        self._rate_limit()
        resp = self.session.get(url, timeout=30)
        resp.raise_for_status()
        return resp.json()
    
    def lookup_cik(self, ticker: str) -> str:
        data = self._get('https://www.sec.gov/files/company_tickers.json')
        for entry in data.values():
            if entry.get('ticker', '').upper() == ticker.upper():
                return str(entry['cik_str']).zfill(10)
        return None
    
    def get_filings(self, cik: str, filing_type: str = '20-F') -> list:
        data = self._get(f"https://data.sec.gov/submissions/CIK{cik}.json")
        filings = data['filings']['recent']
        results = []
        for i, form in enumerate(filings['form']):
            if form == filing_type:
                results.append({
                    'date': filings['filingDate'][i],
                    'accession': filings['accessionNumber'][i],
                    'primary_doc': filings['primaryDocument'][i],
                })
        return results
    
    def download_filing(self, cik: str, filing: dict, output_dir: str) -> str:
        accession = filing['accession'].replace('-', '')
        filename = f"{filing['date']}_{filing['primary_doc']}"
        filepath = os.path.join(output_dir, filename)
        if os.path.exists(filepath) and os.path.getsize(filepath) > 1000:
            return filepath
        
        url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{filing['primary_doc']}"
        self._rate_limit()
        resp = self.session.get(url, timeout=60)
        resp.raise_for_status()
        os.makedirs(output_dir, exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(resp.text)
        return filepath


def collect_sec_edgar(company: dict, query: str, target_years: list, data_dir: str) -> dict:
    """SEC EDGAR pipeline: download 20-F/10-K → LLM two-round extract."""
    ticker = company["ticker"]
    filing_type = company.get("filing_type", "20-F")
    
    collector = SECCollector()
    cik = collector.lookup_cik(ticker)
    if not cik:
        print(f"    ✗ Could not find CIK for {ticker}")
        return None
    
    filings = collector.get_filings(cik, filing_type)
    if not filings:
        print(f"    ✗ No {filing_type} filings found")
        return None
    
    print(f"    Found {len(filings)} {filing_type} filings")
    
    raw_dir = os.path.join(data_dir, "raw", ticker.lower())
    os.makedirs(raw_dir, exist_ok=True)
    
    # Download enough filings to cover target years
    download_count = min((len(target_years) + 2) // 3 + 1, len(filings))
    html_paths = []
    for f in filings[:download_count]:
        path = collector.download_filing(cik, f, raw_dir)
        if path:
            html_paths.append(path)
            print(f"    ✓ Downloaded: {os.path.basename(path)}")
    
    if not html_paths:
        return None
    
    # Two-round LLM extraction
    return _extract_from_html_files(html_paths, query, target_years, filings, collector, cik, raw_dir)


def _extract_from_html_files(html_paths, query, target_years, all_filings=None,
                              collector=None, cik=None, raw_dir=None) -> dict:
    """Two-round LLM extraction from SEC HTML filings."""
    all_data = {}
    all_metadata = {}
    
    for html_path in html_paths:
        print(f"    [Extract] {os.path.basename(html_path)}...")
        
        # Round 1: Parse HTML tables
        tables = _html_to_tables(html_path)
        if not tables:
            continue
        print(f"      Found {len(tables)} tables")
        
        # Round 1.5: Filter relevant tables (Flash model, fast)
        relevant = _filter_tables(tables, query)
        print(f"      Filtered to {len(relevant)} relevant tables")
        
        if not relevant:
            continue
        
        # Round 2: Extract structured data (Pro model, precise)
        result = _extract_structured_data(relevant, query, target_years)
        if result and result.get("data"):
            for group, metrics in result["data"].items():
                if group not in all_data:
                    all_data[group] = {}
                for metric, years in metrics.items():
                    if metric not in all_data[group]:
                        all_data[group][metric] = {}
                    all_data[group][metric].update(years)
            if result.get("metadata"):
                all_metadata.update(result["metadata"])
    
    # Check year coverage, download more if needed
    found_years = set()
    for group in all_data.values():
        for metric in group.values():
            found_years.update(str(y) for y in metric.keys())
    
    missing = [str(y) for y in target_years if str(y) not in found_years]
    if missing and all_filings and collector and cik and raw_dir:
        print(f"    Missing years: {missing}, trying older filings...")
        for f in all_filings[len(html_paths):len(html_paths)+2]:
            path = collector.download_filing(cik, f, raw_dir)
            if path:
                extra = _extract_from_html_files([path], query, target_years)
                if extra and extra.get("data"):
                    for g, metrics in extra["data"].items():
                        if g not in all_data:
                            all_data[g] = {}
                        for m, years in metrics.items():
                            if m not in all_data[g]:
                                all_data[g][m] = {}
                            for y, v in years.items():
                                if y not in all_data[g][m]:
                                    all_data[g][m][y] = v
    
    return {"data": all_data, "metadata": all_metadata} if all_data else None


def _html_to_tables(html_path: str) -> list:
    """Parse all <table> from HTML, convert to Markdown format."""
    with open(html_path, 'r', encoding='utf-8', errors='ignore') as f:
        html = f.read()
    
    soup = BeautifulSoup(html, 'html.parser')
    tables = []
    
    for i, table_elem in enumerate(soup.find_all('table')):
        rows = []
        for tr in table_elem.find_all('tr'):
            cells = [td.get_text(strip=True) for td in tr.find_all(['td', 'th'])]
            if any(cells):
                rows.append('| ' + ' | '.join(cells) + ' |')
        
        if len(rows) < 2:
            continue
        
        # Get context (text before table)
        context = ""
        prev = table_elem.find_previous(['h1', 'h2', 'h3', 'h4', 'p', 'b', 'strong'])
        if prev:
            context = prev.get_text(strip=True)[:200]
        
        markdown = '\n'.join(rows)
        tables.append({
            "index": i,
            "context": context,
            "markdown": markdown,
            "preview": '\n'.join(rows[:3]),
            "rows": len(rows),
            "cols": max((r.count('|') - 1 for r in rows), default=0),
        })
    
    return tables


def _filter_tables(tables: list, query: str) -> list:
    """Round 1: Use Flash model chain to quickly filter relevant tables."""
    if len(tables) <= 5:
        return tables
    
    summaries = []
    for t in tables:
        summaries.append(f"Table #{t['index']} ({t['rows']}×{t['cols']}): {t['context'][:100]} | {t['preview'][:150]}")
    
    prompt = f"""User needs: {query}

Below are {len(tables)} tables from a financial filing. Return ONLY the table numbers (e.g., [54, 161, 186]) 
that contain data relevant to the user's query. Return a JSON array of numbers.

{chr(10).join(summaries)}"""

    # Try each fast model in chain (fallback on 429/503)
    for model in FAST_MODEL_CHAIN:
        try:
            result = generate_content(prompt=prompt, max_output_tokens=500, model=model)
            if result:
                indices = json.loads(result.strip().strip('```json').strip('```'))
                return [t for t in tables if t["index"] in indices]
        except Exception:
            continue
    
    # Final fallback: keyword-based filtering
    keywords = ['revenue', 'income', 'profit', 'loan', 'balance', '收入', '利润', '余额']
    return [t for t in tables if any(k in t['markdown'].lower() for k in keywords)][:15]


def _extract_structured_data(tables: list, query: str, target_years: list) -> dict:
    """Round 2: Use Pro model to extract structured JSON data."""
    tables_text = ""
    for t in tables:
        tables_text += f"\n--- Table #{t['index']} (context: {t['context']}) ---\n{t['markdown']}\n"
    
    if len(tables_text) > 100000:
        tables_text = tables_text[:100000]
    
    prompt = f"""从以下财务报表表格中提取结构化数据。

用户需求: {query}
目标年份: {target_years}

规则:
1. 输出严格的JSON格式
2. 指标名使用"中文(English)"格式，如"贷款撮合收入(Revenue from loan facilitation)"
3. 数值保持原始数字，不要转换单位
4. 找不到的年份不要编造
5. 在metadata中注明单位

输出格式:
{{
  "data": {{
    "数据组名": {{
      "指标名1": {{"2020": 123, "2021": 456}},
      "指标名2": {{"2020": 789}}
    }}
  }},
  "metadata": {{
    "unit": "千元RMB",
    "years_found": [2020, 2021],
    "notes": "..."
  }}
}}

表格内容:
{tables_text}"""

    result = generate_content(prompt=prompt, max_output_tokens=8000)
    try:
        cleaned = result.strip().strip('```json').strip('```').strip()
        return json.loads(cleaned)
    except Exception as e:
        print(f"      ✗ JSON parse failed: {e}")
        return None


# ============================================================
# Path B: PDF Annual Reports (non-listed institutions)
# ============================================================
def collect_pdf_reports(company: dict, query: str, target_years: list, data_dir: str) -> dict:
    """PDF pipeline: Tavily search PDF → download → LLM extract, with missing year retry."""
    search_name = company.get("search_name", company["name"])
    
    # Search for PDF annual reports (filtered by target years)
    pdf_links = _search_pdf_reports(search_name, target_years)
    if not pdf_links:
        print(f"    ✗ No PDF reports found for {search_name}")
        return None
    
    # Download PDFs
    raw_dir = os.path.join(data_dir, "raw", re.sub(r'[^\w]', '_', search_name))
    os.makedirs(raw_dir, exist_ok=True)
    
    pdf_paths = []
    for link in pdf_links:
        path = _download_pdf(link["url"], raw_dir, link.get("filename", "report.pdf"))
        if path:
            pdf_paths.append(path)
            print(f"    ✓ Downloaded: {os.path.basename(path)}")
    
    if not pdf_paths:
        return None
    
    # Extract data from PDFs
    result = _extract_from_pdfs(pdf_paths, query, target_years)
    
    # Check for missing years and retry search for each missing year
    if result and result.get("data"):
        found_years = set()
        for group in result["data"].values():
            for metric in group.values():
                if isinstance(metric, dict):
                    found_years.update(str(y) for y in metric.keys())
        
        missing = [str(y) for y in target_years if str(y) not in found_years]
        if missing:
            print(f"    Missing years: {missing}, searching specifically...")
            for year in missing:
                retry_links = _search_pdf_reports(search_name, [int(year)])
                for link in retry_links:
                    if link.get("url") not in [l.get("url") for l in pdf_links]:
                        path = _download_pdf(link["url"], raw_dir, link.get("filename", "report.pdf"))
                        if path:
                            print(f"    ✓ Retry downloaded: {os.path.basename(path)}")
                            extra = _extract_from_pdfs([path], query, target_years)
                            if extra and extra.get("data"):
                                for g, metrics in extra["data"].items():
                                    if g not in result["data"]:
                                        result["data"][g] = {}
                                    for m, years in metrics.items():
                                        if m not in result["data"][g]:
                                            result["data"][g][m] = {}
                                        for y, v in years.items():
                                            if y not in result["data"][g][m]:
                                                result["data"][g][m][y] = v
    
    return result


def _search_pdf_reports(company_name: str, target_years: list) -> list:
    """Search for PDF annual reports via Tavily, filtered by target years."""
    min_year = str(min(target_years))
    max_year = str(max(target_years))
    try:
        resp = requests.post("https://api.tavily.com/search", json={
            "api_key": TAVILY_API_KEY,
            "query": f'{company_name} 年度报告 PDF 下载 年报 {min_year}-{max_year}',
            "max_results": len(target_years) + 5,
        }, timeout=30)
        data = resp.json()
        
        results = []
        seen_years = set()
        for r in data.get("results", []):
            url = r.get("url", "")
            title = r.get("title", "")
            # Filter for PDF links
            if url.endswith('.pdf') or 'pdf' in url.lower():
                # Extract year from title or URL
                year_match = re.search(r'20[12]\d', title + url)
                year = year_match.group() if year_match else ""
                # Only include PDFs within target year range
                if year and year not in seen_years and min_year <= year <= max_year:
                    seen_years.add(year)
                    results.append({
                        "url": url,
                        "title": title,
                        "year": year,
                        "filename": f"{company_name}_{year}_annual_report.pdf",
                    })
        print(f"    Found {len(results)} PDF reports in range [{min_year}-{max_year}]: {sorted(seen_years, reverse=True)}")
        return results
    except Exception as e:
        print(f"    ✗ PDF search failed: {e}")
        return []


def _download_pdf(url: str, output_dir: str, filename: str) -> str:
    """Download PDF file. Uses verify=False to bypass SSL cert issues on Windows."""
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    filepath = os.path.join(output_dir, filename)
    if os.path.exists(filepath) and os.path.getsize(filepath) > 10000:
        return filepath
    try:
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=60, stream=True, verify=False)
        resp.raise_for_status()
        with open(filepath, 'wb') as f:
            for chunk in resp.iter_content(8192):
                f.write(chunk)
        return filepath
    except Exception as e:
        print(f"    ✗ Download failed: {e}")
        return None


def _extract_from_pdfs(pdf_paths: list, query: str, target_years: list) -> dict:
    """Extract data from PDF annual reports with unit normalization."""
    try:
        import pdfplumber
    except ImportError:
        print("    ✗ pdfplumber not installed (pip install pdfplumber)")
        return None
    
    UNIT_TO_QIAN = {
        '千元': 1, '元': 0.001, '万元': 10,
        '百万元': 1000, '亿元': 100000,
        'thousands': 1, 'millions': 1000, 'billions': 1000000,
    }
    
    all_data = {}
    target_unit = "千元"
    
    for pdf_path in pdf_paths:
        print(f"    [PDF Extract] {os.path.basename(pdf_path)}...")
        try:
            text = ""
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages[:80]:
                    tables = page.extract_tables()
                    for table in tables:
                        rows = ['| ' + ' | '.join(str(c or '') for c in row) + ' |' for row in table]
                        text += '\n'.join(rows) + '\n\n'
                    pt = page.extract_text()
                    if pt:
                        text += pt + '\n'
            
            if len(text) > 200000:
                text = text[:200000]
            
            prompt = f"""从以下PDF年报文本中提取结构化数据。

用户需求: {query}
目标年份: {target_years}

必须输出严格的JSON格式如下（不要自定义格式）:
{{
  "data": {{
    "数据组名": {{
      "指标名(English)": {{"2020": 数值, "2021": 数值}}
    }}
  }},
  "metadata": {{"unit": "原始单位如万元/千元/亿元", "notes": ""}}
}}

规则:
- 年份做key，数值做value，不要用数组
- 在metadata.unit中写年报中实际使用的单位
- 不要编造数据
- 只输出JSON，不要输出其他文字

{text[:150000]}"""

            # Retry up to 2 times for PDF extraction
            parsed = None
            for attempt in range(2):
                result = generate_content(prompt=prompt, max_output_tokens=8000)
                if not result:
                    print(f"      ⚠ Attempt {attempt+1}: empty response, retrying...")
                    continue
                try:
                    cleaned = result.strip().strip('```json').strip('```').strip()
                    parsed = json.loads(cleaned)
                    parsed = _normalize_extracted_json(parsed)
                    break
                except Exception as e:
                    print(f"      ⚠ Attempt {attempt+1}: JSON parse failed ({e}), retrying...")
            
            if parsed and parsed.get("data"):
                # Unit normalization
                this_unit = parsed.get("metadata", {}).get("unit", "千元")
                multiplier = 1
                for unit_key, mult in UNIT_TO_QIAN.items():
                    if unit_key in this_unit:
                        multiplier = mult
                        break
                
                for group, metrics in parsed["data"].items():
                    if group not in all_data:
                        all_data[group] = {}
                    for metric, years in metrics.items():
                        if metric not in all_data[group]:
                            all_data[group][metric] = {}
                        for year, val in years.items():
                            if year not in all_data[group][metric]:
                                try:
                                    all_data[group][metric][year] = round(float(val) * multiplier, 2)
                                except (ValueError, TypeError):
                                    all_data[group][metric][year] = val
                
                print(f"      ✓ Extracted {sum(len(m) for m in parsed['data'].values())} metrics")
            else:
                print(f"      ✗ No structured data extracted from this PDF")
        except Exception as e:
            print(f"      ✗ PDF extraction failed: {e}")
    
    return {"data": all_data, "metadata": {"unit": target_unit}} if all_data else None


# ============================================================
# Path C: Web Search Fallback
# ============================================================
def collect_web_search(company: dict, query: str, target_years: list) -> dict:
    """Web search pipeline: multi-query → LLM summarize."""
    search_name = company.get("search_name", company["name"])
    current_year = datetime.now().year
    
    queries = [
        f"{search_name} 年度 收入 净利润 {current_year} 财务数据",
        f"{search_name} 贷款余额 信贷 规模",
        f"{search_name} 财报 营收 利润 历年 变化",
        f"{search_name} financial results revenue profit",
    ]
    
    all_content = []
    for q in queries:
        try:
            resp = requests.post("https://api.tavily.com/search", json={
                "api_key": TAVILY_API_KEY,
                "query": q,
                "max_results": 5,
                "include_raw_content": True,
            }, timeout=30)
            data = resp.json()
            for r in data.get("results", []):
                content = r.get("raw_content", r.get("content", ""))[:5000]
                if content:
                    all_content.append(f"Source: {r.get('url', '')}\n{content}")
        except Exception:
            continue
    
    if not all_content:
        print(f"    ✗ No web results for {search_name}")
        return None
    
    print(f"    Found {len(all_content)} web articles")
    
    combined = '\n\n---\n\n'.join(all_content[:20])
    if len(combined) > 150000:
        combined = combined[:150000]
    
    prompt = f"""从搜索结果中提取{search_name}的财务数据:
用户需求: {query}
目标年份: {target_years}

规则:
- 不同来源冲突时选最权威/最新的
- 找不到的不编造
- 在metadata的notes中标注数据可靠性(high/medium/low)
- 输出严格JSON格式，指标名用"中文(English)"

必须使用以下格式（不要自定义key名）:
{{
  "data": {{
    "数据组名": {{
      "指标名": {{"2020": 值, "2021": 值}}
    }}
  }},
  "metadata": {{"unit": "...", "notes": "...", "reliability": "medium"}}
}}

重要: 即使数据稀少也要用上述格式。年份做key，数值做value。

{combined}"""

    result = generate_content(prompt=prompt, max_output_tokens=8000)
    if not result:
        print(f"    ✗ LLM returned empty response")
        return None
    
    try:
        parsed = json.loads(result.strip().strip('```json').strip('```').strip())
        # Normalize: if LLM used a custom top-level key instead of "data"
        parsed = _normalize_extracted_json(parsed)
        if parsed and parsed.get("data"):
            metrics_count = sum(
                len(yrs) for g in parsed["data"].values()
                for m, yrs in g.items() if isinstance(yrs, dict)
            )
            print(f"    ✓ Extracted {metrics_count} data points (web search)")
        return parsed
    except Exception as e:
        print(f"    ✗ JSON parse failed: {e}")
        # Try to salvage: ask LLM to reformat
        return _try_reformat_response(result)


# ============================================================
# Path D: CN-Listed (reuse collect_financials.py)
# ============================================================
def collect_cn_listed(company: dict, query: str, target_years: list, data_dir: str) -> dict:
    """CN-listed: use existing collect_financials.py."""
    from collect_financials import run_collection
    ticker = company["ticker"]
    output_path = os.path.join(data_dir, f"cn_{ticker}.json")
    result = run_collection(ticker=ticker, output_path=output_path)
    
    if result:
        # Convert to Type 8 format
        data = {}
        if result.get("financials", {}).get("income_statement"):
            data["利润表(Income Statement)"] = {}
            for year, vals in result["financials"]["income_statement"].items():
                for k, v in vals.items():
                    if k != "source":
                        label = k
                        if label not in data["利润表(Income Statement)"]:
                            data["利润表(Income Statement)"][label] = {}
                        data["利润表(Income Statement)"][label][year] = v
        
        if result.get("financials", {}).get("indicators"):
            data["财务指标(Financial Indicators)"] = {}
            for year, vals in result["financials"]["indicators"].items():
                for k, v in vals.items():
                    if k != "source":
                        if k not in data["财务指标(Financial Indicators)"]:
                            data["财务指标(Financial Indicators)"][k] = {}
                        data["财务指标(Financial Indicators)"][k][year] = v
        
        if result.get("market_data"):
            data["市场数据(Market Data)"] = {
                "当前价格(Current Price)": {"latest": result["market_data"].get("price", "")},
            }
        
        return {"data": data, "metadata": {"source": "cn_listed:eastmoney_f10"}} if data else None
    return None


# ============================================================
# Report Generation (Word)
# ============================================================
def _format_number(val) -> str:
    """Format number with thousand separators. Handles int, float, str."""
    if val == "" or val is None:
        return "-"
    try:
        num = float(val)
        if num == int(num):
            return f"{int(num):,}"
        return f"{num:,.2f}"
    except (ValueError, TypeError):
        return str(val)


def _flatten_value(val) -> str:
    """Flatten nested dicts/lists into a readable string for table cells."""
    if isinstance(val, dict):
        # e.g. {'2023': 123, '2024': 456} -> should not appear as cell value
        # But if it does, format as 'k1: v1, k2: v2'
        parts = [f"{k}: {_format_number(v)}" for k, v in val.items()]
        return "; ".join(parts)
    elif isinstance(val, list):
        return ", ".join(str(v) for v in val)
    else:
        return _format_number(val)


def _set_cell_font(cell, size=None, cn_font='SimSun', en_font='Arial'):
    """Set cell font to 宋体+Arial."""
    from docx.shared import Pt
    from docx.oxml.ns import qn
    if size is None:
        size = Pt(9)
    for paragraph in cell.paragraphs:
        for run in paragraph.runs:
            run.font.size = size
            run.font.name = en_font
            run.element.rPr.rFonts.set(qn('w:eastAsia'), cn_font)


def generate_word_report(company_results: dict, query: str, years: int, output_dir: str) -> str:
    """Generate Word report with analysis + data tables."""
    from docx import Document
    from docx.shared import Pt, Cm, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml.ns import qn
    
    doc = Document()
    
    # Style: 中文宋体, 英文Arial
    style = doc.styles['Normal']
    style.font.name = 'Arial'
    style.font.size = Pt(10.5)
    style.element.rPr.rFonts.set(qn('w:eastAsia'), 'SimSun')
    
    # Title
    title = doc.add_heading(f'财务数据提取报告', level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for run in title.runs:
        run.font.name = 'Arial'
        run.element.rPr.rFonts.set(qn('w:eastAsia'), 'SimSun')
    
    doc.add_paragraph(f'查询: {query}')
    doc.add_paragraph(f'时间范围: 近{years}年')
    doc.add_paragraph(f'生成日期: {datetime.now().strftime("%Y-%m-%d")}')
    doc.add_paragraph(f'公司: {", ".join(company_results.keys())}')
    
    # Part 1: LLM Analysis (structured by user query dimensions)
    doc.add_heading('一、核心发现与分析', level=1)
    
    all_data_for_analysis = json.dumps(
        {k: v.get("data", {}) for k, v in company_results.items() if v},
        ensure_ascii=False, indent=2, default=str
    )[:30000]
    
    analysis_prompt = f"""你是资深金融分析师。根据以下数据写分析报告。

用户的问题是: {query}
涵盖公司: {", ".join(company_results.keys())}

按照用户问题的维度来组织分析。例如用户问"分产品余额情况，收入情况和利润"，则分三部分写:
1. 分产品余额情况 - 每家公司的余额规模、变化趋势、CAGR
2. 收入情况 - 每家公司的收入规模、增速、结构变化
3. 利润变化 - 每家公司的利润水平、利润率变化

规则:
- 每个维度写一个小标题（用"一、""二、"开头），然后分公司说明
- 开门见山，只描述事实和数字，不写建议/启示
- 不要用Markdown格式（不要用**加粗、不要用#标题、不要用列表符号）
- 用纯文本写，每个小标题单独一行，正文分段写
- 数字加千分符（如"5,764,513千元"）
- 不要编造数据中没有的内容

数据:
{all_data_for_analysis}"""

    analysis = generate_content(prompt=analysis_prompt, max_output_tokens=6000)
    if analysis:
        # Clean up any residual markdown
        analysis = analysis.replace('**', '').replace('##', '').replace('# ', '')
        for line in analysis.split('\n'):
            line = line.strip()
            if not line:
                continue
            # Detect section headers (e.g. "一、分产品余额情况")
            if re.match(r'^[一二三四五六七八九十]+、', line):
                h = doc.add_heading(line, level=2)
                for run in h.runs:
                    run.font.name = 'Arial'
                    run.element.rPr.rFonts.set(qn('w:eastAsia'), 'SimSun')
            else:
                p = doc.add_paragraph(line)
                for run in p.runs:
                    run.font.size = Pt(10.5)
                    run.font.name = 'Arial'
                    run.element.rPr.rFonts.set(qn('w:eastAsia'), 'SimSun')
    
    # Part 2: Data Appendix Tables
    doc.add_heading('二、详细数据附录', level=1)
    
    appendix_letter = ord('A')
    for company_name, result in company_results.items():
        if not result or not result.get("data"):
            continue
        
        doc.add_heading(f'附录{chr(appendix_letter)}: {company_name}', level=2)
        appendix_letter += 1
        
        unit = result.get("metadata", {}).get("unit", "")
        if unit:
            p = doc.add_paragraph(f'单位: {unit}')
            p.runs[0].bold = True
        
        for group_name, metrics in result["data"].items():
            # Show unit in section heading
            heading_text = f'{group_name}（单位: {unit}）' if unit else group_name
            doc.add_heading(heading_text, level=3)
            
            # Collect all years from leaf-level data only
            all_years = sorted(set(
                str(y) for m in metrics.values()
                if isinstance(m, dict)
                for y in m.keys()
                if re.match(r'^\d{4}$', str(y))  # Only 4-digit year keys
            ), reverse=True)
            
            if not all_years:
                continue
            
            # Create table
            headers = ['指标'] + all_years
            table = doc.add_table(rows=1, cols=len(headers))
            table.style = 'Table Grid'
            
            for i, h in enumerate(headers):
                cell = table.rows[0].cells[i]
                cell.text = h
                run = cell.paragraphs[0].runs[0]
                run.bold = True
                run.font.size = Pt(9)
                run.font.name = 'Arial'
                run.element.rPr.rFonts.set(qn('w:eastAsia'), 'SimSun')
            
            for metric_name, years_data in metrics.items():
                if not isinstance(years_data, dict):
                    continue
                # Skip if this metric has no year-keyed data
                year_keys = [k for k in years_data.keys() if re.match(r'^\d{4}$', str(k))]
                if not year_keys:
                    continue
                
                row = table.add_row()
                row.cells[0].text = metric_name
                _set_cell_font(row.cells[0])
                
                for i, year in enumerate(all_years, 1):
                    val = years_data.get(year, years_data.get(int(year) if year.isdigit() else year, ""))
                    cell = row.cells[i]
                    cell.text = _flatten_value(val)
                    _set_cell_font(cell)
            
            doc.add_paragraph()  # spacing
    
    # Part 3: Data Source Description
    doc.add_heading('三、数据来源说明', level=1)
    
    source_descriptions = {
        'sec_edgar': 'SEC EDGAR 美国证券交易委员会电子数据库（年报 20-F/10-K 表格提取）',
        'cn_listed': '东方财富 East Money F10 财务数据接口',
        'pdf_search': '年度报告 PDF（经 Tavily 搜索发现并下载，由 LLM 提取结构化数据）',
        'web_search': '公开网络信息（经 Tavily 搜索聚合，由 LLM 提取结构化数据）',
    }
    
    for company_name, result in company_results.items():
        if not result:
            continue
        
        metadata = result.get('metadata', {})
        source_type = metadata.get('source', '').split(':')[0] if metadata.get('source') else ''
        source_desc = source_descriptions.get(source_type, '未知来源')
        unit = metadata.get('unit', '')
        notes = metadata.get('notes', '')
        reliability = metadata.get('reliability', '')
        
        p = doc.add_paragraph()
        run = p.add_run(f'{company_name}')
        run.bold = True
        run.font.size = Pt(10.5)
        run.font.name = 'Arial'
        run.element.rPr.rFonts.set(qn('w:eastAsia'), 'SimSun')
        
        details = []
        if source_desc:
            details.append(f'数据源: {source_desc}')
        if unit:
            details.append(f'原始单位: {unit}')
        if reliability:
            details.append(f'可靠性: {reliability}')
        
        for detail in details:
            dp = doc.add_paragraph(f'  {detail}')
            for run in dp.runs:
                run.font.size = Pt(9)
                run.font.name = 'Arial'
                run.element.rPr.rFonts.set(qn('w:eastAsia'), 'SimSun')
        
        if notes:
            np = doc.add_paragraph(f'  备注: {notes[:300]}')
            for run in np.runs:
                run.font.size = Pt(8)
                run.font.name = 'Arial'
                run.element.rPr.rFonts.set(qn('w:eastAsia'), 'SimSun')
                run.font.color.rgb = RGBColor(128, 128, 128)
    
    # Disclaimer
    doc.add_paragraph()
    disclaimer = doc.add_paragraph('免责声明: 本报告数据由自动化程序从公开渠道提取，可能存在提取误差，仅供参考。建议对关键数据回溯原始文件进行核实。')
    for run in disclaimer.runs:
        run.font.size = Pt(8)
        run.font.name = 'Arial'
        run.element.rPr.rFonts.set(qn('w:eastAsia'), 'SimSun')
        run.font.color.rgb = RGBColor(128, 128, 128)
    
    # Save
    os.makedirs(output_dir, exist_ok=True)
    filename = f"financial_data_{datetime.now().strftime('%Y%m%d')}.docx"
    filepath = os.path.join(output_dir, filename)
    doc.save(filepath)
    return filepath


# ============================================================
# Main Pipeline
# ============================================================
def run_pipeline(companies: list, query: str, years: int = 5, output_dir: str = None):
    """
    Main entry point: multi-company financial data extraction.
    
    Args:
        companies: List of company names (any language)
        query: What data to extract (e.g., "分产品收入和利润")
        years: How many years of data
        output_dir: Where to save results
    """
    if not output_dir:
        output_dir = os.path.join(SCRIPT_DIR, "..", "data", "type8_results")
    
    data_dir = os.path.join(output_dir, "data")
    os.makedirs(data_dir, exist_ok=True)
    
    current_year = datetime.now().year
    target_years = list(range(current_year - years, current_year + 1))
    
    print("=" * 60)
    print(f"Type 8: Financial Data Extraction")
    print(f"  Companies: {companies}")
    print(f"  Query: {query}")
    print(f"  Years: {target_years}")
    print("=" * 60)
    
    company_results = {}
    
    for name in companies:
        print(f"\n{'─' * 40}")
        print(f"Processing: {name}")
        print(f"{'─' * 40}")
        
        # Dynamic data source detection
        company = detect_data_source(name)
        source = company["source"]
        
        try:
            if source == "sec_edgar":
                result = collect_sec_edgar(company, query, target_years, data_dir)
            elif source == "cn_listed":
                result = collect_cn_listed(company, query, target_years, data_dir)
            elif source == "pdf_search":
                result = collect_pdf_reports(company, query, target_years, data_dir)
            elif source == "web_search":
                result = collect_web_search(company, query, target_years)
            else:
                result = None
            
            # Ensure metadata has source type for report footer
            if result and isinstance(result, dict):
                if 'metadata' not in result:
                    result['metadata'] = {}
                if 'source' not in result.get('metadata', {}):
                    result['metadata']['source'] = source
            
            company_results[name] = result
            
            if result and result.get("data"):
                groups = list(result["data"].keys())
                total_metrics = sum(len(m) for g in result["data"].values() for m in g.values() if isinstance(m, dict))
                print(f"  ✓ Success: {len(groups)} groups, ~{total_metrics} data points")
            else:
                print(f"  ✗ No data extracted")
        
        except Exception as e:
            print(f"  ✗ Pipeline error: {e}")
            company_results[name] = None
    
    # Save raw JSON
    json_path = os.path.join(output_dir, "extracted_data.json")
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(company_results, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n  [JSON] {json_path}")
    
    # Generate Word report
    try:
        word_path = generate_word_report(company_results, query, years, output_dir)
        print(f"  [Word] {word_path}")
    except Exception as e:
        print(f"  [Word] Failed: {e}")
        word_path = None
    
    print(f"\n{'=' * 60}")
    print("PIPELINE COMPLETE")
    for name, result in company_results.items():
        status = "✓" if result and result.get("data") else "✗"
        source = detect_data_source(name)["source"] if result else "failed"
        print(f"  {status} {name} [{source}]")
    print(f"{'=' * 60}")
    
    return company_results


# ============================================================
# CLI Entry Point
# ============================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Type 8: Financial Data Extraction")
    parser.add_argument("--companies", required=True,
                        help="Comma-separated company names (e.g., '蚂蚁集团,微众银行,奇富科技')")
    parser.add_argument("--query", default="分产品收入和利润",
                        help="What data to extract (e.g., '分产品收入和利润')")
    parser.add_argument("--years", type=int, default=5,
                        help="Number of years (default: 5)")
    parser.add_argument("--output", default=None,
                        help="Output directory")
    parser.add_argument("--mode", choices=["annual", "earnings"], default="annual",
                        help="annual=年报数据提取(default), earnings=季度业绩分析")
    
    args = parser.parse_args()
    companies = [c.strip() for c in args.companies.split(",")]
    
    if args.mode == "earnings":
        # Route to quarterly earnings analysis pipeline
        from collect_earnings import run_earnings_pipeline
        run_earnings_pipeline(
            companies=companies,
            query=args.query,
            output_dir=args.output,
        )
    else:
        # Default: annual data extraction
        run_pipeline(
            companies=companies,
            query=args.query,
            years=args.years,
            output_dir=args.output,
        )
