"""
Multi-Source Leaderboard Scraper
================================
Scrapes AI model leaderboard data from 3 sources:
  1. LMArena (arena.ai)     - HTML table parsing
  2. ArtificialAnalysis.ai  - Next.js RSC flight data
  3. SuperCLUE (superclueai.com) - Vue JS bundle inline data

Adapted for professional-research skill structure.
"""
import requests
from bs4 import BeautifulSoup
import csv
import os
import json
import re
from datetime import datetime

from utils import read_config

# Load config
_config = None
def _get_config():
    global _config
    if _config is None:
        _config = read_config("leaderboard.json")
    return _config


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/146.0.0.0 Safari/537.36"
    ),
}


# ============================================================
# 1. LMArena (arena.ai) — HTML table parsing
# ============================================================
def scrape_lmarena(date_str: str, data_dir: str) -> dict[str, list[dict]]:
    """Scrape all LMArena categories."""
    config = _get_config()
    lm_config = config["sources"]["lmarena"]
    base_url = lm_config["base_url"]
    categories = lm_config["categories"]

    print(f"\n{'='*60}")
    print(f"  [1/3] LMArena (arena.ai)")
    print(f"{'='*60}")

    all_data = {}
    for category, cat_info in categories.items():
        try:
            url = f"{base_url}/{category}"
            print(f"[LM] 请求: {url}")
            resp = requests.get(url, headers=HEADERS, timeout=30)
            resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "html.parser")
            table = soup.find("table")
            if not table:
                raise RuntimeError(f"[{category}] 未找到排行榜表格")

            rows = table.find("tbody").find_all("tr")
            results = []
            for row in rows:
                tds = row.find_all("td")
                if len(tds) < cat_info["cols"]:
                    continue

                rank_spans = tds[1].find_all("span")
                if len(rank_spans) >= 2:
                    rank_lower = _safe_int(rank_spans[0].get_text(strip=True))
                    rank_upper = _safe_int(rank_spans[1].get_text(strip=True))
                else:
                    raw = tds[1].get_text(strip=True)
                    rank_lower = raw
                    rank_upper = raw

                score = tds[3].get_text(strip=True).replace("Preliminary", "").strip()

                entry = {
                    "rank": _safe_int(tds[0].get_text(strip=True)),
                    "rank_lower": rank_lower,
                    "rank_upper": rank_upper,
                    "model": _parse_model_name(tds[2]),
                    "score": score,
                    "votes": _safe_int(tds[4].get_text(strip=True).replace(",", "")),
                }

                if cat_info["cols"] >= 7:
                    entry["price_per_1m_tokens"] = tds[5].get_text(strip=True)
                    entry["context_length"] = tds[6].get_text(strip=True)

                results.append(entry)

            safe_name = category.replace("-", "_")
            all_data[safe_name] = results

            csv_path = os.path.join(data_dir, f"arena_{safe_name}_{date_str}.csv")
            _save_csv(results, csv_path)
            print(f"  [OK] {category}: {len(results)} 条 → {csv_path}")

        except Exception as e:
            print(f"  [!] {category} 失败: {e}")
            safe_name = category.replace("-", "_")
            all_data[safe_name] = []

    return all_data


# ============================================================
# 2. ArtificialAnalysis.ai — Next.js RSC flight
# ============================================================
def scrape_artificial_analysis(date_str: str, data_dir: str) -> dict[str, list[dict]]:
    """Scrape all AA categories via RSC flight requests."""
    config = _get_config()
    aa_config = config["sources"]["artificial_analysis"]
    base_url = aa_config["base_url"]
    rsc_pages = aa_config["rsc_pages"]

    print(f"\n{'='*60}")
    print(f"  [2/3] ArtificialAnalysis.ai")
    print(f"{'='*60}")

    all_data = {}
    for track_key, page_path in rsc_pages.items():
        try:
            url = f"{base_url}{page_path}"
            headers = {**HEADERS, "RSC": "1", "Next-Url": page_path}
            print(f"[AA] 请求: {url}")
            resp = requests.get(url, headers=headers, timeout=30)
            resp.raise_for_status()

            models = _parse_rsc_flight(resp.text)
            all_data[track_key] = models

            csv_path = os.path.join(data_dir, f"aa_{track_key}_{date_str}.csv")
            _save_csv(models, csv_path)
            print(f"  [OK] {track_key}: {len(models)} 条 → {csv_path}")

        except Exception as e:
            print(f"  [!] AA {track_key} 失败: {e}")
            all_data[track_key] = []

    return all_data


# ============================================================
# 3. SuperCLUE (superclueai.com) — Vue JS bundle inline data
# ============================================================
def scrape_superclue(date_str: str, data_dir: str) -> dict[str, list[dict]]:
    """Scrape SuperCLUE Arena from Vue JS bundle inline data."""
    config = _get_config()
    sc_config = config["sources"]["superclue"]
    base_url = sc_config["base_url"]
    cat_order = sc_config["category_order"]
    cat_labels = sc_config["category_labels"]

    print(f"\n{'='*60}")
    print(f"  [3/3] SuperCLUE Arena")
    print(f"{'='*60}")

    try:
        # Get vue-vendor JS URL
        resp = requests.get(base_url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        match = re.search(r'/assets/(vue-vendor-[A-Za-z0-9]+\.js)', resp.text)
        if not match:
            raise RuntimeError("无法在 SuperCLUE 首页找到 vue-vendor JS 路径")
        vendor_url = f"{base_url}/assets/{match.group(1)}"

        print(f"[SC] 下载: {vendor_url}")
        with requests.get(vendor_url, headers=HEADERS, timeout=60, stream=True) as r:
            r.raise_for_status()
            chunks = []
            for chunk in r.iter_content(chunk_size=65536):
                chunks.append(chunk)
        js = b"".join(chunks).decode("utf-8")
        print(f"[SC] JS bundle: {len(js)} bytes")

        # Extract inline data
        entries = _extract_sc_inline_entries(js)
        print(f"[SC] 提取 {len(entries)} 条记录")

        # Split by rank=1
        cat_groups = _split_by_rank1(entries)
        print(f"[SC] {len(cat_groups)} 个赛道")

        all_data = {}
        for i, group in enumerate(cat_groups):
            cat_name = cat_order[i] if i < len(cat_order) else f"unknown_{i}"
            all_data[cat_name] = group

            csv_path = os.path.join(data_dir, f"sc_{cat_name}_{date_str}.csv")
            _save_sc_csv(group, csv_path)
            label = cat_labels.get(cat_name, cat_name)
            print(f"  [{label}] {len(group)} models → {csv_path}")

        return all_data

    except Exception as e:
        print(f"  [!] SuperCLUE 失败: {e}")
        return {}


# ============================================================
# Unified entry point
# ============================================================
def scrape_all_sources(date_str: str, data_dir: str,
                       sources: list[str] | None = None) -> dict[str, dict]:
    """
    Scrape all (or selected) sources.

    Args:
        date_str: Date string (YYYYMMDD)
        data_dir: Directory to save CSV files
        sources: List of source keys ("lm", "aa", "sc") or None for all

    Returns:
        {"lm": {track: [rows]}, "aa": {...}, "sc": {...}}
    """
    os.makedirs(data_dir, exist_ok=True)
    if sources is None:
        sources = ["lm", "aa", "sc"]

    results = {}
    scrapers = {
        "lm": ("LMArena", scrape_lmarena),
        "aa": ("ArtificialAnalysis", scrape_artificial_analysis),
        "sc": ("SuperCLUE", scrape_superclue),
    }

    for key in sources:
        if key not in scrapers:
            print(f"[!] 未知数据源: {key}")
            continue
        name, func = scrapers[key]
        try:
            data = func(date_str, data_dir)
            results[key] = data
        except Exception as e:
            print(f"\n  ❌ {name} 抓取失败: {e}")
            results[key] = {}

    # Summary
    print(f"\n{'='*60}")
    print(f"  📊 抓取汇总")
    print(f"{'='*60}")
    for key, data in results.items():
        name = scrapers[key][0]
        total = sum(len(v) for v in data.values())
        cats = len(data)
        print(f"  ✅ {name}: {cats} 类别, {total} 条记录")

    return results


# ============================================================
# Internal helpers — LMArena
# ============================================================
def _parse_model_name(td) -> str:
    link = td.find("a")
    if link:
        for span in link.find_all("span"):
            text = span.get_text(strip=True)
            if text and not text.startswith(("·", "Proprietary", "Open", "API")):
                return text

    parts = [p.strip() for p in td.get_text(separator="|", strip=True).split("|") if p.strip()]
    skip = {"Proprietary", "Open", "API", "·"}
    filtered = [p for p in parts if p not in skip and not p.startswith("·")]
    return filtered[1] if len(filtered) >= 2 else (filtered[0] if filtered else td.get_text(strip=True))


def _safe_int(s: str) -> int | str:
    try:
        return int(s.replace(",", ""))
    except (ValueError, AttributeError):
        return s


# ============================================================
# Internal helpers — ArtificialAnalysis RSC
# ============================================================
def _parse_rsc_flight(text: str) -> list[dict]:
    lines = text.split("\n")
    for line in lines:
        if '"rank"' not in line or '"elo"' not in line:
            continue
        if '"formatted"' not in line or '"values"' not in line:
            continue

        match = re.match(r'[\da-f]+:(.*)', line, re.DOTALL)
        if not match:
            continue

        json_str = match.group(1)
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            continue

        entries = []
        _find_rsc_entries(data, entries)

        if entries:
            seen_ids = set()
            unique_entries = []
            for e in entries:
                model_id = e.get("values", {}).get("id", "")
                if model_id and model_id not in seen_ids:
                    seen_ids.add(model_id)
                    unique_entries.append(e)
                elif not model_id:
                    unique_entries.append(e)

            unique_entries.sort(
                key=lambda e: e.get("formatted", {}).get("rank", 9999)
            )
            return [_normalize_rsc_entry(e) for e in unique_entries]

    return []


def _find_rsc_entries(obj, results: list):
    if isinstance(obj, dict):
        if "formatted" in obj and "values" in obj:
            results.append(obj)
        else:
            for v in obj.values():
                _find_rsc_entries(v, results)
    elif isinstance(obj, list):
        for item in obj:
            _find_rsc_entries(item, results)


def _normalize_rsc_entry(entry: dict) -> dict:
    fmt = entry.get("formatted", {})
    vals = entry.get("values", {})
    creator = vals.get("creator", {})

    return {
        "rank": fmt.get("rank", vals.get("rank", 0) + 1),
        "model": vals.get("name", ""),
        "creator": creator.get("name", ""),
        "elo": round(vals.get("elo", 0), 2),
        "ci": vals.get("ci", ""),
        "samples": vals.get("appearances", 0),
        "released": vals.get("released", ""),
        "price_per_1k_images": vals.get("pricePer1kImages", None),
        "win_rate": round(vals.get("winRate", 0) * 100, 1),
        "is_open_weights": vals.get("openWeightsUrl") is not None,
        "is_current": vals.get("isCurrent", False),
    }


# ============================================================
# Internal helpers — SuperCLUE
# ============================================================
def _extract_sc_inline_entries(js: str) -> list[dict]:
    entries = []
    pattern = r'\{rank:\d+,model:"[^"]+",org:"[^"]+",median:[\d.]+'
    for m in re.finditer(pattern, js):
        start = m.start()
        depth, end = 0, start
        for i in range(start, min(start + 500, len(js))):
            if js[i] == '{':
                depth += 1
            elif js[i] == '}':
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break

        entry_str = js[start:end]
        json_str = re.sub(r'(\w+)\s*:', r'"\1":', entry_str)
        json_str = json_str.replace('""', '"')
        try:
            entries.append(json.loads(json_str))
        except json.JSONDecodeError:
            pass
    return entries


def _split_by_rank1(entries: list[dict]) -> list[list[dict]]:
    categories = []
    current = []
    for entry in entries:
        if entry.get("rank") == 1 and current:
            categories.append(current)
            current = []
        current.append(entry)
    if current:
        categories.append(current)
    return categories


def _save_sc_csv(results: list[dict], path: str):
    if not results:
        return
    fieldnames = ["rank", "model", "org", "median", "ciLow", "ciHigh", "battles", "date"]
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)


# ============================================================
# Shared helpers
# ============================================================
def _save_csv(results: list[dict], path: str):
    if not results:
        return
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=results[0].keys())
        writer.writeheader()
        writer.writerows(results)


if __name__ == "__main__":
    import sys
    date = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime("%Y%m%d")
    out_dir = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.getcwd(), "data")
    results = scrape_all_sources(date, out_dir)
