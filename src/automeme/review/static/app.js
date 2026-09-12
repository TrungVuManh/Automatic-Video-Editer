const token = document.querySelector('meta[name="automeme-token"]').content;
const video = document.querySelector('#video');
const overlay = document.querySelector('#meme-preview');
const videoOverlay = document.querySelector('#meme-video-preview');
const eventsRoot = document.querySelector('#events');
const transcriptRoot = document.querySelector('#transcript');
const messages = document.querySelector('#messages');
const saveState = document.querySelector('#save-state');
let state = null;
let selectedEvent = null;

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { 'X-Automeme-Token': token, 'Content-Type': 'application/json', ...(options.headers || {}) },
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
  return payload;
}

function setMessage(text, kind = 'success') {
  messages.replaceChildren();
  if (!text) return;
  const node = document.createElement('div');
  node.className = `message ${kind}`;
  node.textContent = text;
  messages.append(node);
}

function time(value) {
  const minutes = Math.floor(value / 60);
  const seconds = value - minutes * 60;
  return `${String(minutes).padStart(2, '0')}:${seconds.toFixed(2).padStart(5, '0')}`;
}

async function loadState() {
  saveState.textContent = 'Đang tải…';
  saveState.className = 'badge neutral';
  try {
    state = await api('/api/state');
    document.querySelector('#video-name').textContent = state.video;
    document.querySelector('#event-count').textContent = `${state.active_count}/${state.events.length} đang bật`;
    if (!video.src) video.src = state.video_url;
    renderEvents();
    renderTranscript();
    renderMessages();
    saveState.textContent = 'Timeline đã đồng bộ';
    saveState.className = 'badge';
  } catch (error) {
    setMessage(error.message, 'error');
    saveState.textContent = 'Không tải được';
  }
}

function renderMessages() {
  messages.replaceChildren();
  for (const text of state.errors) appendMessage(text, 'error');
  for (const text of state.warnings) appendMessage(text, 'warning');
}

function appendMessage(text, kind) {
  const node = document.createElement('div');
  node.className = `message ${kind}`;
  node.textContent = text;
  messages.append(node);
}

function renderEvents() {
  eventsRoot.replaceChildren();
  if (!state.events.length) {
    const empty = document.createElement('p');
    empty.className = 'empty';
    empty.textContent = 'Timeline chưa có meme.';
    eventsRoot.append(empty);
    return;
  }
  state.events.forEach((event, index) => {
    const card = document.querySelector('#event-template').content.firstElementChild.cloneNode(true);
    card.dataset.id = event.id;
    card.classList.toggle('rejected', event.status === 'rejected');
    card.querySelector('.event-index').textContent = `#${index + 1} · ${event.id}`;
    card.querySelector('.event-time').textContent = time(event.start);
    const badge = card.querySelector('.event-status');
    badge.textContent = event.status;
    badge.className = `event-status badge ${event.status}`;
    const media = document.createElement(isVideoAsset(event.asset) ? 'video' : 'img');
    media.src = event.preview_url;
    media.alt = 'Meme';
    if (media.tagName === 'VIDEO') { media.controls = true; media.muted = true; media.loop = true; }
    card.querySelector('.event-media').append(media);
    card.querySelector('.event-reason').textContent = event.reason || 'Không có ghi chú.';
    card.querySelector('.event-query').textContent = event.query ? `Query: ${event.query}` : '';
    card.querySelector('.start').value = event.start;
    card.querySelector('.duration').value = event.duration;
    card.querySelector('.position').value = event.position || '';
    card.querySelector('.scale').value = event.scale ?? '';
    const asset = card.querySelector('.asset');
    const options = new Set([event.asset, ...state.assets]);
    for (const path of options) {
      const option = document.createElement('option');
      option.value = path;
      option.textContent = path;
      option.selected = path === event.asset;
      asset.append(option);
    }
    card.querySelector('.event-summary').addEventListener('click', () => {
      card.classList.toggle('open');
      selectedEvent = event.id;
      video.currentTime = event.start;
      updateOverlay();
    });
    card.querySelector('.accept').addEventListener('click', () => mutate(event.id, 'accept'));
    card.querySelector('.reject').addEventListener('click', () => mutate(event.id, 'reject'));
    card.querySelector('.save').addEventListener('click', () => saveEvent(card, event.id));
    eventsRoot.append(card);
  });
}

async function mutate(id, action) {
  try {
    await api(`/api/events/${encodeURIComponent(id)}/${action}`, { method: 'POST' });
    await loadState();
    setMessage(action === 'accept' ? 'Đã accept meme.' : 'Đã reject meme.');
  } catch (error) { setMessage(error.message, 'error'); }
}

async function saveEvent(card, id) {
  const body = {
    start: Number(card.querySelector('.start').value),
    duration: Number(card.querySelector('.duration').value),
    asset: card.querySelector('.asset').value,
    position: card.querySelector('.position').value || null,
    scale: card.querySelector('.scale').value ? Number(card.querySelector('.scale').value) : null,
  };
  try {
    await api(`/api/events/${encodeURIComponent(id)}/update`, { method: 'POST', body: JSON.stringify(body) });
    await loadState();
    setMessage('Đã lưu chỉnh sửa timeline.');
  } catch (error) { setMessage(error.message, 'error'); }
}

function renderTranscript() {
  transcriptRoot.replaceChildren();
  if (!state.transcript.length) {
    const empty = document.createElement('p');
    empty.className = 'empty';
    empty.textContent = 'Chưa có transcript để hiển thị.';
    transcriptRoot.append(empty);
    return;
  }
  for (const segment of state.transcript) {
    const row = document.createElement('button');
    row.className = 'segment';
    row.type = 'button';
    const stamp = document.createElement('time');
    stamp.textContent = time(Number(segment.start || 0));
    const text = document.createElement('span');
    text.textContent = segment.text || '';
    row.append(stamp, text);
    row.addEventListener('click', () => { video.currentTime = Number(segment.start || 0); video.play(); });
    transcriptRoot.append(row);
  }
}

function updateOverlay() {
  if (!state) return;
  const current = state.events.find((event) =>
    event.status !== 'rejected' && video.currentTime >= event.start && video.currentTime <= event.start + event.duration
  );
  if (!current) {
    overlay.className = '';
    overlay.removeAttribute('src');
    videoOverlay.className = '';
    videoOverlay.pause();
    videoOverlay.removeAttribute('src');
    return;
  }
  const selectedOverlay = isVideoAsset(current.asset) ? videoOverlay : overlay;
  const hiddenOverlay = selectedOverlay === overlay ? videoOverlay : overlay;
  hiddenOverlay.className = '';
  if (hiddenOverlay === videoOverlay) hiddenOverlay.pause();
  if (selectedEvent !== current.id || !selectedOverlay.src) selectedOverlay.src = current.preview_url;
  selectedEvent = current.id;
  selectedOverlay.className = `visible ${current.position || 'bottom-right'}`;
  selectedOverlay.style.width = `${(current.scale ?? 0.30) * 100}%`;
  if (selectedOverlay === videoOverlay) selectedOverlay.play().catch(() => {});
}

function isVideoAsset(asset) { return /\.(mp4|mov|mkv|webm)$/i.test(asset); }

video.addEventListener('timeupdate', updateOverlay);
document.querySelector('#reload-button').addEventListener('click', loadState);
document.querySelector('#render-button').addEventListener('click', async (event) => {
  event.currentTarget.disabled = true;
  setMessage('Đang render, vui lòng chờ…', 'warning');
  try {
    const result = await api('/api/render', { method: 'POST' });
    setMessage(`Render xong: ${result.output}`);
  } catch (error) { setMessage(error.message, 'error'); }
  finally { event.currentTarget.disabled = false; }
});

loadState();
