export const VERSION='1.3.0';
export const norm=s=>String(s??'').normalize('NFKC').toLocaleLowerCase().replace(/[^\p{L}\p{N}]/gu,'');
export const uid=()=>crypto.randomUUID().replaceAll('-','');
export function validateSnapshot(doc){
 if(!doc||doc.format!=='next-song-mobile'||doc.version!==1||!/^[a-f0-9]{32}$/.test(doc.source_id)||!Array.isArray(doc.tracks)||doc.tracks.length>25000)throw Error('PC에서 내보낸 모바일 데이터 파일이 아니에요. PC의 데이터 화면에서 내보내 주세요.');
 if(doc.number_group_exclusions!=null&&(!Array.isArray(doc.number_group_exclusions)||doc.number_group_exclusions.length>10000||doc.number_group_exclusions.some(r=>!r||!['source_members','target_members'].every(k=>Array.isArray(r[k])&&r[k].every(id=>typeof id==='string'&&id.length<=100)))))throw Error('곡 묶음 제외 정보가 올바르지 않아요.');
 const ids=new Set();
 for(const t of doc.tracks){
  if(!t||typeof t.id!=='string'||t.id.length>100||ids.has(t.id)||!['title','artist'].every(k=>typeof t[k]==='string'&&t[k].length>0&&t[k].length<=300)||!Array.isArray(t.numbers)||!Array.isArray(t.aliases))throw Error('곡 데이터 형식이 올바르지 않아요.');
  for(const k of ['frequency_score','base_score','history_records','karaoke_rating'])if(t[k]!=null&&(!Number.isFinite(t[k])||Math.abs(t[k])>1e9))throw Error('잘못된 곡 점수예요.');
  for(const k of ['number_open_count','last_number_open'])if(t[k]!=null&&(!Number.isFinite(t[k])||t[k]<0||t[k]>1e12))throw Error('번호 확인 기록 형식이 올바르지 않아요.');
  ids.add(t.id);
 }
 if(!Array.isArray(doc.queue)||!Array.isArray(doc.friends)||!Number.isFinite(Date.parse(doc.created_at)))throw Error('모바일 데이터 구성이 올바르지 않아요.');
 return doc;
}
export function reconcile(snapshot,pending){const acknowledged=new Set(snapshot.acknowledged_operations||[]);return pending.filter(o=>!acknowledged.has(o.id));}
export const numberKey=n=>['tj','kumyoung','dam','joysound'].includes(n.brand)&&/^\d{1,8}(?:-\d{1,3})?$/.test(String(n.no))?n.brand+':'+(String(n.no).replaceAll('-','').replace(/^0+/,'')||'0'):null;
export function groupTracks(items,exclusions=[]){
 const groups=[],index=new Map();
 for(const [i,item] of items.entries()){
  let t={...item,id:item.id||'remote-'+i,member_ids:[...(item.member_ids||[item.id||'remote-'+i])],aliases:[...(item.aliases||[])],numbers:[...(item.numbers||[])]};
  const different=(a,b)=>exclusions.some(r=>((a.member_ids||[a.id]).some(m=>r.source_members?.includes(m))&&(b.member_ids||[b.id]).some(m=>r.target_members?.includes(m)))||((a.member_ids||[a.id]).some(m=>r.target_members?.includes(m))&&(b.member_ids||[b.id]).some(m=>r.source_members?.includes(m))));
  const options=[...new Set(t.numbers.flatMap(n=>index.get(numberKey(n))||[]))].filter(g=>!different(t,g));
  const absorbed=[];for(const old of options){if(different(t,old))continue;absorbed.push(old);
   const aliases=[{title:old.title,artist:old.artist},{title:t.title,artist:t.artist},...old.aliases,...t.aliases];
   t={...old,id:[old.id,t.id].sort()[0],member_ids:[...new Set([...old.member_ids,...t.member_ids])],aliases:[...new Map(aliases.map(a=>[a.title+'|'+a.artist,a])).values()],numbers:[...new Map([...t.numbers,...old.numbers].map(n=>[numberKey(n),n])).values()],history_records:(old.history_records||0)+(t.history_records||0),last_watch:[old.last_watch||'',t.last_watch||''].sort().at(-1),frequency_score:Math.max(old.frequency_score||0,t.frequency_score||0),base_score:Math.max(old.base_score||0,t.base_score||0),karaoke_rating:(old.karaoke_rating||0)+(t.karaoke_rating||0),number_open_count:(old.number_open_count||0)+(t.number_open_count||0),last_number_open:Math.max(old.last_number_open||0,t.last_number_open||0),followed:old.followed||t.followed,hidden:old.hidden||t.hidden,karaoke_good:old.karaoke_good||t.karaoke_good};
   groups.splice(groups.indexOf(old),1);
  }
  t.number_group_size=t.member_ids.length;groups.push(t);
  // Replace every index entry pointing to an absorbed group (including bridges).
  for(const [key,values] of index)if(values.some(g=>absorbed.includes(g)))index.set(key,[t]);
  for(const n of t.numbers)if(numberKey(n))index.set(numberKey(n),[...new Set([...(index.get(numberKey(n))||[]).filter(g=>groups.includes(g)),t])]);
 }
 return groups;
}
export const openBoost=count=>Math.min(.15,.035*Math.log1p(Math.max(0,count||0)));
export function mixRecommendations(items,seed){
 const noise=id=>{let h=(seed>>>0)||1;for(const c of id)h=Math.imul(h^c.charCodeAt(0),16777619)>>>0;const u=(h+.5)/4294967296;return Math.max(-.2,Math.min(.25,-.12*Math.log(-Math.log(u))));};
 return [...items].sort((a,b)=>(b.score+noise(b.id))-(a.score+noise(a.id))||a.id.localeCompare(b.id));
}
export function view(snapshot,operations,now=Date.now()){
 if(!snapshot)return {tracks:[],queue:[],friends:[],contacts:[]};
 const tracks=groupTracks(snapshot.tracks,snapshot.number_group_exclusions||[]).map(t=>({...t,numbers:(t.numbers||[]).map(n=>({...n,official_verified:!!n.official_verified&&Number.isFinite(n.checked_at)&&now-n.checked_at*1000>=0&&now-n.checked_at*1000<7*86400000})),aliases:t.aliases||[],karaoke_rating:t.karaoke_rating||0}));
 const byId=new Map(tracks.flatMap(t=>[t.id,...(t.member_ids||[])].map(id=>[id,t])));let queue=[...new Set(snapshot.queue.map(id=>byId.get(id)?.id).filter(Boolean))];let contacts=[...(snapshot.friend_settings?.friends||[])];let blocked=[...(snapshot.friend_settings?.blocked||[])];
 for(const op of operations){const t=byId.get(op.target);
  if(op.kind==='rating'&&t)t.karaoke_rating+=op.value;
  if(op.kind==='number_open'&&t&&op.value-(t.last_number_open||0)>=1800){t.number_open_count=(t.number_open_count||0)+1;t.last_number_open=op.value;}
  if(op.kind==='queue'&&t)queue=op.value?[...new Set([...queue,t.id])]:queue.filter(id=>id!==t.id);
  if(op.kind==='follow')for(const item of tracks)if(norm(item.artist)===norm(op.target))item.followed=op.value;
  if(op.kind==='friend'){contacts=op.value?[...new Set([...contacts,op.target])]:contacts.filter(x=>x!==op.target);blocked=op.value?blocked.filter(x=>x!==op.target):[...new Set([...blocked,op.target])];}
 }
 for(const t of tracks){
  const age=Math.max(0,(now-Date.parse(t.last_watch))/86400000);
  const recency=Number.isFinite(age) ? .3/(1+Math.log1p(age/30)) : 0;
  const frequency=t.frequency_score??Math.max(0,(t.base_score||0)-recency);
  t.score=frequency+recency+(t.followed ? .2 : 0)+(t.karaoke_good ? .2 : 0)+.05*t.karaoke_rating+openBoost(t.number_open_count);
 }
 tracks.sort((a,b)=>b.score-a.score||a.title.localeCompare(b.title));
 const peers=(snapshot.friends||[]).filter(f=>!blocked.includes(f.login)&&(contacts.includes(f.login)||f.state==='incoming')).map(f=>({...f,state:f.state==='incoming'&&contacts.includes(f.login)?'pending':f.state}));
 for(const login of contacts)if(!peers.some(p=>p.login===login))peers.push({login,state:'pending',songs:[],share_songs:false});
 return {tracks,queue:queue.filter(id=>byId.has(id)),friends:peers,contacts};
}
function keys(t){return [t,...(t.aliases||[])].map(a=>norm(a.title)+'|'+norm(a.artist));}
export function common(local,remote){
 const labels=new Set(remote.flatMap(keys));const numbers=new Set(remote.flatMap(t=>(t.numbers||[]).map(n=>numberKey(n))));
 return local.filter(t=>keys(t).some(k=>labels.has(k))||(t.numbers||[]).some(n=>numbers.has(numberKey(n))));
}
export function matching(track,q){const key=norm(q);return keys(track).some(k=>norm(k).includes(key));}
export function changes(snapshot,device,operations){return {format:'next-song-mobile-changes',version:1,source_id:snapshot.source_id,device_id:device,operations};}
