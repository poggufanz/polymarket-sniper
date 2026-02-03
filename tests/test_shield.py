"""
Unit tests for shield.py security checking module.

Tests cover:
- Holder concentration analysis
- Honeypot detection
- Bundled transaction detection
- Comprehensive security check
"""

import pytest
from unittest.mock import Mock, patch
from shield import (
    check_holder_concentration,
    check_honeypot,
    check_bundled_transactions,
    comprehensive_security_check,
    LEVEL_DANGER,
    LEVEL_WARNING,
    LEVEL_OK,
    LEVEL_UNKNOWN,
)


# =============================================================================
# HOLDER CONCENTRATION TESTS
# =============================================================================

def test_holder_concentration_safe(high_quality_token):
    """Test holder concentration check with safe distribution."""
    # Mock RPC to return safe distribution
    # Total amounts must add up such that top 10 is <50%
    with patch('shield._get_holders_from_rpc') as mock_rpc:
        mock_rpc.return_value = [
            {"amount": "20000000"},  # 20%
            {"amount": "10000000"},  # 10%
            {"amount": "10000000"},  # 10%
            {"amount": "5000000"},   # 5%
            {"amount": "5000000"},   # 5%
            {"amount": "5000000"},   # 5%
            {"amount": "5000000"},   # 5%
            {"amount": "5000000"},   # 5%
            {"amount": "5000000"},   # 5%
            {"amount": "5000000"},   # 5%
            {"amount": "30000000"},  # Remaining 30% distributed
            # Top 10: 75M / 125M = 60%, need to adjust
        ]
        
        # Actually, let's make top 10 be 40%
        mock_rpc.return_value = [
            {"amount": "10000000"},  # 10%
            {"amount": "8000000"},   # 8%
            {"amount": "5000000"},   # 5%
            {"amount": "4000000"},   # 4%
            {"amount": "3000000"},   # 3%
            {"amount": "3000000"},   # 3%
            {"amount": "2000000"},   # 2%
            {"amount": "2000000"},   # 2%
            {"amount": "2000000"},   # 2%
            {"amount": "1000000"},   # 1%
            # Top 10 = 40M
            {"amount": "60000000"},  # Rest = 60M
            # Total = 100M, Top 10 = 40%
        ]
        
        result = check_holder_concentration("test_mint", verbose=False)
        
        assert result["level"] == LEVEL_OK
        assert result["top10_percent"] < 50  # Below danger threshold


def test_holder_concentration_danger(low_quality_token):
    """Test holder concentration check with dangerous distribution."""
    # Mock RPC to return concentrated distribution (85% top 10)
    with patch('shield._get_holders_from_rpc') as mock_rpc:
        mock_rpc.return_value = [
            {"amount": "60000000"},  # 60%
            {"amount": "10000000"},  # 10%
            {"amount": "5000000"},   # 5%
            {"amount": "3000000"},   # 3%
            {"amount": "2000000"},   # 2%
            {"amount": "2000000"},   # 2%
            {"amount": "1000000"},   # 1%
            {"amount": "1000000"},   # 1%
            {"amount": "1000000"},   # 1%
            {"amount": "1000000"},   # 1%
            {"amount": "14000000"},  # Remaining 14%
        ]
        
        result = check_holder_concentration("test_mint", verbose=False)
        
        assert result["level"] == LEVEL_DANGER
        assert result["top10_percent"] > 50  # Above danger threshold


def test_holder_concentration_unknown():
    """Test holder concentration when data unavailable."""
    with patch('shield._get_holders_from_rpc') as mock_rpc, \
         patch('shield._get_holders_from_rugcheck') as mock_rugcheck:
        mock_rpc.return_value = None
        mock_rugcheck.return_value = None
        
        result = check_holder_concentration("test_mint", verbose=False)
        
        assert result["level"] == LEVEL_UNKNOWN
        assert result["top10_percent"] is None


# =============================================================================
# HONEYPOT DETECTION TESTS
# =============================================================================

def test_honeypot_detection_safe(high_quality_token):
    """Test honeypot detection with normal trading."""
    result = check_honeypot(token_data=high_quality_token, verbose=False)
    
    assert result["level"] == LEVEL_OK
    assert result["h1_buys"] > 0
    assert result["h1_sells"] > 0


def test_honeypot_detection_danger(low_quality_token):
    """Test honeypot detection with buys but no sells."""
    result = check_honeypot(token_data=low_quality_token, verbose=False)
    
    assert result["level"] == LEVEL_DANGER
    assert result["h1_buys"] > 0
    assert result["h1_sells"] == 0
    assert "HONEYPOT" in result["reason"]


def test_honeypot_detection_no_activity():
    """Test honeypot detection with no trading activity."""
    token_data = {
        "txns": {
            "h1": {
                "buys": 0,
                "sells": 0
            }
        }
    }
    
    result = check_honeypot(token_data=token_data, verbose=False)
    
    assert result["level"] == LEVEL_WARNING
    assert result["h1_buys"] == 0
    assert result["h1_sells"] == 0


def test_honeypot_detection_only_sells():
    """Test honeypot detection with only sells (dump)."""
    token_data = {
        "txns": {
            "h1": {
                "buys": 0,
                "sells": 100
            }
        }
    }
    
    result = check_honeypot(token_data=token_data, verbose=False)
    
    assert result["level"] == LEVEL_WARNING
    assert "dump" in result["reason"].lower()


# =============================================================================
# BUNDLED TRANSACTION TESTS
# =============================================================================

def test_bundled_tx_safe(high_quality_token, token_age_hours):
    """Test bundled transaction check with safe token."""
    age = token_age_hours(high_quality_token)
    
    result = check_bundled_transactions(token_data=high_quality_token, verbose=False)
    
    # Token is 2 hours old with 250 buyers in h1
    assert result["level"] == LEVEL_OK
    assert result["token_age_hours"] > 1.0


def test_bundled_tx_danger(low_quality_token):
    """Test bundled transaction check with very new token + few buyers."""
    result = check_bundled_transactions(token_data=low_quality_token, verbose=False)
    
    # Token is 30 min old with only 15 buyers
    assert result["level"] == LEVEL_DANGER
    assert result["token_age_hours"] < 1.0
    assert result["holder_count"] < 20


def test_bundled_tx_warning_very_new():
    """Test bundled transaction check with very new but active token."""
    token_data = {
        "pairCreatedAt": int((pytest.importorskip('datetime').datetime.now(
            pytest.importorskip('datetime').timezone.utc
        ).timestamp() - 1800) * 1000),  # 30 min
        "txns": {
            "h1": {
                "buys": 50,  # Above threshold but token very new
                "sells": 30
            }
        }
    }
    
    result = check_bundled_transactions(token_data=token_data, verbose=False)
    
    assert result["level"] == LEVEL_WARNING
    assert result["token_age_hours"] < 1.0


# =============================================================================
# COMPREHENSIVE SECURITY CHECK TESTS
# =============================================================================

def test_comprehensive_check_safe_token(high_quality_token, mock_rugcheck_safe):
    """Test comprehensive security check with safe token."""
    with patch('shield.check_security') as mock_security, \
         patch('shield._get_holders_from_rpc') as mock_holders, \
         patch('shield._get_token_data_from_dexscreener') as mock_dex:
        
        # Mock all checks to pass
        mock_security.return_value = (True, "Risk level: good")
        # Top 10 = 40%, rest = 60% (safe distribution)
        mock_holders.return_value = [
            {"amount": "10000000"},  # 10%
            {"amount": "8000000"},   # 8%
            {"amount": "5000000"},   # 5%
            {"amount": "4000000"},   # 4%
            {"amount": "3000000"},   # 3%
            {"amount": "3000000"},   # 3%
            {"amount": "2000000"},   # 2%
            {"amount": "2000000"},   # 2%
            {"amount": "2000000"},   # 2%
            {"amount": "1000000"},   # 1% -> Total 40%
            {"amount": "60000000"},  # Rest
        ]
        mock_dex.return_value = high_quality_token
        
        result = comprehensive_security_check(
            "test_mint",
            token_data=high_quality_token,
            verbose=False
        )
        
        assert result["is_safe"] is True
        assert result["overall_level"] in [LEVEL_OK, LEVEL_WARNING]
        assert result["safety_score"] >= 50
        assert len(result["danger_flags"]) == 0


def test_comprehensive_check_dangerous_token(low_quality_token, mock_rugcheck_danger):
    """Test comprehensive security check with dangerous token."""
    with patch('shield.check_security') as mock_security, \
         patch('shield._get_holders_from_rpc') as mock_holders, \
         patch('shield._get_token_data_from_dexscreener') as mock_dex:
        
        # Mock checks to fail
        mock_security.return_value = (False, "Risk level: danger")
        mock_holders.return_value = [
            {"amount": "85000000"},  # 85% concentration (DANGER)
            {"amount": "15000000"},
        ]
        mock_dex.return_value = low_quality_token
        
        result = comprehensive_security_check(
            "test_mint",
            token_data=low_quality_token,
            verbose=False
        )
        
        assert result["is_safe"] is False
        assert result["overall_level"] == LEVEL_DANGER
        assert result["safety_score"] < 50
        assert len(result["danger_flags"]) > 0


def test_comprehensive_check_mixed_signals(high_quality_token):
    """Test comprehensive security check with mixed signals (warnings but not dangers)."""
    with patch('shield.check_security') as mock_security, \
         patch('shield._get_holders_from_rpc') as mock_holders, \
         patch('shield._get_token_data_from_dexscreener') as mock_dex:
        
        # Pass basic check but return warning
        mock_security.return_value = (True, "Risk level: ok")
        # Top 10 = 45%, slightly concentrated but not >50%
        mock_holders.return_value = [
            {"amount": "15000000"},  # 15%
            {"amount": "10000000"},  # 10%
            {"amount": "5000000"},   # 5%
            {"amount": "3000000"},   # 3%
            {"amount": "3000000"},   # 3%
            {"amount": "2000000"},   # 2%
            {"amount": "2000000"},   # 2%
            {"amount": "2000000"},   # 2%
            {"amount": "2000000"},   # 2%
            {"amount": "1000000"},   # 1% -> Total 45%
            {"amount": "55000000"},  # Rest
        ]
        mock_dex.return_value = high_quality_token
        
        result = comprehensive_security_check(
            "test_mint",
            token_data=high_quality_token,
            verbose=False
        )
        
        assert result["is_safe"] is True  # Still safe with warnings
        assert result["overall_level"] in [LEVEL_WARNING, LEVEL_OK]
        assert result["safety_score"] >= 50


def test_comprehensive_check_api_failures():
    """Test comprehensive security check handles API failures gracefully."""
    with patch('shield.check_security') as mock_security, \
         patch('shield._get_holders_from_rpc') as mock_holders, \
         patch('shield._get_holders_from_rugcheck') as mock_rugcheck, \
         patch('shield._get_token_data_from_dexscreener') as mock_dex:
        
        # Mock API failures
        mock_security.return_value = (True, "API error")
        mock_holders.return_value = None
        mock_rugcheck.return_value = None
        mock_dex.return_value = None
        
        result = comprehensive_security_check(
            "test_mint",
            verbose=False
        )
        
        # Should not crash, returns UNKNOWN for failed checks
        assert result is not None
        assert "holder_concentration" in result
        assert "honeypot" in result
        assert "bundled_tx" in result
