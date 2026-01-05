"""
ARC-AutoFire - Intelligent Macro System for Arc Raiders package.
"""

__version__ = "0.1.0"

# Handle both relative imports (when used as package) and absolute imports (when run directly)
try:
    from .macro_activator import MacroActivator, main
except ImportError:
    # Fallback for when run directly
    import sys
    from pathlib import Path
    # Add parent directory to path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from src.macro_activator import MacroActivator, main

__all__ = ["MacroActivator", "main"]

# Allow running this file directly
if __name__ == "__main__":
    main()
