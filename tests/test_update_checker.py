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
from core.update_checker import (APP_STATE_CURRENT, APP_STATE_FAILED,
                                 APP_STATE_SKIPPED, APP_STATE_UNAVAILABLE,
                                 APP_STATE_UPDATE_FOUND,
                                 HOLIDAYS_STATE_CURRENT, HOLIDAYS_STATE_FAILED,
                                 HOLIDAYS_STATE_UPDATED, HOLIDAYS_URL_ENV,
                                 NETWORK_TIMEOUT_MS, UpdateChecker, digest_hex,
                                 is_newer_version, is_prerelease_tag,
                                 is_safe_download_url, should_notify)

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


def test_is_newer_version_compares_prerelease_suffix_by_base():
    """A suffixed tag must be comparable, not silently refused - int('0-beta')
    used to raise, and the whole tag then read as "up to date"."""
    assert is_newer_version('1.5.0-beta', '1.4.0')
    assert not is_newer_version('1.4.0-rc1', '1.4.0')   # same base, not newer
    assert is_newer_version('2.0-beta', '1.9.9')        # the numeric base decides


def test_is_prerelease_tag_rules():
    assert is_prerelease_tag('1.5.0-beta')
    assert is_prerelease_tag('v2.0-rc1')
    assert not is_prerelease_tag('1.5.0')
    assert not is_prerelease_tag('v1.4.0')


def test_is_prerelease_payload_prefers_the_github_flag():
    """The payload's own ``prerelease`` flag decides when present: a name-based
    rule alone would blackball a STABLE tag like ``1.4.1-hotfix`` forever. The
    suffix check stays only as the fallback for payloads without the field."""
    from core.update_checker import is_prerelease_payload
    assert not is_prerelease_payload({"prerelease": False}, "1.4.1-hotfix")
    assert is_prerelease_payload({"prerelease": True}, "1.5.0")
    assert not is_prerelease_payload({"prerelease": False}, "2.0.0")
    assert is_prerelease_payload({}, "1.5.0-beta")
    assert not is_prerelease_payload({}, "1.5.0")
    assert is_prerelease_payload({"prerelease": None}, "1.5.0-beta")


def test_is_safe_download_url_pins_github_https():
    assert is_safe_download_url(
        'https://github.com/ShamsiTray/ShamsiTray/releases/download/v1.5.0/ShamsiTraySetup-1.5.0.exe')
    assert is_safe_download_url('https://objects.githubusercontent.com/x/ShamsiTraySetup.exe')
    assert not is_safe_download_url('http://github.com/ShamsiTray/ShamsiTray/releases/download/x.exe')
    assert not is_safe_download_url('https://example.invalid/installer.exe')
    assert not is_safe_download_url('https://evil-github.com/installer.exe')  # suffix is dot-anchored
    assert not is_safe_download_url('')
    assert not is_safe_download_url('not a url at all')


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


def _release_payload(tag="v99.0.0", asset=True, prerelease=None):
    payload = {"tag_name": tag}
    if asset:
        payload["assets"] = [{
            "name": f"ShamsiTraySetup-{tag.lstrip('v')}.exe",
            # Offers from other hosts/schemes are refused at the offer boundary,
            # so the stub payload has to carry a pinned-safe URL.
            "browser_download_url": (
                "https://github.com/ShamsiTray/ShamsiTray/releases/download/"
                f"{tag}/ShamsiTraySetup-{tag.lstrip('v')}.exe"),
            "digest": "sha256:" + "ab" * 32,
        }]
    if prerelease is not None:
        payload["prerelease"] = prerelease
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
    got = {"app": [], "holidays": 0, "none": 0, "failed": [], "concluded": [],
           "rounds": []}
    checker.app_update_available.connect(lambda v, u, s: got["app"].append((v, u, s)))
    checker.holidays_updated.connect(lambda: got.__setitem__("holidays", got["holidays"] + 1))
    checker.no_updates.connect(lambda: got.__setitem__("none", got["none"] + 1))
    checker.check_failed.connect(lambda r: got["failed"].append(r))
    checker.check_concluded.connect(lambda f: got["concluded"].append(f))
    checker.round_finished.connect(lambda a, h: got["rounds"].append((a, h)))
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
    assert url == ("https://github.com/ShamsiTray/ShamsiTray/releases/download/"
                   "v99.0.0/ShamsiTraySetup-99.0.0.exe")
    assert sha == "ab" * 32
    assert got["holidays"] == 1
    assert got["none"] == 0
    assert got["failed"] == []
    assert got["concluded"] == [False]  # success conclusion for retry logic
    assert got["rounds"] == [(APP_STATE_UPDATE_FOUND, HOLIDAYS_STATE_UPDATED)]
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
    # Valid remote data, genuinely older than the local store (HOL-2: a
    # version-0/unversioned payload is now treated as invalid, not "up to date").
    handler.routes["/holidays.json"] = (200, {}, _holidays_payload(990001))
    monkeypatch.setattr(APP_CONFIG, "APP_RELEASES_API_URL", f"{base}/api")
    monkeypatch.setenv(HOLIDAYS_URL_ENV, f"{base}/holidays.json")
    stale_checker = UpdateChecker(current_data_version=990002)

    got = _collect(stale_checker)
    stale_checker.check()
    qtbot.waitUntil(lambda: bool(got["concluded"]), timeout=10000)
    assert got["none"] == 1
    assert got["app"] == [] and got["holidays"] == 0
    assert got["concluded"] == [False]
    assert got["rounds"] == [(APP_STATE_CURRENT, HOLIDAYS_STATE_CURRENT)]


def test_check_unversioned_remote_is_refused_not_applied(http_server, checker, qtbot, monkeypatch, user_data):
    """HOL-2: the live GitHub file has no version field; it must be refused
    (never silently applied as version 0), logged, and - since the holiday
    refresh has its own lifecycle - it must NOT fail the round for the app
    update's retry machinery. With the remote file unversioned, every round
    used to conclude 'failed' and the auto-retry kept re-offering the update
    popup every 10 minutes no matter what the user answered."""
    handler, base = http_server
    handler.routes["/api"] = (200, {}, _release_payload("1.0.0"))
    handler.routes["/holidays.json"] = (200, {}, json.dumps({"holidays": {"1403": {"01-01": ["N"]}}}).encode())
    monkeypatch.setattr(APP_CONFIG, "APP_RELEASES_API_URL", f"{base}/api")
    monkeypatch.setenv(HOLIDAYS_URL_ENV, f"{base}/holidays.json")

    got = _collect(checker)
    checker.check()
    qtbot.waitUntil(lambda: bool(got["concluded"]), timeout=10000)
    assert got["holidays"] == 0                          # never applied
    assert not APP_CONFIG.HOLIDAYS_STORE_PATH.exists()   # store untouched
    # App check was clean (up to date) and stays the round's verdict:
    assert got["failed"] == []                           # no check_failed
    # With the holiday fetch FAILED, "app and holiday file are up to date" must
    # NOT fire - it used to, which told the user everything was current while
    # the holiday half had failed.
    assert got["none"] == 0
    assert got["concluded"] == [False]                   # no 10-min retry loop
    assert got["rounds"] == [(APP_STATE_CURRENT, HOLIDAYS_STATE_FAILED)]


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


def test_check_release_without_installer_asset_is_unavailable(http_server, checker, qtbot, monkeypatch, user_data):
    """A newer release with no installer asset is UNAVAILABLE, not "current": a
    manual check must not say «بروز است» while a newer release sits on the
    server, and no clean "last checked" is stamped."""
    handler, base = http_server
    handler.routes["/api"] = (200, {}, _release_payload("99.0.0", asset=False))
    handler.routes["/holidays.json"] = (200, {}, _holidays_payload(990001))
    monkeypatch.setattr(APP_CONFIG, "APP_RELEASES_API_URL", f"{base}/api")
    monkeypatch.setenv(HOLIDAYS_URL_ENV, f"{base}/holidays.json")
    stale_checker = UpdateChecker(current_data_version=990002)

    got = _collect(stale_checker)
    stale_checker.check()
    qtbot.waitUntil(lambda: bool(got["concluded"]), timeout=10000)
    assert got["app"] == []            # no installer -> no offer
    assert got["none"] == 0            # and NOT a clean "no updates" answer
    assert got["concluded"] == [True]  # no clean stamp: re-checked later
    assert got["rounds"] == [(APP_STATE_UNAVAILABLE, HOLIDAYS_STATE_CURRENT)]


def test_check_release_without_valid_digest_skips_offer(http_server, checker, qtbot, monkeypatch, user_data):
    """UPD-1: a missing or malformed digest must never be offered for download.

    The empty digest used to slip through as '' and skip the download-time
    sha256 comparison entirely - an unverified installer was accepted.
    """
    handler, base = http_server
    for digest in (None, "", "sha256:short", "sha256:" + "zz" * 32, "md5:" + "ab" * 32):
        payload = _release_payload()
        obj = json.loads(payload)
        if digest is None:
            del obj["assets"][0]["digest"]
        else:
            obj["assets"][0]["digest"] = digest
        handler.routes["/api"] = (200, {}, json.dumps(obj).encode())
        handler.routes["/holidays.json"] = (200, {}, _holidays_payload(990001))
        monkeypatch.setattr(APP_CONFIG, "APP_RELEASES_API_URL", f"{base}/api")
        monkeypatch.setenv(HOLIDAYS_URL_ENV, f"{base}/holidays.json")

        got = _collect(checker)
        checker.check()
        qtbot.waitUntil(lambda: bool(got["concluded"]), timeout=10000)
        assert got["app"] == [], f"digest {digest!r} must not be offered"
        # The offer is unavailable, not a clean "up to date" (the holidays half
        # of the tuple varies: the first loop iteration applies the remote file,
        # later ones see it as current).
        assert got["rounds"][0][0] == APP_STATE_UNAVAILABLE
        assert got["concluded"] == [True]


def test_is_valid_sha256_rules():
    from core.update_checker import is_valid_sha256
    assert is_valid_sha256("ab" * 32)
    assert is_valid_sha256("AB" * 32)
    assert not is_valid_sha256(None)
    assert not is_valid_sha256("")
    assert not is_valid_sha256("ab" * 31)   # 63 chars
    assert not is_valid_sha256("ab" * 33)   # 65 chars
    assert not is_valid_sha256("zz" * 32)   # non-hex
    assert not is_valid_sha256("sha256:" + "ab" * 32)  # raw field, not the digest


def test_find_installer_asset_matching_rules():
    payload = {"assets": [
        {"name": "ShamsiTray-1.4.0.zip"},
        {"name": "ShamsiTraySetup-1.4.0.exe", "browser_download_url": "u"},
        {"name": "OtherSetup-1.4.0.exe"},
    ]}
    assert UpdateChecker._find_installer_asset(payload)["name"] == "ShamsiTraySetup-1.4.0.exe"
    assert UpdateChecker._find_installer_asset({"assets": []}) is None
    assert UpdateChecker._find_installer_asset({}) is None


def test_find_installer_asset_prefers_tag_version():
    """UPD-2: with duplicate installer assets, the release's own version wins."""
    payload = {"tag_name": "v99.0.0", "assets": [
        {"name": "ShamsiTraySetup-98.0.0.exe", "browser_download_url": "stale"},
        {"name": "ShamsiTraySetup-99.0.0.exe", "browser_download_url": "fresh"},
    ]}
    assert UpdateChecker._find_installer_asset(payload)["name"] == "ShamsiTraySetup-99.0.0.exe"
    # No tag match (or no tag at all) falls back to the first candidate.
    no_tag = {"assets": payload["assets"]}
    assert UpdateChecker._find_installer_asset(no_tag)["name"] == "ShamsiTraySetup-98.0.0.exe"
    other = {"tag_name": "v100.0.0", "assets": payload["assets"]}
    assert UpdateChecker._find_installer_asset(other)["name"] == "ShamsiTraySetup-98.0.0.exe"


def test_check_returns_true_only_when_a_round_starts(checker, monkeypatch):
    """UPD-6: callers must be able to tell a no-op check from a real one.

    The request helper is stubbed: a bare check() here fired real rounds at the
    app's GitHub endpoints - the autouse no-stray-network fixture only drops the
    *scheduled* auto check, not a direct check() - and never waited for the
    replies. The pending-round counter the second assertion rests on is the
    stub's own increment, exactly as ``_get`` raises it.
    """
    urls = []

    def fake_get(url, handler):
        urls.append(url)
        checker._pending += 1

    monkeypatch.setattr(checker, "_get", fake_get)

    assert checker.check() is True
    assert checker.check() is False  # pending round: no-op
    assert len(urls) == 2  # app + holidays; the no-op added none


def test_file_sha256_matches_hashlib(tmp_path):
    from core.update_checker import file_sha256
    p = tmp_path / "blob.bin"
    p.write_bytes(b"some installer bytes")
    assert file_sha256(p) == hashlib.sha256(b"some installer bytes").hexdigest()
    assert file_sha256(tmp_path / "missing.bin") is None


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


def test_download_ignored_while_another_is_in_progress(checker, tmp_path):
    """UPD-7: a second download_installer call must fail fast (False, and NO
    signal) instead of overwriting the shared reply/hasher state of the
    running one. Emitting download_failed here used to close the live
    download dialog and show "download failed" while the first transfer was
    still running fine in the background."""
    failed = []
    checker.download_failed.connect(lambda reason: failed.append(reason))
    checker._download_reply = object()  # simulate an in-flight download
    started = checker.download_installer("http://127.0.0.1:9/x.exe", tmp_path / "out.exe", "")
    assert started is False
    assert failed == []  # the running download's dialog must stay untouched
    assert not (tmp_path / "out.exe").exists()


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


# --- the round's own verdict signal ----------------------------------------------------------------


def test_stable_hotfix_tag_with_prerelease_false_is_offered(http_server, checker, qtbot, monkeypatch, user_data):
    """A stable release with a hyphenated tag (``1.4.1-hotfix``) must not be
    ignored forever - GitHub's flag says it is not a pre-release."""
    handler, base = http_server
    handler.routes["/api"] = (200, {}, _release_payload(tag="v99.0.0-hotfix", prerelease=False))
    handler.routes["/holidays.json"] = (200, {}, _holidays_payload(990001))
    monkeypatch.setattr(APP_CONFIG, "APP_RELEASES_API_URL", f"{base}/api")
    monkeypatch.setenv(HOLIDAYS_URL_ENV, f"{base}/holidays.json")

    got = _collect(checker)
    checker.check()
    qtbot.waitUntil(lambda: bool(got["concluded"]), timeout=10000)
    assert len(got["app"]) == 1
    assert got["app"][0][0] == "99.0.0-hotfix"
    assert got["rounds"] == [(APP_STATE_UPDATE_FOUND, HOLIDAYS_STATE_UPDATED)]


def test_payload_flagged_prerelease_is_skipped_even_with_plain_tag(http_server, checker, qtbot, monkeypatch, user_data):
    """The flag also flags releases a name-based rule would miss."""
    handler, base = http_server
    handler.routes["/api"] = (200, {}, _release_payload(tag="v99.0.0", prerelease=True))
    handler.routes["/holidays.json"] = (200, {}, _holidays_payload(990001))
    monkeypatch.setattr(APP_CONFIG, "APP_RELEASES_API_URL", f"{base}/api")
    monkeypatch.setenv(HOLIDAYS_URL_ENV, f"{base}/holidays.json")

    got = _collect(checker)
    checker.check()
    qtbot.waitUntil(lambda: bool(got["concluded"]), timeout=10000)
    assert got["app"] == []
    assert got["rounds"] == [(APP_STATE_CURRENT, HOLIDAYS_STATE_UPDATED)]


def test_prerelease_tag_is_skipped_not_misread_as_up_to_date(http_server, checker, qtbot, monkeypatch, user_data, caplog):
    """'v99.0.0-beta' used to parse as garbage and log "App is up to date". Now
    it is explicitly recognized as a pre-release and skipped."""
    import logging

    handler, base = http_server
    handler.routes["/api"] = (200, {}, _release_payload(tag="v99.0.0-beta"))
    handler.routes["/holidays.json"] = (200, {}, _holidays_payload(990001))
    monkeypatch.setattr(APP_CONFIG, "APP_RELEASES_API_URL", f"{base}/api")
    monkeypatch.setenv(HOLIDAYS_URL_ENV, f"{base}/holidays.json")
    stale_checker = UpdateChecker(current_data_version=990002)

    got = _collect(stale_checker)
    with caplog.at_level(logging.INFO):
        stale_checker.check()
        qtbot.waitUntil(lambda: bool(got["concluded"]), timeout=10000)
    assert got["app"] == []                                   # never offered
    assert any("pre-release" in r.message for r in caplog.records)
    assert got["rounds"] == [(APP_STATE_CURRENT, HOLIDAYS_STATE_CURRENT)]


def test_unsafe_download_url_is_never_offered(http_server, checker, qtbot, monkeypatch, user_data):
    """A http / non-GitHub browser_download_url is refused at the offer boundary
    instead of being handed to the download dialog."""
    handler, base = http_server
    for url in ("http://example.invalid/installer.exe",
                "https://example.invalid/installer.exe"):
        obj = json.loads(_release_payload())
        obj["assets"][0]["browser_download_url"] = url
        handler.routes["/api"] = (200, {}, json.dumps(obj).encode())
        handler.routes["/holidays.json"] = (200, {}, _holidays_payload(990001))
        monkeypatch.setattr(APP_CONFIG, "APP_RELEASES_API_URL", f"{base}/api")
        monkeypatch.setenv(HOLIDAYS_URL_ENV, f"{base}/holidays.json")
        stale_checker = UpdateChecker(current_data_version=990002)

        got = _collect(stale_checker)
        stale_checker.check()
        qtbot.waitUntil(lambda: bool(got["concluded"]), timeout=10000)
        assert got["app"] == [], f"{url} must not be offered"
        assert got["rounds"] == [(APP_STATE_UNAVAILABLE, HOLIDAYS_STATE_CURRENT)]
        assert got["none"] == 0


# --- the round matrix, driven through real rounds ------------------------------------------------


def test_round_matrix_app_failed_holidays_updated(http_server, checker, qtbot, monkeypatch, user_data):
    """app failed | holidays updated: «فایل تعطیلات به‌روزرسانی شد، اما بررسی برنامه
    ناموفق بود.» - the app verdict stays failed (retry logic untouched)."""
    handler, base = http_server
    handler.routes["/api"] = (200, {}, b"this is not json{")
    handler.routes["/holidays.json"] = (200, {}, _holidays_payload(5))
    monkeypatch.setattr(APP_CONFIG, "APP_RELEASES_API_URL", f"{base}/api")
    monkeypatch.setenv(HOLIDAYS_URL_ENV, f"{base}/holidays.json")

    got = _collect(checker)
    checker.check()
    qtbot.waitUntil(lambda: bool(got["concluded"]), timeout=10000)
    assert got["rounds"] == [(APP_STATE_FAILED, HOLIDAYS_STATE_UPDATED)]
    assert got["concluded"] == [True]  # app verdict still drives the retry


def test_round_matrix_app_failed_holidays_failed(http_server, checker, qtbot, monkeypatch, user_data):
    handler, base = http_server
    handler.routes["/api"] = (200, {}, b"not json{")
    handler.routes["/holidays.json"] = (200, {}, b"nor this]")
    monkeypatch.setattr(APP_CONFIG, "APP_RELEASES_API_URL", f"{base}/api")
    monkeypatch.setenv(HOLIDAYS_URL_ENV, f"{base}/holidays.json")

    got = _collect(checker)
    checker.check()
    qtbot.waitUntil(lambda: bool(got["concluded"]), timeout=10000)
    assert got["rounds"] == [(APP_STATE_FAILED, HOLIDAYS_STATE_FAILED)]
    assert got["failed"] == ["network"]


def test_round_matrix_holiday_only_update_current_app(http_server, checker, qtbot, monkeypatch, user_data):
    """current | updated: the holiday data applies, the app popup stays away, and
    the round verdict names both facts."""
    handler, base = http_server
    handler.routes["/api"] = (200, {}, _release_payload("1.0.0"))
    handler.routes["/holidays.json"] = (200, {}, _holidays_payload(5))
    monkeypatch.setattr(APP_CONFIG, "APP_RELEASES_API_URL", f"{base}/api")
    monkeypatch.setenv(HOLIDAYS_URL_ENV, f"{base}/holidays.json")

    got = _collect(checker)
    checker.check()
    qtbot.waitUntil(lambda: bool(got["concluded"]), timeout=10000)
    assert got["rounds"] == [(APP_STATE_CURRENT, HOLIDAYS_STATE_UPDATED)]
    assert got["holidays"] == 1


def test_round_matrix_update_found_holidays_current(http_server, checker, qtbot, monkeypatch, user_data):
    handler, base = http_server
    handler.routes["/api"] = (200, {}, _release_payload())
    handler.routes["/holidays.json"] = (200, {}, _holidays_payload(990001))
    monkeypatch.setattr(APP_CONFIG, "APP_RELEASES_API_URL", f"{base}/api")
    monkeypatch.setenv(HOLIDAYS_URL_ENV, f"{base}/holidays.json")
    stale_checker = UpdateChecker(current_data_version=990002)

    got = _collect(stale_checker)
    stale_checker.check()
    qtbot.waitUntil(lambda: bool(got["concluded"]), timeout=10000)
    assert got["rounds"] == [(APP_STATE_UPDATE_FOUND, HOLIDAYS_STATE_CURRENT)]


# --- quiet holidays-only rounds --------------------------------------------------------------------


def test_check_holidays_round_is_quiet_and_never_concludes(http_server, checker, qtbot, monkeypatch, user_data):
    """A holidays-only retry refreshes data and reports round_finished
    ('skipped' app verdict) but never emits the app signals or check_concluded,
    so 'last checked' and the retry machinery stay untouched."""
    handler, base = http_server
    handler.routes["/holidays.json"] = (200, {}, _holidays_payload(5))
    monkeypatch.delenv(HOLIDAYS_URL_ENV, raising=False)
    monkeypatch.setattr(APP_CONFIG, "HOLIDAYS_UPDATE_URL", f"{base}/holidays.json")

    got = _collect(checker)
    assert checker.check_holidays() is True
    qtbot.waitUntil(lambda: bool(got["rounds"]), timeout=10000)
    assert got["rounds"] == [(APP_STATE_SKIPPED, HOLIDAYS_STATE_UPDATED)]
    assert got["holidays"] == 1
    assert got["concluded"] == []          # no app verdict
    assert got["failed"] == [] and got["app"] == [] and got["none"] == 0


def test_check_holidays_failure_reports_failed_state(http_server, checker, qtbot, monkeypatch, user_data):
    handler, base = http_server
    handler.routes["/holidays.json"] = (200, {}, b"broken{")
    monkeypatch.delenv(HOLIDAYS_URL_ENV, raising=False)
    monkeypatch.setattr(APP_CONFIG, "HOLIDAYS_UPDATE_URL", f"{base}/holidays.json")

    got = _collect(checker)
    checker.check_holidays()
    qtbot.waitUntil(lambda: bool(got["rounds"]), timeout=10000)
    assert got["rounds"] == [(APP_STATE_SKIPPED, HOLIDAYS_STATE_FAILED)]
    assert got["concluded"] == []


def test_check_holidays_is_noop_while_a_round_is_pending(http_server, checker, qtbot, monkeypatch, user_data):
    handler, base = http_server
    handler.routes["/api"] = (200, {}, _release_payload("1.0.0"))
    handler.routes["/holidays.json"] = (200, {}, _holidays_payload(0))
    monkeypatch.setattr(APP_CONFIG, "APP_RELEASES_API_URL", f"{base}/api")
    monkeypatch.setenv(HOLIDAYS_URL_ENV, f"{base}/holidays.json")

    checker.check()
    assert checker.check_holidays() is False
    qtbot.waitUntil(lambda: checker._pending == 0, timeout=10000)


def test_round_kind_reports_which_kind_is_in_flight(http_server, checker, qtbot, monkeypatch, user_data):
    """The controller reads this to decide whether a manual press during a
    quiet refresh should QUEUE a full check instead of marking that refresh
    manual - a skipped round must never message, or the press is swallowed."""
    handler, base = http_server
    handler.routes["/holidays.json"] = (200, {}, _holidays_payload(5))
    monkeypatch.delenv(HOLIDAYS_URL_ENV, raising=False)
    monkeypatch.setattr(APP_CONFIG, "HOLIDAYS_UPDATE_URL", f"{base}/holidays.json")

    checker.check_holidays()
    assert checker.round_kind == "holidays"
    qtbot.waitUntil(lambda: checker._pending == 0, timeout=10000)


def test_env_override_ignored_in_frozen_build(http_server, checker, qtbot, monkeypatch, user_data):
    """SHAMSITRAY_HOLIDAYS_URL is a development hook; a frozen (installed) build
    must ignore it and use the config URL."""
    import core.update_checker as update_checker_module

    handler, base = http_server
    handler.routes["/api"] = (200, {}, _release_payload("1.0.0"))
    handler.routes["/gh-holidays"] = (200, {}, _holidays_payload(0))
    monkeypatch.setattr(APP_CONFIG, "APP_RELEASES_API_URL", f"{base}/api")
    monkeypatch.setenv(HOLIDAYS_URL_ENV, f"{base}/holidays.json")  # decoy
    monkeypatch.setattr(APP_CONFIG, "HOLIDAYS_UPDATE_URL", f"{base}/gh-holidays")
    monkeypatch.setattr(update_checker_module.sys, "frozen", True, raising=False)

    got = _collect(checker)
    checker.check()
    qtbot.waitUntil(lambda: bool(got["concluded"]), timeout=10000)
    assert handler.hits.get("/holidays.json", 0) == 0   # the decoy was never hit
    assert handler.hits["/gh-holidays"] == 1
