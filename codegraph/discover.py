"""Stage 0: walk the repo and classify files."""
from __future__ import annotations

import os

SKIP_DIRS = {".git", ".hg", ".svn", "node_modules", "build", "dist", ".codegraph", "__pycache__",
             ".venv", "venv", "env", ".tox", ".mypy_cache", ".pytest_cache", ".gradle", ".idea", "target", "out"}

LANG_BY_EXT = {
    ".py": "python", ".java": "java", ".kt": "kotlin", ".kts": "kotlin", ".sh": "shell",
    ".smali": "smali", ".js": "javascript", ".ts": "typescript", ".go": "go", ".rs": "rust",
    ".c": "c", ".h": "c", ".cpp": "cpp", ".md": "markdown", ".json": "json", ".yml": "yaml",
    ".yaml": "yaml", ".xml": "xml", ".toml": "toml", ".tsv": "tsv", ".txt": "text",
}
PARSED_LANGS = {"python", "java"}


def discover(root: str):
    """Yield (relpath, lang) for every file under root, sorted."""
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.endswith(".egg-info"))
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            if os.path.islink(full):
                continue
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            ext = os.path.splitext(fn)[1].lower()
            out.append((rel, LANG_BY_EXT.get(ext, "other")))
    return sorted(out)
