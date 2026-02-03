"""
Network Layer - WebSocket Real-Time Token Detection
=====================================================
Provides WebSocket connectivity to Solana RPC for real-time token monitoring.

Features:
- WebSocket connection to Helius (primary) or public Solana RPC (fallback)
- Subscriptions to Raydium and Pump.fun program logs for new pool detection
- Narrative matching: filters tokens against active keywords before heavy checks
- Automatic reconnection with exponential backoff
- Multi-provider redundancy

Usage:
    manager = WebSocketManager()
    manager.update_narratives(["trump", "musk", "crypto"])
    await manager.start_monitoring(callback)
"""

import asyncio
import json
import logging
import base64
from typing import Callable, Optional, Set, Any
from dataclasses import dataclass
from datetime import datetime

import websockets
from websockets.exceptions import ConnectionClosed, ConnectionClosedError

import config

# Configure logging
logger = logging.getLogger(__name__)

# ============================================================================
# CONSTANTS
# ============================================================================

# Solana Program IDs for new pool detection
RAYDIUM_PROGRAM_ID = config.RAYDIUM_PROGRAM_ID
PUMP_FUN_PROGRAM_ID = config.PUMP_FUN_PROGRAM_ID

# Reconnection settings
INITIAL_RECONNECT_DELAY = 1.0  # seconds
MAX_RECONNECT_DELAY = 60.0  # seconds
BACKOFF_FACTOR = 2.0


@dataclass
class TokenEvent:
    """
    Represents a detected token event from the network.
    
    Attributes:
        signature: Transaction signature
        program_id: Program that emitted the log (Raydium or Pump.fun)
        logs: Raw log messages from the transaction
        token_name: Extracted token name (if available)
        token_symbol: Extracted token symbol (if available)
        mint_address: Token mint address (if available)
        timestamp: When the event was detected
        matched_narrative: Keyword that matched (if narrative matching enabled)
    """
    signature: str
    program_id: str
    logs: list
    token_name: Optional[str] = None
    token_symbol: Optional[str] = None
    mint_address: Optional[str] = None
    timestamp: Optional[datetime] = None
    matched_narrative: Optional[str] = None


class WebSocketManager:
    """
    Manages WebSocket connections to Solana RPC for real-time token detection.
    
    Connects to Helius (if API key available) or public Solana RPC.
    Subscribes to Raydium and Pump.fun program logs to detect new pool creations.
    Implements narrative matching to filter tokens before expensive checks.
    """
    
    def __init__(self):
        """Initialize WebSocket manager with default settings."""
        self._active_narratives: Set[str] = set()
        self._websocket: Optional[websockets.WebSocketClientProtocol] = None
        self._running: bool = False
        self._reconnect_delay: float = INITIAL_RECONNECT_DELAY
        self._subscription_ids: dict = {}
        self._callback: Optional[Callable] = None
        
        # Select endpoint based on available API key
        self._wss_endpoint = config.WSS_ENDPOINT
        self._using_helius = bool(config.HELIUS_API_KEY)
        
        # Statistics
        self._events_received: int = 0
        self._events_matched: int = 0
        self._connection_attempts: int = 0
    
    @property
    def is_connected(self) -> bool:
        """Check if WebSocket is currently connected."""
        return self._websocket is not None and self._websocket.open
    
    @property
    def active_narratives(self) -> Set[str]:
        """Get current active narratives (keywords)."""
        return self._active_narratives.copy()
    
    @property
    def stats(self) -> dict:
        """Get connection statistics."""
        return {
            "events_received": self._events_received,
            "events_matched": self._events_matched,
            "connection_attempts": self._connection_attempts,
            "using_helius": self._using_helius,
            "active_narratives_count": len(self._active_narratives),
        }
    
    def update_narratives(self, keywords: list[str]) -> None:
        """
        Update the list of active narratives (keywords) to match against.
        
        Incoming tokens will be filtered against these keywords.
        Only tokens with names/symbols matching any keyword will trigger callbacks.
        
        Args:
            keywords: List of keywords to match (case-insensitive).
                     Example: ["trump", "musk", "bitcoin", "eth"]
        """
        # Normalize to lowercase for case-insensitive matching
        self._active_narratives = {kw.lower().strip() for kw in keywords if kw.strip()}
        logger.info(f"Updated active narratives: {self._active_narratives}")
    
    async def start_monitoring(self, callback: Callable[[TokenEvent], Any]) -> None:
        """
        Start monitoring for new token events.
        
        Connects to Solana WebSocket, subscribes to program logs, and invokes
        the callback when matching events are detected.
        
        Args:
            callback: Async or sync function to call when a matching token is detected.
                     Receives a TokenEvent object as argument.
        
        Raises:
            ValueError: If no WSS endpoint is configured.
        """
        if not self._wss_endpoint:
            raise ValueError(
                "No WebSocket endpoint configured. "
                "Set HELIUS_API_KEY or WSS_ENDPOINT environment variable."
            )
        
        self._callback = callback
        self._running = True
        
        logger.info(f"Starting WebSocket monitoring (Helius: {self._using_helius})")
        
        # Use async iterator pattern for automatic reconnection
        while self._running:
            try:
                await self._connect_and_monitor()
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
                if self._running:
                    await self._handle_reconnect()
    
    async def stop_monitoring(self) -> None:
        """Stop monitoring and close WebSocket connection."""
        self._running = False
        
        if self._websocket and self._websocket.open:
            # Unsubscribe from all subscriptions
            for sub_id in self._subscription_ids.values():
                try:
                    await self._unsubscribe(sub_id)
                except Exception as e:
                    logger.debug(f"Error unsubscribing {sub_id}: {e}")
            
            await self._websocket.close()
        
        self._subscription_ids = {}
        logger.info("WebSocket monitoring stopped")
    
    async def _connect_and_monitor(self) -> None:
        """Establish connection and start processing messages."""
        self._connection_attempts += 1
        logger.info(f"Connecting to {self._wss_endpoint[:50]}... (attempt {self._connection_attempts})")
        
        async with websockets.connect(
            self._wss_endpoint,
            ping_interval=30,
            ping_timeout=10,
            close_timeout=5,
        ) as websocket:
            self._websocket = websocket
            self._reconnect_delay = INITIAL_RECONNECT_DELAY  # Reset on success
            
            logger.info("WebSocket connected successfully")
            
            # Subscribe to program logs
            await self._subscribe_to_programs()
            
            # Process incoming messages
            async for message in websocket:
                if not self._running:
                    break
                await self._process_message(message)
    
    async def _subscribe_to_programs(self) -> None:
        """Subscribe to Raydium and Pump.fun program logs."""
        programs = [
            ("raydium", RAYDIUM_PROGRAM_ID),
            ("pumpfun", PUMP_FUN_PROGRAM_ID),
        ]
        
        for name, program_id in programs:
            try:
                sub_id = await self._subscribe_logs(program_id)
                self._subscription_ids[name] = sub_id
                logger.info(f"Subscribed to {name} logs (ID: {sub_id})")
            except Exception as e:
                logger.error(f"Failed to subscribe to {name}: {e}")
    
    async def _subscribe_logs(self, program_id: str) -> int:
        """
        Subscribe to logs from a specific program.
        
        Args:
            program_id: Solana program ID to subscribe to.
        
        Returns:
            Subscription ID for later unsubscription.
        """
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "logsSubscribe",
            "params": [
                {"mentions": [program_id]},
                {"commitment": "confirmed"}
            ]
        }
        
        await self._websocket.send(json.dumps(request))
        
        # Wait for subscription confirmation
        response = await self._websocket.recv()
        data = json.loads(response)
        
        if "result" in data:
            return data["result"]
        elif "error" in data:
            raise RuntimeError(f"Subscription error: {data['error']}")
        else:
            raise RuntimeError(f"Unexpected response: {data}")
    
    async def _unsubscribe(self, subscription_id: int) -> None:
        """Unsubscribe from a log subscription."""
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "logsUnsubscribe",
            "params": [subscription_id]
        }
        await self._websocket.send(json.dumps(request))
    
    async def _process_message(self, message: str) -> None:
        """
        Process incoming WebSocket message.
        
        Parses log data, extracts token information, applies narrative matching,
        and invokes callback if match found.
        
        Args:
            message: Raw JSON message from WebSocket.
        """
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON message received")
            return
        
        # Handle subscription notifications
        if data.get("method") != "logsNotification":
            return
        
        self._events_received += 1
        
        params = data.get("params", {})
        result = params.get("result", {})
        value = result.get("value", {})
        
        signature = value.get("signature", "")
        logs = value.get("logs", [])
        
        if not logs:
            return
        
        # Determine which program emitted this
        program_id = self._identify_program(logs)
        if not program_id:
            return
        
        # Extract token information from logs
        token_info = self._extract_token_info(logs)
        
        # Apply narrative matching
        matched_keyword = self._match_narrative(token_info)
        
        if matched_keyword or not self._active_narratives:
            # Match found OR no narratives configured (pass all)
            self._events_matched += 1
            
            event = TokenEvent(
                signature=signature,
                program_id=program_id,
                logs=logs,
                token_name=token_info.get("name"),
                token_symbol=token_info.get("symbol"),
                mint_address=token_info.get("mint"),
                timestamp=datetime.utcnow(),
                matched_narrative=matched_keyword,
            )
            
            logger.info(
                f"Token event matched: {token_info.get('symbol', 'UNKNOWN')} "
                f"(narrative: {matched_keyword or 'none'})"
            )
            
            # Invoke callback
            if self._callback:
                try:
                    result = self._callback(event)
                    if asyncio.iscoroutine(result):
                        await result
                except Exception as e:
                    logger.error(f"Callback error: {e}")
    
    def _identify_program(self, logs: list) -> Optional[str]:
        """
        Identify which program emitted the logs.
        
        Args:
            logs: List of log messages from transaction.
        
        Returns:
            Program ID if Raydium or Pump.fun, None otherwise.
        """
        logs_str = " ".join(logs).lower()
        
        if RAYDIUM_PROGRAM_ID.lower() in logs_str or "raydium" in logs_str:
            return RAYDIUM_PROGRAM_ID
        elif PUMP_FUN_PROGRAM_ID.lower() in logs_str or "pump" in logs_str:
            return PUMP_FUN_PROGRAM_ID
        
        return None
    
    def _extract_token_info(self, logs: list) -> dict:
        """
        Extract token name, symbol, and mint address from transaction logs.
        
        Parses Raydium and Pump.fun log formats to find token metadata.
        
        Args:
            logs: List of log messages from transaction.
        
        Returns:
            Dict with keys: name, symbol, mint (any may be None).
        """
        info = {"name": None, "symbol": None, "mint": None}
        
        for log in logs:
            log_lower = log.lower()
            
            # Look for token mint addresses (base58 format, ~44 chars)
            # Pattern: common log prefixes that indicate mint
            if "mint:" in log_lower or "token:" in log_lower:
                parts = log.split()
                for part in parts:
                    # Solana addresses are base58, typically 32-44 chars
                    if len(part) >= 32 and len(part) <= 44 and part.isalnum():
                        info["mint"] = part
                        break
            
            # Look for token name/symbol in Program log entries
            if "Program log:" in log:
                content = log.replace("Program log:", "").strip()
                
                # Try to parse as JSON (some programs emit JSON logs)
                try:
                    json_data = json.loads(content)
                    info["name"] = json_data.get("name", info["name"])
                    info["symbol"] = json_data.get("symbol", info["symbol"])
                    info["mint"] = json_data.get("mint", info["mint"])
                except (json.JSONDecodeError, TypeError):
                    pass
                
                # Look for common patterns in text logs
                content_lower = content.lower()
                if "name=" in content_lower or "symbol=" in content_lower:
                    for part in content.split():
                        if part.lower().startswith("name="):
                            info["name"] = part.split("=", 1)[1].strip("'\"")
                        elif part.lower().startswith("symbol="):
                            info["symbol"] = part.split("=", 1)[1].strip("'\"")
        
        return info
    
    def _match_narrative(self, token_info: dict) -> Optional[str]:
        """
        Check if token matches any active narrative keywords.
        
        Performs case-insensitive matching against token name and symbol.
        
        Args:
            token_info: Dict with name and symbol keys.
        
        Returns:
            Matching keyword if found, None otherwise.
        """
        if not self._active_narratives:
            return None  # No narratives configured
        
        # Build search text from token info
        search_text = ""
        if token_info.get("name"):
            search_text += token_info["name"].lower() + " "
        if token_info.get("symbol"):
            search_text += token_info["symbol"].lower()
        
        if not search_text.strip():
            return None  # No token info to match against
        
        # Check each narrative keyword
        for keyword in self._active_narratives:
            if keyword in search_text:
                return keyword
        
        return None
    
    async def _handle_reconnect(self) -> None:
        """Handle reconnection with exponential backoff."""
        logger.info(f"Reconnecting in {self._reconnect_delay:.1f} seconds...")
        await asyncio.sleep(self._reconnect_delay)
        
        # Increase delay for next attempt (exponential backoff)
        self._reconnect_delay = min(
            self._reconnect_delay * BACKOFF_FACTOR,
            MAX_RECONNECT_DELAY
        )


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

async def quick_test_connection() -> bool:
    """
    Quick test of WebSocket connectivity.
    
    Returns:
        True if connection successful, False otherwise.
    """
    if not config.WSS_ENDPOINT:
        logger.error("No WSS endpoint configured")
        return False
    
    try:
        async with websockets.connect(
            config.WSS_ENDPOINT,
            close_timeout=5,
        ) as ws:
            # Send a simple RPC request
            request = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getHealth",
            }
            await ws.send(json.dumps(request))
            response = await asyncio.wait_for(ws.recv(), timeout=5.0)
            data = json.loads(response)
            
            if "result" in data or "error" in data:
                logger.info("WebSocket connection test: SUCCESS")
                return True
    except Exception as e:
        logger.error(f"WebSocket connection test failed: {e}")
    
    return False


# ============================================================================
# MAIN (for testing)
# ============================================================================

if __name__ == "__main__":
    import sys
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    async def example_callback(event: TokenEvent):
        """Example callback for testing."""
        print(f"\n{'='*60}")
        print(f"TOKEN EVENT DETECTED")
        print(f"{'='*60}")
        print(f"Program: {event.program_id}")
        print(f"Signature: {event.signature}")
        print(f"Token: {event.token_name or 'N/A'} ({event.token_symbol or 'N/A'})")
        print(f"Mint: {event.mint_address or 'N/A'}")
        print(f"Matched Narrative: {event.matched_narrative or 'none'}")
        print(f"Timestamp: {event.timestamp}")
        print(f"{'='*60}\n")
    
    async def main():
        # Quick connection test
        print("Testing WebSocket connectivity...")
        if not await quick_test_connection():
            print("Failed to connect. Check your HELIUS_API_KEY or WSS_ENDPOINT.")
            sys.exit(1)
        
        print("\nStarting token monitoring...")
        print("Press Ctrl+C to stop\n")
        
        manager = WebSocketManager()
        
        # Set some example narratives
        manager.update_narratives(["trump", "biden", "musk", "crypto", "sol"])
        
        try:
            await manager.start_monitoring(example_callback)
        except KeyboardInterrupt:
            print("\nStopping...")
            await manager.stop_monitoring()
            
            print(f"\nSession Stats:")
            print(f"  Events Received: {manager.stats['events_received']}")
            print(f"  Events Matched: {manager.stats['events_matched']}")
            print(f"  Connection Attempts: {manager.stats['connection_attempts']}")
    
    asyncio.run(main())
