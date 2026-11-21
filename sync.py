"""Subscription synchronization only. Never blocks traffic or controls the Clash app."""
import concurrent.futures, copy, ctypes, datetime, hashlib, http.client, ipaddress, json, os
import subprocess, sys, time, urllib.parse, urllib.request
from pathlib import Path
import psutil, yaml
from sync_model import BOOT, PREFIX, FIXED_PREFIX, entries, overlay, enhancement, stamp, public4, complete_addresses

ROOT=Path(__file__).resolve().parent
DATA=ROOT/'data'
STATE_POLL_SECONDS=60
STATE_READ_TIMEOUT=8

def observation(state,**fields):
    value={'state':state,'observed_at':datetime.datetime.now().astimezone().isoformat(),
           'observed_at_unix':time.time(),'poll_interval_seconds':STATE_POLL_SECONDS,**fields}
    save(DATA/'current-state.json',value)
    destination=settings().get('report_dir')
    if destination:
        try:save(Path(destination)/'current-state.json',value)
        except OSError:pass
    return value

def read_core_state():
    # This read-only child has its own parent deadline, independent of reloads.
    if not running():return dict(state='STOPPED',selected=None,source='clash-process-not-running')
    try:
        proxies=api('GET','/proxies').get('proxies',{})
        runtime=api('GET','/configs')
        selected=proxies.get('GLOBAL',{}).get('now')
        if not selected:raise ValueError('No GLOBAL selection')
        configured=load(Path(settings()['base'])/'clash-verge.yaml')
        nodes={n['name']:n for n in configured.get('proxies',[])}
        selected_group=proxies.get(selected,{})
        active=selected_group.get('now',selected)
        final=nodes.get(active,{})
        fixed=nodes.get(FIXED_PREFIX+selected,nodes.get(selected,{}))
        if active.startswith(PREFIX):route_kind='airport-fallback'
        elif final.get('dialer-proxy'):route_kind='fixed-exit'
        else:route_kind='other'
        ingress=nodes.get(final.get('dialer-proxy'),{})
        if route_kind=='airport-fallback':ingress=final
        # The server is configuration data, never a claimed public-exit test.
        return dict(state='RUNNING',source='live-core-api',selected=selected,
                           mode=runtime.get('mode'),tun_enabled=runtime.get('tun',{}).get('enable'),
                           ipv6=runtime.get('ipv6'),entry_protocol=ingress.get('type'),
                           final_protocol=final.get('type'),configured_exit_server=fixed.get('server'),active_server=final.get('server'),
                           selected_fixed_chain=bool(final.get('dialer-proxy')),
                           active_proxy=active,active_route=route_kind,
                           fallback_to_airport=settings().get('fallback_to_airport',False),
                           public_exit_verified=False)
    except Exception as exc:
        return dict(state='ERROR',source='live-core-api',selected=None,error=type(exc).__name__)

def observe_once():
    value=read_core_state();state=value.pop('state')
    return observation(state,**value)
def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def load(path):return yaml.safe_load(Path(path).read_text(encoding='utf-8-sig')) or {}
def dump(value):return yaml.safe_dump(value,allow_unicode=True,sort_keys=False)
def atomic(path,text):
    p=Path(path);tmp=p.with_name(p.name+'.subsync-new');tmp.write_text(text,encoding='utf-8');os.replace(str(tmp),str(p))
def save(path,value):atomic(path,json.dumps(value,ensure_ascii=True,indent=2))
def settings():return read(ROOT/'settings.json')
def status(state,detail='',**fields):
    value={'state':state,'detail':detail,'time':datetime.datetime.now().astimezone().isoformat(),**fields}
    save(DATA/'status.json',value)
    destination=settings().get('report_dir')
    if destination:
        try:save(Path(destination)/'sync-status.json',value)
        except OSError:pass
def log(message):
    with (DATA/'sync.log').open('a',encoding='utf-8') as stream:stream.write(datetime.datetime.now().astimezone().isoformat()+' '+message+'\n')
def running():
    for process in psutil.process_iter(['name']):
        if (process.info.get('name') or '').lower()=='clash-verge.exe':return True
    return False
def profile():
    base=Path(settings()['base']);profiles=load(base/'profiles.yaml')
    item=next(x for x in profiles['items'] if x.get('uid')==profiles.get('current'))
    if item.get('type')!='remote':raise ValueError('请选择远程机场订阅')
    raw=load(base/'profiles'/Path(item['file']).name);entries(raw)
    return item,raw

def api(method,path,body=None):
    # This entire worker has a parent watchdog deadline; even a stalled pipe read
    # cannot stop the daemon, original application or local network.
    config=load(Path(settings()['base'])/'config.yaml')
    pipe=open(config.get('external-controller-pipe',r'\\.\pipe\verge-mihomo'),'r+b',buffering=0)
    class PipeSocket:
        def makefile(self,*args,**kwargs):return pipe
    payload=json.dumps(body).encode() if body is not None else b''
    header=('%s %s HTTP/1.1\r\nHost: localhost\r\nAuthorization: Bearer %s\r\nContent-Type: application/json\r\nContent-Length: %d\r\nConnection: close\r\n\r\n'%(method,path,config.get('secret',''),len(payload))).encode()
    try:
        pipe.write(header+payload);response=http.client.HTTPResponse(PipeSocket());response.begin();content=response.read()
        if response.status>=300:raise ValueError('Core API HTTP '+str(response.status))
        return json.loads(content) if content else {}
    finally:pipe.close()

def preferred(current):
    proxies=current.get('proxies',{});name=proxies.get('GLOBAL',{}).get('now','')
    if name not in ('出口选择','FIXED-EXIT','') and not name.startswith('__'):return name
    airport=proxies.get('机场入口',{}).get('now','')
    if airport.startswith('__AIRPORT__'):return airport[len('__AIRPORT__'):]
    return ''

def resolve(hosts,opener=None):
    result={};pending=[]
    for host in sorted(set(hosts)):
        try:result[host]=[public4(host)]
        except ValueError:pending.append(host)
    port=int(load(Path(settings()['base'])/'config.yaml').get('mixed-port',7897))
    op=opener or urllib.request.build_opener(urllib.request.ProxyHandler({'https':'http://127.0.0.1:'+str(port)}))
    def query(host):
        for attempt in range(2):
            try:
                request=urllib.request.Request('https://1.1.1.1/dns-query?'+urllib.parse.urlencode({'name':host,'type':'A'}),headers={'Accept':'application/dns-json'})
                with op.open(request,timeout=5) as response:answer=json.load(response)
                values=sorted({public4(a['data']) for a in answer.get('Answer',[]) if a.get('type')==1})
                if answer.get('Status')==0 and values:return host,values
            except Exception:pass
        return host,[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        for host,addresses in pool.map(query,pending):result[host]=addresses
    return result

def routes(action,addresses=None):
    if addresses is not None:save(DATA/'endpoints.json',{'addresses':sorted(set(addresses))})
    command=[str(Path(os.environ['SystemRoot'])/'System32'/'WindowsPowerShell'/'v1.0'/'powershell.exe'),'-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(ROOT/'Routes.ps1'),'-Action',action]
    result=subprocess.run(command,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=30,creationflags=0x08000000)
    if result.returncode:raise ValueError('Endpoint route '+action+' failed')

def sync_once():
    if not running():return
    st=settings();base=Path(st['base']);item,raw=profile();before_stamp=stamp(item['uid'],raw)
    choice=preferred(api('GET','/proxies'))
    source_nodes=entries(raw)
    hosts=[n['server'] for n in source_nodes]
    fresh=resolve(hosts)
    cache_path=DATA/'endpoint-cache.json'
    cache=read(cache_path) if cache_path.exists() else {}
    addresses,new_cache,cached_hosts,unresolved_hosts=complete_addresses(hosts,fresh,cache,time.time())
    fallback_enabled=st.get('fallback_to_airport',False)
    value=overlay(raw,read(DATA/'seed.json'),addresses,choice,load(base/'verge.yaml').get('enable_tun_mode',True),fallback_enabled)
    candidate=dict(load(base/'config.yaml'),**value)
    atomic(DATA/'candidate.yaml',dump(candidate))
    checked=subprocess.run([st['core'],'-t','-d',str(base),'-f',str(DATA/'candidate.yaml')],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=20,creationflags=0x08000000)
    if checked.returncode:raise ValueError('Mihomo rejected subscription candidate')
    new_item,new_raw=profile()
    if not running() or stamp(new_item['uid'],new_raw)!=before_stamp:raise ValueError('Subscription changed while preparing; retry later')
    # Host routes affect only prepared proxy endpoints. No default route, firewall,
    # DNS adapter setting or application process is changed by this tool.
    routes('Add',[p.split('/')[0] for p in value['tun']['route-exclude-address']])
    changes={base/'profiles'/'Script.js':enhancement(value),base/'profiles'/'SubSync.js':enhancement(value)}
    basic=load(base/'config.yaml')
    for key in ('tun','mode','ipv6','interface-name'):basic[key]=value[key]
    changes[base/'config.yaml']=dump(basic)
    merge=load(base/'profiles'/'Merge.yaml') if (base/'profiles'/'Merge.yaml').exists() else {}
    for key in ('tun','dns','mode','ipv6','interface-name'):merge[key]=value[key]
    changes[base/'profiles'/'Merge.yaml']=dump(merge)
    changes[base/'dns_config.yaml']=dump({'dns':value['dns']})
    changes[base/'clash-verge.yaml']=dump(candidate)
    original={p:p.read_bytes() if p.exists() else None for p in changes}
    try:
        for path,text in changes.items():atomic(path,text)
        if not running():raise ValueError('Clash exited; retaining last usable configuration')
        api('PUT','/configs?force=true',{'path':str(base/'clash-verge.yaml')})
        choices=value['proxy-groups'][0]['proxies']
        selected=choice if choice in choices else choices[0]
        api('PUT','/proxies/GLOBAL',{'name':selected})
        api('DELETE','/connections')
    except Exception:
        for path,content in original.items():
            if content is None:
                if path.exists():path.unlink()
            else:path.write_bytes(content)
        if running():
            try:api('PUT','/configs?force=true',{'path':str(base/'clash-verge.yaml')})
            except Exception:pass
        raise
    count=len(value['proxy-groups'][0]['proxies'])
    save(cache_path,new_cache)
    unresolved_names=[n['name'] for n in source_nodes if n['server'] in unresolved_hosts]
    cached_names=[n['name'] for n in source_nodes if n['server'] in cached_hosts]
    summary={'stamp':before_stamp,'time':time.time(),'nodes':count,'selected':selected,'fixed_exit':read(DATA/'seed.json')['expected_ipv4'],
             'skipped_nodes':0,'pending_nodes':len(unresolved_names),'cached_nodes':len(cached_names),'pending_names':unresolved_names,
             'cached_names':cached_names,'retention_policy':'all-valid-subscription-nodes','fallback_to_airport':fallback_enabled}
    save(DATA/'committed.json',summary)
    detail='全部订阅节点已保留；最终出口保持用户配置的固定节点'
    if fallback_enabled:detail='全部订阅节点已保留；优先固定出口，不可用时回退所选机场出口'
    if unresolved_names:detail+='；%d 个节点待 DNS 解析，暂拒绝连接并自动重试'%len(unresolved_names)
    if cached_names:detail+='；%d 个节点使用 24 小时内同域名缓存'%len(cached_names)
    status('READY',detail,**summary)

def kill_worker(process):
    try:
        children=psutil.Process(process.pid).children(recursive=True)
        for child in reversed(children):
            try:child.kill()
            except psutil.Error:pass
        process.kill();process.wait(timeout=5)
    except (psutil.Error,OSError,subprocess.TimeoutExpired):pass

def daemon():
    kernel=ctypes.windll.kernel32
    kernel.CreateMutexW.argtypes=[ctypes.c_void_p,ctypes.c_bool,ctypes.c_wchar_p]
    kernel.CreateMutexW.restype=ctypes.c_void_p
    kernel.CloseHandle.argtypes=[ctypes.c_void_p]
    mutex=kernel.CreateMutexW(None,False,'Global\\ClashSubscriptionSync')
    if not mutex:raise OSError('Cannot create subscription synchronizer mutex')
    if ctypes.windll.kernel32.GetLastError()==183:return
    worker=None;worker_at=0;next_try=0;was_running=False;next_poll=0;force_refresh=False
    observer=None;observer_at=0;next_observe=0
    island=None;island_suppressed=False;next_island=0
    ui_settings=settings()
    status('WAITING','等待 Clash 原生启动；不控制网络或应用启停')
    observation('WAITING',selected=None,source='waiting-for-core-read')
    try:
        while True:
            up=running()
            if not up:
                if island and island.poll() is None:kill_worker(island)
                island=None;island_suppressed=False;next_island=0
                if observer and observer.poll() is None:kill_worker(observer)
                observer=None;next_observe=0
                if was_running or read(DATA/'current-state.json').get('state')!='STOPPED':
                    observation('STOPPED',selected=None,source='clash-process-not-running')
                if worker and worker.poll() is None:kill_worker(worker)
                worker=None
                if was_running or (DATA/'routes.json').exists():
                    try:routes('Cleanup');status('WAITING','Clash 已退出；同步器添加的机场地址路由已清理')
                    except Exception as exc:log('Route cleanup retry: '+type(exc).__name__)
                was_running=False;next_try=0
            else:
                if island and island.poll() is not None:
                    island_suppressed=island.returncode==42
                    island=None;next_island=time.time()+10
                if ui_settings.get('enable_island') and not island and not island_suppressed and time.time()>=next_island:
                    try:
                        interpreter=Path(ui_settings['python']).with_name('pythonw.exe')
                        island=subprocess.Popen([str(interpreter),'-B',str(ROOT/'island.py'),str(ROOT/'settings.json')],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=0x08000000)
                    except OSError:next_island=time.time()+30
                if not was_running:
                    next_try=time.time()+4;was_running=True;force_refresh=True;next_observe=time.time()+1
                if observer:
                    if observer.poll() is not None:observer=None
                    elif time.time()-observer_at>STATE_READ_TIMEOUT:
                        kill_worker(observer);observer=None
                        observation('ERROR',selected=None,source='live-core-api',error='ReadTimeout')
                if not observer and not worker and time.time()>=next_observe:
                    try:
                        observer=subprocess.Popen([settings()['python'],str(ROOT/'sync.py'),'--observe'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=0x08000000)
                        observer_at=time.time()
                    except OSError as exc:
                        observation('ERROR',selected=None,source='live-core-api',error=type(exc).__name__)
                    next_observe=time.time()+STATE_POLL_SECONDS
                if worker:
                    if worker.poll() is not None:
                        if worker.returncode:next_try=time.time()+30
                        worker=None
                    elif time.time()-worker_at>110:
                        kill_worker(worker);worker=None;next_try=time.time()+30
                        status('RETRY','订阅同步超时，保留原链路；稍后重试')
                if not worker and time.time()>=next_try and time.time()>=next_poll:
                    next_poll=time.time()+3
                    try:
                        item,raw=profile();committed=read(DATA/'committed.json') if (DATA/'committed.json').exists() else {}
                        interval=60 if committed.get('pending_nodes') or committed.get('cached_nodes') else 900
                        if force_refresh or committed.get('stamp')!=stamp(item['uid'],raw) or time.time()-committed.get('time',0)>interval:
                            status('SYNCING','检测到订阅变化，准备 Cloudflare 地址解析和节点链路')
                            worker=subprocess.Popen([settings()['python'],str(ROOT/'sync.py'),'--once'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=0x08000000)
                            worker_at=time.time();next_try=time.time()+30
                            force_refresh=False
                    except Exception as exc:status('RETRY',type(exc).__name__);next_try=time.time()+30
            time.sleep(.5)
    finally:
        if worker and worker.poll() is None:kill_worker(worker)
        if observer and observer.poll() is None:kill_worker(observer)
        if island and island.poll() is None:kill_worker(island)
        kernel.CloseHandle(mutex)

if __name__=='__main__':
    try:
        if '--snapshot' in sys.argv:print(json.dumps(dict(read_core_state(),observed_at_unix=time.time()),ensure_ascii=True))
        elif '--observe' in sys.argv:observe_once()
        elif '--once' in sys.argv:sync_once()
        else:daemon()
    except Exception as exc:
        message=str(exc)[:180] if isinstance(exc,ValueError) else type(exc).__name__
        try:status('RETRY','同步未完成，保留原链路：'+message);log('Synchronization error: '+message)
        except Exception:pass
        sys.exit(1)
