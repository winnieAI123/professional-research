"""
Unified Financial Data Collection Script
Usage:
    python collect_financials.py --ticker 300418 --output data/fin.json      # A股
    python collect_financials.py --ticker AAPL --output data/fin.json        # 美股
    python collect_financials.py --ticker 0700.HK --output data/fin.json    # 港股
    python collect_financials.py --company "昆仑万维" --output data/fin.json # 自动识别

Auto-routes to appropriate data source:
  A-stock → akshare (fallback: Sina Finance → Tencent Finance)
  US/HK stock → yfinance (+ optional SEC EDGAR verification)
"""

import sys, os, json, re, argparse
from datetime import datetime

os.environ["PYTHONIOENCODING"] = "utf-8"


# ============================================================
# Stock Type Identification
# ============================================================
def identify_stock_type(ticker: str) -> str:
    """
    Identify stock type from ticker string.
    Returns: 'a_stock', 'us_stock', 'hk_stock', 'unknown'
    """
    ticker = ticker.strip().upper()
    
    # A-stock: 6-digit number, optionally with .SZ/.SH/.BJ suffix
    clean = re.sub(r'\.(SZ|SH|BJ)$', '', ticker)
    if re.match(r'^\d{6}$', clean):
        return 'a_stock'
    
    # HK stock: ends with .HK
    if ticker.endswith('.HK'):
        return 'hk_stock'
    
    # US stock: pure letters (1-5 chars)
    if re.match(r'^[A-Z]{1,5}$', ticker):
        return 'us_stock'
    
    return 'unknown'


def normalize_a_stock_ticker(ticker: str) -> str:
    """Normalize A-stock ticker to pure 6-digit format."""
    return re.sub(r'\.(SZ|SH|BJ)$', '', ticker.strip()).zfill(6)


# ============================================================
# A-Stock Data Collection
# Strategy: akshare (company info only) + Sina/Tencent (market data) + EastMoney HTTP (financials)
# ============================================================
def collect_a_stock(ticker: str) -> dict:
    """Collect A-stock financial data from multiple fast sources."""
    code = normalize_a_stock_ticker(ticker)
    result = {
        "source": "a_stock",
        "ticker": code,
        "company_info": {},
        "financials": {},
        "market_data": {},
        "holders": {},
    }
    
    # Step 1: akshare for company info (fast, single-stock query)
    print(f"  [Step 1] akshare company info for {code}...")
    _try_akshare_info_only(code, result)
    
    # Step 2: Sina/Tencent for market data (single-stock, seconds)
    print(f"  [Step 2] Sina/Tencent market data for {code}...")
    if not result["market_data"]:
        _try_sina_finance(code, result)
    if not result["market_data"].get("price"):
        _try_tencent_finance(code, result)
    
    # Step 3: EastMoney HTTP for financial statements (direct, no akshare)
    print(f"  [Step 3] EastMoney financial statements for {code}...")
    _try_eastmoney_financials(code, result)
    
    # Note: akshare holders (stock_gdfx_holding_analyse_em) disabled because
    # it loads 11,994 rows (full A-stock holder list), taking 5+ minutes.
    # Holders data is non-critical for company research reports.
    
    return result


def _try_akshare_info_only(code: str, result: dict):
    """akshare: only company info (fast, no full-list load)."""
    try:
        import akshare as ak
        info = ak.stock_individual_info_em(symbol=code)
        if info is not None and not info.empty:
            info_dict = dict(zip(info["item"], info["value"]))
            result["company_info"].update({
                "name": info_dict.get("股票简称", ""),
                "industry": info_dict.get("行业", ""),
                "total_market_cap": info_dict.get("总市值", ""),
                "circulating_market_cap": info_dict.get("流通市值", ""),
                "pe_ratio": info_dict.get("市盈率(动态)", ""),
                "pb_ratio": info_dict.get("市净率", ""),
                "listing_date": info_dict.get("上市时间", ""),
                "source": "akshare:stock_individual_info_em",
            })
            print(f"    ✓ Company info: {info_dict.get('股票简称', 'N/A')}")
    except Exception as e:
        print(f"    ✗ akshare company info failed: {e}")


def _try_akshare_holders(code: str, result: dict):
    """akshare: top 10 holders (handles parameter name changes)."""
    try:
        import akshare as ak
        holders = None
        # Try different parameter names (akshare changes these)
        for param_name in ['symbol', 'stock']:
            try:
                holders = ak.stock_gdfx_holding_analyse_em(**{param_name: code})
                break
            except TypeError:
                continue
        if holders is None:
            # Try positional argument
            try:
                holders = ak.stock_gdfx_holding_analyse_em(code)
            except Exception:
                pass
        if holders is not None and not holders.empty:
            top_holders = []
            for _, row in holders.head(10).iterrows():
                top_holders.append({
                    "name": str(row.iloc[0] if len(row) > 0 else ""),
                    "shares": str(row.iloc[1] if len(row) > 1 else ""),
                    "pct": str(row.iloc[2] if len(row) > 2 else ""),
                })
            result["holders"]["top_10"] = top_holders
            print(f"    ✓ Top holders: {len(top_holders)}")
        else:
            print(f"    ✗ No holder data returned")
    except Exception as e:
        print(f"    ✗ akshare holders failed: {e}")


def _try_eastmoney_financials(code: str, result: dict):
    """
    EastMoney F10 API — proven to work for A-stock financials.
    Uses emweb.securities.eastmoney.com (the same API as the F10 page).
    """
    import requests
    
    mkt = "SZ" if code.startswith(("0", "3")) else "SH"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://emweb.securities.eastmoney.com",
    }
    
    # --- Main Financial Indicators (主要指标) ---
    try:
        url = f"https://emweb.securities.eastmoney.com/PC_HSF10/NewFinanceAnalysis/ZYZBAjaxNew?type=0&code={mkt}{code}"
        resp = requests.get(url, headers=headers, timeout=15)
        data = resp.json()
        
        items = data if isinstance(data, list) else data.get("data", [])
        
        if items:
            years_data = {}
            indicators_data = {}
            for row in items:
                date = row.get("REPORT_DATE", "")
                rtype = row.get("REPORT_DATE_NAME", "")
                if "年报" in rtype or "12-31" in date:
                    year = date[:4] if date else ""
                    if not year:
                        continue
                    years_data[year] = {
                        "revenue": _fmt_num(row.get("TOTALOPERATEREVE")),
                        "operating_profit": _fmt_num(row.get("OPERATEPROFIT")),
                        "net_profit": _fmt_num(row.get("PARENTNETPROFIT")),
                        "net_profit_deducted": _fmt_num(row.get("KCFJCXSYJLR")),
                        "eps": str(row.get("EPSJB", "")),
                        "eps_diluted": str(row.get("EPSKCJB", "")),
                        "source": "eastmoney:F10_ZYZB",
                    }
                    indicators_data[year] = {
                        "roe": str(row.get("ROEJQ", "")),
                        "gross_margin": str(row.get("XSMLL", "")),
                        "net_margin": str(row.get("XSJLL", "")),
                        "bps": str(row.get("BPS", "")),
                        "source": "eastmoney:F10_ZYZB",
                    }
            
            if years_data:
                result["financials"]["income_statement"] = years_data
                years_list = ', '.join(sorted(years_data.keys(), reverse=True))
                print(f"    ✓ Income statement: {len(years_data)} years ({years_list})")
            if indicators_data:
                result["financials"]["indicators"] = indicators_data
                print(f"    ✓ Key indicators: {len(indicators_data)} years")
        else:
            print(f"    ✗ EastMoney F10 returned no data")
    except Exception as e:
        print(f"    ✗ EastMoney F10 main indicators failed: {e}")
    
    # --- Balance Sheet (from F10 ZYZB, same API — pull asset/equity data) ---
    # Note: separate zcfzbAjaxNew is anti-scraping blocked, so we extract
    # asset data from the main F10 indicators which include these fields
    try:
        if items:
            years_bs = {}
            for row in items:
                date = row.get("REPORT_DATE", "")
                rtype = row.get("REPORT_DATE_NAME", "")
                if "年报" in rtype or "12-31" in date:
                    year = date[:4] if date else ""
                    if not year:
                        continue
                    total_assets = row.get("TOTALASSETS")
                    if total_assets is not None:
                        years_bs[year] = {
                            "total_assets": _fmt_num(total_assets),
                            "bps": str(row.get("BPS", "")),
                            "source": "eastmoney:F10_ZYZB",
                        }
            if years_bs:
                result["financials"]["balance_sheet"] = years_bs
                print(f"    ✓ Balance sheet (from ZYZB): {len(years_bs)} years")
    except Exception as e:
        print(f"    ✗ Balance sheet extraction failed: {e}")


def _fmt_num(val) -> str:
    """Format large numbers for readability."""
    if val is None:
        return ""
    try:
        v = float(val)
        if abs(v) >= 1e8:
            return f"{v/1e8:.2f}亿"
        elif abs(v) >= 1e4:
            return f"{v/1e4:.2f}万"
        return f"{v:.2f}"
    except (ValueError, TypeError):
        return str(val)


def _try_sina_finance(code: str, result: dict):
    """Fallback: Sina Finance HTTP API for A-stocks."""
    import requests
    
    try:
        # Sina real-time quote API
        prefix = "sh" if code.startswith(("6", "9")) else "sz"
        url = f"https://hq.sinajs.cn/list={prefix}{code}"
        headers = {"Referer": "https://finance.sina.com.cn"}
        resp = requests.get(url, headers=headers, timeout=10)
        resp.encoding = "gbk"
        
        if resp.status_code == 200 and "var hq_str" in resp.text:
            data = resp.text.split('"')[1].split(',')
            if len(data) > 30:
                if not result["company_info"].get("name"):
                    result["company_info"]["name"] = data[0]
                result["market_data"].update({
                    "price": data[3],
                    "open": data[1],
                    "close_prev": data[2],
                    "high": data[4],
                    "low": data[5],
                    "volume": data[8],
                    "turnover": data[9],
                    "date": data[30],
                    "source": "sina_finance",
                })
                print(f"    ✓ Sina market data: price={data[3]}")
    except Exception as e:
        print(f"    ✗ Sina Finance failed: {e}")


def _try_tencent_finance(code: str, result: dict):
    """Fallback: Tencent Finance HTTP API for A-stocks."""
    import requests
    
    try:
        prefix = "sh" if code.startswith(("6", "9")) else "sz"
        url = f"https://qt.gtimg.cn/q={prefix}{code}"
        resp = requests.get(url, timeout=10)
        resp.encoding = "gbk"
        
        if resp.status_code == 200 and "v_" in resp.text:
            data = resp.text.split('~')
            if len(data) > 45:
                if not result["company_info"].get("name"):
                    result["company_info"]["name"] = data[1]
                result["market_data"].update({
                    "price": data[3],
                    "close_prev": data[4],
                    "open": data[5],
                    "volume": data[6],
                    "turnover": data[37],
                    "pe": data[39],
                    "pb": data[46] if len(data) > 46 else "",
                    "total_market_cap": data[45] if len(data) > 45 else "",
                    "source": "tencent_finance",
                })
                print(f"    ✓ Tencent market data: price={data[3]}")
    except Exception as e:
        print(f"    ✗ Tencent Finance failed: {e}")


# ============================================================
# US/HK Stock Data Collection (yfinance)
# ============================================================
def collect_us_hk_stock(ticker: str) -> dict:
    """Collect US or HK stock data via yfinance."""
    result = {
        "source": "us_hk_stock",
        "ticker": ticker,
        "company_info": {},
        "financials": {},
        "market_data": {},
        "holders": {},
        "analyst": {},
    }
    
    try:
        import yfinance as yf
        
        stock = yf.Ticker(ticker)
        info = stock.info
        
        if not info or info.get("regularMarketPrice") is None:
            print(f"    ✗ yfinance returned no data for {ticker}")
            return result
        
        # Company info
        result["company_info"] = {
            "name": info.get("longName", info.get("shortName", "")),
            "industry": info.get("industry", ""),
            "sector": info.get("sector", ""),
            "employees": info.get("fullTimeEmployees", ""),
            "country": info.get("country", ""),
            "website": info.get("website", ""),
            "description": info.get("longBusinessSummary", "")[:500],
            "total_market_cap": info.get("marketCap", ""),
            "pe_ratio": info.get("trailingPE", ""),
            "forward_pe": info.get("forwardPE", ""),
            "pb_ratio": info.get("priceToBook", ""),
            "dividend_yield": info.get("dividendYield", ""),
            "source": "yfinance",
        }
        print(f"    ✓ Company info: {result['company_info']['name']}")
        
        # Market data
        result["market_data"] = {
            "price": str(info.get("regularMarketPrice", "")),
            "currency": info.get("currency", "USD"),
            "high_52w": str(info.get("fiftyTwoWeekHigh", "")),
            "low_52w": str(info.get("fiftyTwoWeekLow", "")),
            "avg_volume": str(info.get("averageVolume", "")),
            "beta": str(info.get("beta", "")),
            "source": "yfinance",
        }
        print(f"    ✓ Market data: price={result['market_data']['price']}")
        
        # Financials (income statement)
        try:
            fin = stock.financials
            if fin is not None and not fin.empty:
                years_data = {}
                for col in fin.columns:
                    year = str(col.year) if hasattr(col, 'year') else str(col)[:4]
                    years_data[year] = {}
                    for idx in fin.index:
                        val = fin.loc[idx, col]
                        if val is not None and str(val) != "nan":
                            years_data[year][idx] = str(int(val)) if abs(val) > 1 else str(val)
                    years_data[year]["source"] = "yfinance:financials"
                result["financials"]["income_statement"] = years_data
                print(f"    ✓ Income statement: {len(years_data)} years")
        except Exception as e:
            print(f"    ✗ Financials failed: {e}")
        
        # Balance sheet
        try:
            bs = stock.balance_sheet
            if bs is not None and not bs.empty:
                years_data = {}
                for col in bs.columns:
                    year = str(col.year) if hasattr(col, 'year') else str(col)[:4]
                    years_data[year] = {}
                    for idx in bs.index:
                        val = bs.loc[idx, col]
                        if val is not None and str(val) != "nan":
                            years_data[year][idx] = str(int(val)) if abs(val) > 1 else str(val)
                    years_data[year]["source"] = "yfinance:balance_sheet"
                result["financials"]["balance_sheet"] = years_data
                print(f"    ✓ Balance sheet: {len(years_data)} years")
        except Exception as e:
            print(f"    ✗ Balance sheet failed: {e}")
        
        # Institutional holders
        try:
            inst = stock.institutional_holders
            if inst is not None and not inst.empty:
                holders_list = []
                for _, row in inst.head(10).iterrows():
                    holders_list.append({
                        "name": str(row.get("Holder", "")),
                        "shares": str(row.get("Shares", "")),
                        "pct": str(row.get("% Out", "")),
                    })
                result["holders"]["institutional"] = holders_list
                print(f"    ✓ Institutional holders: {len(holders_list)}")
        except Exception as e:
            print(f"    ✗ Holders failed: {e}")
        
        # Analyst recommendations
        try:
            rec = stock.recommendations
            if rec is not None and not rec.empty:
                recent = rec.tail(5)
                recs = []
                for _, row in recent.iterrows():
                    recs.append({
                        "firm": str(row.get("Firm", "")),
                        "grade": str(row.get("To Grade", "")),
                        "date": str(row.name)[:10] if hasattr(row, 'name') else "",
                    })
                result["analyst"]["recommendations"] = recs
                print(f"    ✓ Analyst recs: {len(recs)}")
        except Exception as e:
            print(f"    ✗ Recommendations failed: {e}")
    
    except ImportError:
        print("    ✗ yfinance not installed. Run: python -m pip install yfinance")
    except Exception as e:
        print(f"    ✗ yfinance general error: {e}")
    
    return result


# ============================================================
# Company Name → Ticker Resolution (fast, no full-list load)
# ============================================================
def resolve_company_to_ticker(company_name: str) -> tuple:
    """
    Resolve company name to ticker and stock type.
    Uses EastMoney search API (fast) instead of loading full A-stock list.
    Returns: (ticker, stock_type)
    """
    import requests
    
    print(f"  Resolving '{company_name}' to ticker...")
    
    # Method 1: EastMoney search API (fast, JSON)
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
                name = item.get("Name", "")
                market = item.get("MktNum", "")
                # Filter for A-stock markets (0=SZ, 1=SH)
                if market in ("0", "1") and re.match(r'^\d{6}$', code):
                    print(f"  ✓ Resolved: {name} → {code} (A-stock, via EastMoney)")
                    return code, "a_stock"
    except Exception as e:
        print(f"  ✗ EastMoney search failed: {e}")
    
    # Method 2: Try akshare keyword search (lighter than full list)
    try:
        import akshare as ak
        result = ak.stock_info_a_code_name()
        if result is not None and not result.empty:
            match = result[result["name"].str.contains(company_name, na=False)]
            if not match.empty:
                ticker = match.iloc[0]["code"]
                name = match.iloc[0]["name"]
                print(f"  ✓ Resolved: {name} → {ticker} (A-stock, via akshare)")
                return ticker, "a_stock"
    except Exception as e:
        print(f"  ✗ akshare lookup failed: {e}")
    
    print(f"  ✗ Could not resolve '{company_name}' to ticker automatically")
    return None, "unknown"


# ============================================================
# Main Pipeline
# ============================================================
def run_collection(company: str = None, ticker: str = None, output_path: str = None) -> dict:
    """
    Main entry point. Accepts company name or ticker.
    """
    print(f"\n{'=' * 60}")
    print(f"Financial Data Collection Pipeline")
    print(f"{'=' * 60}")
    
    # Resolve input
    if ticker:
        stock_type = identify_stock_type(ticker)
        print(f"  Input: ticker={ticker}, type={stock_type}")
    elif company:
        ticker, stock_type = resolve_company_to_ticker(company)
        if not ticker:
            print(f"  Could not resolve company name. Returning empty result.")
            return {"error": f"Could not resolve '{company}' to ticker", "source": "none"}
    else:
        raise ValueError("Must provide --company or --ticker")
    
    # Route to appropriate collector
    if stock_type == "a_stock":
        result = collect_a_stock(ticker)
    elif stock_type in ("us_stock", "hk_stock"):
        result = collect_us_hk_stock(ticker)
    else:
        result = {"error": f"Unknown stock type for '{ticker}'", "source": "unknown"}
    
    # Add metadata
    result["_metadata"] = {
        "collection_time": datetime.now().isoformat(),
        "input_company": company,
        "input_ticker": ticker,
        "stock_type": stock_type,
    }
    
    # Save
    if output_path:
        os.makedirs(os.path.dirname(output_path), exist_ok=True) if os.path.dirname(output_path) else None
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2, default=str)
        print(f"\n  [Saved] {output_path}")
    
    # Summary
    info_fields = len([v for v in result.get("company_info", {}).values() if v])
    fin_sections = len(result.get("financials", {}))
    market_fields = len([v for v in result.get("market_data", {}).values() if v])
    
    print(f"\n{'=' * 60}")
    print(f"Collection complete:")
    print(f"  Company info fields: {info_fields}")
    print(f"  Financial sections: {fin_sections}")
    print(f"  Market data fields: {market_fields}")
    print(f"  Holders: {'Yes' if result.get('holders') else 'No'}")
    print(f"{'=' * 60}\n")
    
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Unified Financial Data Collection")
    parser.add_argument("--company", default=None, help="Company name (auto-resolves to ticker)")
    parser.add_argument("--ticker", default=None, help="Stock ticker (e.g., 300418, AAPL, 0700.HK)")
    parser.add_argument("--output", default="financial_data.json", help="Output JSON path")
    
    args = parser.parse_args()
    
    if not args.company and not args.ticker:
        parser.error("Must provide --company or --ticker")
    
    run_collection(
        company=args.company,
        ticker=args.ticker,
        output_path=args.output,
    )
