#!/usr/bin/env python3
"""Run C-04 acceptance privately on a user's Windows workstation.

Selected files and the model name stay inside the process; no command-line
arguments, network uploads, transcripts or private paths are logged here.
The benchmark output, if requested, is an explicit private user file.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import sys

_MODEL = re.compile(r'[A-Za-z0-9_.:-]{1,70}\Z')
_REPO = Path(__file__).resolve().parent.parent


def _resolved_windows_path_allowed(target, get_drive_type):
    import ntpath
    if target.startswith(('\\\\', '//')) or not ntpath.isabs(target):
        return False
    drive, _ = ntpath.splitdrive(target)
    if not re.fullmatch(r'[A-Za-z]:', drive):
        return False
    return get_drive_type(drive + '\\') in (2, 3)


def _local_path(value):
    if (not isinstance(value, str) or not value.strip()
            or value.startswith(('\\\\', '//'))
            or re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*://', value)):
        return False
    if sys.platform != 'win32':
        return True  # Tests only; main() requires an actual Windows entry point.
    # A mapped drive may look like a local C: path while actually targeting a
    # network share. Resolve junctions first and fail closed on unknown drives.
    try:
        import ctypes
        target = str(Path(value).resolve())
        return _resolved_windows_path_allowed(target, ctypes.windll.kernel32.GetDriveTypeW)
    except (OSError, ValueError, RuntimeError, AttributeError):
        return False


def _private_output(value, *, repo=_REPO):
    """Do not write results over an existing file or inside the code tree."""
    if not _local_path(value):
        return False
    try:
        target = Path(value).resolve()
        return (not target.exists() and target.parent.is_dir()
                and not target.is_relative_to(Path(repo).resolve()))
    except (OSError, ValueError, RuntimeError):
        return False


def _dialog(title, *, save=False):
    import tkinter as tk
    from tkinter import filedialog
    window = tk.Tk()
    try:
        window.withdraw()
        window.attributes('-topmost', True)
        if save:
            return filedialog.asksaveasfilename(parent=window, title=title,
                defaultextension='.jsonl', filetypes=(('JSONL', '*.jsonl'),))
        return filedialog.askopenfilename(parent=window, title=title,
            filetypes=(('ZIP archive', '*.zip'),))
    finally:
        window.destroy()


def local_model_available(model):
    """Query only the literal loopback Ollama endpoint, never a proxy."""
    if not isinstance(model, str) or not _MODEL.fullmatch(model):
        return False
    try:
        from c04_ollama import list_local_models
        result = list_local_models()
        return result.get('status') == 'ready' and model in result.get('models', [])
    except (OSError, ValueError, TypeError, AttributeError):
        return False


def _yes(prompt, ask):
    return ask(prompt).strip().lower() in ('y', 'yes')


def main(*, platform=None, is_tty=None, ask=input, choose=None, save=None,
         load=None, probe=None, replay=None, app=None):
    """Interactive entry point; injection boundaries permit synthetic tests."""
    platform = sys.platform if platform is None else platform
    is_tty = sys.stdin.isatty() if is_tty is None else is_tty
    if platform != 'win32' or sys.version_info < (3, 10) or not is_tty:
        print('Windows의 Python 3.10 이상과 대화형 터미널이 필요합니다.')
        return 2
    choose = choose or (lambda title: _dialog(title))
    save = save or (lambda: _dialog('비공개 평가 결과 저장 위치 선택', save=True))
    probe = probe or local_model_available
    try:
        canonical = choose('SCRIPTURA W-10R 정본 ZIP 선택')
        if not canonical:
            print('정본 선택 취소: 실제 자료 검증 NOT_RUN')
            return 0
        if not _local_path(canonical):
            print('정본은 이 PC의 로컬 ZIP이어야 합니다: FAIL')
            return 1
        if load is None:
            from c03_canonical_local import CanonicalIndex
            load = CanonicalIndex
        load(canonical)
        print('정본 무결성 및 읽기 검증: PASS')

        model = None
        if _yes('설치된 로컬 Ollama 모델을 확인할까요? [y/N]: ', ask):
            candidate = ask('설치된 모델 이름: ').strip()
            if probe(candidate):
                model = candidate
                print('로컬 Ollama 모델 연결: PASS (실제 추론은 아직 NOT_RUN)')
            else:
                print('로컬 모델 연결: NOT_RUN (설치 또는 실행 상태 확인 필요)')
        else:
            print('로컬 모델 연결 및 실제 추론: NOT_RUN')

        if _yes('W-11 감사 ZIP으로 50문항을 점검할까요? [y/N]: ', ask):
            audit = choose('SCRIPTURA W-11 감사 ZIP 선택')
            if not _local_path(audit):
                print('감사 입력 없음: 50문항 NOT_RUN')
            else:
                run_model = bool(model) and _yes('검증된 근거와 로컬 모델로 실제 평가를 실행할까요? [y/N]: ', ask)
                output = None
                if run_model:
                    output = save()
                    if not _private_output(output):
                        print('저장 위치를 확인할 수 없어 실제 모델 평가 NOT_RUN')
                        run_model = False
                        output = None
                if replay is None:
                    from c04_benchmark import replay
                def progress(state):
                    if isinstance(state, dict):
                        done, total = state.get('completed'), state.get('total')
                        if type(done) is int and total == 50 and 1 <= done <= 50 and (done % 5 == 0 or done == 1):
                            print(f'벤치마크 진행: {done}/50')
                result = replay(canonical, audit, model=model if run_model else None,
                                output=output, progress=progress)
                # Only bounded numeric/status aggregates leave this wrapper.
                if not isinstance(result, dict):
                    raise ValueError('invalid_summary')
                count = result.get('questions')
                called = result.get('model_called')
                responded = result.get('model_responded')
                unrun = result.get('not_run')
                if (count != 50 or any(type(x) is not int or not 0 <= x <= 50
                                       for x in (called, responded, unrun))
                        or responded > called or called + unrun > count
                        or (not run_model and (called != 0 or responded != 0))):
                    raise ValueError('invalid_summary')
                print(f'평가 문항: {count}, HTTP 호출 시도: {called}, '
                      f'모델 응답: {responded}, 미실행: {unrun}')
                print('호출 시도는 실제 모델 응답 또는 학술적 정답의 증거가 아닙니다.')
                print('독립 학술 채점: NOT_RUN (자동 인용 검증은 정답 판정이 아님)')
        else:
            print('실제 50문항 평가: NOT_RUN')

        if _yes('같은 정본으로 연구 탐색기를 열까요? [y/N]: ', ask):
            if app is None:
                from j2_private_preview import main as app
            args = ['--canonical', canonical]
            if model is not None and _yes('이 세션에서 로컬 모델 기능을 켤까요? [y/N]: ', ask):
                args.extend(['--local-model', model])
            return app(args)
        return 0
    except (KeyboardInterrupt, EOFError):
        print('수용 절차가 취소됐습니다. 미실행 항목은 NOT_RUN입니다.')
        return 0
    except Exception:
        # Exceptions can contain private paths, IDs, records, or user input.
        print('수용 절차를 완료하지 못했습니다. 정본·감사 무결성과 설치 상태를 확인하세요.')
        print('확인되지 않은 실제 모델 평가 및 독립 채점: NOT_RUN')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
