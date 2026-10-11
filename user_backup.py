"""Portable user decisions; excludes watch history, API keys and network caches."""
import json
from datetime import datetime,timezone
import core

TYPES={'corrections':dict,'song_aliases':dict,'different_songs':dict,'merge_history':list,
       'follows':list,'hidden':list,'queue':list,'karaoke_good':list,'karaoke_ratings':dict,'numbers':dict}

def export(db):
    return {'format':'karaoke-user-decisions','version':1,'created_at':datetime.now(timezone.utc).isoformat(),
            'user_state':{r['key']:json.loads(r['data']) for r in db.execute('SELECT * FROM user_state') if r['key'] in TYPES}}

def restore(db,payload):
    if payload.get('format')!='karaoke-user-decisions' or payload.get('version')!=1:raise ValueError('지원하지 않는 정리 내용 백업입니다.')
    state=payload.get('user_state')
    if not isinstance(state,dict):raise ValueError('백업 내용이 잘못되었습니다.')
    for key,value in state.items():
        if key not in TYPES or not isinstance(value,TYPES[key]):raise ValueError('잘못된 백업 항목: '+key)
    for vid,edit in state.get('corrections',{}).items():
        if not isinstance(edit,dict) or (not edit.get('exclude') and not all(isinstance(edit.get(k),str) and edit[k].strip() for k in ('title','artist'))):raise ValueError('곡 수정 정보가 잘못되었습니다.')
    previous=export(db)
    folder=core.ROOT/'data'/'backups';folder.mkdir(parents=True,exist_ok=True)
    filename='before-restore-'+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f')+'.json'
    (folder/filename).write_text(json.dumps(previous,ensure_ascii=False,indent=2),encoding='utf8')
    try:
        for key in TYPES:db.execute('DELETE FROM user_state WHERE key=?',(key,))
        for key,value in state.items():core.set_state(db,key,value,'user_state')
        core.rebuild(db)
    except Exception:
        db.rollback()
        raise
    return {'ok':True,'items':len(state),'previous_backup':filename}
