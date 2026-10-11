"""Fetch missing original-song metadata without importing watch events."""
import json, re, threading, time, urllib.parse, urllib.request, urllib.error
from contextlib import nullcontext
from datetime import datetime, timezone
import core, recognition

FETCH_LOCK=threading.Lock()

def request_videos(ids, key):
    params=urllib.parse.urlencode({'part':'snippet,contentDetails,topicDetails','id':','.join(ids)})
    request=urllib.request.Request('https://www.googleapis.com/youtube/v3/videos?'+params,
        headers={'X-Goog-Api-Key':key,'User-Agent':'LocalKaraoke/1.0'})
    try:
        with urllib.request.urlopen(request,timeout=20) as response:
            return {'status':'ok','items':json.loads(response.read()).get('items',[])}
    except urllib.error.HTTPError as error:
        # Never return/log provider bodies or URLs that could contain credentials.
        return {'status':'failed','reason':'YouTube API HTTP '+str(error.code)}
    except (OSError,ValueError):
        return {'status':'failed','reason':'YouTube API 연결 또는 응답 오류'}

def ensure_originals(db, video, key, write_lock=None):
    links=recognition.original_links(video.get('description',''))
    ids=list(dict.fromkeys(x['video_id'] for x in links if re.fullmatch(r'[\w-]{11}',x['video_id']) and x['video_id']!=video.get('video_id')))
    if not ids:return {'status':'not_needed','fetched':0}
    with FETCH_LOCK:
        now=time.time();missing=[]
        for vid in ids:
            cached=core.video_data(db,vid)
            if cached and cached.get('title') and cached.get('channel') and cached.get('metadata_status')!='unavailable':continue
            if cached and cached.get('original_checked_at',0)>now-86400:continue
            missing.append(vid)
        if not missing:return {'status':'cached','fetched':0}
        if not key:return {'status':'no_key','fetched':0,'reason':'원곡 영상 정보 조회에는 YouTube API 키가 필요해요.'}
        failed=core.get_state(db,'original_api_failure',{})
        if failed.get('at',0)>now-60:return {'status':'failed','fetched':0,'reason':failed['reason']}
        fetched=0;unavailable=[]
        for start in range(0,len(missing),50):
            batch=missing[start:start+50];result=request_videos(batch,key)
            if result['status']!='ok':
                with write_lock or nullcontext():
                    core.set_state(db,'original_api_failure',{'at':now,'reason':result['reason']});db.commit()
                return {'status':'failed','fetched':fetched,'reason':result['reason']}
            indexed={item['id']:item for item in result['items'] if item.get('id') in batch}
            with write_lock or nullcontext():
                edits=core.get_state(db,'corrections',{},'user_state')
                for vid in batch:
                    data=core.video_data(db,vid) or {'video_id':vid}
                    item=indexed.get(vid)
                    if item:
                        snippet=item.get('snippet',{});cat=snippet.get('categoryId')
                        data.update({'title':snippet.get('title',''),'channel':snippet.get('channelTitle',''),
                            'description':snippet.get('description',''),'category_id':cat,
                            'category':'Music' if cat=='10' else 'categoryId '+str(cat),
                            'topic_details':item.get('topicDetails',{}),'duration':item.get('contentDetails',{}).get('duration'),
                            'metadata_status':'ok','metadata_source':'youtube_data_api','api_checked':True,
                            'fetched_at':datetime.now(timezone.utc).isoformat()})
                        data.pop('error',None);data['classification']=core.classify(data,correction=edits.get(vid));fetched+=1
                    else:
                        data.update({'metadata_status':'unavailable','api_checked':True});unavailable.append(vid)
                    data['original_checked_at']=now;core.save_video(db,data)
                core.set_state(db,'original_api_failure',{});db.commit()
        return {'status':'ok','fetched':fetched,'unavailable':unavailable}
