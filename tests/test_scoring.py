"""
Unit tests for scoring.py composite scoring module.

Tests cover:
- Composite score calculation
- Alert threshold logic
- Score formatting
- Edge cases and boundaries
"""

import pytest
from scoring import (
    calculate_composite_score,
    should_alert,
    format_score_output,
    format_score_telegram_message,
)


# =============================================================================
# COMPOSITE SCORE CALCULATION TESTS
# =============================================================================

def test_composite_score_high_quality():
    """Test composite score calculation with high quality inputs."""
    shield_result = {"safety_score": 85}
    momentum_result = {"price_velocity": 35, "buy_sell_ratio": 1.8}
    brain_result = {"relevance_score": 80, "confidence": 90}
    pump_phase = "EARLY"
    
    score_data = calculate_composite_score(
        shield_result, momentum_result, brain_result, pump_phase
    )
    
    assert score_data["composite_score"] >= 70
    assert score_data["safety_score"] == 85
    assert score_data["timing_score"] == 80  # EARLY
    assert score_data["momentum_score"] > 50
    assert score_data["relevance_score"] == 80


def test_composite_score_late_phase():
    """Test composite score calculation with LATE phase (bad timing)."""
    shield_result = {"safety_score": 75}
    momentum_result = {"price_velocity": 55, "buy_sell_ratio": 0.8}
    brain_result = {"relevance_score": 70, "confidence": 80}
    pump_phase = "LATE"
    
    score_data = calculate_composite_score(
        shield_result, momentum_result, brain_result, pump_phase
    )
    
    assert score_data["timing_score"] == 20  # LATE phase
    assert score_data["composite_score"] < 70  # Should fail alert threshold


def test_composite_score_low_safety():
    """Test composite score calculation with low safety score."""
    shield_result = {"safety_score": 30}
    momentum_result = {"price_velocity": 35, "buy_sell_ratio": 1.5}
    brain_result = {"relevance_score": 75, "confidence": 85}
    pump_phase = "EARLY"
    
    score_data = calculate_composite_score(
        shield_result, momentum_result, brain_result, pump_phase
    )
    
    assert score_data["safety_score"] == 30
    assert score_data["composite_score"] < 70  # Low safety kills composite


def test_composite_score_weights():
    """Test that score weights are correctly applied."""
    shield_result = {"safety_score": 100}
    momentum_result = {"price_velocity": 25, "buy_sell_ratio": 1.5}
    brain_result = {"relevance_score": 100, "confidence": 100}
    pump_phase = "EARLY"
    
    score_data = calculate_composite_score(
        shield_result, momentum_result, brain_result, pump_phase
    )
    
    # Check weights are present
    assert "weights" in score_data
    assert score_data["weights"]["safety"] == 0.35
    assert score_data["weights"]["timing"] == 0.25
    assert score_data["weights"]["momentum"] == 0.20
    assert score_data["weights"]["relevance"] == 0.20


def test_composite_score_negative_velocity():
    """Test composite score with negative price velocity."""
    shield_result = {"safety_score": 70}
    momentum_result = {"price_velocity": -10, "buy_sell_ratio": 1.2}
    brain_result = {"relevance_score": 65, "confidence": 75}
    pump_phase = "EARLY"
    
    score_data = calculate_composite_score(
        shield_result, momentum_result, brain_result, pump_phase
    )
    
    # Negative velocity should be handled (→ 50 momentum)
    assert score_data["momentum_score"] >= 40
    assert score_data["composite_score"] > 0


def test_composite_score_none_ratio():
    """Test composite score with None buy_sell_ratio."""
    shield_result = {"safety_score": 75}
    momentum_result = {"price_velocity": 30, "buy_sell_ratio": None}
    brain_result = {"relevance_score": 70, "confidence": 80}
    pump_phase = "EARLY"
    
    score_data = calculate_composite_score(
        shield_result, momentum_result, brain_result, pump_phase
    )
    
    # None ratio should be handled with fallback
    assert score_data["momentum_score"] > 0
    assert score_data["composite_score"] > 0


def test_composite_score_extreme_ratio():
    """Test composite score with extreme buy_sell_ratio."""
    shield_result = {"safety_score": 80}
    momentum_result = {"price_velocity": 30, "buy_sell_ratio": 10.0}
    brain_result = {"relevance_score": 75, "confidence": 85}
    pump_phase = "EARLY"
    
    score_data = calculate_composite_score(
        shield_result, momentum_result, brain_result, pump_phase
    )
    
    # Extreme ratio should be capped at 100
    assert score_data["momentum_score"] <= 100


def test_composite_score_all_zeros():
    """Test composite score with all zero inputs."""
    shield_result = {"safety_score": 0}
    momentum_result = {"price_velocity": 0, "buy_sell_ratio": 0}
    brain_result = {"relevance_score": 0, "confidence": 0}
    pump_phase = "LATE"
    
    score_data = calculate_composite_score(
        shield_result, momentum_result, brain_result, pump_phase
    )
    
    assert score_data["composite_score"] >= 0
    assert score_data["composite_score"] < 30


# =============================================================================
# ALERT THRESHOLD TESTS
# =============================================================================

def test_should_alert_pass():
    """Test should_alert with passing scores."""
    score_data = {
        "composite_score": 81.5,
        "individual_scores": {
            "safety": 85,
            "timing": 80,
            "momentum": 75,
            "relevance": 80
        }
    }
    
    assert should_alert(score_data) is True


def test_should_alert_fail_composite():
    """Test should_alert with low composite score."""
    score_data = {
        "composite_score": 65,  # Below 70
        "individual_scores": {
            "safety": 75,
            "timing": 80,
            "momentum": 70,
            "relevance": 75
        }
    }
    
    assert should_alert(score_data) is False


def test_should_alert_fail_individual():
    """Test should_alert with low individual score."""
    score_data = {
        "composite_score": 71,  # Above 70
        "individual_scores": {
            "safety": 85,
            "timing": 20,  # Below 40 (LATE phase)
            "momentum": 75,
            "relevance": 80
        }
    }
    
    assert should_alert(score_data) is False


def test_should_alert_boundary_composite():
    """Test should_alert at composite boundary (70)."""
    score_data = {
        "composite_score": 70.0,
        "individual_scores": {
            "safety": 75,
            "timing": 80,
            "momentum": 70,
            "relevance": 75
        }
    }
    
    assert should_alert(score_data) is False  # Must be > 70


def test_should_alert_boundary_composite_pass():
    """Test should_alert just above composite boundary."""
    score_data = {
        "composite_score": 70.1,
        "individual_scores": {
            "safety": 75,
            "timing": 80,
            "momentum": 70,
            "relevance": 75
        }
    }
    
    assert should_alert(score_data) is True


def test_should_alert_boundary_individual():
    """Test should_alert at individual boundary (40)."""
    score_data = {
        "composite_score": 71,
        "individual_scores": {
            "safety": 75,
            "timing": 80,
            "momentum": 40,  # Exactly 40
            "relevance": 75
        }
    }
    
    assert should_alert(score_data) is False  # Must be > 40


def test_should_alert_boundary_individual_pass():
    """Test should_alert just above individual boundary."""
    score_data = {
        "composite_score": 71,
        "individual_scores": {
            "safety": 75,
            "timing": 80,
            "momentum": 40.1,  # Just above
            "relevance": 75
        }
    }
    
    assert should_alert(score_data) is True


# =============================================================================
# SCORE FORMATTING TESTS
# =============================================================================

def test_format_score_output():
    """Test score output formatting."""
    score_data = {
        "composite_score": 85,
        "individual_scores": {
            "safety": 65,
            "timing": 80,
            "momentum": 70,
            "relevance": 90
        }
    }
    
    output = format_score_output(score_data)
    
    assert "85" in output
    assert "⭐" in output  # Has stars
    assert "Safety" in output
    assert "Timing" in output
    assert "Momentum" in output
    assert "Relevance" in output


def test_format_score_telegram_message():
    """Test Telegram message formatting."""
    score_data = {
        "composite_score": 85,
        "individual_scores": {
            "safety": 70,
            "timing": 80,
            "momentum": 75,
            "relevance": 85
        }
    }
    
    message = format_score_telegram_message(
        score_data,
        token_name="Trump Victory Token",
        token_symbol="TRUMP",
        token_address="test_address_12345"
    )
    
    assert "Trump Victory Token" in message
    assert "TRUMP" in message
    assert "test_address" in message
    assert "85" in message


def test_format_score_telegram_message_no_alert():
    """Test Telegram message formatting for below-threshold score."""
    score_data = {
        "composite_score": 65,
        "individual_scores": {
            "safety": 60,
            "timing": 70,
            "momentum": 65,
            "relevance": 70
        }
    }
    
    message = format_score_telegram_message(
        score_data,
        token_name="Test Token",
        token_symbol="TEST"
    )
    
    assert "Below alert threshold" in message or "❌" in message


def test_format_score_output_zero_scores():
    """Test score output formatting with zero scores."""
    score_data = {
        "composite_score": 0,
        "individual_scores": {
            "safety": 0,
            "timing": 0,
            "momentum": 0,
            "relevance": 0
        }
    }
    
    output = format_score_output(score_data)
    
    # Should not crash, handle gracefully
    assert "0" in output


def test_format_score_output_max_scores():
    """Test score output formatting with maximum scores."""
    score_data = {
        "composite_score": 100,
        "individual_scores": {
            "safety": 100,
            "timing": 100,
            "momentum": 100,
            "relevance": 100
        }
    }
    
    output = format_score_output(score_data)
    
    assert "100" in output
    assert "⭐" in output
