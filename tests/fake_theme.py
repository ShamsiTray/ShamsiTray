"""
In-memory Windows theme backend (test double)
---------------------------------------------

Stands in for ``utils.windows_theme.WindowsThemeBackend`` so theme resolution
runs at boot exactly as it does in production while nothing reads the host's
real personalization registry.

It implements the backend contract and adds the hooks the tests need:

    backend.value          -> the verdict the next theme() reads (None = unset,
                              which degrades to the rule's own DARK default)
    backend.reads          -> how many theme reads happened
    backend.taskbar_light  -> the ground verdict the next
                              taskbar_uses_light() reads (None = unset, which
                              degrades to the rule's own dark/False default)
    backend.taskbar_reads  -> how many taskbar reads happened
"""
from typing import Optional


class FakeThemeBackend:
    """Settable Windows theme verdicts with inspection counters."""

    def __init__(self, value: Optional[str] = None):
        self.value = value
        self.reads = 0
        self.taskbar_light: Optional[bool] = None
        self.taskbar_reads = 0

    # --- the WindowsThemeBackend contract ---

    def theme(self) -> str:
        self.reads += 1
        if self.value is None:
            # Mirror the real rule: an unknowable verdict reads DARK.
            from config import APP_CONFIG
            return APP_CONFIG.Theme.DARK
        return self.value

    def taskbar_uses_light(self) -> bool:
        self.taskbar_reads += 1
        if self.taskbar_light is None:
            # Mirror the real rule: an unknowable ground reads dark.
            return False
        return self.taskbar_light

    def reset(self):
        """Forget the recorded activity, keeping the current verdicts."""
        self.reads = 0
        self.taskbar_reads = 0
