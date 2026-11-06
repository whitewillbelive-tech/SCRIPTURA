#!/usr/bin/env python3
"""Choose a private ZIP on Windows, then start the existing local preview.

The selected path stays in this process: it is never written to the command
line, an environment variable, a file, or an application log by this wrapper.
The operating system's file picker may retain its own recent-file history.
"""
from __future__ import annotations

import sys


def _choose_archive():
    # Import lazily so that command-line and non-Windows use do not require Tk.
    import tkinter as tk
    from tkinter import filedialog

    window = tk.Tk()
    try:
        window.withdraw()
        window.attributes('-topmost', True)
        return filedialog.askopenfilename(
            parent=window,
            title='SCRIPTURA D-8 또는 D-9 연구 ZIP 선택',
            filetypes=(('ZIP archive', '*.zip'),),
        )
    finally:
        window.destroy()


def main(*, platform=None, chooser=None, runner=None, version=None, is_tty=None):
    """Launch interactively. Injectable boundaries are used by synthetic tests."""
    platform = sys.platform if platform is None else platform
    version = sys.version_info if version is None else version
    is_tty = sys.stdin.isatty() if is_tty is None else is_tty
    if platform != 'win32':
        print('이 파일 선택 실행기는 Windows에서만 사용할 수 있습니다.', file=sys.stderr)
        return 2
    if version < (3, 10):
        print('Python 3.10 이상이 필요합니다.', file=sys.stderr)
        return 2
    if not is_tty:
        print('세션 비밀의 숨김 입력을 위해 일반 터미널이 필요합니다.', file=sys.stderr)
        return 2
    try:
        selected = (chooser or _choose_archive)()
    except Exception:
        # Never expose native dialog exceptions: they may contain a user path.
        print('파일 선택기를 열 수 없습니다. Python의 Tcl/Tk 설치를 확인하세요.', file=sys.stderr)
        return 1
    if not selected:
        print('자료 선택을 취소했습니다.')
        return 0
    if not isinstance(selected, str):
        print('선택한 자료를 확인할 수 없습니다.', file=sys.stderr)
        return 1
    try:
        if runner is None:
            from j2_private_preview import main as runner
        # No subprocess: the chosen path and later secret are not added to argv.
        return runner(['--archive', selected])
    except Exception:
        # A loader or interpreter failure must not expose a selected path.
        print('로컬 탐색기를 시작하지 못했습니다. 설치 상태를 확인하세요.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
