"""
Twitter/X data collection using twitterapi.io API.
Collects tweets by keyword search and specific KOL accounts.
"""

import time
import requests
from utils import get_api_key


SEARCH_URL = "https://api.twitterapi.io/twitter/tweet/advanced_search"


# ============================================================
# Tweet Search
# ============================================================

def search_tweets(
    query: str,
    total_count: int = 50,
    query_type: str = "Top",
) -> list:
    """
    Search tweets by keyword using twitterapi.io.
    
    Args:
        query: Twitter advanced search query
        total_count: Maximum number of tweets to return
        query_type: "Top" (most engaged) or "Latest"
    
    Returns:
        List of parsed tweet dicts
    """
    api_key = get_api_key("TWITTER_API_KEY")
    headers = {"X-API-Key": api_key}
    
    all_tweets = []
    cursor = ""
    
    while len(all_tweets) < total_count:
        params = {
            "query": query,
            "queryType": query_type,
            "cursor": cursor,
        }
        
        try:
            resp = requests.get(
                SEARCH_URL,
                headers=headers,
                params=params,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            
            tweets = data.get("tweets", [])
            if not tweets:
                break
            
            for tweet in tweets:
                all_tweets.append(_parse_tweet(tweet))
            
            if not data.get("has_next_page"):
                break
            
            cursor = data.get("next_cursor", "")
            time.sleep(0.5)
            
        except Exception as e:
            print(f"  [Twitter Search Error] {e}")
            break
    
    return all_tweets[:total_count]


def _parse_tweet(tweet: dict) -> dict:
    """Parse raw tweet data into structured format."""
    author = tweet.get("author", {})
    text = tweet.get("text", "")
    username = author.get("userName", "")
    name = author.get("name", "")
    date = tweet.get("createdAt", "")
    return {
        "url": tweet.get("url", ""),
        # Content fields (both names for compatibility)
        "content": text,
        "text": text,
        # Engagement
        "views": tweet.get("viewCount", 0) or 0,
        "likes": tweet.get("likeCount", 0) or 0,
        "retweets": tweet.get("retweetCount", 0) or 0,
        "replies": tweet.get("replyCount", 0) or 0,
        # Author fields (both naming conventions)
        "author_username": username,
        "username": username,
        "author_name": name,
        "name": name,
        "followers": author.get("followers", 0) or 0,
        "verified": author.get("isBlueVerified", False),
        # Date fields (both names)
        "date": date,
        "created_at": date,
        "source": "twitter",
    }


# ============================================================
# KOL-Specific Search
# ============================================================

def search_kol_tweets(
    kol_usernames: list,
    topic_query: str,
    tweets_per_kol: int = 10,
) -> list:
    """
    Search tweets from specific KOLs about a topic.
    
    Args:
        kol_usernames: List of Twitter usernames
        topic_query: Topic keywords to search for
        tweets_per_kol: Max tweets per KOL
    
    Returns:
        List of parsed tweets, sorted by engagement
    """
    all_tweets = []
    
    for username in kol_usernames:
        query = f"from:{username} {topic_query}"
        tweets = search_tweets(
            query=query,
            total_count=tweets_per_kol,
            query_type="Top",
        )
        all_tweets.extend(tweets)
        print(f"  [KOL] @{username} → {len(tweets)} tweets")
        time.sleep(1)
    
    # Sort by engagement (likes + retweets)
    all_tweets.sort(
        key=lambda x: x.get("likes", 0) + x.get("retweets", 0),
        reverse=True,
    )
    
    return all_tweets


def search_topic_tweets(
    topic_query: str,
    total_count: int = 30,
    min_likes: int = 0,
) -> list:
    """
    Search high-engagement tweets about a topic.
    
    Args:
        topic_query: English search keywords
        total_count: Max tweets to collect
        min_likes: Optional minimum likes filter (applied client-side)
    
    Returns:
        Filtered, sorted list of tweets
    """
    tweets = search_tweets(
        query=topic_query,
        total_count=total_count * 2,  # Over-collect to account for filtering
        query_type="Top",
    )
    
    if min_likes > 0:
        tweets = [t for t in tweets if t.get("likes", 0) >= min_likes]
    
    return tweets[:total_count]
