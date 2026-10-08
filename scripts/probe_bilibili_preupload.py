from __future__ import annotations
import argparse, json
from pathlib import Path
import requests

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--cookies',required=True); ap.add_argument('--file',required=True); args=ap.parse_args()
    raw=json.loads(Path(args.cookies).read_text(encoding='utf-8'))
    cookies={x['name']:x['value'] for x in raw.get('cookie_info',{}).get('cookies',[])}
    s=requests.Session(); s.cookies.update(cookies); s.headers.update({'User-Agent':'Mozilla/5.0','Origin':'https://member.bilibili.com','Referer':'https://member.bilibili.com/'})
    path=Path(args.file); size=path.stat().st_size; out=[]
    probe=s.get('https://member.bilibili.com/preupload?r=probe',timeout=30); probe.raise_for_status(); pdata=probe.json()
    out.append({'stage':'probe','http':probe.status_code,'keys':sorted(pdata) if isinstance(pdata,dict) else type(pdata).__name__,'code':pdata.get('code') if isinstance(pdata,dict) else None,'message':pdata.get('message') if isinstance(pdata,dict) else None})
    lines=pdata.get('lines') or pdata.get('data') or []
    if isinstance(lines,dict): lines=lines.get('lines') or []
    if not isinstance(lines,list): lines=[]
    for line in lines[:8]:
        if not isinstance(line,dict): continue
        q=line.get('query',''); params={'r':'upos','profile':'ugcupos/bup','ssl':0,'version':'2.8.12','build':2081200,'name':path.name,'size':size}
        r=s.get('https://member.bilibili.com/preupload?'+q,params=params,timeout=30)
        try: j=r.json()
        except Exception: j={}
        out.append({'stage':'preupload','query_safe':q.split('&')[0] if q else '','http':r.status_code,'keys':sorted(j) if isinstance(j,dict) else [type(j).__name__],'code':j.get('code') if isinstance(j,dict) else None,'message':j.get('message') if isinstance(j,dict) else None,'data_keys':sorted(j.get('data',{})) if isinstance(j,dict) and isinstance(j.get('data'),dict) else []})
    print(json.dumps(out,ensure_ascii=False,indent=2))
if __name__=='__main__': main()
