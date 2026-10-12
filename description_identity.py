"""Conservative identities from explicit original-song and vocal credits."""
import re,unicodedata
import core

def clean(text):
 text=unicodedata.normalize('NFKC',text)
 text=re.sub(r'https?://\S+','',text)
 text=re.sub(r'(?i)\s*(?:\b(?:ft|feat)(?:\.\s*|\s+).*|【[^】]*】|\((?:IA|cover|official[^)]*)\))','',text)
 text=text.strip(' \t「」『』[]-:：様')
 if text.count('(')>text.count(')'):text=re.sub(r'\s*\($','',text)
 return text

def agrees(song,raw):
 key=core.norm(clean(song));return len(key)>=2 and key in core.norm(raw)

def identity(video,lookup=None,tracks=()):
 raw=unicodedata.normalize('NFKC',video.get('title') or video.get('history_title',''))
 desc=unicodedata.normalize('NFKC',video.get('description',''))
 if lookup:
  import recognition
  if len(recognition.original_links(desc))>1:return None
 if re.search(r'(?i)歌枠|medley|playlist|メドレー|모음|노래방송|tutorial|보컬강의|기타.*강의|노래로 만드는 방법',raw):return None
 found=[]
 # Translation uploads may explicitly list native and translated titles.
 alternate=re.search(r'(?im)^Alternative Titles:\s*\n((?:[^\n]*\n?){1,5})',desc)
 music=re.findall(r'(?im)^\s*Music:\s*([^\n]+)',desc)
 if alternate and len(music)==1 and not re.search(r'(?i)cover|remix|歌ってみた|커버',raw):
  credit=core.norm(music[0]);creator=None
  for group in core.ARTIST_GROUPS:
   names=sorted({core.norm(a) for a in group if core.norm(a)},key=len,reverse=True)
   remaining=credit
   for name in names:remaining=remaining.replace(name,'')
   if credit and not remaining:creator=group[0];break
  titles=re.findall(r'[「『]([^」』]+)[」』]',alternate[1])
  if creator and len(set(titles))==1 and any(core.norm(a) in core.norm(raw) for a in next(g for g in core.ARTIST_GROUPS if g[0]==creator)):
   found.append({'title':titles[0],'artist':creator,'confident':True,'reason':'번역 영상의 명시된 원어 제목 목록과 Music 아티스트 크레딧 일치'})
 # Explicit track fields plus independent title agreement: music archives can
 # legitimately be categorized as Gaming rather than Music.
 titles=re.findall(r'(?im)^\s*(?:Title|曲名|곡명)\s*[:：]\s*([^\n]+)',desc)
 artists=[re.split(r'(?i)\s+Thanks\s+to\b',name,maxsplit=1)[0].strip() for name in re.findall(r'(?im)^\s*(?:Artist|アーティスト|아티스트)\s*[:：]\s*([^\n]+)',desc)]
 archive=core.norm(video.get('channel',''))=='djmaxarchive'
 if len(titles)==len(artists)==1 and agrees(titles[0],raw) and (archive or video.get('category')=='Music') and not re.search(r'(?i)cover|커버|歌ってみた|gameplay|実況',raw):
  found.append({'title':titles[0].strip(),'artist':core.canonical(artists[0]),'confident':True,'reason':'설명의 단일 곡명·아티스트 필드와 영상 제목 일치'})
 if archive and not titles and len(artists)==1:
  m=re.match(r'^(.+)\s+by\s+(.+)$',raw,re.I)
  if m and core.norm(m[2])==core.norm(artists[0]):
   found.append({'title':m[1].strip(),'artist':core.canonical(artists[0]),'confident':True,'reason':'음악 아카이브 제목의 by 아티스트와 설명 Artist 일치'})
 for line in desc.splitlines():
  m=re.match(r'(?i)^\s*(?:original(?: song)?|music|원곡|본가|原曲)\s*[:：]\s*(.+)$',line)
  if not m:continue
  text=re.sub(r'https?://\S+','',m[1]).strip()
  parts=re.split(r'\s+[-–]\s+|\s*[/／]\s*',text)
  if len(parts)<2:continue
  left,right=map(clean,parts[:2])
  lm,rm=agrees(left,raw),agrees(right,raw)
  if lm==rm:continue
  song,artist=(left,right) if lm else (right,left)
  if not artist or len(artist)>100 or re.search(r'(?i)vocal|cover|歌ってみた',artist):continue
  found.append({'title':song,'artist':artist,'confident':True,'reason':'설명에 명시된 원곡 제목·아티스트와 영상 제목 일치'})
 if lookup:
  import recognition
  links=recognition.original_links(desc)
  for link in links:
   original=lookup(link['video_id'])
   if not original:continue
   known=original.get('classification',{})
   if known.get('status')!='song':continue
   labels=[{'title':known['title'],'artist':known['artist']}]
   for track in tracks:
    if link['video_id'] in track.get('video_ids',[]):labels+=track.get('aliases',[])
   translated=bool(re.search(r'(?i)\[(?:한글화|자막|한글자막)\]|English Subbed|ENG SUB|한글가사 자막',raw)) and not re.search(r'(?i)cover|커버|歌ってみた|remix|패러디|합성|소스',raw+'\n'+desc)
   if any(agrees(label['title'],raw) for label in labels) or translated:
    found.append({'title':clean(known['title']),'artist':known['artist'],'confident':True,'reason':'명시된 원곡 링크의 확정 곡명 또는 번역 별칭과 영상 제목 일치','original_video_id':link['video_id'],'alternate_labels':labels})
 # Original uploads: require vocal and writing credit to name the same artist,
 # plus that artist in the channel. Never substitute cover vocal for original artist.
 if not re.search(r'(?i)cover|커버|歌ってみた',raw):
  vocal=re.findall(r'(?im)^\s*(?:Vocal\s+by|노래\s*[:：]|보컬\s*[:：])\s*([^\n]+)',desc)
  writer=re.findall(r'(?im)^\s*(?:Composed\s+by|Lyrics\s+by)\s*([^\n]+)',desc)
  if len(set(map(core.norm,vocal)))==1 and vocal and any(core.norm(vocal[0])==core.norm(w) for w in writer) and core.norm(vocal[0]) in core.norm(video.get('channel','')):
   song=raw.split('/')[0].strip();quotes=re.findall(r'[「『]([^」』]+)[」』]',song)
   if quotes:song=quotes[-1]
   found.append({'title':song,'artist':vocal[0].strip(),'confident':True,'reason':'보컬·작사 또는 작곡 크레딧과 업로더 아티스트 일치'})
 unique={ (core.norm(clean(f['title'])),core.norm(f['artist'])):f for f in found }
 if len(unique)==1:
  track=next(iter(unique.values()));return {'status':'recognized','track':track,'candidates':[track]}
 return None
