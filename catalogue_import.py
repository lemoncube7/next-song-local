"""Resumable public catalogue import, filtering TJ/KY locally."""
import json,time,urllib.request,re
import core

def run(db,write_lock):
    folder=core.ROOT/'data'/'catalogue-pages';folder.mkdir(parents=True,exist_ok=True)
    state={'status':'running','next_page':1,'total_pages':1,'brand_counts':{}}
    with write_lock:core.set_state(db,'job',{'status':'running','stage':'full_catalogue','done':0,'total':1});db.commit()
    page=1;pages=1
    while page<=pages:
        path=folder/f'{page:03d}.json'
        if path.exists():data=json.loads(path.read_text(encoding='utf8'))
        else:
            req=urllib.request.Request(f'https://api.manana.kr/v2/karaoke/search.json?limit=10000&page={page}',headers={'User-Agent':'NextSongLocal/1.0'})
            with urllib.request.urlopen(req,timeout=45) as response:data=json.load(response)
            path.write_text(json.dumps(data,ensure_ascii=False),encoding='utf8');time.sleep(.5)
        if int(data.get('page',page))!=page:raise ValueError('목록 페이지 번호 불일치')
        pages=max(pages,int(data['total']['page']))
        with write_lock:
            for row in data.get('data',[]):
                if row.get('brand') in ('tj','kumyoung','dam','joysound') and re.fullmatch(r'[0-9]{1,8}(?:-[0-9]{1,3})?',str(row.get('no',''))) and row.get('title') and row.get('singer'):
                    db.execute('INSERT OR REPLACE INTO catalogue VALUES (?,?,?)',(row['brand'],str(row['no']),json.dumps(row,ensure_ascii=False)))
            state.update(next_page=page+1,total_pages=pages,brand_counts=dict(db.execute('SELECT brand,COUNT(*) FROM catalogue GROUP BY brand').fetchall()))
            core.set_state(db,'full_catalogue_job',state);db.commit()
            core.set_state(db,'job',{'status':'running','stage':'full_catalogue','done':page,'total':pages});db.commit()
        page+=1
    with write_lock:
        state['status']='complete';core.set_state(db,'full_catalogue_job',state)
        core.set_state(db,'job',{'status':'complete','stage':'full_catalogue','done':pages,'total':pages});core.rebuild(db)
    return state
