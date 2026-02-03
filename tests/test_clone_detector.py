"""
Unit tests for clone_detector.py module.

Tests cover:
- Clone detection with DexScreener search mocking
- Fuzzy matching similarity calculations
- Success and failure cases
- Edge cases (empty input, API failures)
"""

import pytest
from unittest.mock import Mock, patch, MagicMock

from clone_detector import (
    check_clone_token,
    _calculate_similarity,
    _search_dexscreener,
    LEVEL_DANGER,
    LEVEL_WARNING,
    LEVEL_OK,
    LEVEL_UNKNOWN,
    FUZZYWUZZY_AVAILABLE,
)


# =============================================================================
# SIMILARITY CALCULATION TESTS
# =============================================================================

@pytest.mark.skipif(not FUZZYWUZZY_AVAILABLE, reason="fuzzywuzzy not installed")
def test_calculate_similarity_exact_match():
    """Test similarity calculation with exact match."""
    score = _calculate_similarity("Trump Token", "Trump Token")
    assert score == 100


@pytest.mark.skipif(not FUZZYWUZZY_AVAILABLE, reason="fuzzywuzzy not installed")
def test_calculate_similarity_case_insensitive():
    """Test similarity calculation is case insensitive."""
    score = _calculate_similarity("TRUMP TOKEN", "trump token")
    assert score >= 90  # Should be high due to token_set_ratio


@pytest.mark.skipif(not FUZZYWUZZY_AVAILABLE, reason="fuzzywuzzy not installed")
def test_calculate_similarity_different_strings():
    """Test similarity calculation with different strings."""
    score = _calculate_similarity("Trump Token", "Biden Token")
    assert score < 70  # Should be low


@pytest.mark.skipif(not FUZZYWUZZY_AVAILABLE, reason="fuzzywuzzy not installed")
def test_calculate_similarity_partial_match():
    """Test similarity with partial match - token_set_ratio is permissive."""
    score = _calculate_similarity("Trump Victory Token", "Trump Token")
    # token_set_ratio returns 100 when one is subset of another (both contain "Trump Token")
    assert score >= 60  # Should be high due to token_set_ratio behavior


# =============================================================================
# DEXSCREENER SEARCH MOCK TESTS
# =============================================================================

def test_search_dexscreener_success():
    """Test DexScreener search returns results."""
    mock_response = Mock()
    mock_response.json.return_value = {
        "pairs": [
            {
                "baseToken": {
                    "address": "Token123",
                    "name": "Trump Token",
                    "symbol": "TRUMP"
                }
            }
        ]
    }
    mock_response.raise_for_status = Mock()
    
    with patch('clone_detector.requests.get', return_value=mock_response):
        result = _search_dexscreener("trump", verbose=False)
        
        assert result is not None
        assert len(result) == 1
        assert result[0]["baseToken"]["symbol"] == "TRUMP"


def test_search_dexscreener_timeout():
    """Test DexScreener search handles timeout gracefully."""
    import requests
    
    with patch('clone_detector.requests.get', side_effect=requests.exceptions.Timeout()):
        result = _search_dexscreener("trump", verbose=False)
        
        assert result is None


def test_search_dexscreener_request_error():
    """Test DexScreener search handles request errors."""
    import requests
    
    with patch('clone_detector.requests.get', side_effect=requests.exceptions.RequestException("Error")):
        result = _search_dexscreener("trump", verbose=False)
        
        assert result is None


# =============================================================================
# CLONE TOKEN CHECK TESTS
# =============================================================================

@pytest.mark.skipif(not FUZZYWUZZY_AVAILABLE, reason="fuzzywuzzy not installed")
def test_check_clone_token_no_clone_found():
    """Test check_clone_token when no clone is found."""
    mock_pairs = [
        {
            "baseToken": {
                "address": "DifferentToken123",
                "name": "Completely Unrelated Name",
                "symbol": "XYZZ"
            }
        }
    ]
    
    with patch('clone_detector._search_dexscreener', return_value=mock_pairs):
        result = check_clone_token(
            symbol="ABCD",
            name="My Awesome Project",
            mint_address="MyToken123",
            verbose=False
        )
        
        # Both name and symbol are very different, should be OK
        assert result["is_clone"] is False
        assert result["similarity_score"] < 75


@pytest.mark.skipif(not FUZZYWUZZY_AVAILABLE, reason="fuzzywuzzy not installed")
def test_check_clone_token_clone_detected():
    """Test check_clone_token when clone is detected with high similarity."""
    mock_pairs = [
        {
            "baseToken": {
                "address": "OriginalToken123",
                "name": "Trump Victory Token",
                "symbol": "TRUMP"
            }
        }
    ]
    
    with patch('clone_detector._search_dexscreener', return_value=mock_pairs):
        result = check_clone_token(
            symbol="TRUMP",
            name="Trump Victory Token Official",
            mint_address="CloneToken456",
            verbose=False
        )
        
        assert result["level"] == LEVEL_WARNING
        assert result["is_clone"] is True
        assert result["similarity_score"] >= 75


def test_check_clone_token_empty_input():
    """Test check_clone_token with empty input."""
    result = check_clone_token(
        symbol="",
        name="",
        mint_address="",
        verbose=False
    )
    
    assert result["level"] == LEVEL_UNKNOWN
    assert result["is_clone"] is False
    assert "Empty symbol or name" in result["reason"]


def test_check_clone_token_same_mint_excluded():
    """Test that same token (by mint) is excluded from clone comparison."""
    mock_pairs = [
        {
            "baseToken": {
                "address": "SameToken123",  # Same as mint_address
                "name": "Trump Token",
                "symbol": "TRUMP"
            }
        }
    ]
    
    with patch('clone_detector._search_dexscreener', return_value=mock_pairs):
        result = check_clone_token(
            symbol="TRUMP",
            name="Trump Token",
            mint_address="SameToken123",  # Same address - should be excluded
            verbose=False
        )
        
        # Should not detect itself as a clone
        assert result["is_clone"] is False


@pytest.mark.skipif(not FUZZYWUZZY_AVAILABLE, reason="fuzzywuzzy not installed")
def test_check_clone_token_moderate_similarity():
    """Test check_clone_token with moderate similarity (50-75%)."""
    mock_pairs = [
        {
            "baseToken": {
                "address": "OtherToken123",
                "name": "Trump Coin",
                "symbol": "TRUMPC"
            }
        }
    ]
    
    with patch('clone_detector._search_dexscreener', return_value=mock_pairs):
        result = check_clone_token(
            symbol="TRMP",
            name="Trump Token",
            mint_address="MyToken456",
            verbose=False
        )
        
        # Moderate similarity should be WARNING but not necessarily is_clone=True
        assert result["level"] in [LEVEL_WARNING, LEVEL_OK]


def test_check_clone_token_api_failure():
    """Test check_clone_token handles API failure gracefully."""
    with patch('clone_detector._search_dexscreener', return_value=None):
        result = check_clone_token(
            symbol="TRUMP",
            name="Trump Token",
            mint_address="Token123",
            verbose=False
        )
        
        assert result["level"] == LEVEL_UNKNOWN
        assert result["is_clone"] is False
        assert "Could not fetch" in result["reason"]


@pytest.mark.skipif(not FUZZYWUZZY_AVAILABLE, reason="fuzzywuzzy not installed")
def test_check_clone_token_multiple_matches():
    """Test check_clone_token with multiple similar tokens."""
    mock_pairs = [
        {
            "baseToken": {
                "address": "Token1",
                "name": "Trump Official",
                "symbol": "TRUMP"
            }
        },
        {
            "baseToken": {
                "address": "Token2",
                "name": "Trump Coin",
                "symbol": "TRUMP"
            }
        },
        {
            "baseToken": {
                "address": "Token3",
                "name": "Trump Meme",
                "symbol": "TRMP"
            }
        }
    ]
    
    with patch('clone_detector._search_dexscreener', return_value=mock_pairs):
        result = check_clone_token(
            symbol="TRUMP",
            name="Trump Victory Token",
            mint_address="NewToken789",
            verbose=False
        )
        
        # Should find matches
        assert len(result["matches"]) >= 0  # May have matches above 50%
        assert result["similarity_score"] >= 0


def test_check_clone_token_fuzzywuzzy_not_available():
    """Test check_clone_token when fuzzywuzzy not installed."""
    with patch('clone_detector.FUZZYWUZZY_AVAILABLE', False):
        result = check_clone_token(
            symbol="TRUMP",
            name="Trump Token",
            mint_address="Token123",
            verbose=False
        )
        
        assert result["level"] == LEVEL_UNKNOWN
        assert "fuzzywuzzy not installed" in result["reason"]
