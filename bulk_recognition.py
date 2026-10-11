"""Whole-history recognition, with durable results and preserved user edits."""
import json, re, time
from collections import defaultdict
import core, recognition, original_metadata, google_search

def store_result(db, vid, result):
    db.execute('INSERT OR REPLACE INTO recognition_results VALUES (?,?)',(vid,json.dumps(result,ensure_ascii=False)))

def music_evidence(video, result):
    if video.get('category')=='Music' or result.get('track',{}).get('original_video_id'):return True
    title=video.get('title') or video.get('history_title','')
    track=result.get('track',{})
    known={core.norm(a) for group in core.ARTIST_GROUPS for a in group}
    if core.norm(track.get('artist','')) in known:return True
    if track.get('reason')=='기존 노래방 목록의 곡명 일치':return True
    if re.search(recognition.VOCAL,title,re.I):return True
    if re.search(r'(?i)\bMV\b',title):return True
    if re.search(r'(?i)music video|official (?:music )?video|[【\[(]\s*(?:MV|オリジナル)[^】\])]?[】\])]',title):return True
    description=video.get('description','')
    return bool(re.search(r'(?im)^\s*[■□・●▷◇◆]*\s*(?:[\[［])?(?:music|音楽|曲|作詞作曲|作曲|作編曲)(?:\s*[:：/＆&、・.,\]］]|\s+(?:[A-Za-z]|-))',description))

def run(db, load_key, write_lock):
    history={r['video_id']:r['n'] for r in db.execute('SELECT video_id,COUNT(*) n FROM events WHERE video_id IS NOT NULL GROUP BY video_id')}
    videos={r['id']:json.loads(r['data']) for r in db.execute('SELECT id,data FROM videos')}
    items=sorted((vid for vid in history if videos[vid].get('classification',{}).get('status') not in ('song','excluded')),key=lambda vid:-history[vid])
    catalogue=defaultdict(list)
    for row in db.execute('SELECT data FROM catalogue'):
        c=json.loads(row[0]);catalogue[core.norm(core.catalogue_title(c.get('title','')))].append(c)
    state={'status':'running','total':len(items),'done':0,'saved':0,'candidates':0,'unresolved':0,'errors':0,'google_available':True,'has_api_key':bool(load_key()),'started_at':time.time()}
    def progress():
        with write_lock:core.set_state(db,'recognition_job',state);db.commit()
    progress();pending=[]
    try:
        for vid in items:
            v=videos[vid];title=v.get('title') or v.get('history_title','')
            keys={core.norm(title),core.norm(re.split(r'[/／]',title,maxsplit=1)[0])}
            keys.update(core.norm(x) for x in re.findall(r'[「『]([^」』]+)[」』]',title))
            rows=[c for key in keys for c in catalogue.get(key,[])]
            try:
                metadata=original_metadata.ensure_originals(db,v,load_key(),write_lock)
                # Re-read edits before saving later; local references stay cached.
                result=recognition.recognize(v,rows,lookup=lambda i:core.video_data(db,i))
                result['original_metadata']=metadata
                if result['status']=='recognized' and not music_evidence(v,result):
                    result={'status':'unresolved','candidates':[],'reason':'전체 처리에서 음악임을 뒷받침하는 근거가 부족해 직접 확인이 필요해요.','original_metadata':metadata}
                if result['status']!='recognized' and state['google_available'] and v.get('classification',{}).get('status')=='review':
                    try:
                        web=google_search.search(db,title);result['google']=web
                        result['candidates']=recognition.merge_candidates(result['candidates']+web.get('candidates',[]))
                        if web['status']!='ok':state['google_available']=False;state['google_reason']=web['reason']
                    except (ValueError,OSError):state['google_available']=False;state['google_reason']='Google 자동 검색 결과를 읽지 못해 나머지는 로컬 인식을 진행했습니다.'
                if metadata.get('reason') and result['status']!='recognized':result['reason']+=' '+metadata['reason']
                pending.append((vid,result))
                if result['status']=='recognized':state['saved']+=1
                elif result.get('candidates'):state['candidates']+=1
                else:state['unresolved']+=1
            except Exception as error:
                state['errors']+=1;pending.append((vid,{'status':'error','candidates':[],'reason':type(error).__name__}))
            state['done']+=1
            if len(pending)>=500 or state['done']==state['total']:
                with write_lock:
                    edits=core.get_state(db,'corrections',{},'user_state')
                    for video_id,result in pending:
                        latest=core.video_data(db,video_id)
                        if video_id in edits or latest.get('classification',{}).get('status') in ('song','excluded'):continue
                        if result['status']=='recognized':
                            t=result['track'];correction={'title':t['title'],'artist':t['artist'],'source':'auto_recognition','reason':t['reason']}
                            if t.get('original_video_id'):correction.update({'original_video_id':t['original_video_id'],'original_url':t.get('url')})
                            edits[video_id]=correction
                        store_result(db,video_id,result)
                    core.set_state(db,'corrections',edits,'user_state');core.set_state(db,'recognition_job',state);db.commit()
                pending=[]
        with write_lock:core.rebuild(db)
        state['status']='complete';state['finished_at']=time.time();progress()
    except Exception as error:
        state.update({'status':'error','reason':type(error).__name__});progress()
    return state
