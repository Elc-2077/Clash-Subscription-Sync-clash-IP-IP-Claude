"""Print non-secret setup metadata, never the recipient's node credentials."""
import json,os,sys
from pathlib import Path
from setup_config import read_user

def discover(path):
    value,_=read_user(path)
    roaming=Path(os.environ['APPDATA']);local=Path(os.environ['LOCALAPPDATA']);programs=Path(os.environ.get('ProgramFiles',r'C:\Program Files'))
    candidates=[Path(value['clash_data_directory']).expanduser()] if value.get('clash_data_directory') else [roaming/'io.github.clash-verge-rev.clash-verge-rev']
    base=next((p.resolve() for p in candidates if (p/'profiles.yaml').is_file() and (p/'config.yaml').is_file()),None)
    if base is None:raise ValueError('Clash data directory was not found; run Clash and import your airport subscription, or set clash_data_directory')
    cores=[Path(value['clash_core_path']).expanduser()] if value.get('clash_core_path') else [programs/'Clash Verge'/'verge-mihomo.exe',local/'Programs'/'Clash Verge'/'verge-mihomo.exe']
    core=next((p.resolve() for p in cores if p.is_file()),None)
    if core is None:raise ValueError('Mihomo core was not found; set clash_core_path to verge-mihomo.exe')
    interface=value.get('physical_interface','')
    if not isinstance(interface,str):raise ValueError('physical_interface must be a string')
    pythonw=Path(sys.executable).with_name('pythonw.exe')
    if not pythonw.is_file():raise ValueError('pythonw.exe was not found next to the selected Python interpreter')
    return {'base':str(base),'core':str(core),'python':sys.executable,'pythonw':str(pythonw),'interface':interface,
            'enable_island':value.get('enable_island',False),'fallback_to_airport':value.get('fallback_to_airport',False)}

if __name__=='__main__':
    try:print(json.dumps(discover(sys.argv[1]),ensure_ascii=True))
    except Exception as exc:
        print('CONFIG ERROR: '+(str(exc) if isinstance(exc,ValueError) else type(exc).__name__),file=sys.stderr);sys.exit(1)
