"""
Main entry point for ARC-AutoFire - Intelligent Macro System for Arc Raiders.
"""

import sys

def main():
    """Launch GUI or CLI based on arguments."""
    if len(sys.argv) > 1 and sys.argv[1] != "--gui":
        # CLI mode - use original macro_activator main
        from src.macro_activator import main as cli_main
        cli_main()
    else:
        # GUI mode (default)
        from src.gui import main as gui_main
        gui_main()

if __name__ == "__main__":
    main()

