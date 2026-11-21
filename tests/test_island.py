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
    self.assertIn('本地公网 IP',text);self.assertIn('物理网卡 · 仅显示地址',text)
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
