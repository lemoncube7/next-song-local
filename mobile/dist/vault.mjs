import {validateSnapshot,reconcile} from './core.mjs';
const enc=new TextEncoder(),dec=new TextDecoder(),AAD=enc.encode('next-song-personal-v1');
const b64=bytes=>{let result='';for(let i=0;i<bytes.length;i+=16384)result+=String.fromCharCode(...bytes.subarray(i,i+16384));return btoa(result);};
const un64=value=>Uint8Array.from(atob(value),c=>c.charCodeAt(0));
async function transform(bytes,compression){return new Uint8Array(await new Response(new Blob([bytes]).stream().pipeThrough(compression)).arrayBuffer());}
async function key(password,salt){const base=await crypto.subtle.importKey('raw',enc.encode(password),'PBKDF2',false,['deriveKey']);return crypto.subtle.deriveKey({name:'PBKDF2',hash:'SHA-256',salt,iterations:310000},base,{name:'AES-GCM',length:256},false,['encrypt','decrypt']);}
export async function seal(doc,password,salt=null){
 if(password.length<12)throw Error('동기화 암호는 12자 이상으로 설정해 주세요.');
 const saltBytes=salt?un64(salt):crypto.getRandomValues(new Uint8Array(16));const iv=crypto.getRandomValues(new Uint8Array(12));
 const plain=enc.encode(JSON.stringify(doc));const bytes=await transform(plain,new CompressionStream('gzip'));
 const ciphertext=new Uint8Array(await crypto.subtle.encrypt({name:'AES-GCM',iv,additionalData:AAD},await key(password,saltBytes),bytes));
 return {format:'next-song-personal-encrypted',version:1,kdf:'PBKDF2-SHA256',iterations:310000,salt:b64(saltBytes),iv:b64(iv),ciphertext:b64(ciphertext),compression:'gzip'};
}
export async function open(envelope,password){
 if(envelope?.format!=='next-song-personal-encrypted'||envelope.version!==1||envelope.iterations!==310000||envelope.kdf!=='PBKDF2-SHA256'||envelope.compression!=='gzip'||typeof envelope.ciphertext!=='string'||envelope.ciphertext.length>2000000)throw Error('지원하지 않는 개인 동기화 파일이에요.');
 const salt=un64(envelope.salt),iv=un64(envelope.iv);if(salt.length!==16||iv.length!==12)throw Error('암호화 정보가 올바르지 않아요.');
 let compressed;try{compressed=await crypto.subtle.decrypt({name:'AES-GCM',iv,additionalData:AAD},await key(password,salt),un64(envelope.ciphertext));}catch(e){throw Error('동기화 암호가 다르거나 파일이 손상됐어요. 덮어쓰지 않았어요.');}
 const plain=await transform(new Uint8Array(compressed),new DecompressionStream('gzip'));if(plain.length>25000000)throw Error('개인 데이터 파일이 너무 커요.');
 const doc=JSON.parse(dec.decode(plain));if(doc.format!=='next-song-personal'||doc.version!==1||!Array.isArray(doc.operations)||doc.operations.length>10000)throw Error('개인 동기화 내용 형식이 다릅니다.');
 validateSnapshot(doc.snapshot);return doc;
}
async function request(config,path,body){
 const response=await fetch('https://api.github.com'+path,{method:body?'PUT':'GET',headers:{Authorization:'Bearer '+config.token,Accept:'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28',...(body?{'Content-Type':'application/json'}:{})},...(body?{body:JSON.stringify(body)}:{})});
 if(response.status===404&&!body)return null;
 if(!response.ok){const error=Error(response.status===409?'동기화 내용이 바뀌어 다시 확인해요.':`GitHub ${response.status} — 저장소 접근 권한과 Contents 읽기·쓰기 권한을 확인해 주세요.`);error.status=response.status;throw error;}
 return response.json();
}
export async function syncVault(config,snapshot,operations){
 if(!/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(config.repo)||!/^[a-f0-9]{32}$/.test(config.vault))throw Error('저장소와 개인 동기화 ID를 확인하세요.');
 const meta=await request(config,'/repos/'+config.repo);if(!meta)throw Error('비공개 저장소에 접근할 수 없어요. 초대 수락과 토큰 설정을 확인하세요.');
 if(!meta.private)throw Error('개인 동기화는 비공개 저장소만 지원해요.');
 const path='/repos/'+config.repo+'/contents/personal/'+config.vault+'.json';
 for(let attempt=0;attempt<3;attempt++){
  const file=await request(config,path);let remote=null;let salt=null;
  if(file){if(file.size>1400000||!file.content)throw Error('개인 동기화 파일이 너무 커요. 파일 가져오기를 사용하세요.');const envelope=JSON.parse(dec.decode(un64(file.content.replace(/\s/g,''))));remote=await open(envelope,config.password);salt=envelope.salt;}
  const base=!snapshot?remote?.snapshot:remote&&Date.parse(remote.snapshot.created_at)>Date.parse(snapshot.created_at)?remote.snapshot:snapshot;
  if(!base)throw Error('PC에서 개인 동기화를 먼저 켜거나 모바일 데이터 파일을 가져와 주세요.');
  if(base.source_id!==config.vault)throw Error('다른 PC의 개인 동기화 ID예요.');
  const pending=reconcile(base,[...new Map([...(remote?.operations||[]),...operations].map(o=>[o.id,o])).values()]);
  const merged={format:'next-song-personal',version:1,snapshot:base,operations:pending};
  if(remote&&JSON.stringify(remote)===JSON.stringify(merged))return {snapshot:base,operations:pending};
  const encrypted=await seal(merged,config.password,salt);const content=b64(enc.encode(JSON.stringify(encrypted)));
  if(content.length>1200000)throw Error('암호화 파일이 너무 커요. 파일 교환으로 가져와 주세요.');
  try{await request(config,path,{message:'Sync encrypted personal song shelf',content,branch:meta.default_branch,...(file?{sha:file.sha}:{})});return {snapshot:base,operations:pending};}
  catch(error){if(error.status!==409||attempt===2)throw error;}
 }
}
