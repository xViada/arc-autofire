"""
GUI for ARC-AutoFire - Intelligent Macro System for Arc Raiders.
"""

import ctypes

# Set Windows AppUserModelID BEFORE tkinter import to show custom taskbar icon
try:
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("xViada.ARC-AutoFire.1.0")
except Exception:
    pass

import queue
import re
import threading
import time
from pathlib import Path
from typing import Optional, Tuple, Dict, Any
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import win32gui
import cv2
import mss
import numpy as np
from PIL import Image, ImageTk
from pynput import keyboard
from pynput.keyboard import Key, KeyCode
import pystray

from .config_manager import ConfigManager
from .config import FALLBACK_DELAYS
from .macro_activator import MacroActivator
from .window_detection import clean_window_title
from .image_paths import (
    get_assets_dir,
    get_templates_dir,
    get_captured_dir,
    get_previews_dir,
    find_template_file,
    get_captured_path,
    get_preview_path,
    get_asset_path
)

# Constants
PREVIEW_MAX_WIDTH = 1200
PREVIEW_MAX_HEIGHT = 800
LOG_PROCESS_INTERVAL = 100  # milliseconds
PREVIEW_DISPLAY_TIME = 3000  # milliseconds


class RegionSelector:
    """Window for selecting regions from screenshot."""

    def __init__(
        self, parent: tk.Tk, screenshot_path: str, callback: callable
    ) -> None:
        """
        Initialize region selector.
        
        Args:
            parent: Parent window
            screenshot_path: Path to screenshot image
            callback: Callback function when region is selected
        """
        self.parent = parent
        self.callback = callback
        self.screenshot_path = screenshot_path

        self.img = Image.open(screenshot_path)
        self.zoom = 1.0
        self.pan_x = 0
        self.pan_y = 0

        self.start_x: Optional[int] = None
        self.start_y: Optional[int] = None
        self.end_x: Optional[int] = None
        self.end_y: Optional[int] = None
        self.rect_id: Optional[int] = None
        
        # Create window
        self.window = tk.Toplevel(parent)
        self.window.title("Select Region - Left click to select, Right click to pan, Wheel to zoom")
        self.window.attributes("-topmost", True)
        
        # Set initial window size (fit to screen but not too large)
        screen_width = self.window.winfo_screenwidth()
        screen_height = self.window.winfo_screenheight()
        window_width = min(self.img.width, screen_width - 100)
        window_height = min(self.img.height + 100, screen_height - 100)
        self.window.geometry(f"{window_width}x{window_height}+50+50")
        
        # Canvas for image
        self.canvas = tk.Canvas(self.window, cursor="crosshair", bg="black")
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        # Bind events
        self.canvas.bind("<Button-1>", self.on_click)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.canvas.bind("<MouseWheel>", self.on_wheel)
        self.canvas.bind("<Button-4>", self.on_wheel)
        self.canvas.bind("<Button-5>", self.on_wheel)
        # Pan with right mouse button
        self.canvas.bind("<Button-3>", self.on_pan_start)
        self.canvas.bind("<B3-Motion>", self.on_pan_drag)
        self.pan_start_x = None
        self.pan_start_y = None
        
        # Buttons frame
        btn_frame = tk.Frame(self.window)
        btn_frame.pack(fill=tk.X, padx=5, pady=5)
        
        tk.Button(btn_frame, text="Set as Weapon Region (Slot 2)", 
                 command=lambda: self.set_region("weapon")).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Set as Weapon Region (Slot 1)", 
                 command=lambda: self.set_region("weapon_alt")).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Set as Menu Region", 
                 command=lambda: self.set_region("menu")).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Cancel", 
                 command=self.window.destroy).pack(side=tk.RIGHT, padx=5)
        
        # Info label
        self.info_label = tk.Label(
            self.window, 
            text="Left click + drag to select region | Right click + drag to pan | Mouse wheel to zoom"
        )
        self.info_label.pack()
        
        # Display image
        self.update_display()
        
        # Handle window close
        self.window.protocol("WM_DELETE_WINDOW", self.window.destroy)
    
    def on_wheel(self, event: tk.Event) -> None:
        """Handle mouse wheel for zoom."""
        ZOOM_FACTOR = 1.1
        MIN_ZOOM = 0.1
        MAX_ZOOM = 5.0
        
        if event.delta > 0 or event.num == 4:
            self.zoom *= ZOOM_FACTOR
        else:
            self.zoom /= ZOOM_FACTOR
        self.zoom = max(MIN_ZOOM, min(MAX_ZOOM, self.zoom))
        self.update_display()
    
    def on_pan_start(self, event):
        """Start panning."""
        self.pan_start_x = event.x
        self.pan_start_y = event.y
    
    def on_pan_drag(self, event):
        """Handle panning."""
        if self.pan_start_x is not None and self.pan_start_y is not None:
            dx = event.x - self.pan_start_x
            dy = event.y - self.pan_start_y
            self.pan_x += dx
            self.pan_y += dy
            self.pan_start_x = event.x
            self.pan_start_y = event.y
            self.update_display()
    
    def on_click(self, event):
        """Handle mouse click start."""
        self.start_x = event.x
        self.start_y = event.y
        self.end_x = None
        self.end_y = None
        if self.rect_id:
            self.canvas.delete(self.rect_id)
    
    def on_drag(self, event):
        """Handle mouse drag."""
        if self.start_x is not None:
            self.end_x = event.x
            self.end_y = event.y
            if self.rect_id:
                self.canvas.delete(self.rect_id)
            self.rect_id = self.canvas.create_rectangle(
                self.start_x, self.start_y, self.end_x, self.end_y,
                outline="red", width=2
            )
    
    def on_release(self, event):
        """Handle mouse release."""
        if self.start_x is not None and self.end_x is not None:
            # Convert canvas coordinates to image coordinates
            img_x1 = int((self.start_x - self.pan_x) / self.zoom)
            img_y1 = int((self.start_y - self.pan_y) / self.zoom)
            img_x2 = int((self.end_x - self.pan_x) / self.zoom)
            img_y2 = int((self.end_y - self.pan_y) / self.zoom)
            
            # Ensure correct order
            left = min(img_x1, img_x2)
            right = max(img_x1, img_x2)
            top = min(img_y1, img_y2)
            bottom = max(img_y1, img_y2)
            
            if right > left and bottom > top:
                self.info_label.config(
                    text=f"Region: ({left}, {top}, {right}, {bottom}) - Size: {right-left}x{bottom-top}"
                )
    
    def set_region(self, region_type):
        """Set the selected region."""
        if self.start_x is None or self.end_x is None:
            messagebox.showwarning("No Selection", "Please select a region first.")
            return
        
        # Convert to image coordinates
        img_x1 = int((self.start_x - self.pan_x) / self.zoom)
        img_y1 = int((self.start_y - self.pan_y) / self.zoom)
        img_x2 = int((self.end_x - self.pan_x) / self.zoom)
        img_y2 = int((self.end_y - self.pan_y) / self.zoom)
        
        left = min(img_x1, img_x2)
        right = max(img_x1, img_x2)
        top = min(img_y1, img_y2)
        bottom = max(img_y1, img_y2)
        
        if right <= left or bottom <= top:
            messagebox.showwarning("Invalid Selection", "Please select a valid region.")
            return
        
        # Crop and save image
        region_img = self.img.crop((left, top, right, bottom))
        # Save to templates directory (default templates)
        if region_type == "weapon":
            filename = "weapon.png"
        elif region_type == "weapon_alt":
            filename = "weapon_alt.png"
        else:
            filename = "menu.png"
        save_path = get_templates_dir() / filename
        region_img.save(save_path)
        
        # Call callback with region coordinates
        self.callback(region_type, (left, top, right, bottom))
        self.window.destroy()
    
    def update_display(self):
        """Update canvas display."""
        # Calculate display size
        display_width = int(self.img.width * self.zoom)
        display_height = int(self.img.height * self.zoom)
        
        # Resize image
        resized = self.img.resize((display_width, display_height), Image.Resampling.LANCZOS)
        
        # Convert to PhotoImage
        self.photo = ImageTk.PhotoImage(resized)
        
        # Update canvas
        self.canvas.delete("all")
        self.canvas.create_image(
            self.pan_x, self.pan_y, anchor=tk.NW, image=self.photo
        )
        self.canvas.config(scrollregion=self.canvas.bbox("all"))


class MacroGUI:
    """Main GUI application."""

    def __init__(self) -> None:
        """Initialize the GUI application."""
        self.config_manager = ConfigManager()
        self.macro_activator: Optional[MacroActivator] = None
        self.macro_thread: Optional[threading.Thread] = None
        self.macro_running = False
        self.macro_paused = False
        self.should_stop = False

        # Status indicators
        self.weapon_detected = False
        self.menu_detected = False
        self.macro_active = False
        self.autoclick_running = False

        # Global keybind listener
        self.keybind_listener: Optional[keyboard.Listener] = None

        # Capture screen listener (temporary)
        self.capture_listener: Optional[keyboard.Listener] = None
        self.waiting_for_capture = False
        
        # Keybind recording state
        self.keybind_recording_listener: Optional[keyboard.Listener] = None
        self.recording_keybind_type: Optional[str] = None  # "stop", "capture_screen"
        self.recording_modifiers = {"alt": False, "ctrl": False, "shift": False}
        self.capture_mode: Optional[str] = None  # "capture" or "autodetect"
        self.autodetect_step = 1  # 1 = first capture, 2 = second capture
        self.first_capture_results: Optional[Dict[str, Any]] = None
        self.alt_pressed = False
        self.ctrl_pressed = False
        self.shift_pressed = False
        
        # Template capture state
        self.template_capture_mode: Optional[str] = None  # "weapon_slot1", "weapon_slot2", "menu"
        self.template_capture_weapon_id: Optional[str] = None
        self.template_capture_step = 0  # 0 = not capturing, 1 = slot1, 2 = slot2

        # Log queue for thread-safe logging
        self.log_queue = queue.Queue()
        
        # Create GUI
        self.root = tk.Tk()
        self.root.title("ARC-AutoFire by xViada")
        icon_path = get_asset_path("icon.ico")
        if icon_path.exists():
            self.root.iconbitmap(str(icon_path.absolute()))
        
        # System tray icon
        self.tray_icon: Optional[pystray.Icon] = None
        self.tray_thread: Optional[threading.Thread] = None
        self._setup_tray_icon(icon_path)
        
        # Load window position/size
        pos = self.config_manager.get("gui.window_position", [100, 100])
        size = self.config_manager.get("gui.window_size", [500, 700])
        self.root.geometry(f"{size[0]}x{size[1]}+{pos[0]}+{pos[1]}")
        
        # Handle window close
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Create UI
        self.create_ui()
        
        # Start log processor
        self.root.after(LOG_PROCESS_INTERVAL, self.process_log_queue)
        
        # Start global keybind listener
        self.start_keybind_listener()
    
    def create_ui(self):
        """Create the UI components."""
        # Notebook for tabs
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=(5, 0))
        
        # Tab 1: Delays Configuration
        settings_frame = ttk.Frame(notebook)
        notebook.add(settings_frame, text="Settings")
        self.create_delays_panel(settings_frame)
        
        # Tab 2: Region Setup
        regions_frame = ttk.Frame(notebook)
        notebook.add(regions_frame, text="Regions")
        self.create_regions_panel(regions_frame)
        
        # Tab 3: Templates
        templates_frame = ttk.Frame(notebook)
        notebook.add(templates_frame, text="Templates")
        self.create_templates_panel(templates_frame)
        
        # Tab 4: Keybinds
        keybinds_frame = ttk.Frame(notebook)
        notebook.add(keybinds_frame, text="Keybinds")
        self.create_keybinds_panel(keybinds_frame)
        
        # Tab 5: Status/Logs
        status_frame = ttk.Frame(notebook)
        notebook.add(status_frame, text="Status")
        self.create_status_panel(status_frame)
        
        # Main controls at bottom
        self.create_main_controls()
    
    def create_delays_panel(self, parent):
        """Create delays configuration panel with per-weapon settings."""
        # Detection settings frame
        detection_frame = ttk.LabelFrame(parent, text="Detection Settings", padding=10)
        detection_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Detection Loop Delay
        ttk.Label(detection_frame, text="Detection Loop Delay (s):").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.loop_delay_var = tk.StringVar(value=str(self.config_manager.get("delays.detection_loop")))
        ttk.Entry(detection_frame, textvariable=self.loop_delay_var, width=10).grid(row=0, column=1, sticky=tk.W, padx=5)
        self.loop_delay_var.trace("w", lambda *args: self.save_delays())
        
        # Hash Threshold
        ttk.Label(detection_frame, text="Hash Threshold (0-256):").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.threshold_var = tk.StringVar(value=str(self.config_manager.get("detection.hash_threshold")))
        ttk.Entry(detection_frame, textvariable=self.threshold_var, width=10).grid(row=1, column=1, sticky=tk.W, padx=5)
        self.threshold_var.trace("w", lambda *args: self.save_delays())
        
        # Weapons configuration frame with scrollable area
        weapons_outer_frame = ttk.LabelFrame(parent, text="Weapon Delays (ms)", padding=10)
        weapons_outer_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Create scrollable canvas for weapons
        canvas = tk.Canvas(weapons_outer_frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(weapons_outer_frame, orient="vertical", command=canvas.yview)
        self.weapons_frame = ttk.Frame(canvas)
        
        self.weapons_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=self.weapons_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Store weapon delay variables
        self.weapon_delay_vars = {}
        
        # Get weapons from config
        weapons = self.config_manager.get("weapons", {})
        
        for idx, (weapon_id, weapon_config) in enumerate(weapons.items()):
            self._create_weapon_delay_widgets(weapon_id, weapon_config, idx)
        
        # Legacy delay variables (kept for backwards compatibility)
        self.down_min_var = tk.StringVar(value=str(self.config_manager.get("delays.click_down_min")))
        self.down_max_var = tk.StringVar(value=str(self.config_manager.get("delays.click_down_max")))
        self.up_min_var = tk.StringVar(value=str(self.config_manager.get("delays.click_up_min")))
        self.up_max_var = tk.StringVar(value=str(self.config_manager.get("delays.click_up_max")))
    
    def _create_weapon_delay_widgets(self, weapon_id: str, weapon_config: dict, row_idx: int):
        """Create delay configuration widgets for a single weapon."""
        weapon_name = weapon_config.get("name", weapon_id.capitalize())
        enabled = weapon_config.get("enabled", True)
        profile = weapon_config.get("profile", "custom")
        default_profiles = weapon_config.get("default_profiles", {})
        delays = weapon_config.get("delays", {})
        
        # Weapon frame
        weapon_frame = ttk.LabelFrame(self.weapons_frame, text=weapon_name, padding=5)
        weapon_frame.pack(fill=tk.X, pady=5, padx=5)
        
        # Top row: Enabled checkbox and Profile dropdown
        top_frame = ttk.Frame(weapon_frame)
        top_frame.grid(row=0, column=0, columnspan=2, sticky=tk.W, padx=5, pady=2)
        
        # Enabled checkbox
        enabled_var = tk.BooleanVar(value=enabled)
        enabled_cb = ttk.Checkbutton(
            top_frame, 
            text="Enabled", 
            variable=enabled_var,
            command=lambda wid=weapon_id, var=enabled_var: self._save_weapon_enabled(wid, var.get())
        )
        enabled_cb.pack(side=tk.LEFT, padx=(0, 15))
        
        # Build profile options from default_profiles + "Custom"
        # Format: {display_name: profile_key}
        profile_options = {}
        for profile_key, profile_data in default_profiles.items():
            display_name = profile_data.get("name", profile_key.capitalize())
            profile_options[display_name] = profile_key
        profile_options["Custom"] = "custom"
        
        # Get current display name for profile
        current_display = "Custom"
        for display_name, profile_key in profile_options.items():
            if profile_key == profile:
                current_display = display_name
                break
        
        # Profile dropdown
        ttk.Label(top_frame, text="Profile:").pack(side=tk.LEFT)
        profile_var = tk.StringVar(value=current_display)
        profile_combo = ttk.Combobox(
            top_frame, 
            textvariable=profile_var, 
            values=list(profile_options.keys()),
            state="readonly",
            width=10
        )
        profile_combo.pack(side=tk.LEFT, padx=5)
        
        # Get current delays based on profile
        if profile in default_profiles:
            current_delays = default_profiles[profile].get("delays", FALLBACK_DELAYS)
        else:
            current_delays = delays if delays else FALLBACK_DELAYS
        
        # Click Down Delay
        down_frame = ttk.Frame(weapon_frame)
        down_frame.grid(row=1, column=0, sticky=tk.W, padx=5, pady=2)
        ttk.Label(down_frame, text="Down:").pack(side=tk.LEFT)
        
        down_min_var = tk.StringVar(value=str(current_delays.get("click_down_min", 54)))
        down_min_entry = ttk.Entry(down_frame, textvariable=down_min_var, width=5)
        down_min_entry.pack(side=tk.LEFT, padx=2)
        
        ttk.Label(down_frame, text="-").pack(side=tk.LEFT)
        
        down_max_var = tk.StringVar(value=str(current_delays.get("click_down_max", 64)))
        down_max_entry = ttk.Entry(down_frame, textvariable=down_max_var, width=5)
        down_max_entry.pack(side=tk.LEFT, padx=2)
        
        # Click Up Delay
        up_frame = ttk.Frame(weapon_frame)
        up_frame.grid(row=1, column=1, sticky=tk.W, padx=5, pady=2)
        ttk.Label(up_frame, text="Up:").pack(side=tk.LEFT)
        
        up_min_var = tk.StringVar(value=str(current_delays.get("click_up_min", 54)))
        up_min_entry = ttk.Entry(up_frame, textvariable=up_min_var, width=5)
        up_min_entry.pack(side=tk.LEFT, padx=2)
        
        ttk.Label(up_frame, text="-").pack(side=tk.LEFT)
        
        up_max_var = tk.StringVar(value=str(current_delays.get("click_up_max", 64)))
        up_max_entry = ttk.Entry(up_frame, textvariable=up_max_var, width=5)
        up_max_entry.pack(side=tk.LEFT, padx=2)
        
        # Store entry widgets for enabling/disabling
        delay_entries = [down_min_entry, down_max_entry, up_min_entry, up_max_entry]
        
        # Set initial state based on profile (disabled if using a default profile)
        is_custom = profile == "custom" or profile not in default_profiles
        entry_state = "normal" if is_custom else "disabled"
        for entry in delay_entries:
            entry.config(state=entry_state)
        
        # Store variables and profile options mapping
        self.weapon_delay_vars[weapon_id] = {
            "enabled": enabled_var,
            "profile": profile_var,
            "profile_options": profile_options,
            "default_profiles": default_profiles,
            "down_min": down_min_var,
            "down_max": down_max_var,
            "up_min": up_min_var,
            "up_max": up_max_var,
            "entries": delay_entries,
        }
        
        # Profile change handler
        def on_profile_change(event, wid=weapon_id):
            self._on_profile_change(wid)
        
        profile_combo.bind("<<ComboboxSelected>>", on_profile_change)
        
        # Bind trace for auto-save (only for custom profile)
        for var_name, var in [("down_min", down_min_var), ("down_max", down_max_var), 
                              ("up_min", up_min_var), ("up_max", up_max_var)]:
            var.trace("w", lambda *args, wid=weapon_id: self._save_weapon_delays(wid))
    
    def _save_weapon_enabled(self, weapon_id: str, enabled: bool):
        """Save weapon enabled state."""
        self.config_manager.set(f"weapons.{weapon_id}.enabled", enabled)
        self.config_manager.save()
    
    def _on_profile_change(self, weapon_id: str):
        """Handle profile change for a weapon."""
        if weapon_id not in self.weapon_delay_vars:
            return
        
        vars_dict = self.weapon_delay_vars[weapon_id]
        display_name = vars_dict["profile"].get()
        profile_options = vars_dict.get("profile_options", {})
        default_profiles = vars_dict.get("default_profiles", {})
        entries = vars_dict.get("entries", [])
        
        # Get profile key from display name
        profile_key = profile_options.get(display_name, "custom")
        
        # Save the profile key
        self.config_manager.set(f"weapons.{weapon_id}.profile", profile_key)
        
        if profile_key in default_profiles:
            # Set values from default profile and disable entries
            profile_delays = default_profiles[profile_key].get("delays", FALLBACK_DELAYS)
            vars_dict["down_min"].set(str(profile_delays.get("click_down_min", 54)))
            vars_dict["down_max"].set(str(profile_delays.get("click_down_max", 64)))
            vars_dict["up_min"].set(str(profile_delays.get("click_up_min", 54)))
            vars_dict["up_max"].set(str(profile_delays.get("click_up_max", 64)))
            for entry in entries:
                entry.config(state="disabled")
        else:
            # Custom profile - enable entries and load saved custom values
            custom_delays = self.config_manager.get(f"weapons.{weapon_id}.delays", FALLBACK_DELAYS)
            vars_dict["down_min"].set(str(custom_delays.get("click_down_min", 54)))
            vars_dict["down_max"].set(str(custom_delays.get("click_down_max", 64)))
            vars_dict["up_min"].set(str(custom_delays.get("click_up_min", 54)))
            vars_dict["up_max"].set(str(custom_delays.get("click_up_max", 64)))
            for entry in entries:
                entry.config(state="normal")
        
        self.config_manager.save()
    
    def _save_weapon_delays(self, weapon_id: str):
        """Save weapon delay configuration."""
        if weapon_id not in self.weapon_delay_vars:
            return
        
        vars_dict = self.weapon_delay_vars[weapon_id]
        try:
            delays = {
                "click_down_min": int(vars_dict["down_min"].get()),
                "click_down_max": int(vars_dict["down_max"].get()),
                "click_up_min": int(vars_dict["up_min"].get()),
                "click_up_max": int(vars_dict["up_max"].get()),
            }
            self.config_manager.set(f"weapons.{weapon_id}.delays", delays)
            self.config_manager.save()
        except ValueError:
            pass  # Invalid input, ignore
    
    def save_delays(self):
        """Save delay configuration."""
        try:
            # Save detection settings
            self.config_manager.set("delays.detection_loop", float(self.loop_delay_var.get()))
            self.config_manager.set("detection.hash_threshold", int(self.threshold_var.get()))
            
            # Legacy delay settings (backwards compatibility)
            if hasattr(self, 'down_min_var'):
                self.config_manager.set("delays.click_down_min", int(self.down_min_var.get()))
                self.config_manager.set("delays.click_down_max", int(self.down_max_var.get()))
                self.config_manager.set("delays.click_up_min", int(self.up_min_var.get()))
                self.config_manager.set("delays.click_up_max", int(self.up_max_var.get()))
            
            self.config_manager.save()
        except ValueError:
            pass  # Invalid input, ignore
    
    def create_regions_panel(self, parent):
        """Create region setup panel."""
        # Instructions frame
        instructions_frame = ttk.LabelFrame(parent, text="Instructions", padding=10)
        instructions_frame.pack(fill=tk.X, padx=5, pady=5)
        
        instructions_text = (
            "1. Use 'Capture Screen' to take a screenshot and manually select regions\n"
            "2. Use 'Auto-detect Regions' to automatically find regions (2 steps: Slot 1, then Slot 2)\n"
            "3. Adjust confidence threshold if auto-detection fails\n"
            "4. Regions are saved automatically when set"
        )
        ttk.Label(instructions_frame, text=instructions_text, justify=tk.LEFT).pack(anchor=tk.W)
        
        frame = ttk.LabelFrame(parent, text="Region Configuration", padding=10)
        frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Buttons frame
        buttons_frame = ttk.Frame(frame)
        buttons_frame.pack(fill=tk.X, pady=5)
        
        # Capture Screen button
        self.capture_btn = ttk.Button(buttons_frame, text="Capture Screen", command=self.start_capture_wait)
        self.capture_btn.pack(side=tk.LEFT, padx=5)
        
        # Auto-detect Regions button
        self.autodetect_btn = ttk.Button(buttons_frame, text="Auto-detect Regions", command=self.auto_detect_regions)
        self.autodetect_btn.pack(side=tk.LEFT, padx=5)
        
        # Confidence threshold frame
        threshold_frame = ttk.Frame(frame)
        threshold_frame.pack(fill=tk.X, pady=5)
        ttk.Label(threshold_frame, text="Confidence Threshold:").pack(side=tk.LEFT)
        threshold_value = self.config_manager.get("detection.confidence_threshold", 0.8)
        self.confidence_threshold_var = tk.DoubleVar(value=threshold_value)
        threshold_scale = ttk.Scale(
            threshold_frame, 
            from_=0.5, 
            to=1.0, 
            variable=self.confidence_threshold_var,
            orient=tk.HORIZONTAL,
            length=150
        )
        threshold_scale.pack(side=tk.LEFT, padx=5)
        self.confidence_label = ttk.Label(threshold_frame, text=f"{threshold_value:.2f}")
        self.confidence_label.pack(side=tk.LEFT, padx=5)
        threshold_scale.configure(command=lambda v: self.confidence_label.config(text=f"{float(v):.2f}"))
        
        # Capture status label
        self.capture_status_label = ttk.Label(frame, text="", foreground="blue")
        self.capture_status_label.pack(pady=5)
        
        # Region previews
        preview_frame = ttk.LabelFrame(frame, text="Current Regions", padding=10)
        preview_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # Weapon region (slot 2)
        weapon_frame = ttk.Frame(preview_frame)
        weapon_frame.pack(fill=tk.X, pady=5)
        ttk.Label(weapon_frame, text="Weapon Region (Slot 2):").pack(side=tk.LEFT)
        self.weapon_coords_label = ttk.Label(weapon_frame, text="Not set")
        self.weapon_coords_label.pack(side=tk.LEFT, padx=10)
        
        # Weapon region alt (slot 1)
        weapon_alt_frame = ttk.Frame(preview_frame)
        weapon_alt_frame.pack(fill=tk.X, pady=5)
        ttk.Label(weapon_alt_frame, text="Weapon Region (Slot 1):").pack(side=tk.LEFT)
        self.weapon_alt_coords_label = ttk.Label(weapon_alt_frame, text="Not set")
        self.weapon_alt_coords_label.pack(side=tk.LEFT, padx=10)
        
        # Menu region
        menu_frame = ttk.Frame(preview_frame)
        menu_frame.pack(fill=tk.X, pady=5)
        ttk.Label(menu_frame, text="Menu Region:").pack(side=tk.LEFT)
        self.menu_coords_label = ttk.Label(menu_frame, text="Not set")
        self.menu_coords_label.pack(side=tk.LEFT, padx=10)
        
        # Update preview after both labels are created
        self.update_region_preview()
    
    def auto_detect_regions(self):
        """Start waiting for capture keybind to auto-detect regions."""
        if self.waiting_for_capture and self.capture_mode == "autodetect":
            self.cancel_capture_wait()
            return
        
        self.waiting_for_capture = True
        self.capture_mode = "autodetect"
        self.autodetect_step = 1  # Start with step 1
        self.first_capture_results = None
        self.autodetect_btn.config(text="Cancel Auto-detect", state=tk.NORMAL)
        self.capture_btn.config(state=tk.DISABLED)  # Disable capture button while autodetect is waiting
        self.capture_status_label.config(
            text=f"Step 1/2: Capture with weapon in Slot 1. Press: {self.config_manager.get('keybinds.capture_screen', 'ALT+P')}",
            foreground="blue"
        )
        self.log(f"Auto-detect Step 1/2: Waiting for capture with weapon in Slot 1. Press: {self.config_manager.get('keybinds.capture_screen', 'ALT+P')}")
        
        # Start listener for capture keybind
        self.start_capture_listener()
    
    def _auto_detect_regions_thread(self, step=1):
        """Auto-detect regions thread."""
        try:
            # Get confidence threshold
            confidence_threshold = self.confidence_threshold_var.get()
            self.config_manager.set("detection.confidence_threshold", confidence_threshold)
            self.config_manager.save()
            
            # Capture screen using the same method
            screen_img, screen_gray, monitor_info = self._capture_screen_for_detection()
            
            # Load templates
            # Find the first enabled weapon template
            weapons_config = self.config_manager.get("weapons", {})
            weapon_template_path = None
            weapon_template_name = None
            
            for weapon_id, weapon_data in weapons_config.items():
                if weapon_data.get("enabled", True):
                    template_name = weapon_data.get("template", f"{weapon_id}.png")
                    template_path = find_template_file(template_name)
                    if template_path:
                        weapon_template_path = template_path
                        weapon_template_name = template_name
                        break
            
            menu_template_path = find_template_file("menu.png")
            
            if step == 1:
                # Step 1: Detect menu and weapon in slot 1
                if weapon_template_path is None:
                    self.root.after(0, lambda: self._show_detection_error("No enabled weapon template found in /images.\nAdd a weapon with a valid template first."))
                    return
                
                if not menu_template_path.exists():
                    self.root.after(0, lambda: self._show_detection_error("menu.png not found in /images"))
                    return
                
                # Load templates
                weapon_template = cv2.imread(str(weapon_template_path), cv2.IMREAD_GRAYSCALE)
                menu_template = cv2.imread(str(menu_template_path), cv2.IMREAD_GRAYSCALE)
                
                if weapon_template is None:
                    self.root.after(0, lambda msg=weapon_template_name: self._show_detection_error(f"Failed to load {msg}"))
                    return
                
                if menu_template is None:
                    self.root.after(0, lambda: self._show_detection_error("Failed to load menu.png"))
                    return
                
                # Perform template matching
                weapon_result = cv2.matchTemplate(screen_gray, weapon_template, cv2.TM_CCOEFF_NORMED)
                menu_result = cv2.matchTemplate(screen_gray, menu_template, cv2.TM_CCOEFF_NORMED)
                
                # Find best matches
                _, weapon_max_val, _, weapon_max_loc = cv2.minMaxLoc(weapon_result)
                _, menu_max_val, _, menu_max_loc = cv2.minMaxLoc(menu_result)
                
                # Check if both found with sufficient confidence
                weapon_found = weapon_max_val >= confidence_threshold
                menu_found = menu_max_val >= confidence_threshold
                
                # Calculate regions (slot 1 stored as weapon_alt_region, will be saved to regions.weapon)
                weapon_alt_region = None
                menu_region = None
                
                if weapon_found:
                    h, w = weapon_template.shape
                    weapon_alt_region = (
                        weapon_max_loc[0],
                        weapon_max_loc[1],
                        weapon_max_loc[0] + w,
                        weapon_max_loc[1] + h
                    )
                
                if menu_found:
                    h, w = menu_template.shape
                    menu_region = (
                        menu_max_loc[0],
                        menu_max_loc[1],
                        menu_max_loc[0] + w,
                        menu_max_loc[1] + h
                    )
                
                # Store results for step 2
                self.first_capture_results = {
                    'weapon_alt_found': weapon_found,
                    'weapon_alt_region': weapon_alt_region,
                    'weapon_alt_confidence': weapon_max_val,
                    'menu_found': menu_found,
                    'menu_region': menu_region,
                    'menu_confidence': menu_max_val,
                    'monitor_info': monitor_info,
                    'screen_img': screen_img,
                    'weapon_template': weapon_template  # Store template for step 2
                }
                
                # Show results and ask for step 2
                self.root.after(0, lambda: self._show_step1_results(
                    screen_img, weapon_found, weapon_alt_region, weapon_max_val,
                    menu_found, menu_region, menu_max_val, confidence_threshold, monitor_info
                ))
                
            elif step == 2:
                # Step 2: Detect weapon in slot 2 using the same weapon template
                if weapon_template_path is None:
                    self.root.after(0, lambda: self._show_detection_error("No enabled weapon template found in /images.\nAdd a weapon with a valid template first."))
                    return
                
                # Use the same weapon template from step 1 if available, otherwise load it
                if self.first_capture_results and 'weapon_template' in self.first_capture_results:
                    weapon_template = self.first_capture_results['weapon_template']
                else:
                    weapon_template = cv2.imread(str(weapon_template_path), cv2.IMREAD_GRAYSCALE)
                
                if weapon_template is None:
                    self.root.after(0, lambda msg=weapon_template_name: self._show_detection_error(f"Failed to load {msg}"))
                    return
                
                # Perform template matching for weapon in slot 2 (same template, different position)
                weapon_result = cv2.matchTemplate(screen_gray, weapon_template, cv2.TM_CCOEFF_NORMED)
                _, weapon_max_val, _, weapon_max_loc = cv2.minMaxLoc(weapon_result)
                
                # Check if found with sufficient confidence
                weapon_found = weapon_max_val >= confidence_threshold
                
                # Calculate region (slot 2 stored as weapon_region, will be saved to regions.weapon_alt)
                weapon_region = None
                if weapon_found:
                    h, w = weapon_template.shape
                    weapon_region = (
                        weapon_max_loc[0],
                        weapon_max_loc[1],
                        weapon_max_loc[0] + w,
                        weapon_max_loc[1] + h
                    )
                
                # Combine results from both steps
                if self.first_capture_results:
                    self.root.after(0, lambda: self._show_final_detection_results(
                        self.first_capture_results['screen_img'],
                        weapon_found,
                        weapon_region,
                        weapon_max_val,
                        self.first_capture_results['weapon_alt_found'],
                        self.first_capture_results['weapon_alt_region'],
                        self.first_capture_results['weapon_alt_confidence'],
                        self.first_capture_results['menu_found'],
                        self.first_capture_results['menu_region'],
                        self.first_capture_results['menu_confidence'],
                        confidence_threshold,
                        self.first_capture_results['monitor_info']
                    ))
                else:
                    self.root.after(0, lambda: self._show_detection_error("Step 1 results not found. Please start over."))
            
        except Exception as e:
            self.root.after(0, lambda: self._show_detection_error(f"Detection error: {str(e)}"))
    
    def _show_detection_error(self, message: str):
        """Show detection error message."""
        self.autodetect_btn.config(text="Auto-detect Regions", state=tk.NORMAL)
        self.capture_btn.config(state=tk.NORMAL)
        self.capture_status_label.config(text="", foreground="blue")
        self.waiting_for_capture = False
        self.capture_mode = None
        self.autodetect_step = 1
        self.first_capture_results = None
        messagebox.showerror("Auto-detection Failed", message)
        self.log(f"Auto-detection failed: {message}")
    
    def _show_step1_results(self, screen_img, weapon_found, weapon_region, weapon_confidence,
                           menu_found, menu_region, menu_confidence, threshold, monitor_info):
        """Show step 1 results and prompt for step 2."""
        # Check if both found
        if not weapon_found and not menu_found:
            self._show_detection_error(f"Neither region found. Weapon: {weapon_confidence:.2%}, Menu: {menu_confidence:.2%} (threshold: {threshold:.2%})")
            return
        
        missing = []
        if not weapon_found:
            missing.append(f"weapon (confidence: {weapon_confidence:.2%}, threshold: {threshold:.2%})")
        if not menu_found:
            missing.append(f"menu (confidence: {menu_confidence:.2%}, threshold: {threshold:.2%})")
        
        if missing:
            self._show_detection_error(f"Missing regions: {', '.join(missing)}")
            return
        
        # Both found - show preview and ask for step 2
        preview_img = screen_img.copy()
        
        # Draw weapon region (green) - Slot 1
        cv2.rectangle(preview_img, 
                     (weapon_region[0], weapon_region[1]), 
                     (weapon_region[2], weapon_region[3]), 
                     (0, 255, 0), 2)
        # Calculate text position to avoid cutting off on the right side
        text_slot1 = f"Weapon (Slot 1): {weapon_confidence:.1%}"
        (text_width_slot1, text_height_slot1), _ = cv2.getTextSize(text_slot1, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
        img_width = preview_img.shape[1]
        text_x_slot1 = weapon_region[0]
        # If text would go off screen, move it left
        if text_x_slot1 + text_width_slot1 > img_width:
            text_x_slot1 = max(0, img_width - text_width_slot1 - 10)
        cv2.putText(preview_img, text_slot1, 
                   (text_x_slot1, weapon_region[1] - 10),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        
        # Draw menu region (blue)
        cv2.rectangle(preview_img,
                     (menu_region[0], menu_region[1]),
                     (menu_region[2], menu_region[3]),
                     (255, 0, 0), 2)
        cv2.putText(preview_img, f"Menu: {menu_confidence:.1%}",
                   (menu_region[0], menu_region[1] - 10),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 0), 2)
        
        # Save preview
        preview_path = get_preview_path("detection_preview_step1.png")
        cv2.imwrite(str(preview_path), preview_img)
        
        # Show preview window with step 2 prompt
        self._show_step1_preview_window(str(preview_path), weapon_region, weapon_confidence, menu_region, menu_confidence)
        
        # Continue to step 2
        self.autodetect_step = 2
        self.capture_status_label.config(
            text=f"Step 2/2: Capture with weapon in Slot 2. Press: {self.config_manager.get('keybinds.capture_screen', 'ALT+P')}",
            foreground="blue"
        )
        self.log(f"Step 1 complete - Weapon (Slot 1): {weapon_confidence:.1%} at {weapon_region}, Menu: {menu_confidence:.1%} at {menu_region}")
        self.log(f"Step 2/2: Waiting for capture with weapon in Slot 2. Press: {self.config_manager.get('keybinds.capture_screen', 'ALT+P')}")
        
        # Restart capture listener for step 2
        self.start_capture_listener()
    
    def _show_step1_preview_window(
        self,
        preview_path: str,
        weapon_region: Tuple[int, int, int, int],
        weapon_confidence: float,
        menu_region: Tuple[int, int, int, int],
        menu_confidence: float,
    ) -> None:
        """Show preview window for step 1 with step 2 prompt."""
        preview_window = tk.Toplevel(self.root)
        preview_window.title("Auto-detection Step 1/2 - Results")
        preview_window.attributes("-topmost", True)

        self._create_preview_info_frame(
            preview_window, weapon_region, weapon_confidence, menu_region, menu_confidence, step=1
        )
        self._create_preview_image_frame(preview_window, preview_path)
        self._create_preview_button_frame(preview_window, "Continue to Step 2")

    def _create_preview_info_frame(
        self,
        parent: tk.Toplevel,
        weapon_region: Tuple[int, int, int, int],
        weapon_confidence: float,
        menu_region: Tuple[int, int, int, int],
        menu_confidence: float,
        step: int = 1,
    ) -> None:
        """Create info frame for preview window."""
        info_frame = ttk.Frame(parent)
        info_frame.pack(fill=tk.X, padx=10, pady=10)

        if step == 1:
            ttk.Label(
                info_frame, text="Step 1/2 Complete!", font=("Arial", 12, "bold")
            ).pack(anchor=tk.W)
            ttk.Label(
                info_frame,
                text=f"Weapon Region (Slot 1): {weapon_region} - Confidence: {weapon_confidence:.1%}",
            ).pack(anchor=tk.W, padx=20)
            ttk.Label(
                info_frame,
                text=f"Menu Region: {menu_region} - Confidence: {menu_confidence:.1%}",
            ).pack(anchor=tk.W, padx=20)
            ttk.Label(info_frame, text="", font=("Arial", 10)).pack()
            ttk.Label(
                info_frame,
                text="Next: Capture screen with weapon in Slot 2",
                font=("Arial", 10, "bold"),
                foreground="blue",
            ).pack(anchor=tk.W, padx=20)
        else:
            ttk.Label(
                info_frame, text="Detection Results:", font=("Arial", 12, "bold")
            ).pack(anchor=tk.W)
            ttk.Label(
                info_frame,
                text=f"Weapon Region: {weapon_region} - Confidence: {weapon_confidence:.1%}",
            ).pack(anchor=tk.W, padx=20)
            ttk.Label(
                info_frame,
                text=f"Menu Region: {menu_region} - Confidence: {menu_confidence:.1%}",
            ).pack(anchor=tk.W, padx=20)

    def _create_preview_image_frame(
        self, parent: tk.Toplevel, preview_path: str
    ) -> None:
        """Create image frame for preview window."""
        img_frame = ttk.Frame(parent)
        img_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        img = Image.open(preview_path)
        img = self._resize_image_if_needed(img)

        photo = ImageTk.PhotoImage(img)
        canvas = tk.Canvas(img_frame, width=img.width, height=img.height)
        canvas.pack()
        canvas.create_image(0, 0, anchor=tk.NW, image=photo)
        canvas.image = photo

    def _create_preview_button_frame(
        self, parent: tk.Toplevel, button_text: str
    ) -> None:
        """Create button frame for preview window."""
        btn_frame = ttk.Frame(parent)
        btn_frame.pack(fill=tk.X, padx=10, pady=10)
        ttk.Button(btn_frame, text=button_text, command=parent.destroy).pack(
            side=tk.RIGHT
        )

    def _resize_image_if_needed(self, img: Image.Image) -> Image.Image:
        """Resize image if it exceeds maximum dimensions."""
        if img.width > PREVIEW_MAX_WIDTH or img.height > PREVIEW_MAX_HEIGHT:
            ratio = min(PREVIEW_MAX_WIDTH / img.width, PREVIEW_MAX_HEIGHT / img.height)
            new_width = int(img.width * ratio)
            new_height = int(img.height * ratio)
            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
        return img
    
    def _show_final_detection_results(self, screen_img, weapon_found, weapon_region, weapon_confidence,
                                     weapon_alt_found, weapon_alt_region, weapon_alt_confidence,
                                     menu_found, menu_region, menu_confidence, threshold, monitor_info):
        """Show final detection results combining both steps."""
        # Stop capture listener
        if self.capture_listener:
            self.capture_listener.stop()
            self.capture_listener = None
        
        self.autodetect_btn.config(text="Auto-detect Regions", state=tk.NORMAL)
        self.capture_btn.config(state=tk.NORMAL)
        self.waiting_for_capture = False
        self.capture_mode = None
        self.autodetect_step = 1
        self.first_capture_results = None
        self.alt_pressed = False
        self.ctrl_pressed = False
        self.shift_pressed = False
        
        # Check if weapon (slot 2) was found
        if not weapon_found:
            self.capture_status_label.config(
                text=f"Step 2: Weapon (Slot 2) not found (confidence: {weapon_confidence:.2%}, threshold: {threshold:.2%})",
                foreground="orange"
            )
            self.log(f"Step 2: Weapon (Slot 2) not found. Confidence: {weapon_confidence:.2%}, Threshold: {threshold:.2%}")
            # Continue anyway with just slot 1
        
        # Update regions (weapon_alt is slot 2, weapon is slot 1)
        # weapon_alt_region is slot 1 (from step 1), weapon_region is slot 2 (from step 2)
        if weapon_alt_region:
            self.config_manager.set("regions.weapon", list(weapon_alt_region))  # slot 1
        if weapon_region:
            self.config_manager.set("regions.weapon_alt", list(weapon_region))  # slot 2
        self.config_manager.set("regions.menu", list(menu_region))
        
        # Update screen resolution
        self.config_manager.set("regions.screen_resolution", [monitor_info["width"], monitor_info["height"]])
        
        self.config_manager.save()
        self.update_region_preview()
        
        # Create preview image with all regions marked
        preview_img = screen_img.copy()
        
        # Draw weapon region slot 2 (green)
        cv2.rectangle(preview_img, 
                     (weapon_region[0], weapon_region[1]), 
                     (weapon_region[2], weapon_region[3]), 
                     (0, 255, 0), 2)
        # Calculate text position to avoid cutting off on the right side
        text_slot2 = f"Weapon (Slot 2): {weapon_confidence:.1%}"
        (text_width_slot2, text_height_slot2), _ = cv2.getTextSize(text_slot2, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
        img_width = preview_img.shape[1]
        text_x_slot2 = weapon_region[0]
        # If text would go off screen, move it left
        if text_x_slot2 + text_width_slot2 > img_width:
            text_x_slot2 = max(0, img_width - text_width_slot2 - 10)
        cv2.putText(preview_img, text_slot2, 
                   (text_x_slot2, weapon_region[1] - 10),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        
        # Draw weapon region slot 1 if found (yellow)
        if weapon_alt_region:
            cv2.rectangle(preview_img,
                         (weapon_alt_region[0], weapon_alt_region[1]),
                         (weapon_alt_region[2], weapon_alt_region[3]),
                         (0, 255, 255), 2)
            # Calculate text position to avoid cutting off on the right side
            text_slot1 = f"Weapon (Slot 1): {weapon_alt_confidence:.1%}"
            (text_width_slot1, text_height_slot1), _ = cv2.getTextSize(text_slot1, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
            text_x_slot1 = weapon_alt_region[0]
            # If text would go off screen, move it left
            if text_x_slot1 + text_width_slot1 > img_width:
                text_x_slot1 = max(0, img_width - text_width_slot1 - 10)
            cv2.putText(preview_img, text_slot1,
                       (text_x_slot1, weapon_alt_region[1] - 10),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        
        # Draw menu region (blue)
        cv2.rectangle(preview_img,
                     (menu_region[0], menu_region[1]),
                     (menu_region[2], menu_region[3]),
                     (255, 0, 0), 2)
        cv2.putText(preview_img, f"Menu: {menu_confidence:.1%}",
                   (menu_region[0], menu_region[1] - 10),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 0), 2)
        
        # Save preview
        preview_path = get_preview_path("detection_preview.png")
        cv2.imwrite(str(preview_path), preview_img)
        
        # Show preview window
        self._show_preview_window(str(preview_path), weapon_region, weapon_confidence, menu_region, menu_confidence)
        
        status_text = f"Auto-detection complete! Weapon (Slot 2): {weapon_confidence:.1%}"
        if weapon_alt_region:
            status_text += f", Weapon (Slot 1): {weapon_alt_confidence:.1%}"
        else:
            status_text += f", Weapon (Slot 1): Not found"
        status_text += f", Menu: {menu_confidence:.1%}"
        self.capture_status_label.config(
            text=status_text,
            foreground="green"
        )
        log_text = f"Auto-detection complete - Weapon (Slot 2): {weapon_confidence:.1%} at {weapon_region}"
        if weapon_alt_region:
            log_text += f", Weapon (Slot 1): {weapon_alt_confidence:.1%} at {weapon_alt_region}"
        log_text += f", Menu: {menu_confidence:.1%} at {menu_region}"
        self.log(log_text)
    
    def _show_detection_results(self, screen_img, weapon_found, weapon_region, weapon_confidence,
                               weapon_alt_region, menu_found, menu_region, menu_confidence, threshold, monitor_info):
        """Show detection results with preview (legacy method - kept for compatibility)."""
        # This method is no longer used in auto-detect flow, but kept for compatibility
        # Auto-detect now uses _show_step1_results and _show_final_detection_results
        self._show_final_detection_results(
            screen_img, weapon_found, weapon_region, weapon_confidence,
            weapon_alt_region is not None, weapon_alt_region, 0.0 if weapon_alt_region is None else 1.0,
            menu_found, menu_region, menu_confidence, threshold, monitor_info
        )
    
    def _show_preview_window(
        self,
        preview_path: str,
        weapon_region: Tuple[int, int, int, int],
        weapon_confidence: float,
        menu_region: Tuple[int, int, int, int],
        menu_confidence: float,
    ) -> None:
        """Show preview window with detected regions."""
        preview_window = tk.Toplevel(self.root)
        preview_window.title("Auto-detection Results")
        preview_window.attributes("-topmost", True)

        self._create_preview_info_frame(
            preview_window, weapon_region, weapon_confidence, menu_region, menu_confidence, step=2
        )
        self._create_preview_image_frame(preview_window, preview_path)
        self._create_preview_button_frame(preview_window, "Close")
    
    def update_region_preview(self):
        """Update region preview labels."""
        weapon_region = self.config_manager.get("regions.weapon")
        weapon_alt_region = self.config_manager.get("regions.weapon_alt")
        menu_region = self.config_manager.get("regions.menu")
        
        # Check if labels exist before updating
        if hasattr(self, 'weapon_coords_label') and weapon_region:
            self.weapon_coords_label.config(
                text=f"({weapon_region[0]}, {weapon_region[1]}, {weapon_region[2]}, {weapon_region[3]})"
            )
        if hasattr(self, 'weapon_alt_coords_label') and weapon_alt_region:
            self.weapon_alt_coords_label.config(
                text=f"({weapon_alt_region[0]}, {weapon_alt_region[1]}, {weapon_alt_region[2]}, {weapon_alt_region[3]})"
            )
        if hasattr(self, 'menu_coords_label') and menu_region:
            self.menu_coords_label.config(
                text=f"({menu_region[0]}, {menu_region[1]}, {menu_region[2]}, {menu_region[3]})"
            )
    
    def find_game_window(self) -> Optional[int]:
        """Find ARC Raiders game window handle."""
        def enum_windows_callback(hwnd, windows):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if title:
                    cleaned_title = clean_window_title(title)
                    title_lower = cleaned_title.lower().strip()
                    
                    # Check if it's ARC Raiders
                    normalized_no_space = re.sub(r"[^a-z0-9]", "", title_lower)
                    if normalized_no_space == "arcraiders":
                        windows.append(hwnd)
                    elif (
                        re.search(r"\barc\s+raiders\b", title_lower)
                        or re.search(r"\barcraiders\b", title_lower)
                        or re.search(r"\barc[\s\-:]*raiders\b", title_lower)
                    ):
                        if len(title_lower) < 50 and not any(char in title_lower for char in ["\\", "/", ".py", ".exe", "macro"]):
                            windows.append(hwnd)
        
        windows = []
        win32gui.EnumWindows(enum_windows_callback, windows)
        return windows[0] if windows else None
    
    def get_monitor_for_window(self, hwnd: int, monitors: list) -> Optional[dict]:
        """Get the monitor that contains the specified window."""
        try:
            # Get window rect
            rect = win32gui.GetWindowRect(hwnd)
            window_left, window_top, window_right, window_bottom = rect
            
            # Calculate window center
            window_center_x = (window_left + window_right) // 2
            window_center_y = (window_top + window_bottom) // 2
            
            # Find monitor that contains the window center
            for monitor in monitors[1:]:  # Skip monitor 0 (all monitors combined)
                if (monitor["left"] <= window_center_x <= monitor["left"] + monitor["width"] and
                    monitor["top"] <= window_center_y <= monitor["top"] + monitor["height"]):
                    return monitor
            
            # If not found, return primary monitor
            return monitors[1] if len(monitors) > 1 else None
        except Exception:
            return monitors[1] if len(monitors) > 1 else None
    
    def start_capture_wait(self):
        """Start waiting for capture keybind."""
        if self.waiting_for_capture and self.capture_mode == "capture":
            self.cancel_capture_wait()
            return
        
        self.waiting_for_capture = True
        self.capture_mode = "capture"
        self.capture_btn.config(text="Cancel Capture", state=tk.NORMAL)
        self.autodetect_btn.config(state=tk.DISABLED)  # Disable autodetect button while capture is waiting
        self.capture_status_label.config(
            text=f"Waiting for keybind: {self.config_manager.get('keybinds.capture_screen', 'ALT+P')}",
            foreground="blue"
        )
        self.log(f"Waiting for capture keybind: {self.config_manager.get('keybinds.capture_screen', 'ALT+P')}")
        
        # Start listener for capture keybind
        self.start_capture_listener()
    
    def cancel_capture_wait(self):
        """Cancel capture wait mode."""
        self.waiting_for_capture = False
        self.capture_mode = None
        self.autodetect_step = 1
        self.first_capture_results = None
        self.alt_pressed = False
        self.ctrl_pressed = False
        self.shift_pressed = False
        if self.capture_listener:
            self.capture_listener.stop()
            self.capture_listener = None
        self.capture_btn.config(text="Capture Screen", state=tk.NORMAL)
        self.autodetect_btn.config(text="Auto-detect Regions", state=tk.NORMAL)
        self.capture_status_label.config(text="", foreground="blue")
        self.log("Capture cancelled")
    
    def start_capture_listener(self):
        """Start listener for capture keybind (regions tab)."""
        if self.capture_listener:
            self.capture_listener.stop()
        
        capture_keybind = self.config_manager.get("keybinds.capture_screen", "ALT+P")
        # Parse keybind (format: "ALT+P", "CTRL+SHIFT+P", etc.)
        parts = capture_keybind.upper().split("+")
        modifiers = [p.strip() for p in parts[:-1]]
        main_key = parts[-1].strip() if parts else "P"
        
        def on_press(key):
            # Don't interfere with template capture
            if self.template_capture_mode is not None:
                return
            
            if not self.waiting_for_capture:
                return
            
            try:
                # Track modifier keys
                if key == Key.alt_l or key == Key.alt_r:
                    self.alt_pressed = True
                    return
                elif key == Key.ctrl_l or key == Key.ctrl_r:
                    self.ctrl_pressed = True
                    return
                elif key == Key.shift_l or key == Key.shift_r:
                    self.shift_pressed = True
                    return
                
                # Check if main key is pressed with correct modifiers
                key_matched = False
                if isinstance(key, KeyCode) and key.char:
                    if key.char.upper() == main_key:
                        key_matched = True
                elif isinstance(key, Key):
                    key_name = self.get_key_name_from_listener(key)
                    if key_name == main_key:
                        key_matched = True
                
                if key_matched:
                    # Check modifiers
                    modifiers_ok = True
                    if "ALT" in modifiers and not self.alt_pressed:
                        modifiers_ok = False
                    if "CTRL" in modifiers and not self.ctrl_pressed:
                        modifiers_ok = False
                    if "SHIFT" in modifiers and not self.shift_pressed:
                        modifiers_ok = False
                    
                    if modifiers_ok:
                        # Execute based on mode
                        if self.capture_mode == "autodetect":
                            self.root.after(0, self.execute_autodetect)
                            # Don't stop listener - we need it for step 2
                            # It will be stopped in _show_final_detection_results
                        else:
                            self.root.after(0, self.execute_capture)
                            return False  # Stop listener for regular capture
                        return  # Continue listening for autodetect
                
                # Reset modifiers if non-modifier key pressed
                if not isinstance(key, Key) or (key not in [Key.alt_l, Key.alt_r, Key.ctrl_l, Key.ctrl_r, Key.shift_l, Key.shift_r]):
                    self.alt_pressed = False
                    self.ctrl_pressed = False
                    self.shift_pressed = False
            except Exception:
                pass
        
        def on_release(key):
            if key == Key.alt_l or key == Key.alt_r:
                self.alt_pressed = False
            elif key == Key.ctrl_l or key == Key.ctrl_r:
                self.ctrl_pressed = False
            elif key == Key.shift_l or key == Key.shift_r:
                self.shift_pressed = False
        
        self.capture_listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        self.capture_listener.start()
    
    def _capture_screen_for_detection(self):
        """Capture screen and return image array and monitor info."""
        # Minimize GUI
        self.root.iconify()
        time.sleep(0.5)
        
        # Find game window
        game_hwnd = self.find_game_window()
        
        with mss.mss() as sct:
            monitors = sct.monitors
            
            if game_hwnd:
                # Get monitor where game is running
                monitor = self.get_monitor_for_window(game_hwnd, monitors)
                if monitor:
                    self.log(f"Capturing monitor where game is running: {monitor['width']}x{monitor['height']}")
                    screenshot = sct.grab(monitor)
                    monitor_info = monitor
                else:
                    # Fallback to primary monitor
                    self.log("Game window found but monitor detection failed, using primary monitor")
                    screenshot = sct.grab(monitors[1])
                    monitor_info = monitors[1]
            else:
                # Game not found, use primary monitor
                self.log("Game window not found, capturing primary monitor")
                screenshot = sct.grab(monitors[1])
                monitor_info = monitors[1]
            
            # Convert to numpy array
            img_array = np.array(screenshot)
            screen_img = cv2.cvtColor(img_array, cv2.COLOR_BGRA2BGR)
            screen_gray = cv2.cvtColor(img_array, cv2.COLOR_BGRA2GRAY)
            
            return screen_img, screen_gray, monitor_info
    
    def execute_capture(self):
        """Execute the actual screen capture."""
        if not self.waiting_for_capture or self.capture_mode != "capture":
            return
        
        self.waiting_for_capture = False
        self.capture_mode = None
        self.alt_pressed = False
        self.ctrl_pressed = False
        self.shift_pressed = False
        if self.capture_listener:
            self.capture_listener.stop()
            self.capture_listener = None
        
        self.capture_btn.config(text="Capture Screen", state=tk.NORMAL)
        self.autodetect_btn.config(state=tk.NORMAL)
        self.capture_status_label.config(text="Capturing...", foreground="green")
        self.log("Capture keybind pressed - capturing screen")
        
        # Capture screen
        screen_img, screen_gray, monitor_info = self._capture_screen_for_detection()
        
        # Convert to PIL Image for saving
        img = Image.fromarray(cv2.cvtColor(screen_img, cv2.COLOR_BGR2RGB))
        
        # Save temporary screenshot
        screenshot_path = get_preview_path("temp_screenshot.png")
        img.save(screenshot_path)
        
        # Reset status
        self.capture_status_label.config(text="", foreground="blue")
        
        # Show region selector
        self.root.after(100, lambda: RegionSelector(
            self.root, str(screenshot_path), self.on_region_selected
        ))
    
    def execute_autodetect(self):
        """Execute auto-detection after capture."""
        if not self.waiting_for_capture or self.capture_mode != "autodetect":
            return
        
        # Don't stop the listener - we need it for step 2
        self.alt_pressed = False
        self.ctrl_pressed = False
        self.shift_pressed = False
        
        current_step = self.autodetect_step
        self.capture_status_label.config(text=f"Capturing and detecting (Step {current_step}/2)...", foreground="green")
        self.log(f"Capture keybind pressed - capturing screen for auto-detection (Step {current_step}/2)")
        
        # Run detection in thread with current step
        threading.Thread(target=lambda: self._auto_detect_regions_thread(step=current_step), daemon=True).start()
    
    def on_region_selected(self, region_type, coords):
        """Handle region selection."""
        self.config_manager.set(f"regions.{region_type}", list(coords))
        
        # Update screen resolution - use the monitor where game is running
        game_hwnd = self.find_game_window()
        with mss.mss() as sct:
            monitors = sct.monitors
            if game_hwnd:
                monitor = self.get_monitor_for_window(game_hwnd, monitors)
                if monitor:
                    self.config_manager.set("regions.screen_resolution", [monitor["width"], monitor["height"]])
                else:
                    monitor = monitors[1]
                    self.config_manager.set("regions.screen_resolution", [monitor["width"], monitor["height"]])
            else:
                monitor = monitors[1]
                self.config_manager.set("regions.screen_resolution", [monitor["width"], monitor["height"]])
        
        # Save region image
        self.config_manager.save()
        self.update_region_preview()
        self.log(f"{region_type.capitalize()} region set: {coords} (Screen: {monitor['width']}x{monitor['height']})")
        
        # Restore GUI
        self.root.deiconify()
        self.root.lift()
    
    def create_templates_panel(self, parent):
        """Create template capture panel."""
        # Instructions frame
        instructions_frame = ttk.LabelFrame(parent, text="Instructions", padding=10)
        instructions_frame.pack(fill=tk.X, padx=5, pady=5)
        
        instructions_text = (
            "1. Make sure regions are configured in the Regions tab\n"
            "2. Click 'Capture Weapon Templates' for a weapon (2 steps: Slot 1, then Slot 2)\n"
            "3. Click 'Capture Menu Template' for the quick menu (1 step)\n"
            "4. Press ALT+P when ready to capture each template\n"
            "5. Templates will be saved automatically to the /images folder"
        )
        ttk.Label(instructions_frame, text=instructions_text, justify=tk.LEFT).pack(anchor=tk.W)
        
        # Status label
        self.template_status_label = ttk.Label(instructions_frame, text="", foreground="blue")
        self.template_status_label.pack(anchor=tk.W, pady=(10, 0))
        
        # Weapons templates frame
        weapons_frame = ttk.LabelFrame(parent, text="Weapon Templates", padding=10)
        weapons_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Create scrollable canvas for weapons
        canvas = tk.Canvas(weapons_frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(weapons_frame, orient="vertical", command=canvas.yview)
        self.weapons_templates_frame = ttk.Frame(canvas)
        
        self.weapons_templates_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=self.weapons_templates_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Store weapon template buttons
        self.weapon_template_buttons = {}
        
        # Get weapons from config
        weapons = self.config_manager.get("weapons", {})
        
        for idx, (weapon_id, weapon_config) in enumerate(weapons.items()):
            self._create_weapon_template_widgets(weapon_id, weapon_config, idx)
        
        # Menu template frame
        menu_frame = ttk.LabelFrame(parent, text="Menu Template", padding=10)
        menu_frame.pack(fill=tk.X, padx=5, pady=5)
        
        menu_info_frame = ttk.Frame(menu_frame)
        menu_info_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(menu_info_frame, text="Quick Menu Template:").pack(side=tk.LEFT, padx=5)
        self.menu_template_status = ttk.Label(menu_info_frame, text="Not captured", foreground="gray")
        self.menu_template_status.pack(side=tk.LEFT, padx=5)
        
        menu_buttons_frame = ttk.Frame(menu_frame)
        menu_buttons_frame.pack(pady=5)
        
        self.capture_menu_btn = ttk.Button(
            menu_buttons_frame,
            text="Capture Menu Template",
            command=lambda: self.start_menu_template_capture()
        )
        self.capture_menu_btn.pack(side=tk.LEFT, padx=5)
        
        self.cancel_menu_btn = ttk.Button(
            menu_buttons_frame,
            text="Cancel",
            command=self.cancel_template_capture,
            state=tk.DISABLED
        )
        self.cancel_menu_btn.pack(side=tk.LEFT, padx=5)
    
    def _create_weapon_template_widgets(self, weapon_id: str, weapon_config: dict, row_idx: int):
        """Create template capture widgets for a single weapon."""
        weapon_name = weapon_config.get("name", weapon_id.capitalize())
        
        # Weapon frame
        weapon_frame = ttk.LabelFrame(self.weapons_templates_frame, text=weapon_name, padding=5)
        weapon_frame.pack(fill=tk.X, pady=5, padx=5)
        
        # Status labels
        status_frame = ttk.Frame(weapon_frame)
        status_frame.pack(fill=tk.X, pady=2)
        
        ttk.Label(status_frame, text="Slot 1:").pack(side=tk.LEFT, padx=5)
        slot1_status = ttk.Label(status_frame, text="Not captured", foreground="gray")
        slot1_status.pack(side=tk.LEFT, padx=5)
        
        ttk.Label(status_frame, text="Slot 2:").pack(side=tk.LEFT, padx=5)
        slot2_status = ttk.Label(status_frame, text="Not captured", foreground="gray")
        slot2_status.pack(side=tk.LEFT, padx=5)
        
        # Update status based on existing templates
        template_base = weapon_config.get("template", f"{weapon_id}.png")
        template_slot1_name = weapon_config.get("template_slot1", template_base)
        template_slot2_name = weapon_config.get("template_slot2", template_base)
        
        if find_template_file(template_slot1_name):
            slot1_status.config(text="Captured", foreground="green")
        if find_template_file(template_slot2_name):
            slot2_status.config(text="Captured", foreground="green")
        
        # Buttons frame
        buttons_frame = ttk.Frame(weapon_frame)
        buttons_frame.pack(pady=5)
        
        capture_btn = ttk.Button(
            buttons_frame,
            text="Capture Weapon Templates",
            command=lambda wid=weapon_id: self.start_weapon_template_capture(wid)
        )
        capture_btn.pack(side=tk.LEFT, padx=5)
        
        cancel_btn = ttk.Button(
            buttons_frame,
            text="Cancel",
            command=self.cancel_template_capture,
            state=tk.DISABLED
        )
        cancel_btn.pack(side=tk.LEFT, padx=5)
        
        # Store references (initialize dictionary first)
        self.weapon_template_buttons[weapon_id] = {
            "button": capture_btn,
            "cancel_button": cancel_btn,
            "slot1_status": slot1_status,
            "slot2_status": slot2_status,
        }
    
    def start_weapon_template_capture(self, weapon_id: str):
        """Start capturing weapon templates (2 steps)."""
        # Check if regions are configured
        weapon_region = self.config_manager.get("regions.weapon")
        weapon_alt_region = self.config_manager.get("regions.weapon_alt")
        
        if not weapon_region or not weapon_alt_region:
            messagebox.showwarning(
                "Regions Not Configured",
                "Please configure weapon regions in the Regions tab first."
            )
            return
        
        # Cancel any existing capture
        if self.waiting_for_capture:
            self.cancel_template_capture()
        
        # Start step 1 (slot 1)
        self.template_capture_mode = "weapon_slot1"
        self.template_capture_weapon_id = weapon_id
        self.template_capture_step = 1
        self.waiting_for_capture = True
        
        weapon_name = self.config_manager.get(f"weapons.{weapon_id}.name", weapon_id.capitalize())
        self.template_status_label.config(
            text=f"Step 1/2: Place {weapon_name} in Slot 1, then press ALT+P",
            foreground="blue",
            font=("TkDefaultFont", 9)
        )
        self.log(f"Template capture started for {weapon_name} - Step 1/2: Slot 1")
        
        # Update button state
        if weapon_id in self.weapon_template_buttons:
            self.weapon_template_buttons[weapon_id]["button"].config(state=tk.DISABLED)
            self.weapon_template_buttons[weapon_id]["cancel_button"].config(state=tk.NORMAL)
        
        # Start capture listener
        self.start_template_capture_listener()
    
    def start_menu_template_capture(self):
        """Start capturing menu template (1 step)."""
        # Check if menu region is configured
        menu_region = self.config_manager.get("regions.menu")
        
        if not menu_region:
            messagebox.showwarning(
                "Region Not Configured",
                "Please configure menu region in the Regions tab first."
            )
            return
        
        # Cancel any existing capture
        if self.waiting_for_capture:
            self.cancel_template_capture()
        
        # Start menu capture
        self.template_capture_mode = "menu"
        self.template_capture_step = 1
        self.waiting_for_capture = True
        
        self.template_status_label.config(
            text="Open the quick menu (Q), then press ALT+P",
            foreground="blue"
        )
        self.log("Menu template capture started - Open quick menu and press ALT+P")
        
        # Update button state
        self.capture_menu_btn.config(state=tk.DISABLED)
        self.cancel_menu_btn.config(state=tk.NORMAL)
        
        # Start capture listener
        self.start_template_capture_listener()
    
    def start_template_capture_listener(self):
        """Start listener for template capture keybind."""
        if self.capture_listener:
            self.capture_listener.stop()
        
        def on_press(key):
            if not self.waiting_for_capture or self.template_capture_mode is None:
                return
            
            try:
                # Track modifier keys
                if key == Key.alt_l or key == Key.alt_r:
                    self.alt_pressed = True
                    return
                elif key == Key.ctrl_l or key == Key.ctrl_r:
                    self.ctrl_pressed = True
                    return
                elif key == Key.shift_l or key == Key.shift_r:
                    self.shift_pressed = True
                    return
                
                # Check if P is pressed with ALT
                if isinstance(key, KeyCode) and key.char and key.char.upper() == "P":
                    if self.alt_pressed:
                        self.root.after(0, self.execute_template_capture)
                        return
                
                # Reset modifiers if non-modifier key pressed
                if not isinstance(key, Key) or (key not in [Key.alt_l, Key.alt_r, Key.ctrl_l, Key.ctrl_r, Key.shift_l, Key.shift_r]):
                    self.alt_pressed = False
                    self.ctrl_pressed = False
                    self.shift_pressed = False
            except Exception:
                pass
        
        def on_release(key):
            if key == Key.alt_l or key == Key.alt_r:
                self.alt_pressed = False
            elif key == Key.ctrl_l or key == Key.ctrl_r:
                self.ctrl_pressed = False
            elif key == Key.shift_l or key == Key.shift_r:
                self.shift_pressed = False
        
        self.capture_listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        self.capture_listener.start()
    
    def execute_template_capture(self):
        """Execute template capture based on current mode."""
        if not self.waiting_for_capture or self.template_capture_mode is None:
            return
        
        # Minimize GUI
        self.root.iconify()
        time.sleep(0.3)  # Small delay to ensure GUI is minimized
        
        if self.template_capture_mode == "menu":
            # Capture menu template
            menu_region = self.config_manager.get("regions.menu")
            if menu_region:
                menu_filename = "menu_captured.png"
                menu_path = get_captured_path(menu_filename)
                
                success = self._capture_template_from_region(
                    tuple(menu_region),
                    menu_path,
                    "Menu"
                )
                if success:
                    self.template_status_label.config(
                        text="Menu template captured successfully!",
                        foreground="green"
                    )
                    self.log(f"Menu template captured successfully: {menu_filename}")
                    self.menu_template_status.config(text="Captured", foreground="green")
                else:
                    self.template_status_label.config(
                        text="Failed to capture menu template",
                        foreground="red"
                    )
                    self.log("Failed to capture menu template")
            
            # Reset state
            self.cancel_template_capture()
            
        elif self.template_capture_mode == "weapon_slot1":
            # Capture slot 1 template (regions.weapon is slot 1)
            weapon_region = self.config_manager.get("regions.weapon")
            if weapon_region:
                weapon_config = self.config_manager.get(f"weapons.{self.template_capture_weapon_id}", {})
                template_base = weapon_config.get("template", f"{self.template_capture_weapon_id}.png")
                template_slot1_name = weapon_config.get("template_slot1", template_base)
                
                success = self._capture_template_from_region(
                    tuple(weapon_region),
                    get_captured_path(template_slot1_name),
                    f"{weapon_config.get('name', self.template_capture_weapon_id)} Slot 1"
                )
                
                if success:
                    # Update status
                    if self.template_capture_weapon_id in self.weapon_template_buttons:
                        self.weapon_template_buttons[self.template_capture_weapon_id]["slot1_status"].config(
                            text="Captured", foreground="green"
                        )
                    
                    # Move to step 2
                    self.template_capture_mode = "weapon_slot2"
                    self.template_capture_step = 2
                    
                    weapon_name = weapon_config.get("name", self.template_capture_weapon_id.capitalize())
                    
                    # Show notification that slot 1 is complete and slot 2 is next
                    messagebox.showinfo(
                        "Slot 1 Captured",
                        f"Slot 1 template captured successfully!\n\n"
                        f"Now place {weapon_name} in Slot 2 and press ALT+P to capture Slot 2."
                    )
                    
                    # Update status label with more prominent styling
                    self.template_status_label.config(
                        text=f"✓ Slot 1 captured! Step 2/2: Place {weapon_name} in Slot 2, then press ALT+P",
                        foreground="green",
                        font=("TkDefaultFont", 10, "bold")
                    )
                    self.log(f"Slot 1 captured - Step 2/2: Place {weapon_name} in Slot 2")
                else:
                    self.template_status_label.config(
                        text="Failed to capture slot 1 template",
                        foreground="red"
                    )
                    self.cancel_template_capture()
            
        elif self.template_capture_mode == "weapon_slot2":
            # Capture slot 2 template (regions.weapon_alt is slot 2)
            weapon_alt_region = self.config_manager.get("regions.weapon_alt")
            if weapon_alt_region:
                weapon_config = self.config_manager.get(f"weapons.{self.template_capture_weapon_id}", {})
                template_base = weapon_config.get("template", f"{self.template_capture_weapon_id}.png")
                template_slot2_name = weapon_config.get("template_slot2", template_base)
                
                success = self._capture_template_from_region(
                    tuple(weapon_alt_region),
                    get_captured_path(template_slot2_name),
                    f"{weapon_config.get('name', self.template_capture_weapon_id)} Slot 2"
                )
                
                if success:
                    # Update status
                    if self.template_capture_weapon_id in self.weapon_template_buttons:
                        self.weapon_template_buttons[self.template_capture_weapon_id]["slot2_status"].config(
                            text="Captured", foreground="green"
                        )
                    
                    weapon_name = weapon_config.get("name", self.template_capture_weapon_id.capitalize())
                    self.template_status_label.config(
                        text=f"✓ {weapon_name} templates captured successfully! (Slot 1 & Slot 2)",
                        foreground="green",
                        font=("TkDefaultFont", 9)
                    )
                    self.log(f"{weapon_name} templates captured successfully (Slot 1 & Slot 2)")
                else:
                    self.template_status_label.config(
                        text="Failed to capture slot 2 template",
                        foreground="red"
                    )
            
            # Reset state
            self.cancel_template_capture()
        
        # Restore GUI
        self.root.after(500, lambda: self.root.deiconify())
        self.root.after(500, lambda: self.root.lift())
    
    def _capture_template_from_region(self, region: Tuple[int, int, int, int], save_path: Path, template_name: str) -> bool:
        """Capture template from a specific region and save it."""
        try:
            # Use HashDetector to capture region
            from .detection import HashDetector
            detector = HashDetector()
            region_img = detector.capture_region(region)
            
            if region_img is None:
                self.log(f"Failed to capture region for {template_name}")
                return False
            
            # Save template
            cv2.imwrite(str(save_path), region_img)
            
            # Calculate hash for verification
            template_hash = detector.calculate_hash(region_img)
            
            self.log(f"Template saved: {save_path.name} ({region_img.shape[1]}x{region_img.shape[0]} px, hash: {template_hash})")
            
            # Show preview
            preview = cv2.resize(region_img, None, fx=2, fy=2)
            cv2.imshow(f"Captured {template_name} Template", preview)
            cv2.waitKey(2000)
            cv2.destroyAllWindows()
            
            return True
            
        except Exception as e:
            self.log(f"Error capturing template {template_name}: {e}")
            return False
    
    def cancel_template_capture(self):
        """Cancel template capture mode."""
        self.waiting_for_capture = False
        self.template_capture_mode = None
        self.template_capture_weapon_id = None
        self.template_capture_step = 0
        self.alt_pressed = False
        self.ctrl_pressed = False
        self.shift_pressed = False
        
        if self.capture_listener:
            self.capture_listener.stop()
            self.capture_listener = None
        
        # Re-enable all buttons
        if hasattr(self, 'weapon_template_buttons'):
            for weapon_id, widgets in self.weapon_template_buttons.items():
                widgets["button"].config(state=tk.NORMAL)
                if "cancel_button" in widgets:
                    widgets["cancel_button"].config(state=tk.DISABLED)
        if hasattr(self, 'capture_menu_btn'):
            self.capture_menu_btn.config(state=tk.NORMAL)
        if hasattr(self, 'cancel_menu_btn'):
            self.cancel_menu_btn.config(state=tk.DISABLED)
        
        self.template_status_label.config(text="", foreground="blue", font=("TkDefaultFont", 9))
    
    def create_keybinds_panel(self, parent):
        """Create keybinds configuration panel."""
        frame = ttk.LabelFrame(parent, text="Global Keybinds", padding=10)
        frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Instructions
        instructions = ttk.Label(
            frame, 
            text="Click a button and press the desired key combination (ESC to cancel)",
            font=("Arial", 9),
            foreground="gray"
        )
        instructions.pack(pady=(0, 10))
        
        # Start/Stop Toggle
        toggle_frame = ttk.Frame(frame)
        toggle_frame.pack(fill=tk.X, pady=8)
        ttk.Label(toggle_frame, text="Start/Stop:", width=15, anchor=tk.W).pack(side=tk.LEFT)
        
        current_stop_key = self.config_manager.get("keybinds.stop", "F7")
        self.stop_keybind_btn = tk.Button(
            toggle_frame,
            text=current_stop_key,
            width=20,
            command=lambda: self.start_recording_keybind("stop"),
            relief=tk.RAISED,
            bg="#f0f0f0",
            activebackground="#e0e0e0"
        )
        self.stop_keybind_btn.pack(side=tk.LEFT, padx=10)
        
        # Capture Screen
        capture_frame = ttk.Frame(frame)
        capture_frame.pack(fill=tk.X, pady=8)
        ttk.Label(capture_frame, text="Capture Screen:", width=15, anchor=tk.W).pack(side=tk.LEFT)
        
        current_capture_key = self.config_manager.get("keybinds.capture_screen", "ALT+P")
        self.capture_keybind_btn = tk.Button(
            capture_frame,
            text=current_capture_key,
            width=20,
            command=lambda: self.start_recording_keybind("capture_screen"),
            relief=tk.RAISED,
            bg="#f0f0f0",
            activebackground="#e0e0e0"
        )
        self.capture_keybind_btn.pack(side=tk.LEFT, padx=10)
        
        # Status indicator
        status_frame = ttk.LabelFrame(frame, text="Status", padding=10)
        status_frame.pack(fill=tk.X, pady=10)
        self.status_label = ttk.Label(status_frame, text="Stopped", font=("Arial", 12, "bold"))
        self.status_label.pack()
    
    def start_recording_keybind(self, keybind_type: str):
        """Start recording a keybind."""
        # Stop any existing recording
        self.stop_recording_keybind()
        
        # Set recording state
        self.recording_keybind_type = keybind_type
        self.recording_modifiers = {"alt": False, "ctrl": False, "shift": False}
        
        # Update button appearance
        if keybind_type == "stop":
            self.stop_keybind_btn.config(
                text="Press any key...",
                bg="#ffeb3b",
                activebackground="#ffc107",
                state=tk.DISABLED
            )
        elif keybind_type == "capture_screen":
            self.capture_keybind_btn.config(
                text="Press any key...",
                bg="#ffeb3b",
                activebackground="#ffc107",
                state=tk.DISABLED
            )
        
        # Start global keyboard listener after a small delay to ensure UI updates
        def start_listener():
            def on_press(key):
                try:
                    if not self.recording_keybind_type:
                        return
                    
                    # Handle ESC to cancel recording
                    if key == Key.esc:
                        self.root.after(0, self.cancel_recording_keybind)
                        return
                    
                    # Check if this is a modifier key
                    is_modifier = False
                    if key == Key.alt_l or key == Key.alt_r:
                        self.recording_modifiers["alt"] = True
                        is_modifier = True
                    elif key == Key.ctrl_l or key == Key.ctrl_r:
                        self.recording_modifiers["ctrl"] = True
                        is_modifier = True
                    elif key == Key.shift_l or key == Key.shift_r:
                        self.recording_modifiers["shift"] = True
                        is_modifier = True
                    
                    # If it's a modifier, don't capture yet - wait for a non-modifier key
                    if is_modifier:
                        return
                    
                    # Get the key name (this should be a non-modifier key)
                    key_name = self.get_key_name_from_listener(key)
                    # Only capture if we have a valid non-modifier key name
                    # and it's not a modifier key itself
                    if key_name and self.recording_keybind_type:
                        # Double-check: make sure key_name is not a modifier
                        if key_name in ["ALT", "CTRL", "SHIFT"]:
                            return
                        
                        # Build keybind string using current modifier state
                        modifiers = []
                        if self.recording_modifiers["alt"]:
                            modifiers.append("ALT")
                        if self.recording_modifiers["ctrl"]:
                            modifiers.append("CTRL")
                        if self.recording_modifiers["shift"]:
                            modifiers.append("SHIFT")
                        
                        # Only save if we have at least a non-modifier key
                        # (modifiers alone are not valid keybinds)
                        if modifiers:
                            keybind_str = "+".join(modifiers) + "+" + key_name
                        else:
                            keybind_str = key_name
                        
                        # Save the keybind (schedule UI update on main thread)
                        # Use a closure to capture the keybind_str value
                        keybind_to_save = keybind_str
                        self.root.after(0, lambda k=keybind_to_save: self.save_recorded_keybind(k))
                except Exception as e:
                    self.log(f"Error recording keybind: {e}")
                    import traceback
                    self.log(traceback.format_exc())
            
            def on_release(key):
                try:
                    # Only clear modifiers if recording is still active
                    # (if we already saved, recording_keybind_type will be None)
                    if not self.recording_keybind_type:
                        return
                    
                    # Handle modifier keys release
                    if key == Key.alt_l or key == Key.alt_r:
                        self.recording_modifiers["alt"] = False
                    elif key == Key.ctrl_l or key == Key.ctrl_r:
                        self.recording_modifiers["ctrl"] = False
                    elif key == Key.shift_l or key == Key.shift_r:
                        self.recording_modifiers["shift"] = False
                except Exception:
                    pass
            
            self.keybind_recording_listener = keyboard.Listener(
                on_press=on_press,
                on_release=on_release
            )
            self.keybind_recording_listener.start()
            self.log(f"Recording keybind for {keybind_type}... Press any key combination")
        
        # Start listener after UI updates
        self.root.after(50, start_listener)
    
    def stop_recording_keybind(self):
        """Stop recording keybind."""
        if self.keybind_recording_listener:
            try:
                self.keybind_recording_listener.stop()
            except Exception:
                pass
            self.keybind_recording_listener = None
        
        self.recording_keybind_type = None
        self.recording_modifiers = {"alt": False, "ctrl": False, "shift": False}
    
    def cancel_recording_keybind(self):
        """Cancel recording keybind without saving."""
        keybind_type = self.recording_keybind_type
        self.stop_recording_keybind()
        
        # Restore button to show current keybind
        if keybind_type == "stop":
            current_key = self.config_manager.get("keybinds.stop", "F7")
            self.stop_keybind_btn.config(
                text=current_key,
                bg="#f0f0f0",
                activebackground="#e0e0e0",
                state=tk.NORMAL
            )
        elif keybind_type == "capture_screen":
            current_key = self.config_manager.get("keybinds.capture_screen", "ALT+P")
            self.capture_keybind_btn.config(
                text=current_key,
                bg="#f0f0f0",
                activebackground="#e0e0e0",
                state=tk.NORMAL
            )
        
        self.log("Keybind recording cancelled")
    
    def save_recorded_keybind(self, keybind_str: str):
        """Save the recorded keybind."""
        if not self.recording_keybind_type:
            return
        
        # Save the keybind type before stopping recording
        keybind_type = self.recording_keybind_type
        
        # Stop recording
        self.stop_recording_keybind()
        
        # Save to config
        self.config_manager.set(f"keybinds.{keybind_type}", keybind_str)
        self.config_manager.save()
        
        # Update button text
        if keybind_type == "stop":
            self.stop_keybind_btn.config(
                text=keybind_str,
                bg="#f0f0f0",
                activebackground="#e0e0e0",
                state=tk.NORMAL
            )
            # Restart keybind listener
            self.start_keybind_listener()
        elif keybind_type == "capture_screen":
            self.capture_keybind_btn.config(
                text=keybind_str,
                bg="#f0f0f0",
                activebackground="#e0e0e0",
                state=tk.NORMAL
            )
            # Restart capture listener if waiting
            if self.waiting_for_capture:
                self.start_capture_listener()
        
        self.log(f"Keybind {keybind_type} set to: {keybind_str}")
    
    def create_status_panel(self, parent):
        """Create status/logs panel."""
        # Status indicators frame
        indicators_frame = ttk.LabelFrame(parent, text="Status Indicators", padding=10)
        indicators_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Create LED indicators
        self.create_led_indicator(indicators_frame, "Weapon Detected", 0, 0)
        self.create_led_indicator(indicators_frame, "Menu Detected", 0, 1)
        self.create_led_indicator(indicators_frame, "Macro Active", 1, 0)
        self.create_led_indicator(indicators_frame, "Autoclick Running", 1, 1)
        
        # Logs frame
        logs_frame = ttk.LabelFrame(parent, text="Logs", padding=10)
        logs_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.log_text = scrolledtext.ScrolledText(logs_frame, height=15, wrap=tk.WORD)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        self.log_text.config(state=tk.DISABLED)
    
    def create_led_indicator(self, parent, label, row, col):
        """Create an LED status indicator."""
        frame = ttk.Frame(parent)
        frame.grid(row=row, column=col, padx=10, pady=5, sticky=tk.W)
        
        # LED canvas
        canvas = tk.Canvas(frame, width=20, height=20, highlightthickness=0)
        canvas.pack(side=tk.LEFT, padx=5)
        led_id = canvas.create_oval(2, 2, 18, 18, fill="gray", outline="black", width=1)
        
        ttk.Label(frame, text=label).pack(side=tk.LEFT)
        
        # Store reference
        if not hasattr(self, "led_indicators"):
            self.led_indicators = {}
        self.led_indicators[label] = (canvas, led_id)
    
    def update_led(self, label, state, macro_running=None):
        """Update LED indicator state.
        
        Args:
            label: Label of the LED indicator
            state: Boolean state (True/False)
            macro_running: Optional boolean indicating if macro is running. 
                          If False, LED will be gray regardless of state.
        """
        if hasattr(self, "led_indicators") and label in self.led_indicators:
            canvas, led_id = self.led_indicators[label]
            # If macro_running is explicitly False, set to gray
            if macro_running is False:
                color = "gray"
            else:
                # Use macro_running from instance if not provided
                if macro_running is None:
                    macro_running = self.macro_running
                if not macro_running:
                    color = "gray"
                else:
                    color = "green" if state else "red"
            canvas.itemconfig(led_id, fill=color)
    
    def create_main_controls(self):
        """Create main control buttons."""
        frame = tk.Frame(self.root)
        frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Start/Stop button
        self.start_stop_btn = tk.Button(
            frame, text="START", command=self.toggle_macro,
            font=("Arial", 14, "bold"), bg="#4CAF50", fg="white",
            width=15, height=2
        )
        self.start_stop_btn.pack(side=tk.LEFT, padx=5)
        
        # Options frame
        options_frame = ttk.Frame(frame)
        options_frame.pack(side=tk.RIGHT, padx=5)
        
        self.minimize_to_tray_var = tk.BooleanVar(
            value=self.config_manager.get("gui.minimize_to_tray")
        )
        ttk.Checkbutton(
            options_frame, text="Minimize to tray",
            variable=self.minimize_to_tray_var,
            command=self.save_gui_settings
        ).pack(anchor=tk.W)
        
        self.run_on_startup_var = tk.BooleanVar(
            value=self.config_manager.get("gui.run_on_startup")
        )
        ttk.Checkbutton(
            options_frame, text="Run on startup",
            variable=self.run_on_startup_var,
            command=self.save_gui_settings
        ).pack(anchor=tk.W)
        
        # Signature/Credits
        self.create_signature()
    
    def save_gui_settings(self):
        """Save GUI settings."""
        self.config_manager.set("gui.minimize_to_tray", self.minimize_to_tray_var.get())
        self.config_manager.set("gui.run_on_startup", self.run_on_startup_var.get())
        self.config_manager.save()
    
    def create_signature(self):
        """Create signature/credits at the bottom of the window."""
        import webbrowser
        
        signature_frame = tk.Frame(self.root)
        signature_frame.pack(fill=tk.X, padx=5, pady=(0, 2), side=tk.BOTTOM)
        
        # Create a clickable link label
        link_label = tk.Label(
            signature_frame,
            text="Created by xViada",
            font=("Arial", 9),
            fg="#0066cc",
            cursor="hand2"
        )
        link_label.pack(anchor=tk.CENTER)
        
        # Bind click event to open GitHub
        link_label.bind("<Button-1>", lambda e: webbrowser.open("https://github.com/xViada"))
        
        # Add hover effect
        link_label.bind("<Enter>", lambda e: link_label.config(fg="#0099ff", font=("Arial", 9, "underline")))
        link_label.bind("<Leave>", lambda e: link_label.config(fg="#0066cc", font=("Arial", 9)))
    
    def _on_interception_error(self, error_message: str):
        """
        Handle Interception driver errors by showing a popup notification.
        Called from a background thread, so we schedule it on the main thread.
        
        Args:
            error_message: The error message from Interception
        """
        def show_error_popup():
            # Stop the macro first
            self.stop_macro()
            
            # Show error popup
            messagebox.showerror(
                "Interception Driver Error",
                f"The Interception driver encountered an error:\n\n{error_message}\n\n"
                "This usually means the Interception driver is not installed.\n\n"
                "Installation steps:\n"
                "1. Download from: https://github.com/oblitum/Interception/releases\n"
                "2. Run as Administrator: install-interception.exe /install\n"
                "3. Restart Windows\n"
                "4. Run: pip install interception-python"
            )
            
            # Update status
            self.status_label.config(text="Error: Interception driver not installed")
            self.log(f"Interception error: {error_message}")
        
        # Schedule on main thread
        self.root.after(0, show_error_popup)
    
    def start_macro(self):
        """Start the macro."""
        if self.macro_running:
            return
        
        # Load configuration
        config = self.config_manager.config
        
        # Get weapons config and check for at least one enabled weapon with template
        weapons_config = config.get("weapons", {})
        has_weapon = False
        for weapon_id, weapon_data in weapons_config.items():
            if weapon_data.get("enabled", True):
                template = weapon_data.get("template", f"{weapon_id}.png")
                if find_template_file(template):
                    has_weapon = True
                    break
        
        if not has_weapon:
            messagebox.showerror("Error", "No weapon templates found. Add weapon images (kettle.png, burletta.png, etc.) to the /images folder.")
            return
        
        # Initialize macro activator with weapons config
        # Note: weapon_alt is slot 2, weapon is slot 1
        weapon_region_config = tuple(config["regions"]["weapon"])
        weapon_region_alt_config = tuple(config["regions"].get("weapon_alt", config["regions"]["weapon"]))
        menu_region = tuple(config["regions"]["menu"])
        
        # Swap: weapon_alt (slot 2) goes to weapon_region, weapon (slot 1) goes to weapon_region_alt
        weapon_region = weapon_region_alt_config  # slot 2
        weapon_region_alt = weapon_region_config  # slot 1
        
        # Use base images directory for MacroActivator (it will use organized structure internally)
        from .image_paths import get_image_base_dir
        self.macro_activator = MacroActivator(
            image_dir=str(get_image_base_dir()),
            hash_threshold=config["detection"]["hash_threshold"],
            weapon_region=weapon_region,
            weapon_region_alt=weapon_region_alt,
            menu_region=menu_region,
            screen_width=config["regions"]["screen_resolution"][0],
            screen_height=config["regions"]["screen_resolution"][1],
            hash_size=config["detection"]["hash_size"],
            weapons_config=weapons_config,
            error_callback=self._on_interception_error,
        )
        
        # Start macro in thread
        self.macro_running = True
        self.macro_paused = False
        self.should_stop = False
        
        self.macro_thread = threading.Thread(target=self.macro_loop, daemon=True)
        self.macro_thread.start()
        
        # Update UI
        self.start_stop_btn.config(text="STOP", bg="#f44336")
        self.status_label.config(text="Running")
        
        # Log loaded weapons
        loaded_weapons = [w["name"] for w in self.macro_activator.weapon_hashes.values()]
        self.log(f"Macro started - Loaded weapons: {', '.join(loaded_weapons)}")
    
    def toggle_macro(self):
        """Toggle macro on/off (start if stopped, stop if running)."""
        if self.macro_running:
            self.stop_macro()
        else:
            self.start_macro()
    
    def stop_macro(self):
        """Stop the macro."""
        self.should_stop = True
        self.macro_running = False
        self.macro_paused = False
        
        if self.macro_activator:
            self.macro_activator._deactivate_macro()
            self.macro_activator.autoclicker.stop()
        
        # Update UI
        self.start_stop_btn.config(text="START", bg="#4CAF50")
        self.status_label.config(text="Stopped")
        self.log("Macro stopped")
        
        # Set all status indicators to gray
        self.root.after(0, lambda: self.update_led("Weapon Detected", False, macro_running=False))
        self.root.after(0, lambda: self.update_led("Menu Detected", False, macro_running=False))
        self.root.after(0, lambda: self.update_led("Macro Active", False, macro_running=False))
        self.root.after(0, lambda: self.update_led("Autoclick Running", False, macro_running=False))
    
    def pause_resume_macro(self):
        """Pause or resume the macro."""
        if not self.macro_running:
            return
        
        self.macro_paused = not self.macro_paused
        
        # When pausing, deactivate the macro in MacroActivator
        # When resuming, let the loop reactivate it automatically
        if self.macro_paused:
            if self.macro_activator and self.macro_activator.macro_active:
                self.macro_activator._deactivate_macro()
                self.macro_active = False
            status = "Paused"
        else:
            status = "Running"
            # When resuming, the loop will automatically reactivate if conditions are met
        
        self.status_label.config(text=status)
        self.log(f"Macro {status.lower()}")
    
    def macro_loop(self):
        """Main macro loop running in separate thread."""
        loop_delay = self.config_manager.get("delays.detection_loop", 0.3)
        last_detected_weapon = None
        
        while not self.should_stop:
            if self.macro_paused:
                time.sleep(0.1)
                continue
            
            try:
                # Run detection cycle using multi-weapon system
                weapon_img = self.macro_activator.detector.capture_region(self.macro_activator.weapon_region)
                weapon_alt_img = self.macro_activator.detector.capture_region(self.macro_activator.weapon_region_alt) if self.macro_activator.weapon_hashes else None
                menu_img = self.macro_activator.detector.capture_region(self.macro_activator.menu_region) if self.macro_activator.menu_hash else None
                
                if weapon_img is None:
                    time.sleep(loop_delay)
                    continue
                
                # Detect weapon in slot 2 using multi-weapon detection (with slot 2 templates)
                weapon_detected_slot2, weapon_id_slot2, distance_slot2 = self.macro_activator.detect_weapon(weapon_img, slot=2)
                
                # Detect weapon in slot 1 using multi-weapon detection (with slot 1 templates)
                weapon_detected_slot1 = False
                weapon_id_slot1 = None
                distance_slot1 = 999
                if weapon_alt_img is not None:
                    weapon_detected_slot1, weapon_id_slot1, distance_slot1 = self.macro_activator.detect_weapon(weapon_alt_img, slot=1)
                
                # Use the BEST match (lowest distance) between both regions
                threshold = self.macro_activator.detector.hash_threshold
                weapon_detected = False
                detected_weapon_id = None
                best_distance = 999
                detected_slot = None
                
                if weapon_detected_slot2 and weapon_detected_slot1:
                    if distance_slot2 <= distance_slot1:
                        weapon_detected = True
                        detected_weapon_id = weapon_id_slot2
                        best_distance = distance_slot2
                        detected_slot = 2
                    else:
                        weapon_detected = True
                        detected_weapon_id = weapon_id_slot1
                        best_distance = distance_slot1
                        detected_slot = 1
                elif weapon_detected_slot2:
                    weapon_detected = True
                    detected_weapon_id = weapon_id_slot2
                    best_distance = distance_slot2
                    detected_slot = 2
                elif weapon_detected_slot1:
                    weapon_detected = True
                    detected_weapon_id = weapon_id_slot1
                    best_distance = distance_slot1
                    detected_slot = 1
                else:
                    best_distance = min(distance_slot2, distance_slot1)
                
                # Apply delays for detected weapon
                if weapon_detected and detected_weapon_id:
                    self.macro_activator.apply_weapon_delays(detected_weapon_id)
                
                # Log detection changes with more detail
                if not weapon_detected and self.weapon_detected:
                    # Show which weapons were checked and their distances
                    weapon_info_slot2 = "None"
                    weapon_info_slot1 = "None"
                    if weapon_id_slot2:
                        weapon_name_slot2 = self.macro_activator.weapon_hashes.get(weapon_id_slot2, {}).get("name", weapon_id_slot2)
                        weapon_info_slot2 = f"{weapon_name_slot2}(dist={distance_slot2})"
                    else:
                        weapon_info_slot2 = f"dist={distance_slot2}"
                    if weapon_id_slot1:
                        weapon_name_slot1 = self.macro_activator.weapon_hashes.get(weapon_id_slot1, {}).get("name", weapon_id_slot1)
                        weapon_info_slot1 = f"{weapon_name_slot1}(dist={distance_slot1})"
                    else:
                        weapon_info_slot1 = f"dist={distance_slot1}"
                    
                    # If distances are very high (999), suggest checking regions or recapturing template
                    suggestion = ""
                    if distance_slot2 >= 999 and distance_slot1 >= 999:
                        suggestion = " - Check that regions are correctly configured"
                    elif distance_slot2 > threshold * 2 or distance_slot1 > threshold * 2:
                        suggestion = " - Consider recapturing the weapon template from this slot"
                    
                    self.log(f"Weapon lost - Slot 2: {weapon_info_slot2}, Slot 1: {weapon_info_slot1} (threshold={threshold}){suggestion}")
                    last_detected_weapon = None
                elif weapon_detected and detected_weapon_id != last_detected_weapon:
                    weapon_name = self.macro_activator.weapon_hashes.get(detected_weapon_id, {}).get("name", detected_weapon_id)
                    delays = self.macro_activator.weapon_hashes.get(detected_weapon_id, {}).get("delays", {})
                    self.log(f"Detected {weapon_name} in Slot {detected_slot} - dist={best_distance} (threshold={threshold})")
                    if delays:
                        self.log(f"  Applied delays: down={delays.get('click_down_min', 54)}-{delays.get('click_down_max', 64)}ms, up={delays.get('click_up_min', 54)}-{delays.get('click_up_max', 64)}ms")
                    last_detected_weapon = detected_weapon_id
                
                # Detect menu
                menu_detected = False
                if menu_img is not None and self.macro_activator.menu_hash is not None:
                    menu_detected, _ = self.macro_activator.detector.detect_hash(
                        menu_img, self.macro_activator.menu_hash, debug=False
                    )
                
                # Update status
                self.weapon_detected = weapon_detected
                self.menu_detected = menu_detected
                
                # Logic: activate macro ONLY if weapon detected AND menu NOT detected AND not paused
                should_activate = weapon_detected and not menu_detected and not self.macro_paused
                
                if should_activate:
                    if not self.macro_activator.macro_active:
                        self.macro_activator._activate_macro()
                        self.macro_active = True
                        weapon_name = self.macro_activator.weapon_hashes.get(detected_weapon_id, {}).get("name", detected_weapon_id)
                        self.log(f"{weapon_name} detected - Macro activated")
                else:
                    if self.macro_activator.macro_active:
                        self.macro_activator._deactivate_macro()
                        self.macro_active = False
                        if self.macro_paused:
                            self.log("Macro paused by user")
                        elif menu_detected:
                            self.log("Menu detected - Macro paused")
                        else:
                            self.log("Weapon not detected - Macro deactivated")
                
                # Update autoclick status
                self.autoclick_running = self.macro_activator.autoclicker.autoclick_running
                
                # Update LEDs (only update if macro is running)
                self.root.after(0, lambda: self.update_led("Weapon Detected", weapon_detected, macro_running=self.macro_running))
                self.root.after(0, lambda: self.update_led("Menu Detected", menu_detected, macro_running=self.macro_running))
                self.root.after(0, lambda: self.update_led("Macro Active", self.macro_active, macro_running=self.macro_running))
                self.root.after(0, lambda: self.update_led("Autoclick Running", self.autoclick_running, macro_running=self.macro_running))
                
                time.sleep(loop_delay)
                
            except Exception as e:
                self.log(f"Error in macro loop: {e}")
                time.sleep(loop_delay)
    
    def start_keybind_listener(self):
        """Start global keybind listener."""
        if self.keybind_listener:
            self.keybind_listener.stop()
        
        toggle_key = self.config_manager.get("keybinds.stop", "F7")
        
        def on_press(key):
            try:
                key_name = self.get_key_name_from_listener(key)
                if key_name == toggle_key:
                    self.root.after(0, self.toggle_macro)
            except Exception:
                pass
        
        self.keybind_listener = keyboard.Listener(on_press=on_press)
        self.keybind_listener.start()
    
    def get_key_name_from_listener(self, key):
        """Get key name from pynput key."""
        if isinstance(key, Key):
            # Handle F keys
            if hasattr(key, 'name') and key.name and key.name.startswith('f'):
                return key.name.upper()
            # Handle special keys
            key_map = {
                Key.esc: "ESC",
                Key.enter: "ENTER",
                Key.space: "SPACE",
                Key.tab: "TAB",
                Key.backspace: "BACKSPACE",
                Key.delete: "DELETE",
            }
            return key_map.get(key)
        elif isinstance(key, KeyCode):
            if key.char:
                return key.char.upper()
            elif hasattr(key, 'vk') and key.vk:
                # Handle F keys via virtual key codes
                # F1-F12 are vk codes 112-123
                if 112 <= key.vk <= 123:
                    return f"F{key.vk - 111}"
        return None
    
    def log(self, message):
        """Add log message (thread-safe)."""
        timestamp = time.strftime("%H:%M:%S")
        self.log_queue.put(f"[{timestamp}] {message}\n")
    
    def process_log_queue(self):
        """Process log queue (called from main thread)."""
        try:
            while True:
                message = self.log_queue.get_nowait()
                self.log_text.config(state=tk.NORMAL)
                self.log_text.insert(tk.END, message)
                self.log_text.see(tk.END)
                self.log_text.config(state=tk.DISABLED)
        except queue.Empty:
            pass
        
        self.root.after(LOG_PROCESS_INTERVAL, self.process_log_queue)
    
    def _setup_tray_icon(self, icon_path: Path):
        """Setup system tray icon."""
        # Load icon image for tray
        if icon_path.exists():
            tray_image = Image.open(str(icon_path))
        else:
            # Create a simple fallback icon if no icon file
            tray_image = Image.new('RGB', (64, 64), color='#4CAF50')
        
        # Create tray menu
        menu = pystray.Menu(
            pystray.MenuItem("Show", self._show_window, default=True),
            pystray.MenuItem("Start/Stop Macro", self._toggle_macro_from_tray),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit", self._exit_from_tray)
        )
        
        # Create tray icon
        self.tray_icon = pystray.Icon(
            "ARC-AutoFire",
            tray_image,
            "ARC-AutoFire",
            menu
        )
    
    def _start_tray_icon(self):
        """Start tray icon in a separate thread."""
        if self.tray_icon and not self.tray_thread:
            self.tray_thread = threading.Thread(target=self.tray_icon.run, daemon=True)
            self.tray_thread.start()
    
    def _stop_tray_icon(self):
        """Stop tray icon."""
        if self.tray_icon:
            self.tray_icon.stop()
            self.tray_icon = None
            self.tray_thread = None
    
    def _show_window(self, icon=None, item=None):
        """Show the main window from tray."""
        self.root.after(0, self._restore_window)
    
    def _restore_window(self):
        """Restore window to screen (called from main thread)."""
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
    
    def _hide_to_tray(self):
        """Hide window to system tray."""
        self._start_tray_icon()
        self.root.withdraw()
        self.log("Minimized to system tray")
    
    def _toggle_macro_from_tray(self, icon=None, item=None):
        """Toggle macro from tray menu."""
        self.root.after(0, self.toggle_macro)
    
    def _exit_from_tray(self, icon=None, item=None):
        """Exit application from tray."""
        self.root.after(0, self._force_close)
    
    def _force_close(self):
        """Force close the application (bypass minimize to tray)."""
        self._cleanup_and_close()
    
    def _cleanup_and_close(self):
        """Cleanup resources and close application."""
        # Save window position/size
        try:
            geometry = self.root.geometry()
            parts = geometry.split("+")
            if len(parts) == 3:
                size = parts[0].split("x")
                pos = [int(parts[1]), int(parts[2])]
                self.config_manager.set("gui.window_position", pos)
                self.config_manager.set("gui.window_size", [int(size[0]), int(size[1])])
                self.config_manager.save()
        except Exception:
            pass
        
        # Stop macro
        if self.macro_running:
            self.stop_macro()
        
        # Stop keybind listener
        if self.keybind_listener:
            self.keybind_listener.stop()
        
        # Stop keybind recording listener
        if self.keybind_recording_listener:
            self.keybind_recording_listener.stop()
        
        # Stop capture listener
        if self.capture_listener:
            self.capture_listener.stop()
        
        # Stop tray icon
        self._stop_tray_icon()
        
        # Close window
        self.root.destroy()
    
    def on_closing(self):
        """Handle window closing."""
        # Check if minimize to tray is enabled
        if hasattr(self, 'minimize_to_tray_var') and self.minimize_to_tray_var.get():
            self._hide_to_tray()
        else:
            self._cleanup_and_close()
    
    def run(self):
        """Run the GUI."""
        self.log("GUI started")
        self.root.mainloop()


def main():
    """Entry point for GUI."""
    app = MacroGUI()
    app.run()


if __name__ == "__main__":
    main()
