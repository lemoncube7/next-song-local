"""Cached, paced official availability checks and weekly refresh while PC app runs."""
import json,time,threading,urllib.error
from datetime import datetime,timezone
import core,official_providers as providers
WEEK=7*86400;LOCK=threading.Lock();STOP=threading.Event();BRANDS=('tj','kumyoung','dam','joysound')

def ensure(db):
    db.execute('CREATE TABLE IF NOT EXISTS official_numbers(brand TEXT,no TEXT,data TEXT,PRIMARY KEY(brand,no))')
    db.execute('CREATE TABLE IF NOT EXISTS official_queries(key TEXT PRIMARY KEY,data TEXT)')

def number_key(brand,no):return brand,str(no).replace('-','').lstrip('0') or '0'

def overlay(db,tracks,now=None):
    if not core.get_state(db,'official_catalogue_enabled',False):return tracks
    now=time.time() if now is None else now
    proofs={number_key(r['brand'],r['no']):json.loads(r['data']) for r in db.execute('SELECT * FROM official_numbers')}
    today=datetime.fromtimestamp(now,timezone.utc).date().isoformat()
    for t in tracks:
        accepted=[];pending=list(t.get('match_candidates',[]))
        for n in t.get('numbers',[]):
            p=proofs.get(number_key(n['brand'],n['no']))
            if p:
                same=core.norm(core.catalogue_title(n.get('title',t['title'])))==core.norm(core.catalogue_title(p['title'])) and core.norm(core.number_artist(n.get('artist',t['artist'])))==core.norm(core.number_artist(p['singer']))
                # Proof must describe this number and this matched song, never only its brand.
                if same and 0<=now-p.get('checked_at',0)<WEEK and not p.get('future') and (not p.get('release') or p['release'][:10]<=today):
                    accepted.append({**n,'source':p['source'],'official_verified':True,'official_url':p['official_url'],'checked_at':p['checked_at'],'models':p.get('models',[]),'release':p.get('release','')});continue
            if n.get('source')=='manual':accepted.append({**n,'official_verified':False,'verification_status':'manual'});continue
            pending.append({**n,'official_verified':False,'reason':'공식 재확인 필요' if p else '공식 확인 대기'})
        t['numbers']=accepted
        keys={(n['brand'],str(n['no'])) for n in accepted}
        t['match_candidates']=list({(n['brand'],str(n['no'])):n for n in pending if (n['brand'],str(n['no'])) not in keys}.values())
    return tracks

def plan(db,limit=None):
    ensure(db);cache={r[0]:json.loads(r[1]) for r in db.execute('SELECT key,data FROM official_queries')};now=time.time();jobs={}
    for t in sorted(core.tracks(db),key=lambda x:-x.get('history_records',0)):
        numbers=t.get('numbers',[])+t.get('match_candidates',[])
        # A changed alias can introduce another spelling without dropping old cached proof.
        titles=list(dict.fromkeys([t['title']]+[a['title'] for a in t.get('aliases',[]) if a.get('title')]))[:3]
        for brand in BRANDS:
            for n in numbers:
                if n['brand']==brand and brand!='joysound':jobs[(brand,'number',str(n['no']))]=None
            for title in titles[:2]:jobs[(brand,'title',title)]=None
    due=[]
    for job in jobs:
        key='|'.join(job);saved=cache.get(key,{})
        ttl=WEEK if saved.get('status')=='ok' and saved.get('count',0) else 86400 if saved.get('status')=='ok' else 6*3600
        if now-saved.get('checked_at',0)>=ttl:due.append(job)
    return due[:limit] if limit is not None else due

def store_result(db,job,rows,now=None):
    ensure(db);now=time.time() if now is None else now
    for r in rows:
        value={**r,'checked_at':now}
        db.execute('INSERT OR REPLACE INTO official_numbers VALUES (?,?,?)',(r['brand'],str(r['no']),json.dumps(value,ensure_ascii=False)))
        # Official observations are also useful candidates for reverse matching.
        db.execute('INSERT OR REPLACE INTO catalogue VALUES (?,?,?)',(r['brand'],str(r['no']),json.dumps(value,ensure_ascii=False)))
    result={'status':'ok','count':len(rows),'checked_at':now}
    db.execute('INSERT OR REPLACE INTO official_queries VALUES (?,?)',('|'.join(job),json.dumps(result)));return result

def status(db):
    ensure(db);job=core.get_state(db,'official_catalogue_job',{'status':'idle'})
    now=time.time();counts={}
    for row in db.execute('SELECT brand,data FROM official_numbers'):
        p=json.loads(row['data'])
        if 0<=now-p.get('checked_at',0)<WEEK and not p.get('future') and (not p.get('release') or p['release'][:10]<=datetime.now(timezone.utc).date().isoformat()):counts[row['brand']]=counts.get(row['brand'],0)+1
    return {'job':job,'verified_numbers':counts,'refresh_days':7,'enabled':core.get_state(db,'official_catalogue_enabled',False),'auto_refresh':core.get_state(db,'official_network_enabled',False)}

def run(db,write_lock,limit=None,delay=1.2):
    with write_lock:
        ensure(db);core.set_state(db,'official_catalogue_enabled',True);db.commit();jobs=plan(db,limit)
        state={'status':'running','total':len(jobs),'done':0,'errors':0,'found':0,'started_at':time.time(),'updated_at':time.time()};core.set_state(db,'official_catalogue_job',state);db.commit()
    changed=False
    for job in jobs:
        if STOP.is_set():state['status']='stopped';break
        started=time.monotonic()
        try:
            rows=providers.search(*job)
            with write_lock:store_result(db,job,rows);db.commit()
            state['found']+=len(rows);changed|=bool(rows)
        except Exception as error:
            reason='HTTP '+str(error.code) if isinstance(error,urllib.error.HTTPError) else str(error)[:150] if isinstance(error,ValueError) else type(error).__name__
            with write_lock:
                db.execute('INSERT OR REPLACE INTO official_queries VALUES (?,?)',('|'.join(job),json.dumps({'status':'error','checked_at':time.time(),'reason':reason})));db.commit()
            state['errors']+=1;state['last_error']=job[0]+' · '+reason
            # Back off instead of hammering a provider that is refusing requests.
            if isinstance(error,urllib.error.HTTPError) and error.code in (403,429):
                state['status']='waiting';state['retry_after']=time.time()+6*3600
        state['done']+=1;state['updated_at']=time.time();state['current_brand']=job[0]
        if state['done']%20==0 or state['status']=='waiting':
            with write_lock:core.set_state(db,'official_catalogue_job',state);db.commit()
        if state['done']%100==0 and changed:
            with write_lock:core.rebuild(db)
            changed=False
        if state['status']=='waiting':break
        STOP.wait(max(0,delay-(time.monotonic()-started)))
    else:state['status']='complete'
    state['updated_at']=time.time();state['finished_at']=time.time()
    with write_lock:
        if changed:core.rebuild(db)
        core.set_state(db,'official_catalogue_job',state);db.commit()
    return state

def start(write_lock,limit=None):
    if not LOCK.acquire(False):return False
    STOP.clear()
    def work():
        db=core.connect()
        try:
            with write_lock:core.set_state(db,'official_network_enabled',True);db.commit()
            run(db,write_lock,limit)
        except Exception as e:
            with write_lock:core.set_state(db,'official_catalogue_job',{'status':'error','reason':type(e).__name__,'finished_at':time.time()});db.commit()
        finally:db.close();LOCK.release()
    threading.Thread(target=work,daemon=True,name='official-catalogue').start();return True

def scheduler(write_lock,busy=lambda:False):
    def loop():
        # Catch up after startup in bounded chunks, then recheck expired entries.
        time.sleep(30)
        while True:
            if not busy() and not LOCK.locked():
                db=core.connect()
                try:
                    state=core.get_state(db,'official_catalogue_job',{})
                    enabled=core.get_state(db,'official_network_enabled',False)
                    retry=state.get('retry_after',0)
                    if enabled and state.get('status')!='stopped' and time.time()>=retry and plan(db,1):start(write_lock,100)
                finally:db.close()
            time.sleep(300)
    threading.Thread(target=loop,daemon=True,name='official-catalogue-scheduler').start()
