import fcntl
import sys
import time
from pathlib import Path

import pytest

from etsy_insights.runner import RunnerBusy, SessionRunner, parse_progress

FAKE = [sys.executable, str(Path(__file__).parent / "fake_session.py")]


def wait_for(cond, timeout=5):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.05)
    return False


def test_parse_progress():
    lines = ["10:00:00 [1/15] mug", "10:00:01   12 searches", "10:00:40 [2/15] tote bag"]
    assert parse_progress(lines) == ("tote bag", 2, 15)
    assert parse_progress([]) == (None, 0, None)


def test_start_status_stop(tmp_path):
    r = SessionRunner(tmp_path, command=FAKE)
    r.start(test_run=True)
    assert wait_for(lambda: r.status().current_keyword == "beta")
    st = r.status()
    assert (st.running, st.source, st.done, st.limit) == (True, "app", 2, 3)
    with pytest.raises(RunnerBusy):
        r.start()
    assert r.stop()
    assert wait_for(lambda: not r.status().running)
    assert any("Stopped" in line for line in r.status().log_tail)


def test_stop_kills_after_timeout(tmp_path):
    r = SessionRunner(tmp_path, command=FAKE + ["--ignore-term"], stop_timeout=0.3)
    r.start()
    assert wait_for(lambda: r.status().done == 2)
    r.stop()
    assert wait_for(lambda: not r.status().running, timeout=5)


def test_terminal_session_detected(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "sesi-20261111-100000.log").write_text("10:00:00 [4/15] mug\n", encoding="utf-8")
    with open(tmp_path / "data" / "sesi.lock", "w") as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        r = SessionRunner(tmp_path, command=FAKE)
        st = r.status()
        assert (st.running, st.source, st.current_keyword) == (True, "terminal", "mug")
        with pytest.raises(RunnerBusy):
            r.start()
    assert not SessionRunner(tmp_path, command=FAKE).status().running


def test_default_command_and_env(tmp_path):
    calls = []

    class P:
        pid = 1

        def poll(self):
            return None

    def fake_popen(args, **kw):
        calls.append((args, kw))
        return P()
    r = SessionRunner(tmp_path, popen=fake_popen)
    log = r.start(test_run=True, ignore_cooldown=True)
    args, kw = calls[0]
    assert args[:4] == [sys.executable, "-m", "etsy_insights", "run"]
    assert "--uji" in args and "--abaikan-pendinginan" in args and "--yes" in args
    assert args[-2:] == ["--log-file", str(log)]
    assert kw["env"]["ETSY_INSIGHTS_HOME"] == str(tmp_path) and kw["start_new_session"] is True
