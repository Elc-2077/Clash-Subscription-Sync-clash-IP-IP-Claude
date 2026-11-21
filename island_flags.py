# -*- coding: utf-8 -*-
"""Offline Canvas flag badges. No downloads or extra geolocation requests.

Common destinations have compact original vector drawings. Other ISO codes
remain readable as code badges, rather than showing an unrelated flag.
"""
import math

NAMES={'CN':'中国','US':'美国','JP':'日本','HK':'香港','MO':'澳门','TW':'台湾','SG':'新加坡','KR':'韩国','GB':'英国','DE':'德国','FR':'法国','NL':'荷兰','CA':'加拿大','AU':'澳大利亚','NZ':'新西兰','RU':'俄罗斯','IN':'印度','IT':'意大利','ES':'西班牙','BR':'巴西','CH':'瑞士','SE':'瑞典','NO':'挪威','DK':'丹麦','FI':'芬兰','AT':'奥地利','BE':'比利时','IE':'爱尔兰','PL':'波兰','UA':'乌克兰','TH':'泰国','VN':'越南','ID':'印度尼西亚','PH':'菲律宾','MY':'马来西亚','TR':'土耳其','IL':'以色列','AE':'阿联酋','ZA':'南非','MX':'墨西哥','PT':'葡萄牙','AR':'阿根廷','CL':'智利','RO':'罗马尼亚'}

def country_label(code):return NAMES.get(code,code or '未知')

def draw_flag(canvas,x,y,code,w=26,h=17):
    def rect(a,b,c,d,color):canvas.create_rectangle(x+a*w,y+b*h,x+c*w,y+d*h,fill=color,outline='')
    def oval(a,b,c,d,color):canvas.create_oval(x+a*w,y+b*h,x+c*w,y+d*h,fill=color,outline='')
    def poly(points,color):canvas.create_polygon(*[v for a,b in points for v in (x+a*w,y+b*h)],fill=color,outline='')
    def star(cx,cy,r,color,n=5):
        points=[]
        for i in range(n*2):
            angle=-math.pi/2+i*math.pi/n;radius=r if i%2==0 else r*.4
            points.extend((x+cx*w+math.cos(angle)*radius*h,y+cy*h+math.sin(angle)*radius*h))
        canvas.create_polygon(points,fill=color,outline='')
    def stripes(colors,vertical=False):
        for i,color in enumerate(colors):
            if vertical:rect(i/len(colors),0,(i+1)/len(colors),1,color)
            else:rect(0,i/len(colors),1,(i+1)/len(colors),color)
    def union(a=0,b=0,c=1,d=1):
        rect(a,b,c,d,'#183269');dx=c-a;dy=d-b
        for points in ([(a,b),(a+.1*dx,b),(c,d-.14*dy),(c,d),(c-.1*dx,d),(a,b+.14*dy)],[(c,b),(c,b+.14*dy),(a+.1*dx,d),(a,d),(a,d-.14*dy),(c-.1*dx,b)]):poly(points,'white')
        rect(a,b+.35*dy,c,b+.65*dy,'white');rect(a+.4*dx,b,a+.6*dx,d,'white')
        rect(a,b+.43*dy,c,b+.57*dy,'#ce243e');rect(a+.46*dx,b,a+.54*dx,d,'#ce243e')
    red='#dc2638';blue='#21468b';green='#178448';white='#ffffff';gold='#ffda44'
    if code=='US':
        stripes([red if i%2==0 else white for i in range(13)]);rect(0,0,.45,.54,blue)
        for row in range(3):
            for col in range(4):star(.065+col*.1,.09+row*.16,.035,white)
    elif code=='CN':
        rect(0,0,1,1,red);star(.2,.28,.19,gold)
        for a,b in ((.4,.12),(.48,.27),(.48,.45),(.39,.57)):star(a,b,.064,gold)
    elif code=='JP':rect(0,0,1,1,white);oval(.31,.21,.69,.79,'#bc002d')
    elif code=='GB':union()
    elif code in ('AU','NZ'):
        rect(0,0,1,1,'#123164');union(0,0,.49,.51)
        for a,b in ((.77,.23),(.63,.54),(.88,.59),(.76,.83)):star(a,b,.085,white if code=='AU' else red)
        if code=='AU':star(.25,.78,.12,white)
    elif code in ('FR','IT','IE','BE','RO','MX'):
        colors={'FR':[blue,white,red],'IT':[green,white,red],'IE':[green,white,'#f18d32'],'BE':['#141414',gold,red],'RO':[blue,gold,red],'MX':[green,white,red]}
        stripes(colors[code],True)
        if code=='MX':oval(.46,.39,.55,.65,green)
    elif code in ('DE','NL','RU','AT','PL','UA','ID','TH','AR'):
        colors={'DE':['#141414',red,gold],'NL':[red,white,blue],'RU':[white,blue,red],'AT':[red,white,red],'PL':[white,red],'UA':[blue,gold],'ID':[red,white],'TH':[red,white,blue,blue,white,red],'AR':['#74b5e8',white,'#74b5e8']}
        stripes(colors[code])
        if code=='AR':oval(.46,.41,.54,.59,gold)
    elif code in ('SE','NO','DK','FI'):
        base,cross={'SE':(blue,gold),'NO':(red,blue),'DK':(red,white),'FI':(white,blue)}[code]
        rect(0,0,1,1,base)
        if code=='NO':rect(.27,0,.43,1,white);rect(0,.35,1,.65,white)
        rect(.31,0,.39,1,cross);rect(0,.42,1,.58,cross)
    elif code=='CH':rect(0,0,1,1,red);rect(.42,.18,.58,.82,white);rect(.28,.37,.72,.63,white)
    elif code=='CA':
        stripes([red,white,white,red],True)
        poly([(.5,.17),(.55,.36),(.63,.29),(.6,.47),(.69,.48),(.59,.63),(.61,.73),(.52,.69),(.52,.85),(.48,.85),(.48,.69),(.39,.73),(.41,.63),(.31,.48),(.4,.47),(.37,.29),(.45,.36)],red)
    elif code in ('HK','MO'):
        rect(0,0,1,1,red if code=='HK' else '#087d65')
        for i in range(5):
            a=-math.pi/2+i*math.pi*2/5;cx=.5+math.cos(a)*.13;cy=.5+math.sin(a)*.2
            oval(cx-.07,cy-.1,cx+.07,cy+.1,white)
        oval(.47,.46,.53,.54,gold if code=='MO' else red)
    elif code=='TW':rect(0,0,1,1,red);rect(0,0,.5,.55,blue);star(.25,.27,.18,white,12)
    elif code in ('SG','MY','TR'):
        if code=='SG':stripes([red,white]);color=white;bg=red
        elif code=='MY':stripes([red if i%2==0 else white for i in range(14)]);rect(0,0,.55,.58,blue);color=gold;bg=blue
        else:rect(0,0,1,1,red);color=white;bg=red
        oval(.1,.1,.34,.49,color);oval(.17,.08,.37,.43,bg);star(.41,.27,.08,color)
    elif code=='VN':rect(0,0,1,1,red);star(.5,.5,.35,gold)
    elif code=='IN':stripes(['#f69a39',white,green]);oval(.43,.38,.57,.62,blue);oval(.46,.42,.54,.58,white)
    elif code=='ES':stripes([red,gold,gold,red]);rect(.22,.35,.3,.65,red)
    elif code=='BR':rect(0,0,1,1,green);poly([(.5,.12),(.9,.5),(.5,.88),(.1,.5)],gold);oval(.32,.23,.68,.77,blue)
    elif code=='KR':
        rect(0,0,1,1,white);oval(.34,.22,.66,.76,red);oval(.34,.43,.66,.76,blue)
        for a,b in ((.12,.14),(.76,.14),(.12,.76),(.76,.76)):rect(a,b,a+.12,b+.08,'#151515')
    else:
        rect(0,0,1,1,'#323b4b');canvas.create_text(x+w/2,y+h/2,text=code or '?',fill=white,font=('Segoe UI',8,'bold'))
    canvas.create_rectangle(x,y,x+w,y+h,outline='#566071',width=1)
