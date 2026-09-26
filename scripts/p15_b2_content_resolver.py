from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import re
import time
import unicodedata
import urllib.request
from pathlib import Path

from yt_dlp import YoutubeDL

YDL_OPTS = {
    'quiet': True,
    'no_warnings': True,
    'skip_download': True,
    'socket_timeout': 25,
    'retries': 2,
    'extractor_retries': 2,
}


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


def fetch_timed_text(info: dict) -> tuple[list[dict], str | None]:
    pools = [info.get('subtitles') or {}, info.get('automatic_captions') or {}]
    tracks = None
    lang = None
    for pool in pools:
        for key in ('pt-orig', 'pt-BR', 'pt'):
            if pool.get(key):
                tracks = pool[key]
                lang = key
                break
        if tracks:
            break
    if not tracks:
        return [], None
    fmt = next((x for x in tracks if x.get('ext') == 'json3'), None)
    if not fmt or not fmt.get('url'):
        return [], lang
    req = urllib.request.Request(fmt['url'], headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=25) as resp:
        raw = resp.read(4_000_000)
    obj = json.loads(raw.decode('utf-8', errors='replace'))
    events = []
    for ev in obj.get('events', []):
        segs = ev.get('segs') or []
        text = ''.join((seg.get('utf8') or '') for seg in segs).strip()
        if not text:
            continue
        events.append({'ms': int(ev.get('tStartMs') or 0), 'text': text, 'norm': norm(text)})
    return events, lang


def first_event_match(events: list[dict], regex: re.Pattern[str] | None = None, token: str | None = None) -> int | None:
    for i, ev in enumerate(events):
        lo = max(0, i - 2)
        hi = min(len(events), i + 3)
        window = ' '.join(x['norm'] for x in events[lo:hi])
        if regex and regex.search(window):
            return ev['ms']
        if token and token in window:
            return ev['ms']
    return None


def marker_hits(events: list[dict], anchor_ms: int | None, radius_ms: int = 12 * 60 * 1000) -> dict[str, int]:
    patterns = {
        'maleta': re.compile(r'\bmaleta\b'),
        'lacre': re.compile(r'\blacre\b'),
        'globo': re.compile(r'\bglobo\b'),
        'auditor': re.compile(r'\bauditor'),
        'balls_25': re.compile(r'(?:\b25\s+bolas\b|\bbolas\b.{0,80}\b0?1\b.{0,80}\b25\b)'),
        'loading': re.compile(r'\b(?:carreg|abastec|colocacao|colocar|suporte)\w*\b'),
        'empty_globe': re.compile(r'\bglobo\b.{0,100}\bvazio\b'),
        'procedure': re.compile(r'\bprocedimento\w*\b|\bpreparativo\w*\b'),
    }
    if anchor_ms is None:
        selected = events
    else:
        selected = [e for e in events if abs(e['ms'] - anchor_ms) <= radius_ms]
    hits: dict[str, int] = {}
    for name, pat in patterns.items():
        for i, ev in enumerate(selected):
            lo = max(0, i - 1)
            hi = min(len(selected), i + 2)
            window = ' '.join(x['norm'] for x in selected[lo:hi])
            if pat.search(window):
                hits[name] = ev['ms']
                break
    return hits


def inspect_candidate(contest_id: int, draw_date: str | None, video_id: str) -> dict:
    url = f'https://www.youtube.com/watch?v={video_id}'
    out = {
        'video_id': video_id,
        'url': url,
        'contest_id': contest_id,
        'draw_date': draw_date,
        'status': 'ERROR',
    }
    try:
        with YoutubeDL(YDL_OPTS) as ydl:
            info = ydl.extract_info(url, download=False)
        title = info.get('title') or ''
        description = info.get('description') or ''
        title_n, desc_n = norm(title), norm(description)
        cre = contest_re(contest_id)
        title_contest = bool(cre.search(title_n))
        desc_contest = bool(cre.search(desc_n))
        title_modality = 'lotofacil' in title_n
        desc_modality = 'lotofacil' in desc_n
        events, lang = fetch_timed_text(info)
        joined = ' '.join(e['norm'] for e in events)
        caption_contest = bool(cre.search(joined))
        caption_modality = 'lotofacil' in joined
        contest_ms = first_event_match(events, regex=cre) if events else None
        modality_ms = first_event_match(events, token='lotofacil') if events else None
        anchor_ms = contest_ms if contest_ms is not None else modality_ms
        markers = marker_hits(events, anchor_ms) if events else {}
        essential = {'maleta', 'globo', 'balls_25'}
        complete = (
            caption_contest and caption_modality
            and essential.issubset(markers)
            and len(markers) >= 4
        )
        identity_strength = sum([
            6 if title_contest else 0,
            3 if title_modality else 0,
            4 if desc_contest else 0,
            2 if desc_modality else 0,
            10 if caption_contest else 0,
            5 if caption_modality else 0,
        ])
        score = identity_strength + len(markers) * 3 + (100 if complete else 0)
        out.update({
            'status': 'OK',
            'title': title,
            'channel': info.get('channel') or info.get('uploader'),
            'upload_date': info.get('upload_date'),
            'duration_seconds': info.get('duration'),
            'timed_text_language': lang,
            'timed_text_events': len(events),
            'title_contest': title_contest,
            'title_modality': title_modality,
            'description_contest': desc_contest,
            'description_modality': desc_modality,
            'caption_contest': caption_contest,
            'caption_modality': caption_modality,
            'contest_anchor_ms': contest_ms,
            'modality_anchor_ms': modality_ms,
            'procedure_markers_ms': markers,
            'complete_procedure': complete,
            'identity_score': identity_strength,
            'score': score,
        })
    except Exception as exc:
        out['error'] = f'{type(exc).__name__}: {exc}'[:1000]
    return out


def resolve_record(record: dict, candidate_results: list[dict]) -> dict:
    ok = [c for c in candidate_results if c.get('status') == 'OK']
    complete = [c for c in ok if c.get('complete_procedure')]
    result = {
        'contest_id': record['contest_id'],
        'draw_date': record.get('draw_date'),
        'input_candidate_count': len(record.get('candidate_video_ids', [])),
        'candidates': sorted(candidate_results, key=lambda x: (-x.get('score', -1), x.get('duration_seconds') or 10**9, x['video_id'])),
        'resolution_status': 'NEEDS_VISUAL',
        'canonical_video_id': None,
        'supporting_complete_video_ids': [],
        'resolution_basis': [],
    }
    if complete:
        complete_sorted = sorted(
            complete,
            key=lambda c: (c.get('duration_seconds') or 10**9, -c.get('score', 0), c['video_id'])
        )
        chosen = complete_sorted[0]
        result['canonical_video_id'] = chosen['video_id']
        result['supporting_complete_video_ids'] = [c['video_id'] for c in complete_sorted]
        if len(complete_sorted) == 1:
            result['resolution_status'] = 'RESOLVED_COMPLETE'
            result['resolution_basis'] = ['ONE_COMPLETE_PROCEDURE_CANDIDATE']
        else:
            result['resolution_status'] = 'RESOLVED_MULTIPLE_COMPLETE_CANONICAL_MINIMAL'
            result['resolution_basis'] = [
                'MULTIPLE_COMPLETE_PROCEDURE_CANDIDATES',
                'CANONICAL_IS_SHORTEST_COMPLETE_VIDEO',
            ]
        return result
    strong_identity = [c for c in ok if c.get('caption_contest') and c.get('caption_modality')]
    if len(strong_identity) == 1:
        result['resolution_status'] = 'IDENTITY_RESOLVED_PROCEDURE_INCOMPLETE'
        result['canonical_video_id'] = strong_identity[0]['video_id']
        result['resolution_basis'] = ['UNIQUE_CAPTION_CONTEST_AND_MODALITY', 'PHYSICAL_PROCEDURE_NOT_PROVEN']
    elif not ok:
        result['resolution_status'] = 'CONTENT_UNAVAILABLE'
        result['resolution_basis'] = ['NO_CANDIDATE_CONTENT_AVAILABLE']
    else:
        result['resolution_basis'] = ['NO_UNIQUE_COMPLETE_PROCEDURE_CANDIDATE']
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--queue', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--workers', type=int, default=4)
    ap.add_argument('--contest', type=int)
    args = ap.parse_args()
    queue = json.loads(Path(args.queue).read_text(encoding='utf-8'))
    records = queue['records']
    if args.contest is not None:
        records = [r for r in records if r['contest_id'] == args.contest]
    jobs = []
    for rec in records:
        for vid in rec.get('candidate_video_ids', []):
            jobs.append((rec['contest_id'], rec.get('draw_date'), vid))
    started = time.time()
    by_contest: dict[int, list[dict]] = {r['contest_id']: [] for r in records}
    with cf.ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
        future_map = {ex.submit(inspect_candidate, *job): job for job in jobs}
        for fut in cf.as_completed(future_map):
            cid, _, vid = future_map[fut]
            try:
                res = fut.result()
            except Exception as exc:
                res = {'contest_id': cid, 'video_id': vid, 'status': 'ERROR', 'error': f'{type(exc).__name__}: {exc}'}
            by_contest[cid].append(res)
            print(json.dumps({'contest_id': cid, 'video_id': vid, 'status': res.get('status'), 'complete': res.get('complete_procedure'), 'score': res.get('score')}, ensure_ascii=False), flush=True)
    resolved = []
    for rec in records:
        resolved.append(resolve_record(rec, by_contest.get(rec['contest_id'], [])))
    summary = {
        'schema_version': 1,
        'program_id': 'P15_PHYSICAL_CONTENT_B2_RESOLVER_V1',
        'records_total': len(records),
        'candidate_videos_total': len(jobs),
        'elapsed_seconds': round(time.time() - started, 3),
        'resolution_counts': {},
        'predictive_evidence': 'NOT_ESTABLISHED',
        'purchase_executed': False,
        'records': resolved,
    }
    for r in resolved:
        s = r['resolution_status']
        summary['resolution_counts'][s] = summary['resolution_counts'].get(s, 0) + 1
    Path(args.out).write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding='utf-8')
    print(json.dumps({k: summary[k] for k in ('records_total','candidate_videos_total','elapsed_seconds','resolution_counts','predictive_evidence','purchase_executed')}, ensure_ascii=False, indent=2), flush=True)
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
