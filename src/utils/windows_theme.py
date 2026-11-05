"""
Windows Theme Backend
---------------------
The winreg reads behind the 'system' (follow Windows) theme mode and the
tray's taskbar-ground verdict, in their own module after living inline in the
controller. The tray asks its backend, so the detection rule - off Windows,
and on any read failure, the answer is DARK, the mode the app has always
defaulted to when nothing else is knowable - is stated once, and tests can
hand a fake instead of pointing at the host's personalization.
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
    """Reads mode values from the CurrentUser personalization key: the app
    mode (``AppsUseLightTheme``) behind theme(), the shell mode
    (``SystemUsesLightTheme``) behind taskbar_uses_light()."""

    KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
    VALUE_NAME = "AppsUseLightTheme"
    TASKBAR_VALUE_NAME = "SystemUsesLightTheme"

    def _read_personalize(self, value_name: str) -> int:
        """One raw read of ``value_name`` under the personalization key; any
        failure raises, so each rule owns its own fallback."""
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.KEY_PATH)
        try:
            value, _ = winreg.QueryValueEx(key, value_name)
        finally:
            winreg.CloseKey(key)
        return value

    def theme(self) -> str:
        """The resolved theme key: ``APP_CONFIG.SYSTEM_LIGHT_THEME`` when
        Windows is light, ``APP_CONFIG.Theme.DARK`` when it is dark.

        The stock light palette was retired from the selectable set, so a
        light verdict resolves to the designated light theme the gallery also
        offers. Returns DARK wherever there is nothing reliable to read - off
        Windows or when the registry query fails - rather than raising: the
        tray has always kept running in dark when detection was impossible.
        """
        if not sys.platform == 'win32':
            return APP_CONFIG.Theme.DARK
        try:
            light = self._read_personalize(self.VALUE_NAME) == 1
        except Exception as e:
            logger.warning(f"Could not detect Windows theme, defaulting to dark: {e}")
            return APP_CONFIG.Theme.DARK
        return (APP_CONFIG.SYSTEM_LIGHT_THEME if light
                else APP_CONFIG.Theme.DARK)

    def taskbar_uses_light(self) -> bool:
        """Whether the Windows taskbar itself renders light.

        The tray glyph is painted onto the taskbar, whose strip follows the
        SHELL mode value - independent of the app mode theme() reads, so a
        light-app/dark-shell user would otherwise get a palette-muted glyph
        judged against the wrong ground. A missing shell value falls back to
        the app value (older builds carry only that); any other read failure
        is an unreadable ground and stops the walk - the answer is dark
        rather than an app mode that failed with it, and a read whose value
        exists but cannot be fetched is not a reason to answer the app mode's
        instead. Off Windows - and with nothing readable - the answer is
        False, the same degrade-dark rule theme() keeps.
        """
        if not sys.platform == 'win32':
            return False
        for value_name in (self.TASKBAR_VALUE_NAME, self.VALUE_NAME):
            try:
                return self._read_personalize(value_name) == 1
            except FileNotFoundError:
                continue  # an absent value steps down; the last pass answers dark
            except Exception as e:
                logger.warning(f"Could not detect the Windows taskbar mode, assuming dark: {e}")
                return False
        logger.warning("Could not detect the Windows taskbar mode, assuming dark")
        return False
