"""Configuration constants and default values."""

# Default screen dimensions
DEFAULT_SCREEN_WIDTH = 1920
DEFAULT_SCREEN_HEIGHT = 1080

# Default regions for 1920x1080 resolution
DEFAULT_WEAPON_REGION = (1811, 941, 1874, 963)  # Weapon region with a single slot or 2nd slot
DEFAULT_WEAPON_REGION_ALT = (1811, 903, 1874, 925)  # Weapon region 1st slot
DEFAULT_MENU_REGION = (950, 372, 970, 392)  # Quick menu region

# Default detection parameters
DEFAULT_HASH_THRESHOLD = 8
DEFAULT_HASH_SIZE = 16
DEFAULT_LOOP_DELAY = 0.3
DEFAULT_INACTIVE_DELAY = 0.5

# Auto-click timing (milliseconds)
AUTOCLICK_DOWN_DELAY_MIN = 54
AUTOCLICK_DOWN_DELAY_MAX = 64
AUTOCLICK_UP_DELAY_MIN = 54
AUTOCLICK_UP_DELAY_MAX = 64

# Template filenames
WEAPON_TEMPLATE_NAME = "weapon.png"
MENU_TEMPLATE_NAME = "menu.png"

# Debug filenames
DEBUG_WEAPON_FILENAME = "debug_weapon.png"
DEBUG_MENU_FILENAME = "debug_menu.png"

# Window detection keywords to exclude
EXCLUDED_WINDOW_KEYWORDS = [
    "cursor",
    "visual studio",
    "vscode",
    "code",
    "pycharm",
    "sublime",
    "notepad",
    "atom",
    "macro_activator",
    ".py",
    "editor",
    "ide",
]

