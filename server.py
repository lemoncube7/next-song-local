"""Loopback-only local web app, with persistent user edits and a small HTTP API."""
import argparse, csv, io, json, secrets, threading, traceback, urllib.parse, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import core, pipeline, recognition, song_identity, song_search, google_search, original_metadata, bulk_recognition, music_metadata, song_databases, user_backup, whole_recognition, reverse_catalogue, github_sync, catalogue_import, non_song

TOKEN=secrets.token_urlsafe(32)
JOB_LOCK=threading.Lock()
WRITE_LOCK=threading.Lock()
RECOGNITION_JOB_LOCK=threading.Lock()
WHOLE_STOP=threading.Event()
REVERSE_LOCK=threading.Lock()

def start_whole_scan():
    if not RECOGNITION_JOB_LOCK.acquire(blocking=False):return False
    WHOLE_STOP.clear()
    def work():
        task_db=core.connect()
        try:whole_recognition.run(task_db,load_key,WRITE_LOCK,WHOLE_STOP)
        finally:task_db.close();RECOGNITION_JOB_LOCK.release()
    threading.Thread(target=work,daemon=True).start();return True
def load_key():
    import os
    value=os.environ.get('YOUTUBE_API_KEY','')
    path=core.ROOT/'data'/'youtube-api-key.txt'
    return value or (path.read_text(encoding='utf8').strip() if path.exists() else '')
def run_job(kind):
    if not JOB_LOCK.acquire(blocking=False):return False
    def work():
        db=core.connect()
        try:
            if kind=='metadata':
                key=load_key()
                if key:pipeline.enrich_api(db,key)
                else:pipeline.enrich(db,workers=4,retry=True)
            elif kind=='catalogue':pipeline.karaoke(db)
            elif kind=='full_catalogue':catalogue_import.run(db,WRITE_LOCK)
            elif kind=='non_song':
                with WRITE_LOCK:core.set_state(db,'job',{'status':'running','stage':'non_song'});db.commit()
                result=non_song.reconcile(db,WRITE_LOCK)
                with WRITE_LOCK:core.set_state(db,'job',{'status':'complete','stage':'non_song','done':result['new_non_song'],'total':result['new_non_song']});db.commit()
            core.rebuild(db);pipeline.export(db)
        except Exception as exc:
            core.set_state(db,'job',{'status':'error','stage':kind,'reason':type(exc).__name__});db.commit()
            traceback.print_exc()
        finally:db.close();JOB_LOCK.release()
    threading.Thread(target=work,daemon=True).start();return True
class Handler(BaseHTTPRequestHandler):
    def log_message(self,fmt,*args):
        if str(args[1] if len(args)>1 else '') not in ('200','304'):super().log_message(fmt,*args)
    def valid_host(self):
        return self.headers.get('Host') in {f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'}
    def send(self,value,status=200,ctype='application/json; charset=utf-8',extra=None):
        body=json.dumps(value,ensure_ascii=False).encode() if not isinstance(value,bytes) else value
        self.send_response(status);self.send_header('Content-Type',ctype);self.send_header('Content-Length',str(len(body)))
        self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        for k,v in (extra or {}).items():self.send_header(k,v)
        self.end_headers();self.wfile.write(body)
    def do_GET(self):
        if not self.valid_host():return self.send({'error':'Host rejected'},403)
        parsed=urllib.parse.urlparse(self.path);path=parsed.path;q=urllib.parse.parse_qs(parsed.query)
        if path in ('/','/app.js','/style.css'):
            file={'/':'index.html','/app.js':'app.js','/style.css':'style.css'}[path]
            return self.send((Path(__file__).resolve().parent/'static'/file).read_bytes(),ctype={'/':'text/html; charset=utf-8','/app.js':'text/javascript; charset=utf-8','/style.css':'text/css; charset=utf-8'}[path])
        db=core.connect()
        try:
            if path=='/api/bootstrap':
                return self.send({'token':TOKEN,'stats':core.stats(db),'tracks':core.tracks(db),
                    'queue':song_identity.queue(db),'has_api_key':bool(load_key()),'recognition_job':core.get_state(db,'recognition_job',{'status':'idle'}),
                    'catalogue':[],'reverse_catalogue_job':core.get_state(db,'reverse_catalogue_job',{}),'full_catalogue_job':core.get_state(db,'full_catalogue_job',{}),
                    'github_sync':github_sync.public_config(),'github_sync_job':core.get_state(db,'github_sync_job',{})})
            if path=='/api/github-sync-status':return self.send({'config':github_sync.public_config(),'job':core.get_state(db,'github_sync_job',{}),'conflicts':[{'video_id':r['id'],'candidates':json.loads(r['data'])} for r in db.execute('SELECT * FROM shared_conflicts LIMIT 100')]})
            if path=='/api/github-login-status':return self.send(dict(github_sync.AUTH_STATE))
            if path=='/api/reverse-catalogue-job':return self.send(core.get_state(db,'reverse_catalogue_job',{}))
            if path=='/api/user-backup':
                if self.headers.get('X-App-Token')!=TOKEN:return self.send({'error':'요청 인증 실패'},403)
                return self.send(user_backup.export(db),extra={'Content-Disposition':'attachment; filename="karaoke-decisions.json"'})
            if path=='/api/recognition-job':return self.send(core.get_state(db,'recognition_job',{'status':'idle'}))
            if path=='/api/non-song-status':return self.send(core.get_state(db,'non_song_job',{}))
            if path=='/api/merge-candidates':return self.send({'candidates':song_identity.candidates(db),'history':core.get_state(db,'merge_history',[],'user_state'),'different':list(core.get_state(db,'different_songs',{},'user_state').values())})
            if path=='/api/stats':return self.send(core.stats(db))
            if path=='/api/recognition-targets':
                minimum=int(q.get('min_views',['5'])[0])
                if minimum<1:raise ValueError('최소 시청 횟수는 1회 이상으로 입력해 주세요.')
                status=q.get('status',['review'])[0];search=q.get('q',[''])[0].casefold()
                history={r['video_id']:r['n'] for r in db.execute('SELECT video_id,COUNT(*) AS n FROM events WHERE video_id IS NOT NULL GROUP BY video_id HAVING COUNT(*)>=?',(minimum,))}
                items=[]
                checked={r['id']:json.loads(r['data']) for r in db.execute('SELECT * FROM recognition_results')}
                retry=q.get('retry',['1'])[0]=='1';skipped=0
                for row in db.execute('SELECT data FROM videos'):
                    v=json.loads(row[0]);c=v.get('classification',{});vid=v['video_id']
                    if vid not in history or c.get('status') in ('song','non_song'):continue
                    if status!='all' and c.get('status')!=status:continue
                    if search and search not in ((v.get('title') or v.get('history_title',''))+' '+(v.get('channel') or v.get('history_channel',''))).casefold():continue
                    old=checked.get(vid,{})
                    if not retry and old.get('status') in ('ambiguous','candidate','unresolved','recognized'):
                        skipped+=1;continue
                    items.append({'video_id':vid,'history_records':history[vid]})
                items.sort(key=lambda v:(-v['history_records'],v['video_id']))
                return self.send({'items':items,'total':len(items),'skipped':skipped})
            if path=='/api/videos':
                status=q.get('status',['review'])[0];search=q.get('q',[''])[0].casefold();offset=max(0,int(q.get('offset',['0'])[0]));limit=min(100,max(1,int(q.get('limit',['50'])[0])))
                sort=q.get('sort',['frequency'])[0]
                if sort not in ('frequency','recent'):return self.send({'error':'지원하지 않는 정렬입니다.'},400)
                history={r['video_id']:dict(r) for r in db.execute('SELECT video_id,COUNT(*) AS history_records,MAX(time) AS last_watch,MAX(julianday(time)) AS last_watch_sort FROM events WHERE video_id IS NOT NULL GROUP BY video_id')}
                result=[]
                for row in db.execute('SELECT data FROM videos'):
                    v=json.loads(row[0]);c=v.get('classification',{})
                    if v['video_id'] not in history or c.get('status')=='song' or (c.get('status')=='non_song' and status!='non_song'):continue
                    if status!='all' and c.get('status')!=status:continue
                    if search and search not in ((v.get('title') or v.get('history_title',''))+' '+(v.get('channel') or v.get('history_channel',''))).casefold():continue
                    activity=history.get(v['video_id'],{})
                    v['history_records']=activity.get('history_records',0);v['last_watch']=activity.get('last_watch')
                    result.append(v)
                def order(v):
                    last=history.get(v['video_id'],{}).get('last_watch_sort') or 0
                    return (v['history_records'],last,v['video_id']) if sort=='frequency' else (last,v['history_records'],v['video_id'])
                result.sort(key=order,reverse=True)
                page=result[offset:offset+limit]
                for v in page:
                    saved=db.execute('SELECT data FROM recognition_results WHERE id=?',(v['video_id'],)).fetchone()
                    if saved:v['recognition_result']=json.loads(saved[0])
                return self.send({'total':len(result),'items':page})
            if path=='/api/video':
                v=core.video_data(db,q.get('id',[''])[0])
                if not v:return self.send({'error':'영상을 찾지 못했습니다.'},404)
                return self.send(v)
            if path=='/api/export':
                items={t['id']:t for t in core.tracks(db)};queue=song_identity.queue(db)
                out=io.StringIO();w=csv.writer(out);w.writerow(['곡명','아티스트','TJ 번호','금영 번호','기록 수','마지막 기록','영상 URL'])
                for tid in queue:
                    if tid not in items:continue
                    t=items[tid];w.writerow([t['title'],t['artist'],' / '.join(n['no'] for n in t['numbers'] if n['brand']=='tj'),' / '.join(n['no'] for n in t['numbers'] if n['brand']=='kumyoung'),t['history_records'],t['last_watch'],'https://www.youtube.com/watch?v='+t['video_ids'][0]])
                return self.send(('\ufeff'+out.getvalue()).encode('utf8'),ctype='text/csv; charset=utf-8',extra={'Content-Disposition':'attachment; filename="karaoke-queue.csv"'})
            return self.send({'error':'Not found'},404)
        except (ValueError,TypeError) as e:return self.send({'error':str(e)},400)
        finally:db.close()
    def do_POST(self):
        if not self.valid_host() or self.headers.get('X-App-Token')!=TOKEN:return self.send({'error':'요청 인증 실패'},403)
        origin=self.headers.get('Origin')
        if origin and origin not in {f'http://127.0.0.1:{self.server.server_port}',f'http://localhost:{self.server.server_port}'}:return self.send({'error':'Origin rejected'},403)
        try:length=int(self.headers.get('Content-Length','0'))
        except ValueError:return self.send({'error':'잘못된 요청'},400)
        if length>100*1024*1024:return self.send({'error':'100MB 이하 파일만 지원합니다.'},413)
        data=self.rfile.read(length);db=core.connect();path=urllib.parse.urlparse(self.path).path
        try:
            if path=='/api/user-backup-restore':
                if JOB_LOCK.locked() or RECOGNITION_JOB_LOCK.locked():return self.send({'error':'진행 중인 작업이 끝난 뒤 복원해 주세요.'},409)
                payload=json.loads(data)
                with WRITE_LOCK:return self.send(user_backup.restore(db,payload))
            if path=='/api/import':
                if JOB_LOCK.locked() or core.get_state(db,'job',{}).get('status')=='running':return self.send({'error':'조회가 끝난 뒤 파일을 가져와 주세요.'},409)
                with WRITE_LOCK:
                    with db:
                        result=core.import_bytes(db,data,urllib.parse.unquote(self.headers.get('X-Filename','history.json')))
                    core.rebuild(db);pipeline.export(db)
                return self.send(result)
            if len(data)>1024*1024:raise ValueError('요청이 너무 큽니다.')
            payload=json.loads(data or '{}')
            if path=='/api/github-sync-config':return self.send(github_sync.save_config(payload))
            if path=='/api/github-login':return self.send(github_sync.start_login())
            if path=='/api/github-sync':
                if not github_sync.start(WRITE_LOCK):return self.send({'error':'이미 동기화 중입니다.'},409)
                return self.send({'started':True})
            if path=='/api/reverse-catalogue':
                if not REVERSE_LOCK.acquire(blocking=False):return self.send({'error':'수록곡 역방향 탐색이 이미 진행 중입니다.'},409)
                def reverse_work():
                    task_db=core.connect()
                    try:reverse_catalogue.run(task_db,WRITE_LOCK)
                    except Exception as e:
                        with WRITE_LOCK:core.set_state(task_db,'reverse_catalogue_job',{'status':'error','reason':type(e).__name__});task_db.commit()
                    finally:task_db.close();REVERSE_LOCK.release()
                threading.Thread(target=reverse_work,daemon=True).start();return self.send({'started':True})
            if path=='/api/reuse-confirmed':
                if JOB_LOCK.locked() or RECOGNITION_JOB_LOCK.locked():return self.send({'error':'진행 중인 작업이 끝난 뒤 연결해 주세요.'},409)
                with WRITE_LOCK:return self.send(recognition.reuse_confirmed(db))
            if path=='/api/recognize-all':
                if JOB_LOCK.locked() or not start_whole_scan():return self.send({'error':'전체 자동 처리 또는 정보 조회가 이미 진행 중입니다.'},409)
                return self.send({'started':True})
            if path=='/api/recognize-all-stop':
                WHOLE_STOP.set();return self.send({'stopping':True})
            if path=='/api/google-song-search':
                video=core.video_data(db,payload.get('video_id',''))
                if not video:raise ValueError('영상을 찾지 못했습니다.')
                query=video.get('title') or video.get('history_title','')
                try:result=google_search.search(db,query)
                except (ValueError,OSError):
                    result={'query':query,'provider':'Google','search_url':'https://www.google.com/search?'+urllib.parse.urlencode({'q':query}),'results':[],'candidates':[],'status':'unavailable','cached':False,'reason':'Google 검색 결과를 자동으로 읽지 못했어요. 제목 전문 검색 링크를 열어 확인해 주세요.'}
                return self.send(result)
            if path=='/api/recognition-candidates':
                candidates=payload.get('candidates',[])
                if not isinstance(candidates,list) or len(candidates)>100:raise ValueError('후보 목록을 확인해 주세요.')
                return self.send({'candidates':recognition.merge_candidates(candidates,core.tracks(db))})
            if path=='/api/song-search':
                result=song_search.search(db,payload.get('title',''),payload.get('artist',''),payload.get('provider','auto'))
                result['candidates']=recognition.merge_candidates(result['candidates'],core.tracks(db))
                return self.send(result)
            if path=='/api/recognize':
                vid=payload.get('video_id','');video=core.video_data(db,vid)
                if not video:raise ValueError('영상을 찾지 못했습니다.')
                metadata=original_metadata.ensure_originals(db,video,load_key(),WRITE_LOCK)
                if video.get('classification',{}).get('status') not in ('song','excluded'):
                    music_metadata.ensure(db,video,WRITE_LOCK)
                video=core.video_data(db,vid)
                database_result=None
                if video.get('classification',{}).get('status') not in ('song','excluded'):
                    local=recognition.recognize(video,lookup=lambda i:core.video_data(db,i),tracks=core.tracks(db))
                    if local['status']!='recognized':database_result=song_databases.search(db,video,WRITE_LOCK)
                with WRITE_LOCK:
                    video=core.video_data(db,vid)
                    result=recognition.recognize(video,[json.loads(r[0]) for r in db.execute('SELECT data FROM catalogue')],lookup=lambda original_id:core.video_data(db,original_id),tracks=core.tracks(db))
                    result['original_metadata']=metadata
                    if database_result:
                        if database_result['status']=='recognized':result={**database_result,'original_metadata':metadata}
                        else:
                            result['candidates']=recognition.merge_candidates(result['candidates']+database_result['candidates'])
                            if result['candidates']:result['status']='ambiguous'
                            result['databases']=database_result['databases']
                    if result['status']=='recognized':
                        track=result['track'];edits=core.get_state(db,'corrections',{},'user_state')
                        result['saved']=False
                        result['existing_track']=video.get('classification',{}).get('status')=='song'
                        if vid not in edits and video.get('classification',{}).get('status') not in ('song','excluded'):
                            correction={'title':track['title'],'artist':track['artist'],'exclude':False,'source':'auto_recognition','reason':track['reason']}
                            correction['alternate_labels']=track.get('alternate_labels',[])
                            if track.get('original_video_id'):
                                correction.update({'original_video_id':track['original_video_id'],'original_url':track.get('url')})
                            edits[vid]=correction;core.set_state(db,'corrections',edits,'user_state');db.commit();core.rebuild(db)
                            result['saved']=True
                        else:
                            current=video.get('classification',{})
                            if current.get('status')=='song':
                                result['track']={**track,'title':current['title'],'artist':current['artist']}
                            else:
                                result['status']='candidate'
                                result['reason']='기존 직접 수정·제외 결정을 유지했어요. 후보를 선택하면 직접 저장할 수 있어요.'
                    elif metadata.get('reason'):result['reason']+=' '+metadata['reason']
                with WRITE_LOCK:bulk_recognition.store_result(db,vid,result);db.commit()
                return self.send(result)
            with WRITE_LOCK:
                if path=='/api/different-songs':
                    song_identity.different(db,payload.get('source',''),payload.get('target',''),payload.get('restore',False));return self.send({'ok':True})
                if path=='/api/merge':
                    return self.send(song_identity.merge(db,payload.get('source',''),payload.get('target','')))
                if path=='/api/unmerge':
                    song_identity.undo(db,payload.get('id',''));return self.send({'ok':True})
                if path=='/api/follow':
                    artist=payload.get('artist','').strip()
                    if not artist or len(artist)>200:raise ValueError('아티스트 이름을 확인해 주세요.')
                    artist=core.canonical(artist);values=core.get_state(db,'follows',[],'user_state')
                    if payload.get('follow',True):values=list(dict.fromkeys(values+[artist]))
                    else:values=[x for x in values if core.canonical(x)!=artist]
                    core.set_state(db,'follows',values,'user_state');db.commit();return self.send({'follows':values})
                if path=='/api/karaoke-rating':
                    tid=payload.get('id','');delta=payload.get('delta')
                    if type(delta) is not int or delta not in (-1,1):raise ValueError('평가는 +1 또는 -1이어야 합니다.')
                    if not db.execute('SELECT 1 FROM tracks WHERE id=?',(tid,)).fetchone():raise ValueError('곡을 찾지 못했습니다.')
                    votes=core.get_state(db,'karaoke_ratings',{},'user_state');votes[tid]=votes.get(tid,0)+delta
                    core.set_state(db,'karaoke_ratings',votes,'user_state');db.commit();return self.send({'ok':True})
                if path=='/api/karaoke-good':
                    tid=payload.get('id','');row=db.execute('SELECT data FROM tracks WHERE id=?',(tid,)).fetchone()
                    if not row:raise ValueError('곡을 찾지 못했습니다.')
                    members=json.loads(row[0]).get('member_ids',[tid]);values=core.get_state(db,'karaoke_good',[],'user_state')
                    values=[x for x in values if x not in members]
                    if payload.get('enabled',True):
                        values.append(tid)
                        hidden=[x for x in core.get_state(db,'hidden',[],'user_state') if x not in members]
                        core.set_state(db,'hidden',hidden,'user_state')
                    core.set_state(db,'karaoke_good',values,'user_state');db.commit();return self.send({'ok':True})
                if path in ('/api/queue','/api/hide'):
                    tid=payload.get('id','')
                    if not db.execute('SELECT 1 FROM tracks WHERE id=?',(tid,)).fetchone():raise ValueError('곡을 찾지 못했습니다.')
                    key='queue' if path.endswith('queue') else 'hidden';values=core.get_state(db,key,[],'user_state')
                    if payload.get('enabled',True):values=list(dict.fromkeys(values+[tid]))
                    else:
                        members=json.loads(db.execute('SELECT data FROM tracks WHERE id=?',(tid,)).fetchone()[0]).get('member_ids',[tid])
                        values=[x for x in values if x not in members]
                    if key=='hidden' and payload.get('enabled',True):
                        members=json.loads(db.execute('SELECT data FROM tracks WHERE id=?',(tid,)).fetchone()[0]).get('member_ids',[tid])
                        core.set_state(db,'karaoke_good',[x for x in core.get_state(db,'karaoke_good',[],'user_state') if x not in members],'user_state')
                    core.set_state(db,key,values,'user_state');db.commit();return self.send({key:song_identity.queue(db) if key=='queue' else values})
                if path=='/api/correct':
                    vid=payload.get('video_id','');video=core.video_data(db,vid)
                    if not video:raise ValueError('영상을 찾지 못했습니다.')
                    if payload.get('reset'):
                        edits=core.get_state(db,'corrections',{},'user_state');edits.pop(vid,None)
                    else:
                        title=payload.get('title','').strip();artist=payload.get('artist','').strip();exclude=bool(payload.get('exclude'))
                        if not exclude and (not title or not artist or max(len(title),len(artist))>300):raise ValueError('곡명과 아티스트를 입력해 주세요.')
                        edits=core.get_state(db,'corrections',{},'user_state');edits[vid]={'title':title,'artist':artist,'exclude':exclude}
                        labels=payload.get('alternate_labels',[])
                        if not isinstance(labels,list) or len(labels)>100:raise ValueError('제목 별칭 형식이 잘못되었습니다.')
                        if any(not isinstance(a,dict) or not all(isinstance(a.get(k),str) and 0<len(a[k])<=300 for k in ('title','artist')) for a in labels):raise ValueError('제목 별칭을 확인해 주세요.')
                        edits[vid]['alternate_labels']=labels
                    db.execute('DELETE FROM recognition_results WHERE id=?',(vid,))
                    core.set_state(db,'corrections',edits,'user_state');db.commit();core.rebuild(db);return self.send({'ok':True})
                if path=='/api/number':
                    tid=payload.get('id','');brand=payload.get('brand');no=str(payload.get('no','')).strip()
                    if brand not in ('tj','kumyoung') or not no.isdigit() or len(no)>8:raise ValueError('브랜드와 숫자로 된 곡 번호를 확인해 주세요.')
                    if not db.execute('SELECT 1 FROM tracks WHERE id=?',(tid,)).fetchone():raise ValueError('곡을 찾지 못했습니다.')
                    numbers=core.get_state(db,'numbers',{},'user_state')
                    members=json.loads(db.execute('SELECT data FROM tracks WHERE id=?',(tid,)).fetchone()[0]).get('member_ids',[tid])
                    for member in members:numbers[member]=[x for x in numbers.get(member,[]) if not (x['brand']==brand and x['no']==no)]
                    values=numbers.get(tid,[])
                    item={'brand':brand,'no':no,'source':'manual','official_verified':False,'reason':'직접 확인한 번호'}
                    values=[x for x in values if not (x['brand']==brand and x['no']==no)]
                    if not payload.get('remove'):values.append(item)
                    numbers[tid]=values;core.set_state(db,'numbers',numbers,'user_state');db.commit();core.rebuild(db);return self.send({'ok':True})
                if path=='/api/api-key':
                    key=payload.get('key','').strip()
                    if key and not __import__('re').fullmatch(r'[A-Za-z0-9_-]{20,100}',key):raise ValueError('API 키 형식을 확인해 주세요.')
                    target=core.ROOT/'data'/'youtube-api-key.txt'
                    if key:target.write_text(key,encoding='utf8')
                    elif target.exists():target.unlink()
                    return self.send({'has_api_key':bool(load_key())})
                if path=='/api/job':
                    kind=payload.get('kind')
                    if kind not in ('metadata','catalogue','full_catalogue','non_song'):raise ValueError('잘못된 작업입니다.')
                    if core.get_state(db,'job',{}).get('status')=='running' or not run_job(kind):return self.send({'error':'이미 조회 중입니다.'},409)
                    return self.send({'started':True})
            return self.send({'error':'Not found'},404)
        except (ValueError,KeyError,TypeError,zipfile_error()) as e:
            db.rollback();return self.send({'error':str(e)},400)
        except Exception:
            db.rollback();traceback.print_exc();return self.send({'error':'처리 중 오류가 발생했습니다. 서버 로그를 확인해 주세요.'},500)
        finally:db.close()
def zipfile_error():
    import zipfile
    return zipfile.BadZipFile
def main():
    p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=8765);p.add_argument('--open',action='store_true');args=p.parse_args()
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    db=core.connect()
    previous=core.get_state(db,'job',{})
    if previous.get('status')=='running':
        previous.update({'status':'interrupted','reason':'이전 실행이 종료됐습니다. 저장된 결과부터 다시 조회할 수 있어요.'});core.set_state(db,'job',previous);db.commit()
    core.rebuild(db);db.close()
    print(f'다음 곡: http://127.0.0.1:{args.port}',flush=True)
    scan=core.connect();resume=core.get_state(scan,'recognition_job',{});scan.close()
    if resume.get('engine')==whole_recognition.VERSION and resume.get('status')=='running':start_whole_scan()
    github_sync.scheduler(WRITE_LOCK)
    if args.open:webbrowser.open(f'http://127.0.0.1:{args.port}')
    try:server.serve_forever()
    except KeyboardInterrupt:server.server_close()

if __name__=='__main__':main()
