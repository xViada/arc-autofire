"""
ARC-AutoFire - Intelligent Macro System for Arc Raiders - Hash-based detection with quick menu detection.

This module provides the main MacroActivator class that manages weapon detection,
menu detection, and macro activation/deactivation based on perceptual hashing.
"""

import sys
import time
from pathlib import Path
from typing import Optional, Tuple
import cv2
import numpy as np
from pynput.keyboard import Key, Listener
import win32gui

from .config import (
    DEFAULT_SCREEN_WIDTH,
    DEFAULT_SCREEN_HEIGHT,
    DEFAULT_WEAPON_REGION,
    DEFAULT_WEAPON_REGION_ALT,
    DEFAULT_MENU_REGION,
    DEFAULT_HASH_THRESHOLD,
    DEFAULT_HASH_SIZE,
    DEFAULT_LOOP_DELAY,
    DEFAULT_INACTIVE_DELAY,
    MENU_TEMPLATE_NAME,
    DEBUG_WEAPON_FILENAME,
    DEBUG_MENU_FILENAME,
    EXCLUDED_WINDOW_KEYWORDS,
    DEFAULT_WEAPONS,
    FALLBACK_DELAYS,
)
from .detection import HashDetector
from .autoclick import AutoClicker
from .window_detection import is_game_active, clean_window_title
from .image_paths import find_template_file, get_image_base_dir


class MacroActivator:
    """
    Weapon and menu detection using perceptual hash.
    
    Macro activates only if: weapon equipped AND menu NOT visible.
    Supports multiple weapons with individual delay configurations.
    """

    def __init__(
        self,
        image_dir: str = "images",
        hash_threshold: int = DEFAULT_HASH_THRESHOLD,
        weapon_region: Optional[Tuple[int, int, int, int]] = None,
        weapon_region_alt: Optional[Tuple[int, int, int, int]] = None,
        menu_region: Optional[Tuple[int, int, int, int]] = None,
        screen_width: int = DEFAULT_SCREEN_WIDTH,
        screen_height: int = DEFAULT_SCREEN_HEIGHT,
        hash_size: int = DEFAULT_HASH_SIZE,
        weapons_config: Optional[dict] = None,
        error_callback: Optional[callable] = None,
    ):
        """
        Initialize the macro activator.

        Args:
            image_dir: Directory containing template images
            hash_threshold: Hamming distance threshold (0-10 recommended)
            weapon_region: Tuple (left, top, right, bottom) for weapon name (slot 2)
            weapon_region_alt: Tuple (left, top, right, bottom) for weapon name (slot 1)
            menu_region: Tuple (left, top, right, bottom) for quick menu
            screen_width: Screen width in pixels
            screen_height: Screen height in pixels
            hash_size: Hash size (8, 16, or 32) - larger = more precise
            weapons_config: Dictionary of weapon configurations with delays
            error_callback: Callback function for error notifications (e.g., Interception driver error)
        """
        self.macro_active = False
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.error_callback = error_callback
        
        self.detector = HashDetector(hash_threshold=hash_threshold, hash_size=hash_size)
        self.autoclicker = AutoClicker(
            macro_active_callback=lambda: self.macro_active,
            error_callback=error_callback
        )
        # Keep image_dir for backwards compatibility, but use organized structure
        self.image_dir = self._resolve_image_dir(image_dir)
        self.image_dir.mkdir(exist_ok=True)

        self.weapon_region = weapon_region or DEFAULT_WEAPON_REGION
        self.weapon_region_alt = weapon_region_alt or DEFAULT_WEAPON_REGION_ALT
        self.menu_region = menu_region or DEFAULT_MENU_REGION
        
        # Store weapons config
        self.weapons_config = weapons_config or DEFAULT_WEAPONS
        
        # Track currently detected weapon for delay switching
        self.current_weapon_id: Optional[str] = None

        self._print_region_info()

        # Load multiple weapon templates
        self.weapon_hashes = self._load_weapon_templates()
        
        # Legacy compatibility - use first available weapon hash
        self.weapon_hash = None
        self.weapon_alt_hash = None
        if self.weapon_hashes:
            first_weapon = next(iter(self.weapon_hashes.values()))
            # Use slot 2 hash for legacy compatibility, fallback to slot 1
            self.weapon_hash = first_weapon.get("hash_slot2") or first_weapon.get("hash_slot1")
            # Use slot 1 hash for legacy compatibility, fallback to slot 2
            self.weapon_alt_hash = first_weapon.get("hash_slot1") or first_weapon.get("hash_slot2")
        
        self.menu_hash = self._load_template_hash(MENU_TEMPLATE_NAME, "menu")

    def _resolve_image_dir(self, image_dir: str) -> Path:
        """Resolve image directory path."""
        image_path = Path(image_dir)
        if image_path.is_absolute():
            return image_path
        
        script_dir = Path(__file__).parent
        project_root = script_dir.parent
        return project_root / image_dir
    
    def _load_weapon_templates(self) -> dict:
        """
        Load all enabled weapon templates and their configurations.
        Supports separate templates for slot 1 and slot 2.
        
        Returns:
            Dictionary mapping weapon_id to {hash_slot1, hash_slot2, name, delays, profile}
        """
        weapon_hashes = {}
        
        for weapon_id, weapon_config in self.weapons_config.items():
            if not weapon_config.get("enabled", True):
                continue
            
            weapon_name = weapon_config.get("name", weapon_id.capitalize())
            
            # Get template filenames (support per-slot templates with fallback)
            template_base = weapon_config.get("template", f"{weapon_id}.png")
            # Generate slot-specific names if not explicitly configured
            base_name = template_base.rsplit('.', 1)[0]  # Remove extension
            template_slot1_name = weapon_config.get("template_slot1", f"{base_name}_slot1.png")
            template_slot2_name = weapon_config.get("template_slot2", f"{base_name}_slot2.png")
            
            # Load slot 1 template (check templates/ and captured/ directories)
            template_slot1_path = find_template_file(template_slot1_name)
            template_slot1_hash = None
            if template_slot1_path:
                template_slot1_img = self.detector.load_image(template_slot1_path)
                if template_slot1_img is not None:
                    template_slot1_hash = self.detector.calculate_hash(template_slot1_img)
                    if template_slot1_hash is None:
                        print(f"Failed to calculate hash for slot 1 template: {template_slot1_path}")
            else:
                print(f"Weapon template (slot 1) not found: {template_slot1_name}")
            
            # Load slot 2 template (check templates/ and captured/ directories)
            template_slot2_path = find_template_file(template_slot2_name)
            template_slot2_hash = None
            if template_slot2_path:
                template_slot2_img = self.detector.load_image(template_slot2_path)
                if template_slot2_img is not None:
                    template_slot2_hash = self.detector.calculate_hash(template_slot2_img)
                    if template_slot2_hash is None:
                        print(f"Failed to calculate hash for slot 2 template: {template_slot2_path}")
            else:
                print(f"Weapon template (slot 2) not found: {template_slot2_name}")
            
            # Skip if no templates loaded
            if template_slot1_hash is None and template_slot2_hash is None:
                print(f"Skipping weapon '{weapon_name}': No valid templates found")
                continue
            
            profile = weapon_config.get("profile", "custom")
            default_profiles = weapon_config.get("default_profiles", {})
            
            # Get delays based on profile
            if profile in default_profiles:
                delays = default_profiles[profile].get("delays", FALLBACK_DELAYS.copy())
                profile_display = default_profiles[profile].get("name", profile.capitalize())
            else:
                delays = weapon_config.get("delays", FALLBACK_DELAYS.copy())
                profile_display = "Custom"
            
            weapon_hashes[weapon_id] = {
                "hash_slot1": template_slot1_hash,
                "hash_slot2": template_slot2_hash,
                "name": weapon_name,
                "delays": delays,
                "profile": profile,
            }
            
            # Print loading info
            print(f"Loaded weapon '{weapon_name}':")
            if template_slot1_hash:
                print(f"  Slot 1: {template_slot1_name} (hash: {template_slot1_hash})")
            if template_slot2_hash:
                print(f"  Slot 2: {template_slot2_name} (hash: {template_slot2_hash})")
            if template_slot1_hash is None:
                print(f"  Warning: Slot 1 template missing, will use slot 2 template")
            if template_slot2_hash is None:
                print(f"  Warning: Slot 2 template missing, will use slot 1 template")
            print(f"  Profile: {profile_display}")
            print(f"  Delays: down={delays['click_down_min']}-{delays['click_down_max']}ms, up={delays['click_up_min']}-{delays['click_up_max']}ms")
        
        if not weapon_hashes:
            print("WARNING: No weapon templates loaded!")
        else:
            print(f"Loaded {len(weapon_hashes)} weapon(s): {', '.join(weapon_hashes.keys())}")
        
        return weapon_hashes
    
    def detect_weapon(self, weapon_img: np.ndarray, slot: int = 1) -> Tuple[bool, Optional[str], int]:
        """
        Detect which weapon (if any) matches the captured image.
        
        Args:
            weapon_img: Captured weapon region image
            slot: Slot number (1 or 2) to determine which template to use
            
        Returns:
            Tuple (detected: bool, weapon_id: str or None, best_distance: int)
        """
        if not self.weapon_hashes:
            return False, None, 999
        
        best_match = None
        best_distance = 999
        best_distance_overall = 999  # Track best distance even if outside threshold
        
        # Determine which hash to use based on slot
        hash_key = f"hash_slot{slot}"
        
        for weapon_id, weapon_data in self.weapon_hashes.items():
            # Get the appropriate hash for this slot
            template_hash = weapon_data.get(hash_key)
            
            # Fallback: if slot-specific hash not available, try the other slot's hash
            if template_hash is None:
                fallback_key = f"hash_slot{3 - slot}"  # 3-1=2, 3-2=1
                template_hash = weapon_data.get(fallback_key)
            
            # Skip if no hash available
            if template_hash is None:
                continue
            
            detected, distance = self.detector.detect_hash(
                weapon_img, template_hash, debug=False
            )
            
            # Track the overall best distance (even if outside threshold)
            if distance < best_distance_overall:
                best_distance_overall = distance
                # If this is the best match and within threshold, use it
                if detected and distance < best_distance:
                    best_distance = distance
                    best_match = weapon_id
        
        # If we found a match within threshold, return it
        if best_match is not None:
            return True, best_match, best_distance
        
        # Otherwise, return the best distance found (even if outside threshold)
        # This helps with debugging - we can see how close we were
        return False, None, best_distance_overall
    
    def apply_weapon_delays(self, weapon_id: str) -> None:
        """
        Apply the delay configuration for a specific weapon to the autoclicker.
        
        Args:
            weapon_id: ID of the weapon to apply delays for
        """
        if weapon_id not in self.weapon_hashes:
            return
        
        delays = self.weapon_hashes[weapon_id]["delays"]
        weapon_name = self.weapon_hashes[weapon_id]["name"]
        
        # Only update if weapon changed
        if self.current_weapon_id != weapon_id:
            self.autoclicker.click_down_min = delays["click_down_min"]
            self.autoclicker.click_down_max = delays["click_down_max"]
            self.autoclicker.click_up_min = delays["click_up_min"]
            self.autoclicker.click_up_max = delays["click_up_max"]
            self.current_weapon_id = weapon_id
            print(f"Switched to {weapon_name}: delays down={delays['click_down_min']}-{delays['click_down_max']}ms, up={delays['click_up_min']}-{delays['click_up_max']}ms")

    def _print_region_info(self) -> None:
        """Print region information for debugging."""
        w_width = self.weapon_region[2] - self.weapon_region[0]
        w_height = self.weapon_region[3] - self.weapon_region[1]
        w_alt_width = self.weapon_region_alt[2] - self.weapon_region_alt[0]
        w_alt_height = self.weapon_region_alt[3] - self.weapon_region_alt[1]
        m_width = self.menu_region[2] - self.menu_region[0]
        m_height = self.menu_region[3] - self.menu_region[1]
        
        print(f"Weapon region (slot 2): {self.weapon_region} ({w_width}x{w_height} pixels)")
        print(f"Weapon region (slot 1): {self.weapon_region_alt} ({w_alt_width}x{w_alt_height} pixels)")
        print(f"Menu region: {self.menu_region} ({m_width}x{m_height} pixels)")

    def _load_template_hash(self, filename: str, template_type: str) -> Optional[object]:
        """
        Load template image and calculate hash.
        
        Args:
            filename: Template image filename
            template_type: Type of template ("weapon" or "menu")
            
        Returns:
            ImageHash object or None if template not found
        """
        template_path = find_template_file(filename)
        if template_path is None:
            print(f"No {template_type} template. Use --capture-template {template_type}")
            return None
        
        template_img = self.detector.load_image(template_path)
        
        if template_img is None:
            print(f"No {template_type} template. Use --capture-template {template_type}")
            return None
        
        template_hash = self.detector.calculate_hash(template_img)
        print(f"{template_type.capitalize()} template loaded: {template_img.shape[1]}x{template_img.shape[0]} pixels")
        print(f"{template_type.capitalize()} hash: {template_hash}")
        return template_hash

    def save_current_capture(self, region_type: str = "weapon") -> bool:
        """
        Save current screen capture for debugging.
        
        Args:
            region_type: Type of region to capture ("weapon" or "menu")
            
        Returns:
            True if capture was successful, False otherwise
        """
        if region_type == "weapon":
            region_img = self.detector.capture_region(self.weapon_region)
            template_hash = self.weapon_hash
            filename = DEBUG_WEAPON_FILENAME
        else:
            region_img = self.detector.capture_region(self.menu_region)
            template_hash = self.menu_hash
            filename = DEBUG_MENU_FILENAME
            
        if region_img is None:
            return False
        
        from .image_paths import get_previews_dir
        path = get_previews_dir() / filename
        cv2.imwrite(str(path), region_img)
        print(f"Current {region_type} capture saved to: {path}")
        
        current_hash = self.detector.calculate_hash(region_img)
        print(f"Current hash: {current_hash}")
        
        if template_hash:
            distance = template_hash - current_hash
            print(f"Distance from template: {distance}")
            print(f"Threshold: {self.detector.hash_threshold}")
            print(f"Would detect: {distance <= self.detector.hash_threshold}")
        
        return True

    def show_live_preview(self, preview_type: str = "both") -> None:
        """
        Show live preview with hash-based detection.
        
        Args:
            preview_type: "weapon", "menu", or "both"
        """
        print(f"\n=== LIVE PREVIEW MODE ({preview_type.upper()}) ===")
        print("Press 'q' to quit, 's' to save current frame")
        print(f"Hash threshold: {self.detector.hash_threshold}")

        try:
            while True:
                frames, titles = self._capture_preview_frames(preview_type)
                
                for frame, title in zip(frames, titles):
                    cv2.imshow(title, frame)
                
                key = cv2.waitKey(100) & 0xFF
                if key == ord("q"):
                    break
                elif key == ord("s"):
                    self._save_preview_frames(preview_type)

        except KeyboardInterrupt:
            pass
        finally:
            cv2.destroyAllWindows()
            print("Preview closed")

    def _capture_preview_frames(self, preview_type: str) -> Tuple[list, list]:
        """Capture and process preview frames."""
        frames = []
        titles = []
        
        if preview_type in ["weapon", "both"] and self.weapon_hash:
            frame, title = self._create_weapon_preview()
            if frame is not None:
                frames.append(frame)
                titles.append(title)
        
        if preview_type in ["menu", "both"] and self.menu_hash:
            frame, title = self._create_menu_preview()
            if frame is not None:
                frames.append(frame)
                titles.append(title)
        
        return frames, titles

    def _create_weapon_preview(self) -> Tuple[Optional[np.ndarray], str]:
        """Create weapon detection preview frame."""
        weapon_img = self.detector.capture_region(self.weapon_region)
        if weapon_img is None:
            return None, ""
        
        weapon_color = cv2.cvtColor(weapon_img, cv2.COLOR_GRAY2BGR)
        current_hash = self.detector.calculate_hash(weapon_img)
        
        if current_hash and self.weapon_hash:
            distance = self.weapon_hash - current_hash
            detected = distance <= self.detector.hash_threshold
            color = (0, 255, 0) if detected else (0, 0, 255)
            status = "WEAPON DETECTED" if detected else "NO WEAPON"
            
            cv2.putText(weapon_color, f"Dist: {distance} (thresh: {self.detector.hash_threshold})",
                       (10, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
            cv2.putText(weapon_color, status, (10, 40),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
        
        resized = cv2.resize(weapon_color, None, fx=2, fy=2, interpolation=cv2.INTER_NEAREST)
        return resized, "Weapon Detection"

    def _create_menu_preview(self) -> Tuple[Optional[np.ndarray], str]:
        """Create menu detection preview frame."""
        menu_img = self.detector.capture_region(self.menu_region)
        if menu_img is None:
            return None, ""
        
        menu_color = cv2.cvtColor(menu_img, cv2.COLOR_GRAY2BGR)
        current_hash = self.detector.calculate_hash(menu_img)
        
        if current_hash and self.menu_hash:
            distance = self.menu_hash - current_hash
            detected = distance <= self.detector.hash_threshold
            color = (0, 255, 0) if detected else (0, 0, 255)
            status = "MENU OPEN" if detected else "MENU CLOSED"
            
            cv2.putText(menu_color, f"Dist: {distance} (thresh: {self.detector.hash_threshold})",
                       (10, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
            cv2.putText(menu_color, status, (10, 40),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
        
        resized = cv2.resize(menu_color, None, fx=2, fy=2, interpolation=cv2.INTER_NEAREST)
        return resized, "Menu Detection"

    def _save_preview_frames(self, preview_type: str) -> None:
        """Save current preview frames."""
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        if preview_type in ["weapon", "both"]:
            self.save_current_capture("weapon")
        if preview_type in ["menu", "both"]:
            self.save_current_capture("menu")
        print(f"Frames saved with timestamp {timestamp}")

    def capture_template(self, template_name: str = "weapon") -> bool:
        """
        Capture the current screen region as a template image.
        
        Args:
            template_name: "weapon" or "menu"
            
        Returns:
            True if template was captured successfully, False otherwise
        """
        print(f"\n=== TEMPLATE CAPTURE MODE: {template_name.upper()} ===")
        
        region = self.weapon_region if template_name == "weapon" else self.menu_region
        self._print_capture_instructions(template_name, region)

        captured = False

        def on_press(key):
            nonlocal captured
            try:
                if key == Key.space:
                    captured = self._perform_template_capture(template_name, region)
                    return False
                elif key == Key.esc:
                    print("\n✗ Template capture cancelled.")
                    return False
            except AttributeError:
                pass
            return True

        listener = Listener(on_press=on_press)
        listener.start()
        listener.join()
        return captured

    def _print_capture_instructions(self, template_name: str, region: Tuple[int, int, int, int]) -> None:
        """Print capture instructions."""
        if template_name == "weapon":
            print("Steps:")
            print("1. Equip the weapon in-game")
            print("2. Make sure the weapon name is clearly visible")
            print("3. Press SPACE to capture")
        else:
            print("Steps:")
            print("1. Press Q to open the quick menu")
            print("2. Make sure the menu is fully visible")
            print("3. Press SPACE to capture")
        
        print("4. Press ESC to cancel")
        print(f"\nCapture region: {region}")

    def _perform_template_capture(self, template_name: str, region: Tuple[int, int, int, int]) -> bool:
        """Perform the actual template capture."""
        region_img = self.detector.capture_region(region)
        if region_img is None:
            print("✗ Failed to capture region.", file=sys.stderr)
            return False
        
        from .image_paths import get_captured_dir
        template_path = get_captured_dir() / f"{template_name}.png"
        cv2.imwrite(str(template_path), region_img)
        
        template_hash = self.detector.calculate_hash(region_img)
        
        print(f"\n✓ Template saved to: {template_path}")
        print(f"✓ Template size: {region_img.shape[1]}x{region_img.shape[0]} pixels")
        print(f"✓ Template hash: {template_hash}")

        print("\nShowing preview for 3 seconds...")
        preview = cv2.resize(region_img, None, fx=2, fy=2)
        cv2.imshow(f"Captured {template_name.title()} Template", preview)
        cv2.waitKey(3000)
        cv2.destroyAllWindows()
        
        return True

    def _activate_macro(self) -> None:
        """Activate the macro if not already active."""
        if not self.macro_active:
            self.macro_active = True
            print("✓ Macro activated (auto-click enabled)")
            self.autoclicker.start_if_button_pressed()

    def _deactivate_macro(self) -> None:
        """Deactivate the macro if currently active."""
        if self.macro_active:
            self.macro_active = False
            print("✗ Macro deactivated (auto-click disabled)")

    def run(
        self,
        loop_delay: float = DEFAULT_LOOP_DELAY,
        inactive_delay: float = DEFAULT_INACTIVE_DELAY,
        debug: bool = False,
    ) -> None:
        """
        Main loop for detecting weapon and menu, managing macro state.
        
        Logic:
        - Macro activates ONLY if: weapon detected AND menu NOT detected
        - If menu is open (detected), macro pauses even if weapon equipped
        - When macro is active and left mouse button is held, auto-click runs
        
        Args:
            loop_delay: Delay between detection cycles when game is active
            inactive_delay: Delay between checks when game is inactive
            debug: Enable debug output
        """
        if not self._validate_setup():
            return

        self._print_startup_info(loop_delay, debug)

        last_shown_title: Optional[str] = None
        check_count = 0

        try:
            while True:
                is_active = is_game_active(EXCLUDED_WINDOW_KEYWORDS, debug=debug)

                if not is_active:
                    if self.macro_active:
                        self._deactivate_macro()

                    if debug and check_count % 10 == 0:
                        last_shown_title = self._print_window_info(last_shown_title)

                    check_count += 1
                    time.sleep(inactive_delay)
                    continue

                check_count = 0
                last_shown_title = None

                weapon_detected, menu_detected = self._perform_detection(debug)
                self._update_macro_state(weapon_detected, menu_detected, debug)

                time.sleep(loop_delay)

        except KeyboardInterrupt:
            print("\n\nStopping...")
        finally:
            self._cleanup()

    def _validate_setup(self) -> bool:
        """Validate that required templates and drivers are available."""
        if not self.weapon_hashes:
            print("ERROR: No weapon templates loaded!", file=sys.stderr)
            print("Add weapon template images (e.g. kettle.png, burletta.png) to the /images folder", file=sys.stderr)
            return False

        if not AutoClicker.is_available():
            print("ERROR: Interception driver not available!", file=sys.stderr)
            print("Install steps:", file=sys.stderr)
            print("  1. Download from: https://github.com/oblitum/Interception/releases", file=sys.stderr)
            print("  2. Run as Admin: install-interception.exe /install", file=sys.stderr)
            print("  3. Restart Windows", file=sys.stderr)
            print("  4. pip install interception-python", file=sys.stderr)
            return False

        return True

    def _print_startup_info(self, loop_delay: float, debug: bool) -> None:
        """Print startup information."""
        print("\n=== ARC-AUTOFIRE - INTELLIGENT MACRO SYSTEM (Interception Driver) ===")
        print("    Created by xViada - https://github.com/xViada")
        print("=" * 65)
        print(f"Weapon region (slot 2): {self.weapon_region}")
        print(f"Weapon region (slot 1): {self.weapon_region_alt}")
        print(f"Menu region: {self.menu_region}")
        print(f"Loop delay: {loop_delay}s")
        print(f"Hash threshold: {self.detector.hash_threshold}")
        
        # Print loaded weapons
        if self.weapon_hashes:
            print(f"\n✓ Loaded {len(self.weapon_hashes)} weapon(s):")
            for weapon_id, weapon_data in self.weapon_hashes.items():
                delays = weapon_data["delays"]
                print(f"  - {weapon_data['name']}: down={delays['click_down_min']}-{delays['click_down_max']}ms, up={delays['click_up_min']}-{delays['click_up_max']}ms")
        else:
            print("\n⚠ No weapons loaded! Add weapon templates to /images folder.")
        
        if self.menu_hash:
            print(f"\n✓ Menu detection ENABLED - macro will pause when Q menu is open")
        else:
            print("\n⚠ Menu detection DISABLED - no menu template loaded")
        
        print(f"\nDebug mode: {debug}")
        print("\nLogic: Macro ON only if weapon equipped AND menu closed")
        print("Auto-click: Hold LEFT MOUSE BUTTON to auto-fire when macro is active")
        print("Delays are automatically applied based on detected weapon")
        print("Mouse listener: ACTIVE (tracking physical button state)")
        print("Press Ctrl+C to stop\n")

    def _print_window_info(self, last_shown_title: Optional[str]) -> Optional[str]:
        """Print current window information for debugging."""
        try:
            hwnd = win32gui.GetForegroundWindow()
            current_title = win32gui.GetWindowText(hwnd)
            cleaned_current = clean_window_title(current_title)
            if current_title != last_shown_title:
                print(f"Waiting for game... Current: '{cleaned_current}'")
                return current_title
        except Exception:
            pass
        return last_shown_title

    def _perform_detection(self, debug: bool) -> Tuple[bool, bool]:
        """Perform weapon and menu detection using multi-weapon system."""
        weapon_img = self.detector.capture_region(self.weapon_region)
        weapon_alt_img = (
            self.detector.capture_region(self.weapon_region_alt)
            if self.weapon_hashes
            else None
        )
        menu_img = (
            self.detector.capture_region(self.menu_region)
            if self.menu_hash
            else None
        )

        if weapon_img is None:
            return False, False

        # Detect weapon in slot 2 (using slot 2 templates)
        weapon_detected_slot2, weapon_id_slot2, distance_slot2 = self.detect_weapon(weapon_img, slot=2)
        
        # Detect weapon in slot 1 (using slot 1 templates)
        weapon_detected_slot1 = False
        weapon_id_slot1 = None
        distance_slot1 = 999
        if weapon_alt_img is not None:
            weapon_detected_slot1, weapon_id_slot1, distance_slot1 = self.detect_weapon(weapon_alt_img, slot=1)
        
        # Use the best match (lowest distance)
        weapon_detected = False
        detected_weapon_id = None
        best_distance = 999
        
        if weapon_detected_slot2 and weapon_detected_slot1:
            # Both detected - use the one with lower distance
            if distance_slot2 <= distance_slot1:
                weapon_detected = True
                detected_weapon_id = weapon_id_slot2
                best_distance = distance_slot2
            else:
                weapon_detected = True
                detected_weapon_id = weapon_id_slot1
                best_distance = distance_slot1
        elif weapon_detected_slot2:
            weapon_detected = True
            detected_weapon_id = weapon_id_slot2
            best_distance = distance_slot2
        elif weapon_detected_slot1:
            weapon_detected = True
            detected_weapon_id = weapon_id_slot1
            best_distance = distance_slot1
        else:
            best_distance = min(distance_slot2, distance_slot1)
        
        # Apply delays for detected weapon
        if weapon_detected and detected_weapon_id:
            self.apply_weapon_delays(detected_weapon_id)
        
        # Store detected weapon ID for external access
        self.detected_weapon_id = detected_weapon_id

        menu_detected = False
        menu_distance = 999
        if menu_img is not None and self.menu_hash is not None:
            menu_detected, menu_distance = self.detector.detect_hash(
                menu_img, self.menu_hash, debug=debug
            )

        if debug:
            weapon_name = self.weapon_hashes.get(detected_weapon_id, {}).get("name", "None") if detected_weapon_id else "None"
            print(
                f"Weapon: {weapon_name} (slot2={distance_slot2}, slot1={distance_slot1}), detected={weapon_detected} | "
                f"Menu: dist={menu_distance}, detected={menu_detected} | "
                f"Left btn: {self.autoclicker.left_button_pressed} | "
                f"Auto-click: {self.autoclicker.autoclick_running}"
            )

        return weapon_detected, menu_detected

    def _update_macro_state(self, weapon_detected: bool, menu_detected: bool, debug: bool) -> None:
        """Update macro activation state based on detection results."""
        should_activate = weapon_detected and not menu_detected

        if should_activate:
            self._activate_macro()
        else:
            self._deactivate_macro()
            if debug and weapon_detected and menu_detected:
                print("  -> Macro paused: menu is open")

    def _cleanup(self) -> None:
        """Cleanup resources."""
        if self.macro_active:
            self._deactivate_macro()
        self.autoclicker.stop()
        print("Stopped")


def main():
    """Entry point for the macro activator."""
    import argparse

    parser = argparse.ArgumentParser(
        description="ARC-AutoFire - Intelligent Macro System for Arc Raiders (Hash Detection + Integrated Auto-Click)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Capture weapon template
  python main.py --capture-template weapon

  # Capture menu template (open Q menu first!)
  python main.py --capture-template menu

  # Preview weapon detection
  python main.py --preview weapon

  # Preview menu detection
  python main.py --preview menu

  # Preview both
  python main.py --preview both

  # Run with debug output
  python main.py --debug

How it works:
  1. Equip the weapon -> Macro activates automatically
  2. Hold LEFT MOUSE BUTTON -> Auto-click starts (54-64ms random delays)
  3. Release button -> Auto-click stops
  4. Open Q menu -> Macro pauses automatically
  5. Switch weapon/unequip -> Macro deactivates

Created by xViada - https://github.com/xViada
""",
    )

    parser.add_argument("--debug", action="store_true", help="Enable debug output")
    parser.add_argument(
        "--loop-delay",
        type=float,
        default=DEFAULT_LOOP_DELAY,
        help=f"Detection loop delay in seconds (default: {DEFAULT_LOOP_DELAY})",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=DEFAULT_HASH_THRESHOLD,
        help=f"Hash distance threshold (default: {DEFAULT_HASH_THRESHOLD}, range: 0-15)",
    )
    parser.add_argument(
        "--hash-size",
        type=int,
        default=DEFAULT_HASH_SIZE,
        choices=[8, 16, 32],
        help=f"Hash size - larger = more precise (default: {DEFAULT_HASH_SIZE})",
    )
    parser.add_argument(
        "--weapon-region",
        nargs=4,
        type=int,
        metavar=("LEFT", "TOP", "RIGHT", "BOTTOM"),
        help="Custom weapon capture region",
    )
    parser.add_argument(
        "--menu-region",
        nargs=4,
        type=int,
        metavar=("LEFT", "TOP", "RIGHT", "BOTTOM"),
        help="Custom menu capture region",
    )
    parser.add_argument(
        "--screen-width",
        type=int,
        default=DEFAULT_SCREEN_WIDTH,
        help=f"Screen width (default: {DEFAULT_SCREEN_WIDTH})",
    )
    parser.add_argument(
        "--screen-height",
        type=int,
        default=DEFAULT_SCREEN_HEIGHT,
        help=f"Screen height (default: {DEFAULT_SCREEN_HEIGHT})",
    )

    # Tools
    parser.add_argument(
        "--capture-template",
        type=str,
        choices=["weapon", "menu"],
        metavar="TYPE",
        help="Capture a new template (weapon or menu)",
    )
    parser.add_argument(
        "--preview",
        type=str,
        choices=["weapon", "menu", "both"],
        metavar="TYPE",
        help="Show live detection preview (weapon, menu, or both)",
    )
    parser.add_argument(
        "--save-capture",
        type=str,
        choices=["weapon", "menu"],
        metavar="TYPE",
        help="Save current capture and show hash",
    )

    args = parser.parse_args()

    try:
        weapon_region = tuple(args.weapon_region) if args.weapon_region else None
        menu_region = tuple(args.menu_region) if args.menu_region else None

        activator = MacroActivator(
            hash_threshold=args.threshold,
            hash_size=args.hash_size,
            weapon_region=weapon_region,
            menu_region=menu_region,
            screen_width=args.screen_width,
            screen_height=args.screen_height,
        )

        if args.capture_template:
            activator.capture_template(args.capture_template)
            return

        if args.preview:
            activator.show_live_preview(args.preview)
            return

        if args.save_capture:
            activator.save_current_capture(args.save_capture)
            return

        activator.run(loop_delay=args.loop_delay, debug=args.debug)

    except Exception as e:
        print(f"Fatal error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
