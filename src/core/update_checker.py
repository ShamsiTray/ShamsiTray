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
import sys
import urllib.parse
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
# config.py. Set before launch; read on every check. Development-only: frozen
# (installed) builds ignore it, so an environment variable can never redirect
# the update traffic of a user's machine.
HOLIDAYS_URL_ENV = "SHAMSITRAY_HOLIDAYS_URL"

# Round-state vocabulary for the round_finished(app, holidays) signal.
# App: "update_found" / "current" / "unavailable" / "failed" / "skipped"
# (holidays-only round). "unavailable" = a newer release EXISTS but cannot be
# offered safely (no installer asset, no valid sha256 digest, untrusted URL) -
# reporting that as "current" would tell a manual check «بروز است» while a
# newer release sits on the server.
# Holidays: "updated" / "current" / "failed".
APP_STATE_UPDATE_FOUND = "update_found"
APP_STATE_CURRENT = "current"
APP_STATE_UNAVAILABLE = "unavailable"
APP_STATE_FAILED = "failed"
APP_STATE_SKIPPED = "skipped"
HOLIDAYS_STATE_UPDATED = "updated"
HOLIDAYS_STATE_CURRENT = "current"
HOLIDAYS_STATE_FAILED = "failed"

# Download offers are pinned to GitHub over TLS: the releases API response is
# trusted for the URL only as far as its host is the project's.
SAFE_DOWNLOAD_SCHEME = "https"
SAFE_DOWNLOAD_HOST_SUFFIXES = ("github.com", "githubusercontent.com")


def _version_base_parts(value: str) -> Optional[Tuple[int, ...]]:
    """Numeric dot parts of a version tag, ignoring any pre-release suffix.

    ``1.4.0`` -> (1, 4, 0), ``v2.0`` -> (2, 0), ``1.5.0-beta`` -> (1, 5, 0),
    ``junk`` -> None. The suffix split is what makes a pre-release tag
    comparable at all: ``int('0-beta')`` raised and the whole tag was silently
    refused, which reads as "up to date" in the log.
    """
    text = str(value).strip().lstrip('vV ')
    # A pre-release suffix follows the first '-': 1.5.0-beta, 2.0-rc1.
    base = text.split('-', 1)[0].strip()
    if not base:
        return None
    try:
        return tuple(int(p) for p in base.split('.'))
    except ValueError:
        return None


def is_prerelease_tag(tag: str) -> bool:
    """True when a release tag carries a pre-release suffix (``1.5.0-beta``).

    The NAME-BASED fallback of ``is_prerelease_payload``, used only when the
    release payload carries no ``prerelease`` field of its own. Policy:
    pre-releases are never offered as updates - the caller skips them with a
    clear log line instead of the old silent refusal, which looked exactly
    like "the app is up to date".
    """
    text = str(tag).strip().lstrip('vV ')
    return '-' in text


def is_prerelease_payload(payload: dict, tag: str) -> bool:
    """Whether the release the payload describes is a pre-release.

    GitHub's own ``prerelease`` flag decides when present - a name-based rule
    alone would blackball a STABLE tag like ``1.4.1-hotfix`` forever (and the
    ``/releases/latest`` endpoint never returns pre-releases or drafts, so the
    flag is authoritative in practice). The tag-suffix check remains only as
    the fallback for payloads without the field (hand-made API responses).
    """
    field = payload.get('prerelease')
    if field is None:
        return is_prerelease_tag(tag)
    return bool(field)


def is_newer_version(latest: str, current: str) -> bool:
    """True when `latest` is strictly newer than `current` (dot-separated integers).

    A pre-release suffix on the tag is ignored for the comparison (the tag's
    base version decides); offering pre-releases is the caller's policy via
    ``is_prerelease_tag``.
    """
    latest_parts = _version_base_parts(latest)
    current_parts = _version_base_parts(current)
    if latest_parts is None or current_parts is None:
        return False
    width = max(len(latest_parts), len(current_parts))
    latest_parts += (0,) * (width - len(latest_parts))
    current_parts += (0,) * (width - len(current_parts))
    return latest_parts > current_parts


def is_safe_download_url(url: str) -> bool:
    """True for https URLs hosted by GitHub.

    ``browser_download_url`` comes from the same API response as the digest, so
    pinning the host adds no tamper resistance against the response itself - it
    guarantees the offer can never point anywhere BUT the project's release
    infrastructure, whatever a compromised or broken API response claims.
    """
    try:
        parsed = urllib.parse.urlparse(str(url))
    except ValueError:
        return False
    if parsed.scheme.lower() != SAFE_DOWNLOAD_SCHEME:
        return False
    host = (parsed.hostname or "").lower()
    return any(host == h or host.endswith("." + h) for h in SAFE_DOWNLOAD_HOST_SUFFIXES)


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
    no_updates = pyqtSignal()  # app current AND holidays current: nothing changed, nothing failed
    check_failed = pyqtSignal(str)
    check_concluded = pyqtSignal(bool)  # True when the APP check failed (retry verdict)
    # One signal carrying the WHOLE round's verdict: (app, holidays) using the
    # APP_STATE_* / HOLIDAYS_STATE_* constants. The controller builds its
    # manual-check message from here, so the two halves of a round can never be
    # reported separately or falsely.
    round_finished = pyqtSignal(str, str)
    download_progress = pyqtSignal(int, int)  # received bytes, total bytes (-1 if unknown)
    installer_downloaded = pyqtSignal(str)  # local file path
    download_failed = pyqtSignal(str)

    def __init__(self, current_data_version: int = 0, parent=None):
        super().__init__(parent)
        self._current_data_version = current_data_version
        self._manager = QNetworkAccessManager(self)
        self._pending = 0
        self._round_kind = "full"  # "full" = app + holidays, "holidays" = quiet refresh
        self._app_found: Optional[Tuple[str, str, str]] = None
        self._app_failed = False
        self._app_unavailable = False
        self._holidays_applied = False
        self._holidays_failed = False
        self._download_reply: Optional[QNetworkReply] = None

    # --- checks ---

    @property
    def round_kind(self) -> str:
        """What the current (or last configured) round asks: "full" or "holidays".

        Read by the controller when a manual check lands on a busy checker, so a
        press during a quiet holidays-only refresh can QUEUE a full check instead
        of marking that refresh manual - a skipped round must never message, so
        marking it would swallow the press. Meaningful only while a round is in
        flight (``check()`` returned False); between rounds it simply carries the
        last round's kind.
        """
        return self._round_kind

    def _holidays_url(self) -> str:
        """Holiday endpoint, honouring the test override only outside a build.

        The env hook is a development aid: a frozen (installed) build ignores
        it, so an environment variable can never redirect the update traffic of
        a user's machine.
        """
        override = ""
        if not getattr(sys, 'frozen', False):
            override = os.environ.get(HOLIDAYS_URL_ENV, "").strip()
        return override or APP_CONFIG.HOLIDAYS_UPDATE_URL

    def check(self) -> bool:
        """Fire both update checks asynchronously; results arrive via signals.

        Returns True only when a round actually started. Callers that track
        whether the running round is manual must set that flag only on True:
        setting it unconditionally mis-attributes an in-flight automatic round
        when this call was a no-op (the ``_pending`` guard).
        """
        if self._pending:
            return False
        self._round_kind = "full"
        self._app_found = None
        self._app_failed = False
        self._app_unavailable = False
        self._holidays_applied = False
        self._holidays_failed = False
        self._get(APP_CONFIG.APP_RELEASES_API_URL, self._on_app_reply)
        self._get(self._holidays_url(), self._on_holidays_reply)
        return True

    def check_holidays(self) -> bool:
        """Quiet holidays-only refresh: no app check, no app verdict.

        A failed holiday fetch must not wait 24h for the next full round, but
        retrying the FULL round would re-pop the app popup after "remind later"
        and stamp "last checked" on a round that never asked the app question.
        This refetches just the holiday file; it emits holidays_updated on
        success (the normal refresh path) and round_finished("skipped", ...) -
        never check_concluded, so the app verdict and its stamping stay
        untouched. Returns True when started.
        """
        if self._pending:
            return False
        self._round_kind = "holidays"
        self._holidays_applied = False
        self._holidays_failed = False
        self._get(self._holidays_url(), self._on_holidays_reply)
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
            # exactly once, then the reply is released. A lambda left connected
            # would re-enter after a timeout abort and read an already-closed
            # device ("device not open").
            try:
                reply.finished.disconnect(on_finished)
            except TypeError:
                pass
            try:
                handler(reply)
            except Exception:
                # The handler's own finally-block emits Qt signals (the conclude
                # path emits several); an exception raised by a slot could
                # otherwise escape back into Qt's C++ dispatch, which PyQt
                # answers with qFatal. Contain it: the pending bookkeeping
                # already ran inside the handler.
                logger.exception("Update reply handler raised; containing the error.")
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
        holidays_state = (HOLIDAYS_STATE_UPDATED if self._holidays_applied
                          else HOLIDAYS_STATE_FAILED if self._holidays_failed
                          else HOLIDAYS_STATE_CURRENT)
        if self._round_kind == "holidays":
            # Quiet refresh: only the holiday outcome exists to report.
            if self._holidays_applied:
                self.holidays_updated.emit()
            self.round_finished.emit(APP_STATE_SKIPPED, holidays_state)
            return
        app_state = (APP_STATE_UPDATE_FOUND if self._app_found
                     else APP_STATE_FAILED if self._app_failed
                     else APP_STATE_UNAVAILABLE if self._app_unavailable
                     else APP_STATE_CURRENT)
        if self._app_found:
            self.app_update_available.emit(*self._app_found)
        if self._holidays_applied:
            self.holidays_updated.emit()
        if self._app_found is None:
            if self._app_failed:
                self.check_failed.emit("network")
            elif self._app_unavailable:
                # The skip paths already logged WHY the release cannot be
                # offered; it must not read as "no updates".
                pass
            elif holidays_state == HOLIDAYS_STATE_CURRENT:
                # "No updates" must mean the holidays are CURRENT, not merely
                # "didn't change": a failed holiday fetch used to be announced
                # as "app and holiday file are up to date".
                self.no_updates.emit()
        # One end-of-round signal carrying the WHOLE verdict, so the controller
        # can message a manual check without reporting the two halves separately
        # (or falsely).
        self.round_finished.emit(app_state, holidays_state)
        # Definitive end of this round, success or not: lets the controller
        # stamp "last checked" only for real answers and retry the rest.
        #
        # The verdict tracks the APP check only. The holiday refresh has its own
        # state and log line, and a failed holiday download must not mark the
        # whole round failed - that would retry the app update every 10 minutes
        # and bring the popup back after "remind later". An UNAVAILABLE round
        # counts as failed here: no clean stamp, so the release is re-checked
        # instead of waiting out the 24h gate.
        self.check_concluded.emit(self._app_failed or self._app_unavailable)

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
            if is_prerelease_payload(payload, tag):
                # Policy: pre-releases are never offered. The old parser choked
                # on the suffix and logged the silent refusal as "App is up to
                # date (latest release: 1.5.0-beta)".
                logger.info(f"Ignoring pre-release {tag!r}; only stable releases are offered.")
                return
            if not is_newer_version(tag, APP_CONFIG.APP_VERSION):
                logger.info(f"App is up to date (latest release: {tag or 'unknown'}).")
                return
            asset = self._find_installer_asset(payload)
            if asset is None:
                # A newer release exists but cannot be offered: the round must
                # report "unavailable", not "current".
                self._app_unavailable = True
                logger.warning(f"Release {tag} has no setup installer asset; the app update offer is unavailable.")
                return
            sha256 = digest_hex(str(asset.get('digest', '')))
            if not is_valid_sha256(sha256):
                # A release without a verifiable digest is never offered: an
                # empty digest would compare equal and skip the download's final
                # sha256 check, accepting the installer unverified.
                self._app_unavailable = True
                logger.warning(f"Release {tag} installer has no valid sha256 digest; the app update offer is unavailable.")
                return
            download_url = str(asset['browser_download_url'])
            if not is_safe_download_url(download_url):
                # The offer is pinned to GitHub over https. The digest protects
                # against corruption, not a tampered response - an unexpected
                # host/scheme is refused outright.
                self._app_unavailable = True
                logger.warning(f"Release {tag} installer URL is not a trusted GitHub https URL; the app update offer is unavailable.")
                return
            version = tag.lstrip('vV ')
            self._app_found = (version, download_url, sha256)
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
            # Validate the payload fully BEFORE comparing versions: an invalid
            # or unversioned remote reads as version 0 and looks exactly like
            # "nothing newer", which would silently end the check.
            validated = holiday_io.validate_payload(payload)
            if validated is None:
                self._holidays_failed = True
                return
            _parsed, remote_version = validated
            if remote_version <= self._current_data_version:
                logger.info(f"Holiday data is up to date (remote version {remote_version}).")
                return
            # The payload was already fully validated above: hand that result
            # to replace_store so it is parsed exactly once.
            if not holiday_io.replace_store(payload, validated=validated):
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
            try:
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
            except Exception:
                # Same qFatal rule as the finished handler: whatever a connected
                # slot raised, it must not escape back into Qt's dispatch.
                logger.exception("Installer download read handler raised; containing the error.")

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
            try:
                reply.abort()
                release_reply()
                _fail(f"no data for {DOWNLOAD_INACTIVITY_TIMEOUT_MS // 1000}s; connection stalled")
            except Exception:
                # _fail emits a Qt signal: a raising slot must not escape into Qt.
                logger.exception("Installer download watchdog handler raised; containing the error.")

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
            except Exception:
                # installer_downloaded/download_failed land in application slots;
                # an exception raised there must never escape into Qt (qFatal).
                logger.exception("Installer download completion handler raised; containing the error.")

        watchdog.timeout.connect(on_watchdog_timeout)
        watchdog.start()
        reply.readyRead.connect(on_ready_read)
        reply.finished.connect(on_finished)
        return True
