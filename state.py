"""
State management for PM-Predict bot.

This module handles persistence of daily alert limits across bot restarts.
The state is stored in state.json and tracks:
  - Current date
  - Number of alerts sent today
  - List of tokens already alerted on
  - Last reset time
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class StateManager:
    """Manages bot state persistence."""
    
    STATE_FILE = "state.json"
    
    # Schema version for future compatibility
    SCHEMA_VERSION = "1.1"
    
    @staticmethod
    def get_default_state() -> Dict:
        """Get default state structure.
        
        Returns:
            dict: Default state with today's date and zero alerts.
        """
        today = datetime.utcnow().date().isoformat()
        
        return {
            "schema_version": StateManager.SCHEMA_VERSION,
            "date": today,
            "alerts_today": 0,
            "alerted_tokens": [],  # Token mints that triggered alerts today
            "processed_cabal_tokens": [],  # Tokens that have been cabal-traced (cached)
            "stats": {  # Scan statistics
                "tokens_scanned": 0,
                "tokens_rejected": 0,
                "rejected_by_reason": {
                    "low_liquidity": 0,
                    "late_pump": 0,
                    "stale": 0,
                    "security_fail": 0,
                    "low_score": 0,
                    "daily_limit": 0,
                    "duplicate": 0,
                    "no_data": 0
                }
            },
            "last_reset": datetime.utcnow().isoformat(),
            "metadata": {
                "bot_version": "2.0-overhaul",
                "notes": "Daily alert tracking for PM-Predict"
            }
        }
    
    @staticmethod
    def load_state() -> Dict:
        """Load state from disk or create new state.
        
        Returns:
            dict: Current state (loaded from file or fresh default).
        """
        if not os.path.exists(StateManager.STATE_FILE):
            logger.info(f"[STATE] Creating new state file: {StateManager.STATE_FILE}")
            state = StateManager.get_default_state()
            StateManager.save_state(state)
            return state
        
        try:
            with open(StateManager.STATE_FILE, 'r') as f:
                state = json.load(f)
            logger.info(f"[STATE] Loaded state from {StateManager.STATE_FILE}")
            
            # Migrate state if needed (before date check)
            state = StateManager._migrate_state(state)
            
            # Check if date has changed (new day)
            state = StateManager._check_date_reset(state)
            
            return state
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"[STATE] Error loading state file: {e}")
            logger.warning("[STATE] Creating fresh state")
            state = StateManager.get_default_state()
            StateManager.save_state(state)
            return state
    
    @staticmethod
    def save_state(state: Dict) -> bool:
        """Save state to disk.
        
        Args:
            state (dict): State to save.
            
        Returns:
            bool: True if saved successfully, False otherwise.
        """
        try:
            with open(StateManager.STATE_FILE, 'w') as f:
                json.dump(state, f, indent=2)
            logger.debug(f"[STATE] State saved to {StateManager.STATE_FILE}")
            return True
        except IOError as e:
            logger.error(f"[STATE] Error saving state file: {e}")
            return False
    
    @staticmethod
    def _check_date_reset(state: Dict) -> Dict:
        """Check if a new day has started and reset alert counter if needed.
        
        Args:
            state (dict): Current state.
            
        Returns:
            dict: Updated state with reset if necessary.
        """
        today = datetime.utcnow().date().isoformat()
        
        if state.get("date") != today:
            logger.info(f"[STATE] New day detected. Resetting alert counter.")
            logger.info(f"[STATE] Previous date: {state.get('date')}, Today: {today}")
            state["date"] = today
            state["alerts_today"] = 0
            state["alerted_tokens"] = []
            state["processed_cabal_tokens"] = []
            # Reset stats for new day
            state["stats"] = StateManager.get_default_state()["stats"]
            state["last_reset"] = datetime.utcnow().isoformat()
        
        return state
    
    @staticmethod
    def _migrate_state(state: Dict) -> Dict:
        """Migrate state from older schema versions to current.
        
        Args:
            state (dict): Current state that may need migration.
            
        Returns:
            dict: Migrated state.
        """
        schema_version = state.get("schema_version", "1.0")
        
        # Migrate from 1.0 to 1.1
        if schema_version == "1.0":
            logger.info("[STATE] Migrating state from schema 1.0 to 1.1")
            
            # Add new fields with defaults
            if "processed_cabal_tokens" not in state:
                state["processed_cabal_tokens"] = []
            
            if "stats" not in state:
                state["stats"] = {
                    "tokens_scanned": 0,
                    "tokens_rejected": 0,
                    "rejected_by_reason": {
                        "low_liquidity": 0,
                        "late_pump": 0,
                        "stale": 0,
                        "security_fail": 0,
                        "low_score": 0,
                        "daily_limit": 0,
                        "duplicate": 0,
                        "no_data": 0
                    }
                }
            
            state["schema_version"] = "1.1"
            StateManager.save_state(state)
            logger.info("[STATE] Migration to 1.1 complete")
        
        # Future migrations can be added here
        # if schema_version == "1.1":
        #     # Migrate to 1.2
        #     pass
        
        return state
    
    @staticmethod
    def can_alert(max_per_day: int = 3) -> bool:
        """Check if we can send another alert today.
        
        Args:
            max_per_day (int): Maximum alerts allowed per day.
            
        Returns:
            bool: True if we haven't reached the limit.
        """
        state = StateManager.load_state()
        alerts_count = state.get("alerts_today", 0)
        can_send = alerts_count < max_per_day
        
        if not can_send:
            logger.warning(f"[STATE] Daily alert limit reached ({alerts_count}/{max_per_day})")
        else:
            logger.debug(f"[STATE] Alert available ({alerts_count}/{max_per_day})")
        
        return can_send
    
    @staticmethod
    def record_alert(token_mint: str, token_symbol: str = "") -> bool:
        """Record that an alert was sent for a token.
        
        Args:
            token_mint (str): Token mint address.
            token_symbol (str): Token symbol (for logging).
            
        Returns:
            bool: True if recorded successfully.
        """
        state = StateManager.load_state()
        
        # Check if already alerted on this token today
        if token_mint in state.get("alerted_tokens", []):
            logger.warning(f"[STATE] Already alerted on {token_symbol or token_mint} today")
            return False
        
        state["alerted_tokens"].append(token_mint)
        state["alerts_today"] = state.get("alerts_today", 0) + 1
        
        success = StateManager.save_state(state)
        if success:
            logger.info(f"[STATE] Recorded alert for {token_symbol or token_mint} ({state['alerts_today']}/3)")
        
        return success
    
    @staticmethod
    def was_alerted_today(token_mint: str) -> bool:
        """Check if we already alerted on this token today.
        
        Args:
            token_mint (str): Token mint address.
            
        Returns:
            bool: True if already alerted.
        """
        state = StateManager.load_state()
        return token_mint in state.get("alerted_tokens", [])
    
    @staticmethod
    def get_alerts_remaining(max_per_day: int = 3) -> int:
        """Get number of alerts remaining today.
        
        Args:
            max_per_day (int): Maximum alerts per day.
            
        Returns:
            int: Number of alerts remaining.
        """
        state = StateManager.load_state()
        alerts_count = state.get("alerts_today", 0)
        return max(0, max_per_day - alerts_count)
    
    @staticmethod
    def get_alert_history() -> tuple[int, List[str], str]:
        """Get today's alert history.
        
        Returns:
            tuple: (alerts_count, alerted_tokens_list, reset_time)
        """
        state = StateManager.load_state()
        return (
            state.get("alerts_today", 0),
            state.get("alerted_tokens", []),
            state.get("last_reset", "unknown")
        )
    
    @staticmethod
    def reset_state() -> bool:
        """Force reset of state (useful for testing).
        
        Returns:
            bool: True if reset successfully.
        """
        logger.warning("[STATE] Force resetting state (manual reset)")
        state = StateManager.get_default_state()
        return StateManager.save_state(state)
    
    # =========================================================================
    # CABAL CACHING METHODS
    # =========================================================================
    
    @staticmethod
    def was_cabal_traced(token_mint: str) -> bool:
        """Check if a token has already been cabal-traced today.
        
        Args:
            token_mint (str): Token mint address.
            
        Returns:
            bool: True if already traced (cached).
        """
        state = StateManager.load_state()
        return token_mint in state.get("processed_cabal_tokens", [])
    
    @staticmethod
    def record_cabal_traced(token_mint: str) -> bool:
        """Record that a token has been cabal-traced.
        
        Args:
            token_mint (str): Token mint address.
            
        Returns:
            bool: True if recorded successfully.
        """
        state = StateManager.load_state()
        
        # Initialize if missing (backward compat)
        if "processed_cabal_tokens" not in state:
            state["processed_cabal_tokens"] = []
        
        if token_mint not in state["processed_cabal_tokens"]:
            state["processed_cabal_tokens"].append(token_mint)
            success = StateManager.save_state(state)
            if success:
                logger.debug(f"[STATE] Recorded cabal trace for {token_mint[:16]}...")
            return success
        return True  # Already recorded
    
    # =========================================================================
    # STATISTICS METHODS
    # =========================================================================
    
    @staticmethod
    def increment_stat(stat_name: str, amount: int = 1) -> bool:
        """Increment a statistic counter.
        
        Args:
            stat_name (str): Name of the stat to increment.
                Can be: "tokens_scanned", "tokens_rejected", or a rejection reason
                like "low_liquidity", "late_pump", "stale", "security_fail",
                "low_score", "daily_limit", "duplicate", "no_data".
            amount (int): Amount to increment by (default 1).
            
        Returns:
            bool: True if incremented successfully.
        """
        state = StateManager.load_state()
        
        # Initialize stats if missing (backward compat)
        if "stats" not in state:
            state["stats"] = StateManager.get_default_state()["stats"]
        
        stats = state["stats"]
        
        # Direct stats (tokens_scanned, tokens_rejected)
        if stat_name in ("tokens_scanned", "tokens_rejected"):
            stats[stat_name] = stats.get(stat_name, 0) + amount
        # Rejection reasons
        elif stat_name in stats.get("rejected_by_reason", {}):
            stats["rejected_by_reason"][stat_name] = stats["rejected_by_reason"].get(stat_name, 0) + amount
            # Also increment total rejected count
            stats["tokens_rejected"] = stats.get("tokens_rejected", 0) + amount
        else:
            logger.warning(f"[STATE] Unknown stat name: {stat_name}")
            return False
        
        state["stats"] = stats
        return StateManager.save_state(state)
    
    @staticmethod
    def get_stats() -> Dict:
        """Get current statistics.
        
        Returns:
            dict: Current statistics with keys:
                - tokens_scanned: Total tokens processed
                - tokens_rejected: Total tokens rejected
                - rejected_by_reason: Breakdown by rejection reason
        """
        state = StateManager.load_state()
        
        # Return default stats if not present
        if "stats" not in state:
            return StateManager.get_default_state()["stats"]
        
        return state["stats"]
    
    @staticmethod
    def get_stats_summary() -> str:
        """Get a formatted summary of today's statistics.
        
        Returns:
            str: Formatted statistics summary.
        """
        stats = StateManager.get_stats()
        
        scanned = stats.get("tokens_scanned", 0)
        rejected = stats.get("tokens_rejected", 0)
        passed = scanned - rejected if scanned >= rejected else 0
        
        summary_lines = [
            f"📊 Daily Statistics",
            f"  Scanned: {scanned}",
            f"  Passed: {passed}",
            f"  Rejected: {rejected}",
        ]
        
        # Add rejection breakdown if any rejections
        if rejected > 0:
            reasons = stats.get("rejected_by_reason", {})
            summary_lines.append("  Rejection Reasons:")
            for reason, count in reasons.items():
                if count > 0:
                    reason_label = reason.replace("_", " ").title()
                    summary_lines.append(f"    - {reason_label}: {count}")
        
        return "\n".join(summary_lines)


def display_state_info():
    """Display current state information (for debugging)."""
    print("PM-Predict State Information")
    print("=" * 60)
    
    state = StateManager.load_state()
    print()
    print(f"Schema Version: {state.get('schema_version')}")
    print(f"Date: {state.get('date')}")
    print(f"Alerts Today: {state.get('alerts_today')}/3")
    print(f"Last Reset: {state.get('last_reset')}")
    print()
    print("Alerted Tokens Today:")
    tokens = state.get('alerted_tokens', [])
    if tokens:
        for token in tokens:
            print(f"  - {token}")
    else:
        print("  (none)")
    print()
    print(f"Alerts Remaining: {StateManager.get_alerts_remaining()}")
    print()
    
    # Show cabal cache info
    cabal_tokens = state.get('processed_cabal_tokens', [])
    print(f"Cabal-Traced Tokens (Cached): {len(cabal_tokens)}")
    if cabal_tokens:
        for token in cabal_tokens[:5]:  # Show first 5
            print(f"  - {token[:30]}...")
        if len(cabal_tokens) > 5:
            print(f"  ... and {len(cabal_tokens) - 5} more")
    print()
    
    # Show stats
    print(StateManager.get_stats_summary())


if __name__ == "__main__":
    # Set up logging for debugging
    logging.basicConfig(
        level=logging.DEBUG,
        format="[%(levelname)s] %(message)s"
    )
    
    display_state_info()
