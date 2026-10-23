"""Non-destructive number groups and private number-reveal recommendation signals."""
import copy,hashlib,json,math,re,time

def number_key(n):
    brand=n.get('brand');no=str(n.get('no',''))
    if brand not in ('tj','kumyoung','dam','joysound') or not re.fullmatch(r'\d{1,8}(?:-\d{1,3})?',no):return None
    return brand+':'+(no.replace('-','').lstrip('0') or '0')

def group_tracks(items,rejections=()):
    import song_identity
    groups=[];index={}
    for original in items:
        t=copy.deepcopy(original);t.setdefault('id',hashlib.sha256((t['title']+'|'+t['artist']).encode()).hexdigest()[:20]);t.setdefault('member_ids',[t['id']]);t.setdefault('aliases',[])
        keys={number_key(n) for n in t.get('numbers',[]) if number_key(n)}
        options=sorted({id(g):g for key in keys for g in index.get(key,[])}.values(),key=lambda g:g['id'])
        target=None
        for candidate in options:
            if song_identity.marked_different(t,candidate,list(rejections)):continue
            if target is None:target=candidate;continue
            if song_identity.marked_different(target,candidate,list(rejections)):continue
            combine(target,candidate);groups.remove(candidate)
            for values in index.values():
                if candidate in values:values.remove(candidate)
        if target is None:target=t;groups.append(t)
        else:combine(target,t)
        for n in target.get('numbers',[]):
            key=number_key(n)
            if key and target not in index.setdefault(key,[]):index[key].append(target)
    return groups

def combine(a,b):
    aid,bid=a['id'],b['id'];members=list(dict.fromkeys(a.get('member_ids',[aid])+b.get('member_ids',[bid])))
    aliases=[{'title':t['title'],'artist':t['artist']} for t in (a,b)]+a.get('aliases',[])+b.get('aliases',[])
    a['aliases']=list({(t['title'],t['artist']):t for t in aliases}.values());a['member_ids']=members;a['id']=min(aid,bid)
    for key in ('video_ids','sources'):
        if key in a or key in b:a[key]=list(dict.fromkeys(a.get(key,[])+b.get(key,[])))
    a['numbers']=list({number_key(n):n for n in b.get('numbers',[])+a.get('numbers',[]) if number_key(n)}.values())
    a['match_candidates']=list({number_key(n):n for n in b.get('match_candidates',[])+a.get('match_candidates',[]) if number_key(n)}.values())
    a['history_records']=a.get('history_records',0)+b.get('history_records',0)
    a['last_watch']=max(a.get('last_watch',''),b.get('last_watch',''))
    for key in ('frequency_score','recency_score','base_score'):a[key]=max(a.get(key,0),b.get(key,0))
    for key in ('followed','karaoke_good','hidden'):a[key]=bool(a.get(key) or b.get(key))
    for key in ('karaoke_rating','number_open_count'):a[key]=a.get(key,0)+b.get(key,0)
    a['last_number_open']=max(a.get('last_number_open',0),b.get('last_number_open',0))
    a['number_group_size']=len(members)

def boost(count):return min(.15,.035*math.log1p(max(0,count)))

def record_open(db,tid,event_id,opened_at=None,track=None):
    import core
    if not isinstance(event_id,str) or not re.fullmatch(r'[a-f0-9]{32}',event_id):raise ValueError('번호 확인 기록 식별자 오류')
    now=time.time();at=now if opened_at is None else opened_at
    if type(at) not in (int,float) or not math.isfinite(at) or at<now-366*86400 or at>now+300:raise ValueError('번호 확인 시각 오류')
    t=track or next((t for t in core.tracks(db) if tid in t.get('member_ids',[t['id']]) or tid==t['id']),None)
    if not t or not t.get('numbers'):raise ValueError('확인할 노래방 번호가 없어요.')
    db.execute('CREATE TABLE IF NOT EXISTS number_open_receipts(id TEXT PRIMARY KEY,track_id TEXT,opened_at REAL)')
    if db.execute('SELECT 1 FROM number_open_receipts WHERE id=?',(event_id,)).fetchone():return {'recorded':False,'duplicate':True}
    data=core.get_state(db,'number_opens',{},'user_state');members=t.get('member_ids',[t['id']]);last=max([data.get(m,{}).get('last_opened',0) for m in members]+[0])
    accepted=at-last>=1800
    if accepted:
        entry=data.get(t['id'],{'count':0,'last_opened':0});entry['count']+=1;entry['last_opened']=at;data[t['id']]=entry;core.set_state(db,'number_opens',data,'user_state')
    db.execute('INSERT INTO number_open_receipts VALUES (?,?,?)',(event_id,t['id'],at))
    return {'recorded':accepted,'duplicate':False}
