import WaveSurfer from "./vendor/wavesurfer.mjs";
import RegionsPlugin from "./vendor/wavesurfer-regions.mjs";
import TimelinePlugin from "./vendor/wavesurfer-timeline.mjs";

const token = document.querySelector('meta[name="automeme-token"]').content;
const stageOrder = ["transcribe", "analyze", "timeline", "render"];
const labels = {home:"Tổng quan",create:"Tạo video",editor:"Biên tập",library:"Kho meme",settings:"Thiết lập"};
const profileInfo = {
  default:["◎","Cân bằng","Thiết lập mặc định"],
  subtle:["◌","Tinh tế","Ít meme, chọn lọc"],
  funny:["☺","Hài hước","Nhịp vui, rõ punchline"],
  chaotic:["ϟ","Bùng nổ","Meme dày và nhanh"],
  pro:["★","Chuyên nghiệp","Cắt tràn màn hình, zoom, SFX"],
};

const state = {
  dashboard:null, selectedVideo:null, selectedProfile:"default", currentProject:null,
  selectedEvent:null, library:[], libraryFilter:"all", player:null, wave:null, regions:null,
  poller:null, handledJob:null, suggestTimer:null,
};

const $ = (selector, root=document) => root.querySelector(selector);
const $$ = (selector, root=document) => [...root.querySelectorAll(selector)];
const escapeHtml = (value="") => String(value).replace(/[&<>'"]/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"})[char]);
const attr = value => escapeHtml(value);
const formatBytes = bytes => {
  if (!Number.isFinite(bytes)) return "—";
  const units=["B","KB","MB","GB"]; let value=bytes,index=0;
  while(value>=1024 && index<units.length-1){value/=1024;index+=1;}
  return `${value.toFixed(index ? 1 : 0)} ${units[index]}`;
};
const formatTime = seconds => {
  const value=Math.max(0,Number(seconds)||0), mins=Math.floor(value/60), secs=value-mins*60;
  return `${String(mins).padStart(2,"0")}:${secs.toFixed(2).padStart(5,"0")}`;
};
const splitList = value => value.split(",").map(item=>item.trim()).filter(Boolean);
const isVideoAsset = asset => /\.(mp4|webm|mov)$/i.test(asset||"");
const eventKind = event => event.type==="zoom"?"ZOOM":event.type==="sfx"?"SFX":event.mode==="cutaway"?"TRÀN MÀN HÌNH":"MEME GÓC";
const regionColor = event => event.status==="rejected"?"rgba(125,135,151,.18)"
  :event.type==="zoom"?"rgba(54,214,160,.28)":event.type==="sfx"?"rgba(245,184,75,.26)"
  :event.mode==="cutaway"?"rgba(251,113,133,.34)":"rgba(139,92,246,.32)";

async function api(path, options={}) {
  const headers={...(options.headers||{})};
  if (options.method && options.method !== "GET") headers["X-Automeme-Token"]=token;
  if (options.body && typeof options.body === "object" && !(options.body instanceof Blob)) {
    headers["Content-Type"]="application/json";
    options.body=JSON.stringify(options.body);
  }
  const response=await fetch(path,{...options,headers});
  const data=await response.json().catch(()=>({error:`HTTP ${response.status}`}));
  if(!response.ok) throw new Error(data.error||`HTTP ${response.status}`);
  return data;
}

function icons(){ if(window.lucide) window.lucide.createIcons({attrs:{"stroke-width":1.8}}); }
function toast(message,type="success"){
  const node=document.createElement("div"); node.className=`toast ${type}`;
  node.innerHTML=`<i data-lucide="${type==="error"?"circle-alert":"circle-check"}"></i><span>${escapeHtml(message)}</span>`;
  $("#toast-stack").append(node); icons(); setTimeout(()=>node.remove(),4200);
}

function navigate(view){
  $$(".view").forEach(node=>node.classList.toggle("active",node.id===`view-${view}`));
  $$(".nav-item[data-view]").forEach(node=>node.classList.toggle("active",node.dataset.view===view));
  $("#page-name").textContent=labels[view]; $("#sidebar").classList.remove("open");
  history.replaceState(null,"",`#${view}`);
  if(view==="library") loadLibrary();
  if(view==="editor" && state.selectedVideo) loadEditor(state.selectedVideo);
}

function renderProfiles(profiles){
  const root=$("#profile-cards");
  root.innerHTML=profiles.map(name=>{
    const info=profileInfo[name]||["◇",name,"Profile tùy chỉnh"];
    return `<button class="profile-card ${name===state.selectedProfile?"active":""}" data-profile="${attr(name)}"><i>${escapeHtml(info[0])}</i><strong>${escapeHtml(info[1])}</strong><small>${escapeHtml(info[2])}</small></button>`;
  }).join("");
  $$(".profile-card",root).forEach(button=>button.addEventListener("click",()=>{
    state.selectedProfile=button.dataset.profile;
    $$(".profile-card",root).forEach(item=>item.classList.toggle("active",item===button));
  }));
}

function projectCard(project){
  const done=Object.values(project.artifacts).filter(Boolean).length;
  const status={completed:"Hoàn tất",review:"Chờ duyệt",processing:"Đang làm",new:"Mới"}[project.status]||project.status;
  return `<article class="project-card" data-project="${attr(project.name)}"><div class="project-thumb"><i data-lucide="play-circle"></i><span class="project-status ${attr(project.status)}">${escapeHtml(status)}</span></div><div class="project-info"><strong title="${attr(project.name)}">${escapeHtml(project.name)}</strong><div><span>${formatBytes(project.size)}</span><span>${new Date(project.modified*1000).toLocaleDateString("vi-VN")}</span></div><div class="project-progress" title="${done}/4 bước">${[0,1,2,3].map(i=>`<i class="${i<done?"done":""}"></i>`).join("")}</div></div></article>`;
}

function renderDashboard(data){
  state.dashboard=data;
  $("#stat-projects").textContent=data.project_count;
  $("#stat-assets").textContent=data.asset_count;
  const failures=data.environment.filter(row=>row.status==="fail").length;
  const warnings=data.environment.filter(row=>row.status==="warn").length;
  $("#stat-system").textContent=failures?"Cần sửa":warnings?"Sẵn sàng*":"Sẵn sàng";
  $("#stat-system-note").textContent=failures?`${failures} mục đang chặn`:warnings?`${warnings} cảnh báo không chặn`:"mọi thành phần đã đạt";
  const pill=$("#system-pill"), dot=$(".status-dot",pill);
  dot.className=`status-dot ${failures?"fail":warnings?"warn":""}`;
  $("span:last-child",pill).textContent=failures?"Hệ thống cần sửa":warnings?"Có cảnh báo":"Hệ thống sẵn sàng";
  const root=$("#recent-projects");
  root.innerHTML=data.projects.length?data.projects.slice(0,6).map(projectCard).join(""):`<div class="empty-state"><i data-lucide="film"></i><p>Chưa có dự án. Hãy nhập video đầu tiên.</p><button class="button primary" data-go="create">Tạo video mới</button></div>`;
  bindProjectCards(); renderProfiles(data.profiles); renderEnvironment(data.environment); updateJob(data.job,{silent:true}); icons();
}

function bindProjectCards(){
  $$("[data-project]").forEach(card=>card.addEventListener("click",()=>{
    const project=state.dashboard?.projects.find(item=>item.name===card.dataset.project);
    selectProject(project);
    if(project?.artifacts.timeline) navigate("editor"); else navigate("create");
  }));
  $$('[data-go]').forEach(button=>button.onclick=()=>navigate(button.dataset.go));
}

function selectProject(project){
  if(!project)return;
  state.selectedVideo=project.name;
  localStorage.setItem("automeme.lastVideo",project.name);
  $("#selected-project").classList.remove("hidden");
  $("#selected-name").textContent=project.name;
  $("#selected-meta").textContent=`${formatBytes(project.size)} · ${project.status==="completed"?"Đã hoàn tất":"Sẵn sàng xử lý"}`;
}

function renderEnvironment(rows){
  const root=$("#environment-list"); if(!root)return;
  root.innerHTML=rows.map(row=>`<div class="env-row"><span class="env-status ${attr(row.status)}"><i data-lucide="${row.status==="ok"?"check":"triangle-alert"}"></i></span><div><strong>${escapeHtml(row.name)}</strong><small>${escapeHtml(row.detail)}</small></div></div>`).join("");
  icons();
}

async function loadDashboard(refresh=false){
  try {
    const data=await api(refresh?"/api/dashboard?refresh=1":"/api/dashboard"); renderDashboard(data);
  } catch(error){ toast(error.message,"error"); }
}

function setupUploads(){
  if(window.FilePond){
    const pond=window.FilePond.create($("#video-upload"),{
      labelIdle:'Kéo video vào đây hoặc <span class="filepond--label-action">chọn từ máy</span>',
      labelFileProcessing:"Đang nhập video",labelFileProcessingComplete:"Đã nhập xong",
      labelTapToCancel:"Bấm để hủy",labelTapToRetry:"Bấm để thử lại",allowMultiple:false,
      server:{process:(_field,file,_metadata,load,error,progress,abort)=>{
        const xhr=new XMLHttpRequest(); xhr.open("POST","/api/videos/upload");
        xhr.setRequestHeader("X-Automeme-Token",token); xhr.setRequestHeader("X-Filename",file.name);
        xhr.upload.onprogress=event=>progress(event.lengthComputable,event.loaded,event.total);
        xhr.onload=()=>{try{const data=JSON.parse(xhr.responseText);if(xhr.status>=200&&xhr.status<300){selectProject(data.project);loadDashboard();load(data.project.name);}else error(data.error||"Không thể tải video");}catch{error("Phản hồi upload không hợp lệ");}};
        xhr.onerror=()=>error("Mất kết nối khi upload"); xhr.send(file); return {abort:()=>{xhr.abort();abort();}};
      }},
    });
    pond.on("addfile",error=>{if(error)toast(error.main||String(error),"error");});
  }
  $("#asset-upload-button").onclick=()=>$("#asset-upload").click();
  $("#popular-library-button").onclick=installPopularLibrary;
  $("#animated-library-button").onclick=installAnimatedLibrary;
  $("#sfx-library-button").onclick=installSfxLibrary;
  $("#asset-upload").onchange=async event=>{
    const file=event.target.files[0]; if(!file)return;
    try{
      const response=await fetch("/api/library/upload",{method:"POST",headers:{"X-Automeme-Token":token,"X-Filename":file.name},body:file});
      const data=await response.json(); if(!response.ok)throw new Error(data.error);
      toast(`Đã thêm ${file.name}`); await loadLibrary(); await loadDashboard();
    }catch(error){toast(error.message,"error");} finally{event.target.value="";}
  };
}

async function startJob(){
  if(!state.selectedVideo){toast("Hãy chọn hoặc tải lên một video trước.","error");return;}
  try{
    const data=await api("/api/jobs",{method:"POST",body:{video:state.selectedVideo,profile:state.selectedProfile,force:$("#force-run").checked}});
    updateJob(data.job); toast("Pipeline đã bắt đầu"); beginPolling();
  }catch(error){toast(error.message,"error");}
}

async function startYoutubeDownload(){
  const url=$("#youtube-url").value.trim();
  if(!url){toast("Hãy dán link YouTube trước.","error");$("#youtube-url").focus();return;}
  const body={url,start:$("#youtube-from").value.trim()||null,end:$("#youtube-to").value.trim()||null};
  try{
    const data=await api("/api/videos/youtube",{method:"POST",body});
    updateJob(data.job); toast("Đang tải video từ YouTube"); beginPolling();
  }catch(error){toast(error.message,"error");}
}

function updateJob(job,{silent=false}={}){
  if(!job)return;
  const download=job.kind==="download";
  $("#job-title").textContent=download
    ?(job.status==="completed"?"Đã tải video":job.status==="failed"?"Tải video cần chú ý":"Đang tải từ YouTube")
    :(job.status==="completed"?"Video đã sẵn sàng":job.status==="failed"?"Pipeline cần chú ý":job.video);
  $("#job-message span").textContent=job.error||job.message;
  $("#job-message").classList.toggle("error",job.status==="failed");
  $$("#pipeline-steps [data-stage]").forEach(row=>{
    row.classList.toggle("done",job.completed_stages.includes(row.dataset.stage));
    row.classList.toggle("running",job.status==="running"&&job.stage===row.dataset.stage);
  });
  if(job.status==="running"||job.status==="queued"){beginPolling();return;}
  // Việc khi job kết thúc chỉ chạy MỘT lần cho mỗi job. Trước đây updateJob → loadDashboard →
  // renderDashboard → updateJob lặp vô hạn khi job cuối đã xong (gọi API và hiện toast liên tục).
  const key=`${job.id}:${job.status}`;
  const polling=Boolean(state.poller);
  clearInterval(state.poller);state.poller=null;
  if(state.handledJob===key)return;
  if(silent&&!polling){state.handledJob=key;return;}  // mở trang lại: không báo job cũ
  state.handledJob=key;
  if(job.status!=="completed")return;
  if(download){
    loadDashboard().then(()=>selectProject(state.dashboard?.projects.find(item=>item.name===job.video)));
    $("#youtube-url").value="";
    toast("Đã tải video — chọn phong cách rồi bấm Bắt đầu xử lý.");
  }else{
    loadDashboard();
    toast("Pipeline hoàn tất — mở Biên tập để duyệt timeline.");
  }
}

function beginPolling(){
  if(state.poller)return;
  state.poller=setInterval(async()=>{try{const data=await api("/api/job");updateJob(data.job);}catch{}},1200);
}

async function loadEditor(videoName){
  try{
    const project=await api(`/api/project?video=${encodeURIComponent(videoName)}`);
    state.currentProject=project; state.selectedEvent=null;
    $("#editor-empty").classList.add("hidden"); $("#editor-layout").classList.remove("hidden");
    $("#editor-title").textContent=project.video;
    const source=project.video_url;
    if(state.player){state.player.source={type:"video",sources:[{src:source}]};}
    else {state.player=new window.Plyr($("#player"),{iconUrl:"/assets/vendor/plyr.svg",controls:["play-large","play","progress","current-time","mute","volume","settings","pip","fullscreen"],settings:["speed"]});state.player.source={type:"video",sources:[{src:source}]};state.player.on("timeupdate",onTimeUpdate);}
    $("#download-button").classList.toggle("disabled",!project.output_exists);
    $("#download-button").href=project.output_url;
    renderTimeline(); renderTranscript(); setupWaveform();
    if(project.events.length) selectEvent(project.events[0].id);
    icons();
  }catch(error){
    $("#editor-layout").classList.add("hidden");$("#editor-empty").classList.remove("hidden");
    toast(error.message,"error");
  }
}

function mediaPreview(url,type,alt=""){
  if(type==="video")return `<video src="${attr(url)}" muted loop preload="metadata" aria-label="${attr(alt)}"></video>`;
  if(type==="audio")return `<audio src="${attr(url)}" controls preload="metadata" aria-label="${attr(alt)}"></audio>`;
  return `<img src="${attr(url)}" alt="${attr(alt)}" loading="lazy">`;
}

function renderTimeline(){
  const root=$("#timeline-list"), events=state.currentProject.events;
  root.innerHTML=events.map(event=>`<button class="event-chip ${event.status==="rejected"?"rejected":""} ${event.mode==="cutaway"?"cutaway":""}" data-event="${attr(event.id)}">${chipMedia(event)}<span><strong>${escapeHtml(event.query||event.reason||event.id)}</strong><small>${escapeHtml(eventKind(event))} · ${formatTime(event.start)} · ${event.duration.toFixed(1)}s</small></span></button>`).join("");
  $$("[data-event]",root).forEach(button=>button.onclick=()=>selectEvent(button.dataset.event));
  if(window.Sortable) new window.Sortable(root,{animation:160,direction:"horizontal",onEnd:()=>toast("Thứ tự hiển thị được quyết định bởi timestamp trên waveform.")});
}

function chipMedia(event){
  if(event.type==="zoom")return `<span class="chip-icon zoom"><i data-lucide="zoom-in"></i></span>`;
  if(event.type==="sfx")return `<span class="chip-icon sfx"><i data-lucide="audio-lines"></i></span>`;
  return mediaPreview(event.preview_url,isVideoAsset(event.asset)?"video":"image",event.id);
}

function setupWaveform(){
  if(state.wave){state.wave.destroy();state.wave=null;}
  const video=$("#player");
  state.regions=RegionsPlugin.create();
  state.wave=WaveSurfer.create({container:"#waveform",media:video,url:state.currentProject.video_url,height:62,waveColor:"#495466",progressColor:"#9c6afb",cursorColor:"#ffffff",cursorWidth:1,barWidth:2,barGap:2,barRadius:2,normalize:true,plugins:[state.regions,TimelinePlugin.create({container:"#wave-timeline",height:16,timeInterval:.5,primaryLabelInterval:5,style:{fontSize:"8px",color:"#7d8797"}})]});
  state.wave.on("ready",()=>{
    state.currentProject.events.forEach(event=>state.regions.addRegion({id:event.id,start:event.start,end:event.start+event.duration,color:regionColor(event),drag:true,resize:true}));
  });
  state.regions.on("region-clicked",region=>selectEvent(region.id));
  state.regions.on("region-updated",async region=>{
    try{await updateEvent(region.id,{start:region.start,duration:region.end-region.start},false);toast("Đã cập nhật thời gian");}catch(error){toast(error.message,"error");await loadEditor(state.selectedVideo);}
  });
}

function selectEvent(eventId){
  state.selectedEvent=state.currentProject.events.find(event=>event.id===eventId);
  if(!state.selectedEvent)return;
  $$(".event-chip").forEach(node=>node.classList.toggle("active",node.dataset.event===eventId));
  renderEventInspector();
  if(state.player)state.player.currentTime=state.selectedEvent.start;
}

const actionButtons = () => `<div class="event-actions"><button class="button accept" id="accept-event"><i data-lucide="check"></i>Chấp nhận</button><button class="button reject" id="reject-event"><i data-lucide="x"></i>Từ chối</button></div>`;
const timingFields = (event,maxDuration="") => `<div class="form-grid"><label><span>Bắt đầu (giây)</span><input id="event-start" type="number" min="0" step="0.05" value="${event.start}"></label><label><span>Thời lượng</span><input id="event-duration" type="number" min="0.05" ${maxDuration?`max="${maxDuration}"`:""} step="0.05" value="${event.duration}"></label></div>`;
const eventReason = event => event.reason||event.confidence!=null?`<p class="event-reason">${event.confidence!=null?`<b>${Math.round(event.confidence*100)}%</b> · `:""}${escapeHtml(event.reason||"")}</p>`:"";
const modeSwitch = mode => `<div class="mode-switch" role="radiogroup" aria-label="Cách hiện meme"><button type="button" role="radio" data-mode="overlay" aria-checked="${mode!=="cutaway"}" class="${mode!=="cutaway"?"active":""}"><i data-lucide="picture-in-picture-2"></i>Góc màn hình</button><button type="button" role="radio" data-mode="cutaway" aria-checked="${mode==="cutaway"}" class="${mode==="cutaway"?"active":""}"><i data-lucide="maximize"></i>Tràn màn hình</button></div>`;
const suggestionBox = (query,title,hint) => `<div class="suggestions"><div class="suggestions-head"><strong>${escapeHtml(title)}</strong><small>${escapeHtml(hint)}</small></div><label class="search-box"><i data-lucide="search"></i><input id="suggestion-query" value="${attr(query||"")}" placeholder="Tìm meme khác: sốc, cười, xấu hổ…"></label><div class="suggestion-grid" id="suggestion-grid"></div></div>`;

function bindStatusButtons(event){
  $("#accept-event").onclick=()=>setEventStatus(event.id,"accept");
  $("#reject-event").onclick=()=>setEventStatus(event.id,"reject");
}

function renderEventInspector(){
  const event=state.selectedEvent, assets=state.currentProject.assets, inspector=$("#event-inspector");
  if(event.type==="zoom"){
    inspector.innerHTML=`<div class="event-form"><div class="event-preview zoom-preview"><i data-lucide="zoom-in"></i><p>Phóng vào khung hình gốc ngay trước cú cắt — tạo đà cho meme tràn màn hình.</p></div>${timingFields(event,3)}<label><span>Độ phóng <b class="range-value" id="factor-value">${event.factor.toFixed(2)}×</b></span><input id="event-factor" type="range" min="1.01" max="1.5" step="0.01" value="${event.factor}"></label><button class="button primary wide" id="save-event"><i data-lucide="save"></i>Lưu thay đổi</button>${actionButtons()}</div>`;
    $("#event-factor").oninput=input=>$("#factor-value").textContent=`${Number(input.target.value).toFixed(2)}×`;
    $("#save-event").onclick=()=>saveEvent(event.id,{start:Number($("#event-start").value),duration:Number($("#event-duration").value),factor:Number($("#event-factor").value)});
    bindStatusButtons(event); icons(); return;
  }
  if(event.type==="sfx"){
    const sounds=state.currentProject.sfx_assets||[];
    inspector.innerHTML=`<div class="event-form"><div class="event-preview">${mediaPreview(event.preview_url,"audio",event.id)}</div>${eventReason(event)}<label><span>Sound effect thay thế</span><select id="event-asset">${sounds.map(asset=>`<option value="${attr(asset)}" ${asset===event.asset?"selected":""}>${escapeHtml(asset.split("/").pop())}</option>`).join("")}</select></label>${timingFields(event,5)}<label><span>Âm lượng (0–100%)</span><input id="event-volume" type="range" min="0" max="1" step="0.01" value="${event.volume}"></label><button class="button primary wide" id="save-event"><i data-lucide="save"></i>Lưu thay đổi</button>${actionButtons()}</div>`;
    $("#save-event").onclick=()=>saveEvent(event.id,{asset:$("#event-asset").value,start:Number($("#event-start").value),duration:Number($("#event-duration").value),volume:Number($("#event-volume").value)});
    bindStatusButtons(event); icons(); return;
  }
  const cut=event.mode==="cutaway";
  inspector.innerHTML=`<div class="event-form"><div class="event-preview ${cut?"cutaway":""}">${mediaPreview(event.preview_url,isVideoAsset(event.asset)?"video":"image",event.id)}</div>${eventReason(event)}${modeSwitch(event.mode)}${timingFields(event)}<div class="form-grid ${cut?"hidden":""}"><label><span>Vị trí</span><select id="event-position">${["top-left","top-right","bottom-left","bottom-right","center"].map(value=>`<option ${value===(event.position||state.currentProject.display?.position_default||"bottom-right")?"selected":""}>${value}</option>`).join("")}</select></label><label><span>Tỉ lệ</span><input id="event-scale" type="number" min="0.05" max="1" step="0.05" value="${event.scale||state.currentProject.display?.scale_default||.3}"></label></div><label><span>Hoặc chọn trong toàn bộ thư viện</span><select id="event-asset">${assets.map(asset=>`<option value="${attr(asset)}" ${asset===event.asset?"selected":""}>${escapeHtml(asset.split("/").pop())}</option>`).join("")}</select></label><button class="button primary wide" id="save-event"><i data-lucide="save"></i>Lưu thay đổi</button>${actionButtons()}${suggestionBox(event.query,"Meme khác phù hợp","Bấm để thay ngay")}</div>`;
  $$(".mode-switch button",inspector).forEach(button=>button.onclick=()=>{
    if(button.dataset.mode!==event.mode)saveEvent(event.id,{mode:button.dataset.mode});
  });
  $("#save-event").onclick=()=>{
    const patch={asset:$("#event-asset").value,start:Number($("#event-start").value),duration:Number($("#event-duration").value)};
    if(!cut){patch.position=$("#event-position").value;patch.scale=Number($("#event-scale").value);}
    saveEvent(event.id,patch);
  };
  bindStatusButtons(event);
  const pick=asset=>{if(asset!==event.asset)saveEvent(event.id,{asset});};
  bindSuggestionSearch({eventId:event.id,onPick:pick});
  loadSuggestions({eventId:event.id,onPick:pick}); icons();
}

function bindSuggestionSearch(options){
  $("#suggestion-query").oninput=input=>{
    clearTimeout(state.suggestTimer);
    state.suggestTimer=setTimeout(()=>loadSuggestions({...options,query:input.target.value.trim()}),300);
  };
}

async function loadSuggestions({eventId=null,query="",mode=null,onPick}){
  const grid=$("#suggestion-grid"); if(!grid)return;
  grid.innerHTML='<div class="spinner"></div>';
  const params=new URLSearchParams({video:state.selectedVideo});
  if(eventId)params.set("id",eventId); if(query)params.set("q",query); if(mode)params.set("mode",mode);
  try{
    const data=await api(`/api/suggestions?${params}`);
    if(!grid.isConnected)return;
    grid.innerHTML=data.items.length?data.items.map(item=>`<button type="button" class="suggestion-card ${item.current?"current":""}" data-pick="${attr(item.asset)}" title="${attr(item.description||item.id)}">${mediaPreview(item.preview_url,item.type==="video"?"video":"image",item.id)}<span>${escapeHtml(item.id)}</span>${item.current?"<b>Đang dùng</b>":""}</button>`).join(""):`<p class="suggestion-empty">Không có meme khớp. Thử từ khác, hoặc thêm meme ở Kho meme.</p>`;
    $$("[data-pick]",grid).forEach(card=>card.onclick=()=>onPick(card.dataset.pick,card));
  }catch(error){grid.innerHTML=`<p class="suggestion-empty">${escapeHtml(error.message)}</p>`;}
}

function renderAddForm(){
  if(!state.currentProject)return;
  state.player?.pause(); state.selectedEvent=null;
  $$(".event-chip").forEach(node=>node.classList.remove("active"));
  $$(".inspector-tabs button").forEach(item=>item.classList.toggle("active",item.dataset.tab==="event"));
  $("#event-inspector").classList.remove("hidden"); $("#transcript-panel").classList.add("hidden");
  let mode="overlay", picked=null;
  const start=Number((state.player?.currentTime||0).toFixed(2));
  $("#event-inspector").innerHTML=`<div class="event-form"><div class="inspector-title"><i data-lucide="plus"></i><strong>Chèn meme mới</strong></div><label><span>Bắt đầu (giây)</span><input id="add-start" type="number" min="0" step="0.05" value="${start}"></label>${modeSwitch(mode)}${suggestionBox("","Chọn meme","Bấm một meme để chọn")}<button class="button primary wide" id="add-confirm" disabled><i data-lucide="plus"></i>Chèn meme đã chọn</button><button class="button ghost wide" id="add-cancel">Hủy</button></div>`;
  const onPick=(asset,card)=>{picked=asset;$$("[data-pick]").forEach(node=>node.classList.toggle("picked",node===card));$("#add-confirm").disabled=false;};
  $$(".mode-switch button").forEach(button=>button.onclick=()=>{
    mode=button.dataset.mode;
    $$(".mode-switch button").forEach(item=>{item.classList.toggle("active",item===button);item.setAttribute("aria-checked",String(item===button));});
    loadSuggestions({mode,query:$("#suggestion-query").value.trim(),onPick});
  });
  $("#suggestion-query").oninput=input=>{
    clearTimeout(state.suggestTimer);
    state.suggestTimer=setTimeout(()=>loadSuggestions({mode,query:input.target.value.trim(),onPick}),300);
  };
  $("#add-cancel").onclick=()=>{$("#event-inspector").innerHTML=`<div class="inspector-empty"><i data-lucide="panel-right-open"></i><p>Chọn một meme trên timeline để chỉnh sửa.</p></div>`;icons();};
  $("#add-confirm").onclick=async()=>{
    try{
      const data=await api(`/api/events/add?video=${encodeURIComponent(state.selectedVideo)}`,{method:"POST",body:{start:Number($("#add-start").value),asset:picked,mode}});
      toast("Đã chèn meme"); await loadEditor(state.selectedVideo); selectEvent(data.event.id);
    }catch(error){toast(error.message,"error");}
  };
  loadSuggestions({mode,onPick}); icons();
}

async function updateEvent(eventId,patch,reload=true){
  const data=await api(`/api/events/${encodeURIComponent(eventId)}/update?video=${encodeURIComponent(state.selectedVideo)}`,{method:"POST",body:patch});
  Object.assign(state.currentProject.events.find(event=>event.id===eventId),data.event);
  if(reload){toast("Đã lưu thay đổi");await loadEditor(state.selectedVideo);selectEvent(eventId);}
}
async function saveEvent(eventId,patch){
  try{await updateEvent(eventId,patch);}catch(error){toast(error.message,"error");}
}
async function setEventStatus(eventId,action){
  try{await api(`/api/events/${encodeURIComponent(eventId)}/${action}?video=${encodeURIComponent(state.selectedVideo)}`,{method:"POST"});toast(action==="accept"?"Đã chấp nhận":"Đã loại khỏi video");await loadEditor(state.selectedVideo);selectEvent(eventId);}catch(error){toast(error.message,"error");}
}

function renderTranscript(){
  const root=$("#transcript-list"), rows=state.currentProject.transcript||[];
  root.innerHTML=rows.length?rows.map((row,index)=>`<div class="transcript-row" data-segment="${index}"><time>${formatTime(row.start)}</time><p>${escapeHtml(row.text)}</p></div>`).join(""):`<div class="inspector-empty"><p>Chưa có transcript.</p></div>`;
  $$("[data-segment]",root).forEach(node=>node.onclick=()=>{state.player.currentTime=rows[Number(node.dataset.segment)].start;state.player.play();});
}

function onTimeUpdate(){
  const time=state.player.currentTime; $("#playhead-time").textContent=formatTime(time);
  const active=(state.currentProject?.events||[]).filter(item=>item.status!=="rejected"&&time>=item.start&&time<=item.start+item.duration);
  // Tràn màn hình che mọi meme góc, giống bản render
  showOverlay(active.find(item=>item.type==="meme"&&item.mode==="cutaway")||active.find(item=>item.type==="meme"));
  const zoom=active.find(item=>item.type==="zoom");
  $("#player").style.transform=zoom?`scale(${zoom.factor})`:"";
  const rows=state.currentProject?.transcript||[];
  $$(".transcript-row").forEach((node,index)=>node.classList.toggle("active",time>=rows[index].start&&time<=rows[index].end));
}

function showOverlay(event){
  const image=$("#meme-overlay"), clip=$("#meme-overlay-video");
  const node=event&&isVideoAsset(event.asset)?clip:image, other=node===image?clip:image;
  other.style.display="none"; if(!clip.paused&&other===clip)clip.pause();
  if(!event){node.style.display="none";if(node===clip)clip.pause();return;}
  if(node.dataset.src!==event.preview_url){node.src=event.preview_url;node.dataset.src=event.preview_url;}
  node.classList.toggle("cutaway",event.mode==="cutaway");
  if(event.mode==="cutaway"){node.style.cssText="display:block";}
  else{
    const display=state.currentProject?.display||{}, margin=`${(display.margin_ratio??.03)*100}%`;
    const position=event.position||display.position_default||"bottom-right";
    // giống renderer: rộng theo scale nhưng không cao quá max_height_ratio của khung
    node.style.cssText=`display:block;width:${(event.scale||display.scale_default||.3)*100}%;height:auto;max-height:${(display.max_height_ratio??1)*100}%;inset:auto`;
    if(position.includes("top"))node.style.top=margin;else if(position.includes("bottom"))node.style.bottom=margin;else node.style.top="50%";
    if(position.includes("left"))node.style.left=margin;else if(position.includes("right"))node.style.right=margin;else node.style.left="50%";
    node.style.transform=position==="center"?"translate(-50%,-50%)":"none";
    // bị giới hạn chiều cao thì ảnh hẹp hơn khung: bám sát mép như bản render
    node.style.objectPosition=position.includes("right")?"right":position.includes("left")?"left":"center";
  }
  if(node===clip&&clip.paused)clip.play().catch(()=>{});
}

async function renderProject(){
  if(!state.selectedVideo)return;
  const button=$("#render-button"), old=button.innerHTML;button.disabled=true;button.innerHTML='<span class="spinner"></span>Đang render';
  try{await api(`/api/render?video=${encodeURIComponent(state.selectedVideo)}`,{method:"POST"});toast("Render hoàn tất");$("#download-button").classList.remove("disabled");loadDashboard();}catch(error){toast(error.message,"error");}finally{button.disabled=false;button.innerHTML=old;icons();}
}

async function loadLibrary(){
  try{const data=await api("/api/library");state.library=data.items;renderLibrary();}catch(error){toast(error.message,"error");}
}
function renderLibrary(){
  const term=$("#library-search").value.trim().toLowerCase();
  const items=state.library.filter(item=>(state.libraryFilter==="all"||item.type===state.libraryFilter)&&[item.id,item.description,...item.tags,...item.emotion,...item.style].join(" ").toLowerCase().includes(term));
  $("#library-count").textContent=`${items.length} asset`;
  $("#library-grid").innerHTML=items.length?items.map(item=>`<article class="asset-card" data-asset="${attr(item.id)}"><div class="asset-preview">${mediaPreview(item.preview_url,item.type,item.id)}<span class="asset-kind">${escapeHtml(item.type)}</span><span class="asset-safe ${item.safe?"":"unsafe"}"><i data-lucide="${item.safe?"shield-check":"shield-alert"}"></i></span></div><div class="asset-info"><strong>${escapeHtml(item.id)}</strong><div class="asset-tags">${item.tags.slice(0,3).map(tag=>`<span>${escapeHtml(tag)}</span>`).join("")||"<span>chưa có tag</span>"}</div></div></article>`).join(""):`<div class="empty-state"><i data-lucide="image-off"></i><p>Không tìm thấy asset phù hợp.</p></div>`;
  $$("[data-asset]").forEach(card=>card.onclick=()=>openMetadata(card.dataset.asset)); icons();
}
function openMetadata(id){
  const item=state.library.find(row=>row.id===id);if(!item)return;
  $("#meta-id").value=item.id;$("#meta-description").value=item.description;$("#meta-tags").value=item.tags.join(", ");$("#meta-emotion").value=item.emotion.join(", ");$("#meta-style").value=item.style.join(", ");$("#meta-intensity").value=item.intensity;$("#meta-quality").value=item.quality;$("#meta-safe").checked=item.safe;
  $("#intensity-value").textContent=`${Math.round(item.intensity*100)}%`;$("#quality-value").textContent=`${Math.round(item.quality*100)}%`;
  const source=$("#meta-source");source.classList.toggle("hidden",!item.source_url);source.textContent=item.source_url?`Nguồn: ${item.source_url} · ${item.license_note||"Hãy tự xác minh quyền sử dụng trước khi xuất bản."}`:"";
  $("#save-metadata").classList.toggle("hidden",item.type==="audio");
  $("#dialog-preview").innerHTML=mediaPreview(item.preview_url,item.type,item.id);$("#metadata-dialog").showModal();icons();
}
async function installPopularLibrary(){
  const button=$("#popular-library-button"),old=button.innerHTML;
  button.disabled=true;button.innerHTML='<span class="spinner"></span>Đang tải 100 meme';
  try{const result=await api("/api/library/popular?limit=100",{method:"POST"});toast(`Kho meme: ${result.installed} tải mới, ${result.reused} dùng lại${result.failed?`, ${result.failed} lỗi`:""}.`,result.failed?"error":"success");await loadLibrary();await loadDashboard();}catch(error){toast(error.message,"error");}finally{button.disabled=false;button.innerHTML=old;icons();}
}
async function installAnimatedLibrary(){
  const button=$("#animated-library-button"),old=button.innerHTML;
  button.disabled=true;button.innerHTML='<span class="spinner"></span>Đang tải 30 GIF';
  try{const result=await api("/api/library/animated?limit=30",{method:"POST"});toast(`Kho GIF: ${result.installed} tải mới, ${result.reused} dùng lại${result.failed?`, ${result.failed} lỗi`:""}.`,result.failed?"error":"success");await loadLibrary();await loadDashboard();}catch(error){toast(error.message,"error");}finally{button.disabled=false;button.innerHTML=old;icons();}
}
async function installSfxLibrary(){
  const button=$("#sfx-library-button"),old=button.innerHTML;
  button.disabled=true;button.innerHTML='<span class="spinner"></span>Đang tải 30 SFX';
  try{const result=await api("/api/library/sfx?limit=30",{method:"POST"});toast(`Kho SFX: ${result.installed} tải mới, ${result.reused} dùng lại${result.failed?`, ${result.failed} lỗi`:""}.`,result.failed?"error":"success");await loadLibrary();await loadDashboard();}catch(error){toast(error.message,"error");}finally{button.disabled=false;button.innerHTML=old;icons();}
}
async function saveMetadata(event){
  event.preventDefault();const id=$("#meta-id").value;
  try{await api(`/api/library/${encodeURIComponent(id)}`,{method:"POST",body:{id,tags:splitList($("#meta-tags").value),emotion:splitList($("#meta-emotion").value),style:splitList($("#meta-style").value),description:$("#meta-description").value,intensity:Number($("#meta-intensity").value),quality:Number($("#meta-quality").value),safe:$("#meta-safe").checked,language:"none"}});$("#metadata-dialog").close();toast("Đã lưu metadata");await loadLibrary();}catch(error){toast(error.message,"error");}
}

function bindEvents(){
  $$(".nav-item[data-view]").forEach(button=>button.onclick=()=>navigate(button.dataset.view));
  $$('[data-go]').forEach(button=>button.onclick=()=>navigate(button.dataset.go));
  $("#mobile-menu").onclick=()=>$("#sidebar").classList.toggle("open");
  $("#refresh-button").onclick=()=>loadDashboard(true);$("#refresh-environment").onclick=()=>loadDashboard(true);
  $("#start-job").onclick=startJob;$("#render-button").onclick=renderProject;
  $("#add-meme-button").onclick=renderAddForm;
  $("#youtube-download").onclick=startYoutubeDownload;
  $("#youtube-url").onkeydown=event=>{if(event.key==="Enter")startYoutubeDownload();};
  $("#library-search").oninput=renderLibrary;
  $$("[data-filter]").forEach(button=>button.onclick=()=>{state.libraryFilter=button.dataset.filter;$$('[data-filter]').forEach(item=>item.classList.toggle("active",item===button));renderLibrary();});
  $$(".inspector-tabs button").forEach(button=>button.onclick=()=>{$$(".inspector-tabs button").forEach(item=>item.classList.toggle("active",item===button));$("#event-inspector").classList.toggle("hidden",button.dataset.tab!=="event");$("#transcript-panel").classList.toggle("hidden",button.dataset.tab!=="transcript");});
  $("#transcript-search").oninput=event=>{const term=event.target.value.toLowerCase();$$(".transcript-row").forEach(row=>row.classList.toggle("hidden",!row.textContent.toLowerCase().includes(term)));};
  $("#metadata-form").addEventListener("submit",saveMetadata);
  $$(".dialog-close").forEach(button=>button.onclick=()=>$("#metadata-dialog").close());
  for(const id of ["meta-intensity","meta-quality"]){$("#"+id).oninput=event=>$("#"+id.replace("meta-","")+"-value").textContent=`${Math.round(event.target.value*100)}%`;}
}

document.addEventListener("DOMContentLoaded",async()=>{
  icons();bindEvents();setupUploads();
  state.selectedVideo=new URLSearchParams(location.search).get("video")||localStorage.getItem("automeme.lastVideo");
  const initial=location.hash.slice(1);navigate(labels[initial]?initial:"home");
  await loadDashboard();
});
