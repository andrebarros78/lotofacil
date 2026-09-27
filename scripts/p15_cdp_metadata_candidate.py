from __future__ import annotations
import json, subprocess, sys, time, unicodedata, re, urllib.request
import websocket

CHROME=r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT=9231
PROFILE=r"C:\Users\andre\P15Tools\ChromeP15MetadataCandidate"

def wait_port():
    end=time.time()+12
    while time.time()<end:
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{PORT}/json/version',timeout=2): return
        except Exception: time.sleep(.35)
    raise RuntimeError('CDP_START_TIMEOUT')

def main():
    video_id=sys.argv[1]
    chrome=subprocess.Popen([CHROME,'--headless=new','--disable-gpu','--no-first-run','--no-default-browser-check',f'--remote-debugging-port={PORT}','--remote-debugging-address=127.0.0.1','--remote-allow-origins=*',f'--user-data-dir={PROFILE}','about:blank'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    ws=None
    out={'video_id':video_id,'status':'ERROR'}
    try:
        wait_port()
        with urllib.request.urlopen(f'http://127.0.0.1:{PORT}/json',timeout=5) as r: target=json.loads(r.read().decode())[0]
        ws=websocket.create_connection(target['webSocketDebuggerUrl'],timeout=8,origin=f'http://127.0.0.1:{PORT}')
        seq=0
        def cmd(method,params=None):
            nonlocal seq
            seq+=1; my=seq
            ws.send(json.dumps({'id':my,'method':method,'params':params or {}}))
            while True:
                m=json.loads(ws.recv())
                if m.get('id')==my:return m
        def ev(expr):
            r=cmd('Runtime.evaluate',{'expression':expr,'returnByValue':True,'userGesture':True})
            return (((r.get('result') or {}).get('result') or {}).get('value'))
        cmd('Runtime.enable'); cmd('Page.enable'); cmd('Page.navigate',{'url':f'https://www.youtube.com/watch?v={video_id}'})
        end=time.time()+12; player=None
        while time.time()<end:
            raw=ev('JSON.stringify(window.ytInitialPlayerResponse||null)')
            if raw and raw!='null': player=json.loads(raw); break
            time.sleep(.7)
        if not player:
            out['error']='PLAYER_RESPONSE_UNAVAILABLE'
        else:
            d=player.get('videoDetails') or {}; p=player.get('playabilityStatus') or {}
            out.update({'status':'OK','title':d.get('title') or '', 'description':d.get('shortDescription') or '', 'duration_seconds':int(d.get('lengthSeconds') or 0),'channel_id':d.get('channelId'),'author':d.get('author'),'playability_status':p.get('status')})
    except Exception as e:
        out['error']=f'{type(e).__name__}: {e}'[:800]
    finally:
        try:
            if ws: ws.close()
        except Exception: pass
        try:
            chrome.terminate(); chrome.wait(timeout=3)
        except Exception:
            try: chrome.kill()
            except Exception: pass
    print(json.dumps(out,ensure_ascii=False),flush=True)
if __name__=='__main__': main()
