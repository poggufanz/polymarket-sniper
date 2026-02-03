"""
Entry Watcher - Post-Rejection Entry Point Monitor
===================================================
Monitors tokens that passed initial validation but were rejected due to
late pump phase. Tracks price drops and signals when entry conditions are met.

Key Features:
- Add tokens to watchlist with initial price snapshot
- Periodically check current prices against initial prices
- Signal when price drops by ENTRY_DROP_THRESHOLD_PERCENT
- Auto-remove tokens after ENTRY_WATCH_DURATION_MINUTES
- Return list of triggered tokens for alerting
"""

import time
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from config import (
    ENTRY_DROP_THRESHOLD_PERCENT,
    ENTRY_WATCH_DURATION_MINUTES,
)

logger = logging.getLogger(__name__)


class EntryWatcher:
    """Monitors tokens for entry point signals after price drops."""
    
    def __init__(self):
        """Initialize the entry watcher with empty watchlist."""
        # Watchlist structure: {mint: {symbol, initial_price, added_at, dex_url}}
        self.watchlist: Dict[str, Dict] = {}
        logger.info("[ENTRY_WATCHER] Initialized")
    
    def add_to_watchlist(
        self,
        mint: str,
        symbol: str,
        initial_price: float,
        dex_url: str = ""
    ) -> bool:
        """Add a token to the watchlist for entry point monitoring.
        
        Args:
            mint: Token mint address.
            symbol: Token symbol (e.g., "TRUMP").
            initial_price: Current price when added to watchlist.
            dex_url: DexScreener URL for the token pair.
            
        Returns:
            bool: True if added successfully, False if already in watchlist.
        """
        if mint in self.watchlist:
            logger.debug(f"[ENTRY_WATCHER] {symbol} already in watchlist")
            return False
        
        self.watchlist[mint] = {
            "symbol": symbol,
            "initial_price": initial_price,
            "added_at": datetime.utcnow(),
            "dex_url": dex_url,
        }
        
        logger.info(
            f"[ENTRY_WATCHER] Added {symbol} to watchlist "
            f"(initial_price=${initial_price:.8f}, threshold={ENTRY_DROP_THRESHOLD_PERCENT}%)"
        )
        return True
    
    def remove_from_watchlist(self, mint: str, reason: str = "manual") -> bool:
        """Remove a token from the watchlist.
        
        Args:
            mint: Token mint address to remove.
            reason: Reason for removal (for logging).
            
        Returns:
            bool: True if removed, False if not in watchlist.
        """
        if mint not in self.watchlist:
            return False
        
        token = self.watchlist.pop(mint)
        logger.info(
            f"[ENTRY_WATCHER] Removed {token['symbol']} from watchlist "
            f"(reason: {reason})"
        )
        return True
    
    def get_watchlist(self) -> Dict[str, Dict]:
        """Get the current watchlist.
        
        Returns:
            dict: Current watchlist {mint: token_data}.
        """
        return self.watchlist.copy()
    
    def get_watchlist_size(self) -> int:
        """Get the number of tokens in watchlist.
        
        Returns:
            int: Number of tokens being watched.
        """
        return len(self.watchlist)
    
    def _fetch_current_price(self, mint: str) -> Optional[float]:
        """Fetch current price for a token from DexScreener.
        
        Args:
            mint: Token mint address.
            
        Returns:
            float: Current price in USD, or None if fetch failed.
        """
        try:
            import requests
            from rate_limiter import rate_limit_dexscreener
            
            # Use DexScreener API to get current price
            @rate_limit_dexscreener
            def fetch_price(mint_address: str) -> Optional[float]:
                url = f"https://api.dexscreener.com/latest/dex/tokens/{mint_address}"
                response = requests.get(url, timeout=10)
                response.raise_for_status()
                
                data = response.json()
                pairs = data.get("pairs", [])
                
                if not pairs:
                    return None
                
                # Get first pair (highest liquidity)
                first_pair = pairs[0]
                price_usd = first_pair.get("priceUsd")
                
                if price_usd:
                    return float(price_usd)
                return None
            
            return fetch_price(mint)
            
        except Exception as e:
            logger.error(f"[ENTRY_WATCHER] Error fetching price for {mint[:16]}...: {e}")
            return None
    
    def _is_expired(self, added_at: datetime) -> bool:
        """Check if a token has exceeded the watch duration.
        
        Args:
            added_at: Timestamp when token was added to watchlist.
            
        Returns:
            bool: True if token is expired (should be removed).
        """
        now = datetime.utcnow()
        duration = now - added_at
        return duration > timedelta(minutes=ENTRY_WATCH_DURATION_MINUTES)
    
    def _cleanup_expired_tokens(self) -> List[str]:
        """Remove tokens that have exceeded the watch duration.
        
        Returns:
            list: List of removed token symbols.
        """
        expired_mints = []
        
        for mint, data in list(self.watchlist.items()):
            if self._is_expired(data["added_at"]):
                expired_mints.append(mint)
        
        removed_symbols = []
        for mint in expired_mints:
            token = self.watchlist[mint]
            removed_symbols.append(token["symbol"])
            self.remove_from_watchlist(mint, reason="expired")
        
        if removed_symbols:
            logger.info(
                f"[ENTRY_WATCHER] Cleaned up {len(removed_symbols)} expired tokens: "
                f"{', '.join(removed_symbols)}"
            )
        
        return removed_symbols
    
    def check_entry_signals(self) -> List[Dict]:
        """Check all watchlist tokens for entry point signals.
        
        Workflow:
        1. Fetch current price for each token
        2. Compare with initial price
        3. Signal if current_price <= initial_price * (1 - threshold/100)
        4. Remove triggered tokens from watchlist
        5. Remove expired tokens (older than ENTRY_WATCH_DURATION_MINUTES)
        
        Returns:
            list: List of triggered token dictionaries with keys:
                - mint: Token mint address
                - symbol: Token symbol
                - initial_price: Price when added to watchlist
                - current_price: Current price
                - drop_percent: Percentage drop from initial price
                - dex_url: DexScreener URL
        """
        triggered_tokens = []
        
        # First, cleanup expired tokens
        self._cleanup_expired_tokens()
        
        if not self.watchlist:
            return triggered_tokens
        
        logger.debug(f"[ENTRY_WATCHER] Checking {len(self.watchlist)} tokens for entry signals...")
        
        # Check each token in watchlist
        for mint, data in list(self.watchlist.items()):
            symbol = data["symbol"]
            initial_price = data["initial_price"]
            
            # Fetch current price
            current_price = self._fetch_current_price(mint)
            
            if current_price is None:
                logger.warning(
                    f"[ENTRY_WATCHER] Failed to fetch current price for {symbol}, "
                    "skipping this check cycle"
                )
                continue
            
            # Calculate price drop percentage
            drop_percent = ((initial_price - current_price) / initial_price) * 100
            
            # Check if entry threshold is met
            entry_price_threshold = initial_price * (1 - ENTRY_DROP_THRESHOLD_PERCENT / 100)
            
            logger.debug(
                f"[ENTRY_WATCHER] {symbol}: "
                f"initial=${initial_price:.8f}, "
                f"current=${current_price:.8f}, "
                f"drop={drop_percent:.2f}%, "
                f"threshold={ENTRY_DROP_THRESHOLD_PERCENT}%"
            )
            
            if current_price <= entry_price_threshold:
                # Entry signal triggered!
                logger.info(
                    f"[ENTRY_WATCHER] 🎯 Entry signal for {symbol}! "
                    f"Price dropped {drop_percent:.2f}% "
                    f"(${initial_price:.8f} → ${current_price:.8f})"
                )
                
                triggered_tokens.append({
                    "mint": mint,
                    "symbol": symbol,
                    "initial_price": initial_price,
                    "current_price": current_price,
                    "drop_percent": drop_percent,
                    "dex_url": data.get("dex_url", ""),
                })
                
                # Remove from watchlist after triggering
                self.remove_from_watchlist(mint, reason="triggered")
        
        if triggered_tokens:
            logger.info(
                f"[ENTRY_WATCHER] Found {len(triggered_tokens)} entry signals: "
                f"{', '.join([t['symbol'] for t in triggered_tokens])}"
            )
        
        return triggered_tokens
    
    def get_watchlist_summary(self) -> str:
        """Get a formatted summary of the current watchlist.
        
        Returns:
            str: Formatted watchlist summary.
        """
        if not self.watchlist:
            return "[ENTRY_WATCHER] Watchlist is empty"
        
        summary_lines = [
            f"[ENTRY_WATCHER] Watchlist ({len(self.watchlist)} tokens):",
        ]
        
        for mint, data in self.watchlist.items():
            symbol = data["symbol"]
            initial_price = data["initial_price"]
            added_at = data["added_at"]
            
            # Calculate time remaining
            now = datetime.utcnow()
            elapsed = now - added_at
            remaining = timedelta(minutes=ENTRY_WATCH_DURATION_MINUTES) - elapsed
            remaining_minutes = max(0, int(remaining.total_seconds() / 60))
            
            summary_lines.append(
                f"  - {symbol} (${initial_price:.8f}) | "
                f"Added {int(elapsed.total_seconds() / 60)}m ago | "
                f"{remaining_minutes}m remaining"
            )
        
        return "\n".join(summary_lines)


# =============================================================================
# TESTING
# =============================================================================
if __name__ == "__main__":
    # Set up logging for debugging
    logging.basicConfig(
        level=logging.DEBUG,
        format="[%(levelname)s] %(message)s"
    )
    
    print("\n" + "="*75)
    print("ENTRY WATCHER - Test Module")
    print("="*75 + "\n")
    
    # Initialize watcher
    watcher = EntryWatcher()
    
    # Test 1: Add tokens to watchlist
    print("Test 1: Adding tokens to watchlist...")
    watcher.add_to_watchlist(
        mint="TRUMP123456789",
        symbol="TRUMP",
        initial_price=0.00012345,
        dex_url="https://dexscreener.com/solana/trump123"
    )
    
    watcher.add_to_watchlist(
        mint="BIDEN987654321",
        symbol="BIDEN",
        initial_price=0.00054321,
        dex_url="https://dexscreener.com/solana/biden987"
    )
    
    print(f"Watchlist size: {watcher.get_watchlist_size()}")
    print(watcher.get_watchlist_summary())
    print()
    
    # Test 2: Try to add duplicate
    print("Test 2: Adding duplicate token...")
    result = watcher.add_to_watchlist(
        mint="TRUMP123456789",
        symbol="TRUMP",
        initial_price=0.00012345,
    )
    print(f"Duplicate add result: {result} (should be False)")
    print()
    
    # Test 3: Remove token
    print("Test 3: Removing token...")
    result = watcher.remove_from_watchlist("BIDEN987654321", reason="test")
    print(f"Remove result: {result} (should be True)")
    print(f"Watchlist size: {watcher.get_watchlist_size()}")
    print()
    
    # Test 4: Get watchlist
    print("Test 4: Getting watchlist...")
    watchlist = watcher.get_watchlist()
    print(f"Watchlist: {watchlist}")
    print()
    
    print("="*75)
    print("Test Complete!")
    print("="*75 + "\n")
    print("NOTE: check_entry_signals() requires real API calls and is not tested here.")
    print("Use in production with actual token data from DexScreener.")
