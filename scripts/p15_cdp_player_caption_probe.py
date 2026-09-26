from __future__ import annotations
import json, subprocess, sys, time, urllib.parse, urllib.request
import websocket

CHROME=r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PROFILE=r"C:\Users\andre\P15Tools\ChromeP15PlayerCaption"
PORT=9226

def wait_port():
    for _ in range(40):
        try:
            urllib.request.urlopen(f'http://127.0.0.1:{PORT}/json/version',timeout=2).read(); return
        except Exception: time.sleep(.5)
    raise RuntimeError('CDP did not start')

def main():
    vid=sys.argv[1]
    chrome=subprocess.Popen([CHROME,'--headless=new','--disable-gpu','--no-first-run','--no-default-browser-check',f'--remote-debugging-port={PORT}','--remote-debugging-address=127.0.0.1','--remote-allow-origins=*',f'--user-data-dir={PROFILE}','about:blank'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    ws=None; target=None
    try:
        wait_port()
        u='https://www.youtube.com/watch?v='+vid
        req=urllib.request.Request(f'http://127.0.0.1:{PORT}/json/new?'+urllib.parse.quote(u,safe=':/?=&'),method='PUT')
        target=json.loads(urllib.request.urlopen(req,timeout=10).read())
        ws=websocket.create_connection(target['webSocketDebuggerUrl'],timeout=30,origin=f'http://127.0.0.1:{PORT}')
        seq=0
        def cmd(method,params=None):
            nonlocal seq; seq+=1; i=seq
            ws.send(json.dumps({'id':i,'method':method,'params':params or {}}))
            while True:
                m=json.loads(ws.recv())
                if m.get('id')==i:return m
        def ev(expr,await_promise=False):
            r=cmd('Runtime.evaluate',{'expression':expr,'returnByValue':True,'awaitPromise':await_promise,'userGesture':True})
            return (((r.get('result') or {}).get('result') or {}).get('value'))
        cmd('Runtime.enable'); cmd('Page.enable')
        for _ in range(20):
            if ev("!!window.ytcfg && !!ytcfg.get('INNERTUBE_API_KEY')"): break
            time.sleep(1)
        js=f'''(async()=>{{
          const key=ytcfg.get('INNERTUBE_API_KEY');
          const context=ytcfg.get('INNERTUBE_CONTEXT');
          const pr=await fetch('/youtubei/v1/player?key='+encodeURIComponent(key),{{method:'POST',credentials:'include',headers:{{'content-type':'application/json'}},body:JSON.stringify({{context,videoId:{json.dumps(vid)}}})}});
          const pobj=await pr.json();
          const tracks=((((pobj||{{}}).captions||{{}}).playerCaptionsTracklistRenderer||{{}}).captionTracks||[]);
          const t=tracks.find(x=>['pt','pt-BR','pt-PT'].includes(x.languageCode))||tracks[0]||null;
          let capStatus=null, capText='';
          if(t&&t.baseUrl){{const cr=await fetch(t.baseUrl,{{credentials:'include'}});capStatus=cr.status;capText=await cr.text();}}
          return JSON.stringify({{playerStatus:pr.status,playability:(pobj.playabilityStatus||{{}}).status,trackCount:tracks.length,track:t?{{languageCode:t.languageCode,kind:t.kind,name:t.name}}:null,captionStatus:capStatus,captionLength:capText.length,captionPrefix:capText.slice(0,300)}});
        }})()'''
        print(ev(js,True))
        return 0
    finally:
        try:
            if ws: ws.close()
        except Exception: pass
        chrome.terminate()
        try: chrome.wait(timeout=10)
        except Exception: chrome.kill()
if __name__=='__main__': raise SystemExit(main())
