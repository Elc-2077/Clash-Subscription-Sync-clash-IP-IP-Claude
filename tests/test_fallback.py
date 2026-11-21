import copy,http.client,json,pathlib,select,socket,socketserver,struct,subprocess,sys,tempfile,threading,time,unittest,urllib.request
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import sync
from sync_model import overlay,PREFIX,FIXED_PREFIX

def receive(sock,n):
 data=b''
 while len(data)<n:
  chunk=sock.recv(n-len(data))
  if not chunk:raise OSError('closed')
  data+=chunk
 return data
class Server(socketserver.ThreadingTCPServer):allow_reuse_address=True;daemon_threads=True
class Socks(socketserver.BaseRequestHandler):
 def handle(self):
  s=self.request;s.settimeout(3)
  try:
   head=receive(s,2);receive(s,head[1]);s.sendall(b'\x05\x00');head=receive(s,4)
   if head[3]==1:host=socket.inet_ntoa(receive(s,4))
   elif head[3]==3:host=receive(s,receive(s,1)[0]).decode()
   else:return
   port=struct.unpack('!H',receive(s,2))[0]
   if self.server.role=='FIXED' and not self.server.healthy.is_set():return
   s.sendall(b'\x05\x00\x00\x01'+b'\0'*6)
   if self.server.role=='AIRPORT' and port==self.server.fixed_port:
    with socket.create_connection(('127.0.0.1',port),2) as out:
     while True:
      readable,_,_=select.select([s,out],[],[],3)
      if not readable:return
      for a in readable:
       data=a.recv(4096)
       if not data:return
       (out if a is s else s).sendall(data)
   else:
    request=b''
    while b'\r\n\r\n' not in request:request+=receive(s,1)
    body=self.server.role.encode();s.sendall(b'HTTP/1.1 200 OK\r\nContent-Length: '+str(len(body)).encode()+b'\r\nConnection: close\r\n\r\n'+body)
  except (OSError,ValueError):pass

class Fallback(unittest.TestCase):
 def setUp(self):
  self.raw={'proxies':[{'name':'Airport A','type':'socks5','server':'1.1.1.1','port':443,'udp':True}]}
  self.seed={'expected_ipv4':'8.8.8.8','interface':'unused','final':{'type':'socks5','server':'8.8.8.8','port':443,'udp':True},'bootstrap':{'type':'socks5','server':'1.0.0.1','port':443,'udp':True}}
 def test_optional_order_and_no_direct_fallback(self):
  normal=overlay(self.raw,self.seed,{'1.1.1.1':['1.1.1.1']},'')
  self.assertFalse(any(g['type']=='fallback' for g in normal['proxy-groups']))
  value=overlay(self.raw,self.seed,{'1.1.1.1':['1.1.1.1']},'',True,True)
  group=next(g for g in value['proxy-groups'] if g['name']=='Airport A')
  self.assertEqual(group['proxies'],[FIXED_PREFIX+'Airport A',PREFIX+'Airport A']);self.assertNotIn('DIRECT',group['proxies'])
  self.assertEqual(value['dns']['nameserver'],normal['dns']['nameserver'])
 def test_offline_core_prefers_fixed_falls_back_then_recovers(self):
  core=pathlib.Path('C:/Program Files/Clash Verge/verge-mihomo.exe')
  if not core.exists():self.skipTest('Local core unavailable')
  fixed=Server(('127.0.0.1',0),Socks);fixed.role='FIXED';fixed.healthy=threading.Event();fixed.healthy.set()
  airport=Server(('127.0.0.1',0),Socks);airport.role='AIRPORT';airport.fixed_port=fixed.server_address[1]
  for server in (fixed,airport):threading.Thread(target=server.serve_forever,daemon=True).start()
  try:
   with tempfile.TemporaryDirectory() as folder:
    value=overlay(self.raw,self.seed,{'1.1.1.1':['1.1.1.1']},'',False,True)
    nodes={n['name']:n for n in value['proxies']}
    nodes[PREFIX+'Airport A'].update(server='127.0.0.1',port=airport.server_address[1]);nodes[PREFIX+'Airport A'].pop('interface-name')
    nodes[FIXED_PREFIX+'Airport A'].update(server='127.0.0.1',port=fixed.server_address[1])
    value['proxies']=[nodes[PREFIX+'Airport A'],nodes[FIXED_PREFIX+'Airport A']]
    value.pop('interface-name');value['tun']={'enable':False};value['dns']={'enable':False};value['profile']={'store-selected':False}
    ports=[]
    for _ in range(2):
     with socket.socket() as s:s.bind(('127.0.0.1',0));ports.append(s.getsockname()[1])
    port,controller=ports
    value.update({'mixed-port':port,'external-controller':'127.0.0.1:'+str(controller),'log-level':'silent'})
    group=value['proxy-groups'][1];group.update({'interval':1,'timeout':300,'lazy':False,'url':'http://example.invalid/health'})
    path=pathlib.Path(folder)/'config.yaml';path.write_text(sync.dump(value),encoding='utf-8')
    process=subprocess.Popen([str(core),'-d',folder,'-f',str(path)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=0x08000000)
    def get_active():
     conn=http.client.HTTPConnection('127.0.0.1',controller,timeout=1);conn.request('GET','/proxies/Airport%20A')
     result=json.loads(conn.getresponse().read());conn.close();return result['now']
    def wait_for(name):
     until=time.monotonic()+10
     while time.monotonic()<until:
      try:
       if get_active()==name:return
      except (OSError,ValueError):pass
      time.sleep(.2)
     self.fail('Expected fallback state was not reached: '+name)
    def body():
     opener=urllib.request.build_opener(urllib.request.ProxyHandler({'http':'http://127.0.0.1:'+str(port)}))
     with opener.open('http://example.invalid/result',timeout=3) as response:return response.read().decode()
    try:
     wait_for(FIXED_PREFIX+'Airport A');self.assertEqual(body(),'FIXED')
     fixed.healthy.clear();wait_for(PREFIX+'Airport A');self.assertEqual(body(),'AIRPORT')
     fixed.healthy.set();wait_for(FIXED_PREFIX+'Airport A');self.assertEqual(body(),'FIXED')
    finally:process.terminate();process.wait(timeout=5)
  finally:
   for server in (fixed,airport):server.shutdown();server.server_close()

if __name__=='__main__':unittest.main(verbosity=2)
