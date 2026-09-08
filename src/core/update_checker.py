"""
Update Checker
--------------

Non-blocking application and holiday-data update checks over QtNetwork.

The app check asks the GitHub releases API for the latest release and reports
the setup installer's download URL together with its sha256 digest (GitHub
provides it, so downloads can be verified without a separate checksum file).
The holiday check downloads the raw holidays file, validates it, and swaps the
AppData store atomically. Network failures are logged, never raised.
"""
import hashlib
import json
import logging
from typing import Optional, Tuple

from PyQt6.QtCore import QObject, QUrl, pyqtSignal
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from config import APP_CONFIG
from utils import holiday_io

logger = logging.getLogger(__name__)

NETWORK_TIMEOUT_MS = 15000
INSTALLER_ASSET_PREFIX = "ShamsiTraySetup"
INSTALLER_ASSET_SUFFIX = ".exe"
DAY_MS = 24 * 60 * 60 * 1000


def is_newer_version(latest: str, current: str) -> bool:
    """True when `latest` is strictly newer than `current` (dot-separated integers)."""
    def parts(value: str) -> Optional[Tuple[int, ...]]:
        try:
            return tuple(int(p) for p in str(value).strip().lstrip('vV ').split('.'))
        except ValueError:
            return None

    latest_parts, current_parts = parts(latest), parts(current)
    if latest_parts is None or current_parts is None:
        return False
    width = max(len(latest_parts), len(current_parts))
    latest_parts += (0,) * (width - len(latest_parts))
    current_parts += (0,) * (width - len(current_parts))
    return latest_parts > current_parts


def digest_hex(digest_field: str) -> Optional[str]:
    """Extract the hex part of a GitHub asset digest ('sha256:abc...')."""
    if not digest_field or ':' not in digest_field:
        return None
    algorithm, _, value = digest_field.partition(':')
    return value.lower() if algorithm.lower() == 'sha256' else None


def should_notify(latest_version: str, ignored_version: Optional[str]) -> bool:
    """Auto checks stay quiet about versions the user chose to ignore."""
    return latest_version != ignored_version


class UpdateChecker(QObject):
    app_update_available = pyqtSignal(str, str, str)  # version, installer_url, sha256_hex
    holidays_updated = pyqtSignal()
    no_updates = pyqtSignal()
    check_failed = pyqtSignal(str)
    download_progress = pyqtSignal(int, int)  # received bytes, total bytes (-1 if unknown)
    installer_downloaded = pyqtSignal(str)  # local file path
    download_failed = pyqtSignal(str)

    def __init__(self, current_data_version: int = 0, parent=None):
        super().__init__(parent)
        self._current_data_version = current_data_version
        self._manager = QNetworkAccessManager(self)
        self._pending = 0
        self._app_found: Optional[Tuple[str, str, str]] = None
        self._app_failed = False
        self._holidays_applied = False
        self._holidays_failed = False
        self._download_reply: Optional[QNetworkReply] = None

    # --- checks ---

    def check(self):
        """Fire both update checks asynchronously; results arrive via signals."""
        if self._pending:
            return
        self._app_found = None
        self._app_failed = False
        self._holidays_applied = False
        self._holidays_failed = False
        self._get(APP_CONFIG.APP_RELEASES_API_URL, self._on_app_reply)
        self._get(APP_CONFIG.HOLIDAYS_UPDATE_URL, self._on_holidays_reply)

    def cancel_download(self):
        if self._download_reply is not None:
            self._download_reply.abort()
            self._download_reply = None

    def _get(self, url: str, handler):
        request = QNetworkRequest(QUrl(url))
        request.setTransferTimeout(NETWORK_TIMEOUT_MS)
        request.setAttribute(
            QNetworkRequest.Attribute.RedirectPolicyAttribute,
            QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy)
        request.setRawHeader(b"User-Agent", f"{APP_CONFIG.APP_NAME}/{APP_CONFIG.APP_VERSION}".encode())
        reply = self._manager.get(request)
        reply.finished.connect(lambda: handler(reply))
        self._pending += 1

    @staticmethod
    def _error_text(reply: QNetworkReply) -> str:
        error = reply.error()
        return f"{error.name} ({error.value}): {reply.errorString()}"

    def _finish_request(self):
        self._pending -= 1
        if self._pending <= 0:
            self._conclude()

    def _conclude(self):
        if self._app_found:
            self.app_update_available.emit(*self._app_found)
        if self._holidays_applied:
            self.holidays_updated.emit()
        if self._app_found is None and not self._holidays_applied:
            if self._app_failed or self._holidays_failed:
                self.check_failed.emit("network")
            else:
                self.no_updates.emit()

    def _on_app_reply(self, reply: QNetworkReply):
        try:
            if reply.error() != QNetworkReply.NetworkError.NoError:
                raise RuntimeError(self._error_text(reply))
            payload = json.loads(bytes(reply.readAll()).decode('utf-8'))
            tag = str(payload.get('tag_name', '')).strip()
            if not is_newer_version(tag, APP_CONFIG.APP_VERSION):
                logger.info(f"App is up to date (latest release: {tag or 'unknown'}).")
                return
            asset = self._find_installer_asset(payload)
            if asset is None:
                logger.warning(f"Release {tag} has no setup installer asset; skipping the app update offer.")
                return
            version = tag.lstrip('vV ')
            self._app_found = (version, asset['browser_download_url'], digest_hex(str(asset.get('digest', ''))) or '')
            logger.info(f"App update available: {version}")
        except Exception as e:
            self._app_failed = True
            logger.warning(f"App update check failed: {e}")
        finally:
            self._finish_request()

    @staticmethod
    def _find_installer_asset(payload: dict) -> Optional[dict]:
        assets = payload.get('assets', [])
        for asset in assets:
            name = str(asset.get('name', ''))
            if name.startswith(INSTALLER_ASSET_PREFIX) and name.endswith(INSTALLER_ASSET_SUFFIX):
                return asset
        return None

    def _on_holidays_reply(self, reply: QNetworkReply):
        try:
            if reply.error() != QNetworkReply.NetworkError.NoError:
                raise RuntimeError(self._error_text(reply))
            payload = bytes(reply.readAll())
            remote_version = holiday_io.read_version_from_payload(payload)
            if remote_version <= self._current_data_version:
                logger.info(f"Holiday data is up to date (remote version {remote_version}).")
                return
            if not holiday_io.replace_store(payload):
                self._holidays_failed = True
                return
            self._current_data_version = remote_version
            self._holidays_applied = True
        except Exception as e:
            self._holidays_failed = True
            logger.warning(f"Holiday update check failed: {e}")
        finally:
            self._finish_request()

    # --- installer download ---

    def download_installer(self, url: str, destination, expected_sha256: str = ''):
        """Stream the installer to `destination`; emits download_progress, then
        installer_downloaded(path) after sha256 verification, or download_failed."""
        request = QNetworkRequest(QUrl(url))
        request.setTransferTimeout(0)
        request.setAttribute(
            QNetworkRequest.Attribute.RedirectPolicyAttribute,
            QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy)
        request.setRawHeader(b"User-Agent", f"{APP_CONFIG.APP_NAME}/{APP_CONFIG.APP_VERSION}".encode())
        self._download_reply = self._manager.get(request)
        reply = self._download_reply
        reply.downloadProgress.connect(self.download_progress.emit)
        hasher = hashlib.sha256()

        def on_finished():
            self._download_reply = None
            try:
                if reply.error() == QNetworkReply.NetworkError.OperationCanceledError:
                    self.download_failed.emit("canceled")
                    return
                if reply.error() != QNetworkReply.NetworkError.NoError:
                    raise RuntimeError(self._error_text(reply))
                data = bytes(reply.readAll())
                hasher.update(data)
                if expected_sha256 and hasher.hexdigest() != expected_sha256.lower():
                    raise RuntimeError("Downloaded installer failed the sha256 check; it was not saved.")
                with open(destination, 'wb') as f:
                    f.write(data)
                self.installer_downloaded.emit(str(destination))
            except Exception as e:
                logger.error(f"Installer download failed: {e}")
                self.download_failed.emit(str(e))

        reply.finished.connect(on_finished)
