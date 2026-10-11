"""Streaming reader for Google My Activity HTML. Does not execute HTML."""
from collections import Counter, deque
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
import re

def activity_time(text):
    m=re.search(r'(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})\.\s*(오전|오후)\s*(\d{1,2}):(\d{2}):(\d{2})\s*(KST|UTC|GMT)',text)
    if not m:return None
    y,month,day,ampm,hour,minute,second,zone=m.groups()
    hour=int(hour)%12+(12 if ampm=='오후' else 0)
    tz=timezone(timedelta(hours=9)) if zone=='KST' else timezone.utc
    return datetime(int(y),int(month),int(day),hour,int(minute),int(second),tzinfo=tz).astimezone(timezone.utc).isoformat().replace('+00:00','Z')

class ActivityParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth=0;self.outer=None;self.primary=None;self.seen_primary=False
        self.parts=[];self.links=[];self.anchor=None;self.ready=deque();self.counts=Counter()
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=='div':
            self.depth+=1;classes=attrs.get('class','').split()
            if 'outer-cell' in classes:
                self.outer=self.depth;self.primary=None;self.seen_primary=False;self.parts=[];self.links=[];self.anchor=None
            elif self.outer and 'content-cell' in classes and 'mdl-cell--6-col' in classes and 'mdl-typography--text-right' not in classes and not self.seen_primary:
                self.primary=self.depth;self.seen_primary=True
        if self.primary:
            if tag=='br':self.parts.append('\n')
            if tag=='a':self.anchor={'url':attrs.get('href',''),'parts':[]}
    def handle_data(self,data):
        if self.primary:
            self.parts.append(data)
            if self.anchor is not None:self.anchor['parts'].append(data)
    def handle_endtag(self,tag):
        if tag=='a' and self.anchor is not None:
            self.links.append({'url':self.anchor['url'],'title':''.join(self.anchor['parts'])});self.anchor=None
        if tag=='div':
            if self.primary==self.depth:self.primary=None
            if self.outer==self.depth:
                self.emit();self.outer=None
            self.depth=max(0,self.depth-1)
    def emit(self):
        self.counts['activity_cards']+=1;text=''.join(self.parts)
        if '시청했습니다' not in text and not text.lstrip().startswith('Watched '):
            self.counts['non_watch_cards']+=1;return
        date=activity_time(text)
        if not date:self.counts['unparsed_watch_time']+=1;return
        link=next((a for a in self.links if re.search(r'(?:youtube\.com/watch\?|youtube\.com/post/|youtu\.be/)',a['url'])),None)
        channel=next((a for a in self.links if '/channel/' in a['url'] or '/@' in a['url']),None)
        title=link['title'] if link else text.split('\n')[0]
        row={'time':date,'title':title,'titleUrl':link['url'] if link else '',
             'subtitles':[{'name':channel['title'],'url':channel['url']}] if channel else [],
             '_time_precision':'second','_source':'my_activity_html'}
        self.ready.append(row);self.counts['watch_records']+=1

def iter_rows(stream,report=None):
    import codecs
    parser=ActivityParser();decoder=codecs.getincrementaldecoder('utf-8-sig')()
    while True:
        chunk=stream.read(128*1024)
        if not chunk:break
        parser.feed(decoder.decode(chunk))
        while parser.ready:yield parser.ready.popleft()
    parser.feed(decoder.decode(b'',final=True));parser.close()
    while parser.ready:yield parser.ready.popleft()
    if report is not None:report.update(parser.counts)
