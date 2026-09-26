from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

import websocket

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PROFILE = r"C:\Users\andre\P15Tools\ChromeP15CDPBatch"
PORT = 9224


def norm(text: str | None) -> str:
    text = text or ''
    text = unicodedata.normalize('NFKD', text)
    text = ''.join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower()
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'[^a-z0-9]+', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()


def contest_re(contest_id: int) -> re.Pattern[str]:
    return re.compile(rf'\bconcurso(?:\s+(?:n|numero))?\s*{contest_id}\b')


def parse_events(obj: dict) -> list[dict]:
    out = []
    for ev in obj.get('events', []):
        text = ''.join((seg.get('utf8') or '') for seg in (ev.get('segs') or [])).strip()
        if text:
            out.append({'ms': int(ev.get('tStartMs') or 0), 'text': text, 'norm': norm(text)})
    return out


def marker_hits(events: list[dict], anchor_ms: int | None, radius_ms: int = 12 * 60 * 1000) -> dict[str, int]:
    pats = {
        'maleta': re.compile(r'\bmaleta\b'),
        'lacre': re.compile(r'\blacre\b'),
        'globo': re.compile(r'\bglobo\b'),
        'auditor': re.compile(r'\bauditor'),
        'balls_25': re.compile(r'(?:\b25\s+bolas\b|\bbolas\b.{0,80}\b0?1\b.{0,80}\b25\b)'),
        'loading': re.compile(r'\b(?:carreg|abastec|colocacao|colocar|suporte)\w*\b'),
        'empty_globe': re.compile(r'\bglobo\b.{0,100}\bvazio\b'),
        'procedure': re.compile(r'\bprocedimento\w*\b|\bpreparativo\w*\b'),
    }
    selected = events if anchor_ms is None else [e for e in events if abs(e['ms'] - anchor_ms) <= radius_ms]
    hits = {}
    for name, pat in pats.items():
        for i in range(len(selected)):
            window = ' '.join(e['norm'] for e in selected[max(0, i-1):min(len(selected), i+2)])
            if pat.search(window):
                hits[name] = selected[i]['ms']
                break
    return hits


def wait_port(port: int, seconds: int = 20) -> None:
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/json/version', timeout=2):
                return
        except Exception:
            time.sleep(0.5)
    raise RuntimeError('CDP did not start')


def new_target(url: str) -> dict:
    endpoint = f'http://127.0.0.1:{PORT}/json/new?' + urllib.parse.quote(url, safe=':/?=&')
    req = urllib.request.Request(endpoint, method='PUT')
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode('utf-8'))


def cdp_probe(contest_id: int, draw_date: str | None, video_id: str) -> dict:
    url = f'https://www.youtube.com/watch?v={video_id}'
    out = {'contest_id': contest_id, 'draw_date': draw_date, 'video_id': video_id, 'url': url, 'status': 'ERROR'}
    target = None
    ws = None
    try:
        target = new_target(url)
        ws = websocket.create_connection(target['webSocketDebuggerUrl'], timeout=20, origin=f'http://127.0.0.1:{PORT}')
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
        def ev(expr: str):
            res = cmd('Runtime.evaluate', {'expression': expr, 'returnByValue': True, 'userGesture': True})
            return (((res.get('result') or {}).get('result') or {}).get('value'))
        cmd('Runtime.enable')
        cmd('Page.enable')
        deadline = time.time() + 18
        player = None
        while time.time() < deadline:
            player_json = ev('JSON.stringify(window.ytInitialPlayerResponse||null)')
            if player_json and player_json != 'null':
                player = json.loads(player_json)
                break
            time.sleep(1)
        if not player:
            body = ev("(document.body && document.body.innerText || '').slice(0,12000)") or ''
            out['error'] = 'PLAYER_RESPONSE_UNAVAILABLE'
            out['body_bot_gate'] = 'sign in to confirm' in body.lower() and 'bot' in body.lower()
            return out
        details = player.get('videoDetails') or {}
        playability = player.get('playabilityStatus') or {}
        caption_tracks = (((player.get('captions') or {}).get('playerCaptionsTracklistRenderer') or {}).get('captionTracks') or [])
        track = None
        for code in ('pt-orig', 'pt-BR', 'pt'):
            track = next((t for t in caption_tracks if t.get('languageCode') == code), None)
            if track:
                break
        events = []
        if track and track.get('baseUrl'):
            cap_url = track['baseUrl'] + ('&' if '?' in track['baseUrl'] else '?') + 'fmt=json3'
            req = urllib.request.Request(cap_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=25) as resp:
                events = parse_events(json.loads(resp.read(5_000_000).decode('utf-8', errors='replace')))
        title = details.get('title') or ''
        desc = details.get('shortDescription') or ''
        title_n, desc_n = norm(title), norm(desc)
        joined = ' '.join(e['norm'] for e in events)
        cre = contest_re(contest_id)
        title_contest = bool(cre.search(title_n))
        desc_contest = bool(cre.search(desc_n))
        caption_contest = bool(cre.search(joined))
        title_modality = 'lotofacil' in title_n
        desc_modality = 'lotofacil' in desc_n
        caption_modality = 'lotofacil' in joined
        anchor_ms = None
        for e in events:
            if cre.search(e['norm']):
                anchor_ms = e['ms']; break
        if anchor_ms is None:
            for e in events:
                if 'lotofacil' in e['norm']:
                    anchor_ms = e['ms']; break
        markers = marker_hits(events, anchor_ms) if events else {}
        essential = {'maleta', 'globo', 'balls_25'}
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
            'status': 'OK',
            'title': title,
            'description': desc,
            'duration_seconds': int(details.get('lengthSeconds') or 0),
            'playability_status': playability.get('status'),
            'timed_text_events': len(events),
            'caption_language': track.get('languageCode') if track else None,
            'title_contest': title_contest,
            'title_modality': title_modality,
            'description_contest': desc_contest,
            'description_modality': desc_modality,
            'caption_contest': caption_contest,
            'caption_modality': caption_modality,
            'contest_anchor_ms': anchor_ms,
            'procedure_markers_ms': markers,
            'complete_procedure': complete,
            'identity_score': identity_score,
            'score': score,
        })
        return out
    except Exception as exc:
        out['error'] = f'{type(exc).__name__}: {exc}'[:1000]
        return out
    finally:
        try:
            if ws:
                ws.close()
        except Exception:
            pass
        if target:
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/close/{target['id']}", timeout=5).read()
            except Exception:
                pass


def resolve(record: dict, candidates: list[dict]) -> dict:
    ok = [c for c in candidates if c.get('status') == 'OK']
    complete = [c for c in ok if c.get('complete_procedure')]
    result = {
        'contest_id': record['contest_id'],
        'draw_date': record.get('draw_date'),
        'input_candidate_count': len(record.get('candidate_video_ids', [])),
        'resolution_status': 'NEEDS_VISUAL',
        'canonical_video_id': None,
        'supporting_complete_video_ids': [],
        'candidates': sorted(candidates, key=lambda c: (-c.get('score', -1), c.get('duration_seconds') or 10**9, c['video_id'])),
    }
    if complete:
        complete = sorted(complete, key=lambda c: (c.get('duration_seconds') or 10**9, -c.get('score', 0), c['video_id']))
        result['canonical_video_id'] = complete[0]['video_id']
        result['supporting_complete_video_ids'] = [c['video_id'] for c in complete]
        result['resolution_status'] = 'RESOLVED_COMPLETE' if len(complete) == 1 else 'RESOLVED_MULTIPLE_COMPLETE_CANONICAL_MINIMAL'
    elif len([c for c in ok if c.get('caption_contest') and c.get('caption_modality')]) == 1:
        chosen = [c for c in ok if c.get('caption_contest') and c.get('caption_modality')][0]
        result['canonical_video_id'] = chosen['video_id']
        result['resolution_status'] = 'IDENTITY_RESOLVED_PROCEDURE_INCOMPLETE'
    elif not ok:
        result['resolution_status'] = 'CONTENT_UNAVAILABLE'
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--queue', required=True)
    ap.add_argument('--prior', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--pause-seconds', type=float, default=1.5)
    args = ap.parse_args()
    queue = json.loads(Path(args.queue).read_text(encoding='utf-8'))
    prior = json.loads(Path(args.prior).read_text(encoding='utf-8'))
    prior_by = {r['contest_id']: r for r in prior['records']}
    pending_ids = {cid for cid, r in prior_by.items() if not r['resolution_status'].startswith('RESOLVED')}
    records = [r for r in queue['records'] if r['contest_id'] in pending_ids]
    chrome = subprocess.Popen([
        CHROME, '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
        '--remote-debugging-address=127.0.0.1', f'--remote-debugging-port={PORT}', '--remote-allow-origins=*',
        f'--user-data-dir={PROFILE}', 'about:blank'
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        wait_port(PORT)
        resolved = []
        for rec in records:
            candidates = []
            for vid in rec.get('candidate_video_ids', []):
                res = cdp_probe(rec['contest_id'], rec.get('draw_date'), vid)
                candidates.append(res)
                print(json.dumps({'contest_id': rec['contest_id'], 'video_id': vid, 'status': res.get('status'), 'complete': res.get('complete_procedure'), 'score': res.get('score'), 'error': res.get('error')}, ensure_ascii=False), flush=True)
                time.sleep(max(0.2, args.pause_seconds))
            resolved.append(resolve(rec, candidates))
        counts = {}
        for r in resolved:
            counts[r['resolution_status']] = counts.get(r['resolution_status'], 0) + 1
        output = {
            'schema_version': 1,
            'program_id': 'P15_B2_CDP_PENDING_RESOLVER_V1',
            'records_total': len(records),
            'resolution_counts': counts,
            'predictive_evidence': 'NOT_ESTABLISHED',
            'purchase_executed': False,
            'records': resolved,
        }
        Path(args.out).write_text(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True), encoding='utf-8')
        print(json.dumps({k: output[k] for k in ('records_total','resolution_counts','predictive_evidence','purchase_executed')}, ensure_ascii=False, indent=2), flush=True)
    finally:
        chrome.terminate()
        try:
            chrome.wait(timeout=10)
        except Exception:
            chrome.kill()
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
