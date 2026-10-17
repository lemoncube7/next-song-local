'use strict';
const $=s=>document.querySelector(s);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const brandNames={tj:'TJ',kumyoung:'금영',dam:'DAM',joysound:'JOYSOUND'};
const searchKey=s=>String(s||'').normalize('NFKC').toLocaleLowerCase().replace(/[^\p{L}\p{N}]/gu,'');
const sourceNames={spotify:'Spotify 기록',library:'라이브러리',topic:'Topic 음원',auto_generated:'음원 설명',video_title:'제목에서 추정',manual:'직접 확인',auto_recognition:'자동 인식',shared:'공유된 확정 곡'};
const names={recommend:'오늘의 추천',songs:'기록 속 노래',knowledge:'분류된 곡',friends:'친구 · 함께 부를 곡',artists:'아티스트',queue:'부를 목록',review:'곡 확인하기',data:'데이터 가져오기',merge:'같은 곡 정리'};
let friendState=null,friendLogin='',friendMode='common',friendQuery='',friendOffset=0,friendRequest=0;
function friendsView(){return intro('SING TOGETHER','친구와 함께 부를 노래.','친구가 공유한 곡을 보고, 서로 알고 있는 노래를 찾아보세요.')+'<div id="friends-content">친구 정보를 불러오는 중…</div>';}
function friendNumbers(items){return (items||[]).map(n=>`${esc(brandNames[n.brand]||n.brand)} ${esc(n.no)}`).join(' · ')||'번호 미연결';}
async function loadFriends(){
 const request=++friendRequest;
 try{
  const r=await api('/api/friends');if(view!=='friends'||request!==friendRequest)return;friendState=r;
  const states={accepted:'친구',incoming:'받은 요청',pending:'상대 등록 대기'};
  $('#friends-content').innerHTML=`<div class="panel"><h3>내 친구 설정</h3><p class="note">연결 계정: ${esc(r.account||'다음 동기화에서 확인해요')} · ${esc(r.repo||'공유 저장소 미설정')}</p><form id="friends-settings"><label class="field">표시 이름<input id="friends-display" maxlength="80" value="${esc(r.settings.display_name)}" placeholder="친구에게 보여줄 이름"></label><label class="small"><input id="friends-share" type="checkbox" ${r.settings.share_songs?'checked':''}> 내 기록 속 곡 목록 공유</label><p class="small muted">곡명·아티스트·별칭·노래방 번호만 공유해요. 시청 기록 원본·시각·횟수·영상 ID는 보내지 않아요. 공유 목록은 비공개 저장소 참여자 모두가 읽을 수 있으며, 앱에서는 서로 친구 등록을 마친 뒤 보여줘요. 공유 해제는 다음 동기화에서 현재 목록을 비우지만 GitHub의 과거 커밋 이력에는 남을 수 있어요.</p><button class="button outline" type="submit">친구 설정 저장</button></form><form id="friend-add-form" class="dialog-actions"><label class="field">친구 GitHub 사용자명<input id="friend-add-login" maxlength="39" placeholder="예: JUNGCCI" required></label><button class="button primary" type="submit">친구 추가</button></form><p class="small muted">상대도 내 GitHub 사용자명을 추가하면 친구가 돼요. 두 사람 모두 같은 비공개 공유 저장소에 접근할 수 있어야 해요.</p><div class="dialog-actions"><button class="button outline" data-action="friends-sync">지금 동기화</button><button class="button outline" data-view="data">GitHub 연결·저장소 설정</button><button class="button subtle" data-action="friends-refresh">새로 확인</button></div><p id="friends-sync-status" class="note">${r.job.status==='error'?esc(r.job.reason):r.job.finished_at?'마지막 친구 동기화: '+new Date(r.job.finished_at*1000).toLocaleString('ko-KR'):'친구 설정을 저장하고 동기화해 주세요.'}</p></div><div class="panel"><h3>친구 ${r.friends.filter(f=>f.state==='accepted').length}명</h3>${r.friends.map(f=>`<div class="kv"><div><strong>${esc(f.display_name||f.login)}</strong><p class="small">@${esc(f.login)} · ${states[f.state]}${f.state==='accepted'?' · '+(f.share_songs?count(f.song_count)+'곡 공유':'곡 목록 비공개'):''}</p></div><div class="dialog-actions">${f.state==='incoming'?`<button class="button primary" data-action="friend-accept" data-login="${esc(f.login)}">수락</button>`:''}${f.state==='accepted'?`<button class="button outline" data-action="friend-open" data-login="${esc(f.login)}">곡·함께 부르기</button>`:''}<button class="button subtle" data-action="friend-remove" data-login="${esc(f.login)}">${f.state==='incoming'?'거절':'삭제'}</button></div></div>`).join('')||'<p class="muted">아직 등록한 친구가 없어요. GitHub 사용자명으로 추가해 보세요.</p>'}</div><div id="friend-shelf"></div>`;
  if(friendLogin&&r.friends.some(f=>f.login===friendLogin&&f.state==='accepted'))await loadFriendShelf();
 }catch(e){if(view==='friends'&&$('#friends-content'))$('#friends-content').textContent=e.message;}
}
async function loadFriendShelf(){
 const login=friendLogin;const request=++friendRequest;
 const r=await api(`/api/friend-songs?login=${encodeURIComponent(login)}&q=${encodeURIComponent(friendQuery)}&offset=${friendOffset}&limit=40`);
 if(view!=='friends'||login!==friendLogin||request!==friendRequest)return;
 const rows=friendMode==='common'?r.common.filter(s=>!friendQuery||(s.title+' '+s.artist).toLocaleLowerCase().includes(friendQuery.toLocaleLowerCase())):r.songs;
 $('#friend-shelf').innerHTML=`<div class="panel"><h3>@${esc(login)} · ${friendMode==='common'?'함께 부를 곡':'공유한 곡 목록'}</h3><div class="dialog-actions"><button class="button ${friendMode==='common'?'primary':'outline'}" data-action="friend-mode" data-mode="common">함께 부를 곡 ${count(r.common.length)}</button><button class="button ${friendMode==='songs'?'primary':'outline'}" data-action="friend-mode" data-mode="songs">친구의 곡 ${count(r.total)}</button></div><form id="friend-search-form" class="toolbar"><input id="friend-search" value="${esc(friendQuery)}" placeholder="곡명·가수 검색"><button class="button outline" type="submit">검색</button></form><p class="small muted">함께 부를 곡은 두 사람 목록의 곡명·아티스트·별칭 또는 노래방 번호를 대조한 후보예요. 친구 목록을 보는 것만으로 내 기록이나 추천에 추가하지 않아요.</p>${r.reason?`<p class="note">${esc(r.reason)}</p>`:''}${rows.map(s=>`<div class="kv"><div><strong>${esc(s.title)}</strong><p>${esc(s.artist)}</p><p class="small">${friendNumbers(friendMode==='common'?s.common_numbers:s.numbers)}</p>${s.basis?`<p class="small muted">${esc(s.basis)}${s.friend_title!==s.title?' · 친구 표기: '+esc(s.friend_title):''}</p>`:''}</div>${s.local_id?`<button class="button outline" data-action="queue" data-id="${esc(s.local_id)}">${S.queue.includes(s.local_id)?'부를 목록에서 빼기':'부를 목록에 담기'}</button>`:''}</div>`).join('')||'<p class="muted">표시할 곡이 없어요. 서로 곡 목록을 공유하고 동기화했는지 확인해 주세요.</p>'}${friendMode==='songs'?`<div class="pagination"><button class="button outline" data-action="friend-page" data-step="-1" ${friendOffset===0?'disabled':''}>← 이전</button><span>${friendOffset+1}–${Math.min(friendOffset+40,r.total)} / ${count(r.total)}</span><button class="button outline" data-action="friend-page" data-step="1" ${friendOffset+40>=r.total?'disabled':''}>다음 →</button></div>`:''}</div>`;
}
let knowledgeQuery='',knowledgeScope='all',knowledgeOffset=0,knowledgeRequest=0;
function knowledgeView(){return intro('SHARED SONG KNOWLEDGE','분류된 곡 · 함께 모은 노래 정보.','내 시청 기록과 관계없이, 이 PC에서 분류한 곡과 동기화로 받은 다른 사람의 곡 정보를 볼 수 있어요.')+`<div class="toolbar"><input class="search" id="knowledge-search" value="${esc(knowledgeQuery)}" placeholder="곡명·아티스트·다른 표기 검색"><select id="knowledge-scope">${[['all','전체 · 타인 포함'],['local','내 분류 포함'],['shared','공유 분류 포함'],['watched','내 시청 기록 있음'],['unwatched','내 시청 기록 없음']].map(([k,v])=>`<option value="${k}" ${knowledgeScope===k?'selected':''}>${v}</option>`).join('')}</select></div><div id="knowledge-results">곡 정보를 불러오는 중…</div>`;}
async function loadKnowledge(){const request=++knowledgeRequest;try{const r=await api(`/api/knowledge-songs?q=${encodeURIComponent(knowledgeQuery)}&scope=${knowledgeScope}&offset=${knowledgeOffset}&limit=40`);if(view!=='knowledge'||request!==knowledgeRequest)return;$('#knowledge-results').innerHTML=`<p class="note">전체 ${count(r.summary.all)}곡 · 내 분류 ${count(r.summary.local)} · 공유 분류 ${count(r.summary.shared)} · 내 기록 없음 ${count(r.summary.unwatched)}<br>내 분류와 공유 분류는 겹칠 수 있어요. 공유 곡을 보는 것만으로 추천이나 시청 기록에 추가되지는 않아요.</p><div class="song-list">${r.items.map(t=>`<div class="review-row"><div><strong>${esc(t.title)}</strong><p>${esc(t.artist)} · ${t.sources.map(s=>s==='local'?'내 분류':'공유 분류').join(' + ')} · ${t.history_records?`내 기록 ${count(t.history_records)}회`:'내 시청 기록 없음'}</p><p>${t.numbers.map(n=>`${brandNames[n.brand]||n.brand} ${esc(n.no)}`).join(' · ')||'노래방 번호 미연결'}</p><details><summary>표기·연결 영상 ${count(t.video_ids.length)}개 보기</summary><p>${t.aliases.slice(0,20).map(a=>esc(a.title)+' · '+esc(a.artist)).join('<br>')}</p>${t.video_ids.slice(0,50).map(vid=>`<a href="https://www.youtube.com/watch?v=${encodeURIComponent(vid)}" target="_blank" rel="noreferrer">영상 ${esc(vid)} ↗</a>`).join('<br>')}${t.video_ids.length>50?'<p>연결 영상은 앞의 50개를 표시해요.</p>':''}</details></div>${t.local_track_id?`<button class="button outline" data-action="detail" data-id="${t.local_track_id}">내 기록의 곡 보기</button>`:''}</div>`).join('')||empty('해당하는 곡이 없어요.')}</div><div class="pagination"><button class="button outline" data-action="knowledge-prev" ${knowledgeOffset===0?'disabled':''}>← 이전</button><span>${count(r.total)}곡 중 ${r.total?knowledgeOffset+1:0}–${Math.min(knowledgeOffset+40,r.total)}</span><button class="button outline" data-action="knowledge-next" ${knowledgeOffset+40>=r.total?'disabled':''}>다음 →</button></div>`;}catch(e){if(view==='knowledge')$('#knowledge-results').textContent=e.message;}}
let S={tracks:[],stats:{},queue:[],catalogue:[],token:'',has_api_key:false};
let view='recommend',brand='all',query='',sort='score',numberFilter='all',limit=40,reviewStatus='review',reviewOffset=0,reviewQuery='',reviewSort='frequency',reviewVersion=0;
let toastTimer,pollTimer,refreshing=false;
let recommendationLimit=14;
let bulkMinimum=5;
let reviewKind='all';
const kindLabels={song:'곡 중심',collection:'여러 곡·음악 방송',music_explain:'음악 설명·레슨',music_possible:'음악 관련·형식 미확인',activity:'다른 활동 중심',insufficient:'정보 부족'};
function autoIdentityPanel(){return `<div class="panel"><h3>연결 근거 자동 처리</h3><p class="small muted">앱 실행 중 3분마다 같은 원곡 링크·확정 곡·제목 별칭을 재사용해요. 원곡의 공개 정보는 중복 없이 묶어서 조회하고, 결과가 바뀌지 않은 영상은 다시 분석하지 않아요. 모델 API 비용은 없어요.</p><button class="button outline" data-action="auto-identity">지금 자동 처리</button><p id="auto-identity-status" class="note">상태 확인 중…</p></div>`;}
setInterval(async()=>{const p=$('#auto-identity-status');if(!p)return;try{const j=await api('/api/auto-identity-status'),labels={original_unidentified:'원곡 미식별',multiple_references:'복수 원곡',identity_ambiguous:'곡 정보 후보 충돌',no_identity_evidence:'곡 식별 근거 부족'};p.textContent=j.status==='running'?'자동 처리 중…':j.status==='error'?`자동 처리 오류: ${j.reason}`:`누적 추가 연결 ${count(j.total_saved)}영상 · 이번 확인 ${count(j.checked)} · 재분석 생략 ${count(j.cached)} · 원곡 조회 대기 ${count(j.reference_pending)} · ${Object.entries(j.reasons||{}).filter(([k])=>labels[k]).map(([k,n])=>`${labels[k]} ${count(n)}`).join(' / ')}`;}catch(e){p.textContent=e.message;}},3000);
function videoKindsPanel(){const j=S.video_kind_job||{};return `<div class="panel"><h3>영상 종류와 곡 식별은 별도로 봐요</h3><div class="type-summary">${Object.entries(kindLabels).map(([k,label])=>`<span>${label}<b>${count(j.counts?.[k])}</b></span>`).join('')}</div><p class="small muted">${count(j.done)} / ${count(j.total)}영상 분류 · 카테고리 단독 추정 ${count(j.confidence?.category)}개 · 제목 기반 추정 ${count(j.confidence?.inferred)}개는 확정 판정이 아니에요. 게임 영상의 명시된 곡 정보도 보존하며, 음악 방송은 설명의 곡 목록을 별도로 추출해요.</p><button class="button outline" data-action="job" data-kind="video_kind">전체 영상 종류 다시 분류</button></div>`;}
let bulkRecognition={running:false,stop:false,total:0,done:0,saved:0,candidates:0,errors:0,localOnly:false};
const date=s=>s?new Date(s).toLocaleDateString('ko-KR',{timeZone:'Asia/Seoul',year:'numeric',month:'2-digit',day:'2-digit'}):'—';
const count=n=>Number(n||0).toLocaleString('ko-KR');
function toast(text){$('#toast').textContent=text;$('#toast').classList.add('show');clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('#toast').classList.remove('show'),3600);}
async function api(path,body){
  const options=()=>body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json','X-App-Token':S.token},body:JSON.stringify(body)};
  let response=await fetch(path,options());
  if(response.status===403&&body!==undefined){
    const bootstrap=await fetch('/api/bootstrap');
    if(bootstrap.ok){
      const fresh=await bootstrap.json();
      if(fresh.token&&fresh.token!==S.token){S.token=fresh.token;response=await fetch(path,options());}
    }
  }
  const result=await response.json();if(!response.ok)throw new Error(result.error||'요청을 처리하지 못했습니다.');return result;
}
async function refresh(){
  S=await api('/api/bootstrap');render();
  if(S.stats.job.status==='running')startPoll();
}
function nav(v){
  if(view==='review'&&v!==view){
    for(const [id,result] of recognitionResults)if(result.status==='recognized')recognitionResults.delete(id);
  }
  view=v;query='';limit=40;recommendationLimit=14;reviewOffset=0;render();window.scrollTo({top:0,behavior:'smooth'});
}
function intro(eyebrow,title,description){return `<div class="intro"><div><span class="eyebrow">${eyebrow}</span><h1>${title}</h1><p class="muted">${description}</p></div><div class="period">현재 가져온 기록<strong>${date(S.stats.earliest)} — ${date(S.stats.latest)}</strong></div></div>`;}
function numbers(t){
  const list=t.numbers.filter(n=>brand==='all'||n.brand===brand);
  return list.length?list.map(n=>`<span class="number"><b>${brandNames[n.brand]||n.brand}</b>${esc(n.no)}</span>`).join(''):'<span class="number unchecked">번호 확인 필요</span>';
}
function addButton(t){const inQueue=S.queue.includes(t.id);return `<button class="add ${inQueue?'added':''}" data-action="queue" data-id="${t.id}" aria-label="${esc(t.title)} ${inQueue?'목록에서 빼기':'목록에 담기'}">${inQueue?'✓':'+'}</button>`;}
function filtered({numbered=false,queue=false}={}){
  let list=S.tracks.filter(t=>queue?S.queue.includes(t.id):(view!=='recommend'||!t.hidden));
  if(!queue){
    const availability=view==='songs'?numberFilter:'all';
    const hasNumber=t=>t.numbers.some(n=>brand==='all'||n.brand===brand);
    if(availability==='missing'&&!numbered)list=list.filter(t=>!hasNumber(t));
    else if(numbered||availability==='present'||brand!=='all')list=list.filter(hasNumber);
    if(query){const q=searchKey(query);list=list.filter(t=>[t,...(t.aliases||[])].some(a=>searchKey(a.title+' '+a.artist).includes(q)));}
    if(sort==='recent')list.sort((a,b)=>b.last_watch.localeCompare(a.last_watch));
    if(sort==='frequency')list.sort((a,b)=>b.history_records-a.history_records||b.score-a.score);
    if(sort==='least-frequency')list.sort((a,b)=>a.history_records-b.history_records||b.score-a.score);
    if(sort==='forgotten')list.sort((a,b)=>a.last_watch.localeCompare(b.last_watch));
  }else list.sort((a,b)=>S.queue.indexOf(a.id)-S.queue.indexOf(b.id));
  return list;
}
function rows(list,start=0){return `<div class="song-list">${list.length?list.map((t,i)=>`<div class="song-row${view==='recommend'?' recommendation-row':''}"><span class="rank">${String(i+start+1).padStart(2,'0')}</span><div><button class="song-name" data-action="detail" data-id="${t.id}">${esc(t.title)}</button><div class="song-artist">${esc(t.artist)} ${t.followed?'♡':''}</div><div class="song-meta"><span>기록 ${t.history_records}회</span><span class="source-tag">${t.sources.map(s=>sourceNames[s]||s).join(' · ')}</span></div></div><div class="number-badges">${numbers(t)}</div><div class="song-actions">${addButton(t)}${view==='recommend'?notForKaraokeButton(t):''}</div></div>`).join(''):empty('조건에 맞는 곡이 없어요.','다른 브랜드를 선택하거나 검색어를 바꿔보세요.')}</div>`;}
function empty(title,body=''){return `<div class="empty"><span class="empty-icon">♫</span>${title}<br><span class="small">${body}</span></div>`;}
function toolbar(){return `<div class="toolbar"><div class="chips" aria-label="노래방 브랜드">${[['all','전체'],['tj','TJ'],['kumyoung','금영'],['dam','DAM'],['joysound','JOYSOUND']].map(([k,v])=>`<button class="chip ${brand===k?'active':''}" data-brand="${k}">${v}</button>`).join('')}</div><input class="search" id="song-search" placeholder="곡명이나 아티스트 찾기" aria-label="곡 검색" value="${esc(query)}"><select id="sort-select" aria-label="정렬">${[['score','추천순'],['frequency','많이 들은 순'],['least-frequency','적게 들은 순'],['recent','최근 기록순'],['forgotten','오래전 기록순']].map(([k,v])=>`<option value="${k}" ${sort===k?'selected':''}>${v}</option>`).join('')}</select>${view==='songs'?`<select id="number-filter" aria-label="노래방 번호 연결 상태">${[['all','번호 상태 전체'],['present','번호 연결된 곡'],['missing','번호 미연결 곡']].map(([k,label])=>`<option value="${k}" ${numberFilter===k?'selected':''}>${label}</option>`).join('')}</select>`:''}</div>`;}
function notForKaraokeButton(t){return `<div class="karaoke-feedback"><button class="karaoke-good" data-action="karaoke-good" data-id="${t.id}" title="추천 점수 +5점">노래방에서 부르기 좋음 +</button><button class="karaoke-skip" data-action="karaoke-skip" data-id="${t.id}" title="추천 점수 −5점">노래방에서 부르기엔 그다지 −</button>${t.karaoke_rating?`<span class="small muted">평가 ${t.karaoke_rating>0?'+':''}${Math.round(t.karaoke_rating_score*100)}점</span>`:''}</div>`;}
function hero(t,i){return `<article class="song-hero"><div class="hero-top"><span class="hero-label">PICK ${String(i+1).padStart(2,'0')}</span><button class="compact-follow ${t.followed?'followed':''}" data-action="follow" data-followed="${t.followed}" data-artist="${esc(t.artist)}" aria-label="${esc(t.artist)} ${t.followed?'팔로우 해제':'팔로우'}">${t.followed?'♥':'♡'}</button></div><button class="song-name hero-title" data-action="detail" data-id="${t.id}">${esc(t.title)}</button><p class="hero-artist">${esc(t.artist)}</p><div class="hero-bottom"><div class="number-badges">${numbers(t)}</div>${addButton(t)}</div>${notForKaraokeButton(t)}</article>`;}
function recommend(){
  const list=filtered({numbered:true});
  return intro('FROM YOUR HISTORY','다음엔, 이 노래 어때요?','내가 들었던 노래에서 골랐어요.<br>익숙한 곡을 꺼내 오늘의 부를 목록에 담아보세요.')+
  `<div class="stats-strip"><div class="stat"><span>기록 속 노래</span><strong>${count(S.stats.tracks)}<small>곡</small></strong></div><div class="stat"><span>번호가 연결된 노래</span><strong>${count(S.stats.numbered_tracks)}<small>곡</small></strong></div><div class="stat"><span>팔로우 아티스트</span><strong>${count(S.stats.follows?.length)}<small>명</small></strong></div></div>`+
  `${S.stats.metadata_errors||S.stats.metadata_done<S.stats.videos||S.stats.unknown?`<div class="notice">${S.stats.metadata_done===S.stats.videos?`전체 영상 조회는 끝났어요. 공개 정보가 없는 ${count(S.stats.metadata_unavailable)}개는 미확인 상태로 남겼어요.`:`아직 정보를 조회하지 못한 영상이 있어요. 지금 추천은 확인된 곡을 기준으로 보여드려요.`} <button data-view="data" class="compact-follow">조회 상태 보기 ↗</button></div>`:''}`+
  toolbar()+`<div class="section-head"><div><h2>지금 꺼내 부르기 좋은 곡</h2><p>최근 기록 · 반복 기록 · 팔로우를 함께 반영했어요.</p></div><span class="small muted">${count(list.length)}곡</span></div>`+
  (list.length?`<div class="hero-grid">${list.slice(0,window.innerWidth>=1600?3:2).map(hero).join('')}</div>`:empty('연결된 곡 번호가 아직 없어요.','기록 속 노래에서 곡을 확인하거나 직접 번호를 연결할 수 있어요.'))+
  `<div class="section-head"><div><h2>이 곡들도 기억나나요?</h2><p>추천은 지금 가져온 기록 속 곡으로만 구성돼요.</p></div><div><button data-action="missing-numbers">번호 미연결 곡 보기 ↗</button> <button data-view="songs">모든 곡 보기 ↗</button></div></div>`+
  rows(list.slice(window.innerWidth>=1600?3:2,recommendationLimit),window.innerWidth>=1600?3:2)+
  (list.length>recommendationLimit?`<button class="button outline load-more" data-action="recommend-more">20곡 더 보기 ↓ · ${count(recommendationLimit)} / ${count(list.length)}곡</button>`:'')+
  `<p class="note">TJ·금영 번호는 비공식 곡 목록과 연결한 결과예요. 동명곡이나 커버 버전은 곡 상세에서 확인하세요.</p>`;
}
function songs(){const list=filtered();return intro('YOUR SONG ARCHIVE','들었던 노래, 한곳에.','라이브러리와 일반 유튜브 기록에서 곡 정보를 모았어요.')+toolbar()+`<div class="section-head"><h2>${count(list.length)}곡</h2><span class="small muted">제목을 누르면 추천 이유와 영상 정보를 볼 수 있어요.</span></div>`+rows(list.slice(0,limit))+(list.length>limit?`<button class="button outline load-more" data-action="more">40곡 더 보기 ↓</button>`:'');}
function artists(){
  const map=new Map();for(const t of S.tracks){if(t.hidden)continue;const a=map.get(t.artist)||{artist:t.artist,tracks:0,records:0,followed:t.followed};a.tracks++;a.records+=t.history_records;map.set(t.artist,a);}
  for(const a of S.stats.follows||[]){if(!map.has(a))map.set(a,{artist:a,tracks:0,records:0,followed:true});}
  const list=[...map.values()].filter(a=>!query||a.artist.toLocaleLowerCase().includes(query.toLocaleLowerCase())).sort((a,b)=>Number(b.followed)-Number(a.followed)||b.records-a.records);
  return intro('FOLLOW YOUR FAVORITES','좋아하는 목소리를 가까이.','팔로우한 아티스트의 기록 속 노래를 추천에서 먼저 보여드려요.')+
  `<div class="toolbar"><input class="search" id="song-search" placeholder="아티스트 검색" aria-label="아티스트 검색" value="${esc(query)}"></div><div class="artist-grid">${list.map(a=>`<article class="artist-card"><div class="artist-avatar">${esc([...a.artist][0])}</div><h3>${esc(a.artist)}</h3><p>기록 속 ${a.tracks}곡 · 활동 ${a.records}건</p><button class="button ${a.followed?'primary':'outline'}" data-action="follow" data-followed="${a.followed}" data-artist="${esc(a.artist)}">${a.followed?'♥ 팔로우 중':'♡ 팔로우'}</button><button class="compact-follow" data-action="artist-songs" data-artist="${esc(a.artist)}">노래 보기 ↗</button></article>`).join('')||empty('아티스트를 찾지 못했어요.')}</div>`;
}
function queueView(){const oldBrand=brand;brand='all';const list=filtered({queue:true});const html=intro('READY TO SING','오늘의 부를 목록.','추천에서 담아둔 노래를 여기서 확인하세요. 목록은 다시 열어도 남아 있어요.')+`<div class="section-head"><h2>${list.length}곡 담았어요</h2><a class="button outline" href="/api/export" download="karaoke-queue.csv">CSV 저장 ↓</a></div>`+(list.length?rows(list):empty('아직 담은 노래가 없어요.','추천곡 옆의 + 버튼으로 첫 곡을 담아보세요.'));brand=oldBrand;return html;}
function reviewView(){
  return intro('FIND YOUR SONGS','내 기록에서 노래를 모아요.','남은 영상 전체를 자동 처리하고, 근거가 맞는 곡을 저장해요.')+videoKindsPanel()+wholeRecognitionSummary()+
    `<div class="toolbar"><select id="review-status" aria-label="확인할 영상 분류">${[['pending_scan','전체 처리: 재탐색 대기'],['review','음악 관련 후보'],['unknown','정보 미확인'],['other','다른 분야의 영상'],['excluded','음악 아님 · 직접 지정'],['non_song','자동 판정: 곡 영상 아님'],['all','모든 영상']].map(([k,v])=>`<option value="${k}" ${reviewStatus===k?'selected':''}>${v}</option>`).join('')}</select><select id="review-kind" aria-label="영상 종류"><option value="all">모든 영상 종류</option>${Object.entries(kindLabels).map(([k,v])=>`<option value="${k}" ${reviewKind===k?'selected':''}>${v}</option>`).join('')}</select><select id="review-sort" aria-label="확인할 영상 정렬"><option value="frequency" ${reviewSort==='frequency'?'selected':''}>많이 들은 순</option><option value="recent" ${reviewSort==='recent'?'selected':''}>최신순</option></select><input class="search" id="review-search" placeholder="영상 제목이나 채널 검색" aria-label="영상 검색" value="${esc(reviewQuery)}"></div><details class="panel"><summary>시청 횟수와 범위를 골라 확인하기</summary>${bulkRecognitionPanel()}</details><div id="review-results" class="loading">영상을 불러오는 중…</div>`;
}
async function loadReview(){
  const version=++reviewVersion;
  try{
    const r=await api(`/api/videos?status=${encodeURIComponent(reviewStatus)}&kind=${encodeURIComponent(reviewKind)}&q=${encodeURIComponent(reviewQuery)}&sort=${encodeURIComponent(reviewSort)}&offset=${reviewOffset}&limit=30`);
    if(view!=='review'||version!==reviewVersion)return;
    $('#review-results').className='';$('#review-results').innerHTML=`<div class="song-list">${r.items.length?r.items.map(v=>`<div class="review-row"><div><strong>${esc(v.title||v.history_title)}</strong><p>${esc(v.channel||v.history_channel||'채널 정보 없음')} · ${esc(v.category||'카테고리 미확인')}</p><p>시청 기록 ${count(v.history_records)}회 · 마지막 기록 ${date(v.last_watch)}</p><p>${esc(v.classification.reason)}</p><p class="review-type">${esc(v.video_kind?.label)}${v.video_kind?.subtype?' · '+esc(v.video_kind.subtype):''} · ${v.video_kind?.confidence==='category'?'카테고리 기반 추정':esc(v.video_kind?.reason)}</p>${v.classification.status==='song'?`<p class="review-registration">✓ 등록된 곡 · ${esc(v.classification.title)} · ${esc(v.classification.artist)}</p>`:''}</div><div class="review-actions"><button class="button primary" data-action="recognize" data-video-id="${v.video_id}">알아서 확인해라</button><button class="button outline" data-action="review" data-video-id="${v.video_id}">직접 입력</button><button class="button outline" data-action="${v.classification.status==='excluded'?'manual-not-music-reset':'manual-not-music'}" data-video-id="${v.video_id}">${v.classification.status==='excluded'?'음악 아님 취소':'음악 아님'}</button></div></div>`).join(''):empty('해당하는 영상이 없어요.')}</div><div class="pagination"><button class="button outline" data-action="review-prev" ${reviewOffset===0?'disabled':''}>← 이전</button><span>${count(r.total)}개 중 ${r.total?reviewOffset+1:0}–${Math.min(reviewOffset+30,r.total)}</span><button class="button outline" data-action="review-next" ${reviewOffset+30>=r.total?'disabled':''}>다음 →</button></div>`;
    for(const button of document.querySelectorAll('#review-results [data-action="recognize"]')){
      const video=r.items.find(v=>v.video_id===button.dataset.videoId);
      const persisted=video?.recognition_result;
      const result=recognitionResults.get(button.dataset.videoId)||(persisted?.status!=='recognized'?persisted:null);if(!result)continue;
      recognitionResults.set(button.dataset.videoId,result);paintRecognitionButton(button,result);

    }
  }catch(e){if($('#review-results'))$('#review-results').textContent=e.message;}
}
function jobLabel(job){const stages={metadata:'공개 페이지 조회',official_metadata:'공식 API 영상 조회',catalogue_artists:'아티스트별 곡 목록 조회',catalogue_titles:'곡명별 번호 조회',catalogue_complete:'노래방 번호 연결 완료',complete:'처리 완료',non_song:'곡 아닌 영상 정리'};return stages[job.stage]||'대기 중';}
function dataView(){
  const s=S.stats,job=s.job||{},running=job.status==='running',percent=job.total?Math.min(100,100*(job.done||0)/job.total):0;
  const statsHTML=`<div class="kv"><span>가져온 활동</span><b>${count(s.records)}건</b></div><div class="kv"><span>고유 영상</span><b>${count(s.videos)}개</b></div><div class="kv"><span>게시글 등 영상 외 활동</span><b>${count(s.nonvideo_records)}건</b></div><div class="kv"><span>곡으로 연결한 영상</span><b>${count(s.song_videos)}개 / ${count(s.tracks)}곡</b></div><div class="kv"><span>음악 관련 확인 대기</span><b>${count(s.review)}개</b></div><div class="kv"><span>음악 여부 미확인</span><b>${count(s.unknown)}개</b></div><div class="kv"><span>확보한 노래방 목록</span><b>${count(s.catalogue_rows)}항목</b></div><div class="kv"><span>노래방 검색 보류</span><b>${count(s.catalogue_query_statuses?.deferred)}건</b></div>`;
  return intro('BRING YOUR HISTORY','내 기록으로 채우는 노래 서랍.','YouTube·YouTube Music Takeout 또는 Spotify 재생 기록 JSON을 가져오세요.')+
  `<div class="panel"><h3>시청·재생 기록 가져오기</h3><p class="small muted">Spotify는 확장 스트리밍 기록 또는 일반 StreamingHistory JSON 파일을 선택하세요. 여러 파일은 하나씩 가져오면 돼요. 계정 정보·IP는 저장하지 않으며, 음악이 아닌 항목과 재생 시간 0인 항목은 제외해요.</p><p class="small muted">추가 기록을 다시 가져와도 같은 영상·같은 시각의 활동은 중복되지 않아요. 팔로우와 직접 수정한 정보도 유지돼요.</p><div class="upload-zone"><span class="eyebrow">TAKEOUT → YOUR SONGS</span><p>Takeout ZIP / YouTube JSON·HTML / Spotify 기록 JSON · 최대 100MB</p><input type="file" id="import-file" accept=".zip,.json,.html" aria-label="Takeout 파일 선택" ${running?'disabled':''}><div><button class="button primary" id="upload-button" ${running?'disabled':''}>파일 가져오기</button></div></div><p id="import-feedback" class="small muted"></p></div>`+
  `<div class="data-grid"><div class="panel"><h3>현재 데이터</h3>${statsHTML}<p class="note">기간 ${date(s.earliest)} — ${date(s.latest)}<br>곡 추천의 최근성은 기록 마지막 시점을 기준으로 계산해요.</p></div><div class="panel"><h3>영상 정보와 곡 번호 조회</h3><p class="small muted">영상 정보는 유튜브 공개 메타데이터로 확인해요. 곡명·가수는 api.manana.kr에 보내 TJ·금영 번호를 검색해요.</p><div id="job-status"><div class="kv"><span>${jobLabel(job)}</span><b>${running?`${count(job.done)} / ${count(job.total)}`:job.status==='blocked'?'조회 보류':job.status==='error'?'조회 실패':job.status==='interrupted'?'중단됨':job.status==='complete'?'완료':'대기'}</b></div>${running?`<progress class="job-progress" max="100" value="${percent}" aria-label="조회 진행률"></progress>`:''}<p class="small muted">${esc(job.reason||'')}</p></div><p class="note">영상 조회 시도 ${count(s.metadata_done)} / ${count(s.videos)}개 · 오류 ${count(s.metadata_errors)}개<br>공식 API 처리 ${count(s.official_checked)}개 · 공개 정보 없음 ${count(s.metadata_unavailable)}개</p><div class="dialog-actions"><button class="button outline" data-action="job" data-kind="metadata" ${running?'disabled':''}>${S.has_api_key?'공식 API로 영상 조회':'공개 영상 정보 조회'}</button><button class="button primary" data-action="job" data-kind="catalogue" ${running?'disabled':''}>곡 번호 조회</button></div></div></div>`+
  `<div class="panel"><h3>YouTube Data API 키 ${S.has_api_key?'· 저장됨':'· 미설정'}</h3><p class="small muted">전체 영상 정보를 안정적으로 가져오려면 API 키를 넣어주세요. 이 키는 공개 영상 정보 조회에만 사용하며, 유튜브 계정 로그인이나 시청 기록 자동 동기화 기능은 아니에요.</p><form id="key-form" class="form-row"><label class="field">API 키<input id="api-key" type="password" autocomplete="off" placeholder="이 PC에 저장할 API 키" aria-label="YouTube API 키"></label><button class="button primary" type="submit">저장</button>${S.has_api_key?'<button class="button subtle" data-action="remove-key" type="button">삭제</button>':''}</form><p class="note">키는 앱의 data 폴더에 로컬 파일로 저장돼요. 공유할 때 해당 파일은 제외하세요. <a href="https://console.cloud.google.com/apis/library/youtube.googleapis.com" target="_blank" rel="noreferrer">YouTube Data API 사용 설정 ↗</a> · <a href="https://console.cloud.google.com/apis/credentials" target="_blank" rel="noreferrer">키 발급 ↗</a></p></div>`+
  `<div class="panel"><h3>가져오기 기록</h3>${(s.imports||[]).slice().reverse().map(i=>`<div class="kv"><span>${esc(i.filename)}<br><span class="small muted">${date(i.imported_at)}</span></span><b>새 활동 ${count(i.new_records)}건<br><span class="small muted">중복 ${count(i.duplicate_records)}건</span></b></div>`).join('')||'<p class="muted small">아직 가져온 기록이 없어요.</p>'}</div>`;
}
function sidebarQueue(){
  const map=new Map(S.tracks.map(t=>[t.id,t]));const items=S.queue.map(id=>map.get(id)).filter(Boolean);
  $('#nav-queue').textContent=items.length;$('#queue-count').textContent=items.length;$('#nav-songs').textContent=S.tracks.length;
  const oldBrand=brand;brand='all';$('#queue-mini').innerHTML=items.length?items.map(t=>`<div class="mini-song"><div class="mini-content"><b>${esc(t.title)}</b><small>${esc(t.artist)}</small><div class="number-badges">${numbers(t)}</div></div><button class="icon-button" data-action="queue" data-id="${t.id}" aria-label="${esc(t.title)} 목록에서 빼기">×</button></div>`).join(''):'<div class="mini-empty"><span>＋</span>어떤 노래로 시작할까요?<br>추천곡의 + 를 눌러 담아보세요.</div>';brand=oldBrand;
}
function decisionsPanel(){return `<div class="panel"><h3>확정된 곡으로 다른 영상 연결</h3><p class="small muted">저장된 제목 별칭과 아티스트가 함께 일치하는 미등록 영상을 찾아요. 외부 조회 없이 처리하며 직접 수정·제외한 영상은 유지해요.</p><button class="button outline" data-action="reuse-confirmed">확정된 곡으로 연결하기</button></div><div class="panel"><h3>정리 내용 백업·복원</h3><p class="small muted">곡 수정·별칭·같은 곡 연결·다른 곡 표시·팔로우·부를 목록·추천 평가·직접 연결한 번호를 백업해요. 시청 기록과 API 키는 포함하지 않아요. 복원은 현재 정리 내용을 백업의 내용으로 교체하므로 같은 시청 기록을 가져온 앱에서 사용하세요. 복원 직전 내용도 PC에 자동 백업해요.</p><button class="button outline" data-action="backup-export">정리 내용 백업 다운로드</button><p><input id="backup-file" type="file" accept=".json" aria-label="정리 내용 백업 파일"></p><button class="button outline" data-action="backup-restore">선택한 백업으로 복원</button><p id="decisions-feedback" class="small muted"></p></div>`;}
function sharingPanel(){
  const c=S.github_sync||{},j=S.github_sync_job||{};
  return `<div id="sharing-panel" class="panel"><h3>친구와 확정 곡 정보 공유</h3><p class="small muted">시청 기록 파일·시청 시각·횟수·영상 설명·API 키는 공유하지 않아요. 직접 확인하거나 근거로 확정된 곡명·가수·별칭·노래방 번호·음악 DB ID와 영상 ID·원곡 연결·버전·명시된 가창자를 비공개 GitHub 저장소에서 주고받아요. 공유된 영상 ID는 로컬 기록에 바로 연결하고, 직접 수정·제외한 결정과 서로 다른 분류는 유지해요.</p><button type="button" class="button outline" data-action="github-login">GitHub 계정 연결</button><p id="github-login-status" class="note"></p><form id="sharing-form"><label class="field">비공개 공유 저장소<input id="sharing-repo" value="${esc(c.repo||'')}" placeholder="owner/repo" required></label><label class="field">GitHub 토큰 (계정 연결을 사용하면 생략)<input id="sharing-token" type="password" autocomplete="off" placeholder="${c.has_token?'저장된 토큰 유지 — 변경할 때만 입력':'토큰을 입력하거나 GitHub CLI 로그인 사용'}"></label><label class="small muted"><input id="sharing-enabled" type="checkbox" ${c.enabled?'checked':''}> 분류 공유 켜기 · 저장 후 자동 동기화 · 실행 중 5분마다 확인</label><p><button class="button outline" type="submit">공유 설정 저장</button> <button class="button primary" type="button" data-action="github-sync">지금 받아오고 내 분류 올리기</button></p></form><p id="sharing-status" class="note">${sharingStatus(j)}</p><button class="button outline" data-action="shared-connections">내 기록에 적용된 공유 연결 보기</button> <button class="button outline" data-action="shared-conflicts">분류 충돌 보기</button><div id="shared-connections"></div><p class="small muted">각자 자신의 GitHub 계정으로 로그인하세요. 친구는 저장소 초대를 먼저 수락해야 해요. 토큰은 이 PC에만 저장하며, 이 저장소의 Contents 읽기·쓰기 권한이 필요해요.</p><a href="https://github.com/notifications" target="_blank" rel="noreferrer">분류 저장소 초대 확인 ↗</a> · <a href="https://github.com/settings/personal-access-tokens/new" target="_blank" rel="noreferrer">저장소 전용 토큰 만들기 ↗</a></div>`;
}
function updatePanel(){return `<div class="panel"><h3>앱 업데이트</h3><p class="small muted">새 버전을 설치하면 앱이 다시 실행돼요. 시청 기록과 설정은 유지해요.</p><button class="button outline" data-action="update-check">새 버전 확인</button> <button class="button primary" data-action="update-install">업데이트 설치</button><p id="update-status" class="note"></p></div>`;}
function mobilePanel(){return `<div class="panel"><h3>휴대폰에서 사용하기 · 독립 PWA</h3><p class="small muted">추천·곡 검색·노래방 번호·부를 목록·평가·친구 목록을 휴대폰에 담아요. 가져온 뒤에는 PC가 꺼져 있어도 사용할 수 있어요. 원본 시청 기록·영상 설명·API 키는 모바일 데이터에 포함하지 않아요. 개인 추천용 횟수·마지막 기록이 들어 있으므로 이 파일을 친구 공유 저장소에 올리지 마세요.</p><a class="button primary" href="https://next-song-mobile.lemoncube07.chatgpt.site" target="_blank" rel="noreferrer">모바일 앱 열기 ↗</a> <button class="button outline" data-action="mobile-export">모바일용 개인 데이터 내보내기</button><p class="small muted">파일을 휴대폰으로 옮긴 뒤 모바일 앱의 가져오기에서 선택하세요.</p><label class="field">휴대폰에서 바꾼 내용<input id="mobile-changes" type="file" accept=".json"></label><button class="button outline" data-action="mobile-apply">모바일 변경 파일 가져오기</button><p id="mobile-transfer-status" class="note"></p><details><summary>암호화된 개인 자동 동기화</summary><p class="small muted">기존 비공개 공유 저장소에는 암호화된 파일만 올려요. PC가 켜져 있을 때 1분마다 확인하고, 모바일에서도 앱을 열고 잠금을 풀면 변경을 주고받아요. 원본 Takeout 기록·YouTube/Gemini 키는 보내지 않아요. 암호를 잊으면 기존 동기화 파일을 열 수 없으니 모바일 데이터 파일도 따로 보관하세요.</p><form id="personal-sync-form"><label class="field">비공개 GitHub 저장소<input id="personal-repo" placeholder="owner/repo"></label><label class="field">개인 동기화 암호<input id="personal-password" type="password" autocomplete="new-password" minlength="12" maxlength="300" placeholder="12자 이상 · 휴대폰에서도 같은 암호 사용"></label><label><input id="personal-enabled" type="checkbox"> 개인 자동 동기화 켜기</label><p><button class="button outline" type="submit">개인 동기화 설정 저장</button> <button class="button outline" type="button" data-action="personal-sync">지금 동기화</button></p></form><p class="note">휴대폰에 입력할 개인 동기화 ID: <b id="personal-vault">설정을 저장하면 표시돼요.</b></p><p class="small muted">PC의 암호는 Windows 계정 보호 기능으로 암호화해 저장해요. 이 설정은 친구에게 곡 목록을 공유하는 설정과 별개예요.</p><p id="personal-status" class="note"></p></details></div>`;}
async function loadPersonalSettings(){try{const r=await api('/api/personal-sync');if(!$('#personal-enabled'))return;$('#personal-enabled').checked=Boolean(r.config.enabled);$('#personal-repo').value=r.config.repo||S.github_sync?.repo||'';$('#personal-vault').textContent=r.config.vault||'설정을 저장하면 표시돼요.';personalStatus(r);}catch(e){if($('#personal-status'))$('#personal-status').textContent=e.message;}}
function personalStatus(r){const p=$('#personal-status');if(p)p.textContent=r.job.status==='error'?r.job.reason:r.job.status==='running'?'개인 동기화 중…':r.job.finished_at?`마지막 동기화 ${new Date(r.job.finished_at*1000).toLocaleString('ko-KR')} · 적용 ${r.job.applied||0}건 · 확인 필요 ${r.job.pending||0}건`:r.config.enabled?'다음 동기화 대기':'개인 동기화 꺼짐';}
setInterval(async()=>{if(!$('#personal-status'))return;try{personalStatus(await api('/api/personal-sync'));}catch(e){}},5000);
async function installUpdate(){
  await api('/api/update-download',{});
  const tick=async()=>{
    let r;try{r=await api('/api/update-status');}catch(e){toast(e.message);return;}
    const p=$('#update-status');if(p)p.textContent=r.status==='error'?r.reason:r.status==='ready'?'다운로드 완료 · 재시작 준비 중…':r.status==='current'?`최신 버전 ${r.version}`:`업데이트 ${r.status==='downloading'?'다운로드 중':'확인 중'}…`;
    if(r.status==='ready'){
      try{await api('/api/update-apply',{});if(p)p.textContent='업데이트 설치 중… 앱이 다시 열려요.';let retries=0;const reconnect=setInterval(async()=>{try{await api('/api/update-status');clearInterval(reconnect);location.reload();}catch(e){if(++retries>100){clearInterval(reconnect);if(p)p.textContent='앱 폴더의 .updates/result.txt에서 업데이트 결과를 확인하세요.';}}},1500);}catch(e){if(p)p.textContent=e.message;toast(e.message);}return;
    }
    if(!['error','current'].includes(r.status))setTimeout(tick,1000);
  };tick();
}
function sharingStatus(j){const methods={video_id:'영상 ID',original_link:'원곡 링크',title_artist_alias:'제목·아티스트 별칭',external_id:'음악 DB ID'};return `${{running:'동기화 중',complete:'동기화 완료',error:'동기화 실패'}[j.status]||'대기'} · 올린 확정 정보 ${count(j.exported_records)}개 · 내 시청 영상 연결 ${count(j.applied_to_watched)}개 (추가 ${count(j.new_connections)} · 수정 ${count(j.updated_connections)} · 철회 ${count(j.withdrawn_connections)}) · ${Object.entries(j.connection_methods||{}).map(([k,n])=>`${methods[k]||k} ${count(n)}`).join(' / ')} · 분류 충돌 ${count(j.conflicts)}개${j.finished_at?' · 마지막 동기화 '+new Date(j.finished_at*1000).toLocaleString('ko-KR'):''}${j.reason?' · '+esc(j.reason):''}`;}
let sharingPoll;
let githubLoginPoll;
function startSharingPoll(){
  if(sharingPoll)return;
  sharingPoll=setInterval(async()=>{try{const r=await api('/api/github-sync-status');S.github_sync_job=r.job;const p=$('#sharing-status');if(p)p.innerHTML=sharingStatus(r.job);if(r.job.status!=='running'){clearInterval(sharingPoll);sharingPoll=null;S=await api('/api/bootstrap');sidebarQueue();toast(r.job.status==='complete'?'공유 곡 정보를 반영했어요.':r.job.reason||'동기화 상태를 확인하세요.');}}catch(e){clearInterval(sharingPoll);sharingPoll=null;toast(e.message);}},2000);
}
function reverseCataloguePanel(){
  const f=S.full_catalogue_job||{},r=S.reverse_catalogue_job||{};
  return `<div id="reverse-catalogue-panel" class="panel"><h3>노래방 수록곡으로 기록 역방향 탐색</h3><p class="small muted">확보한 TJ·금영·DAM·JOYSOUND 수록곡을 영상 제목·가수·원곡 크레딧과 로컬에서 대조해요. 제목만 우연히 겹치는 경우와 여러 곡 방송은 자동 저장하지 않아요.</p><p class="note">전체 목록: ${f.status==='complete'?'수집 완료':f.status==='running'?`수집 중 · ${count((f.next_page||1)-1)} / ${count(f.total_pages)}페이지`:'미수집'} · TJ ${count(f.brand_counts?.tj)} / 금영 ${count(f.brand_counts?.kumyoung)} / DAM ${count(f.brand_counts?.dam)} / JOYSOUND ${count(f.brand_counts?.joysound)}<br>역방향 탐색: ${r.status==='running'?'진행 중':r.status==='complete'?'완료':r.status==='error'?'오류':'대기'} · ${count(r.done)} / ${count(r.total)}영상 · 추가 저장 ${count(r.saved)} · 후보 ${count(r.candidates)}</p><button class="button outline" data-action="job" data-kind="full_catalogue">전체 노래방 목록 받기</button> <button class="button primary" data-action="reverse-catalogue" ${r.status==='running'?'disabled':''}>수록곡으로 전체 기록 탐색</button><p class="small muted">수집 자료는 Manana의 비공식 목록이며, 전체 제공 목록과 각 기기의 실제 수록곡은 다를 수 있어요.</p></div>`;
}
async function backupExport(){
  const response=await fetch('/api/user-backup',{headers:{'X-App-Token':S.token}});
  if(!response.ok)throw new Error('백업 다운로드 실패. 화면을 새로고침하고 다시 시도하세요.');
  const url=URL.createObjectURL(await response.blob()),link=document.createElement('a');link.href=url;link.download='karaoke-decisions-'+new Date().toISOString().slice(0,10)+'.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
function render(){
  const focused=document.activeElement?.id,start=document.activeElement?.selectionStart,end=document.activeElement?.selectionEnd;
  document.querySelectorAll('.nav').forEach(n=>n.classList.toggle('active',n.dataset.view===view));
  $('#breadcrumb').innerHTML=`내 노래 서랍 <span>/</span> ${names[view]}`;
  $('#main-content').innerHTML=({recommend,songs,knowledge:knowledgeView,friends:friendsView,artists,queue:queueView,review:()=>autoIdentityPanel()+reviewView(),data:()=>updatePanel()+mobilePanel()+autoIdentityPanel()+sharingPanel()+dataView()+reverseCataloguePanel()+decisionsPanel(),merge:mergeView}[view])();
  if(view==='data')loadPersonalSettings();
  if(view==='knowledge')loadKnowledge();
  if(view==='friends')loadFriends();
  sidebarQueue();if(view==='review'){loadReview();if(S.recognition_job?.status==='running')startWholePoll();}if(view==='merge')loadMerges();
  if(focused&&$('#'+focused)){const input=$('#'+focused);input.focus();if(typeof start==='number'&&input.setSelectionRange)input.setSelectionRange(start,end);}
}
const platformNames={spotify:'Spotify',youtube_music:'YouTube Music',youtube:'YouTube'};
function listeningInfo(t){
 const details=t.listening_details||{};
 const platforms=Object.entries(details).map(([platform,d])=>`${platformNames[platform]||platform} ${count(d.records)}회`).join(' · ');
 const sp=details.spotify;
 const time=sp&&sp.duration_known_records?`<p class="note">Spotify 실제 재생 시간 ${(sp.played_ms/60000).toFixed(1)}분 · 시간 정보 ${count(sp.duration_known_records)}회${sp.skip_known_records?` · 건너뛰기 ${count(sp.skipped_records)}회 / 여부 확인 ${count(sp.skip_known_records)}회`:''}</p>`:'';
 const recordings=(t.recordings||[]).map(r=>`<div class="kv"><span>${esc(r.title)}${r.album?`<br><span class="small muted">앨범 ${esc(r.album)}</span>`:''}</span>${r.track_uri?`<a class="small compact-follow" href="https://open.spotify.com/track/${encodeURIComponent(r.track_uri.split(':').pop())}" target="_blank" rel="noreferrer">Spotify 음원 ↗</a>`:''}</div>`).join('');
 return (platforms?`<p class="note">재생 출처: ${esc(platforms)}</p>`:'')+time+(recordings?`<details class="panel"><summary>Spotify 연결 음원 ${count(t.recordings.length)}개</summary><p class="small muted">곡 목록은 곡명·아티스트로 묶지만 서로 다른 음원 URI와 앨범은 별도로 보존해요.</p>${recordings}</details>`:'');
}
const linkedVideoTitles=new Map();
async function loadLinkedVideoTitles(trackId){
  const links=[...document.querySelectorAll('#detail-content [data-linked-video]')];
  for(let offset=0;offset<links.length;offset+=4){
    await Promise.allSettled(links.slice(offset,offset+4).map(async link=>{
      const vid=link.dataset.linkedVideo;
      let title=linkedVideoTitles.get(vid);
      try{
        if(!title){const video=await api('/api/video?id='+encodeURIComponent(vid));if(video.source_platform==='spotify'){link.href=video.source_url;link.dataset.action='';const button=link.parentElement.querySelector('button');if(button)button.remove();}title=video.title||video.history_title||`제목 정보 없음 · ${vid}`;const t=S.tracks.find(t=>t.id===trackId);const channel=searchKey((video.channel||video.history_channel||'').replace(/\s*-\s*Topic$|\s+official(?: channel)?$/i,''));const isCover=/cover|커버|歌ってみた/i.test(title);const isOriginal=!isCover&&t&&channel===searchKey(t.artist);title=(isCover?'[커버] ':isOriginal?'[원곡] ':'')+title+(video.history_records?` · 기록 ${video.history_records}회`:'');linkedVideoTitles.set(vid,title);}
      }catch(e){title=`영상 제목을 불러오지 못했어요 · ${vid}`;}
      if(link.isConnected&&$('#detail-content').dataset.trackId===trackId){link.textContent=title+' ↗';link.title=title;}
    }));
    if($('#detail-content').dataset.trackId!==trackId)break;
  }
}
async function detail(id){
  const t=S.tracks.find(x=>x.id===id);if(!t)return;
  const queued=S.queue.includes(id),oldBrand=brand;brand='all';
  $('#detail-content').innerHTML=`<div class="dialog-head"><div><span class="eyebrow">IN YOUR HISTORY</span><h2>${esc(t.title)}</h2></div><button class="icon-button" data-close="detail-dialog" aria-label="닫기">×</button></div><div class="detail-artist">${esc(t.artist)} <button class="compact-follow" data-action="follow" data-followed="${t.followed}" data-artist="${esc(t.artist)}">${t.followed?'♥ 팔로우 중':'♡ 팔로우'}</button></div><div class="number-badges">${numbers(t)}</div><p class="note">비공식 곡 목록의 제목·아티스트 일치 또는 직접 연결한 번호예요. 공식 수록 여부와 기기 지원은 별도로 확인하세요.</p><div class="detail-grid"><div class="detail-block"><span>시청 활동 기록</span><b>${t.history_records}회</b></div><div class="detail-block"><span>마지막 기록</span><b>${date(t.last_watch)}</b></div></div>${listeningInfo(t)}<h3>이 곡을 추천한 이유</h3><p class="small muted">반복 기록 ${Math.round(t.frequency_score*100)}점 + 최근성 ${Math.round(t.recency_score*100)}점${t.followed?' + 팔로우 20점':''}${t.karaoke_good?' + 부르기 좋음 20점':''}${t.karaoke_rating?` · 노래방 평가 ${t.karaoke_rating>0?'+':''}${Math.round(t.karaoke_rating_score*100)}점`:''}<br>최근성의 기준일은 ${date(t.reference_time)}예요. 시청 활동 기록은 실제 완곡 재생 횟수와 다를 수 있어요.</p>${notForKaraokeButton(t)}<button class="button outline" data-action="merge-open" data-id="${id}">같은 곡 연결</button>${(t.aliases||[]).length>1?`<p class="note">연결된 표기: ${t.aliases.map(a=>esc(a.title)+" · "+esc(a.artist)).join(" / ")}</p>`:""}<h3>연결한 영상·음원</h3>${t.video_ids.map((vid,i)=>`<div class="kv linked-video-row"><a data-linked-video="${vid}" href="https://www.youtube.com/watch?v=${vid}" target="_blank" rel="noreferrer">영상 제목 불러오는 중…</a><button class="compact-follow" data-action="review" data-video-id="${vid}">곡 정보 수정</button></div>`).join('')}<p class="note">곡 정보 출처: ${t.sources.map(x=>sourceNames[x]||x).join(' · ')}</p>${t.match_candidates.length?`<h3>확인이 필요한 번호 후보</h3>${t.match_candidates.slice(0,15).map(n=>`<div class="candidate"><div>${esc(n.title)} · ${esc(n.artist)}<p>${brandNames[n.brand]||n.brand} ${esc(n.no)} · ${esc(n.reason)}</p></div>${n.reason==='수록 예정'?'<span class="small muted">수록 예정</span>':`<button class="button outline" data-action="candidate" data-id="${t.id}" data-brand="${n.brand}" data-no="${esc(n.no)}">이 번호 연결</button>`}</div>`).join('')}`:''}<details class="panel"><summary>직접 곡 번호 연결</summary><p class="small muted">노래방 검색에서 확인한 번호를 입력하세요.</p><form class="number-form" id="number-form" data-id="${id}"><select id="number-brand" aria-label="번호 브랜드"><option value="tj">TJ</option><option value="kumyoung">금영</option><option value="dam">DAM</option><option value="joysound">JOYSOUND</option></select><input id="number-value" placeholder="곡 번호" inputmode="numeric" pattern="[0-9]{1,8}(-[0-9]{1,3})?" required aria-label="곡 번호"><button class="button outline">번호 저장</button></form>${t.numbers.filter(n=>n.source==='manual').map(n=>`<div class="kv"><span>직접 입력: ${brandNames[n.brand]||n.brand} ${esc(n.no)}</span><button class="compact-follow danger" data-action="remove-number" data-id="${id}" data-brand="${n.brand}" data-no="${esc(n.no)}">연결 해제</button></div>`).join('')}</details><div class="dialog-actions"><button class="button subtle" data-action="hide" data-id="${id}">${t.hidden?'추천에 다시 표시':'추천에서 숨기기'}</button><button class="button primary" data-action="queue" data-id="${id}">${queued?'목록에서 빼기':'부를 목록에 담기'}</button></div>`;
  $('#detail-content').dataset.trackId=id;brand=oldBrand;const d=$('#detail-dialog');if(!d.open)d.showModal();
  loadLinkedVideoTitles(id);
}

const recognitionResults=new Map();
const recognizing=new Set();
let recognitionSyncTimer;
function syncRecognitionState(){
  if(bulkRecognition.running)return;
  clearTimeout(recognitionSyncTimer);
  recognitionSyncTimer=setTimeout(async()=>{
    if(recognizing.size)return;
    try{S=await api('/api/bootstrap');$('#nav-songs').textContent=count(S.stats.tracks);}catch(e){toast(e.message);}
  },300);
}
function paintRecognitionButton(button,result){
  if(['collection','music_explain','activity_known','activity_provisional','info_missing'].includes(result.status)){
    button.className='button recognition-excluded';button.textContent=result.candidates?.length?'포함 곡 정보':{collection:'여러 곡 영상',music_explain:'음악 설명',activity_known:'활동 중심',activity_provisional:'활동 중심(추정)',info_missing:'정보 부족'}[result.status];button.title=result.reason||'';button.disabled=false;button.dataset.action='recognition-result';return;
  }
  if(result.status==='non_song'){
    button.className='button recognition-excluded';button.textContent='곡 영상 아님';button.title=result.reason||'';button.disabled=false;button.dataset.action='recognition-result';return;
  }
  button.classList.remove('primary','recognition-candidate','recognition-direct','recognition-web','recognition-saved');
  const saved=result.status==='recognized';
  const state=saved?'saved':result.candidates?.length?'candidate':result.google?'web':'direct';
  button.classList.add('recognition-'+state);
  button.textContent={saved:result.saved===false?'✓ 이미 등록된 곡':'✓ 저장됨',candidate:'후보 확인',web:'Google 결과 확인',direct:'직접 확인'}[state];
  button.disabled=saved;button.dataset.action=saved?'recognize':'recognition-result';
  button.title=saved?`${result.track.title} · ${result.track.artist}`:result.reason||'';
  if(saved)button.closest('.review-row')?.classList.add('recognition-saved');
}
async function saveReviewInformation(candidate=null){
  const vid=$('#review-video-id').value,title=$('#review-title').value,artist=$('#review-artist').value;
  $('#review-dialog').close();
  toast('곡 정보를 저장하는 중이에요.');
  try{await api('/api/correct',{video_id:vid,title,artist,alternate_labels:candidate?.alternate_labels||[]});}
  catch(e){toast(`${title} · ${artist} 저장에 실패했어요: ${e.message}`);return;}
  const result={status:'recognized',track:{title,artist},candidates:[]};recognitionResults.set(vid,result);
  for(const button of document.querySelectorAll('#review-results [data-video-id]')){
    if(button.dataset.videoId===vid&&['recognize','recognition-result'].includes(button.dataset.action))paintRecognitionButton(button,result);
  }
  if(view==='review'){
    api('/api/bootstrap').then(fresh=>{S=fresh;$('#nav-songs').textContent=count(S.stats.tracks);sidebarQueue();}).catch(e=>toast('저장은 완료됐지만 화면 정보 갱신에 실패했어요: '+e.message));
  }
  toast(`${title} · ${artist} 저장했어요.`);
}
async function showRecognitionResult(vid,result){
  result.candidates=(await api('/api/recognition-candidates',{candidates:result.candidates})).candidates;
  await review(vid);$('#recognition-result').textContent=result.reason+(result.local_decision?.status==='unavailable'||result.local_decision?.status==='busy'?' '+result.local_decision.reason:'');
  $('#recognition-candidates').innerHTML=result.candidates.map((c,i)=>`<div class="panel"><button type="button" class="button outline" data-action="recognition-candidate" data-index="${i}">${esc(c.title)} · ${esc(c.artist)} — 이 곡으로 저장</button><p class="small muted">${esc(c.provider||(c.music_card?'YouTube 음악 정보':'영상·로컬 곡 정보'))} · ${esc(c.reason||'곡명·아티스트 대조 필요')}</p>${c.alternate_labels?.length>1?`<p class="small muted">다른 표기: ${c.alternate_labels.map(a=>esc(a.title)+' · '+esc(a.artist)).join(' / ')}</p>`:''}${c.url?`<a href="${esc(c.url)}" target="_blank" rel="noreferrer">근거 확인 ↗</a>`:''}</div>`).join('');
  $('#recognition-candidates')._candidates=result.candidates;
  if(result.google){
    const g=result.google;
    $('#recognition-candidates').insertAdjacentHTML('beforeend',`<div class="panel"><h3>Google 전문 검색</h3><p class="small muted">${esc(g.query)}</p><a href="${esc(g.search_url)}" target="_blank" rel="noreferrer">Google 검색 결과 열기 ↗</a>${(g.results||[]).slice(0,10).map(r=>`<p><a href="${esc(r.url)}" target="_blank" rel="noreferrer">${esc(r.title)} ↗</a></p>`).join('')}</div>`);
  }
}
async function autoRecognize(vid,button,options={}){
  if(recognizing.has(vid))return;
  const fromList=Boolean(button.closest('.review-row'));
  recognizing.add(vid);button.disabled=true;const oldText=button.textContent;button.textContent='확인 중…';
  let completed=false;
  try{
    const result=await api('/api/recognize',{video_id:vid});
    if(result.status!=='recognized'&&options.web!==false){
      button.textContent='웹에서 찾는 중…';
      try{
        const web=await api('/api/google-song-search',{video_id:vid});
        result.google=web;
        const found=web.candidates.map(c=>({...c,reason:`${c.provider} 곡 정보 · 아티스트를 확인해 주세요.`}));
        result.candidates=(await api('/api/recognition-candidates',{candidates:[...result.candidates,...found].slice(0,100)})).candidates.slice(0,30);
        result.reason+=` ${web.provider}: ${web.reason}`;
      }catch(error){result.reason+=` 웹 검색: ${error.message}`;}
    }
    recognitionResults.set(vid,result);
    if(fromList)paintRecognitionButton(button,result);
    if(result.status==='recognized'){
      completed=true;
      if(fromList){button.textContent=result.saved===false?'✓ 이미 등록된 곡':'✓ 저장됨';button.title=`${result.track.title} · ${result.track.artist}`;button.closest('.review-row').classList.add('recognition-saved');}
      else{if($('#review-dialog').open && $('#review-video-id').value===vid)$('#review-dialog').close();button.disabled=false;button.textContent=oldText;}
      toast(`${result.track.title} · ${result.track.artist}${result.saved===false?' 이미 곡 목록에 등록되어 있어요.':' 저장했어요.'}`);
    }else if(fromList){
      completed=true;paintRecognitionButton(button,result);
    }else{await showRecognitionResult(vid,result);}
    return result;
  }catch(e){toast(e.message);return {status:'error',reason:e.message};}finally{
    recognizing.delete(vid);
    if(!completed){button.disabled=false;button.textContent=oldText;}
    syncRecognitionState();
  }
}

async function review(vid){
  $('#recognition-result').textContent='';$('#recognition-candidates').innerHTML='';
  const v=await api('/api/video?id='+encodeURIComponent(vid));$('#detail-dialog').close();
  $('#review-video-id').value=vid;$('#review-original').textContent=(v.title||v.history_title)+' · '+(v.channel||v.history_channel||'');
  $('#review-description').textContent=v.description||'공개 설명을 가져오지 못했어요. 알고 있는 곡 정보를 입력하거나 영상을 열어 확인해 주세요.';
  $('#review-title').value=v.classification.title||'';$('#review-artist').value=v.classification.artist||'';
  $('#review-heading').innerHTML=`이 영상은 어떤 곡인가요? <a class="small compact-follow" href="https://www.youtube.com/watch?v=${vid}" target="_blank" rel="noreferrer">영상 열기 ↗</a>`;
  if(!$('#review-dialog').open)$('#review-dialog').showModal();
}
async function upload(){
  const file=$('#import-file').files[0];if(!file){toast('Takeout ZIP이나 JSON·HTML 파일을 먼저 선택해 주세요.');return;}
  if(file.size>100*1024*1024){toast('100MB 이하 파일만 지원해요.');return;}
  const button=$('#upload-button');button.disabled=true;button.textContent='가져오는 중…';
  try{
    const response=await fetch('/api/import',{method:'POST',headers:{'Content-Type':'application/octet-stream','X-App-Token':S.token,'X-Filename':encodeURIComponent(file.name)},body:file});
    const r=await response.json();if(!response.ok)throw new Error(r.error);
    await refresh();$('#import-feedback').textContent=`새 활동 ${count(r.new_records)}건을 가져왔어요. 중복 ${count(r.duplicate_records)}건${r.skipped_records?`, 형식 미지원 ${r.skipped_records}건`:''}은 추가하지 않았어요.`;toast('가져오기가 끝났어요. 새 영상 정보와 곡 번호를 조회할 수 있어요.');
  }catch(e){toast(e.message);button.disabled=false;button.textContent='파일 가져오기';}
}
function startPoll(){
  if(pollTimer)return;
  pollTimer=setInterval(async()=>{
    if(refreshing)return;refreshing=true;
    try{const s=await api('/api/stats');S.stats=s;if(view==='data')render();if(s.job.status!=='running'){clearInterval(pollTimer);pollTimer=null;await refresh();toast(s.job.status==='complete'?'조회 결과를 반영했어요.':`조회가 멈췄어요: ${s.job.reason||s.job.status}`);}}
    catch(e){clearInterval(pollTimer);pollTimer=null;toast(e.message);}finally{refreshing=false;}
  },4000);
}
document.addEventListener('click',async event=>{
  const b=event.target.closest('button,a');if(!b)return;
  try{
    if(b.dataset.close){$('#'+b.dataset.close).close();return;}
    if(b.dataset.view){nav(b.dataset.view);return;}
    if(b.id==='import-shortcut'){nav('data');return;}
    if(b.id==='show-queue'){nav('queue');return;}
    if(b.id==='upload-button'){await upload();return;}
    if(b.dataset.brand&&!b.dataset.action){brand=b.dataset.brand;limit=40;render();return;}
    const action=b.dataset.action,id=b.dataset.id;
    if(action==='mobile-export'){const response=await fetch('/api/mobile-export',{headers:{'X-App-Token':S.token}});if(!response.ok)throw Error('모바일 데이터 내보내기에 실패했어요. 새로고침 후 다시 시도하세요.');const url=URL.createObjectURL(await response.blob());const link=document.createElement('a');link.href=url;link.download='NextSong-mobile-private.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),2000);toast('개인용 모바일 데이터를 내보냈어요. 친구에게 보내지 마세요.');return;}
    if(action==='mobile-apply'){const file=$('#mobile-changes').files[0];if(!file)throw Error('모바일 변경 파일을 선택하세요.');if(file.size>10000000)throw Error('10MB 이하 파일만 지원해요.');const result=await api('/api/mobile-apply',JSON.parse(await file.text()));await refresh();$('#mobile-transfer-status').textContent=`변경 ${result.applied}건 적용 · 이미 적용한 ${result.duplicates}건 생략 · 현재 PC에 없는 곡 ${result.unresolved.length}건. PC 데이터를 다시 내보내 모바일에 가져오면 확인 대기 표시도 정리돼요.`;return;}
    if(action==='personal-sync'){await api('/api/personal-sync-now',{});toast('개인 동기화를 시작해요. 상태를 확인해 주세요.');return;}
    if(action==='friends-refresh'){await loadFriends();return;}
    if(action==='friends-sync'){await api('/api/github-sync',{});toast('친구·분류 정보를 동기화해요. 완료 후 새로 확인을 눌러 주세요.');return;}
    if(action==='friend-open'){friendLogin=b.dataset.login;friendOffset=0;friendQuery='';await loadFriendShelf();return;}
    if(action==='friend-mode'){friendMode=b.dataset.mode;friendOffset=0;await loadFriendShelf();return;}
    if(action==='friend-page'){friendOffset=Math.max(0,friendOffset+40*Number(b.dataset.step));await loadFriendShelf();return;}
    if(action==='friend-accept'||action==='friend-remove'){
      const login=b.dataset.login,old=friendState.settings;
      const contacts=action==='friend-accept'?[...new Set([...old.friends,login])]:old.friends.filter(n=>n!==login);
      const blocked=action==='friend-remove'?[...new Set([...(old.blocked||[]),login])]:(old.blocked||[]).filter(n=>n!==login);
      await api('/api/friends',{friends:contacts,blocked});if(action==='friend-remove'&&friendLogin===login)friendLogin='';await loadFriends();toast('친구 설정을 저장했어요. 다음 동기화에 반영돼요.');return;
    }
    if(action==='knowledge-prev'||action==='knowledge-next'){knowledgeOffset=Math.max(0,knowledgeOffset+(action==='knowledge-next'?40:-40));loadKnowledge();return;}
    if(action==='shared-conflicts'){const r=await api('/api/github-sync-status');$('#shared-connections').innerHTML=r.conflicts.map(v=>`<div class="panel"><strong>분류 충돌 · ${esc(v.video_id)}</strong><p class="small muted">직접 정한 내용은 유지돼요. 아래 표기를 선택하면 직접 확인한 곡으로 저장해요.</p>${v.candidates.map(c=>`<p>${esc(c.title)} · ${esc(c.artist)} ${c.local?'(내 기존 분류)':''} <button class="button outline" data-action="shared-conflict-select" data-video-id="${v.video_id}" data-title="${esc(c.title)}" data-artist="${esc(c.artist)}">이 표기로 저장</button></p>`).join('')}</div>`).join('')||'분류 충돌이 없어요.';return;}
    if(action==='shared-conflict-select'){await api('/api/correct',{video_id:b.dataset.videoId,title:b.dataset.title,artist:b.dataset.artist});b.closest('.panel').remove();toast('직접 확인한 곡으로 저장했어요.');return;}
    if(action==='shared-connections'){const r=await api('/api/shared-connections');$('#shared-connections').innerHTML=r.items.map(v=>`<div class="kv"><span>${esc(v.title)} · ${esc(v.artist)}<br><small>${esc(v.shared_basis)} ${esc(v.shared_kind)} ${esc(v.shared_performer)}</small></span><button class="button outline" data-action="shared-reject" data-video-id="${v.video_id}">공유 연결 취소</button></div>`).join('')||'적용된 공유 연결이 없어요.';$('#shared-connections').innerHTML+=r.rejected.map(v=>`<div class="kv"><span>자동 연결 취소됨 · ${esc(v.title)}</span><button class="button outline" data-action="shared-reject" data-undo="true" data-video-id="${v.video_id}">공유 연결 다시 허용</button></div>`).join('');return;}
    if(action==='shared-reject'){await api('/api/shared-reject',{video_id:b.dataset.videoId,undo:b.dataset.undo==='true'});b.closest('.kv').remove();toast(b.dataset.undo==='true'?'공유 연결을 다시 허용했어요.':'공유 연결을 취소했어요. 이 영상은 자동으로 다시 연결하지 않아요.');return;}
    if(action==='auto-identity'){await api('/api/auto-identity',{});toast('연결 근거를 재사용해 자동 처리해요.');return;}
    if(action==='update-check'){b.disabled=true;try{const r=await api('/api/update-check',{});$('#update-status').textContent=`현재 ${r.version} · 최신 ${r.latest}${r.available?' · 업데이트 가능':' · 최신 버전이에요'}${r.install_supported?'':' · 소스 실행 환경에서는 파일 교체가 필요해요'}`;}finally{b.disabled=false;}return;}
    if(action==='update-install'){await installUpdate();return;}
    if(action==='github-login'){
      await api('/api/github-login',{});if(githubLoginPoll)clearInterval(githubLoginPoll);
      githubLoginPoll=setInterval(async()=>{const r=await api('/api/github-login-status'),p=$('#github-login-status');if(p)p.innerHTML=r.status==='error'?esc(r.reason||'GitHub 연결 오류'):r.code?`일회용 코드 <b>${esc(r.code)}</b>를 <a href="https://github.com/login/device" target="_blank" rel="noreferrer">GitHub 인증 페이지 ↗</a>에 입력하고 승인하세요.`:r.status==='complete'?'GitHub 계정 연결 완료':r.reason||'GitHub 인증 준비 중…';if(['complete','error'].includes(r.status)){clearInterval(githubLoginPoll);githubLoginPoll=null;}},1000);return;
    }
    if(action==='github-sync'){await api('/api/github-sync',{});$('#sharing-status').textContent='동기화 중…';startSharingPoll();return;}
    if(action==='reverse-catalogue'){b.disabled=true;try{await api('/api/reverse-catalogue',{});startReversePoll();toast('수록곡으로 전체 기록을 탐색하기 시작했어요.');}catch(e){b.disabled=false;throw e;}return;}
    if(action==='manual-not-music'||action==='manual-not-music-reset'){
      b.disabled=true;try{await api('/api/correct',{video_id:b.dataset.videoId,exclude:action==='manual-not-music',reset:action==='manual-not-music-reset'});recognitionResults.delete(b.dataset.videoId);b.closest('.review-row')?.remove();toast(action==='manual-not-music'?'음악 아님으로 지정했어요. 자동 탐색에서 제외해요.':'음악 아님 지정을 취소했어요.');}catch(e){b.disabled=false;throw e;}return;
    }
    if(action==='missing-numbers'){view='songs';numberFilter='missing';brand='all';query='';limit=40;render();return;}
    if(action==='scan-pending'){view='review';reviewStatus='pending_scan';reviewKind='all';reviewOffset=0;reviewQuery='';render();return;}
    if(action==='whole-start'){
      b.disabled=true;try{await api('/api/recognize-all',{});S.recognition_job={...S.recognition_job,status:'running',stage:'local'};updateWholePanel();startWholePoll();toast('남은 영상 전체 자동 처리를 시작했어요. 다른 화면으로 이동해도 계속 진행해요.');}catch(e){b.disabled=false;throw e;}return;
    }
    if(action==='whole-stop'){b.disabled=true;await api('/api/recognize-all-stop',{});toast('현재 영상 처리 후 중지해요. 저장된 위치에서 이어갈 수 있어요.');return;}
    if(action==='backup-export'){await backupExport();return;}
    if(action==='backup-restore'){
      const file=$('#backup-file').files[0];if(!file){toast('정리 내용 백업 JSON을 선택해 주세요.');return;}
      if(file.size>100*1024*1024)throw new Error('100MB 이하 백업을 선택하세요.');
      b.disabled=true;try{const response=await fetch('/api/user-backup-restore',{method:'POST',headers:{'X-App-Token':S.token,'Content-Type':'application/json'},body:file});const r=await response.json();if(!response.ok)throw new Error(r.error);await refresh();$('#decisions-feedback').textContent=`복원 완료 · 이전 내용은 data/backups/${r.previous_backup}에 보관했어요.`;}finally{b.disabled=false;}return;
    }
    if(action==='reuse-confirmed'){b.disabled=true;b.textContent='연결할 영상 찾는 중…';try{const r=await api('/api/reuse-confirmed',{});await refresh();$('#decisions-feedback').textContent=`기존 확정 곡에 영상 ${r.saved}개를 추가로 연결했어요.`;}finally{b.disabled=false;b.textContent='확정된 곡으로 연결하기';}return;}
    if(b.id==='bulk-recognize-start'){await startBulkRecognition();return;}
    if(b.id==='bulk-recognize-stop'){bulkRecognition.stop=true;updateBulkRecognition();return;}
    if(action==='different-song'||action==='different-undo'){
      b.disabled=true;await api('/api/different-songs',{source:id,target:b.dataset.target,restore:action==='different-undo'});
      await loadMerges();toast(action==='different-song'?'다른 곡으로 표시했어요. 이 조합은 후보에서 제외해요.':'다른 곡 표시를 되돌렸어요.');return;
    }
    if(action==='karaoke-good'||action==='karaoke-skip'){
      b.disabled=true;const delta=action==='karaoke-good'?1:-1;
      await api('/api/karaoke-rating',{id,delta});await refresh();
      if($('#detail-dialog').open)detail(id);toast(delta>0?'추천 점수를 5점 올렸어요.':'추천 점수를 5점 낮췄어요.');return;
    }
    if(action==='merge-now'){
      if(b.disabled)return;
      b.disabled=true;b.textContent='합치는 중…';
      await api('/api/merge',{source:id,target:b.dataset.target});
      await refresh();toast('곡을 합쳤어요. 연결 기록에서 되돌릴 수 있어요.');return;
    }
    if(action==='merge-open'){openMerge(id);if(b.dataset.target)$('#merge-target').value=b.dataset.target;return;}
    if(action==='merge-save'){await api('/api/merge',{source:$('#merge-source').value,target:$('#merge-target').value});$('#merge-dialog').close();await refresh();toast('곡을 연결했어요. 같은 곡 정리에서 되돌릴 수 있어요.');return;}
    if(action==='merge-undo'){await api('/api/unmerge',{id});await refresh();toast('곡 연결을 되돌렸어요.');return;}
    if(b.id==='review-web-search'){await webSongSearch(b);return;}
    if(action==='detail'){await detail(id);return;}
    if(action==='recognition-result'){await showRecognitionResult(b.dataset.videoId,recognitionResults.get(b.dataset.videoId));return;}
    if(action==='recognition-candidate'){const c=$('#recognition-candidates')._candidates[Number(b.dataset.index)];b.disabled=true;$('#review-title').value=c.title;$('#review-artist').value=c.artist;try{await saveReviewInformation(c);}finally{b.disabled=false;}return;}
    if(b.id==='review-recognize'){await autoRecognize($('#review-video-id').value,b);return;}
    if(action==='recognize'){await autoRecognize(b.dataset.videoId,b);return;}
    if(action==='review'){await review(b.dataset.videoId);return;}
    if(action==='queue'){const enabled=!S.queue.includes(id);const r=await api('/api/queue',{id,enabled});S.queue=r.queue;render();if($('#detail-dialog').open)detail(id);toast(enabled?'부를 목록에 담았어요.':'목록에서 뺐어요.');return;}
    if(action==='follow'){b.disabled=true;const artist=b.dataset.artist,follow=b.dataset.followed!=='true',detailId=$('#detail-content').dataset.trackId;await api('/api/follow',{artist,follow});await refresh();if($('#detail-dialog').open&&detailId)detail(detailId);toast(follow?'팔로우했어요. 이 아티스트의 곡을 먼저 추천해요.':'팔로우를 해제했어요.');return;}
    if(action==='artist-songs'){view='songs';query=b.dataset.artist;brand='all';numberFilter='all';limit=40;render();return;}
    if(action==='hide'){const t=S.tracks.find(x=>x.id===id);await api('/api/hide',{id,enabled:!t.hidden});await refresh();detail(id);return;}
    if(action==='recommend-more'){recommendationLimit+=20;render();return;}
    if(action==='more'){limit+=40;render();return;}
    if(action==='review-prev'){reviewOffset=Math.max(0,reviewOffset-30);loadReview();return;}
    if(action==='review-next'){reviewOffset+=30;loadReview();return;}
    if(action==='candidate'||action==='remove-number'){await api('/api/number',{id,brand:b.dataset.brand,no:b.dataset.no,remove:action==='remove-number'});await refresh();detail(id);toast(action==='candidate'?'확인한 번호를 연결했어요.':'직접 연결한 번호를 지웠어요.');return;}
    if(action==='job'){b.disabled=true;await api('/api/job',{kind:b.dataset.kind});S.stats.job={status:'running',stage:b.dataset.kind,total:0,done:0};render();startPoll();toast('조회가 시작됐어요. 다른 화면도 사용할 수 있어요.');return;}
    if(action==='remove-key'){await api('/api/api-key',{key:''});S.has_api_key=false;render();toast('저장한 API 키를 삭제했어요.');return;}
    if(b.id==='review-exclude'||b.id==='review-reset'){await api('/api/correct',{video_id:$('#review-video-id').value,exclude:b.id==='review-exclude',reset:b.id==='review-reset'});$('#review-dialog').close();await refresh();toast(b.id==='review-exclude'?'음악 아님으로 지정했어요.':'직접 수정한 정보를 되돌렸어요.');return;}
  }catch(e){toast(e.message);b.disabled=false;if(b.dataset.action==='merge-now')b.textContent='합치기';}
});
let searchTimer;
document.addEventListener('input',e=>{
  if(e.target.id==='knowledge-search'){knowledgeQuery=e.target.value;knowledgeOffset=0;clearTimeout(searchTimer);searchTimer=setTimeout(loadKnowledge,200);return;}
  if(e.target.id==='bulk-minimum'){const n=Number(e.target.value);if(Number.isSafeInteger(n)&&n>0){bulkMinimum=n;$('#bulk-recognize-start').textContent=`${n}회 이상 알아서 확인`;}return;}
  if(e.target.id==='merge-query'){renderMergeTargets();return;}
  if(e.target.id==='song-search'){query=e.target.value;limit=40;clearTimeout(searchTimer);searchTimer=setTimeout(render,140);}
  if(e.target.id==='review-search'){reviewQuery=e.target.value;reviewOffset=0;clearTimeout(searchTimer);searchTimer=setTimeout(loadReview,180);}
});
document.addEventListener('change',e=>{
  if(e.target.id==='knowledge-scope'){knowledgeScope=e.target.value;knowledgeOffset=0;loadKnowledge();return;}
  if(e.target.id==='sort-select'){sort=e.target.value;render();}
  if(e.target.id==='number-filter'){numberFilter=e.target.value;limit=40;render();}
  if(e.target.id==='review-sort'){reviewSort=e.target.value;reviewOffset=0;loadReview();}
  if(e.target.id==='review-status'){reviewStatus=e.target.value;reviewOffset=0;loadReview();}
  if(e.target.id==='review-kind'){reviewKind=e.target.value;reviewStatus='all';reviewOffset=0;render();}
});
document.addEventListener('submit',async e=>{
  e.preventDefault();try{
    if(e.target.id==='personal-sync-form'){await api('/api/personal-sync-config',{enabled:$('#personal-enabled').checked,repo:$('#personal-repo').value.trim(),password:$('#personal-password').value});$('#personal-password').value='';await loadPersonalSettings();toast('개인 동기화 설정을 저장했어요.');}
    if(e.target.id==='friends-settings'){await api('/api/friends',{display_name:$('#friends-display').value,share_songs:$('#friends-share').checked});await loadFriends();toast('설정을 저장했어요. 공유 내용은 다음 동기화에 반영돼요.');}
    if(e.target.id==='friend-add-form'){const login=$('#friend-add-login').value.trim().toLowerCase();await api('/api/friends',{friends:[...new Set([...friendState.settings.friends,login])]});await loadFriends();toast('친구를 등록했어요. 상대도 나를 추가한 뒤 동기화하면 연결돼요.');}
    if(e.target.id==='friend-search-form'){friendQuery=$('#friend-search').value.trim();friendOffset=0;await loadFriendShelf();}
    if(e.target.id==='sharing-form'){S.github_sync=await api('/api/github-sync-config',{repo:$('#sharing-repo').value,token:$('#sharing-token').value,enabled:$('#sharing-enabled').checked});$('#sharing-token').value='';toast('공유 설정을 저장했어요. 지금 동기화할 수 있어요.');}
    if(e.target.id==='review-form'){await saveReviewInformation();}
    if(e.target.id==='number-form'){const id=e.target.dataset.id;await api('/api/number',{id,brand:$('#number-brand').value,no:$('#number-value').value});await refresh();detail(id);toast('곡 번호를 저장했어요.');}
    if(e.target.id==='key-form'){const key=$('#api-key').value.trim();if(!key){toast('API 키를 입력해 주세요.');return;}const r=await api('/api/api-key',{key});S.has_api_key=r.has_api_key;$('#api-key').value='';render();toast('API 키를 이 PC에 저장했어요. 공식 API로 영상 조회를 시작할 수 있어요.');}
  }catch(error){toast(error.message);}
});
for(const d of document.querySelectorAll('dialog'))d.addEventListener('click',e=>{if(e.target===d){const r=d.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)d.close();}});
$('#main-content').innerHTML='<div class="loading">내 기록 속 노래를 불러오는 중…</div>';
refresh().catch(e=>{$('#main-content').innerHTML=`<div class="empty">앱에 연결하지 못했어요.<br>${esc(e.message)}<br>실행 창이 열려 있는지 확인해 주세요.</div>`;});

function mergeView(){return intro('SONG IDENTITIES','같은 노래를 한곳으로.','비슷한 제목은 후보예요. 아티스트와 원곡·커버·버전을 확인한 뒤 연결하세요.')+`<div class="panel"><p class="small muted">번역 제목이나 별칭도 직접 찾아 연결할 수 있어요. 원래 영상과 시청 기록은 유지되고 연결은 되돌릴 수 있어요.</p><label class="field">연결할 곡<select id="merge-pick">${S.tracks.map(t=>`<option value="${t.id}">${esc(t.title)} · ${esc(t.artist)}</option>`).join('')}</select></label><button class="button outline" data-action="merge-open">다른 표기 찾기</button> <button class="button primary" data-action="job" data-kind="auto_merge">확실한 같은 곡 자동 정리</button></div><div id="merge-results" class="loading">비슷한 제목을 찾는 중…</div>`;}
async function loadMerges(){try{const r=await api('/api/merge-candidates');if(view!=='merge')return;$('#merge-results').className='';$('#merge-results').innerHTML=`<h2>비슷한 제목 후보</h2>${r.candidates.map(c=>{const a=S.tracks.find(t=>t.id===c.source),b=S.tracks.find(t=>t.id===c.target);return a&&b?`<div class="kv"><span>${esc(a.title)} ↔ ${esc(b.title)}<br><small>${esc(a.artist)} · ${esc(c.reason||'제목 표기 비교')} · 유사도 ${Math.round(c.similarity*100)}%</small></span><button class="button outline" data-action="merge-now" data-id="${a.id}" data-target="${b.id}" title="${esc(b.title)}에 합치기">합치기</button><button class="button different-song" data-action="different-song" data-id="${a.id}" data-target="${b.id}">다른 곡임</button></div>`:'';}).join('')||'<p class="muted">비슷한 제목 후보가 없어요. 위에서 곡을 직접 찾아 연결할 수 있어요.</p>'}<h2>다른 곡으로 표시한 항목</h2>${(r.different||[]).map(d=>`<div class="kv"><span>${esc(d.source_title)} ↔ ${esc(d.target_title)}</span><button class="button outline" data-action="different-undo" data-id="${d.source}" data-target="${d.target}">표시 되돌리기</button></div>`).join('')||'<p class="muted">아직 다른 곡으로 표시한 항목이 없어요.</p>'}<h2>연결 기록</h2>${r.history.slice().reverse().map(h=>`<div class="kv"><span>${esc(h.source_title)} → ${esc(h.target_title)}${h.automatic?'<br><small>자동 정리 · 같은 아티스트의 제목 별칭 일치</small>':''}</span>${h.undone?'<span class="small muted">되돌림</span>':`<button class="button outline" data-action="merge-undo" data-id="${h.id}">되돌리기</button>`}</div>`).join('')||'<p class="muted">아직 직접 연결한 곡이 없어요.</p>'}`;}catch(e){if($('#merge-results'))$('#merge-results').textContent=e.message;}}
function openMerge(id){id=id||$('#merge-pick')?.value;const t=S.tracks.find(t=>t.id===id);if(!t)return;$('#detail-dialog').close();$('#merge-source').value=id;$('#merge-origin').textContent=`${t.title} · ${t.artist} · 기록 ${t.history_records}회`;$('#merge-query').value='';renderMergeTargets();$('#merge-dialog').showModal();}
function renderMergeTargets(){const source=$('#merge-source').value,q=$('#merge-query').value.toLocaleLowerCase();const a=S.tracks.find(t=>t.id===source);const list=S.tracks.filter(t=>t.id!==source&&(!q||(t.title+' '+t.artist).toLocaleLowerCase().includes(q))).sort((x,y)=>Number(y.artist===a?.artist)-Number(x.artist===a?.artist));$('#merge-target').innerHTML=list.map(t=>`<option value="${t.id}">${esc(t.title)} · ${esc(t.artist)} · 기록 ${t.history_records}회</option>`).join('');$('#merge-save').disabled=!list.length;}
async function webSongSearch(button){
  button.disabled=true;button.textContent='Google 검색 중…';
  try{
    const r=await api('/api/google-song-search',{video_id:$('#review-video-id').value});
    $('#recognition-result').textContent=`Google${r.cached?' · 저장된 결과':''}: ${r.reason}`;
    const root=$('#recognition-candidates');root._candidates=r.candidates;
    root.innerHTML=`<p class="small muted">검색어: ${esc(r.query)}</p><a href="${esc(r.search_url)}" target="_blank" rel="noreferrer">제목 전문으로 Google 검색 ↗</a>`+
      r.candidates.map((c,i)=>`<div class="candidate"><button type="button" class="button outline" data-action="recognition-candidate" data-index="${i}">${esc(c.title)} · ${esc(c.artist)}</button><a href="${esc(c.url)}" target="_blank" rel="noreferrer">곡 정보 ↗</a></div>`).join('')+
      (r.results||[]).slice(0,10).map(item=>`<p><a href="${esc(item.url)}" target="_blank" rel="noreferrer">${esc(item.title)} ↗</a></p>`).join('');
  }catch(e){toast('Google 검색: '+e.message);}finally{button.disabled=false;button.textContent='Google 전문 검색';}
}

function bulkRecognitionPanel(){return `<div class="panel"><div class="dialog-actions"><label>시청 기록 <input id="bulk-minimum" type="number" min="1" step="1" value="${bulkMinimum}" aria-label="자동 확인 최소 시청 횟수" class="bulk-minimum" ${bulkRecognition.running?'disabled':''}>회 이상</label><button id="bulk-recognize-start" class="button primary" ${bulkRecognition.running?'disabled':''}>${bulkMinimum}회 이상 알아서 확인</button><button id="bulk-recognize-stop" class="button outline" ${bulkRecognition.running?'':'disabled'}>중지</button></div><p class="small muted">현재 분류·검색 조건의 전체 영상에 적용해요. 등록된 곡은 목록과 일괄 확인 대상에서 제외해요. 직접 제외한 영상은 선택 범주에 포함되면 확인하되 기존 결정을 자동으로 덮어쓰지 않아요. 명확한 곡은 저장하고 애매한 후보는 확인용으로 남겨요.</p><label class="small muted"><input id="bulk-retry" type="checkbox"> 이미 검사한 영상도 재검사</label><p id="bulk-recognize-progress" class="small muted">${bulkProgressText()}</p></div>`;}
function bulkProgressText(){const b=bulkRecognition;return `${b.running?(b.stop?'현재 항목 처리 후 중지':'처리 중'):b.done?'처리 종료':'대기'} · ${b.done} / ${b.total}개 · 저장 ${b.saved} · 확인 필요 ${b.candidates} · 오류 ${b.errors}${b.localOnly?' · Google 조회 제한으로 나머지는 로컬 인식만 진행':''}`;}
function updateBulkRecognition(){const p=$('#bulk-recognize-progress');if(p)p.textContent=bulkProgressText();const start=$('#bulk-recognize-start'),stop=$('#bulk-recognize-stop'),input=$('#bulk-minimum');if(start)start.disabled=bulkRecognition.running;if(stop)stop.disabled=!bulkRecognition.running||bulkRecognition.stop;if(input)input.disabled=bulkRecognition.running;}
async function startBulkRecognition(){
  if(bulkRecognition.running)return;
  const n=Number($('#bulk-minimum').value);
  if(!Number.isSafeInteger(n)||n<1){toast('시청 횟수는 1 이상의 정수로 입력해 주세요.');return;}
  bulkMinimum=n;bulkRecognition={running:true,stop:false,total:0,done:0,saved:0,candidates:0,errors:0,localOnly:false};updateBulkRecognition();
  const status=reviewStatus,q=reviewQuery;
  try{
    const retry=$('#bulk-retry')?.checked?'1':'0';
    const targets=await api(`/api/recognition-targets?status=${encodeURIComponent(status)}&q=${encodeURIComponent(q)}&min_views=${n}&kind=${encodeURIComponent(reviewKind)}&retry=${retry}`);
    bulkRecognition.total=targets.items.length;updateBulkRecognition();
    for(const item of targets.items){
      if(bulkRecognition.stop)break;
      if(recognizing.has(item.video_id))continue;
      let button=document.querySelector(`[data-action="recognize"][data-video-id="${item.video_id}"]`);
      if(!button){const row=document.createElement('div');row.className='review-row';button=document.createElement('button');row.appendChild(button);}
      const result=await autoRecognize(item.video_id,button,{web:!bulkRecognition.localOnly});
      bulkRecognition.done++;
      if(result?.status==='recognized'&&result.saved!==false)bulkRecognition.saved++;
      else if(result?.status==='recognized'){}
      else if(result?.status==='error')bulkRecognition.errors++;
      else bulkRecognition.candidates++;
      if(result?.google&&result.google.status!=='ok')bulkRecognition.localOnly=true;
      updateBulkRecognition();
    }
    toast(`일괄 확인 ${bulkRecognition.done}개 처리 · 이미 검사한 ${targets.skipped||0}개 건너뜀${targets.total?'':' · 재검사하려면 재검사 포함을 선택하세요.'}`);
  }catch(e){toast(e.message);}finally{bulkRecognition.running=false;updateBulkRecognition();syncRecognitionState();}
}

function wholeRecognitionSummary(){
  return `<div id="whole-scan-panel" class="panel">${wholePanelContent()}</div>`;
}
let wholePollTimer;
let reversePollTimer;
function startReversePoll(){
  if(reversePollTimer)return;
  reversePollTimer=setInterval(async()=>{
    try{const r=await api('/api/reverse-catalogue-job');S.reverse_catalogue_job=r;if(r.status!=='running'){clearInterval(reversePollTimer);reversePollTimer=null;S=await api('/api/bootstrap');sidebarQueue();toast(r.status==='complete'?`역방향 탐색 완료 · 영상 ${r.saved}개 추가 저장`:'역방향 탐색 상태를 확인해 주세요.');}const panel=$('#reverse-catalogue-panel');if(panel)panel.outerHTML=reverseCataloguePanel();}
    catch(e){clearInterval(reversePollTimer);reversePollTimer=null;toast(e.message);}
  },2000);
}
let wholeSavedSeen=-1;
function wholePanelContent(){
  const j=S.recognition_job||{},active=j.status==='running',current=j.engine==='whole-metadata-v1';
  return `<h3>남은 영상 전체에서 음악 추출</h3><p class="small muted">시청 횟수·위의 분류 선택과 관계없이 모든 미등록 영상을 자동 판별해요. 빠른 전체 판별 후 음악 근거가 있는 영상의 음악 정보·원곡 링크·음악 DB를 조회하고, 일치하는 곡을 저장해요. 직접 수정·제외한 영상은 유지해요. 화면을 닫아도 서버가 켜져 있으면 계속 진행하며 서버 재시작 시 진행 중이던 작업을 이어가요.</p><div class="dialog-actions"><button class="button primary" data-action="whole-start" ${active?'disabled':''}>${current&&j.status!=='complete'?'전체 처리 이어가기':'남은 영상 전체 자동 처리'}</button><button class="button outline" data-action="scan-pending">재탐색 대기 목록 보기</button><button class="button outline" data-action="whole-stop" ${active?'':'disabled'}>전체 처리 중지</button><button class="button outline" data-action="job" data-kind="non_song">곡 아닌 영상 정리</button></div>${current?`<p class="note">${{running:'진행 중',complete:'완료',stopped:'중지됨',error:'오류'}[j.status]||'대기'} · ${j.stage==='local'?'전체 로컬 판별':'음악 메타데이터 확인'}<br>처리 완료 ${count(j.done)} / ${count(j.total)} · 로컬 판별 대기 ${count(j.local_remaining)} · 추가 조회 대기 ${count(j.deep_remaining)}<br>자동 저장 ${count(j.saved)} · 후보 ${count(j.candidates)} · 곡 영상 아님 ${count(j.non_song)} · 단일곡 근거 없음 ${count(j.no_music_evidence)} · 여러 곡 ${count(j.collection)} · 음악 설명 ${count(j.music_explain)} · 활동 유형 판별 ${count(j.activity_known)} · 활동 유형 추정 ${count(j.activity_provisional)} · 정보 부족 ${count(j.info_missing)} · 곡 정보 미확인 ${count(j.unresolved)} · 오류 ${count(j.errors)}${j.current_title?`<br>현재: ${esc(j.current_title)}`:''}${j.reason?`<br>${esc(j.reason)}`:''}</p>`:'<p class="small muted">기존 전체 확인 결과도 최신 인식 로직으로 다시 검사해요. 사람이 후보를 하나씩 선택할 필요 없이 처리합니다.</p>'}`;
}
function updateWholePanel(){const panel=$('#whole-scan-panel');if(panel)panel.innerHTML=wholePanelContent();}
function startWholePoll(){
  if(wholePollTimer)return;
  wholePollTimer=setInterval(async()=>{
    try{S.recognition_job=await api('/api/recognition-job');updateWholePanel();if(S.recognition_job.saved!==wholeSavedSeen){wholeSavedSeen=S.recognition_job.saved;S=await api('/api/bootstrap');sidebarQueue();updateWholePanel();}if(S.recognition_job.status!=='running'){clearInterval(wholePollTimer);wholePollTimer=null;syncRecognitionState();toast(S.recognition_job.status==='complete'?'전체 음악 추출이 완료됐어요.':S.recognition_job.status==='stopped'?'전체 처리를 중지했어요. 이어갈 수 있어요.':'전체 처리 상태를 확인해 주세요.');}}
    catch(e){clearInterval(wholePollTimer);wholePollTimer=null;toast(e.message);}
  },4000);
}














