#!/usr/bin/env python3
"""Choose a private ZIP on Windows, then start the existing local preview.

The selected path stays in this process: it is never written to the command
line, an environment variable, a file, or an application log by this wrapper.
The operating system's file picker may retain its own recent-file history.
"""
from __future__ import annotations

import os
import re
import sys


def _choose_archive(*, increment=False):
    # Import lazily so that command-line and non-Windows use do not require Tk.
    import tkinter as tk
    from tkinter import filedialog

    window = tk.Tk()
    try:
        window.withdraw()
        window.attributes('-topmost', True)
        return filedialog.askopenfilename(
            parent=window,
            title=('SCRIPTURA D-14~D-16 증분 ZIP 선택' if increment else
                   'SCRIPTURA 기준 연구 ZIP 선택 (D-8, D-9, D-10, D-12 또는 D-13)'),
            filetypes=(('ZIP archive', '*.zip'),),
        )
    finally:
        window.destroy()


def _is_d13_archive(path):
    """Recognize the pinned D13 bytes without printing a path or a digest."""
    import hashlib
    import hmac
    from k37_work_archive_compat import D13_SHA, read_local_unchanged
    try:
        return hmac.compare_digest(hashlib.sha256(read_local_unchanged(path)).hexdigest(), D13_SHA)
    except Exception:
        return False


def main(*, platform=None, chooser=None, increment_chooser=None, is_d13=None, runner=None, version=None, is_tty=None):
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
        args = ['--archive', selected]
        if (is_d13 or _is_d13_archive)(selected):
            print('D-13 정본 확인. 다음 선택창에서 D-14~D-16 증분 ZIP을 선택하세요.')
            increment = (increment_chooser or (lambda: _choose_archive(increment=True)))()
            if not increment:
                print('증분 자료 선택을 취소했습니다.')
                return 0
            if not isinstance(increment, str):
                print('선택한 증분 자료를 확인할 수 없습니다.', file=sys.stderr)
                return 1
            args.extend(['--increment', increment])
        elif re.search(r'(?:^|[_-])d13(?=[_.-]|$)', os.path.basename(selected), re.I):
            # Never silently misclassify a D13-named but unreadable archive
            # as a historic D8/D9/D10/D12 single-file input.
            print('D-13으로 지정한 파일을 확인할 수 없습니다. 정본 ZIP을 선택했는지 확인하세요.', file=sys.stderr)
            return 1
        # No subprocess: chosen paths and the later secret are not added to argv.
        return runner(args)
    except Exception:
        # A loader or interpreter failure must not expose a selected path.
        print('로컬 탐색기를 시작하지 못했습니다. 설치 상태를 확인하세요.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
