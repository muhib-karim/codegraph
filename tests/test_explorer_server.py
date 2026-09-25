import http.client
import json
import os
import threading
import urllib.parse

import pytest

from codegraph import indexer
from codegraph.explorer_server import make_server

MINI = os.path.join(os.path.dirname(__file__), 'fixtures', 'mini')


@pytest.fixture(scope='module')
def server(tmp_path_factory):
    root = tmp_path_factory.mktemp('web')
    db = str(root / 'graph.lbug')
    indexer.index(MINI, db)
    httpd = make_server(db, 0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd
    httpd.shutdown()
    httpd.server_close()
    thread.join()


def get(server, path, host=None, method='GET'):
    c = http.client.HTTPConnection('127.0.0.1', server.server_port)
    c.request(method, path, headers={'Host': host or f'127.0.0.1:{server.server_port}'})
    resp = c.getresponse()
    body = resp.read()
    result = (resp.status, dict(resp.getheaders()), body)
    c.close()
    return result


def test_routes(server):
    status, headers, body = get(server, '/api/meta')
    assert status == 200 and json.loads(body)['schema_version'] == '1'
    assert 'Access-Control-Allow-Origin' not in headers
    status, _, body = get(server, '/api/files?prefix=pkg%2F')
    assert status == 200 and json.loads(body)['items']
    status, _, body = get(server, '/api/query?command=callers&target=make')
    assert status == 200 and json.loads(body)['results']['items']
    assert get(server, '/')[0] == 200


def test_rejections(server):
    assert get(server, '/api/meta', host='attacker.example')[0] == 403
    assert get(server, '/api/meta', method='POST')[0] == 405
    assert get(server, '/api/source?path=..%2Fsecret&start=1&end=2')[0] == 400
    assert get(server, '/api/files?limit=9999')[0] == 400
    assert get(server, '/api/query?command=delete')[0] == 400
    assert get(server, '/api/query?command=callers&target=make&target=Circle')[0] == 400
    assert get(server, '/api/source?path=app.py&start=1&end=3')[0] == 200


def test_http_indexed_symlink_escape(tmp_path):
    """Index a regular file, then swap it for an outside symlink before HTTP read."""
    import shutil
    repo = tmp_path / 'repo'
    shutil.copytree(MINI, repo)
    db = str(tmp_path / 'index.lbug')
    indexer.index(str(repo), db)
    from codegraph.explorer_data import Explorer
    assert Explorer(db).file('app.py')['file']['path'] == 'app.py'
    outside = tmp_path / 'outside.txt'
    outside.write_text('UNIQUE_DISPOSABLE_SENTINEL')
    (repo / 'app.py').unlink()
    (repo / 'app.py').symlink_to(outside)
    assert not (repo / 'app.py').resolve().is_relative_to(repo.resolve())
    server = make_server(db, 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, _, body = get(server, '/api/source?path=app.py&start=1&end=5')
        assert status == 404
        assert b'UNIQUE_DISPOSABLE_SENTINEL' not in body
        assert 'error' in json.loads(body)
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
