"""
Technical Indicators Module (technicals.py)
============================================

Fetches OHLCV data from GeckoTerminal and calculates technical indicators
(RSI, EMA, MACD) for trend analysis.

Indicators are implemented manually (no ta-lib dependency).
"""

import logging
import asyncio
from typing import List, Dict, Any, Optional, Tuple

import aiohttp

from config import (
    GECKOTERMINAL_API_URL,
    GECKOTERMINAL_RPM,
    API_TIMEOUT_SECONDS,
    RSI_PERIOD,
    RSI_OVERSOLD,
    RSI_OVERBOUGHT,
    EMA_SHORT_PERIOD,
    EMA_LONG_PERIOD,
    MACD_FAST,
    MACD_SLOW,
    MACD_SIGNAL,
)
from rate_limiter import rate_limit_geckoterminal

logger = logging.getLogger(__name__)


# =============================================================================
# EMA (Exponential Moving Average)
# =============================================================================

def calculate_ema(closes: List[float], period: int) -> Optional[float]:
    """
    Calculate Exponential Moving Average.
    
    EMA formula:
        EMA_today = (Close * multiplier) + (EMA_yesterday * (1 - multiplier))
        multiplier = 2 / (period + 1)
    
    Args:
        closes: List of closing prices (oldest first).
        period: EMA period (e.g., 9, 21).
    
    Returns:
        Current EMA value, or None if insufficient data.
    """
    if not closes or len(closes) < period:
        return None
    
    # Start with SMA for initial EMA value
    multiplier = 2 / (period + 1)
    ema = sum(closes[:period]) / period
    
    # Calculate EMA for remaining values
    for close in closes[period:]:
        ema = (close * multiplier) + (ema * (1 - multiplier))
    
    return ema


# =============================================================================
# RSI (Relative Strength Index)
# =============================================================================

def calculate_rsi(closes: List[float], period: int = RSI_PERIOD) -> Optional[float]:
    """
    Calculate Relative Strength Index.
    
    RSI formula:
        RSI = 100 - (100 / (1 + RS))
        RS = Average Gain / Average Loss
    
    Uses Wilder's smoothing method.
    
    Args:
        closes: List of closing prices (oldest first).
        period: RSI period (default 14).
    
    Returns:
        RSI value (0-100), or None if insufficient data.
    """
    if not closes or len(closes) < period + 1:
        return None
    
    # Calculate price changes
    gains = []
    losses = []
    
    for i in range(1, len(closes)):
        change = closes[i] - closes[i - 1]
        if change > 0:
            gains.append(change)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(change))
    
    if len(gains) < period:
        return None
    
    # Initial averages (SMA)
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    
    # Wilder's smoothing for remaining values
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    
    # Calculate RSI
    if avg_loss == 0:
        return 100.0  # No losses = max RSI
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    
    return rsi


# =============================================================================
# MACD (Moving Average Convergence Divergence)
# =============================================================================

def calculate_macd(
    closes: List[float],
    fast_period: int = MACD_FAST,
    slow_period: int = MACD_SLOW,
    signal_period: int = MACD_SIGNAL
) -> Optional[Tuple[float, float, float]]:
    """
    Calculate MACD (Moving Average Convergence Divergence).
    
    MACD formula:
        MACD Line = EMA(fast) - EMA(slow)
        Signal Line = EMA(MACD Line, signal_period)
        Histogram = MACD Line - Signal Line
    
    Args:
        closes: List of closing prices (oldest first).
        fast_period: Fast EMA period (default 12).
        slow_period: Slow EMA period (default 26).
        signal_period: Signal line EMA period (default 9).
    
    Returns:
        Tuple of (macd_line, signal_line, histogram), or None if insufficient data.
    """
    if not closes or len(closes) < slow_period + signal_period:
        return None
    
    # Calculate fast and slow EMAs
    ema_fast = calculate_ema(closes, fast_period)
    ema_slow = calculate_ema(closes, slow_period)
    
    if ema_fast is None or ema_slow is None:
        return None
    
    # Calculate MACD line values for signal line computation
    macd_values = []
    multiplier_fast = 2 / (fast_period + 1)
    multiplier_slow = 2 / (slow_period + 1)
    
    # Initialize EMAs
    ema_f = sum(closes[:fast_period]) / fast_period
    ema_s = sum(closes[:slow_period]) / slow_period
    
    # Calculate MACD values starting from slow_period
    for i in range(slow_period, len(closes)):
        # Update EMAs
        if i >= fast_period:
            idx = i
            ema_f = (closes[idx] * multiplier_fast) + (ema_f * (1 - multiplier_fast))
        if i >= slow_period:
            idx = i
            ema_s = (closes[idx] * multiplier_slow) + (ema_s * (1 - multiplier_slow))
        
        macd_values.append(ema_f - ema_s)
    
    if len(macd_values) < signal_period:
        return None
    
    # Calculate signal line (EMA of MACD values)
    signal_line = calculate_ema(macd_values, signal_period)
    
    if signal_line is None:
        return None
    
    # Current MACD line
    macd_line = ema_fast - ema_slow
    
    # Histogram
    histogram = macd_line - signal_line
    
    return (macd_line, signal_line, histogram)


# =============================================================================
# OHLCV Data Fetching (GeckoTerminal)
# =============================================================================

@rate_limit_geckoterminal
async def fetch_ohlcv(
    pool_address: str,
    timeframe: str = "minute",
    limit: int = 100
) -> Optional[List[Dict[str, Any]]]:
    """
    Fetch OHLCV candle data from GeckoTerminal API.
    
    Args:
        pool_address: Solana pool address.
        timeframe: Candle timeframe ("minute", "hour", "day").
        limit: Number of candles to fetch (max 1000).
    
    Returns:
        List of OHLCV dicts with keys: timestamp, open, high, low, close, volume.
        Returns None on error.
    """
    url = f"{GECKOTERMINAL_API_URL}/networks/solana/pools/{pool_address}/ohlcv/{timeframe}"
    params = {
        "limit": limit,
        "currency": "usd"
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                params=params,
                timeout=aiohttp.ClientTimeout(total=API_TIMEOUT_SECONDS)
            ) as response:
                if response.status != 200:
                    logger.warning(
                        f"GeckoTerminal OHLCV fetch failed: {response.status} for pool {pool_address}"
                    )
                    return None
                
                data = await response.json()
                
                # Parse GeckoTerminal response format
                ohlcv_list = data.get("data", {}).get("attributes", {}).get("ohlcv_list", [])
                
                if not ohlcv_list:
                    logger.warning(f"No OHLCV data returned for pool {pool_address}")
                    return None
                
                # Convert to standardized format
                # GeckoTerminal format: [timestamp, open, high, low, close, volume]
                candles = []
                for candle in ohlcv_list:
                    if len(candle) >= 6:
                        candles.append({
                            "timestamp": int(candle[0]),
                            "open": float(candle[1]),
                            "high": float(candle[2]),
                            "low": float(candle[3]),
                            "close": float(candle[4]),
                            "volume": float(candle[5])
                        })
                
                # Sort by timestamp ascending (oldest first)
                candles.sort(key=lambda x: x["timestamp"])
                
                logger.debug(f"Fetched {len(candles)} OHLCV candles for pool {pool_address}")
                return candles
                
    except asyncio.TimeoutError:
        logger.warning(f"GeckoTerminal OHLCV fetch timeout for pool {pool_address}")
        return None
    except Exception as e:
        logger.error(f"GeckoTerminal OHLCV fetch error: {e}")
        return None


# =============================================================================
# Combined Technical Signals
# =============================================================================

async def get_technical_signals(pool_address: str) -> Optional[Dict[str, Any]]:
    """
    Fetch OHLCV data and calculate all technical indicators.
    
    Calculates:
        - RSI (14 period)
        - EMA short (9 period)
        - EMA long (21 period)
        - MACD (12, 26, 9)
    
    Args:
        pool_address: Solana pool address.
    
    Returns:
        Dict with indicator values and trend assessment, or None on failure.
    """
    # Fetch OHLCV data
    ohlcv_data = await fetch_ohlcv(pool_address)
    
    if not ohlcv_data or len(ohlcv_data) < MACD_SLOW + MACD_SIGNAL:
        logger.warning(
            f"Insufficient OHLCV data for technical analysis: "
            f"got {len(ohlcv_data) if ohlcv_data else 0} candles, "
            f"need {MACD_SLOW + MACD_SIGNAL}"
        )
        return None
    
    # Extract closing prices
    closes = [candle["close"] for candle in ohlcv_data]
    
    # Calculate indicators
    rsi = calculate_rsi(closes, RSI_PERIOD)
    ema_short = calculate_ema(closes, EMA_SHORT_PERIOD)
    ema_long = calculate_ema(closes, EMA_LONG_PERIOD)
    macd_result = calculate_macd(closes, MACD_FAST, MACD_SLOW, MACD_SIGNAL)
    
    # Validate all indicators calculated successfully
    if rsi is None or ema_short is None or ema_long is None or macd_result is None:
        logger.warning(f"Failed to calculate one or more indicators for pool {pool_address}")
        return None
    
    macd_line, signal_line, histogram = macd_result
    
    # Determine trend
    trend = _determine_trend(rsi, ema_short, ema_long, histogram)
    
    return {
        "rsi": rsi,
        "ema_short": ema_short,
        "ema_long": ema_long,
        "macd": macd_line,
        "signal": signal_line,
        "histogram": histogram,
        "trend": trend,
        "rsi_oversold": rsi < RSI_OVERSOLD,
        "rsi_overbought": rsi > RSI_OVERBOUGHT,
        "ema_bullish": ema_short > ema_long,
        "macd_bullish": histogram > 0,
    }


def _determine_trend(
    rsi: float,
    ema_short: float,
    ema_long: float,
    histogram: float
) -> str:
    """
    Determine overall trend based on indicator values.
    
    Bullish criteria (need 2 of 3):
        - RSI > 50
        - EMA short > EMA long
        - MACD histogram > 0
    
    Args:
        rsi: RSI value (0-100).
        ema_short: Short-term EMA.
        ema_long: Long-term EMA.
        histogram: MACD histogram value.
    
    Returns:
        "bullish", "bearish", or "neutral".
    """
    bullish_signals = 0
    bearish_signals = 0
    
    # RSI signal
    if rsi > 50:
        bullish_signals += 1
    elif rsi < 50:
        bearish_signals += 1
    
    # EMA signal
    if ema_short > ema_long:
        bullish_signals += 1
    elif ema_short < ema_long:
        bearish_signals += 1
    
    # MACD signal
    if histogram > 0:
        bullish_signals += 1
    elif histogram < 0:
        bearish_signals += 1
    
    # Determine trend
    if bullish_signals >= 2:
        return "bullish"
    elif bearish_signals >= 2:
        return "bearish"
    else:
        return "neutral"
