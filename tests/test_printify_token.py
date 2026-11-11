import stat

import pytest

from etsy_insights.printify_token import delete_token, load_token, save_token, token_hint


def test_save_load_delete(tmp_path):
    assert save_token(tmp_path, "  Bearer abc.def-123\n") == "abc.def-123"
    assert load_token(tmp_path) == "abc.def-123"
    assert stat.S_IMODE((tmp_path / "printify-token").stat().st_mode) == 0o600
    assert token_hint("abc.def-123") == "…-123"
    delete_token(tmp_path)
    delete_token(tmp_path)
    assert load_token(tmp_path) is None


def test_empty_token_rejected(tmp_path):
    with pytest.raises(ValueError):
        save_token(tmp_path, "  Bearer  ")
