"""Bounded read-only views of an indexed graph. No browser-supplied Cypher."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from . import SCHEMA_VERSION, queries, store

MAX_PAGE = 100
MAX_GRAPH = 200


class BadRequest(ValueError):
    pass


class Explorer:
    def __init__(self, db_path):
        self.db, self.conn = store.connect(db_path)
        self.meta = queries.meta(self.conn)
        if int(self.meta.get('schema_version', '-1')) != SCHEMA_VERSION:
            raise BadRequest('Unsupported graph schema version')
        self.root = Path(self.meta['repo_root']).resolve()

    def rows(self, statement, params=None):
        return self.conn.execute(statement, params or {}).get_all()

    def status(self):
        m = dict(self.meta)
        m['stats'] = json.loads(m.get('stats', '{}'))
        m['indexed_commit'] = m.get('repo_commit', '')
        try:
            m['current_head'] = subprocess.run(['git', '-C', str(self.root), 'rev-parse', 'HEAD'],
                capture_output=True, text=True, timeout=2).stdout.strip()
            m['commit_mismatch'] = bool(m.get('repo_commit') and m['current_head'] and m['current_head'] != m['repo_commit'])
            # This is a coarse global signal, not a per-file content comparison.
            dirty = subprocess.run(['git', '-C', str(self.root), 'status', '--porcelain', '--untracked-files=no'],
                capture_output=True, text=True, timeout=2)
            m['working_tree_modified'] = bool(dirty.stdout.strip()) if dirty.returncode == 0 else False
        except (OSError, subprocess.TimeoutExpired):
            m['current_head'] = ''
            m['commit_mismatch'] = False
            m['working_tree_modified'] = False
        m['snapshot_stale'] = m['commit_mismatch'] or m['working_tree_modified']
        return m

    @staticmethod
    def page(limit, cursor):
        try:
            n, offset = int(limit), int(cursor)
        except (TypeError, ValueError):
            raise BadRequest('Invalid pagination')
        if not 1 <= n <= MAX_PAGE or offset < 0:
            raise BadRequest('Pagination out of range')
        return n, offset

    @staticmethod
    def sliced(items, limit, cursor):
        n, offset = Explorer.page(limit, cursor)
        return {'items': items[offset:offset+n], 'total': len(items),
                'next': str(offset+n) if offset+n < len(items) else None,
                'truncated': offset+n < len(items)}

    def files(self, prefix='', limit=50, cursor=0):
        # prefix filters by repo-relative path, never touches the filesystem
        rows = self.rows('MATCH (f:File) WHERE f.path STARTS WITH $prefix '
                         'RETURN f.path, f.lang, f.loc, f.parsed ORDER BY f.path', {'prefix': prefix})
        return self.sliced([dict(zip(('path', 'lang', 'loc', 'parsed'), r)) for r in rows], limit, cursor)

    def file(self, path, limit=50, cursor=0):
        info = self.rows('MATCH (f:File {path: $path}) RETURN f.path, f.lang, f.loc, f.parsed', {'path': path})
        if not info:
            raise queries.NotFound(path)
        symbols = self.rows('MATCH (s:Symbol) WHERE s.file = $path '
                            'RETURN s.id, s.qualname, s.kind, s.line, s.end_line ORDER BY s.line, s.id', {'path': path})
        return {'file': dict(zip(('path', 'lang', 'loc', 'parsed'), info[0])),
                'symbols': self.sliced([dict(zip(('id', 'qualname', 'kind', 'line', 'end_line'), r))
                                        for r in symbols], limit, cursor)}

    def symbols(self, q='', file='', limit=50, cursor=0):
        if len(q) > 200:
            raise BadRequest('Search too long')
        statement = ('MATCH (s:Symbol) WHERE (s.name CONTAINS $q OR s.qualname CONTAINS $q) '
                     'AND ($file = \'\' OR s.file = $file) '
                     'RETURN s.id, s.qualname, s.kind, s.file, s.line ORDER BY s.file, s.line, s.id')
        rows = self.rows(statement, {'q': q, 'file': file})
        return self.sliced([dict(zip(('id', 'qualname', 'kind', 'file', 'line'), r)) for r in rows], limit, cursor)

    def symbol(self, sid):
        rows = self.rows('MATCH (s:Symbol {id: $id}) RETURN s.id, s.name, s.qualname, s.kind, s.lang, '
                         's.file, s.line, s.end_line, s.parent_id, s.entry_reason, s.visibility', {'id': sid})
        if not rows:
            raise queries.NotFound(sid)
        item = dict(zip(('id', 'name', 'qualname', 'kind', 'lang', 'file', 'line', 'end_line',
                         'parent_id', 'entry_reason', 'visibility'), rows[0]))
        item['citation'] = f"{item['file']}:{item['line']}" if item['file'] and item['line'] else None
        children = self.rows('MATCH (s:Symbol) WHERE s.parent_id = $id RETURN s.id, s.qualname, s.kind, s.line '
                             'ORDER BY s.line, s.id', {'id': sid})
        item['children'] = [dict(zip(('id', 'qualname', 'kind', 'line'), r)) for r in children[:MAX_PAGE]]
        item['children_truncated'] = len(children) > MAX_PAGE
        return item

    def neighborhood(self, sid, direction='both', relations='CALLS,REFERENCES,INHERITS', limit=100):
        if direction not in ('in', 'out', 'both'):
            raise BadRequest('Invalid direction')
        kinds = relations.split(',')
        if not kinds or len(kinds) > 3 or len(set(kinds)) != len(kinds) or any(k not in ('CALLS', 'REFERENCES', 'INHERITS') for k in kinds):
            raise BadRequest('Invalid relations')
        n, _ = self.page(limit, 0)
        n = min(n, MAX_GRAPH // 2)
        center = self.symbol(sid)
        edges = []
        for kind in kinds:
            for way in (('in', 'out') if direction == 'both' else (direction,)):
                if way == 'out':
                    match = f'MATCH (a:Symbol {{id: $id}})-[r:{kind}]->(b:Symbol)'
                else:
                    match = f'MATCH (a:Symbol)-[r:{kind}]->(b:Symbol {{id: $id}})'
                extra = ', r.reason' if kind != 'INHERITS' else ', r.kind'
                rows = self.rows(match + ' RETURN a.id, a.qualname, a.kind, a.file, a.line, '
                                 'b.id, b.qualname, b.kind, b.file, b.line, r.file, r.line, '
                                 'r.confidence' + extra + ' ORDER BY a.id, b.id, r.line', {'id': sid})
                for r in rows:
                    edges.append({'source': r[0], 'target': r[5], 'type': kind,
                                  'file': r[10], 'line': r[11], 'confidence': r[12],
                                  'reason': r[13] if kind != 'INHERITS' else None,
                                  'relation': r[13] if kind == 'INHERITS' else None,
                                  'source_def': f'{r[3]}:{r[4]}' if r[3] and r[4] else None,
                                  'target_def': f'{r[8]}:{r[9]}' if r[8] and r[9] else None,
                                  '_source': (r[0], r[1], r[2], r[3], r[4]),
                                  '_target': (r[5], r[6], r[7], r[8], r[9])})
        edges.sort(key=lambda e: (e['type'], e['source'], e['target'], e['file'] or '', e['line'] or 0))
        selected = edges[:n]
        nodes = {center['id']: {k: center[k] for k in ('id', 'qualname', 'kind', 'file', 'line')}}
        for e in selected:
            for internal in ('_source', '_target'):
                r = e.pop(internal)
                nodes[r[0]] = dict(zip(('id', 'qualname', 'kind', 'file', 'line'), r))
        return {'nodes': list(nodes.values()), 'edges': selected, 'total_edges': len(edges),
                'truncated': len(edges) > n}

    def query(self, command, target='', file='', scope='', depth=None, ancestors=False,
              kind='', confidence='all', limit=50, cursor=0):
        if len(target) > 512 or len(file) > 512 or len(scope) > 512:
            raise BadRequest('Query too long')
        if command == 'callers':
            resolved, result = queries.callers(self.conn, target, file, self.depth(depth, 1, 1), scope)
        elif command == 'inherits':
            resolved, result = queries.inherits(self.conn, target, file, ancestors, self.depth(depth, 0, 0), scope)
        elif command == 'blast':
            resolved, result = queries.blast(self.conn, target, file, self.depth(depth, 3, 1), scope)
        elif command == 'dead-code':
            if confidence not in ('all', 'likely', 'possible'):
                raise BadRequest('Invalid confidence')
            kinds = kind.split(',') if kind else None
            if kinds and any(k not in queries.CODE_KINDS for k in kinds):
                raise BadRequest('Invalid kind')
            resolved, result = [], queries.dead_code(self.conn, scope, kinds, confidence)
        else:
            raise BadRequest('Invalid command')
        return {'command': command, 'resolved': [queries._sym(r) for r in resolved] if resolved and isinstance(resolved[0], tuple) else resolved,
                'results': self.sliced(result, limit, cursor)}

    @staticmethod
    def depth(value, default, min_value):
        try:
            n = default if value is None else int(value)
        except (TypeError, ValueError):
            raise BadRequest('Invalid depth')
        if n < min_value or n > 3:
            raise BadRequest('Depth out of range')
        return n

    def source(self, path, start, end):
        try:
            start, end = int(start), int(end)
        except (TypeError, ValueError):
            raise BadRequest('Invalid source range')
        if not 1 <= start <= end <= start + 59:
            raise BadRequest('Source range out of bounds')
        if not path or path.startswith('/') or '\\' in path or any(part in ('..', '.git', '') for part in path.split('/')):
            raise BadRequest('Invalid path')
        indexed = self.rows('MATCH (f:File {path: $p}) RETURN f.path', {'p': path})
        if not indexed:
            raise queries.NotFound(path)
        candidate = (self.root / path).resolve()
        if candidate == self.root or not candidate.is_relative_to(self.root) or not candidate.is_file():
            raise queries.NotFound(path)
        lines = []
        with candidate.open('r', encoding='utf-8', errors='replace') as stream:
            for number, line in enumerate(stream, 1):
                if number > end:
                    break
                if number >= start:
                    lines.append({'line': number, 'text': line.rstrip('\n\r')[:2000]})
        return {'path': path, 'lines': lines, 'indexed_commit': self.meta.get('repo_commit')}
