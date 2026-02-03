"""
Unit tests for momentum.py price analysis module.

Tests cover:
- Price velocity calculation
- Pump phase classification (EARLY/LATE)
- Buy/sell ratio analysis
- Staleness detection
"""

import pytest
from momentum import (
    calculate_price_velocity,
    classify_pump_phase,
    get_buy_sell_ratio,
    check_staleness,
)


# =============================================================================
# PRICE VELOCITY TESTS
# =============================================================================

def test_price_velocity_positive(high_quality_token):
    """Test price velocity calculation with positive change."""
    velocity = calculate_price_velocity(high_quality_token)
    
    assert velocity == 30.0
    assert isinstance(velocity, float)


def test_price_velocity_negative():
    """Test price velocity calculation with negative change."""
    token_data = {
        "priceChange": {
            "h1": -15.5
        }
    }
    
    velocity = calculate_price_velocity(token_data)
    
    assert velocity == -15.5


def test_price_velocity_zero():
    """Test price velocity calculation with zero change."""
    token_data = {
        "priceChange": {
            "h1": 0.0
        }
    }
    
    velocity = calculate_price_velocity(token_data)
    
    assert velocity == 0.0


def test_price_velocity_missing_data():
    """Test price velocity calculation with missing data."""
    token_data = {
        "priceChange": {}
    }
    
    velocity = calculate_price_velocity(token_data)
    
    assert velocity == 0.0  # Fallback


def test_price_velocity_invalid_data():
    """Test price velocity calculation with invalid data."""
    token_data = {
        "priceChange": {
            "h1": "not_a_number"
        }
    }
    
    velocity = calculate_price_velocity(token_data)
    
    assert velocity == 0.0  # Fallback


# =============================================================================
# BUY/SELL RATIO TESTS
# =============================================================================

def test_buy_sell_ratio_high_pressure(high_quality_token):
    """Test buy/sell ratio with high buying pressure."""
    ratio = get_buy_sell_ratio(high_quality_token)
    
    assert ratio is not None
    assert ratio == 2.5  # 250 buys / 100 sells
    assert ratio > 1.0


def test_buy_sell_ratio_balanced():
    """Test buy/sell ratio with balanced trading."""
    token_data = {
        "txns": {
            "h1": {
                "buys": 100,
                "sells": 100
            }
        }
    }
    
    ratio = get_buy_sell_ratio(token_data)
    
    assert ratio == 1.0


def test_buy_sell_ratio_sell_pressure():
    """Test buy/sell ratio with selling pressure."""
    token_data = {
        "txns": {
            "h1": {
                "buys": 50,
                "sells": 100
            }
        }
    }
    
    ratio = get_buy_sell_ratio(token_data)
    
    assert ratio is not None
    assert ratio == 0.5
    assert ratio < 1.0


def test_buy_sell_ratio_zero_sells():
    """Test buy/sell ratio with zero sells (infinite pressure)."""
    token_data = {
        "txns": {
            "h1": {
                "buys": 100,
                "sells": 0
            }
        }
    }
    
    ratio = get_buy_sell_ratio(token_data)
    
    assert ratio == float('inf')


def test_buy_sell_ratio_zero_buys_and_sells():
    """Test buy/sell ratio with zero activity."""
    token_data = {
        "txns": {
            "h1": {
                "buys": 0,
                "sells": 0
            }
        }
    }
    
    ratio = get_buy_sell_ratio(token_data)
    
    assert ratio == 1.0  # Fallback for no activity


def test_buy_sell_ratio_missing_data():
    """Test buy/sell ratio with missing data."""
    token_data = {
        "txns": {}
    }
    
    ratio = get_buy_sell_ratio(token_data)
    
    assert ratio is None


# =============================================================================
# PUMP PHASE CLASSIFICATION TESTS
# =============================================================================

def test_classify_pump_early(high_quality_token):
    """Test pump phase classification for EARLY phase."""
    phase = classify_pump_phase(high_quality_token)
    
    assert phase == "EARLY"


def test_classify_pump_late_high_price(low_quality_token):
    """Test pump phase classification for LATE phase (high price change)."""
    phase = classify_pump_phase(low_quality_token)
    
    assert phase == "LATE"


def test_classify_pump_late_sell_pressure():
    """Test pump phase classification for LATE phase (more sells than buys)."""
    token_data = {
        "priceChange": {
            "h1": 40.0  # Below 50% but...
        },
        "txns": {
            "h1": {
                "buys": 100,
                "sells": 200  # More sells = LATE
            }
        }
    }
    
    phase = classify_pump_phase(token_data)
    
    assert phase == "LATE"


def test_classify_pump_boundary_50_percent():
    """Test pump phase classification at 50% boundary."""
    token_data = {
        "priceChange": {
            "h1": 50.0
        },
        "txns": {
            "h1": {
                "buys": 150,
                "sells": 100
            }
        }
    }
    
    phase = classify_pump_phase(token_data)
    
    assert phase == "EARLY"  # Exactly 50% is still EARLY


def test_classify_pump_boundary_50_1_percent():
    """Test pump phase classification just over 50% boundary."""
    token_data = {
        "priceChange": {
            "h1": 50.1
        },
        "txns": {
            "h1": {
                "buys": 150,
                "sells": 100
            }
        }
    }
    
    phase = classify_pump_phase(token_data)
    
    assert phase == "LATE"  # Over 50% is LATE


def test_classify_pump_missing_data():
    """Test pump phase classification with missing data."""
    token_data = {
        "priceChange": {}
    }
    
    phase = classify_pump_phase(token_data)
    
    # Missing data means price_change=0 and ratio=None
    # 0 < 50 and ratio is None (not < 1.0), so returns EARLY
    assert phase == "EARLY"


# =============================================================================
# STALENESS DETECTION TESTS
# =============================================================================

def test_staleness_young_token(high_quality_token, token_age_hours):
    """Test staleness detection with young active token."""
    age = token_age_hours(high_quality_token)
    is_stale = check_staleness(high_quality_token, token_age_hours=age)
    
    assert is_stale is False


def test_staleness_old_flat_token(stale_token, token_age_hours):
    """Test staleness detection with old flat token."""
    age = token_age_hours(stale_token)
    is_stale = check_staleness(stale_token, token_age_hours=age)
    
    assert is_stale is True


def test_staleness_old_active_token():
    """Test staleness detection with old but active token."""
    token_data = {
        "priceChange": {
            "h1": 10.0  # Still moving
        }
    }
    
    is_stale = check_staleness(token_data, token_age_hours=30)
    
    assert is_stale is False  # Old but not flat


def test_staleness_young_flat_token():
    """Test staleness detection with young flat token."""
    token_data = {
        "priceChange": {
            "h1": 0.05  # Flat
        }
    }
    
    is_stale = check_staleness(token_data, token_age_hours=2)
    
    assert is_stale is False  # Young so not stale


def test_staleness_boundary_24_hours():
    """Test staleness detection at 24h boundary."""
    token_data = {
        "priceChange": {
            "h1": 0.05  # Flat
        }
    }
    
    is_stale = check_staleness(token_data, token_age_hours=24.0)
    
    assert is_stale is False  # Exactly 24h is not stale (> 24h required)


def test_staleness_boundary_24_1_hours():
    """Test staleness detection just over 24h boundary."""
    token_data = {
        "priceChange": {
            "h1": 0.05  # Flat
        }
    }
    
    is_stale = check_staleness(token_data, token_age_hours=24.1)
    
    assert is_stale is True  # Over 24h + flat = stale


def test_staleness_missing_age():
    """Test staleness detection with missing age data."""
    token_data = {
        "priceChange": {
            "h1": 0.05
        }
    }
    
    is_stale = check_staleness(token_data)
    
    assert is_stale is False  # Can't determine age, default to not stale
