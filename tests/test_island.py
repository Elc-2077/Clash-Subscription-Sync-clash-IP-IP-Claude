# -*- coding: utf-8 -*-
import json,pathlib,sys,tempfile,time,unittest
from unittest.mock import Mock,patch
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import island_probe as probe,island,sync
from island_flags import draw_flag,country_label

class IslandTests(unittest.TestCase):
 def test_probe_ip_validation_and_mean(self):
  self.assertEqual(probe.parse_trace('ip=8.8.8.8\ncolo=EXAMPLE'),'8.8.8.8')
  for value in ('ip=127.0.0.1','no-ip','ip=bad'):
   with self.assertRaises(ValueError):probe.parse_trace(value)
  values=iter([('8.8.8.8',100),('8.8.8.8',200),('8.8.8.8',300)])
  result=probe.measure(lambda:next(values))
  self.assertEqual(result['mean_ms'],200);self.assertEqual(result['successes'],3)
 def test_local_ip_has_no_latency(self):
  result=probe.measure(lambda:('9.9.9.9',None),1)
  self.assertTrue(result['ok']);self.assertIsNone(result['mean_ms'])
 def test_country_comes_from_same_trace_and_missing_country_stays_unknown(self):
  self.assertEqual(probe.trace_country('ip=8.8.8.8\nloc=US\ncolo=LAX'),'US')
  self.assertEqual(probe.trace_country('loc=jp'),'JP')
  for trace in ('','loc=XX','loc=ZZ','loc=USA','loc=<>','loc=中国'):
   self.assertIsNone(probe.trace_country(trace))
  value=probe.measure(lambda:('8.8.8.8',100,'US'))
  self.assertEqual(value['country'],'US');self.assertEqual(value['mean_ms'],100)
  self.assertIsNone(probe.measure(lambda:('8.8.8.8',100))['country'])
 def test_private_metrics_redact_airport_and_local_but_keep_flag_latency_and_fixed(self):
  value={'local':{'ip':'9.9.9.9','country':'CN'},'airport':{'ip':'1.0.0.1','country':'JP','mean_ms':100},'fixed':{'ip':'8.8.8.8','country':'US','mean_ms':200},'current':{'ip':'8.8.8.8','mean_ms':210}}
  result=probe.redact_private_metrics(value,{})
  self.assertNotIn('9.9.9.9',json.dumps(result));self.assertNotIn('1.0.0.1',json.dumps(result))
  self.assertIsNone(result['local']['country']);self.assertEqual(result['airport']['country'],'JP');self.assertEqual(result['airport']['mean_ms'],100)
  self.assertEqual(result['fixed']['ip'],'8.8.8.8');self.assertEqual(result['current']['ip'],'8.8.8.8')
 def test_fallback_airport_ip_is_also_hidden_in_current_exit(self):
  result=probe.redact_private_metrics({'airport':{'ip':'1.0.0.1'},'current':{'ok':True,'ip':'1.0.0.1','mean_ms':100}}, {})
  self.assertIsNone(result['current']['ip']);self.assertTrue(result['current']['ip_hidden']);self.assertEqual(result['current']['mean_ms'],100)
 def test_hidden_local_ip_never_starts_a_physical_network_probe(self):
  with tempfile.TemporaryDirectory() as folder:
   base=pathlib.Path(folder);(base/'clash-verge.yaml').write_text('proxies: []\n',encoding='utf-8');(base/'config.yaml').write_text('mixed-port: 7897\n',encoding='utf-8')
   (base/'current-state.json').write_text(json.dumps({'state':'RUNNING','selected':'Example','observed_at_unix':time.time()}),encoding='utf-8')
   with patch.object(probe,'trace_proxy',return_value=('8.8.8.8',100,'US')),patch.object(probe,'physical_target') as target,patch.object(probe,'trace_physical') as physical:
    result=probe.probe({'base':folder,'report_dir':folder})
   target.assert_not_called();physical.assert_not_called();self.assertTrue(result['local']['hidden'])
 def test_common_flags_use_local_canvas_drawings_and_unknown_codes_use_badges(self):
  for code in ('CN','US','JP','HK','SG','KR','GB','DE','FR','CA','AU','TW',None,'XY'):
   canvas=Mock();draw_flag(canvas,0,0,code)
   canvas.create_rectangle.assert_called()
   if code in (None,'XY'):canvas.create_text.assert_called()
  self.assertEqual(country_label('JP'),'日本');self.assertEqual(country_label(None),'未知')
 def test_physical_probe_requires_existing_cloudflare_host_route(self):
  with self.assertRaises(ValueError):probe.physical_target({'tun':{'route-exclude-address':['8.8.8.8/32']}})
  self.assertEqual(probe.physical_target({'tun':{'route-exclude-address':['104.17.1.1/32']}}),('104.17.1.1','www.cloudflare.com'))
 def test_ui_renders_drags_refreshes_and_collapses(self):
  with tempfile.TemporaryDirectory() as temp:
   settings=pathlib.Path(temp)/'settings.json';settings.write_text(json.dumps({'report_dir':temp}),encoding='utf-8')
   with patch.object(sys,'argv',['island','--demo']):app=island.Island(settings,demo=True)
   try:
    app.show();app.root.update()
    text=[app.canvas.itemcget(item,'text') for item in app.canvas.find_all() if app.canvas.type(item)=='text']
    self.assertIn('本地网络',text);self.assertIn('不探测本地公网 IP',text)
    self.assertNotIn('192.0.2.10',text);self.assertNotIn('198.51.100.20',text)
    self.assertNotIn('中国',text);self.assertIn('日本',text)
    self.assertTrue(any('639' in value for value in text))
    self.assertEqual(app.canvas.winfo_width(),800)
    app.toggle();self.assertTrue(app.compact);app.root.update();self.assertEqual(app.canvas.winfo_height(),68)
    app.toggle();self.assertFalse(app.compact)
    app.refresh();self.assertGreater(app.next_refresh,time.monotonic()+59)
    app.drag=(0,0);event=Mock(x_root=100,y_root=100);app.move(event);app.root.update_idletasks();app.release(event)
    self.assertTrue((pathlib.Path(temp)/'island-window.json').exists())
   finally:app.close()
 def test_ui_follows_clash_exit_without_starting_a_probe(self):
  app=object.__new__(island.Island);app.demo=False;app.close=Mock()
  with patch.object(island,'clash_running',return_value=False):app.tick()
  app.close.assert_called_once_with(0)
 def test_manual_refresh_does_not_spawn_duplicate_workers(self):
  app=object.__new__(island.Island);app.worker=Mock();app.demo=False
  with patch.object(island.subprocess,'Popen') as popen:app.refresh();popen.assert_not_called()
 def test_manual_refresh_reads_core_before_starting_measurements(self):
  app=object.__new__(island.Island);app.worker=None;app.demo=False;app.start_snapshot=Mock();app.start_probe=Mock();app.draw=Mock()
  app.refresh()
  app.start_snapshot.assert_called_once();app.start_probe.assert_not_called();self.assertTrue(app.refresh_pending)
 def test_switch_immediately_clears_old_measurements_and_starts_fresh_probe(self):
  app=object.__new__(island.Island);app.live_state={'state':'RUNNING','selected':'Old'};app.data={'selected':'Old','current':{'mean_ms':999}}
  app.settings={'fallback_to_airport':True};app.worker=Mock();app.worker.poll.return_value=None;old_worker=app.worker;app.start_probe=Mock()
  with patch.object(island,'stop_process') as stop:
   app.accept_snapshot({'state':'RUNNING','selected':'New','active_route':'fixed-exit'})
  stop.assert_called_once_with(old_worker);self.assertEqual(app.live_state['selected'],'New');self.assertEqual(app.data['selected'],'New')
  self.assertNotIn('current',app.data);app.start_probe.assert_called_once()
 def test_old_or_changed_measurement_cannot_overwrite_new_selection(self):
  app=object.__new__(island.Island);app.live_state={'state':'RUNNING','selected':'New'};app.data={'selected':'New'}
  self.assertFalse(app.accept_metrics({'selected':'Old','selection_fresh':True}));self.assertEqual(app.data['selected'],'New')
  self.assertFalse(app.accept_metrics({'selected':'New','selection_fresh':False,'selection_changed_during_test':True}))
  self.assertTrue(app.accept_metrics({'selected':'New','selection_fresh':True,'current':{'mean_ms':123}}));self.assertEqual(app.data['current']['mean_ms'],123)
 def test_probe_uses_fresh_core_selection_instead_of_the_old_export(self):
  with tempfile.TemporaryDirectory() as folder:
   base=pathlib.Path(folder);(base/'clash-verge.yaml').write_text('proxies: []\n',encoding='utf-8');(base/'config.yaml').write_text('mixed-port: 7897\n',encoding='utf-8')
   (base/'current-state.json').write_text(json.dumps({'state':'RUNNING','selected':'Old','observed_at_unix':time.time()}),encoding='utf-8')
   snapshot={'state':'RUNNING','selected':'New','observed_at_unix':time.time()}
   with patch.object(probe,'live_snapshot',return_value=snapshot) as live,patch.object(probe,'trace_proxy',return_value=('8.8.8.8',100,'US')):
    result=probe.probe({'base':folder,'report_dir':folder})
   self.assertEqual(result['selected'],'New');self.assertTrue(result['selection_fresh']);self.assertEqual(live.call_count,2)
 def test_core_snapshot_timeout_returns_error_without_using_cached_node(self):
  with patch.object(probe.subprocess,'run',side_effect=probe.subprocess.TimeoutExpired('test',4)):
   value=probe.live_snapshot({'python':sys.executable})
  self.assertEqual(value['state'],'ERROR');self.assertIsNone(value['selected'])
 def test_daemon_starts_island_with_clash_and_stops_it_on_exit(self):
  class EndLoop(Exception):pass
  with tempfile.TemporaryDirectory() as temp:
   data=pathlib.Path(temp);sync.save(data/'committed.json',{'stamp':sync.stamp('r',{'proxies':[]}), 'time':1000})
   clock=[1000.0];children=[]
   def sleep(_):
    clock[0]+=.5
    if clock[0]>1003:raise EndLoop()
   def spawn(args,**kwargs):
    child=Mock();child.poll.return_value=None;children.append((args,child));return child
   kernel=Mock();kernel.CreateMutexW.return_value=1;kernel.GetLastError.return_value=0
   with patch.object(sync,'DATA',data),patch.object(sync,'settings',return_value={'report_dir':temp,'python':sys.executable,'enable_island':True}),patch.object(sync.ctypes,'windll',Mock(kernel32=kernel)),patch.object(sync.time,'time',side_effect=lambda:clock[0]),patch.object(sync.time,'sleep',side_effect=sleep),patch.object(sync,'running',side_effect=lambda:clock[0]<1002),patch.object(sync.subprocess,'Popen',side_effect=spawn),patch.object(sync,'kill_worker') as kill:
    with self.assertRaises(EndLoop):sync.daemon()
   windows=[child for args,child in children if str(ROOT/'island.py') in args]
   self.assertEqual(len(windows),1);self.assertIn(((windows[0],),{}),kill.call_args_list)

if __name__=='__main__':unittest.main(verbosity=2)
