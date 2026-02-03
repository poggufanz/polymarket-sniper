"""
Clone Detector Module - Token Clone Detection
==============================================
Detects clone tokens using fuzzy name matching against DexScreener search.

Uses fuzzywuzzy token_set_ratio to compare token names and identify
potential clones/copies of existing tokens.

Enhanced with:
- DexScreener search integration
- Fuzzy matching with configurable threshold
- Clone similarity scoring
"""

import requests
from typing import Dict, Any, Optional, List
from colorama import init, Fore, Style

from rate_limiter import rate_limit_dexscreener
import config

# Initialize colorama
init(autoreset=True)

# Constants
DEXSCREENER_SEARCH_URL = "https://api.dexscreener.com/latest/dex/search"
REQUEST_TIMEOUT_SECONDS = config.API_TIMEOUT_SECONDS

# Import fuzzywuzzy (graceful degradation if not available)
try:
    from fuzzywuzzy import fuzz
    FUZZYWUZZY_AVAILABLE = True
except ImportError:
    FUZZYWUZZY_AVAILABLE = False
    fuzz = None
    print(f"{Fore.YELLOW}WARNING: fuzzywuzzy not installed. Clone detection will be disabled.{Style.RESET_ALL}")
    print(f"{Fore.YELLOW}   Install with: pip install fuzzywuzzy python-Levenshtein{Style.RESET_ALL}")


# Risk levels from shield module
LEVEL_DANGER = "DANGER"
LEVEL_WARNING = "WARNING"
LEVEL_OK = "OK"
LEVEL_UNKNOWN = "UNKNOWN"


@rate_limit_dexscreener
def _search_dexscreener(query: str, verbose: bool = False) -> Optional[List[Dict]]:
    """
    Search DexScreener for tokens matching the query.
    
    Args:
        query: Token name or symbol to search for.
        verbose: If True, print status messages.
        
    Returns:
        List of token pairs from DexScreener, or None on failure.
    """
    try:
        params = {"q": query}
        response = requests.get(
            DEXSCREENER_SEARCH_URL,
            params=params,
            timeout=REQUEST_TIMEOUT_SECONDS
        )
        response.raise_for_status()
        
        data = response.json()
        pairs = data.get("pairs", [])
        
        if verbose and pairs:
            print(f"  {Fore.WHITE}DexScreener found {len(pairs)} matching pairs{Style.RESET_ALL}")
        
        return pairs
        
    except requests.exceptions.Timeout:
        if verbose:
            print(f"  {Fore.YELLOW}⏱️  DexScreener search timeout{Style.RESET_ALL}")
        return None
    except requests.exceptions.RequestException as e:
        if verbose:
            print(f"  {Fore.YELLOW}⚠️  DexScreener search error: {e}{Style.RESET_ALL}")
        return None
    except Exception as e:
        if verbose:
            print(f"  {Fore.YELLOW}⚠️  Unexpected error: {e}{Style.RESET_ALL}")
        return None


def _calculate_similarity(name1: str, name2: str) -> int:
    """
    Calculate similarity score between two token names using fuzzy matching.
    
    Uses fuzzywuzzy token_set_ratio which handles:
    - Word order differences
    - Extra/missing words
    - Case insensitivity
    
    Args:
        name1: First token name.
        name2: Second token name.
        
    Returns:
        Similarity score 0-100 (100 = exact match).
    """
    if not FUZZYWUZZY_AVAILABLE:
        # Fallback to simple case-insensitive string comparison
        return 100 if name1.lower() == name2.lower() else 0
    
    return fuzz.token_set_ratio(name1, name2)


def check_clone_token(
    symbol: str,
    name: str,
    mint_address: str,
    verbose: bool = True
) -> Dict[str, Any]:
    """
    Check if a token is a clone of an existing token using DexScreener search.
    
    Searches DexScreener for tokens with similar names, then uses fuzzy matching
    to calculate similarity scores. Flags tokens that exceed the similarity threshold
    as potential clones.
    
    Args:
        symbol: Token symbol (e.g., "TRUMP").
        name: Token full name (e.g., "Trump Victory Token").
        mint_address: Token mint address (to exclude self from results).
        verbose: If True, print status messages.
        
    Returns:
        Dict with keys:
        - level: DANGER, WARNING, OK, or UNKNOWN
        - reason: Human-readable explanation
        - is_clone: Boolean indicating if clone detected
        - clone_of: Name of original token (if clone detected)
        - similarity_score: Highest similarity score found (0-100)
        - matches: List of similar tokens found
    """
    if not symbol or not name:
        return {
            "level": LEVEL_UNKNOWN,
            "reason": "Empty symbol or name",
            "is_clone": False,
            "clone_of": None,
            "similarity_score": 0,
            "matches": []
        }
    
    if not FUZZYWUZZY_AVAILABLE:
        return {
            "level": LEVEL_UNKNOWN,
            "reason": "fuzzywuzzy not installed",
            "is_clone": False,
            "clone_of": None,
            "similarity_score": 0,
            "matches": []
        }
    
    if verbose:
        print(f"  {Fore.WHITE}Searching for clones of '{name}' ({symbol})...{Style.RESET_ALL}")
    
    # Search DexScreener for tokens with similar names
    # Try searching by both name and symbol for better coverage
    search_results = _search_dexscreener(name, verbose=verbose)
    
    if not search_results:
        # Try searching by symbol as fallback
        search_results = _search_dexscreener(symbol, verbose=verbose)
    
    if not search_results:
        return {
            "level": LEVEL_UNKNOWN,
            "reason": "Could not fetch DexScreener search results",
            "is_clone": False,
            "clone_of": None,
            "similarity_score": 0,
            "matches": []
        }
    
    # Analyze similarity scores for each result
    matches = []
    highest_similarity = 0
    clone_of = None
    
    for pair in search_results[:10]:  # Check top 10 results only
        try:
            base_token = pair.get("baseToken", {})
            pair_address = base_token.get("address", "")
            pair_name = base_token.get("name", "")
            pair_symbol = base_token.get("symbol", "")
            
            # Skip if it's the same token (same mint address)
            if pair_address.lower() == mint_address.lower():
                continue
            
            # Skip if no name available
            if not pair_name:
                continue
            
            # Calculate similarity using token_set_ratio
            name_similarity = _calculate_similarity(name, pair_name)
            symbol_similarity = _calculate_similarity(symbol, pair_symbol)
            
            # Use the higher of name or symbol similarity
            similarity = max(name_similarity, symbol_similarity)
            
            # Track matches above 50% similarity
            if similarity >= 50:
                matches.append({
                    "name": pair_name,
                    "symbol": pair_symbol,
                    "address": pair_address,
                    "similarity": similarity
                })
                
                if verbose:
                    print(f"    {Fore.YELLOW}Similar: {pair_name} ({pair_symbol}) - {similarity}% match{Style.RESET_ALL}")
            
            # Track highest similarity
            if similarity > highest_similarity:
                highest_similarity = similarity
                clone_of = f"{pair_name} ({pair_symbol})"
        
        except Exception as e:
            if verbose:
                print(f"  {Fore.YELLOW}⚠️  Error analyzing pair: {e}{Style.RESET_ALL}")
            continue
    
    # Determine if it's a clone based on threshold
    is_clone = highest_similarity >= config.CLONE_SIMILARITY_THRESHOLD
    
    if is_clone:
        level = LEVEL_WARNING  # Clone detection is WARNING, not DANGER
        reason = f"Possible clone detected: {highest_similarity}% similar to '{clone_of}'"
        if verbose:
            print(f"  {Fore.YELLOW}WARNING: {reason}{Style.RESET_ALL}")
    elif highest_similarity >= 50:
        level = LEVEL_WARNING
        reason = f"Moderate similarity ({highest_similarity}%) to existing token '{clone_of}'"
        if verbose:
            print(f"  {Fore.YELLOW}WARNING: {reason}{Style.RESET_ALL}")
    else:
        level = LEVEL_OK
        reason = f"No clones detected (highest similarity: {highest_similarity}%)"
        if verbose:
            print(f"  {Fore.GREEN}OK: {reason}{Style.RESET_ALL}")
    
    return {
        "level": level,
        "reason": reason,
        "is_clone": is_clone,
        "clone_of": clone_of,
        "similarity_score": highest_similarity,
        "matches": matches
    }


# =============================================================================
# TESTING
# =============================================================================
if __name__ == "__main__":
    print(f"\n{Fore.CYAN}{'='*60}")
    print(f"CLONE DETECTOR MODULE - Test")
    print(f"{'='*60}{Style.RESET_ALL}\n")
    
    # Test 1: Well-known token (should not be a clone)
    print(f"\n{Fore.CYAN}--- Test 1: USDC (should not be clone) ---{Style.RESET_ALL}")
    result1 = check_clone_token(
        symbol="USDC",
        name="USD Coin",
        mint_address="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        verbose=True
    )
    print(f"Result: {result1['level']} - {result1['reason']}")
    print(f"Is Clone: {result1['is_clone']}, Similarity: {result1['similarity_score']}%")
    
    # Test 2: Generic token name (likely to find similar tokens)
    print(f"\n{Fore.CYAN}--- Test 2: Generic 'Trump' token ---{Style.RESET_ALL}")
    result2 = check_clone_token(
        symbol="TRUMP",
        name="Trump Token",
        mint_address="FakeAddress123456789",
        verbose=True
    )
    print(f"Result: {result2['level']} - {result2['reason']}")
    print(f"Is Clone: {result2['is_clone']}, Similarity: {result2['similarity_score']}%")
    print(f"Matches found: {len(result2['matches'])}")
    
    # Test 3: Empty input
    print(f"\n{Fore.CYAN}--- Test 3: Empty input ---{Style.RESET_ALL}")
    result3 = check_clone_token(
        symbol="",
        name="",
        mint_address="",
        verbose=True
    )
    print(f"Result: {result3['level']} - {result3['reason']}")
    
    print(f"\n{Fore.CYAN}{'='*60}")
    print(f"All Tests Complete!")
    print(f"{'='*60}{Style.RESET_ALL}\n")
