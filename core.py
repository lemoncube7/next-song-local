"""Local watch-history recommendation engine. Standard library only."""
import csv, hashlib, io, json, math, re, sqlite3, unicodedata, zipfile, sys, urllib.parse
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from functools import lru_cache

ROOT = Path(sys.executable).resolve().parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parent
DB = ROOT / 'data' / 'karaoke.sqlite3'
ARTIST_GROUPS = [
    ['ヨルシカ', 'Yorushika', '요루시카'],
    ['ずっと真夜中でいいのに。', 'ZUTOMAYO', 'ずっと真夜中でいいのに', 'ずっと真夜中でいいのに。 ZUTOMAYO'],
    ['結束バンド', 'kessoku band', '결속밴드'],
    ['稲葉曇', 'inabakumori', '이나바쿠모리'],
    ['音乃瀬奏', 'Otonose Kanade'], ['てにをは', 'teniwoha'],
    ['ツミキ', 'tsumiki'], ['かいりきベア', 'Kairiki bear'],
    ['星街すいせい', 'Hoshimachi Suisei', '호시마치 스이세이'],
    ['なとり', 'natori'], ['青谷', 'AOYA', 'Aoya'],
    ['いよわ', 'Iyowa'], ['n-buna', 'N-buna'],
    ['米津玄師', 'Kenshi Yonezu'], ['サカナクション', 'sakanaction'],
    ['キタニタツヤ', 'Tatsuya Kitani'], ['실리카겔', 'Silica Gel'],
    ['하현상', 'Ha Hyunsang', '하현상 HA HYUN SANG', '하현상 (Ha Hyunsang)'],
    ['柊マグネタイト', 'Hiiragi Magnetite'], ['shr', 'shr VOCALOID channel'],
]
TITLE_HINTS = {'flowerandbadgergame': '花人局'}
@lru_cache(maxsize=100000)
def norm(s):
    return ''.join(c for c in unicodedata.normalize('NFKC', str(s)).casefold() if c.isalnum())
@lru_cache(maxsize=10000)
def canonical(s):
    # Auto-generated credits repeat the same person for multiple roles.
    # Deduplicate explicit credit separators, retaining distinct collaborators.
    s=unicodedata.normalize('NFKC',str(s)).strip()
    parts=[p.strip() for p in re.split(r'\s*[·•]\s*|\s+・\s+',s) if p.strip()]
    if len(parts)>1:
        unique=[];seen=set()
        for part in parts:
            value=canonical(part);key=norm(value)
            if key not in seen:unique.append(value);seen.add(key)
        return ' · '.join(unique)
    for group in ARTIST_GROUPS:
        if norm(s) in {norm(x) for x in group}: return group[0]
    return s.strip()
def clean_title(s):
    s = re.sub(r'\s*을\(를\) 시청했습니다\.?$', '', s)
    s = re.sub(r'^Watched\s+', '', s)
    return s.strip()
def regular_song(video):
    """Conservative title rules for ordinary YouTube originals and artist videos."""
    title=unicodedata.normalize('NFKC',video.get('title') or video.get('history_title',''))
    channel=video.get('channel') or video.get('history_channel','')
    if not title or not channel:return None
    if re.search(r'(?i)cover|歌ってみた|歌枠|shorts?|커버|모음|メドレー|medley|playlist',title):return None
    if len(re.findall(r'[/／]',title))>=3:return None
    if video.get('category')!='Music':return None
    artist=canonical(channel.split(' / ')[0].strip())
    marker=bool(re.search(r'(?i)official (?:music )?video|music video|[【\[]MV[】\]]|オリジナル|\boriginal\b',title))
    text=re.sub(r'^[【\[][^】\]]+[】\]]\s*','',title).strip()
    if 'オリジナル' in title and '初音ミク' in title and 'n-buna' in channel:artist='n-buna'
    quoted=re.search(r'[「『]([^」』]+)[」』]',title) if marker else None
    if quoted:
        text=quoted.group(1).strip()
        prefix=title[:quoted.start()].strip()
        if prefix and norm(prefix) in norm(channel):artist=canonical(prefix)
        elif not re.search(r'(?i)official (?:music )?video|music video',title) and not title.startswith('【'):
            return None
    # Only strip an explicit uploader/artist prefix; arbitrary dashed titles stay intact.
    prefix=re.match(r'^(.{1,80}?)\s+[-–—]\s+(.+)$',text)
    explicit=False
    if prefix and norm(canonical(prefix.group(1)))==norm(artist):
        text=prefix.group(2).strip();explicit=True
    elif not marker:return None
    # Full-width separators are common in original vocal-synth video titles.
    if marker and not explicit and not quoted:
        text=re.split(r'\s*[/／]\s*',text,maxsplit=1)[0].strip()
    text=re.sub(r'(?i)\s*(?:[（(\[【［]\s*)?(?:official\s+(?:music\s+)?video|music\s+video|オリジナル|original)[^\n]*$','',text).strip()
    text=re.sub(r'(?i)\s*[（(]\s*(?:feat\.|feat\b|ft\.)[^）)]*[）)]\s*','',text).strip()
    text=re.sub(r'\s*[【\[［](?:オリジナル|MV|Official)[^】\]］]*[】\]］]\s*','',text,flags=re.I).strip()
    text=re.split(r'\s+[/／]\s*(?:可不|初音ミク|IA\b|鏡音|重音テト|feat\.)',text,maxsplit=1,flags=re.I)[0].strip()
    text=re.sub(r'(?i)\s+M/V$','',text).strip()
    if norm(text) in ('初音ミク','original','mv','short'):return None
    if not text or len(text)>120 or norm(text)==norm(artist):return None
    if not explicit and not marker:return None
    return {'status':'song','title':text,'artist':artist,'source':'video_title','reason':'Music 영상의 아티스트 표기 또는 원곡·MV 제목 규칙'}
def time_weight(days, scale):
    """A logarithmic tail retains familiarity from older listening history."""
    return 1 / (1 + math.log1p(max(0, days) / scale))

def timestamp(s):
    return datetime.fromisoformat(s.replace('Z', '+00:00')).timestamp()
def connect(path=None):
    p = Path(path or DB); p.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(p, timeout=30); db.row_factory = sqlite3.Row
    db.execute('PRAGMA journal_mode=WAL')
    db.executescript('''
      CREATE TABLE IF NOT EXISTS events (key TEXT PRIMARY KEY, video_id TEXT, time TEXT NOT NULL, url TEXT, title TEXT);
      CREATE INDEX IF NOT EXISTS events_video ON events(video_id);
      CREATE TABLE IF NOT EXISTS event_details (key TEXT PRIMARY KEY, data TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS recognition_results (id TEXT PRIMARY KEY, data TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS videos (id TEXT PRIMARY KEY, data TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS library (id TEXT PRIMARY KEY, data TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS catalogue (brand TEXT, no TEXT, data TEXT NOT NULL, PRIMARY KEY(brand,no));
      CREATE TABLE IF NOT EXISTS queries (key TEXT PRIMARY KEY, data TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS tracks (id TEXT PRIMARY KEY, data TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS user_state (key TEXT PRIMARY KEY, data TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS shared_records (path TEXT, video_id TEXT, data TEXT, PRIMARY KEY(path,video_id));
      CREATE TABLE IF NOT EXISTS shared_identities (id TEXT PRIMARY KEY,data TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS shared_conflicts (id TEXT PRIMARY KEY,data TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, data TEXT NOT NULL);
    ''')
    import video_index
    video_index.ensure(db)
    return db
def get_state(db, key, default=None, table='state'):
    assert table in ('state', 'user_state')
    r = db.execute(f'SELECT data FROM {table} WHERE key=?', (key,)).fetchone()
    return json.loads(r[0]) if r else default
def set_state(db, key, value, table='state'):
    assert table in ('state', 'user_state')
    serialized=json.dumps(value,ensure_ascii=False)
    previous=db.execute(f'SELECT data FROM {table} WHERE key=?',(key,)).fetchone() if table=='user_state' and key in ('corrections','numbers','song_aliases') else None
    db.execute(f'INSERT OR REPLACE INTO {table} VALUES (?,?)', (key, serialized))
    if table=='user_state' and key in ('corrections','numbers','song_aliases') and (not previous or previous[0]!=serialized):
        import github_sync
        github_sync.notify()
def video_data(db, vid):
    r=db.execute('SELECT data FROM videos WHERE id=?',(vid,)).fetchone()
    return json.loads(r[0]) if r else None
def save_video(db, data):
    db.execute('INSERT OR REPLACE INTO videos VALUES (?,?)',(data['video_id'], json.dumps(data,ensure_ascii=False)))
def import_bytes(db, content, filename):
    if len(content)>100*1024*1024: raise ValueError('파일은 100MB 이하로 가져올 수 있습니다.')
    library=[];html_report={}
    if content[:2]==b'PK':
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            entries=[n for n in z.namelist() if n.endswith(('/시청 기록.json','/watch-history.json'))]
            html_entries=[n for n in z.namelist() if n.rsplit('/',1)[-1].lower() in ('내활동.html','내 활동.html','myactivity.html','my-activity.html','watch-history.html','시청 기록.html')]
            if not entries and not html_entries: raise ValueError('ZIP에서 JSON 또는 HTML 시청 기록을 찾지 못했습니다.')
            selected=entries or html_entries
            if sum(z.getinfo(n).file_size for n in selected)>512*1024*1024: raise ValueError('압축 해제된 기록이 512MB를 넘습니다.')
            rows=[]
            for n in entries: rows.extend(json.loads(z.read(n)))
            if not entries:
                import takeout_html
                for n in html_entries:
                    with z.open(n) as stream:rows.extend(takeout_html.iter_rows(stream,html_report))
            for n in z.namelist():
                if n.endswith('music library songs.csv'):
                    if z.getinfo(n).file_size>20*1024*1024: raise ValueError('라이브러리 파일이 너무 큽니다.')
                    library.extend(csv.DictReader(io.StringIO(z.read(n).decode('utf-8-sig'))))
    elif filename.lower().endswith('.html'):
        import takeout_html
        rows=list(takeout_html.iter_rows(io.BytesIO(content),html_report))
    else: rows=json.loads(content.decode('utf-8-sig'))
    import spotify_import
    if spotify_import.supported(rows):return spotify_import.load(db,rows,filename)
    if not isinstance(rows,list): raise ValueError('시청 기록은 JSON 배열이어야 합니다.')
    before=db.execute('SELECT COUNT(*) FROM events').fetchone()[0]
    skipped=0
    # HTML loses milliseconds; reconcile against pre-existing activities by second.
    coarse={(r['video_id'] or r['url'] or r['title'],r['time'][:19]):r['key'] for r in db.execute('SELECT key,video_id,url,title,time FROM events')} if html_report else {}
    cached_videos={}
    for row in rows:
        if not isinstance(row,dict) or not row.get('time'): skipped+=1; continue
        try: timestamp(row['time'])
        except (ValueError,TypeError): skipped+=1; continue
        url=row.get('titleUrl',''); m=re.search(r'(?:[?&]v=|youtu\.be/)([\w-]{11})',url)
        vid=m.group(1) if m else None
        # Same video/time or same nonvideo URL/time is the same activity across imports.
        key=hashlib.sha256((row['time']+'|'+(vid or url or row.get('title',''))).encode()).hexdigest()
        if row.get('_time_precision')=='second':key=coarse.get(((vid or url or row.get('title','')),row['time'][:19]),key)
        db.execute('INSERT OR IGNORE INTO events VALUES (?,?,?,?,?)',(key,vid,row['time'],url,row.get('title','')))
        products=row.get('products',[])
        if not isinstance(products,list):products=[]
        music_source=urllib.parse.urlparse(url).hostname=='music.youtube.com' or row.get('header','').casefold()=='youtube music' or any(str(p).casefold()=='youtube music' for p in products)
        platform='youtube_music' if music_source else 'youtube'
        previous=db.execute('SELECT data FROM event_details WHERE key=?',(key,)).fetchone()
        if previous and json.loads(previous[0]).get('platform')=='youtube_music':platform='youtube_music';music_source=True
        db.execute('INSERT OR REPLACE INTO event_details VALUES (?,?)',(key,json.dumps({'platform':platform},ensure_ascii=False)))
        if vid:
            if vid not in cached_videos:cached_videos[vid]=video_data(db,vid) or {'video_id':vid,'metadata_status':'pending'}
            data=cached_videos[vid]
            data['history_title']=clean_title(row.get('title',''))
            data['history_channel']=' '.join(x.get('name','') for x in row.get('subtitles',[]) if isinstance(x,dict))
            data['source_platforms']=sorted(set(data.get('source_platforms',[])+[platform]))
            if music_source:data['music_service_origin']=True
    for data in cached_videos.values():save_video(db,data)
    for row in library:
        vid=row.get('동영상 ID',row.get('Video ID','')).strip()
        if not re.fullmatch(r'[\w-]{11}',vid): continue
        data={'title':row.get('Song Title',''),'artist':row.get('Artist Name 1',''),'album':row.get('Album Title','')}
        db.execute('INSERT OR REPLACE INTO library VALUES (?,?)',(vid,json.dumps(data,ensure_ascii=False)))
    after=db.execute('SELECT COUNT(*) FROM events').fetchone()[0]
    result={'filename':Path(filename).name,'input_records':len(rows),'new_records':after-before,'duplicate_records':len(rows)-skipped-(after-before),'skipped_records':skipped,'total_records':after,'imported_at':datetime.now(timezone.utc).isoformat()}
    if html_report:result.update({'html_activity_counts':html_report,'time_precision':'second','deduplication':'existing video/url + UTC second; original millisecond times preserved'})
    imports=get_state(db,'imports',[]); imports.append(result);set_state(db,'imports',imports[-20:]);db.commit()
    return result
def classify(video, library=None, correction=None, shared=None):
    title=video.get('title') or video.get('history_title','')
    channel=video.get('channel') or video.get('history_channel','')
    desc=video.get('description','')
    if correction:
        if correction.get('exclude'): return {'status':'excluded','reason':'직접 제외'}
        return {'status':'song','title':correction['title'],'artist':canonical(correction['artist']),'source':'auto_recognition' if correction.get('source')=='auto_recognition' else 'manual','reason':correction.get('reason') or '직접 확인한 곡'}
    if video.get('source_platform')=='spotify':
        song=video['spotify_identity']
        return {'status':'song','title':song['title'],'artist':canonical(song['artist']),'source':'spotify','reason':'Spotify 기록의 곡명·아티스트'}
    if library and library.get('title') and library.get('artist'):
        return {'status':'song','title':library['title'],'artist':canonical(library['artist']),'source':'library','reason':'Takeout 라이브러리의 영상 ID 일치'}
    if shared:
        basis=shared.get('shared_basis','video_id')
        return {'status':'song','title':shared['title'],'artist':canonical(shared['artist']),'source':'shared','shared_basis':basis,'shared_song_id':shared.get('shared_song_id',''),'shared_kind':shared.get('shared_kind','unknown'),'shared_performer':shared.get('shared_performer',''),'reason':{'video_id':'공유된 확정 곡 정보의 영상 ID 일치','original_link':'공유된 원곡 링크와 곡 정보 일치','title_artist_alias':'공유된 제목 별칭·아티스트 일치','external_id':'공유된 음악 DB 곡 ID 일치'}.get(basis,'공유된 확정 곡 정보')}
    if 'Provided to YouTube by ' in desc and 'Auto-generated by YouTube.' in desc:
        line=next((s.strip() for s in desc.splitlines() if ' · ' in s),None)
        if line:
            song,artist=line.split(' · ',1)
            return {'status':'song','title':song,'artist':canonical(artist),'source':'auto_generated','reason':'음원 자동 생성 설명의 곡명·아티스트'}
    # Topic channels provide music identity even if the public page omitted microformat.
    if channel.endswith(' - Topic') and norm(channel[:-8]) in ('release','stations','variousartists','unknown'):
        return {'status':'review','reason':'공용 Topic 채널 — 실제 아티스트 확인 필요'}
    if channel.endswith(' - Topic') and title and not title.startswith('https://'):
        return {'status':'song','title':title,'artist':canonical(channel[:-8]),'source':'topic','reason':'음원 Topic 채널의 제목·아티스트'}
    ordinary=regular_song(video)
    if ordinary:return ordinary
    import non_song
    if non_song.valid(video):return {'status':'non_song','source':'automatic_non_song','reason':video['non_song']['reason']}
    import recognition
    signals=bool(re.search(r'(?i)\bofficial\s+(?:music\s+)?video\b|\bofficial\s+mv\b|\blyric\s+video\b|\bcover\b|歌ってみた|歌枠|作詞|作曲|デモソング|music video|뮤직비디오|커버|가사|노래',title+'\n'+desc[:1800])) or bool(recognition.original_links(desc))
    if video.get('category')=='Music' or signals:
        return {'status':'review','reason':'음악 관련 영상 — 곡 정보 확인 필요'}
    if video.get('music_service_origin'):
        return {'status':'review','music_presence':'service_origin','reason':'YouTube Music 재생 출처 확인 — 곡명·아티스트 또는 음원 종류 확인 필요'}
    if not video.get('category'):
        return {'status':'unknown','reason':'카테고리 미확인 — 음악 여부 미판정'}
    return {'status':'other','reason':'음악 곡 정보가 확인되지 않은 영상'}
@lru_cache(maxsize=10000)
def catalogue_title(s):
    # Strip explicit feat/OST qualifiers, not arbitrary distinguishing title parentheses.
    return re.sub(r'(?i)[（(](?:feat\.?|ft\.?|.*?OST|영화|드라마|애니메이션|만화).*?[）)]','',s).strip()
@lru_cache(maxsize=10000)
def artist_base(s):
    return canonical(re.sub(r'(?i)\s*(?:[（(]\s*)?(?<![A-Za-z])(?:feat\.|feat\b|ft\.|ft\b)\s*.*$','',s).strip())

def number_artist(s):
    value=artist_base(s)
    for group in [['女王蜂','QUEEN BEE'],['バルーン','balloon'],['ぬゆり','nulut','Lanndo'],['しがない高校生','Shiganaikoukousei']]:
        if norm(value) in {norm(a) for a in group}:return group[0]
    return value
def match_track(track, catalogue, reference):
    exact=[];candidates=[]
    import song_labels
    title_keys={norm(t) for t in song_labels.variants(track['title'])}
    nt=norm(catalogue_title(track['title']));na=norm(canonical(track['artist']))
    hint=TITLE_HINTS.get(nt)
    for row in catalogue:
        rt=norm(catalogue_title(row.get('title','')))
        row_keys={norm(t) for t in song_labels.variants(row.get('title',''))}
        if not title_keys.intersection(row_keys) and rt!=(norm(hint) if hint else ''):continue
        match={'brand':row['brand'],'no':str(row['no']),'title':row['title'],'artist':row['singer'],'source':row.get('source','manana'),'release':row.get('release',''),'official_verified':False}
        release=row.get('release','')
        # Catalogues may include announced future entries. Do not offer these as available.
        if release and release[:10]>reference[:10]: match['reason']='수록 예정';candidates.append(match);continue
        if title_keys.intersection(row_keys) and norm(number_artist(row['singer']))==norm(number_artist(track['artist'])):
            if norm(canonical(row['singer']))!=na:match['reason']='기본 아티스트 일치 · 피처링 표기 차이'
            exact.append(match)
        else:
            match['reason']='제목 별칭 확인 필요' if hint and rt==norm(hint) else '동명곡·커버 아티스트 확인 필요'
            candidates.append(match)
    return exact,candidates
def rebuild(db, affected_video=None):
    import song_identity,song_labels
    aliases=get_state(db,"song_aliases",{},"user_state")
    events=defaultdict(list)
    for r in db.execute('SELECT video_id,time FROM events WHERE video_id IS NOT NULL'):events[r['video_id']].append(r['time'])
    activity_details=defaultdict(dict)
    for row in db.execute("""SELECT e.video_id,COALESCE(json_extract(d.data,'$.platform'),CASE WHEN e.video_id LIKE 'spotify:%' THEN 'spotify' WHEN e.url LIKE 'https://music.youtube.com/%' THEN 'youtube_music' ELSE 'youtube' END) AS platform,
      count(*) AS records,sum(COALESCE(json_extract(d.data,'$.played_ms'),0)) AS played_ms,
      sum(CASE WHEN json_type(d.data,'$.played_ms')='integer' THEN 1 ELSE 0 END) AS duration_known_records,
      sum(CASE WHEN json_extract(d.data,'$.skipped')=1 THEN 1 ELSE 0 END) AS skipped_records,
      sum(CASE WHEN json_type(d.data,'$.skipped') IN ('true','false') THEN 1 ELSE 0 END) AS skip_known_records
      FROM events e LEFT JOIN event_details d ON d.key=e.key WHERE e.video_id IS NOT NULL GROUP BY e.video_id,platform"""):
        activity_details[row['video_id']][row['platform']]={k:row[k] for k in ('records','played_ms','duration_known_records','skipped_records','skip_known_records')}
    libraries={r['id']:json.loads(r['data']) for r in db.execute('SELECT * FROM library')}
    shared={r['id']:json.loads(r['data']) for r in db.execute('SELECT * FROM shared_identities')}
    rejected=get_state(db,'shared_rejections',{},'user_state')
    shared={vid:s for vid,s in shared.items() if vid not in rejected}
    corrections=get_state(db,'corrections',{},'user_state')
    import shared_knowledge
    resolver=shared_knowledge.Resolver(db)
    def shared_for(vid,data):
        if vid in shared:return shared[vid]
        if vid in corrections or vid in rejected or not resolver.labels:return None
        return resolver.resolve(data)
    affected_groups=None
    if affected_video is not None:
        changed=video_data(db,affected_video)
        changed['classification']=classify(changed,libraries.get(affected_video),corrections.get(affected_video),shared_for(affected_video,changed))
        save_video(db,changed)
        affected_groups={json.loads(r[0])['id'] for r in db.execute('SELECT data FROM tracks') if affected_video in json.loads(r[0]).get('video_ids',[])}
        c=changed['classification']
        if c['status']=='song':
            original=song_identity.identity(c['title'],c['artist'])
            tid=song_identity.identity(song_identity.presentation_title(c['title']),canonical(c['artist']))
            if original in aliases:tid=song_identity.resolve(original,song_identity.presentation_title(c['title']),canonical(c['artist']),aliases)[0]
            affected_groups.add(tid)
    catalogue=[json.loads(r[0]) for r in db.execute('SELECT data FROM catalogue')]
    catalogue_by_title=defaultdict(list)
    for row in catalogue:
        for label in song_labels.variants(row.get('title','')):catalogue_by_title[norm(label)].append(row)
    reference=db.execute('SELECT MAX(time) FROM events').fetchone()[0] or datetime.now(timezone.utc).isoformat()
    ref=timestamp(reference);groups={};statuses=Counter()
    for r in db.execute("SELECT * FROM videos" if affected_groups is None else "SELECT v.* FROM videos v JOIN video_browse b ON b.id=v.id WHERE b.status='song'").fetchall():
        data=json.loads(r['data']);previous=data.get('classification',{});received=shared_for(r['id'],data);classification=classify(data,libraries.get(r['id']),corrections.get(r['id']),received)
        same_shared=previous.get('source')==classification.get('source')=='shared' and bool(received) and (bool(previous.get('shared_song_id')) and previous.get('shared_song_id')==classification.get('shared_song_id') or any(norm(a['title'])==norm(previous.get('title','')) and norm(canonical(a['artist']))==norm(canonical(previous.get('artist',''))) for a in received.get('aliases',[])))
        if previous.get('status')=='song' and classification.get('status')=='song' and (same_shared or norm(previous.get('title',''))==norm(classification.get('title','')) and norm(canonical(previous.get('artist','')))==norm(canonical(classification.get('artist','')))):
            if previous.get('artist')!=classification.get('artist') or previous.get('title')!=classification.get('title'):
                labels=data.setdefault('classification_identity_aliases',[]);label={'title':previous['title'],'artist':previous['artist']}
                if label not in labels:labels.append(label)
        elif previous!=classification:data.pop('classification_identity_aliases',None)
        if data.get('classification')!=classification:
            data['classification']=classification;save_video(db,data)
        # Metadata-only reference videos are not watched recommendations.
        if r['id'] not in events:continue
        statuses[classification['status']]+=1
        if classification['status']!='song':continue
        original=song_identity.identity(classification['title'],classification['artist'])
        title=song_identity.presentation_title(classification['title'])
        artist=canonical(classification['artist'])
        tid=song_identity.identity(title,artist)
        tid,title,artist=song_identity.resolve(original,title,artist,aliases) if original in aliases else song_identity.resolve(tid,title,artist,aliases)
        artist=canonical(artist)
        if affected_groups is not None and tid not in affected_groups:continue
        g=groups.setdefault(tid,{'id':tid,'title':title,'artist':artist,'member_ids':[],'aliases':[],'video_ids':[],'dates':[],'sources':[]})
        g['member_ids']=list(dict.fromkeys(g['member_ids']+[original,tid]))
        for old_label in data.get('classification_identity_aliases',[]):
            member=song_identity.identity(old_label['title'],old_label['artist'])
            if member not in g['member_ids']:g['member_ids'].append(member)
        label={'title':classification['title'],'artist':classification['artist']}
        if label not in g['aliases']:g['aliases'].append(label)
        for alternate in corrections.get(r['id'],{}).get('alternate_labels',[]):
            if alternate not in g['aliases']:g['aliases'].append(alternate)
        for alternate in (received or {}).get('aliases',[]):
            if alternate not in g['aliases']:g['aliases'].append(alternate)
            alias_id=song_identity.identity(alternate['title'],alternate['artist'])
            if alias_id not in g['member_ids']:g['member_ids'].append(alias_id)
        for alternate in song_labels.video_labels(data,{'title':classification['title'],'artist':classification['artist'],'aliases':g['aliases']}):
            if alternate not in g['aliases']:g['aliases'].append(alternate)
        g['video_ids'].append(r['id']);g['dates'].extend(events[r['id']]);g['sources'].append(classification['source'])
        for platform,details in activity_details[r['id']].items():
            aggregate=g.setdefault('listening_details',{}).setdefault(platform,{k:0 for k in details})
            for key,value in details.items():aggregate[key]+=value
        if data.get('spotify_identity'):
            recording={**data['spotify_identity'],'video_id':r['id']}
            if recording not in g.setdefault('recordings',[]):g['recordings'].append(recording)
    for member in aliases:
        target=song_identity.resolve(member,'','',aliases)[0]
        if target in groups and member not in groups[target]['member_ids']:groups[target]['member_ids'].append(member)
    if affected_groups is None:db.execute('DELETE FROM tracks')
    else:db.executemany('DELETE FROM tracks WHERE id=?',[(tid,) for tid in affected_groups])
    for g in groups.values():
        dates=g.pop('dates');times=[timestamp(t) for t in dates]
        g['history_records']=len(dates);g['last_watch']=max(dates)
        ages=[max(0,(ref-t)/86400) for t in times]
        weight=sum(time_weight(age,90) for age in ages);last_age=min(ages)
        g['frequency_score']=.5*weight/(weight+5);g['recency_score']=.3*time_weight(last_age,30)
        g['base_score']=g['frequency_score']+g['recency_score']
        g['reference_time']=reference;g['days_since_last']=round(last_age,1)
        g['numbers']=[];g['match_candidates']=[]
        for label in [g]+g['aliases']:
            relevant=[]
            for variant in song_labels.variants(label['title']):
                key=norm(variant);relevant.extend(catalogue_by_title.get(key,[]))
                if TITLE_HINTS.get(key):relevant.extend(catalogue_by_title.get(norm(TITLE_HINTS[key]),[]))
            found,possible=match_track(label,relevant,datetime.now(timezone.utc).isoformat())
            for item in possible:
                if item not in g['match_candidates']:g['match_candidates'].append(item)
            for item in found:
                if item not in g['numbers']:g['numbers'].append(item)
        saved_numbers=get_state(db,'numbers',{},'user_state')
        manual=[item for member in g['member_ids'] for item in saved_numbers.get(member,[])]
        for item in manual:
            if item not in g['numbers']:g['numbers'].append(item)
        unique_numbers={}
        for number in g['numbers']:
            key=(number['brand'],str(number['no']))
            if key not in unique_numbers or number.get('source')=='manual':unique_numbers[key]=number
        g['numbers']=list(unique_numbers.values())
        available=set(unique_numbers)
        g['match_candidates']=list({(n['brand'],str(n['no'])):n for n in g['match_candidates'] if (n['brand'],str(n['no'])) not in available}.values())
        g['sources']=sorted(set(g['sources']))
        db.execute('INSERT INTO tracks VALUES (?,?)',(g['id'],json.dumps(g,ensure_ascii=False)))
    if affected_groups is not None:
        statuses=dict(db.execute('SELECT b.status,count(*) FROM video_browse b JOIN video_activity a ON a.id=b.id GROUP BY b.status').fetchall())
    set_state(db,'classification_counts',dict(statuses));set_state(db,'reference_time',reference);db.commit()
def tracks(db):
    followed={canonical(a) for a in get_state(db,'follows',[],'user_state')};hidden=set(get_state(db,'hidden',[],'user_state'))
    good=set(get_state(db,'karaoke_good',[],'user_state'))
    votes=get_state(db,'karaoke_ratings',{},'user_state')
    result=[]
    for row in db.execute('SELECT data FROM tracks'):
        t=json.loads(row[0]);t['followed']=canonical(t['artist']) in followed;t['hidden']=bool(hidden.intersection(t.get('member_ids',[t['id']])))
        t['karaoke_good']=bool(good.intersection(t.get('member_ids',[t['id']]))) and not t['hidden']
        t['karaoke_good_score']=.2 if t['karaoke_good'] else 0
        t['karaoke_rating']=sum(votes.get(m,0) for m in t.get('member_ids',[t['id']]))
        t['karaoke_rating_score']=round(.05*t['karaoke_rating'],6)
        t['score']=round(t['base_score']+(.2 if t['followed'] else 0)+t['karaoke_good_score']+t['karaoke_rating_score'],6);result.append(t)
    return sorted(result,key=lambda t:(-t['score'],-t['history_records'],t['id']))
def stats(db):
    counts=get_state(db,'classification_counts',{});items=tracks(db)
    video_rows=[json.loads(r[0]) for r in db.execute('SELECT data FROM videos')]
    result={'app':'local-karaoke-v1','records':db.execute('SELECT COUNT(*) FROM events').fetchone()[0],
        'videos':len(video_rows),'nonvideo_records':db.execute('SELECT COUNT(*) FROM events WHERE video_id IS NULL').fetchone()[0],
        'tracks':len(items),'numbered_tracks':sum(bool(t['numbers']) for t in items),
        'review':counts.get('review',0),'unknown':counts.get('unknown',0),'other':counts.get('other',0),
        'excluded':counts.get('excluded',0),'non_song':counts.get('non_song',0),'song_videos':counts.get('song',0),
        'metadata_done':sum(v.get('metadata_status') in ('ok','unavailable','error') for v in video_rows),
        'metadata_errors':sum(v.get('metadata_status')=='error' for v in video_rows),
        'official_checked':sum(bool(v.get('api_checked')) for v in video_rows),
        'metadata_unavailable':sum(v.get('metadata_status')=='unavailable' for v in video_rows),
        'categories':dict(Counter(v.get('category') or '미확인' for v in video_rows)),
        'earliest':db.execute('SELECT MIN(time) FROM events').fetchone()[0],
        'latest':db.execute('SELECT MAX(time) FROM events').fetchone()[0],
        'imports':get_state(db,'imports',[]),'job':get_state(db,'job',{'status':'idle'}),
        'catalogue_rows':db.execute('SELECT COUNT(*) FROM catalogue').fetchone()[0],
        'catalogue_queries':db.execute('SELECT COUNT(*) FROM queries').fetchone()[0],
        'catalogue_query_statuses':dict(Counter(json.loads(r[0]).get('status') for r in db.execute('SELECT data FROM queries'))),
        'reference_time':get_state(db,'reference_time'),
        'follows':get_state(db,'follows',[],'user_state')}
    return result
