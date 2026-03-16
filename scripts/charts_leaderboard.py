"""
Multi-Source Leaderboard Charts
================================
Generates matplotlib charts for the Word report.
Adapted for professional-research skill structure.
"""
import os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

from analyze_leaderboard import SOURCE_LABELS

# ============================================================
# Font config
# ============================================================
_CN_FONTS = ["Microsoft YaHei", "SimHei", "SimSun", "KaiTi"]
_FONT_FOUND = None
for fn in _CN_FONTS:
    if any(fn.lower() in f.name.lower() for f in fm.fontManager.ttflist):
        _FONT_FOUND = fn
        break

if _FONT_FOUND:
    plt.rcParams["font.sans-serif"] = [_FONT_FOUND, "Arial"]
else:
    plt.rcParams["font.sans-serif"] = ["Arial"]
plt.rcParams["axes.unicode_minus"] = False

COLORS = {"lm": "#2563EB", "aa": "#16A34A", "sc": "#DC2626"}
SCORE_FIELDS = {"lm": "score", "aa": "elo", "sc": "median"}


# ============================================================
# Track Top10 bar chart
# ============================================================
def chart_track_top10(track_label: str, track_data: dict,
                      date_str: str, charts_dir: str) -> str:
    fig, axes = plt.subplots(1, 3, figsize=(16, 6), sharey=False)
    fig.suptitle(track_label, fontsize=16, fontweight="bold", y=1.02)

    for idx, src in enumerate(["lm", "aa", "sc"]):
        ax = axes[idx]
        rows = track_data.get("top10_per_source", {}).get(src, [])

        if not rows:
            ax.text(0.5, 0.5, "无数据", ha="center", va="center", fontsize=12)
            ax.set_title(SOURCE_LABELS[src])
            continue

        models = []
        scores = []
        for r in rows[:10]:
            model = r.get("model", "?")
            if len(model) > 20:
                model = model[:18] + "…"
            models.append(model)

            score_field = SCORE_FIELDS[src]
            raw = str(r.get(score_field, "0"))
            raw = raw.split("±")[0].strip()
            try:
                scores.append(float(raw))
            except ValueError:
                scores.append(0)

        y_pos = np.arange(len(models))
        bars = ax.barh(y_pos, scores, color=COLORS[src], alpha=0.85, height=0.7)

        ax.set_yticks(y_pos)
        ax.set_yticklabels(models, fontsize=8)
        ax.invert_yaxis()
        ax.set_title(SOURCE_LABELS[src], fontsize=12, fontweight="bold", color=COLORS[src])
        ax.set_xlabel("Score / Elo", fontsize=9)

        for bar, score in zip(bars, scores):
            ax.text(bar.get_width() + 2, bar.get_y() + bar.get_height()/2,
                    f"{score:.0f}", va="center", fontsize=7, color="#666")

    plt.tight_layout()
    safe_name = track_label.split("(")[0].strip().replace(" ", "_")
    path = os.path.join(charts_dir, f"track_{safe_name}_{date_str}.png")
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"  [图表] {path}")
    return path


# ============================================================
# Vendor seats bar chart
# ============================================================
def chart_vendor_seats(vendor_data: dict, date_str: str, charts_dir: str) -> str:
    top_vendors = list(vendor_data.items())[:12]
    if not top_vendors:
        return ""

    vendors = [v[0] for v in top_vendors]
    counts = [v[1]["total_entries"] for v in top_vendors]
    n_tracks = [len(v[1]["tracks"]) for v in top_vendors]

    fig, ax = plt.subplots(figsize=(12, 6))
    x = np.arange(len(vendors))
    width = 0.4

    bars1 = ax.bar(x - width/2, counts, width, label="入榜模型数",
                   color="#2563EB", alpha=0.85)
    bars2 = ax.bar(x + width/2, n_tracks, width, label="覆盖赛道数",
                   color="#F59E0B", alpha=0.85)

    ax.set_xticks(x)
    ax.set_xticklabels(vendors, rotation=30, ha="right", fontsize=9)
    ax.set_ylabel("数量")
    ax.set_title("厂商入榜实力全景（Top 12）", fontsize=14, fontweight="bold")
    ax.legend(loc="upper right")

    for bar in bars1:
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.3,
                f"{int(bar.get_height())}", ha="center", va="bottom", fontsize=8)
    for bar in bars2:
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.3,
                f"{int(bar.get_height())}", ha="center", va="bottom", fontsize=8)

    plt.tight_layout()
    path = os.path.join(charts_dir, f"vendor_seats_{date_str}.png")
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"  [图表] {path}")
    return path


# ============================================================
# Cross-source scatter plot
# ============================================================
def chart_cross_source_scatter(comparisons: dict, date_str: str, charts_dir: str) -> str:
    fig, ax = plt.subplots(figsize=(10, 8))
    track_colors = ["#2563EB", "#DC2626", "#16A34A"]
    markers = ["o", "s", "^"]

    for idx, (track, data) in enumerate(comparisons.items()):
        cross = data.get("cross_models", [])
        lm_ranks, aa_ranks, labels = [], [], []
        for cm in cross:
            lr = cm.get("lm_rank")
            ar = cm.get("aa_rank")
            if lr is not None and ar is not None:
                lm_ranks.append(lr)
                aa_ranks.append(ar)
                labels.append(cm["model"])

        if lm_ranks:
            short_track = track.split("(")[0].strip()
            ax.scatter(lm_ranks, aa_ranks, c=track_colors[idx % len(track_colors)],
                      marker=markers[idx % len(markers)], s=60, alpha=0.7,
                      label=short_track, edgecolors="white", linewidths=0.5)
            for i in range(min(3, len(labels))):
                name = labels[i][:15] + "…" if len(labels[i]) > 15 else labels[i]
                ax.annotate(name, (lm_ranks[i], aa_ranks[i]),
                           fontsize=7, alpha=0.8,
                           xytext=(5, 5), textcoords="offset points")

    max_val = 50
    ax.plot([0, max_val], [0, max_val], "--", color="#CCC", linewidth=1, zorder=0)
    ax.set_xlabel("LMArena 排名", fontsize=11)
    ax.set_ylabel("ArtificialAnalysis 排名", fontsize=11)
    ax.set_title("跨平台排名一致性", fontsize=14, fontweight="bold")
    ax.legend(loc="lower right")
    ax.set_xlim(0, max_val)
    ax.set_ylim(0, max_val)
    ax.invert_xaxis()
    ax.invert_yaxis()

    plt.tight_layout()
    path = os.path.join(charts_dir, f"cross_scatter_{date_str}.png")
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"  [图表] {path}")
    return path


# ============================================================
# Generate all charts
# ============================================================
def generate_charts(analysis: dict, output_dir: str) -> dict:
    date_str = analysis["date"]
    comparisons = analysis["comparisons"]
    vendors = analysis["vendors"]

    charts_dir = os.path.join(output_dir, "charts")
    os.makedirs(charts_dir, exist_ok=True)

    chart_paths = {"track_charts": {}}

    print("\n[图表] 生成赛道对比图...")
    for track, data in comparisons.items():
        path = chart_track_top10(track, data, date_str, charts_dir)
        chart_paths["track_charts"][track] = path

    print("[图表] 生成厂商席位图...")
    chart_paths["vendor_chart"] = chart_vendor_seats(vendors, date_str, charts_dir)

    print("[图表] 生成跨源散点图...")
    chart_paths["scatter_chart"] = chart_cross_source_scatter(comparisons, date_str, charts_dir)

    return chart_paths
