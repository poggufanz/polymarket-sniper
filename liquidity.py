"""
Liquidity Shape Analysis Module for Meteora DLMM Pools.

This module analyzes Meteora DLMM (Dynamic Liquidity Market Maker) pools
to determine liquidity distribution shapes and extract active bin information.

Shapes:
- SPOT: Uniform distribution - neutral sentiment
- CURVE: Gaussian/concentrated around active bin - stability/mean reversion
- BID_ASK: Bimodal/heavy at edges - expecting volatility/breakout

Reference: system_prompt.md Section 2.2 (Liquidity Shapes as Sentiment Map)
"""

import logging
from enum import Enum
from typing import Any, Dict, List, Optional
from statistics import variance, mean

import aiohttp

from config import METEORA_API_URL, API_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)


class LiquidityShape(Enum):
    """
    Liquidity distribution shape classifications.
    
    SPOT: Uniform distribution - LP has no directional bias
    CURVE: Gaussian/Bell curve - concentrated around active bin
    BID_ASK: Bimodal/U-shape - heavy at edges, thin in middle
    """
    SPOT = "SPOT"
    CURVE = "CURVE"
    BID_ASK = "BID_ASK"


async def fetch_dlmm_pool(pair_address: str) -> Optional[Dict[str, Any]]:
    """
    Fetch DLMM pool data from Meteora API.
    
    Args:
        pair_address: The Meteora DLMM pool address
        
    Returns:
        Pool data dict if found, None if not found or error (fail-open)
        
    Note:
        Implements fail-open pattern - returns None on any error
        to allow graceful degradation in the pipeline.
    """
    url = f"{METEORA_API_URL}/pair/{pair_address}"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=API_TIMEOUT_SECONDS)) as response:
                if response.status == 404:
                    logger.debug(f"DLMM pool not found: {pair_address}")
                    return None
                    
                if response.status != 200:
                    logger.warning(f"Meteora API returned status {response.status} for {pair_address}")
                    return None
                    
                data = await response.json()
                return data
                
    except aiohttp.ClientError as e:
        logger.warning(f"Network error fetching DLMM pool {pair_address}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error fetching DLMM pool {pair_address}: {e}")
        return None


def get_active_bin(pool_data: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Extract the active bin from pool data.
    
    The active bin is where the current price resides. Trades within
    this bin experience zero slippage.
    
    Args:
        pool_data: DLMM pool data from Meteora API
        
    Returns:
        Active bin dict with bin_id, x_amount, y_amount, or None if not found
    """
    if pool_data is None:
        return None
        
    active_id = pool_data.get("active_id")
    if active_id is None:
        return None
        
    bins = pool_data.get("bins", [])
    if not bins:
        return None
        
    for bin_data in bins:
        if bin_data.get("bin_id") == active_id:
            return bin_data
            
    return None


def _get_bin_liquidity(bin_data: Dict[str, Any]) -> float:
    """
    Calculate total liquidity in a bin.
    
    Args:
        bin_data: Single bin dict
        
    Returns:
        Total liquidity as float (x_amount + y_amount)
    """
    try:
        x_amount = float(bin_data.get("x_amount", 0) or 0)
        y_amount = float(bin_data.get("y_amount", 0) or 0)
        return x_amount + y_amount
    except (ValueError, TypeError):
        return 0.0


def _calculate_distribution_metrics(bins: List[Dict[str, Any]], active_id: Optional[int]) -> Dict[str, float]:
    """
    Calculate statistical metrics for liquidity distribution.
    
    Args:
        bins: List of bin data
        active_id: The active bin ID
        
    Returns:
        Dict with metrics: center_weight, edge_weight, uniformity_score, max_ratio
    """
    if not bins:
        return {"center_weight": 0, "edge_weight": 0, "uniformity_score": 0, "max_ratio": 1.0}
        
    # Sort bins by bin_id
    sorted_bins = sorted(bins, key=lambda b: b.get("bin_id", 0))
    
    # Get liquidity values
    liquidities = [_get_bin_liquidity(b) for b in sorted_bins]
    total_liquidity = sum(liquidities)
    
    if total_liquidity == 0:
        return {"center_weight": 0, "edge_weight": 0, "uniformity_score": 1.0, "max_ratio": 1.0}
    
    # Normalize
    normalized = [liq / total_liquidity for liq in liquidities]
    n = len(normalized)
    
    if n < 3:
        # Too few bins to classify meaningfully
        return {"center_weight": 0.5, "edge_weight": 0.5, "uniformity_score": 1.0, "max_ratio": 1.0}
    
    # Calculate center vs edge weights
    # For 11 bins: edge_size=2 (bins 0,1 and 9,10), center is bins 2-8
    edge_size = max(1, n // 4)
    center_start = edge_size
    center_end = n - edge_size
    
    left_edge = sum(normalized[:edge_size])
    right_edge = sum(normalized[-edge_size:])
    center = sum(normalized[center_start:center_end])
    
    edge_weight = left_edge + right_edge
    center_weight = center
    
    # Max ratio: how much larger is max bin compared to min bin
    max_liq = max(liquidities)
    min_liq = min(liquidities) if min(liquidities) > 0 else 1.0
    max_ratio = max_liq / min_liq
    
    # Uniformity score based on coefficient of variation
    if n > 1 and mean(liquidities) > 0:
        try:
            std_dev = variance(liquidities) ** 0.5
            cv = std_dev / mean(liquidities)  # Coefficient of variation
            # CV < 0.2 is very uniform, CV > 1.0 is highly variable
            uniformity_score = max(0, 1.0 - cv)
        except Exception:
            uniformity_score = 0.5
    else:
        uniformity_score = 1.0
    
    return {
        "center_weight": center_weight,
        "edge_weight": edge_weight,
        "uniformity_score": uniformity_score,
        "max_ratio": max_ratio,
    }


def classify_liquidity_shape(pool_data: Optional[Dict[str, Any]]) -> Optional[LiquidityShape]:
    """
    Classify the liquidity distribution shape.
    
    Detection logic based on system_prompt.md Section 2.2:
    - SPOT: Uniform distribution (high uniformity score, low max_ratio)
    - CURVE: Gaussian/concentrated in center (high center_weight vs edges)
    - BID_ASK: Heavy at edges (high edge_weight, low center_weight)
    
    Args:
        pool_data: DLMM pool data from Meteora API
        
    Returns:
        LiquidityShape enum or None if cannot classify
    """
    if pool_data is None:
        return None
        
    bins = pool_data.get("bins", [])
    if not bins:
        return None
        
    active_id = pool_data.get("active_id")
    
    # Single or two bins = default to SPOT
    if len(bins) <= 2:
        return LiquidityShape.SPOT
    
    metrics = _calculate_distribution_metrics(bins, active_id)
    
    uniformity = metrics["uniformity_score"]
    center_weight = metrics["center_weight"]
    edge_weight = metrics["edge_weight"]
    max_ratio = metrics["max_ratio"]
    
    # Classification thresholds
    
    # First check for uniformity - if bins are all similar (low max_ratio)
    # This is the defining characteristic of SPOT
    if max_ratio < 2.0 and uniformity > 0.5:
        return LiquidityShape.SPOT
    
    # Now compare edge vs center weights to determine CURVE vs BID_ASK
    # BID_ASK: edges have more than center
    if edge_weight > center_weight:
        return LiquidityShape.BID_ASK
    
    # CURVE: center has more than edges
    if center_weight > edge_weight:
        return LiquidityShape.CURVE
    
    # Default to SPOT if no clear pattern
    return LiquidityShape.SPOT


async def analyze_liquidity(pair_address: str) -> Optional[Dict[str, Any]]:
    """
    Perform comprehensive liquidity analysis on a DLMM pool.
    
    Combines fetch, active bin extraction, and shape classification
    into a single analysis result.
    
    Args:
        pair_address: The Meteora DLMM pool address
        
    Returns:
        Analysis result dict or None if pool not found:
        {
            "pool_address": str,
            "shape": LiquidityShape or None,
            "active_bin": dict or None,
            "bin_step": int,
            "pool_name": str or None,
        }
    """
    pool_data = await fetch_dlmm_pool(pair_address)
    
    if pool_data is None:
        return None
    
    shape = classify_liquidity_shape(pool_data)
    active_bin = get_active_bin(pool_data)
    
    return {
        "pool_address": pair_address,
        "shape": shape,
        "active_bin": active_bin,
        "bin_step": pool_data.get("bin_step"),
        "pool_name": pool_data.get("name"),
    }
