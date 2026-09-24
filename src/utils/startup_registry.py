"""
Startup Registry Access
-----------------------

Autostart on Windows lives in the per-user Run key
(``HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run``). The controller
performs every autostart registry operation through this small interface, so the
*policy* (opt-out first run, healing a stale entry, only persisting the
preference once the registry agrees) stays in one place and can be exercised
against an in-memory backend in tests instead of the developer's real hive.

Contract used by the caller:

- ``read()``   -> the stored value, or None when it is absent or unreadable
- ``write()``  -> True when the registry now holds the given value
- ``delete()`` -> True when the value is absent afterwards (an already-absent
                  value counts as success: the desired state holds, and a stale
                  entry left behind by a failed delete must stay healable)
"""
import logging
from typing import Optional

from config import APP_CONFIG

logger = logging.getLogger(__name__)

RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"

try:
    import winreg
except ImportError:  # non-Windows: the controller never reaches these methods
    winreg = None


class StartupRegistry:
    """Real per-user Run-key access (Windows only)."""

    key_path = RUN_KEY_PATH

    def __init__(self, value_name: str = APP_CONFIG.APP_NAME):
        self.value_name = value_name

    def read(self) -> Optional[str]:
        """The current Run value, or None when it is absent or unreadable."""
        if winreg is None:
            return None
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.key_path, 0, winreg.KEY_READ) as key:
                value, _ = winreg.QueryValueEx(key, self.value_name)
                return value
        except FileNotFoundError:
            return None
        except OSError as e:
            logger.warning(f"Could not read the startup registry key: {e}")
            return None

    def write(self, value: str) -> bool:
        """Create/replace the Run value; True when the registry holds it."""
        if winreg is None:
            return False
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.key_path, 0, winreg.KEY_ALL_ACCESS) as key:
                winreg.SetValueEx(key, self.value_name, 0, winreg.REG_SZ, value)
            return True
        except FileNotFoundError:
            logger.error(f"Could not find registry key path: {self.key_path}")
            return False
        except OSError as e:
            logger.error(f"Error writing the Windows registry: {e}")
            return False

    def delete(self) -> bool:
        """Remove the Run value; True when it is absent afterwards."""
        if winreg is None:
            return False
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.key_path, 0, winreg.KEY_ALL_ACCESS) as key:
                try:
                    winreg.DeleteValue(key, self.value_name)
                except FileNotFoundError:
                    pass  # already gone: the desired state holds
            return True
        except FileNotFoundError:
            # The whole Run key is missing, so the value is absent by definition.
            return True
        except OSError as e:
            logger.error(f"Error deleting the Windows registry value: {e}")
            return False
