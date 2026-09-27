from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.parse
import urllib.request

import websocket

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9229
PROFILE = r"C:\Users\andre\P15Tools\ChromeP15StreamProbeV2"


def wait_port(seconds=20):
    end=time.time()+seconds
    while time.time()<end:
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{PORT}/json/version', timeout=2): return
        except Exception: time.sleep(.5)
    raise RuntimeError('CDP did not start')


def main():
    video_id=sys.argv[1]
    watch=f'https://www.youtube.com/watch?v={video_id}'
    chrome=subprocess.Popen([
        CHROME,'--headless=new','--disable-gpu','--no-first-run','--no-default-browser-check',
        '--remote-debugging-address=127.0.0.1',f'--remote-debugging-port={PORT}','--remote-allow-origins=*',
        f'--user-data-dir={PROFILE}','about:blank'
    ],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    ws=None
    try:
        wait_port()
        req=urllib.request.Request(f'http://127.0.0.1:{PORT}/json/new?'+urllib.parse.quote(watch,safe=':/?=&'),method='PUT')
        with urllib.request.urlopen(req,timeout=8) as r: target=json.loads(r.read().decode())
        ws=websocket.create_connection(target['webSocketDebuggerUrl'],timeout=15,origin=f'http://127.0.0.1:{PORT}')
        seq=0
        def cmd(method,params=None):
            nonlocal seq
            seq+=1; mid=seq
            ws.send(json.dumps({'id':mid,'method':method,'params':params or {}}))
            while True:
                m=json.loads(ws.recv())
                if m.get('id')==mid:return m
        def ev(expr):
            r=cmd('Runtime.evaluate',{'expression':expr,'returnByValue':True})
            return (((r.get('result') or {}).get('result') or {}).get('value'))
        cmd('Runtime.enable'); cmd('Page.enable')
        player=None; end=time.time()+15
        while time.time()<end:
            raw=ev('JSON.stringify(window.ytInitialPlayerResponse||null)')
            if raw and raw!='null': player=json.loads(raw); break
            time.sleep(1)
        if not player: raise RuntimeError('no player')
        streaming=player.get('streamingData') or {}
        out={
            'video_id':video_id,
            'title':(player.get('videoDetails') or {}).get('title'),
            'streaming_keys':sorted(streaming.keys()),
            'hlsManifestUrl':streaming.get('hlsManifestUrl'),
            'dashManifestUrl':streaming.get('dashManifestUrl'),
            'serverAbrStreamingUrl':streaming.get('serverAbrStreamingUrl'),
            'expiresInSeconds':streaming.get('expiresInSeconds'),
            'formats_count':len(streaming.get('formats') or []),
            'adaptive_count':len(streaming.get('adaptiveFormats') or []),
        }
        for field in ('hlsManifestUrl','dashManifestUrl','serverAbrStreamingUrl'):
            url=out.get(field)
            if url:
                try:
                    req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0','Referer':watch})
                    with urllib.request.urlopen(req,timeout=15) as resp:
                        data=resp.read(262144)
                    out[field+'_probe']={'status':getattr(resp,'status',None),'bytes':len(data),'content_type':resp.headers.get('Content-Type'),'prefix':data[:300].decode('utf-8','replace')}
                except Exception as exc:
                    out[field+'_probe']={'error':f'{type(exc).__name__}: {exc}'}
        print(json.dumps(out,ensure_ascii=False))
    finally:
        try:
            if ws: ws.close()
        except Exception: pass
        try: chrome.terminate(); chrome.wait(timeout=5)
        except Exception:
            try: chrome.kill()
            except Exception: pass

if __name__=='__main__': main()
