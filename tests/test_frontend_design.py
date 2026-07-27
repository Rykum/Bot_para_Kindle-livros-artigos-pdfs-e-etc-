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


def test_tokens_match_the_landing_palette():
    """A paleta do app tem que ser a mesma da landing, valor por valor."""
    css = (FRONT / "styles.css").read_text(encoding="utf-8")
    for token, valor in [
        ("--ink-950", "#08090c"), ("--ink-900", "#0b0d12"),
        ("--ink-850", "#0e1117"), ("--ink-800", "#11151d"),
        ("--tx", "#eceef3"), ("--tx-2", "#98a1b2"), ("--tx-3", "#616a7b"),
        ("--blue", "#7ea6ff"), ("--cream", "#e8d5b0"),
    ]:
        assert f"{token}:{valor}" in css.replace(" ", ""), token


def test_borders_are_alpha_hairlines_not_solid():
    """Bordas sólidas criam 'caixinhas'; a landing usa hairlines em alpha."""
    css = (FRONT / "styles.css").read_text(encoding="utf-8")
    assert "rgba(255,255,255,.065)" in css.replace(" ", "")
    assert "#212c3d" not in css, "cor de borda sólida antiga ainda presente"


def test_old_token_names_still_resolve():
    """Apelidos evitam quebrar as regras existentes nesta etapa."""
    css = (FRONT / "styles.css").read_text(encoding="utf-8").replace(" ", "")
    assert "--bg:var(--ink-950)" in css
    assert "--accent:var(--blue)" in css


def test_no_slate_blue_leftovers_outside_root():
    """A paleta antiga era slate-blue; sobre o near-black ela destoa."""
    css = (FRONT / "styles.css").read_text(encoding="utf-8")
    for antiga in ["#2c3d61", "#2b3a52", "#24334f", "#30456a", "#212c3d"]:
        assert antiga not in css, f"cor da paleta antiga ainda presente: {antiga}"
