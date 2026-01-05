"""Window detection utilities for ARC Raiders."""

import re
import win32gui


def clean_window_title(title: str) -> str:
    """
    Remove invisible Unicode characters from window title.
    
    Args:
        title: Raw window title
        
    Returns:
        Cleaned window title
    """
    # Remove zero-width characters and other invisible Unicode
    cleaned = re.sub(r"[\u200b-\u200d\ufeff\u2000-\u200a\u2028-\u2029]", "", title)
    # Keep only printable characters
    cleaned = re.sub(r"[^\x20-\x7E\u00A0-\uFFFF]", "", cleaned)
    # Normalize whitespace
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def is_game_active(excluded_keywords: list[str], debug: bool = False) -> bool:
    """
    Check if ARC Raiders window is active.
    
    Args:
        excluded_keywords: List of keywords to exclude from detection
        debug: Enable debug output
        
    Returns:
        True if ARC Raiders window is active, False otherwise
    """
    try:
        hwnd = win32gui.GetForegroundWindow()
        if hwnd == 0:
            return False

        title = win32gui.GetWindowText(hwnd)
        if _is_arc_raiders_title(title, excluded_keywords):
            return True

        return False

    except Exception as e:
        if debug:
            import sys
            print(f"Error checking game window: {e}", file=sys.stderr)
        return False


def _is_arc_raiders_title(title: str, excluded_keywords: list[str]) -> bool:
    """Check if title matches ARC Raiders pattern."""
    # Quick check on raw title
    raw_normalized = re.sub(r"[^a-z0-9]", "", title.lower())
    if raw_normalized == "arcraiders":
        return True

    cleaned_title = clean_window_title(title)
    title_lower = cleaned_title.lower().strip()

    # Exclude if contains excluded keywords
    if any(keyword in title_lower for keyword in excluded_keywords):
        return False

    # Check normalized patterns
    normalized_no_space = re.sub(r"[^a-z0-9]", "", title_lower)
    if normalized_no_space == "arcraiders":
        return True

    normalized = re.sub(r"[^a-z0-9\s]", "", title_lower)
    if normalized == "arc raiders":
        return True

    # Pattern matching
    patterns = [
        r"\barc\s+raiders\b",
        r"\barcraiders\b",
        r"\barc[\s\-:]*raiders\b",
    ]
    if any(re.search(pattern, title_lower) for pattern in patterns):
        return True

    # Fallback: starts with "arc" and contains "raiders"
    invalid_chars = ["\\", "/", ".py", ".exe", "macro"]
    if (
        len(title_lower) < 50
        and title_lower.startswith("arc")
        and "raiders" in title_lower
        and not any(char in title_lower for char in invalid_chars)
    ):
        return True

    return False

