import json,pathlib,sys,tempfile,unittest
from unittest.mock import Mock,patch
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import sync

class Observation(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.temp.name)
  self.data=self.root/'data';self.data.mkdir();self.base=self.root/'clash';self.base.mkdir();self.report=self.root/'report';self.report.mkdir()
  cfg={'proxies':[{'name':'Choice A','type':'trojan','server':'8.8.8.8','password':'never-export-this-secret','dialer-proxy':'ingress A'},{'name':'ingress A','type':'vless','uuid':'never-export-this-uuid'}]}
  (self.base/'clash-verge.yaml').write_text(sync.dump(cfg),encoding='utf-8')
  self.patches=[patch.object(sync,'DATA',self.data),patch.object(sync,'settings',return_value={'base':str(self.base),'report_dir':str(self.report),'python':sys.executable}),patch.object(sync,'running',return_value=True)]
  for p in self.patches:p.start()
 def tearDown(self):
  for p in reversed(self.patches):p.stop()
  self.temp.cleanup()
 def api(self,method,path,body=None):
  self.assertEqual(method,'GET');self.assertIsNone(body)
  if path=='/proxies':return {'proxies':{'GLOBAL':{'now':'Choice A'}}}
  if path=='/configs':return {'mode':'global','tun':{'enable':True},'ipv6':False}
  self.fail('Unexpected API path')
 def test_reads_live_selection_without_changing_sync_or_routes(self):
  for name in ('committed.json','status.json'):(self.data/name).write_text('{"sentinel":true}',encoding='utf-8')
  before=(self.base/'clash-verge.yaml').read_bytes()
  with patch.object(sync,'api',side_effect=self.api),patch.object(sync,'routes') as routes:
   value=sync.observe_once();routes.assert_not_called()
  self.assertEqual(value['state'],'RUNNING');self.assertEqual(value['selected'],'Choice A');self.assertEqual(value['poll_interval_seconds'],60)
  self.assertEqual(value['configured_exit_server'],'8.8.8.8');self.assertFalse(value['public_exit_verified'])
  self.assertEqual((self.base/'clash-verge.yaml').read_bytes(),before)
  for name in ('committed.json','status.json'):self.assertEqual(sync.read(self.data/name),{'sentinel':True})
  self.assertEqual(sync.read(self.report/'current-state.json'),value)
  text=json.dumps(value);self.assertNotIn('never-export',text);self.assertNotIn('password',text);self.assertNotIn('uuid',text)
 def test_error_clears_old_selection_and_omits_raw_exception(self):
  with patch.object(sync,'api',side_effect=self.api):sync.observe_once()
  with patch.object(sync,'api',side_effect=PermissionError('private-secret-in-exception')):value=sync.observe_once()
  self.assertEqual(value['state'],'ERROR');self.assertIsNone(value['selected']);self.assertEqual(value['error'],'PermissionError')
  self.assertNotIn('private-secret',json.dumps(value))
 def test_closed_clash_exports_stopped_without_api_access(self):
  with patch.object(sync,'running',return_value=False),patch.object(sync,'api') as api:
   value=sync.observe_once();api.assert_not_called()
  self.assertEqual(value['state'],'STOPPED');self.assertIsNone(value['selected'])
 def test_direct_or_rule_mode_is_not_reported_as_fixed_exit(self):
  with patch.object(sync,'api',side_effect=[{'proxies':{'GLOBAL':{'now':'DIRECT'}}},{'mode':'rule','tun':{'enable':False},'ipv6':True}]):value=sync.observe_once()
  self.assertEqual(value['selected'],'DIRECT');self.assertEqual(value['mode'],'rule');self.assertFalse(value['tun_enabled'])
  self.assertFalse(value['selected_fixed_chain']);self.assertIsNone(value['configured_exit_server'])
 def test_empty_core_selection_is_an_error(self):
  with patch.object(sync,'api',return_value={}):value=sync.observe_once()
  self.assertEqual(value['state'],'ERROR');self.assertIsNone(value['selected'])
 def test_sixty_second_observation_does_not_reload_every_minute(self):
  class EndLoop(Exception):pass
  clock=[1000.0];calls=[]
  kernel=Mock();kernel.CreateMutexW.return_value=1;kernel.GetLastError.return_value=0
  raw={'proxies':[{'name':'fixture'}]};sync.save(self.data/'committed.json',{'stamp':sync.stamp('test',raw),'time':1000})
  def sleep(seconds):
   clock[0]+=seconds
   if clock[0]>1125:raise EndLoop()
  def popen(args,**kwargs):
   calls.append((clock[0],args[-1]));worker=Mock();worker.poll.return_value=0;worker.returncode=0;return worker
  with patch.object(sync.ctypes,'windll',Mock(kernel32=kernel)),patch.object(sync.time,'time',side_effect=lambda:clock[0]),patch.object(sync.time,'sleep',side_effect=sleep),patch.object(sync,'profile',return_value=({'uid':'test'},raw)),patch.object(sync.subprocess,'Popen',side_effect=popen):
   with self.assertRaises(EndLoop):sync.daemon()
  observed=[t for t,arg in calls if arg=='--observe'];reloaded=[t for t,arg in calls if arg=='--once']
  self.assertEqual(observed,[1001.0,1061.0,1121.0]);self.assertEqual(len(reloaded),1)

if __name__=='__main__':unittest.main(verbosity=2)
