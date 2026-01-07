"""
Asset Management Utilities
--------------------------

This module provides functions for verifying and loading application assets,
such as fonts and data files. It helps ensure that the application has all
its required resources before starting up.
"""
from PyQt5.QtGui import QFontDatabase

from config import APP_CONFIG
from .logging_setup import setup_logging

logger = setup_logging(__name__)

def load_fonts() -> None:
    """Load all .ttf and .otf fonts from the resources directory."""
    font_dir = APP_CONFIG.FONT_DIR
    if not font_dir.is_dir():
        raise FileNotFoundError(f"Font directory not found: {font_dir}")
    
    loaded_fonts = []
    for extension in ("*.ttf", "*.otf"):
        for font_path in font_dir.glob(extension):
            if QFontDatabase.addApplicationFont(str(font_path)) != -1:
                loaded_fonts.append(font_path.name)
            else:
                logger.warning(f"Failed to load font: {font_path.name}")
            
    if loaded_fonts:
        logger.info(f"Loaded fonts: {', '.join(loaded_fonts)}")
    else:
        raise RuntimeError("No fonts were loaded from the font directory.")

def verify_assets() -> None:
    """
    Verify that required assets exist. Raises FileNotFoundError if any are missing.
    """
    assets_to_check = {
        "App icon": APP_CONFIG.ICON_PATH,
        "Holidays data file": APP_CONFIG.HOLIDAYS_FILE_PATH,
        "Tutorial GIF": APP_CONFIG.TUTORIAL_GIF_PATH,
        "Font directory": APP_CONFIG.FONT_DIR,
    }
    
    missing_assets = [name for name, path in assets_to_check.items() if not path.exists()]
    
    if not any(APP_CONFIG.FONT_DIR.glob("*.ttf")) and not any(APP_CONFIG.FONT_DIR.glob("*.otf")):
        missing_assets.append("Any .ttf or .otf font file")

    if missing_assets:
        error_msg = "One or more required assets are missing: " + ", ".join(missing_assets)
        logger.error(error_msg)
        raise FileNotFoundError(error_msg)
    
    logger.info("All required assets verified successfully.")
