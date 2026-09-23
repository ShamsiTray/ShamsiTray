"""Release version-consistency check.

Asserts the three places the app version must agree actually do:

1. ``src/config.py``         -> ``APP_VERSION = "X.Y.Z"`` (source of truth)
2. ``build/SetupScript.iss`` -> ``#define MyAppVersion "X.Y.Z"``
3. ``build/details.txt``     -> ``filevers``/``prodvers`` (X.Y.Z.0) and the
                                ``FileVersion``/``ProductVersion`` strings

Run before tagging a release:

    python build/check_versions.py

Exits 0 when everything matches; exits 1 and prints every mismatch found, so a
single forgotten bump can never ship a release whose updater offers the wrong
version to its own users.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def check_versions() -> int:
    config_text = read(ROOT / "src" / "config.py")
    iss_text = read(ROOT / "build" / "SetupScript.iss")
    details_text = read(ROOT / "build" / "details.txt")

    errors: list = []

    match = re.search(r'APP_VERSION\s*=\s*"(\d+\.\d+\.\d+)"', config_text)
    if not match:
        errors.append("src/config.py: APP_VERSION not found")
        app_version = None
    else:
        app_version = match.group(1)

    match = re.search(r'#define\s+MyAppVersion\s+"(\d+\.\d+\.\d+)"', iss_text)
    if not match:
        errors.append("build/SetupScript.iss: MyAppVersion not found")
        iss_version = None
    else:
        iss_version = match.group(1)

    match = re.search(r"StringStruct\('FileVersion',\s*'(\d+\.\d+\.\d+\.\d+)'\)", details_text)
    file_version = match.group(1) if match else None
    if file_version is None:
        errors.append("build/details.txt: FileVersion StringStruct not found")

    match = re.search(r"StringStruct\('ProductVersion',\s*'(\d+\.\d+\.\d+\.\d+)'\)", details_text)
    product_version = match.group(1) if match else None
    if product_version is None:
        errors.append("build/details.txt: ProductVersion StringStruct not found")

    print(f"src/config.py APP_VERSION        : {app_version}")
    print(f"build/SetupScript.iss MyAppVersion: {iss_version}")
    print(f"build/details.txt FileVersion    : {file_version}")
    print(f"build/details.txt ProductVersion : {product_version}")
    print()

    if app_version is not None:
        expected_four = f"{app_version}.0"
        if iss_version != app_version:
            errors.append(f"SetupScript.iss MyAppVersion {iss_version!r} != APP_VERSION {app_version!r}")
        if file_version != expected_four:
            errors.append(f"details.txt FileVersion {file_version!r} != {expected_four!r} (from APP_VERSION)")
        if product_version != expected_four:
            errors.append(f"details.txt ProductVersion {product_version!r} != {expected_four!r} (from APP_VERSION)")

    if errors:
        print("VERSION MISMATCH - resolve before tagging the release:")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("All version strings agree.")
    return 0


if __name__ == "__main__":
    sys.exit(check_versions())
