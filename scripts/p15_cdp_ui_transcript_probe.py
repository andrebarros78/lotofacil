from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.parse
import urllib.request

import websocket

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9226
PROFILE = r"C:\Users\andre\P15Tools\ChromeP15TranscriptUI"


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
        CHROME,
        "--headless=new",
        "--disable-gpu",
        "--no-first-run",
        "--no-default-browser-check",
        "--remote-debugging-address=127.0.0.1",
        f"--remote-debugging-port={PORT}",
        "--remote-allow-origins=*",
        f"--user-data-dir={PROFILE}",
        "about:blank",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ws = None
    target = None
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
                if msg.get("id") == myid:
                    return msg

        def ev(expr: str, await_promise: bool = False):
            res = cmd("Runtime.evaluate", {
                "expression": expr,
                "returnByValue": True,
                "awaitPromise": await_promise,
                "userGesture": True,
            })
            inner = ((res.get("result") or {}).get("result") or {})
            return inner.get("value")

        cmd("Runtime.enable")
        cmd("Page.enable")
        time.sleep(7)
        title = ev("document.title")
        body = ev("(document.body && document.body.innerText || '').slice(0,60000)") or ""
        # Expand the description if present.
        ev("""
(() => {
  const sels = ['#expand', 'tp-yt-paper-button#expand', 'ytd-text-inline-expander #expand'];
  for (const s of sels) {
    const el = document.querySelector(s);
    if (el) { try { el.click(); return true; } catch(e) {} }
  }
  return false;
})()
""")
        time.sleep(2)
        candidates_raw = ev("""
JSON.stringify([...document.querySelectorAll('button, yt-button-shape button, tp-yt-paper-button, ytd-button-renderer, a')]
  .map((el, i) => ({i, text:(el.innerText||el.textContent||'').trim().replace(/\s+/g,' '), tag:el.tagName, id:el.id||''}))
  .filter(x => /transcri|transcript/i.test(x.text))
  .slice(0,30))
""")
        candidates = json.loads(candidates_raw or "[]")
        click_result = ev("""
(() => {
  const els=[...document.querySelectorAll('button, yt-button-shape button, tp-yt-paper-button, ytd-button-renderer, a')];
  const el=els.find(e => /transcri|transcript/i.test((e.innerText||e.textContent||'').trim()));
  if(!el) return JSON.stringify({clicked:false});
  const text=(el.innerText||el.textContent||'').trim().replace(/\s+/g,' ');
  try { el.click(); return JSON.stringify({clicked:true,text}); }
  catch(e) { return JSON.stringify({clicked:false,text,error:String(e)}); }
})()
""")
        click_info = json.loads(click_result or "{}")
        time.sleep(6)
        segments_raw = ev("""
JSON.stringify([
  ...document.querySelectorAll('ytd-transcript-segment-renderer, yt-formatted-string.segment-text, .segment-text, ytd-transcript-segment-list-renderer [class*="segment"]')
].map(el => (el.innerText||el.textContent||'').trim()).filter(Boolean).slice(0,2000))
""")
        segments = json.loads(segments_raw or "[]")
        body_after = ev("(document.body && document.body.innerText || '').slice(0,120000)") or ""
        transcript_word_present = bool(__import__('re').search(r"transcri|transcript", body_after, __import__('re').I))
        result = {
            "video_id": video_id,
            "title": title,
            "body_has_transcript_word_before": bool(__import__('re').search(r"transcri|transcript", body, __import__('re').I)),
            "candidate_controls": candidates,
            "click": click_info,
            "segment_count": len(segments),
            "segment_sample": segments[:30],
            "body_has_transcript_word_after": transcript_word_present,
        }
        print(json.dumps(result, ensure_ascii=False))
        return 0
    finally:
        try:
            if ws:
                ws.close()
        except Exception:
            pass
        try:
            chrome.terminate()
            chrome.wait(timeout=5)
        except Exception:
            try:
                chrome.kill()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
