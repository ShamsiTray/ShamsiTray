"""Tests for core.update_checker: pure helpers plus the full networking
behaviour against a local HTTP server (check round-trips, streaming installer
download, sha256 verification, cancel, truncated transfers, error paths).
"""
import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from PyQt6.QtNetwork import QNetworkReply

from config import APP_CONFIG
from core.update_checker import (HOLIDAYS_URL_ENV, NETWORK_TIMEOUT_MS,
                                 UpdateChecker, digest_hex, is_newer_version,
                                 should_notify)

# --- pure helpers (kept from the original suite) ------------------------------


def test_is_newer_version_basic():
    assert is_newer_version('1.4.0', '1.3.1')
    assert is_newer_version('v1.4.0', '1.3.1')
    assert is_newer_version('1.10.0', '1.9.9')
    assert is_newer_version('2.0', '1.9.9')


def test_is_newer_version_not_newer():
    assert not is_newer_version('1.3.1', '1.3.1')
    assert not is_newer_version('1.3.0', '1.3.1')
    assert not is_newer_version('1.3', '1.3.1')  # zero-padded compare, not newer
    assert not is_newer_version('0.9.9', '1.0.0')


def test_is_newer_version_garbage_is_false():
    assert not is_newer_version('', '1.0.0')
    assert not is_newer_version('junk', '1.0.0')
    assert not is_newer_version('1.x.y', '1.0.0')
    assert not is_newer_version('1.4.0', 'oops')


def test_digest_hex_parses_github_format():
    assert digest_hex('sha256:ABCDEF') == 'abcdef'
    assert digest_hex('sha256:9966b08c') == '9966b08c'


def test_digest_hex_rejects_other_algorithms():
    assert digest_hex('md5:abc') is None
    assert digest_hex('') is None
    assert digest_hex('sha256') is None


def test_should_notify_respects_ignored_version():
    assert should_notify('1.4.0', None)
    assert should_notify('1.4.0', '1.3.9')
    assert not should_notify('1.4.0', '1.4.0')


def test_network_timeout_is_slow_route_safe():
    assert NETWORK_TIMEOUT_MS == 20000  # 15s timed out on slow GitHub routes


# --- local HTTP server harness -------------------------------------------------


class _RouteHandler(BaseHTTPRequestHandler):
    routes: dict = {}      # class attr replaced per server instance
    hits: dict = {}        # path -> request count
    slow_gate = None       # optional threading.Event gate before answering

    def do_GET(self):
        # NOTE: self.routes/self.hits resolve to the per-fixture subclass
        # dicts; referencing _RouteHandler here would share state across tests.
        self.hits[self.path] = self.hits.get(self.path, 0) + 1
        route = self.routes.get(self.path)
        if route is None:
            self.send_error(404)
            return
        status, headers, body = route
        if self.slow_gate is not None:
            # Block until released (capped: never wedge the suite).
            self.slow_gate.wait(timeout=5)
        self.send_response(status)
        for key, value in headers.items():
            self.send_header(key, value)
        if "Content-Length" not in headers:
            self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture
def http_server():
    handler = type("Handler", (_RouteHandler,), {"routes": {}, "hits": {}, "slow_gate": None})
    # The routes dict must be per-instance; class attrs above are templates.
    handler.routes = {}
    handler.hits = {}
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield handler, f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def _release_payload(tag="v99.0.0", asset=True):
    payload = {"tag_name": tag}
    if asset:
        payload["assets"] = [{
            "name": f"ShamsiTraySetup-{tag.lstrip('v')}.exe",
            "browser_download_url": "http://example.invalid/installer.exe",
            "digest": "sha256:" + "ab" * 32,
        }]
    return json.dumps(payload).encode()


def _holidays_payload(version=990001):
    return json.dumps({
        "version": version,
        "holidays": {"1405": {"01-01": ["نوروز"], "03-15": ["جشن"]}},
    }).encode()


@pytest.fixture
def checker(qtbot):
    return UpdateChecker(current_data_version=0)


def _collect(checker):
    got = {"app": [], "holidays": 0, "none": 0, "failed": [], "concluded": []}
    checker.app_update_available.connect(lambda v, u, s: got["app"].append((v, u, s)))
    checker.holidays_updated.connect(lambda: got.__setitem__("holidays", got["holidays"] + 1))
    checker.no_updates.connect(lambda: got.__setitem__("none", got["none"] + 1))
    checker.check_failed.connect(lambda r: got["failed"].append(r))
    checker.check_concluded.connect(lambda f: got["concluded"].append(f))
    return got


# --- check() round-trips --------------------------------------------------------


def test_check_reports_app_update_and_holiday_update(http_server, checker, qtbot, monkeypatch, user_data):
    handler, base = http_server
    handler.routes["/api"] = (200, {"Content-Type": "application/json"}, _release_payload())
    handler.routes["/holidays.json"] = (200, {"Content-Type": "application/json"}, _holidays_payload())
    monkeypatch.setattr(APP_CONFIG, "APP_RELEASES_API_URL", f"{base}/api")
    monkeypatch.setenv(HOLIDAYS_URL_ENV, f"{base}/holidays.json")

    got = _collect(checker)
    checker.check()
    qtbot.waitUntil(lambda: bool(got["concluded"]), timeout=10000)

    assert len(got["app"]) == 1
    version, url, sha = got["app"][0]
    assert version == "99.0.0"
    assert url == "http://example.invalid/installer.exe"
    assert sha == "ab" * 32
    assert got["holidays"] == 1
    assert got["none"] == 0
    assert got["failed"] == []
    assert got["concluded"] == [False]  # success conclusion for retry logic
    # The store was atomically replaced with the remote data.
    assert APP_CONFIG.HOLIDAYS_STORE_PATH.exists()


def test_check_uses_github_url_without_env_override(http_server, checker, qtbot, monkeypatch, user_data):
    handler, base = http_server
    handler.routes["/api"] = (200, {}, _release_payload("1.0.0"))
    handler.routes[APP_CONFIG.HOLIDAYS_UPDATE_URL] = (200, {}, _holidays_payload(0))
    monkeypatch.setattr(APP_CONFIG, "APP_RELEASES_API_URL", f"{base}/api")
    monkeypatch.delenv(HOLIDAYS_URL_ENV, raising=False)
    # The default holidays URL points at raw.githubusercontent.com; point the
    # checker at it via a stubbed config URL instead of real network.
    monkeypatch.setattr(APP_CONFIG, "HOLIDAYS_UPDATE_URL", f"{base}/gh-holidays")
    handler.routes["/gh-holidays"] = (200, {}, _holidays_payload(0))

    got = _collect(checker)
    checker.check()
    qtbot.waitUntil(lambda: bool(got["concluded"]), timeout=10000)
    assert handler.hits["/gh-holidays"] == 1


def test_check_is_noop_while_a_round_is_pending(http_server, checker, qtbot, monkeypatch, user_data):
    handler, base = http_server
    handler.routes["/api"] = (200, {}, _release_payload("1.0.0"))
    handler.routes["/holidays.json"] = (200, {}, _holidays_payload(0))
    monkeypatch.setattr(APP_CONFIG, "APP_RELEASES_API_URL", f"{base}/api")
    monkeypatch.setenv(HOLIDAYS_URL_ENV, f"{base}/holidays.json")

    checker.check()
    assert checker._pending == 2
    checker.check()  # second call must be ignored
    assert checker._pending == 2
    qtbot.waitUntil(lambda: checker._pending == 0, timeout=10000)


def test_check_up_to_date_emits_no_updates(http_server, checker, qtbot, monkeypatch, user_data):
    handler, base = http_server
    handler.routes["/api"] = (200, {}, _release_payload("1.0.0"))
    handler.routes["/holidays.json"] = (200, {}, _holidays_payload(0))  # <= current (0)
    monkeypatch.setattr(APP_CONFIG, "APP_RELEASES_API_URL", f"{base}/api")
    monkeypatch.setenv(HOLIDAYS_URL_ENV, f"{base}/holidays.json")

    got = _collect(checker)
    checker.check()
    qtbot.waitUntil(lambda: bool(got["concluded"]), timeout=10000)
    assert got["none"] == 1
    assert got["app"] == [] and got["holidays"] == 0
    assert got["concluded"] == [False]


def test_check_holiday_only_update_still_concludes_clean(http_server, checker, qtbot, monkeypatch, user_data):
    handler, base = http_server
    handler.routes["/api"] = (200, {}, _release_payload("1.0.0"))
    handler.routes["/holidays.json"] = (200, {}, _holidays_payload(5))
    monkeypatch.setattr(APP_CONFIG, "APP_RELEASES_API_URL", f"{base}/api")
    monkeypatch.setenv(HOLIDAYS_URL_ENV, f"{base}/holidays.json")

    got = _collect(checker)
    checker.check()
    qtbot.waitUntil(lambda: bool(got["concluded"]), timeout=10000)
    assert got["holidays"] == 1
    assert got["none"] == 0  # holiday data WAS applied: no "no updates" signal
    assert got["concluded"] == [False]


def test_check_connection_refused_reports_failure(checker, qtbot, monkeypatch, user_data):
    """Both requests hit a dead port: check_failed + failed conclusion."""
    monkeypatch.setattr(APP_CONFIG, "APP_RELEASES_API_URL", "http://127.0.0.1:9/api")
    monkeypatch.setenv(HOLIDAYS_URL_ENV, "http://127.0.0.1:9/holidays.json")

    got = _collect(checker)
    checker.check()
    qtbot.waitUntil(lambda: bool(got["concluded"]), timeout=10000)
    assert got["failed"] == ["network"]
    assert got["concluded"] == [True]
    assert got["none"] == 0


def test_check_bad_json_counts_as_failed(http_server, checker, qtbot, monkeypatch, user_data):
    handler, base = http_server
    handler.routes["/api"] = (200, {}, b"this is not json{")
    handler.routes["/holidays.json"] = (200, {}, b"nor is this]")
    monkeypatch.setattr(APP_CONFIG, "APP_RELEASES_API_URL", f"{base}/api")
    monkeypatch.setenv(HOLIDAYS_URL_ENV, f"{base}/holidays.json")

    got = _collect(checker)
    checker.check()
    qtbot.waitUntil(lambda: bool(got["concluded"]), timeout=10000)
    assert got["failed"] == ["network"]
    assert got["concluded"] == [True]


def test_check_release_without_installer_asset_skips_offer(http_server, checker, qtbot, monkeypatch, user_data):
    handler, base = http_server
    handler.routes["/api"] = (200, {}, _release_payload("99.0.0", asset=False))
    handler.routes["/holidays.json"] = (200, {}, _holidays_payload(0))
    monkeypatch.setattr(APP_CONFIG, "APP_RELEASES_API_URL", f"{base}/api")
    monkeypatch.setenv(HOLIDAYS_URL_ENV, f"{base}/holidays.json")

    got = _collect(checker)
    checker.check()
    qtbot.waitUntil(lambda: bool(got["concluded"]), timeout=10000)
    assert got["app"] == []            # no installer -> no offer
    assert got["none"] == 1            # but the round was clean
    assert got["concluded"] == [False]


def test_find_installer_asset_matching_rules():
    payload = {"assets": [
        {"name": "ShamsiTray-1.4.0.zip"},
        {"name": "ShamsiTraySetup-1.4.0.exe", "browser_download_url": "u"},
        {"name": "OtherSetup-1.4.0.exe"},
    ]}
    assert UpdateChecker._find_installer_asset(payload)["name"] == "ShamsiTraySetup-1.4.0.exe"
    assert UpdateChecker._find_installer_asset({"assets": []}) is None
    assert UpdateChecker._find_installer_asset({}) is None


# --- installer download ----------------------------------------------------------


def test_download_installer_streams_and_verifies(http_server, checker, qtbot, tmp_path):
    handler, base = http_server
    payload = b"A" * 70000 + b"B" * 30000  # 100 KB: several readyRead chunks
    handler.routes["/installer.exe"] = (200, {}, payload)
    destination = tmp_path / "ShamsiTraySetup-99.0.0.exe"

    progress, failed = [], []
    checker.download_progress.connect(lambda r, t: progress.append((r, t)))
    checker.download_failed.connect(lambda reason: failed.append(reason))

    with qtbot.waitSignal(checker.installer_downloaded, timeout=15000) as blocker:
        checker.download_installer(f"{base}/installer.exe", destination,
                                   hashlib.sha256(payload).hexdigest())

    assert blocker.args == [str(destination)]
    assert destination.read_bytes() == payload          # byte-exact
    assert not destination.with_name(destination.name + ".part").exists()
    assert failed == []
    assert progress and progress[-1][0] > 0             # progress flowed


def test_download_progress_reports_totals(http_server, checker, qtbot, tmp_path):
    handler, base = http_server
    payload = b"x" * 5000
    handler.routes["/installer.exe"] = (200, {}, payload)
    destination = tmp_path / "out.exe"

    progress = []
    checker.download_progress.connect(lambda r, t: progress.append((r, t)))
    with qtbot.waitSignal(checker.installer_downloaded, timeout=15000):
        checker.download_installer(f"{base}/installer.exe", destination, "")

    received, total = progress[-1]
    assert received == len(payload)
    assert total == len(payload)  # Content-Length known


def test_download_sha_mismatch_discards_file(http_server, checker, qtbot, tmp_path):
    handler, base = http_server
    payload = b"real installer bytes"
    handler.routes["/installer.exe"] = (200, {}, payload)
    destination = tmp_path / "ShamsiTraySetup-99.0.0.exe"

    failed, downloaded = [], []
    checker.download_failed.connect(lambda reason: failed.append(reason))
    checker.installer_downloaded.connect(lambda path: downloaded.append(path))

    checker.download_installer(f"{base}/installer.exe", destination, "00" * 32)
    qtbot.waitUntil(lambda: bool(failed), timeout=15000)

    assert failed == ["Downloaded installer failed the sha256 check; it was not saved."]
    assert downloaded == []
    assert not destination.exists()                     # never saved
    assert not destination.with_name(destination.name + ".part").exists()


def test_download_truncated_body_fails_and_cleans_part(http_server, checker, qtbot, tmp_path):
    """Server declares more Content-Length than it sends, then closes."""
    handler, base = http_server
    payload = b"partial"
    handler.routes["/installer.exe"] = (200, {"Content-Length": str(len(payload) + 1000)}, payload)
    destination = tmp_path / "ShamsiTraySetup-99.0.0.exe"

    failed = []
    checker.download_failed.connect(lambda reason: failed.append(reason))
    checker.download_installer(f"{base}/installer.exe", destination,
                               hashlib.sha256(payload).hexdigest())
    qtbot.waitUntil(lambda: bool(failed), timeout=15000)

    assert failed and "canceled" not in failed[0]
    assert not destination.exists()
    assert not destination.with_name(destination.name + ".part").exists()


def test_cancel_download_aborts_and_cleans_up(http_server, checker, qtbot, tmp_path):
    """A cancel while the server is stalled yields download_failed('canceled'),
    no destination file and no stray .part."""
    handler, base = http_server
    gate = threading.Event()
    release = threading.Event()
    handler.slow_gate = gate

    def hold():
        gate.set()      # announce the request arrived
        release.wait(timeout=5)

    # Replace the generic gate behaviour for this route via the gate event:
    # the handler waits on gate (set by us only after the request arrives? no)
    # - simplest: wait until the request arrives, then keep holding.
    class HoldOnce(_RouteHandler):
        def do_GET(self):
            gate.set()
            release.wait(timeout=5)
            self.send_response(200)
            self.send_header("Content-Length", "10")
            self.end_headers()
            self.wfile.write(b"0123456789")

    server2 = ThreadingHTTPServer(("127.0.0.1", 0), HoldOnce)
    thread2 = threading.Thread(target=server2.serve_forever, daemon=True)
    thread2.start()
    try:
        destination = tmp_path / "ShamsiTraySetup-99.0.0.exe"
        failed = []
        checker.download_failed.connect(lambda reason: failed.append(reason))

        checker.download_installer(f"http://127.0.0.1:{server2.server_address[1]}/exe",
                                   destination, "")
        assert gate.wait(timeout=5), "server never saw the request"
        checker.cancel_download()
        qtbot.waitUntil(lambda: bool(failed), timeout=10000)
        assert failed == ["canceled"]
        assert not destination.exists()
        assert not destination.with_name(destination.name + ".part").exists()
    finally:
        release.set()
        server2.shutdown()
        server2.server_close()


def test_cancel_download_without_active_reply_is_noop(checker):
    checker.cancel_download()  # must not raise
    assert checker._download_reply is None


def test_unwritable_destination_fails_fast(checker, tmp_path):
    blocked = tmp_path / "blocker"
    blocked.write_text("i am a file")
    destination = blocked / "sub" / "installer.exe"  # parent is a file
    failed = []
    checker.download_failed.connect(lambda reason: failed.append(reason))
    checker.download_installer("http://127.0.0.1:9/installer.exe", destination, "")
    assert failed  # emitted synchronously, no network attempt


def test_error_text_includes_code_and_string(checker, qtbot):
    """_error_text formats 'Name (value): string' from a reply error."""
    class FakeError:
        name = "ConnectionRefusedError"
        value = 1

    class FakeReply:
        def error(self):
            return FakeError()

        errorString = lambda self: "connection refused"  # noqa: E731

    text = UpdateChecker._error_text(FakeReply())
    assert text == "ConnectionRefusedError (1): connection refused"


def test_operation_canceled_error_name_exists():
    # The cancel path maps this exact enum; a rename would silently change
    # the download_failed payload the controller matches on.
    assert QNetworkReply.NetworkError.OperationCanceledError is not None
