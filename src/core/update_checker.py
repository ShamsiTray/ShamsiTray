"""
Update Checker
--------------

Non-blocking application and holiday-data update checks over QtNetwork.

The app check asks the GitHub releases API for the latest release and reports
the setup installer's download URL together with its sha256 digest (GitHub
provides it, so downloads can be verified without a separate checksum file).
The holiday check downloads the raw holidays file, validates it, and swaps the
AppData store atomically. Network failures are logged, never raised.

Reply hygiene: every reply is handled exactly once (the finished handler
disconnects itself), is never read after the transport was aborted, and is
released with deleteLater() right after handling. Reading an aborted TLS
transport is what makes Qt print "QIODevice::read (QSslSocket): device not
open" - the warning accompanies the failure, it is not a failure itself.
The installer download additionally streams to disk in readyRead chunks:
nothing is buffered whole in RAM and the reply is never read after finished
beyond whatever bytes are still demonstrably available.
"""
import hashlib
import json
import logging
import os
import re
from typing import Optional, Tuple

from PyQt6.QtCore import QObject, QTimer, QUrl, pyqtSignal
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from config import APP_CONFIG
from utils import holiday_io

logger = logging.getLogger(__name__)

NETWORK_TIMEOUT_MS = 20000  # slow GitHub routes timed out at 15s too often
DOWNLOAD_INACTIVITY_TIMEOUT_MS = 30000  # stalled-transfer watchdog
INSTALLER_ASSET_PREFIX = "ShamsiTraySetup"
INSTALLER_ASSET_SUFFIX = ".exe"
DAY_MS = 24 * 60 * 60 * 1000

# Test hook: point the holiday check at a local server (e.g.
# `python -m http.server` serving a hand-made holidays.json) without touching
# config.py. Set before launch; read on every check.
HOLIDAYS_URL_ENV = "SHAMSITRAY_HOLIDAYS_URL"


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


def is_valid_sha256(value: Optional[str]) -> bool:
    """True when ``value`` is a well-formed 64-char hex sha256 digest.

    Used at the update-offer boundary: a missing/empty/malformed digest used to
    slip through as '' and silently skip the final download checksum comparison,
    accepting the installer unverified.
    """
    return bool(value) and re.fullmatch(r"[0-9a-fA-F]{64}", value) is not None


def file_sha256(path) -> Optional[str]:
    """sha256 hex digest of a local file, or None when it cannot be read.

    Lets the controller reuse an already-downloaded installer when its digest
    matches the release's, instead of re-downloading the same file.
    """
    hasher = hashlib.sha256()
    try:
        with open(os.fspath(path), 'rb') as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b''):
                hasher.update(chunk)
    except OSError:
        return None
    return hasher.hexdigest()


def should_notify(latest_version: str, ignored_version: Optional[str]) -> bool:
    """Auto checks stay quiet about versions the user chose to ignore."""
    return latest_version != ignored_version


class UpdateChecker(QObject):
    app_update_available = pyqtSignal(str, str, str)  # version, installer_url, sha256_hex
    holidays_updated = pyqtSignal()
    no_updates = pyqtSignal()
    check_failed = pyqtSignal(str)
    check_concluded = pyqtSignal(bool)  # True when the APP check failed (retry verdict)
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

    def check(self) -> bool:
        """Fire both update checks asynchronously; results arrive via signals.

        Returns True only when a round actually started. Callers that track
        whether the running round is manual must set that flag only on True:
        setting it unconditionally mis-attributes an in-flight automatic round
        when this call was a no-op (the ``_pending`` guard).
        """
        if self._pending:
            return False
        self._app_found = None
        self._app_failed = False
        self._holidays_applied = False
        self._holidays_failed = False
        holidays_url = os.environ.get(HOLIDAYS_URL_ENV, "").strip() or APP_CONFIG.HOLIDAYS_UPDATE_URL
        self._get(APP_CONFIG.APP_RELEASES_API_URL, self._on_app_reply)
        self._get(holidays_url, self._on_holidays_reply)
        return True

    def cancel_download(self):
        if self._download_reply is not None:
            self._download_reply.abort()
            self._download_reply = None

    def is_downloading(self) -> bool:
        """True while an installer download is in flight.

        Lets the controller refuse a second download request BEFORE building its
        progress dialog, so a repeated «دانلود» can never spawn an orphaned,
        frozen dialog next to the live one.
        """
        return self._download_reply is not None

    def _get(self, url: str, handler):
        request = QNetworkRequest(QUrl(url))
        request.setTransferTimeout(NETWORK_TIMEOUT_MS)
        request.setAttribute(
            QNetworkRequest.Attribute.RedirectPolicyAttribute,
            QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy)
        request.setRawHeader(b"User-Agent", f"{APP_CONFIG.APP_NAME}/{APP_CONFIG.APP_VERSION}".encode())
        reply = self._manager.get(request)
        self._pending += 1

        def on_finished():
            # One-shot by construction: a reply's finished() must be handled
            # exactly once, then the reply is released. The old lambda stayed
            # connected forever; combined with timeout aborts this produced
            # re-entries that read an already-closed device ("device not open").
            try:
                reply.finished.disconnect(on_finished)
            except TypeError:
                pass
            try:
                handler(reply)
            finally:
                reply.deleteLater()

        reply.finished.connect(on_finished)

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
        if self._app_found is None:
            if self._app_failed:
                self.check_failed.emit("network")
            elif not self._holidays_applied:
                self.no_updates.emit()
        # Definitive end of this round, success or not: lets the controller
        # stamp "last checked" only for real answers and retry the rest.
        #
        # The verdict tracks the APP check only. The holiday refresh has its own
        # signals and its own log line; letting a failed holiday download mark
        # the whole round failed made the controller retry the APP update every
        # 10 minutes - and since the live remote holidays file currently lacks a
        # version field, every round was "failed", so answering the update popup
        # with "remind later" was followed by a phantom retry that brought the
        # popup straight back (and an offline round later surfaced the offline
        # dialog out of nowhere).
        self.check_concluded.emit(self._app_failed)

    def _on_app_reply(self, reply: QNetworkReply):
        try:
            if reply.error() != QNetworkReply.NetworkError.NoError:
                raise RuntimeError(self._error_text(reply))
            # Aborted replies (timeout / remote close) must never be read:
            # reading a closed TLS transport is exactly what makes Qt print
            # "QIODevice::read (QSslSocket): device not open".
            payload_text = bytes(reply.readAll()).decode('utf-8') if reply.isOpen() else ''
            payload = json.loads(payload_text)
            tag = str(payload.get('tag_name', '')).strip()
            if not is_newer_version(tag, APP_CONFIG.APP_VERSION):
                logger.info(f"App is up to date (latest release: {tag or 'unknown'}).")
                return
            asset = self._find_installer_asset(payload)
            if asset is None:
                logger.warning(f"Release {tag} has no setup installer asset; skipping the app update offer.")
                return
            sha256 = digest_hex(str(asset.get('digest', '')))
            if not is_valid_sha256(sha256):
                # A release without a verifiable digest is never offered: an
                # empty digest used to become '' and skip the download's final
                # sha256 comparison entirely, accepting the installer unverified.
                logger.warning(f"Release {tag} installer has no valid sha256 digest; skipping the app update offer.")
                return
            version = tag.lstrip('vV ')
            self._app_found = (version, asset['browser_download_url'], sha256)
            logger.info(f"App update available: {version}")
        except Exception as e:
            self._app_failed = True
            logger.warning(f"App update check failed: {e}")
        finally:
            self._finish_request()

    @staticmethod
    def _find_installer_asset(payload: dict) -> Optional[dict]:
        candidates = []
        for asset in payload.get('assets', []):
            name = str(asset.get('name', ''))
            if name.startswith(INSTALLER_ASSET_PREFIX) and name.endswith(INSTALLER_ASSET_SUFFIX):
                candidates.append(asset)
        if len(candidates) <= 1:
            return candidates[0] if candidates else None
        # A release can carry more than one matching asset (re-upload, legacy
        # naming). Prefer the one carrying the release's own version tag so a
        # stale sibling asset is never offered by accident.
        tag = str(payload.get('tag_name', '')).lstrip('vV ')
        if tag:
            for asset in candidates:
                if tag in str(asset.get('name', '')):
                    return asset
        return candidates[0]

    def _on_holidays_reply(self, reply: QNetworkReply):
        try:
            if reply.error() != QNetworkReply.NetworkError.NoError:
                raise RuntimeError(self._error_text(reply))
            payload = bytes(reply.readAll()) if reply.isOpen() else b""
            # Validate the payload fully BEFORE comparing versions: an
            # invalid/unversioned remote used to read as version 0 and look
            # exactly like "nothing newer", silently ending the check.
            validated = holiday_io.validate_payload(payload)
            if validated is None:
                self._holidays_failed = True
                return
            _parsed, remote_version = validated
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

    def download_installer(self, url: str, destination, expected_sha256: str = '') -> bool:
        """Stream the installer to `destination` chunk by chunk; emits
        download_progress, then installer_downloaded(path) after sha256
        verification, or download_failed. Returns True when a download was
        started, False when it was rejected (another one already running).

        Data is consumed in readyRead as it arrives and written straight to a
        `<name>.part` file, which is renamed over `destination` only after the
        digest verifies. The old implementation buffered the entire installer
        inside the reply and read it once at finished: a 60 MB download held
        60 MB of RAM, and the finished-time readAll() could land after the
        transport had already closed - the exact "read a closed device"
        pattern behind Qt's "QIODevice::read (QSslSocket): device not open"
        noise when the remote (or a middlebox) drops the connection right at
        the end of the transfer. A crash mid-download leaves at worst a
        harmless stray .part file in Downloads.

        Robustness: exactly one download may run at a time (a second start used
        to overwrite the shared reply/hasher state mid-flight), an unhandled
        OSError inside the readyRead slot used to abort the whole process (Qt
        calls qFatal for slot exceptions), and a stalled connection used to hang
        the dialog forever - an inactivity watchdog now fails the download after
        DOWNLOAD_INACTIVITY_TIMEOUT_MS.

        A rejected second request returns False and emits NOTHING: reusing
        ``download_failed`` for it used to close the live download dialog and
        display "download failed" while the first transfer was still running
        fine in the background.
        """
        if self._download_reply is not None:
            logger.warning("Installer download ignored: another download is already in progress.")
            return False

        request = QNetworkRequest(QUrl(url))
        request.setTransferTimeout(0)
        request.setAttribute(
            QNetworkRequest.Attribute.RedirectPolicyAttribute,
            QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy)
        request.setRawHeader(b"User-Agent", f"{APP_CONFIG.APP_NAME}/{APP_CONFIG.APP_VERSION}".encode())
        destination_path = os.fspath(destination)
        part_path = destination_path + ".part"
        try:
            file_handle = open(part_path, "wb")
        except OSError as e:
            logger.error(f"Installer download failed: cannot write {part_path}: {e}")
            self.download_failed.emit(str(e))
            return False

        self._download_reply = self._manager.get(request)
        reply = self._download_reply
        reply.downloadProgress.connect(self.download_progress.emit)
        hasher = hashlib.sha256()
        # One decision per download, ever: the watchdog, an I/O error and the
        # natural finished all race for the same cleanup/report path.
        settled = [False]
        # Watches for a stalled transfer: transfer timeouts are disabled for
        # downloads (large file over slow links), so nothing else catches a
        # connection that simply stops delivering bytes.
        watchdog = QTimer(reply)
        watchdog.setSingleShot(True)
        watchdog.setInterval(DOWNLOAD_INACTIVITY_TIMEOUT_MS)

        def _discard_part():
            nonlocal file_handle
            if file_handle is not None:
                try:
                    file_handle.close()
                except OSError:
                    pass
                file_handle = None
            try:
                os.remove(part_path)
            except OSError:
                pass

        def _fail(message: str):
            _discard_part()
            logger.error(f"Installer download failed: {message}")
            self.download_failed.emit(message)

        def on_ready_read():
            watchdog.start()  # data flowed: restart the inactivity window
            try:
                # Consume whatever arrived now; readAll() is only ever called
                # on the open transport inside this handler.
                data = bytes(reply.readAll())
                if data:
                    hasher.update(data)
                    file_handle.write(data)
            except OSError as e:
                # Disk full / AV scanning the .part: an exception escaping a Qt
                # slot hard-aborts the process (qFatal), so I/O failures are
                # converted into the normal download_failed flow here.
                if not settled[0]:
                    settled[0] = True
                    watchdog.stop()
                    reply.abort()
                    release_reply()
                    _fail(str(e))

        def release_reply():
            if self._download_reply is reply:
                self._download_reply = None
            try:
                reply.finished.disconnect(on_finished)
            except TypeError:
                pass
            try:
                reply.readyRead.disconnect(on_ready_read)
            except TypeError:
                pass
            reply.deleteLater()

        def on_watchdog_timeout():
            if settled[0]:
                return
            settled[0] = True
            reply.abort()
            release_reply()
            _fail(f"no data for {DOWNLOAD_INACTIVITY_TIMEOUT_MS // 1000}s; connection stalled")

        def on_finished():
            # One-shot by construction: disconnect both handlers, then decide.
            # No readAll() "just in case" here: the transport may already be
            # closed by the time finished runs, and only bytesAvailable() data
            # (a final readyRead racing finished) is still legitimately there.
            nonlocal file_handle
            release_reply()
            watchdog.stop()
            if settled[0]:
                # The watchdog or an I/O error already cleaned up and reported;
                # this late finished belongs to the aborted transport.
                return
            settled[0] = True
            try:
                error = reply.error()
                if error != QNetworkReply.NetworkError.NoError:
                    raise RuntimeError(
                        "canceled" if error == QNetworkReply.NetworkError.OperationCanceledError
                        else self._error_text(reply))
                if reply.bytesAvailable():
                    tail = bytes(reply.readAll())
                    hasher.update(tail)
                    file_handle.write(tail)
                file_handle.close()
                file_handle = None
                if expected_sha256 and hasher.hexdigest() != expected_sha256.lower():
                    raise RuntimeError("Downloaded installer failed the sha256 check; it was not saved.")
                os.replace(part_path, destination_path)
                logger.info(f"Installer saved to {destination_path} (sha256 verified).")
                self.installer_downloaded.emit(destination_path)
            except Exception as e:
                _discard_part()
                logger.error(f"Installer download failed: {e}")
                self.download_failed.emit(str(e))

        watchdog.timeout.connect(on_watchdog_timeout)
        watchdog.start()
        reply.readyRead.connect(on_ready_read)
        reply.finished.connect(on_finished)
        return True
