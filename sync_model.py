import copy, hashlib, ipaddress, json, re

BOOT='__SUBSYNC_CF__'
PREFIX='__SUBSYNC_AIRPORT__'
META=re.compile(r'^(剩余流量|距离下次|套餐到期|官网|客服邮箱)')
CACHE_MAX_AGE=24*60*60

def complete_addresses(hosts,fresh,cache,now):
    result={};records={};cached=[];unresolved=[]
    previous=cache.get('hosts',{}) if isinstance(cache,dict) else {}
    for host in sorted(set(hosts)):
        values=[]
        for value in fresh.get(host,[]) or []:
            try:values.append(public4(value))
            except ValueError:pass
        if values:
            result[host]=sorted(set(values));records[host]={'addresses':result[host],'resolved_at':now}
            continue
        record=previous.get(host,{})
        try:age=now-float(record.get('resolved_at',0))
        except (ValueError,TypeError):age=CACHE_MAX_AGE+1
        if 0<=age<=CACHE_MAX_AGE:
            for value in record.get('addresses',[]) or []:
                try:values.append(public4(value))
                except ValueError:pass
        if values:
            result[host]=sorted(set(values));records[host]={'addresses':result[host],'resolved_at':record['resolved_at']};cached.append(host)
        else:result[host]=[];unresolved.append(host)
    return result,{'hosts':records},cached,unresolved

def stamp(uid,raw):
    return hashlib.sha256(json.dumps({'uid':uid,'proxies':raw.get('proxies',[])},ensure_ascii=True,sort_keys=True).encode()).hexdigest()

def public4(value):
    address=ipaddress.ip_address(value)
    if address.version!=4 or not address.is_global:raise ValueError('Endpoint is not a public IPv4')
    return str(address)

def entries(raw):
    result=[];names=set()
    for value in raw.get('proxies',[]):
        if not isinstance(value,dict) or not value.get('server') or META.match(str(value.get('name',''))):continue
        if not isinstance(value.get('name'),str) or value['name'] in names or value['name'] in ('GLOBAL','DIRECT','REJECT',BOOT) or value['name'].startswith(PREFIX):
            raise ValueError('Duplicate or reserved airport name')
        if value.get('dialer-proxy'):raise ValueError('Nested airport chains are not supported')
        if not value.get('type') or not 1<=int(value.get('port',0))<=65535:continue
        names.add(value['name']);result.append(copy.deepcopy(value))
    if not result:raise ValueError('No usable airport nodes')
    return result

def pin(node,addresses):
    p=copy.deepcopy(node);host=p['server'];p['server']=public4(addresses[host][0])
    try:ipaddress.ip_address(host)
    except ValueError:
        if p['type'] in ('trojan','tuic','hysteria2','hysteria','anytls'):p.setdefault('sni',host)
        elif p.get('tls'):p.setdefault('servername',host)
    return p

def overlay(raw,seed,addresses,preferred,tun_enabled=True):
    final=copy.deepcopy(seed['final']);final.pop('dialer-proxy',None)
    public4(seed['expected_ipv4'])
    public4(final['server'])
    selected=entries(raw)
    selected.sort(key=lambda n:n['name']!=preferred)
    airport=[];chains=[];blocked=[]
    for item in selected:
        ingress=PREFIX+item['name']
        if addresses.get(item['server']):
            p=pin(item,addresses);p['name']=ingress;p['interface-name']=seed['interface'];airport.append(p)
        else:
            # Keep the public node name and final exit unchanged. A hidden reject-only
            # dialer prevents unresolved domains from recursing through the active TUN.
            blocked.append({'name':ingress,'type':'select','proxies':['REJECT'],'hidden':True})
        chain=copy.deepcopy(final);chain.update({'name':item['name'],'dialer-proxy':ingress,'udp':True})
        chains.append(chain)
    boot=copy.deepcopy(seed['bootstrap']);boot['name']=BOOT;boot['interface-name']=seed['interface']
    boot.pop('dialer-proxy',None)
    ips=sorted({public4(p['server']) for p in airport+[boot,final]})
    cf=['https://1.1.1.1/dns-query#GLOBAL','https://1.0.0.1/dns-query#GLOBAL']
    bootcf=['https://1.1.1.1/dns-query#'+BOOT,'https://1.0.0.1/dns-query#'+BOOT]
    return {'proxies':airport+chains+[boot],'proxy-providers':{},'rule-providers':{},
            'proxy-groups':[{'name':'GLOBAL','type':'select','proxies':[p['name'] for p in chains]}]+blocked,
            'rules':['MATCH,GLOBAL'],'mode':'global','ipv6':False,'allow-lan':False,
            'interface-name':seed['interface'],'profile':{'store-selected':True},
            'tun':{'enable':bool(tun_enabled),'device':'RevFixedTun','stack':'gvisor','auto-route':True,
                   'strict-route':True,'auto-detect-interface':False,'dns-hijack':['any:53','tcp://any:53'],
                   'mtu':1400,'route-exclude-address':[ip+'/32' for ip in ips]},
            'dns':{'enable':True,'listen':'127.0.0.1:53','ipv6':False,'enhanced-mode':'fake-ip',
                   'fake-ip-range':'198.18.0.1/16','fake-ip-filter':['localhost','*.lan','*.local'],
                   'nameserver':cf,'direct-nameserver':cf,'default-nameserver':bootcf,
                   'proxy-server-nameserver':bootcf,'fallback':[],'respect-rules':False,
                   'use-system-hosts':False,'use-hosts':False}}

def enhancement(value):
    # Retain the last validated chain during a provider refresh. The synchronizer
    # replaces it only after DNS, routes and core schema checks have succeeded.
    return '// SubscriptionSync: last validated fixed-exit configuration.\nfunction main(config){return Object.assign(config,'+json.dumps(value,ensure_ascii=False)+');}\n'
