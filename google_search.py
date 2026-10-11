"""Google full-video-title search in an isolated, anonymous browser profile."""
import json, os, re, subprocess, tempfile, threading, time, urllib.parse
from html.parser import HTMLParser
from pathlib import Path
import core, recognition

LOCK=threading.Lock()
class Results(HTMLParser):
    def __init__(self):super().__init__();self.links=[];self.heading=None;self.results=[]
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=='a':self.links.append(attrs.get('href',''))
        if tag=='h3':self.heading={'parts':[],'url':self.links[-1] if self.links else ''}
    def handle_data(self,data):
        if self.heading is not None:self.heading['parts'].append(data)
    def handle_endtag(self,tag):
        if tag=='h3' and self.heading is not None:
            title=' '.join(''.join(self.heading['parts']).split());url=urllib.parse.urljoin('https://www.google.com',self.heading['url'])
            if self.heading['url'] and title and urllib.parse.urlparse(url).scheme in ('http','https'):self.results.append({'title':title,'url':url})
            self.heading=None
        if tag=='a' and self.links:self.links.pop()

def parse(document):
    p=Results();p.feed(document);items=list({(x['title'],x['url']):x for x in p.results}.values())[:20]
    candidates=[]
    for item in items:
        title=item['title']
        match=re.match(r'^(.+?)\s*[\-–—‑]\s*曲[・･]歌詞[:：]\s*(.+?)(?:\s*\|\s*Spotify)?$',title)
        if not match:match=re.match(r'^(.+?)\s*[\-–—]\s*(?:song and lyrics by|Song by)\s+(.+?)(?:\s*\|\s*Spotify)?$',title,re.I)
        if match:candidates.append({'title':match[1].strip(),'artist':match[2].strip(),'url':item['url'],'provider':'Google','reason':'Google 검색에 나온 곡 정보'})
    return items,recognition.merge_candidates(candidates)

def search(db,query):
    query=query.strip()
    if not query or len(query)>500:raise ValueError('영상 제목을 확인해 주세요.')
    url='https://www.google.com/search?'+urllib.parse.urlencode({'q':query})
    cache=core.get_state(db,'google_search_cache',{})
    saved=cache.get(query)
    if saved and time.time()-saved['time']<86400:return {**saved['result'],'cached':True}
    chrome=next((Path(p) for p in [r'C:\Program Files\Google\Chrome\Application\chrome.exe',r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe'] if Path(p).exists()),None)
    if not chrome:raise ValueError('Google 결과를 읽는 데 필요한 Chrome을 찾지 못했어요.')
    if not LOCK.acquire(timeout=35):raise ValueError('다른 Google 검색을 처리 중이에요. 잠시 후 다시 눌러 주세요.')
    try:
        root=(core.ROOT/'data'/'google-browser').resolve();root.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='query-',dir=root,ignore_cleanup_errors=True) as profile:
            if not Path(profile).resolve().is_relative_to(root):raise ValueError('검색용 폴더 경로 오류')
            command=[str(chrome),'--headless=new','--disable-gpu','--no-first-run','--no-default-browser-check','--disable-extensions','--disable-sync','--disable-background-networking','--disable-component-update','--user-data-dir='+profile,'--dump-dom','--timeout=20000','--virtual-time-budget=6000',url]
            run=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=30,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        document=run.stdout[:6*1024*1024].decode('utf8',errors='replace');items,candidates=parse(document)
        blocked=not items and bool(re.search(r'Our systems have detected unusual traffic|unusual traffic from|/sorry/|g-recaptcha',document,re.I))
        status='blocked' if blocked else 'ok' if items else 'unavailable'
        result={'query':query,'provider':'Google','search_url':url,'results':items,'candidates':candidates,'status':status,'cached':False,'reason':'Google에서 자동 검색을 제한했어요. 검색 결과를 직접 열어 확인해 주세요.' if blocked else 'Google 전문 검색 결과를 확인해 주세요.' if items else 'Google 검색 결과를 읽지 못했어요. 검색 결과를 직접 열어 확인해 주세요.'}
        if status=='ok':
            cache[query]={'time':time.time(),'result':result}
            cache=dict(sorted(cache.items(),key=lambda x:x[1]['time'],reverse=True)[:200])
            core.set_state(db,'google_search_cache',cache);db.commit()
        return result
    except subprocess.TimeoutExpired as exc:raise ValueError('Google 검색 응답이 늦어 중단했어요. 검색 결과를 직접 열어 확인해 주세요.') from exc
    finally:LOCK.release()
