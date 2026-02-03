"""
Tests for config.py - Verify API endpoints and thresholds are properly configured.
"""

import pytest
import config


class TestGeckoTerminalConfig:
    """Test GeckoTerminal configuration."""

    def test_geckoterminal_config_exists(self):
        """Verify GeckoTerminal API URL is configured."""
        assert hasattr(config, "GECKOTERMINAL_API_URL")
        assert config.GECKOTERMINAL_API_URL == "https://api.geckoterminal.com/api/v2"

    def test_geckoterminal_rpm_configured(self):
        """Verify GeckoTerminal rate limit is configured."""
        assert hasattr(config, "GECKOTERMINAL_RPM")
        assert config.GECKOTERMINAL_RPM == 30


class TestMeteoraDLMMConfig:
    """Test Meteora DLMM configuration."""

    def test_meteora_config_exists(self):
        """Verify Meteora API URL is configured."""
        assert hasattr(config, "METEORA_API_URL")
        assert config.METEORA_API_URL == "https://dlmm-api.meteora.ag"

    def test_meteora_rpm_configured(self):
        """Verify Meteora rate limit is configured."""
        assert hasattr(config, "METEORA_RPM")
        assert config.METEORA_RPM == 30


class TestTechnicalIndicatorThresholds:
    """Test technical indicator threshold configuration."""

    def test_rsi_period_configured(self):
        """Verify RSI period is configured."""
        assert hasattr(config, "RSI_PERIOD")
        assert config.RSI_PERIOD == 14

    def test_rsi_oversold_threshold(self):
        """Verify RSI oversold threshold."""
        assert hasattr(config, "RSI_OVERSOLD")
        assert config.RSI_OVERSOLD == 30

    def test_rsi_overbought_threshold(self):
        """Verify RSI overbought threshold."""
        assert hasattr(config, "RSI_OVERBOUGHT")
        assert config.RSI_OVERBOUGHT == 70

    def test_ema_periods_configured(self):
        """Verify EMA short and long periods are configured."""
        assert hasattr(config, "EMA_SHORT_PERIOD")
        assert config.EMA_SHORT_PERIOD == 9
        assert hasattr(config, "EMA_LONG_PERIOD")
        assert config.EMA_LONG_PERIOD == 21

    def test_macd_periods_configured(self):
        """Verify MACD periods are configured."""
        assert hasattr(config, "MACD_FAST")
        assert config.MACD_FAST == 12
        assert hasattr(config, "MACD_SLOW")
        assert config.MACD_SLOW == 26
        assert hasattr(config, "MACD_SIGNAL")
        assert config.MACD_SIGNAL == 9

    def test_indicator_thresholds_valid(self):
        """Verify indicator thresholds are reasonable values."""
        # RSI should be 0-100
        assert 0 <= config.RSI_OVERSOLD <= 100
        assert 0 <= config.RSI_OVERBOUGHT <= 100
        assert config.RSI_OVERSOLD < config.RSI_OVERBOUGHT

        # EMA periods should be positive
        assert config.EMA_SHORT_PERIOD > 0
        assert config.EMA_LONG_PERIOD > 0
        assert config.EMA_SHORT_PERIOD < config.EMA_LONG_PERIOD

        # MACD periods should be positive and ordered
        assert config.MACD_FAST > 0
        assert config.MACD_SLOW > 0
        assert config.MACD_SIGNAL > 0
        assert config.MACD_FAST < config.MACD_SLOW


class TestCabalDetectionThresholds:
    """Test cabal detection configuration."""

    def test_cabal_trace_timeout_configured(self):
        """Verify cabal trace timeout is configured."""
        assert hasattr(config, "CABAL_TRACE_TIMEOUT_SECONDS")
        assert config.CABAL_TRACE_TIMEOUT_SECONDS == 5

    def test_cabal_top_holders_limit_configured(self):
        """Verify cabal top holders limit is configured."""
        assert hasattr(config, "CABAL_TOP_HOLDERS_LIMIT")
        assert config.CABAL_TOP_HOLDERS_LIMIT == 5

    def test_cabal_common_funder_threshold(self):
        """Verify cabal common funder threshold is configured."""
        assert hasattr(config, "CABAL_COMMON_FUNDER_THRESHOLD")
        assert config.CABAL_COMMON_FUNDER_THRESHOLD == 3

    def test_cabal_funding_lookback_hours(self):
        """Verify cabal funding lookback period is configured."""
        assert hasattr(config, "CABAL_FUNDING_LOOKBACK_HOURS")
        assert config.CABAL_FUNDING_LOOKBACK_HOURS == 24


class TestLiquidityThresholds:
    """Test liquidity analysis configuration."""

    def test_min_active_bin_depth_usd_configured(self):
        """Verify minimum active bin depth is configured."""
        assert hasattr(config, "MIN_ACTIVE_BIN_DEPTH_USD")
        assert config.MIN_ACTIVE_BIN_DEPTH_USD == 1000


class TestFeatureFlags:
    """Test advanced feature flags."""

    def test_enable_cabal_tracing_flag(self):
        """Verify cabal tracing feature flag exists."""
        assert hasattr(config, "ENABLE_CABAL_TRACING")
        assert isinstance(config.ENABLE_CABAL_TRACING, bool)

    def test_enable_technicals_flag(self):
        """Verify technical indicators feature flag exists."""
        assert hasattr(config, "ENABLE_TECHNICALS")
        assert isinstance(config.ENABLE_TECHNICALS, bool)

    def test_enable_liquidity_analysis_flag(self):
        """Verify liquidity analysis feature flag exists."""
        assert hasattr(config, "ENABLE_LIQUIDITY_ANALYSIS")
        assert isinstance(config.ENABLE_LIQUIDITY_ANALYSIS, bool)
