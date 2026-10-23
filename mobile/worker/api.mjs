const API='/api/server',MAX_BYTES=1800000;
const json=(data,status=200)=>new Response(JSON.stringify(data),{status,headers:{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Vary':'Cookie, Authorization'}});
const fail=(message,status=400)=>{const e=Error(message);e.status=status;throw e;};
const hex=bytes=>Array.from(bytes,b=>b.toString(16).padStart(2,'0')).join('');
const random=n=>hex(crypto.getRandomValues(new Uint8Array(n)));
const hash=async text=>hex(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(text))));
const now=()=>Math.floor(Date.now()/1000);
const pair=(a,b)=>a<b?[a,b]:[b,a];
async function input(request){if(!request.headers.get('content-type')?.startsWith('application/json'))fail('JSON 형식으로 요청해 주세요.',415);const text=await request.text();if(new TextEncoder().encode(text).length>MAX_BYTES)fail('요청 데이터가 너무 커요.',413);try{return JSON.parse(text);}catch{fail('JSON 형식 오류');}}
const cleanText=(value,max=300)=>typeof value==='string'&&value.trim().length>0&&value.length<=max?value.trim():fail('문자열 형식을 확인하세요.');
async function limit(db,key,max=30,seconds=60){const t=now(),bucket=Math.floor(t/seconds),id=key+':'+bucket;const row=await db.prepare('INSERT INTO rate_limits(key,count,expires) VALUES (?,1,?) ON CONFLICT(key) DO UPDATE SET count=count+1 RETURNING count').bind(id,t+seconds*2).first();if(Math.random()<.01)await db.prepare('DELETE FROM rate_limits WHERE expires<?').bind(t).run();if(row.count>max)fail('요청이 많아요. 잠시 뒤 다시 시도하세요.',429);}
async function identity(request,db){const uid=request.headers.get('oai-authenticated-user-id'),email=request.headers.get('oai-authenticated-user-email');if(uid&&email)return {id:uid,browser:true};const token=request.headers.get('authorization')?.replace(/^Bearer /,'');if(token?.startsWith('nsd_')&&token.length===68){const device=await db.prepare('SELECT user_id FROM devices WHERE token_hash=? AND expires>?').bind(await hash(token),now()).first();if(device?.user_id)return {id:device.user_id,browser:false};}fail('로그인이 필요해요.',401);}
async function profile(db,id){return await db.prepare('SELECT id,handle,display,share,updated FROM profiles WHERE id=?').bind(id).first();}
function shelfInput(songs){if(!Array.isArray(songs)||songs.length>10000)fail('공유 곡은 10,000개까지 지원해요.');return songs.map(s=>{if(!s||Object.keys(s).some(k=>!['title','artist','aliases','numbers'].includes(k)))fail('곡명·가수·별칭·번호만 공유할 수 있어요.');const aliases=s.aliases||[],numbers=s.numbers||[];if(!Array.isArray(aliases)||aliases.length>50||!Array.isArray(numbers)||numbers.length>100)fail('별칭 또는 번호 형식 오류');return {title:cleanText(s.title),artist:cleanText(s.artist),aliases:aliases.map(a=>{if(Object.keys(a).some(k=>!['title','artist'].includes(k)))fail('별칭 형식 오류');return {title:cleanText(a.title),artist:cleanText(a.artist)};}),numbers:numbers.map(n=>{if(Object.keys(n).some(k=>!['brand','no'].includes(k))||!['tj','kumyoung','dam','joysound'].includes(n.brand)||typeof n.no!=='string'||!/^\d{1,8}(?:-\d{1,3})?$/.test(n.no))fail('노래방 번호 형식 오류');return {brand:n.brand,no:n.no};})};});}
async function saveShelf(db,user,songs,revision){if(!Number.isSafeInteger(revision)||revision<0)fail('목록 버전을 확인하세요.');const text=JSON.stringify(shelfInput(songs));if(new TextEncoder().encode(text).length>1500000)fail('공유 목록이 너무 커요.',413);const old=await db.prepare('SELECT revision FROM shelves WHERE user_id=?').bind(user).first();if((old?.revision||0)!==revision)fail('다른 기기에서 목록이 바뀌었어요. 다시 확인해 주세요.',409);const result=await db.prepare('INSERT INTO shelves(user_id,songs,revision,updated) VALUES (?,?,1,?) ON CONFLICT(user_id) DO UPDATE SET songs=excluded.songs,revision=shelves.revision+1,updated=excluded.updated WHERE shelves.revision=?').bind(user,text,now(),revision).run();if(!result.meta.changes)fail('목록이 바뀌었어요. 다시 확인해 주세요.',409);return {revision:revision+1,count:songs.length};}
function envelopeInput(e){if(!e||Object.keys(e).some(k=>!['format','version','kdf','iterations','salt','iv','ciphertext','compression'].includes(k))||e.format!=='next-song-personal-encrypted'||e.version!==1||e.kdf!=='PBKDF2-SHA256'||e.iterations!==310000||e.compression!=='gzip'||typeof e.salt!=='string'||typeof e.iv!=='string'||typeof e.ciphertext!=='string'||e.ciphertext.length>1700000||!/^[A-Za-z0-9+/]{22}==$/.test(e.salt)||!/^[A-Za-z0-9+/]{16}$/.test(e.iv)||!/^[A-Za-z0-9+/]+={0,2}$/.test(e.ciphertext))fail('암호화된 개인 데이터 형식이 아니에요.');return e;}

export async function handleAPI(request,env){
 const url=new URL(request.url),path=url.pathname.slice(API.length),method=request.method,db=env.DB;
 try{
  if(path==='/health'&&method==='GET')return json({ok:true,service:'next-song',version:'1.3.0',database:!!db});
  if(!db)fail('서버 DB가 아직 준비되지 않았어요.',503);
  if(!['GET','HEAD'].includes(method)){const origin=request.headers.get('origin');if((origin&&origin!==url.origin)||request.headers.get('sec-fetch-site')==='cross-site')fail('다른 사이트에서 요청할 수 없어요.',403);}
  if(path==='/devices/start'&&method==='POST'){
   await input(request);await limit(db,'pair-ip:'+await hash(request.headers.get('cf-connecting-ip')||'unknown'),10,600);const token='nsd_'+random(32),code=random(4).toUpperCase(),expires=now()+600;
   await db.prepare('DELETE FROM devices WHERE expires<?').bind(now()).run();await db.prepare('INSERT INTO devices(token_hash,code,user_id,expires,created,name) VALUES (?,?,NULL,?,?,?)').bind(await hash(token),code,expires,now(),'PC').run();return json({token,code,expires,verification_url:url.origin+'/?pair='+code},201);
  }
  if(path==='/devices/poll'&&method==='GET'){
   const token=request.headers.get('authorization')?.replace(/^Bearer /,'')||'';if(!/^nsd_[a-f0-9]{64}$/.test(token))fail('기기 연결 정보 오류',401);const d=await db.prepare('SELECT user_id,expires FROM devices WHERE token_hash=?').bind(await hash(token)).first();if(!d||d.expires<now())fail('기기 연결 시간이 만료됐어요.',410);return json({status:d.user_id?'approved':'pending',expires:d.expires});
  }
  const auth=await identity(request,db);await limit(db,'user:'+auth.id,240,60);
  if(path==='/me'&&method==='GET')return json({authenticated:true,user_id:auth.id,profile:await profile(db,auth.id),server_time:now()});
  if(path==='/profile'&&method==='POST'){
   const p=await input(request);if(!auth.browser)fail('표시 이름과 공유 설정은 로그인한 웹 앱에서 변경해 주세요.',403);const handle=cleanText(p.handle,24).toLowerCase();if(!/^[a-z0-9][a-z0-9_]{2,23}$/.test(handle)||typeof p.share_songs!=='boolean')fail('친구 ID는 영문·숫자·밑줄 3~24자예요.');const display=cleanText(p.display_name,80);const old=await profile(db,auth.id);if(old?.handle&&old.handle!==handle)fail('친구 ID 변경은 아직 지원하지 않아요.');
   try{await db.prepare('INSERT INTO profiles(id,handle,display,share,updated) VALUES (?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET display=excluded.display,share=excluded.share,updated=excluded.updated').bind(auth.id,handle,display,p.share_songs?1:0,now()).run();}catch(e){if(String(e).includes('UNIQUE'))fail('이미 사용 중인 친구 ID예요.',409);throw e;}return json({profile:await profile(db,auth.id)});
  }
  if(path==='/devices/approve'&&method==='POST'){
   if(!auth.browser)fail('로그인한 웹 앱에서 연결을 승인해 주세요.',403);const p=await input(request);if(!/^[A-Fa-f0-9]{8}$/.test(p.code||''))fail('PC에 표시된 8자리 코드를 입력하세요.');await limit(db,'pair-user:'+auth.id,10,600);const r=await db.prepare('UPDATE devices SET user_id=?,expires=? WHERE code=? AND user_id IS NULL AND expires>?').bind(auth.id,now()+90*86400,p.code.toUpperCase(),now()).run();if(!r.meta.changes)fail('코드가 없거나 만료·사용됐어요.',404);return json({approved:true});
  }
  if(path==='/devices/revoke'&&method==='POST'){
   const p=await input(request);if(!auth.browser)fail('웹 앱에서 기기 연결을 해제해 주세요.',403);await db.prepare('DELETE FROM devices WHERE token_hash=? AND user_id=?').bind(cleanText(p.id,64),auth.id).run();return json({ok:true});
  }
  if(path==='/devices'&&method==='GET')return json({devices:(await db.prepare('SELECT token_hash AS id,name,created,expires FROM devices WHERE user_id=? AND expires>?').bind(auth.id,now()).all()).results});
  if(path==='/shelf'&&method==='GET'){const r=await db.prepare('SELECT songs,revision,updated FROM shelves WHERE user_id=?').bind(auth.id).first();return json({songs:r?JSON.parse(r.songs):[],revision:r?.revision||0,updated:r?.updated||0});}
  if(path==='/shelf'&&method==='PUT'){const p=await input(request);if(!await profile(db,auth.id))fail('친구 ID를 먼저 정해 주세요.');return json(await saveShelf(db,auth.id,p.songs,p.revision));}
  if(path==='/friends'&&method==='GET'){
   const rows=(await db.prepare('SELECT f.user_low,f.user_high,f.requester,f.status,f.created,p.id,p.handle,p.display,p.share FROM friendships f JOIN profiles p ON p.id=CASE WHEN f.user_low=? THEN f.user_high ELSE f.user_low END WHERE f.user_low=? OR f.user_high=? ORDER BY f.created DESC LIMIT 100').bind(auth.id,auth.id,auth.id).all()).results;
   return json({friends:rows.map(p=>({id:p.id,login:p.handle,display_name:p.display,state:p.status==='accepted'?'accepted':p.requester===auth.id?'pending':'incoming',share_songs:!!p.share,created:p.created}))});
  }
  if(path==='/friends/request'&&method==='POST'){
   const p=await input(request);if(!await profile(db,auth.id))fail('친구 ID를 먼저 정해 주세요.');const target=await db.prepare('SELECT id FROM profiles WHERE handle=?').bind(cleanText(p.handle,24).toLowerCase()).first();if(!target)fail('해당 친구 ID가 없어요. 상대도 서버에 로그인해 ID를 만들어야 해요.',404);if(target.id===auth.id)fail('본인은 친구로 추가할 수 없어요.');const [lo,hi]=pair(auth.id,target.id);const old=await db.prepare('SELECT status FROM friendships WHERE user_low=? AND user_high=?').bind(lo,hi).first();if(old)fail('이미 친구이거나 요청이 있어요. 친구 목록을 확인하세요.',409);const count=await db.prepare('SELECT count(*) AS n FROM friendships WHERE user_low=? OR user_high=?').bind(auth.id,auth.id).first();if(count.n>=100)fail('친구와 요청은 합계 100개까지 지원해요.');await db.prepare('INSERT INTO friendships VALUES (?,?,?,?,?)').bind(lo,hi,auth.id,'pending',now()).run();return json({requested:true},201);
  }
  const friendMatch=path.match(/^\/friends\/([^/]+)(\/songs|\/accept)?$/);
  if(friendMatch){const peer=decodeURIComponent(friendMatch[1]),[lo,hi]=pair(auth.id,peer);const f=await db.prepare('SELECT requester,status FROM friendships WHERE user_low=? AND user_high=?').bind(lo,hi).first();if(!f)fail('친구 관계가 없어요.',404);
   if(friendMatch[2]==='/accept'&&method==='POST'){await input(request);if(f.requester===auth.id||f.status!=='pending')fail('받은 요청만 수락할 수 있어요.',403);await db.prepare('UPDATE friendships SET status=? WHERE user_low=? AND user_high=?').bind('accepted',lo,hi).run();return json({accepted:true});}
   if(!friendMatch[2]&&method==='DELETE'){await db.prepare('DELETE FROM friendships WHERE user_low=? AND user_high=?').bind(lo,hi).run();return json({removed:true});}
   if(friendMatch[2]==='/songs'&&method==='GET'){if(f.status!=='accepted')fail('친구 요청 수락이 필요해요.',403);const p=await profile(db,peer);if(!p?.share)return json({songs:[],shared:false});const r=await db.prepare('SELECT songs,updated FROM shelves WHERE user_id=?').bind(peer).first();return json({songs:r?JSON.parse(r.songs):[],shared:true,updated:r?.updated||0});}
  }
  const vault=path.match(/^\/vault\/([a-f0-9]{32})$/);
  if(vault){
   if(method==='GET'){const r=await db.prepare('SELECT envelope,revision,updated FROM vaults WHERE user_id=? AND vault=?').bind(auth.id,vault[1]).first();return json({envelope:r?JSON.parse(r.envelope):null,revision:r?.revision||0,updated:r?.updated||0});}
   if(method==='PUT'){const p=await input(request),e=envelopeInput(p.envelope);if(!Number.isSafeInteger(p.revision)||p.revision<0)fail('개인 동기화 버전 오류');const old=await db.prepare('SELECT revision FROM vaults WHERE user_id=? AND vault=?').bind(auth.id,vault[1]).first();if((old?.revision||0)!==p.revision)fail('개인 동기화 데이터가 바뀌었어요.',409);const r=await db.prepare('INSERT INTO vaults(user_id,vault,envelope,revision,updated) VALUES (?,?,?,1,?) ON CONFLICT(user_id,vault) DO UPDATE SET envelope=excluded.envelope,revision=vaults.revision+1,updated=excluded.updated WHERE vaults.revision=?').bind(auth.id,vault[1],JSON.stringify(e),now(),p.revision).run();if(!r.meta.changes)fail('개인 동기화 데이터가 바뀌었어요.',409);return json({revision:p.revision+1});}
  }
  fail('없는 API예요.',404);
 }catch(e){return json({error:e.status?e.message:'서버 처리 중 오류가 발생했어요.'},e.status||500);}
}
