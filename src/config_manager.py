"""Configuration manager for loading and saving config.json."""

import json
from pathlib import Path
from typing import Dict, Any, Optional

from .config import (
    DEFAULT_SCREEN_WIDTH,
    DEFAULT_SCREEN_HEIGHT,
    DEFAULT_WEAPON_REGION,
    DEFAULT_WEAPON_REGION_ALT,
    DEFAULT_MENU_REGION,
    DEFAULT_HASH_THRESHOLD,
    DEFAULT_HASH_SIZE,
    DEFAULT_LOOP_DELAY,
    AUTOCLICK_DOWN_DELAY_MIN,
    AUTOCLICK_DOWN_DELAY_MAX,
    AUTOCLICK_UP_DELAY_MIN,
    AUTOCLICK_UP_DELAY_MAX,
)


class ConfigManager:
    """Manages loading and saving of configuration from config.json."""

    def __init__(self, config_path: str = "config.json") -> None:
        """
        Initialize config manager.
        
        Args:
            config_path: Path to config file relative to project root
        """
        script_dir = Path(__file__).parent
        project_root = script_dir.parent
        self.config_path = project_root / config_path
        self.config: Dict[str, Any] = {}
        self.load()
    
    def get_default_config(self) -> Dict[str, Any]:
        """Get default configuration."""
        return {
            "delays": {
                "click_down_min": AUTOCLICK_DOWN_DELAY_MIN,
                "click_down_max": AUTOCLICK_DOWN_DELAY_MAX,
                "click_up_min": AUTOCLICK_UP_DELAY_MIN,
                "click_up_max": AUTOCLICK_UP_DELAY_MAX,
                "detection_loop": DEFAULT_LOOP_DELAY,
            },
            "detection": {
                "hash_threshold": DEFAULT_HASH_THRESHOLD,
                "hash_size": DEFAULT_HASH_SIZE,
                "confidence_threshold": 0.8,
            },
            "regions": {
                "weapon": list(DEFAULT_WEAPON_REGION),
                "weapon_alt": list(DEFAULT_WEAPON_REGION_ALT),
                "menu": list(DEFAULT_MENU_REGION),
                "screen_resolution": [DEFAULT_SCREEN_WIDTH, DEFAULT_SCREEN_HEIGHT],
            },
            "keybinds": {
                "pause_resume": "F6",
                "stop": "F7",
                "capture_screen": "ALT+P",
            },
            "gui": {
                "window_position": [100, 100],
                "window_size": [500, 700],
                "minimize_to_tray": False,
                "run_on_startup": False,
            },
        }
    
    def load(self) -> Dict[str, Any]:
        """
        Load configuration from file.
        
        Returns:
            Loaded configuration dictionary
        """
        if not self.config_path.exists():
            self.config = self.get_default_config()
            self.save()
            return self.config

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                loaded_config = json.load(f)
            default_config = self.get_default_config()
            self.config = self._merge_config(default_config, loaded_config)
            return self.config
        except Exception as e:
            print(f"Error loading config: {e}")
            self.config = self.get_default_config()
            self.save()
            return self.config
    
    def _merge_config(self, default: Dict[str, Any], loaded: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively merge loaded config with defaults."""
        result = default.copy()
        for key, value in loaded.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_config(result[key], value)
            else:
                result[key] = value
        return result
    
    def save(self) -> bool:
        """Save configuration to file."""
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"Error saving config: {e}")
            return False
    
    def get(self, key_path: str, default: Any = None) -> Any:
        """Get a configuration value using dot notation (e.g., 'delays.click_down_min')."""
        keys = key_path.split(".")
        value = self.config
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        return value
    
    def set(self, key_path: str, value: Any) -> None:
        """Set a configuration value using dot notation."""
        keys = key_path.split(".")
        config = self.config
        for key in keys[:-1]:
            if key not in config:
                config[key] = {}
            config = config[key]
        config[keys[-1]] = value
    
    def update(self, updates: Dict[str, Any]) -> None:
        """Update multiple configuration values."""
        for key_path, value in updates.items():
            self.set(key_path, value)

