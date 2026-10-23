import json
from pathlib import Path
import pandas as pd

def main():
    paths=sorted(Path('data/records').glob('*.json'))
    if not paths:raise SystemExit('Нет карточек. Сначала collect.py')
    rows=[json.loads(p.read_text(encoding='utf-8')) for p in paths]
    frame=pd.json_normalize(rows)
    if frame.patent_id.duplicated().any():raise SystemExit('Повтор patent_id')
    if frame.title.isna().any():raise SystemExit('Нет названия')
    out=Path('results');out.mkdir(exist_ok=True)
    (out/'variant11.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
    with (out/'variant11.jsonl').open('w',encoding='utf-8') as f:
        for row in rows:f.write(json.dumps(row,ensure_ascii=False)+'\n')
    frame.to_csv(out/'table.csv',index=False,encoding='utf-8-sig')
    quality={
        'variant':11,'records':len(rows),
        'by_type':frame.patent_type.value_counts().to_dict(),
        'unreviewed':sum(bool(r.get('review_required',True)) for r in rows),
        'missing_date':sum(not r.get('date') for r in rows),
        'coverage':'partial; full assigned range NOT verified',
        'ready_for_submission':False
    }
    (out/'quality.json').write_text(json.dumps(quality,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(quality,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
