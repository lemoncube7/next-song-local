"""Video-purpose taxonomy, independent from song identity and music presence."""
import json,re,hashlib,time
from collections import Counter
import core,non_song,recognition

VERSION='video-kind-v4'
ARTISTS=set()
ARTIST_ROWS=-1

def prime_artists(db,force=False):
    global ARTISTS,ARTIST_ROWS
    count=db.execute('SELECT COUNT(*) FROM catalogue').fetchone()[0]
    if not force and count==ARTIST_ROWS:return
    ARTISTS={core.norm(core.number_artist(json.loads(r[0])['singer'])) for r in db.execute('SELECT data FROM catalogue')}
    ARTIST_ROWS=count
LABELS={'song':'곡 중심','collection':'여러 곡·음악 방송','music_explain':'음악 설명·레슨','music_possible':'음악 관련·형식 미확인','activity':'다른 활동 중심','insufficient':'정보 부족'}
CATEGORIES={'Gaming':'게임','News & Politics':'보도','Sports':'스포츠','Education':'교육','Science & Technology':'기술·과학','Howto & Style':'생활 설명','Travel & Events':'여행','Pets & Animals':'동물','Autos & Vehicles':'자동차','People & Blogs':'일상·개인 방송','Entertainment':'예능','Film & Animation':'영상·애니메이션','Comedy':'코미디','Nonprofits & Activism':'사회 활동'}

def fingerprint(v):
    c=v.get('classification',{})
    value=non_song.fingerprint(v)+'|'+str(len(ARTISTS))+'|'+json.dumps({k:c.get(k) for k in ('status','source','title','artist')},sort_keys=True,ensure_ascii=False)
    return hashlib.sha256(value.encode()).hexdigest()

def classify(v):
    raw=v.get('title') or v.get('history_title','');desc=v.get('description','');category=v.get('category')
    c=v.get('classification',{});kind=None;confidence='strong';subtype='';reason=''
    if c.get('status')=='song' and c.get('source') in ('topic','library','auto_generated') and core.norm(raw)==core.norm(c.get('title','')):kind='song';confidence='registered';reason='음원 메타데이터의 곡명이 영상 제목과 일치'
    elif re.search(r'(?i)歌枠|歌配信|karaoke stream|singing stream|노래 방송|노래방송|메들리|メドレー|medley|playlist|플레이리스트|작업용.*음악|作業用.*(?:音楽|BGM)',raw):kind='collection';reason='음악 방송·여러 곡 형식이 제목에 명시됨'
    elif re.search(r'(?i)(?:기타|피아노|보컬|음악|작곡|믹싱|노래|반주).*(?:강의|레슨|강좌|방법|만드는|분석|비하인드)|(?:music|guitar|piano|vocal|song).*(?:lesson|tutorial|analysis|behind)|(?:ギター|ピアノ|作曲|音楽|歌).*(?:講座|レッスン|解説)|(?:이펙터|エフェクター|guitar amp|audio interface).*(?:리뷰|비교|review|比較|レビュー)|기타 반주법|tuning guide',raw):kind='music_explain';reason='음악 관련 설명·제작·장비 주제가 제목에 명시됨'
    elif category=='Gaming' and re.search(r'(?i)arcaea|phigros|bemani|\bosu\b|adofai|音ゲー|리듬게임',raw):kind='activity';confidence='title';subtype='리듬게임';reason='리듬게임 플레이 표기 — 포함된 곡 정보는 별도로 보존'
    elif category=='Gaming' and not re.search(non_song.MUSIC,raw) and re.search(r'(?i)minecraft|マイクラ|마인크래프트|gameplay|実況|공략|攻略',raw):kind='activity';confidence='corroborated';subtype='게임';reason='게임 카테고리와 플레이 형식이 일치 — 포함된 곡 정보는 별도로 보존'
    elif non_song.valid(v) and c.get('status')!='song':kind='activity';confidence='strong';subtype=CATEGORIES.get(category,'기타 활동');reason=v['non_song']['reason']
    elif c.get('status')=='song':kind='song';reason='기존에 연결된 곡 정보';confidence='registered'
    elif re.search(r'(?i)歌ってみた|cover|커버|뮤직비디오|music video|official.*\bMV\b|lyric video|가사|歌詞|lyrics|演奏|연주|オリジナルMV|初音ミク|重音テト|GUMI',raw):kind='song';confidence='title';reason='곡·커버·연주 형식이 제목에 명시됨'
    elif category and not re.search(non_song.MUSIC,raw) and re.search(r'(?i)레전드|근황|특징|정체|반응|몰카|후기|꿀팁|구별법|정상화|이유|왜|실수로|해봤|해버|ㅋㅋ|検証|あるある|ドッキリ|切り抜き|反応|作ってみた|#meme|#funny|#skit|tips|\bwhy\b|explained',raw):kind='activity';confidence='inferred';subtype=CATEGORIES.get(category,'이야기·클립');reason='제목의 설명·반응·상황 표현에 따른 추정 — 확정 비곡 판정은 아님'
    elif recognition.original_links(desc):kind='song';confidence='reference';reason='설명란에 명시된 원곡 링크 존재'
    elif not re.search(r'(?i)behind|비하인드|interview|인터뷰|리뷰|review|雑談',raw) and any(core.norm(core.number_artist(p)) in ARTISTS for p in re.split(r'\s*[/／]\s*|\s+-\s+',raw)) and len(re.split(r'\s*[/／]\s*|\s+-\s+',raw))==2:kind='song';confidence='structured_artist';reason='곡명·가수 구조와 수록곡 목록의 아티스트 표기 일치'
    elif re.search(r'(?i)\[?(?:music|曲|作曲|作詞作曲)\s*[:：/]',desc[:2500]):kind='music_possible';confidence='credit';reason='음악 제작 크레딧 존재 — 단일 곡 여부는 미확인'
    elif category=='Music':kind='music_possible';confidence='category';reason='YouTube Music 카테고리만 확인 — 영상 형식은 미확인'
    elif category in CATEGORIES:
        kind='activity';subtype=CATEGORIES[category];confidence='category';reason='YouTube 카테고리에 따른 활동 유형 추정 — 곡이 없다는 확정은 아님'
        if re.search(r'(?i)gameplay|実況|공략|마인크래프트|マイクラ|minecraft|레시피|요리법|브이로그|\bvlog\b|속보|뉴스|강의|강좌|리뷰|review|잡담|雑談|경기 하이라이트',raw):confidence='corroborated';reason='카테고리와 제목의 활동 형식이 함께 일치'
    else:
        kind='insufficient';confidence='insufficient';reason='공개 메타데이터가 부족해 영상 형식 판별 불가'
        if v.get('metadata_status') in ('unavailable','error'):
            subtype='공개 정보 조회 실패';reason='공개 정보 조회 실패 — 삭제·비공개·접근 제한·일시 오류 여부 미확인'
        elif not raw or raw.startswith('http'):
            subtype='제목 없음';reason='기록에 영상 ID·URL만 있어 음악 여부 판정 불가'
        elif v.get('metadata_status')=='pending':subtype='영상 정보 미조회'
        else:subtype='정보는 있으나 형식 미판정'
    return {'version':VERSION,'kind':kind,'label':LABELS[kind],'subtype':subtype,'confidence':confidence,'reason':reason,'has_identified_song':c.get('status')=='song','has_music_cue':bool(re.search(non_song.MUSIC,raw)),'has_original_reference':bool(recognition.original_links(desc)),'fingerprint':fingerprint(v)}

def get(v):
    old=v.get('video_kind',{})
    return old if old.get('version')==VERSION and old.get('fingerprint')==fingerprint(v) else classify(v)

def mentions(v,catalogue,lookup):
    """Extract explicit set-list/original references; never infer playback from them."""
    found=[]
    for link in recognition.original_links(v.get('description','')):
        original=lookup(link['video_id']);c=original.get('classification',{}) if original else {}
        if original and c.get('status')!='song':
            result=recognition.recognize(original)
            if result['status']=='recognized':c={'status':'song',**result['track']}
        if c.get('status')=='song':found.append({'title':c['title'],'artist':c['artist'],'original_video_id':link['video_id'],'reason':'설명에 명시된 원곡 링크의 확인된 곡','confident':False})
    for line in v.get('description','').splitlines():
        match=re.match(r'^\s*((?:\d{1,2}:)?\d{1,2}:\d{2})\s*[-–]?\s*(.+)$',line)
        if not match:continue
        text=match[2].strip();parts=re.split(r'\s*[/／]\s*|\s+-\s+',text,maxsplit=1)
        if len(parts)==1 and (get(v)['kind']!='collection' or core.norm(text) in {'intro','outro','opening','ending','mc','bgm','소개','시작','엔딩'}):continue
        keys={core.norm(core.catalogue_title(text))}|{core.norm(p) for p in parts}
        for key in keys:
            for row in catalogue.get(key,[]):
                artist=core.number_artist(row['singer'])
                if len(parts)==2 and core.norm(artist) not in {core.norm(core.number_artist(p)) for p in parts}:continue
                found.append({'title':core.catalogue_title(row['title']),'artist':artist,'offset':match[1],'reason':'설명 타임스탬프의 곡명과 수록곡 일치 — 실제 청취 구간은 미확인','confident':False})
    return recognition.merge_candidates(found)[:100]

def run(db,write_lock):
    prime_artists(db,force=True)
    rows=db.execute('SELECT id,data FROM videos WHERE EXISTS(SELECT 1 FROM events e WHERE e.video_id=videos.id)').fetchall()
    catalogue={}
    for row in db.execute('SELECT data FROM catalogue'):
        r=json.loads(row[0]);catalogue.setdefault(core.norm(core.catalogue_title(r['title'])),[]).append(r);ARTISTS.add(core.norm(core.number_artist(r['singer'])))
    state={'status':'running','total':len(rows),'done':0,'requeued':0,'started_at':time.time()};counts=Counter();confidence=Counter();subtypes=Counter();pending=[]
    def flush():
        with write_lock:
            for vid,decision in pending:
                latest=core.video_data(db,vid)
                if decision['fingerprint']!=fingerprint(latest):decision=classify(latest)
                counts[decision['kind']]+=1;confidence[decision['confidence']]+=1
                if decision['subtype']:subtypes[decision['subtype']]+=1
                if latest.get('video_kind')!=decision:latest['video_kind']=decision;core.save_video(db,latest)
                if latest.get('classification',{}).get('status') not in ('song','excluded','non_song') and decision['kind'] in ('collection','music_explain'):
                    songs=mentions(latest,catalogue,lambda i:core.video_data(db,i))
                    result={'status':decision['kind'],'reason':decision['reason']+' — 영상 유형과 포함 곡 정보를 분리하여 보관','candidates':songs}
                    db.execute('INSERT OR REPLACE INTO recognition_results VALUES (?,?)',(vid,json.dumps(result,ensure_ascii=False)))
                    if db.execute("SELECT 1 FROM sqlite_master WHERE name='whole_scan_tasks'").fetchone():db.execute('UPDATE whole_scan_tasks SET stage=?,data=? WHERE id=? AND stage NOT IN (?,?,?)',(decision['kind'],json.dumps(result,ensure_ascii=False),vid,'saved','protected','non_song'))
                elif latest.get('classification',{}).get('status') not in ('song','excluded','non_song'):
                    task=db.execute('SELECT stage FROM whole_scan_tasks WHERE id=?',(vid,)).fetchone() if db.execute("SELECT 1 FROM sqlite_master WHERE name='whole_scan_tasks'").fetchone() else None
                    if task and task['stage'] in ('collection','music_explain') and decision['kind'] not in ('collection','music_explain'):
                        db.execute('UPDATE whole_scan_tasks SET stage=?,data=? WHERE id=?',('deep','{}',vid));state['requeued']+=1
                    elif task and decision['kind'] in ('activity','insufficient') and task['stage'] in ('no_music_evidence','unresolved'):
                        stage='info_missing' if decision['kind']=='insufficient' else 'activity_provisional' if decision['confidence'] in ('category','inferred') else 'activity_known'
                        result={'status':stage,'reason':decision['reason'],'candidates':[],'video_kind':decision}
                        db.execute('UPDATE whole_scan_tasks SET stage=?,data=? WHERE id=?',(stage,json.dumps(result,ensure_ascii=False),vid))
                        db.execute('INSERT OR REPLACE INTO recognition_results VALUES (?,?)',(vid,json.dumps(result,ensure_ascii=False)))
                    elif task and decision['kind']=='song' and task['stage'] in ('no_music_evidence','info_missing','activity_provisional','activity_known'):
                        db.execute('UPDATE whole_scan_tasks SET stage=?,data=? WHERE id=?',('deep','{}',vid));state['requeued']+=1
                if decision['kind']=='activity' and decision['has_original_reference'] and latest.get('classification',{}).get('status') not in ('song','excluded'):
                    songs=mentions(latest,catalogue,lambda i:core.video_data(db,i))
                    if songs:
                        result={'status':'activity_provisional' if decision['confidence'] in ('category','inferred') else 'activity_known','reason':decision['reason']+' — 명시된 원곡 정보는 별도로 보존','candidates':songs,'video_kind':decision}
                        db.execute('INSERT OR REPLACE INTO recognition_results VALUES (?,?)',(vid,json.dumps(result,ensure_ascii=False)))
            pending.clear();state.update(counts=dict(counts),confidence=dict(confidence),subtypes=dict(subtypes),updated_at=time.time())
            core.set_state(db,'video_kind_job',state);db.commit()
    for row in rows:
        v=json.loads(row['data']);pending.append((row['id'],classify(v)));state['done']+=1
        if len(pending)>=1000:flush()
    state.update(status='complete',finished_at=time.time());flush();return state
