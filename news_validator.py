"""
News Validator Module - Google News RSS Feed Checker
=====================================================
Validates whether tokens have legitimate news coverage by checking
Google News RSS feeds. This helps filter out pump-and-dump schemes
without real-world narrative backing.

Features:
- Google News RSS feed parsing
- Query-based search with caching
- Returns structured validation results
- Respects rate limits and cache TTL
"""

import feedparser
import requests
import time
from typing import Dict, Any, List, Optional
from urllib.parse import quote_plus
from colorama import init, Fore, Style
from datetime import datetime, timedelta

from rate_limiter import rate_limit
import config

# Initialize colorama
init(autoreset=True)

# Constants from config
RSS_URL_TEMPLATE = config.GOOGLE_NEWS_RSS_URL_TEMPLATE
CACHE_TTL_SECONDS = config.GOOGLE_NEWS_CACHE_TTL_SECONDS
GOOGLE_NEWS_RPM = config.GOOGLE_NEWS_RPM
REQUEST_TIMEOUT_SECONDS = config.API_TIMEOUT_SECONDS

# Security check result levels
LEVEL_DANGER = "DANGER"
LEVEL_WARNING = "WARNING"
LEVEL_OK = "OK"
LEVEL_UNKNOWN = "UNKNOWN"

# Simple cache dictionary {query: (timestamp, result)}
_cache: Dict[str, tuple[float, Dict[str, Any]]] = {}


def _is_cache_valid(query: str) -> bool:
    """Check if cached result exists and is still valid."""
    if query not in _cache:
        return False
    
    timestamp, _ = _cache[query]
    age_seconds = time.time() - timestamp
    return age_seconds < CACHE_TTL_SECONDS


def _get_cached_result(query: str) -> Optional[Dict[str, Any]]:
    """Retrieve cached result if valid, else None."""
    if _is_cache_valid(query):
        _, result = _cache[query]
        return result
    return None


def _set_cache(query: str, result: Dict[str, Any]) -> None:
    """Store result in cache with current timestamp."""
    _cache[query] = (time.time(), result)


@rate_limit(requests_per_minute=GOOGLE_NEWS_RPM)
def _fetch_rss_feed(query: str, verbose: bool = True) -> Dict[str, Any]:
    """
    Fetch and parse Google News RSS feed for a given query.
    
    Args:
        query: Search query string
        verbose: If True, print status messages
        
    Returns:
        Dict containing parsed feed data with entries
    """
    encoded_query = quote_plus(query)
    url = RSS_URL_TEMPLATE.format(query=encoded_query)
    
    if verbose:
        print(f"  {Fore.CYAN}[NEWS] Fetching Google News RSS for: {query}{Style.RESET_ALL}")
    
    try:
        response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        
        # Parse RSS feed using feedparser
        feed = feedparser.parse(response.content)
        
        if verbose:
            entry_count = len(feed.entries) if hasattr(feed, 'entries') else 0
            print(f"  {Fore.GREEN}[OK] Found {entry_count} news articles{Style.RESET_ALL}")
        
        return {
            "success": True,
            "feed": feed,
            "entries": feed.entries if hasattr(feed, 'entries') else [],
            "error": None
        }
        
    except requests.exceptions.Timeout:
        if verbose:
            print(f"  {Fore.YELLOW}[WARN] Request timeout{Style.RESET_ALL}")
        return {"success": False, "feed": None, "entries": [], "error": "Timeout"}
        
    except requests.exceptions.RequestException as e:
        if verbose:
            print(f"  {Fore.RED}[ERROR] Request failed: {e}{Style.RESET_ALL}")
        return {"success": False, "feed": None, "entries": [], "error": str(e)}
        
    except Exception as e:
        if verbose:
            print(f"  {Fore.RED}[ERROR] Parsing error: {e}{Style.RESET_ALL}")
        return {"success": False, "feed": None, "entries": [], "error": str(e)}


def validate_news(
    query: str,
    token_name: Optional[str] = None,
    matched_narrative: Optional[str] = None,
    verbose: bool = True
) -> Dict[str, Any]:
    """
    Validate whether a token has legitimate news coverage.
    
    This function searches Google News RSS feeds to determine if there's
    real-world news about the token or its related narrative.
    
    Args:
        query: Primary search query (usually token name + symbol)
        token_name: Optional token name for enhanced search
        matched_narrative: Optional narrative to prioritize in search
        verbose: If True, print status messages
        
    Returns:
        Dict with structure:
        {
            "level": str,  # "OK", "WARNING", "DANGER", or "UNKNOWN"
            "reason": str,  # Human-readable explanation
            "has_news": bool,  # True if news articles found
            "article_count": int,  # Number of articles found
            "articles": List[Dict],  # List of article metadata
        }
        
    Example:
        >>> result = validate_news("Trump Victory Token TRUMP")
        >>> print(result["level"])  # "OK"
        >>> print(result["article_count"])  # 5
    """
    # Check cache first
    cache_key = f"{query}|{matched_narrative or ''}"
    cached = _get_cached_result(cache_key)
    if cached is not None:
        if verbose:
            print(f"  {Fore.CYAN}[CACHE] Using cached news result{Style.RESET_ALL}")
        return cached
    
    # Prioritize matched_narrative if provided
    search_query = query
    if matched_narrative:
        search_query = f"{matched_narrative} {query}"
        if verbose:
            print(f"  {Fore.CYAN}[TARGET] Prioritizing narrative: {matched_narrative}{Style.RESET_ALL}")
    
    # Fetch RSS feed
    feed_result = _fetch_rss_feed(search_query, verbose=verbose)
    
    if not feed_result["success"]:
        result = {
            "level": LEVEL_UNKNOWN,
            "reason": f"Failed to fetch news: {feed_result['error']}",
            "has_news": False,
            "article_count": 0,
            "articles": []
        }
        _set_cache(cache_key, result)
        return result
    
    # Process articles
    entries = feed_result["entries"]
    article_count = len(entries)
    
    # Extract article metadata
    articles = []
    for entry in entries[:10]:  # Limit to first 10 articles
        article = {
            "title": entry.get("title", ""),
            "link": entry.get("link", ""),
            "published": entry.get("published", ""),
            "source": entry.get("source", {}).get("title", "Unknown")
        }
        articles.append(article)
    
    # Determine validation level
    if article_count == 0:
        level = LEVEL_WARNING
        reason = "No news coverage found"
        has_news = False
        if verbose:
            print(f"  {Fore.YELLOW}[WARN] WARNING: No news articles found{Style.RESET_ALL}")
    else:
        level = LEVEL_OK
        reason = f"Found {article_count} news article{'s' if article_count != 1 else ''}"
        has_news = True
        if verbose:
            print(f"  {Fore.GREEN}[OK] Found {article_count} news articles{Style.RESET_ALL}")
    
    result = {
        "level": level,
        "reason": reason,
        "has_news": has_news,
        "article_count": article_count,
        "articles": articles
    }
    
    # Cache the result
    _set_cache(cache_key, result)
    
    return result


def clear_cache() -> None:
    """Clear the news validation cache. Useful for testing."""
    global _cache
    _cache.clear()


def get_cache_stats() -> Dict[str, Any]:
    """
    Get cache statistics for debugging.
    
    Returns:
        Dict with cache size and entry details
    """
    now = time.time()
    valid_entries = sum(1 for ts, _ in _cache.values() if now - ts < CACHE_TTL_SECONDS)
    
    return {
        "total_entries": len(_cache),
        "valid_entries": valid_entries,
        "expired_entries": len(_cache) - valid_entries,
        "cache_ttl_seconds": CACHE_TTL_SECONDS
    }


if __name__ == "__main__":
    # Test the module with a sample query
    print("=" * 60)
    print("News Validator Test")
    print("=" * 60)
    print()
    
    # Test 1: Popular topic with news
    print("Test 1: Popular Topic (Trump)")
    result1 = validate_news("Trump election", verbose=True)
    print(f"Result: {result1['level']} - {result1['reason']}")
    print(f"Articles: {result1['article_count']}")
    print()
    
    # Test 2: Obscure topic without news
    print("Test 2: Obscure Topic")
    result2 = validate_news("XYZ123FakeToken999", verbose=True)
    print(f"Result: {result2['level']} - {result2['reason']}")
    print(f"Articles: {result2['article_count']}")
    print()
    
    # Test 3: Cached result
    print("Test 3: Cached Result (should be instant)")
    result3 = validate_news("Trump election", verbose=True)
    print(f"Result: {result3['level']} - {result3['reason']}")
    print()
    
    # Cache stats
    print("Cache Statistics:")
    stats = get_cache_stats()
    print(f"  Total entries: {stats['total_entries']}")
    print(f"  Valid entries: {stats['valid_entries']}")
    print(f"  Expired entries: {stats['expired_entries']}")
    print(f"  TTL: {stats['cache_ttl_seconds']}s")
