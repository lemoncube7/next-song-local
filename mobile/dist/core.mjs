export const VERSION='1.0.0';
export const norm=s=>String(s??'').normalize('NFKC').toLocaleLowerCase().replace(/[^\p{L}\p{N}]/gu,'');
export const uid=()=>crypto.randomUUID().replaceAll('-','');
export function validateSnapshot(doc){
 if(!doc||doc.format!=='next-song-mobile'||doc.version!==1||!/^[a-f0-9]{32}$/.test(doc.source_id)||!Array.isArray(doc.tracks)||doc.tracks.length>25000)throw Error('PC에서 내보낸 모바일 데이터 파일이 아니에요. PC의 데이터 화면에서 내보내 주세요.');
 const ids=new Set();
 for(const t of doc.tracks){
  if(!t||typeof t.id!=='string'||t.id.length>100||ids.has(t.id)||!['title','artist'].every(k=>typeof t[k]==='string'&&t[k].length>0&&t[k].length<=300)||!Array.isArray(t.numbers)||!Array.isArray(t.aliases))throw Error('곡 데이터 형식이 올바르지 않아요.');
  for(const k of ['frequency_score','base_score','history_records','karaoke_rating'])if(t[k]!=null&&(!Number.isFinite(t[k])||Math.abs(t[k])>1e9))throw Error('잘못된 곡 점수예요.');
  ids.add(t.id);
 }
 if(!Array.isArray(doc.queue)||!Array.isArray(doc.friends)||!Number.isFinite(Date.parse(doc.created_at)))throw Error('모바일 데이터 구성이 올바르지 않아요.');
 return doc;
}
export function reconcile(snapshot,pending){const acknowledged=new Set(snapshot.acknowledged_operations||[]);return pending.filter(o=>!acknowledged.has(o.id));}
export function view(snapshot,operations,now=Date.now()){
 if(!snapshot)return {tracks:[],queue:[],friends:[],contacts:[]};
 const tracks=snapshot.tracks.map(t=>({...t,numbers:t.numbers||[],aliases:t.aliases||[],karaoke_rating:t.karaoke_rating||0}));
 const byId=new Map(tracks.map(t=>[t.id,t]));let queue=[...snapshot.queue];let contacts=[...(snapshot.friend_settings?.friends||[])];let blocked=[...(snapshot.friend_settings?.blocked||[])];
 for(const op of operations){const t=byId.get(op.target);
  if(op.kind==='rating'&&t)t.karaoke_rating+=op.value;
  if(op.kind==='queue'&&t)queue=op.value?[...new Set([...queue,t.id])]:queue.filter(id=>id!==t.id);
  if(op.kind==='follow')for(const item of tracks)if(norm(item.artist)===norm(op.target))item.followed=op.value;
  if(op.kind==='friend'){contacts=op.value?[...new Set([...contacts,op.target])]:contacts.filter(x=>x!==op.target);blocked=op.value?blocked.filter(x=>x!==op.target):[...new Set([...blocked,op.target])];}
 }
 for(const t of tracks){
  const age=Math.max(0,(now-Date.parse(t.last_watch))/86400000);
  const recency=Number.isFinite(age) ? .3/(1+Math.log1p(age/30)) : 0;
  const frequency=t.frequency_score??Math.max(0,(t.base_score||0)-recency);
  t.score=frequency+recency+(t.followed ? .2 : 0)+(t.karaoke_good ? .2 : 0)+.05*t.karaoke_rating;
 }
 tracks.sort((a,b)=>b.score-a.score||a.title.localeCompare(b.title));
 const peers=(snapshot.friends||[]).filter(f=>!blocked.includes(f.login)&&(contacts.includes(f.login)||f.state==='incoming'));
 for(const login of contacts)if(!peers.some(p=>p.login===login))peers.push({login,state:'pending',songs:[],share_songs:false});
 return {tracks,queue:queue.filter(id=>byId.has(id)),friends:peers,contacts};
}
function keys(t){return [t,...(t.aliases||[])].map(a=>norm(a.title)+'|'+norm(a.artist));}
export function common(local,remote){
 const labels=new Set(remote.flatMap(keys));const numbers=new Set(remote.flatMap(t=>(t.numbers||[]).map(n=>n.brand+':'+n.no)));
 return local.filter(t=>keys(t).some(k=>labels.has(k))||(t.numbers||[]).some(n=>numbers.has(n.brand+':'+n.no)));
}
export function matching(track,q){const key=norm(q);return keys(track).some(k=>norm(k).includes(key));}
export function changes(snapshot,device,operations){return {format:'next-song-mobile-changes',version:1,source_id:snapshot.source_id,device_id:device,operations};}
