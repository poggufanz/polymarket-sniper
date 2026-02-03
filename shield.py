"""
Shield Module - Token Security Checker
=======================================
Validates tokens against RugCheck API to filter out
scams, honeypots, and high-risk tokens.

Enhanced with:
- Holder concentration analysis (via Solana RPC or RugCheck topHolders)
- Honeypot detection (via DexScreener txns analysis)
- Bundled transaction detection (heuristic: new token + few holders)
- Comprehensive security check aggregator
"""

import requests
from typing import Optional, Tuple, Dict, Any, List
from colorama import init, Fore, Style
from datetime import datetime
import time

from rate_limiter import rate_limit_rugcheck, rate_limit, rate_limit_dexscreener
import config

# Initialize colorama
init(autoreset=True)

# Constants
RUGCHECK_API_URL = "https://api.rugcheck.xyz/v1/tokens/{mint_address}/report/summary"
RUGCHECK_FULL_URL = "https://api.rugcheck.xyz/v1/tokens/{mint_address}/report"
DEXSCREENER_TOKEN_URL = "https://api.dexscreener.com/tokens/v1/solana/{mint_address}"
REQUEST_TIMEOUT_SECONDS = config.API_TIMEOUT_SECONDS

# Risk levels that should be rejected
DANGER_LEVELS = {"danger", "high", "critical", "honeypot", "scam", "rug"}
# Risk levels that are acceptable
SAFE_LEVELS = {"good", "safe", "low", "ok", "verified"}

# Security check result levels
LEVEL_DANGER = "DANGER"
LEVEL_WARNING = "WARNING"
LEVEL_OK = "OK"
LEVEL_UNKNOWN = "UNKNOWN"


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
# HOLDER CONCENTRATION ANALYSIS
# =============================================================================

@rate_limit(config.SOLANA_RPC_RPM)
def _get_holders_from_rpc(mint_address: str, verbose: bool = True) -> Optional[List[Dict]]:
    """
    Fetch top token holders using Solana RPC getTokenLargestAccounts.
    
    Args:
        mint_address: The token's mint address.
        verbose: If True, print status messages.
        
    Returns:
        List of holder accounts with balances, or None on failure.
    """
    try:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getTokenLargestAccounts",
            "params": [mint_address]
        }
        
        response = requests.post(
            config.SOLANA_RPC_URL,
            json=payload,
            timeout=REQUEST_TIMEOUT_SECONDS
        )
        response.raise_for_status()
        data = response.json()
        
        if "error" in data:
            if verbose:
                print(f"  {Fore.YELLOW}⚠️  RPC error: {data['error'].get('message', 'Unknown')}{Style.RESET_ALL}")
            return None
        
        result = data.get("result", {})
        accounts = result.get("value", [])
        
        if verbose and accounts:
            print(f"  {Fore.WHITE}📊 RPC returned {len(accounts)} top holders{Style.RESET_ALL}")
        
        return accounts
        
    except requests.exceptions.Timeout:
        if verbose:
            print(f"  {Fore.YELLOW}⏱️  RPC timeout for holder check{Style.RESET_ALL}")
        return None
    except requests.exceptions.RequestException as e:
        if verbose:
            print(f"  {Fore.YELLOW}⚠️  RPC request error: {e}{Style.RESET_ALL}")
        return None
    except Exception as e:
        if verbose:
            print(f"  {Fore.YELLOW}⚠️  RPC unexpected error: {e}{Style.RESET_ALL}")
        return None


@rate_limit_rugcheck
def _get_holders_from_rugcheck(mint_address: str, verbose: bool = True) -> Optional[List[Dict]]:
    """
    Fetch top holders using RugCheck API (fallback).
    
    Args:
        mint_address: The token's mint address.
        verbose: If True, print status messages.
        
    Returns:
        List of holder objects with percentages, or None on failure.
    """
    try:
        url = RUGCHECK_FULL_URL.format(mint_address=mint_address)
        response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
        
        if response.status_code == 404:
            if verbose:
                print(f"  {Fore.YELLOW}⚠️  Token not found in RugCheck{Style.RESET_ALL}")
            return None
        
        response.raise_for_status()
        data = response.json()
        
        # RugCheck returns topHolders in the response
        top_holders = data.get("topHolders", [])
        
        if verbose and top_holders:
            print(f"  {Fore.WHITE}📊 RugCheck returned {len(top_holders)} top holders{Style.RESET_ALL}")
        
        return top_holders
        
    except requests.exceptions.Timeout:
        if verbose:
            print(f"  {Fore.YELLOW}⏱️  RugCheck timeout for holder check{Style.RESET_ALL}")
        return None
    except requests.exceptions.RequestException as e:
        if verbose:
            print(f"  {Fore.YELLOW}⚠️  RugCheck request error: {e}{Style.RESET_ALL}")
        return None
    except Exception as e:
        if verbose:
            print(f"  {Fore.YELLOW}⚠️  RugCheck unexpected error: {e}{Style.RESET_ALL}")
        return None


def check_holder_concentration(
    mint_address: str,
    token_supply: Optional[float] = None,
    verbose: bool = True
) -> Dict[str, Any]:
    """
    Check if top 10 holders control more than threshold % of supply.
    
    Uses tiered approach:
    - Primary: Solana RPC getTokenLargestAccounts
    - Fallback: RugCheck topHolders field
    
    Args:
        mint_address: The token's mint address.
        token_supply: Total token supply (for RPC calculation). Optional.
        verbose: If True, print status messages.
        
    Returns:
        Dict with keys:
        - level: DANGER, WARNING, OK, or UNKNOWN
        - top10_percent: Percentage held by top 10 (if calculable)
        - reason: Human-readable explanation
        - source: "rpc" or "rugcheck" or "failed"
    """
    if not mint_address:
        return {
            "level": LEVEL_UNKNOWN,
            "top10_percent": None,
            "reason": "Empty address",
            "source": "failed"
        }
    
    # Try RPC first
    rpc_holders = _get_holders_from_rpc(mint_address, verbose=verbose)
    
    if rpc_holders and len(rpc_holders) > 0:
        # Calculate top 10 concentration from RPC response
        # RPC returns amounts, need to calculate percentages
        try:
            # Get total supply from sum of all returned holders (approximation)
            # or use provided token_supply
            total_amount = 0
            top10_amounts = []
            
            for i, holder in enumerate(rpc_holders[:10]):
                amount_str = holder.get("amount", "0")
                amount = float(amount_str) if amount_str else 0
                top10_amounts.append(amount)
                if i < 20:  # Sum all returned (up to 20)
                    total_amount += float(holder.get("amount", "0") or 0)
            
            # Sum all holders for total approximation
            all_amounts = sum(float(h.get("amount", "0") or 0) for h in rpc_holders)
            
            if all_amounts > 0:
                top10_sum = sum(top10_amounts)
                top10_percent = (top10_sum / all_amounts) * 100
                
                if verbose:
                    print(f"  {Fore.WHITE}📊 Top 10 holders: {top10_percent:.1f}% of supply{Style.RESET_ALL}")
                
                if top10_percent > config.MAX_TOP10_HOLDER_PERCENT:
                    level = LEVEL_DANGER
                    reason = f"Top 10 holders control {top10_percent:.1f}% (threshold: {config.MAX_TOP10_HOLDER_PERCENT}%)"
                    if verbose:
                        print(f"  {Fore.RED}🚨 {reason}{Style.RESET_ALL}")
                else:
                    level = LEVEL_OK
                    reason = f"Top 10 holders: {top10_percent:.1f}% (below threshold)"
                    if verbose:
                        print(f"  {Fore.GREEN}✅ {reason}{Style.RESET_ALL}")
                
                return {
                    "level": level,
                    "top10_percent": round(top10_percent, 2),
                    "reason": reason,
                    "source": "rpc"
                }
        except Exception as e:
            if verbose:
                print(f"  {Fore.YELLOW}⚠️  Error calculating RPC holders: {e}{Style.RESET_ALL}")
    
    # Fallback to RugCheck
    rugcheck_holders = _get_holders_from_rugcheck(mint_address, verbose=verbose)
    
    if rugcheck_holders and len(rugcheck_holders) > 0:
        try:
            # RugCheck provides percentage directly in "pct" field
            top10_percent = 0.0
            for i, holder in enumerate(rugcheck_holders[:10]):
                pct = holder.get("pct", 0) or 0
                # pct might be 0-1 or 0-100, normalize
                if pct > 0 and pct <= 1:
                    pct = pct * 100
                top10_percent += pct
            
            if verbose:
                print(f"  {Fore.WHITE}📊 Top 10 holders: {top10_percent:.1f}% (via RugCheck){Style.RESET_ALL}")
            
            if top10_percent > config.MAX_TOP10_HOLDER_PERCENT:
                level = LEVEL_DANGER
                reason = f"Top 10 holders control {top10_percent:.1f}% (threshold: {config.MAX_TOP10_HOLDER_PERCENT}%)"
                if verbose:
                    print(f"  {Fore.RED}🚨 {reason}{Style.RESET_ALL}")
            else:
                level = LEVEL_OK
                reason = f"Top 10 holders: {top10_percent:.1f}% (below threshold)"
                if verbose:
                    print(f"  {Fore.GREEN}✅ {reason}{Style.RESET_ALL}")
            
            return {
                "level": level,
                "top10_percent": round(top10_percent, 2),
                "reason": reason,
                "source": "rugcheck"
            }
        except Exception as e:
            if verbose:
                print(f"  {Fore.YELLOW}⚠️  Error calculating RugCheck holders: {e}{Style.RESET_ALL}")
    
    # Both sources failed
    return {
        "level": LEVEL_UNKNOWN,
        "top10_percent": None,
        "reason": "Could not fetch holder data from RPC or RugCheck",
        "source": "failed"
    }


# =============================================================================
# HONEYPOT DETECTION
# =============================================================================

@rate_limit_dexscreener
def _get_token_data_from_dexscreener(mint_address: str, verbose: bool = True) -> Optional[Dict]:
    """
    Fetch token data from DexScreener API.
    
    Args:
        mint_address: The token's mint address.
        verbose: If True, print status messages.
        
    Returns:
        Token data dict from DexScreener, or None on failure.
    """
    try:
        url = DEXSCREENER_TOKEN_URL.format(mint_address=mint_address)
        response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        
        data = response.json()
        
        # DexScreener returns array of pairs, get first one
        if isinstance(data, list) and len(data) > 0:
            return data[0]
        elif isinstance(data, dict):
            pairs = data.get("pairs", [])
            if pairs and len(pairs) > 0:
                return pairs[0]
        
        if verbose:
            print(f"  {Fore.YELLOW}⚠️  No DexScreener data for token{Style.RESET_ALL}")
        return None
        
    except requests.exceptions.Timeout:
        if verbose:
            print(f"  {Fore.YELLOW}⏱️  DexScreener timeout{Style.RESET_ALL}")
        return None
    except requests.exceptions.RequestException as e:
        if verbose:
            print(f"  {Fore.YELLOW}⚠️  DexScreener error: {e}{Style.RESET_ALL}")
        return None
    except Exception as e:
        if verbose:
            print(f"  {Fore.YELLOW}⚠️  DexScreener unexpected error: {e}{Style.RESET_ALL}")
        return None


def check_honeypot(token_data: Optional[Dict] = None, mint_address: Optional[str] = None, verbose: bool = True) -> Dict[str, Any]:
    """
    Check if token is a honeypot using DexScreener txns data.
    
    A honeypot is detected when:
    - There are buys but ZERO sells in the last 1 hour
    
    Args:
        token_data: Pre-fetched DexScreener token data (optional).
        mint_address: Token mint address (used if token_data not provided).
        verbose: If True, print status messages.
        
    Returns:
        Dict with keys:
        - level: DANGER, WARNING, OK, or UNKNOWN
        - h1_buys: Number of buys in 1h
        - h1_sells: Number of sells in 1h
        - reason: Human-readable explanation
    """
    # Fetch data if not provided
    if token_data is None and mint_address:
        token_data = _get_token_data_from_dexscreener(mint_address, verbose=verbose)
    
    if not token_data:
        return {
            "level": LEVEL_UNKNOWN,
            "h1_buys": None,
            "h1_sells": None,
            "reason": "Could not fetch DexScreener data"
        }
    
    try:
        txns = token_data.get("txns", {})
        h1 = txns.get("h1", {})
        
        h1_buys = h1.get("buys", 0) or 0
        h1_sells = h1.get("sells", 0) or 0
        
        if verbose:
            print(f"  {Fore.WHITE}📈 1h Transactions: {h1_buys} buys, {h1_sells} sells{Style.RESET_ALL}")
        
        # Honeypot detection: buys > 0 but sells = 0
        if h1_buys > 0 and h1_sells == 0:
            level = LEVEL_DANGER
            reason = f"HONEYPOT DETECTED: {h1_buys} buys but 0 sells in 1h"
            if verbose:
                print(f"  {Fore.RED}🚨 {reason}{Style.RESET_ALL}")
        elif h1_sells > 0 and h1_buys == 0:
            # Only sells, no buys - could be dumping
            level = LEVEL_WARNING
            reason = f"Suspicious: 0 buys but {h1_sells} sells in 1h (possible dump)"
            if verbose:
                print(f"  {Fore.YELLOW}⚠️  {reason}{Style.RESET_ALL}")
        elif h1_buys == 0 and h1_sells == 0:
            level = LEVEL_WARNING
            reason = "No trading activity in 1h"
            if verbose:
                print(f"  {Fore.YELLOW}⚠️  {reason}{Style.RESET_ALL}")
        else:
            level = LEVEL_OK
            reason = f"Normal trading: {h1_buys} buys, {h1_sells} sells in 1h"
            if verbose:
                print(f"  {Fore.GREEN}✅ {reason}{Style.RESET_ALL}")
        
        return {
            "level": level,
            "h1_buys": h1_buys,
            "h1_sells": h1_sells,
            "reason": reason
        }
        
    except Exception as e:
        if verbose:
            print(f"  {Fore.YELLOW}⚠️  Error checking honeypot: {e}{Style.RESET_ALL}")
        return {
            "level": LEVEL_UNKNOWN,
            "h1_buys": None,
            "h1_sells": None,
            "reason": f"Error: {str(e)[:50]}"
        }


# =============================================================================
# BUNDLED TRANSACTION DETECTION
# =============================================================================

def check_bundled_transactions(
    token_data: Optional[Dict] = None,
    mint_address: Optional[str] = None,
    verbose: bool = True
) -> Dict[str, Any]:
    """
    Heuristic check for bundled/cabal transactions.
    
    Detects suspicious patterns indicating coordinated launch:
    - Token age < 1 hour AND holder count < 20
    
    This is a simplified heuristic, not full graph analysis.
    
    Args:
        token_data: Pre-fetched DexScreener token data (optional).
        mint_address: Token mint address (used if token_data not provided).
        verbose: If True, print status messages.
        
    Returns:
        Dict with keys:
        - level: DANGER, WARNING, OK, or UNKNOWN
        - token_age_hours: Age of token in hours (if available)
        - holder_count: Number of holders (if available, from txns)
        - reason: Human-readable explanation
    """
    # Fetch data if not provided
    if token_data is None and mint_address:
        token_data = _get_token_data_from_dexscreener(mint_address, verbose=verbose)
    
    if not token_data:
        return {
            "level": LEVEL_UNKNOWN,
            "token_age_hours": None,
            "holder_count": None,
            "reason": "Could not fetch token data"
        }
    
    try:
        # Get token creation time
        pair_created_at = token_data.get("pairCreatedAt")
        
        token_age_hours = None
        if pair_created_at:
            # pairCreatedAt is Unix timestamp in milliseconds
            created_time = datetime.fromtimestamp(pair_created_at / 1000)
            now = datetime.now()
            age_delta = now - created_time
            token_age_hours = age_delta.total_seconds() / 3600
        
        # Estimate holder count from transactions (heuristic)
        # A rough estimate: unique buyers in 24h as proxy for holders
        txns = token_data.get("txns", {})
        h24 = txns.get("h24", {})
        h24_buys = h24.get("buys", 0) or 0
        
        # Very rough estimate: assume ~50% of buys are unique holders
        estimated_holders = max(h24_buys // 2, h24_buys if h24_buys < 50 else 0)
        
        # Also check h1 for very new tokens
        h1 = txns.get("h1", {})
        h1_buys = h1.get("buys", 0) or 0
        
        if verbose and token_age_hours is not None:
            print(f"  {Fore.WHITE}⏰ Token age: {token_age_hours:.2f} hours, ~{max(estimated_holders, h1_buys)} holders (est.){Style.RESET_ALL}")
        
        # Bundled detection heuristic:
        # Token age < 1 hour AND very few unique buyers
        is_very_new = token_age_hours is not None and token_age_hours < 1.0
        has_few_holders = h1_buys < 20
        
        if is_very_new and has_few_holders:
            level = LEVEL_DANGER
            reason = f"Bundled TX risk: Token is {token_age_hours:.2f}h old with only {h1_buys} buyers"
            if verbose:
                print(f"  {Fore.RED}🚨 {reason}{Style.RESET_ALL}")
        elif is_very_new:
            level = LEVEL_WARNING
            reason = f"Very new token ({token_age_hours:.2f}h), proceed with caution"
            if verbose:
                print(f"  {Fore.YELLOW}⚠️  {reason}{Style.RESET_ALL}")
        elif has_few_holders and token_age_hours is not None and token_age_hours < 6:
            level = LEVEL_WARNING
            reason = f"Low holder count ({h1_buys}) for token age ({token_age_hours:.2f}h)"
            if verbose:
                print(f"  {Fore.YELLOW}⚠️  {reason}{Style.RESET_ALL}")
        else:
            level = LEVEL_OK
            reason = "No bundled transaction indicators detected"
            if verbose:
                print(f"  {Fore.GREEN}✅ {reason}{Style.RESET_ALL}")
        
        return {
            "level": level,
            "token_age_hours": round(token_age_hours, 2) if token_age_hours else None,
            "holder_count": h1_buys,  # Using h1 buys as proxy
            "reason": reason
        }
        
    except Exception as e:
        if verbose:
            print(f"  {Fore.YELLOW}⚠️  Error checking bundled tx: {e}{Style.RESET_ALL}")
        return {
            "level": LEVEL_UNKNOWN,
            "token_age_hours": None,
            "holder_count": None,
            "reason": f"Error: {str(e)[:50]}"
        }


# =============================================================================
# COMPREHENSIVE SECURITY CHECK
# =============================================================================

def comprehensive_security_check(
    mint_address: str,
    token_data: Optional[Dict] = None,
    verbose: bool = True
) -> Dict[str, Any]:
    """
    Run all security checks and aggregate results.
    
    Tiered validation order:
    1. RugCheck basic check (existing check_security)
    2. Holder concentration check (RPC or RugCheck topHolders)
    3. Honeypot detection (DexScreener txns)
    4. Bundled transaction detection (heuristic)
    
    Args:
        mint_address: The token's mint address.
        token_data: Pre-fetched DexScreener data (optional, will fetch if needed).
        verbose: If True, print status messages.
        
    Returns:
        Dict with keys:
        - is_safe: Boolean overall assessment
        - overall_level: DANGER, WARNING, or OK
        - safety_score: 0-100 score (higher = safer)
        - rugcheck: Result from check_security
        - holder_concentration: Result from check_holder_concentration
        - honeypot: Result from check_honeypot
        - bundled_tx: Result from check_bundled_transactions
        - danger_flags: List of danger-level issues
        - warning_flags: List of warning-level issues
    """
    if verbose:
        print(f"\n{Fore.CYAN}{'─'*50}")
        print(f"🛡️  COMPREHENSIVE SECURITY CHECK")
        print(f"{'─'*50}{Style.RESET_ALL}")
        print(f"Token: {Fore.YELLOW}{mint_address[:30]}...{Style.RESET_ALL}\n")
    
    results = {
        "is_safe": True,
        "overall_level": LEVEL_OK,
        "safety_score": 100,
        "rugcheck": {},
        "holder_concentration": {},
        "honeypot": {},
        "bundled_tx": {},
        "danger_flags": [],
        "warning_flags": []
    }
    
    # Fetch DexScreener data once for reuse
    if token_data is None:
        if verbose:
            print(f"{Fore.WHITE}📡 Fetching DexScreener data...{Style.RESET_ALL}")
        token_data = _get_token_data_from_dexscreener(mint_address, verbose=verbose)
    
    # Tier 1: RugCheck basic check
    if verbose:
        print(f"\n{Fore.WHITE}[1/4] RugCheck Security Scan{Style.RESET_ALL}")
    is_safe_rc, reason_rc = check_security(mint_address, verbose=verbose)
    results["rugcheck"] = {"is_safe": is_safe_rc, "reason": reason_rc}
    
    if not is_safe_rc:
        results["danger_flags"].append(f"RugCheck: {reason_rc}")
        results["safety_score"] -= 35
    
    # Tier 2: Holder concentration check
    if verbose:
        print(f"\n{Fore.WHITE}[2/4] Holder Concentration Analysis{Style.RESET_ALL}")
    holder_result = check_holder_concentration(mint_address, verbose=verbose)
    results["holder_concentration"] = holder_result
    
    if holder_result["level"] == LEVEL_DANGER:
        results["danger_flags"].append(holder_result["reason"])
        results["safety_score"] -= 30
    elif holder_result["level"] == LEVEL_WARNING:
        results["warning_flags"].append(holder_result["reason"])
        results["safety_score"] -= 10
    
    # Tier 3: Honeypot detection
    if verbose:
        print(f"\n{Fore.WHITE}[3/4] Honeypot Detection{Style.RESET_ALL}")
    honeypot_result = check_honeypot(token_data=token_data, verbose=verbose)
    results["honeypot"] = honeypot_result
    
    if honeypot_result["level"] == LEVEL_DANGER:
        results["danger_flags"].append(honeypot_result["reason"])
        results["safety_score"] -= 40  # Honeypot is very serious
    elif honeypot_result["level"] == LEVEL_WARNING:
        results["warning_flags"].append(honeypot_result["reason"])
        results["safety_score"] -= 15
    
    # Tier 4: Bundled transaction detection
    if verbose:
        print(f"\n{Fore.WHITE}[4/4] Bundled Transaction Check{Style.RESET_ALL}")
    bundled_result = check_bundled_transactions(token_data=token_data, verbose=verbose)
    results["bundled_tx"] = bundled_result
    
    if bundled_result["level"] == LEVEL_DANGER:
        results["danger_flags"].append(bundled_result["reason"])
        results["safety_score"] -= 25
    elif bundled_result["level"] == LEVEL_WARNING:
        results["warning_flags"].append(bundled_result["reason"])
        results["safety_score"] -= 10
    
    # Calculate overall level
    if len(results["danger_flags"]) > 0:
        results["overall_level"] = LEVEL_DANGER
        results["is_safe"] = False
    elif len(results["warning_flags"]) > 0:
        results["overall_level"] = LEVEL_WARNING
        # Still safe but with caution
        results["is_safe"] = True
    else:
        results["overall_level"] = LEVEL_OK
        results["is_safe"] = True
    
    # Clamp safety score
    results["safety_score"] = max(0, min(100, results["safety_score"]))
    
    # Print summary
    if verbose:
        print(f"\n{Fore.CYAN}{'─'*50}")
        print(f"📊 SECURITY SUMMARY")
        print(f"{'─'*50}{Style.RESET_ALL}")
        
        level_color = Fore.GREEN if results["overall_level"] == LEVEL_OK else (
            Fore.YELLOW if results["overall_level"] == LEVEL_WARNING else Fore.RED
        )
        print(f"Overall: {level_color}{results['overall_level']}{Style.RESET_ALL}")
        print(f"Safety Score: {results['safety_score']}/100")
        
        if results["danger_flags"]:
            print(f"\n{Fore.RED}🚨 DANGER FLAGS:{Style.RESET_ALL}")
            for flag in results["danger_flags"]:
                print(f"  • {flag}")
        
        if results["warning_flags"]:
            print(f"\n{Fore.YELLOW}⚠️  WARNING FLAGS:{Style.RESET_ALL}")
            for flag in results["warning_flags"]:
                print(f"  • {flag}")
        
        print(f"\n{Fore.CYAN}{'─'*50}{Style.RESET_ALL}\n")
    
    return results


# =============================================================================
# TESTING
# =============================================================================
if __name__ == "__main__":
    print(f"\n{Fore.CYAN}{'='*60}")
    print(f"🛡️  SHIELD MODULE - Enhanced Security Check Test")
    print(f"{'='*60}{Style.RESET_ALL}\n")
    
    # Test token - use a well-known token for testing
    test_mint = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"  # USDC
    
    print(f"{Fore.WHITE}Testing with: {Fore.YELLOW}{test_mint}{Style.RESET_ALL}\n")
    
    # Test 1: Basic RugCheck
    print(f"\n{Fore.CYAN}--- Test 1: Basic RugCheck ---{Style.RESET_ALL}")
    is_safe, reason = check_security(test_mint, verbose=True)
    print(f"Result: {'SAFE' if is_safe else 'RISKY'} - {reason}")
    
    # Test 2: Holder Concentration
    print(f"\n{Fore.CYAN}--- Test 2: Holder Concentration ---{Style.RESET_ALL}")
    holder_result = check_holder_concentration(test_mint, verbose=True)
    print(f"Level: {holder_result['level']}, Top10%: {holder_result['top10_percent']}")
    
    # Test 3: Honeypot Detection  
    print(f"\n{Fore.CYAN}--- Test 3: Honeypot Detection ---{Style.RESET_ALL}")
    honeypot_result = check_honeypot(mint_address=test_mint, verbose=True)
    print(f"Level: {honeypot_result['level']}, Buys: {honeypot_result['h1_buys']}, Sells: {honeypot_result['h1_sells']}")
    
    # Test 4: Bundled Transaction Check
    print(f"\n{Fore.CYAN}--- Test 4: Bundled TX Check ---{Style.RESET_ALL}")
    bundled_result = check_bundled_transactions(mint_address=test_mint, verbose=True)
    print(f"Level: {bundled_result['level']}, Age: {bundled_result['token_age_hours']}h")
    
    # Test 5: Comprehensive Security Check
    print(f"\n{Fore.CYAN}--- Test 5: Comprehensive Security Check ---{Style.RESET_ALL}")
    full_result = comprehensive_security_check(test_mint, verbose=True)
    print(f"\nFinal Result:")
    print(f"  Is Safe: {full_result['is_safe']}")
    print(f"  Overall Level: {full_result['overall_level']}")
    print(f"  Safety Score: {full_result['safety_score']}/100")
    print(f"  Danger Flags: {len(full_result['danger_flags'])}")
    print(f"  Warning Flags: {len(full_result['warning_flags'])}")
    
    print(f"\n{Fore.CYAN}{'='*60}")
    print(f"All Tests Complete!")
    print(f"{'='*60}{Style.RESET_ALL}\n")
