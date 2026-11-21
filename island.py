# -*- coding: utf-8 -*-
"""Draggable desktop island. Follows Clash lifetime; stores only display data."""
import ctypes,json,os,subprocess,sys,time,tkinter as tk
from pathlib import Path
import psutil
from island_probe import read,stop_process,redact_private_metrics
from island_flags import country_label,draw_flag

BACKGROUND='#101318';CARD='#1b2029';TEXT='#f0f3fa';MUTED='#8993a4';GREEN='#8ce6c5';BLUE='#94baff';AMBER='#f0c582';TRANSPARENT='#010203'

def clash_running():
    for pid in psutil.pids():
        try:
            if psutil.Process(pid).name().lower()=='clash-verge.exe':return True
        except (psutil.Error,OSError):pass
    return False

class Island:
    def __init__(self,settings_path,demo=False):
        self.settings_path=Path(settings_path);self.settings=read(settings_path);self.folder=Path(self.settings['report_dir']);self.demo=demo
        self.root=tk.Tk();self.root.title('Clash Network Island');self.root.configure(bg=TRANSPARENT)
        self.root.overrideredirect('--qa' not in sys.argv);self.root.attributes('-topmost',True)
        if os.name=='nt':self.root.wm_attributes('-transparentcolor',TRANSPARENT)
        self.width=800;self.height=232;self.compact=False;self.worker=None;self.started=0;self.next_refresh=0;self.data={};self.error='';self.drag=None
        self.live_worker=None;self.live_started=0;self.next_live=0;self.live_state={};self.refresh_pending=True
        self.canvas=tk.Canvas(self.root,width=self.width,height=self.height,bg=TRANSPARENT,highlightthickness=0)
        self.canvas.pack();self.root.update_idletasks()
        x=(self.root.winfo_screenwidth()-self.width)//2;y=18
        try:
            position=read(self.folder/'island-window.json');x=int(position['x']);y=int(position['y'])
        except (OSError,ValueError,KeyError):pass
        x=max(0,min(x,self.root.winfo_screenwidth()-self.width));y=max(0,min(y,self.root.winfo_screenheight()-self.height))
        self.root.geometry('%dx%d+%d+%d'%(self.width,self.height,x,y))
        self.root.deiconify()
        self.root.after(50,self.show)
        self.canvas.bind('<ButtonPress-1>',self.press);self.canvas.bind('<B1-Motion>',self.move);self.canvas.bind('<ButtonRelease-1>',self.release)
        self.canvas.bind('<Double-Button-1>',lambda e:self.toggle());self.root.bind('<Escape>',lambda e:self.close())
        self.root.bind('<Control-r>',lambda e:self.refresh())
        if demo:
            self.data=self.demo_data();self.next_refresh=time.monotonic()+60
            self.live_state={'state':'RUNNING','selected':self.data['selected']};self.refresh_pending=False
        self.draw();self.root.after(100,self.tick)
    def show(self):
        self.root.deiconify();self.root.lift()
        if os.name=='nt':
            # A hidden-console parent may pass SW_HIDE to the first Tk window.
            # Show only our own window, without activating another application.
            user=ctypes.windll.user32
            user.GetAncestor.argtypes=[ctypes.c_void_p,ctypes.c_uint];user.GetAncestor.restype=ctypes.c_void_p
            user.ShowWindow.argtypes=[ctypes.c_void_p,ctypes.c_int]
            handle=user.GetAncestor(self.root.winfo_id(),2)
            user.ShowWindow(handle,4)
    def round(self,x,y,w,h,r,fill,outline=None):
        points=[x+r,y,x+w-r,y,x+w,y,x+w,y+r,x+w,y+h-r,x+w,y+h,x+w-r,y+h,x+r,y+h,x,y+h,x,y+h-r,x,y+r,x,y]
        return self.canvas.create_polygon(points,smooth=True,splinesteps=24,fill=fill,outline=outline or fill)
    def text(self,x,y,value,size=10,color=TEXT,bold=False,anchor='nw',width=None):
        args={'text':str(value),'font':('Microsoft YaHei UI',size,'bold' if bold else 'normal'),'fill':color,'anchor':anchor}
        if width:args['width']=width
        return self.canvas.create_text(x,y,**args)
    def fit(self,value,limit):return value if len(value)<=limit else value[:limit-1]+'…'
    def demo_data(self):
        return {'selected':'Example · Airport 01','completed_at_unix':time.time(),'selection_fresh':True,'local':{'ok':True,'ip':'192.0.2.10','country':'CN'},'airport':{'ok':True,'ip':'198.51.100.20','country':'JP','mean_ms':183.4},'fixed':{'ok':True,'ip':'203.0.113.30','country':'US','mean_ms':641.5},'current':{'ok':True,'ip':'203.0.113.30','country':'US','mean_ms':639.2},'fallback_configured':True}
    def draw(self):
        c=self.canvas;c.delete('all');height=68 if self.compact else self.height
        self.round(1,1,self.width-3,height-3,30,BACKGROUND,'#2c3441')
        # Mask old on-disk/in-memory measurements too, before any Canvas text.
        redact_private_metrics(self.data,self.settings)
        active=self.data.get('current',{});age=time.time()-self.data.get('completed_at_unix',0)
        final_text='机场出口已隐藏' if active.get('ip_hidden') else str(active.get('ip') or '未测得')
        healthy=bool(active.get('ok')) and age<100 and not self.error and self.data.get('selection_fresh')
        c.create_oval(22,24,29,31,fill=GREEN if healthy else AMBER,outline='')
        self.text(39,17,'NETWORK ISLAND',11,GREEN,True)
        selection=self.live_state.get('selected') or ('节点读取失败' if self.live_state.get('state')=='ERROR' else '等待内核状态')
        self.text(207,18,self.fit(selection,39),10,MUTED)
        self.text(630,16,'刷新中…' if self.worker or self.refresh_pending else '↻ 刷新',10,BLUE)
        self.text(730,15,'+' if self.compact else '−',14,MUTED)
        self.text(768,17,'×',12,MUTED)
        if self.compact:
            self.text(39,43,'最终出口 '+final_text,9,TEXT)
            draw_flag(c,275,41,active.get('country'),22,14)
            ms=active.get('mean_ms');self.text(320,43,'总耗时 '+(str(round(ms))+' ms' if ms is not None else '—'),9,GREEN)
            return
        cards=[('本地公网 IP','local',MUTED,'物理网卡 · 仅显示地址'),('机场出口 IP','airport',BLUE,'仅经机场 · HTTPS 平均'),('固定出口 IP','fixed',GREEN,'机场 → 固定出口 · HTTPS 平均')]
        for i,(label,key,color,caption) in enumerate(cards):
            x=20+i*259;item=self.data.get(key,{})
            self.round(x,57,243,96,16,CARD)
            if key=='local' and self.settings.get('hide_local_info',True):
                self.text(x+15,67,'本地网络',9,MUTED)
                self.text(x+14,89,'信息已隐藏',16,MUTED,True)
                self.text(x+15,124,'不探测本地公网 IP',9,MUTED)
                continue
            self.text(x+15,67,label,9,color)
            draw_flag(c,x+155,68,item.get('country'))
            self.text(x+186,69,self.fit(country_label(item.get('country')),5),8,MUTED)
            address='IP 已隐藏' if item.get('ip_hidden') else item.get('ip') if item.get('ok') else '—'
            self.text(x+14,87,address or '—',18,TEXT,True)
            if key=='local':self.text(x+15,124,caption,9,MUTED)
            else:
                ms=item.get('mean_ms');latency=(str(round(ms))+' ms') if ms is not None else ('超时 / 未测得' if self.data.get('completed_at_unix') else '等待测试')
                self.text(x+15,123,latency,10,color,True)
                self.text(x+108,125,'仅经机场' if key=='airport' else '含机场前置',8,MUTED)
        self.text(269,91,'›',18,MUTED);self.text(528,91,'›',18,MUTED)
        final=final_text
        self.text(25,164,'当前最终出口',9,MUTED);self.text(127,160,final,15,TEXT,True)
        draw_flag(c,365,163,active.get('country'),25,17)
        ms=active.get('mean_ms');self.text(435,164,'当前总耗时',9,MUTED)
        self.text(530,160,(str(round(ms))+' ms') if ms is not None else '—',15,GREEN,True)
        fallback=self.data.get('fallback_configured',False)
        badge='固定优先 / 机场回退' if fallback else '固定出口模式'
        if self.data.get('core_active_route')=='airport-fallback':badge='正在回退机场'
        self.text(650,166,badge,8,AMBER if fallback else MUTED)
        if self.worker:footer='正在实测公网出口与 HTTPS 耗时…'
        elif self.refresh_pending:footer='正在读取当前节点，准备实测…'
        elif self.error:footer=self.error+' · 上次结果保留，不能视为当前状态'
        elif not self.data.get('completed_at_unix'):footer='等待测试 · 每 60 秒刷新'
        else:
            stamp=time.strftime('%H:%M:%S',time.localtime(self.data.get('completed_at_unix',0)))
            footer='更新 '+stamp+'  ·  '+str(max(0,int(self.next_refresh-time.monotonic())))+'s 后刷新  ·  拖动移动 / 双击收起'
            if not self.data.get('selection_fresh'):footer='入口状态过期或切换中 · '+footer
        self.text(25,204,self.fit(footer,94),8,MUTED)
    def press(self,event):
        if event.y<48:
            if event.x>758:self.close();return
            if event.x>716:self.toggle();return
            if event.x>610:self.refresh();return
        self.drag=(event.x_root-self.root.winfo_x(),event.y_root-self.root.winfo_y())
    def move(self,event):
        if not self.drag:return
        x=event.x_root-self.drag[0];y=event.y_root-self.drag[1]
        self.root.geometry('+%d+%d'%(x,y))
    def release(self,event):
        if self.drag:
            try:(self.folder/'island-window.json').write_text(json.dumps({'x':self.root.winfo_x(),'y':self.root.winfo_y()}),encoding='utf-8')
            except OSError:pass
        self.drag=None
    def toggle(self):
        self.compact=not self.compact;h=68 if self.compact else self.height
        self.canvas.configure(height=h);self.root.geometry('%dx%d'%(self.width,h));self.draw()
    def refresh(self):
        if self.worker:return
        if self.demo:self.next_refresh=time.monotonic()+60;self.draw();return
        self.refresh_pending=True;self.start_snapshot();self.draw()
    def start_snapshot(self):
        if self.live_worker:return
        try:
            self.live_worker=subprocess.Popen([self.settings['python'],'-B',str(Path(__file__).with_name('sync.py')),'--snapshot'],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,creationflags=0x08000000)
            self.live_started=time.monotonic();self.next_live=self.live_started+3
        except OSError:
            self.live_state={'state':'ERROR','selected':None};self.error='节点读取失败';self.next_live=time.monotonic()+3
    def accept_snapshot(self,value):
        previous=self.live_state.get('selected');selected=value.get('selected')
        self.live_state=value
        if value.get('state')!='RUNNING' or not selected:
            self.error='当前节点读取失败';self.data['selection_fresh']=False
            return
        if selected!=previous:
            if self.worker and self.worker.poll() is None:stop_process(self.worker)
            self.worker=None
            self.data={'selected':selected,'selection_fresh':False,'fallback_configured':self.settings.get('fallback_to_airport',False),'core_active_route':value.get('active_route')}
            self.refresh_pending=True
        self.error=''
        if self.refresh_pending and not self.worker:self.start_probe()
    def start_probe(self):
        self.refresh_pending=False
        self.error='';self.started=time.monotonic();self.next_refresh=self.started+60
        try:
            self.worker=subprocess.Popen([self.settings['python'],'-B',str(Path(__file__).with_name('island_probe.py')),str(self.settings_path)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=0x08000000)
        except OSError:self.error='无法启动测试'
        self.draw()
    def accept_metrics(self,result):
        if self.live_state.get('state')=='RUNNING' and result.get('selected')==self.live_state.get('selected') and result.get('selection_fresh') and not result.get('selection_changed_during_test'):
            self.data=result;return True
        self.refresh_pending=True;self.next_live=0
        return False
    def tick(self):
        if not self.demo and not clash_running():self.close(0);return
        if not self.demo:
            if self.live_worker:
                if self.live_worker.poll() is not None:
                    process=self.live_worker;self.live_worker=None
                    try:
                        stdout,_=process.communicate(timeout=.2)
                        if process.returncode:raise ValueError('Snapshot child error')
                        self.accept_snapshot(json.loads(stdout))
                    except Exception:self.accept_snapshot({'state':'ERROR','selected':None})
                elif time.monotonic()-self.live_started>4:
                    stop_process(self.live_worker);self.live_worker=None
                    self.accept_snapshot({'state':'ERROR','selected':None})
            if not self.live_worker and time.monotonic()>=self.next_live:self.start_snapshot()
        if self.worker:
            if self.worker.poll() is not None:
                code=self.worker.returncode;self.worker=None
                if code==0:
                    try:
                        result=read(self.folder/'island-metrics.json')
                        self.accept_metrics(result)
                    except (OSError,ValueError):self.error='测试结果无法读取'
                else:self.error='测试未完成'
            elif time.monotonic()-self.started>32:
                stop_process(self.worker);self.worker=None;self.error='测试超过 32 秒'
        if not self.worker and not self.refresh_pending and time.monotonic()>=self.next_refresh:self.refresh()
        self.draw();self.root.after(500,self.tick)
    def close(self,code=42):
        if self.worker and self.worker.poll() is None:stop_process(self.worker)
        if self.live_worker and self.live_worker.poll() is None:stop_process(self.live_worker)
        self.root.destroy();self.exit_code=code
    def run(self):
        self.exit_code=0;self.root.mainloop();return self.exit_code

if __name__=='__main__':
    try:
        if os.name=='nt':
            try:ctypes.windll.shcore.SetProcessDpiAwareness(1)
            except OSError:pass
        app=Island(sys.argv[1],demo='--demo' in sys.argv);sys.exit(app.run())
    except Exception as exc:
        # Do not log configuration or node credentials into UI error messages.
        try:
            folder=Path(read(sys.argv[1])['report_dir'])
            (folder/'island-ui-error.json').write_text(json.dumps({'error':type(exc).__name__,'time':time.time()}),encoding='utf-8')
        except Exception:pass
        sys.exit(1)
