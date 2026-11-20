import copy,importlib.util,pathlib,sys,unittest
from unittest.mock import Mock,patch
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from sync_model import CACHE_MAX_AGE,PREFIX,complete_addresses,overlay
import update_support

class Retention(unittest.TestCase):
 def setUp(self):
  self.raw={'proxies':[{'name':'HY2 Example','type':'hysteria2','server':'hy.invalid','port':443,'password':'synthetic'},{'name':'VLESS Example','type':'vless','server':'vless.invalid','port':443,'uuid':'00000000-0000-4000-8000-000000000001'}]}
  self.seed={'expected_ipv4':'9.9.9.9','interface':'unused','final':{'type':'trojan','server':'8.8.8.8','port':443,'password':'synthetic','udp':True},'bootstrap':{'type':'trojan','server':'1.0.0.1','port':443,'password':'synthetic','udp':True}}
 def test_protocols_and_unresolved_nodes_retained(self):
  value=overlay(self.raw,self.seed,{'vless.invalid':['1.1.1.1']},'HY2 Example')
  self.assertEqual(value['proxy-groups'][0]['proxies'],['HY2 Example','VLESS Example'])
  self.assertEqual(value['proxy-groups'][1]['proxies'],['REJECT'])
  for name in value['proxy-groups'][0]['proxies']:
   node=next(n for n in value['proxies'] if n['name']==name)
   self.assertEqual(node['server'],'8.8.8.8');self.assertEqual(node['dialer-proxy'],PREFIX+name)
 def test_no_resolved_nodes_still_keeps_every_choice(self):
  value=overlay(self.raw,self.seed,{},'')
  self.assertEqual(len(value['proxy-groups'][0]['proxies']),2)
  self.assertTrue(all(group['proxies']==['REJECT'] for group in value['proxy-groups'][1:]))
 def test_fresh_dns_overrides_cache(self):
  cache={'hosts':{'hy.invalid':{'addresses':['8.8.8.8'],'resolved_at':100}}}
  addresses,updated,cached,pending=complete_addresses(['hy.invalid'],{'hy.invalid':['1.1.1.1']},cache,200)
  self.assertEqual(addresses['hy.invalid'],['1.1.1.1']);self.assertFalse(cached);self.assertFalse(pending)
  self.assertEqual(updated['hosts']['hy.invalid']['resolved_at'],200)
 def test_cached_dns_expires_without_renewing_on_failure(self):
  cache={'hosts':{'hy.invalid':{'addresses':['8.8.8.8'],'resolved_at':100}}}
  addresses,updated,cached,pending=complete_addresses(['hy.invalid'],{},cache,200)
  self.assertEqual(cached,['hy.invalid']);self.assertEqual(updated['hosts']['hy.invalid']['resolved_at'],100)
  addresses,updated,cached,pending=complete_addresses(['hy.invalid'],{},updated,101+CACHE_MAX_AGE)
  self.assertEqual(pending,['hy.invalid']);self.assertFalse(updated['hosts'])
 def test_wrong_hostname_private_and_future_cache_rejected(self):
  cache={'hosts':{'hy.invalid':{'addresses':['127.0.0.1','bad','::1'],'resolved_at':100},'other.invalid':{'addresses':['8.8.8.8'],'resolved_at':100},'vless.invalid':{'addresses':['1.1.1.1'],'resolved_at':300}}}
  addresses,updated,cached,pending=complete_addresses(['hy.invalid','vless.invalid','new.invalid'],{},cache,200)
  self.assertEqual(len(pending),3);self.assertFalse(cached);self.assertFalse(updated['hosts'])
 def test_updater_targets_only_installed_worker_script(self):
  target=ROOT/'sync.py'
  self.assertTrue(update_support.is_worker({'name':'pythonw.exe','cmdline':['pythonw.exe','-B',str(target)]},target))
  self.assertFalse(update_support.is_worker({'name':'clash-verge.exe','cmdline':['clash-verge.exe',str(target)]},target))
  self.assertFalse(update_support.is_worker({'name':'python.exe','cmdline':['python.exe',str(ROOT/'update_support.py'),'stop-workers',str(target)]},target))
  self.assertFalse(update_support.is_worker({'name':'python.exe','cmdline':['python.exe',str(ROOT/'tests/example.py'),str(target)]},target))

 def test_updater_ignores_native_998_and_reads_only_python_command_lines(self):
  target=ROOT/'sync.py'
  system=Mock();system.name.return_value='System';system.cmdline.side_effect=AssertionError('Must not read a system command line')
  unreadable=Mock();unreadable.name.side_effect=OSError(998,'Synthetic native process read error')
  python_unreadable=Mock();python_unreadable.name.return_value='python.exe';python_unreadable.cmdline.side_effect=OSError(998,'Synthetic native command line error')
  worker=Mock();worker.name.return_value='pythonw.exe';worker.cmdline.return_value=['pythonw.exe','-B',str(target)]
  child=Mock();worker.children.return_value=[child]
  unrelated=Mock();unrelated.name.return_value='python.exe';unrelated.cmdline.return_value=['python.exe',str(ROOT/'tests/example.py')]
  processes={1:system,2:unreadable,3:python_unreadable,4:worker,5:unrelated}
  with patch.object(update_support.psutil,'pids',return_value=[1,2,3,4,5]),patch.object(update_support.psutil,'Process',side_effect=processes.__getitem__),patch.object(update_support.os,'getpid',return_value=999):
   update_support.stop_workers(target)
  system.cmdline.assert_not_called();system.kill.assert_not_called();unreadable.kill.assert_not_called();python_unreadable.kill.assert_not_called();unrelated.kill.assert_not_called()
  child.kill.assert_called_once();worker.kill.assert_called_once();worker.wait.assert_called_once_with(timeout=5)

 def test_updater_does_not_ignore_failure_to_stop_a_known_worker(self):
  target=ROOT/'sync.py';worker=Mock();worker.name.return_value='python.exe';worker.cmdline.return_value=['python.exe',str(target)];worker.children.return_value=[]
  worker.kill.side_effect=update_support.psutil.AccessDenied(pid=1)
  with patch.object(update_support.psutil,'pids',return_value=[1]),patch.object(update_support.psutil,'Process',return_value=worker),patch.object(update_support.os,'getpid',return_value=999):
   with self.assertRaises(update_support.psutil.AccessDenied):update_support.stop_workers(target)

if __name__=='__main__':unittest.main(verbosity=2)
