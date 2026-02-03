"""
Unit tests for news_validator.py module.

Tests cover:
- Google News RSS feed fetching
- News validation logic
- Caching behavior
- Rate limiting
- Success and failure cases
"""

import pytest
import time
from unittest.mock import Mock, patch, MagicMock

from news_validator import (
    validate_news,
    clear_cache,
    get_cache_stats,
    _fetch_rss_feed,
    _is_cache_valid,
    _get_cached_result,
    _set_cache,
    LEVEL_OK,
    LEVEL_WARNING,
    LEVEL_UNKNOWN,
)


# =============================================================================
# TEST FIXTURES
# =============================================================================

@pytest.fixture(autouse=True)
def clear_cache_before_test():
    """Clear cache before each test and disable rate limiting."""
    clear_cache()
    # Patch the rate limiter to not sleep during tests
    with patch('news_validator.rate_limit', lambda rpm: lambda f: f):
        yield
    clear_cache()


@pytest.fixture(autouse=True)
def disable_rate_limiter():
    """Disable rate limiter for all tests to prevent timeouts."""
    import rate_limiter
    original_wait = rate_limiter.RateLimiter.wait_if_needed
    rate_limiter.RateLimiter.wait_if_needed = lambda self: None
    yield
    rate_limiter.RateLimiter.wait_if_needed = original_wait


@pytest.fixture
def mock_feed_with_entries():
    """Mock feedparser result with news entries."""
    mock_feed = Mock()
    mock_feed.entries = [
        {
            "title": "Trump wins election",
            "link": "https://example.com/1",
            "published": "2025-02-03T10:00:00Z",
            "source": {"title": "CNN"}
        },
        {
            "title": "Election results announced",
            "link": "https://example.com/2",
            "published": "2025-02-03T09:00:00Z",
            "source": {"title": "Reuters"}
        }
    ]
    return mock_feed


@pytest.fixture
def mock_feed_empty():
    """Mock feedparser result with no entries."""
    mock_feed = Mock()
    mock_feed.entries = []
    return mock_feed


# =============================================================================
# CACHE TESTS
# =============================================================================

def test_cache_hit():
    """Test that cached results are returned."""
    # Pre-populate cache
    _set_cache("test_query|", {
        "level": LEVEL_OK,
        "reason": "Cached result",
        "has_news": True,
        "article_count": 5,
        "articles": []
    })
    
    result = validate_news("test_query", verbose=False)
    
    assert result["level"] == LEVEL_OK
    assert result["reason"] == "Cached result"


def test_cache_miss():
    """Test that cache miss triggers API call."""
    mock_response = Mock()
    mock_response.content = b"<rss></rss>"
    mock_response.raise_for_status = Mock()
    
    with patch('news_validator.requests.get', return_value=mock_response), \
         patch('news_validator.feedparser.parse') as mock_parse:
        
        mock_parse.return_value = Mock(entries=[])
        
        result = validate_news("new_query", verbose=False)
        
        # Should have made the API call
        assert result["level"] == LEVEL_WARNING  # No articles found


def test_cache_stats():
    """Test cache statistics reporting."""
    _set_cache("query1|", {"level": LEVEL_OK, "reason": "test", "has_news": True, "article_count": 1, "articles": []})
    _set_cache("query2|", {"level": LEVEL_OK, "reason": "test", "has_news": True, "article_count": 1, "articles": []})
    
    stats = get_cache_stats()
    
    assert stats["total_entries"] == 2
    assert stats["valid_entries"] == 2


def test_cache_clear():
    """Test cache clearing."""
    _set_cache("query1|", {"level": LEVEL_OK, "reason": "test", "has_news": True, "article_count": 1, "articles": []})
    
    clear_cache()
    
    stats = get_cache_stats()
    assert stats["total_entries"] == 0


# =============================================================================
# RSS FEED FETCH TESTS
# =============================================================================

def test_fetch_rss_feed_success(mock_feed_with_entries):
    """Test successful RSS feed fetch."""
    mock_response = Mock()
    mock_response.content = b"<rss>feed content</rss>"
    mock_response.raise_for_status = Mock()
    
    with patch('news_validator.requests.get', return_value=mock_response), \
         patch('news_validator.feedparser.parse', return_value=mock_feed_with_entries):
        
        result = _fetch_rss_feed("test query", verbose=False)
        
        assert result["success"] is True
        assert len(result["entries"]) == 2
        assert result["error"] is None


def test_fetch_rss_feed_timeout():
    """Test RSS feed fetch timeout handling."""
    import requests
    
    with patch('news_validator.requests.get', side_effect=requests.exceptions.Timeout()):
        result = _fetch_rss_feed("test query", verbose=False)
        
        assert result["success"] is False
        assert result["error"] == "Timeout"


def test_fetch_rss_feed_request_error():
    """Test RSS feed fetch error handling."""
    import requests
    
    with patch('news_validator.requests.get', side_effect=requests.exceptions.RequestException("Network error")):
        result = _fetch_rss_feed("test query", verbose=False)
        
        assert result["success"] is False
        assert "Network error" in result["error"]


# =============================================================================
# VALIDATE NEWS TESTS
# =============================================================================

def test_validate_news_with_articles(mock_feed_with_entries):
    """Test news validation when articles are found."""
    mock_response = Mock()
    mock_response.content = b"<rss>feed</rss>"
    mock_response.raise_for_status = Mock()
    
    with patch('news_validator.requests.get', return_value=mock_response), \
         patch('news_validator.feedparser.parse', return_value=mock_feed_with_entries):
        
        result = validate_news("Trump election", verbose=False)
        
        assert result["level"] == LEVEL_OK
        assert result["has_news"] is True
        assert result["article_count"] == 2
        assert len(result["articles"]) == 2


def test_validate_news_no_articles(mock_feed_empty):
    """Test news validation when no articles are found."""
    mock_response = Mock()
    mock_response.content = b"<rss>empty feed</rss>"
    mock_response.raise_for_status = Mock()
    
    with patch('news_validator.requests.get', return_value=mock_response), \
         patch('news_validator.feedparser.parse', return_value=mock_feed_empty):
        
        result = validate_news("XYZ123FakeToken999", verbose=False)
        
        assert result["level"] == LEVEL_WARNING
        assert result["has_news"] is False
        assert result["article_count"] == 0


def test_validate_news_with_matched_narrative(mock_feed_with_entries):
    """Test news validation with matched narrative priority."""
    mock_response = Mock()
    mock_response.content = b"<rss>feed</rss>"
    mock_response.raise_for_status = Mock()
    
    with patch('news_validator.requests.get', return_value=mock_response) as mock_get, \
         patch('news_validator.feedparser.parse', return_value=mock_feed_with_entries):
        
        result = validate_news(
            query="TRUMP",
            token_name="Trump Victory Token",
            matched_narrative="US Presidential Election",
            verbose=False
        )
        
        assert result["level"] == LEVEL_OK


def test_validate_news_api_failure():
    """Test news validation when API fails."""
    import requests
    
    with patch('news_validator.requests.get', side_effect=requests.exceptions.RequestException("API Error")):
        result = validate_news("test query", verbose=False)
        
        assert result["level"] == LEVEL_UNKNOWN
        assert result["has_news"] is False
        assert "Failed to fetch" in result["reason"]


def test_validate_news_caches_result(mock_feed_with_entries):
    """Test that validate_news caches the result."""
    mock_response = Mock()
    mock_response.content = b"<rss>feed</rss>"
    mock_response.raise_for_status = Mock()
    
    with patch('news_validator.requests.get', return_value=mock_response) as mock_get, \
         patch('news_validator.feedparser.parse', return_value=mock_feed_with_entries):
        
        # First call should hit the API
        result1 = validate_news("cache_test_query", verbose=False)
        
        # Second call should use cache
        result2 = validate_news("cache_test_query", verbose=False)
        
        # API should only be called once
        assert mock_get.call_count == 1
        
        # Results should be identical
        assert result1 == result2


def test_validate_news_article_extraction(mock_feed_with_entries):
    """Test that article metadata is correctly extracted."""
    mock_response = Mock()
    mock_response.content = b"<rss>feed</rss>"
    mock_response.raise_for_status = Mock()
    
    with patch('news_validator.requests.get', return_value=mock_response), \
         patch('news_validator.feedparser.parse', return_value=mock_feed_with_entries):
        
        result = validate_news("test query", verbose=False)
        
        assert len(result["articles"]) == 2
        
        # Check first article structure
        article = result["articles"][0]
        assert "title" in article
        assert "link" in article
        assert "published" in article
        assert "source" in article


def test_validate_news_limits_articles():
    """Test that articles are limited to 10."""
    mock_feed = Mock()
    mock_feed.entries = [
        {"title": f"Article {i}", "link": f"https://example.com/{i}", "published": "", "source": {"title": "Source"}}
        for i in range(15)  # More than 10 articles
    ]
    
    mock_response = Mock()
    mock_response.content = b"<rss>feed</rss>"
    mock_response.raise_for_status = Mock()
    
    with patch('news_validator.requests.get', return_value=mock_response), \
         patch('news_validator.feedparser.parse', return_value=mock_feed):
        
        result = validate_news("many articles", verbose=False)
        
        # Should limit to 10 articles
        assert len(result["articles"]) <= 10
        # But article_count reflects actual count
        assert result["article_count"] == 15
