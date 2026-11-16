"""Start SCRIPTURA with the user's LOCAL W10R canonical ZIP, without argv leaks.

Opt-in model processing is confined to a local Ollama server on 127.0.0.1.
"""
import getpass
import sys

def main():
    if sys.platform != 'win32':
        print('Windows 전용 파일 선택 실행기입니다.', file=sys.stderr)
        return 2
    if sys.version_info < (3,10) or not sys.stdin.isatty():
        print('Python 3.10 이상 및 대화형 터미널이 필요합니다.', file=sys.stderr)
        return 2
    try:
        import tkinter as tk
        from tkinter import filedialog
        window=tk.Tk()
        window.withdraw()
        window.attributes('-topmost',True)
        try:
            archive=filedialog.askopenfilename(
                parent=window,title='SCRIPTURA W10R 최신 통합 정본 ZIP 선택',
                filetypes=(('ZIP archive','*.zip'),))
        finally:
            window.destroy()
        if not archive:
            return 0
        print('정본 파일은 비공개 로컬에서만 읽습니다.')
        print('로컬 AI는 별도 설치된 Ollama를 사용하는 경우에만 활성화됩니다.')
        use=input('이 PC의 Ollama 모델을 연결할까요? [y/N]: ').strip().lower()
        args=['--canonical',archive]
        if use in ('y','yes'):
            model=input('이미 설치된 Ollama 모델 이름 (예: qwen2.5:3b): ').strip()
            import re
            if not re.fullmatch(r'[A-Za-z0-9_.:-]{1,70}',model):
                print('모델 이름이 올바르지 않습니다.', file=sys.stderr)
                return 1
            args+=['--local-model',model]
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
