"""PC device pairing for the hosted friends service; no watch-history upload."""
import base64,json,threading,time,urllib.request,urllib.error
import core,friends,personal_sync
BASE='https://next-song-mobile.lemoncube07.chatgpt.site'
LOCK=threading.Lock()
def path():return core.ROOT/'data/server-sync.json'
def config():
    try:return json.loads(path().read_text(encoding='utf8'))
    except (OSError,ValueError):return {}
def write(c):
    p=path();p.parent.mkdir(parents=True,exist_ok=True);t=p.with_suffix('.tmp');t.write_text(json.dumps(c),encoding='utf8');t.replace(p)
def request(route,payload=None,method=None,token=None):
    headers={'User-Agent':'Mozilla/5.0 NextSong/1.3','Accept':'application/json'}
    if token:headers['Authorization']='Bearer '+token
    if payload is not None:headers['Content-Type']='application/json'
    req=urllib.request.Request(BASE+'/api/server'+route,data=json.dumps(payload).encode() if payload is not None else None,headers=headers,method=method or ('POST' if payload is not None else 'GET'))
    try:
        with urllib.request.urlopen(req,timeout=25) as r:return json.load(r)
    except urllib.error.HTTPError as e:
        try:message=json.load(e).get('error','서버 연결 오류')
        except (ValueError,AttributeError):message='서버 연결 오류: '+str(e.code)
        raise ValueError(message) from None
    except OSError:raise ValueError('친구 서버에 연결하지 못했어요. 잠시 후 다시 시도하세요.') from None
def token(c):return personal_sync.protect(base64.b64decode(c['protected_token']),decrypt=True).decode()
def begin():
    c=config()
    if c.get('protected_token'):
        try:
            p=request('/devices/poll',token=token(c))
            if p['status']=='approved':return {'status':'approved','url':BASE+'/#friends'}
            return {'status':'pending','code':c['code'],'url':BASE+'/?pair='+c['code']}
        except ValueError:pass
    r=request('/devices/start',{});write({'protected_token':base64.b64encode(personal_sync.protect(r['token'].encode())).decode(),'code':r['code'],'expires':r['expires']})
    return {'status':'pending','code':r['code'],'url':r['verification_url']}
def status():
    c=config()
    if not c.get('protected_token'):return {'status':'disconnected','url':BASE+'/#friends'}
    t=token(c);p=request('/devices/poll',token=t)
    if p['status']!='approved':return {'status':'pending','code':c['code'],'url':BASE+'/?pair='+c['code']}
    me=request('/me',token=t);return {'status':'approved','profile':me['profile'],'url':BASE+'/#friends','last_sync':c.get('last_sync'), 'count':c.get('count',0)}
def sync(db):
    c=config()
    if not c.get('protected_token'):raise ValueError('먼저 서버를 연결해 주세요.')
    t=token(c);p=request('/me',token=t).get('profile')
    if not p or not p.get('share'):raise ValueError('모바일 친구 탭에서 곡 공유를 먼저 켜세요.')
    songs=friends.shelf(core.tracks(db));old=request('/shelf',token=t)
    if old['songs']!=songs:request('/shelf',{'songs':songs,'revision':old['revision']},'PUT',t)
    c.update(last_sync=int(time.time()),count=len(songs));write(c);return {'count':len(songs),'status':'synced'}
def scheduler():
    def run():
        while True:
            time.sleep(120)
            if not config().get('protected_token'):continue
            if not LOCK.acquire(False):continue
            db=None
            try:db=core.connect();sync(db)
            except Exception:pass
            finally:
                if db:db.close()
                LOCK.release()
    threading.Thread(target=run,daemon=True).start()
