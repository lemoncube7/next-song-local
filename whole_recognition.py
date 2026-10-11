"""Resumable whole-history scan: cheap pass first, then queued public metadata."""
import json,re,time
from collections import defaultdict
import core,recognition,bulk_recognition,original_metadata,music_metadata,song_databases,pipeline,non_song

VERSION='whole-metadata-v1'

def references(db,video,write_lock):
    ids=[x['video_id'] for x in recognition.original_links(video.get('description',''))]
    ids.extend(c['video_id'] for c in video.get('music_metadata',{}).get('cards',[]) if c.get('video_id'))
    for vid in list(dict.fromkeys(ids))[:3]:
        if vid==video['video_id']:continue
        old=core.video_data(db,vid) or {'video_id':vid}
        if old.get('title') and old.get('channel') and old.get('metadata_status')=='ok':continue
        if old.get('original_public_checked_at',0)>time.time()-7*86400:continue
        found=pipeline.metadata(vid)
        with write_lock:
            latest=core.video_data(db,vid) or {'video_id':vid}
            latest.update(found);latest['original_public_checked_at']=time.time()
            latest['classification']=core.classify(latest,correction=core.get_state(db,'corrections',{},'user_state').get(vid))
            core.save_video(db,latest);db.commit()

def potential(video,result):
    if non_song.valid(video):return False
    raw=video.get('title') or video.get('history_title','')
    return (video.get('metadata_status')=='pending' or video.get('classification',{}).get('status')=='review' or
            bulk_recognition.music_evidence(video,result) or
            bool(re.search(non_song.MUSIC,raw)) or
            bool(re.search(r'(?i)歌ってみた|cover|커버|가사|lyrics|lyric video|歌詞|remix|ピアノ|piano|\bfeat\.|\bft\.',raw)))

def resolve(video,result):
    if result['status']=='recognized':return result
    raw=video.get('title') or video.get('history_title','')
    explicit=[]
    q=re.findall(r'[「『]([^」』]+)[」』]',raw)
    for text in q+[raw]:
        split=re.split(r'\s*[/／]\s*',text,maxsplit=1)
        if len(split)==2:
            artist=re.split(r'(?i)\s+feat\.|\s+covered|\s+cover|\s*\(',split[1])[0].strip()
            explicit.append((split[0].strip(),artist))
    m=re.match(r'^(.+?)\s+-\s+(.+)$',raw)
    if m:
        artist=m[1].split('&')[0].strip();title=re.split(r'\s*[/／]\s*|\s+-\s+',m[2])[0]
        explicit.append((title.strip(),artist))
    matches=[]
    for c in result.get('candidates',[]):
        if c.get('music_card') and music_metadata.risky_video(video):continue
        if any(core.norm(core.catalogue_title(c['title']))==core.norm(t) and core.norm(core.number_artist(c['artist']))==core.norm(core.number_artist(a)) for t,a in explicit):
            matches.append(c)
    matches=recognition.merge_candidates(matches)
    if len(matches)==1:
        c={**matches[0],'confident':True,'reason':'음악 DB 후보의 곡명·원곡 아티스트가 영상의 명시된 표기와 함께 일치'}
        return {**result,'status':'recognized','track':c,'candidates':[c]}
    return result

def run(db,load_key,write_lock,stop):
    db.execute('CREATE TABLE IF NOT EXISTS whole_scan_tasks (id TEXT PRIMARY KEY, version TEXT, stage TEXT, data TEXT)');db.commit()
    db.execute('CREATE INDEX IF NOT EXISTS whole_scan_stage ON whole_scan_tasks(version,stage)');db.commit()
    videos={r['id']:json.loads(r['data']) for r in db.execute('SELECT id,data FROM videos')}
    history={r['video_id']:r['n'] for r in db.execute('SELECT video_id,COUNT(*) n FROM events WHERE video_id IS NOT NULL GROUP BY video_id')}
    edits=core.get_state(db,'corrections',{},'user_state')
    targets=[v for v in history if v in videos and v not in edits and videos[v].get('classification',{}).get('status') not in ('song','excluded','non_song')]
    with write_lock:
        for vid in targets:db.execute('INSERT INTO whole_scan_tasks VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE SET version=excluded.version,stage=excluded.stage,data=excluded.data WHERE whole_scan_tasks.version<>excluded.version OR whole_scan_tasks.stage="non_song"',(vid,VERSION,'local','{}'))
        db.commit()
    catalogue=defaultdict(list)
    for row in db.execute('SELECT data FROM catalogue'):
        c=json.loads(row[0]);catalogue[core.norm(core.catalogue_title(c.get('title','')))].append(c)
    artists=defaultdict(dict)
    def index_tracks():
        artists.clear()
        for t in core.tracks(db):
            for a in [t]+t.get('aliases',[]):artists[core.norm(recognition.artist_name(core.artist_base(a['artist'])))][t['id']]=t
    index_tracks()
    state={'status':'running','engine':VERSION,'stage':'local','total':db.execute('SELECT COUNT(*) FROM whole_scan_tasks WHERE version=?',(VERSION,)).fetchone()[0],
           'has_api_key':bool(load_key()),'started_at':time.time(),'current_title':''}
    pending=[]
    def flush(rebuild=False):
        with write_lock:
            current_edits=core.get_state(db,'corrections',{},'user_state')
            for vid,result,stage in pending:
                v=core.video_data(db,vid)
                if v.get('classification',{}).get('status')=='non_song' and non_song.valid(v):
                    stage='non_song';result={'status':'non_song','candidates':[],'reason':v['non_song']['reason']}
                if vid in current_edits or v.get('classification',{}).get('status') in ('song','excluded'):
                    stage='protected';result={'status':'skipped','reason':'기존 결정 유지','candidates':[]}
                elif result['status']=='recognized':
                    t=result['track'];current_edits[vid]={**t,'source':'auto_recognition','exclude':False};result['saved']=True
                    v['classification']=core.classify(v,correction=current_edits[vid]);core.save_video(db,v);videos[vid]=v
                bulk_recognition.store_result(db,vid,result)
                db.execute('UPDATE whole_scan_tasks SET stage=?,data=? WHERE id=?',(stage,json.dumps(result,ensure_ascii=False),vid))
            core.set_state(db,'corrections',current_edits,'user_state');db.commit();pending.clear()
            if rebuild:core.rebuild(db)
            counts=dict(db.execute('SELECT stage,COUNT(*) FROM whole_scan_tasks WHERE version=? GROUP BY stage',(VERSION,)).fetchall())
            state.update(done=sum(n for s,n in counts.items() if s not in ('local','deep')),local_remaining=counts.get('local',0),deep_remaining=counts.get('deep',0),
                         saved=counts.get('saved',0),candidates=counts.get('candidate',0),unresolved=counts.get('unresolved',0),non_song=counts.get('non_song',0),no_music_evidence=counts.get('no_music_evidence',0),errors=counts.get('error',0),updated_at=time.time())
            core.set_state(db,'recognition_job',state);db.commit()
        if rebuild:index_tracks()
    def local(v):
        title=v.get('title') or v.get('history_title','');keys={core.norm(title),core.norm(re.split(r'[/／]',title,maxsplit=1)[0])}
        keys.update(core.norm(x) for x in re.findall(r'[「『]([^」』]+)[」』]',title))
        rows=[c for k in keys for c in catalogue.get(k,[])]
        names=[v.get('channel') or v.get('history_channel','')]+[c['artist'] for c in v.get('music_metadata',{}).get('cards',[])]
        tracks={t['id']:t for a in names for t in artists.get(core.norm(recognition.artist_name(core.artist_base(a))),{}).values()}
        return recognition.recognize(v,rows,lookup=lambda i:videos.get(i),tracks=list(tracks.values()))
    flush()
    try:
        local_ids={r[0] for r in db.execute('SELECT id FROM whole_scan_tasks WHERE version=? AND stage=?',(VERSION,'local'))}
        for vid in sorted(local_ids,key=lambda x:-history.get(x,0)):
            if stop.is_set():break
            v=videos[vid]
            try:
                result=resolve(v,local(v))
                verdict=non_song.decide(v,result) if result['status']!='recognized' else None
                if verdict:
                    with write_lock:
                        current=core.video_data(db,vid);current['non_song']=verdict;core.save_video(db,current);db.commit()
                    result={'status':'non_song','candidates':[],'reason':verdict['reason']};stage='non_song'
                elif result['status']=='recognized' and bulk_recognition.music_evidence(v,result):stage='saved'
                else:
                    stage='deep' if potential(v,result) else 'no_music_evidence'
                    if stage=='no_music_evidence':result={'status':'unresolved','candidates':[],'reason':'자동 판별에서 음악 근거 없음 — 비음악으로 확정한 것은 아님'}
                    elif result['status']=='recognized':result={'status':'unresolved','candidates':[],'reason':'추가 음악 근거 조회 대기'}
            except Exception as e:result={'status':'error','candidates':[],'reason':type(e).__name__};stage='error'
            pending.append((vid,result,stage))
            if len(pending)>=500:flush()
        flush(True)
        if not stop.is_set():
            state['stage']='metadata'
            deep_ids={r[0] for r in db.execute('SELECT id FROM whole_scan_tasks WHERE version=? AND stage=?',(VERSION,'deep'))}
            for vid in sorted(deep_ids,key=lambda x:-history.get(x,0)):
                if stop.is_set():break
                v=core.video_data(db,vid);state['current_title']=v.get('title') or v.get('history_title','');flush()
                if non_song.valid(v):
                    pending.append((vid,{'status':'non_song','candidates':[],'reason':v['non_song']['reason']},'non_song'));flush();continue
                try:
                    if v.get('classification',{}).get('status') in ('song','excluded'):
                        result={'status':'skipped','candidates':[]};stage='protected'
                    else:
                        original_metadata.ensure_originals(db,v,load_key(),write_lock)
                        music_metadata.ensure(db,v,write_lock);v=core.video_data(db,vid);videos[vid]=v
                        verdict=non_song.decide(v,local(v))
                        if verdict:
                            with write_lock:
                                current=core.video_data(db,vid)
                                if non_song.fingerprint(current)==verdict['fingerprint']:
                                    current['non_song']=verdict;current['classification']=core.classify(current,correction=core.get_state(db,'corrections',{},'user_state').get(vid));core.save_video(db,current);db.commit()
                            if non_song.valid(current):
                                pending.append((vid,{'status':'non_song','candidates':[],'reason':verdict['reason']},'non_song'));flush();continue
                        if not load_key():references(db,v,write_lock)
                        for link in recognition.original_links(v.get('description','')):videos[link['video_id']]=core.video_data(db,link['video_id'])
                        for card in v.get('music_metadata',{}).get('cards',[]):
                            if card.get('video_id'):videos[card['video_id']]=core.video_data(db,card['video_id'])
                        result=local(v)
                        if result['status']!='recognized':
                            found=song_databases.search(db,v,write_lock)
                            if found['status']=='recognized':result=found
                            else:result={**result,'candidates':recognition.merge_candidates(result.get('candidates',[])+found.get('candidates',[])),'databases':found.get('databases',[])}
                            result=resolve(v,result)
                        stage='saved' if result['status']=='recognized' else 'candidate' if result.get('candidates') else 'unresolved'
                except Exception as e:result={'status':'error','candidates':[],'reason':type(e).__name__};stage='error'
                pending.append((vid,result,stage));flush(rebuild=stage=='saved')
                # Keep public-page requests sequential and gentle; provider calls have their own throttles.
                if stop.wait(.35):break
        flush(True)
        state.update(status='stopped' if stop.is_set() else 'complete',current_title='',finished_at=time.time());flush()
    except Exception as e:
        state.update(status='error',reason=type(e).__name__);flush()
    return state
