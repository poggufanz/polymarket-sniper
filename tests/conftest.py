"""
Pytest configuration and fixtures for PM-Predict tests.

This module provides shared test fixtures for mocking API responses
and creating high-quality/low-quality token test data.
"""

import pytest
from datetime import datetime, timezone
from typing import Dict, Any


# =============================================================================
# MOCK TOKEN DATA FIXTURES
# =============================================================================

@pytest.fixture
def high_quality_token() -> Dict[str, Any]:
    """
    High-quality token fixture for testing.
    
    Characteristics:
    - Good liquidity ($50,000)
    - EARLY pump phase (30% price change)
    - Strong buy pressure (2.5x ratio)
    - Normal holder distribution (30% top 10)
    - Active trading (buys and sells present)
    - Young token (2 hours old)
    """
    return {
        # Basic token info
        "baseToken": {
            "address": "GoodToken123456789",
            "name": "Trump Victory Token",
            "symbol": "TRUMP",
        },
        
        # Price and liquidity
        "priceUsd": "0.15",
        "liquidity": {
            "usd": 50000,
            "base": 333333,
            "quote": 50000,
        },
        
        # Price changes
        "priceChange": {
            "h1": 30.0,    # 30% pump in 1h (EARLY)
            "h6": 45.0,
            "h24": 60.0,
        },
        
        # Transaction data
        "txns": {
            "h1": {
                "buys": 250,
                "sells": 100,  # 2.5x buy pressure
            },
            "h6": {
                "buys": 800,
                "sells": 400,
            },
            "h24": {
                "buys": 1500,
                "sells": 800,
            },
        },
        
        # Token age
        "pairCreatedAt": int((datetime.now(timezone.utc).timestamp() - 7200) * 1000),  # 2 hours ago
        
        # Metadata
        "url": "https://dexscreener.com/solana/GoodToken123456789",
        "chainId": "solana",
        "dexId": "raydium",
        
        # Additional info
        "info": {
            "description": "Official Trump Victory Token commemorating election win",
            "socials": [
                {"type": "twitter", "url": "https://twitter.com/trumptoken"}
            ],
        }
    }


@pytest.fixture
def low_quality_token() -> Dict[str, Any]:
    """
    Low-quality token fixture for testing.
    
    Characteristics:
    - LATE pump phase (65% price change)
    - Low liquidity ($3,000)
    - More sells than buys (0.6x ratio)
    - Potential honeypot (no sells in 1h)
    - Very new token (30 min old)
    - High holder concentration (60% top 10)
    """
    return {
        # Basic token info
        "baseToken": {
            "address": "ScamToken987654321",
            "name": "Trump Fake Coin",
            "symbol": "FAKE",
        },
        
        # Price and liquidity
        "priceUsd": "0.0001",
        "liquidity": {
            "usd": 3000,
            "base": 30000000,
            "quote": 3000,
        },
        
        # Price changes
        "priceChange": {
            "h1": 65.0,    # 65% pump in 1h (LATE)
            "h6": 80.0,
            "h24": 120.0,
        },
        
        # Transaction data (HONEYPOT: buys but no sells)
        "txns": {
            "h1": {
                "buys": 15,
                "sells": 0,  # HONEYPOT!
            },
            "h6": {
                "buys": 30,
                "sells": 5,
            },
            "h24": {
                "buys": 50,
                "sells": 10,
            },
        },
        
        # Token age (30 minutes)
        "pairCreatedAt": int((datetime.now(timezone.utc).timestamp() - 1800) * 1000),
        
        # Metadata
        "url": "https://dexscreener.com/solana/ScamToken987654321",
        "chainId": "solana",
        "dexId": "raydium",
        
        # Additional info
        "info": {
            "description": "Get rich quick with Trump Fake Coin!",
            "socials": [],
        }
    }


@pytest.fixture
def stale_token() -> Dict[str, Any]:
    """
    Stale token fixture for testing.
    
    Characteristics:
    - Old token (48 hours)
    - Flat price movement (0.05% change)
    - Low trading volume
    - Balanced buy/sell ratio
    """
    return {
        # Basic token info
        "baseToken": {
            "address": "StaleToken111111111",
            "name": "Old Stable Coin",
            "symbol": "STALE",
        },
        
        # Price and liquidity
        "priceUsd": "1.00",
        "liquidity": {
            "usd": 100000,
            "base": 100000,
            "quote": 100000,
        },
        
        # Price changes (flat)
        "priceChange": {
            "h1": 0.05,    # Minimal movement
            "h6": 0.1,
            "h24": 0.2,
        },
        
        # Transaction data (low volume)
        "txns": {
            "h1": {
                "buys": 10,
                "sells": 10,  # Balanced
            },
            "h6": {
                "buys": 30,
                "sells": 30,
            },
            "h24": {
                "buys": 100,
                "sells": 100,
            },
        },
        
        # Token age (48 hours)
        "pairCreatedAt": int((datetime.now(timezone.utc).timestamp() - 172800) * 1000),
        
        # Metadata
        "url": "https://dexscreener.com/solana/StaleToken111111111",
        "chainId": "solana",
        "dexId": "raydium",
        
        # Additional info
        "info": {
            "description": "Established stablecoin project",
            "socials": [
                {"type": "twitter", "url": "https://twitter.com/staletoken"}
            ],
        }
    }


# =============================================================================
# MOCK API RESPONSE FIXTURES
# =============================================================================

@pytest.fixture
def mock_rugcheck_safe() -> Dict[str, Any]:
    """Mock RugCheck API response for safe token."""
    return {
        "riskLevel": "good",
        "score": 15,
        "risks": []
    }


@pytest.fixture
def mock_rugcheck_danger() -> Dict[str, Any]:
    """Mock RugCheck API response for dangerous token."""
    return {
        "riskLevel": "danger",
        "score": 95,
        "risks": [
            {"level": "danger", "name": "High holder concentration"},
            {"level": "danger", "name": "Mutable metadata"},
        ]
    }


@pytest.fixture
def mock_llm_high_relevance() -> Dict[str, Any]:
    """Mock LLM response for high relevance token."""
    return {
        "relevance_score": 85,
        "authenticity_score": 75,
        "red_flags": [],
        "confidence": 90,
        "reasoning": "Token name closely matches event title, appears authentic"
    }


@pytest.fixture
def mock_llm_low_relevance() -> Dict[str, Any]:
    """Mock LLM response for low relevance token."""
    return {
        "relevance_score": 25,
        "authenticity_score": 30,
        "red_flags": ["Generic name", "Suspicious marketing"],
        "confidence": 80,
        "reasoning": "Token appears to be unrelated scam attempt"
    }


# =============================================================================
# HELPER FIXTURES
# =============================================================================

@pytest.fixture
def mock_solana_rpc_holders() -> Dict[str, Any]:
    """Mock Solana RPC getTokenLargestAccounts response."""
    return {
        "jsonrpc": "2.0",
        "result": {
            "value": [
                {"address": "holder1", "amount": "30000000"},  # 30%
                {"address": "holder2", "amount": "10000000"},  # 10%
                {"address": "holder3", "amount": "10000000"},  # 10%
                {"address": "holder4", "amount": "5000000"},   # 5%
                {"address": "holder5", "amount": "5000000"},   # 5%
                {"address": "holder6", "amount": "5000000"},   # 5%
                {"address": "holder7", "amount": "5000000"},   # 5%
                {"address": "holder8", "amount": "5000000"},   # 5%
                {"address": "holder9", "amount": "5000000"},   # 5%
                {"address": "holder10", "amount": "5000000"},  # 5%
                # Total top 10: 85%
            ]
        },
        "id": 1
    }


@pytest.fixture
def token_age_hours():
    """Helper function to calculate token age from pairCreatedAt."""
    def _token_age(token_data: Dict[str, Any]) -> float:
        created_at = token_data.get("pairCreatedAt")
        if not created_at:
            return 0.0
        now = datetime.now(timezone.utc).timestamp()
        created = created_at / 1000
        return (now - created) / 3600
    return _token_age
