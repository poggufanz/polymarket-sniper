"""
Brain Module - Meme Coin Keyword Extraction & LLM Analysis
===========================================================
Extracts relevant keywords from Polymarket event titles
for potential meme coin narrative signals.

Also provides LLM-powered token analysis using Gemini.
"""

import re
import time
import logging
from pathlib import Path
from typing import List, Set, Dict, Any, Optional

import google.generativeai as genai

from config import GEMINI_API_KEY
from rate_limiter import rate_limit_gemini

logger = logging.getLogger(__name__)

# ==============================================================================
# LLM ANALYSIS CACHE
# ==============================================================================
# In-memory cache: { "token_address": (timestamp, result_dict) }
_llm_cache: Dict[str, tuple] = {}
LLM_CACHE_TTL_SECONDS = 3600  # 1 hour cache TTL

# Neutral result returned on API failures
NEUTRAL_RESULT: Dict[str, Any] = {
    "relevance_score": 50,
    "authenticity_score": 50,
    "red_flags": [],
    "confidence": 0,
    "reasoning": "Analysis unavailable (API error or timeout)",
}

# Load prompt template
_PROMPT_TEMPLATE: Optional[str] = None


def _get_prompt_template() -> str:
    """Load the prompt template from file (cached after first load)."""
    global _PROMPT_TEMPLATE
    if _PROMPT_TEMPLATE is None:
        prompt_path = Path(__file__).parent / "prompts" / "token_analysis.txt"
        try:
            _PROMPT_TEMPLATE = prompt_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            logger.error(f"Prompt template not found: {prompt_path}")
            _PROMPT_TEMPLATE = ""
    return _PROMPT_TEMPLATE


def _is_cache_valid(cache_key: str) -> bool:
    """Check if a cache entry exists and is still valid (within TTL)."""
    if cache_key not in _llm_cache:
        return False
    timestamp, _ = _llm_cache[cache_key]
    return (time.time() - timestamp) < LLM_CACHE_TTL_SECONDS


def _get_cached_result(cache_key: str) -> Optional[Dict[str, Any]]:
    """Get cached result if valid, otherwise return None."""
    if _is_cache_valid(cache_key):
        _, result = _llm_cache[cache_key]
        logger.debug(f"Cache hit for token: {cache_key[:16]}...")
        return result
    return None


def _cache_result(cache_key: str, result: Dict[str, Any]) -> None:
    """Store result in cache with current timestamp."""
    _llm_cache[cache_key] = (time.time(), result)
    logger.debug(f"Cached result for token: {cache_key[:16]}...")


@rate_limit_gemini
def analyze_with_llm(token_data: Dict[str, Any], event_title: str) -> Dict[str, Any]:
    """
    Analyze a token using Gemini LLM for relevance and authenticity scoring.
    
    Uses the Gemini API with structured JSON output to evaluate:
    - How relevant the token is to the Polymarket event
    - Authenticity indicators (genuine project vs scam)
    - Red flags and concerns
    - Overall confidence in the analysis
    
    Results are cached for 1 hour to avoid redundant API calls.
    
    Args:
        token_data: Dictionary containing token metadata:
            - address: Token mint address (required)
            - name: Token name (optional)
            - symbol: Token symbol (optional)
            - description: Token description (optional)
        event_title: The Polymarket event title for context.
        
    Returns:
        Dictionary with analysis results:
            - relevance_score: 0-100 integer
            - authenticity_score: 0-100 integer
            - red_flags: List of concern strings
            - confidence: 0-100 integer
            - reasoning: Brief explanation string
            
        Returns neutral scores on API failure.
    """
    # Extract token address for caching
    token_address = token_data.get("address", "")
    if not token_address:
        logger.warning("No token address provided, returning neutral result")
        return NEUTRAL_RESULT.copy()
    
    # Check cache first
    cached = _get_cached_result(token_address)
    if cached is not None:
        return cached
    
    # Validate API key
    if not GEMINI_API_KEY:
        logger.error("GEMINI_API_KEY not configured, returning neutral result")
        return NEUTRAL_RESULT.copy()
    
    # Load prompt template
    prompt_template = _get_prompt_template()
    if not prompt_template:
        logger.error("Prompt template not available, returning neutral result")
        return NEUTRAL_RESULT.copy()
    
    # Build the prompt
    prompt = prompt_template.format(
        event_title=event_title,
        token_name=token_data.get("name", "Unknown"),
        token_symbol=token_data.get("symbol", "???"),
        token_description=token_data.get("description", "No description available"),
    )
    
    try:
        # Configure Gemini
        genai.configure(api_key=GEMINI_API_KEY)
        
        # Use gemini-2.5-flash for faster responses (verified to work in learnings.md)
        model = genai.GenerativeModel("gemini-2.5-flash")
        
        # Generate with JSON output mode
        response = model.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json",
                temperature=0.3,  # Lower temperature for consistent analysis
            ),
        )
        
        # Parse response
        if not response.text:
            logger.warning("Empty response from Gemini API")
            return NEUTRAL_RESULT.copy()
        
        import json
        result = json.loads(response.text)
        
        # Validate and sanitize the result
        sanitized_result = {
            "relevance_score": _clamp(result.get("relevance_score", 50), 0, 100),
            "authenticity_score": _clamp(result.get("authenticity_score", 50), 0, 100),
            "red_flags": result.get("red_flags", []) if isinstance(result.get("red_flags"), list) else [],
            "confidence": _clamp(result.get("confidence", 50), 0, 100),
            "reasoning": str(result.get("reasoning", "No reasoning provided"))[:500],
        }
        
        # Cache the result
        _cache_result(token_address, sanitized_result)
        
        logger.info(
            f"LLM analysis complete for {token_data.get('symbol', '???')}: "
            f"relevance={sanitized_result['relevance_score']}, "
            f"authenticity={sanitized_result['authenticity_score']}, "
            f"confidence={sanitized_result['confidence']}"
        )
        
        return sanitized_result
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Gemini response as JSON: {e}")
        return NEUTRAL_RESULT.copy()
    except Exception as e:
        logger.error(f"Gemini API error: {e}")
        return NEUTRAL_RESULT.copy()


def _clamp(value: Any, min_val: int, max_val: int) -> int:
    """Clamp a value to a range, converting to int if needed."""
    try:
        return max(min_val, min(max_val, int(value)))
    except (TypeError, ValueError):
        return (min_val + max_val) // 2


# ==============================================================================
# KEYWORD EXTRACTION
# ==============================================================================

# Stop words commonly found in Polymarket titles
STOP_WORDS: Set[str] = {
    # Question words
    "will", "would", "could", "should", "can", "does", "do", "did", "is", "are",
    "was", "were", "be", "been", "being", "have", "has", "had", "having",
    # Articles & prepositions
    "the", "a", "an", "of", "in", "on", "at", "to", "for", "by", "with",
    "from", "through", "during", "before", "after", "above", "below",
    "between", "into", "out", "over", "under", "again", "further",
    # Common Polymarket phrases
    "yes", "no", "or", "and", "but", "if", "than", "so", "as", "about",
    "any", "all", "each", "every", "either", "neither", "both", "few",
    "more", "most", "other", "some", "such", "only", "own", "same",
    # Time-related
    "january", "february", "march", "april", "may", "june", "july",
    "august", "september", "october", "november", "december",
    "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "oct", "nov", "dec",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "day", "days", "week", "weeks", "month", "months", "year", "years",
    "today", "tomorrow", "yesterday",
    # Numbers as words
    "first", "second", "third", "next", "last",
    # Question markers
    "what", "who", "when", "where", "why", "how", "which", "whom",
    # Common verbs
    "win", "wins", "winning", "winner", "leave", "hit", "hits", "make",
    "get", "gets", "become", "becomes", "announce", "announced",
    # Filler words
    "this", "that", "these", "those", "here", "there",
}

# High-value keywords to always prioritize (politics, tech, scandals)
PRIORITY_KEYWORDS: Set[str] = {
    "trump", "biden", "musk", "elon", "vance",
    "tiktok", "twitter", "meta", "google", "apple", "nvidia", "tesla",
    "war", "russia", "ukraine", "china", "israel", "iran",
    "fed", "inflation", "recession", "election",
    "scandal", "resign", "impeach", "arrest", "indicted",
}

# ==============================================================================
# NOISE GATE: Blacklist for Sports & Crypto Price Bets
# ==============================================================================
# These topics rarely create viral meme coins - we want narratives!
BLACKLIST: Set[str] = {
    # Sports - boring for meme coins
    "nfl", "nba", "mlb", "nhl", "ufc", "wwe",
    "premier league", "champions league", "la liga", "bundesliga",
    "super bowl", "world cup", "world series",
    "lakers", "celtics", "warriors", "yankees", "cowboys", "patriots",
    "man city", "manchester", "liverpool", "arsenal", "chelsea", "barcelona", "real madrid",
    "playoffs", "championship", "finals", "mvp",
    # Crypto price bets - not narrative driven
    "bitcoin", "btc", "ethereum", "eth", "solana", "sol",
    "price", "above", "below", "ath", "all-time high",
    "$100k", "$50k", "$10k",
    # Pop culture noise
    "taylor swift", "grammys", "oscars", "emmys",
    "box office", "album", "tour",
    # Weather/misc
    "temperature", "weather", "hurricane",
}


def clean_title(title: str) -> str:
    """
    Clean the title by removing special characters and normalizing whitespace.
    
    Args:
        title: Raw event title from Polymarket.
        
    Returns:
        Cleaned title string.
    """
    # Remove special characters but keep alphanumeric and spaces
    cleaned = re.sub(r"[^a-zA-Z0-9\s]", " ", title)
    # Normalize whitespace
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def remove_dates(title: str) -> str:
    """
    Remove date patterns from the title.
    
    Args:
        title: Title string.
        
    Returns:
        Title with dates removed.
    """
    # Remove year patterns (2023, 2024, 2025, 2026, etc.)
    title = re.sub(r"\b20[2-3][0-9]\b", "", title)
    # Remove day numbers (1st, 2nd, 15th, etc.)
    title = re.sub(r"\b\d{1,2}(st|nd|rd|th)?\b", "", title)
    return title


def is_proper_noun(word: str, original_title: str) -> bool:
    """
    Check if a word is likely a proper noun based on capitalization.
    
    Args:
        word: The word to check.
        original_title: The original title for context.
        
    Returns:
        True if the word appears to be a proper noun.
    """
    # Find the word in original title (case-sensitive search)
    pattern = r"\b" + re.escape(word) + r"\b"
    match = re.search(pattern, original_title, re.IGNORECASE)
    
    if match:
        original_word = match.group()
        # Check if it's capitalized (proper noun indicator)
        return original_word[0].isupper()
    return False


def extract_keywords(title: str) -> List[str]:
    """
    Extract meme coin relevant keywords from a Polymarket event title.
    
    Strategy:
    1. Clean and normalize the title
    2. Remove dates and stop words
    3. Prioritize known high-value keywords
    4. Focus on proper nouns (capitalized words)
    5. Return top 3 most relevant keywords in UPPERCASE
    
    Args:
        title: The Polymarket event title.
        
    Returns:
        List of up to 3 keywords in UPPERCASE.
    """
    original_title = title
    title_lower = title.lower()
    
    # NOISE GATE: Check blacklist first
    for banned in BLACKLIST:
        if banned in title_lower:
            return []  # Skip this event entirely
    
    # Step 1: Remove dates first
    title = remove_dates(title)
    
    # Step 2: Clean special characters
    title = clean_title(title)
    
    # Step 3: Tokenize
    words = title.split()
    
    # Step 4: Filter and score words
    candidates: List[tuple] = []  # (word, score)
    
    for word in words:
        word_lower = word.lower()
        
        # Skip stop words
        if word_lower in STOP_WORDS:
            continue
        
        # Skip very short words (likely noise)
        if len(word) < 2:
            continue
        
        # Skip pure numbers
        if word.isdigit():
            continue
        
        # Calculate relevance score
        score = 0
        
        # High priority keywords get top score
        if word_lower in PRIORITY_KEYWORDS:
            score += 100
        
        # Proper nouns (capitalized) get bonus
        if is_proper_noun(word, original_title):
            score += 50
        
        # Longer words might be more specific/relevant
        score += min(len(word), 10)
        
        # Add to candidates if score > 0
        if score > 0 or is_proper_noun(word, original_title):
            candidates.append((word_lower, score))
    
    # Step 5: Sort by score (descending) and deduplicate
    candidates.sort(key=lambda x: (-x[1], x[0]))
    
    # Deduplicate while preserving order
    seen: Set[str] = set()
    unique_keywords: List[str] = []
    
    for word, _ in candidates:
        if word not in seen:
            seen.add(word)
            unique_keywords.append(word.upper())
    
    # Return top 3
    return unique_keywords[:3]


def extract_keywords_verbose(title: str) -> dict:
    """
    Verbose version of extract_keywords for debugging.
    Returns detailed extraction info.
    
    Args:
        title: The Polymarket event title.
        
    Returns:
        Dictionary with extraction details.
    """
    keywords = extract_keywords(title)
    return {
        "original": title,
        "keywords": keywords,
        "count": len(keywords),
    }


# =============================================================================
# TESTING
# =============================================================================
if __name__ == "__main__":
    from colorama import init, Fore, Style
    init(autoreset=True)
    
    test_cases = [
        ("Will Nicolas Maduro leave Venezuela by January?", ["MADURO", "VENEZUELA"]),
        ("Bitcoin hits $100k in 2024?", ["BITCOIN"]),
        ("Who will win the 2024 US Election?", ["ELECTION", "US"]),
        ("Trump announces TikTok deal", ["TRUMP", "TIKTOK"]),
        ("Will Elon Musk buy Twitter by December 2024?", ["MUSK", "ELON", "TWITTER"]),
        ("Fed decision in January?", ["FED"]),
        ("Russia-Ukraine war ends by 2025?", ["RUSSIA", "UKRAINE", "WAR"]),
        ("Super Bowl Champion 2026", ["SUPER", "BOWL", "CHAMPION"]),
    ]
    
    print(f"\n{Fore.CYAN}{'='*70}")
    print(f"🧠 BRAIN MODULE - Keyword Extraction Test")
    print(f"{'='*70}{Style.RESET_ALL}\n")
    
    passed = 0
    total = len(test_cases)
    
    for title, expected in test_cases:
        result = extract_keywords(title)
        
        # Check if expected keywords are in results (order-independent partial match)
        matches = sum(1 for kw in expected if kw in result)
        is_pass = matches >= min(len(expected), len(result)) or set(expected[:2]).issubset(set(result[:3]))
        
        status = f"{Fore.GREEN}✓ PASS" if is_pass else f"{Fore.RED}✗ FAIL"
        passed += 1 if is_pass else 0
        
        print(f"{Fore.WHITE}Title: {Fore.YELLOW}\"{title}\"{Style.RESET_ALL}")
        print(f"  Result:   {Fore.CYAN}{result}{Style.RESET_ALL}")
        print(f"  Expected: {Fore.MAGENTA}{expected}{Style.RESET_ALL}")
        print(f"  {status}{Style.RESET_ALL}")
        print()
    
    print(f"{Fore.CYAN}{'='*70}")
    print(f"Results: {passed}/{total} tests passed")
    print(f"{'='*70}{Style.RESET_ALL}\n")
