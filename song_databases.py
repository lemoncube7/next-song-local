"""Cached song metadata from public databases. No account data or audio uploads."""
import json,re,time,threading,urllib.request,urllib.parse,urllib.error
from datetime import datetime,timezone,timedelta
import core

LOCK=threading.Lock()
LAST={}
BACKOFF={}
INTERVAL={'VocaDB':1.1,'MusicBrainz':1.1,'iTunes':3.1}
ROOTS={'VocaDB':'https://vocadb.net/api/','MusicBrainz':'https://musicbrainz.org/ws/2/','iTunes':'https://itunes.apple.com/'}

def request(db,provider,path,params,write_lock):
    key='song_db|'+provider+'|'+path+'|'+json.dumps(params,sort_keys=True,ensure_ascii=False)
    row=db.execute('SELECT data FROM queries WHERE key=?',(key,)).fetchone();now=datetime.now(timezone.utc)
    if row:
        old=json.loads(row[0]);ttl=timedelta(days=7) if old['status']=='ok' else timedelta(minutes=30)
        if now-datetime.fromisoformat(old['checked_at'])<ttl:return {**old,'cached':True}
    with LOCK:
        if BACKOFF.get(provider,0)>time.monotonic():return {'provider':provider,'status':'unavailable','reason':'조회 실패 후 잠시 대기 중','data':None}
        time.sleep(max(0,INTERVAL[provider]-(time.monotonic()-LAST.get(provider,0))))
        result={'provider':provider,'checked_at':now.isoformat(),'status':'ok','data':None}
        try:
            req=urllib.request.Request(ROOTS[provider]+path+'?'+urllib.parse.urlencode(params),headers={'Accept':'application/json','User-Agent':'LocalKaraoke/1.0 (local noncommercial song metadata)'})
            with urllib.request.urlopen(req,timeout=12) as response:result['data']=json.loads(response.read(2*1024*1024))
        except (OSError,ValueError) as exc:
            result.update(status='unavailable',reason='HTTP '+str(exc.code) if isinstance(exc,urllib.error.HTTPError) else type(exc).__name__)
            BACKOFF[provider]=time.monotonic()+1800
        finally:LAST[provider]=time.monotonic()
    with write_lock:
        db.execute('INSERT OR REPLACE INTO queries VALUES (?,?)',(key,json.dumps(result,ensure_ascii=False)));db.commit()
    return result

def clean_title(title):
    return re.sub(r'\s*[（(](?:feat\.?|ft\.?)\s*[^)）]+[)）]\s*$','',title,flags=re.I).strip()

def voca_candidate(song,video_id):
    names=song.get('names',[]);title=next((n['value'] for n in names if n.get('language')=='Japanese'),song.get('name',''))
    artists=[a for a in song.get('artists',[]) if 'Producer' in str(a.get('categories','')) and 'Arranger' not in str(a.get('effectiveRoles',''))]
    human_vocal=any('Vocalist' in str(a.get('categories','')) and a.get('artist',{}).get('artistType') not in ('Vocaloid','UTAU','SynthesizerV','CeVIO') for a in song.get('artists',[]))
    artist=', '.join(a.get('name') or a.get('artist',{}).get('name','') for a in artists) or song.get('artistString','')
    pvs=song.get('pvs',[]);exact=any(p.get('service')=='Youtube' and p.get('pvId')==video_id for p in pvs)
    return {'title':title,'artist':core.canonical(artist),'provider':'VocaDB','url':'https://vocadb.net/S/'+str(song['id']),
            'reason':'VocaDB에 연결된 영상 ID 일치' if exact else 'VocaDB 곡명·별칭 검색 결과',
            'confident':exact and song.get('songType')=='Original' and not human_vocal,
            'alternate_labels':[{'title':n['value'],'artist':artist} for n in names if n.get('value')]}

def search(db,video,write_lock):
    raw=video.get('title') or video.get('history_title','');cards=video.get('music_metadata',{}).get('cards',[])
    import music_metadata
    risky=music_metadata.risky_video(video)
    inputs=[(c['title'],c['artist']) for c in cards[:1]]
    if inputs and risky:
        q=re.search(r'[「『]([^」』]+)[」』]',inputs[0][0])
        if q and '/' in q[1]:inputs=[tuple(p.strip() for p in q[1].split('/',1))]
    quoted=re.findall(r'[「『]([^」』]+)[」』]',raw)
    if not inputs and (quoted or video.get('classification',{}).get('status')=='review'):
        title=quoted[0] if len(quoted)==1 else re.split(r'[/／]|\s+-\s+',raw)[0]
        title=re.sub(r'^\[[^]]+\]|^【[^】]+】','',title).strip()
        if 2<=len(title)<=100:inputs.append((title,''))
    if not cards and inputs:
        structured=re.match(r'^(.+?)\s+-\s+(.+)$',raw)
        if structured:
            performer=structured[1].split('&')[0].strip()
            song=re.split(r'[/／]|\s+-\s+',structured[2])[0]
            song=re.sub(r'(?i)\s*(?:\([^)]*(?:remix|cover)[^)]*\)|\b(?:ft|feat)\..*)$','',song).strip()
            if song:inputs=[(song,performer)]
    candidates=[];attempts=[]
    v=request(db,'VocaDB','songs/byPv',{'pvService':'Youtube','pvId':video['video_id'],'fields':'Names,Artists,PVs','lang':'Japanese'},write_lock)
    attempts.append({k:v[k] for k in ('provider','status','reason','cached') if k in v})
    if v['status']=='ok' and v['data']:candidates.append(voca_candidate(v['data'],video['video_id']))
    if inputs:
        title,artist=inputs[0]
        if not candidates and v['status']=='ok':
            v=request(db,'VocaDB','songs',{'query':title,'fields':'Names,Artists,PVs','lang':'Japanese','maxResults':5},write_lock)
            attempts.append({k:v[k] for k in ('provider','status','reason','cached') if k in v})
            if v['status']=='ok':candidates.extend(voca_candidate(s,video['video_id']) for s in (v['data'] or {}).get('items',[]))
        term=' '.join([title,artist]).strip()
        store='KR' if re.search(r'[가-힣]',title) else 'JP'
        apple=request(db,'iTunes','search',{'term':term,'entity':'song','country':store,'lang':'ja_jp','limit':5},write_lock)
        attempts.append({k:apple[k] for k in ('provider','status','reason','cached') if k in apple})
        if apple['status']=='ok':
            alias_lookups=0
            for row in (apple['data'] or {}).get('results',[]):
                if row.get('kind')!='song':continue
                native=clean_title(row['trackName']);performer=row['artistName'];agrees=bool(artist and core.norm(core.canonical(artist))==core.norm(core.canonical(performer)))
                version=r'(?i)\blive\b|instrumental|karaoke|remix|ライブ|반주'
                if re.search(version,native) and not re.search(version,raw):continue
                forms={core.norm(native),core.norm(re.sub(r'[（(][ぁ-んー]+[)）]$','',native))}
                title_agrees=core.norm(title) in forms or any(len(t)>=2 and t in core.norm(raw) for t in forms)
                english_alias=None
                if not title_agrees and agrees and row.get('trackId') and alias_lookups<2:
                    alias_lookups+=1
                    translated=request(db,'iTunes','lookup',{'id':row['trackId'],'country':store,'lang':'en_us'},write_lock)
                    if translated['status']=='ok':
                        paired=next((a for a in (translated['data'] or {}).get('results',[]) if a.get('trackId')==row['trackId']),None)
                        if paired and core.norm(clean_title(paired.get('trackName','')))==core.norm(title):
                            english_alias={'title':paired['trackName'],'artist':paired['artistName']};title_agrees=True
                roman_suggestion=bool(cards and agrees and re.fullmatch(r'[A-Za-z0-9 ._!?\-]+',title) and len(title)>=6)
                if (not title_agrees and not roman_suggestion) or (artist and not agrees):continue
                candidate={'title':native,'artist':core.canonical(performer),'provider':'iTunes','url':row['trackViewUrl'],
                           'reason':'iTunes 일본어 카탈로그 검색 결과 — 로마자 표기와 대조 필요' if not title_agrees else 'iTunes 일본어 카탈로그 검색 결과','confident':not risky and len(cards)==1 and agrees and title_agrees and core.norm(native) in core.norm(raw),
                           'alternate_labels':[{'title':row['trackName'],'artist':performer}]}
                # A search hit alone does not establish that the English query is an alias.
                if candidate['confident']:candidate['alternate_labels'].append({'title':title,'artist':artist})
                if english_alias:candidate['alternate_labels'].append(english_alias)
                candidates.append(candidate)
        escape=lambda s:s.replace('\\','\\\\').replace('"','\\"')
        query='recording:"'+escape(title)+'"'+(' AND artist:"'+escape(artist)+'"' if artist else '')
        mb=request(db,'MusicBrainz','recording',{'query':query,'fmt':'json','limit':5},write_lock)
        attempts.append({k:mb[k] for k in ('provider','status','reason','cached') if k in mb})
        if mb['status']=='ok':
            for row in (mb['data'] or {}).get('recordings',[]):
                performer=''.join(a.get('name',a.get('artist',{}).get('name',''))+a.get('joinphrase','') for a in row.get('artist-credit',[]) if isinstance(a,dict))
                if core.norm(row['title'])!=core.norm(title):continue
                if artist and core.norm(core.canonical(artist))!=core.norm(core.canonical(performer)):continue
                candidates.append({'title':row['title'],'artist':performer,'provider':'MusicBrainz','url':'https://musicbrainz.org/recording/'+row['id'],'reason':'MusicBrainz 음원 검색 결과','confident':False})
    import recognition
    candidates=recognition.merge_candidates(candidates)
    strong=[c for c in candidates if c.get('confident')]
    if len(strong)==1 and not risky:return {'status':'recognized','track':strong[0],'candidates':candidates,'databases':attempts}
    return {'status':'ambiguous' if candidates else 'unresolved','candidates':candidates,'reason':'음악 데이터베이스 검색 후보를 확인해 주세요.' if candidates else '음악 데이터베이스에서도 확실한 곡 정보를 찾지 못했어요.','databases':attempts}
