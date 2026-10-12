"""Evidence-based display aliases; no fuzzy substring identity matching."""
import re,unicodedata
import core
JP=r'[\u3040-\u30ff\u4e00-\u9fff]'
VERSION=r'(?i)\blive\b|remix|instrumental|karaoke|re-record|remaster|\bcover\b|ライブ|歌ってみた|커버|inst\.'

def variants(title):
 text=unicodedata.normalize('NFKC',title).strip()
 text=re.sub(r'(?i)\s+feat\.?\s*.*$','',text).strip()
 text=core.catalogue_title(text)
 result={text}
 parts=re.split(r'\s+[-–]\s+',text)
 if len(parts)==2 and not re.search(VERSION,text) and re.search(JP,parts[0]) and re.search(r'[A-Za-z]',parts[1]) and not re.search(JP,parts[1]):result.update(parts)
 return {p.strip(' 「」『』\"') for p in result if core.norm(p)}

def video_labels(video,track):
 raw=unicodedata.normalize('NFKC',video.get('title') or video.get('history_title',''))
 if re.search(VERSION,raw):return []
 channel=video.get('channel') or video.get('history_channel','')
 channel=re.sub(r'(?i)\s*-\s*Topic$|\s+official(?: channel)?$','',channel).strip()
 # New bilingual pairs must come from this track's original artist channel.
 channel_parts=re.split(r'\s*[/／]\s*',channel)
 known_artist=core.norm(core.canonical(track['artist']))
 if not any(core.norm(core.canonical(p))==known_artist for p in channel_parts) and not (len(known_artist)>=3 and known_artist in core.norm(channel)):return []
 names={track['artist'],channel}
 for group in core.ARTIST_GROUPS:
  if any(core.norm(core.canonical(n))==core.norm(core.canonical(track['artist'])) for n in group):names.update(group)
 patterns=[re.escape(name).replace(r'\ ',r'\s+') for name in names if name]
 author_pattern='(?:'+'|'.join(sorted(patterns,key=len,reverse=True))+')'
 raw=re.sub(r'(?i)^'+author_pattern+r'(?:\s+'+author_pattern+r')*\s*[-–]\s*','',raw)
 for name in sorted(names,key=len,reverse=True):
  raw=re.sub(r'(?i)^'+re.escape(name)+r'\s*[-–]\s*','',raw)
 # Strip an explicit repeated artist before the translated title.
 for name in names:raw=re.sub(r'(?i)\s*,\s*'+re.escape(name)+r'\s*[-–]\s*',' - ',raw)
 raw=re.sub(r'(?i)\s*[【\[](?:official|MV|music video)[^】\]]*[】\]]\s*$','',raw)
 labels=variants(raw)
 artist_keys={core.norm(n) for n in names}
 labels={label for label in labels if core.norm(label) not in artist_keys and not any(core.norm(label).startswith(key) for key in artist_keys if len(key)>=3)}
 existing=set().union(*(variants(a['title']) for a in [track]+track.get('aliases',[])))
 if not {core.norm(x) for x in labels}.intersection(core.norm(x) for x in existing):return []
 return [{'title':label,'artist':track['artist']} for label in sorted(labels) if len(label)<=200]
