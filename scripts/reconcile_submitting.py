from __future__ import annotations
import argparse, json
from datetime import datetime, timezone
from pathlib import Path
import requests

def cookies(path):
    raw=json.loads(path.read_text(encoding='utf-8'))
    return {x['name']:x['value'] for x in raw.get('cookie_info',{}).get('cookies',[])}
def find_items(obj):
    if isinstance(obj,dict):
        yield obj
        for v in obj.values(): yield from find_items(v)
    elif isinstance(obj,list):
        for v in obj: yield from find_items(v)
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--cookies',type=Path,required=True); ap.add_argument('--state',type=Path,required=True); ap.add_argument('--video-id',required=True); ap.add_argument('--title',required=True); ap.add_argument('--report',type=Path,required=True); args=ap.parse_args()
    sess=requests.Session(); sess.cookies.update(cookies(args.cookies)); sess.headers.update({'User-Agent':'Mozilla/5.0','Origin':'https://member.bilibili.com','Referer':'https://member.bilibili.com/'})
    matches=[]
    for pn in range(1,101):
        r=sess.get('https://member.bilibili.com/x2/creative/web/archives/sp',params={'pn':pn,'ps':50},timeout=30); r.raise_for_status(); payload=r.json()
        if payload.get('code') not in (0,None): raise RuntimeError(f"Bilibili API failed: {payload.get('code')} {payload.get('message')}")
        for item in find_items(payload.get('data',payload)):
            text=' '.join(str(item.get(k,'')) for k in ('title','name','archive_title','arc_title'))
            if args.title in text or text.strip()==args.title:
                aid=item.get('aid') or item.get('archive_id'); bvid=item.get('bvid') or item.get('bvid_str')
                if aid or bvid: matches.append({'aid':aid,'bvid':bvid,'title':text.strip(),'keys':sorted(item)})
        data=payload.get('data')
        if not isinstance(data,dict) or not data.get('archives') and not data.get('list') and pn>1: break
    state=json.loads(args.state.read_text(encoding='utf-8')); entry=(state.get('videos') or {}).get(args.video_id)
    if not entry: raise RuntimeError(f'video id not found in state: {args.video_id}')
    now=datetime.now(timezone.utc).isoformat()
    report={'video_id':args.video_id,'title':args.title,'matches':matches,'checked_at':now}
    if matches:
        m=matches[0]; entry.update({'status':'published','aid':int(m['aid']) if m.get('aid') else None,'bvid':str(m.get('bvid') or ''),'reconciled_at':now,'reconcile_reason':'账号稿件列表按标题核对到已存在稿件'})
        report['action']='marked_published'
    else:
        entry.update({'status':'retryable','reconciled_at':now,'reconcile_reason':'账号稿件列表未找到同标题稿件，可重新处理'})
        report['action']='marked_retryable'
    args.state.write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); args.report.parent.mkdir(parents=True,exist_ok=True); args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__': main()
