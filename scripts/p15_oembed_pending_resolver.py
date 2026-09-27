from __future__ import annotations
import argparse, json, re, time, unicodedata, urllib.parse, urllib.request
from pathlib import Path

def norm(s:str|None)->str:
    s=unicodedata.normalize('NFKD',s or '')
    s=''.join(ch for ch in s if not unicodedata.combining(ch)).lower()
    s=re.sub(r'[^a-z0-9]+',' ',s)
    return re.sub(r'\s+',' ',s).strip()

def fetch_oembed(video_id:str)->dict:
    watch=f'https://www.youtube.com/watch?v={video_id}'
    url='https://www.youtube.com/oembed?'+urllib.parse.urlencode({'url':watch,'format':'json'})
    req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req,timeout=12) as r:
            d=json.loads(r.read().decode('utf-8','replace'))
        return {'video_id':video_id,'status':'OK','title':d.get('title') or '','author_name':d.get('author_name') or '','author_url':d.get('author_url') or ''}
    except Exception as e:
        return {'video_id':video_id,'status':'ERROR','error':f'{type(e).__name__}: {e}'[:500]}

def score(c:dict)->tuple[int,list[str]]:
    if c.get('status')!='OK':return -999,['UNAVAILABLE']
    t=norm(c.get('title'));a=norm(c.get('author_name'));s=0;why=[]
    if 'loterias caixa' in t:s+=50;why.append('TITLE_FULL_BROADCAST')
    if 'resultado da lotofacil' in t:s-=40;why.append('TITLE_RESULT_CLIP')
    if 'lotofacil' in t and 'resultado' not in t:s+=10;why.append('TITLE_LOTOFACIL')
    if a=='caixa':s+=20;why.append('AUTHOR_CAIXA')
    if a=='redetv':s+=10;why.append('AUTHOR_REDETV')
    return s,why

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--queue',required=True);ap.add_argument('--metadata',required=True);ap.add_argument('--out',required=True);ap.add_argument('--pause',type=float,default=1.0)
    a=ap.parse_args();q=json.loads(Path(a.queue).read_text(encoding='utf-8'));m=json.loads(Path(a.metadata).read_text(encoding='utf-8'))
    visual={r['contest_id'] for r in m['records'] if r['resolution_status']=='NEEDS_VISUAL'}
    records=[r for r in q['records'] if r['contest_id'] in visual]
    out=[]
    for i,r in enumerate(records,1):
        cand=[]
        for vid in r.get('candidate_video_ids',[]):
            c=fetch_oembed(vid);sc,why=score(c);c['score']=sc;c['basis']=why;cand.append(c);time.sleep(a.pause)
        ok=sorted([c for c in cand if c.get('status')=='OK'],key=lambda x:(-x['score'],x['video_id']))
        rec={'contest_id':r['contest_id'],'draw_date':r.get('draw_date'),'resolution_status':'NEEDS_VISUAL','canonical_video_id':None,'candidates':cand,'basis':[]}
        if ok:
            top=ok[0];second=ok[1] if len(ok)>1 else None;margin=top['score']-(second['score'] if second else -999)
            if top['score']>=50 and margin>=30:
                rec['resolution_status']='RESOLVED_BY_OEMBED_METADATA';rec['canonical_video_id']=top['video_id'];rec['basis']=top['basis']+[f'MARGIN_{margin}']
        out.append(rec)
        Path(a.out).write_text(json.dumps({'records_total':len(records),'records_completed':len(out),'records':out},ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'i':i,'contest_id':r['contest_id'],'status':rec['resolution_status'],'canonical':rec['canonical_video_id']},ensure_ascii=False),flush=True)
    counts={}
    for r in out:counts[r['resolution_status']]=counts.get(r['resolution_status'],0)+1
    payload={'schema_version':1,'program_id':'P15_OEMBED_PENDING_RESOLVER','records_total':len(records),'resolution_counts':counts,'predictive_evidence':'NOT_ESTABLISHED','purchase_executed':False,'records':out}
    Path(a.out).write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'FINAL':True,'resolution_counts':counts},ensure_ascii=False),flush=True)
if __name__=='__main__':main()
