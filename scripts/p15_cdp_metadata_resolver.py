from __future__ import annotations
import argparse, json, re, subprocess, time, urllib.parse, urllib.request
from pathlib import Path
import websocket

CHROME=r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT=9230
PROFILE=r"C:\Users\andre\P15Tools\ChromeP15MetadataResolver"

def norm(s:str|None)->str:
    s=(s or '').lower()
    s=re.sub(r'[^a-z0-9áàâãéêíóôõúç]+',' ',s)
    return re.sub(r'\s+',' ',s).strip()

def wait_port():
    end=time.time()+20
    while time.time()<end:
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{PORT}/json/version',timeout=2): return
        except Exception: time.sleep(.5)
    raise RuntimeError('CDP_START_TIMEOUT')

def probe(video_id:str)->dict:
    url=f'https://www.youtube.com/watch?v={video_id}'
    with urllib.request.urlopen(f'http://127.0.0.1:{PORT}/json') as r: target=json.loads(r.read().decode())[0]
    ws=websocket.create_connection(target['webSocketDebuggerUrl'],timeout=15,origin=f'http://127.0.0.1:{PORT}')
    seq=0
    def cmd(method,params=None):
        nonlocal seq
        seq+=1; my=seq
        ws.send(json.dumps({'id':my,'method':method,'params':params or {}}))
        while True:
            m=json.loads(ws.recv())
            if m.get('id')==my:return m
    def ev(expr):
        r=cmd('Runtime.evaluate',{'expression':expr,'returnByValue':True,'userGesture':True})
        return (((r.get('result') or {}).get('result') or {}).get('value'))
    try:
        cmd('Runtime.enable'); cmd('Page.enable'); cmd('Page.navigate',{'url':url})
        end=time.time()+18; player=None
        while time.time()<end:
            raw=ev('JSON.stringify(window.ytInitialPlayerResponse||null)')
            if raw and raw!='null': player=json.loads(raw); break
            time.sleep(1)
        if not player:return {'video_id':video_id,'status':'ERROR','error':'PLAYER_RESPONSE_UNAVAILABLE'}
        d=player.get('videoDetails') or {}; p=player.get('playabilityStatus') or {}
        return {'video_id':video_id,'status':'OK','title':d.get('title') or '', 'description':d.get('shortDescription') or '', 'duration_seconds':int(d.get('lengthSeconds') or 0), 'playability_status':p.get('status')}
    finally:
        ws.close()

def score_candidate(contest_id:int,c:dict)->tuple[int,list[str]]:
    if c.get('status')!='OK': return (-999, ['UNAVAILABLE'])
    t=norm(c.get('title')); d=norm(c.get('description')); dur=c.get('duration_seconds') or 0
    s=0; why=[]
    if re.search(r'loterias caixa',t): s+=30; why.append('TITLE_OFFICIAL_FULL_BROADCAST')
    if re.search(r'resultado da lotofácil|resultado da lotofacil',t): s-=30; why.append('TITLE_RESULT_CLIP')
    if re.search(rf'lotofácil\s*-?\s*concurso\s*(?:nº|n|numero)?\s*{contest_id}\b',d,re.I) or re.search(rf'lotofacil\s*-?\s*concurso\s*(?:nº|n|numero)?\s*{contest_id}\b',norm(d)):
        s+=35; why.append('DESCRIPTION_EXPLICIT_CONTEST')
    elif str(contest_id) in d and 'lotof' in d:
        s+=20; why.append('DESCRIPTION_MODALITY_AND_CONTEST')
    if dur>=900: s+=20; why.append('DURATION_GE_15MIN')
    elif dur>=480: s+=10; why.append('DURATION_GE_8MIN')
    elif dur<=360: s-=10; why.append('SHORT_CLIP')
    if any(x in d for x in ('quina','mega sena','timemania','dia de sorte','mais milionária','mais milionaria')):
        s+=10; why.append('MULTI_LOTTERY_DESCRIPTION')
    return s,why

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--queue',required=True); ap.add_argument('--prior',required=True); ap.add_argument('--out',required=True); ap.add_argument('--pause',type=float,default=2.0)
    a=ap.parse_args(); q=json.loads(Path(a.queue).read_text(encoding='utf-8')); prior=json.loads(Path(a.prior).read_text(encoding='utf-8'))
    pending={r['contest_id'] for r in prior['records'] if not r['resolution_status'].startswith('RESOLVED')}
    records=[r for r in q['records'] if r['contest_id'] in pending]
    chrome=subprocess.Popen([CHROME,'--headless=new','--disable-gpu','--no-first-run','--no-default-browser-check',f'--remote-debugging-port={PORT}','--remote-debugging-address=127.0.0.1','--remote-allow-origins=*',f'--user-data-dir={PROFILE}','about:blank'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    out=[]
    try:
        wait_port()
        for i,r in enumerate(records,1):
            cand=[]
            for vid in r.get('candidate_video_ids',[]):
                try: c=probe(vid)
                except Exception as e: c={'video_id':vid,'status':'ERROR','error':f'{type(e).__name__}: {e}'}
                sc,why=score_candidate(r['contest_id'],c); c['metadata_score']=sc; c['metadata_basis']=why; cand.append(c); time.sleep(a.pause)
            ok=sorted([c for c in cand if c.get('status')=='OK'],key=lambda x:(-x['metadata_score'],-(x.get('duration_seconds') or 0),x['video_id']))
            rec={'contest_id':r['contest_id'],'draw_date':r.get('draw_date'),'candidates':cand,'resolution_status':'NEEDS_VISUAL','canonical_video_id':None,'basis':[]}
            if ok:
                top=ok[0]; second=ok[1] if len(ok)>1 else None
                margin=top['metadata_score']-(second['metadata_score'] if second else -999)
                if top['metadata_score']>=55 and margin>=20:
                    rec['resolution_status']='RESOLVED_BY_OFFICIAL_METADATA'; rec['canonical_video_id']=top['video_id']; rec['basis']=top['metadata_basis']+[f'MARGIN_{margin}']
            out.append(rec)
            Path(a.out).write_text(json.dumps({'records_total':len(records),'records_completed':len(out),'records':out},ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps({'i':i,'contest_id':r['contest_id'],'status':rec['resolution_status'],'canonical':rec['canonical_video_id']},ensure_ascii=False),flush=True)
    finally:
        try: chrome.terminate(); chrome.wait(timeout=5)
        except Exception:
            try: chrome.kill()
            except Exception: pass
    counts={}
    for r in out: counts[r['resolution_status']]=counts.get(r['resolution_status'],0)+1
    payload={'schema_version':1,'program_id':'P15_CDP_METADATA_RESOLVER','records_total':len(records),'resolution_counts':counts,'predictive_evidence':'NOT_ESTABLISHED','purchase_executed':False,'records':out}
    Path(a.out).write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'FINAL':True,'resolution_counts':counts},ensure_ascii=False))
if __name__=='__main__': main()
