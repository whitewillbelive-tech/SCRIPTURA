"""Start SCRIPTURA with the user's LOCAL W10R canonical ZIP, without argv leaks.

Opt-in model processing is confined to a local Ollama server on 127.0.0.1.
"""
import re
import sys


def _select_archive():
    import tkinter as tk
    from tkinter import filedialog
    window = tk.Tk()
    try:
        window.withdraw()
        window.attributes('-topmost', True)
        return filedialog.askopenfilename(parent=window,
            title='SCRIPTURA W10R 최신 통합 정본 ZIP 선택',
            filetypes=(('ZIP archive', '*.zip'),))
    finally:
        window.destroy()


def _select_model(ask, discover):
    """Show only sanitized installed names; failure leaves the model disabled."""
    result = discover()
    models = result.get('models', []) if isinstance(result, dict) and result.get('status') == 'ready' else []
    if isinstance(models, list):
        models = [model for model in models if isinstance(model, str)
                  and re.fullmatch(r'[A-Za-z0-9_.:-]{1,70}', model)]
    if not isinstance(models, list) or not models:
        print('사용 가능한 로컬 모델을 확인하지 못해 모델 없이 시작합니다.')
        return None
    for index, model in enumerate(models, 1):
        print(f'{index}. {model}')
    choice = ask('모델 번호 또는 직접 입력 m (취소: 0): ').strip()
    if choice.lower() == 'm':
        name = ask('설치된 모델 이름: ').strip()
        if name in models:
            return name
        print('설치된 모델을 확인하지 못해 모델 없이 시작합니다.')
        return None
    if not choice.isdecimal() or not 1 <= int(choice) <= len(models):
        print('모델 선택을 건너뛰고 모델 없이 시작합니다.')
        return None
    return models[int(choice) - 1]


def main(*, platform=None, is_tty=None, chooser=None, ask=input, discover=None, app=None, local_path=None):
    platform = sys.platform if platform is None else platform
    is_tty = sys.stdin.isatty() if is_tty is None else is_tty
    if platform != 'win32':
        print('Windows 전용 파일 선택 실행기입니다.', file=sys.stderr)
        return 2
    if sys.version_info < (3,10) or not is_tty:
        print('Python 3.10 이상 및 대화형 터미널이 필요합니다.', file=sys.stderr)
        return 2
    try:
        archive = (chooser or _select_archive)()
        if not archive:
            return 0
        if local_path is None:
            from c04_windows_acceptance import _local_path as local_path
        if not local_path(archive):
            print('정본은 이 PC의 로컬 ZIP이어야 합니다.', file=sys.stderr)
            return 1
        print('정본 파일은 비공개 로컬에서만 읽습니다.')
        print('로컬 AI는 별도 설치된 Ollama를 사용하는 경우에만 활성화됩니다.')
        use = ask('이 PC의 Ollama 모델을 연결할까요? [y/N]: ').strip().lower()
        args = ['--canonical', archive]
        if use in ('y','yes'):
            if discover is None:
                from c04_ollama import list_local_models as discover
            model = _select_model(ask, discover)
            if model:
                args += ['--local-model', model]
        if app is None:
            from j2_private_preview import main as app
        return app(args)
    except (EOFError,KeyboardInterrupt):
        print('선택이 취소되었습니다.')
        return 0
    except Exception:
        print('정본 연구 화면을 시작할 수 없습니다. 입력 파일과 설치 상태를 확인하세요.', file=sys.stderr)
        return 1

if __name__=='__main__':
    raise SystemExit(main())
