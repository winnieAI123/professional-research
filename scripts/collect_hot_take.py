"""
Hot Take: 热点事件观点速览
Collects opinions from Twitter + Web about a breaking event,
synthesizes them via LLM, and outputs Markdown + Word report.

Usage:
    python scripts/collect_hot_take.py --topic "Sora关停" --output "D:/clauderesult/claude0326/"
"""

import os
import sys
import json
import argparse
import datetime

# Ensure scripts/ is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from collect_twitter import search_topic_tweets
from collect_search import tavily_search, TavilyQuotaExhausted
from llm_client import generate_content
from md_to_word import convert_md_to_word


# ============================================================
# Phase 1: Generate Search Keywords
# ============================================================

def generate_hot_take_keywords(topic: str, count: int = 5) -> list:
    """Generate English + Chinese search keywords for the event."""
    prompt = f"""你是搜索策略专家。用户想了解关于"{topic}"这个热点事件的各方观点。
请生成{count}个搜索关键词/短语，用于在Twitter和网页上搜索相关讨论和分析。

要求：
1. 包含英文和中文关键词（英文为主，便于Twitter搜索）
2. 覆盖不同角度：事件本身、影响分析、业内反应等
3. 使用社交媒体上实际常用的表达
4. 不要太泛也不要太窄
5. 输出JSON数组

示例（假设话题是"Sora关停"）：
["Sora shutdown OpenAI", "Sora discontinued why", "OpenAI video generation future", "Sora 关停 影响", "AI video generation market"]

现在为"{topic}"生成{count}个搜索关键词："""

    result = generate_content(prompt=prompt, use_fast_model=True, return_json=True)

    if isinstance(result, list) and all(isinstance(k, str) for k in result):
        print(f"  [Keywords] Generated {len(result)} terms: {result}")
        return result[:count]

    # Fallback
    print(f"  [Keywords] LLM unexpected output, using topic directly")
    return [topic]


# ============================================================
# Phase 2: Data Collection
# ============================================================

def collect_twitter_opinions(keywords: list, max_tweets: int = 20) -> list:
    """Search Twitter for top tweets about the event."""
    print(f"\n{'='*50}")
    print(f"Phase 2a: Twitter Search ({max_tweets} tweets max)")
    print(f"{'='*50}")

    all_tweets = []
    seen_urls = set()

    for kw in keywords:
        try:
            tweets = search_topic_tweets(
                topic_query=kw,
                total_count=max_tweets,
                min_likes=5,  # Filter out noise
            )
            for t in tweets:
                url = t.get("url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    all_tweets.append(t)
            print(f"  [Twitter] '{kw}' → {len(tweets)} tweets")
        except Exception as e:
            print(f"  [Twitter] '{kw}' failed: {e}")

    # Sort by engagement, take top N
    all_tweets.sort(
        key=lambda x: x.get("likes", 0) + x.get("retweets", 0),
        reverse=True,
    )
    result = all_tweets[:max_tweets]
    print(f"  [Twitter] Total: {len(all_tweets)} unique → Top {len(result)}")
    return result


def collect_web_opinions(keywords: list, max_web: int = 15) -> list:
    """Search web for articles and analyses about the event."""
    print(f"\n{'='*50}")
    print(f"Phase 2b: Web Search ({max_web} results max)")
    print(f"{'='*50}")

    all_results = []
    seen_urls = set()

    for kw in keywords:
        try:
            results = tavily_search(
                query=kw,
                max_results=8,
                search_depth="advanced",
            )
            for r in results:
                url = r.get("url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    all_results.append(r)
            print(f"  [Web] '{kw}' → {len(results)} results")
        except TavilyQuotaExhausted:
            print(f"  [Web] Tavily quota exhausted, stopping web search")
            break
        except Exception as e:
            print(f"  [Web] '{kw}' failed: {e}")

    # Sort by score
    all_results.sort(key=lambda x: x.get("score", 0), reverse=True)
    result = all_results[:max_web]
    print(f"  [Web] Total: {len(all_results)} unique → Top {len(result)}")
    return result


# ============================================================
# Phase 3: LLM Opinion Extraction & Synthesis
# ============================================================

def extract_opinions_from_sources(topic: str, tweets: list, web_results: list) -> dict:
    """Use LLM to extract and synthesize opinions from all sources."""
    print(f"\n{'='*50}")
    print(f"Phase 3: LLM Opinion Extraction")
    print(f"{'='*50}")

    # Prepare Twitter data
    twitter_text = ""
    for i, t in enumerate(tweets, 1):
        name = t.get("author_name", "") or t.get("name", "")
        username = t.get("author_username", "") or t.get("username", "")
        text = t.get("text", "") or t.get("content", "")
        likes = t.get("likes", 0)
        rts = t.get("retweets", 0)
        url = t.get("url", "")
        twitter_text += f"\n---\nTweet #{i}: @{username} ({name})\n"
        twitter_text += f"Likes: {likes} | Retweets: {rts}\n"
        twitter_text += f"URL: {url}\n"
        twitter_text += f"Content: {text}\n"

    # Prepare Web data
    web_text = ""
    for i, r in enumerate(web_results, 1):
        title = r.get("title", "")
        url = r.get("url", "")
        content = r.get("content", "")[:1500]  # Truncate long articles
        web_text += f"\n---\nArticle #{i}: {title}\n"
        web_text += f"URL: {url}\n"
        web_text += f"Content: {content}\n"

    prompt = f"""你是一位资深科技分析师。以下是关于"{topic}"这个热点事件的多方信息来源。
请完成以下任务：

1. **事件概要**（event_summary）：用3-5句话简明扼要说清楚发生了什么
2. **Twitter观点**（twitter_opinions）：翻译每条有价值的推文原文，每条包含：
   - author: 作者名和用户名
   - opinion: 推文原文的中文翻译（完整翻译，不要提炼或缩写，让读者能看出原作者到底说了什么）
   - engagement: 互动量描述（如"❤️ 1.2K 🔄 300"）
   - url: 原始链接
3. **媒体/博客观点**（web_opinions）：从网页文章中提取核心观点，每条包含：
   - source: 来源名称
   - opinion: 文章的核心观点（2-3句话，保留关键信息）
   - url: 原始链接
4. **综合观察**（synthesis）：一段话总结——主流声音是什么、有什么分歧、值得注意的独特视角

要求：
- 直接呈现各方观点，不做看多/看空分类
- 保留信息多样性，不要只选同质观点
- Twitter 推文必须完整翻译原文，不要概括提炼
- 输出JSON格式

=== TWITTER 数据 ===
{twitter_text if twitter_text else "（无 Twitter 数据）"}

=== WEB 数据 ===
{web_text if web_text else "（无 Web 数据）"}

请输出JSON：
{{
  "event_summary": "...",
  "twitter_opinions": [
    {{"author": "@xxx (Name)", "opinion": "推文原文的完整中文翻译...", "engagement": "❤️ X 🔄 Y", "url": "..."}}
  ],
  "web_opinions": [
    {{"source": "The Verge", "opinion": "...", "url": "..."}}
  ],
  "synthesis": "..."
}}"""

    print(f"  [LLM] Sending {len(tweets)} tweets + {len(web_results)} articles for analysis...")
    result = generate_content(prompt=prompt, use_fast_model=False, return_json=True)

    if isinstance(result, dict):
        n_tw = len(result.get("twitter_opinions", []))
        n_web = len(result.get("web_opinions", []))
        print(f"  [LLM] Extracted {n_tw} Twitter opinions + {n_web} Web opinions")
        return result

    print(f"  [LLM] Unexpected output type: {type(result)}")
    return {
        "event_summary": f"关于{topic}的热点事件。",
        "twitter_opinions": [],
        "web_opinions": [],
        "synthesis": "LLM 分析失败，请检查数据源。",
    }


# ============================================================
# Phase 4: Report Assembly
# ============================================================

def build_report(topic: str, analysis: dict, n_tweets: int, n_web: int) -> str:
    """Assemble Markdown report from LLM analysis."""
    print(f"\n{'='*50}")
    print(f"Phase 4: Report Assembly")
    print(f"{'='*50}")

    today = datetime.date.today().strftime("%Y-%m-%d")

    # Header
    md = f"# 🔥 {topic} — 观点速览\n\n"
    md += f"> 生成时间：{today} | 数据源：Twitter {n_tweets} 条 + Web {n_web} 篇\n\n"

    # Event Summary
    md += "## 📌 事件概要\n\n"
    md += analysis.get("event_summary", "暂无概要。") + "\n\n"

    # Twitter Opinions
    twitter_ops = analysis.get("twitter_opinions", [])
    if twitter_ops:
        md += "## 🗣️ Twitter/X 热议\n\n"
        md += "| 来源 | 原文翻译 | 互动量 | 链接 |\n"
        md += "|------|----------|--------|------|\n"
        for op in twitter_ops:
            author = op.get("author", "")
            opinion = op.get("opinion", "").replace("|", "\\|").replace("\n", " ")
            engagement = op.get("engagement", "")
            url = op.get("url", "")
            link_text = f"[🔗]({url})" if url else "-"
            md += f"| {author} | {opinion} | {engagement} | {link_text} |\n"
        md += "\n"

    # Web Opinions
    web_ops = analysis.get("web_opinions", [])
    if web_ops:
        md += "## 📰 媒体/博客报道\n\n"
        md += "| 来源 | 核心观点 | 链接 |\n"
        md += "|------|----------|------|\n"
        for op in web_ops:
            source = op.get("source", "")
            opinion = op.get("opinion", "").replace("|", "\\|").replace("\n", " ")
            url = op.get("url", "")
            link_text = f"[🔗]({url})" if url else "-"
            md += f"| {source} | {opinion} | {link_text} |\n"
        md += "\n"

    # Synthesis
    md += "## 💡 综合观察\n\n"
    md += analysis.get("synthesis", "暂无综合分析。") + "\n"

    print(f"  [Report] {len(md):,} chars generated")
    return md


# ============================================================
# Main Pipeline
# ============================================================

def run_hot_take(topic: str, output_dir: str, max_tweets: int = 20, max_web: int = 15):
    """Main pipeline: keyword gen → data collection → LLM → report."""
    print(f"\n{'='*60}")
    print(f"🔥 Hot Take: {topic}")
    print(f"{'='*60}")

    os.makedirs(output_dir, exist_ok=True)

    # Phase 1: Generate search keywords
    print(f"\n{'='*50}")
    print(f"Phase 1: Search Keyword Generation")
    print(f"{'='*50}")
    keywords = generate_hot_take_keywords(topic, count=5)

    # Phase 2: Collect data
    tweets = collect_twitter_opinions(keywords, max_tweets=max_tweets)
    web_results = collect_web_opinions(keywords, max_web=max_web)

    if not tweets and not web_results:
        print("\n⚠️ No data collected from any source. Aborting.")
        return

    # Phase 3: LLM analysis
    analysis = extract_opinions_from_sources(topic, tweets, web_results)

    # Phase 4: Build report
    md_content = build_report(topic, analysis, len(tweets), len(web_results))

    # Save files
    today = datetime.date.today().strftime("%Y%m%d")
    # Sanitize topic for filename
    safe_topic = "".join(c if c.isalnum() or c in "_ -" else "_" for c in topic)[:30]
    base_name = f"hot_take_{safe_topic}_{today}"

    md_path = os.path.join(output_dir, f"{base_name}.md")
    docx_path = os.path.join(output_dir, f"{base_name}.docx")

    # Save Markdown
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)
    print(f"\n  ✅ Markdown: {md_path}")

    # Save Word
    try:
        convert_md_to_word(md_path, docx_path)
        print(f"  ✅ Word: {docx_path}")
    except Exception as e:
        print(f"  ⚠️ Word conversion failed: {e}")
        print(f"  Markdown report is still available at: {md_path}")

    # Save raw data for reference
    raw_path = os.path.join(output_dir, f"{base_name}_raw.json")
    raw_data = {
        "topic": topic,
        "keywords": keywords,
        "tweets_count": len(tweets),
        "web_count": len(web_results),
        "analysis": analysis,
    }
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(raw_data, f, ensure_ascii=False, indent=2)
    print(f"  ✅ Raw data: {raw_path}")

    print(f"\n{'='*60}")
    print(f"🔥 Hot Take 完成！")
    print(f"{'='*60}")


# ============================================================
# CLI Entry Point
# ============================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Hot Take: 热点事件观点速览")
    parser.add_argument("--topic", required=True, help="事件名称/关键词，如 'Sora关停'")
    parser.add_argument("--output", required=True, help="输出目录")
    parser.add_argument("--max-tweets", type=int, default=20, help="Twitter 最大条数 (default: 20)")
    parser.add_argument("--max-web", type=int, default=15, help="Web 最大结果数 (default: 15)")

    args = parser.parse_args()
    run_hot_take(
        topic=args.topic,
        output_dir=args.output,
        max_tweets=args.max_tweets,
        max_web=args.max_web,
    )
