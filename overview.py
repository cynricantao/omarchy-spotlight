#!/usr/bin/env python3
"""Read-only landing view; reuse existing discovery and activation contracts."""
import json
from pathlib import Path
import backend


def overview(home=None):
    home = Path.home() if home is None else Path(home)
    installed = backend.apps(limit=10000)
    preferred = ('visual studio code', 'vivaldi', 'spotify', 'obsidian', 'hermes', 'files', 'ghostty')
    installed.sort(key=lambda x: (preferred.index(x['title'].casefold()) if x['title'].casefold() in preferred else len(preferred), x['title'].casefold()))
    featured, seen = [], set()
    for app in installed:
        name = app['title'].casefold()
        if name not in seen:
            featured.append(app)
            seen.add(name)
        if len(featured) == 4:
            break
    folders, status = [], ''
    for name in ('Documents', 'Downloads', 'Projects'):
        candidates, status = backend.file_results(name)
        target = str(home/name)
        folders.extend(x for x in candidates if x['value'] == target and x['kind'] == 'folder' and Path(target).is_dir())
    return {'query':'', 'items':[backend.quick_actions()[0]]+featured+folders, 'status':status, 'error':''}

if __name__ == '__main__':
    try:
        result = overview()
    except Exception:
        result = {'query':'', 'items':backend.quick_actions(), 'status':'Home suggestions unavailable', 'error':''}
    print(json.dumps(result, ensure_ascii=True))
