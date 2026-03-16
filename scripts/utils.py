"""
Utility functions for Professional Research Skill.
Handles API key management, JSON parsing, retry logic, and common helpers.
"""

import os
import re
import json
import time
import functools
from datetime import datetime


# ============================================================
# API Key Management
# ============================================================

_env_loaded = False

def _load_dotenv():
    """Load .env file from skill root directory (one-time)."""
    global _env_loaded
    if _env_loaded:
        return
    _env_loaded = True
    
    skill_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env_path = os.path.join(skill_dir, ".env")
    
    if not os.path.exists(env_path):
        return
    
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and value and key not in os.environ:
                    os.environ[key] = value


def get_api_key(name: str) -> str:
    """
    Get API key. Priority: system env var > .env file in skill root.
    
    Supported keys:
        GEMINI_API_KEY, TAVILY_API_KEY, TWITTER_API_KEY
    
    Raises EnvironmentError if key is not found.
    """
    _load_dotenv()  # Auto-load .env on first call
    
    value = os.environ.get(name, "").strip()
    if not value:
        raise EnvironmentError(
            f"API key '{name}' not found. Two ways to set it:\n"
            f"  1. Copy .env.example → .env and fill in your key\n"
            f"  2. Set env var: $env:{name}='your-key-here'"
        )
    return value


# ============================================================
# JSON Parsing (LLM output)
# ============================================================

def parse_json_response(text: str):
    """
    Extract JSON from LLM response text.
    Handles common formats:
    - Pure JSON
    - ```json ... ``` wrapped
    - JSON with surrounding text
    
    Returns parsed Python object (dict or list).
    Raises ValueError if no valid JSON found.
    """
    if not text:
        raise ValueError("Empty response text")
    
    text = text.strip()
    
    # Try 1: Direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    
    # Try 2: Extract from ```json ... ``` block
    json_block = re.search(r'```(?:json)?\s*\n?(.*?)\n?\s*```', text, re.DOTALL)
    if json_block:
        try:
            return json.loads(json_block.group(1).strip())
        except json.JSONDecodeError:
            pass
    
    # Try 3: Find first { or [ and match to last } or ]
    for start_char, end_char in [('{', '}'), ('[', ']')]:
        start_idx = text.find(start_char)
        end_idx = text.rfind(end_char)
        if start_idx != -1 and end_idx > start_idx:
            try:
                return json.loads(text[start_idx:end_idx + 1])
            except json.JSONDecodeError:
                continue
    
    raise ValueError(f"Could not parse JSON from response: {text[:200]}...")


# ============================================================
# Retry Logic
# ============================================================

def retry_with_backoff(max_retries: int = 3, base_delay: float = 5.0,
                       max_delay: float = 60.0, retryable_exceptions=(Exception,)):
    """
    Decorator for retry with exponential backoff.
    
    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay in seconds
        max_delay: Maximum delay cap in seconds
        retryable_exceptions: Tuple of exception types to retry on
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except retryable_exceptions as e:
                    last_exception = e
                    if attempt < max_retries:
                        delay = min(base_delay * (2 ** attempt), max_delay)
                        print(f"  [Retry {attempt + 1}/{max_retries}] "
                              f"{type(e).__name__}: {str(e)[:100]}. "
                              f"Waiting {delay:.0f}s...")
                        time.sleep(delay)
                    else:
                        print(f"  [Failed] All {max_retries} retries exhausted.")
            raise last_exception
        return wrapper
    return decorator


# ============================================================
# File & Path Helpers
# ============================================================

def get_skill_dir() -> str:
    """Get the absolute path of the skill directory (parent of scripts/)."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_template_path(template_name: str) -> str:
    """Get absolute path to a template file."""
    return os.path.join(get_skill_dir(), "templates", template_name)


def get_config_path(config_name: str) -> str:
    """Get absolute path to a config file."""
    return os.path.join(get_skill_dir(), "config", config_name)


def get_reference_path(reference_name: str) -> str:
    """Get absolute path to a reference file."""
    return os.path.join(get_skill_dir(), "references", reference_name)


def read_template(template_name: str) -> str:
    """
    Read a template file and return its content.
    Always reads fresh from disk (templates are user-editable).
    """
    path = get_template_path(template_name)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Template not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def read_config(config_name: str):
    """Read a JSON config file and return parsed content."""
    path = get_config_path(config_name)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Config not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def sanitize_filename(name: str, max_length: int = 80) -> str:
    """
    Create a safe filename from arbitrary text.
    Replaces unsafe characters, truncates to max_length.
    """
    # Replace unsafe characters
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name)
    # Collapse multiple underscores
    safe = re.sub(r'_+', '_', safe).strip('_')
    # Truncate
    if len(safe) > max_length:
        safe = safe[:max_length].rstrip('_')
    return safe or "untitled"


def get_output_dir() -> str:
    """
    Get the standard output directory for reports.
    Priority:
      1. Environment variable RESEARCH_OUTPUT_DIR (if set)
      2. D:\\clauderesult\\claudeMMDD (if D:\\ exists, for the original author)
      3. ./output/ (portable fallback)
    Creates the directory if it doesn't exist.
    """
    # Check env var first
    custom = os.environ.get("RESEARCH_OUTPUT_DIR", "").strip()
    if custom:
        os.makedirs(custom, exist_ok=True)
        return custom
    
    # Original author's path
    today = datetime.now().strftime("%m%d")
    personal_dir = os.path.join("D:\\clauderesult", f"claude{today}")
    if os.path.exists("D:\\clauderesult"):
        os.makedirs(personal_dir, exist_ok=True)
        return personal_dir
    
    # Portable fallback
    fallback = os.path.join(os.getcwd(), "output")
    os.makedirs(fallback, exist_ok=True)
    return fallback


def get_timestamp() -> str:
    """Get current timestamp string for filenames."""
    return datetime.now().strftime("%Y%m%d_%H%M%S")


# ============================================================
# Data Deduplication
# ============================================================

def normalize_url(url: str) -> str:
    """
    Normalize URL for deduplication.
    Strips www./wap. prefixes, removes fragments.
    """
    from urllib.parse import urlparse, urlunparse
    parsed = urlparse(url)
    host = re.sub(r'^(wap\.|www\.)', '', parsed.netloc.lower())
    return urlunparse((parsed.scheme, host, parsed.path.rstrip('/'),
                       parsed.params, parsed.query, ''))


def deduplicate_results(results: list, key_field: str = "url") -> list:
    """
    Deduplicate a list of dicts by a key field (default: url).
    Uses URL normalization for URL fields.
    """
    seen = set()
    unique = []
    for item in results:
        key = item.get(key_field, "")
        if key_field == "url":
            key = normalize_url(key)
        if key and key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


# ============================================================
# Search Attempt Tracking (3-Strike Rule)
# ============================================================

class SearchAttemptTracker:
    """
    Tracks search attempts per data point.
    Enforces the 3-strike rule: max 3 attempts per item.
    """
    
    def __init__(self, max_attempts: int = 3):
        self.max_attempts = max_attempts
        self._attempts = {}  # key -> count
        self._not_found = set()  # keys that exhausted attempts
    
    def can_search(self, key: str) -> bool:
        """Check if we can still search for this data point."""
        return self._attempts.get(key, 0) < self.max_attempts
    
    def record_attempt(self, key: str, found: bool = False):
        """Record a search attempt. If found=True, remove from tracking."""
        if found:
            self._attempts.pop(key, None)
            self._not_found.discard(key)
            return
        
        self._attempts[key] = self._attempts.get(key, 0) + 1
        if self._attempts[key] >= self.max_attempts:
            self._not_found.add(key)
            print(f"  [3-Strike] '{key}' not found after {self.max_attempts} attempts. "
                  f"Will report as '未找到相关数据'.")
    
    def get_not_found(self) -> set:
        """Get all data points that were not found after max attempts."""
        return self._not_found.copy()
