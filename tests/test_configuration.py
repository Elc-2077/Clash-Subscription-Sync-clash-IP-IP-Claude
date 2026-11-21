import copy,importlib,json,os,pathlib,subprocess,sys,tempfile,unittest
from unittest.mock import patch
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import sync,setup_config,discover
from sync_model import overlay,PREFIX

class Tests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.temp.name)
  self.base=self.root/'clash';self.data=self.root/'data';self.base.mkdir();self.data.mkdir();(self.base/'profiles').mkdir()
  self.user={'expected_exit_ipv4':'9.9.9.9','final_exit':{'type':'trojan','server':'8.8.8.8','port':443,'password':'synthetic-only','udp':True},
             'bootstrap':{'type':'tuic','server':'1.0.0.1','port':443,'password':'synthetic-only','uuid':'00000000-0000-4000-8000-000000000001','udp':True}}
  self.raw={'proxies':[{'name':'Example Airport','type':'trojan','server':'airport.invalid','port':443,'password':'synthetic-ingress','udp':True}]}
  self.st={'base':str(self.base),'core':'synthetic-mihomo','interface':'Synthetic Ethernet'}
  self.initial={'profiles.yaml':{'current':'remote','items':[{'uid':'remote','type':'remote','file':'remote.yaml'}]},'profiles/remote.yaml':self.raw,
                'config.yaml':{'mixed-port':7897,'mode':'rule'},'verge.yaml':{},'clash-verge.yaml':{'mode':'rule'},'profiles/Script.js':None}
  for file,data in self.initial.items():
   target=self.base/file
   if data is None:target.write_text('function main(c){return c;}\n',encoding='utf-8')
   else:target.write_text(sync.dump(data),encoding='utf-8')
  (self.root/'user-config.yaml').write_text(sync.dump(self.user),encoding='utf-8')
  self.patches=[patch.object(sync,'ROOT',self.root),patch.object(sync,'DATA',self.data),patch.object(sync,'settings',return_value=self.st),patch.object(setup_config,'__file__',str(self.root/'setup_config.py'))]
  for p in self.patches:p.start()
 def tearDown(self):
  for p in reversed(self.patches):p.stop()
  self.temp.cleanup()
 def run_initialize(self,code=0):
  with patch.object(setup_config,'resolve_initial',return_value={'airport.invalid':['1.1.1.1']}),patch.object(subprocess,'run',return_value=type('R',(),{'returncode':code})()),patch('builtins.print'):
   setup_config.initialize()

 def test_placeholder_template_is_not_a_live_config(self):
  with self.assertRaises(ValueError):setup_config.read_user(ROOT/'user-config.example.yaml')
 def test_optional_features_are_off_by_default_and_require_boolean_values(self):
  self.run_initialize()
  self.assertFalse(any(g.get('type')=='fallback' for g in sync.load(self.base/'clash-verge.yaml')['proxy-groups']))
  for key in ('enable_island','fallback_to_airport'):
   bad=dict(self.user,**{key:'false'});path=self.root/'bad.yaml';path.write_text(sync.dump(bad),encoding='utf-8')
   with self.assertRaises(ValueError):setup_config.read_user(path)
 def test_first_setup_can_enable_airport_fallback(self):
  user=dict(self.user,fallback_to_airport=True,enable_island=True)
  (self.root/'user-config.yaml').write_text(sync.dump(user),encoding='utf-8')
  self.run_initialize()
  groups=sync.load(self.base/'clash-verge.yaml')['proxy-groups']
  group=next(g for g in groups if g.get('type')=='fallback')
  self.assertEqual(group['name'],'Example Airport');self.assertNotIn('DIRECT',group['proxies'])
 def test_no_personal_seed_required_and_exit_ip_may_differ_from_server(self):
  self.run_initialize()
  seed=sync.read(self.data/'seed.json')
  self.assertEqual(seed['expected_ipv4'],'9.9.9.9');self.assertEqual(seed['final']['server'],'8.8.8.8')
  cfg=sync.load(self.base/'clash-verge.yaml');nodes={p['name']:p for p in cfg['proxies']}
  self.assertEqual(cfg['proxy-groups'][0]['proxies'],['Example Airport'])
  self.assertEqual(nodes['Example Airport']['server'],'8.8.8.8')
  self.assertEqual(nodes['Example Airport']['dialer-proxy'],PREFIX+'Example Airport')
  self.assertEqual(nodes[PREFIX+'Example Airport']['sni'],'airport.invalid')
 def test_core_schema_failure_does_not_modify_any_clash_file(self):
  original={p:p.read_bytes() for p in self.base.rglob('*') if p.is_file()}
  with self.assertRaises(ValueError):self.run_initialize(code=1)
  for path,data in original.items():self.assertEqual(path.read_bytes(),data)
  self.assertFalse((self.base/'profiles'/'SubSync.js').exists())
 def test_first_setup_rolls_back_partial_write_failure(self):
  original={p:p.read_bytes() for p in self.base.rglob('*') if p.is_file()};atomic=sync.atomic
  def failing(path,text):
   if pathlib.Path(path)==self.base/'config.yaml':raise OSError('Synthetic write failure')
   return atomic(path,text)
  with patch.object(sync,'atomic',side_effect=failing):
   with self.assertRaises(OSError):self.run_initialize()
  for path,data in original.items():self.assertEqual(path.read_bytes(),data)
  self.assertFalse((self.base/'profiles'/'SubSync.js').exists())
 def test_uninstall_restore_can_remove_new_files_and_restore_original(self):
  original={p:p.read_bytes() for p in self.base.rglob('*') if p.is_file()};self.run_initialize()
  self.assertTrue((self.base/'profiles'/'SubSync.js').exists())
  setup_config.rollback_initial()
  for path,data in original.items():self.assertEqual(path.read_bytes(),data)
  self.assertFalse((self.base/'profiles'/'SubSync.js').exists())
  self.assertFalse((self.base/'dns_config.yaml').exists())
 def test_validation_requires_own_credentials_and_udp(self):
  for change in ({'udp':False},{'server':'192.168.1.1'},{'server':'YOUR_SERVER'},{'port':0},{'password':''},{'dialer-proxy':'DIRECT'},{'plugin':'external'}):
   with self.assertRaises(ValueError):setup_config.node_check(dict(self.user['final_exit'],**change),'final_exit')
 def test_protocol_specific_credentials(self):
  for node in ({'type':'vless','server':'8.8.8.8','port':443,'udp':True,'uuid':'bad'},
               {'type':'ss','server':'8.8.8.8','port':443,'udp':True,'password':'p'}):
   with self.assertRaises(ValueError):setup_config.node_check(node,'test')
 def test_bootstrap_failure_cannot_leave_clash_modified(self):
  original={p:p.read_bytes() for p in self.base.rglob('*') if p.is_file()}
  with patch.object(setup_config,'resolve_initial',side_effect=ValueError('Synthetic lookup failure')):
   with self.assertRaises(ValueError):setup_config.initialize()
  for path,data in original.items():self.assertEqual(path.read_bytes(),data)
 def test_paths_and_interpreter_discover_without_original_user(self):
  core=self.root/'recipient-core.exe';core.write_bytes(b'fixture')
  config=dict(self.user,clash_data_directory=str(self.base),clash_core_path=str(core),physical_interface='Synthetic Wi-Fi')
  file=self.root/'discover.yaml';file.write_text(sync.dump(config),encoding='utf-8')
  with patch.dict(os.environ,{'APPDATA':str(self.root/'recipient-roaming'),'LOCALAPPDATA':str(self.root/'recipient-local')}),patch('discover.Path.is_file',return_value=True):
   value=discover.discover(file)
  self.assertEqual(value['base'],str(self.base.resolve()));self.assertEqual(value['interface'],'Synthetic Wi-Fi')
  self.assertNotIn('password',json.dumps(value))
 def test_overlay_all_visible_paths_have_final_exit(self):
  _,seed=setup_config.read_user(self.root/'user-config.yaml');seed['interface']='Synthetic Ethernet'
  value=overlay(self.raw,seed,{'airport.invalid':['1.1.1.1']},'Example Airport')
  for choice in value['proxy-groups'][0]['proxies']:
   node=next(p for p in value['proxies'] if p['name']==choice)
   self.assertEqual(node['server'],'8.8.8.8');self.assertNotEqual(choice,'DIRECT')
 def test_no_protection_startup_interception_or_firewall_changes(self):
  runtime=(ROOT/'sync.py').read_text(encoding='utf-8')+(ROOT/'Routes.ps1').read_text(encoding='utf-8-sig')
  for blocked in ('New-NetFirewallRule','Set-NetFirewallProfile','Set-DnsClientServerAddress','Disable-NetAdapter','Start-Process','Stop-Process'):
   self.assertNotIn(blocked,runtime)
  for path in ROOT.glob('*.cmd'):self.assertNotIn('C:\\Users\\',path.read_text(encoding='ascii'))

 def test_generated_generic_config_passes_real_mihomo_schema_validation(self):
  _,seed=setup_config.read_user(self.root/'user-config.yaml');seed['interface']='Synthetic Ethernet'
  cfg=overlay(self.raw,seed,{'airport.invalid':['1.1.1.1']},'Example Airport')
  cfg.update({'mixed-port':17993,'log-level':'silent'})
  file=self.root/'schema.yaml';file.write_text(sync.dump(cfg),encoding='utf-8')
  core=pathlib.Path(os.environ.get('ProgramFiles','C:/Program Files'))/'Clash Verge'/'verge-mihomo.exe'
  if not core.exists():self.skipTest('Local Mihomo not available for schema validation')
  checked=subprocess.run([str(core),'-t','-d',str(self.root),'-f',str(file)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=15)
  self.assertEqual(checked.returncode,0,'Mihomo rejected generic recipient config')

if __name__=='__main__':unittest.main(verbosity=2)
