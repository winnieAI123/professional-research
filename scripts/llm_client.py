"""
Gemini API client with automatic model fallback chain and retry logic.
Handles 503/429 errors gracefully by switching models.
"""

import time
import json
from google import genai

# Import from sibling module
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from utils import get_api_key, parse_json_response


# ============================================================
# Model Fallback Chain
# ============================================================

# Ordered by preference. On 503, try the next model in chain.
MODEL_FALLBACK_CHAIN = [
    "models/gemini-3-pro-preview",
    "models/gemini-2.5-flash",
    "models/gemini-2.5-pro",
]

# Lighter model for filtering/classification tasks (cost optimization)
FAST_MODEL = "models/gemini-2.0-flash"

# Default delays
LLM_CALL_DELAY = 3  # seconds between calls
RETRY_BASE_DELAY = 10  # seconds for first retry


# ============================================================
# Client Initialization
# ============================================================

_client = None

def get_client() -> genai.Client:
    """Get or create the Gemini API client."""
    global _client
    if _client is None:
        api_key = get_api_key("GEMINI_API_KEY")
        _client = genai.Client(api_key=api_key)
    return _client


# ============================================================
# Core Generation Function
# ============================================================

def generate_content(
    prompt: str,
    model: str = None,
    use_fast_model: bool = False,
    max_retries: int = 3,
    temperature: float = None,
    return_json: bool = False,
    max_output_tokens: int = None,
) -> str:
    """
    Generate content using Gemini API with automatic fallback.
    
    Args:
        prompt: The prompt text to send
        model: Specific model to use (overrides defaults)
        use_fast_model: If True, use the fast/cheap model (gemini-2.0-flash)
        max_retries: Max retries per model before moving to next
        temperature: Generation temperature (None = model default)
        return_json: If True, parse and return JSON from response
    
    Returns:
        Response text (str) or parsed JSON (if return_json=True)
    
    Raises:
        RuntimeError: If all models in fallback chain fail
    """
    client = get_client()
    
    # Determine model list to try
    if model:
        models_to_try = [model]
    elif use_fast_model:
        models_to_try = [FAST_MODEL] + MODEL_FALLBACK_CHAIN
    else:
        models_to_try = MODEL_FALLBACK_CHAIN
    
    # Build generation config
    gen_config = {}
    if temperature is not None:
        gen_config["temperature"] = temperature
    if max_output_tokens is not None:
        gen_config["max_output_tokens"] = max_output_tokens
    
    last_error = None
    
    for model_name in models_to_try:
        for attempt in range(max_retries):
            try:
                kwargs = {
                    "model": model_name,
                    "contents": prompt,
                }
                if gen_config:
                    kwargs["config"] = gen_config
                
                response = client.models.generate_content(**kwargs)
                
                result_text = response.text.strip() if response.text else ""
                
                if not result_text:
                    print(f"  [Warning] Empty response from {model_name}, retrying...")
                    time.sleep(LLM_CALL_DELAY)
                    continue
                
                # Add delay between calls to avoid rate limiting
                time.sleep(LLM_CALL_DELAY)
                
                if return_json:
                    return parse_json_response(result_text)
                return result_text
                
            except Exception as e:
                error_str = str(e).lower()
                last_error = e
                
                is_503 = "503" in error_str or "service unavailable" in error_str
                is_429 = "429" in error_str or "resource exhausted" in error_str or "rate limit" in error_str
                
                if is_503:
                    print(f"  [503] Model {model_name} unavailable. "
                          f"Switching to next model...")
                    break  # Skip remaining retries, try next model
                
                elif is_429:
                    delay = RETRY_BASE_DELAY * (2 ** min(attempt, 3))
                    print(f"  [429] Rate limited on {model_name}. "
                          f"Retry {attempt + 1}/{max_retries}, "
                          f"waiting {delay:.0f}s...")
                    time.sleep(delay)
                    continue
                
                else:
                    # Unknown error — retry with backoff
                    delay = RETRY_BASE_DELAY * (2 ** min(attempt, 2))
                    print(f"  [Error] {type(e).__name__}: {str(e)[:150]}. "
                          f"Retry {attempt + 1}/{max_retries}, "
                          f"waiting {delay:.0f}s...")
                    time.sleep(delay)
                    continue
    
    raise RuntimeError(
        f"All models in fallback chain failed. Last error: {last_error}"
    )


# ============================================================
# Convenience Functions
# ============================================================

def classify_intent(user_input: str, classification_prompt: str) -> dict:
    """
    Classify user research intent using fast model.
    Returns parsed JSON with classification result.
    """
    return generate_content(
        prompt=classification_prompt.format(user_input=user_input),
        use_fast_model=True,
        return_json=True,
    )


def extract_structured_data(content: str, extraction_prompt: str) -> dict:
    """
    Extract structured data from article/document content.
    Uses the main (pro) model for better quality.
    """
    return generate_content(
        prompt=extraction_prompt.format(content=content),
        return_json=True,
    )


def generate_report_section(
    template_content: str,
    collected_data: str,
    section_prompt: str,
) -> str:
    """
    Generate a report section by feeding template + data to Gemini.
    
    Args:
        template_content: The MD template content (read fresh from file)
        collected_data: Stringified collected & normalized data
        section_prompt: Additional instructions for this section
    
    Returns:
        Generated markdown text following the template structure
    """
    full_prompt = f"""你是一位顶级机构的行业研究分析师。请根据以下模板格式和采集到的数据，撰写研究报告。

## 模板格式（必须严格遵循此结构）

{template_content}

## 采集到的数据

{collected_data}

## 撰写要求

{section_prompt}

## 重要规则
1. 严格按照模板格式输出，保持所有章节结构
2. 所有数据必须来自上方提供的采集数据，绝对不能编造
3. 如果某个字段没有数据，标注"未找到相关数据（截至搜索日期）"
4. 数据来源必须标注出处
5. 用中文撰写报告
6. 输出纯 Markdown 格式，不要包裹在代码块中

请直接输出完整的报告内容："""
    
    return generate_content(
        prompt=full_prompt,
        temperature=0.3,  # Lower temperature for factual accuracy
    )


def filter_items(items_text: str, criteria: str) -> list:
    """
    Use fast model to filter/score items by relevance.
    
    Args:
        items_text: Formatted text of items to filter
        criteria: What to filter for
    
    Returns:
        List of dicts with index and relevance score
    """
    prompt = f"""请判断以下条目与研究需求的相关性。

研究需求：{criteria}

条目列表：
{items_text}

对每个条目输出JSON数组：
[{{"index": 0, "relevant": true, "relevance_score": 8, "reason": "简要原因"}}]

只输出JSON，不要其他内容。"""
    
    return generate_content(
        prompt=prompt,
        use_fast_model=True,
        return_json=True,
    )


def extract_opinions(text: str = None, topic: str = "", source_url: str = "",
                     article_content: str = None, source_type: str = "") -> dict:
    """
    Read full article content and extract structured opinions.
    Accepts either 'text' or 'article_content' for the content body.
    Used in Trend Analysis (Type 4) pipeline.
    """
    # Support both parameter names
    content = text or article_content or ""
    source = source_url or source_type or "unknown"
    
    prompt = f"""请阅读以下文章全文，提取与"{topic}"相关的观点。

文章来源：{source}
文章全文：
{content[:30000]}

请按以下JSON格式输出数组（中文），每个观点一个对象：
[{{
    "author": "文章作者（如能识别）",
    "stance": "看好/看衰/中立",
    "core_opinion": "用一句话概括核心观点",
    "key_arguments": ["论据1", "论据2", "论据3"],
    "original_quotes": ["直接引用的原文关键句子1", "原文关键句子2"],
    "relevance_score": 8,
    "source_type": "{source}"
}}]
只输出JSON数组，不要其他内容。"""
    
    return generate_content(prompt=prompt, return_json=True)


def generate_search_keywords(topic: str, count: int = 5) -> list:
    """
    Generate targeted search keywords for a research topic.
    Used in Type 4 Trend Analysis to create diverse Twitter/web searches.
    
    Args:
        topic: User's research topic (e.g., "AI Coding趋势")
        count: Number of keywords to generate (default 5)
    
    Returns:
        List of English keyword strings for search APIs
    """
    prompt = f"""你是一个搜索策略专家。用户想研究"{topic}"的趋势。
请生成{count}个英文搜索关键词/短语，用于在Twitter/X上搜索高质量讨论。

要求：
1. 每个关键词2-5个英文单词
2. 覆盖不同角度（技术术语、产品名、趋势词、争议点等）
3. 使用Twitter上实际常用的表达方式
4. 不要太泛（如"AI"太宽），也不要太窄
5. 输出JSON数组

示例（假设话题是"具身智能"）：
["embodied AI robotics", "humanoid robot progress", "physical AI agent", "robot foundation model", "Tesla Optimus Figure"]

现在为"{topic}"生成{count}个搜索关键词："""

    result = generate_content(prompt=prompt, use_fast_model=True, return_json=True)
    
    if isinstance(result, list) and all(isinstance(k, str) for k in result):
        print(f"  [Keywords] Generated {len(result)} search terms: {result}")
        return result[:count]
    
    # Fallback: use topic directly
    print(f"  [Keywords] LLM output unexpected, using topic as keyword")
    return [topic]


def analyze_paper(paper_text: str, paper_title: str) -> dict:
    """
    Deep analysis of an academic paper's full text.
    Used in Industry Research (Type 3 tech) and Academic Briefing (Type 6).
    """
    prompt = f"""你是一位擅长把复杂技术讲得通俗易懂的科技记者。
请深度分析以下论文全文，提取结构化信息。

论文标题：{paper_title}
论文全文：
{paper_text[:40000]}

请按以下JSON格式输出（中文，术语后紧跟括号解释）：
{{
    "title_zh": "论文标题中文翻译",
    "core_problem": "该论文要解决什么问题？",
    "proposed_method": "用通俗语言描述技术方案，避免术语堆砌",
    "key_innovations": ["创新点1", "创新点2"],
    "experiment_results": [
        {{"benchmark": "基准名称", "result": "本文结果", "previous_best": "此前最好", "improvement": "+X%"}}
    ],
    "limitations": "局限性",
    "industry_implications": "对行业的启示",
    "summary_zh": "3-5句通俗摘要，150-200字，用大白话写",
    "one_liner": "一句话概括"
}}
只输出JSON，不要其他内容。"""
    
    return generate_content(prompt=prompt, return_json=True)
