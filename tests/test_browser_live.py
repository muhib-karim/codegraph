"""Optional live UI smoke test; no browser is required by CI."""

import threading
from pathlib import Path

import pytest

from codegraph.explorer_server import make_server
from codegraph.indexer import index


def test_browser_loads_local_explorer(tmp_path):
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as runtime:
        if not Path(runtime.chromium.executable_path).is_file():
            pytest.skip("Chromium is not installed")
        try:
            browser = runtime.chromium.launch(headless=True)
        except playwright.Error as exc:
            pytest.skip(f"Chromium is unavailable: {exc}")
        db = str(tmp_path / "graph.lbug")
        index(str(Path(__file__).parent / "fixtures" / "mini"), db)
        server = make_server(db, 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            page = browser.new_page()
            failures = []
            page.on("pageerror", failures.append)
            page.goto(f"http://127.0.0.1:{server.server_port}/")
            page.get_by_text("app.py", exact=True).first.wait_for()
            assert not failures
        finally:
            browser.close()
            server.shutdown()
            server.server_close()
            thread.join()
