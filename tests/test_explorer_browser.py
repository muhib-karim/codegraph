"""Small contract smoke test for packaged UI, no browser runtime dependency."""
from importlib import resources


def test_bundled_frontend_and_no_remote_assets():
    root = resources.files('codegraph').joinpath('web')
    for name in ('index.html', 'style.css', 'app.js'):
        text = root.joinpath(name).read_text()
        assert text
        assert 'https://' not in text and 'http://' not in text.replace('http://www.w3.org/2000/svg', '')
    js = root.joinpath('app.js').read_text()
    assert 'textContent' in js
    assert 'innerHTML' not in js
