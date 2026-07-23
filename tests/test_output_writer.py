import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from app.output_writer import OutputWriter


def test_build_comicinfo_has_fields_and_escapes():
    xml = OutputWriter().build_comicinfo_xml({
        "series": "Tom & Jerry <manga>", "number": 15, "volume": 2,
        "title": "Cap", "summary": "abc", "writer": "Autor A",
        "count": 120, "page_count": 3, "web": "http://x", "language": "pt-br",
    })
    root = ET.fromstring(xml)  # parse valida o XML e o escaping
    assert root.tag == "ComicInfo"
    got = {child.tag: child.text for child in root}
    assert got["Series"] == "Tom & Jerry <manga>"
    assert got["Number"] == "15"
    assert got["LanguageISO"] == "pt"
    assert got["Manga"] == "YesAndRightToLeft"
    assert got["PageCount"] == "3"


def test_build_comicinfo_omits_missing():
    xml = OutputWriter().build_comicinfo_xml({"series": "S", "number": 1})
    root = ET.fromstring(xml)
    tags = {c.tag for c in root}
    assert "Summary" not in tags
    assert "Writer" not in tags
    assert "Series" in tags


def test_write_cbz_contains_comicinfo_and_pages(tmp_path):
    dest = tmp_path / "cap.cbz"
    result = OutputWriter().write_cbz(
        pages=[("001.jpg", b"aaa"), ("002.jpg", b"bbb")],
        comicinfo={"series": "S", "number": 1, "page_count": 2},
        dest_path=dest,
    )
    assert dest.exists()
    assert result["page_count"] == 2
    assert result["size"] == dest.stat().st_size
    assert len(result["sha256"]) == 64
    with zipfile.ZipFile(dest) as zf:
        names = zf.namelist()
        assert "ComicInfo.xml" in names
        assert "001.jpg" in names and "002.jpg" in names
        ET.fromstring(zf.read("ComicInfo.xml"))  # ComicInfo é XML válido
