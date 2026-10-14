"""Resumable metadata enrichment. No account cookies, playback or LLM requests."""
import argparse, json, re, time, urllib.request, urllib.parse, urllib.error, os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
import core

def fetch(url, timeout=15):
    req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'})
    with urllib.request.urlopen(req,timeout=timeout) as response:
        return response.read(6*1024*1024).decode('utf-8')
def metadata(vid):
    result={'video_id':vid,'fetched_at':datetime.now(timezone.utc).isoformat()}
    try:
        page=fetch('https://www.youtube.com/watch?v='+vid)
        m=re.search(r'(?:var\s+)?ytInitialPlayerResponse\s*=\s*',page)
        if not m:result['metadata_status']='unavailable';result['error']='player_metadata_missing';return result
        player=json.JSONDecoder().raw_decode(page[m.end():])[0]
        details=player.get('videoDetails',{});micro=player.get('microformat',{}).get('playerMicroformatRenderer',{})
        if details.get('videoId') not in (None,vid): raise ValueError('video_id_mismatch')
        result.update({'title':details.get('title',''),'channel':details.get('author',''),'description':details.get('shortDescription','')[:16000],
            'length_seconds':details.get('lengthSeconds'),'live':details.get('isLiveContent',False),
            'player_status':player.get('playabilityStatus',{}).get('status'),'category':micro.get('category')})
        if not result['category']:
            m=re.search(r'"category"\s*:\s*"((?:[^"\\]|\\.)*)"',page)
            if m:result['category']=json.loads('"'+m.group(1)+'"')
        result['metadata_status']='ok' if details else 'unavailable'
        if not details:result['error']=player.get('playabilityStatus',{}).get('reason','video_details_unavailable')
    except urllib.error.HTTPError as e:
        result['metadata_status']='error';result['error']='HTTP_'+str(e.code)
        result['rate_limited']=e.code==429
    except Exception as e:
        result['metadata_status']='error';result['error']=type(e).__name__
    return result
def seed(db):
    parent=core.ROOT.parent
    for name in ['category-pilot.json','general-youtube-pilot.json','non-music-review.json','random-category-pilot.json']:
        path=parent/name
        if not path.exists():continue
        for cached in json.loads(path.read_text(encoding='utf8')):
            old=core.video_data(db,cached['video_id'])
            if not old:continue
            old['category']=cached.get('category')
            if 'description' in cached:
                old.update({k:cached[k] for k in ('description','live','length_seconds','player_status') if k in cached})
                old['metadata_status']='ok'
            core.save_video(db,old)
    path=core.ROOT.parents[1]/'work'/'artist-catalogue-expanded.json'
    if path.exists():
        for row in json.loads(path.read_text(encoding='utf8')):
            if row['brand'] in ('tj','kumyoung'):
                db.execute('INSERT OR REPLACE INTO catalogue VALUES (?,?,?)',(row['brand'],str(row['no']),json.dumps(row,ensure_ascii=False)))
    db.commit();core.rebuild(db)
def enrich(db, workers=8, retry=False):
    vids=[]
    for row in db.execute('SELECT id,data FROM videos'):
        data=json.loads(row['data'])
        if data.get('metadata_status','pending')=='pending' or (retry and data.get('metadata_status') in ('error','unavailable')):vids.append(row['id'])
    total=len(vids);done=0;errors=0;started=time.monotonic()
    def progress(status='running'):
        state={'status':status,'stage':'metadata','total':total,'done':done,'errors':errors,'elapsed_seconds':round(time.monotonic()-started),'updated_at':datetime.now(timezone.utc).isoformat()}
        core.set_state(db,'job',state);db.commit()
        print(json.dumps(state),flush=True)
    progress()
    # Stop on rate limiting. Only a bounded batch is ever submitted.
    with ThreadPoolExecutor(max_workers=workers) as pool:
        blocked=False
        for offset in range(0,total,workers):
            pending=[pool.submit(metadata,vid) for vid in vids[offset:offset+workers]]
            for future in as_completed(pending):
                result=future.result();old=core.video_data(db,result['video_id']) or {}
                old.update(result);core.save_video(db,old);done+=1
                errors+=result['metadata_status']=='error'
                blocked=blocked or result.get('rate_limited',False)
            if blocked:
                core.set_state(db,'job',{'status':'blocked','stage':'metadata','done':done,'total':total,'reason':'YouTube HTTP 429 — 공식 API 키를 설정해 주세요.'});db.commit();core.rebuild(db);return
            if done%50<workers:progress()
            if done%250<workers:core.rebuild(db)
    progress('complete');core.rebuild(db)
def catalogue_request(kind, value, brand):
    if '/' in value:
        return {'status':'deferred','error':'슬래시가 포함된 검색어 — 자동 경로 검색 보류','rows':[]}
    url=f'https://api.manana.kr/karaoke/{kind}/{urllib.parse.quote(value,safe="")}/{brand}.json'
    try:
        rows=json.loads(fetch(url,20))
        if not isinstance(rows,list):raise ValueError('Unexpected catalogue format')
        valid=[r for r in rows if isinstance(r,dict) and r.get('brand')==brand and all(r.get(k) for k in ('no','title','singer'))]
        return {'status':'ok','rows':valid}
    except urllib.error.HTTPError as e:return {'status':'error','error':'HTTP_'+str(e.code),'rate_limited':e.code==429,'rows':[]}
    except Exception as e:return {'status':'error','error':type(e).__name__,'rows':[]}
def enrich_api(db, key):
    """Official public metadata API, 50 IDs per request. API key never logged."""
    vids=[r['id'] for r in db.execute('SELECT id,data FROM videos') if re.fullmatch(r'[A-Za-z0-9_-]{11}',r['id']) and not json.loads(r['data']).get('api_checked')]
    total=len(vids);done=0
    categories={'10':'Music','20':'Gaming','24':'Entertainment','23':'Comedy','27':'Education','17':'Sports'}
    categories.update(core.get_state(db,'category_names',{}))
    for offset in range(0,total,50):
        batch=vids[offset:offset+50]
        params=urllib.parse.urlencode({'part':'snippet,contentDetails,topicDetails','id':','.join(batch)})
        request=urllib.request.Request('https://www.googleapis.com/youtube/v3/videos?'+params,headers={'X-Goog-Api-Key':key,'User-Agent':'LocalKaraoke/1.0'})
        try:
            with urllib.request.urlopen(request,timeout=25) as response:payload=json.loads(response.read())
        except urllib.error.HTTPError as error:
            reason='HTTP_'+str(error.code)
            try:reason=json.loads(error.read()).get('error',{}).get('errors',[{}])[0].get('reason',reason)
            except Exception:pass
            core.set_state(db,'job',{'status':'blocked','stage':'official_metadata','done':done,'total':total,'reason':reason});db.commit();core.rebuild(db);return
        except Exception as error:
            core.set_state(db,'job',{'status':'error','stage':'official_metadata','done':done,'total':total,'reason':type(error).__name__});db.commit();core.rebuild(db);return
        indexed={x['id']:x for x in payload.get('items',[])}
        for vid in batch:
            data=core.video_data(db,vid);item=indexed.get(vid)
            if item:
                s=item.get('snippet',{});cat=s.get('categoryId')
                data.update({'title':s.get('title',''),'channel':s.get('channelTitle',''),'description':s.get('description',''),
                    'category':categories.get(cat,'categoryId '+str(cat)),'category_id':cat,
                    'topic_details':item.get('topicDetails',{}),'duration':item.get('contentDetails',{}).get('duration'),
                    'metadata_status':'ok','metadata_source':'youtube_data_api','player_status':None})
                data.pop('error',None)
            else:data.update({'metadata_status':'unavailable','error':'공개 API에서 영상 정보를 반환하지 않음'})
            data['api_checked']=True;data['fetched_at']=datetime.now(timezone.utc).isoformat();core.save_video(db,data)
        done+=len(batch);core.set_state(db,'job',{'status':'running','stage':'official_metadata','done':done,'total':total});db.commit()
        if done%1000==0:
            print(json.dumps({'stage':'official_metadata','done':done,'total':total}),flush=True)
        if done%(10000 if total>10000 else 250)==0:core.rebuild(db)
    core.set_state(db,'job',{'status':'complete','stage':'official_metadata','done':done,'total':total});db.commit();core.rebuild(db)
def query(db, kind, value, brand):
    key=kind+'|'+value+'|'+brand
    cached=db.execute('SELECT data FROM queries WHERE key=?',(key,)).fetchone()
    if cached and json.loads(cached[0]).get('status')=='ok':return
    result=catalogue_request(kind,value,brand)
    for row in result.pop('rows'):
        db.execute('INSERT OR REPLACE INTO catalogue VALUES (?,?,?)',(row['brand'],str(row['no']),json.dumps(row,ensure_ascii=False)))
    result.update({'kind':kind,'value':value,'brand':brand,'fetched_at':datetime.now(timezone.utc).isoformat()})
    db.execute('INSERT OR REPLACE INTO queries VALUES (?,?)',(key,json.dumps(result,ensure_ascii=False)));db.commit()
def karaoke(db):
    core.rebuild(db);items=core.tracks(db)
    artists=sorted({t['artist'] for t in items if 1<len(t['artist'])<=100})
    jobs=[('singer',artist,brand) for artist in artists for brand in ('tj','kumyoung')]
    def run_jobs(jobs,stage):
        fresh=[j for j in jobs if not (r:=db.execute('SELECT data FROM queries WHERE key=?',('|'.join(j),)).fetchone()) or json.loads(r[0]).get('status') not in ('ok','deferred')]
        with ThreadPoolExecutor(max_workers=4) as pool:
            for offset in range(0,len(fresh),4):
                batch=fresh[offset:offset+4]
                results=list(pool.map(lambda j:catalogue_request(*j),batch))
                for (kind,value,brand),result in zip(batch,results):
                    for row in result.pop('rows'):
                        db.execute('INSERT OR REPLACE INTO catalogue VALUES (?,?,?)',(row['brand'],str(row['no']),json.dumps(row,ensure_ascii=False)))
                    result.update({'kind':kind,'value':value,'brand':brand,'fetched_at':datetime.now(timezone.utc).isoformat()})
                    db.execute('INSERT OR REPLACE INTO queries VALUES (?,?)',('|'.join((kind,value,brand)),json.dumps(result,ensure_ascii=False)))
                db.commit()
                if any(result.get('rate_limited') for result in results):
                    core.set_state(db,'job',{'status':'blocked','stage':stage,'reason':'노래방 API HTTP 429 — 조회를 중단했습니다.'});db.commit();core.rebuild(db);return False
                core.set_state(db,'job',{'status':'running','stage':stage,'done':min(offset+4,len(fresh)),'total':len(fresh)});db.commit()
                if offset%20==0:print(f'{stage} {min(offset+4,len(fresh))}/{len(fresh)}',flush=True)
        core.rebuild(db)
        return True
    if not run_jobs(jobs,'catalogue_artists'):return
    # Exact title queries supplement artist spellings; cache even empty responses.
    titles=sorted({core.catalogue_title(a['title']) for t in core.tracks(db) if not t['numbers'] for a in [t]+t.get('aliases',[]) if 1<len(a['title'])<=120})
    if not run_jobs([('song',title,brand) for title in titles for brand in ('tj','kumyoung')],'catalogue_titles'):return
    core.set_state(db,'job',{'status':'complete','stage':'catalogue_complete'});db.commit()
def export(db):
    (core.ROOT/'data'/'summary.json').write_text(json.dumps(core.stats(db),ensure_ascii=False,indent=2),encoding='utf8')
    (core.ROOT/'data'/'tracks.json').write_text(json.dumps(core.tracks(db),ensure_ascii=False,indent=2),encoding='utf8')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--import-file');p.add_argument('--seed',action='store_true');p.add_argument('--enrich',action='store_true');p.add_argument('--official',action='store_true');p.add_argument('--karaoke',action='store_true');p.add_argument('--retry',action='store_true');p.add_argument('--workers',type=int,default=8);args=p.parse_args()
    db=core.connect()
    if args.import_file:
        path=Path(args.import_file);print(json.dumps(core.import_bytes(db,path.read_bytes(),path.name),ensure_ascii=False),flush=True)
    if args.seed:seed(db)
    if args.enrich:enrich(db,max(1,min(8,args.workers)),args.retry)
    if args.official:
        api_key=os.environ.get('YOUTUBE_API_KEY','')
        if not api_key:raise SystemExit('YOUTUBE_API_KEY is required; no key was printed.')
        enrich_api(db,api_key)
    if args.karaoke:karaoke(db)
    core.rebuild(db);export(db);print(json.dumps(core.stats(db),ensure_ascii=False),flush=True)
