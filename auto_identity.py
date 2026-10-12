"""Continuous local identity reuse, grouped references, and bounded public lookup."""
import hashlib,json,re,threading,time
from collections import Counter,defaultdict
from concurrent.futures import ThreadPoolExecutor
import core,recognition,description_identity,pipeline,video_kind

VERSION='identity-graph-v1'
LOCK=threading.Lock()
def run(db,write_lock,fetch_limit=20):
    db.execute('CREATE TABLE IF NOT EXISTS identity_checks(id TEXT PRIMARY KEY,fingerprint TEXT,result TEXT)');db.commit()
    videos={r['id']:json.loads(r['data']) for r in db.execute('SELECT id,data FROM videos')}
    edits=core.get_state(db,'corrections',{},'user_state');watched={r[0] for r in db.execute('SELECT id FROM video_activity')}
    tracks=core.tracks(db);by_artist=defaultdict(dict);by_video=defaultdict(list)
    for t in tracks:
        for a in [t]+t.get('aliases',[]):by_artist[core.norm(recognition.artist_name(core.artist_base(a['artist'])))][t['id']]=t
        for vid in t['video_ids']:by_video[vid].append(t)
    targets=[];links={};owners=defaultdict(list)
    for vid in watched:
        v=videos[vid];c=v.get('classification',{})
        if vid in edits or c.get('status') in ('song','excluded','non_song'):continue
        kind=video_kind.get(v)['kind']
        refs=recognition.original_links(v.get('description',''))
        if kind in ('collection','music_explain'):continue
        if kind not in ('song','music_possible') and not refs:continue
        targets.append(vid);links[vid]=refs
        for ref in refs:owners[ref['video_id']].append(vid)
    now=time.time();missing=[]
    for vid in owners:
        v=videos.get(vid,{})
        if v.get('title') and v.get('channel') and v.get('metadata_status') not in ('error','unavailable'):continue
        if v.get('identity_reference_checked_at',0)<now-7*86400:missing.append(vid)
    missing.sort(key=lambda vid:-len(owners[vid]));fetched=0
    if fetch_limit and missing and core.get_state(db,'identity_lookup_backoff',0)<=now:
        with ThreadPoolExecutor(max_workers=4) as pool:
            results=list(pool.map(pipeline.metadata,missing[:fetch_limit]))
        with write_lock:
            if any(result.get('rate_limited') for result in results):core.set_state(db,'identity_lookup_backoff',now+3600)
            for result in results:
                vid=result['video_id'];v=core.video_data(db,vid) or {'video_id':vid};v.update(result);v['identity_reference_checked_at']=now
                v['classification']=core.classify(v,correction=edits.get(vid));core.save_video(db,v);videos[vid]=v;fetched+=1
            db.commit()
    # Resolve each referenced original once, then propagate through its edges.
    inferred={};saved=[]
    for _ in range(3):
        changed=False
        for vid in owners:
            v=videos.get(vid)
            if not v or vid in edits or v.get('classification',{}).get('status') in ('song','excluded','non_song'):continue
            native=core.classify(v)
            r={'status':'recognized','track':{**native,'confident':True}} if native.get('status')=='song' else recognition.recognize(v,lookup=videos.get)
            if r.get('status')=='recognized' and r.get('track',{}).get('confident'):
                inferred[vid]=r;v['classification']={'status':'song',**r['track'],'source':'auto_recognition'};changed=True
        if not changed:break
    knowledge=hashlib.sha256(json.dumps([(v,t.get('classification',{})) for v,t in sorted(videos.items()) if t.get('classification',{}).get('status')=='song'],sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    counts=Counter();cached=0;checks=[]
    for vid in targets:
        v=videos[vid];refs=links[vid]
        fp=hashlib.sha256((VERSION+knowledge+json.dumps({k:v.get(k) for k in ('title','history_title','channel','description','category','music_metadata')},sort_keys=True,ensure_ascii=False)).encode()).hexdigest()
        previous=db.execute('SELECT fingerprint,result FROM identity_checks WHERE id=?',(vid,)).fetchone()
        if previous and previous[0]==fp:counts[previous[1]]+=1;cached+=1;continue
        names=[v.get('channel') or v.get('history_channel','')]+[c['artist'] for c in v.get('music_metadata',{}).get('cards',[])]
        relevant={t['id']:t for name in names for t in by_artist.get(core.norm(recognition.artist_name(core.artist_base(name))),{}).values()}
        for ref in refs:
            for t in by_video.get(ref['video_id'],[]):relevant[t['id']]=t
        r=recognition.recognize(v,lookup=videos.get,tracks=list(relevant.values()))
        if r.get('status')=='recognized' and r.get('track',{}).get('confident'):
            inferred[vid]=r;stage='saved';saved.append({'video_id':vid,'title':r['track']['title'],'artist':r['track']['artist']})
        elif len(refs)>1:stage='multiple_references'
        elif refs and any(videos.get(ref['video_id'],{}).get('classification',{}).get('status')!='song' for ref in refs):stage='original_unidentified'
        elif r.get('candidates'):stage='identity_ambiguous'
        else:stage='no_identity_evidence'
        counts[stage]+=1;checks.append((vid,fp,stage))
    with write_lock:
        db.executemany('INSERT OR REPLACE INTO identity_checks VALUES (?,?,?)',checks)
        current=core.get_state(db,'corrections',{},'user_state')
        for vid,r in inferred.items():
            latest=core.video_data(db,vid)
            if vid in current or latest.get('classification',{}).get('status') in ('song','excluded','non_song'):continue
            current[vid]={**r['track'],'source':'auto_recognition','exclude':False};latest['classification']=core.classify(latest,correction=current[vid]);core.save_video(db,latest)
            r['saved']=True;db.execute('INSERT OR REPLACE INTO recognition_results VALUES (?,?)',(vid,json.dumps(r,ensure_ascii=False)))
        core.set_state(db,'corrections',current,'user_state');db.commit()
        if inferred:core.rebuild(db);db.commit()
        state={'status':'complete','checked':len(targets),'cached':cached,'saved':len(saved),'reference_resolved':len(inferred)-len(saved),'unique_references':len(owners),'shared_reference_groups':sum(len(x)>1 for x in owners.values()),'reference_fetched':fetched,'reference_pending':max(0,len(missing)-fetched),'reasons':dict(counts),'last_run':time.time(),'items':saved[:50]}
        old=core.get_state(db,'auto_identity_job',{});state['total_saved']=old.get('total_saved',0)+len(saved)
        core.set_state(db,'auto_identity_job',state);db.commit()
    return state
def start(write_lock,fetch_limit=20):
    if not LOCK.acquire(False):return False
    def work():
        db=core.connect()
        try:
            with write_lock:core.set_state(db,'auto_identity_job',{'status':'running','started_at':time.time(), 'total_saved':core.get_state(db,'auto_identity_job',{}).get('total_saved',0)});db.commit()
            run(db,write_lock,fetch_limit)
        except Exception as exc:
            db.rollback()
            with write_lock:core.set_state(db,'auto_identity_job',{'status':'error','reason':type(exc).__name__});db.commit()
        finally:db.close();LOCK.release()
    threading.Thread(target=work,daemon=True).start();return True
def scheduler(write_lock,busy):
    def loop():
        time.sleep(40)
        while True:
            if not busy():start(write_lock)
            time.sleep(180)
    threading.Thread(target=loop,daemon=True).start()
