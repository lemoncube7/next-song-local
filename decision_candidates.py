"""Role candidates v2: original-credit context and punctuation-aware names."""
import re,unicodedata
VERSION='roles-v3'
def candidates(v):
 raw=unicodedata.normalize('NFKC',v.get('title') or v.get('history_title',''));desc=unicodedata.normalize('NFKC',v.get('description',''));lines=desc.splitlines();out=[]
 cover=bool(re.search(r'(?i)cover|歌ってみた|커버',raw));translated=bool(re.search(r'(?i)자막|한글화|ENG SUB|字幕',raw))
 def key(s):return ''.join(c for c in unicodedata.normalize('NFKC',s).casefold() if c.isalnum())
 def clean(s):return re.sub(r'\s*(?:様)\s*$','',re.split(r'https?://|@',s)[0].strip(' \t:：;■✘☁🎙️🎶')).strip()
 def add(s,role,evidence,context='current'):
  s=clean(s)
  if not s or len(s)>140 or s.casefold() in ('cover','official','null'):return
  if any(c['text']==s and c['role']==role for c in out):return
  out.append({'id':'C'+str(len(out)+1),'text':s,'role':role,'source':evidence[:220],'context':context})
 def singers(s,evidence):
  for name in re.split(r'\s+[×＆&X]\s+',s):add(name,'performer',evidence)
 body=re.sub(r'(?i)^\s*[【\[][^】\]]*(?:SUB|자막|프로세카|シャニマス)[^】\]]*[】\]]\s*','',raw)
 body=re.sub(r'(?i)\s*\(cover\)\s*$','',body).strip();parts=re.split(r'\s+/\s*|\s*/\s+|／',body)
 quotes=re.findall(r'[『「]([^』」]+)[』」]',body)
 credits=bool(re.search(r'(?im)^\s*[■☁🎶]*\s*(?:作曲|作詞.*作曲|音楽|Music\s*(?::|&|\s{2,})|Compose|작곡|曲[:：]|Vocal[:：])',desc))
 hint=cover or translated or bool(quotes) or credits or bool(re.search(r'(?i)3DMV|2DMV|VOCALOID|初音ミク|歌愛ユキ',raw))
 title=quotes[0] if len(quotes)==1 else parts[0]
 title=re.sub(r'(?i)\s*covered\s+by\s+.*$','',title);title=re.sub(r'(?i)\s*\[(?:Long Ver|Fan Upload|자막|한글화)[^]]*\]\s*','',title)
 title=re.sub(r'(?i)\s*\([^)]*(?:Official|Remix)[^)]*\)\s*$','',title).strip()
 title=re.sub(r'(?i)\s*(?:노래방)?커버(?:\s*#.*)?$|\s+(?:Band\s+)?COVER(?:\s*#.*)?$','',title).strip()
 dash=re.match(r'^(.+?)\s+[-–]\s+(.+)$',title)
 voice=re.search(r'(?im)^\s*(?:VOCALOID|Vocal|歌|ボーカル)\s*(?:[:：]|\s{2,}|は)\s*(.+)',desc)
 if dash and hint and voice and key(voice[1]) and key(voice[1]) in key(dash[2]):
  title=dash[1];dash=None
 if dash and hint:
  title=dash[2]
  if not cover and not re.search(r'(?i)뮤지컬|musical',dash[1]) and not any(re.fullmatch(r'\s*[『「]([^』」]+)[』」]\s*',line) and key(re.fullmatch(r'\s*[『「]([^』」]+)[』」]\s*',line)[1]) in key(dash[1]) for line in lines[:12]):add(dash[1],'original_artist',raw)
 for line in lines[:12]:
  q=re.fullmatch(r'\s*[『「]([^』」]+)[』」]\s*',line)
  if q and key(q[1]) in key(raw):title=q[1];break
 if hint and title:add(title,'song_title',raw)
 if translated and len(parts)==3:add(parts[1],'original_artist',raw);singers(re.sub(r'\[[^]]*\]','',parts[2]),raw)
 elif cover:
  by=re.search(r'(?i)covered\s+by\s+(.+)$',raw);vo=re.search(r'(?i)\bVo\.\s*(.+)$',raw)
  if by:singers(by[1],raw)
  elif vo:singers(vo[1],raw)
  elif len(parts)==2:singers(re.sub(r'(?i)\(?cover\)?','',parts[1]),raw)
 elif len(parts)==2 and re.search(r'(?i)3DMV|2DMV',raw+'\n'+desc):singers(re.sub(r'[【\[].*$','',parts[1]),raw)
 original=False
 for index,line in enumerate(lines):
  text=line.strip().lstrip('■□✘●☁🎙️🎶 ')
  while text and (unicodedata.category(text[0])=='So' or text[0].isspace()):text=text[1:]
  if re.search(r'(?i)^(?:-?original\s*-|原曲|本家|\[원곡\]|원곡\s*[:：])',text):original=True
  if re.match(r'(?i)^(?:映像|イラスト|Director|Rec\s*&|動画|Mix)',text):original=False
  explicit=re.match(r'(?i)^(曲名|곡명|Song title|原曲アーティスト|원곡 아티스트|Original artist)\s*[:：]\s*(.+)',text)
  if explicit:add(explicit[2],'song_title' if explicit[1].casefold() in ('曲名','곡명','song title') else 'original_artist',line)
  m=re.match(r'(?i)^(?:作詞[,、/・]作曲|作曲(?:・編曲)?|작사[,、/]작곡|작곡|Music(?:\s*/\s*Movie|\s*&\s*Arrange)?|Composed?|Composer|曲|音楽|音)\s*(?:by\s+|[:：.]\s*|\s{2,})(.+)',text)
  if m and not (re.match(r'(?i)^Music\s+by',text) and re.search(r'(?im)^\s*[■□]?\s*(?:Compose|Composer|作曲|작곡)\s*[:：.]',desc)):add(m[1],'composer',line,'original' if original else 'current')
  m=re.match(r'(?i)^(?:Vocals?|VOCALOID|Vc(?:&MIX)?|Vo\.?|歌|ボーカル|노래|보컬)\s*(?:by\s+|[:：.]\s*|は\s*|\s{2,})(.+)',text)
  if m and not (original and cover):singers(m[1],line)
  if re.match(r'^music\s*-\s*',text,re.I):add(re.sub(r'^music\s*-\s*','',text,flags=re.I),'song_title',line)
  if original:
   m=re.search(r'[「『]([^」』]+)[」』]\s*[-–]\s*(.+)',text)
   if m:add(m[2],'original_artist',line,'original')
   m=re.search(r'\[원곡\]\s*(.+?)\s+[-–]\s+(.+)',text)
   if m:add(m[1],'original_artist',line,'original')
   m=re.match(r'원곡\s+([^()]+)',text)
   if m:add(m[1],'song_title',line,'original')
  if cover and index<5:
   m=re.match(r'^(.+?)\s+/\s+(.+?)\s*様?$',text)
   if m and clean(m[1])==clean(title) and any('youtu' in x for x in lines[index+1:index+3]):add(m[2],'original_artist',line,'original')
  m=re.match(r'^(.+?)さんの\s*$',text)
  if m and cover:add(m[1],'original_artist',line,'original')
 if credits and not any(c['role']=='song_title' for c in out):
  for line in lines[:6]:
   m=re.fullmatch(r'\s*[『「]([^』」]+)[』」]\s*',line)
   if m:add(m[1],'song_title',line);break
 if re.search(r'가창하게 되었습니다|歌いました',desc) and len(parts)==2:singers(parts[1],raw)
 return out[:30]
