"""Private GitHub exchange of confirmed identities. Never serialize watch events."""
import base64,hashlib,json,re,secrets,subprocess,threading,time,urllib.request,urllib.error,shutil
from pathlib import Path
import core
import shared_knowledge
import friends

FORMAT='next-song-classifications'
DEFAULT_REPO=''
SYNC_LOCK=threading.Lock()
AUTH_STATE={'status':'idle'}
AUTH_LOCK=threading.Lock()
WAKE=threading.Event()
def notify():WAKE.set()
RECORD_KEYS={'video_id','title','artist','aliases','numbers','evidence'}

def config_path():return core.ROOT/'data'/'github-sync.json'
def config():
    path=config_path()
    return json.loads(path.read_text(encoding='utf8')) if path.exists() else {'repo':DEFAULT_REPO,'enabled':False}
def public_config():
    c=config();return {'repo':c.get('repo',DEFAULT_REPO),'enabled':c.get('enabled',False),'has_token':bool(c.get('token')),'client_id':c.get('client_id','')}
def save_config(payload):
    c=config();repo=payload.get('repo',c.get('repo',DEFAULT_REPO)).strip()
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repo):raise ValueError('GitHub 저장소는 owner/name 형식으로 입력하세요.')
    c.update(repo=repo,enabled=bool(payload.get('enabled',False)),client_id=c.get('client_id') or secrets.token_hex(16))
    if payload.get('token'):c['token']=payload['token'].strip()
    if payload.get('remove_token'):c.pop('token',None)
    if len(c.get('token',''))>300:raise ValueError('GitHub 토큰 형식을 확인하세요.')
    path=config_path();path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(c),encoding='utf8');return public_config()
def credential(c):
    if c.get('token'):return c['token']
    try:
        p=subprocess.run([gh_executable(),'auth','token','--hostname','github.com'],stdin=subprocess.DEVNULL,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=8,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if p.returncode==0 and p.stdout.strip():return p.stdout.strip()
    except (OSError,subprocess.TimeoutExpired):pass
    raise ValueError('GitHub에 로그인하거나 이 비공개 저장소용 토큰을 설정하세요.')

def gh_executable():
    bundled=core.ROOT/'tools'/'gh.exe'
    if bundled.exists():return str(bundled)
    found=shutil.which('gh')
    if found:return found
    raise ValueError('GitHub CLI가 없습니다. Windows 실행 패키지를 사용하거나 GitHub CLI를 설치하세요.')

def start_login():
    if not AUTH_LOCK.acquire(blocking=False):return dict(AUTH_STATE)
    AUTH_STATE.clear();AUTH_STATE.update(status='starting',url='https://github.com/login/device')
    def work():
        timer=None
        try:
            # The packaged app has no interactive terminal for hidden gh prompts.
            # DEVNULL also supplies a valid stdin handle in Windows GUI launches.
            p=subprocess.Popen([gh_executable(),'auth','login','--hostname','github.com','--git-protocol','https','--web'],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            def timeout():
                if AUTH_STATE.get('status')=='starting' and p.poll() is None:
                    AUTH_STATE.update(status='error',reason='30초 안에 인증 코드를 받지 못했어요. 인터넷 연결·방화벽을 확인하고 다시 시도하세요.')
                    p.kill()
            timer=threading.Timer(30,timeout);timer.daemon=True;timer.start()
            buffer=''
            while True:
                char=p.stdout.read(1)
                if not char:break
                buffer=(buffer+char)[-1024:]
                plain=re.sub(r'\x1b\[[0-9;]*[A-Za-z]','',buffer)
                match=re.search(r'one-time code\s*[:(]\s*([A-Z0-9]{4}-[A-Z0-9]{4})(?![A-Z0-9])',plain,re.I)
                if match and AUTH_STATE.get('status')=='starting':
                    AUTH_STATE.update(status='awaiting_approval',code=match[1]);timer.cancel()
            if p.wait()==0:AUTH_STATE.clear();AUTH_STATE.update(status='complete')
            elif AUTH_STATE.get('status')!='error':
                reason='GitHub 인증이 완료되지 않았어요. 다시 시도하세요.'
                if 'git' in buffer.lower() and any(word in buffer.lower() for word in ('not found','cannot find','executable file')):reason='Git 실행 파일을 찾지 못했어요. Git for Windows 설치 후 앱을 다시 실행하세요.'
                elif any(word in buffer.lower() for word in ('certificate','x509')):reason='GitHub 인증 서버의 인증서를 확인하지 못했어요. PC 시간·네트워크 보안 설정을 확인하세요.'
                AUTH_STATE.update(status='error',reason=reason)
        except Exception as e:AUTH_STATE.update(status='error',reason=str(e) if isinstance(e,ValueError) else type(e).__name__)
        finally:
            if timer:timer.cancel()
            AUTH_LOCK.release()
    threading.Thread(target=work,daemon=True).start();return dict(AUTH_STATE)

def request(path,token,payload=None,missing_ok=False):
    data=json.dumps(payload).encode() if payload is not None else None
    req=urllib.request.Request('https://api.github.com'+path,data=data,method='PUT' if data is not None else 'GET',headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28','User-Agent':'NextSongLocal/1.0','Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(req,timeout=30) as response:return json.load(response)
    except urllib.error.HTTPError as e:
        if missing_ok and e.code==404:return None
        if e.code==404 and re.fullmatch(r'/repos/[^/]+/[^/]+',path):raise ValueError('GitHub 404 — 저장소 주소를 확인하고, 앱에 연결한 계정으로 비공개 저장소 초대를 수락하세요.') from None
        raise ValueError('GitHub HTTP '+str(e.code)+' — 저장소 접근 권한 또는 API 사용량을 확인하세요.') from None

def validate_record(r):
    if not isinstance(r,dict) or set(r)!=RECORD_KEYS:raise ValueError('공유 곡 정보 외의 항목은 허용하지 않습니다.')
    if not re.fullmatch(r'[A-Za-z0-9_-]{11}',r.get('video_id','')):raise ValueError('영상 ID 형식 오류')
    if any(not isinstance(r.get(k),str) or not 1<=len(r[k])<=300 for k in ('title','artist')):raise ValueError('곡명·가수 형식 오류')
    if r['evidence'] not in ('manual','verified_auto','native_music_metadata'):raise ValueError('분류 근거 형식 오류')
    if not isinstance(r['aliases'],list) or len(r['aliases'])>50:raise ValueError('별칭 형식 오류')
    for a in r['aliases']:
        if not isinstance(a,dict) or set(a)!={'title','artist'} or any(not isinstance(a[k],str) or not 1<=len(a[k])<=300 for k in a):raise ValueError('별칭 형식 오류')
    if not isinstance(r['numbers'],list) or len(r['numbers'])>100:raise ValueError('곡 번호 형식 오류')
    for n in r['numbers']:
        if not isinstance(n,dict) or set(n)!={'brand','no'} or n['brand'] not in ('tj','kumyoung') or not isinstance(n['no'],str) or not re.fullmatch(r'\d{1,8}',n['no']):raise ValueError('곡 번호 형식 오류')
    return r

def export_records(db):
    edits=core.get_state(db,'corrections',{},'user_state')
    results={r['id']:json.loads(r['data']) for r in db.execute('SELECT * FROM recognition_results')}
    numbers={v:t['numbers'] for t in core.tracks(db) for v in t['video_ids']}
    records=[]
    for row in db.execute('SELECT id,data FROM videos'):
        if row['id'].startswith('spotify:'):continue
        v=json.loads(row['data']);c=v.get('classification',{});vid=row['id']
        if c.get('status')!='song' or c.get('source')=='shared':continue
        edit=edits.get(vid);result=results.get(vid,{});t=result.get('track',{})
        if edit and not edit.get('exclude') and edit.get('source')!='auto_recognition':evidence='manual'
        elif c.get('source') in ('library','topic','auto_generated'):evidence='native_music_metadata'
        elif c.get('source')=='auto_recognition' and (edit or {}).get('confident') is True:evidence='verified_auto'
        elif result.get('status')=='recognized' and t.get('confident') is True and core.norm(t.get('title',''))==core.norm(c['title']) and core.norm(t.get('artist',''))==core.norm(c['artist']):evidence='verified_auto'
        else:continue
        import video_kind
        purpose=video_kind.get(v)
        if evidence!='manual' and (purpose['kind'] in ('collection','music_explain') or (purpose['kind']=='activity' and not purpose.get('has_music_cue'))):continue
        raw=v.get('title') or v.get('history_title','')
        if evidence!='manual' and re.search(r'(?i)歌枠|雑談|medley|メドレー|playlist|作業用|耐久|\blive\b|minecraft|マイクラ',raw):continue
        # Repeated author/lyricist credits in a Topic description are not a performer name.
        artist=core.canonical(c['artist'])
        if evidence=='native_music_metadata' and ' · ' in artist:
            channel=v.get('channel') or v.get('history_channel','')
            if channel.endswith(' - Topic'):artist=core.canonical(channel[:-8])
            else:continue
        record={'video_id':vid,'title':c['title'],'artist':artist,'aliases':[],'numbers':[],'evidence':evidence}
        for a in (edit or {}).get('alternate_labels',[]):
            if isinstance(a,dict) and a.get('title') and a.get('artist') and len(a['title'])<=300 and len(a['artist'])<=300:
                pair={'title':a['title'],'artist':a['artist']}
                if pair not in record['aliases']:record['aliases'].append(pair)
        record['aliases']=record['aliases'][:50]
        record['numbers']=list({(n['brand'],str(n['no'])):{'brand':n['brand'],'no':str(n['no'])} for n in numbers.get(vid,[]) if n.get('brand') in ('tj','kumyoung') and str(n.get('no','')).isdigit()}.values())[:100]
        try:validate_record(record)
        except ValueError:continue
        records.append(record)
    return sorted(records,key=lambda r:r['video_id'])

def documents(records,client_id):
    shards={f'{i:x}':[] for i in range(16)}
    for r in records:shards[hashlib.sha256(r['video_id'].encode()).hexdigest()[0]].append(r)
    return {f'classifications/{client_id}/{s}.json':{'format':FORMAT,'version':1,'client_id':client_id,'records':items} for s,items in shards.items()}

def validate_document(path,doc):
    m=re.fullmatch(r'classifications/([a-f0-9]{32})/[a-f0-9]\.json',path)
    if not m or not isinstance(doc,dict) or set(doc)!={'format','version','client_id','records'} or doc.get('format')!=FORMAT or doc.get('version')!=1 or doc.get('client_id')!=m[1]:raise ValueError('공유 파일 형식 오류')
    if not isinstance(doc['records'],list) or len(doc['records'])>10000:raise ValueError('공유 파일 크기 오류')
    ids=set()
    for r in doc['records']:
        validate_record(r)
        if r['video_id'] in ids:raise ValueError('중복 영상 ID')
        ids.add(r['video_id'])
    return doc['records']

def apply_shared(db,write_lock):
    from collections import defaultdict
    shared_knowledge.ensure(db)
    graph_counts=defaultdict(int)
    for row in db.execute('SELECT path FROM shared_knowledge'):
        graph_counts[row[0].split('/')[1].split('-')[0]]+=1
    grouped=defaultdict(list)
    for row in db.execute('SELECT path,data FROM shared_records'):
        if row[0].startswith('classifications/') and graph_counts.get(row[0].split('/')[1],0)==16:continue
        item=json.loads(row[1]);grouped[item['video_id']].append(item)
    accepted={};conflicts={}
    pair=lambda r:(core.norm(r['title']),core.norm(core.number_artist(r['artist'])))
    for vid,items in grouped.items():
        groups=[]
        for r in items:
            keys={pair(a) for a in [r]+r['aliases']};matches=[g for g in groups if g.intersection(keys)]
            for g in matches:keys.update(g);groups.remove(g)
            groups.append(keys)
        if len(groups)!=1:conflicts[vid]=items;continue
        preferred=next((r for r in items if r['evidence']=='manual'),items[0])
        value={**preferred,'aliases':[],'numbers':[]}
        for r in items:
            label={'title':r['title'],'artist':r['artist']}
            if label not in value['aliases']:value['aliases'].append(label)
            for key in ('aliases','numbers'):
                for x in r[key]:
                    if x not in value[key]:value[key].append(x)
        accepted[vid]=value
    with write_lock:
        before={r[0]:r[1] for r in db.execute("SELECT v.id,json_extract(v.data,'$.classification.title')||'|'||json_extract(v.data,'$.classification.artist') FROM videos v JOIN video_activity a ON a.id=v.id WHERE json_extract(v.data,'$.classification.source')='shared'")}
        db.execute('DELETE FROM shared_identities');db.execute('DELETE FROM shared_conflicts')
        db.execute("DELETE FROM catalogue WHERE json_extract(data,'$.source')='shared'")
        for row in db.execute('SELECT data FROM shared_knowledge').fetchall():
            for song in json.loads(row[0])['songs']:
                for n in song['numbers']:
                    entry={'brand':n['brand'],'no':n['no'],'title':song['title'],'singer':song['artist'],'source':'shared','release':''}
                    db.execute('INSERT OR IGNORE INTO catalogue VALUES (?,?,?)',(n['brand'],n['no'],json.dumps(entry,ensure_ascii=False)))
        for vid,r in accepted.items():
            local=core.video_data(db,vid);c=local.get('classification',{}) if local else {}
            if c.get('status')=='song' and c.get('source')!='shared' and pair(c) not in {pair(a) for a in [r]+r['aliases']}:
                conflicts[vid]=[r,{'title':c['title'],'artist':c['artist'],'local':True}];continue
            db.execute('INSERT INTO shared_identities VALUES (?,?)',(vid,json.dumps(r,ensure_ascii=False)))
            for n in r['numbers']:
                row={'brand':n['brand'],'no':n['no'],'title':r['title'],'singer':r['artist'],'source':'shared','release':''}
                db.execute('INSERT OR IGNORE INTO catalogue VALUES (?,?,?)',(n['brand'],n['no'],json.dumps(row,ensure_ascii=False)))
        for vid,values in conflicts.items():db.execute('INSERT INTO shared_conflicts VALUES (?,?)',(vid,json.dumps(values,ensure_ascii=False)))
        db.commit();core.rebuild(db)
        after={};methods=defaultdict(int)
        for row in db.execute("SELECT v.id,json_extract(v.data,'$.classification.title')||'|'||json_extract(v.data,'$.classification.artist'),json_extract(v.data,'$.classification.shared_basis') FROM videos v JOIN video_activity a ON a.id=v.id WHERE json_extract(v.data,'$.classification.source')='shared'"):
            after[row[0]]=row[1];methods[row[2] or 'video_id']+=1
    edits=core.get_state(db,'corrections',{},'user_state')
    return {'shared_identities':db.execute('SELECT COUNT(*) FROM shared_identities').fetchone()[0],'conflicts':len(conflicts),'applied_to_watched':len(after),'new_connections':len(set(after)-set(before)),'updated_connections':sum(before[k]!=after[k] for k in set(before)&set(after)),'withdrawn_connections':len(set(before)-set(after)),'connection_methods':dict(methods),'protected_manual':sum(vid in edits and edits[vid].get('source')!='auto_recognition' for vid in accepted)}

def sync(db,write_lock):
    shared_knowledge.ensure(db)
    c=config()
    if not c.get('enabled'):raise ValueError('분류 공유를 먼저 켜 주세요.')
    token=credential(c);repo=c['repo'];meta=request('/repos/'+repo,token)
    if not meta.get('private'):raise ValueError('분류 데이터는 비공개 GitHub 저장소에만 올릴 수 있습니다.')
    if core.get_state(db,'github_sync_repo','')!=repo:
        with write_lock:
            db.execute('DELETE FROM shared_records');db.execute('DELETE FROM shared_identities');db.execute('DELETE FROM shared_conflicts')
            db.execute('DELETE FROM shared_knowledge')
            core.set_state(db,'github_sync_blobs',{});core.set_state(db,'github_sync_published',{});core.set_state(db,'github_sync_repo',repo);db.commit()
    state={'status':'running','downloaded_files':0,'uploaded_files':0,'repo':repo,'started_at':time.time()}
    with write_lock:core.set_state(db,'github_sync_job',state);db.commit()
    tree=request('/repos/'+repo+'/git/trees/'+meta['default_branch']+'?recursive=1',token)
    if tree.get('truncated'):raise ValueError('공유 저장소 파일 목록이 너무 큽니다.')
    cache=core.get_state(db,'github_sync_blobs',{});remote={x['path']:x['sha'] for x in tree.get('tree',[]) if re.fullmatch(r'classifications/[a-f0-9]{32}/[a-f0-9]\.json|knowledge/[a-f0-9]{32}-[a-f0-9]\.json',x.get('path',''))}
    for path,sha in remote.items():
        if path.startswith('classifications/'+c['client_id']+'/') or path.startswith('knowledge/'+c['client_id']+'-'):
            with write_lock:
                db.execute('DELETE FROM shared_records WHERE path=?',(path,));cache[path]=sha;core.set_state(db,'github_sync_blobs',cache);db.commit()
                db.execute('DELETE FROM shared_knowledge WHERE path=?',(path,));db.commit()
            continue
        if cache.get(path)==sha:continue
        blob=request('/repos/'+repo+'/git/blobs/'+sha,token)
        if blob.get('size',0)>3*1024*1024:raise ValueError('공유 파일 크기 제한 초과')
        doc=json.loads(base64.b64decode(blob['content']))
        graph=path.startswith('knowledge/')
        records=shared_knowledge.records(shared_knowledge.validate(path,doc)) if graph else validate_document(path,doc)
        with write_lock:
            db.execute('DELETE FROM shared_records WHERE path=?',(path,))
            if graph:db.execute('INSERT OR REPLACE INTO shared_knowledge VALUES (?,?)',(path,json.dumps(doc,ensure_ascii=False)))
            for r in records:db.execute('INSERT INTO shared_records VALUES (?,?,?)',(path,r['video_id'],json.dumps(r,ensure_ascii=False)))
            cache[path]=sha;core.set_state(db,'github_sync_blobs',cache);db.commit()
        state['downloaded_files']+=1
    with write_lock:
        for path in set(cache)-set(remote):
            db.execute('DELETE FROM shared_records WHERE path=?',(path,));db.execute('DELETE FROM shared_knowledge WHERE path=?',(path,));cache.pop(path,None)
        core.set_state(db,'github_sync_blobs',cache);db.commit()
    applied=apply_shared(db,write_lock)
    own=export_records(db);uploads=documents(own,c['client_id']);uploads.update(shared_knowledge.documents(db,own,c['client_id']));published=core.get_state(db,'github_sync_published',{})
    for path,doc in uploads.items():
        current=config()
        if not current.get('enabled') or current.get('repo')!=repo:
            state['status']='stopped';break
        raw=json.dumps(doc,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode();digest=hashlib.sha256(raw).hexdigest()
        if published.get(path)==digest and path in remote:continue
        previous=request('/repos/'+repo+'/contents/'+path,token,missing_ok=True)
        payload={'message':'Update confirmed song classifications','content':base64.b64encode(raw).decode(),'branch':meta['default_branch']}
        if previous:payload['sha']=previous['sha']
        request('/repos/'+repo+'/contents/'+path,token,payload);published[path]=digest;state['uploaded_files']+=1
        with write_lock:core.set_state(db,'github_sync_published',published);db.commit()
    if state['status']!='stopped':
        try:state['friends']=friends.sync(db,write_lock,c,meta,tree,token,request)
        except Exception as error:
            note={'status':'error','reason':str(error) if isinstance(error,ValueError) else type(error).__name__}
            state['friends']=note
            with write_lock:core.set_state(db,'friends_job',note);db.commit()
    state.update(status='stopped' if state['status']=='stopped' else 'complete',exported_records=len(own),finished_at=time.time(),**applied)
    with write_lock:core.set_state(db,'github_sync_job',state);db.commit()
    return state

def start(write_lock):
    if not SYNC_LOCK.acquire(blocking=False):return False
    initial=core.connect()
    with write_lock:core.set_state(initial,'github_sync_job',{'status':'running','started_at':time.time()});initial.commit()
    initial.close()
    def work():
        db=core.connect()
        try:sync(db,write_lock)
        except Exception as e:
            # Never include credential values or request objects in diagnostics.
            reason=str(e) if isinstance(e,ValueError) else type(e).__name__
            with write_lock:core.set_state(db,'github_sync_job',{'status':'error','reason':reason[:300],'finished_at':time.time()});db.commit()
        finally:db.close();SYNC_LOCK.release()
    threading.Thread(target=work,daemon=True).start();return True

def scheduler(write_lock):
    def work():
        while True:
            if config().get('enabled'):start(write_lock)
            WAKE.wait(300);WAKE.clear()
            # Coalesce consecutive song saves without delaying local responses.
            time.sleep(8)
    threading.Thread(target=work,daemon=True).start()
