"""Offline Spotify export reader. Retains music fields only."""
import hashlib, json, re
from datetime import datetime, timezone
import core

def supported(rows):
    return isinstance(rows,list) and any(isinstance(r,dict) and ('ms_played' in r or 'msPlayed' in r) for r in rows)

def load(db,rows,filename):
    before=db.execute('SELECT count(*) FROM events').fetchone()[0]
    skipped=0
    for r in rows:
        if not isinstance(r,dict):skipped+=1;continue
        title=r.get('master_metadata_track_name',r.get('trackName'))
        artist=r.get('master_metadata_album_artist_name',r.get('artistName'))
        uri=r.get('spotify_track_uri') or ''
        try:
            ms=int(r.get('ms_played',r.get('msPlayed',0)))
            date=r.get('ts') or r.get('endTime')
            dt=datetime.fromisoformat(date.replace('Z','+00:00'))
            if dt.tzinfo is None:dt=dt.replace(tzinfo=timezone.utc)
            date=dt.astimezone(timezone.utc).isoformat()
        except (ValueError,TypeError,AttributeError):skipped+=1;continue
        if not isinstance(title,str) or not title.strip() or not isinstance(artist,str) or not artist.strip() or ms<=0:
            skipped+=1;continue
        # URI identifies a recording; legacy exports have names only.
        valid=re.fullmatch(r'spotify:track:([A-Za-z0-9]{22})',uri)
        identity=uri if valid else title.strip()+'|'+artist.strip()
        vid='spotify:'+hashlib.sha256(identity.encode()).hexdigest()[:24]
        url='https://open.spotify.com/track/'+valid[1] if valid else 'https://open.spotify.com/search/'+__import__('urllib.parse',fromlist=['quote']).quote(title+' '+artist)
        key=hashlib.sha256(('spotify|'+date+'|'+title.strip()+'|'+artist.strip()).encode()).hexdigest()
        db.execute('INSERT OR IGNORE INTO events VALUES (?,?,?,?,?)',(key,vid,date,url,title))
        core.save_video(db,{'video_id':vid,'source_platform':'spotify','title':title.strip(),'channel':artist.strip(),'category':'Music','metadata_status':'complete','source_url':url,'spotify_identity':{'title':title.strip(),'artist':artist.strip()},'description':''})
    after=db.execute('SELECT count(*) FROM events').fetchone()[0]
    result={'filename':__import__('pathlib').Path(filename).name,'source':'spotify','input_records':len(rows),'new_records':after-before,'duplicate_records':len(rows)-skipped-(after-before),'skipped_records':skipped,'total_records':after,'imported_at':datetime.now(timezone.utc).isoformat()}
    imports=core.get_state(db,'imports',[]);core.set_state(db,'imports',(imports+[result])[-20:]);db.commit()
    return result
