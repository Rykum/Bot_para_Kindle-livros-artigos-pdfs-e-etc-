from pathlib import Path

from app.komga_exporter import KomgaExporter


class FakeFile:
    def __init__(self, file_path, file_format="cbz"):
        self.file_path = file_path
        self.file_format = file_format
        self.download_status = "completed"


class FakeChapter:
    def __init__(self, chapter_number, files, volume_number=1.0):
        self.chapter_number = chapter_number
        self.files = files
        self.volume_number = volume_number


class FakeLibrary:
    """Simula o mínimo que o exporter consome."""
    def __init__(self, chapters):
        self._chapters = chapters

    def get_or_create_series(self, title, *a, **k):
        return type("S", (), {"title": title})()

    def iter_downloaded_files(self, series):
        # (volume_number, chapter_number, file_path, file_format)
        for chap in self._chapters:
            for f in chap.files:
                yield (chap.volume_number, chap.chapter_number, f.file_path, f.file_format)


def make_source_file(tmp_path, name):
    p = tmp_path / name
    p.write_bytes(b"conteudo")
    return str(p)


def test_export_creates_komga_layout(tmp_path):
    src = make_source_file(tmp_path, "cap1.cbz")
    library = FakeLibrary([FakeChapter(1.0, [FakeFile(src)])])
    exporter = KomgaExporter(library=library, export_root=str(tmp_path / "out"))

    result = exporter.export_series("Dandadan")

    exported = Path(result["base_path"]) / "Chapter 001" / "cap1.cbz"
    assert exported.exists()
    assert result["exported"] == 1


def test_export_is_idempotent(tmp_path):
    src = make_source_file(tmp_path, "cap1.cbz")
    library = FakeLibrary([FakeChapter(1.0, [FakeFile(src)])])
    exporter = KomgaExporter(library=library, export_root=str(tmp_path / "out"))

    exporter.export_series("Dandadan")
    result = exporter.export_series("Dandadan")  # segunda vez pula
    assert result["skipped"] == 1
    assert result["exported"] == 0


def test_sanitize_removes_invalid_chars(tmp_path):
    exporter = KomgaExporter(library=FakeLibrary([]), export_root=str(tmp_path))
    assert exporter.sanitize('a/b:c*?"<>|') == "a_b_c"


def test_fractional_and_integer_chapters_get_distinct_folders(tmp_path):
    src_int = make_source_file(tmp_path, "cap10.cbz")
    src_frac = make_source_file(tmp_path, "cap10_5.cbz")
    library = FakeLibrary([
        FakeChapter(10.0, [FakeFile(src_int)]),
        FakeChapter(10.5, [FakeFile(src_frac)]),
    ])
    exporter = KomgaExporter(library=library, export_root=str(tmp_path / "out"))

    result = exporter.export_series("Dandadan")

    int_file = Path(result["base_path"]) / "Chapter 010" / "cap10.cbz"
    frac_file = Path(result["base_path"]) / "Chapter 010.5" / "cap10_5.cbz"
    assert int_file.exists()
    assert frac_file.exists()
    assert result["exported"] == 2
