from __future__ import annotations
import argparse, csv, json
from pathlib import Path

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--state',type=Path,required=True); ap.add_argument('--videos',type=Path,required=True); args=ap.parse_args()
    state=json.loads(args.state.read_text(encoding='utf-8')) if args.state.exists() else {'videos':{}}
    with args.videos.open(encoding='utf-8-sig',newline='') as f: rows=list(csv.DictReader(f))
    ids={r.get('id','').strip() for r in rows if r.get('id','').strip()}
    blocked=[]
    for vid in sorted(ids):
        entry=(state.get('videos') or {}).get(vid) or {}
        if entry.get('status') in {'submitting','uploading'}:
            blocked.append({'id':vid,'status':entry.get('status'),'title':entry.get('title',''),'workflow_run_id':entry.get('workflow_run_id','')})
    if blocked:
        print(json.dumps({'blocked':blocked},ensure_ascii=False,indent=2))
        raise SystemExit('发布前检查失败：清单包含上传结果不确定的记录，请先核对 Bilibili 后再继续')
    print(f'发布前检查通过：{len(ids)} 条清单记录没有 submitting/uploading 阻塞状态')
if __name__=='__main__': main()
