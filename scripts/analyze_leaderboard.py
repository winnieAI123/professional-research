"""
Multi-Source Leaderboard Analysis Engine
=========================================
Aggregates LMArena / ArtificialAnalysis / SuperCLUE data,
performs cross-source comparison, vendor panorama, tech barriers,
opportunity screening, and Gemini narrative insights.

Adapted for professional-research skill structure.
"""
import csv
import os
import re
import json
from collections import defaultdict
from difflib import SequenceMatcher

from utils import read_config
from llm_client import generate_content

# Load config
_config = None
def _get_config():
    global _config
    if _config is None:
        _config = read_config("leaderboard.json")
    return _config


# ============================================================
# Source metadata
# ============================================================
SOURCE_PREFIX = {"lm": "arena_", "aa": "aa_", "sc": "sc_"}
SOURCE_LABELS = {"lm": "LMArena", "aa": "ArtificialAnalysis", "sc": "SuperCLUE"}

SCORE_FIELD = {"lm": "score", "aa": "elo", "sc": "median"}
RANK_FIELD = "rank"


# ============================================================
# Vendor identification (inlined from analyze.py)
# ============================================================
VENDOR_PATTERNS = [
    ("claude",         "Anthropic"),
    ("gemini",         "Google"),
    ("gemma",          "Google"),
    ("nano-banana",    "Google"),
    ("imagen",         "Google"),
    ("veo-",           "Google"),
    ("gpt-",           "OpenAI"),
    ("chatgpt",        "OpenAI"),
    ("o1-",            "OpenAI"),
    ("o3-",            "OpenAI"),
    ("o4-",            "OpenAI"),
    ("gpt-image",      "OpenAI"),
    ("dall-e",         "OpenAI"),
    ("sora",           "OpenAI"),
    ("grok",           "xAI"),
    ("deepseek",       "DeepSeek"),
    ("qwen",           "Alibaba"),
    ("qwq",            "Alibaba"),
    ("wan2",           "Alibaba"),
    ("glm-",           "Zhipu"),
    ("chatglm",        "Zhipu"),
    ("cogview",        "Zhipu"),
    ("cogvideo",       "Zhipu"),
    ("longcat",        "Zhipu"),
    ("llama",          "Meta"),
    ("mistral",        "Mistral"),
    ("minimax",        "MiniMax"),
    ("hailuo",         "MiniMax"),
    ("ernie",          "Baidu"),
    ("kimi",           "Moonshot"),
    ("hunyuan",        "Tencent"),
    ("phi-",           "Microsoft"),
    ("mai-",           "Microsoft"),
    ("nova-",          "Amazon"),
    ("command",        "Cohere"),
    ("step-",          "StepFun"),
    ("yi-",            "01.AI"),
    ("flux",           "BlackForestLabs"),
    ("kling",          "Kuaishou"),
    ("kolors",         "Kuaishou"),
    ("seedance",       "ByteDance"),
    ("seedream",       "ByteDance"),
    ("doubao",         "ByteDance"),
    ("jimeng",         "ByteDance"),
    ("runway",         "Runway"),
    ("gen-3",          "Runway"),
    ("gen-4",          "Runway"),
    ("pika",           "Pika"),
    ("recraft",        "Recraft"),
    ("ideogram",       "Ideogram"),
    ("nemotron",       "NVIDIA"),
    ("nvidia",         "NVIDIA"),
    ("vidu",           "Shengshu"),
    ("ray2",           "Luma"),
    ("ray-3",          "Luma"),
    ("dream machine",  "Luma"),
    ("jamba",          "AI21"),
    ("reka",           "Reka"),
    ("granite",        "IBM"),
    ("olmo",           "AI2"),
    ("mimo",           "Xiaomi"),
    ("firefly",        "Adobe"),
    ("midjourney",     "Midjourney"),
    ("stable diffusion","Stability"),
    ("sdxl",           "Stability"),
    ("sd3",            "Stability"),
]


def identify_vendor(model_name: str) -> str:
    """Identify vendor from model name."""
    lower = model_name.lower()
    for pattern, vendor in VENDOR_PATTERNS:
        if pattern in lower:
            return vendor
    return "Other"


# ============================================================
# Data loading from CSV
# ============================================================
def load_all_sources(date_str: str, data_dir: str) -> dict:
    """Load all source CSV data."""
    all_data = {}
    for src, prefix in SOURCE_PREFIX.items():
        src_data = {}
        if not os.path.exists(data_dir):
            all_data[src] = {}
            continue
        for f in os.listdir(data_dir):
            if f.startswith(prefix) and f.endswith(f"_{date_str}.csv"):
                track_key = f[len(prefix):-len(f"_{date_str}.csv")]
                rows = _load_csv(os.path.join(data_dir, f))
                src_data[track_key] = rows
        all_data[src] = src_data
        total = sum(len(v) for v in src_data.values())
        print(f"[分析] {SOURCE_LABELS[src]}: {len(src_data)} 赛道, {total} 条")
    return all_data


def _load_csv(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _get_score(row: dict, source: str) -> float:
    field = SCORE_FIELD[source]
    raw = row.get(field, "0")
    if isinstance(raw, (int, float)):
        return float(raw)
    raw = str(raw).split("±")[0].strip()
    try:
        return float(raw)
    except ValueError:
        return 0.0


def _get_rank(row: dict) -> int:
    try:
        return int(row.get("rank", 999))
    except (ValueError, TypeError):
        return 999


# ============================================================
# Model name normalization & fuzzy matching
# ============================================================
def _normalize_model_name(name: str) -> str:
    n = name.lower().strip()
    n = re.sub(r'\([^)]*\)', '', n)
    n = re.sub(r'[-_]v?\d+(\.\d+)*$', '', n)
    n = re.sub(r'[_\-\s]+', '', n)
    return n.strip()


def _merge_similar_models(all_models: dict) -> dict:
    merged = {}
    used = set()
    norms = list(all_models.keys())
    for i, n1 in enumerate(norms):
        if n1 in used:
            continue
        sources = dict(all_models[n1])
        best_name = list(all_models[n1].values())[0]["name"]
        for j in range(i + 1, len(norms)):
            n2 = norms[j]
            if n2 in used:
                continue
            if SequenceMatcher(None, n1, n2).ratio() > 0.8:
                for src, info in all_models[n2].items():
                    if src not in sources:
                        sources[src] = info
                used.add(n2)
        merged[best_name] = sources
        used.add(n1)
    return merged


# ============================================================
# Cross-source comparison
# ============================================================
def cross_source_comparison(all_data: dict) -> dict:
    config = _get_config()
    shared_tracks = config["shared_tracks"]

    results = {}
    for track_label, src_keys in shared_tracks.items():
        track_data = {"sources": {}, "top10_per_source": {}, "cross_models": []}

        for src, csv_key in src_keys.items():
            rows = all_data.get(src, {}).get(csv_key, [])
            track_data["sources"][src] = rows
            track_data["top10_per_source"][src] = rows[:10]

        all_models = {}
        for src, csv_key in src_keys.items():
            rows = all_data.get(src, {}).get(csv_key, [])
            for row in rows[:30]:
                model = row.get("model", "")
                if not model:
                    continue
                norm = _normalize_model_name(model)
                if norm not in all_models:
                    all_models[norm] = {}
                all_models[norm][src] = {
                    "name": model,
                    "rank": _get_rank(row),
                    "score": _get_score(row, src),
                }

        merged = _merge_similar_models(all_models)

        cross = []
        for canonical, sources in merged.items():
            entry = {"model": canonical, "vendor": identify_vendor(canonical)}
            for src in ["lm", "aa", "sc"]:
                if src in sources:
                    entry[f"{src}_rank"] = sources[src]["rank"]
                    entry[f"{src}_score"] = round(sources[src]["score"], 1)
                else:
                    entry[f"{src}_rank"] = None
                    entry[f"{src}_score"] = None
            ranks = [entry[f"{s}_rank"] for s in ["lm", "aa", "sc"] if entry[f"{s}_rank"]]
            entry["best_rank"] = min(ranks) if ranks else 999
            cross.append(entry)

        cross.sort(key=lambda x: x["best_rank"])
        track_data["cross_models"] = cross[:20]
        results[track_label] = track_data

    return results


# ============================================================
# Vendor panorama
# ============================================================
def vendor_panorama(all_data: dict) -> dict:
    config = _get_config()
    shared_tracks = config["shared_tracks"]
    exclusive_tracks = config["exclusive_tracks"]

    vendors = defaultdict(lambda: {
        "total_entries": 0, "tracks": {}, "best_overall_rank": 999,
    })

    all_tracks = {}
    for track_label, src_keys in shared_tracks.items():
        combined = []
        for src, csv_key in src_keys.items():
            rows = all_data.get(src, {}).get(csv_key, [])
            for r in rows[:20]:
                combined.append({"model": r.get("model", ""), "rank": _get_rank(r), "source": src})
        all_tracks[track_label] = combined

    for src, tracks in exclusive_tracks.items():
        for track_label, csv_key in tracks.items():
            rows = all_data.get(src, {}).get(csv_key, [])
            combined = [{"model": r.get("model", ""), "rank": _get_rank(r), "source": src} for r in rows[:20]]
            all_tracks[track_label] = combined

    for track_label, entries in all_tracks.items():
        for entry in entries:
            vendor = identify_vendor(entry["model"])
            v = vendors[vendor]
            v["total_entries"] += 1
            rank = entry["rank"]
            if track_label not in v["tracks"]:
                v["tracks"][track_label] = {"best_rank": rank, "best_model": entry["model"], "count": 0}
            t = v["tracks"][track_label]
            t["count"] += 1
            if rank < t["best_rank"]:
                t["best_rank"] = rank
                t["best_model"] = entry["model"]
            if rank < v["best_overall_rank"]:
                v["best_overall_rank"] = rank

    sorted_vendors = sorted(
        vendors.items(),
        key=lambda x: (x[0] == "Other", -x[1]["total_entries"])
    )
    return dict(sorted_vendors)


# ============================================================
# Exclusive track summary
# ============================================================
def exclusive_track_summary(all_data: dict) -> dict:
    config = _get_config()
    exclusive_tracks = config["exclusive_tracks"]

    result = {}
    for src, tracks in exclusive_tracks.items():
        for track_label, csv_key in tracks.items():
            rows = all_data.get(src, {}).get(csv_key, [])
            if rows:
                result[track_label] = {
                    "source": SOURCE_LABELS[src],
                    "top10": rows[:10],
                    "total": len(rows),
                }
    return result


# ============================================================
# Tech barriers (open/closed source)
# ============================================================
def tech_barriers_analysis(all_data: dict) -> dict:
    config = _get_config()
    chinese_vendors = set(config.get("chinese_vendors", []))

    open_models = []
    closed_models = []

    for track_key, rows in all_data.get("aa", {}).items():
        for r in rows[:20]:
            model = r.get("model", "")
            vendor = identify_vendor(model)
            is_open = str(r.get("is_open_weights", "False")).lower() == "true"
            entry = {
                "model": model,
                "vendor": vendor,
                "rank": _get_rank(r),
                "track": track_key,
                "is_chinese": vendor in chinese_vendors,
            }
            if is_open:
                open_models.append(entry)
            else:
                closed_models.append(entry)

    return {
        "open_count": len(open_models),
        "closed_count": len(closed_models),
        "open_vendors": sorted(set(m["vendor"] for m in open_models)),
        "closed_vendors": sorted(set(m["vendor"] for m in closed_models)),
        "open_top5": sorted(open_models, key=lambda x: x["rank"])[:5],
        "closed_top5": sorted(closed_models, key=lambda x: x["rank"])[:5],
        "chinese_open": len([m for m in open_models if m["is_chinese"]]),
        "chinese_closed": len([m for m in closed_models if m["is_chinese"]]),
    }


# ============================================================
# Opportunity screening
# ============================================================
def opportunity_screening(all_data: dict, vendors: dict) -> dict:
    config = _get_config()
    chinese_vendors = set(config.get("chinese_vendors", []))
    threshold = config.get("analysis", {}).get("opportunity_threshold", 3)

    opportunities = []
    for vendor_name, info in vendors.items():
        if vendor_name == "Other":
            continue
        is_chinese = vendor_name in chinese_vendors
        n_tracks = len(info["tracks"])
        best_rank = info["best_overall_rank"]

        score = 0
        tags = []
        if is_chinese:
            score += 3
            tags.append("🇨🇳 中国厂商")
        if n_tracks >= 3:
            score += 2
            tags.append(f"📊 覆盖{n_tracks}赛道")
        if best_rank <= 3:
            score += 3
            tags.append(f"🏆 最佳排名#{best_rank}")
        elif best_rank <= 5:
            score += 2
            tags.append(f"⭐ 最佳排名#{best_rank}")
        elif best_rank <= 10:
            score += 1
        if info["total_entries"] >= 10:
            score += 2
            tags.append(f"💪 {info['total_entries']}模型入榜")

        if score >= threshold:
            opportunities.append({
                "vendor": vendor_name, "score": score, "tags": tags,
                "is_chinese": is_chinese, "n_tracks": n_tracks,
                "best_rank": best_rank, "total_entries": info["total_entries"],
                "top_tracks": [
                    f"{t.split('(')[0].strip()}:#{d['best_rank']}({d['best_model']})"
                    for t, d in sorted(info["tracks"].items(), key=lambda x: x[1]["best_rank"])[:3]
                ],
            })

    opportunities.sort(key=lambda x: -x["score"])
    return {
        "opportunities": opportunities,
        "chinese_highlights": [o for o in opportunities if o["is_chinese"]],
        "global_leaders": [o for o in opportunities if not o["is_chinese"]][:5],
    }


# ============================================================
# Gemini narrative insights (using llm_client)
# ============================================================
def generate_multi_insights(comparisons: dict, vendor_data: dict,
                            exclusives: dict = None) -> str:
    """Generate narrative insights via Gemini."""
    config = _get_config()
    gemini_config = config.get("report", {}).get("gemini", {})
    temperature = gemini_config.get("temperature", 0.4)
    max_tokens = gemini_config.get("max_output_tokens", 8192)

    prompt = _build_multi_prompt(comparisons, vendor_data, exclusives)

    print("[分析] 调用 Gemini 生成多源洞察...")
    text = generate_content(
        prompt,
        use_fast_model=False,
        temperature=temperature,
        max_output_tokens=max_tokens,
    )
    print(f"[分析] Gemini 返回 {len(text)} 字")
    return text


def _build_multi_prompt(comparisons: dict, vendor_data: dict,
                        exclusives: dict = None) -> str:
    sections = []

    track_names = []
    for track, data in comparisons.items():
        track_names.append(track)
        s = f"\n## {track}\n"
        for cm in data.get("cross_models", [])[:10]:
            ranks = []
            for src in ["lm", "aa", "sc"]:
                r = cm.get(f"{src}_rank")
                sc = cm.get(f"{src}_score")
                if r is not None:
                    ranks.append(f"{SOURCE_LABELS[src]}:#{r}({sc})")
            s += f"  {cm['model']} ({cm['vendor']}) — {' | '.join(ranks)}\n"
        sections.append(s)

    excl_names = []
    if exclusives:
        for track_label, info in exclusives.items():
            excl_names.append(track_label)
            s = f"\n## {track_label}（{info['source']}独有）\n"
            for r in info.get("top10", [])[:5]:
                model = r.get("model", "?")
                score = r.get("median", r.get("score", "?"))
                org = r.get("org", r.get("creator", "?"))
                s += f"  #{r.get('rank','?')} {model} ({org}) Score:{score}\n"
            sections.append(s)

    s = "\n## 厂商全景\n"
    for vendor, info in list(vendor_data.items())[:10]:
        if vendor == "Other":
            continue
        tracks_str = ", ".join(f"{t}:#{d['best_rank']}" for t, d in info["tracks"].items())
        s += f"  {vendor}: {info['total_entries']}个模型入榜, 覆盖{len(info['tracks'])}赛道 [{tracks_str}]\n"
    sections.append(s)

    data_text = "\n".join(sections)

    track_format = ""
    for t in track_names:
        short = t.split("(")[0].strip()
        track_format += f"\n[TRACK_{short}]\n一段50-100字的赛道分析，点出该赛道的竞争格局和关键发现。\n"

    excl_format = ""
    if excl_names:
        excl_format = "\n[EXCLUSIVE_TRACKS]\n一段100-150字概述独有赛道的亮点（" + "、".join(n.split("(")[0].strip() for n in excl_names) + "）。\n"

    return f"""你是一位顶级 AI 行业分析师，正在撰写多平台 AI 模型竞争力分析报告。
以下是来自三个排行榜平台（LMArena、ArtificialAnalysis、SuperCLUE）的跨源对比数据。

{data_text}

请用中文撰写完整分析报告，严格按以下格式输出所有部分（每个标记都必须出现）：

=== 宏观格局 ===

[MACRO_LANDSCAPE]
一段150-200字的宏观格局分析。回答：谁是当前全赛道的统治者？谁是挑战者？中国厂商与海外厂商的整体差距如何？市场是集中化还是碎片化？

=== 核心洞察 ===

[INSIGHT_1]
标题：用一句话概括此洞察
正文：2-3句分析，引用具体数据支撑。

[INSIGHT_2]
标题：...
正文：...

[INSIGHT_3]
标题：...
正文：...

（共3-5条洞察）

=== 赛道分析 ==={track_format}
=== 独有赛道 ==={excl_format}
=== 技术壁垒 ===

[TECH_BARRIERS]
一段100-150字分析开源vs闭源的竞争态势。Top 5中开源和闭源各占多少？中国厂商在开源/闭源上的策略倾向是什么？开源模型在哪些赛道更有竞争力？

=== 机会筛选 ===

[OPPORTUNITY]
一段150-200字，从产品选型和竞品监控两个视角给出建议：
1. 产品选型：如果要为产品集成AI生成能力，各赛道应优先考虑哪些模型？（考虑质量、成本、开源可控性）
2. 竞品监控：哪些中国厂商值得重点关注？它们在哪些赛道有突破性表现？

=== 结论 ===

[CONCLUSION]
3条简洁的结论判断，每条一句话，格式为：
结论1：...
结论2：...
结论3：...

要求：
- 所有标记（MACRO_LANDSCAPE, INSIGHT_N, TRACK_xxx, EXCLUSIVE_TRACKS, TECH_BARRIERS, OPPORTUNITY, CONCLUSION）都必须出现
- 必须基于数据，引用具体排名和分数
- 语气专业简洁，像 a16z 分析师风格
- 不要使用 Markdown 格式符号
"""


# ============================================================
# Main analysis flow
# ============================================================
def run_analysis(date_str: str, data_dir: str) -> dict:
    """
    Execute full multi-source analysis.

    Returns:
        {
            "date": str,
            "sources": {src: {track: [rows]}},
            "comparisons": {track: {...}},
            "vendors": {vendor: {...}},
            "exclusives": {track: {...}},
            "tech_barriers": {...},
            "opportunities": {...},
            "insights": str,
        }
    """
    print(f"\n{'='*60}")
    print(f"  多源分析引擎 — {date_str}")
    print(f"{'='*60}")

    all_data = load_all_sources(date_str, data_dir)

    print("\n[分析] 跨源赛道对比...")
    comparisons = cross_source_comparison(all_data)
    for track, data in comparisons.items():
        n_cross = len(data.get("cross_models", []))
        print(f"  {track}: {n_cross} 个跨源模型")

    print("\n[分析] 厂商全景分析...")
    vendors = vendor_panorama(all_data)
    print(f"  {len(vendors)} 个厂商")

    exclusives = exclusive_track_summary(all_data)

    print("\n[分析] 技术壁垒分析...")
    tech = tech_barriers_analysis(all_data)
    print(f"  开源: {tech['open_count']} | 闭源: {tech['closed_count']}")

    print("[分析] 机会筛选...")
    opps = opportunity_screening(all_data, vendors)
    print(f"  {len(opps['opportunities'])} 个值得关注, 其中中国厂商 {len(opps['chinese_highlights'])} 个")

    try:
        insights = generate_multi_insights(comparisons, vendors, exclusives)
    except Exception as e:
        print(f"[!] Gemini 调用失败: {e}")
        insights = "（Gemini 分析不可用）"

    return {
        "date": date_str,
        "sources": all_data,
        "comparisons": comparisons,
        "vendors": vendors,
        "exclusives": exclusives,
        "tech_barriers": tech,
        "opportunities": opps,
        "insights": insights,
    }
