"""Relational, indexed browse data synchronized by SQLite triggers."""
import json

def ensure(db):
    if db.execute("SELECT 1 FROM sqlite_master WHERE name='video_browse'").fetchone():return
    values="""COALESCE(NULLIF(json_extract({}.data,'$.title'),''),json_extract({}.data,'$.history_title'),''),COALESCE(NULLIF(json_extract({}.data,'$.channel'),''),json_extract({}.data,'$.history_channel'),''),COALESCE(json_extract({}.data,'$.classification.status'),'unknown'),COALESCE(json_extract({}.data,'$.video_kind.kind'),'insufficient')"""
    initial=values.replace('{}.data','data');new=values.replace('{}.data','new.data')
    db.executescript(f"""
    BEGIN IMMEDIATE;
    CREATE TABLE IF NOT EXISTS video_browse(id TEXT PRIMARY KEY,title TEXT,channel TEXT,status TEXT,kind TEXT);
    CREATE TABLE IF NOT EXISTS video_activity(id TEXT PRIMARY KEY,records INTEGER,last_watch TEXT,last_sort REAL);
    CREATE INDEX IF NOT EXISTS browse_status ON video_browse(status,id);
    CREATE INDEX IF NOT EXISTS browse_kind ON video_browse(kind,status,id);
    CREATE INDEX IF NOT EXISTS activity_frequency ON video_activity(records DESC,last_sort DESC,id DESC);
    CREATE INDEX IF NOT EXISTS activity_recent ON video_activity(last_sort DESC,records DESC,id DESC);
    CREATE TRIGGER IF NOT EXISTS browse_insert AFTER INSERT ON videos BEGIN
      INSERT OR REPLACE INTO video_browse VALUES(new.id,{new}); END;
    CREATE TRIGGER IF NOT EXISTS browse_update AFTER UPDATE ON videos BEGIN
      INSERT OR REPLACE INTO video_browse VALUES(new.id,{new}); END;
    CREATE TRIGGER IF NOT EXISTS browse_delete AFTER DELETE ON videos BEGIN
      DELETE FROM video_browse WHERE id=old.id; END;
    CREATE TRIGGER IF NOT EXISTS activity_insert AFTER INSERT ON events WHEN new.video_id IS NOT NULL BEGIN
      INSERT INTO video_activity VALUES(new.video_id,1,new.time,julianday(new.time))
      ON CONFLICT(id) DO UPDATE SET records=records+1,last_watch=max(last_watch,excluded.last_watch),last_sort=max(last_sort,excluded.last_sort); END;
    CREATE TRIGGER IF NOT EXISTS activity_delete AFTER DELETE ON events WHEN old.video_id IS NOT NULL BEGIN
      DELETE FROM video_activity WHERE id=old.video_id;
      INSERT INTO video_activity SELECT video_id,count(*),max(time),max(julianday(time)) FROM events WHERE video_id=old.video_id GROUP BY video_id; END;
    CREATE TRIGGER IF NOT EXISTS activity_update AFTER UPDATE ON events BEGIN
      DELETE FROM video_activity WHERE id IN(old.video_id,new.video_id);
      INSERT INTO video_activity SELECT video_id,count(*),max(time),max(julianday(time)) FROM events WHERE video_id IS NOT NULL AND video_id IN(old.video_id,new.video_id) GROUP BY video_id; END;
    INSERT OR REPLACE INTO video_browse SELECT id,{initial} FROM videos;
    INSERT OR REPLACE INTO video_activity SELECT video_id,count(*),max(time),max(julianday(time)) FROM events WHERE video_id IS NOT NULL GROUP BY video_id;
    COMMIT;
    """)

def page(db,status='review',kind='all',search='',sort='frequency',offset=0,limit=30):
    where=["b.status<>'song'"];args=[]
    if status=='pending_scan':
        import whole_recognition
        where.append("b.id IN(SELECT t.id FROM whole_scan_tasks t WHERE t.version=? AND t.stage IN ('local','deep'))");args.append(whole_recognition.VERSION)
    elif status!='all':where.append('b.status=?');args.append(status)
    if status!='non_song' and kind=='all':where.append("b.status<>'non_song'")
    if kind!='all':where.append('b.kind=?');args.append(kind)
    if search:where.append("instr(lower(b.title||' '||b.channel),lower(?))>0");args.append(search)
    clause=' AND '.join(where);source=' FROM video_browse b JOIN video_activity a ON a.id=b.id '
    total=db.execute('SELECT count(*)'+source+'WHERE '+clause,args).fetchone()[0]
    order='a.records DESC,a.last_sort DESC,b.id DESC' if sort=='frequency' else 'a.last_sort DESC,a.records DESC,b.id DESC'
    rows=db.execute('SELECT v.data,a.records,a.last_watch'+source+'JOIN videos v ON v.id=b.id WHERE '+clause+' ORDER BY '+order+' LIMIT ? OFFSET ?',args+[limit,offset]).fetchall()
    items=[]
    for row in rows:
        v=json.loads(row['data']);v['history_records']=row['records'];v['last_watch']=row['last_watch'];items.append(v)
    return {'total':total,'items':items}
