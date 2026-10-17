"""Private PC/phone snapshot transfer; never part of shared GitHub documents."""
import json,re,secrets,time,uuid
from datetime import datetime,timezone
import core,song_identity,friends

FORMAT='next-song-mobile';OPERATIONS='next-song-mobile-changes'
def source_id(db):
    value=core.get_state(db,'mobile_source_id','', 'user_state')
    if not value:
        value=uuid.uuid4().hex;core.set_state(db,'mobile_source_id',value,'user_state');db.commit()
    return value

def ensure(db):
    db.execute('CREATE TABLE IF NOT EXISTS mobile_applied(id TEXT PRIMARY KEY,source_id TEXT,applied_at REAL)')

def snapshot(db,repo=''):
    ensure(db);sid=source_id(db);tracks=[]
    for t in core.tracks(db):
        value={k:t.get(k) for k in ('id','title','artist','aliases','numbers','history_records','last_watch','frequency_score','base_score','followed','hidden','karaoke_good','karaoke_rating')}
        value['aliases']=value['aliases'] or [];value['numbers']=value['numbers'] or [];tracks.append(value)
    state=friends.status(db,repo);peer=[]
    for p in state['friends']:
        songs=friends.profiles(db,repo).get(p['login'],{}).get('songs',[]) if p['state']=='accepted' and p['share_songs'] else []
        peer.append({**p,'songs':songs})
    return {'format':FORMAT,'version':1,'source_id':sid,'created_at':datetime.now(timezone.utc).isoformat(),
            'tracks':tracks,'queue':song_identity.queue(db),'friends':peer,
            'friend_settings':state['settings'],'account':state['account'],
            'acknowledged_operations':[r[0] for r in db.execute('SELECT id FROM mobile_applied WHERE source_id=?',(sid,))]}

def validate(payload):
    if not isinstance(payload,dict) or set(payload)!={'format','version','source_id','device_id','operations'} or payload['format']!=OPERATIONS or payload['version']!=1:raise ValueError('모바일 변경 파일 형식을 확인하세요.')
    for key in ('source_id','device_id'):
        if not isinstance(payload[key],str) or not re.fullmatch(r'[a-f0-9]{32}',payload[key]):raise ValueError('모바일 파일 식별자 오류')
    if not isinstance(payload['operations'],list) or len(payload['operations'])>10000:raise ValueError('모바일 변경은 한 번에 10,000개까지 가져올 수 있어요.')
    for op in payload['operations']:
        if not isinstance(op,dict) or set(op)!={'id','kind','target','value'} or not isinstance(op['id'],str) or not re.fullmatch(r'[a-f0-9]{32}',op['id']):raise ValueError('변경 항목 형식 오류')
        kind=op['kind'];target=op['target'];value=op['value']
        if not isinstance(target,str) or not 1<=len(target)<=300:raise ValueError('변경 대상 오류')
        if kind=='rating':
            if type(value) is not int or value not in (-1,1):raise ValueError('평가 변경 값 오류')
        elif kind in ('queue','follow','friend'):
            if type(value) is not bool:raise ValueError('목록 변경 값 오류')
            if kind=='friend' and not friends.LOGIN.fullmatch(target):raise ValueError('친구 사용자명 오류')
        else:raise ValueError('지원하지 않는 모바일 변경')
    return payload

def apply(db,payload):
    validate(payload);ensure(db)
    if payload['source_id']!=source_id(db):raise ValueError('이 PC에서 내보낸 데이터의 변경 파일이 아니에요. 다른 사람의 파일인지 확인하세요.')
    tracks=core.tracks(db);ids={m:t['id'] for t in tracks for m in t.get('member_ids',[t['id']])}
    for t in tracks:ids[t['id']]=t['id']
    seen={r[0] for r in db.execute('SELECT id FROM mobile_applied')}
    result={'applied':0,'duplicates':0,'unresolved':[]}
    with db:
        for op in payload['operations']:
            if op['id'] in seen:result['duplicates']+=1;continue
            kind=op['kind'];target=op['target'];value=op['value']
            if kind in ('queue','rating') and target not in ids:
                result['unresolved'].append({'id':op['id'],'reason':'현재 PC 목록에 없는 곡'});continue
            if kind=='rating':
                ratings=core.get_state(db,'karaoke_ratings',{},'user_state');tid=ids[target];ratings[tid]=ratings.get(tid,0)+value;core.set_state(db,'karaoke_ratings',ratings,'user_state')
            elif kind=='queue':
                queue=song_identity.queue(db);tid=ids[target]
                queue=list(dict.fromkeys(queue+[tid])) if value else [i for i in queue if ids.get(i,i)!=tid]
                core.set_state(db,'queue',queue,'user_state')
            elif kind=='follow':
                target=core.canonical(target);values=core.get_state(db,'follows',[],'user_state')
                values=list(dict.fromkeys(values+[target])) if value else [a for a in values if core.canonical(a)!=target]
                core.set_state(db,'follows',values,'user_state')
            elif kind=='friend':
                state=friends.settings(db);target=target.lower()
                if target==core.get_state(db,'friends_account','').lower():raise ValueError('본인은 친구로 등록할 수 없어요.')
                state['friends']=list(dict.fromkeys(state['friends']+[target])) if value else [x for x in state['friends'] if x!=target]
                state['blocked']=[x for x in state['blocked'] if x!=target] if value else list(dict.fromkeys(state['blocked']+[target]))
                if len(state['friends'])>100 or len(state['blocked'])>100:raise ValueError('친구 목록은 100명까지 지원해요.')
                # Do not commit mid-import; the complete batch is transactional.
                core.set_state(db,'friends_settings',state,'user_state')
            db.execute('INSERT INTO mobile_applied VALUES (?,?,?)',(op['id'],payload['source_id'],time.time()));seen.add(op['id']);result['applied']+=1
    return result
