"""Offline core checks: no TUN, no external DNS or external connections."""
import http.client,json,pathlib,socket,subprocess,sys,tempfile,time,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import sync
from sync_model import overlay

class CoreRetention(unittest.TestCase):
 def test_unresolved_hidden_dialer_is_valid_and_rejects_connection(self):
  core=pathlib.Path('C:/Program Files/Clash Verge/verge-mihomo.exe')
  if not core.exists():self.skipTest('Local Mihomo unavailable')
  seed={'expected_ipv4':'8.8.8.8','interface':'unused','final':{'type':'trojan','server':'8.8.8.8','port':443,'password':'synthetic','udp':True},'bootstrap':{'type':'trojan','server':'1.1.1.1','port':443,'password':'synthetic','udp':True}}
  raw={'proxies':[{'name':'Unresolved HY2','type':'hysteria2','server':'airport.invalid','port':443,'password':'synthetic'}]}
  value=overlay(raw,seed,{},'Unresolved HY2',False)
  with tempfile.TemporaryDirectory() as temp, socket.socket() as endpoint, socket.socket() as portpicker:
   endpoint.bind(('127.0.0.1',0));endpoint.listen();endpoint.settimeout(.4)
   portpicker.bind(('127.0.0.1',0));port=portpicker.getsockname()[1];portpicker.close()
   # If the hidden reject dialer is bypassed, the final proxy contacts this listener.
   value['proxies'][0].update({'server':'127.0.0.1','port':endpoint.getsockname()[1]})
   value.pop('interface-name');value['tun']={'enable':False};value['dns']={'enable':False}
   with socket.socket() as picker:picker.bind(('127.0.0.1',0));controller=picker.getsockname()[1]
   value.update({'mixed-port':port,'external-controller':'127.0.0.1:'+str(controller),'bind-address':'127.0.0.1','log-level':'silent','profile':{'store-selected':False}})
   cfg=pathlib.Path(temp)/'test.yaml';cfg.write_text(sync.dump(value),encoding='utf-8')
   checked=subprocess.run([str(core),'-t','-d',temp,'-f',str(cfg)],capture_output=True,timeout=15)
   self.assertEqual(checked.returncode,0,'Core rejected hidden REJECT dialer configuration')
   process=subprocess.Popen([str(core),'-d',temp,'-f',str(cfg)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=0x08000000)
   try:
    connected=None
    for attempt in range(50):
     try:connected=socket.create_connection(('127.0.0.1',port),.1);break
     except OSError:
      if process.poll() is not None:self.fail('Isolated core exited before accepting localhost requests')
      time.sleep(.05)
    self.assertIsNotNone(connected,'Isolated core listener did not start')
    control=http.client.HTTPConnection('127.0.0.1',controller,timeout=2)
    control.request('GET','/proxies/GLOBAL');group=json.loads(control.getresponse().read());control.close()
    self.assertEqual(group['now'],'Unresolved HY2',str(group))
    with connected:
     connected.settimeout(8)
     connected.sendall(b'CONNECT 1.1.1.1:443 HTTP/1.1\r\nHost: 1.1.1.1:443\r\n\r\n')
     response=connected.recv(4096)
     if b' 200 ' in response:
      # Mihomo acknowledges CONNECT before attempting the remote dial.
      connected.sendall(b'synthetic-handshake')
      try:closed=connected.recv(4096)==b''
      except ConnectionResetError:closed=True
      self.assertTrue(closed,'Unresolved chain did not reject its TCP stream')
    with self.assertRaises(socket.timeout):endpoint.accept()
   finally:
    process.terminate();process.wait(timeout=5)

if __name__=='__main__':unittest.main(verbosity=2)

