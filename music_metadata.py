"""Anonymous public music-card lookup; no account, playback or API key."""
import json,re
from datetime import datetime,timezone,timedelta
import core,pipeline

def extract(page):
    match=re.search(r'(?:var\s+)?ytInitialData\s*=\s*',page)
    if not match:return []
    data=json.JSONDecoder().raw_decode(page[match.end():])[0];cards=[]
    def walk(value):
        if isinstance(value,dict):
            for key,item in value.items():
                if key=='horizontalCardListRenderer':
                    heading=item.get('header',{}).get('richListHeaderRenderer',{}).get('title',{})
                    label=heading.get('simpleText') or ''.join(r.get('text','') for r in heading.get('runs',[]))
                    if label in ('음악','Music','音楽'):
                        for card in item.get('cards',[]):
                            a=card.get('videoAttributeViewModel',{})
                            title=a.get('title');artist=a.get('subtitle')
                            if not isinstance(title,str) or not isinstance(artist,str):continue
                            endpoint=a.get('onTap',{}).get('innertubeCommand',{}).get('watchEndpoint',{})
                            vid=endpoint.get('videoId')
                            entry={'title':title,'artist':artist,'album':a.get('secondarySubtitle',{}).get('content','')}
                            if isinstance(vid,str) and re.fullmatch(r'[A-Za-z0-9_-]{11}',vid):entry['video_id']=vid
                            if entry not in cards:cards.append(entry)
                walk(item)
        elif isinstance(value,list):
            for item in value:walk(item)
    walk(data);return cards[:10]

def ensure(db,video,write_lock):
    now=datetime.now(timezone.utc);old=video.get('music_metadata',{})
    try:
        if old and now-datetime.fromisoformat(old['checked_at'])<timedelta(days=7):return old
    except (ValueError,KeyError):pass
    result={'checked_at':now.isoformat(),'status':'ok','cards':[]}
    details={}
    try:
        page=pipeline.fetch('https://www.youtube.com/watch?v='+video['video_id']+'&hl=ja');result['cards']=extract(page)
        match=re.search(r'(?:var\s+)?ytInitialPlayerResponse\s*=\s*',page)
        if match:
            player=json.JSONDecoder().raw_decode(page[match.end():])[0];info=player.get('videoDetails',{})
            if info.get('videoId')==video['video_id']:
                details={'title':info.get('title',''),'channel':info.get('author',''),'description':info.get('shortDescription','')[:16000],
                         'category':player.get('microformat',{}).get('playerMicroformatRenderer',{}).get('category'),'metadata_status':'ok'}
    except Exception as exc:result.update(status='unavailable',error=type(exc).__name__)
    with write_lock:
        current=core.video_data(db,video['video_id'])
        if current:
            if current.get('metadata_status')=='pending':current.update({k:v for k,v in details.items() if v is not None})
            current['music_metadata']=result;core.save_video(db,current);db.commit()
    return result

def risky_video(video):
    raw=video.get('title') or video.get('history_title','')
    if re.search(r'(?i)cover|歌ってみた|커버|remix|medley|メドレー|모음|playlist|\blive\b|歌枠|karaoke',raw):return True
    for card in video.get('music_metadata',{}).get('cards',[]):
        # Some cover rights metadata repeats "song / cover singer - original artist".
        parts=re.split(r'\s*[/／_]\s*',card.get('title',''),maxsplit=1)
        if len(parts)==2 and core.norm(card.get('artist','')) in core.norm(parts[1]):return True
    return False

def identity(video,lookup=None):
    cards=video.get('music_metadata',{}).get('cards',[])
    if not cards:return None
    raw=video.get('title') or video.get('history_title','')
    risky=risky_video(video)
    candidates=[]
    for card in cards:
        clean_title=re.sub(r'\s*[/／]\s*(?:初音ミク|鏡音リン|鏡音レン|歌愛ユキ|GUMI|flower|IA)(?:\s*\[.*?\])?\s*$','',card['title'],flags=re.I).strip()
        candidate={'title':clean_title,'artist':core.canonical(card['artist']),
                   'reason':'유튜브 공개 음악 카드의 곡명·가수','confident':False,
                   'alternate_labels':[{'title':card['title'],'artist':card['artist']}],
                   'music_card':True}
        if card.get('video_id'):candidate['url']='https://www.youtube.com/watch?v='+card['video_id']
        if lookup and card.get('video_id') and card['video_id']!=video['video_id']:
            original=lookup(card['video_id'])
            known=original.get('classification',{}) if original else {}
            if known.get('status')=='song':
                candidate.update(title=known['title'],artist=known['artist'],original_video_id=card['video_id'])
        # Preserve the native spelling printed in the video when it is the same normalized title.
        quoted=re.findall(r'[「『]([^」』]+)[」』]',raw)
        labels=quoted+[raw.split(' / ')[0].split('／')[0].strip()]
        native=next((t for t in labels if core.norm(t)==core.norm(card['title'])),None)
        if native and not candidate.get('original_video_id') and clean_title==card['title']:candidate['title']=native
        candidate['confident']=len(cards)==1 and not risky and len(core.norm(candidate['title']))>=3 and core.norm(candidate['title']) in core.norm(raw)
        split=re.split(r'\s*[/／]\s*',raw,maxsplit=1)
        if risky and len(split)==2 and '-' in split[1]:
            cover_artist,original_artist=split[1].rsplit('-',1)
            if core.norm(cover_artist)==core.norm(card['artist']) and original_artist.strip():
                candidate.update(title=split[0].strip(),artist=core.canonical(original_artist.strip()),
                                 reason='음악 카드의 커버 가수와 영상 제목의 원곡 가수 표기 대조 — 후보 확인 필요',alternate_labels=[])
        candidates.append(candidate)
    strong=[c for c in candidates if c['confident']]
    if len(strong)==1:return {'status':'recognized','track':strong[0],'candidates':candidates}
    return {'status':'ambiguous','candidates':candidates,'reason':'유튜브 음악 정보는 찾았어요. 번역 표기·커버·복수 곡 여부를 확인해 주세요.'}
