"""Opt-in encrypted personal PC/phone relay. No raw watch events exported."""
import base64,ctypes,gzip,json,os,secrets,threading,time
from pathlib import Path
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
import core,github_sync,mobile_transfer

LOCK=threading.Lock();STATE={'status':'idle'};AAD=b'next-song-personal-v1'
def path():return core.ROOT/'data/personal-sync.json'
def config():
    try:return json.loads(path().read_text(encoding='utf8'))
    except (OSError,ValueError):return {'enabled':False}
def public_config():
    c=config();return {k:c.get(k) for k in ('enabled','repo','vault')}
def protect(data,decrypt=False):
    if os.name!='nt':raise ValueError('자동 개인 동기화의 비밀 저장은 Windows 실행본에서 지원해요.')
    class Blob(ctypes.Structure):_fields_=[('size',ctypes.c_ulong),('data',ctypes.POINTER(ctypes.c_ubyte))]
    buffer=ctypes.create_string_buffer(data);source=Blob(len(data),ctypes.cast(buffer,ctypes.POINTER(ctypes.c_ubyte)));target=Blob()
    crypt=ctypes.windll.crypt32
    function=crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    function.argtypes=[ctypes.POINTER(Blob),ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_ulong,ctypes.POINTER(Blob)]
    function.restype=ctypes.c_int
    if not function(ctypes.byref(source),None,None,None,None,1,ctypes.byref(target)):raise ValueError('Windows의 암호 보호 기능을 사용할 수 없어요.')
    try:return ctypes.string_at(target.data,target.size)
    finally:
        free=ctypes.windll.kernel32.LocalFree;free.argtypes=[ctypes.c_void_p];free.restype=ctypes.c_void_p;free(target.data)
def configure(db,payload):
    old=config();enabled=bool(payload.get('enabled'));repo=payload.get('repo') or github_sync.config().get('repo','')
    if enabled and not github_sync.re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repo):raise ValueError('비공개 저장소를 먼저 설정하세요.')
    password=payload.get('password','')
    if password:
        if not isinstance(password,str) or not 12<=len(password)<=300:raise ValueError('개인 동기화 암호를 12~300자로 설정해 주세요.')
        if old.get('protected_password') and protect(base64.b64decode(old['protected_password']),decrypt=True).decode()!=password:raise ValueError('기존 동기화 암호 변경은 아직 지원하지 않아요. 기존 암호를 사용하거나 암호 입력란을 비워 주세요.')
        old['protected_password']=base64.b64encode(protect(password.encode())).decode()
    if enabled and not old.get('protected_password'):raise ValueError('휴대폰에서도 사용할 개인 동기화 암호를 입력하세요.')
    old.update(enabled=enabled,repo=repo,vault=mobile_transfer.source_id(db))
    path().parent.mkdir(exist_ok=True,parents=True);temporary=path().with_suffix('.tmp');temporary.write_text(json.dumps(old),encoding='utf8');temporary.replace(path())
    return public_config()
def derive(password,salt):return PBKDF2HMAC(algorithm=hashes.SHA256(),length=32,salt=salt,iterations=310000).derive(password.encode())
def seal(doc,password,salt=None):
    salt=salt or secrets.token_bytes(16);iv=secrets.token_bytes(12)
    data=gzip.compress(json.dumps(doc,ensure_ascii=False,separators=(',',':')).encode(),mtime=0)
    cipher=AESGCM(derive(password,salt)).encrypt(iv,data,AAD)
    b64=lambda b:base64.b64encode(b).decode()
    return {'format':'next-song-personal-encrypted','version':1,'kdf':'PBKDF2-SHA256','iterations':310000,'salt':b64(salt),'iv':b64(iv),'ciphertext':b64(cipher),'compression':'gzip'}
def open_envelope(doc,password):
    if doc.get('format')!='next-song-personal-encrypted' or doc.get('version')!=1 or doc.get('iterations')!=310000 or doc.get('compression')!='gzip' or doc.get('kdf')!='PBKDF2-SHA256':raise ValueError('개인 동기화 파일 형식 오류')
    try:
        salt=base64.b64decode(doc['salt'],validate=True);iv=base64.b64decode(doc['iv'],validate=True);cipher=base64.b64decode(doc['ciphertext'],validate=True)
        if len(salt)!=16 or len(iv)!=12 or len(cipher)>1500000:raise ValueError()
        compressed=AESGCM(derive(password,salt)).decrypt(iv,cipher,AAD)
        import zlib
        unzip=zlib.decompressobj(31);plain=unzip.decompress(compressed,25000001)
        if len(plain)>25000000 or not unzip.eof:raise ValueError()
        value=json.loads(plain)
        if value.get('format')!='next-song-personal' or value.get('version')!=1 or not isinstance(value.get('operations'),list):raise ValueError()
        return value,salt
    except Exception:raise ValueError('동기화 암호가 다르거나 파일이 손상됐어요. 기존 파일은 덮어쓰지 않았어요.') from None
def run(db,write_lock):
    c=config()
    if not c.get('enabled'):return
    password=protect(base64.b64decode(c['protected_password']),decrypt=True).decode()
    token=github_sync.credential({'repo':c['repo']});request=github_sync.request
    meta=request('/repos/'+c['repo'],token)
    if not meta.get('private'):raise ValueError('개인 동기화는 비공개 저장소에서만 사용할 수 있어요.')
    target='/repos/'+c['repo']+'/contents/personal/'+c['vault']+'.json'
    for attempt in range(3):
        old=request(target,token,missing_ok=True);remote=None;salt=None
        if old:
            if old.get('size',0)>1400000 or not old.get('content'):raise ValueError('동기화 파일이 너무 커요. 파일 교환을 사용하세요.')
            remote,salt=open_envelope(json.loads(base64.b64decode(old['content'])),password)
            if remote['snapshot'].get('source_id')!=c['vault']:raise ValueError('다른 PC의 개인 동기화 파일이에요. 덮어쓰지 않았어요.')
        ops=remote.get('operations',[]) if remote else []
        with write_lock:
            if ops:mobile_transfer.apply(db,{'format':mobile_transfer.OPERATIONS,'version':1,'source_id':c['vault'],'device_id':c['vault'],'operations':ops})
            snapshot=mobile_transfer.snapshot(db,c['repo']);db.commit()
        ack=set(snapshot['acknowledged_operations']);pending=[op for op in ops if op['id'] not in ack]
        if remote:
            a=dict(remote['snapshot']);b=dict(snapshot);a.pop('created_at',None);b.pop('created_at',None)
            if a==b and pending==ops:
                STATE.update(status='complete',finished_at=time.time(),applied=0,pending=len(pending));return
        content=base64.b64encode(json.dumps(seal({'format':'next-song-personal','version':1,'snapshot':snapshot,'operations':pending},password,salt)).encode()).decode()
        if len(content)>1200000:raise ValueError('동기화 데이터가 너무 커요. 파일 교환으로 가져오세요.')
        body={'message':'Sync encrypted personal song shelf','branch':meta['default_branch'],'content':content}
        if old:body['sha']=old['sha']
        if not config().get('enabled'):return
        try:request(target,token,body)
        except ValueError as error:
            if '409' in str(error) and attempt<2:continue
            raise
        STATE.update(status='complete',finished_at=time.time(),applied=len(ops)-len(pending),pending=len(pending));return
def start(write_lock):
    if not config().get('enabled') or not LOCK.acquire(blocking=False):return False
    STATE.clear();STATE.update(status='running')
    def work():
        db=core.connect()
        try:run(db,write_lock)
        except Exception as error:STATE.update(status='error',reason=str(error) if isinstance(error,ValueError) else type(error).__name__)
        finally:db.close();LOCK.release()
    threading.Thread(target=work,daemon=True).start();return True
def scheduler(write_lock):
    def work():
        while True:
            start(write_lock);time.sleep(60)
    threading.Thread(target=work,daemon=True).start()
