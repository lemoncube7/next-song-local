"""Local reverse lookup using an Aho-Corasick title index and artist evidence."""
import json,re,time
from collections import deque,defaultdict
import core,bulk_recognition,recognition

class TitleIndex:
    def __init__(self,titles):
        self.next=[{}];self.fail=[0];self.out=[[]]
        for title in titles:
            state=0
            for char in title:
                if char not in self.next[state]:
                    self.next[state][char]=len(self.next);self.next.append({});self.fail.append(0);self.out.append([])
                state=self.next[state][char]
            self.out[state].append(title)
        queue=deque(self.next[0].values())
        while queue:
            state=queue.popleft()
            for char,child in self.next[state].items():
                queue.append(child);f=self.fail[state]
                while f and char not in self.next[f]:f=self.fail[f]
                self.fail[child]=self.next[f].get(char,0);self.out[child].extend(self.out[self.fail[child]])
    def find(self,text):
        result=set();state=0
        for char in text:
            while state and char not in self.next[state]:state=self.fail[state]
            state=self.next[state].get(char,0);result.update(self.out[state])
        return result

def match(video,rows,index):
    raw=video.get('title') or video.get('history_title','');nt=core.norm(raw)
    if re.search(r'(?i)歌枠|歌配信|medley|メドレー|playlist|作業用|耐久|모음|\blive\b|reaction|리액션|interview|인터뷰|雑談',raw):return []
    music=bulk_recognition.music_evidence(video,{'track':{}}) or bool(re.search(r'(?i)cover|歌ってみた|커버|歌詞|가사|lyrics|subbed',raw))
    if not music:return []
    keys=index.find(nt)
    exact={nt}|{core.norm(s) for s in re.findall(r'[「『]([^」』]+)[」』]',raw)}
    keys.update(k for k in exact if k in rows)
    credits=[]
    for line in video.get('description','').splitlines():
        m=re.match(r'(?i)^\s*[■□・●]*\s*(?:Original(?: song)?(?: by)?|原曲|本家(?:様)?|원곡|Music|作曲|音楽)\s*[:：]?\s+(.+)$',line)
        if m:credits.append(core.norm(m[1]))
    channel=core.norm(core.number_artist(video.get('channel') or video.get('history_channel','')))
    groups={}
    for key in keys:
        if not key or key.isdigit():continue
        if len(key)<3 and key not in exact:continue
        for row in rows[key]:
            song=core.catalogue_title(row['title'])
            if re.fullmatch(r'[A-Za-z0-9 ]+',song) and not re.search(r'(?i)(?<![A-Za-z0-9])'+re.escape(song)+r'(?![A-Za-z0-9])',raw):continue
            artist=core.number_artist(row['singer']);na=core.norm(artist)
            if len(na)<3:continue
            # Latin names must be separate words rather than arbitrary title substrings.
            in_title=na in nt
            if re.fullmatch(r'[A-Za-z0-9 ]+',artist):in_title=bool(re.search(r'(?i)(?<![A-Za-z0-9])'+re.escape(artist)+r'(?![A-Za-z0-9])',raw))
            forms={na}
            for group in core.ARTIST_GROUPS:
                if na in {core.norm(g) for g in group}:
                    forms.update(core.norm(g) for g in group)
                    in_title=in_title or any(bool(re.search(r'(?i)(?<![A-Za-z0-9])'+re.escape(g)+r'(?![A-Za-z0-9])',raw)) for g in group if len(core.norm(g))>=3)
            if not (channel==na or in_title or any(f in c for f in forms for c in credits)):continue
            identity=(key,na)
            value=groups.setdefault(identity,{'title':core.catalogue_title(row['title']),'artist':artist,'numbers':[],'confident':True,'reason':'노래방 수록곡의 제목과 가수·원곡 크레딧이 영상 정보와 함께 일치'})
            value['numbers'].append({'brand':row['brand'],'no':str(row['no'])})
    # Prefer the longer full title, keeping different artists or versions ambiguous.
    return [v for (title,artist),v in groups.items() if not any(artist==a and title!=t and title in t for t,a in groups)]

def run(db,write_lock):
    db.execute('CREATE TABLE IF NOT EXISTS reverse_catalogue_matches (id TEXT PRIMARY KEY,data TEXT)');db.commit()
    rows=defaultdict(list)
    for r in db.execute('SELECT data FROM catalogue'):
        row=json.loads(r[0]);key=core.norm(core.catalogue_title(row['title']))
        if key:rows[key].append(row)
    index=TitleIndex(k for k in rows if len(k)>=3 and len(k)<=120 and not k.isdigit())
    watched={r[0] for r in db.execute('SELECT DISTINCT video_id FROM events WHERE video_id IS NOT NULL')}
    state={'status':'running','catalogue_rows':sum(map(len,rows.values())),'total':len(watched),'done':0,'saved':0,'candidates':0,'started_at':time.time()}
    pending=[]
    def flush(final=False):
        with write_lock:
            edits=core.get_state(db,'corrections',{},'user_state')
            for vid,candidates in pending:
                latest=core.video_data(db,vid)
                if vid in edits or latest.get('classification',{}).get('status') in ('song','excluded'):continue
                db.execute('INSERT OR REPLACE INTO reverse_catalogue_matches VALUES (?,?)',(vid,json.dumps(candidates,ensure_ascii=False)))
                if len(candidates)==1:
                    c=candidates[0];edits[vid]={**c,'source':'auto_recognition','exclude':False}
                    latest['classification']=core.classify(latest,correction=edits[vid]);core.save_video(db,latest);state['saved']+=1
                    db.execute('INSERT OR REPLACE INTO recognition_results VALUES (?,?)',(vid,json.dumps({'status':'recognized','saved':True,'track':c,'candidates':candidates},ensure_ascii=False)))
                else:state['candidates']+=1
            core.set_state(db,'corrections',edits,'user_state');core.set_state(db,'reverse_catalogue_job',state);db.commit();pending.clear()
            if final:core.rebuild(db)
    flush()
    edits=core.get_state(db,'corrections',{},'user_state')
    for r in db.execute('SELECT id,data FROM videos').fetchall():
        if r['id'] not in watched:continue
        v=json.loads(r['data']);state['done']+=1
        if r['id'] not in edits and v.get('classification',{}).get('status') not in ('song','excluded'):
            found=match(v,rows,index)
            if found:pending.append((r['id'],found))
        if state['done']%2000==0:flush()
    state['status']='complete';state['finished_at']=time.time();flush(True)
    return state
