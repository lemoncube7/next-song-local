"""Local identity extraction for a video the user has confirmed is a song."""
import re, unicodedata
import core
import song_identity

def merge_candidates(candidates, tracks=()):
    """Collapse identity aliases, retaining distinct performers and versions."""
    known={}
    for t in tracks:
        for a in t.get('aliases',[]):
            known[(core.norm(core.artist_base(a['artist'])),core.norm(a['title']))]=t['id']
    def keys(c):
        artist=core.norm(artist_name(core.artist_base(c['artist'])))
        title=unicodedata.normalize('NFKC',c['title']).strip()
        title=song_identity.presentation_title(title)
        # Artist/voice credit in a video title is not a second song identity.
        parts=re.split(r'\s*[/／]\s*',title,maxsplit=1)
        if len(parts)==2 and core.norm(core.artist_base(parts[1]))==artist:title=parts[0]
        variants=bool(re.search(r'(?i)\blive\b|remix|instrumental|karaoke|\bver(?:sion)?\b|re-record|ライブ|커버|cover',title))
        if not variants:title=re.sub(r'(?i)\s*\(?\s*(?:feat\.|ft\.|Vo\.)\s*[^\n]+$','',title).strip()
        forms={core.norm(title)}
        if not variants and re.search(r'[\u3040-\u30ff\u4e00-\u9fff]',title):
            forms.update(core.norm(p) for p in title.split(' - ') if p.strip())
        result={(artist,f) for f in forms}
        saved=known.get((artist,core.norm(c['title'])))
        if saved:result.add(('confirmed',saved))
        return result
    groups=[]
    for candidate in candidates:
        if not isinstance(candidate,dict) or not candidate.get('title') or not candidate.get('artist'):continue
        c={**candidate};k=keys(c);matches=[g for g in groups if k.intersection(g['keys'])]
        labels=[{'title':c['title'],'artist':c['artist']}]+[a for a in c.get('alternate_labels',[]) if a.get('title') and a.get('artist')]
        if not matches:groups.append({'value':c,'keys':k,'labels':labels,'urls':[c['url']] if c.get('url') else []});continue
        g=matches[0]
        for other in matches[1:]:
            g['keys'].update(other['keys']);g['labels'].extend(other['labels']);g['urls'].extend(other['urls']);g['value']['confident']=bool(g['value'].get('confident') or other['value'].get('confident'));groups.remove(other)
        g['keys'].update(k);g['labels'].extend(labels)
        g['value']['confident']=bool(g['value'].get('confident') or c.get('confident'))
        if c.get('url'):g['urls'].append(c['url'])
        if not g['value'].get('url') and c.get('url'):g['value']['url']=c['url']
    result=[]
    for g in groups:
        c=g['value'];c['alternate_labels']=list({(a['title'],a['artist']):a for a in g['labels']}.values());c['urls']=list(dict.fromkeys(g['urls']));result.append(c)
    return result

def artist_name(value):
    value=re.sub(r'(?i)\s+(?:official(?: channel)?|[-–] Topic)$','',value.strip())
    name=core.canonical(re.split(r'\s*[/／]\s*',value,maxsplit=1)[0].strip())
    return 'ぬゆり' if core.norm(name)=='lanndo' else name


VOCAL = r'(?:初音ミク|重音テト(?:SV)?|歌愛ユキ|可不|(?:Ci |v )?flower|GUMI|IA|miku|鏡音リン(?:・レン)?|鏡音レン|巡音ルカ|結月ゆかり|音街ウナ|MEIKO|KAITO|鳴花ヒメ|ミコト)'

def expanded_identity(video):
    """Read a single-song title together with explicit creator credits."""
    title=unicodedata.normalize('NFKC',video.get('title') or video.get('history_title','')).strip()
    desc=unicodedata.normalize('NFKC',video.get('description',''))
    channel=artist_name(video.get('channel') or video.get('history_channel',''))
    if re.search(r'(?i)cover|歌ってみた|歌枠|medley|playlist|メドレー|커버|모음|\bshorts?\b|remix|instrumental|karaoke|\blive\b',title):return None
    aliases={'須田景凪 バルーン':'バルーン','Suisei Channel':'星街すいせい',
             'Okayu Ch. 猫又おかゆ':'猫又おかゆ','神山羊':'有機酸',
             'ピノキオピー PINOCCHIOP':'ピノキオピー','みきとP mikitoP':'みきとP','きさら - KISARA':'きさら','MAISONdes -メゾン・デ-':'MAISONdes'}
    channel=aliases.get(channel,channel)
    raw_channel=video.get('channel','')
    if re.search(r'(?i)n-buna',raw_channel) and re.search(VOCAL,title,re.I):channel='n-buna'
    credits=[]
    for line in desc.splitlines():
        line=line.strip().lstrip('■□・●▷◇◆ ')
        # Match a credit label, never lyric prose or album track listings.
        m=re.match(r'(?i)^(?:\[|［)?((?:music|words|vocal|lyrics?|arrange|mix|movie|音楽|曲|詞|作詞作曲|作詞|作曲|作編曲|動画|絵|映像|歌|mastering)(?:\s*[,、&＆/・.]\s*(?:music|words|vocal|lyrics?|arrange|mix|movie|音楽|曲|詞|作詞作曲|作詞|作曲|作編曲|動画|絵|映像|歌|mastering))*)\s*(?:\]|］|[:：/]|\s+-\s+|\s)\s*(.+)$',line)
        if not m or not re.search(r'(?i)music|音楽|(?:^|[,、&＆/・.])曲|作曲|作編曲',m[1]):continue
        name=re.split(r'\s+(?:https?://|@)|\s*https?://|\s*@',m[2],maxsplit=1)[0].strip()
        name=re.split(r'\s*\(',name,maxsplit=1)[0].strip()
        name=artist_name(name)
        if name=='ナブナ':name='n-buna'
        if name and len(name)<80:credits.append(name)
    agrees=next((x for x in credits if core.norm(channel) in {core.norm(a.strip()) for a in re.split(r'[,、]',x)}),None)
    creator=agrees or (credits[0] if len(set(credits))==1 else None)
    text=re.sub(r'^【公式】\s*','',title)
    if channel=='MAISONdes':text=re.sub(r'^【\d+】\[feat\.[^]]+\]\s*','',text)
    bracket=re.match(r'^【([^】]+)】\s*(.+)$',text)
    bracket_agrees=bool(bracket and core.norm(artist_name(bracket[1]))==core.norm(channel))
    if bracket_agrees:
        text=bracket[2]
        if creator and text.endswith('】'):text=re.sub(r'【[^】]+】$','',text).strip()
    text=re.sub(r'(?i)\s*(?:\(\s*(?:official(?: video)?|MV)\s*\)|\bMV)\s*$','',text).strip()
    quoted=list(re.finditer(r'[「『\']([^」』\']+)[」』\']',text))
    song=None;performer=None;proof=False
    if len(quoted)==1:
        q=quoted[0];prefix=text[:q.start()].strip()
        if not prefix or core.norm(artist_name(prefix))==core.norm(channel) or (channel=='有機酸' and prefix=='有機酸/ewe'):
            song=q[1].strip();performer=creator or channel;proof=bool(creator or prefix)
    if song is None:
        parts=re.split(r'\s*[/／]\s*',text,maxsplit=1)
        if len(parts)==2:
            left,right=parts
            right=re.sub(r'\s+-\s+[A-Za-z][A-Za-z ]+$','',right).strip()
            vocal_only=bool(re.fullmatch(r'(?i)(?:feat\.?\s*)?'+VOCAL+r'(?:\s*[＆&・×,、]\s*'+VOCAL+r')*',right))
            artist_part=re.split(r'(?i)\s+feat\.?|\s*×|・MARETU',right,maxsplit=1)[0].strip()
            if vocal_only and creator:song=left;performer=creator;proof=True
            elif core.norm(artist_name(artist_part))==core.norm(channel):song=left;performer=channel;proof=True
            elif creator and '[オリジナル]' in right:song=left;performer=creator;proof=True
        dash=re.match(r'^(.+?)\s+-\s+(.+)$',text)
        if song is None and dash:
            left,right=dash.groups()
            if re.fullmatch(r'(?i)'+VOCAL+r'(?:\[[^]]+\])?',right) and creator:
                song=left;performer=creator;proof=True
            elif core.norm(artist_name(right.split(' × ')[0]))==core.norm(channel):
                song=left;performer=channel;proof=True
            elif core.norm(artist_name(left))==core.norm(channel) and ('/' not in right or re.search(r'(?i)\s+feat\.?\s*',right)):
                song=re.split(r'(?i)\s+feat\.?\s*',right,maxsplit=1)[0];performer=channel;proof=True
    if song is None and bracket_agrees and creator and core.norm(creator)==core.norm(channel):
        song=text;performer=creator;proof=True
    if not song or not performer or not proof:return None
    if core.norm(channel) not in {core.norm(a.strip()) for a in re.split(r'[,、]',performer)} and not (channel=='YOASOBI' and performer=='Ayase'):return None
    song=song.strip(' 「」『』');song=re.sub(r'(?i)\s+feat\.?\s*.*$','',song).strip()
    if not song or len(song)>120 or len(quoted)>1:return None
    return {'title':song,'artist':performer,'reason':'단일 곡 제목의 보컬·MV 표기를 분리하고 제작 크레딧 또는 아티스트 표기를 확인','confident':True}

def original_links(description):
    """Only links in short, explicitly labelled original-song blocks."""
    lines=description.splitlines();found=[]
    for i,line in enumerate(lines):
        labelled=bool(re.match(r'(?i)^\s*[■□・●]*\s*(?:original(?: song)?(?: by)?|原曲|本家(?:様)?|본가(?:MV)?|원곡(?:MV)?|원본 영상 출처)\s*[:：]?\s*',line))
        named=bool(re.search(r'[「『][^」』]+[」』].*Music Video|/[^/\n]+\s*様\s*$',line,re.I))
        if not labelled and not named:continue
        block='\n'.join(lines[i:i+4])
        for vid in re.findall(r'(?:https?://(?:www\.)?youtu\.be/|https?://(?:www\.)?youtube\.com/watch\?v=)([\w-]{11})',block):
            found.append({'video_id':vid,'context':block})
    return list({x['video_id']:x for x in found}.values())

def recognize_cover(video, lookup):
    title=video.get('title') or video.get('history_title','')
    import music_metadata
    if not re.search(r'(?i)cover|歌ってみた|커버|자막|가사|subbed',title) and not music_metadata.risky_video(video):return None
    links=original_links(video.get('description',''));candidates=[]
    for link in links:
        original=lookup(link['video_id']);candidate=None
        if original:
            known=original.get('classification',{})
            r={'status':'recognized','track':{'title':known['title'],'artist':known['artist'],'confident':True}} if known.get('status')=='song' else recognize(original)
            if r['status']=='recognized':candidate={**r['track']}
            else:
                # KAF's numbered original-MV titles explicitly name the singer.
                ot=unicodedata.normalize('NFKC',original.get('title',''))
                m=re.match(r'^(.+?)\s*#\d+\s*[「『]([^」』]+)[」』]\s*【オリジナルMV】$',ot)
                if m and core.norm(m[1])==core.norm(re.sub(r'\s+-KAF-$','',original.get('channel',''))):
                    candidate={'title':m[2],'artist':m[1].strip(),'confident':True}
        if candidate and core.norm(candidate['title']) in core.norm(title):
            candidates.append({**candidate,'reason':'커버 설명의 원곡 링크와 연결된 원곡 영상 정보 일치','url':'https://www.youtube.com/watch?v='+link['video_id'],'original_video_id':link['video_id']})
        elif candidate:
            candidates.append({**candidate,'confident':False,'reason':'원곡 링크의 곡 정보 확인, 번역된 영상 제목과 대조 필요','url':'https://www.youtube.com/watch?v='+link['video_id']})
        elif not original:
            m=re.search(r'([^\n]+?)\s*様\s*[「『]([^」』]+)[」』]',link['context'])
            if not m:m=re.search(r'(?:Original[:：]\s*)?([^\n「『]+)[「『]([^」』]+)[」』].*Music Video',link['context'],re.I)
            if m and core.norm(m[2]) in core.norm(title):
                candidates.append({'title':m[2],'artist':m[1].strip(),'confident':False,'reason':'설명에 원곡명·아티스트·링크 명시, 연결 영상 정보 미보유','url':'https://www.youtube.com/watch?v='+link['video_id']})
    candidates=merge_candidates(candidates)
    if len(links)==1 and len(candidates)==1 and candidates[0].get('confident'):
        return {'status':'recognized','track':candidates[0],'candidates':candidates}
    if candidates:return {'status':'ambiguous','candidates':candidates,'reason':'설명의 원곡 정보 후보를 확인해 주세요.'}
    return None

def confirmed_identity(video, tracks):
    """Reuse exact saved title/artist pairs, never title-only or cover credits."""
    import music_metadata
    if music_metadata.risky_video(video):return None
    if len(video.get('music_metadata',{}).get('cards',[]))>1:return None
    raw=video.get('title') or video.get('history_title','')
    channel=artist_name(video.get('channel') or video.get('history_channel',''))
    pairs=[(c['title'],c['artist']) for c in video.get('music_metadata',{}).get('cards',[])]
    m=re.match(r'^(.+?)\s+[-–—]\s+(.+)$',raw)
    if m and core.norm(artist_name(m[1]))==core.norm(channel):
        pairs.append((re.split(r'\s*[/／]\s*',m[2])[0],channel))
    quoted=re.findall(r'[「『]([^」』]+)[」』]',raw)
    if len(quoted)==1:pairs.append((quoted[0],channel))
    matches={}
    for track in tracks:
        labels=track.get('aliases',[])+[{'title':track['title'],'artist':track['artist']}]
        # A claimed background track in a talk/game video is not a song video.
        if not any(len(core.norm(a['title']))>=3 and core.norm(a['title']) in core.norm(raw) for a in labels):continue
        for title,artist in pairs:
            if any(core.norm(title)==core.norm(a['title']) and core.norm(artist_name(core.artist_base(artist)))==core.norm(artist_name(core.artist_base(a['artist']))) for a in labels):
                matches[track['id']]=track
    if len(matches)!=1:return None
    t=next(iter(matches.values()))
    candidate={'title':t['title'],'artist':t['artist'],'alternate_labels':t.get('aliases',[]),
               'reason':'이미 확정된 곡의 제목 별칭과 아티스트가 함께 일치','confident':True}
    return {'status':'recognized','track':candidate,'candidates':[candidate]}

def reuse_confirmed(db):
    """One local pass over watched videos; protect every existing correction."""
    import json
    by_artist={}
    for track in core.tracks(db):
        for label in track.get('aliases',[])+[track]:
            key=core.norm(artist_name(core.artist_base(label['artist'])))
            by_artist.setdefault(key,{})[track['id']]=track
    watched={r[0] for r in db.execute('SELECT DISTINCT video_id FROM events WHERE video_id IS NOT NULL')}
    edits=core.get_state(db,'corrections',{},'user_state');saved=[]
    for row in db.execute('SELECT id,data FROM videos'):
        if row['id'] not in watched or row['id'] in edits:continue
        video=json.loads(row['data'])
        if video.get('classification',{}).get('status') in ('song','excluded'):continue
        artists=[video.get('channel') or video.get('history_channel','')]+[c['artist'] for c in video.get('music_metadata',{}).get('cards',[])]
        possible={t['id']:t for a in artists for t in by_artist.get(core.norm(artist_name(core.artist_base(a))),{}).values()}
        result=confirmed_identity(video,list(possible.values())) if possible else None
        if not result:continue
        track=result['track'];edits[row['id']]={**track,'source':'auto_recognition','exclude':False}
        result['saved']=True
        db.execute('INSERT OR REPLACE INTO recognition_results VALUES (?,?)',(row['id'],json.dumps(result,ensure_ascii=False)))
        saved.append({'video_id':row['id'],'title':track['title'],'artist':track['artist']})
    core.set_state(db,'corrections',edits,'user_state');core.rebuild(db)
    return {'saved':len(saved),'items':saved}

def recognize(video, catalogue=(), lookup=None, tracks=()):
    title=unicodedata.normalize('NFKC',video.get('title') or video.get('history_title','')).strip()
    channel=video.get('channel') or video.get('history_channel','')
    description=video.get('description','')
    artist=artist_name(channel)
    known=confirmed_identity(video,tracks)
    if known:return known
    if lookup:
        cover=recognize_cover(video,lookup)
        if cover:return cover
    expanded=expanded_identity(video)
    if expanded:return {'status':'recognized','track':expanded,'candidates':[expanded]}
    import music_metadata
    music=music_metadata.identity(video,lookup)
    if music:return music
    candidates=[]
    blocked=bool(re.search(r'(?i)cover|歌ってみた|歌枠|メドレー|medley|playlist|모음|커버|歌唱枠|\blive\b|remix|instrumental|karaoke',title))
    def add(song,performer,reason,confident=False):
        song=song.strip(' \t-–/／');performer=artist_name(performer)
        if not song or not performer or max(len(song),len(performer))>300:return
        if core.norm(song)==core.norm(performer):return
        pair=(core.norm(song),core.norm(performer))
        old=next((x for x in candidates if (core.norm(x['title']),core.norm(x['artist']))==pair),None)
        if old:old['confident'] |= confident and not blocked
        else:candidates.append({'title':song,'artist':performer,'reason':reason,'confident':confident and not blocked})
    classification=video.get('classification',{})
    if classification.get('status')=='song':
        add(classification['title'],classification['artist'],'이미 확인된 곡 정보',True)
    quoted=list(re.finditer(r'[「『]([^」』]+)[」』]',title))
    if len(quoted)==1:
        match=quoted[0];prefix=title[:match.start()].strip()
        if prefix and core.norm(artist_name(prefix))==core.norm(artist):
            add(match[1],artist,'제목의 아티스트·따옴표 곡명이 채널과 일치',True)
    # Artist - song / vocal : translated title. The uploader must agree.
    structured=re.match(r'^(.+?)\s+[-–—]\s+(.+)$',title)
    structured_song=None
    if structured and core.norm(artist_name(structured[1]))==core.norm(artist):
        body=structured[2].strip()
        vocal=r'(?:GUMI|初音ミク|鏡音リン|鏡音レン|鏡音リン・レン|巡音ルカ|歌愛ユキ|flower|v flower|IA|可不|重音テト|結月ゆかり|音街ウナ|MEIKO|KAITO|鳴花ヒメ|ミコト)'
        cleaned=re.sub(r'(?i)\s*[/／]\s*(?:feat\.?\s*|Vo\.?\s*)?'+vocal+r'(?:\s*[:：]\s*[^/／]+)?\s*$','',body).strip()
        if cleaned!=body and cleaned:
            structured_song=cleaned
            add(cleaned,structured[1],'제목의 아티스트가 채널과 일치하고 곡명·보컬·영문 표기를 분리',True)
    if 'Provided to YouTube by ' in description and 'Auto-generated by YouTube.' in description:
        line=next((x.strip() for x in description.splitlines() if ' · ' in x),None)
        if line:
            song,performer=line.split(' · ',1);add(song,performer,'자동 생성 음원 설명',True)
    # Credit lines refer to the creator of the clicked video, not linked albums.
    credit=any(core.norm(artist_name(m[1]))==core.norm(artist) for m in re.finditer(r'(?im)^\s*(?:music|作詞(?:作編曲)?|作曲|作詞[・/／]作曲)\s*[:：/／]\s*([^\n@]+)',description))
    parts=re.split(r'\s*[/／]\s*',title,maxsplit=1)
    if len(parts)==2 and not quoted:
        suffix=re.sub(r'(?i)\s*(?:feat\.?|ft\.?|Vo\.)\s*.*$','',parts[1]).strip()
        song=parts[0]
        if suffix and core.norm(artist_name(suffix))==core.norm(artist):
            add(song,artist,'제목의 곡명·아티스트가 채널과 일치',True)
        elif re.match(r'(?i)^(?:feat\.?|ft\.?|Vo\.)\s*',parts[1]) and credit:
            add(song,artist,'피처링 제목과 채널에 일치하는 제작 크레딧',True)
    ordinary=core.regular_song({**video,'category':'Music'}) if not structured_song else None
    if ordinary:
        explicit=re.match(r'^(.+?)\s+[-–—]\s+',title)
        agrees=bool(explicit and core.norm(artist_name(explicit[1]))==core.norm(artist))
        add(ordinary['title'],ordinary['artist'],ordinary['reason'],credit or agrees)
    # Exact local catalogue identity is a suggestion unless uploader identity agrees.
    possible_titles={core.norm(title)}|{core.norm(m[1]) for m in quoted}
    if len(parts)==2:possible_titles.add(core.norm(parts[0]))
    for row in catalogue:
        if core.norm(core.catalogue_title(row.get('title',''))) in possible_titles:
            add(row['title'],row['singer'],'기존 노래방 목록의 곡명 일치',not blocked and core.norm(core.artist_base(row['singer']))==core.norm(artist))
    candidates=merge_candidates(candidates)
    strong=[x for x in candidates if x['confident']]
    if len(strong)==1 and len(quoted)<=1:
        return {'status':'recognized','track':strong[0],'candidates':candidates}
    return {'status':'ambiguous' if candidates else 'unresolved','candidates':candidates[:12],
            'reason':'커버·여러 곡 또는 복수 후보라서 직접 선택이 필요해요.' if blocked or candidates else '곡명과 아티스트를 확실하게 찾지 못했어요. 직접 입력해 주세요.'}
