"""Opt-in social song shelves on the existing private GitHub exchange.

Friendship controls app presentation, not repository access: all collaborators
can read shared shelves. Never export history, play counts, dates or video IDs.
"""
import base64,hashlib,json,math,re,time
import core

FORMAT='next-song-friends'
LOGIN=re.compile(r'^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$')
PATH=re.compile(r'^social/([a-f0-9]{32})\.json$')

def ensure(db):
    db.execute('CREATE TABLE IF NOT EXISTS friend_profiles(repo TEXT,path TEXT,sha TEXT,data TEXT,PRIMARY KEY(repo,path))')

def settings(db):
    return {**{'friends':[],'blocked':[],'share_songs':False,'display_name':''},**core.get_state(db,'friends_settings',{},'user_state')}

def save_settings(db,payload):
    old=settings(db)
    names=payload.get('friends',old['friends'])
    if not isinstance(names,list) or len(names)>100:raise ValueError('친구는 최대 100명까지 등록할 수 있어요.')
    if any(not isinstance(x,str) or not LOGIN.fullmatch(x.strip()) for x in names):raise ValueError('GitHub 사용자명을 입력하세요. URL·이메일은 사용할 수 없어요.')
    names=list(dict.fromkeys(x.strip().lower() for x in names))
    login=core.get_state(db,'friends_account','')
    if login.lower() in names:raise ValueError('본인 계정은 친구로 추가할 수 없어요.')
    display=payload.get('display_name',old['display_name'])
    if not isinstance(display,str) or len(display)>80:raise ValueError('표시 이름은 80자 이내로 입력하세요.')
    blocked=payload.get('blocked',old['blocked'])
    if not isinstance(blocked,list) or len(blocked)>100 or any(not isinstance(x,str) or not LOGIN.fullmatch(x) for x in blocked):raise ValueError('친구 제외 목록 오류')
    value={'friends':names,'blocked':list(dict.fromkeys(x.lower() for x in blocked if x.lower() not in names)),
           'share_songs':bool(payload.get('share_songs',old['share_songs'])),'display_name':display.strip()}
    core.set_state(db,'friends_settings',value,'user_state');db.commit()
    return value

def shelf(tracks):
    result=[]
    for track in tracks:
        title,artist=track.get('title',''),track.get('artist','')
        if not title or not artist:continue
        aliases=[{'title':a['title'],'artist':a['artist']} for a in track.get('aliases',[]) if a.get('title') and a.get('artist')][:50]
        numbers=[{'brand':n['brand'],'no':str(n['no'])} for n in track.get('numbers',[]) if n.get('brand') in ('tj','kumyoung','dam','joysound') and re.fullmatch(r'\d{1,8}(?:-\d{1,3})?',str(n.get('no','')))][:100]
        result.append({'title':title,'artist':artist,'aliases':aliases,'numbers':numbers})
    return sorted(result,key=lambda s:(s['artist'],s['title']))[:10000]

def document(db,client,login,tracks=None):
    value=settings(db)
    return {'format':FORMAT,'version':1,'client_id':client,'login':login.lower(),'display_name':value['display_name'],
            'friends':value['friends'],'share_songs':value['share_songs'],
            'songs':shelf(core.tracks(db) if tracks is None else tracks) if value['share_songs'] else []}

def validate(path,doc):
    match=PATH.fullmatch(path)
    expected={'format','version','client_id','login','display_name','friends','share_songs','songs'}
    if not match or not isinstance(doc,dict) or set(doc)!=expected or doc['format']!=FORMAT or doc['version']!=1 or doc['client_id']!=match[1]:raise ValueError('친구 공유 형식 오류')
    if not isinstance(doc['login'],str) or not LOGIN.fullmatch(doc['login']):raise ValueError('친구 계정 형식 오류')
    if not isinstance(doc['display_name'],str) or len(doc['display_name'])>80:raise ValueError('친구 표시 이름 오류')
    if not isinstance(doc['friends'],list) or len(doc['friends'])>100 or any(not isinstance(x,str) or not LOGIN.fullmatch(x) for x in doc['friends']):raise ValueError('친구 목록 오류')
    if not isinstance(doc['share_songs'],bool) or not isinstance(doc['songs'],list) or len(doc['songs'])>10000 or (not doc['share_songs'] and doc['songs']):raise ValueError('친구 곡 목록 오류')
    for song in doc['songs']:
        if not isinstance(song,dict) or set(song)!={'title','artist','aliases','numbers'}:raise ValueError('곡 정보 외의 항목은 공유할 수 없어요.')
        def pair(a):return isinstance(a,dict) and set(a)=={'title','artist'} and all(isinstance(a[k],str) and 1<=len(a[k])<=300 for k in a)
        if not pair({k:song[k] for k in ('title','artist')}) or not isinstance(song['aliases'],list) or len(song['aliases'])>50 or any(not pair(a) for a in song['aliases']):raise ValueError('공유 곡명 오류')
        if not isinstance(song['numbers'],list) or len(song['numbers'])>100:raise ValueError('공유 번호 오류')
        for n in song['numbers']:
            if not isinstance(n,dict) or set(n)!={'brand','no'} or n['brand'] not in ('tj','kumyoung','dam','joysound') or not isinstance(n['no'],str) or not re.fullmatch(r'\d{1,8}(?:-\d{1,3})?',n['no']):raise ValueError('공유 번호 오류')
    return doc

def sync(db,write_lock,c,meta,tree,token,request):
    ensure(db)
    if not meta.get('private'):raise ValueError('친구 곡 목록은 비공개 저장소에서만 공유할 수 있어요.')
    local=settings(db)
    account=request('/user',token)['login'].lower()
    if not LOGIN.fullmatch(account):raise ValueError('GitHub 계정을 확인하지 못했어요.')
    repo=c['repo'];own_path='social/'+c['client_id']+'.json'
    remote={x['path']:x['sha'] for x in tree.get('tree',[]) if PATH.fullmatch(x.get('path',''))}
    if len(remote)>500:raise ValueError('친구 공유 파일이 너무 많아요.')
    for path,sha in remote.items():
        if path==own_path:continue
        cached=db.execute('SELECT sha FROM friend_profiles WHERE repo=? AND path=?',(repo,path)).fetchone()
        if cached and cached[0]==sha:continue
        blob=request('/repos/'+repo+'/git/blobs/'+sha,token)
        if blob.get('size',0)>6*1024*1024:raise ValueError('친구 곡 목록 크기 제한 초과')
        doc=validate(path,json.loads(base64.b64decode(blob['content'])))
        with write_lock:
            db.execute('INSERT OR REPLACE INTO friend_profiles VALUES (?,?,?,?)',(repo,path,sha,json.dumps(doc,ensure_ascii=False)));db.commit()
    with write_lock:
        for (path,) in db.execute('SELECT path FROM friend_profiles WHERE repo=?',(repo,)).fetchall():
            if path not in remote:db.execute('DELETE FROM friend_profiles WHERE repo=? AND path=?',(repo,path))
        core.set_state(db,'friends_account',account);db.commit()
    # Re-read settings after downloads so a concurrent privacy change wins.
    doc=document(db,c['client_id'],account)
    raw=json.dumps(doc,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
    digest=hashlib.sha256(raw).hexdigest()
    marker=core.get_state(db,'friends_published',{})
    uploaded=False
    should_publish=bool(settings(db)['friends'] or settings(db)['share_songs'] or marker)
    if should_publish and (marker!={'repo':repo,'digest':digest} or own_path not in remote):
        old=request('/repos/'+repo+'/contents/'+own_path,token,missing_ok=True)
        payload={'message':'Update opt-in friend song shelf','content':base64.b64encode(raw).decode(),'branch':meta['default_branch']}
        if old:payload['sha']=old['sha']
        request('/repos/'+repo+'/contents/'+own_path,token,payload)
        with write_lock:core.set_state(db,'friends_published',{'repo':repo,'digest':digest});db.commit()
        uploaded=True
    result={'status':'complete','account':account,'uploaded':uploaded,'shared_songs':len(doc['songs']),'finished_at':time.time()}
    with write_lock:core.set_state(db,'friends_job',result);db.commit()
    return result

def profiles(db,repo):
    ensure(db)
    grouped={}
    for (raw,) in db.execute('SELECT data FROM friend_profiles WHERE repo=? ORDER BY path',(repo,)):
        doc=json.loads(raw);key=doc['login'].lower()
        if key not in grouped:grouped[key]=doc
        else:
            old=grouped[key]
            # Privacy withdrawal on any device wins over stale copies.
            old['friends']=list(set(old['friends'])&set(doc['friends']))
            old['share_songs']=old['share_songs'] and doc['share_songs']
            old['songs']=list({(s['title'],s['artist']):s for s in old['songs']+doc['songs']}.values()) if old['share_songs'] else []
    return grouped

def status(db,repo):
    local=settings(db);account=core.get_state(db,'friends_account','').lower();people=profiles(db,repo)
    all_names=set(local['friends'])|{name for name,p in people.items() if account and account in [x.lower() for x in p['friends']]}
    items=[]
    for name in sorted(all_names):
        if name in local['blocked']:continue
        profile=people.get(name)
        outgoing=name in local['friends'];incoming=bool(profile and account and account in [x.lower() for x in profile['friends']])
        state='accepted' if outgoing and incoming else 'incoming' if incoming else 'pending'
        # A shelf appears in the app only after both sides have added each other.
        items.append({'login':name,'display_name':profile['display_name'] if profile else '', 'state':state,
                      'share_songs':bool(profile and profile['share_songs'] and state=='accepted'),
                      'song_count':len(profile['songs']) if profile and state=='accepted' and profile['share_songs'] else 0})
    return {'settings':local,'account':account,'friends':items,'job':core.get_state(db,'friends_job',{'status':'idle'}),
            'repo':repo,'repository_readable':True}

def song_keys(song):
    return {(core.norm(a['title']),core.norm(core.number_artist(a['artist']))) for a in [song]+song.get('aliases',[]) if a.get('title') and a.get('artist')}

def common(local,remote):
    from recommendation import number_key
    by_label={};by_number={}
    for song in remote:
        for key in song_keys(song):by_label.setdefault(key,[]).append(song)
        for n in song.get('numbers',[]):by_number.setdefault(number_key(n),[]).append(song)
    out=[]
    for track in local:
        candidates={}
        for key in song_keys(track):
            for song in by_label.get(key,[]):candidates[(song['title'],song['artist'])]=(song,'곡명·아티스트 또는 별칭 일치')
        for n in track.get('numbers',[]):
            for song in by_number.get(number_key(n),[]):
                candidates.setdefault((song['title'],song['artist']),(song,'노래방 번호 일치'))
        if not candidates:continue
        song,basis=next(iter(candidates.values()))
        numbers={(n['brand'],str(n['no'])):n for n in track.get('numbers',[])}
        common_numbers=[n for n in song['numbers'] if (n['brand'],n['no']) in numbers]
        out.append({'local_id':track.get('id'),'title':track['title'],'artist':track['artist'],'friend_title':song['title'],
                    'friend_artist':song['artist'],'numbers':track.get('numbers',[]),'common_numbers':common_numbers,'basis':basis,
                    'score':round(math.log1p(max(0,track.get('history_records',0)))+5*len(common_numbers),3)})
    return sorted(out,key=lambda s:(-s['score'],s['title']))

def listing(db,repo,login,query='',offset=0,limit=50):
    name=login.lower();state=status(db,repo)
    entry=next((p for p in state['friends'] if p['login']==name),None)
    if not entry or entry['state']!='accepted':raise ValueError('서로 친구로 등록하고 동기화한 뒤 볼 수 있어요.')
    if not entry['share_songs']:return {'songs':[],'common':[],'total':0,'reason':'친구가 곡 목록 공유를 켜지 않았어요.'}
    import recommendation
    songs=recommendation.group_tracks(profiles(db,repo)[name]['songs']);shared=common(core.tracks(db),songs)
    if query:songs=[s for s in songs if query.casefold() in (s['title']+' '+s['artist']).casefold()]
    return {'songs':songs[offset:offset+limit],'total':len(songs),'common':shared,'reason':''}
