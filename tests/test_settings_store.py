from pathlib import Path

import app.settings_store as ss


def test_set_get_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(ss, "_PATH", tmp_path / "cfg.json")
    assert ss.get_setting("download_dir") is None
    assert ss.get_setting("download_dir", "x") == "x"
    ss.set_setting("download_dir", "/some/path")
    assert ss.get_setting("download_dir") == "/some/path"


def test_persisted_to_disk(tmp_path, monkeypatch):
    cfg = tmp_path / "cfg.json"
    monkeypatch.setattr(ss, "_PATH", cfg)
    ss.set_setting("a", 1)
    ss.set_setting("b", "dois")
    assert cfg.exists()
    # nova leitura reflete os dois valores
    assert ss.get_setting("a") == 1
    assert ss.get_setting("b") == "dois"


def test_corrupt_file_degrades_to_default(tmp_path, monkeypatch):
    cfg = tmp_path / "cfg.json"
    cfg.write_text("nao é json", encoding="utf-8")
    monkeypatch.setattr(ss, "_PATH", cfg)
    assert ss.get_setting("x", "default") == "default"
