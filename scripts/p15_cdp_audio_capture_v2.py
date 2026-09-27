from __future__ import annotations

import base64
import json
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import websocket

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9231
PROFILE = r"C:\Users\andre\P15Tools\ChromeP15AudioCaptureV2"


def wait_port(seconds=20):
    end=time.time()+seconds
    while time.time()<end:
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{PORT}/json/version',timeout=2): return
        except Exception: time.sleep(.5)
    raise RuntimeError('CDP did not start')


def main():
    video_id=sys.argv[1]; start_sec=float(sys.argv[2]); duration_sec=float(sys.argv[3]); out_path=Path(sys.argv[4])
    watch=f'https://www.youtube.com/watch?v={video_id}'
    chrome=subprocess.Popen([
        CHROME,'--headless=new','--disable-gpu','--no-first-run','--no-default-browser-check','--autoplay-policy=no-user-gesture-required',
        '--remote-debugging-address=127.0.0.1',f'--remote-debugging-port={PORT}','--remote-allow-origins=*',
        f'--user-data-dir={PROFILE}','about:blank'
    ],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    ws=None
    try:
        wait_port()
        req=urllib.request.Request(f'http://127.0.0.1:{PORT}/json/new?'+urllib.parse.quote(watch,safe=':/?=&'),method='PUT')
        with urllib.request.urlopen(req,timeout=8) as r: target=json.loads(r.read().decode())
        ws=websocket.create_connection(target['webSocketDebuggerUrl'],timeout=max(45,int(duration_sec)+40),origin=f'http://127.0.0.1:{PORT}')
        seq=0
        def cmd(method,params=None):
            nonlocal seq
            seq+=1; mid=seq
            ws.send(json.dumps({'id':mid,'method':method,'params':params or {}}))
            while True:
                m=json.loads(ws.recv())
                if m.get('id')==mid:return m
        def ev(expr,await_promise=False):
            r=cmd('Runtime.evaluate',{'expression':expr,'returnByValue':True,'awaitPromise':await_promise,'userGesture':True})
            inner=((r.get('result') or {}).get('result') or {})
            if inner.get('subtype')=='error': raise RuntimeError(inner.get('description') or 'Runtime error')
            return inner.get('value')
        cmd('Runtime.enable'); cmd('Page.enable')
        deadline=time.time()+20; info=None
        while time.time()<deadline:
            raw=ev("""
(() => { const v=document.querySelector('video'); const p=document.getElementById('movie_player');
 if(!v) return null;
 return JSON.stringify({readyState:v.readyState,duration:v.duration,currentTime:v.currentTime,paused:v.paused,seeking:v.seeking,hasCapture:!!(v.captureStream||v.mozCaptureStream),hasPlayer:!!p}); })()
""")
            if raw:
                info=json.loads(raw)
                if info.get('readyState',0)>=1 and info.get('duration') and info.get('hasCapture'): break
            time.sleep(1)
        if not info: raise RuntimeError('video unavailable')

        js=f"""
(async () => {{
 const v=document.querySelector('video');
 const p=document.getElementById('movie_player');
 const start={start_sec}; const seconds={duration_sec};
 const sleep=ms=>new Promise(r=>setTimeout(r,ms));
 try {{
   if(p&&p.pauseVideo) p.pauseVideo(); else v.pause();
   v.muted=false; v.volume=1.0; v.playbackRate=1.0;
   if(p&&p.seekTo) p.seekTo(start,true); else v.currentTime=start;
   const deadline=Date.now()+18000;
   while(Date.now()<deadline) {{
      if(Math.abs(v.currentTime-start)<4 && !v.seeking && v.readyState>=2) break;
      await sleep(250);
   }}
   await sleep(1200);
   const settled={{currentTime:v.currentTime,readyState:v.readyState,seeking:v.seeking,paused:v.paused}};
   if(Math.abs(v.currentTime-start)>=8) return JSON.stringify({{ok:false,error:'SEEK_NOT_SETTLED',settled}});
   const cap=(v.captureStream||v.mozCaptureStream).call(v);
   const aud=cap.getAudioTracks();
   if(!aud.length) return JSON.stringify({{ok:false,error:'NO_AUDIO_TRACK',settled,streamTracks:cap.getTracks().map(t=>t.kind)}});
   const stream=new MediaStream(aud);
   let mime='audio/webm;codecs=opus';
   if(!MediaRecorder.isTypeSupported(mime)) mime='audio/webm';
   if(!MediaRecorder.isTypeSupported(mime)) mime='video/webm';
   const chunks=[];
   const rec=new MediaRecorder(stream,{{mimeType:mime,audioBitsPerSecond:64000}});
   rec.ondataavailable=e=>{{if(e.data&&e.data.size) chunks.push(e.data);}};
   const stopped=new Promise(resolve=>rec.onstop=resolve);
   rec.start(1000);
   let played=false;
   for(let i=0;i<4&&!played;i++) {{
      try {{
        if(p&&p.playVideo) {{ p.playVideo(); await sleep(800); played=!v.paused; }}
        else {{ await v.play(); played=true; }}
      }} catch(e) {{ await sleep(1000); }}
   }}
   if(!played && v.paused) {{ rec.stop(); await stopped; return JSON.stringify({{ok:false,error:'PLAY_FAILED',settled,now:{{currentTime:v.currentTime,readyState:v.readyState,paused:v.paused}}}}); }}
   const actualStart=v.currentTime;
   await sleep(seconds*1000);
   if(p&&p.pauseVideo) p.pauseVideo(); else v.pause();
   rec.stop(); await stopped;
   const actualEnd=v.currentTime;
   const blob=new Blob(chunks,{{type:mime}});
   const b64=await new Promise((resolve,reject)=>{{const fr=new FileReader();fr.onload=()=>resolve(String(fr.result).split(',')[1]||'');fr.onerror=()=>reject(fr.error);fr.readAsDataURL(blob);}});
   return JSON.stringify({{ok:true,mime,bytes:blob.size,settled,actualStart,actualEnd,base64:b64}});
 }} catch(e) {{ return JSON.stringify({{ok:false,error:String(e),name:e&&e.name,currentTime:v&&v.currentTime,readyState:v&&v.readyState,seeking:v&&v.seeking}}); }}
}})()
"""
        raw=ev(js,await_promise=True); result=json.loads(raw or '{}')
        if result.get('ok') and result.get('base64'):
            data=base64.b64decode(result.pop('base64')); out_path.parent.mkdir(parents=True,exist_ok=True); out_path.write_bytes(data)
            result['written_bytes']=len(data); result['out_path']=str(out_path)
        print(json.dumps({'video_id':video_id,'requested_start':start_sec,'requested_duration':duration_sec,'video_info':info,'result':result},ensure_ascii=False))
    finally:
        try:
            if ws: ws.close()
        except Exception: pass
        try: chrome.terminate(); chrome.wait(timeout=5)
        except Exception:
            try: chrome.kill()
            except Exception: pass

if __name__=='__main__': main()
