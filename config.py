"""
Centralized configuration for PM-Predict bot.

This module defines all thresholds, API rate limits, and endpoint configurations.
API keys are loaded from environment variables via .env file.
"""

import os

# ============================================================================
# SECURITY & VALIDATION THRESHOLDS
# ============================================================================

# Price change thresholds
MAX_1H_PRICE_CHANGE_PERCENT = 50  # >50% pump in 1h = late entry, filter out
MIN_1H_PRICE_CHANGE_PERCENT = 0.1  # Minimum discernible price movement

# Holder concentration analysis
MAX_TOP10_HOLDER_PERCENT = 50  # >50% in top 10 holders = danger signal
MIN_HOLDER_COUNT = 100  # Tokens with <100 holders = high risk
MAX_TOP_HOLDER_PERCENT = 30  # Single holder >30% = extreme concentration risk

# Liquidity requirements
MIN_LIQUIDITY_USD = 5000  # Minimum pool liquidity to consider
MAX_LIQUIDITY_USD = 1_000_000  # Suspiciously high liquidity (potential rug)

# Token age requirements
MAX_TOKEN_AGE_HOURS = 24  # Tokens older than 24h are less risky
MIN_TOKEN_AGE_MINUTES = 5  # Ignore tokens created less than 5 minutes ago (noise)

# Daily alert limits
MAX_ALERTS_PER_DAY = 3  # Maximum high-quality alerts per day
ALERT_RESET_HOUR = 0  # Reset alert counter at midnight UTC

# ============================================================================
# SCORING THRESHOLDS
# ============================================================================

# Composite score thresholds
MIN_COMPOSITE_SCORE = 70  # Minimum composite score to alert
MIN_INDIVIDUAL_SCORE = 40  # Minimum score for each dimension

# Score weights (must sum to 1.0)
SCORE_WEIGHTS = {
    "safety": 0.35,      # Shield results (rugcheck, holders, honeypot)
    "timing": 0.25,      # Pump phase (EARLY/LATE classification)
    "momentum": 0.20,    # Price velocity and buy/sell ratio
    "relevance": 0.20    # LLM relevance and authenticity analysis
}

# ============================================================================
# API RATE LIMITS (requests per minute)
# ============================================================================

DEXSCREENER_RPM = 30  # DexScreener free tier: 300 req/10 minutes
GEMINI_RPM = 60  # Gemini: 60 requests per minute default
RUGCHECK_RPM = 10  # RugCheck: Conservative limit
SOLANA_RPC_RPM = 20  # Solana RPC: Conservative for shared endpoints
GECKOTERMINAL_RPM = 30  # GeckoTerminal free tier (no API key needed)
METEORA_RPM = 30  # Meteora DLMM API

# ============================================================================
# SOLANA RPC ENDPOINTS
# ============================================================================

# Primary RPC (Helius is recommended for stability)
HELIUS_API_KEY = os.getenv("HELIUS_API_KEY", "")
if HELIUS_API_KEY:
    SOLANA_RPC_URL = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"
    WSS_ENDPOINT = f"wss://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"
else:
    # Fallback to public RPC (rate limited)
    SOLANA_RPC_URL = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
    WSS_ENDPOINT = os.getenv("WSS_ENDPOINT", "wss://api.mainnet-beta.solana.com")

# ============================================================================
# EXTERNAL API ENDPOINTS
# ============================================================================

# GeckoTerminal (FREE - no key needed!)
GECKOTERMINAL_API_URL = "https://api.geckoterminal.com/api/v2"

# Meteora DLMM
METEORA_API_URL = "https://dlmm-api.meteora.ag"

# ============================================================================
# API KEYS (from environment variables)
# ============================================================================

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# ============================================================================
# FEATURE FLAGS
# ============================================================================

# Enable/disable dry-run mode
DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"

# Enable verbose logging
VERBOSE_LOGGING = os.getenv("VERBOSE_LOGGING", "false").lower() == "true"

# Use mock data for testing
USE_MOCK_DATA = os.getenv("USE_MOCK_DATA", "false").lower() == "true"

# Advanced feature flags (graceful degradation)
ENABLE_CABAL_TRACING = True
ENABLE_TECHNICALS = True
ENABLE_LIQUIDITY_ANALYSIS = True

# ============================================================================
# CABAL DETECTION THRESHOLDS
# ============================================================================

CABAL_TRACE_TIMEOUT_SECONDS = 5
CABAL_TOP_HOLDERS_LIMIT = 5  # Only trace top N holders
CABAL_COMMON_FUNDER_THRESHOLD = 3  # Min holders from same funder = DANGER
CABAL_FUNDING_LOOKBACK_HOURS = 24

# ============================================================================
# TECHNICAL INDICATORS THRESHOLDS
# ============================================================================

RSI_PERIOD = 14
RSI_OVERSOLD = 30
RSI_OVERBOUGHT = 70
EMA_SHORT_PERIOD = 9
EMA_LONG_PERIOD = 21
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9

# ============================================================================
# LIQUIDITY ANALYSIS THRESHOLDS
# ============================================================================

MIN_ACTIVE_BIN_DEPTH_USD = 1000

# ============================================================================
# SOLANA PROGRAM IDs (for WebSocket subscriptions)
# ============================================================================

RAYDIUM_PROGRAM_ID = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"
PUMP_FUN_PROGRAM_ID = "6EF8rQNxjNDoERZkwPost5FDE7vaKc27NSMqRyAZLt4e"

# ============================================================================
# TIMEOUTS & RETRIES
# ============================================================================

API_TIMEOUT_SECONDS = 10  # Timeout for HTTP requests
MAX_RETRIES = 3  # Maximum retries for API calls
RETRY_BACKOFF_FACTOR = 2  # Exponential backoff multiplier

# ============================================================================
# VALIDATION & CHECKS
# ============================================================================

def validate_config():
    """Validate that required configuration is set."""
    errors = []
    
    if not GEMINI_API_KEY:
        errors.append("GEMINI_API_KEY environment variable not set")
    
    if not TELEGRAM_BOT_TOKEN:
        errors.append("TELEGRAM_BOT_TOKEN environment variable not set")
    
    if not TELEGRAM_CHAT_ID:
        errors.append("TELEGRAM_CHAT_ID environment variable not set")
    
    if not HELIUS_API_KEY:
        print("[WARNING] HELIUS_API_KEY not set, using public RPC (rate limited)")
    
    return errors


if __name__ == "__main__":
    # Print configuration when run directly
    print("PM-Predict Configuration Summary")
    print("=" * 60)
    print()
    print("Thresholds:")
    print(f"  MAX_1H_PRICE_CHANGE_PERCENT: {MAX_1H_PRICE_CHANGE_PERCENT}%")
    print(f"  MAX_TOP10_HOLDER_PERCENT: {MAX_TOP10_HOLDER_PERCENT}%")
    print(f"  MIN_HOLDER_COUNT: {MIN_HOLDER_COUNT}")
    print(f"  MIN_LIQUIDITY_USD: ${MIN_LIQUIDITY_USD:,}")
    print(f"  MAX_TOKEN_AGE_HOURS: {MAX_TOKEN_AGE_HOURS}")
    print(f"  MAX_ALERTS_PER_DAY: {MAX_ALERTS_PER_DAY}")
    print()
    print("API Rate Limits (req/min):")
    print(f"  DexScreener: {DEXSCREENER_RPM}")
    print(f"  Gemini: {GEMINI_RPM}")
    print(f"  RugCheck: {RUGCHECK_RPM}")
    print(f"  Solana RPC: {SOLANA_RPC_RPM}")
    print()
    print("API Keys Status:")
    print(f"  GEMINI_API_KEY: {'SET' if GEMINI_API_KEY else 'NOT SET'}")
    print(f"  HELIUS_API_KEY: {'SET' if HELIUS_API_KEY else 'NOT SET'}")
    print(f"  TELEGRAM_BOT_TOKEN: {'SET' if TELEGRAM_BOT_TOKEN else 'NOT SET'}")
    print(f"  TELEGRAM_CHAT_ID: {'SET' if TELEGRAM_CHAT_ID else 'NOT SET'}")
    print()
    print("RPC Configuration:")
    print(f"  SOLANA_RPC_URL: {SOLANA_RPC_URL[:60]}...")
    print(f"  WSS_ENDPOINT: {WSS_ENDPOINT[:60]}...")
    print()
    
    errors = validate_config()
    if errors:
        print("Configuration Errors:")
        for error in errors:
            print(f"  - {error}")
    else:
        print("[OK] All required configuration is set")
