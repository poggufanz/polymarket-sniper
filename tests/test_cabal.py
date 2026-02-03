"""
Unit tests for cabal (star topology) detection in shield.py.

Tests cover:
- Funding source extraction from transaction history
- Star topology detection (3+ holders funded by same source)
- Timeout handling for RPC calls
- Integration with comprehensive_security_check
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import asyncio

from shield import (
    _get_funding_source,
    check_cabal_topology,
    comprehensive_security_check,
    LEVEL_DANGER,
    LEVEL_WARNING,
    LEVEL_OK,
    LEVEL_UNKNOWN,
)


# =============================================================================
# FUNDING SOURCE EXTRACTION TESTS
# =============================================================================

def test_funding_source_extraction_sol_transfer():
    """Test extracting funding source from SOL transfer transaction."""
    # Mock Helius transaction response with SOL transfer
    mock_tx_response = {
        "signature": "abc123",
        "type": "SOL_TRANSFER",
        "feePayer": "FunderWallet123",
        "nativeTransfers": [
            {
                "fromUserAccount": "FunderWallet123",
                "toUserAccount": "HolderWallet1",
                "amount": 1000000000  # 1 SOL in lamports
            }
        ]
    }
    
    with patch('shield._fetch_transactions_helius') as mock_helius, \
         patch('shield.config.HELIUS_API_KEY', 'test-api-key'):
        mock_helius.return_value = [mock_tx_response]
        
        result = _get_funding_source("HolderWallet1", use_helius=True)
        
        assert result == "FunderWallet123"


def test_funding_source_extraction_fallback_rpc():
    """Test fallback to sequential RPC when Helius unavailable."""
    # Mock signature and transaction responses
    mock_signatures = [
        {"signature": "sig123", "blockTime": 1234567890}
    ]
    
    mock_tx = {
        "result": {
            "meta": {
                "preBalances": [1000000000, 0],
                "postBalances": [0, 1000000000],
            },
            "transaction": {
                "message": {
                    "accountKeys": ["FunderWallet456", "HolderWallet2"]
                }
            }
        }
    }
    
    with patch('shield._fetch_transactions_helius') as mock_helius, \
         patch('shield._fetch_signatures_rpc') as mock_sigs, \
         patch('shield._fetch_transaction_rpc') as mock_tx_fetch:
        mock_helius.return_value = None  # Helius unavailable
        mock_sigs.return_value = mock_signatures
        mock_tx_fetch.return_value = mock_tx
        
        result = _get_funding_source("HolderWallet2", use_helius=False)
        
        assert result == "FunderWallet456"


def test_funding_source_no_transactions():
    """Test handling wallet with no transactions."""
    with patch('shield._fetch_transactions_helius') as mock_helius:
        mock_helius.return_value = []
        
        result = _get_funding_source("EmptyWallet", use_helius=True)
        
        assert result is None


def test_funding_source_timeout():
    """Test timeout handling returns None gracefully."""
    with patch('shield._fetch_transactions_helius') as mock_helius:
        mock_helius.side_effect = TimeoutError("RPC timeout")
        
        result = _get_funding_source("TimeoutWallet", use_helius=True)
        
        assert result is None


# =============================================================================
# STAR TOPOLOGY DETECTION TESTS
# =============================================================================

def test_detect_star_topology_cabal():
    """Test detection when 3+ wallets have same funding source (CABAL)."""
    holder_addresses = [
        "Holder1",
        "Holder2", 
        "Holder3",
        "Holder4",
        "Holder5"
    ]
    
    # Mock: Holder1, Holder2, Holder3 funded by same "CabalMaster"
    with patch('shield._get_funding_source') as mock_funder:
        mock_funder.side_effect = [
            "CabalMaster",  # Holder1
            "CabalMaster",  # Holder2
            "CabalMaster",  # Holder3
            "IndependentFunder1",  # Holder4
            "IndependentFunder2",  # Holder5
        ]
        
        result = check_cabal_topology(holder_addresses, verbose=False)
        
        assert result["is_cabal"] is True
        assert result["level"] == LEVEL_DANGER
        assert "CabalMaster" in str(result["common_funders"])
        assert len(result["common_funders"]) >= 1


def test_no_cabal_different_funders():
    """Test no cabal detected when holders have different funders."""
    holder_addresses = [
        "Holder1",
        "Holder2",
        "Holder3",
        "Holder4",
        "Holder5"
    ]
    
    # Mock: All different funders
    with patch('shield._get_funding_source') as mock_funder:
        mock_funder.side_effect = [
            "Funder1",
            "Funder2",
            "Funder3",
            "Funder4",
            "Funder5",
        ]
        
        result = check_cabal_topology(holder_addresses, verbose=False)
        
        assert result["is_cabal"] is False
        assert result["level"] == LEVEL_OK
        assert len(result["common_funders"]) == 0


def test_cabal_edge_case_exactly_threshold():
    """Test exactly at threshold (3 from same funder = CABAL)."""
    holder_addresses = ["Holder1", "Holder2", "Holder3", "Holder4"]
    
    with patch('shield._get_funding_source') as mock_funder:
        # Exactly 3 from same funder
        mock_funder.side_effect = [
            "CommonFunder",
            "CommonFunder",
            "CommonFunder",
            "DifferentFunder",
        ]
        
        result = check_cabal_topology(holder_addresses, verbose=False)
        
        assert result["is_cabal"] is True
        assert result["level"] == LEVEL_DANGER


def test_cabal_below_threshold():
    """Test below threshold (2 from same funder != CABAL)."""
    holder_addresses = ["Holder1", "Holder2", "Holder3", "Holder4"]
    
    with patch('shield._get_funding_source') as mock_funder:
        # Only 2 from same funder
        mock_funder.side_effect = [
            "CommonFunder",
            "CommonFunder",
            "DifferentFunder1",
            "DifferentFunder2",
        ]
        
        result = check_cabal_topology(holder_addresses, verbose=False)
        
        assert result["is_cabal"] is False
        assert result["level"] == LEVEL_OK


def test_cabal_timeout_handling():
    """Test graceful handling when tracing times out."""
    holder_addresses = ["Holder1", "Holder2", "Holder3"]
    
    with patch('shield._get_funding_source') as mock_funder:
        # All timeouts/failures
        mock_funder.return_value = None
        
        result = check_cabal_topology(holder_addresses, verbose=False)
        
        # Should fail-open (not flag as cabal if we can't determine)
        assert result["is_cabal"] is False
        assert result["level"] == LEVEL_UNKNOWN
        assert "timeout" in result["reason"].lower() or "unknown" in result["reason"].lower()


def test_cabal_empty_holder_list():
    """Test handling empty holder list."""
    result = check_cabal_topology([], verbose=False)
    
    assert result["is_cabal"] is False
    assert result["level"] == LEVEL_UNKNOWN


def test_cabal_respects_holder_limit():
    """Test that only top N holders are traced (respects CABAL_TOP_HOLDERS_LIMIT)."""
    # Pass more holders than limit
    holder_addresses = [f"Holder{i}" for i in range(10)]
    
    with patch('shield._get_funding_source') as mock_funder:
        mock_funder.return_value = "SomeFunder"
        
        check_cabal_topology(holder_addresses, verbose=False)
        
        # Should only call for CABAL_TOP_HOLDERS_LIMIT (5) holders
        assert mock_funder.call_count <= 5


# =============================================================================
# INTEGRATION WITH COMPREHENSIVE SECURITY CHECK
# =============================================================================

def test_integration_comprehensive_check_cabal_detected(high_quality_token):
    """Test cabal detection integrated into comprehensive_security_check."""
    with patch('shield.check_security') as mock_security, \
         patch('shield._get_holders_from_rpc') as mock_holders_rpc, \
         patch('shield._get_token_data_from_dexscreener') as mock_dex, \
         patch('shield._get_funding_source') as mock_funder:
        
        # Mock basic checks to pass
        mock_security.return_value = (True, "Risk level: good")
        mock_holders_rpc.return_value = [
            {"address": "Holder1", "amount": "10000000"},
            {"address": "Holder2", "amount": "9000000"},
            {"address": "Holder3", "amount": "8000000"},
            {"address": "Holder4", "amount": "7000000"},
            {"address": "Holder5", "amount": "6000000"},
            {"address": "Rest", "amount": "60000000"},
        ]
        mock_dex.return_value = high_quality_token
        
        # Mock cabal detection - 3 holders from same funder
        mock_funder.side_effect = [
            "CabalMaster",  # Holder1
            "CabalMaster",  # Holder2
            "CabalMaster",  # Holder3
            "IndependentFunder1",  # Holder4
            "IndependentFunder2",  # Holder5
        ]
        
        result = comprehensive_security_check(
            "test_mint",
            token_data=high_quality_token,
            verbose=False
        )
        
        # Cabal should be in danger flags
        assert "cabal_topology" in result
        assert result["cabal_topology"]["is_cabal"] is True
        assert any("cabal" in flag.lower() for flag in result["danger_flags"])


def test_integration_comprehensive_check_no_cabal(high_quality_token):
    """Test comprehensive_security_check when no cabal detected."""
    with patch('shield.check_security') as mock_security, \
         patch('shield._get_holders_from_rpc') as mock_holders_rpc, \
         patch('shield._get_token_data_from_dexscreener') as mock_dex, \
         patch('shield._get_funding_source') as mock_funder:
        
        mock_security.return_value = (True, "Risk level: good")
        mock_holders_rpc.return_value = [
            {"address": "Holder1", "amount": "10000000"},
            {"address": "Holder2", "amount": "9000000"},
            {"address": "Holder3", "amount": "8000000"},
            {"address": "Holder4", "amount": "7000000"},
            {"address": "Holder5", "amount": "6000000"},
            {"address": "Rest", "amount": "60000000"},
        ]
        mock_dex.return_value = high_quality_token
        
        # All different funders
        mock_funder.side_effect = [
            "Funder1", "Funder2", "Funder3", "Funder4", "Funder5"
        ]
        
        result = comprehensive_security_check(
            "test_mint",
            token_data=high_quality_token,
            verbose=False
        )
        
        assert "cabal_topology" in result
        assert result["cabal_topology"]["is_cabal"] is False


def test_integration_cabal_check_disabled():
    """Test that cabal check can be disabled via config."""
    with patch('shield.config.ENABLE_CABAL_TRACING', False), \
         patch('shield.check_security') as mock_security, \
         patch('shield._get_holders_from_rpc') as mock_holders_rpc, \
         patch('shield._get_token_data_from_dexscreener') as mock_dex:
        
        mock_security.return_value = (True, "Risk level: good")
        mock_holders_rpc.return_value = [{"address": "H1", "amount": "100"}]
        mock_dex.return_value = {"txns": {"h1": {"buys": 10, "sells": 10}}}
        
        result = comprehensive_security_check("test_mint", verbose=False)
        
        # Cabal topology should be skipped or empty
        if "cabal_topology" in result:
            assert result["cabal_topology"].get("level") in [LEVEL_UNKNOWN, None]
