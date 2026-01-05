"""Auto-click functionality using Interception driver."""

import sys
import time
import random
import threading
from typing import Optional, Callable
from pynput.mouse import Button, Listener as MouseListener

from .config import (
    AUTOCLICK_DOWN_DELAY_MIN,
    AUTOCLICK_DOWN_DELAY_MAX,
    AUTOCLICK_UP_DELAY_MIN,
    AUTOCLICK_UP_DELAY_MAX,
)

# Interception driver for kernel-level clicks
INTERCEPTION_AVAILABLE = False

try:
    import interception
    INTERCEPTION_AVAILABLE = True
    print("Interception: Module loaded OK")
except ImportError:
    print("WARNING: interception-python not installed. Install with: pip install interception-python")
except Exception as e:
    print(f"WARNING: Interception init failed: {e}")


class AutoClicker:
    """Manages auto-click functionality with Interception driver."""

    def __init__(
        self,
        macro_active_callback: Optional[Callable[[], bool]] = None,
        click_down_min: Optional[int] = None,
        click_down_max: Optional[int] = None,
        click_up_min: Optional[int] = None,
        click_up_max: Optional[int] = None,
    ):
        """
        Initialize auto-clicker.
        
        Args:
            macro_active_callback: Callback function that returns macro active state
            click_down_min: Minimum delay for click down in ms (default: 54)
            click_down_max: Maximum delay for click down in ms (default: 64)
            click_up_min: Minimum delay for click up in ms (default: 54)
            click_up_max: Maximum delay for click up in ms (default: 64)
        """
        self.macro_active_callback = macro_active_callback
        self.autoclick_running = False
        self.autoclick_thread: Optional[threading.Thread] = None
        self.should_stop_autoclick = False
        self.left_button_pressed = False
        self.simulated_presses_pending = 0
        self.simulated_releases_pending = 0
        self._click_lock = threading.Lock()

        self.click_down_min = click_down_min or AUTOCLICK_DOWN_DELAY_MIN
        self.click_down_max = click_down_max or AUTOCLICK_DOWN_DELAY_MAX
        self.click_up_min = click_up_min or AUTOCLICK_UP_DELAY_MIN
        self.click_up_max = click_up_max or AUTOCLICK_UP_DELAY_MAX

        self.mouse_listener = MouseListener(on_click=self._on_mouse_click)
        self.mouse_listener.start()
    
    def _on_mouse_click(self, x: int, y: int, button: Button, pressed: bool) -> None:
        """
        Callback to detect when left mouse button is pressed/released.
        Tracks REAL button state and ignores simulated events.
        """
        if button != Button.left:
            return

        if pressed:
            if self._is_simulated_press():
                return
            self.left_button_pressed = True
            if self.macro_active_callback and self.macro_active_callback():
                self._start_autoclick()
        else:
            if self._is_simulated_release():
                return
            self.left_button_pressed = False
            self._stop_autoclick()

    def _is_simulated_press(self) -> bool:
        """Check if current press is simulated."""
        with self._click_lock:
            if self.simulated_presses_pending > 0:
                self.simulated_presses_pending -= 1
                return True
        return False

    def _is_simulated_release(self) -> bool:
        """Check if current release is simulated."""
        with self._click_lock:
            if self.simulated_releases_pending > 0:
                self.simulated_releases_pending -= 1
                return True
        return False
    
    def _send_click(self, button_down: bool = True) -> None:
        """
        Send click event using Interception driver.
        
        Args:
            button_down: True for mouse down, False for mouse up
        """
        if not INTERCEPTION_AVAILABLE:
            print("ERROR: Interception not available", file=sys.stderr)
            return

        try:
            if button_down:
                interception.mouse_down("left")
            else:
                interception.mouse_up("left")
        except Exception as e:
            print(f"Interception send error: {e}", file=sys.stderr)
    
    def _autoclick_loop(self) -> None:
        """
        Auto-click loop - simulates clicks while user holds left button.
        Uses random delays to appear more human-like.
        """
        if self.macro_active_callback and self.macro_active_callback():
            print("  [Auto-click thread started]")

        POLL_INTERVAL = 0.01

        while not self.should_stop_autoclick:
            if not self._should_continue_clicking():
                time.sleep(POLL_INTERVAL)
                continue

            try:
                self._perform_click_cycle()
            except Exception as e:
                print(f"Auto-click error: {e}", file=sys.stderr)
                break

        if self.autoclick_running:
            print("  [Auto-click thread stopped]")
        self.autoclick_running = False

    def _should_continue_clicking(self) -> bool:
        """Check if auto-click should continue."""
        return (
            self.macro_active_callback
            and self.macro_active_callback()
            and self.left_button_pressed
        )

    def _perform_click_cycle(self) -> None:
        """Perform a single click cycle (down and up)."""
        with self._click_lock:
            self.simulated_presses_pending += 1

        self._send_click(button_down=True)
        down_delay = random.randint(self.click_down_min, self.click_down_max) / 1000.0
        time.sleep(down_delay)

        with self._click_lock:
            self.simulated_releases_pending += 1

        self._send_click(button_down=False)
        up_delay = random.randint(self.click_up_min, self.click_up_max) / 1000.0
        time.sleep(up_delay)
    
    def _start_autoclick(self) -> None:
        """Start auto-click thread if not already running."""
        if (
            not self.autoclick_running
            and self.macro_active_callback
            and self.macro_active_callback()
        ):
            self.autoclick_running = True
            self.should_stop_autoclick = False
            self.autoclick_thread = threading.Thread(
                target=self._autoclick_loop, daemon=True
            )
            self.autoclick_thread.start()

    def _stop_autoclick(self) -> None:
        """Stop auto-click thread."""
        if not self.autoclick_running:
            return

        self.should_stop_autoclick = True
        if self.autoclick_thread and self.autoclick_thread.is_alive():
            self.autoclick_thread.join(timeout=1.0)
        self.autoclick_running = False

        with self._click_lock:
            self.simulated_presses_pending = 0
            self.simulated_releases_pending = 0

    def start_if_button_pressed(self) -> None:
        """Start auto-click if button is already pressed."""
        if self.left_button_pressed:
            self._start_autoclick()

    def stop(self) -> None:
        """Stop auto-click and cleanup."""
        self._stop_autoclick()
        if self.mouse_listener:
            self.mouse_listener.stop()
    
    @staticmethod
    def is_available() -> bool:
        """Check if Interception driver is available."""
        return INTERCEPTION_AVAILABLE

