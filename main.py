"""
PM-Predict Main Orchestrator (Async)
=====================================
Async event-driven orchestrator that connects all modules together:

- network_layer: WebSocket monitoring for real-time token detection
- brain: Keyword extraction from Polymarket events + LLM analysis
- shield: Multi-tier security validation
- momentum: Pump phase classification and staleness detection
- scoring: Composite score calculation and alert decision
- state: Daily alert limiting and persistence
- config: Centralized configuration

Architecture:
- Asyncio event loop with two concurrent tasks:
  1. update_narratives_task: Fetches Polymarket events every 60s, extracts keywords
  2. WebSocket monitoring: Listens for token events, triggers validation pipeline

Event Flow:
  Polymarket -> Keywords -> WebSocket filter -> Token Event
    -> Tier 0: DexScreener data
    -> Tier 1: Momentum check (EARLY/LATE, staleness)
    -> Tier 2: Shield security check (SAFE/DANGER)
    -> Tier 3: Brain LLM analysis (gatekept - only if tiers 1-2 pass)
    -> Scoring: Composite score calculation
    -> Alert: State limiting + Telegram notification
"""

import asyncio
import logging
import sys
import requests
from datetime import datetime
from typing import Optional, Dict, Any
from concurrent.futures import ThreadPoolExecutor
from functools import partial

from colorama import init, Fore, Style
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Local modules
import config
from network_layer import WebSocketManager, TokenEvent
from polymarket_watcher import fetch_events
from brain import extract_keywords, analyze_with_llm
from shield import comprehensive_security_check, _get_token_data_from_dexscreener
from momentum import classify_pump_phase, check_staleness, calculate_price_velocity, get_buy_sell_ratio, analyze_momentum
from scoring import calculate_composite_score, should_alert, format_score_telegram_message
from state import StateManager
from dex_hunter import format_usd
from technicals import get_technical_signals
from liquidity import analyze_liquidity

# Initialize colorama
init(autoreset=True)

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if config.VERBOSE_LOGGING else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

# Suppress noisy third-party loggers
logging.getLogger("websockets").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

# =============================================================================
# CONFIGURATION
# =============================================================================

# Timing
NARRATIVE_UPDATE_INTERVAL_SECONDS = 60  # How often to fetch Polymarket events
MIN_VOLUME_FOR_NARRATIVE = 100_000  # Only use events with >$100K volume for narratives

# Thread pool for running blocking I/O in async context
_executor = ThreadPoolExecutor(max_workers=4)


# =============================================================================
# TELEGRAM NOTIFICATIONS
# =============================================================================

def send_telegram_alert(message: str) -> bool:
    """
    Send an alert message via Telegram Bot API.
    
    Args:
        message: The message to send (supports Markdown).
        
    Returns:
        True if sent successfully, False otherwise.
    """
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        logger.warning("Telegram not configured (missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID)")
        return False
    
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    
    try:
        response = requests.post(
            url,
            json={
                "chat_id": config.TELEGRAM_CHAT_ID,
                "text": message,
                "parse_mode": "Markdown",
                "disable_web_page_preview": False,
            },
            timeout=config.API_TIMEOUT_SECONDS
        )
        if response.status_code == 200:
            logger.info("Telegram alert sent successfully")
            return True
        else:
            logger.error(f"Telegram API error: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        logger.error(f"Telegram error: {e}")
        return False


# =============================================================================
# NARRATIVE UPDATE TASK
# =============================================================================

async def update_narratives_task(manager: WebSocketManager) -> None:
    """
    Background task: Fetch Polymarket events every 60s, extract keywords,
    and update WebSocket manager narratives.
    
    Args:
        manager: WebSocketManager instance to update narratives on.
    """
    logger.info("Starting narrative update task...")
    
    while True:
        try:
            # Run blocking fetch_events in executor
            loop = asyncio.get_running_loop()
            events = await loop.run_in_executor(_executor, fetch_events)
            
            if not events:
                logger.warning("No Polymarket events fetched")
                await asyncio.sleep(NARRATIVE_UPDATE_INTERVAL_SECONDS)
                continue
            
            # Extract keywords from high-volume events
            all_keywords = set()
            events_processed = 0
            
            for event in events:
                volume = float(event.get("volume", 0) or 0)
                if volume < MIN_VOLUME_FOR_NARRATIVE:
                    continue
                
                title = event.get("title", "")
                keywords = extract_keywords(title)
                
                if keywords:
                    all_keywords.update(kw.lower() for kw in keywords)
                    events_processed += 1
            
            if all_keywords:
                # Update WebSocket manager with new narratives
                manager.update_narratives(list(all_keywords))
                logger.info(
                    f"Narratives updated: {len(all_keywords)} keywords from "
                    f"{events_processed} events"
                )
                logger.debug(f"Keywords: {sorted(all_keywords)[:10]}...")
            else:
                logger.warning("No keywords extracted from events")
            
        except Exception as e:
            logger.error(f"Narrative update task error: {e}")
        
        await asyncio.sleep(NARRATIVE_UPDATE_INTERVAL_SECONDS)


# =============================================================================
# TOKEN EVENT HANDLER (Tiered Validation Pipeline)
# =============================================================================

async def handle_token_event(event: TokenEvent) -> None:
    """
    Handle a token event detected by WebSocket.
    
    Tiered validation pipeline:
    1. Narrative Check: Already done by WS manager, just log
    2. Tier 0: Fetch DexScreener data
    3. Tier 1 (Momentum): EARLY/LATE classification, staleness check
    4. Tier 2 (Shield): Comprehensive security check
    5. Tier 3 (Brain): LLM analysis (gatekept - only if tiers 1-2 pass)
    6. Scoring: Composite score calculation
    7. Alert: State limiting + Telegram notification
    
    Args:
        event: TokenEvent from network_layer
    """
    timestamp = datetime.now().strftime("%H:%M:%S")
    
    logger.info(f"\n{'='*60}")
    logger.info(f"TOKEN EVENT RECEIVED @ {timestamp}")
    logger.info(f"{'='*60}")
    logger.info(f"Symbol: {event.token_symbol or 'UNKNOWN'}")
    logger.info(f"Name: {event.token_name or 'Unknown'}")
    logger.info(f"Mint: {event.mint_address or 'N/A'}")
    logger.info(f"Matched Narrative: {event.matched_narrative or 'none'}")
    logger.info(f"Program: {event.program_id}")
    
    # Get mint address - required for downstream checks
    mint_address = event.mint_address
    if not mint_address:
        logger.warning("No mint address available, skipping event")
        return
    
    # Check if already alerted on this token today
    if StateManager.was_alerted_today(mint_address):
        logger.info(f"Already alerted on {event.token_symbol or mint_address[:16]} today, skipping")
        return
    
    # Check if we have alerts remaining
    if not StateManager.can_alert(config.MAX_ALERTS_PER_DAY):
        logger.warning(f"Daily alert limit reached ({config.MAX_ALERTS_PER_DAY}), skipping")
        return
    
    try:
        # =================================================================
        # TIER 0: Fetch DexScreener Data
        # =================================================================
        logger.info(f"\n[TIER 0] Fetching DexScreener data...")
        
        # Run blocking DexScreener fetch in executor
        loop = asyncio.get_running_loop()
        token_data = await loop.run_in_executor(
            _executor,
            partial(_get_token_data_from_dexscreener, mint_address, verbose=False)
        )
        
        if not token_data:
            logger.warning(f"No DexScreener data for {mint_address[:16]}, skipping")
            return
        
        # Extract basic info
        token_name = token_data.get("baseToken", {}).get("name", event.token_name or "Unknown")
        token_symbol = token_data.get("baseToken", {}).get("symbol", event.token_symbol or "???")
        liquidity = float(token_data.get("liquidity", {}).get("usd", 0) or 0)
        
        logger.info(f"Token: {token_name} ({token_symbol})")
        logger.info(f"Liquidity: {format_usd(liquidity)}")
        
        # Quick liquidity check
        if liquidity < config.MIN_LIQUIDITY_USD:
            logger.info(f"Liquidity ${liquidity:.0f} below threshold ${config.MIN_LIQUIDITY_USD}, skipping")
            return
        
        # =================================================================
        # TIER 1: Momentum Check (EARLY/LATE, Staleness)
        # =================================================================
        logger.info(f"\n[TIER 1] Momentum Analysis...")
        
        pump_phase = classify_pump_phase(token_data)
        is_stale = check_staleness(token_data)
        price_velocity = calculate_price_velocity(token_data)
        buy_sell_ratio = get_buy_sell_ratio(token_data)
        
        logger.info(f"Pump Phase: {pump_phase}")
        logger.info(f"Price Velocity: {price_velocity:.2f}%")
        logger.info(f"Buy/Sell Ratio: {buy_sell_ratio or 'N/A'}")
        logger.info(f"Is Stale: {is_stale}")
        
        # EARLY phase required
        if pump_phase != "EARLY":
            logger.info(f"Pump phase is {pump_phase} (not EARLY), skipping")
            return
        
        # Not stale required
        if is_stale:
            logger.info("Token is stale (old + flat price), skipping")
            return
        
        # =================================================================
        # TIER 1.5: Technical Signals & Liquidity Analysis (Parallel, Fail-Open)
        # =================================================================
        technical_signals = None
        liquidity_result = None
        
        # Get pool address from token_data (for GeckoTerminal/Meteora)
        pool_address = token_data.get("pairAddress")
        
        if pool_address:
            try:
                # Run technical signals and liquidity analysis in parallel
                if config.ENABLE_TECHNICALS or config.ENABLE_LIQUIDITY_ANALYSIS:
                    logger.info(f"\n[TIER 1.5] Technical & Liquidity Analysis...")
                    
                    tasks = []
                    if config.ENABLE_TECHNICALS:
                        tasks.append(("technicals", get_technical_signals(pool_address)))
                    if config.ENABLE_LIQUIDITY_ANALYSIS:
                        tasks.append(("liquidity", analyze_liquidity(pool_address)))
                    
                    if tasks:
                        # Gather results with fail-open (return_exceptions=True)
                        results = await asyncio.gather(
                            *[task[1] for task in tasks],
                            return_exceptions=True
                        )
                        
                        for i, (name, _) in enumerate(tasks):
                            result = results[i]
                            if isinstance(result, Exception):
                                logger.warning(f"{name} analysis failed (fail-open): {result}")
                            elif name == "technicals" and isinstance(result, dict):
                                technical_signals = result
                            elif name == "liquidity" and isinstance(result, dict):
                                liquidity_result = result
                    
                    # Log technical signals summary
                    if technical_signals and isinstance(technical_signals, dict):
                        rsi_val = technical_signals.get('rsi')
                        logger.info(f"RSI: {rsi_val:.1f}" if rsi_val else "RSI: N/A")
                        logger.info(f"Trend: {technical_signals.get('trend', 'N/A')}")
                        logger.info(f"EMA Bullish: {technical_signals.get('ema_bullish', 'N/A')}")
                        logger.info(f"MACD Bullish: {technical_signals.get('macd_bullish', 'N/A')}")
                    else:
                        logger.info("Technical signals: N/A (insufficient data or disabled)")
                    
                    # Log liquidity analysis summary
                    if liquidity_result and isinstance(liquidity_result, dict):
                        shape = liquidity_result.get("shape")
                        if shape is not None:
                            shape_str = shape.value if hasattr(shape, 'value') else str(shape)
                        else:
                            shape_str = "Unknown"
                        logger.info(f"Liquidity Shape: {shape_str}")
                    else:
                        logger.info("Liquidity analysis: N/A (not DLMM pool or disabled)")
            
            except Exception as e:
                logger.warning(f"Technical/Liquidity analysis error (fail-open): {e}")
        
        # =================================================================
        # TIER 2: Shield Security Check
        # =================================================================
        logger.info(f"\n[TIER 2] Security Analysis...")
        
        # Run blocking security check in executor
        shield_result = await loop.run_in_executor(
            _executor,
            partial(comprehensive_security_check, mint_address, token_data, verbose=False)
        )
        
        is_safe = shield_result.get("is_safe", False)
        safety_score = shield_result.get("safety_score", 0)
        danger_flags = shield_result.get("danger_flags", [])
        warning_flags = shield_result.get("warning_flags", [])
        
        logger.info(f"Is Safe: {is_safe}")
        logger.info(f"Safety Score: {safety_score}/100")
        logger.info(f"Danger Flags: {len(danger_flags)}")
        logger.info(f"Warning Flags: {len(warning_flags)}")
        
        if not is_safe:
            logger.info(f"Security check FAILED: {danger_flags}")
            return
        
        # =================================================================
        # TIER 3: Brain LLM Analysis (Gatekept)
        # =================================================================
        logger.info(f"\n[TIER 3] LLM Analysis (Gatekept)...")
        
        # Prepare token data for LLM
        llm_token_data = {
            "address": mint_address,
            "name": token_name,
            "symbol": token_symbol,
            "description": token_data.get("info", {}).get("description", ""),
        }
        
        # Use matched narrative as event context
        event_title = event.matched_narrative or "Unknown Narrative"
        
        # Run blocking LLM call in executor
        brain_result = await loop.run_in_executor(
            _executor,
            partial(analyze_with_llm, llm_token_data, event_title)
        )
        
        relevance_score = brain_result.get("relevance_score", 50)
        authenticity_score = brain_result.get("authenticity_score", 50)
        confidence = brain_result.get("confidence", 0)
        
        logger.info(f"Relevance Score: {relevance_score}/100")
        logger.info(f"Authenticity Score: {authenticity_score}/100")
        logger.info(f"Confidence: {confidence}%")
        
        # =================================================================
        # SCORING: Composite Score Calculation
        # =================================================================
        logger.info(f"\n[SCORING] Calculating composite score...")
        
        # Use enhanced analyze_momentum which integrates technical signals
        momentum_result = analyze_momentum(token_data, technical_signals)
        
        # Ensure buy_sell_ratio is properly set for backward compatibility
        if momentum_result.get("buy_sell_ratio") == float('inf'):
            momentum_result["buy_sell_ratio"] = 1.0
        
        score_data = calculate_composite_score(
            shield_result=shield_result,
            momentum_result=momentum_result,
            brain_result=brain_result,
            pump_phase=pump_phase,
            liquidity_result=liquidity_result,
        )
        
        composite_score = score_data.get("composite_score", 0)
        
        logger.info(f"Composite Score: {composite_score}/100")
        logger.info(f"Safety: {score_data.get('safety_score')}/100")
        logger.info(f"Timing: {score_data.get('timing_score')}/100")
        logger.info(f"Momentum: {score_data.get('momentum_score')}/100")
        logger.info(f"Relevance: {score_data.get('relevance_score')}/100")
        if score_data.get("liquidity_adjustment"):
            logger.info(f"{score_data.get('liquidity_adjustment')}")
        
        # Check if alert should be sent
        if not should_alert(score_data):
            logger.info("Composite score below alert threshold, skipping")
            return
        
        # =================================================================
        # ALERT: State Limiting + Telegram Notification
        # =================================================================
        logger.info(f"\n[ALERT] Sending alert...")
        
        # DRY RUN mode check
        if config.DRY_RUN:
            logger.info("DRY RUN mode - would send alert but skipping")
            print(f"\n{Fore.YELLOW}{'='*60}")
            print(f"[DRY RUN] ALERT WOULD BE SENT")
            print(f"{'='*60}{Style.RESET_ALL}")
            print(format_score_telegram_message(
                score_data,
                token_name=token_name,
                token_symbol=token_symbol,
                token_address=mint_address
            ))
            return
        
        # Record alert in state (prevents duplicates)
        if not StateManager.record_alert(mint_address, token_symbol):
            logger.warning("Failed to record alert in state, may be duplicate")
            return
        
        # Format Telegram message
        telegram_message = format_score_telegram_message(
            score_data,
            token_name=token_name,
            token_symbol=token_symbol,
            token_address=mint_address
        )
        
        # Add DexScreener link
        dex_url = token_data.get("url", f"https://dexscreener.com/solana/{mint_address}")
        telegram_message += f"\n\n🔗 [View on DexScreener]({dex_url})"
        
        # Send Telegram alert
        if send_telegram_alert(telegram_message):
            logger.info(f"✅ Alert sent for {token_symbol}")
            
            # Print to console as well
            print(f"\n{Fore.GREEN}{'='*60}")
            print(f"🚀 ALPHA ALERT SENT!")
            print(f"{'='*60}{Style.RESET_ALL}")
            print(f"Token: {token_name} ({token_symbol})")
            print(f"Composite Score: {composite_score}/100")
            print(f"Alerts Remaining: {StateManager.get_alerts_remaining(config.MAX_ALERTS_PER_DAY)}")
        else:
            logger.error(f"Failed to send Telegram alert for {token_symbol}")
        
    except Exception as e:
        logger.error(f"Error processing token event: {e}", exc_info=True)


# =============================================================================
# MAIN ASYNC ORCHESTRATOR
# =============================================================================

async def run_orchestrator() -> None:
    """
    Main async orchestrator function.
    
    Starts two concurrent tasks:
    1. Narrative update task (Polymarket -> Keywords)
    2. WebSocket monitoring (Token events -> Validation pipeline)
    """
    print(f"\n{Fore.CYAN}{Style.BRIGHT}")
    print("╔═══════════════════════════════════════════════════════════════════════╗")
    print("║       PM-PREDICT - Async Polymarket Alpha Scanner (v2.0)              ║")
    print("║                       Press Ctrl+C to stop                            ║")
    print("╚═══════════════════════════════════════════════════════════════════════╝")
    print(f"{Style.RESET_ALL}")
    
    # Validate configuration
    errors = config.validate_config()
    if errors:
        for error in errors:
            print(f"{Fore.RED}❌ {error}{Style.RESET_ALL}")
        if not config.DRY_RUN:
            print(f"{Fore.YELLOW}⚠️  Running in limited mode (some features disabled){Style.RESET_ALL}")
    
    # Check Telegram config
    if config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID:
        print(f"{Fore.GREEN}✅ Telegram alerts enabled{Style.RESET_ALL}")
    else:
        print(f"{Fore.YELLOW}⚠️  Telegram not configured (alerts will be console-only){Style.RESET_ALL}")
    
    # Check DRY RUN mode
    if config.DRY_RUN:
        print(f"{Fore.YELLOW}⚠️  DRY RUN mode enabled (no real alerts will be sent){Style.RESET_ALL}")
    
    # Print state info
    alerts_remaining = StateManager.get_alerts_remaining(config.MAX_ALERTS_PER_DAY)
    print(f"{Fore.WHITE}📊 Alerts remaining today: {alerts_remaining}/{config.MAX_ALERTS_PER_DAY}{Style.RESET_ALL}")
    print()
    
    # Create WebSocket manager
    manager = WebSocketManager()
    narrative_task = None
    
    try:
        # Start narrative update task
        narrative_task = asyncio.create_task(update_narratives_task(manager))
        
        # Give narrative task a moment to populate initial keywords
        await asyncio.sleep(2)
        
        # Start WebSocket monitoring with event handler
        logger.info("Starting WebSocket monitoring...")
        await manager.start_monitoring(handle_token_event)
        
    except asyncio.CancelledError:
        logger.info("Orchestrator cancelled")
    finally:
        await manager.stop_monitoring()
        if narrative_task:
            narrative_task.cancel()
        
        # Print final stats
        stats = manager.stats
        print(f"\n{Fore.CYAN}{'='*60}")
        print(f"Session Statistics")
        print(f"{'='*60}{Style.RESET_ALL}")
        print(f"Events Received: {stats.get('events_received', 0)}")
        print(f"Events Matched: {stats.get('events_matched', 0)}")
        print(f"Connection Attempts: {stats.get('connection_attempts', 0)}")
        
        # Print state info
        alerts_count, _, _ = StateManager.get_alert_history()
        print(f"Alerts Sent Today: {alerts_count}/{config.MAX_ALERTS_PER_DAY}")


def main() -> None:
    """Entry point with graceful shutdown handling."""
    # Check for TELEGRAM_BOT_TOKEN requirement
    if not config.TELEGRAM_BOT_TOKEN and not config.DRY_RUN:
        print(f"{Fore.YELLOW}⚠️  TELEGRAM_BOT_TOKEN not set. Set it or use DRY_RUN=true{Style.RESET_ALL}")
    
    try:
        asyncio.run(run_orchestrator())
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}👋 Scanner stopped. Goodbye!{Style.RESET_ALL}")


if __name__ == "__main__":
    main()
