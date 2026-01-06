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

# Auto-click timing (milliseconds) - Default values, can be overridden per weapon
AUTOCLICK_DOWN_DELAY_MIN = 54
AUTOCLICK_DOWN_DELAY_MAX = 64
AUTOCLICK_UP_DELAY_MIN = 54
AUTOCLICK_UP_DELAY_MAX = 64

# Template filenames (legacy - kept for backwards compatibility)
WEAPON_TEMPLATE_NAME = "weapon.png"
MENU_TEMPLATE_NAME = "menu.png"

# Debug filenames
DEBUG_WEAPON_FILENAME = "debug_weapon.png"
DEBUG_MENU_FILENAME = "debug_menu.png"

# Weapon configurations with individual delay settings
# Each weapon has: name, template_file, and delay settings (ms)
# Delays can be customized per weapon for optimal fire rate
DEFAULT_WEAPONS = {
    "kettle": {
        "name": "Kettle",
        "template": "kettle.png",
        "enabled": True,
        "delays": {
            "click_down_min": 33,
            "click_down_max": 37,
            "click_up_min": 33,
            "click_up_max": 37,
        }
    },
    "burletta": {
        "name": "Burletta",
        "template": "burletta.png",
        "enabled": True,
        "delays": {
            "click_down_min": 33,
            "click_down_max": 37,
            "click_up_min": 33,
            "click_up_max": 37,
        }
    },
}

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

