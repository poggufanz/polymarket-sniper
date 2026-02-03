# PM-Predict

**Polymarket Alpha Scanner** - Real-time Solana token detection based on Polymarket event narratives.

PM-Predict is an async event-driven bot that monitors Solana WebSocket feeds for new token deployments (Raydium/Pump.fun), matches them against trending Polymarket events, validates them through multi-tier security checks, and sends high-quality Telegram alerts when alpha opportunities are detected.

---

## Features

- **Real-time Token Detection**: WebSocket monitoring of Raydium and Pump.fun program logs
- **Narrative Matching**: Extracts keywords from Polymarket events and filters tokens by relevance
- **Multi-Tier Security Validation**:
  - Tier 0: DexScreener data fetch + liquidity check
  - Tier 1: Momentum analysis (EARLY/LATE phase, staleness detection)
  - Tier 2: Shield security (RugCheck, holder concentration, honeypot, bundled TX)
  - Tier 3: Brain LLM analysis (relevance and authenticity scoring)
- **Composite Scoring**: 4-dimensional score (Safety 35%, Timing 25%, Momentum 20%, Relevance 20%)
- **Alert Rate Limiting**: Maximum 3 high-quality alerts per day
- **Duplicate Prevention**: Tracks tokens alerted on, prevents same-day re-alerts

---

## Architecture

```
Polymarket Events → Keywords → WebSocket Filter → Token Event
  ↓
  → Tier 0: DexScreener data fetch
  → Tier 1: Momentum check (EARLY/LATE, staleness)
  → Tier 2: Shield security check (multi-factor validation)
  → Tier 3: Brain LLM analysis (gatekept - only if tiers 1-2 pass)
  → Scoring: Composite score calculation
  → Alert: State limiting + Telegram notification
```

---

## Prerequisites

- **Python 3.9+**
- **API Keys**:
  - `GEMINI_API_KEY` - Required for LLM analysis ([Get key](https://ai.google.dev/))
  - `TELEGRAM_BOT_TOKEN` - Required for alerts ([Create bot](https://t.me/botfather))
  - `TELEGRAM_CHAT_ID` - Your chat ID ([Get chat ID](https://t.me/userinfobot))
  - `HELIUS_API_KEY` - Optional but recommended for stable RPC ([Get key](https://helius.dev))

---

## Installation

### 1. Clone Repository

```bash
git clone <repository-url>
cd pm-predict
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Environment

Copy `.env.example` to `.env` and fill in your API keys:

```bash
cp .env.example .env
```

Edit `.env`:

```ini
# Required API Keys
GEMINI_API_KEY=your_gemini_api_key_here
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
TELEGRAM_CHAT_ID=your_telegram_chat_id_here

# Optional (recommended for stability)
HELIUS_API_KEY=your_helius_api_key_here

# Optional Feature Flags
DRY_RUN=false              # Set to 'true' to test without sending real alerts
VERBOSE_LOGGING=false      # Set to 'true' for detailed logs
```

---

## Configuration

All thresholds and settings are centralized in `config.py`:

### Security Thresholds
- `MAX_1H_PRICE_CHANGE_PERCENT = 50` - Tokens above this are filtered as LATE entry
- `MAX_TOP10_HOLDER_PERCENT = 50` - Top 10 holder concentration danger threshold
- `MIN_LIQUIDITY_USD = 5000` - Minimum pool liquidity required
- `MAX_TOKEN_AGE_HOURS = 24` - Tokens older than this are considered stale

### Scoring Thresholds
- `MIN_COMPOSITE_SCORE = 70` - Minimum composite score to alert
- `MIN_INDIVIDUAL_SCORE = 40` - Minimum score for each dimension
- `SCORE_WEIGHTS` - Safety (35%), Timing (25%), Momentum (20%), Relevance (20%)

### Rate Limits
- `DEXSCREENER_RPM = 30` - DexScreener API rate limit
- `GEMINI_RPM = 60` - Gemini API rate limit
- `RUGCHECK_RPM = 10` - RugCheck API rate limit
- `SOLANA_RPC_RPM = 20` - Solana RPC rate limit

### Daily Alert Limits
- `MAX_ALERTS_PER_DAY = 3` - Maximum high-quality alerts per day
- `ALERT_RESET_HOUR = 0` - Reset alert counter at midnight UTC

---

## Usage

### Production Mode

```bash
python main.py
```

### Dry Run Mode (Testing)

Test the full pipeline without sending real Telegram alerts:

```bash
DRY_RUN=true python main.py
```

### Verbose Logging

Enable detailed logging for debugging:

```bash
VERBOSE_LOGGING=true python main.py
```

### Graceful Shutdown

Press `Ctrl+C` to stop the scanner. It will:
- Close WebSocket connections gracefully
- Cancel background tasks
- Print session statistics

---

## Testing

### Run All Tests

```bash
pytest
```

### Run Specific Test Module

```bash
pytest tests/test_shield.py
pytest tests/test_momentum.py
pytest tests/test_scoring.py
```

### Run with Verbose Output

```bash
pytest -v
```

### Run with Coverage

```bash
pytest --cov=. --cov-report=html
```

---

## Module Overview

### Core Modules

- **`main.py`** - Async orchestrator, entry point
- **`config.py`** - Centralized configuration and thresholds
- **`network_layer.py`** - WebSocket manager for real-time token detection
- **`shield.py`** - Multi-tier security validation
- **`momentum.py`** - Price velocity and pump phase analysis
- **`scoring.py`** - Composite score calculation and alert logic
- **`brain.py`** - Keyword extraction and LLM analysis
- **`state.py`** - Daily alert tracking and persistence
- **`rate_limiter.py`** - API rate limiting decorators
- **`dex_hunter.py`** - DexScreener API integration
- **`polymarket_watcher.py`** - Polymarket event fetching

### Test Modules

- **`tests/conftest.py`** - Shared test fixtures (high/low quality tokens)
- **`tests/test_shield.py`** - Security validation tests
- **`tests/test_momentum.py`** - Price analysis tests
- **`tests/test_scoring.py`** - Composite scoring tests

---

## How It Works

### 1. Narrative Update Loop

Every 60 seconds:
1. Fetch Polymarket events via API
2. Filter events by volume (>$100K)
3. Extract keywords using NLP
4. Update WebSocket manager with new narratives

### 2. Token Detection Pipeline

When a token event is detected:

**Tier 0 - Data Fetch**:
- Fetch token data from DexScreener
- Quick liquidity check (>$5K threshold)

**Tier 1 - Momentum Check**:
- Classify pump phase: EARLY (<50% pump, buys>sells) or LATE (>50% or sells>buys)
- Check staleness: old (>24h) + flat (<0.1% movement)
- **Gate**: Must be EARLY and NOT stale to proceed

**Tier 2 - Security Check**:
- RugCheck API validation
- Holder concentration analysis (RPC or RugCheck)
- Honeypot detection (buys but zero sells)
- Bundled transaction heuristic (<1h old + <20 buyers)
- **Gate**: Must pass security check to proceed

**Tier 3 - LLM Analysis** (Gatekept):
- Only called if Tiers 1-2 pass
- Gemini 2.5-flash structured JSON output
- Relevance score (0-100) and authenticity score (0-100)

**Scoring**:
- Calculate composite score using weighted dimensions
- Check alert thresholds (composite >70, all individual >40)

**Alert**:
- Check daily limit (max 3 per day)
- Check duplicate prevention (mint address tracking)
- Send Telegram alert with formatted message
- Record alert in state

---

## Alert Format

Telegram alerts include:

```
🚀 Trump Victory Token (TRUMP)
Address: GoodToken12345...

Score Analysis:
⭐⭐⭐⭐⭐ 85/100

Safety      ⭐⭐⭐⭐ 80/100
Timing      ⭐⭐⭐⭐ 80/100
Momentum    ⭐⭐⭐⭐ 75/100
Relevance   ⭐⭐⭐⭐⭐ 90/100

🔗 View on DexScreener
```

---

## State Persistence

Alert state is persisted in `state.json`:

```json
{
  "date": "2025-02-03",
  "alerts_sent": 2,
  "tokens_alerted": [
    {"mint": "GoodToken123...", "symbol": "TRUMP", "timestamp": "2025-02-03T15:30:00Z"}
  ]
}
```

- Automatically resets daily at midnight UTC
- Prevents duplicate alerts on same token
- Tracks alert count for rate limiting

---

## Troubleshooting

### Common Issues

**Issue**: `GEMINI_API_KEY not set`
- **Solution**: Add your Gemini API key to `.env` file

**Issue**: `Telegram not configured`
- **Solution**: Add `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` to `.env`

**Issue**: `Public RPC rate limiting (429 errors)`
- **Solution**: Get a Helius API key and add `HELIUS_API_KEY` to `.env`

**Issue**: `No events received from WebSocket`
- **Solution**: Check internet connection, verify `WSS_ENDPOINT` in config

**Issue**: `Tests failing with API errors`
- **Solution**: Run tests in mock mode, don't call real APIs during testing

### Debugging

Enable verbose logging:

```bash
VERBOSE_LOGGING=true python main.py
```

Run in dry-run mode to test without side effects:

```bash
DRY_RUN=true python main.py
```

Check configuration:

```bash
python config.py
```

---

## Development

### Code Style

- Follow PEP 8 conventions
- Use type hints throughout
- Add docstrings to all functions
- Keep functions focused and testable

### Testing Guidelines

- Write tests for all new features
- Use fixtures from `conftest.py` for consistent test data
- Mock external API calls using `unittest.mock`
- Aim for >80% code coverage

### Adding New Security Checks

1. Add check function to `shield.py`
2. Integrate into `comprehensive_security_check()`
3. Add test in `tests/test_shield.py`
4. Update scoring weights in `config.py` if needed

### Adding New Scoring Dimensions

1. Add dimension to `calculate_composite_score()` in `scoring.py`
2. Update `SCORE_WEIGHTS` in `config.py` (must sum to 1.0)
3. Add tests in `tests/test_scoring.py`
4. Update README documentation

---

## Architecture Decisions

### Why Async?

- **Non-blocking I/O**: WebSocket and HTTP calls don't block the event loop
- **Concurrent tasks**: Narrative updates and token monitoring run in parallel
- **Scalability**: Easy to add more concurrent streams

### Why Tiered Validation?

- **Cost optimization**: Expensive LLM calls only after basic checks pass
- **Performance**: Quick filters eliminate bad candidates early
- **Quality**: Multi-factor validation ensures high signal-to-noise ratio

### Why Daily Limits?

- **Quality over quantity**: Forces high standards for alerts
- **Prevents spam**: Users won't be overwhelmed
- **Focus**: 3 best opportunities per day is actionable

---

## Performance

- **Average latency per token**: <2 seconds (Tiers 0-2)
- **LLM call latency**: ~1-2 seconds (Tier 3, gatekept)
- **WebSocket reconnection**: Automatic with exponential backoff
- **Memory usage**: <100MB steady state
- **API rate limits**: Respected via decorators

---

## Roadmap

### Short Term
- Add database for state persistence (replace JSON)
- Implement historical price tracking
- Add Web UI dashboard

### Medium Term
- Multi-chain support (Base, Ethereum)
- Advanced technical indicators (RSI, MACD)
- Telegram bot commands (subscribe, configure thresholds)

### Long Term
- Machine learning for better relevance scoring
- Distributed processing with message queue
- Real-time portfolio tracking integration

---

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## License

This project is licensed under the MIT License.

---

## Disclaimer

**This tool is for educational and research purposes only.**

- Do not invest money you cannot afford to lose
- Always conduct your own research (DYOR)
- Crypto markets are highly volatile and risky
- No guarantee of accuracy or profitability
- Use at your own risk

---

## Support

For issues and questions:
- Open an issue on GitHub
- Check documentation in `/docs`
- Review code comments in modules

---

## Acknowledgments

- **DexScreener** - Token data API
- **RugCheck** - Security validation API
- **Gemini** - LLM analysis
- **Helius** - Solana RPC infrastructure
- **Polymarket** - Event data source
