<p align="center">
  <img src="images/assets/banner.png" alt="ARC-AutoFire Banner" width="800">
</p>

# ARC-AutoFire - Intelligent Macro System for Arc Raiders

An intelligent macro activator for Arc Raiders that uses perceptual hashing to detect weapon states and automatically activate/deactivate macros based on game conditions.

## Features

- **Multi-Weapon Support**: Supports multiple weapons (Kettle, Burletta, etc.) with individual delay configurations
- **Per-Weapon Delays**: Automatically switches delay settings based on detected weapon
- **Weapon Profiles**: Each weapon can have multiple profiles (e.g., "Optimal") with different delay settings
- **Hash-based Detection**: Uses perceptual hashing (pHash) for robust weapon and menu detection
- **Dual Slot Support**: Monitors both weapon slots (slot 1 and slot 2) for weapon detection
- **Menu Detection**: Automatically pauses macro when game "Q" menu is visible
- **GUI Interface**: Comprehensive graphical interface with multiple tabs (Settings, Regions, Templates, Keybinds, Status)
- **System Tray Support**: Minimize to system tray for background operation
- **CLI Mode**: Command-line interface for advanced users
- **Auto-detect Regions**: Automatic region detection using template matching
- **Region Selection**: Visual region selector for configuring detection areas
- **Real-time Preview**: Live preview of detection regions and captured screenshots
- **Configurable Delays**: Adjustable click delays per weapon and detection intervals
- **Hotkey Controls**: Pause/resume and stop functionality via keyboard shortcuts
- **Window Detection**: Automatically detects and focuses on the Arc Raiders game window

## Requirements

- Python 3.8 or higher
- Windows OS (uses `pywin32` and `interception-python`)
- Arc Raiders game
- **Game language must be set to English** (required for template matching)

## Installation

1. Clone or download this repository:
   ```bash
   git clone <repository-url>
   cd arc-autofire
   ```

2. Create a virtual environment (recommended):
   ```bash
   python -m venv venv
   venv\Scripts\activate  # On Windows
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Install Interception driver (required for auto-clicking):
   - Download from: https://github.com/oblitum/Interception/releases
   - Run `install-interception.exe /install` as Administrator
   - Restart Windows after installation
   - The `interception-python` package should be installed via pip, but the driver itself needs to be installed separately

## Usage

### GUI Mode (Default)

Launch the application with the GUI:
```bash
python main.py
```

Or explicitly:
```bash
python main.py --gui
```

### CLI Mode

Launch in command-line mode:
```bash
python main.py --cli
```

**Note**: CLI mode uses configuration from `config.json`. For full configuration options, use the GUI mode.

## Configuration

Configuration is stored in `config.json`. You can edit it manually or use the GUI to configure:

### GUI Tabs Overview

The GUI provides several tabs for configuration:

- **Settings Tab**: 
  - Configure delays for each weapon individually
  - Select weapon profiles (e.g., "Optimal" preset or custom delays)
  - Enable/disable weapons
  - Adjust detection settings (hash threshold, hash size, confidence threshold)
  - Set detection loop delay
- **Regions Tab**: 
  - Auto-detect regions using template matching (recommended)
  - Manual region selection with visual region selector
  - Preview detected regions with confidence scores
  - Configure screen resolution
- **Templates Tab**: 
  - View all weapon templates
  - Capture new templates for weapons or menu
  - Enable/disable individual weapons
  - View template file paths
- **Keybinds Tab**: 
  - Configure keyboard shortcuts for pause/resume (default: F6)
  - Configure stop shortcut (default: F7)
  - Configure screen capture shortcut (default: ALT+P)
- **Status Tab**: 
  - Real-time weapon detection status
  - Menu detection status
  - Macro activation status
  - Auto-click status
  - Detection logs and system information

**System Tray**: The GUI can minimize to the system tray. Right-click the tray icon to restore or exit.

### Setting Up Detection Regions (Recommended: Auto-detect)

**⚠️ Important: The game language must be set to English for auto-detection to work properly.**

The **recommended method** for setting up detection regions is using the **Auto-detect Regions** feature in the GUI. This automatically finds and configures all required regions using template matching.

#### Using Auto-detect Regions

1. **Prepare Template Images**: Ensure you have weapon templates (e.g., `kettle.png`, `burletta.png`) and `menu.png` in the `images/templates/` or `images/captured/` directory. These should be screenshots of:
   - Weapon templates: The weapon name text from your weapon slot
   - `menu.png`: The "Q" menu indicator (the number of any slot in the menu)

2. **Launch the GUI**: Start the application in GUI mode (`python main.py`)

3. **Start Auto-detection**: 
   - Go to the **Regions** tab
   - Click the **"Auto-detect Regions"** button
   - The application will wait for you to capture a screenshot

4. **Step 1/2 - Capture with single Weapon Slot and "Q"**:
   - In-game, equip a **kettle** in **Slot 1** and select it
   - In-game, equip a weapon in **Slot 2**
   - Make sure the game "Q" menu is **VISIBLE**
   - Press the capture keybind (default: `ALT+P`) to take a screenshot
   - The application will automatically detect:
     - Weapon region for Slot 2
     - "Q" menu region
   - A preview window will show the detected regions with confidence percentages

5. **Step 2/2 - Capture with two Weapon Slots**:
   - In-game, equip a **kettle** in **Slot 1**
   - In-game, equip a different weapon in **Slot 2** and select it
   - Make sure the game "Q" menu is **NOT visible**
   - Press the capture keybind again (default: `ALT+P`)
   - The application will automatically detect:
     - Weapon region for Slot 1
   - A final preview will show all three detected regions

6. **Review and Confirm**: 
   - Check the confidence percentages (should be above your threshold, typically 0.8)
   - Verify the regions are correctly positioned in the preview
   - Click "Save Regions" to apply the configuration

#### Manual Region Selection (Alternative)

If auto-detection doesn't work or you prefer manual setup:
- Click **"Capture Screen"** to take a screenshot
- Use the region selector to manually draw rectangles around:
  - Weapon name in Slot 2
  - Weapon name in Slot 1
  - "Q" menu indicator
- Click the appropriate "Set as..." buttons to save each region

### Detection Regions

- **Weapon Region (Slot 1)**: Screen region where weapon name appears in slot 1
- **Weapon Region (Slot 2)**: Screen region where weapon name appears in slot 2
- **"Q" Menu Region**: Screen region where a slot number of the quick menu appears

### Detection Settings

- **Hash Threshold**: Hamming distance threshold (0-10 recommended, lower = more strict)
- **Hash Size**: Hash size (8, 16, or 32) - larger = more precise but slower
- **Confidence Threshold**: Detection confidence level (0.0-1.0)

### Weapon Configuration

Each weapon can be configured with:
- **Enabled/Disabled**: Toggle weapon detection on/off
- **Template Images**: Per-slot templates (`weapon_slot1.png`, `weapon_slot2.png`) or shared template
- **Profiles**: Predefined delay profiles (e.g., "Optimal") or custom delays
- **Delays**: Per-weapon click timing configuration:
  - **Click Down Min/Max**: Random delay range for mouse button down (milliseconds)
  - **Click Up Min/Max**: Random delay range for mouse button up (milliseconds)

The system automatically switches to the appropriate delays when a weapon is detected.

### Detection Settings

- **Hash Threshold**: Hamming distance threshold (0-10 recommended, lower = more strict)
- **Hash Size**: Hash size (8, 16, or 32) - larger = more precise but slower
- **Confidence Threshold**: Detection confidence level (0.0-1.0) for auto-detection
- **Detection Loop**: Delay between detection checks (seconds)

### Keybinds

- **Pause/Resume**: Toggle macro on/off (default: F6)
- **Stop**: Stop the macro completely (default: F7)
- **Capture Screen**: Take a screenshot for region selection (default: ALT+P)

## How It Works

1. **Weapon Detection**: Continuously monitors specified screen regions for weapon names using perceptual hashing
   - Supports multiple weapons (Kettle, Burletta, etc.)
   - Checks both slot 1 and slot 2
   - Uses per-slot templates when available, falls back to shared templates
2. **Weapon Identification**: Identifies which weapon is equipped and automatically switches to that weapon's delay configuration
3. **"Q" Menu Detection**: Checks if the game "Q" menu is visible
4. **Macro Activation**: Macro activates only when:
   - A weapon is detected in either slot 1 or slot 2
   - The game "Q" menu is NOT visible
5. **Auto-clicking**: When active, performs mouse clicks with weapon-specific random delays using the Interception driver
   - Delays are automatically adjusted based on the detected weapon
   - Hold LEFT MOUSE BUTTON to activate auto-click when macro is active

### Perceptual Hashing

The application uses perceptual hashing (pHash) to detect images. This method:
- Is robust to minor visual changes (brightness, contrast, slight position shifts)
- Works well with text and UI elements
- Provides fast comparison using Hamming distance

## Template Images

Template images are organized in subdirectories within `images/`:
- `images/templates/`: Default templates (included with the project)
- `images/captured/`: User-captured templates (takes priority over templates/)
- `images/previews/`: Auto-detection preview images
- `images/assets/`: Icons, banners, and other assets

### Weapon Templates

Each weapon needs template images. You can use:
- **Shared template**: `weapon_name.png` (e.g., `kettle.png`) - used for both slots
- **Per-slot templates**: `weapon_name_slot1.png` and `weapon_name_slot2.png` (e.g., `kettle_slot1.png`, `kettle_slot2.png`) - more accurate

**Template naming**: Templates are named after the weapon ID in the configuration (e.g., `kettle.png` for the "kettle" weapon).

### Menu Template

- `menu.png`: Template image of the "Q" menu indicator

**Important**: 
- Template images should be captured with the game language set to **English**
- Capture these images at the same screen resolution you'll be playing at
- Weapon templates should show just the weapon name text area (not the entire weapon slot)
- The `menu.png` should show just the "Q" menu indicator icon/text

### Capturing Templates

You can capture templates using the GUI:
1. Go to the **Templates** tab
2. Select a weapon or menu
3. Click **"Capture Template"** or use the capture keybind
4. Templates are automatically saved to `images/captured/`

For best results:
- Capture templates at the same resolution you'll be playing at
- Ensure the weapon name is clearly visible
- Use per-slot templates for better accuracy if weapon appearance differs between slots

## Project Structure

```
arc-autofire/
├── main.py                 # Entry point
├── config.json             # Configuration file (auto-generated)
├── requirements.txt        # Python dependencies
├── pyproject.toml          # Project metadata
├── images/                 # Images directory
│   ├── assets/            # Icons, banners, etc.
│   ├── templates/         # Default weapon/menu templates
│   ├── captured/          # User-captured templates (priority)
│   └── previews/          # Auto-detection preview images
└── src/
    ├── macro_activator.py  # Main macro logic (multi-weapon support)
    ├── detection.py        # Hash-based detection
    ├── autoclick.py        # Auto-click functionality (Interception driver)
    ├── window_detection.py # Game window detection
    ├── gui.py              # GUI interface (multi-tab)
    ├── config.py           # Configuration constants and defaults
    ├── config_manager.py   # Configuration management (JSON)
    └── image_paths.py      # Image directory management
```

## Troubleshooting

### Interception Driver Not Working

If you see warnings about the Interception driver:
1. Ensure `interception-python` is installed: `pip install interception-python`
2. Download the Interception driver from: https://github.com/oblitum/Interception/releases
3. Run `install-interception.exe /install` as Administrator
4. Restart Windows after installation
5. Verify installation by checking if the driver appears in Device Manager

### Detection Not Working

1. **Verify Game Language**: Ensure the game is set to **English** - this is required for template matching
2. **Use Auto-detect**: Try using the "Auto-detect Regions" feature (recommended) instead of manual setup
3. **Check Confidence Threshold**: Lower the confidence threshold in the GUI if auto-detection fails (try 0.7 or 0.75)
4. **Check Region Coordinates**: Ensure detection regions are correctly set for your screen resolution
5. **Update Template Images**: Capture new template images if the game UI has changed or if you're using a different screen resolution
6. **Verify Weapon Templates**: Ensure weapon templates exist in `images/templates/` or `images/captured/` and are enabled in the Settings tab
7. **Check Per-Slot Templates**: If using per-slot templates, ensure both `weapon_slot1.png` and `weapon_slot2.png` exist
8. **Adjust Hash Threshold**: Increase threshold if detection is too strict, decrease if too loose
9. **Verify Screen Resolution**: Ensure `screen_resolution` in config.json matches your actual resolution
10. **Check Weapon Configuration**: Verify the weapon is enabled in the Settings tab and has valid templates

### Game Window Not Detected

- Ensure Arc Raiders is running
- Check that the window title contains expected keywords
- Try manually focusing the game window

## Development

### Running Tests

```bash
pytest
```

### Code Formatting

```bash
black src/
```

### Linting

```bash
flake8 src/
```

## Disclaimer

This tool is for educational purposes. Use at your own risk. Make sure you comply with the game's terms of service regarding automation tools.Author is not responsible for bans or penalties.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

