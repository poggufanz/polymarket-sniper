"""
Unit tests for social_checker.py module.

Tests cover:
- Social presence detection (Twitter, Telegram, Discord, Website)
- Risk level assessment based on social count
- Edge cases (empty data, malformed input)
"""

import pytest
from unittest.mock import Mock, patch

from social_checker import (
    check_social_presence,
    LEVEL_OK,
    LEVEL_WARNING,
    LEVEL_UNKNOWN,
)


# =============================================================================
# SOCIAL PRESENCE DETECTION TESTS
# =============================================================================

def test_check_social_presence_no_socials():
    """Test social check when token has no social presence."""
    token_data = {
        "info": {
            "socials": []
        }
    }
    
    result = check_social_presence(token_data, verbose=False)
    
    assert result["level"] == LEVEL_WARNING
    assert result["social_count"] == 0
    assert result["has_twitter"] is False
    assert result["has_telegram"] is False
    assert result["has_discord"] is False
    assert result["has_website"] is False
    assert "No social media presence" in result["reason"]


def test_check_social_presence_twitter_only():
    """Test social check with Twitter only."""
    token_data = {
        "info": {
            "socials": [
                {"type": "twitter", "url": "https://twitter.com/example"}
            ]
        }
    }
    
    result = check_social_presence(token_data, verbose=False)
    
    assert result["level"] == LEVEL_OK
    assert result["social_count"] == 1
    assert result["has_twitter"] is True
    assert result["has_telegram"] is False
    assert result["has_discord"] is False
    assert result["has_website"] is False


def test_check_social_presence_telegram_only():
    """Test social check with Telegram only."""
    token_data = {
        "info": {
            "socials": [
                {"type": "telegram", "url": "https://t.me/example"}
            ]
        }
    }
    
    result = check_social_presence(token_data, verbose=False)
    
    assert result["level"] == LEVEL_OK
    assert result["social_count"] == 1
    assert result["has_telegram"] is True


def test_check_social_presence_discord_only():
    """Test social check with Discord only."""
    token_data = {
        "info": {
            "socials": [
                {"type": "discord", "url": "https://discord.gg/example"}
            ]
        }
    }
    
    result = check_social_presence(token_data, verbose=False)
    
    assert result["level"] == LEVEL_OK
    assert result["social_count"] == 1
    assert result["has_discord"] is True


def test_check_social_presence_website_only():
    """Test social check with Website only."""
    token_data = {
        "info": {
            "socials": [
                {"type": "website", "url": "https://example.com"}
            ]
        }
    }
    
    result = check_social_presence(token_data, verbose=False)
    
    assert result["level"] == LEVEL_OK
    assert result["social_count"] == 1
    assert result["has_website"] is True


def test_check_social_presence_multiple_socials():
    """Test social check with multiple social links."""
    token_data = {
        "info": {
            "socials": [
                {"type": "twitter", "url": "https://twitter.com/example"},
                {"type": "telegram", "url": "https://t.me/example"},
                {"type": "discord", "url": "https://discord.gg/example"},
                {"type": "website", "url": "https://example.com"}
            ]
        }
    }
    
    result = check_social_presence(token_data, verbose=False)
    
    assert result["level"] == LEVEL_OK
    assert result["social_count"] == 4
    assert result["has_twitter"] is True
    assert result["has_telegram"] is True
    assert result["has_discord"] is True
    assert result["has_website"] is True
    assert "Twitter" in result["reason"]
    assert "Telegram" in result["reason"]


def test_check_social_presence_x_type():
    """Test social check recognizes 'x' as Twitter."""
    token_data = {
        "info": {
            "socials": [
                {"type": "x", "url": "https://x.com/example"}
            ]
        }
    }
    
    result = check_social_presence(token_data, verbose=False)
    
    assert result["level"] == LEVEL_OK
    assert result["has_twitter"] is True


# =============================================================================
# EDGE CASE TESTS
# =============================================================================

def test_check_social_presence_missing_info_field():
    """Test social check when info field is missing."""
    token_data = {}
    
    result = check_social_presence(token_data, verbose=False)
    
    # Should default to empty socials list
    assert result["level"] == LEVEL_WARNING
    assert result["social_count"] == 0


def test_check_social_presence_missing_socials_field():
    """Test social check when socials field is missing."""
    token_data = {
        "info": {}
    }
    
    result = check_social_presence(token_data, verbose=False)
    
    # Should default to empty socials list
    assert result["level"] == LEVEL_WARNING
    assert result["social_count"] == 0


def test_check_social_presence_empty_urls():
    """Test social check ignores entries with empty URLs."""
    token_data = {
        "info": {
            "socials": [
                {"type": "twitter", "url": ""},
                {"type": "telegram", "url": None}
            ]
        }
    }
    
    result = check_social_presence(token_data, verbose=False)
    
    assert result["level"] == LEVEL_WARNING
    assert result["social_count"] == 0
    assert result["has_twitter"] is False
    assert result["has_telegram"] is False


def test_check_social_presence_invalid_socials_format():
    """Test social check when socials is not a list."""
    token_data = {
        "info": {
            "socials": "not a list"
        }
    }
    
    result = check_social_presence(token_data, verbose=False)
    
    assert result["level"] == LEVEL_UNKNOWN
    assert "unavailable" in result["reason"]


def test_check_social_presence_malformed_social_entry():
    """Test social check handles malformed social entries."""
    token_data = {
        "info": {
            "socials": [
                {"type": "twitter", "url": "https://twitter.com/valid"},
                "not a dict",  # Malformed entry
                123,  # Another malformed entry
            ]
        }
    }
    
    result = check_social_presence(token_data, verbose=False)
    
    # Should still detect the valid Twitter entry
    assert result["level"] == LEVEL_OK
    assert result["social_count"] == 1
    assert result["has_twitter"] is True


def test_check_social_presence_unknown_social_type():
    """Test social check ignores unknown social types."""
    token_data = {
        "info": {
            "socials": [
                {"type": "twitter", "url": "https://twitter.com/example"},
                {"type": "instagram", "url": "https://instagram.com/example"},  # Unknown type
                {"type": "facebook", "url": "https://facebook.com/example"},  # Unknown type
            ]
        }
    }
    
    result = check_social_presence(token_data, verbose=False)
    
    # Only Twitter should be counted
    assert result["level"] == LEVEL_OK
    assert result["social_count"] == 1
    assert result["has_twitter"] is True


def test_check_social_presence_case_insensitive_types():
    """Test social check handles uppercase type names."""
    token_data = {
        "info": {
            "socials": [
                {"type": "TWITTER", "url": "https://twitter.com/example"},
                {"type": "Telegram", "url": "https://t.me/example"},
            ]
        }
    }
    
    result = check_social_presence(token_data, verbose=False)
    
    assert result["level"] == LEVEL_OK
    assert result["social_count"] == 2
    assert result["has_twitter"] is True
    assert result["has_telegram"] is True


# =============================================================================
# HIGH QUALITY TOKEN FIXTURE TESTS
# =============================================================================

def test_check_social_presence_high_quality_token(high_quality_token):
    """Test social check with high quality token fixture."""
    result = check_social_presence(high_quality_token, verbose=False)
    
    # High quality token has Twitter
    assert result["level"] == LEVEL_OK
    assert result["has_twitter"] is True


def test_check_social_presence_low_quality_token(low_quality_token):
    """Test social check with low quality token fixture."""
    result = check_social_presence(low_quality_token, verbose=False)
    
    # Low quality token has no socials
    assert result["level"] == LEVEL_WARNING
    assert result["social_count"] == 0
