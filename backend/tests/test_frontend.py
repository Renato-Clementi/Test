from mosaika.config import REPO_ROOT

COLORI = (
    "#FFFFFF",
    "#374350",
    "#3C4348",
    "#5B6670",
    "#3F6A8A",
    "#EFF4F8",
    "#D6E1EA",
)


def test_stile_tema_e_larghezza():
    html = (REPO_ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    css = (REPO_ROOT / "frontend" / "css" / "app.css").read_text(encoding="utf-8")
    manifest = (REPO_ROOT / "frontend" / "manifest.webmanifest").read_text(encoding="utf-8")
    script = (REPO_ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
    assert 'name="viewport"' in html
    assert "width=device-width" in html
    assert "Work+Sans" in html
    assert "JetBrains+Mono" in html
    assert "manifest.webmanifest" in html
    assert 'lang="it"' in html
    for colore in COLORI:
        assert colore in css
    assert '[data-theme="dark"]' in css
    assert "--late" in css
    assert ".in-ritardo" in css
    assert "Work Sans" in css
    assert "JetBrains Mono" in css
    assert '"display": "standalone"' in manifest
    assert "data-theme" in html
    assert "dataset.theme" in script
    assert '.lang = "it-IT"' in script
    assert (REPO_ROOT / "frontend" / "icons" / "icon-192.png").is_file()
    assert (REPO_ROOT / "frontend" / "icons" / "icon-512.png").is_file()
    assert (REPO_ROOT / "frontend" / "sw.js").is_file()
