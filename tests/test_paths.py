from etsy_insights import paths


def test_app_home_default_and_env(monkeypatch, tmp_path):
    monkeypatch.delenv(paths.ENV_HOME, raising=False)
    assert paths.app_home() == paths.PROJECT_ROOT and paths.excel_dir(tmp_path) == tmp_path / "hasil"
    monkeypatch.setenv(paths.ENV_HOME, str(tmp_path / "home"))
    monkeypatch.setenv("HOME", str(tmp_path))
    assert paths.app_home() == tmp_path / "home"
    assert paths.excel_dir(tmp_path / "home") == tmp_path / "Documents" / "Etsy Insights"
