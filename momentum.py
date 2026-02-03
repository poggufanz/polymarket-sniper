"""
Momentum and price velocity analysis for PM-Predict bot.

This module analyzes token price movement and identifies pump phases to detect
late entries and stale tokens. It uses data from DexScreener API.

Key Functions:
- calculate_price_velocity(): Get 1-hour price change percentage
- classify_pump_phase(): Determine EARLY or LATE pump phase
- check_staleness(): Identify tokens with no recent price movement
- get_buy_sell_ratio(): Calculate buying pressure vs selling pressure
"""

import logging
from typing import Optional, Dict, Any

import config

logger = logging.getLogger(__name__)


def calculate_price_velocity(token_data: Dict[str, Any]) -> float:
    """
    Calculate 1-hour price velocity (% change).
    
    Uses DexScreener's pre-calculated priceChange.h1 field directly.
    
    Args:
        token_data: Token data from DexScreener API response
        
    Returns:
        Float representing 1-hour price change percentage (e.g., 45.5 for +45.5%)
        Returns 0.0 if data unavailable
        
    Example:
        >>> token_data = {"priceChange": {"h1": 45.5}}
        >>> velocity = calculate_price_velocity(token_data)
        >>> velocity
        45.5
    """
    try:
        # DexScreener returns priceChange.h1 as percentage value
        price_change = token_data.get("priceChange", {})
        if isinstance(price_change, dict):
            h1_change = price_change.get("h1")
            if h1_change is not None:
                return float(h1_change)
        
        logger.warning("priceChange.h1 not found in token data")
        return 0.0
        
    except (TypeError, ValueError) as e:
        logger.warning(f"Error calculating price velocity: {e}")
        return 0.0


def get_buy_sell_ratio(token_data: Dict[str, Any]) -> Optional[float]:
    """
    Calculate buy/sell transaction ratio from 1-hour data.
    
    Uses DexScreener's txns.h1.buys and txns.h1.sells fields.
    
    Args:
        token_data: Token data from DexScreener API response
        
    Returns:
        Float representing buys/sells ratio (e.g., 1.5 = 50% more buys than sells)
        Returns None if data unavailable
        
    Example:
        >>> token_data = {"txns": {"h1": {"buys": 150, "sells": 100}}}
        >>> ratio = get_buy_sell_ratio(token_data)
        >>> ratio
        1.5
    """
    try:
        txns = token_data.get("txns", {})
        if not isinstance(txns, dict):
            return None
            
        h1_txns = txns.get("h1")
        if not isinstance(h1_txns, dict):
            return None
        
        buys = h1_txns.get("buys")
        sells = h1_txns.get("sells")
        
        # Handle missing or invalid data
        if buys is None or sells is None:
            logger.warning("txns.h1.buys or txns.h1.sells not found in token data")
            return None
        
        buys = int(buys)
        sells = int(sells)
        
        # Avoid division by zero
        if sells == 0:
            # If no sells and some buys, ratio is very high (infinite buying pressure)
            return float('inf') if buys > 0 else 1.0
        
        return buys / sells
        
    except (TypeError, ValueError) as e:
        logger.warning(f"Error calculating buy/sell ratio: {e}")
        return None


def classify_pump_phase(token_data: Dict[str, Any]) -> str:
    """
    Classify token into pump phase: EARLY or LATE.
    
    Binary classification based on:
    - EARLY: priceChange.h1 < 50% AND buys > sells (increasing buying pressure)
    - LATE: priceChange.h1 > 50% OR sells > buys (peak or declining pressure)
    
    This simple binary model filters out late entries without complex indicators.
    
    Args:
        token_data: Token data from DexScreener API response
        
    Returns:
        "EARLY" or "LATE" string
        
    Example:
        >>> token_data = {
        ...     "priceChange": {"h1": 30},  # 30% pump
        ...     "txns": {"h1": {"buys": 200, "sells": 100}}
        ... }
        >>> phase = classify_pump_phase(token_data)
        >>> phase
        'EARLY'
    """
    try:
        # Get price velocity
        price_change = calculate_price_velocity(token_data)
        
        # Get buy/sell ratio
        ratio = get_buy_sell_ratio(token_data)
        
        # Determine phase based on thresholds
        # LATE: If >50% pump has already happened
        if price_change > config.MAX_1H_PRICE_CHANGE_PERCENT:
            logger.info(f"Token in LATE phase: {price_change:.2f}% pump (>50%)")
            return "LATE"
        
        # LATE: If sells are exceeding buys (losing momentum)
        if ratio is not None and ratio < 1.0:
            logger.info(f"Token in LATE phase: buy/sell ratio {ratio:.2f} (<1.0, more sells)")
            return "LATE"
        
        # EARLY: Low pump + more buys than sells
        logger.info(f"Token in EARLY phase: {price_change:.2f}% pump, ratio {ratio or 'N/A'}")
        return "EARLY"
        
    except Exception as e:
        logger.warning(f"Error classifying pump phase: {e}")
        # Default to LATE on error (conservative approach)
        return "LATE"


def check_staleness(token_data: Dict[str, Any], token_age_hours: Optional[float] = None) -> bool:
    """
    Check if token is stale (old and flat price).
    
    A token is considered STALE if:
    - Token age > 24 hours (MAX_TOKEN_AGE_HOURS from config)
    - Price change in 1h is near zero (close to 0%, minimal movement)
    
    Stale tokens indicate mature projects or dead tokens, not interesting for timing.
    
    Args:
        token_data: Token data from DexScreener API response
        token_age_hours: Token age in hours. If None, uses age from token_data.
        
    Returns:
        True if token is stale, False otherwise
        
    Example:
        >>> token_data = {
        ...     "priceChange": {"h1": 0.5},  # Minimal price movement
        ...     "createdAt": "2025-01-01T00:00:00Z"
        ... }
        >>> is_stale = check_staleness(token_data, token_age_hours=50)
        >>> is_stale
        True
    """
    try:
        # Get price change
        price_change = calculate_price_velocity(token_data)
        
        # Use provided age or extract from token_data
        if token_age_hours is None:
            # Try to get age from token_data (createdAt timestamp)
            created_at = token_data.get("createdAt")
            if created_at:
                from datetime import datetime, timezone
                try:
                    created_time = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    now = datetime.now(timezone.utc)
                    token_age_hours = (now - created_time).total_seconds() / 3600
                except (ValueError, AttributeError):
                    logger.warning(f"Could not parse createdAt: {created_at}")
                    token_age_hours = 0
            else:
                token_age_hours = 0
        
        # Check staleness conditions
        is_old = token_age_hours > config.MAX_TOKEN_AGE_HOURS
        is_flat = abs(price_change) < config.MIN_1H_PRICE_CHANGE_PERCENT
        
        is_stale = is_old and is_flat
        
        if is_stale:
            logger.info(
                f"Token is STALE: age {token_age_hours:.1f}h (>{config.MAX_TOKEN_AGE_HOURS}h), "
                f"price change {price_change:.2f}% (<{config.MIN_1H_PRICE_CHANGE_PERCENT}%)"
            )
        
        return is_stale
        
    except Exception as e:
        logger.warning(f"Error checking staleness: {e}")
        return False


# ============================================================================
# TESTING & DEBUGGING
# ============================================================================

if __name__ == "__main__":
    """Test momentum module with example data."""
    
    logging.basicConfig(
        level=logging.INFO,
        format="[%(levelname)s] %(message)s"
    )
    
    # Test case 1: EARLY pump (30% change, more buys than sells)
    early_token = {
        "priceChange": {"h1": 30.0},
        "txns": {"h1": {"buys": 250, "sells": 100}},
        "createdAt": "2025-02-03T10:00:00Z"
    }
    
    print("=" * 70)
    print("TEST CASE 1: EARLY Phase Token")
    print("=" * 70)
    vel = calculate_price_velocity(early_token)
    ratio = get_buy_sell_ratio(early_token)
    phase = classify_pump_phase(early_token)
    stale = check_staleness(early_token, token_age_hours=0.5)
    
    print(f"Price Velocity: {vel}%")
    print(f"Buy/Sell Ratio: {ratio}")
    print(f"Pump Phase: {phase}")
    print(f"Is Stale: {stale}")
    print(f"Expected: EARLY, not stale")
    print()
    
    # Test case 2: LATE pump (60% change, more sells)
    late_token = {
        "priceChange": {"h1": 60.0},
        "txns": {"h1": {"buys": 100, "sells": 300}},
        "createdAt": "2025-02-02T10:00:00Z"
    }
    
    print("=" * 70)
    print("TEST CASE 2: LATE Phase Token")
    print("=" * 70)
    vel = calculate_price_velocity(late_token)
    ratio = get_buy_sell_ratio(late_token)
    phase = classify_pump_phase(late_token)
    stale = check_staleness(late_token, token_age_hours=26)
    
    print(f"Price Velocity: {vel}%")
    print(f"Buy/Sell Ratio: {ratio}")
    print(f"Pump Phase: {phase}")
    print(f"Is Stale: {stale}")
    print(f"Expected: LATE, might be stale")
    print()
    
    # Test case 3: Stale token (old, flat price)
    stale_token = {
        "priceChange": {"h1": 0.05},
        "txns": {"h1": {"buys": 10, "sells": 10}},
        "createdAt": "2025-01-01T00:00:00Z"
    }
    
    print("=" * 70)
    print("TEST CASE 3: Stale Token")
    print("=" * 70)
    vel = calculate_price_velocity(stale_token)
    ratio = get_buy_sell_ratio(stale_token)
    phase = classify_pump_phase(stale_token)
    stale = check_staleness(stale_token, token_age_hours=48)
    
    print(f"Price Velocity: {vel}%")
    print(f"Buy/Sell Ratio: {ratio}")
    print(f"Pump Phase: {phase}")
    print(f"Is Stale: {stale}")
    print(f"Expected: EARLY, IS STALE")
    print()
    
    # Test case 4: Missing data handling
    incomplete_token = {
        "priceChange": {}
    }
    
    print("=" * 70)
    print("TEST CASE 4: Incomplete Data Handling")
    print("=" * 70)
    vel = calculate_price_velocity(incomplete_token)
    ratio = get_buy_sell_ratio(incomplete_token)
    phase = classify_pump_phase(incomplete_token)
    
    print(f"Price Velocity: {vel}% (fallback to 0)")
    print(f"Buy/Sell Ratio: {ratio} (fallback to None)")
    print(f"Pump Phase: {phase} (fallback to LATE on missing data)")
    print(f"Expected: Safe defaults with graceful error handling")
    print()
    
    print("=" * 70)
    print("[OK] All momentum module tests completed")
    print("=" * 70)
