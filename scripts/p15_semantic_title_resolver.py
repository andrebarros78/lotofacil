from __future__ import annotations
import argparse, json, re, unicodedata
from pathlib import Path

def norm(s:str|None)->str:
    s=unicodedata.normalize('NFKD',s or '')
    s=''.join(ch for ch in s if not unicodedata.combining(ch)).lower()
    s=re.sub(r'[^a-z0-9]+',' ',s)
    return re.sub(r'\s+',' ',s).strip()

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--oembed',required=True);ap.add_argument('--out',required=True)
    a=ap.parse_args();d=json.loads(Path(a.oembed).read_text(encoding='utf-8'));out=[]
    for r in d['records']:
        cid=r['contest_id']; cand=r['candidates']; ok=[c for c in cand if c.get('status')=='OK']
        rec={'contest_id':cid,'draw_date':r.get('draw_date'),'resolution_status':'NEEDS_VISUAL','canonical_video_id':None,'supporting_video_ids':[],'basis':[],'candidates':cand}
        if len(ok)>=2:
            titles=[norm(c.get('title')) for c in ok]
            # Exact target contest beats an explicitly wrong contest/result clip.
            exact=[c for c,t in zip(ok,titles) if 'lotofacil' in t and str(cid) in t]
            wrong=[c for c,t in zip(ok,titles) if 'lotofacil' in t and re.search(r'concurso\s+(?:n\s+)?(\d+)',t) and str(cid) not in t]
            if len(exact)==1 and wrong:
                rec['resolution_status']='RESOLVED_BY_EXACT_TARGET_TITLE';rec['canonical_video_id']=exact[0]['video_id'];rec['basis']=['TITLE_EXPLICIT_TARGET_CONTEST','OTHER_CANDIDATE_EXPLICIT_DIFFERENT_CONTEST']
            else:
                federal=[c for c,t in zip(ok,titles) if 'federal' in t]
                nonfed=[c for c,t in zip(ok,titles) if 'federal' not in t]
                if len(federal)>=1 and len(nonfed)==1:
                    rec['resolution_status']='RESOLVED_BY_BROADCAST_TYPE';rec['canonical_video_id']=nonfed[0]['video_id'];rec['basis']=['NON_FEDERAL_GENERAL_BROADCAST_SELECTED','FEDERAL_SPECIFIC_BROADCAST_EXCLUDED_FOR_LOTOFACIL']
                elif len(set(titles))==1 and len({norm(c.get('author_name')) for c in ok})==1 and 'lotofacil' in titles[0]:
                    ids=sorted(c['video_id'] for c in ok)
                    rec['resolution_status']='RESOLVED_EQUIVALENT_BROADCASTS';rec['canonical_video_id']=ids[0];rec['supporting_video_ids']=ids;rec['basis']=['IDENTICAL_TITLE_AND_AUTHOR','TITLE_EXPLICITLY_INCLUDES_LOTOFACIL','CANONICAL_ID_DETERMINISTIC_ONLY']
        out.append(rec)
    counts={}
    for r in out:counts[r['resolution_status']]=counts.get(r['resolution_status'],0)+1
    payload={'schema_version':1,'program_id':'P15_SEMANTIC_TITLE_RESOLVER','records_total':len(out),'resolution_counts':counts,'predictive_evidence':'NOT_ESTABLISHED','purchase_executed':False,'records':out}
    Path(a.out).write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'FINAL':True,'resolution_counts':counts,'records_total':len(out)},ensure_ascii=False))
if __name__=='__main__':main()
