"""
Rate Limiter - API Rate Limiting Utilities
===========================================
Provides decorators for rate-limiting API calls to respect
API quota limits from various services.

Supported rate limits:
- DexScreener: 30 requests per minute (rpm)
- RugCheck: 10 requests per minute (rpm)
- Gemini: 60 requests per minute (rpm)
- GeckoTerminal: 30 requests per minute (rpm)
"""

import time
import logging
from functools import wraps
from typing import Callable, Any

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Token bucket-based rate limiter for API calls.
    
    Maintains per-API rate limit state and enforces delays
    to prevent exceeding quota limits.
    """
    
    def __init__(self, requests_per_minute: int):
        """
        Initialize rate limiter.
        
        Args:
            requests_per_minute: Number of requests allowed per 60 seconds.
        """
        self.requests_per_minute = requests_per_minute
        self.min_interval = 60.0 / requests_per_minute
        self.last_call_time = 0
    
    def wait_if_needed(self) -> None:
        """
        Wait if necessary to maintain rate limit.
        
        Uses simple time-based throttling: tracks the last API call
        and sleeps for the minimum required interval if needed.
        """
        current_time = time.time()
        time_since_last_call = current_time - self.last_call_time
        
        if time_since_last_call < self.min_interval:
            sleep_time = self.min_interval - time_since_last_call
            logger.debug(f"Rate limiter: sleeping for {sleep_time:.3f}s")
            time.sleep(sleep_time)
        
        self.last_call_time = time.time()


# Global rate limiters for each API
_dexscreener_limiter = RateLimiter(30)  # 30 rpm
_rugcheck_limiter = RateLimiter(10)     # 10 rpm
_gemini_limiter = RateLimiter(60)       # 60 rpm
_geckoterminal_limiter = RateLimiter(30)  # 30 rpm


def rate_limit_dexscreener(func: Callable) -> Callable:
    """
    Decorator to rate-limit DexScreener API calls (30 rpm).
    
    Usage:
        @rate_limit_dexscreener
        def fetch_dex_results(keyword):
            # API call here
            pass
    """
    @wraps(func)
    def wrapper(*args, **kwargs) -> Any:
        _dexscreener_limiter.wait_if_needed()
        return func(*args, **kwargs)
    return wrapper


def rate_limit_rugcheck(func: Callable) -> Callable:
    """
    Decorator to rate-limit RugCheck API calls (10 rpm).
    
    Usage:
        @rate_limit_rugcheck
        def check_security(mint_address):
            # API call here
            pass
    """
    @wraps(func)
    def wrapper(*args, **kwargs) -> Any:
        _rugcheck_limiter.wait_if_needed()
        return func(*args, **kwargs)
    return wrapper


def rate_limit_gemini(func: Callable) -> Callable:
    """
    Decorator to rate-limit Gemini API calls (60 rpm).
    
    Usage:
        @rate_limit_gemini
        def analyze_with_llm(token_data):
            # API call here
            pass
    """
    @wraps(func)
    def wrapper(*args, **kwargs) -> Any:
        _gemini_limiter.wait_if_needed()
        return func(*args, **kwargs)
    return wrapper


def rate_limit_geckoterminal(func: Callable) -> Callable:
    """
    Decorator to rate-limit GeckoTerminal API calls (30 rpm).
    
    Usage:
        @rate_limit_geckoterminal
        async def fetch_ohlcv(pool_address):
            # API call here
            pass
    """
    @wraps(func)
    def wrapper(*args, **kwargs) -> Any:
        _geckoterminal_limiter.wait_if_needed()
        return func(*args, **kwargs)
    return wrapper


def rate_limit(requests_per_minute: int) -> Callable:
    """
    Generic rate-limit decorator for custom rate limits.
    
    Usage:
        @rate_limit(requests_per_minute=25)
        def custom_api_call():
            # API call here
            pass
    """
    def decorator(func: Callable) -> Callable:
        limiter = RateLimiter(requests_per_minute)
        
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            limiter.wait_if_needed()
            return func(*args, **kwargs)
        return wrapper
    return decorator
