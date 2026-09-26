from __future__ import annotations

import argparse
import json
import re
import time
import unicodedata
from pathlib import Path

from youtube_transcript_api import YouTubeTranscriptApi


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


def marker_hits(events: list[dict], anchor_ms: int | None, radius_ms: int = 12 * 60 * 1000) -> dict[str, int]:
    pats = {
        'maleta': re.compile(r'\bmaleta\b'),
        'lacre': re.compile(r'\blacre\b'),
        'globo': re.compile(r'\bglobo\b'),
        'auditor': re.compile(r'\bauditor'),
        'balls_25': re.compile(r'(?:\b25\s+bolas\b|\bbolas\b.{0,100}\b0?1\b.{0,100}\b25\b)'),
        'loading': re.compile(r'\b(?:carreg|abastec|colocacao|colocar|suporte)\w*\b'),
        'empty_globe': re.compile(r'\bglobo\b.{0,120}\bvazio\b'),
        'procedure': re.compile(r'\bprocedimento\w*\b|\bpreparativo\w*\b'),
    }
    selected = events if anchor_ms is None else [e for e in events if abs(e['ms'] - anchor_ms) <= radius_ms]
    hits: dict[str, int] = {}
    for name, pat in pats.items():
        for i in range(len(selected)):
            window = ' '.join(e['norm'] for e in selected[max(0, i-2):min(len(selected), i+3)])
            if pat.search(window):
                hits[name] = selected[i]['ms']
                break
    return hits


def prior_candidate_map(prior: dict) -> dict[str, dict]:
    out = {}
    for rec in prior.get('records', []):
        for cand in rec.get('candidates', []):
            out[cand.get('video_id')] = cand
    return out


def inspect_candidate(api: YouTubeTranscriptApi, contest_id: int, draw_date: str | None, video_id: str, prior_meta: dict | None) -> dict:
    out = {
        'contest_id': contest_id,
        'draw_date': draw_date,
        'video_id': video_id,
        'url': f'https://www.youtube.com/watch?v={video_id}',
        'status': 'NO_TRANSCRIPT',
    }
    try:
        fetched = api.fetch(video_id, languages=['pt', 'pt-BR', 'pt-PT'])
        events = []
        duration_s = 0.0
        for snip in fetched:
            text = snip.text or ''
            start = float(snip.start or 0.0)
            dur = float(snip.duration or 0.0)
            duration_s = max(duration_s, start + dur)
            if text.strip():
                events.append({'ms': int(round(start * 1000)), 'text': text, 'norm': norm(text)})
        joined = ' '.join(e['norm'] for e in events)
        cre = contest_re(contest_id)
        caption_contest = bool(cre.search(joined))
        caption_modality = 'lotofacil' in joined
        anchor_ms = None
        for e in events:
            if cre.search(e['norm']):
                anchor_ms = e['ms']
                break
        if anchor_ms is None:
            for e in events:
                if 'lotofacil' in e['norm']:
                    anchor_ms = e['ms']
                    break
        markers = marker_hits(events, anchor_ms)
        essential = {'maleta', 'globo', 'balls_25'}
        complete = caption_contest and caption_modality and essential.issubset(markers) and len(markers) >= 4
        prior_meta = prior_meta or {}
        title_contest = bool(prior_meta.get('title_contest'))
        title_modality = bool(prior_meta.get('title_modality'))
        desc_contest = bool(prior_meta.get('description_contest'))
        desc_modality = bool(prior_meta.get('description_modality'))
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
            'transcript_events': len(events),
            'transcript_language': getattr(fetched, 'language_code', None),
            'duration_seconds_estimate': round(duration_s, 3),
            'caption_contest': caption_contest,
            'caption_modality': caption_modality,
            'contest_anchor_ms': anchor_ms,
            'procedure_markers_ms': markers,
            'complete_procedure': complete,
            'identity_score': identity_score,
            'score': score,
            'prior_title_contest': title_contest,
            'prior_title_modality': title_modality,
            'prior_description_contest': desc_contest,
            'prior_description_modality': desc_modality,
        })
        return out
    except Exception as exc:
        out['error_type'] = type(exc).__name__
        out['error'] = str(exc)[:1000]
        return out


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
        'candidates': sorted(candidates, key=lambda c: (-c.get('score', -1), c.get('duration_seconds_estimate') or 10**9, c['video_id'])),
    }
    if complete:
        complete = sorted(complete, key=lambda c: (c.get('duration_seconds_estimate') or 10**9, -c.get('score', 0), c['video_id']))
        result['canonical_video_id'] = complete[0]['video_id']
        result['supporting_complete_video_ids'] = [c['video_id'] for c in complete]
        result['resolution_status'] = 'RESOLVED_COMPLETE' if len(complete) == 1 else 'RESOLVED_MULTIPLE_COMPLETE_CANONICAL_MINIMAL'
        return result
    strong = [c for c in ok if c.get('caption_contest') and c.get('caption_modality')]
    if len(strong) == 1:
        result['canonical_video_id'] = strong[0]['video_id']
        result['resolution_status'] = 'IDENTITY_RESOLVED_PROCEDURE_INCOMPLETE'
    elif not ok:
        result['resolution_status'] = 'TRANSCRIPT_UNAVAILABLE'
    return result


def write_checkpoint(path: Path, resolved: list[dict], total: int) -> None:
    counts = {}
    for rec in resolved:
        counts[rec['resolution_status']] = counts.get(rec['resolution_status'], 0) + 1
    payload = {
        'schema_version': 1,
        'program_id': 'P15_B2_TRANSCRIPT_RESOLVER_V1',
        'records_total': total,
        'records_completed': len(resolved),
        'resolution_counts': counts,
        'predictive_evidence': 'NOT_ESTABLISHED',
        'purchase_executed': False,
        'records': resolved,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding='utf-8')


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--queue', required=True)
    ap.add_argument('--prior', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--contest', type=int)
    ap.add_argument('--pause-seconds', type=float, default=2.0)
    args = ap.parse_args()
    queue = json.loads(Path(args.queue).read_text(encoding='utf-8'))
    prior = json.loads(Path(args.prior).read_text(encoding='utf-8'))
    meta = prior_candidate_map(prior)
    prior_by = {r['contest_id']: r for r in prior.get('records', [])}
    pending_ids = {cid for cid, rec in prior_by.items() if not rec['resolution_status'].startswith('RESOLVED')}
    records = [r for r in queue['records'] if r['contest_id'] in pending_ids]
    if args.contest is not None:
        records = [r for r in records if r['contest_id'] == args.contest]
    out_path = Path(args.out)
    partial_path = out_path.with_suffix(out_path.suffix + '.partial')
    api = YouTubeTranscriptApi()
    resolved = []
    for rec in records:
        candidates = []
        for vid in rec.get('candidate_video_ids', []):
            res = inspect_candidate(api, rec['contest_id'], rec.get('draw_date'), vid, meta.get(vid))
            candidates.append(res)
            print(json.dumps({'contest_id': rec['contest_id'], 'video_id': vid, 'status': res.get('status'), 'events': res.get('transcript_events'), 'complete': res.get('complete_procedure'), 'score': res.get('score'), 'error_type': res.get('error_type')}, ensure_ascii=False), flush=True)
            time.sleep(max(0.2, args.pause_seconds))
        resolved.append(resolve(rec, candidates))
        write_checkpoint(partial_path, resolved, len(records))
    write_checkpoint(out_path, resolved, len(records))
    if partial_path.exists():
        partial_path.unlink()
    final = json.loads(out_path.read_text(encoding='utf-8'))
    print(json.dumps({k: final[k] for k in ('records_total','records_completed','resolution_counts','predictive_evidence','purchase_executed')}, ensure_ascii=False, indent=2), flush=True)
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
