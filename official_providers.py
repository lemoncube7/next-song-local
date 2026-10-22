"""Official public karaoke search adapters; no third-party result is official proof."""
import html,json,re,time,urllib.parse,urllib.request
from html.parser import HTMLParser
from functools import lru_cache

BASE={'tj':'https://www.tjmedia.com/song/accompaniment_search','kumyoung':'https://kysing.kr/search/','dam':'https://www.clubdam.com/karaokesearch/','joysound':'https://www.joysound.com/web/search/song'}

def fetch(url,body=None):
    headers={'User-Agent':'Mozilla/5.0 (compatible; NextSong/0.1.14)','Accept':'text/html,application/json','Referer':BASE.get('dam') if 'clubdam.com' in url else url}
    if body is not None:headers['Content-Type']='application/json'
    req=urllib.request.Request(url,data=json.dumps(body).encode() if body is not None else None,headers=headers)
    with urllib.request.urlopen(req,timeout=20) as response:
        raw=response.read(6000001)
        if len(raw)>6000000:raise ValueError('공식 응답 크기 제한')
        return raw.decode('utf8')

class Node:
    def __init__(self,tag='',attrs=()):self.tag=tag;self.attrs=dict(attrs);self.children=[]
    def text(self):return ' '.join((c.text() if isinstance(c,Node) else c) for c in self.children).strip()
    def all(self,cls):
        result=[]
        for c in self.children:
            if isinstance(c,Node):
                if cls in c.attrs.get('class','').split():result.append(c)
                result.extend(c.all(cls))
        return result
class Tree(HTMLParser):
    def __init__(self,text):
        super().__init__(convert_charrefs=True);self.root=Node();self.stack=[self.root];self.feed(text)
    def handle_starttag(self,tag,attrs):
        n=Node(tag,attrs);self.stack[-1].children.append(n)
        if tag not in ('area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'):self.stack.append(n)
    def handle_endtag(self,tag):
        for i in range(len(self.stack)-1,0,-1):
            if self.stack[i].tag==tag:self.stack=self.stack[:i];break
    def handle_data(self,text):self.stack[-1].children.append(text)

def clean(s):return re.sub(r'\s+',' ',s).strip()
def record(brand,no,title,singer,url,**extra):
    no=str(no)
    if not re.fullmatch(r'\d{1,8}(?:-\d{1,3})?',no) or not clean(title) or not clean(singer):return None
    return dict(brand=brand,no=no,title=clean(title),singer=clean(singer),source='official:'+brand,official_url=url,**extra)

def parse_tj(text,url):
    if '반주곡 검색' not in text and '반주곡검색' not in text:raise ValueError('TJ 검색 페이지 형식 변경')
    rows=[]
    for ul in Tree(text).root.all('grid-container'):
        if 'list' not in ul.attrs.get('class','').split():continue
        no=ul.all('num2');title=ul.all('title3');singer=ul.all('singer')
        if no and title and singer:
            row=record('tj',no[0].text(),title[0].text(),singer[0].text(),url)
            if row:rows.append(row)
    return rows

def parse_ky(text,url):
    if 'search_chart' not in text:raise ValueError('금영 검색 페이지 형식 변경')
    rows=[]
    for ul in Tree(text).root.all('search_chart_list'):
        no=ul.all('search_chart_num');titles=ul.all('tit');singer=ul.all('search_chart_sng');release=ul.all('search_chart_rel')
        if no and titles and singer:
            row=record('kumyoung',no[0].text(),titles[0].text(),singer[0].text(),url)
            if row:
                if release:
                    m=re.search(r'(20\d{2})\D*(\d{1,2})',release[0].text())
                    if m:row['release']=f'{m[1]}-{int(m[2]):02d}-01'
                rows.append(row)
    return rows

def flight(text):
    chunks=[]
    for m in re.finditer(r'self\.__next_f\.push\((\[.*?\])\)</script>',text,re.S):
        try:
            a=json.loads(m[1])
            if len(a)>1 and isinstance(a[1],str):chunks.append(a[1])
        except (ValueError,IndexError):pass
    return ''.join(chunks)

def parse_joy(text,url):
    stream=flight(text)
    if not stream or 'JOYSOUND' not in text:raise ValueError('JOYSOUND 검색 페이지 형식 변경')
    rows=[];decoder=json.JSONDecoder()
    # Parse complete result cards so future/preview labels remain attached.
    for m in re.finditer(r'\{"title":',stream):
        try:card,_=decoder.raw_decode(stream[m.start():])
        except ValueError:continue
        if not isinstance(card,dict) or not isinstance(card.get('buttonsProps'),list):continue
        badges=json.dumps(card.get('headerBadges',[]),ensure_ascii=False)
        future=any(word in badges for word in ('配信予定','配信前','未配信'))
        for item in card['buttonsProps']:
            if not isinstance(item,dict) or not item.get('selSongNo'):continue
            row=record('joysound',item.get('selSongNo',''),item.get('songName',''),item.get('artistName',''),url,future=future)
            if row:rows.append(row)
    return list({r['no']:r for r in rows}.values())

@lru_cache(maxsize=1)
def dam_auth():
    text=fetch('https://www.clubdam.com/assets/dkcommon/js/main_karaokesearch.js')
    m=re.search(r'var _authKey\s*=\s*"([^"]+)"',text)
    if not m:raise ValueError('DAM 공개 검색 설정 변경')
    return m[1]

def dam_api(endpoint,payload):
    doc=json.loads(fetch('https://www.clubdam.com/dkwebsys/search-api/'+endpoint,{'modelTypeCode':'1','compId':'1','authKey':dam_auth(),**payload}))
    if doc.get('result',{}).get('statusCode')!='0000':raise ValueError('DAM 조회 오류 '+str(doc.get('result',{}).get('statusCode')))
    return doc

def parse_dam(doc,url,detail=False):
    if doc.get('result',{}).get('statusCode')!='0000':raise ValueError('DAM 응답 오류')
    items=[doc.get('data',{})] if detail else doc.get('list',[]);rows=[]
    for item in items:
        row=record('dam',item.get('requestNo',''),item.get('title',''),item.get('artist',''),BASE['dam']+'songleaf.html?'+urllib.parse.urlencode({'requestNo':item.get('requestNo','')}),release=item.get('releaseDate',''),future=item.get('futureReleaseFlag')=='1')
        if row:
            if detail:
                models=[]
                for group in doc.get('list',[]):
                    for info in group.get('kModelMusicInfoList',[]):
                        for model in info.get('eachModelMusicInfoList',[]):
                            models.append({'name':model.get('karaokeModelName',''),'release':model.get('releaseDate','')})
                row['models']=models
            rows.append(row)
    return rows

def search(brand,kind,value):
    """Bounded public search; a miss is not proof of unavailability."""
    if not value or len(value)>160:raise ValueError('검색어 길이 오류')
    if brand=='tj':
        url=BASE[brand]+'?'+urllib.parse.urlencode({'strType':'16' if kind=='number' else '1','searchTxt':value,'pageNo':1,'pageRowCnt':100})
        return parse_tj(fetch(url),url)
    if brand=='kumyoung':
        url=BASE[brand]+'?'+urllib.parse.urlencode({'category':'1' if kind=='number' else '2','keyword':value})
        return parse_ky(fetch(url),url)
    if brand=='dam':
        if kind=='number':
            if '-' not in value and len(value)==6:value=value[:4]+'-'+value[4:]
            return parse_dam(dam_api('GetMusicDetailInfoApi',{'requestNo':value}),BASE[brand],True)
        return parse_dam(dam_api('SearchMusicByKeywordApi',{'serialNo':'BA000001','keyword':value,'contentsCode':None,'serviceCode':None,'sort':'2','dispCount':'100','pageNo':'1'}),BASE[brand])
    if brand=='joysound':
        # Search pages expose selectable karaoke numbers, rather than music-video IDs.
        url=BASE[brand]+'?'+urllib.parse.urlencode({'keyword':value,'match':'1'})
        return parse_joy(fetch(url),url)
    raise ValueError('지원하지 않는 노래방')
