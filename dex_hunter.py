"""
DEX Hunter - Token Discovery Module
====================================
Searches DexScreener for potential "alpha" tokens based on
keywords extracted from Polymarket event titles.
"""

import time
import requests
from typing import Optional
from colorama import init, Fore, Style

# Initialize colorama
init(autoreset=True)

# Constants
DEXSCREENER_SEARCH_URL = "https://api.dexscreener.com/latest/dex/search"
REQUEST_TIMEOUT_SECONDS = 15
RATE_LIMIT_DELAY_SECONDS = 0.5

# Filter thresholds
MIN_LIQUIDITY_USD = 1000
MIN_VOLUME_24H_USD = 500
ALLOWED_CHAINS = {"solana", "base", "ethereum"}


def fetch_dex_results(keyword: str) -> Optional[list[dict]]:
    """
    Fetch token search results from DexScreener for a given keyword.
    
    Args:
        keyword: Search term to query.
        
    Returns:
        List of pair dictionaries, or None if request fails.
    """
    try:
        response = requests.get(
            DEXSCREENER_SEARCH_URL,
            params={"q": keyword},
            timeout=REQUEST_TIMEOUT_SECONDS
        )
        response.raise_for_status()
        data = response.json()
        return data.get("pairs", [])
    except requests.exceptions.RequestException as e:
        print(f"{Fore.RED}❌ DexScreener API Error for '{keyword}': {e}{Style.RESET_ALL}")
        return None


def apply_alpha_filter(pairs: list[dict]) -> list[dict]:
    """
    Apply the "Alpha" filter to remove low-quality tokens.
    
    Criteria:
    - liquidity.usd > 1000
    - volume.h24 > 500
    - chainId in ['solana', 'base', 'ethereum']
    
    Args:
        pairs: Raw list of pair data from DexScreener.
        
    Returns:
        Filtered list of pairs meeting alpha criteria.
    """
    filtered = []
    
    for pair in pairs:
        # Get chainId
        chain_id = pair.get("chainId", "").lower()
        if chain_id not in ALLOWED_CHAINS:
            continue
        
        # Get liquidity
        liquidity = pair.get("liquidity", {})
        liquidity_usd = liquidity.get("usd", 0) if isinstance(liquidity, dict) else 0
        try:
            liquidity_usd = float(liquidity_usd) if liquidity_usd else 0
        except (ValueError, TypeError):
            liquidity_usd = 0
        
        if liquidity_usd < MIN_LIQUIDITY_USD:
            continue
        
        # Get 24h volume
        volume = pair.get("volume", {})
        volume_24h = volume.get("h24", 0) if isinstance(volume, dict) else 0
        try:
            volume_24h = float(volume_24h) if volume_24h else 0
        except (ValueError, TypeError):
            volume_24h = 0
        
        if volume_24h < MIN_VOLUME_24H_USD:
            continue
        
        # Passed all filters
        filtered.append(pair)
    
    return filtered


def extract_token_info(pair: dict) -> dict:
    """
    Extract relevant token information from a pair dictionary.
    
    Args:
        pair: Raw pair data from DexScreener.
        
    Returns:
        Cleaned dictionary with essential token info.
    """
    base_token = pair.get("baseToken", {})
    liquidity = pair.get("liquidity", {})
    volume = pair.get("volume", {})
    
    return {
        "name": base_token.get("name", "Unknown"),
        "symbol": base_token.get("symbol", "???"),
        "address": base_token.get("address", ""),
        "chain": pair.get("chainId", "unknown"),
        "price_usd": pair.get("priceUsd", "0"),
        "liquidity_usd": liquidity.get("usd", 0) if isinstance(liquidity, dict) else 0,
        "volume_24h": volume.get("h24", 0) if isinstance(volume, dict) else 0,
        "fdv": pair.get("fdv", 0),
        "pair_created_at": pair.get("pairCreatedAt", 0),
        "url": pair.get("url", ""),
        "dex_id": pair.get("dexId", ""),
    }


def deduplicate_by_address(tokens: list[dict]) -> list[dict]:
    """
    Remove duplicate tokens by contract address.
    Keeps the first occurrence (highest priority).
    
    Args:
        tokens: List of token info dictionaries.
        
    Returns:
        Deduplicated list.
    """
    seen_addresses = set()
    unique_tokens = []
    
    for token in tokens:
        address = token.get("address", "").lower()
        if address and address not in seen_addresses:
            seen_addresses.add(address)
            unique_tokens.append(token)
    
    return unique_tokens


def search_potential_tokens(keywords: list[str]) -> list[dict]:
    """
    Search DexScreener for potential alpha tokens based on keywords.
    
    Workflow:
    1. Query DexScreener for each keyword
    2. Merge results (deduplicate by address)
    3. Apply alpha filters (liquidity, volume, chain)
    4. Sort by freshness (pairCreatedAt) or liquidity as fallback
    5. Return cleaned token info
    
    Args:
        keywords: List of keywords to search (e.g., ['MADURO', 'VENEZUELA']).
        
    Returns:
        List of filtered token dictionaries sorted by freshness.
    """
    all_pairs = []
    
    for keyword in keywords:
        print(f"{Fore.BLUE}🔍 Searching DexScreener for: {Fore.YELLOW}{keyword}{Style.RESET_ALL}")
        
        pairs = fetch_dex_results(keyword)
        
        if pairs:
            print(f"   {Fore.WHITE}Found {len(pairs)} raw pairs{Style.RESET_ALL}")
            all_pairs.extend(pairs)
        else:
            print(f"   {Fore.YELLOW}No results or API error{Style.RESET_ALL}")
        
        # Rate limit protection
        time.sleep(RATE_LIMIT_DELAY_SECONDS)
    
    # Apply alpha filter
    print(f"\n{Fore.CYAN}⚙️  Applying Alpha Filter...{Style.RESET_ALL}")
    print(f"   Criteria: Liquidity>${MIN_LIQUIDITY_USD}, Vol24h>${MIN_VOLUME_24H_USD}, Chains={ALLOWED_CHAINS}")
    
    filtered_pairs = apply_alpha_filter(all_pairs)
    print(f"   {Fore.GREEN}Passed filter: {len(filtered_pairs)} pairs{Style.RESET_ALL}")
    
    # Extract token info
    tokens = [extract_token_info(pair) for pair in filtered_pairs]
    
    # Deduplicate by address
    tokens = deduplicate_by_address(tokens)
    print(f"   {Fore.GREEN}After dedup: {len(tokens)} unique tokens{Style.RESET_ALL}")
    
    # Sort by freshness (pairCreatedAt descending), fallback to liquidity
    tokens.sort(key=lambda x: (
        -x.get("pair_created_at", 0),  # Primary: newest first
        -x.get("liquidity_usd", 0)     # Secondary: highest liquidity
    ))
    
    return tokens


def format_usd(value: float) -> str:
    """Format USD values with K/M suffix."""
    try:
        value = float(value)
    except (ValueError, TypeError):
        return "$0"
    
    if value >= 1_000_000:
        return f"${value / 1_000_000:.2f}M"
    elif value >= 1_000:
        return f"${value / 1_000:.1f}K"
    else:
        return f"${value:.0f}"


def display_tokens(tokens: list[dict], limit: int = 10) -> None:
    """
    Display tokens in a clean, colorized format.
    
    Args:
        tokens: List of token dictionaries.
        limit: Maximum number of tokens to display.
    """
    print(f"\n{Fore.CYAN}{'='*75}")
    print(f"🎯 POTENTIAL ALPHA TOKENS (Top {min(limit, len(tokens))})")
    print(f"{'='*75}{Style.RESET_ALL}\n")
    
    if not tokens:
        print(f"{Fore.YELLOW}No tokens found matching criteria.{Style.RESET_ALL}")
        return
    
    for idx, token in enumerate(tokens[:limit], start=1):
        chain_colors = {
            "solana": Fore.MAGENTA,
            "base": Fore.BLUE,
            "ethereum": Fore.CYAN,
        }
        chain_color = chain_colors.get(token["chain"], Fore.WHITE)
        
        print(f"{Fore.GREEN}#{idx:02d} {Fore.WHITE}{token['name']} ({Fore.YELLOW}{token['symbol']}{Fore.WHITE})")
        print(f"    {chain_color}Chain: {token['chain'].upper()}{Style.RESET_ALL}")
        print(f"    {Fore.WHITE}Price: {Fore.GREEN}${token['price_usd']}{Style.RESET_ALL}")
        print(f"    {Fore.WHITE}Liq: {Fore.CYAN}{format_usd(token['liquidity_usd'])}{Style.RESET_ALL} | Vol24h: {Fore.CYAN}{format_usd(token['volume_24h'])}{Style.RESET_ALL} | FDV: {format_usd(token['fdv'])}")
        print(f"    {Fore.BLUE}📋 {token['address'][:20]}...{Style.RESET_ALL}")
        if token["url"]:
            print(f"    {Fore.BLUE}🔗 {token['url']}{Style.RESET_ALL}")
        print()


# =============================================================================
# TESTING
# =============================================================================
if __name__ == "__main__":
    from brain import extract_keywords
    
    print(f"\n{Fore.CYAN}{'='*75}")
    print(f"🦎 DEX HUNTER - Token Discovery Test")
    print(f"{'='*75}{Style.RESET_ALL}\n")
    
    # Test with a mock Polymarket title
    test_title = "Will Nicolas Maduro resign?"
    
    print(f"{Fore.WHITE}Test Title: {Fore.YELLOW}\"{test_title}\"{Style.RESET_ALL}")
    
    # Extract keywords using brain module
    keywords = extract_keywords(test_title)
    print(f"{Fore.WHITE}Extracted Keywords: {Fore.CYAN}{keywords}{Style.RESET_ALL}\n")
    
    # Search for potential tokens
    tokens = search_potential_tokens(keywords)
    
    # Display top 5 results
    display_tokens(tokens, limit=5)
    
    print(f"{Fore.CYAN}{'='*75}")
    print(f"Test Complete!")
    print(f"{'='*75}{Style.RESET_ALL}\n")
