"""
Shield Module - Token Security Checker
=======================================
Validates tokens against RugCheck API to filter out
scams, honeypots, and high-risk tokens.
"""

import requests
from typing import Optional, Tuple
from colorama import init, Fore, Style
from rate_limiter import rate_limit_rugcheck

# Initialize colorama
init(autoreset=True)

# Constants
RUGCHECK_API_URL = "https://api.rugcheck.xyz/v1/tokens/{mint_address}/report/summary"
REQUEST_TIMEOUT_SECONDS = 10

# Risk levels that should be rejected
DANGER_LEVELS = {"danger", "high", "critical", "honeypot", "scam", "rug"}
# Risk levels that are acceptable
SAFE_LEVELS = {"good", "safe", "low", "ok", "verified"}


@rate_limit_rugcheck
def check_security(mint_address: str, verbose: bool = True) -> Tuple[bool, str]:
    """
    Check if a Solana token is safe using RugCheck API.
    
    Args:
        mint_address: The token's mint/contract address.
        verbose: If True, print status messages.
        
    Returns:
        Tuple of (is_safe: bool, reason: str)
        - is_safe: True if token passed security check
        - reason: Human-readable explanation
    """
    if not mint_address:
        return False, "Empty address"
    
    url = RUGCHECK_API_URL.format(mint_address=mint_address)
    
    try:
        response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
        
        # Handle 404 - token not found in RugCheck
        if response.status_code == 404:
            if verbose:
                print(f"  {Fore.YELLOW}⚠️  Not found in RugCheck (new token?){Style.RESET_ALL}")
            return True, "Not indexed yet (proceed with caution)"
        
        response.raise_for_status()
        data = response.json()
        
        # Extract risk score/level
        # RugCheck response structure can vary, check common fields
        risk_level = ""
        risk_score = 0
        
        # Check various possible response structures
        if isinstance(data, dict):
            risk_level = str(data.get("riskLevel", "")).lower()
            risk_score = data.get("score", data.get("riskScore", 0))
            
            # Some responses use "risks" array
            risks = data.get("risks", [])
            if risks and isinstance(risks, list):
                # Count high-severity risks
                high_risks = sum(1 for r in risks if str(r.get("level", "")).lower() in DANGER_LEVELS)
                if high_risks > 0:
                    return False, f"Found {high_risks} high-risk issues"
        
        # Evaluate risk level
        if risk_level in DANGER_LEVELS:
            if verbose:
                print(f"  {Fore.RED}🚨 DANGER: Risk level = {risk_level}{Style.RESET_ALL}")
            return False, f"Risk level: {risk_level}"
        
        if risk_level in SAFE_LEVELS:
            if verbose:
                print(f"  {Fore.GREEN}✅ SAFE: Risk level = {risk_level}{Style.RESET_ALL}")
            return True, f"Risk level: {risk_level}"
        
        # If we got a numeric score, evaluate it
        if isinstance(risk_score, (int, float)):
            if risk_score >= 80:
                if verbose:
                    print(f"  {Fore.RED}🚨 HIGH RISK: Score = {risk_score}{Style.RESET_ALL}")
                return False, f"Risk score: {risk_score}"
            elif risk_score <= 30:
                if verbose:
                    print(f"  {Fore.GREEN}✅ LOW RISK: Score = {risk_score}{Style.RESET_ALL}")
                return True, f"Risk score: {risk_score}"
        
        # Default: cautiously allow if no red flags found
        if verbose:
            print(f"  {Fore.YELLOW}⚠️  Unknown risk level, allowing cautiously{Style.RESET_ALL}")
        return True, "No major red flags detected"
        
    except requests.exceptions.Timeout:
        if verbose:
            print(f"  {Fore.YELLOW}⏱️  RugCheck timeout - skipping check{Style.RESET_ALL}")
        return True, "Security check timed out"
        
    except requests.exceptions.RequestException as e:
        if verbose:
            print(f"  {Fore.YELLOW}⚠️  RugCheck API error: {e}{Style.RESET_ALL}")
        return True, f"API error: {str(e)[:50]}"
    
    except Exception as e:
        if verbose:
            print(f"  {Fore.YELLOW}⚠️  Unexpected error: {e}{Style.RESET_ALL}")
        return True, f"Check failed: {str(e)[:50]}"


def is_safe_token(mint_address: str) -> bool:
    """
    Simple wrapper that returns only the boolean result.
    
    Args:
        mint_address: The token's mint/contract address.
        
    Returns:
        True if token appears safe, False otherwise.
    """
    is_safe, _ = check_security(mint_address, verbose=False)
    return is_safe


# =============================================================================
# TESTING
# =============================================================================
if __name__ == "__main__":
    print(f"\n{Fore.CYAN}{'='*60}")
    print(f"🛡️  SHIELD MODULE - Security Check Test")
    print(f"{'='*60}{Style.RESET_ALL}\n")
    
    # Test with some known addresses
    test_addresses = [
        # Random test addresses (may or may not exist)
        "So11111111111111111111111111111111111111112",  # Wrapped SOL
        "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
        "invalid_address_12345",  # Invalid
    ]
    
    for addr in test_addresses:
        print(f"{Fore.WHITE}Checking: {Fore.YELLOW}{addr[:30]}...{Style.RESET_ALL}")
        is_safe, reason = check_security(addr)
        status = f"{Fore.GREEN}✓ SAFE" if is_safe else f"{Fore.RED}✗ RISKY"
        print(f"  Result: {status} - {reason}{Style.RESET_ALL}")
        print()
    
    print(f"{Fore.CYAN}{'='*60}")
    print(f"Test Complete!")
    print(f"{'='*60}{Style.RESET_ALL}\n")
