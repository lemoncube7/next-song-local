import {open,seal} from './vault.mjs';import {validateSnapshot,reconcile} from './core.mjs';
export async function serverRequest(path,body=null,method=null){const r=await fetch('/api/server'+path,{method:method||(body?'POST':'GET'),credentials:'same-origin',cache:'no-store',headers:body?{'Content-Type':'application/json'}:{},...(body?{body:JSON.stringify(body)}:{})});let d;try{d=await r.json();}catch{throw Error('서버 응답을 읽지 못했어요. 앱을 새로고침해 주세요.');}if(!r.ok){const e=Error(d.error||'서버 연결 오류');e.status=r.status;throw e;}return d;}
export function serverShelf(tracks){return tracks.slice(0,10000).map(t=>({title:t.title,artist:t.artist,aliases:(t.aliases||[]).slice(0,50).map(a=>({title:a.title,artist:a.artist})),numbers:(t.numbers||[]).slice(0,100).map(n=>({brand:n.brand,no:String(n.no)}))}));}
export async function syncServerVault(vault,password,snapshot,operations){
 if(!/^[a-f0-9]{32}$/.test(vault))throw Error('PC의 개인 동기화 ID를 입력하세요.');
 for(let attempt=0;attempt<3;attempt++){
  const file=await serverRequest('/vault/'+vault);const remote=file.envelope?await open(file.envelope,password):null;
  const base=!snapshot?remote?.snapshot:remote&&Date.parse(remote.snapshot.created_at)>Date.parse(snapshot.created_at)?remote.snapshot:snapshot;
  if(!base)throw Error('PC에서 개인 데이터를 먼저 동기화하거나 모바일 파일을 가져오세요.');validateSnapshot(base);if(base.source_id!==vault)throw Error('다른 PC 데이터의 동기화 ID예요.');
  const pending=reconcile(base,[...new Map([...(remote?.operations||[]),...operations].map(o=>[o.id,o])).values()]);const merged={format:'next-song-personal',version:1,snapshot:base,operations:pending};
  if(remote&&JSON.stringify(remote)===JSON.stringify(merged))return {snapshot:base,operations:pending};
  try{await serverRequest('/vault/'+vault,{envelope:await seal(merged,password,file.envelope?.salt),revision:file.revision},'PUT');return {snapshot:base,operations:pending};}catch(e){if(e.status!==409||attempt===2)throw e;}
 }
}
