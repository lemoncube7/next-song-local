"""Reversible song aliases. Original video classifications remain untouched."""
import hashlib, re, uuid
from difflib import SequenceMatcher
import core

def presentation_title(title):
    # Only presentation labels; live/remix/instrumental/version text is retained.
    return re.sub(r'\s*[\[(](?:official\s+(?:music\s+)?video|music\s+video|official\s+audio|lyrics?\s+video)[\])]\s*$', '', title, flags=re.I).strip()

def identity(title, artist):
    return hashlib.sha256((core.norm(artist)+'|'+core.norm(title)).encode()).hexdigest()[:20]

def resolve(tid, title, artist, aliases):
    seen=set()
    while tid in aliases:
        if tid in seen:raise ValueError('곡 연결에 순환이 있습니다.')
        seen.add(tid);a=aliases[tid];title=a['title'];artist=a['artist'];tid=a['target']
    return tid,title,artist

def queue(db):
    mapping={m:t['id'] for t in core.tracks(db) for m in t.get('member_ids',[t['id']])}
    return list(dict.fromkeys(mapping.get(x,x) for x in core.get_state(db,'queue',[],'user_state')))

def merge(db, source, target):
    items={t['id']:t for t in core.tracks(db)}
    if source==target or source not in items or target not in items:raise ValueError('서로 다른 두 곡을 선택해 주세요.')
    a,b=items[source],items[target];aliases=core.get_state(db,'song_aliases',{},'user_state')
    change={'id':uuid.uuid4().hex,'source_title':a['title'],'target_title':b['title'],'previous':{},'members':a.get('member_ids',[source])}
    for member in change['members']:
        change['previous'][member]=aliases.get(member)
        aliases[member]={'target':target,'title':b['title'],'artist':b['artist'],'change':change['id']}
    history=core.get_state(db,'merge_history',[],'user_state');history.append(change)
    core.set_state(db,'song_aliases',aliases,'user_state');core.set_state(db,'merge_history',history,'user_state');db.commit();core.rebuild(db)
    return change

def undo(db, change_id):
    history=core.get_state(db,'merge_history',[],'user_state');change=next((h for h in history if h['id']==change_id),None)
    if not change or change.get('undone'):raise ValueError('되돌릴 연결을 찾지 못했습니다.')
    aliases=core.get_state(db,'song_aliases',{},'user_state')
    if any(aliases.get(m,{}).get('change')!=change_id for m in change['members']):raise ValueError('이후 연결을 먼저 되돌려 주세요.')
    for member,previous in change['previous'].items():
        if previous is None:aliases.pop(member,None)
        else:aliases[member]=previous
    change['undone']=True;core.set_state(db,'song_aliases',aliases,'user_state');core.set_state(db,'merge_history',history,'user_state');db.commit();core.rebuild(db)

def different(db, source, target, restore=False):
    key='|'.join(sorted([source,target]))
    saved=core.get_state(db,'different_songs',{},'user_state')
    if restore:
        saved.pop(key,None)
    else:
        items={t['id']:t for t in core.tracks(db)}
        if source==target or source not in items or target not in items:raise ValueError('서로 다른 두 곡을 선택해 주세요.')
        a,b=items[source],items[target]
        saved[key]={'source':source,'target':target,'source_title':a['title'],'target_title':b['title'],
                    'source_members':a.get('member_ids',[source]),'target_members':b.get('member_ids',[target])}
    core.set_state(db,'different_songs',saved,'user_state');db.commit()

def marked_different(a,b,rejections):
    am=set(a.get('member_ids',[a['id']]));bm=set(b.get('member_ids',[b['id']]))
    return any((am.intersection(r['source_members']) and bm.intersection(r['target_members'])) or
               (am.intersection(r['target_members']) and bm.intersection(r['source_members'])) for r in rejections)

def candidates(db):
    groups={};result=[];rejections=list(core.get_state(db,'different_songs',{},'user_state').values())
    for t in core.tracks(db):groups.setdefault(core.norm(core.canonical(t['artist'])),[]).append(t)
    for group in groups.values():
        for i,a in enumerate(group):
            for b in group[i+1:]:
                if marked_different(a,b,rejections):continue
                # Shared vocal credits must not make unrelated song titles look similar.
                def compare_title(value):
                    return re.split(r'\s*(?:\(?feat\.|featuring)',value,flags=re.I)[0].strip()
                at,bt=compare_title(a['title']),compare_title(b['title'])
                score=SequenceMatcher(None,core.norm(at),core.norm(bt)).ratio()
                def alias_parts(value):
                    if not re.search(r'[\u3040-\u30ff\u4e00-\u9fff]',value):return {core.norm(value)}
                    return {core.norm(p) for p in value.split(' - ') if p.strip() and not re.search(r'(?i)\blive\b|remix|edition|first take|re-recording',p)}
                parts_a=alias_parts(at);parts_b=alias_parts(bt)
                shared=parts_a.intersection(parts_b)
                same_alias=bool(shared and (len(parts_a)>1 or len(parts_b)>1))
                if same_alias:score=1
                # Distinct numbered entries / named chapters are separate songs.
                numbers_a=re.findall(r'\d+|(?<=[^A-Za-z])[IVX]+$',at)
                numbers_b=re.findall(r'\d+|(?<=[^A-Za-z])[IVX]+$',bt)
                ordinal=r'\b(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth)\b'
                if numbers_a!=numbers_b and numbers_a and numbers_b:continue
                if re.findall(ordinal,at,re.I)!=re.findall(ordinal,bt,re.I):continue
                if score>=.8:result.append({'source':a['id'],'target':b['id'],'similarity':round(score,3),'reason':'제목 안에 같은 별칭이 있어요' if same_alias else '제목 표기가 비슷해요'})
    return sorted(result,key=lambda x:-x['similarity'])[:100]
