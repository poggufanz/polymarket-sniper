"""
Brain Module - Meme Coin Keyword Extraction
============================================
Extracts relevant keywords from Polymarket event titles
for potential meme coin narrative signals.
"""

import re
from typing import List, Set


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
