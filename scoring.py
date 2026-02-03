"""
Multi-dimensional scoring system for PM-Predict bot.

Combines results from Shield (safety), Momentum (timing), Brain (relevance),
and LLM analysis into a composite score for alert decision making.

Scoring dimensions:
- Safety (35%): Shield results (rugcheck, holder concentration, honeypot)
- Timing (25%): Pump phase classification (EARLY/LATE)
- Momentum (20%): Price velocity and buy/sell ratio
- Relevance (20%): LLM relevance and authenticity analysis
"""

import logging
from typing import Dict, Any, Optional

import config

logger = logging.getLogger(__name__)


def calculate_composite_score(
    shield_result: Dict[str, Any],
    momentum_result: Dict[str, Any],
    brain_result: Dict[str, Any],
    pump_phase: str
) -> Dict[str, Any]:
    """
    Calculate composite multi-dimensional score.
    
    Args:
        shield_result: From shield.comprehensive_security_check()
                      Must contain: safety_score (0-100)
        momentum_result: From momentum module
                        Must contain: price_velocity (float), buy_sell_ratio (float)
        brain_result: From brain.analyze_with_llm()
                     Must contain: relevance_score (0-100), confidence (0-100)
        pump_phase: "EARLY" or "LATE" from momentum.classify_pump_phase()
    
    Returns:
        Dict with composite score and breakdown:
        {
            "composite_score": 0-100,
            "safety_score": 0-100,
            "timing_score": 0-100,
            "momentum_score": 0-100,
            "relevance_score": 0-100,
            "individual_scores": {
                "safety": ...,
                "timing": ...,
                "momentum": ...,
                "relevance": ...
            },
            "weights": config.SCORE_WEIGHTS,
            "timestamp": ISO8601 string
        }
    """
    import datetime
    
    # Extract individual scores from results
    safety_score = shield_result.get("safety_score", 0)
    
    # Timing score: EARLY phase = good (80), LATE phase = bad (20)
    timing_score = 80 if pump_phase == "EARLY" else 20
    
    # Momentum score: based on price velocity and buy/sell ratio
    # Normalize price velocity (0-50% = 20-80 score, >50% = 20 score)
    price_velocity = momentum_result.get("price_velocity", 0)
    if price_velocity < 0:
        momentum_from_velocity = 50  # Negative is neutral (decline but no rug)
    elif price_velocity < config.MAX_1H_PRICE_CHANGE_PERCENT:
        # Scale linearly: 0% = 20, 50% = 80
        momentum_from_velocity = 20 + (price_velocity / config.MAX_1H_PRICE_CHANGE_PERCENT) * 60
    else:
        momentum_from_velocity = 20  # Over 50% = weak momentum signal
    
    # Buy/sell ratio factor (1.0 = balanced, higher = more bullish)
    ratio = momentum_result.get("buy_sell_ratio", 1.0)
    if ratio is None:
        ratio_score = 50
    elif ratio < 1.0:
        ratio_score = 20 + (ratio * 80)  # 0.0 = 20, 1.0 = 100
    else:
        ratio_score = min(80 + (ratio - 1.0) * 20, 100)  # 1.0 = 80, 2.0 = 100
    
    # Average the two momentum factors
    momentum_score = (momentum_from_velocity + ratio_score) / 2
    
    # Relevance score: from LLM analysis
    relevance_score = brain_result.get("relevance_score", 50)
    
    # Calculate composite using configured weights
    weights = config.SCORE_WEIGHTS
    composite_score = (
        safety_score * weights["safety"]
        + timing_score * weights["timing"]
        + momentum_score * weights["momentum"]
        + relevance_score * weights["relevance"]
    )
    
    # Cap scores at 0-100 range
    composite_score = max(0, min(100, composite_score))
    safety_score = max(0, min(100, safety_score))
    timing_score = max(0, min(100, timing_score))
    momentum_score = max(0, min(100, momentum_score))
    relevance_score = max(0, min(100, relevance_score))
    
    logger.debug(
        f"Composite score breakdown: safety={safety_score:.1f}, "
        f"timing={timing_score:.1f}, momentum={momentum_score:.1f}, "
        f"relevance={relevance_score:.1f} → composite={composite_score:.1f}"
    )
    
    return {
        "composite_score": round(composite_score, 1),
        "safety_score": round(safety_score, 1),
        "timing_score": round(timing_score, 1),
        "momentum_score": round(momentum_score, 1),
        "relevance_score": round(relevance_score, 1),
        "individual_scores": {
            "safety": round(safety_score, 1),
            "timing": round(timing_score, 1),
            "momentum": round(momentum_score, 1),
            "relevance": round(relevance_score, 1),
        },
        "weights": config.SCORE_WEIGHTS,
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
    }


def should_alert(score_data: Dict[str, Any]) -> bool:
    """
    Determine if composite score warrants an alert.
    
    Alert criteria:
    1. Composite score > MIN_COMPOSITE_SCORE (70)
    2. ALL individual scores > MIN_INDIVIDUAL_SCORE (40)
    
    Args:
        score_data: Result from calculate_composite_score()
    
    Returns:
        True if alert should be sent, False otherwise
    """
    composite = score_data.get("composite_score", 0)
    individual = score_data.get("individual_scores", {})
    
    # Check composite score threshold
    if composite <= config.MIN_COMPOSITE_SCORE:
        logger.debug(
            f"Composite score {composite:.1f} below threshold "
            f"({config.MIN_COMPOSITE_SCORE})"
        )
        return False
    
    # Check ALL individual scores above threshold
    min_score = min(individual.values()) if individual else 0
    if min_score <= config.MIN_INDIVIDUAL_SCORE:
        logger.debug(
            f"Individual score {min_score:.1f} below threshold "
            f"({config.MIN_INDIVIDUAL_SCORE}). Breakdown: {individual}"
        )
        return False
    
    logger.info(
        f"Alert criteria met: composite={composite:.1f}, "
        f"min_individual={min_score:.1f}"
    )
    return True


def format_score_output(score_data: Dict[str, Any]) -> str:
    """
    Format score data for Telegram output.
    
    Returns human-readable multi-line string with emoji rating scale.
    
    Args:
        score_data: Result from calculate_composite_score()
    
    Returns:
        Formatted string like:
        ⭐⭐⭐⭐⭐ 85/100
        
        Safety:     ⭐⭐⭐ 65/100
        Timing:     ⭐⭐⭐⭐ 80/100
        Momentum:   ⭐⭐ 45/100
        Relevance:  ⭐⭐⭐⭐ 75/100
    """
    composite = score_data.get("composite_score", 0)
    individual = score_data.get("individual_scores", {})
    
    def score_to_stars(score: float, max_score: int = 100, max_stars: int = 5) -> str:
        """Convert numeric score to star rating."""
        num_stars = max(0, min(max_stars, int((score / max_score) * max_stars)))
        return "⭐" * num_stars
    
    # Build output
    lines = []
    
    # Composite score with stars (main header)
    composite_stars = score_to_stars(composite, max_stars=5)
    lines.append(f"{composite_stars} {composite:.0f}/100")
    lines.append("")
    
    # Individual dimensions
    dimension_order = ["safety", "timing", "momentum", "relevance"]
    dimension_labels = {
        "safety": "Safety",
        "timing": "Timing",
        "momentum": "Momentum",
        "relevance": "Relevance",
    }
    
    for dim in dimension_order:
        if dim in individual:
            score = individual[dim]
            stars = score_to_stars(score, max_stars=5)
            label = dimension_labels[dim]
            lines.append(f"{label:12} {stars} {score:.0f}/100")
    
    return "\n".join(lines)


def format_score_telegram_message(
    score_data: Dict[str, Any],
    token_name: str = "Token",
    token_symbol: str = "???",
    token_address: Optional[str] = None,
) -> str:
    """
    Format complete Telegram message with scores and metadata.
    
    Args:
        score_data: Result from calculate_composite_score()
        token_name: Token display name
        token_symbol: Token symbol
        token_address: Token mint address (optional)
    
    Returns:
        Formatted Telegram message
    """
    lines = []
    
    # Header
    composite = score_data.get("composite_score", 0)
    if composite >= 80:
        emoji = "🚀"
    elif composite >= 70:
        emoji = "📈"
    else:
        emoji = "📊"
    
    lines.append(f"{emoji} {token_name} ({token_symbol})")
    if token_address:
        # Show short address hash
        lines.append(f"Address: {token_address[:16]}...")
    
    lines.append("")
    
    # Scores
    lines.append("Score Analysis:")
    lines.append(format_score_output(score_data))
    
    lines.append("")
    
    # Alert decision
    if should_alert(score_data):
        lines.append("✅ ALERT THRESHOLD MET - Ready to send")
    else:
        lines.append("❌ Below alert threshold")
        missing = []
        if score_data.get("composite_score", 0) <= config.MIN_COMPOSITE_SCORE:
            missing.append(f"composite: {score_data.get('composite_score', 0):.1f}/{config.MIN_COMPOSITE_SCORE}")
        for dim, score in score_data.get("individual_scores", {}).items():
            if score <= config.MIN_INDIVIDUAL_SCORE:
                missing.append(f"{dim}: {score:.1f}/{config.MIN_INDIVIDUAL_SCORE}")
        if missing:
            lines.append(f"Needs: {', '.join(missing)}")
    
    return "\n".join(lines)


# ============================================================================
# TESTING & VERIFICATION
# ============================================================================

if __name__ == "__main__":
    # Test with sample data
    logging.basicConfig(level=logging.DEBUG)
    
    print("=" * 70)
    print("SCORING SYSTEM TEST")
    print("=" * 70)
    print()
    
    # Test case 1: High-quality candidate
    print("Test Case 1: High-Quality Candidate")
    print("-" * 70)
    shield_result = {"safety_score": 85}
    momentum_result = {"price_velocity": 35, "buy_sell_ratio": 1.8}
    brain_result = {"relevance_score": 80, "confidence": 90}
    pump_phase = "EARLY"
    
    score1 = calculate_composite_score(shield_result, momentum_result, brain_result, pump_phase)
    print(f"Composite Score: {score1['composite_score']}/100")
    print(format_score_output(score1))
    print(f"Should Alert: {should_alert(score1)}")
    print()
    
    # Test case 2: Medium quality
    print("Test Case 2: Medium Quality")
    print("-" * 70)
    shield_result = {"safety_score": 65}
    momentum_result = {"price_velocity": 45, "buy_sell_ratio": 1.2}
    brain_result = {"relevance_score": 60, "confidence": 70}
    pump_phase = "EARLY"
    
    score2 = calculate_composite_score(shield_result, momentum_result, brain_result, pump_phase)
    print(f"Composite Score: {score2['composite_score']}/100")
    print(format_score_output(score2))
    print(f"Should Alert: {should_alert(score2)}")
    print()
    
    # Test case 3: Late entry (bad timing)
    print("Test Case 3: Late Entry (Bad Timing)")
    print("-" * 70)
    shield_result = {"safety_score": 75}
    momentum_result = {"price_velocity": 55, "buy_sell_ratio": 0.8}
    brain_result = {"relevance_score": 70, "confidence": 80}
    pump_phase = "LATE"  # This kills the score
    
    score3 = calculate_composite_score(shield_result, momentum_result, brain_result, pump_phase)
    print(f"Composite Score: {score3['composite_score']}/100")
    print(format_score_output(score3))
    print(f"Should Alert: {should_alert(score3)}")
    print()
    
    # Test case 4: Telegram message formatting
    print("Test Case 4: Telegram Message Formatting")
    print("-" * 70)
    msg = format_score_telegram_message(
        score1,
        token_name="Trump Coin",
        token_symbol="TRUMP",
        token_address="12345abcde..."
    )
    print(msg)
    print()
    
    print("=" * 70)
    print("All tests completed successfully!")
    print("=" * 70)
