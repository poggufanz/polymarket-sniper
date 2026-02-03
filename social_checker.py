"""
Social Media Presence Checker Module
====================================

This module analyzes the social media presence of tokens to assess their
legitimacy and community engagement. Tokens with minimal or no social presence
are often higher-risk projects.

Key Function:
- check_social_presence(token_data): Evaluate social media presence
"""

from typing import Dict, Any, Optional
from colorama import init, Fore, Style

# Initialize colorama
init(autoreset=True)

# Risk levels
LEVEL_DANGER = "DANGER"
LEVEL_WARNING = "WARNING"
LEVEL_OK = "OK"
LEVEL_UNKNOWN = "UNKNOWN"


def check_social_presence(token_data: Dict[str, Any], verbose: bool = True) -> Dict[str, Any]:
    """
    Check social media presence of a token.
    
    Evaluates the token's social presence by checking for:
    - Twitter/X
    - Telegram
    - Discord
    - Website
    
    A token with zero social presence indicates higher risk (new/rug pull potential).
    A token with 1+ social links indicates established presence.
    
    Args:
        token_data: Token data from DexScreener API response containing socials info
        verbose: If True, print status messages using colorama
        
    Returns:
        Dict with keys:
        - level: LEVEL_WARNING if social_count == 0, LEVEL_OK if social_count >= 1
        - reason: Human-readable explanation
        - has_twitter: Boolean indicating Twitter presence
        - has_telegram: Boolean indicating Telegram presence
        - has_discord: Boolean indicating Discord presence
        - has_website: Boolean indicating Website presence
        - social_count: Total count of social links found
        
    Example:
        >>> token_data = {
        ...     "info": {
        ...         "socials": [
        ...             {"type": "twitter", "url": "https://twitter.com/..."},
        ...             {"type": "telegram", "url": "https://t.me/..."},
        ...         ]
        ...     }
        ... }
        >>> result = check_social_presence(token_data)
        >>> result["level"]
        'OK'
        >>> result["social_count"]
        2
    """
    try:
        # Extract socials from token data
        info = token_data.get("info", {})
        socials = info.get("socials", [])
        
        if not isinstance(socials, list):
            if verbose:
                print(f"  {Fore.YELLOW}[WARNING] Socials not in expected format{Style.RESET_ALL}")
            return {
                "level": LEVEL_UNKNOWN,
                "reason": "Socials data unavailable",
                "has_twitter": False,
                "has_telegram": False,
                "has_discord": False,
                "has_website": False,
                "social_count": 0
            }
        
        # Check for each social type
        has_twitter = False
        has_telegram = False
        has_discord = False
        has_website = False
        
        for social in socials:
            if not isinstance(social, dict):
                continue
            
            social_type = social.get("type", "").lower()
            url = social.get("url", "")
            
            # Only count if URL is present and non-empty
            if not url:
                continue
            
            if social_type == "twitter" or social_type == "x":
                has_twitter = True
            elif social_type == "telegram":
                has_telegram = True
            elif social_type == "discord":
                has_discord = True
            elif social_type == "website":
                has_website = True
        
        # Calculate total social count
        social_count = sum([has_twitter, has_telegram, has_discord, has_website])
        
        # Determine risk level
        if social_count == 0:
            level = LEVEL_WARNING
            reason = "No social media presence detected - higher risk"
            if verbose:
                print(f"  {Fore.YELLOW}[WARNING] {reason}{Style.RESET_ALL}")
        else:
            level = LEVEL_OK
            socials_found = []
            if has_twitter:
                socials_found.append("Twitter")
            if has_telegram:
                socials_found.append("Telegram")
            if has_discord:
                socials_found.append("Discord")
            if has_website:
                socials_found.append("Website")
            
            reason = f"Social presence confirmed: {', '.join(socials_found)}"
            if verbose:
                print(f"  {Fore.GREEN}[OK] {reason}{Style.RESET_ALL}")
        
        return {
            "level": level,
            "reason": reason,
            "has_twitter": has_twitter,
            "has_telegram": has_telegram,
            "has_discord": has_discord,
            "has_website": has_website,
            "social_count": social_count
        }
        
    except Exception as e:
        if verbose:
            print(f"  {Fore.YELLOW}[ERROR] Error checking social presence: {e}{Style.RESET_ALL}")
        
        return {
            "level": LEVEL_UNKNOWN,
            "reason": f"Error: {str(e)[:50]}",
            "has_twitter": False,
            "has_telegram": False,
            "has_discord": False,
            "has_website": False,
            "social_count": 0
        }


# =============================================================================
# TESTING
# =============================================================================

if __name__ == "__main__":
    print(f"\n{Fore.CYAN}{'='*60}")
    print(f"SOCIAL CHECKER MODULE - Test")
    print(f"{'='*60}{Style.RESET_ALL}\n")
    
    # Test 1: Token with no social presence
    print(f"{Fore.CYAN}--- Test 1: No Social Presence ---{Style.RESET_ALL}")
    token_data_no_socials = {
        "info": {
            "socials": []
        }
    }
    result = check_social_presence(token_data_no_socials, verbose=True)
    print(f"Level: {result['level']}, Count: {result['social_count']}\n")
    
    # Test 2: Token with multiple social links
    print(f"{Fore.CYAN}--- Test 2: Multiple Social Presence ---{Style.RESET_ALL}")
    token_data_with_socials = {
        "info": {
            "socials": [
                {"type": "twitter", "url": "https://twitter.com/example"},
                {"type": "telegram", "url": "https://t.me/example"},
                {"type": "website", "url": "https://example.com"}
            ]
        }
    }
    result = check_social_presence(token_data_with_socials, verbose=True)
    print(f"Level: {result['level']}, Count: {result['social_count']}")
    print(f"Twitter: {result['has_twitter']}, Telegram: {result['has_telegram']}, Website: {result['has_website']}\n")
    
    # Test 3: Token with single social link
    print(f"{Fore.CYAN}--- Test 3: Single Social Presence ---{Style.RESET_ALL}")
    token_data_single_social = {
        "info": {
            "socials": [
                {"type": "twitter", "url": "https://twitter.com/example"}
            ]
        }
    }
    result = check_social_presence(token_data_single_social, verbose=True)
    print(f"Level: {result['level']}, Count: {result['social_count']}\n")
    
    # Test 4: Token with missing socials field
    print(f"{Fore.CYAN}--- Test 4: Missing Socials Field ---{Style.RESET_ALL}")
    token_data_missing_socials = {
        "info": {}
    }
    result = check_social_presence(token_data_missing_socials, verbose=True)
    print(f"Level: {result['level']}, Count: {result['social_count']}\n")
    
    # Test 5: Token with empty URLs
    print(f"{Fore.CYAN}--- Test 5: Empty Social URLs ---{Style.RESET_ALL}")
    token_data_empty_urls = {
        "info": {
            "socials": [
                {"type": "twitter", "url": ""},
                {"type": "telegram", "url": None}
            ]
        }
    }
    result = check_social_presence(token_data_empty_urls, verbose=True)
    print(f"Level: {result['level']}, Count: {result['social_count']}\n")
    
    print(f"{Fore.CYAN}{'='*60}")
    print(f"All Tests Complete!")
    print(f"{'='*60}{Style.RESET_ALL}\n")
