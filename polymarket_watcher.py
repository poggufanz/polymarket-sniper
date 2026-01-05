"""
Polymarket Market Watcher
=========================
A real-time monitor for high-volume events on Polymarket.
Fetches data from the Gamma API and displays colorized output.
"""

import time
import requests
from typing import Optional
from colorama import init, Fore, Style

# Initialize colorama for Windows compatibility
init(autoreset=True)

# Constants
API_URL = "https://gamma-api.polymarket.com/events"
REFRESH_INTERVAL_SECONDS = 30
RETRY_DELAY_SECONDS = 5
REQUEST_TIMEOUT_SECONDS = 15

# Noise Gate: Minimum volume threshold (USD)
MIN_VOLUME_FILTER = 50_000  # Only process events with volume > $50K


def format_volume(volume: float) -> str:
    """
    Format volume in USD with appropriate suffix (K, M, B).
    
    Args:
        volume: Raw volume amount in USD.
        
    Returns:
        Formatted string like '$1.5M' or '$500K'.
    """
    if volume >= 1_000_000_000:
        return f"${volume / 1_000_000_000:.2f}B"
    elif volume >= 1_000_000:
        return f"${volume / 1_000_000:.2f}M"
    elif volume >= 1_000:
        return f"${volume / 1_000:.1f}K"
    else:
        return f"${volume:.0f}"


def fetch_events() -> Optional[list[dict]]:
    """
    Fetch top events from Polymarket Gamma API.
    
    Returns:
        List of event dictionaries, or None if the request fails.
    """
    params = {
        "limit": 20,
        "active": "true",
        "closed": "false",
        "order": "volume",
        "ascending": "false",  # Descending order for highest volume first
    }
    
    try:
        response = requests.get(API_URL, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        events = response.json()
        
        # Apply volume filter - only keep high-conviction events
        filtered_events = []
        for event in events:
            volume = float(event.get("volume", 0) or 0)
            if volume >= MIN_VOLUME_FILTER:
                filtered_events.append(event)
        
        return filtered_events
    except requests.exceptions.RequestException as e:
        print(f"{Fore.RED}❌ API Error: {e}{Style.RESET_ALL}")
        return None


def display_events(events: list[dict]) -> None:
    """
    Display events in a clean, colorized format.
    
    Args:
        events: List of event dictionaries from the API.
    """
    # Clear screen effect with separator
    print("\n" + "=" * 70)
    print(f"{Fore.CYAN}{Style.BRIGHT}🔥 POLYMARKET HOT EVENTS 🔥{Style.RESET_ALL}")
    print(f"{Fore.WHITE}Top 20 by Volume | Refreshing every {REFRESH_INTERVAL_SECONDS}s{Style.RESET_ALL}")
    print("=" * 70 + "\n")
    
    if not events:
        print(f"{Fore.YELLOW}No active events found.{Style.RESET_ALL}")
        return
    
    for idx, event in enumerate(events, start=1):
        title = event.get("title", "Unknown Event")
        
        # Volume can be in different formats; try to extract it
        volume_raw = event.get("volume", 0)
        try:
            volume = float(volume_raw) if volume_raw else 0.0
        except (ValueError, TypeError):
            volume = 0.0
        
        volume_formatted = format_volume(volume)
        
        # Color coding based on volume
        if volume >= 10_000_000:
            volume_color = Fore.GREEN + Style.BRIGHT
            rank_color = Fore.GREEN + Style.BRIGHT
        elif volume >= 1_000_000:
            volume_color = Fore.YELLOW
            rank_color = Fore.YELLOW
        else:
            volume_color = Fore.WHITE
            rank_color = Fore.WHITE
        
        # Extract liquidity if available
        liquidity_raw = event.get("liquidity", None)
        liquidity_str = ""
        if liquidity_raw:
            try:
                liquidity = float(liquidity_raw)
                liquidity_str = f" | Liq: {format_volume(liquidity)}"
            except (ValueError, TypeError):
                pass
        
        # Print formatted line
        print(f"{rank_color}#{idx:02d}{Style.RESET_ALL} {Fore.CYAN}{title[:55]:<55}{Style.RESET_ALL}")
        print(f"     {volume_color}Vol: {volume_formatted}{Style.RESET_ALL}{Fore.MAGENTA}{liquidity_str}{Style.RESET_ALL}")
        print()


def run_watcher() -> None:
    """
    Main loop: fetch and display events, repeat every REFRESH_INTERVAL_SECONDS.
    """
    print(f"{Fore.CYAN}{Style.BRIGHT}")
    print("╔═══════════════════════════════════════════════════════════════════╗")
    print("║           POLYMARKET WATCHER - Real-Time Volume Monitor           ║")
    print("║                    Press Ctrl+C to stop                           ║")
    print("╚═══════════════════════════════════════════════════════════════════╝")
    print(f"{Style.RESET_ALL}")
    
    while True:
        events = fetch_events()
        
        if events is not None:
            display_events(events)
            print(f"{Fore.BLUE}⏰ Next refresh in {REFRESH_INTERVAL_SECONDS} seconds...{Style.RESET_ALL}")
            time.sleep(REFRESH_INTERVAL_SECONDS)
        else:
            # Retry logic on API failure
            print(f"{Fore.YELLOW}⚠️ Retrying in {RETRY_DELAY_SECONDS} seconds...{Style.RESET_ALL}")
            time.sleep(RETRY_DELAY_SECONDS)


def main() -> None:
    """Entry point with graceful shutdown handling."""
    try:
        run_watcher()
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}👋 Watcher stopped. Goodbye!{Style.RESET_ALL}")


if __name__ == "__main__":
    main()
