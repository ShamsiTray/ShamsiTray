"""
Windows Theme Backend
---------------------
The winreg read behind the 'system' (follow Windows) theme mode, in its own
module after living inline in the controller. The tray asks its backend, so
the detection rule - off Windows, and on any read failure, the answer is
DARK, the mode the app has always defaulted to when nothing else is knowable
- is stated once, and tests can hand a fake instead of pointing at the
host's personalization.
"""
import sys

from config import APP_CONFIG
from utils.logger import setup_logging

# winreg exists only on Windows; guard the import the same way the read is
# guarded so importing this module never depends on the host platform.
if sys.platform == 'win32':
    import winreg

logger = setup_logging(__name__)


class WindowsThemeBackend:
    """Reads ``AppsUseLightTheme`` from the CurrentUser personalization key."""

    KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
    VALUE_NAME = "AppsUseLightTheme"

    def theme(self) -> str:
        """The resolved theme verdict: ``APP_CONFIG.Theme.LIGHT`` or ``.DARK``.

        Returns DARK wherever there is nothing reliable to read - off Windows
        or when the registry query fails - rather than raising: the tray has
        always kept running in dark when detection was impossible.
        """
        if not sys.platform == 'win32':
            return APP_CONFIG.Theme.DARK
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.KEY_PATH)
            value, _ = winreg.QueryValueEx(key, self.VALUE_NAME)
            winreg.CloseKey(key)
            return APP_CONFIG.Theme.LIGHT if value == 1 else APP_CONFIG.Theme.DARK
        except Exception as e:
            logger.warning(f"Could not detect Windows theme, defaulting to dark: {e}")
            return APP_CONFIG.Theme.DARK
