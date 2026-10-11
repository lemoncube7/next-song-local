"""Bounded public song metadata searches; no lyrics are stored."""
import html, json, re, threading, time, urllib.parse, urllib.request, urllib.error
from html.parser import HTMLParser
import core

SLOTS=threading.BoundedSemaphore(2)
class Text(HTMLParser):
    def __init__(self):super().__init__();self.parts=[]
    def handle_data(self,data):self.parts.append(data)
def plain(value):
    p=Text();p.feed(value);return ' '.join(' '.join(p.parts).split())
def parse(provider, document):
    result=[]
    for row in re.findall(r'<tr\b[^>]*>(.*?)</tr>',document,re.S|re.I):
        if provider=='utaten':
            title=re.search(r'<p\b[^>]*class="searchResult__title"[^>]*>\s*<a\b[^>]*href="(/lyric/[^"?]+/)"[^>]*>(.*?)</a>',row,re.S)
            artist=re.search(r'class="searchResult__artist".*?<a\b[^>]*>(.*?)</a>',row,re.S)
            if title and artist:result.append({'title':plain(title[2]),'artist':plain(artist[1]),'url':'https://utaten.com'+title[1],'provider':'UtaTen'})
        else:
            title=re.search(r'<p\b[^>]*class="title"[^>]*>.*?<a\b[^>]*>(.*?)</a>',row,re.S)
            artist=re.search(r'<p\b[^>]*class="artist"[^>]*>.*?<a\b[^>]*>(.*?)</a>',row,re.S)
            track=re.search(r'https://music\.bugs\.co\.kr/track/(\d+)',row)
            if title and artist and track:result.append({'title':plain(title[1]),'artist':plain(artist[1]),'url':'https://music.bugs.co.kr/track/'+track[1],'provider':'Bugs'})
    return list({(r['title'],r['artist'],r['url']):r for r in result}.values())[:30]

class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        u=urllib.parse.urlparse(newurl)
        if u.scheme!='https' or u.hostname!=urllib.parse.urlparse(req.full_url).hostname:raise ValueError('검색 사이트 밖으로 이동하는 요청은 중단했습니다.')
        return super().redirect_request(req,fp,code,msg,headers,newurl)

def search(db,title,artist='',provider='auto'):
    title=title.strip();artist=artist.strip()
    if not title or len(title)>300 or len(artist)>300:raise ValueError('검색할 곡명을 입력해 주세요.')
    jp=bool(re.search(r'[\u3040-\u30ff\u4e00-\u9fff]',title+artist))
    if provider not in ('auto','utaten','bugs'):raise ValueError('검색 사이트를 확인해 주세요.')
    provider=('utaten' if jp else 'bugs') if provider=='auto' else provider
    jp=provider=='utaten';key=provider+'|'+title+'|'+artist
    cache=core.get_state(db,'song_search_cache',{},'user_state');saved=cache.get(key)
    if saved and time.time()-saved['time']<86400:return {**saved['result'],'cached':True}
    query=urllib.parse.urlencode({'title':title,'artist_name':artist,'show_artists':'1'}) if jp else urllib.parse.urlencode({'q':title+' '+artist})
    url=('https://utaten.com/lyric/search?' if jp else 'https://music.bugs.co.kr/search/integrated?')+query
    if not SLOTS.acquire(blocking=False):raise ValueError('다른 곡을 검색 중이에요. 잠시 후 다시 눌러 주세요.')
    try:
        req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0','Accept':'text/html'})
        with urllib.request.build_opener(SafeRedirect()).open(req,timeout=15) as response:
            raw=response.read(4*1024*1024+1)
            if len(raw)>4*1024*1024:raise ValueError('검색 응답이 너무 큽니다.')
            document=raw.decode(response.headers.get_content_charset() or 'utf-8',errors='replace')
        if re.search(r'captcha|access denied',document,re.I):raise ValueError('검색 사이트에서 자동 접근을 제한했습니다.')
        candidates=parse(provider,document)
        candidates.sort(key=lambda r:(core.norm(r['title'])!=core.norm(title),core.norm(core.canonical(r['artist']))!=core.norm(core.canonical(artist))))
        result={'candidates':candidates,'provider':'UtaTen' if jp else 'Bugs','search_url':url,'cached':False,'reason':'곡명과 아티스트를 확인한 뒤 선택해 주세요.' if candidates else '사이트에서 곡 후보를 찾지 못했어요. 검색 결과 페이지에서 확인할 수 있어요.'}
        cache[key]={'time':time.time(),'result':result}
        if len(cache)>500:cache=dict(sorted(cache.items(),key=lambda x:x[1]['time'],reverse=True)[:500])
        core.set_state(db,'song_search_cache',cache,'user_state');db.commit();return result
    except (urllib.error.URLError,TimeoutError,OSError) as exc:
        raise ValueError('검색 사이트 연결에 실패했어요. 잠시 후 다시 시도해 주세요.') from exc
    finally:SLOTS.release()
