"""Resolve the local data folder independently of the application's install path."""
import os
from pathlib import Path


def data_directory(root):
    root=Path(root)
    override=os.environ.get('SCROLL_STUDIO_DATA','').strip()
    if override:
        path=Path(override).expanduser()
    else:
        location=root/'data-location.txt'
        if not location.exists():return root/'data'
        configured=location.read_text('utf-8-sig').strip()
        if not configured:raise ValueError('data-location.txt 中的数据目录为空，请填写有效路径')
        path=Path(configured).expanduser()
    return path if path.is_absolute() else root/path
