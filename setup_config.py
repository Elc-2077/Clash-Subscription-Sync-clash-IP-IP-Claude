"""First installation uses only the recipient's configuration and subscription."""
import copy,datetime,ipaddress,json,os,socket,subprocess,time,urllib.request,uuid
from pathlib import Path
import sync
from sync_model import BOOT,entries,overlay,enhancement,public4

SUPPORTED={'trojan','ss','vmess','vless','socks5','tuic','hysteria2','anytls'}
PLACEHOLDERS=('YOUR_','REPLACE_','CHANGE_ME')

def node_check(value,label):
    if not isinstance(value,dict) or value.get('type') not in SUPPORTED:
        raise ValueError(label+': unsupported or missing protocol')
    if any(marker in json.dumps(value,ensure_ascii=True) for marker in PLACEHOLDERS):
        raise ValueError(label+': replace all YOUR_ placeholders with your own node information')
    result=copy.deepcopy(value)
    public4(result.get('server',''))
    if not isinstance(result.get('port'),int) or isinstance(result['port'],bool) or not 1<=result['port']<=65535:
        raise ValueError(label+': port must be an integer from 1 to 65535')
    if result.get('udp') is not True:raise ValueError(label+': set udp: true and use a server with actual UDP support')
    prohibited={'dialer-proxy','interface-name','routing-mark','plugin','plugin-opts','certificate','private-key','ca','ip-version'}
    if prohibited.intersection(result):raise ValueError(label+': remove custom routing, external plugin or certificate file fields')
    kind=result['type']
    if kind in ('trojan','ss','tuic','hysteria2','anytls') and not result.get('password'):raise ValueError(label+': missing password')
    if kind in ('vmess','vless','tuic'):
        try:uuid.UUID(result.get('uuid',''))
        except (ValueError,AttributeError):raise ValueError(label+': invalid UUID')
    if kind=='ss' and not result.get('cipher'):raise ValueError(label+': missing Shadowsocks cipher')
    result.pop('name',None)
    return result

def read_user(path):
    value=sync.load(path)
    if not isinstance(value,dict):raise ValueError('user-config.yaml must contain a YAML mapping')
    for flag in ('enable_island','fallback_to_airport'):
        if flag in value and not isinstance(value[flag],bool):raise ValueError(flag+': use YAML true or false')
    expected=public4(value.get('expected_exit_ipv4',''))
    final=node_check(value.get('final_exit'),'final_exit')
    bootstrap=node_check(value.get('bootstrap'),'bootstrap')
    return value,{'expected_ipv4':expected,'final':final,'bootstrap':bootstrap}

def free_port():
    with socket.socket() as listener:listener.bind(('127.0.0.1',0));return listener.getsockname()[1]

def resolve_initial(raw,seed,settings,root):
    """Launch a temporary isolated core. Does not enable TUN or start the Clash app."""
    port=free_port();boot=copy.deepcopy(seed['bootstrap']);boot.update(name=BOOT,**{'interface-name':seed['interface']})
    cf=['https://1.1.1.1/dns-query#'+BOOT,'https://1.0.0.1/dns-query#'+BOOT]
    config={'mixed-port':port,'external-controller':'','allow-lan':False,'mode':'global','ipv6':False,'log-level':'silent',
            'interface-name':seed['interface'],'tun':{'enable':False},'profile':{'store-selected':False},
            'proxies':[boot],'proxy-groups':[{'name':'GLOBAL','type':'select','proxies':[BOOT]}],
            'rules':['MATCH,GLOBAL'],'dns':{'enable':True,'listen':'127.0.0.1:0','ipv6':False,'nameserver':cf,'default-nameserver':cf}}
    folder=root/'data'/'first-lookup';folder.mkdir(exist_ok=True)
    sync.atomic(folder/'config.yaml',sync.dump(config))
    with open(os.devnull,'w') as null:
        process=subprocess.Popen([settings['core'],'-d',str(folder),'-f',str(folder/'config.yaml')],stdout=null,stderr=null,creationflags=0x08000000)
        try:
            for _ in range(50):
                if process.poll() is not None:raise ValueError('Bootstrap proxy core could not start')
                try:
                    with socket.create_connection(('127.0.0.1',port),.2):break
                except OSError:time.sleep(.1)
            else:raise ValueError('Bootstrap proxy startup timed out')
            proxy=urllib.request.build_opener(urllib.request.ProxyHandler({'https':'http://127.0.0.1:'+str(port)}))
            addresses=sync.resolve([p['server'] for p in entries(raw)],opener=proxy)
            if not any(addresses.values()):raise ValueError('Bootstrap proxy could not resolve airport endpoints through Cloudflare')
            return addresses
        finally:
            process.terminate()
            try:process.wait(timeout=3)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=3)

def rollback_initial():
    root=Path(__file__).resolve().parent
    path=root/'data'/'installation.json'
    if not path.exists():return
    report=sync.read(path);base=Path(sync.settings()['base']);backup=Path(report['backup'])
    manifest=sync.read(backup/'manifest.json')
    for name,existed in manifest.items():
        relative=Path(name)
        if relative.is_absolute() or '..' in relative.parts:raise ValueError('Invalid backup manifest')
        target=base/relative
        if existed:target.write_bytes((backup/relative).read_bytes())
        elif target.exists():target.unlink()

def initialize():
    root=Path(__file__).resolve().parent;settings=sync.settings();base=Path(settings['base'])
    user,seed=read_user(root/'user-config.yaml');seed['interface']=settings['interface']
    profiles=sync.load(base/'profiles.yaml')
    item=next((i for i in profiles.get('items',[]) if i.get('uid')==profiles.get('current')),None)
    if not item or item.get('type')!='remote':raise ValueError('Import and select your own remote airport subscription in Clash before setup')
    relative=Path(item['file'])
    if relative.is_absolute() or '..' in relative.parts:raise ValueError('Subscription file must be inside Clash profiles directory')
    raw=sync.load(base/'profiles'/relative);originals=entries(raw)
    addresses=resolve_initial(raw,seed,settings,root)
    preferred=next((s.get('now') for s in item.get('selected',[]) if s.get('name')=='GLOBAL' and s.get('now') in {p['name'] for p in originals}),originals[0]['name'])
    value=overlay(raw,seed,addresses,preferred,True,user.get('fallback_to_airport',False))
    script=enhancement(value)
    if not any(i.get('uid')=='SubSync' for i in profiles['items']):profiles['items'].append({'uid':'SubSync','type':'script','name':'Subscription Sync · Fixed Exit','file':'SubSync.js'})
    # Only the current remote profile is enrolled. New airport subscriptions must
    # select SubSync in their script options; never silently modify other profiles.
    item.setdefault('option',{})['script']='SubSync'
    item['selected']=[{'name':'GLOBAL','now':value['proxy-groups'][0]['proxies'][0]}]
    basic=sync.load(base/'config.yaml')
    for key in ('tun','mode','ipv6','interface-name'):basic[key]=value[key]
    merge=sync.load(base/'profiles'/'Merge.yaml') if (base/'profiles'/'Merge.yaml').exists() else {}
    for key in ('tun','dns','mode','ipv6','interface-name'):merge[key]=value[key]
    verge=sync.load(base/'verge.yaml');verge['enable_builtin_enhanced']=False;verge['enable_dns_settings']=True;verge['enable_tun_mode']=True
    changes={base/'profiles'/'SubSync.js':script,base/'profiles'/'Script.js':script,
             base/'config.yaml':sync.dump(basic),base/'clash-verge.yaml':sync.dump(dict(basic,**value)),
             base/'profiles'/'Merge.yaml':sync.dump(merge),base/'dns_config.yaml':sync.dump({'dns':value['dns']}),
             base/'verge.yaml':sync.dump(verge),base/'profiles.yaml':sync.dump(profiles)}
    sync.atomic(root/'data'/'initial.yaml',changes[base/'clash-verge.yaml'])
    test=subprocess.run([settings['core'],'-t','-d',str(base),'-f',str(root/'data'/'initial.yaml')],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=25)
    if test.returncode:raise ValueError('Mihomo rejected the generated configuration; no Clash settings changed')
    backup=base/'repair-backups'/('subscription-sync-share-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f'));backup.mkdir(parents=True,exist_ok=False)
    previous={p:p.read_bytes() if p.exists() else None for p in changes}
    for path,content in previous.items():
        if content is not None:
            saved=backup/path.relative_to(base);saved.parent.mkdir(parents=True,exist_ok=True);saved.write_bytes(content)
    sync.save(backup/'manifest.json',{str(p.relative_to(base)):data is not None for p,data in previous.items()})
    report={'ok':False,'backup':str(backup),'initial_nodes':len(value['proxy-groups'][0]['proxies']),'skipped_nodes':len(originals)-len(value['proxy-groups'][0]['proxies']),
            'expected_exit_ipv4':seed['expected_ipv4'],'firewall_changes':False,'startup_interception':False}
    sync.save(root/'data'/'installation.json',report)
    sync.save(root/'data'/'seed.json',seed)
    try:
        for path,text in changes.items():sync.atomic(path,text)
    except Exception:
        for path,data in previous.items():
            if data is None:
                if path.exists():path.unlink()
            else:path.write_bytes(data)
        raise
    report['ok']=True;sync.save(root/'data'/'installation.json',report)
    print('Initial configuration saved. Nodes: '+str(report['initial_nodes'])+'. Backup created locally.')

if __name__=='__main__':
    import sys
    try:
        if '--rollback' in sys.argv:rollback_initial();print('Previous Clash configuration restored.')
        else:initialize()
    except Exception as exc:
        # Raw network/server responses and user proxy credentials never enter stdout.
        print('SETUP ERROR: '+(str(exc) if isinstance(exc,ValueError) else type(exc).__name__));sys.exit(1)
