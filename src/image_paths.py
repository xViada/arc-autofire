"""Helper functions for managing organized image directory structure."""

from pathlib import Path
from typing import Optional


def get_image_base_dir() -> Path:
    """Get the base images directory path."""
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    return project_root / "images"


def get_assets_dir() -> Path:
    """Get the assets directory (icons, banners, etc.)."""
    base_dir = get_image_base_dir()
    assets_dir = base_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    return assets_dir


def get_templates_dir() -> Path:
    """Get the templates directory (default templates)."""
    base_dir = get_image_base_dir()
    templates_dir = base_dir / "templates"
    templates_dir.mkdir(parents=True, exist_ok=True)
    return templates_dir


def get_captured_dir() -> Path:
    """Get the captured templates directory (user-captured templates)."""
    base_dir = get_image_base_dir()
    captured_dir = base_dir / "captured"
    captured_dir.mkdir(parents=True, exist_ok=True)
    return captured_dir


def get_previews_dir() -> Path:
    """Get the previews directory (auto-detection previews)."""
    base_dir = get_image_base_dir()
    previews_dir = base_dir / "previews"
    previews_dir.mkdir(parents=True, exist_ok=True)
    return previews_dir


def find_template_file(filename: str) -> Optional[Path]:
    """
    Find a template file, checking both templates/ and captured/ directories.
    Checks captured/ first, then templates/ for backwards compatibility.
    
    Args:
        filename: Template filename (e.g., "kettle.png", "menu.png")
        
    Returns:
        Path to the template file if found, None otherwise
    """
    # Check captured directory first (user-captured templates take priority)
    captured_path = get_captured_dir() / filename
    if captured_path.exists():
        return captured_path
    
    # Check templates directory (default templates)
    templates_path = get_templates_dir() / filename
    if templates_path.exists():
        return templates_path
    
    # Fallback: check root images directory for backwards compatibility
    base_path = get_image_base_dir() / filename
    if base_path.exists():
        return base_path
    
    return None


def get_asset_path(filename: str) -> Path:
    """Get path to an asset file (icon, banner, etc.)."""
    return get_assets_dir() / filename


def get_captured_path(filename: str) -> Path:
    """Get path for saving a captured template."""
    return get_captured_dir() / filename


def get_preview_path(filename: str) -> Path:
    """Get path for saving a preview image."""
    return get_previews_dir() / filename
