import pytest

from etsy_insights.browser import ChromeNotFound, ChromeStartTimeout, PortBusy, chrome_args, ensure_chrome

INFO = {"Browser": "Chrome/140.0.0.0"}


def fake_chrome(tmp_path):
    p = tmp_path / "chrome"
    p.write_text("")
    return p


def test_chrome_args(tmp_path):
    args = chrome_args(tmp_path / "c", 9222, tmp_path / "prof")
    assert args[0] == str(tmp_path / "c") and f"--user-data-dir={tmp_path / 'prof'}" in args
    assert "--remote-debugging-port=9222" in args and "--no-first-run" in args
    assert not any("automation" in a for a in args)


def test_reuses_running_chrome(tmp_path):
    launched = []
    ep = ensure_chrome(9222, tmp_path / "p", fake_chrome(tmp_path), launch=lambda *a, **k: launched.append(a),
                       probe=lambda port: INFO, in_use=lambda port: True, sleep=lambda s: None)
    assert ep == "http://127.0.0.1:9222" and launched == []


def test_launches_and_waits(tmp_path):
    launched, answers = [], iter([None, None, None, INFO])
    ep = ensure_chrome(9333, tmp_path / "p", fake_chrome(tmp_path), launch=lambda args, **k: launched.append(args),
                       probe=lambda port: next(answers), in_use=lambda port: False, sleep=lambda s: None)
    assert ep == "http://127.0.0.1:9333" and len(launched) == 1 and (tmp_path / "p").is_dir()


def test_timeout(tmp_path):
    with pytest.raises(ChromeStartTimeout):
        ensure_chrome(9222, tmp_path / "p", fake_chrome(tmp_path), launch=lambda *a, **k: None,
                      probe=lambda port: None, in_use=lambda port: False, sleep=lambda s: None, wait_seconds=2)


def test_port_busy(tmp_path):
    with pytest.raises(PortBusy, match="port_debug"):
        ensure_chrome(9222, tmp_path / "p", fake_chrome(tmp_path), probe=lambda port: None, in_use=lambda port: True)


def test_chrome_missing(tmp_path):
    with pytest.raises(ChromeNotFound):
        ensure_chrome(9222, tmp_path / "p", tmp_path / "tidak-ada", probe=lambda port: None, in_use=lambda port: False)
