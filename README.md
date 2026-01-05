# ARC-AutoFire - Intelligent Macro System for Arc Raiders

An intelligent macro activator for Arc Raiders that uses perceptual hashing to detect weapon states and automatically activate/deactivate macros based on game conditions.

## Features

- **Hash-based Detection**: Uses perceptual hashing (pHash) for robust weapon and menu detection
- **Dual Slot Support**: Monitors both weapon slots (slot 1 and slot 2) for weapon detection
- **Menu Detection**: Automatically pauses macro when game menu is visible
- **GUI Interface**: User-friendly graphical interface for configuration and monitoring
- **CLI Mode**: Command-line interface for advanced users
- **Region Selection**: Visual region selector for configuring detection areas
- **Real-time Preview**: Live preview of detection regions and captured screenshots
- **Configurable Delays**: Adjustable click delays and detection intervals
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
   - Download from: https://github.com/oblitum/Interception
   - Follow the installation instructions to install the driver
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

## Configuration

Configuration is stored in `config.json`. You can edit it manually or use the GUI to configure:

### Setting Up Detection Regions (Recommended: Auto-detect)

**⚠️ Important: The game language must be set to English for auto-detection to work properly.**

The **recommended method** for setting up detection regions is using the **Auto-detect Regions** feature in the GUI. This automatically finds and configures all required regions using template matching.

#### Using Auto-detect Regions

1. **Prepare Template Images**: Ensure you have `weapon.png` and `menu.png` in the `images/` directory. These should be screenshots of:
   - `weapon.png`: The kettle weapon name text from your weapon slot
   - `menu.png`: The "Q" menu indicator (the number of any slot in the menu)

2. **Launch the GUI**: Start the application in GUI mode (`python main.py`)

3. **Start Auto-detection**: 
   - Click the **"Auto-detect Regions"** button in the Region Configuration panel
   - The application will wait for you to capture a screenshot

4. **Step 1/2 - Capture with single Weapon Slot and "Q"**:
   - In-game, equip the kettle weapon in **Slot 1**
   - Make sure you don't have other wapon equipped in slot 2
   - Make sure the game "Q" menu is **VISIBLE**
   - Press the capture keybind (default: `ALT+P`) to take a screenshot
   - The application will automatically detect:
     - Weapon region for Slot 2
     - "Q" menu region
   - A preview window will show the detected regions with confidence percentages

5. **Step 2/2 - Capture with two Weapon Slots**:
   - In-game, equip the kettle weapon in **Slot 1** (the upper weapon slot)
   - In-game, equip any other weapon in **Slot 2** (It can't be a kettle)
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

- **Weapon Region (Slot 2)**: Screen region where weapon name appears in slot 2
- **Weapon Region (Slot 1)**: Screen region where weapon name appears in slot 1
- **"Q" Menu Region**: Screen region where a slot number of the quick menu appears

### Detection Settings

- **Hash Threshold**: Hamming distance threshold (0-10 recommended, lower = more strict)
- **Hash Size**: Hash size (8, 16, or 32) - larger = more precise but slower
- **Confidence Threshold**: Detection confidence level (0.0-1.0)

### Delays

- **Click Down Min/Max**: Random delay range for mouse button down (milliseconds)
- **Click Up Min/Max**: Random delay range for mouse button up (milliseconds)
- **Detection Loop**: Delay between detection checks (seconds)

### Keybinds

- **Pause/Resume**: Toggle macro on/off (default: F6)
- **Stop**: Stop the macro completely (default: F7)
- **Capture Screen**: Take a screenshot for region selection (default: ALT+P)

## How It Works

1. **Weapon Detection**: Continuously monitors specified screen regions for weapon names using perceptual hashing
2. **"Q" Menu Detection**: Checks if the game "Q" menu is visible
3. **Macro Activation**: Macro activates only when:
   - A weapon is detected in either slot 1 or slot 2
   - The game "Q" menu is NOT visible
4. **Auto-clicking**: When active, performs mouse clicks with configurable random delays using the Interception driver

### Perceptual Hashing

The application uses perceptual hashing (pHash) to detect images. This method:
- Is robust to minor visual changes (brightness, contrast, slight position shifts)
- Works well with text and UI elements
- Provides fast comparison using Hamming distance

## Template Images

Template images are required for auto-detection. Place them in the `images/` directory:
- `weapon.png`: Template image of the weapon name text (used for both slot 1 and slot 2 detection)
- `menu.png`: Template image of the "Q" menu indicator

**Important**: 
- Template images should be captured with the game language set to **English**
- Capture these images at the same screen resolution you'll be playing at
- The `weapon.png` should show just the weapon name text area (not the entire weapon slot)
- The `menu.png` should show just the "Q" menu indicator icon/text

You can capture these using the GUI's region selector or manually. For best results:
1. Take a screenshot in-game
2. Use the region selector to crop just the weapon name or menu indicator
3. Save the cropped image as `weapon.png` or `menu.png` in the `images/` directory

## Project Structure

```
arc-autofire/
├── main.py                 # Entry point
├── config.json             # Configuration file
├── requirements.txt        # Python dependencies
├── pyproject.toml          # Project metadata
├── images/                 # Template images directory
│   ├── weapon.png
│   └── menu.png
└── src/
    ├── macro_activator.py  # Main macro logic
    ├── detection.py        # Hash-based detection
    ├── autoclick.py        # Auto-click functionality
    ├── window_detection.py # Game window detection
    ├── gui.py              # GUI interface
    ├── config.py           # Configuration constants
    └── config_manager.py   # Configuration management
```

## Troubleshooting

### Interception Driver Not Working

If you see warnings about the Interception driver:
1. Ensure `interception-python` is installed: `pip install interception-python`
2. Download and install the Interception driver from the official repository
3. Run the installer as administrator

### Detection Not Working

1. **Verify Game Language**: Ensure the game is set to **English** - this is required for template matching
2. **Use Auto-detect**: Try using the "Auto-detect Regions" feature (recommended) instead of manual setup
3. **Check Confidence Threshold**: Lower the confidence threshold in the GUI if auto-detection fails (try 0.7 or 0.75)
4. **Check Region Coordinates**: Ensure detection regions are correctly set for your screen resolution
5. **Update Template Images**: Capture new template images if the game UI has changed or if you're using a different screen resolution
6. **Adjust Hash Threshold**: Increase threshold if detection is too strict, decrease if too loose
7. **Verify Screen Resolution**: Ensure `screen_resolution` in config.json matches your actual resolution

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

