"""Browse confirmed local and peer knowledge without adding watch events."""
import json
from collections import defaultdict
import core,shared_knowledge,song_labels

def page(db,query='',scope='all',offset=0,limit=40):
    if scope not in ('all','local','shared','watched','unwatched'):raise ValueError('잘못된 곡 목록 범위입니다.')
    groups={};labels=defaultdict(set)
    def key(title,artist):return core.norm(title),core.norm(core.number_artist(artist))
    def add(s,source,vids=(),track=None):
        keys={key(t,s['artist']) for t in song_labels.variants(s['title'])}
        possible=set().union(*(labels[k] for k in keys))
        primary=next(iter(possible)) if len(possible)==1 and not track else key(s['title'],s['artist'])
        g=groups.setdefault(primary,{'id':shared_knowledge.song_id(s['title'],s['artist']),'title':s['title'],'artist':s['artist'],'sources':set(),'video_ids':set(),'watched_video_ids':set(),'aliases':[],'numbers':[],'history_records':0,'local_track_id':''})
        g['sources'].add(source);g['video_ids'].update(vids)
        for a in [{'title':s['title'],'artist':s['artist']}]+s.get('aliases',[]):
            if a not in g['aliases']:g['aliases'].append(a)
            for t in song_labels.variants(a['title']):labels[key(t,a['artist'])].add(primary)
        for n in s.get('numbers',[]):
            if not any(x['brand']==n['brand'] and str(x['no'])==str(n['no']) for x in g['numbers']):g['numbers'].append({k:n[k] for k in ('brand','no')})
        if track:g['watched_video_ids'].update(track['video_ids']);g['local_track_id']=track['id']
        return g
    for t in core.tracks(db):add(t,'local' if any(s!='shared' for s in t['sources']) else 'shared',t['video_ids'],t)
    for row in db.execute("SELECT id,data FROM videos WHERE json_extract(data,'$.classification.status')='song' AND json_extract(data,'$.classification.source')<>'shared'"):
        v=json.loads(row['data']);add(v['classification'],'local',[row['id']])
    shared_knowledge.ensure(db)
    for row in db.execute('SELECT data FROM shared_knowledge'):
        doc=json.loads(row[0]);mapping=defaultdict(list)
        for m in doc['mappings']:mapping[m['song_id']].append(m['video_id'])
        for s in doc['songs']:add(s,'shared',mapping[s['id']]+s['original_video_ids'])
    for row in db.execute('SELECT data FROM shared_records'):
        s=json.loads(row[0]);add(s,'shared',[s['video_id']])
    activity={r[0]:r[1] for r in db.execute('SELECT id,records FROM video_activity')}
    items=list(groups.values())
    for s in items:s['history_records']=sum(activity.get(vid,0) for vid in s.pop('watched_video_ids'))
    summary={'all':len(items),'local':sum('local' in s['sources'] for s in items),'shared':sum('shared' in s['sources'] for s in items),'watched':sum(s['history_records']>0 for s in items)}
    summary['unwatched']=summary['all']-summary['watched']
    q=core.norm(query)
    items=[s for s in items if (scope=='all' or scope in s['sources'] or scope=='watched' and s['history_records']>0 or scope=='unwatched' and not s['history_records']) and (not q or any(q in core.norm(a['title']+' '+a['artist']) for a in s['aliases']))]
    items.sort(key=lambda s:(core.norm(s['artist']),core.norm(s['title']),s['id']))
    total=len(items)
    for s in items:s['sources']=sorted(s['sources']);s['video_ids']=sorted(s['video_ids'])
    return {'items':items[offset:offset+limit],'total':total,'summary':summary}
