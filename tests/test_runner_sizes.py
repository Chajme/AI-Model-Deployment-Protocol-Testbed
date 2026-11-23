import pytest

import common.file_manager as fm
import runner


def test_resolve_sizes_sorted_by_size(tmp_path, monkeypatch):
    for name, size in (("binary_file_1mb.bin", 2000), ("binary_file_250kb.bin", 1000)):
        (tmp_path / name).write_bytes(b"x" * size)
    monkeypatch.setattr(fm, "DATA_DIR", str(tmp_path))
    assert runner.resolve_sizes(["1mb", "250KB"]) == ["binary_file_250kb.bin",
                                                      "binary_file_1mb.bin"]


def test_resolve_sizes_unknown_size_fails(tmp_path, monkeypatch):
    (tmp_path / "binary_file_1mb.bin").write_bytes(b"x")
    monkeypatch.setattr(fm, "DATA_DIR", str(tmp_path))
    with pytest.raises(SystemExit, match="no payload for size '7kb'"):
        runner.resolve_sizes(["7kb"])
