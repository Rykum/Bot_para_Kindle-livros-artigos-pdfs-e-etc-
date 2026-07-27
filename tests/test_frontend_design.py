from pathlib import Path

FRONT = Path(__file__).parent.parent / "frontend"


def test_fonts_are_self_hosted():
    """O app roda offline: nenhuma fonte pode vir de CDN."""
    fontes = FRONT / "fonts"
    assert (fontes / "inter-var-latin.woff2").exists()
    assert (fontes / "instrumentserif-latin.woff2").exists()
    assert (fontes / "instrumentserif-italic-latin.woff2").exists()


def test_css_declares_both_families_locally():
    css = (FRONT / "styles.css").read_text(encoding="utf-8")
    assert "@font-face" in css
    assert "url(fonts/inter-var-latin.woff2)" in css
    assert "url(fonts/instrumentserif-latin.woff2)" in css
    assert "fonts.googleapis.com" not in css
    assert "https://" not in css.split("/* ---------------- Sidebar")[0]
