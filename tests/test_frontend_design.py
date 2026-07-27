from pathlib import Path
import re

FRONT = Path(__file__).parent.parent / "frontend"


def _regra(css, seletor):
    """Extrai o corpo da regra de um seletor, sem casar com listas como 'html, body'.

    Usa regex com multiline para evitar false positives com seletores combinados.
    """
    # Procura por um newline seguido de opicional whitespace, depois o seletor
    # Isso evita casar 'body' dentro de 'html, body' na mesma linha
    pattern = rf'(?:^|\n)\s*{re.escape(seletor)}\s*\{{([^}}]*)\}}'
    m = re.search(pattern, css, re.MULTILINE)
    assert m, f"regra '{seletor}' não encontrada"
    return m.group(1)


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


def test_body_uses_inter_and_headings_use_serif():
    css = (FRONT / "styles.css").read_text(encoding="utf-8")
    corpo = _regra(css, "body")
    assert "'Inter'" in corpo
    assert "Segoe UI" in corpo, "manter como fallback"
    h1 = _regra(css, "h1")
    assert "'Instrument Serif'" in h1


def test_signature_keeps_the_editorial_italic():
    """'By Munhoz' é assinatura: serifa itálica creme, como na landing."""
    css = (FRONT / "styles.css").read_text(encoding="utf-8")
    assinatura = _regra(css, ".signature b")
    assert "var(--cream)" in assinatura


def test_body_keeps_its_box_model_reset():
    """Sem margin:0 no body, Chromium aplica 8px e cria barra de rolagem indesejada."""
    css = (FRONT / "styles.css").read_text(encoding="utf-8")
    assert re.search(r'html,\s*body\s*\{[^}]*margin:\s*0', css), \
        "o reset de margin do body sumiu — vai criar 8px de margem do user-agent"


def test_background_has_grain_and_glow_like_the_landing():
    css = (FRONT / "styles.css").read_text(encoding="utf-8")
    assert "feTurbulence" in css, "grão ausente"
    assert "radial-gradient" in css, "brilho radial ausente"
    # Verifica pointer-events:none especificamente em body::before e body::after
    before = _regra(css, "body::before")
    after = _regra(css, "body::after")
    assert "pointer-events:none" in before.replace(" ", ""), \
        "pointer-events:none ausente em body::before"
    assert "pointer-events:none" in after.replace(" ", ""), \
        "pointer-events:none ausente em body::after"


def test_background_texture_matches_the_landing_exactly():
    """A textura do app tem que ser a mesma da landing, valor por valor."""
    css = (FRONT / "styles.css").read_text(encoding="utf-8")
    landing = (FRONT.parent / "site" / "index.html").read_text(encoding="utf-8")

    def gradientes(texto):
        bloco = re.search(r'body::before\s*\{([^}]*)\}', texto).group(1)
        # Extrai todos os radial-gradient e normaliza
        return sorted(re.findall(r'radial-gradient\([^)]*\)', bloco))

    app_grads = gradientes(css)
    landing_grads = gradientes(landing)
    assert app_grads == landing_grads, \
        f"gradientes diferem:\napp: {app_grads}\nlanding: {landing_grads}"

    # Verifica opacidade do grão
    app_opacity = re.search(r'body::after\s*\{([^}]*)\}', css).group(1)
    landing_opacity = re.search(r'body::after\s*\{([^}]*)\}', landing).group(1)
    assert "opacity:.032" in app_opacity.replace(" ", ""), \
        "opacidade do grão deve ser .032"
    assert "opacity:.032" in landing_opacity.replace(" ", ""), \
        "opacidade do grão na landing deve ser .032"
