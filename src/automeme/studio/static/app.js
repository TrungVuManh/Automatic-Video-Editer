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
};

const state = {
  dashboard:null, selectedVideo:null, selectedProfile:"default", currentProject:null,
  selectedEvent:null, library:[], libraryFilter:"all", player:null, wave:null, regions:null,
  poller:null,
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
  bindProjectCards(); renderProfiles(data.profiles); renderEnvironment(data.environment); updateJob(data.job); icons();
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

function updateJob(job){
  if(!job)return;
  $("#job-title").textContent=job.status==="completed"?"Video đã sẵn sàng":job.status==="failed"?"Pipeline cần chú ý":job.video;
  $("#job-message span").textContent=job.error||job.message;
  $("#job-message").classList.toggle("error",job.status==="failed");
  $$("#pipeline-steps [data-stage]").forEach(row=>{
    row.classList.toggle("done",job.completed_stages.includes(row.dataset.stage));
    row.classList.toggle("running",job.status==="running"&&job.stage===row.dataset.stage);
  });
  if(job.status==="running"||job.status==="queued") beginPolling();
  if(job.status==="completed"){
    clearInterval(state.poller);state.poller=null;loadDashboard();
    toast("Pipeline hoàn tất — mở Biên tập để duyệt timeline.");
  }
  if(job.status==="failed"){clearInterval(state.poller);state.poller=null;}
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
  return `<img src="${attr(url)}" alt="${attr(alt)}" loading="lazy">`;
}

function renderTimeline(){
  const root=$("#timeline-list"), events=state.currentProject.events;
  root.innerHTML=events.map(event=>`<button class="event-chip ${event.status==="rejected"?"rejected":""}" data-event="${attr(event.id)}">${mediaPreview(event.preview_url,event.asset.match(/\.(mp4|webm|mov)$/i)?"video":"image",event.id)}<span><strong>${escapeHtml(event.query||event.id)}</strong><small>${formatTime(event.start)} · ${event.duration.toFixed(1)}s · ${escapeHtml(event.status)}</small></span></button>`).join("");
  $$("[data-event]",root).forEach(button=>button.onclick=()=>selectEvent(button.dataset.event));
  if(window.Sortable) new window.Sortable(root,{animation:160,direction:"horizontal",onEnd:()=>toast("Thứ tự hiển thị được quyết định bởi timestamp trên waveform.")});
}

function setupWaveform(){
  if(state.wave){state.wave.destroy();state.wave=null;}
  const video=$("#player");
  state.regions=RegionsPlugin.create();
  state.wave=WaveSurfer.create({container:"#waveform",media:video,url:state.currentProject.video_url,height:62,waveColor:"#495466",progressColor:"#9c6afb",cursorColor:"#ffffff",cursorWidth:1,barWidth:2,barGap:2,barRadius:2,normalize:true,plugins:[state.regions,TimelinePlugin.create({container:"#wave-timeline",height:16,timeInterval:.5,primaryLabelInterval:5,style:{fontSize:"8px",color:"#7d8797"}})]});
  state.wave.on("ready",()=>{
    state.currentProject.events.forEach(event=>state.regions.addRegion({id:event.id,start:event.start,end:event.start+event.duration,color:event.status==="rejected"?"rgba(125,135,151,.18)":"rgba(139,92,246,.32)",drag:true,resize:true}));
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

function renderEventInspector(){
  const event=state.selectedEvent, assets=state.currentProject.assets;
  const type=event.asset.match(/\.(mp4|webm|mov)$/i)?"video":"image";
  $("#event-inspector").innerHTML=`<div class="event-form"><div class="event-preview">${mediaPreview(event.preview_url,type,event.id)}</div><label><span>Meme thay thế</span><select id="event-asset">${assets.map(asset=>`<option value="${attr(asset)}" ${asset===event.asset?"selected":""}>${escapeHtml(asset.split("/").pop())}</option>`).join("")}</select></label><div class="form-grid"><label><span>Bắt đầu (giây)</span><input id="event-start" type="number" min="0" step="0.05" value="${event.start}"></label><label><span>Thời lượng</span><input id="event-duration" type="number" min="0.1" step="0.05" value="${event.duration}"></label></div><div class="form-grid"><label><span>Vị trí</span><select id="event-position">${["top-left","top-right","bottom-left","bottom-right","center"].map(value=>`<option ${value===(event.position||"bottom-right")?"selected":""}>${value}</option>`).join("")}</select></label><label><span>Tỉ lệ</span><input id="event-scale" type="number" min="0.05" max="1" step="0.05" value="${event.scale||.3}"></label></div><button class="button primary wide" id="save-event"><i data-lucide="save"></i>Lưu thay đổi</button><div class="event-actions"><button class="button accept" id="accept-event"><i data-lucide="check"></i>Chấp nhận</button><button class="button reject" id="reject-event"><i data-lucide="x"></i>Từ chối</button></div></div>`;
  $("#save-event").onclick=()=>updateEvent(event.id,{asset:$("#event-asset").value,start:Number($("#event-start").value),duration:Number($("#event-duration").value),position:$("#event-position").value,scale:Number($("#event-scale").value)});
  $("#accept-event").onclick=()=>setEventStatus(event.id,"accept");
  $("#reject-event").onclick=()=>setEventStatus(event.id,"reject"); icons();
}

async function updateEvent(eventId,patch,reload=true){
  const data=await api(`/api/events/${encodeURIComponent(eventId)}/update?video=${encodeURIComponent(state.selectedVideo)}`,{method:"POST",body:patch});
  Object.assign(state.currentProject.events.find(event=>event.id===eventId),data.event);
  if(reload){toast("Đã lưu thay đổi");await loadEditor(state.selectedVideo);selectEvent(eventId);}
}
async function setEventStatus(eventId,action){
  try{await api(`/api/events/${encodeURIComponent(eventId)}/${action}?video=${encodeURIComponent(state.selectedVideo)}`,{method:"POST"});toast(action==="accept"?"Đã chấp nhận meme":"Đã loại meme");await loadEditor(state.selectedVideo);selectEvent(eventId);}catch(error){toast(error.message,"error");}
}

function renderTranscript(){
  const root=$("#transcript-list"), rows=state.currentProject.transcript||[];
  root.innerHTML=rows.length?rows.map((row,index)=>`<div class="transcript-row" data-segment="${index}"><time>${formatTime(row.start)}</time><p>${escapeHtml(row.text)}</p></div>`).join(""):`<div class="inspector-empty"><p>Chưa có transcript.</p></div>`;
  $$("[data-segment]",root).forEach(node=>node.onclick=()=>{state.player.currentTime=rows[Number(node.dataset.segment)].start;state.player.play();});
}

function onTimeUpdate(){
  const time=state.player.currentTime; $("#playhead-time").textContent=formatTime(time);
  const event=state.currentProject?.events.find(item=>item.status!=="rejected"&&time>=item.start&&time<=item.start+item.duration);
  const overlay=$("#meme-overlay");
  if(!event){overlay.style.display="none";} else if(!event.asset.match(/\.(mp4|webm|mov)$/i)){
    overlay.src=event.preview_url;overlay.style.display="block";const scale=event.scale||.3;overlay.style.width=`${scale*100}%`;overlay.style.height="auto";
    const margin="3%",position=event.position||"bottom-right";overlay.style.inset="auto";
    if(position.includes("top"))overlay.style.top=margin;else if(position.includes("bottom"))overlay.style.bottom=margin;else overlay.style.top="50%";
    if(position.includes("left"))overlay.style.left=margin;else if(position.includes("right"))overlay.style.right=margin;else overlay.style.left="50%";
    overlay.style.transform=position==="center"?"translate(-50%,-50%)":"none";
  }
  const rows=state.currentProject?.transcript||[];
  $$(".transcript-row").forEach((node,index)=>node.classList.toggle("active",time>=rows[index].start&&time<=rows[index].end));
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
  $("#dialog-preview").innerHTML=mediaPreview(item.preview_url,item.type,item.id);$("#metadata-dialog").showModal();icons();
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
