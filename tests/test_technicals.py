"""
Tests for Technical Indicators Module (technicals.py).

Tests RSI, EMA, MACD calculations and GeckoTerminal OHLCV fetching.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from typing import List, Dict, Any


# =============================================================================
# TEST FIXTURES
# =============================================================================

@pytest.fixture
def sample_ohlcv_data() -> List[Dict[str, Any]]:
    """
    Sample OHLCV data for indicator calculations.
    
    40 candles with varying prices for testing RSI, EMA, MACD.
    (Need at least 35 for MACD: slow_period 26 + signal_period 9)
    """
    # Create realistic price data with ups and downs
    prices = [
        100.0, 102.0, 101.5, 103.0, 104.5,
        103.8, 105.2, 106.0, 104.5, 107.0,
        108.5, 107.2, 109.0, 110.5, 109.8,
        111.0, 112.5, 111.8, 113.0, 114.5,
        115.0, 114.2, 116.0, 117.5, 116.8,
        118.0, 119.5, 118.8, 120.0, 121.5,
        122.0, 121.2, 123.0, 124.5, 123.8,
        125.0, 126.5, 125.8, 127.0, 128.5
    ]
    
    ohlcv = []
    for i, close in enumerate(prices):
        ohlcv.append({
            "timestamp": 1700000000 + (i * 60),
            "open": close - 0.5,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": 10000 + (i * 100)
        })
    return ohlcv


@pytest.fixture
def trending_up_ohlcv() -> List[Dict[str, Any]]:
    """OHLCV data with clear uptrend for bullish signals."""
    prices = [100.0 + i * 2.0 for i in range(50)]  # Steady uptrend, 50 candles
    ohlcv = []
    for i, close in enumerate(prices):
        ohlcv.append({
            "timestamp": 1700000000 + (i * 60),
            "open": close - 0.5,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": 10000
        })
    return ohlcv


@pytest.fixture
def trending_down_ohlcv() -> List[Dict[str, Any]]:
    """OHLCV data with clear downtrend for bearish signals."""
    prices = [200.0 - i * 3.0 for i in range(50)]  # Steady downtrend, 50 candles
    ohlcv = []
    for i, close in enumerate(prices):
        ohlcv.append({
            "timestamp": 1700000000 + (i * 60),
            "open": close + 0.5,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": 10000
        })
    return ohlcv


@pytest.fixture
def mock_geckoterminal_response() -> Dict[str, Any]:
    """Mock GeckoTerminal OHLCV API response."""
    return {
        "data": {
            "id": "solana_pool_12345",
            "type": "ohlcv",
            "attributes": {
                "ohlcv_list": [
                    # [timestamp, open, high, low, close, volume]
                    [1700000000, "100.0", "101.0", "99.0", "100.5", "10000"],
                    [1700000060, "100.5", "102.0", "100.0", "101.5", "11000"],
                    [1700000120, "101.5", "103.0", "101.0", "102.5", "12000"],
                    [1700000180, "102.5", "104.0", "102.0", "103.5", "13000"],
                    [1700000240, "103.5", "105.0", "103.0", "104.5", "14000"],
                    [1700000300, "104.5", "106.0", "104.0", "105.5", "15000"],
                    [1700000360, "105.5", "107.0", "105.0", "106.5", "16000"],
                    [1700000420, "106.5", "108.0", "106.0", "107.5", "17000"],
                    [1700000480, "107.5", "109.0", "107.0", "108.5", "18000"],
                    [1700000540, "108.5", "110.0", "108.0", "109.5", "19000"],
                    [1700000600, "109.5", "111.0", "109.0", "110.5", "20000"],
                    [1700000660, "110.5", "112.0", "110.0", "111.5", "21000"],
                    [1700000720, "111.5", "113.0", "111.0", "112.5", "22000"],
                    [1700000780, "112.5", "114.0", "112.0", "113.5", "23000"],
                    [1700000840, "113.5", "115.0", "113.0", "114.5", "24000"],
                ]
            }
        }
    }


# =============================================================================
# UNIT TESTS: calculate_ema
# =============================================================================

class TestCalculateEMA:
    """Tests for EMA (Exponential Moving Average) calculation."""

    def test_ema_basic(self, sample_ohlcv_data):
        """Test basic EMA calculation returns valid value."""
        from technicals import calculate_ema
        
        closes = [candle["close"] for candle in sample_ohlcv_data]
        ema = calculate_ema(closes, period=9)
        
        assert ema is not None
        assert isinstance(ema, float)
        assert ema > 0

    def test_ema_short_vs_long(self, sample_ohlcv_data):
        """Test shorter EMA reacts faster (closer to recent prices)."""
        from technicals import calculate_ema
        
        closes = [candle["close"] for candle in sample_ohlcv_data]
        ema_short = calculate_ema(closes, period=5)
        ema_long = calculate_ema(closes, period=20)
        
        # For uptrending data, short EMA should be closer to current price
        current_price = closes[-1]
        assert abs(ema_short - current_price) < abs(ema_long - current_price)

    def test_ema_insufficient_data(self):
        """Test EMA returns None when insufficient data."""
        from technicals import calculate_ema
        
        closes = [100.0, 101.0, 102.0]  # Only 3 data points
        ema = calculate_ema(closes, period=14)
        
        assert ema is None

    def test_ema_empty_list(self):
        """Test EMA handles empty list gracefully."""
        from technicals import calculate_ema
        
        ema = calculate_ema([], period=9)
        assert ema is None


# =============================================================================
# UNIT TESTS: calculate_rsi
# =============================================================================

class TestCalculateRSI:
    """Tests for RSI (Relative Strength Index) calculation."""

    def test_rsi_range(self, sample_ohlcv_data):
        """Test RSI is always between 0 and 100."""
        from technicals import calculate_rsi
        
        closes = [candle["close"] for candle in sample_ohlcv_data]
        rsi = calculate_rsi(closes, period=14)
        
        assert rsi is not None
        assert 0 <= rsi <= 100

    def test_rsi_uptrend(self, trending_up_ohlcv):
        """Test RSI > 50 for uptrending data."""
        from technicals import calculate_rsi
        
        closes = [candle["close"] for candle in trending_up_ohlcv]
        rsi = calculate_rsi(closes, period=14)
        
        assert rsi is not None
        assert rsi > 50  # Strong uptrend should have RSI > 50

    def test_rsi_downtrend(self, trending_down_ohlcv):
        """Test RSI < 50 for downtrending data."""
        from technicals import calculate_rsi
        
        closes = [candle["close"] for candle in trending_down_ohlcv]
        rsi = calculate_rsi(closes, period=14)
        
        assert rsi is not None
        assert rsi < 50  # Strong downtrend should have RSI < 50

    def test_rsi_insufficient_data(self):
        """Test RSI returns None when insufficient data."""
        from technicals import calculate_rsi
        
        closes = [100.0, 101.0, 102.0]  # Only 3 data points
        rsi = calculate_rsi(closes, period=14)
        
        assert rsi is None

    def test_rsi_empty_list(self):
        """Test RSI handles empty list gracefully."""
        from technicals import calculate_rsi
        
        rsi = calculate_rsi([], period=14)
        assert rsi is None


# =============================================================================
# UNIT TESTS: calculate_macd
# =============================================================================

class TestCalculateMACD:
    """Tests for MACD (Moving Average Convergence Divergence) calculation."""

    def test_macd_returns_tuple(self, sample_ohlcv_data):
        """Test MACD returns tuple of (macd_line, signal_line, histogram)."""
        from technicals import calculate_macd
        
        closes = [candle["close"] for candle in sample_ohlcv_data]
        result = calculate_macd(closes)
        
        assert result is not None
        assert isinstance(result, tuple)
        assert len(result) == 3
        
        macd_line, signal_line, histogram = result
        assert isinstance(macd_line, float)
        assert isinstance(signal_line, float)
        assert isinstance(histogram, float)

    def test_macd_histogram_calculation(self, sample_ohlcv_data):
        """Test histogram equals MACD line minus signal line."""
        from technicals import calculate_macd
        
        closes = [candle["close"] for candle in sample_ohlcv_data]
        macd_line, signal_line, histogram = calculate_macd(closes)
        
        # Allow small floating point tolerance
        assert abs(histogram - (macd_line - signal_line)) < 0.0001

    def test_macd_uptrend(self, trending_up_ohlcv):
        """Test MACD line > signal line in strong uptrend (bullish)."""
        from technicals import calculate_macd
        
        closes = [candle["close"] for candle in trending_up_ohlcv]
        macd_line, signal_line, histogram = calculate_macd(closes)
        
        # In strong uptrend, histogram should be positive
        assert histogram > 0

    def test_macd_insufficient_data(self):
        """Test MACD returns None when insufficient data."""
        from technicals import calculate_macd
        
        closes = [100.0, 101.0, 102.0]  # Only 3 data points
        result = calculate_macd(closes)
        
        assert result is None

    def test_macd_empty_list(self):
        """Test MACD handles empty list gracefully."""
        from technicals import calculate_macd
        
        result = calculate_macd([])
        assert result is None


# =============================================================================
# UNIT TESTS: fetch_ohlcv
# =============================================================================

class TestFetchOHLCV:
    """Tests for GeckoTerminal OHLCV fetching."""

    @pytest.mark.asyncio
    async def test_fetch_ohlcv_success(self, mock_geckoterminal_response):
        """Test successful OHLCV fetch from GeckoTerminal."""
        from technicals import fetch_ohlcv
        
        with patch("aiohttp.ClientSession") as mock_session:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value=mock_geckoterminal_response)
            mock_response.__aenter__ = AsyncMock(return_value=mock_response)
            mock_response.__aexit__ = AsyncMock(return_value=None)
            
            mock_ctx = MagicMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_response)
            mock_ctx.__aexit__ = AsyncMock(return_value=None)
            
            mock_session_instance = MagicMock()
            mock_session_instance.get = MagicMock(return_value=mock_ctx)
            mock_session_instance.__aenter__ = AsyncMock(return_value=mock_session_instance)
            mock_session_instance.__aexit__ = AsyncMock(return_value=None)
            mock_session.return_value = mock_session_instance
            
            result = await fetch_ohlcv("test_pool_address")
            
            assert result is not None
            assert isinstance(result, list)
            assert len(result) > 0
            assert "close" in result[0]

    @pytest.mark.asyncio
    async def test_fetch_ohlcv_api_error(self):
        """Test OHLCV fetch handles API errors gracefully."""
        from technicals import fetch_ohlcv
        
        with patch("aiohttp.ClientSession") as mock_session:
            mock_response = AsyncMock()
            mock_response.status = 500
            mock_response.__aenter__ = AsyncMock(return_value=mock_response)
            mock_response.__aexit__ = AsyncMock(return_value=None)
            
            mock_ctx = MagicMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_response)
            mock_ctx.__aexit__ = AsyncMock(return_value=None)
            
            mock_session_instance = MagicMock()
            mock_session_instance.get = MagicMock(return_value=mock_ctx)
            mock_session_instance.__aenter__ = AsyncMock(return_value=mock_session_instance)
            mock_session_instance.__aexit__ = AsyncMock(return_value=None)
            mock_session.return_value = mock_session_instance
            
            result = await fetch_ohlcv("test_pool_address")
            
            assert result is None

    @pytest.mark.asyncio
    async def test_fetch_ohlcv_network_error(self):
        """Test OHLCV fetch handles network errors gracefully."""
        from technicals import fetch_ohlcv
        
        with patch("aiohttp.ClientSession") as mock_session:
            mock_session_instance = MagicMock()
            mock_session_instance.get = MagicMock(side_effect=Exception("Network error"))
            mock_session_instance.__aenter__ = AsyncMock(return_value=mock_session_instance)
            mock_session_instance.__aexit__ = AsyncMock(return_value=None)
            mock_session.return_value = mock_session_instance
            
            result = await fetch_ohlcv("test_pool_address")
            
            assert result is None


# =============================================================================
# INTEGRATION TESTS: get_technical_signals
# =============================================================================

class TestGetTechnicalSignals:
    """Tests for combined technical signals function."""

    @pytest.mark.asyncio
    async def test_get_technical_signals_bullish(self, trending_up_ohlcv, mock_geckoterminal_response):
        """Test bullish signals are detected correctly."""
        from technicals import get_technical_signals
        
        with patch("technicals.fetch_ohlcv", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = trending_up_ohlcv
            
            signals = await get_technical_signals("test_pool_address")
            
            assert signals is not None
            assert "rsi" in signals
            assert "ema_short" in signals
            assert "ema_long" in signals
            assert "macd" in signals
            assert "signal" in signals
            assert "histogram" in signals
            assert "trend" in signals

    @pytest.mark.asyncio
    async def test_get_technical_signals_trend_detection(self, trending_up_ohlcv, trending_down_ohlcv):
        """Test trend detection (bullish vs bearish)."""
        from technicals import get_technical_signals
        
        # Test bullish trend
        with patch("technicals.fetch_ohlcv", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = trending_up_ohlcv
            signals = await get_technical_signals("test_pool_address")
            assert signals["trend"] == "bullish"
        
        # Test bearish trend
        with patch("technicals.fetch_ohlcv", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = trending_down_ohlcv
            signals = await get_technical_signals("test_pool_address")
            assert signals["trend"] == "bearish"

    @pytest.mark.asyncio
    async def test_get_technical_signals_fetch_failure(self):
        """Test graceful degradation when OHLCV fetch fails."""
        from technicals import get_technical_signals
        
        with patch("technicals.fetch_ohlcv", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = None
            
            signals = await get_technical_signals("test_pool_address")
            
            assert signals is None

    @pytest.mark.asyncio
    async def test_get_technical_signals_insufficient_data(self):
        """Test handling of insufficient OHLCV data."""
        from technicals import get_technical_signals
        
        # Only 5 candles - not enough for RSI(14)
        insufficient_data = [
            {"timestamp": 1700000000 + i * 60, "open": 100, "high": 101, "low": 99, "close": 100 + i, "volume": 1000}
            for i in range(5)
        ]
        
        with patch("technicals.fetch_ohlcv", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = insufficient_data
            
            signals = await get_technical_signals("test_pool_address")
            
            # Should return None or partial signals when data insufficient
            assert signals is None or signals.get("rsi") is None


# =============================================================================
# EDGE CASE TESTS
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_ema_single_value(self):
        """Test EMA with single value."""
        from technicals import calculate_ema
        
        ema = calculate_ema([100.0], period=1)
        # With period 1, EMA of single value should be that value
        assert ema == 100.0 or ema is None  # Depends on implementation

    def test_rsi_all_gains(self):
        """Test RSI when all price changes are positive."""
        from technicals import calculate_rsi
        
        # Prices only go up
        closes = [100.0 + i for i in range(20)]
        rsi = calculate_rsi(closes, period=14)
        
        if rsi is not None:
            assert rsi >= 90  # Should be very high (close to 100)

    def test_rsi_all_losses(self):
        """Test RSI when all price changes are negative."""
        from technicals import calculate_rsi
        
        # Prices only go down
        closes = [200.0 - i for i in range(20)]
        rsi = calculate_rsi(closes, period=14)
        
        if rsi is not None:
            assert rsi <= 10  # Should be very low (close to 0)

    def test_macd_flat_prices(self):
        """Test MACD with flat price movement."""
        from technicals import calculate_macd
        
        closes = [100.0] * 50  # Flat prices (need 35+ for MACD)
        result = calculate_macd(closes)
        
        if result is not None:
            macd_line, signal_line, histogram = result
            # All EMAs should be equal with flat prices
            assert abs(histogram) < 0.01
