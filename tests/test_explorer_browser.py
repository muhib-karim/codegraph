"""Packaged UI contract plus optional real-browser smoke tests (run separately)."""

from importlib import resources


def test_bundled_frontend_and_no_remote_assets():
    root = resources.files("codegraph").joinpath("web")
    for name in ("index.html", "style.css", "app.js"):
        text = root.joinpath(name).read_text()
        assert text
        assert "https://" not in text and "http://" not in text.replace(
            "http://www.w3.org/2000/svg", ""
        )
    js = root.joinpath("app.js").read_text()
    assert "textContent" in js
    assert "innerHTML" not in js


def test_live_status_and_route_state_contract():
    root = resources.files("codegraph").joinpath("web")
    html = root.joinpath("index.html").read_text()
    js = root.joinpath("app.js").read_text()
    assert 'id="query-message" role="status" aria-live="polite"' in html
    assert 'id="source-message" class="sr-only" role="status" aria-live="polite"' in html
    for field in ("ancestors", "kind", "confidence", "scope", "depth", "target"):
        assert f"hash.set('{field}'" in js or f"hash.set('{field}'," in js
    assert "hash.set('run','1')" in js
    assert "window.addEventListener('popstate',scheduleRestore)" in js
    assert "window.addEventListener('hashchange',scheduleRestore)" in js
