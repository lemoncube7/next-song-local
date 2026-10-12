"""Versioned shared songs and video mappings. No watch history fields."""
import hashlib,json,re
from collections import defaultdict
import core,recognition,song_identity

FORMAT='next-song-knowledge'
def external_id(value):
    url=value.get('url','')
    for provider,pattern in [('VocaDB',r'^https://vocadb\.net/S/(\d+)$'),('MusicBrainz',r'^https://musicbrainz\.org/recording/([a-f0-9-]{36})$'),('iTunes',r'^https://(?:music|itunes)\.apple\.com/[^?]+\?i=(\d+)(?:&.*)?$')]:
        m=re.match(pattern,url)
        if m:return {'provider':provider,'id':m[1]}
    return None
def ensure(db):
    db.execute('CREATE TABLE IF NOT EXISTS shared_knowledge(path TEXT PRIMARY KEY,data TEXT NOT NULL)')
def song_id(title,artist):return song_identity.identity(title,core.number_artist(artist))
def documents(db,records,client):
    tracks={v:t for t in core.tracks(db) for v in t['video_ids']}
    edits=core.get_state(db,'corrections',{},'user_state')
    parts={f'{i:x}':{'songs':{},'mappings':[]} for i in range(16)}
    for r in records:
        t=tracks.get(r['video_id'],r);sid=song_id(t['title'],t['artist'])
        v=core.video_data(db,r['video_id']) or {};raw=v.get('title') or v.get('history_title','')
        kind='remix' if re.search(r'(?i)remix|リミックス',raw) else 'cover' if re.search(r'(?i)cover|커버|歌ってみた',raw) else 'translation' if re.search(r'(?i)subbed|字幕|자막|한글화|ENG SUB',raw) else 'original' if v.get('classification',{}).get('source') in ('topic','auto_generated','library') else 'unknown'
        channel=v.get('channel') or v.get('history_channel','')
        if kind=='unknown' and channel.endswith(' - Topic') and core.norm(core.canonical(channel[:-8]))==core.norm(core.canonical(t['artist'])):kind='original'
        performer=''
        if kind=='cover':
            m=re.search(r'(?im)^\s*(?:Vocal\s*[:：]|Vocal by\s+|노래\s*[:：]|보컬\s*[:：])\s*([^\n]+)',v.get('description',''))
            if m:performer=re.split(r'https?://|@',m[1])[0].strip()[:100]
        originals=[]
        correction=edits.get(r['video_id'],{})
        if correction.get('original_video_id'):originals.append(correction['original_video_id'])
        if kind=='original':originals.append(r['video_id'])
        aliases=list({(a['title'],a['artist']):a for a in t.get('aliases',[])+r['aliases']+[{'title':r['title'],'artist':r['artist']}]}.values())[:50]
        numbers=list({(n['brand'],str(n['no'])):{'brand':n['brand'],'no':str(n['no'])} for n in t.get('numbers',r['numbers']) if n.get('brand') in ('tj','kumyoung','dam','joysound')}.values())[:100]
        shard=hashlib.sha256(r['video_id'].encode()).hexdigest()[0];p=parts[shard]
        song=p['songs'].setdefault(sid,{'id':sid,'title':t['title'],'artist':core.canonical(t['artist']),'aliases':aliases,'numbers':numbers,'original_video_ids':[],'external_ids':[]})
        ext=external_id(correction)
        if ext and ext not in song['external_ids']:song['external_ids'].append(ext)
        song['original_video_ids']=list(dict.fromkeys(song['original_video_ids']+originals))
        p['mappings'].append({'video_id':r['video_id'],'song_id':sid,'kind':kind,'performer':performer,'evidence':r['evidence']})
    result={}
    for shard,p in parts.items():
        body={'format':FORMAT,'version':2,'client_id':client,'songs':sorted(p['songs'].values(),key=lambda s:s['id']),'mappings':sorted(p['mappings'],key=lambda m:m['video_id'])}
        body['revision']=hashlib.sha256(json.dumps(body,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        result[f'knowledge/{client}-{shard}.json']=body
    return result
def validate(path,doc):
    m=re.fullmatch(r'knowledge/([a-f0-9]{32})-[a-f0-9]\.json',path)
    keys={'format','version','client_id','songs','mappings','revision'}
    if not m or not isinstance(doc,dict) or set(doc)!=keys or doc['format']!=FORMAT or doc['version']!=2 or doc['client_id']!=m[1]:raise ValueError('공유 곡 문서 형식 오류')
    if not isinstance(doc['songs'],list) or not isinstance(doc['mappings'],list) or max(len(doc['songs']),len(doc['mappings']))>10000:raise ValueError('공유 문서 크기 오류')
    body={k:v for k,v in doc.items() if k!='revision'}
    if doc['revision']!=hashlib.sha256(json.dumps(body,sort_keys=True,ensure_ascii=False).encode()).hexdigest():raise ValueError('공유 문서 변경 검증 실패')
    ids=set()
    for s in doc['songs']:
        if not isinstance(s,dict) or set(s)!={'id','title','artist','aliases','numbers','original_video_ids','external_ids'}:raise ValueError('곡에 허용하지 않은 항목이 있습니다.')
        if any(not isinstance(s[k],str) or not 1<=len(s[k])<=300 for k in ('title','artist')) or not re.fullmatch(r'[a-f0-9]{20}',s['id']) or s['id'] in ids:raise ValueError('곡 식별자 오류')
        if s['id']!=song_id(s['title'],s['artist']):raise ValueError('곡 식별자·제목 불일치')
        ids.add(s['id'])
        if not isinstance(s['aliases'],list) or len(s['aliases'])>50 or not isinstance(s['numbers'],list) or len(s['numbers'])>100 or not isinstance(s['original_video_ids'],list) or len(s['original_video_ids'])>10000:raise ValueError('곡 정보 크기 오류')
        for a in s['aliases']:
            if not isinstance(a,dict) or set(a)!={'title','artist'} or any(not isinstance(a[k],str) or not 1<=len(a[k])<=300 for k in a):raise ValueError('곡 별칭 오류')
        for n in s['numbers']:
            if not isinstance(n,dict) or set(n)!={'brand','no'} or n['brand'] not in ('tj','kumyoung','dam','joysound') or not isinstance(n['no'],str) or not re.fullmatch(r'\d{1,8}(?:-\d{1,3})?',n['no']):raise ValueError('곡 번호 오류')
        if any(not isinstance(v,str) or not re.fullmatch(r'[A-Za-z0-9_-]{11}',v) for v in s['original_video_ids']):raise ValueError('원곡 영상 ID 오류')
        if not isinstance(s['external_ids'],list) or len(s['external_ids'])>20:raise ValueError('음악 DB ID 오류')
        for ext in s['external_ids']:
            if not isinstance(ext,dict) or set(ext)!={'provider','id'} or ext['provider'] not in ('VocaDB','iTunes','MusicBrainz') or not isinstance(ext['id'],str) or not re.fullmatch(r'[a-zA-Z0-9-]{1,64}',ext['id']):raise ValueError('음악 DB ID 오류')
    videos=set()
    for r in doc['mappings']:
        if not isinstance(r,dict) or set(r)!={'video_id','song_id','kind','performer','evidence'}:raise ValueError('영상 연결에 허용하지 않은 항목이 있습니다.')
        if not isinstance(r['video_id'],str) or not re.fullmatch(r'[A-Za-z0-9_-]{11}',r['video_id']) or r['video_id'] in videos or r['song_id'] not in ids:raise ValueError('영상 연결 식별자 오류')
        videos.add(r['video_id'])
        if r['kind'] not in ('original','cover','translation','remix','unknown') or r['evidence'] not in ('manual','verified_auto','native_music_metadata') or not isinstance(r['performer'],str) or len(r['performer'])>100:raise ValueError('영상 버전 정보 오류')
    return doc
def records(doc):
    songs={s['id']:s for s in doc['songs']}
    return [{'video_id':r['video_id'],'title':songs[r['song_id']]['title'],'artist':songs[r['song_id']]['artist'],'aliases':songs[r['song_id']]['aliases'],'numbers':songs[r['song_id']]['numbers'],'evidence':r['evidence'],'shared_song_id':r['song_id'],'shared_kind':r['kind'],'shared_performer':r['performer']} for r in doc['mappings']]
class Resolver:
    def __init__(self,db):
        ensure(db);self.originals=defaultdict(dict);self.labels=defaultdict(dict);self.external=defaultdict(dict);self.known_external={}
        if not db.execute('SELECT 1 FROM shared_knowledge LIMIT 1').fetchone():return
        for row in db.execute("SELECT id,data FROM recognition_results WHERE json_extract(data,'$.track.confident')=1 AND json_extract(data,'$.track.url') IS NOT NULL"):
            ext=external_id(json.loads(row[1]).get('track',{}))
            if ext:self.known_external[row[0]]=ext
        for row in db.execute('SELECT data FROM shared_knowledge'):
            doc=json.loads(row[0])
            for s in doc['songs']:
                for vid in s['original_video_ids']:self.originals[vid][s['id']]=s
                for a in [s]+s['aliases']:self.labels[(core.norm(a['title']),core.norm(core.number_artist(a['artist'])))][s['id']]=s
                for ext in s['external_ids']:self.external[(ext['provider'],ext['id'])][s['id']]=s
    def resolve(self,v):
        raw=v.get('title') or v.get('history_title','')
        if re.search(r'(?i)歌枠|playlist|medley|メドレー|모음|tutorial|레슨|리믹스|remix|매시업|mashup',raw):return None
        refs=recognition.original_links(v.get('description',''));matches={};basis=''
        ext=self.known_external.get(v.get('video_id'))
        if ext:matches.update(self.external.get((ext['provider'],ext['id']),{}));basis='external_id'
        if len(refs)==1:
            for sid,s in self.originals.get(refs[0]['video_id'],{}).items():
                agrees=any(len(core.norm(a['title']))>=3 and core.norm(a['title']) in core.norm(raw) for a in [s]+s['aliases'])
                translation=bool(re.search(r'(?i)\[(?:자막|한글화)\]|ENG SUB|English Subbed',raw)) and not re.search(r'(?i)cover|커버|歌ってみた|합성|패러디|소스',raw+'\n'+v.get('description',''))
                if agrees or translation:matches[sid]=s;basis='original_link'
        if not matches:
            channel=recognition.artist_name(v.get('channel') or v.get('history_channel',''));pairs=[]
            for card in v.get('music_metadata',{}).get('cards',[]):
                if len(v['music_metadata']['cards'])==1:pairs.append((card['title'],card['artist']))
            m=re.match(r'^(.+?)\s+[-–—]\s+(.+)$',raw)
            if m and core.norm(recognition.artist_name(m[1]))==core.norm(channel):pairs.append((m[2],channel))
            quoted=re.findall(r'[「『]([^」』]+)[」』]',raw)
            if len(quoted)==1:pairs.append((quoted[0],channel))
            for title,artist in pairs:
                if len(core.norm(title))>=3 and core.norm(title) in core.norm(raw):matches.update(self.labels.get((core.norm(title),core.norm(core.number_artist(artist))),{}))
            if matches:basis='title_artist_alias'
        # Distinct peers can describe the same pair with different IDs.
        groups=[]
        for s in matches.values():
            keys={(core.norm(a['title']),core.norm(core.number_artist(a['artist']))) for a in [s]+s['aliases']}
            overlap=[g for g in groups if keys.intersection(g['keys'])]
            if not overlap:groups.append({'keys':keys,'song':s})
            else:
                group=overlap[0];group['keys'].update(keys)
                for other in overlap[1:]:group['keys'].update(other['keys']);groups.remove(other)
        if len(groups)!=1:return None
        s=groups[0]['song']
        return {'title':s['title'],'artist':s['artist'],'aliases':s['aliases'],'numbers':s['numbers'],'shared_song_id':s['id'],'shared_basis':basis}
