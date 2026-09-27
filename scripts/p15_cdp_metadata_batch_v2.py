from __future__ import annotations
import argparse, json, re, subprocess, sys, time, unicodedata
from pathlib import Path


def norm(s:str|None)->str:
    s=unicodedata.normalize('NFKD',s or '')
    s=''.join(ch for ch in s if not unicodedata.combining(ch)).lower()
    s=re.sub(r'[^a-z0-9]+',' ',s)
    return re.sub(r'\s+',' ',s).strip()

def score(contest:int,c:dict)->tuple[int,list[str]]:
    if c.get('status')!='OK':return -999,['UNAVAILABLE']
    t=norm(c.get('title')); d=norm(c.get('description')); dur=int(c.get('duration_seconds') or 0)
    s=0; why=[]
    if 'loterias caixa' in t:s+=30;why.append('TITLE_OFFICIAL_FULL_BROADCAST')
    if 'resultado da lotofacil' in t:s-=30;why.append('TITLE_RESULT_CLIP')
    if 'lotofacil' in d and str(contest) in d:s+=35;why.append('DESCRIPTION_MODALITY_AND_CONTEST')
    if dur>=900:s+=20;why.append('DURATION_GE_15MIN')
    elif dur>=480:s+=10;why.append('DURATION_GE_8MIN')
    elif dur<=360:s-=10;why.append('SHORT_CLIP')
    if sum(x in d for x in ('quina','mega sena','timemania','dia de sorte','mais milionaria'))>=2:s+=10;why.append('MULTI_LOTTERY_DESCRIPTION')
    if norm(c.get('author'))=='caixa':s+=10;why.append('AUTHOR_CAIXA')
    return s,why

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--queue',required=True);ap.add_argument('--prior',required=True);ap.add_argument('--candidate-script',required=True);ap.add_argument('--out',required=True);ap.add_argument('--timeout',type=int,default=35);ap.add_argument('--pause',type=float,default=1.5)
    a=ap.parse_args();q=json.loads(Path(a.queue).read_text(encoding='utf-8')); prior=json.loads(Path(a.prior).read_text(encoding='utf-8'))
    pending={r['contest_id'] for r in prior['records'] if not r['resolution_status'].startswith('RESOLVED')}
    records=[r for r in q['records'] if r['contest_id'] in pending]
    out=[]; cache={}; outp=Path(a.out); cachep=outp.with_suffix('.candidates.json')
    def save():
        cachep.write_text(json.dumps(cache,ensure_ascii=False,indent=2),encoding='utf-8')
        counts={}
        for r in out:counts[r['resolution_status']]=counts.get(r['resolution_status'],0)+1
        outp.write_text(json.dumps({'schema_version':2,'records_total':len(records),'records_completed':len(out),'resolution_counts':counts,'predictive_evidence':'NOT_ESTABLISHED','purchase_executed':False,'records':out},ensure_ascii=False,indent=2),encoding='utf-8')
    for idx,r in enumerate(records,1):
        cand=[]
        for vid in r.get('candidate_video_ids',[]):
            key=f"{r['contest_id']}:{vid}"
            if key in cache:c=cache[key]
            else:
                try:
                    cp=subprocess.run([sys.executable,a.candidate_script,vid],capture_output=True,text=True,timeout=a.timeout)
                    lines=[x for x in cp.stdout.splitlines() if x.strip()]
                    c=json.loads(lines[-1]) if lines else {'video_id':vid,'status':'ERROR','error':(cp.stderr or 'NO_OUTPUT')[-800:]}
                except subprocess.TimeoutExpired:
                    c={'video_id':vid,'status':'TIMEOUT','error':f'TIMEOUT_{a.timeout}s'}
                except Exception as e:
                    c={'video_id':vid,'status':'ERROR','error':f'{type(e).__name__}: {e}'[:800]}
                cache[key]=c;save();time.sleep(a.pause)
            sc,why=score(r['contest_id'],c); cc=dict(c);cc['metadata_score']=sc;cc['metadata_basis']=why;cand.append(cc)
        ok=sorted([c for c in cand if c.get('status')=='OK'],key=lambda c:(-c['metadata_score'],-int(c.get('duration_seconds') or 0),c['video_id']))
        rec={'contest_id':r['contest_id'],'draw_date':r.get('draw_date'),'resolution_status':'NEEDS_VISUAL','canonical_video_id':None,'basis':[],'candidates':cand}
        if ok:
            top=ok[0];second=ok[1] if len(ok)>1 else None;margin=top['metadata_score']-(second['metadata_score'] if second else -999)
            if top['metadata_score']>=65 and margin>=20:
                rec['resolution_status']='RESOLVED_BY_OFFICIAL_METADATA';rec['canonical_video_id']=top['video_id'];rec['basis']=top['metadata_basis']+[f'MARGIN_{margin}']
        out.append(rec);save()
        print(json.dumps({'i':idx,'records_total':len(records),'contest_id':r['contest_id'],'status':rec['resolution_status'],'canonical':rec['canonical_video_id']},ensure_ascii=False),flush=True)
    counts={}
    for r in out:counts[r['resolution_status']]=counts.get(r['resolution_status'],0)+1
    print(json.dumps({'FINAL':True,'resolution_counts':counts},ensure_ascii=False),flush=True)
if __name__=='__main__':main()
