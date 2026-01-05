"""
PM-Predict Main Orchestrator
==============================
The main script that bridges all modules together:
- Polymarket Watcher: Fetches hot events
- Brain: Extracts keywords from titles
- DEX Hunter: Finds potential tokens
- Shield: Validates token security
- Telegram: Sends alerts (optional)
"""

import os
import time
import requests
from typing import Optional
from datetime import datetime
from colorama import init, Fore, Back, Style
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Local modules
from polymarket_watcher import fetch_events
from brain import extract_keywords
from dex_hunter import search_potential_tokens, format_usd
from shield import check_security

# Initialize colorama
init(autoreset=True)

# =============================================================================
# CONFIGURATION
# =============================================================================

# Timing
MAIN_LOOP_INTERVAL_SECONDS = 60  # How often to check for new events
ERROR_RETRY_DELAY_SECONDS = 10

# Filters
MIN_VOLUME_FOR_ALERT = 1_000_000  # Only alert on events with >$1M volume
MAX_TOKENS_TO_CHECK = 10  # Limit security checks per cycle

# Noise Gate: Token freshness and liquidity filters
MIN_LIQUIDITY_FOR_ALERT = 5_000  # Only alert if liquidity > $5K
MAX_TOKEN_AGE_HOURS = 24  # Only alert on tokens created < 24h ago

# Telegram (set via environment or .env file)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Track already-alerted tokens to avoid spam
ALERTED_TOKENS: set = set()


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
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    
    try:
        response = requests.post(
            url,
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
                "parse_mode": "Markdown",
                "disable_web_page_preview": False,
            },
            timeout=10
        )
        return response.status_code == 200
    except Exception as e:
        print(f"{Fore.YELLOW}⚠️  Telegram error: {e}{Style.RESET_ALL}")
        return False


# =============================================================================
# ALERT DISPLAY
# =============================================================================

def display_alpha_alert(token: dict, event_title: str, security_reason: str) -> None:
    """
    Display a big, bold, colorful alert for a validated alpha token.
    
    Args:
        token: Token info dictionary.
        event_title: The Polymarket event that triggered this.
        security_reason: Security check result.
    """
    print("\n")
    print(f"{Back.GREEN}{Fore.BLACK}{Style.BRIGHT}")
    print("=" * 75)
    print("   🚀🚀🚀  SCAM-FREE ALPHA DETECTED  🚀🚀🚀")
    print("=" * 75)
    print(f"{Style.RESET_ALL}")
    
    print(f"{Fore.WHITE}📰 Trigger: {Fore.YELLOW}{event_title}{Style.RESET_ALL}")
    print()
    print(f"{Fore.WHITE}🪙 Token: {Fore.CYAN}{token['name']} ({token['symbol']}){Style.RESET_ALL}")
    print(f"{Fore.WHITE}⛓️  Chain: {Fore.MAGENTA}{token['chain'].upper()}{Style.RESET_ALL}")
    print(f"{Fore.WHITE}💰 Price: {Fore.GREEN}${token['price_usd']}{Style.RESET_ALL}")
    print(f"{Fore.WHITE}💧 Liquidity: {Fore.CYAN}{format_usd(token['liquidity_usd'])}{Style.RESET_ALL}")
    print(f"{Fore.WHITE}📊 24h Volume: {Fore.CYAN}{format_usd(token['volume_24h'])}{Style.RESET_ALL}")
    print(f"{Fore.WHITE}🛡️  Security: {Fore.GREEN}{security_reason}{Style.RESET_ALL}")
    print()
    print(f"{Fore.WHITE}📋 Contract Address:{Style.RESET_ALL}")
    print(f"{Back.WHITE}{Fore.BLACK} {token['address']} {Style.RESET_ALL}")
    print()
    if token.get("url"):
        print(f"{Fore.BLUE}🔗 DexScreener: {token['url']}{Style.RESET_ALL}")
    
    print(f"{Back.GREEN}{Fore.BLACK}{Style.BRIGHT}")
    print("=" * 75)
    print(f"{Style.RESET_ALL}\n")


def format_telegram_message(token: dict, event_title: str) -> str:
    """Format a Telegram alert message."""
    return f"""🚀 *ALPHA DETECTED* 🚀

📰 *Trigger:* {event_title}

🪙 *Token:* {token['name']} ({token['symbol']})
⛓️ *Chain:* {token['chain'].upper()}
💰 *Price:* ${token['price_usd']}
💧 *Liquidity:* {format_usd(token['liquidity_usd'])}
📊 *Volume 24h:* {format_usd(token['volume_24h'])}

📋 *Contract:*
`{token['address']}`

🔗 [View on DexScreener]({token.get('url', '')})
"""


# =============================================================================
# MAIN ORCHESTRATION
# =============================================================================

def process_event(event: dict) -> list[dict]:
    """
    Process a single Polymarket event:
    1. Extract keywords
    2. Search for tokens
    3. Validate security
    4. Return safe tokens
    
    Args:
        event: Event dictionary from Polymarket API.
        
    Returns:
        List of validated, safe tokens.
    """
    title = event.get("title", "")
    volume = float(event.get("volume", 0))
    
    # Skip low-volume events
    if volume < MIN_VOLUME_FOR_ALERT:
        return []
    
    print(f"\n{Fore.CYAN}📌 Processing: {Fore.WHITE}{title}{Style.RESET_ALL}")
    print(f"   Volume: {format_usd(volume)}")
    
    # Step 1: Extract keywords
    keywords = extract_keywords(title)
    if not keywords:
        print(f"   {Fore.YELLOW}No keywords extracted, skipping{Style.RESET_ALL}")
        return []
    
    print(f"   Keywords: {Fore.YELLOW}{keywords}{Style.RESET_ALL}")
    
    # Step 2: Search for tokens
    tokens = search_potential_tokens(keywords)
    if not tokens:
        print(f"   {Fore.YELLOW}No tokens found{Style.RESET_ALL}")
        return []
    
    print(f"   {Fore.GREEN}Found {len(tokens)} potential tokens{Style.RESET_ALL}")
    
    # Step 3: Security check (only for Solana tokens, limit to avoid rate limits)
    safe_tokens = []
    checked = 0
    current_time_ms = int(datetime.now().timestamp() * 1000)
    max_age_ms = MAX_TOKEN_AGE_HOURS * 60 * 60 * 1000  # Convert hours to milliseconds
    
    for token in tokens[:MAX_TOKENS_TO_CHECK]:
        address = token.get("address", "")
        chain = token.get("chain", "").lower()
        liquidity = float(token.get("liquidity_usd", 0) or 0)
        pair_created_at = token.get("pair_created_at", 0)
        
        # Skip if already alerted
        if address.lower() in ALERTED_TOKENS:
            continue
        
        # NOISE GATE: Check liquidity threshold
        if liquidity < MIN_LIQUIDITY_FOR_ALERT:
            print(f"   {Fore.YELLOW}⏭️  Skipping {token['symbol']}: Low liquidity (${liquidity:.0f}){Style.RESET_ALL}")
            continue
        
        # NOISE GATE: Check token age (must be fresh < 24h)
        if pair_created_at > 0:
            age_ms = current_time_ms - pair_created_at
            age_hours = age_ms / (1000 * 60 * 60)
            if age_hours > MAX_TOKEN_AGE_HOURS:
                print(f"   {Fore.YELLOW}⏭️  Skipping {token['symbol']}: Stale token ({age_hours:.1f}h old){Style.RESET_ALL}")
                continue
        
        # Only check Solana tokens with RugCheck (others pass by default)
        if chain == "solana":
            print(f"\n   {Fore.WHITE}🛡️  Checking: {token['symbol']} ({address[:20]}...){Style.RESET_ALL}")
            is_safe, reason = check_security(address, verbose=True)
            
            if is_safe:
                token["security_reason"] = reason
                safe_tokens.append(token)
            checked += 1
        else:
            # Non-Solana tokens: pass with warning
            token["security_reason"] = f"No RugCheck for {chain} (manual DYOR)"
            safe_tokens.append(token)
    
    return safe_tokens


def run_main_loop() -> None:
    """
    Main orchestration loop:
    1. Fetch hot events from Polymarket
    2. Process each event
    3. Display and send alerts for safe tokens
    """
    print(f"\n{Fore.CYAN}{Style.BRIGHT}")
    print("╔═══════════════════════════════════════════════════════════════════════╗")
    print("║             PM-PREDICT - Polymarket Alpha Scanner                     ║")
    print("║                    Press Ctrl+C to stop                               ║")
    print("╚═══════════════════════════════════════════════════════════════════════╝")
    print(f"{Style.RESET_ALL}")
    
    # Check Telegram config
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        print(f"{Fore.GREEN}✅ Telegram alerts enabled{Style.RESET_ALL}")
    else:
        print(f"{Fore.YELLOW}⚠️  Telegram not configured (set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID){Style.RESET_ALL}")
    
    print(f"{Fore.WHITE}🔄 Scanning every {MAIN_LOOP_INTERVAL_SECONDS}s | Min volume: {format_usd(MIN_VOLUME_FOR_ALERT)}{Style.RESET_ALL}")
    print()
    
    cycle_count = 0
    
    while True:
        try:
            cycle_count += 1
            timestamp = datetime.now().strftime("%H:%M:%S")
            
            print(f"\n{Fore.BLUE}{'='*75}")
            print(f"⏰ Cycle #{cycle_count} | {timestamp}")
            print(f"{'='*75}{Style.RESET_ALL}")
            
            # Fetch events
            print(f"\n{Fore.CYAN}📡 Fetching Polymarket events...{Style.RESET_ALL}")
            events = fetch_events()
            
            if not events:
                print(f"{Fore.YELLOW}No events fetched, retrying...{Style.RESET_ALL}")
                time.sleep(ERROR_RETRY_DELAY_SECONDS)
                continue
            
            print(f"{Fore.GREEN}✓ Fetched {len(events)} events{Style.RESET_ALL}")
            
            # Process top events (limit to avoid overload)
            for event in events[:5]:  # Top 5 by volume
                try:
                    safe_tokens = process_event(event)
                    event_title = event.get("title", "Unknown Event")
                    
                    # Alert for each safe token
                    for token in safe_tokens:
                        address = token.get("address", "").lower()
                        
                        # Avoid duplicate alerts
                        if address in ALERTED_TOKENS:
                            continue
                        
                        ALERTED_TOKENS.add(address)
                        
                        # Display console alert
                        display_alpha_alert(
                            token,
                            event_title,
                            token.get("security_reason", "Passed checks")
                        )
                        
                        # Send Telegram alert
                        if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
                            msg = format_telegram_message(token, event_title)
                            if send_telegram_alert(msg):
                                print(f"{Fore.GREEN}📱 Telegram alert sent!{Style.RESET_ALL}")
                
                except Exception as e:
                    print(f"{Fore.RED}❌ Error processing event: {e}{Style.RESET_ALL}")
                    continue
            
            # Wait before next cycle
            print(f"\n{Fore.BLUE}💤 Sleeping {MAIN_LOOP_INTERVAL_SECONDS}s until next scan...{Style.RESET_ALL}")
            time.sleep(MAIN_LOOP_INTERVAL_SECONDS)
            
        except KeyboardInterrupt:
            raise
        except Exception as e:
            print(f"{Fore.RED}❌ Main loop error: {e}{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}⚠️  Retrying in {ERROR_RETRY_DELAY_SECONDS}s...{Style.RESET_ALL}")
            time.sleep(ERROR_RETRY_DELAY_SECONDS)


def main() -> None:
    """Entry point with graceful shutdown handling."""
    try:
        run_main_loop()
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}👋 Scanner stopped. Goodbye!{Style.RESET_ALL}")


if __name__ == "__main__":
    main()
