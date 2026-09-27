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
    t=norm(c.get('title'));d=norm(c.get('description'));dur=int(c.get('duration_seconds') or 0)
    s=0;why=[]
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
    ap=argparse.ArgumentParser();ap.add_argument('--queue',required=True);ap.add_argument('--prior',required=True);ap.add_argument('--candidate-script',required=True);ap.add_argument('--out',required=True);ap.add_argument('--timeout',type=int,default=28);ap.add_argument('--pause',type=float,default=1.0);ap.add_argument('--max-new-records',type=int,default=6)
    a=ap.parse_args();q=json.loads(Path(a.queue).read_text(encoding='utf-8'));prior=json.loads(Path(a.prior).read_text(encoding='utf-8'));outp=Path(a.out);cachep=outp.with_suffix('.candidates.json')
    pending={r['contest_id'] for r in prior['records'] if not r['resolution_status'].startswith('RESOLVED')}
    records=[r for r in q['records'] if r['contest_id'] in pending]
    cache=json.loads(cachep.read_text(encoding='utf-8')) if cachep.exists() else {}
    existing=json.loads(outp.read_text(encoding='utf-8')) if outp.exists() else {'records':[]}
    done={r['contest_id']:r for r in existing.get('records',[])}
    processed_new=0
    def save():
        cachep.write_text(json.dumps(cache,ensure_ascii=False,indent=2),encoding='utf-8')
        ordered=[done[r['contest_id']] for r in records if r['contest_id'] in done]
        counts={}
        for rr in ordered:counts[rr['resolution_status']]=counts.get(rr['resolution_status'],0)+1
        outp.write_text(json.dumps({'schema_version':3,'records_total':len(records),'records_completed':len(ordered),'resolution_counts':counts,'predictive_evidence':'NOT_ESTABLISHED','purchase_executed':False,'records':ordered},ensure_ascii=False,indent=2),encoding='utf-8')
    for r in records:
        cid=r['contest_id']
        if cid in done:continue
        cand=[]
        for vid in r.get('candidate_video_ids',[]):
            key=f'{cid}:{vid}'
            if key in cache:c=cache[key]
            else:
                try:
                    cp=subprocess.run([sys.executable,a.candidate_script,vid],capture_output=True,text=True,timeout=a.timeout)
                    lines=[x for x in cp.stdout.splitlines() if x.strip()]
                    c=json.loads(lines[-1]) if lines else {'video_id':vid,'status':'ERROR','error':(cp.stderr or 'NO_OUTPUT')[-800:]}
                except subprocess.TimeoutExpired:c={'video_id':vid,'status':'TIMEOUT','error':f'TIMEOUT_{a.timeout}s'}
                except Exception as e:c={'video_id':vid,'status':'ERROR','error':f'{type(e).__name__}: {e}'[:800]}
                cache[key]=c;save();time.sleep(a.pause)
            sc,why=score(cid,c);cc=dict(c);cc['metadata_score']=sc;cc['metadata_basis']=why;cand.append(cc)
        ok=sorted([c for c in cand if c.get('status')=='OK'],key=lambda c:(-c['metadata_score'],-int(c.get('duration_seconds') or 0),c['video_id']))
        rec={'contest_id':cid,'draw_date':r.get('draw_date'),'resolution_status':'NEEDS_VISUAL','canonical_video_id':None,'basis':[],'candidates':cand}
        if ok:
            top=ok[0];second=ok[1] if len(ok)>1 else None;margin=top['metadata_score']-(second['metadata_score'] if second else -999)
            if top['metadata_score']>=65 and margin>=20:
                rec['resolution_status']='RESOLVED_BY_OFFICIAL_METADATA';rec['canonical_video_id']=top['video_id'];rec['basis']=top['metadata_basis']+[f'MARGIN_{margin}']
        done[cid]=rec;processed_new+=1;save()
        print(json.dumps({'new':processed_new,'contest_id':cid,'status':rec['resolution_status'],'canonical':rec['canonical_video_id']},ensure_ascii=False),flush=True)
        if processed_new>=a.max_new_records:break
    ordered=[done[r['contest_id']] for r in records if r['contest_id'] in done]
    counts={}
    for rr in ordered:counts[rr['resolution_status']]=counts.get(rr['resolution_status'],0)+1
    print(json.dumps({'CHECKPOINT':True,'records_total':len(records),'records_completed':len(ordered),'new_records':processed_new,'resolution_counts':counts},ensure_ascii=False),flush=True)
if __name__=='__main__':main()
