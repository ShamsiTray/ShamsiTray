from core.update_checker import digest_hex, is_newer_version, should_notify


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
