"""
GoPlusLabs Security API Integration for Solana Tokens.

This module provides security checks via GoPlusLabs API to detect:
- Honeypot contracts
- Mintable tokens
- Hidden owner privileges
- Self-destruct capability
- Blacklist functionality

API Documentation: https://docs.gopluslabs.io/
"""

import asyncio
import logging
from typing import Dict, Any, Optional
import aiohttp

import config
from rate_limiter import rate_limit

logger = logging.getLogger(__name__)

# Security level constants
LEVEL_OK = "OK"
LEVEL_WARNING = "WARNING"
LEVEL_DANGER = "DANGER"
LEVEL_UNKNOWN = "UNKNOWN"


async def check_goplus_security(address: str) -> Dict[str, Any]:
    """
    Check token security using GoPlusLabs API.
    
    Args:
        address: Solana token contract address
        
    Returns:
        Dict with:
            - level: str - Security level (OK/WARNING/DANGER/UNKNOWN)
            - reason: str - Human-readable explanation
            - checks: Dict - Individual check results
            
    Example:
        {
            "level": "DANGER",
            "reason": "Honeypot detected, token is blacklisted",
            "checks": {
                "is_honeypot": True,
                "is_mintable": False,
                "hidden_owner": False,
                "selfdestruct": False,
                "is_blacklisted": True
            }
        }
    """
    logger.info(f"Checking GoPlusLabs security for {address}")
    
    try:
        result = await _fetch_goplus_data(address)
        
        if not result:
            logger.warning(f"No GoPlus data for {address} (404 or not found)")
            return {
                "level": LEVEL_UNKNOWN,
                "reason": "Token not found in GoPlusLabs database",
                "checks": {}
            }
        
        # Parse security checks from API response
        checks = _parse_security_checks(result)
        
        # Determine security level based on checks
        level, reason = _evaluate_security_level(checks)
        
        return {
            "level": level,
            "reason": reason,
            "checks": checks
        }
        
    except Exception as e:
        logger.error(f"GoPlus security check failed for {address}: {e}", exc_info=True)
        return {
            "level": LEVEL_UNKNOWN,
            "reason": f"API error: {str(e)}",
            "checks": {}
        }


@rate_limit(requests_per_minute=config.GOPLUS_RPM)
async def _fetch_goplus_data(address: str) -> Optional[Dict[str, Any]]:
    """
    Fetch token security data from GoPlusLabs API.
    
    Args:
        address: Solana token contract address
        
    Returns:
        Dict with API response data, or None if not found
    """
    url = config.GOPLUS_API_URL
    params = {"contract_addresses": address}
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                params=params,
                timeout=aiohttp.ClientTimeout(total=config.API_TIMEOUT_SECONDS)
            ) as response:
                # Handle 404 gracefully - token not in database
                if response.status == 404:
                    logger.info(f"Token {address} not found in GoPlus database")
                    return None
                
                # Raise for other error status codes
                response.raise_for_status()
                
                data = await response.json()
                
                # API returns nested structure: {"code": 1, "result": {address: {...}}}
                if data.get("code") != 1:
                    logger.warning(f"GoPlus API error code: {data.get('code')}")
                    return None
                
                result = data.get("result", {})
                token_data = result.get(address.lower())
                
                if not token_data:
                    logger.info(f"No security data for {address} in response")
                    return None
                
                return token_data
                
    except aiohttp.ClientError as e:
        logger.error(f"HTTP error fetching GoPlus data: {e}")
        raise
    except asyncio.TimeoutError:
        logger.error(f"Timeout fetching GoPlus data for {address}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error fetching GoPlus data: {e}")
        raise


def _parse_security_checks(data: Dict[str, Any]) -> Dict[str, bool]:
    """
    Parse security check results from API response.
    
    GoPlusLabs API returns "0" for false and "1" for true as strings.
    Convert these to proper booleans.
    
    Args:
        data: Raw API response data for token
        
    Returns:
        Dict with boolean check results
    """
    def str_to_bool(value: Any) -> bool:
        """Convert GoPlusLabs string "0"/"1" to boolean."""
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value == "1"
        if isinstance(value, int):
            return value == 1
        return False
    
    checks = {
        "is_honeypot": str_to_bool(data.get("is_honeypot", "0")),
        "is_mintable": str_to_bool(data.get("is_mintable", "0")),
        "hidden_owner": str_to_bool(data.get("hidden_owner", "0")),
        "selfdestruct": str_to_bool(data.get("selfdestruct", "0")),
        "is_blacklisted": str_to_bool(data.get("is_blacklisted", "0"))
    }
    
    logger.debug(f"Parsed GoPlus checks: {checks}")
    return checks


def _evaluate_security_level(checks: Dict[str, bool]) -> tuple[str, str]:
    """
    Evaluate overall security level based on individual checks.
    
    Priority:
    1. DANGER: Honeypot or blacklisted
    2. WARNING: Mintable or hidden owner or selfdestruct
    3. OK: All checks passed
    
    Args:
        checks: Dict of boolean check results
        
    Returns:
        Tuple of (level, reason)
    """
    danger_flags = []
    warning_flags = []
    
    # Critical flags (DANGER level)
    if checks.get("is_honeypot"):
        danger_flags.append("honeypot detected")
    if checks.get("is_blacklisted"):
        danger_flags.append("token is blacklisted")
    
    # Medium severity flags (WARNING level)
    if checks.get("is_mintable"):
        warning_flags.append("unlimited minting possible")
    if checks.get("hidden_owner"):
        warning_flags.append("hidden owner privileges")
    if checks.get("selfdestruct"):
        warning_flags.append("self-destruct capability")
    
    # Evaluate level
    if danger_flags:
        level = LEVEL_DANGER
        reason = ", ".join(danger_flags).capitalize()
    elif warning_flags:
        level = LEVEL_WARNING
        reason = ", ".join(warning_flags).capitalize()
    else:
        level = LEVEL_OK
        reason = "All security checks passed"
    
    return level, reason


# Example usage
if __name__ == "__main__":
    import sys
    
    logging.basicConfig(level=logging.INFO)
    
    if len(sys.argv) < 2:
        print("Usage: python goplus_security.py <token_address>")
        sys.exit(1)
    
    token_address = sys.argv[1]
    
    async def main():
        result = await check_goplus_security(token_address)
        print(f"\nGoPlus Security Check Results:")
        print(f"Level: {result['level']}")
        print(f"Reason: {result['reason']}")
        print(f"Checks: {result['checks']}")
    
    asyncio.run(main())
