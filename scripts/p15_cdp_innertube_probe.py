from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.parse
import urllib.request

import websocket

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PROFILE = r"C:\Users\andre\P15Tools\ChromeP15Innertube"
PORT = 9225


def wait_port(seconds: int = 20) -> None:
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{PORT}/json/version', timeout=2):
                return
        except Exception:
            time.sleep(0.5)
    raise RuntimeError('CDP did not start')


def new_target(url: str) -> dict:
    endpoint = f'http://127.0.0.1:{PORT}/json/new?' + urllib.parse.quote(url, safe=':/?=&')
    req = urllib.request.Request(endpoint, method='PUT')
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode('utf-8'))


def main() -> int:
    video_id = sys.argv[1]
    chrome = subprocess.Popen([
        CHROME, '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
        '--remote-debugging-address=127.0.0.1', f'--remote-debugging-port={PORT}', '--remote-allow-origins=*',
        f'--user-data-dir={PROFILE}', 'about:blank'
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    target = None
    ws = None
    try:
        wait_port()
        target = new_target(f'https://www.youtube.com/watch?v={video_id}')
        ws = websocket.create_connection(target['webSocketDebuggerUrl'], timeout=30, origin=f'http://127.0.0.1:{PORT}')
        seq = 0
        def cmd(method: str, params=None):
            nonlocal seq
            seq += 1
            myid = seq
            ws.send(json.dumps({'id': myid, 'method': method, 'params': params or {}}))
            while True:
                msg = json.loads(ws.recv())
                if msg.get('id') == myid:
                    return msg
        def ev(expr: str, await_promise: bool = False):
            res = cmd('Runtime.evaluate', {
                'expression': expr,
                'returnByValue': True,
                'awaitPromise': await_promise,
                'userGesture': True,
            })
            inner = (res.get('result') or {}).get('result') or {}
            if inner.get('subtype') == 'error':
                raise RuntimeError(inner.get('description') or 'Runtime.evaluate error')
            return inner.get('value')
        cmd('Runtime.enable')
        cmd('Page.enable')
        deadline = time.time() + 20
        while time.time() < deadline:
            ready = ev("document.readyState + '|' + (!!window.ytInitialData) + '|' + (!!window.ytcfg)")
            if ready and '|true|true' in ready:
                break
            time.sleep(1)
        locator_js = r'''(() => {
          const seen = new Set();
          function walk(o) {
            if (!o || typeof o !== 'object' || seen.has(o)) return null;
            seen.add(o);
            if (o.getTranscriptEndpoint && o.getTranscriptEndpoint.params) return o.getTranscriptEndpoint.params;
            for (const k of Object.keys(o)) {
              const r = walk(o[k]);
              if (r) return r;
            }
            return null;
          }
          return JSON.stringify({
            params: walk(window.ytInitialData),
            apiKey: window.ytcfg && ytcfg.get('INNERTUBE_API_KEY'),
            context: window.ytcfg && ytcfg.get('INNERTUBE_CONTEXT'),
            title: document.title,
            botGate: /sign in to confirm/i.test(document.body?.innerText||'') && /bot/i.test(document.body?.innerText||'')
          });
        })()'''
        located = json.loads(ev(locator_js) or '{}')
        if not located.get('params'):
            print(json.dumps({'video_id': video_id, 'status': 'NO_TRANSCRIPT_ENDPOINT', **located}, ensure_ascii=False))
            return 2
        req_js = r'''(async () => {
          const seen = new Set();
          function walk(o) {
            if (!o || typeof o !== 'object' || seen.has(o)) return null;
            seen.add(o);
            if (o.getTranscriptEndpoint && o.getTranscriptEndpoint.params) return o.getTranscriptEndpoint.params;
            for (const k of Object.keys(o)) {
              const r = walk(o[k]);
              if (r) return r;
            }
            return null;
          }
          const params = walk(window.ytInitialData);
          const key = ytcfg.get('INNERTUBE_API_KEY');
          const context = ytcfg.get('INNERTUBE_CONTEXT');
          const r = await fetch('/youtubei/v1/get_transcript?key=' + encodeURIComponent(key), {
            method: 'POST',
            credentials: 'include',
            headers: {'content-type':'application/json'},
            body: JSON.stringify({context, params})
          });
          const text = await r.text();
          let obj = null;
          try { obj = JSON.parse(text); } catch(e) {}
          const segs = [];
          const seen2 = new Set();
          function collect(o) {
            if (!o || typeof o !== 'object' || seen2.has(o)) return;
            seen2.add(o);
            const s = o.transcriptSegmentRenderer;
            if (s) {
              const runs = ((s.snippet||{}).runs||[]).map(x => x.text||'').join('');
              segs.push({startMs:s.startMs||null, endMs:s.endMs||null, text:runs});
            }
            for (const k of Object.keys(o)) collect(o[k]);
          }
          if (obj) collect(obj);
          return JSON.stringify({httpStatus:r.status, bodyLength:text.length, segmentCount:segs.length, first:segs.slice(0,3), last:segs.slice(-3)});
        })()'''
        transcript = json.loads(ev(req_js, await_promise=True) or '{}')
        print(json.dumps({'video_id': video_id, 'status': 'OK', 'locator': located, 'transcript': transcript}, ensure_ascii=False))
        return 0
    finally:
        try:
            if ws:
                ws.close()
        except Exception:
            pass
        try:
            if target:
                req = urllib.request.Request(f"http://127.0.0.1:{PORT}/json/close/{target['id']}", method='PUT')
                urllib.request.urlopen(req, timeout=5).read()
        except Exception:
            pass
        chrome.terminate()
        try:
            chrome.wait(timeout=10)
        except Exception:
            chrome.kill()


if __name__ == '__main__':
    raise SystemExit(main())
