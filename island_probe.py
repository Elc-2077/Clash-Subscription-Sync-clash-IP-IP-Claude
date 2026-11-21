"""Read-only local network measurements for the desktop island.

No firewall, route, adapter DNS, or running Clash configuration is changed.
Local public-IP discovery explicitly uses the physical interface. Other probes
use the running proxy or an isolated core with TUN and DNS disabled.
"""
import concurrent.futures,copy,ctypes,http.client,ipaddress,json,os,socket,ssl,statistics,subprocess,sys,tempfile,time,urllib.request
from pathlib import Path
import psutil,yaml

def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def load(path):return yaml.safe_load(Path(path).read_text(encoding='utf-8-sig')) or {}
def free_port():
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));return sock.getsockname()[1]
def parse_trace(text):
    fields=dict(line.split('=',1) for line in text.splitlines() if '=' in line)
    address=str(ipaddress.ip_address(fields.get('ip','')))
    if not ipaddress.ip_address(address).is_global:raise ValueError('Invalid public address')
    return address
def trace_country(text):
    fields=dict(line.split('=',1) for line in text.splitlines() if '=' in line)
    code=fields.get('loc','').upper()
    return code if len(code)==2 and code.isascii() and code.isalpha() and code not in ('XX','ZZ') else None
def trace_proxy(port):
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({'https':'http://127.0.0.1:'+str(port)}))
    request=urllib.request.Request('https://1.1.1.1/cdn-cgi/trace',headers={'Connection':'close','Cache-Control':'no-cache'})
    started=time.perf_counter()
    with opener.open(request,timeout=5) as response:
        ms=(time.perf_counter()-started)*1000;body=response.read(4096).decode()
    return parse_trace(body),round(ms,1),trace_country(body)
def physical_address(interface):
    if os.name=='nt':
        # Winsock's if_nametoindex expects ethernet_N, not the UI adapter alias.
        luid=ctypes.c_ulonglong();number=ctypes.c_ulong()
        api=ctypes.WinDLL('iphlpapi')
        api.ConvertInterfaceAliasToLuid.argtypes=[ctypes.c_wchar_p,ctypes.POINTER(ctypes.c_ulonglong)]
        api.ConvertInterfaceLuidToIndex.argtypes=[ctypes.POINTER(ctypes.c_ulonglong),ctypes.POINTER(ctypes.c_ulong)]
        if api.ConvertInterfaceAliasToLuid(interface,ctypes.byref(luid)) or api.ConvertInterfaceLuidToIndex(ctypes.byref(luid),ctypes.byref(number)):raise OSError('Physical interface unavailable')
        index=number.value
    else:index=socket.if_nametoindex(interface)
    addresses=[item.address for item in psutil.net_if_addrs().get(interface,[]) if item.family==socket.AF_INET and not item.address.startswith(('127.','169.254.'))]
    if not addresses:raise ValueError('Physical IPv4 unavailable')
    return index,addresses[0]
def trace_physical(interface,endpoint='1.1.1.1',hostname='1.1.1.1'):
    index,local=physical_address(interface)
    sock=socket.socket(socket.AF_INET,socket.SOCK_STREAM);sock.settimeout(5)
    try:
        # IP_UNICAST_IF is in network byte order on Windows. This does not add
        # a route and intentionally has no default-route fallback if binding fails.
        sock.setsockopt(socket.IPPROTO_IP,31,index.to_bytes(4,'big'))
        sock.bind((local,0));sock.connect((endpoint,443))
        with ssl.create_default_context().wrap_socket(sock,server_hostname=hostname) as secure:
            secure.sendall(('GET /cdn-cgi/trace HTTP/1.1\r\nHost: '+hostname+'\r\nConnection: close\r\nCache-Control: no-cache\r\n\r\n').encode('ascii'))
            response=http.client.HTTPResponse(secure);response.begin()
            if response.status!=200:raise ValueError('Physical probe HTTP failure')
            body=response.read(4096).decode()
            return parse_trace(body),None,trace_country(body)
    finally:sock.close()
def physical_target(configured):
    # Reuse an already excluded Cloudflare edge /32. TUN may still intercept
    # a socket bound to a physical interface when its destination is not excluded.
    networks=[ipaddress.ip_network(n) for n in ('104.16.0.0/13','104.24.0.0/14','172.64.0.0/13','162.158.0.0/15')]
    for prefix in configured.get('tun',{}).get('route-exclude-address',[]):
        network=ipaddress.ip_network(prefix,strict=False)
        if network.prefixlen==32 and any(network.network_address in net for net in networks):return str(network.network_address),'www.cloudflare.com'
    raise ValueError('No existing physical Cloudflare endpoint route; local public IP unverified')
def measure(fn,count=3):
    samples=[];errors=[]
    for _ in range(count):
        try:
            sample=fn();address,ms=sample[:2];country=sample[2] if len(sample)>2 else None
            samples.append({'ip':address,'ms':ms,'country':country})
        except Exception as exc:errors.append(type(exc).__name__)
    values=[s['ms'] for s in samples if s['ms'] is not None]
    return {'ok':bool(samples),'ip':samples[-1]['ip'] if samples else None,
            'country':samples[-1]['country'] if samples else None,
            'mean_ms':round(statistics.mean(values),1) if values else None,
            'successes':len(samples),'attempts':count,'errors':errors,
            'ip_changed_during_test':len({s['ip'] for s in samples})>1}
def stop_process(process):
    try:
        for child in reversed(psutil.Process(process.pid).children(recursive=True)):
            try:child.kill()
            except psutil.NoSuchProcess:pass
        process.kill();process.wait(timeout=4)
    except (psutil.NoSuchProcess,ProcessLookupError):pass
def probe(settings):
    base=Path(settings['base']);folder=Path(settings['report_dir'])
    configured=load(base/'clash-verge.yaml');basic=load(base/'config.yaml')
    state=read(folder/'current-state.json') if (folder/'current-state.json').exists() else {}
    age=time.time()-float(state.get('observed_at_unix',0))
    selected=state.get('selected') if state.get('state')=='RUNNING' and 0<=age<=90 else None
    result={'measured_at_unix':time.time(),'selected':selected,'selection_age_seconds':round(age,1),
            'selection_fresh':selected is not None,'state_source':'60-second-core-export',
            'local':{'ok':False},'airport':{'ok':False},'fixed':{'ok':False},'current':{'ok':False},
            'fallback_configured':bool(settings.get('fallback_to_airport')),
            'core_active_route':state.get('active_route'),'metric':'HTTPS including CONNECT/TLS and response headers; averages of up to 3 attempts'}
    nodes={p['name']:p for p in configured.get('proxies',[])}
    groups={p['name']:p for p in configured.get('proxy-groups',[])}
    choice=groups.get(selected,{})
    final_name=choice['proxies'][0] if choice.get('type')=='fallback' else selected
    final=nodes.get(final_name,{})
    ingress=nodes.get(final.get('dialer-proxy'),{})
    worker=None
    with tempfile.TemporaryDirectory(prefix='clash-island-probe-') as temporary:
        try:
            ports={}
            if ingress and final:
                ports={'airport':free_port(),'fixed':free_port()}
                while ports['fixed']==ports['airport']:ports['fixed']=free_port()
                probe_cfg={'allow-lan':False,'bind-address':'127.0.0.1','mode':'rule','log-level':'silent','ipv6':False,
                           'external-controller':'','tun':{'enable':False},'dns':{'enable':False},
                           'profile':{'store-selected':False},'proxies':[copy.deepcopy(ingress),copy.deepcopy(final)],
                           'rules':['MATCH,REJECT'],'listeners':[{'name':kind,'type':'mixed','listen':'127.0.0.1','port':port,'proxy':ingress['name'] if kind=='airport' else final['name']} for kind,port in ports.items()]}
                file=Path(temporary)/'config.yaml';file.write_text(yaml.safe_dump(probe_cfg,allow_unicode=True,sort_keys=False),encoding='utf-8')
                checked=subprocess.run([settings['core'],'-t','-d',temporary,'-f',str(file)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=6,creationflags=0x08000000)
                if checked.returncode:raise ValueError('Probe core schema rejected')
                worker=subprocess.Popen([settings['core'],'-d',temporary,'-f',str(file)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=0x08000000)
                for _ in range(40):
                    if worker.poll() is not None:raise ValueError('Probe core exited')
                    try:
                        with socket.create_connection(('127.0.0.1',ports['airport']),.1):break
                    except OSError:time.sleep(.05)
                else:raise ValueError('Probe listener unavailable')
            def local_probe():
                endpoint,hostname=physical_target(configured)
                return trace_physical(settings['interface'],endpoint,hostname)
            jobs={'local':lambda:measure(local_probe,1),
                  'current':lambda:measure(lambda:trace_proxy(int(basic.get('mixed-port',7897))))}
            if ports:
                jobs.update(airport=lambda:measure(lambda:trace_proxy(ports['airport'])),fixed=lambda:measure(lambda:trace_proxy(ports['fixed'])))
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                futures={key:pool.submit(fn) for key,fn in jobs.items()}
                for key,future in futures.items():result[key]=future.result()
        except Exception as exc:result['probe_error']=type(exc).__name__
        finally:
            if worker and worker.poll() is None:stop_process(worker)
    result['configured_fixed_server']=final.get('server')
    result['completed_at_unix']=time.time()
    latest=read(folder/'current-state.json') if (folder/'current-state.json').exists() else {}
    result['selection_changed_during_test']=latest.get('selected')!=state.get('selected')
    if result['selection_changed_during_test']:result['selection_fresh']=False
    return result

if __name__=='__main__':
    try:
        settings=read(sys.argv[1]);value=probe(settings)
        target=Path(settings['report_dir'])/'island-metrics.json';temporary=target.with_suffix('.new')
        temporary.write_text(json.dumps(value,ensure_ascii=True,indent=2),encoding='utf-8');os.replace(str(temporary),str(target))
    except Exception as exc:
        print(type(exc).__name__);sys.exit(1)
