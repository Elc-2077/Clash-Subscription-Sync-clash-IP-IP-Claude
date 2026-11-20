"""One-time updater helpers. Never controls Clash or Windows network settings."""
import ast,os,sys
from pathlib import Path
import psutil

def validate_source(root):
    for name in ('sync.py','sync_model.py'):
        ast.parse((Path(root)/name).read_text(encoding='utf-8-sig'))

def is_worker(info,target):
    if (info.get('name') or '').lower() not in ('python.exe','pythonw.exe'):return False
    args=info.get('cmdline') or []
    script=next((arg for arg in args[1:] if not arg.startswith('-')),'')
    return bool(script) and os.path.normcase(os.path.abspath(script))==os.path.normcase(os.path.abspath(target))

def stop_workers(target):
    # Read names first. Asking process_iter for every system command line can
    # raise native WinError 998 before it yields a process on some Windows builds.
    for pid in psutil.pids():
        if pid==os.getpid():continue
        try:
            process=psutil.Process(pid)
            name=process.name()
            if name.lower() not in ('python.exe','pythonw.exe'):continue
            info={'name':name,'cmdline':process.cmdline()}
        except (psutil.Error,OSError):
            # Unreadable or exited unrelated processes must not break an update.
            continue
        if not is_worker(info,target):continue
        try:
            for child in reversed(process.children(recursive=True)):
                try:child.kill()
                except psutil.NoSuchProcess:pass
            process.kill();process.wait(timeout=5)
        except psutil.NoSuchProcess:pass

def clear_bytecode(root):
    cache=Path(root)/'__pycache__'
    for pattern in ('sync.*.pyc','sync_model.*.pyc'):
        for file in cache.glob(pattern):file.unlink()

if __name__=='__main__':
    actions={'validate-source':validate_source,'stop-workers':stop_workers,'clear-bytecode':clear_bytecode}
    actions[sys.argv[1]](sys.argv[2])
