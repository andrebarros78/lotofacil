from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import websocket

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9233
PROFILE = r"C:\Users\andre\P15Tools\ChromeP15StoryboardVisible"
OUT_ROOT = Path(r"C:\Users\andre\P15Tools\P15Acquire\storyboard_probe")


def wait_cdp(seconds: int = 25) -> None:
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version", timeout=2):
                return
        except Exception:
            time.sleep(0.5)
    raise RuntimeError("CDP_START_TIMEOUT")


def main() -> int:
    video_id = sys.argv[1]
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    out_file = OUT_ROOT / f"{video_id}.json"

    # IMPORTANT: intentionally NOT headless. Separate technical profile only.
    chrome = subprocess.Popen(
        [
            CHROME,
            "--disable-gpu",
            "--no-first-run",
            "--no-default-browser-check",
            "--autoplay-policy=no-user-gesture-required",
            f"--remote-debugging-port={PORT}",
            "--remote-debugging-address=127.0.0.1",
            "--remote-allow-origins=*",
            f"--user-data-dir={PROFILE}",
            f"https://www.youtube.com/watch?v={video_id}",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    ws = None
    result = {
        "schema_version": 1,
        "program_id": "P15_STORYBOARD_VISIBLE_PROBE_V1",
        "video_id": video_id,
        "status": "ERROR",
        "predictive_evidence": "NOT_ESTABLISHED",
        "purchase_executed": False,
    }
    try:
        wait_cdp()
        targets = []
        deadline = time.time() + 20
        while time.time() < deadline:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json", timeout=5) as r:
                targets = json.loads(r.read().decode("utf-8"))
            yt = [t for t in targets if video_id in (t.get("url") or "") and t.get("type") == "page"]
            if yt:
                target = yt[0]
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("YOUTUBE_TARGET_NOT_FOUND")

        ws = websocket.create_connection(
            target["webSocketDebuggerUrl"], timeout=12, origin=f"http://127.0.0.1:{PORT}"
        )
        seq = 0

        def cmd(method: str, params=None):
            nonlocal seq
            seq += 1
            my_id = seq
            ws.send(json.dumps({"id": my_id, "method": method, "params": params or {}}))
            while True:
                msg = json.loads(ws.recv())
                if msg.get("id") == my_id:
                    return msg

        def ev(expr: str):
            raw = cmd(
                "Runtime.evaluate",
                {"expression": expr, "returnByValue": True, "userGesture": True},
            )
            return (((raw.get("result") or {}).get("result") or {}).get("value"))

        cmd("Runtime.enable")
        cmd("Page.enable")
        player = None
        deadline = time.time() + 25
        while time.time() < deadline:
            raw = ev("JSON.stringify(window.ytInitialPlayerResponse||null)")
            if raw and raw != "null":
                player = json.loads(raw)
                break
            time.sleep(1)

        if not player:
            body = ev("(document.body && document.body.innerText || '').slice(0,12000)") or ""
            result.update(
                {
                    "status": "NO_PLAYER_RESPONSE",
                    "title": ev("document.title"),
                    "body_bot_gate": "sign in to confirm" in body.lower() and "bot" in body.lower(),
                }
            )
        else:
            details = player.get("videoDetails") or {}
            playability = player.get("playabilityStatus") or {}
            storyboards = player.get("storyboards") or {}
            result.update(
                {
                    "status": "OK",
                    "title": details.get("title"),
                    "length_seconds": int(details.get("lengthSeconds") or 0),
                    "author": details.get("author"),
                    "playability_status": playability.get("status"),
                    "storyboards_present": bool(storyboards),
                    "storyboards": storyboards,
                }
            )

        out_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({
            "video_id": video_id,
            "status": result.get("status"),
            "title": result.get("title"),
            "storyboards_present": result.get("storyboards_present"),
            "length_seconds": result.get("length_seconds"),
            "out_file": str(out_file),
        }, ensure_ascii=False), flush=True)
        return 0
    finally:
        try:
            if ws:
                ws.close()
        except Exception:
            pass
        # Terminate only this technical browser process tree.
        try:
            subprocess.run(
                ["taskkill", "/PID", str(chrome.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
            )
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
