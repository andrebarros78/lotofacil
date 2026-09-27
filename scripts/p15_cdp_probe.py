import json, sys, time, urllib.parse, urllib.request
import websocket

video_id = sys.argv[1]
url = f"https://www.youtube.com/watch?v={video_id}"
endpoint = "http://127.0.0.1:9223/json/new?" + urllib.parse.quote(url, safe=":/?=&")
req = urllib.request.Request(endpoint, method="PUT")
with urllib.request.urlopen(req, timeout=10) as r:
    target = json.loads(r.read().decode("utf-8"))

ws = websocket.create_connection(target["webSocketDebuggerUrl"], timeout=15, origin="http://127.0.0.1:9223")
seq = 0

def cmd(method, params=None):
    global seq
    seq += 1
    myid = seq
    ws.send(json.dumps({"id": myid, "method": method, "params": params or {}}))
    while True:
        msg = json.loads(ws.recv())
        if msg.get("id") == myid:
            return msg

def evaluate(expr, await_promise=False):
    res = cmd("Runtime.evaluate", {
        "expression": expr,
        "returnByValue": True,
        "awaitPromise": await_promise,
        "userGesture": True,
    })
    return (((res.get("result") or {}).get("result") or {}).get("value"))

cmd("Page.enable")
cmd("Runtime.enable")
time.sleep(8)

title = evaluate("document.title")
href = evaluate("location.href")
body = evaluate("(document.body && document.body.innerText || '').slice(0,20000)")
video_details = evaluate("JSON.stringify((window.ytInitialPlayerResponse||{}).videoDetails||null)")
tracks_json = evaluate("JSON.stringify((((window.ytInitialPlayerResponse||{}).captions||{}).playerCaptionsTracklistRenderer||{}).captionTracks||[])")
playability = evaluate("JSON.stringify((window.ytInitialPlayerResponse||{}).playabilityStatus||null)")

tracks = json.loads(tracks_json or "[]")
details = json.loads(video_details or "null")
status = json.loads(playability or "null")
print(json.dumps({
    "video_id": video_id,
    "title": title,
    "href": href,
    "body_bot_gate": "sign in to confirm" in (body or "").lower() and "bot" in (body or "").lower(),
    "details": details,
    "playability": status,
    "caption_tracks": [
        {
            "name": (((t.get("name") or {}).get("simpleText")) or ""),
            "languageCode": t.get("languageCode"),
            "kind": t.get("kind"),
            "baseUrl": t.get("baseUrl"),
        } for t in tracks
    ],
}, ensure_ascii=False))

try:
    cmd("Page.close")
except Exception:
    pass
ws.close()
