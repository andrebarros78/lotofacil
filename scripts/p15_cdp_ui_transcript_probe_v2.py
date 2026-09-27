from __future__ import annotations

import json
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request

import websocket

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9227
PROFILE = r"C:\Users\andre\P15Tools\ChromeP15TranscriptUIV2"


def wait_port(seconds: int = 20) -> None:
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version", timeout=2):
                return
        except Exception:
            time.sleep(0.5)
    raise RuntimeError("CDP did not start")


def main() -> int:
    video_id = sys.argv[1]
    watch_url = f"https://www.youtube.com/watch?v={video_id}"
    chrome = subprocess.Popen([
        CHROME, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
        "--remote-debugging-address=127.0.0.1", f"--remote-debugging-port={PORT}", "--remote-allow-origins=*",
        f"--user-data-dir={PROFILE}", "about:blank",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ws = None
    target = None
    network_events: list[dict] = []
    try:
        wait_port()
        endpoint = f"http://127.0.0.1:{PORT}/json/new?" + urllib.parse.quote(watch_url, safe=":/?=&")
        req = urllib.request.Request(endpoint, method="PUT")
        with urllib.request.urlopen(req, timeout=8) as resp:
            target = json.loads(resp.read().decode("utf-8"))
        ws = websocket.create_connection(target["webSocketDebuggerUrl"], timeout=15, origin=f"http://127.0.0.1:{PORT}")
        seq = 0

        def cmd(method: str, params=None):
            nonlocal seq
            seq += 1
            myid = seq
            ws.send(json.dumps({"id": myid, "method": method, "params": params or {}}))
            while True:
                msg = json.loads(ws.recv())
                if msg.get("method") == "Network.responseReceived":
                    network_events.append(msg)
                if msg.get("id") == myid:
                    return msg

        def ev(expr: str):
            res = cmd("Runtime.evaluate", {"expression": expr, "returnByValue": True, "userGesture": True})
            inner = ((res.get("result") or {}).get("result") or {})
            return inner.get("value")

        cmd("Network.enable")
        cmd("Runtime.enable")
        cmd("Page.enable")
        time.sleep(7)
        # Pump queued network events.
        ev("document.title")

        ev("""
(() => {
  for (const s of ['#expand','tp-yt-paper-button#expand','ytd-text-inline-expander #expand']) {
    const el=document.querySelector(s); if(el){ try{el.click(); return true;}catch(e){} }
  }
  return false;
})()
""")
        time.sleep(2)
        ev("document.title")

        controls_raw = ev("""
JSON.stringify([...document.querySelectorAll('button, yt-button-shape button, tp-yt-paper-button, ytd-button-renderer, a')]
 .map((el,i)=>({i,text:(el.innerText||el.textContent||'').trim().replace(/\s+/g,' '),tag:el.tagName,id:el.id||''}))
 .filter(x=>/transcri|transcript/i.test(x.text)).slice(0,50))
""")
        controls = json.loads(controls_raw or "[]")

        click_raw = ev("""
(() => {
  const els=[...document.querySelectorAll('button, yt-button-shape button, tp-yt-paper-button, ytd-button-renderer, a')];
  const score=e=>{
    const t=(e.innerText||e.textContent||'').trim();
    if(/mostrar\s+transcri|show\s+transcript/i.test(t)) return 3;
    if(/^transcri|^transcript/i.test(t)) return 1;
    return 0;
  };
  const ranked=els.map(e=>({e,s:score(e),t:(e.innerText||e.textContent||'').trim().replace(/\s+/g,' ')})).filter(x=>x.s>0).sort((a,b)=>b.s-a.s);
  if(!ranked.length) return JSON.stringify({clicked:false});
  const x=ranked[0];
  try{x.e.scrollIntoView({block:'center'});x.e.click();return JSON.stringify({clicked:true,text:x.t,score:x.s});}
  catch(e){return JSON.stringify({clicked:false,text:x.t,error:String(e)});}
})()
""")
        click_info = json.loads(click_raw or "{}")

        for _ in range(10):
            time.sleep(1)
            try:
                ev("document.title")
            except Exception:
                pass

        interesting = []
        seen = set()
        for msg in network_events:
            p = msg.get("params") or {}
            response = p.get("response") or {}
            url = response.get("url") or ""
            low = url.lower()
            if not any(token in low for token in ("transcript", "timedtext", "get_transcript")):
                continue
            req_id = p.get("requestId")
            key = (req_id, url)
            if key in seen:
                continue
            seen.add(key)
            body = ""
            body_error = None
            if req_id:
                try:
                    rb = cmd("Network.getResponseBody", {"requestId": req_id})
                    body = (((rb.get("result") or {}).get("body")) or "")
                except Exception as exc:
                    body_error = f"{type(exc).__name__}: {exc}"
            interesting.append({
                "url": url,
                "status": response.get("status"),
                "mimeType": response.get("mimeType"),
                "body_bytes": len(body.encode("utf-8", errors="ignore")),
                "body_prefix": body[:1200],
                "body_error": body_error,
            })

        dom_nodes_raw = ev("""
JSON.stringify([...document.querySelectorAll('*')]
 .filter(el=>/transcript|segment/i.test((el.tagName||'')+' '+(el.id||'')+' '+(typeof el.className==='string'?el.className:'')))
 .slice(0,300)
 .map(el=>({tag:el.tagName,id:el.id||'',className:(typeof el.className==='string'?el.className:''),text:(el.innerText||el.textContent||'').trim().replace(/\s+/g,' ').slice(0,500)})))
""")
        dom_nodes = json.loads(dom_nodes_raw or "[]")
        body_after = ev("(document.body && document.body.innerText || '').slice(0,160000)") or ""
        m = re.search(r"(.{0,3000}(?:transcri|transcript).{0,10000})", body_after, re.I | re.S)
        body_excerpt = m.group(1) if m else ""

        print(json.dumps({
            "video_id": video_id,
            "controls": controls,
            "click": click_info,
            "network_matches": interesting,
            "dom_nodes": dom_nodes[:120],
            "body_excerpt": body_excerpt[:12000],
        }, ensure_ascii=False))
        return 0
    finally:
        try:
            if ws:
                ws.close()
        except Exception:
            pass
        try:
            chrome.terminate(); chrome.wait(timeout=5)
        except Exception:
            try: chrome.kill()
            except Exception: pass


if __name__ == "__main__":
    raise SystemExit(main())
