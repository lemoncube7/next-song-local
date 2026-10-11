"""Conservative metadata rules for videos whose main purpose is not a song."""
import hashlib,json,re,time

VERSION='non-song-v1'
MUSIC=r'(?i)歌ってみた|歌枠|歌配信|cover|커버|노래|가사|歌詞|lyrics?|\bMV\b|music video|뮤직비디오|remix|\bOST\b|feat\.?|\bft\.|演奏|연주|ピアノ|piano|악보|楽譜|\bsolo\b|オリジナル曲|original song|demo song|デモソング|初音ミク|GUMI|重音テト|可不|鏡音|flower|音ゲー|bemani|arcaea|\bosu\b|리듬게임|歌唱'

def fingerprint(v):
    fields={k:v.get(k) for k in ('title','history_title','channel','history_channel','description','category','metadata_status')}
    fields['cards']=v.get('music_metadata',{}).get('cards',[])
    return hashlib.sha256(json.dumps(fields,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def valid(v):
    d=v.get('non_song',{})
    return d.get('version')==VERSION and d.get('fingerprint')==fingerprint(v)

def decide(v,result=None):
    import core,recognition
    title=v.get('title') or v.get('history_title','');category=v.get('category','')
    if v.get('metadata_status')!='ok' or not title or not category:return None
    if re.search(MUSIC,title):return None
    description=v.get('description','')
    if 'Provided to YouTube by ' in description or (v.get('channel') or v.get('history_channel','')).endswith(' - Topic'):return None
    if recognition.original_links(description):return None
    for c in (result or {}).get('candidates',[])+v.get('music_metadata',{}).get('cards',[]):
        name=core.norm(c.get('title',''))
        if c.get('confident') or (len(name)>=3 and name in core.norm(title)):return None
    rule=None
    if category=='Gaming' and re.search(r'(?i)minecraft|マイクラ|마인크래프트|valorant|발로란트|리그 오브 레전드|\b롤\b|apex|overwatch|오버워치|simulator|シミュレーター|ゼリーテトリス|砂テトリス|gameplay|게임플레이|実況|공략|패치|버그|攻略|解説|初見プレイ',title):rule='gameplay'
    elif category=='News & Politics' and re.search(r'(?i)속보|뉴스|정치|대통령|국회|선거|news|election|政治|速報|ニュース',title):rule='news'
    elif category=='Sports' and re.search(r'(?i)축구|야구|농구|골프|캐디|경기|football|soccer|baseball|basketball|golf|サッカー|野球|ゴルフ',title):rule='sports'
    elif category in ('Education','Science & Technology') and re.search(r'(?i)강의|강좌|수학|증명|실험|과학|인공지능|컴퓨터|lecture|tutorial|science|実験|講義|解説',title):rule='education'
    elif category in ('People & Blogs','Entertainment','Travel & Events') and re.search(r'(?i)브이로그|\bvlog\b|여행 브이로그|일상 브이로그|雑談配信|雑談枠|talk stream|chatting stream',title):rule='vlog_talk'
    elif category in ('Howto & Style','People & Blogs','Education') and re.search(r'(?i)레시피|요리법|料理|recipe|메이크업|화장법|makeup tutorial',title):rule='howto'
    elif re.search(r'(?i)리뷰|review|언박싱|unboxing|レビュー|比較',title) and re.search(r'(?i)이펙터|앰프|오디오 인터페이스|페달|アンプ|エフェクター|audio interface|effect pedal|guitar amp',title):rule='gear_review'
    if not rule:return None
    reasons={'gameplay':'게임 카테고리와 명시된 게임·플레이·공략 표기 일치','news':'뉴스·정치 카테고리와 보도 주제 일치','sports':'스포츠 카테고리와 경기·운동 주제 일치','education':'교육·기술 카테고리와 강의·설명 주제 일치','vlog_talk':'일상·예능 카테고리와 브이로그·잡담 형식 일치','howto':'생활·교육 카테고리와 요리·화장 설명 형식 일치','gear_review':'장비 대상과 리뷰·비교 형식이 함께 명시됨'}
    return {'version':VERSION,'rule':rule,'reason':reasons[rule]+' — 곡·커버·연주 표기나 일치하는 음악 근거 없음','fingerprint':fingerprint(v),'decided_at':time.time()}

def reconcile(db,write_lock):
    import core
    rows=db.execute('SELECT v.id,v.data,r.data result FROM videos v LEFT JOIN recognition_results r ON r.id=v.id WHERE EXISTS(SELECT 1 FROM events e WHERE e.video_id=v.id)').fetchall()
    counts={};changed=0;pending=[]
    edits=core.get_state(db,'corrections',{},'user_state')
    def flush():
        nonlocal changed
        with write_lock:
            current=core.get_state(db,'corrections',{},'user_state')
            has_tasks=db.execute("SELECT 1 FROM sqlite_master WHERE name='whole_scan_tasks'").fetchone()
            for vid,d in pending:
                v=core.video_data(db,vid)
                if vid in current or v.get('classification',{}).get('status') in ('song','excluded'):continue
                if d['fingerprint']!=fingerprint(v):continue
                v['non_song']=d;v['classification']={'status':'non_song','source':'automatic_non_song','reason':d['reason']};core.save_video(db,v)
                result={'status':'non_song','reason':d['reason'],'candidates':[],'rule':d['rule']}
                db.execute('INSERT OR REPLACE INTO recognition_results VALUES (?,?)',(vid,json.dumps(result,ensure_ascii=False)))
                if has_tasks:db.execute('UPDATE whole_scan_tasks SET stage=?,data=? WHERE id=?',('non_song',json.dumps(result,ensure_ascii=False),vid))
                counts[d['rule']]=counts.get(d['rule'],0)+1;changed+=1
            db.commit();pending.clear()
    for row in rows:
        v=json.loads(row['data'])
        if row['id'] in edits or v.get('classification',{}).get('status') in ('song','excluded','non_song'):continue
        result=json.loads(row['result']) if row['result'] else {}
        d=decide(v,result)
        if d:pending.append((row['id'],d))
        if len(pending)>=500:flush()
    flush()
    with write_lock:
        core.rebuild(db)
        report={'status':'complete','new_non_song':changed,'rules':counts,'version':VERSION,'finished_at':time.time()}
        core.set_state(db,'non_song_job',report);db.commit()
    return report
