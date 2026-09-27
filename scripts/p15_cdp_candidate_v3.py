from __future__ import annotations

import html
import json
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

import websocket


def norm(text: str | None) -> str:
    text = text or ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower()
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def contest_re(contest_id: int) -> re.Pattern[str]:
    return re.compile(rf"\bconcurso(?:\s+(?:n|numero))?\s*{contest_id}\b")


def force_fmt(base_url: str, fmt: str | None) -> str:
    parts = urllib.parse.urlsplit(base_url)
    pairs = [(k, v) for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=True) if k != "fmt"]
    if fmt:
        pairs.append(("fmt", fmt))
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, urllib.parse.urlencode(pairs), parts.fragment))


def parse_json3(text: str) -> list[dict]:
    obj = json.loads(text)
    out = []
    for ev in obj.get("events", []):
        msg = "".join((seg.get("utf8") or "") for seg in (ev.get("segs") or [])).strip()
        if msg:
            out.append({"ms": int(ev.get("tStartMs") or 0), "text": msg, "norm": norm(msg)})
    return out


def parse_vtt(text: str) -> list[dict]:
    out: list[dict] = []
    current_ms: int | None = None
    for raw in text.splitlines():
        line = raw.strip()
        cue = re.match(r"(?:(\d+):)?(\d{2}):(\d{2})[\.,](\d{3})\s+-->", line)
        if cue:
            h = int(cue.group(1) or 0)
            m = int(cue.group(2))
            s = int(cue.group(3))
            ms = int(cue.group(4))
            current_ms = ((h * 60 + m) * 60 + s) * 1000 + ms
            continue
        if current_ms is None or not line or line.startswith(("WEBVTT", "Kind:", "Language:")):
            continue
        clean = re.sub(r"<[^>]+>", "", line).strip()
        if clean and "-->" not in clean:
            out.append({"ms": current_ms, "text": clean, "norm": norm(clean)})
    return out


def parse_xml_transcript(text: str) -> list[dict]:
    root = ET.fromstring(text)
    out = []
    for el in root.iter():
        if el.tag.rsplit("}", 1)[-1] != "text":
            continue
        msg = html.unescape("".join(el.itertext())).strip()
        if not msg:
            continue
        start = float(el.attrib.get("start", "0") or 0)
        out.append({"ms": int(start * 1000), "text": msg, "norm": norm(msg)})
    return out


def decode_caption(text: str) -> tuple[list[dict], str]:
    stripped = text.lstrip("\ufeff \t\r\n")
    if not stripped:
        return [], "empty"
    if stripped.startswith("{"):
        return parse_json3(stripped), "json3"
    if stripped.startswith("WEBVTT") or "-->" in stripped[:5000]:
        return parse_vtt(stripped), "vtt"
    if stripped.startswith("<"):
        try:
            return parse_xml_transcript(stripped), "xml"
        except Exception:
            pass
    return [], "other"


def fetch_caption(base_url: str, watch_url: str) -> tuple[list[dict], str, int]:
    headers = {"User-Agent": "Mozilla/5.0", "Referer": watch_url}
    last_fmt = "none"
    for fmt in ("json3", "vtt", None):
        url = force_fmt(base_url, fmt)
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                raw = resp.read(5_000_000)
        except Exception:
            continue
        text = raw.decode("utf-8", errors="replace")
        events, detected = decode_caption(text)
        last_fmt = detected if fmt is None else f"{fmt}->{detected}"
        if events:
            return events, last_fmt, len(raw)
    return [], last_fmt, 0


def marker_hits(events: list[dict], anchor_ms: int | None, radius_ms: int = 12 * 60 * 1000) -> dict[str, int]:
    pats = {
        "maleta": re.compile(r"\bmaleta\b"),
        "lacre": re.compile(r"\blacre\b"),
        "globo": re.compile(r"\bglobo\b"),
        "auditor": re.compile(r"\bauditor"),
        "balls_25": re.compile(r"(?:\b25\s+bolas\b|\bbolas\b.{0,100}\b0?1\b.{0,100}\b25\b)"),
        "loading": re.compile(r"\b(?:carreg|abastec|colocacao|colocar|suporte)\w*\b"),
        "empty_globe": re.compile(r"\bglobo\b.{0,120}\bvazio\b"),
        "procedure": re.compile(r"\bprocedimento\w*\b|\bpreparativo\w*\b"),
    }
    selected = events if anchor_ms is None else [e for e in events if abs(e["ms"] - anchor_ms) <= radius_ms]
    hits: dict[str, int] = {}
    for name, pat in pats.items():
        for i in range(len(selected)):
            window = " ".join(e["norm"] for e in selected[max(0, i - 1): min(len(selected), i + 2)])
            if pat.search(window):
                hits[name] = selected[i]["ms"]
                break
    return hits


def main() -> int:
    port = int(sys.argv[1])
    contest_id = int(sys.argv[2])
    draw_date = sys.argv[3] or None
    video_id = sys.argv[4]
    watch_url = f"https://www.youtube.com/watch?v={video_id}"
    out = {"contest_id": contest_id, "draw_date": draw_date, "video_id": video_id, "url": watch_url, "status": "ERROR"}
    ws = None
    target = None
    try:
        endpoint = f"http://127.0.0.1:{port}/json/new?" + urllib.parse.quote(watch_url, safe=":/?=&")
        req = urllib.request.Request(endpoint, method="PUT")
        with urllib.request.urlopen(req, timeout=8) as resp:
            target = json.loads(resp.read().decode("utf-8"))
        ws = websocket.create_connection(target["webSocketDebuggerUrl"], timeout=12, origin=f"http://127.0.0.1:{port}")
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
        player = None
        deadline = time.time() + 14
        while time.time() < deadline:
            raw = ev("JSON.stringify(window.ytInitialPlayerResponse||null)")
            if raw and raw != "null":
                player = json.loads(raw)
                break
            time.sleep(1)
        if not player:
            out["error"] = "PLAYER_RESPONSE_UNAVAILABLE"
            print(json.dumps(out, ensure_ascii=False), flush=True)
            return 0

        details = player.get("videoDetails") or {}
        playability = player.get("playabilityStatus") or {}
        tracks = (((player.get("captions") or {}).get("playerCaptionsTracklistRenderer") or {}).get("captionTracks") or [])
        track = None
        for code in ("pt-orig", "pt-BR", "pt"):
            track = next((t for t in tracks if t.get("languageCode") == code), None)
            if track:
                break
        events: list[dict] = []
        caption_format = None
        caption_bytes = 0
        if track and track.get("baseUrl"):
            events, caption_format, caption_bytes = fetch_caption(track["baseUrl"], watch_url)

        title = details.get("title") or ""
        desc = details.get("shortDescription") or ""
        title_n, desc_n = norm(title), norm(desc)
        joined = " ".join(e["norm"] for e in events)
        cre = contest_re(contest_id)
        title_contest = bool(cre.search(title_n))
        desc_contest = bool(cre.search(desc_n))
        caption_contest = bool(cre.search(joined))
        title_modality = "lotofacil" in title_n
        desc_modality = "lotofacil" in desc_n
        caption_modality = "lotofacil" in joined
        anchor_ms = None
        for e in events:
            if cre.search(e["norm"]):
                anchor_ms = e["ms"]
                break
        if anchor_ms is None:
            for e in events:
                if "lotofacil" in e["norm"]:
                    anchor_ms = e["ms"]
                    break
        markers = marker_hits(events, anchor_ms) if events else {}
        essential = {"maleta", "globo", "balls_25"}
        complete = caption_contest and caption_modality and essential.issubset(markers) and len(markers) >= 4
        identity_score = sum([
            6 if title_contest else 0,
            3 if title_modality else 0,
            4 if desc_contest else 0,
            2 if desc_modality else 0,
            10 if caption_contest else 0,
            5 if caption_modality else 0,
        ])
        score = identity_score + len(markers) * 3 + (100 if complete else 0)
        out.update({
            "status": "OK",
            "title": title,
            "description": desc,
            "duration_seconds": int(details.get("lengthSeconds") or 0),
            "playability_status": playability.get("status"),
            "caption_language": track.get("languageCode") if track else None,
            "caption_format": caption_format,
            "caption_bytes": caption_bytes,
            "timed_text_events": len(events),
            "title_contest": title_contest,
            "title_modality": title_modality,
            "description_contest": desc_contest,
            "description_modality": desc_modality,
            "caption_contest": caption_contest,
            "caption_modality": caption_modality,
            "contest_anchor_ms": anchor_ms,
            "procedure_markers_ms": markers,
            "complete_procedure": complete,
            "identity_score": identity_score,
            "score": score,
        })
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"[:1200]
    finally:
        try:
            if ws:
                ws.close()
        except Exception:
            pass
        if target:
            try:
                req = urllib.request.Request(f"http://127.0.0.1:{port}/json/close/{target['id']}", method="PUT")
                urllib.request.urlopen(req, timeout=3).read()
            except Exception:
                pass
    print(json.dumps(out, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
