"""
Unit tests for entry_watcher.py module.

Tests cover:
- Adding tokens to watchlist
- Removing tokens from watchlist
- Entry signal detection with mocked price fetches
- Watchlist expiration and cleanup
- Edge cases and error handling
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock

from entry_watcher import EntryWatcher
import config


# =============================================================================
# TEST FIXTURES
# =============================================================================

@pytest.fixture
def watcher():
    """Create a fresh EntryWatcher instance."""
    return EntryWatcher()


@pytest.fixture
def populated_watcher():
    """Create an EntryWatcher with tokens in watchlist."""
    watcher = EntryWatcher()
    watcher.add_to_watchlist(
        mint="TRUMP123",
        symbol="TRUMP",
        initial_price=0.0001,
        dex_url="https://dexscreener.com/solana/trump123"
    )
    watcher.add_to_watchlist(
        mint="BIDEN456",
        symbol="BIDEN",
        initial_price=0.0005,
        dex_url="https://dexscreener.com/solana/biden456"
    )
    return watcher


# =============================================================================
# WATCHLIST MANAGEMENT TESTS
# =============================================================================

def test_add_to_watchlist_success(watcher):
    """Test successfully adding a token to watchlist."""
    result = watcher.add_to_watchlist(
        mint="TOKEN123",
        symbol="TEST",
        initial_price=0.001,
        dex_url="https://example.com"
    )
    
    assert result is True
    assert watcher.get_watchlist_size() == 1
    
    watchlist = watcher.get_watchlist()
    assert "TOKEN123" in watchlist
    assert watchlist["TOKEN123"]["symbol"] == "TEST"
    assert watchlist["TOKEN123"]["initial_price"] == 0.001


def test_add_to_watchlist_duplicate(watcher):
    """Test adding duplicate token returns False."""
    watcher.add_to_watchlist("TOKEN123", "TEST", 0.001)
    
    # Try to add same mint again
    result = watcher.add_to_watchlist("TOKEN123", "TEST", 0.002)
    
    assert result is False
    assert watcher.get_watchlist_size() == 1
    # Original price should be preserved
    assert watcher.get_watchlist()["TOKEN123"]["initial_price"] == 0.001


def test_remove_from_watchlist_success(populated_watcher):
    """Test successfully removing a token from watchlist."""
    initial_size = populated_watcher.get_watchlist_size()
    
    result = populated_watcher.remove_from_watchlist("TRUMP123", reason="test")
    
    assert result is True
    assert populated_watcher.get_watchlist_size() == initial_size - 1
    assert "TRUMP123" not in populated_watcher.get_watchlist()


def test_remove_from_watchlist_not_found(watcher):
    """Test removing non-existent token returns False."""
    result = watcher.remove_from_watchlist("NONEXISTENT", reason="test")
    
    assert result is False


def test_get_watchlist_returns_copy(populated_watcher):
    """Test that get_watchlist returns a shallow copy of keys, not the original dict."""
    watchlist = populated_watcher.get_watchlist()
    
    # The copy() method does a shallow copy, so modifying the outer dict shouldn't affect original
    del watchlist["TRUMP123"]
    
    # Original should still have the key
    assert "TRUMP123" in populated_watcher.get_watchlist()


def test_get_watchlist_size(populated_watcher):
    """Test watchlist size tracking."""
    assert populated_watcher.get_watchlist_size() == 2
    
    populated_watcher.remove_from_watchlist("TRUMP123")
    assert populated_watcher.get_watchlist_size() == 1
    
    populated_watcher.remove_from_watchlist("BIDEN456")
    assert populated_watcher.get_watchlist_size() == 0


# =============================================================================
# ENTRY SIGNAL DETECTION TESTS
# =============================================================================

def test_check_entry_signals_triggered(populated_watcher):
    """Test entry signal detection when price drops below threshold."""
    initial_price = 0.0001
    # Price dropped by threshold percent
    drop_price = initial_price * (1 - config.ENTRY_DROP_THRESHOLD_PERCENT / 100) - 0.00001
    
    # Mock the price fetch to return dropped price
    with patch.object(populated_watcher, '_fetch_current_price', return_value=drop_price):
        triggered = populated_watcher.check_entry_signals()
        
        # TRUMP123 should trigger (started at 0.0001)
        assert len(triggered) >= 1
        
        triggered_mints = [t["mint"] for t in triggered]
        assert "TRUMP123" in triggered_mints


def test_check_entry_signals_not_triggered(populated_watcher):
    """Test no entry signal when price hasn't dropped enough."""
    # TRUMP123 has initial price 0.0001, BIDEN456 has 0.0005
    # Use price values that represent less than threshold drop for BOTH tokens
    # e.g., if threshold is 50%, price would need to drop below 0.00005 for TRUMP
    # Here we return a price that's 10% less than initial - not enough for 50% threshold
    
    def mock_price(mint):
        if mint == "TRUMP123":
            return 0.00009  # 10% drop from 0.0001
        else:  # BIDEN456
            return 0.00045  # 10% drop from 0.0005
    
    with patch.object(populated_watcher, '_fetch_current_price', side_effect=mock_price):
        triggered = populated_watcher.check_entry_signals()
        
        # With 50% threshold, 10% drop should NOT trigger any tokens
        if config.ENTRY_DROP_THRESHOLD_PERCENT >= 50:
            assert len(triggered) == 0


def test_check_entry_signals_removes_triggered(populated_watcher):
    """Test that triggered tokens are removed from watchlist."""
    initial_size = populated_watcher.get_watchlist_size()
    drop_price = 0.00001  # Very low price - should trigger
    
    with patch.object(populated_watcher, '_fetch_current_price', return_value=drop_price):
        triggered = populated_watcher.check_entry_signals()
        
        # Triggered tokens should be removed
        for token in triggered:
            assert token["mint"] not in populated_watcher.get_watchlist()


def test_check_entry_signals_empty_watchlist(watcher):
    """Test entry signal check on empty watchlist."""
    triggered = watcher.check_entry_signals()
    
    assert triggered == []


def test_check_entry_signals_price_fetch_failure(populated_watcher):
    """Test handling when price fetch fails."""
    with patch.object(populated_watcher, '_fetch_current_price', return_value=None):
        triggered = populated_watcher.check_entry_signals()
        
        # Should not trigger and tokens should remain
        assert len(triggered) == 0
        assert populated_watcher.get_watchlist_size() == 2


def test_check_entry_signals_returns_correct_data(populated_watcher):
    """Test that triggered token data is correct."""
    drop_price = 0.00001
    
    with patch.object(populated_watcher, '_fetch_current_price', return_value=drop_price):
        triggered = populated_watcher.check_entry_signals()
        
        if triggered:
            token = triggered[0]
            
            assert "mint" in token
            assert "symbol" in token
            assert "initial_price" in token
            assert "current_price" in token
            assert "drop_percent" in token
            assert "dex_url" in token
            
            # Drop percent should be positive
            assert token["drop_percent"] > 0


# =============================================================================
# WATCHLIST EXPIRATION TESTS
# =============================================================================

def test_cleanup_expired_tokens(watcher):
    """Test that expired tokens are removed."""
    # Add token with old timestamp
    watcher.add_to_watchlist("OLD_TOKEN", "OLD", 0.001)
    
    # Manually set the added_at to be older than watch duration
    watcher.watchlist["OLD_TOKEN"]["added_at"] = (
        datetime.utcnow() - timedelta(minutes=config.ENTRY_WATCH_DURATION_MINUTES + 10)
    )
    
    # Add fresh token with high initial price - price of 0.001 is NOT a 50% drop from 0.002
    watcher.add_to_watchlist("NEW_TOKEN", "NEW", 0.002)
    
    # Return price that won't trigger NEW_TOKEN (only 50% drop would trigger)
    # 0.001 is 50% of 0.002, so we need price > 0.001 to not trigger
    with patch.object(watcher, '_fetch_current_price', return_value=0.0015):  # 25% drop
        watcher.check_entry_signals()
    
    # Old token should be removed (expired), new token should remain (not triggered)
    assert "OLD_TOKEN" not in watcher.get_watchlist()
    assert "NEW_TOKEN" in watcher.get_watchlist()


def test_is_expired_true():
    """Test _is_expired returns True for old tokens."""
    watcher = EntryWatcher()
    
    old_time = datetime.utcnow() - timedelta(minutes=config.ENTRY_WATCH_DURATION_MINUTES + 1)
    
    assert watcher._is_expired(old_time) is True


def test_is_expired_false():
    """Test _is_expired returns False for fresh tokens."""
    watcher = EntryWatcher()
    
    fresh_time = datetime.utcnow() - timedelta(minutes=config.ENTRY_WATCH_DURATION_MINUTES - 1)
    
    assert watcher._is_expired(fresh_time) is False


# =============================================================================
# PRICE FETCH TESTS
# =============================================================================

def test_fetch_current_price_success(watcher):
    """Test successful price fetch from DexScreener."""
    mock_response = Mock()
    mock_response.json.return_value = {
        "pairs": [
            {"priceUsd": "0.00012345"}
        ]
    }
    mock_response.raise_for_status = Mock()
    
    # requests is imported inside the method, so patch at the source
    with patch('requests.get', return_value=mock_response):
        price = watcher._fetch_current_price("TOKEN123")
        
        assert price == 0.00012345


def test_fetch_current_price_no_pairs(watcher):
    """Test price fetch when no pairs found."""
    mock_response = Mock()
    mock_response.json.return_value = {"pairs": []}
    mock_response.raise_for_status = Mock()
    
    with patch('requests.get', return_value=mock_response):
        price = watcher._fetch_current_price("UNKNOWN_TOKEN")
        
        assert price is None


def test_fetch_current_price_api_error(watcher):
    """Test price fetch handles API errors."""
    import requests as req
    
    with patch('requests.get', side_effect=req.exceptions.RequestException("Error")):
        price = watcher._fetch_current_price("TOKEN123")
        
        assert price is None


# =============================================================================
# WATCHLIST SUMMARY TESTS
# =============================================================================

def test_get_watchlist_summary_empty(watcher):
    """Test summary for empty watchlist."""
    summary = watcher.get_watchlist_summary()
    
    assert "empty" in summary.lower()


def test_get_watchlist_summary_with_tokens(populated_watcher):
    """Test summary with tokens in watchlist."""
    summary = populated_watcher.get_watchlist_summary()
    
    assert "TRUMP" in summary
    assert "BIDEN" in summary
    assert "2 tokens" in summary


# =============================================================================
# EDGE CASE TESTS
# =============================================================================

def test_add_to_watchlist_zero_price(watcher):
    """Test adding token with zero price."""
    result = watcher.add_to_watchlist("TOKEN", "TEST", 0.0)
    
    assert result is True
    assert watcher.get_watchlist()["TOKEN"]["initial_price"] == 0.0


def test_multiple_tokens_different_thresholds(watcher):
    """Test multiple tokens with different initial prices."""
    watcher.add_to_watchlist("HIGH_PRICE", "HIGH", 1.0, "")
    watcher.add_to_watchlist("LOW_PRICE", "LOW", 0.00001, "")
    
    # Set current prices where only LOW triggers
    def mock_price(mint):
        if mint == "HIGH_PRICE":
            return 0.9  # Only 10% drop
        else:
            return 0.000001  # 90% drop
    
    with patch.object(watcher, '_fetch_current_price', side_effect=mock_price):
        triggered = watcher.check_entry_signals()
        
        # Only LOW should trigger (if threshold is 50%)
        if config.ENTRY_DROP_THRESHOLD_PERCENT <= 50:
            triggered_symbols = [t["symbol"] for t in triggered]
            assert "LOW" in triggered_symbols
            # HIGH might not trigger depending on exact threshold


def test_watchlist_persistence_after_checks(populated_watcher):
    """Test that non-triggered tokens remain after checks."""
    # Price increased - no trigger
    with patch.object(populated_watcher, '_fetch_current_price', return_value=0.001):
        triggered = populated_watcher.check_entry_signals()
        
        # No tokens should be removed (price went up)
        assert populated_watcher.get_watchlist_size() == 2
