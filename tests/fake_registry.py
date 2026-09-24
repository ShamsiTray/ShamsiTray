"""
In-memory startup registry backend (test double)
-----------------------------------------------

Stands in for ``utils.startup_registry.StartupRegistry`` so the real autostart
logic (opt-out first run, healing a stale entry, only persisting the preference
once the registry agrees) runs exactly as it does in production while the
developer's real HKCU hive is never touched.

It implements the same three-method contract as the real backend and adds the
failure switches and inspection hooks the tests need:

    registry.value          -> the stored value (None = no Run entry)
    registry.entry_exists   -> whether a Run entry is present
    registry.writes         -> every value written, in order
    registry.deletes        -> how many successful deletes happened
    registry.reads          -> how many reads happened
    registry.fail_writes    -> make write() fail (e.g. access denied)
    registry.fail_deletes   -> make delete() fail
"""
from typing import List, Optional


class FakeStartupRegistry:
    """In-memory Run key with inspectable state and injectable failures."""

    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"

    def __init__(self, value: Optional[str] = None):
        self.value = value
        self.writes: List[str] = []
        self.deletes = 0
        self.reads = 0
        self.fail_writes = False
        self.fail_deletes = False

    # --- the StartupRegistry contract ---

    def read(self) -> Optional[str]:
        self.reads += 1
        return self.value

    def write(self, value: str) -> bool:
        if self.fail_writes:
            return False
        self.value = value
        self.writes.append(value)
        return True

    def delete(self) -> bool:
        if self.fail_deletes:
            return False
        self.deletes += 1
        self.value = None
        return True

    # --- inspection helpers ---

    @property
    def entry_exists(self) -> bool:
        """True when a Run entry is currently present."""
        return self.value is not None

    def reset(self):
        """Forget the recorded activity, keeping the current value.

        Booting a tray runs the real first-run autostart default, so a test that
        asserts on what a TOGGLE (or a platform-guarded call) did must first clear
        the boot's own activity.
        """
        self.writes.clear()
        self.deletes = 0
        self.reads = 0
