from __future__ import annotations
import json, subprocess, sys, time, urllib.parse, urllib.request
import websocket

CHROME=r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT=9228
PROFILE=r"C:\Users\andre\P15Tools\ChromeP15MediaProbe"

def wait_port():
    end=time.time()+20
    while time.time()<end:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version",timeout=2): return
        except Exception: time.sleep(.5)
    raise RuntimeError("CDP_START_TIMEOUT")

def main():
    vid=sys.argv[1]
    chrome=subprocess.Popen([CHROME,"--headless=new","--disable-gpu","--autoplay-policy=no-user-gesture-required","--no-first-run","--no-default-browser-check",f"--remote-debugging-port={PORT}","--remote-debugging-address=127.0.0.1","--remote-allow-origins=*",f"--user-data-dir={PROFILE}","about:blank"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    ws=None
    try:
        wait_port()
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json") as r:
            target=json.loads(r.read().decode())[0]
        ws=websocket.create_connection(target['webSocketDebuggerUrl'],timeout=3,origin=f"http://127.0.0.1:{PORT}")
        seq=0
        media={}
        def send(method,params=None):
            nonlocal seq
            seq+=1
            ws.send(json.dumps({"id":seq,"method":method,"params":params or {}})); return seq
        send("Network.enable")
        send("Page.enable")
        send("Runtime.enable")
        send("Page.navigate",{"url":f"https://www.youtube.com/watch?v={vid}"})
        deadline=time.time()+25
        played=False
        while time.time()<deadline:
            try:
                msg=json.loads(ws.recv())
            except Exception:
                if not played and time.time()+18>deadline:
                    send("Runtime.evaluate",{"expression":"(()=>{const v=document.querySelector('video');if(v){v.muted=true;v.play().catch(()=>{});return {src:v.currentSrc,ready:v.readyState};}return null})()","returnByValue":True,"userGesture":True})
                    played=True
                continue
            m=msg.get("method")
            p=msg.get("params") or {}
            if m=="Network.responseReceived":
                r=p.get("response") or {}; u=r.get("url") or ""
                if "googlevideo.com/videoplayback" in u:
                    media[p.get("requestId") or u]={"url":u,"status":r.get("status"),"mimeType":r.get("mimeType"),"protocol":r.get("protocol"),"encodedDataLength":r.get("encodedDataLength")}
            if not played and time.time()>deadline-17:
                send("Runtime.evaluate",{"expression":"(()=>{const v=document.querySelector('video');if(v){v.muted=true;v.play().catch(()=>{});return {src:v.currentSrc,ready:v.readyState};}return null})()","returnByValue":True,"userGesture":True})
                played=True
            if len(media)>=4 and played:
                break
        vals=list(media.values())
        print(json.dumps({"video_id":vid,"media_count":len(vals),"media":vals[:8]},ensure_ascii=False))
    finally:
        try:
            if ws: ws.close()
        except Exception: pass
        try:
            chrome.terminate(); chrome.wait(timeout=5)
        except Exception:
            try: chrome.kill()
            except Exception: pass
if __name__=='__main__': main()
