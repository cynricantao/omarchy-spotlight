"""Ownership and permission checks for user-local settings and cache files."""
import os
from pathlib import Path
import stat


def check_parents(path):
    path = Path(path)
    if not path.is_absolute():
        raise ValueError('Storage paths must be absolute.')
    for parent in reversed(path.parents):
        try:
            info = parent.lstat()
        except FileNotFoundError:
            continue
        if not stat.S_ISDIR(info.st_mode):
            raise ValueError('Storage cannot traverse a symlink or non-directory parent.')
        # Root-owned sticky temporary roots are safe for owned private children.
        sticky_root = info.st_uid == 0 and bool(info.st_mode & stat.S_ISVTX)
        if info.st_mode & 0o022 and not sticky_root:
            raise ValueError('Storage cannot traverse a group/world-writable parent.')


def require_directory(path, create=False, private=False):
    path = Path(path)
    check_parents(path)
    if create:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
        raise ValueError('Storage directory must be an owned directory, not a symlink.')
    if info.st_mode & (0o077 if private else 0o022):
        raise ValueError('Storage permissions are too broad; no permissions were changed.')
    return path


def validate_fd(fd, private=False):
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
        raise ValueError('Storage file must be owned and regular.')
    if info.st_mode & (0o077 if private else 0o022):
        raise ValueError('Storage file permissions are too broad; no permissions were changed.')
    return info
