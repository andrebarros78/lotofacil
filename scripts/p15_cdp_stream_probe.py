from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.parse
import urllib.request

import websocket

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9228
PROFILE = r"C:\Users\andre\P15Tools\ChromeP15StreamProbe"


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

        def ev(expr: str):
            res = cmd("Runtime.evaluate", {"expression": expr, "returnByValue": True})
            inner = ((res.get("result") or {}).get("result") or {})
            return inner.get("value")

        cmd("Runtime.enable")
        cmd("Page.enable")
        deadline = time.time() + 15
        player = None
        while time.time() < deadline:
            raw = ev("JSON.stringify(window.ytInitialPlayerResponse||null)")
            if raw and raw != "null":
                player = json.loads(raw)
                break
            time.sleep(1)
        if not player:
            raise RuntimeError("PLAYER_RESPONSE_UNAVAILABLE")

        details = player.get("videoDetails") or {}
        streaming = player.get("streamingData") or {}
        all_formats = (streaming.get("adaptiveFormats") or []) + (streaming.get("formats") or [])
        audio = []
        for f in all_formats:
            mime = f.get("mimeType") or ""
            if not mime.startswith("audio/"):
                continue
            audio.append({
                "itag": f.get("itag"),
                "mimeType": mime,
                "bitrate": f.get("bitrate"),
                "averageBitrate": f.get("averageBitrate"),
                "contentLength": f.get("contentLength"),
                "approxDurationMs": f.get("approxDurationMs"),
                "audioQuality": f.get("audioQuality"),
                "audioSampleRate": f.get("audioSampleRate"),
                "audioChannels": f.get("audioChannels"),
                "has_url": bool(f.get("url")),
                "has_signature_cipher": bool(f.get("signatureCipher") or f.get("cipher")),
                "url": f.get("url"),
            })
        audio.sort(key=lambda x: (x.get("bitrate") or 10**12, x.get("itag") or 0))

        probe = None
        direct = next((x for x in audio if x.get("url")), None)
        if direct:
            req = urllib.request.Request(direct["url"], headers={"Range": "bytes=0-262143", "User-Agent": "Mozilla/5.0", "Referer": watch_url})
            try:
                with urllib.request.urlopen(req, timeout=15) as resp:
                    chunk = resp.read(262144)
                    probe = {
                        "status": getattr(resp, "status", None),
                        "content_type": resp.headers.get("Content-Type"),
                        "content_range": resp.headers.get("Content-Range"),
                        "bytes_read": len(chunk),
                    }
            except Exception as exc:
                probe = {"error": f"{type(exc).__name__}: {exc}"}

        print(json.dumps({
            "video_id": video_id,
            "title": details.get("title"),
            "lengthSeconds": details.get("lengthSeconds"),
            "audio_formats": audio,
            "first_direct_probe": probe,
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
