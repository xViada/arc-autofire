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
    WEAPON_TEMPLATE_NAME,
    MENU_TEMPLATE_NAME,
    DEBUG_WEAPON_FILENAME,
    DEBUG_MENU_FILENAME,
    EXCLUDED_WINDOW_KEYWORDS,
)
from .detection import HashDetector
from .autoclick import AutoClicker
from .window_detection import is_game_active, clean_window_title


class MacroActivator:
    """
    Weapon and menu detection using perceptual hash.
    
    Macro activates only if: weapon equipped AND menu NOT visible.
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
        """
        self.macro_active = False
        self.screen_width = screen_width
        self.screen_height = screen_height
        
        self.detector = HashDetector(hash_threshold=hash_threshold, hash_size=hash_size)
        self.autoclicker = AutoClicker(macro_active_callback=lambda: self.macro_active)
        self.image_dir = self._resolve_image_dir(image_dir)
        self.image_dir.mkdir(exist_ok=True)

        self.weapon_region = weapon_region or DEFAULT_WEAPON_REGION
        self.weapon_region_alt = weapon_region_alt or DEFAULT_WEAPON_REGION_ALT
        self.menu_region = menu_region or DEFAULT_MENU_REGION

        self._print_region_info()

        # Load templates - use same weapon template for both slots
        self.weapon_hash = self._load_template_hash(WEAPON_TEMPLATE_NAME, "weapon")
        self.weapon_alt_hash = self.weapon_hash
        if self.weapon_hash:
            print("Using same weapon template for both slot 1 and slot 2 detection")
        self.menu_hash = self._load_template_hash(MENU_TEMPLATE_NAME, "menu")

    def _resolve_image_dir(self, image_dir: str) -> Path:
        """Resolve image directory path."""
        image_path = Path(image_dir)
        if image_path.is_absolute():
            return image_path
        
        script_dir = Path(__file__).parent
        project_root = script_dir.parent
        return project_root / image_dir

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
        template_path = self.image_dir / filename
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
        
        path = self.image_dir / filename
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
        
        template_path = self.image_dir / f"{template_name}.png"
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
        if self.weapon_hash is None:
            print("ERROR: No weapon template loaded!", file=sys.stderr)
            print("Use: python main.py --capture-template weapon", file=sys.stderr)
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
        print(f"Weapon hash (used for both slots): {self.weapon_hash}")
        
        if self.menu_hash:
            print(f"Menu hash: {self.menu_hash}")
            print("\n✓ Menu detection ENABLED - macro will pause when Q menu is open")
        else:
            print("\n⚠ Menu detection DISABLED - no menu template loaded")
        
        print(f"Debug mode: {debug}")
        print("\nLogic: Macro ON only if weapon equipped AND menu closed")
        print("Auto-click: Hold LEFT MOUSE BUTTON to auto-fire when macro is active")
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
        """Perform weapon and menu detection."""
        weapon_img = self.detector.capture_region(self.weapon_region)
        weapon_alt_img = (
            self.detector.capture_region(self.weapon_region_alt)
            if self.weapon_alt_hash
            else None
        )
        menu_img = (
            self.detector.capture_region(self.menu_region)
            if self.menu_hash
            else None
        )

        if weapon_img is None:
            return False, False

        weapon_detected, weapon_distance = self.detector.detect_hash(
            weapon_img, self.weapon_hash, debug=debug
        )

        weapon_alt_detected = False
        weapon_alt_distance = 999
        if weapon_alt_img is not None and self.weapon_alt_hash is not None:
            weapon_alt_detected, weapon_alt_distance = self.detector.detect_hash(
                weapon_alt_img, self.weapon_alt_hash, debug=debug
            )

        weapon_detected = weapon_detected or weapon_alt_detected

        menu_detected = False
        menu_distance = 999
        if menu_img is not None and self.menu_hash is not None:
            menu_detected, menu_distance = self.detector.detect_hash(
                menu_img, self.menu_hash, debug=debug
            )

        if debug:
            weapon_dist_str = f"dist={weapon_distance}"
            if weapon_alt_img is not None and self.weapon_alt_hash is not None:
                weapon_dist_str += f"/alt={weapon_alt_distance}"
            print(
                f"Weapon: {weapon_dist_str}, detected={weapon_detected} | "
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
