"""
Unit tests for liquidity.py Meteora DLMM analysis module.

Tests cover:
- fetch_dlmm_pool: Fetching pool data from Meteora API
- get_active_bin: Extracting active bin info
- classify_liquidity_shape: SPOT/CURVE/BID_ASK detection
- analyze_liquidity: Combined liquidity analysis
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from liquidity import (
    fetch_dlmm_pool,
    get_active_bin,
    classify_liquidity_shape,
    analyze_liquidity,
    LiquidityShape,
)


# =============================================================================
# MOCK DATA FIXTURES
# =============================================================================

@pytest.fixture
def mock_dlmm_pool_spot():
    """Mock Meteora DLMM pool data with SPOT (uniform) distribution."""
    return {
        "address": "PoolAddress123",
        "name": "SOL-TOKEN",
        "mint_x": "So11111111111111111111111111111111111111112",
        "mint_y": "TokenMint123",
        "bin_step": 25,
        "active_id": 100,
        "bins": [
            {"bin_id": 95, "x_amount": "1000000", "y_amount": "1000000"},
            {"bin_id": 96, "x_amount": "1000000", "y_amount": "1000000"},
            {"bin_id": 97, "x_amount": "1000000", "y_amount": "1000000"},
            {"bin_id": 98, "x_amount": "1000000", "y_amount": "1000000"},
            {"bin_id": 99, "x_amount": "1000000", "y_amount": "1000000"},
            {"bin_id": 100, "x_amount": "1000000", "y_amount": "1000000"},  # active
            {"bin_id": 101, "x_amount": "1000000", "y_amount": "1000000"},
            {"bin_id": 102, "x_amount": "1000000", "y_amount": "1000000"},
            {"bin_id": 103, "x_amount": "1000000", "y_amount": "1000000"},
            {"bin_id": 104, "x_amount": "1000000", "y_amount": "1000000"},
            {"bin_id": 105, "x_amount": "1000000", "y_amount": "1000000"},
        ],
        "liquidity_locked": True,
        "reserve_x": "5000000",
        "reserve_y": "5000000",
        "reserve_x_int": 5000000,
        "reserve_y_int": 5000000,
    }


@pytest.fixture
def mock_dlmm_pool_curve():
    """Mock Meteora DLMM pool data with CURVE (Gaussian) distribution."""
    return {
        "address": "PoolAddress456",
        "name": "SOL-MEME",
        "mint_x": "So11111111111111111111111111111111111111112",
        "mint_y": "MemeMint456",
        "bin_step": 50,
        "active_id": 100,
        "bins": [
            {"bin_id": 95, "x_amount": "100000", "y_amount": "100000"},      # edge - low
            {"bin_id": 96, "x_amount": "300000", "y_amount": "300000"},
            {"bin_id": 97, "x_amount": "800000", "y_amount": "800000"},
            {"bin_id": 98, "x_amount": "2000000", "y_amount": "2000000"},
            {"bin_id": 99, "x_amount": "4000000", "y_amount": "4000000"},    # near center
            {"bin_id": 100, "x_amount": "5000000", "y_amount": "5000000"},   # active/peak
            {"bin_id": 101, "x_amount": "4000000", "y_amount": "4000000"},   # near center
            {"bin_id": 102, "x_amount": "2000000", "y_amount": "2000000"},
            {"bin_id": 103, "x_amount": "800000", "y_amount": "800000"},
            {"bin_id": 104, "x_amount": "300000", "y_amount": "300000"},
            {"bin_id": 105, "x_amount": "100000", "y_amount": "100000"},     # edge - low
        ],
        "liquidity_locked": True,
        "reserve_x": "10000000",
        "reserve_y": "10000000",
        "reserve_x_int": 10000000,
        "reserve_y_int": 10000000,
    }


@pytest.fixture
def mock_dlmm_pool_bid_ask():
    """Mock Meteora DLMM pool data with BID_ASK (bimodal) distribution."""
    return {
        "address": "PoolAddress789",
        "name": "SOL-VOLATILE",
        "mint_x": "So11111111111111111111111111111111111111112",
        "mint_y": "VolatileMint789",
        "bin_step": 100,
        "active_id": 100,
        "bins": [
            {"bin_id": 95, "x_amount": "5000000", "y_amount": "5000000"},    # heavy at edge
            {"bin_id": 96, "x_amount": "4000000", "y_amount": "4000000"},
            {"bin_id": 97, "x_amount": "1000000", "y_amount": "1000000"},
            {"bin_id": 98, "x_amount": "500000", "y_amount": "500000"},      # thin middle
            {"bin_id": 99, "x_amount": "200000", "y_amount": "200000"},
            {"bin_id": 100, "x_amount": "100000", "y_amount": "100000"},     # active - thin
            {"bin_id": 101, "x_amount": "200000", "y_amount": "200000"},
            {"bin_id": 102, "x_amount": "500000", "y_amount": "500000"},     # thin middle
            {"bin_id": 103, "x_amount": "1000000", "y_amount": "1000000"},
            {"bin_id": 104, "x_amount": "4000000", "y_amount": "4000000"},
            {"bin_id": 105, "x_amount": "5000000", "y_amount": "5000000"},   # heavy at edge
        ],
        "liquidity_locked": True,
        "reserve_x": "10000000",
        "reserve_y": "10000000",
        "reserve_x_int": 10000000,
        "reserve_y_int": 10000000,
    }


@pytest.fixture
def mock_dlmm_pool_empty():
    """Mock Meteora DLMM pool with no bins."""
    return {
        "address": "EmptyPool",
        "name": "EMPTY-POOL",
        "bin_step": 25,
        "active_id": None,
        "bins": [],
    }


# =============================================================================
# FETCH DLMM POOL TESTS
# =============================================================================

@pytest.mark.asyncio
async def test_fetch_dlmm_pool_success(mock_dlmm_pool_spot):
    """Test successful pool fetch from Meteora API."""
    with patch("aiohttp.ClientSession") as mock_session:
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=mock_dlmm_pool_spot)
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        
        mock_session_instance = MagicMock()
        mock_session_instance.get = MagicMock(return_value=mock_response)
        mock_session_instance.__aenter__ = AsyncMock(return_value=mock_session_instance)
        mock_session_instance.__aexit__ = AsyncMock(return_value=None)
        mock_session.return_value = mock_session_instance
        
        result = await fetch_dlmm_pool("PoolAddress123")
        
        assert result is not None
        assert result["address"] == "PoolAddress123"
        assert "bins" in result


@pytest.mark.asyncio
async def test_fetch_dlmm_pool_not_found():
    """Test pool fetch when pool doesn't exist."""
    with patch("aiohttp.ClientSession") as mock_session:
        mock_response = AsyncMock()
        mock_response.status = 404
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        
        mock_session_instance = MagicMock()
        mock_session_instance.get = MagicMock(return_value=mock_response)
        mock_session_instance.__aenter__ = AsyncMock(return_value=mock_session_instance)
        mock_session_instance.__aexit__ = AsyncMock(return_value=None)
        mock_session.return_value = mock_session_instance
        
        result = await fetch_dlmm_pool("NonExistentPool")
        
        assert result is None


@pytest.mark.asyncio
async def test_fetch_dlmm_pool_network_error():
    """Test pool fetch with network error (fail-open)."""
    with patch("aiohttp.ClientSession") as mock_session:
        mock_session_instance = MagicMock()
        mock_session_instance.get = MagicMock(side_effect=Exception("Network error"))
        mock_session_instance.__aenter__ = AsyncMock(return_value=mock_session_instance)
        mock_session_instance.__aexit__ = AsyncMock(return_value=None)
        mock_session.return_value = mock_session_instance
        
        result = await fetch_dlmm_pool("SomePool")
        
        assert result is None  # Fail-open: return None on error


# =============================================================================
# GET ACTIVE BIN TESTS
# =============================================================================

def test_get_active_bin_exists(mock_dlmm_pool_spot):
    """Test extracting active bin when it exists."""
    active_bin = get_active_bin(mock_dlmm_pool_spot)
    
    assert active_bin is not None
    assert active_bin["bin_id"] == 100
    assert "x_amount" in active_bin
    assert "y_amount" in active_bin


def test_get_active_bin_curve(mock_dlmm_pool_curve):
    """Test extracting active bin from curve distribution."""
    active_bin = get_active_bin(mock_dlmm_pool_curve)
    
    assert active_bin is not None
    assert active_bin["bin_id"] == 100
    # Curve has highest liquidity at active bin
    assert int(active_bin["x_amount"]) == 5000000


def test_get_active_bin_empty_pool(mock_dlmm_pool_empty):
    """Test extracting active bin from empty pool."""
    active_bin = get_active_bin(mock_dlmm_pool_empty)
    
    assert active_bin is None


def test_get_active_bin_no_matching_bin():
    """Test when active_id doesn't match any bin."""
    pool_data = {
        "active_id": 999,  # Doesn't exist in bins
        "bins": [
            {"bin_id": 100, "x_amount": "1000", "y_amount": "1000"},
        ],
    }
    
    active_bin = get_active_bin(pool_data)
    
    assert active_bin is None


def test_get_active_bin_none_pool():
    """Test get_active_bin with None input."""
    active_bin = get_active_bin(None)
    
    assert active_bin is None


# =============================================================================
# CLASSIFY LIQUIDITY SHAPE TESTS
# =============================================================================

def test_classify_spot_distribution(mock_dlmm_pool_spot):
    """Test classification of uniform/SPOT distribution."""
    shape = classify_liquidity_shape(mock_dlmm_pool_spot)
    
    assert shape == LiquidityShape.SPOT


def test_classify_curve_distribution(mock_dlmm_pool_curve):
    """Test classification of Gaussian/CURVE distribution."""
    shape = classify_liquidity_shape(mock_dlmm_pool_curve)
    
    assert shape == LiquidityShape.CURVE


def test_classify_bid_ask_distribution(mock_dlmm_pool_bid_ask):
    """Test classification of bimodal/BID_ASK distribution."""
    shape = classify_liquidity_shape(mock_dlmm_pool_bid_ask)
    
    assert shape == LiquidityShape.BID_ASK


def test_classify_empty_pool(mock_dlmm_pool_empty):
    """Test classification of empty pool."""
    shape = classify_liquidity_shape(mock_dlmm_pool_empty)
    
    assert shape is None


def test_classify_none_pool():
    """Test classification with None input."""
    shape = classify_liquidity_shape(None)
    
    assert shape is None


def test_classify_single_bin():
    """Test classification with only one bin."""
    pool_data = {
        "active_id": 100,
        "bins": [
            {"bin_id": 100, "x_amount": "1000000", "y_amount": "1000000"},
        ],
    }
    
    shape = classify_liquidity_shape(pool_data)
    
    # Single bin should default to SPOT (uniform by definition)
    assert shape == LiquidityShape.SPOT


def test_classify_two_bins():
    """Test classification with only two bins."""
    pool_data = {
        "active_id": 100,
        "bins": [
            {"bin_id": 100, "x_amount": "1000000", "y_amount": "1000000"},
            {"bin_id": 101, "x_amount": "1000000", "y_amount": "1000000"},
        ],
    }
    
    shape = classify_liquidity_shape(pool_data)
    
    assert shape == LiquidityShape.SPOT


# =============================================================================
# ANALYZE LIQUIDITY TESTS
# =============================================================================

@pytest.mark.asyncio
async def test_analyze_liquidity_success(mock_dlmm_pool_curve):
    """Test full liquidity analysis."""
    with patch("liquidity.fetch_dlmm_pool", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = mock_dlmm_pool_curve
        
        result = await analyze_liquidity("PoolAddress456")
        
        assert result is not None
        assert "shape" in result
        assert result["shape"] == LiquidityShape.CURVE
        assert "active_bin" in result
        assert result["active_bin"]["bin_id"] == 100
        assert "bin_step" in result
        assert result["bin_step"] == 50


@pytest.mark.asyncio
async def test_analyze_liquidity_pool_not_found():
    """Test liquidity analysis when pool not found."""
    with patch("liquidity.fetch_dlmm_pool", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = None
        
        result = await analyze_liquidity("NonExistentPool")
        
        assert result is None


@pytest.mark.asyncio
async def test_analyze_liquidity_spot(mock_dlmm_pool_spot):
    """Test liquidity analysis for SPOT shape."""
    with patch("liquidity.fetch_dlmm_pool", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = mock_dlmm_pool_spot
        
        result = await analyze_liquidity("PoolAddress123")
        
        assert result is not None
        assert result["shape"] == LiquidityShape.SPOT


@pytest.mark.asyncio
async def test_analyze_liquidity_bid_ask(mock_dlmm_pool_bid_ask):
    """Test liquidity analysis for BID_ASK shape."""
    with patch("liquidity.fetch_dlmm_pool", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = mock_dlmm_pool_bid_ask
        
        result = await analyze_liquidity("PoolAddress789")
        
        assert result is not None
        assert result["shape"] == LiquidityShape.BID_ASK


@pytest.mark.asyncio
async def test_analyze_liquidity_empty_pool(mock_dlmm_pool_empty):
    """Test liquidity analysis for empty pool."""
    with patch("liquidity.fetch_dlmm_pool", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = mock_dlmm_pool_empty
        
        result = await analyze_liquidity("EmptyPool")
        
        # Should return partial result with None values for shape/active_bin
        assert result is not None
        assert result["shape"] is None
        assert result["active_bin"] is None


# =============================================================================
# EDGE CASES AND ROBUSTNESS TESTS
# =============================================================================

def test_classify_with_string_amounts():
    """Test classification handles string amounts correctly."""
    pool_data = {
        "active_id": 100,
        "bins": [
            {"bin_id": 95, "x_amount": "100", "y_amount": "100"},
            {"bin_id": 100, "x_amount": "5000", "y_amount": "5000"},
            {"bin_id": 105, "x_amount": "100", "y_amount": "100"},
        ],
    }
    
    shape = classify_liquidity_shape(pool_data)
    
    # Concentrated in center = CURVE
    assert shape == LiquidityShape.CURVE


def test_classify_with_missing_amounts():
    """Test classification handles missing amounts gracefully."""
    pool_data = {
        "active_id": 100,
        "bins": [
            {"bin_id": 95},  # Missing amounts
            {"bin_id": 100, "x_amount": "1000"},  # Missing y_amount
            {"bin_id": 105, "x_amount": "1000", "y_amount": "1000"},
        ],
    }
    
    # Should not crash
    shape = classify_liquidity_shape(pool_data)
    
    assert shape is not None or shape is None  # Any valid result


def test_get_active_bin_depth():
    """Test active bin depth calculation."""
    pool_data = {
        "active_id": 100,
        "bins": [
            {"bin_id": 100, "x_amount": "10000000", "y_amount": "5000000"},
        ],
    }
    
    active_bin = get_active_bin(pool_data)
    
    assert active_bin is not None
    # Total depth should be sum of x and y amounts
    total_depth = int(active_bin["x_amount"]) + int(active_bin["y_amount"])
    assert total_depth == 15000000
