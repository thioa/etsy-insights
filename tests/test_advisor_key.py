import stat

import pytest

from etsy_insights.advisor_key import clean_key, delete_key, key_hint, load_key, looks_like_key, save_key

GOOD = "sk-ant-api03-" + "a" * 20


def test_clean_and_shape():
    assert clean_key(" sk-ant-api03-abc\n def ") == "sk-ant-api03-abcdef"
    assert looks_like_key(GOOD)
    assert not looks_like_key("sk-ant-short")
    assert not looks_like_key("sk-proj-" + "a" * 30)
    assert not looks_like_key("sk-ant-api03-" + "é" * 20)


def test_save_load_delete_permissions(tmp_path):
    assert save_key(tmp_path, f"  {GOOD}\n") == GOOD
    path = tmp_path / "anthropic-key"
    assert path.exists()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert load_key(tmp_path) == GOOD
    delete_key(tmp_path)
    assert load_key(tmp_path) is None
    delete_key(tmp_path)


def test_save_rejects_bad_key(tmp_path):
    with pytest.raises(ValueError, match="That does not look like an Anthropic API key."):
        save_key(tmp_path, "hello")
    assert not (tmp_path / "anthropic-key").exists()


def test_key_hint():
    assert key_hint("sk-ant-api03-xyz1234") == "…1234"
