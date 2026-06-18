// ── Arix Integrations: Gmail, Drive, Plugins, TTS, Vision ─────────────────────

// ─────────────────────────────── TTS ────────────────────────────────────────
let _ttsEnabled = false;
let _ttsSpeaking = false;

function toggleTTS() {
  _ttsEnabled = !_ttsEnabled;
  const btn = document.getElementById('tts-btn');
  if (btn) {
    btn.classList.toggle('active', _ttsEnabled);
    btn.title = _ttsEnabled ? 'Speak responses aloud (ON)' : 'Speak responses aloud';
  }
  if (!_ttsEnabled && window.speechSynthesis) {
    window.speechSynthesis.cancel();
    _ttsSpeaking = false;
  }
  if (typeof toast === 'function') {
    toast(_ttsEnabled ? '🔊 Voice responses ON' : '🔇 Voice responses OFF', 'info');
  }
}

function speakText(text) {
  if (!_ttsEnabled) return;
  if (!window.speechSynthesis) return;
  const cleaned = text
    .replace(/```[\s\S]*?```/g, 'code block')
    .replace(/`[^`]+`/g, '')
    .replace(/\*\*([^*]+)\*\*/g, '$1')
    .replace(/\*([^*]+)\*/g, '$1')
    .replace(/#+\s/g, '')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/https?:\/\/\S+/g, 'link')
    .replace(/[_~|>]/g, '')
    .trim()
    .slice(0, 600);
  if (!cleaned) return;
  window.speechSynthesis.cancel();
  const utt = new SpeechSynthesisUtterance(cleaned);
  utt.rate = 1.05;
  utt.pitch = 1;
  const voices = window.speechSynthesis.getVoices();
  const preferred = voices.find(v => v.name.includes('Google') && v.lang.startsWith('en'))
    || voices.find(v => v.lang.startsWith('en'));
  if (preferred) utt.voice = preferred;
  utt.onstart = () => { _ttsSpeaking = true; };
  utt.onend = () => { _ttsSpeaking = false; };
  window.speechSynthesis.speak(utt);
}

// Hook TTS into incoming assistant messages
document.addEventListener('arix:assistant-message', (e) => {
  if (_ttsEnabled && e.detail && e.detail.text) {
    speakText(e.detail.text);
  }
});

// ─────────────────────────────── Vision ─────────────────────────────────────
async function triggerVisionCapture() {
  const btn = document.getElementById('vision-btn');
  const inp = document.getElementById('cmd-input');

  const question = (inp && inp.value.trim()) || 'Describe what you see on this screen in detail.';
  if (btn) { btn.disabled = true; btn.style.opacity = '0.5'; }
  if (typeof toast === 'function') toast('👁 Capturing screen…', 'info');

  try {
    // 1. Add user message to chat
    if (typeof addUserMsg === 'function') addUserMsg('👁 ' + question);
    if (inp) inp.value = '';

    // 2. Create assistant thinking bubble
    const bubble = typeof createAssistantBubble === 'function'
      ? createAssistantBubble(null, 'Analyzing screenshot…')
      : null;

    // 3. Capture the page using html2canvas
    let imageB64 = null;
    if (typeof html2canvas !== 'undefined') {
      try {
        const canvas = await html2canvas(document.body, {
          useCORS: true,
          allowTaint: true,
          scale: 0.6,
          logging: false,
          ignoreElements: el => el.id === 'sfx-canvas',
        });
        imageB64 = canvas.toDataURL('image/jpeg', 0.7).split(',')[1];
      } catch (e) {
        console.warn('html2canvas failed:', e);
      }
    }

    // 4. Call the vision API
    const payload = { question };
    if (imageB64) { payload.image_b64 = imageB64; payload.media_type = 'image/jpeg'; }

    const res = await fetch('/api/vision/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();

    // 5. Show result in the bubble
    if (bubble && typeof showTextResponse === 'function') {
      if (data.ok) {
        showTextResponse(bubble, data.analysis);
      } else {
        showTextResponse(bubble, `**Vision Error:** ${data.error}`);
      }
    } else if (typeof toast === 'function') {
      toast(data.ok ? '👁 ' + data.analysis.slice(0, 100) : '❌ ' + data.error, data.ok ? 'info' : 'error');
    }

  } catch (e) {
    if (typeof toast === 'function') toast('👁 Vision failed: ' + e.message, 'error');
  } finally {
    if (btn) { btn.disabled = false; btn.style.opacity = ''; }
  }
}

// ─────────────────────────────── Gmail ──────────────────────────────────────
async function loadGmail() {
  try {
    const res = await fetch('/api/gmail/status');
    const data = await res.json();
    const badge = document.getElementById('gmail-status-badge');
    const notConnected = document.getElementById('gmail-not-connected');
    const connected = document.getElementById('gmail-connected');

    if (data.configured) {
      if (badge) { badge.textContent = '🟢 Connected'; badge.className = 'intg-status-badge connected'; }
      if (notConnected) notConnected.style.display = 'none';
      if (connected) connected.style.display = 'block';
      await loadGmailEmails();
    } else {
      if (badge) { badge.textContent = '⚪ Not connected'; badge.className = 'intg-status-badge disconnected'; }
      if (notConnected) notConnected.style.display = 'block';
      if (connected) connected.style.display = 'none';
    }
  } catch (e) {
    console.error('Gmail status error:', e);
  }
}

async function loadGmailEmails() {
  const sel = document.getElementById('gmail-label-sel');
  const label = sel ? sel.value : 'INBOX';
  const list = document.getElementById('gmail-email-list');
  if (!list) return;
  list.innerHTML = '<div class="panel-empty">Loading…</div>';

  try {
    const res = await fetch(`/api/gmail/emails?label=${encodeURIComponent(label)}&max_results=15`);
    const data = await res.json();
    if (!data.ok) {
      list.innerHTML = `<div class="panel-empty" style="color:var(--muted)">${data.error || 'Error loading emails'}</div>`;
      return;
    }
    const emails = data.emails || [];
    if (!emails.length) {
      list.innerHTML = '<div class="panel-empty">No emails found.</div>';
      return;
    }
    const unreadCount = emails.filter(e => e.unread).length;
    const badge = document.getElementById('badge-gmail');
    if (badge && unreadCount > 0) {
      badge.textContent = unreadCount;
      badge.style.display = 'inline-flex';
    }
    list.innerHTML = emails.map(email => `
      <div class="email-item ${email.unread ? 'unread' : ''}" onclick="viewEmail('${email.id}')">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:6px">
          <div class="email-from">${escHtml(email.from)}</div>
          <div class="email-date">${formatEmailDate(email.date)}</div>
        </div>
        <div class="email-subject">${escHtml(email.subject)}</div>
        <div class="email-snippet">${escHtml(email.snippet)}</div>
      </div>
    `).join('');
  } catch (e) {
    list.innerHTML = `<div class="panel-empty" style="color:var(--muted)">Error: ${e.message}</div>`;
  }
}

async function viewEmail(id) {
  const overlay = document.getElementById('email-view-overlay');
  const subject = document.getElementById('email-view-subject');
  const meta = document.getElementById('email-view-meta');
  const body = document.getElementById('email-view-body');
  if (!overlay) return;

  if (subject) subject.textContent = 'Loading…';
  if (meta) meta.textContent = '';
  if (body) body.textContent = '';
  overlay.style.display = 'flex';

  try {
    const res = await fetch(`/api/gmail/emails/${id}`);
    const data = await res.json();
    if (!data.ok) {
      if (body) body.textContent = data.error || 'Failed to load email.';
      return;
    }
    if (subject) subject.textContent = data.subject || '(No subject)';
    if (meta) meta.innerHTML = `
      <b>From:</b> ${escHtml(data.from)}<br>
      <b>To:</b> ${escHtml(data.to)}<br>
      ${data.cc ? `<b>Cc:</b> ${escHtml(data.cc)}<br>` : ''}
      <b>Date:</b> ${escHtml(data.date)}
    `;
    if (body) body.textContent = data.body || '(Empty email body)';
  } catch (e) {
    if (body) body.textContent = `Error: ${e.message}`;
  }
}

function hideEmailView() {
  const el = document.getElementById('email-view-overlay');
  if (el) el.style.display = 'none';
}

async function searchGmail(query) {
  if (!query.trim()) { await loadGmailEmails(); return; }
  const list = document.getElementById('gmail-email-list');
  if (!list) return;
  list.innerHTML = '<div class="panel-empty">Searching…</div>';
  try {
    const res = await fetch(`/api/gmail/search?q=${encodeURIComponent(query)}&max_results=15`);
    const data = await res.json();
    if (!data.ok) { list.innerHTML = `<div class="panel-empty">${data.error}</div>`; return; }
    const emails = data.emails || [];
    if (!emails.length) { list.innerHTML = '<div class="panel-empty">No results.</div>'; return; }
    list.innerHTML = emails.map(email => `
      <div class="email-item ${email.unread ? 'unread' : ''}" onclick="viewEmail('${email.id}')">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:6px">
          <div class="email-from">${escHtml(email.from)}</div>
          <div class="email-date">${formatEmailDate(email.date)}</div>
        </div>
        <div class="email-subject">${escHtml(email.subject)}</div>
        <div class="email-snippet">${escHtml(email.snippet)}</div>
      </div>
    `).join('');
  } catch (e) {
    list.innerHTML = `<div class="panel-empty">Error: ${e.message}</div>`;
  }
}

function showComposeModal() {
  const el = document.getElementById('compose-modal-overlay');
  if (el) el.style.display = 'flex';
  setTimeout(() => document.getElementById('compose-to')?.focus(), 50);
}

function hideComposeModal() {
  const el = document.getElementById('compose-modal-overlay');
  if (el) el.style.display = 'none';
  ['compose-to','compose-cc','compose-subject','compose-body'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = '';
  });
}

async function sendComposedEmail() {
  const to = document.getElementById('compose-to')?.value?.trim();
  const subject = document.getElementById('compose-subject')?.value?.trim();
  const body = document.getElementById('compose-body')?.value?.trim();
  const cc = document.getElementById('compose-cc')?.value?.trim() || '';
  if (!to || !subject || !body) {
    if (typeof toast === 'function') toast('To, subject, and body are required.', 'error');
    return;
  }
  try {
    const res = await fetch('/api/gmail/emails/send', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ to, subject, body, cc }),
    });
    const data = await res.json();
    if (data.ok) {
      if (typeof toast === 'function') toast('✅ Email sent!', 'ok');
      hideComposeModal();
    } else {
      if (typeof toast === 'function') toast('❌ ' + (data.error || 'Send failed'), 'error');
    }
  } catch (e) {
    if (typeof toast === 'function') toast('❌ ' + e.message, 'error');
  }
}

function formatEmailDate(dateStr) {
  if (!dateStr) return '';
  try {
    const d = new Date(dateStr);
    const now = new Date();
    const diff = now - d;
    if (diff < 86400000) return d.toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'});
    if (diff < 7 * 86400000) return d.toLocaleDateString([], {weekday:'short'});
    return d.toLocaleDateString([], {month:'short', day:'numeric'});
  } catch { return dateStr.slice(0, 10); }
}

function escHtml(s) {
  if (!s) return '';
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ─────────────────────────────── Drive ──────────────────────────────────────
let _driveFolderStack = [];

async function loadDrive() {
  try {
    const res = await fetch('/api/drive/status');
    const data = await res.json();
    const badge = document.getElementById('drive-status-badge');
    const notConnected = document.getElementById('drive-not-connected');
    const connected = document.getElementById('drive-connected');
    if (data.configured) {
      if (badge) { badge.textContent = '🟢 Connected'; badge.className = 'intg-status-badge connected'; }
      if (notConnected) notConnected.style.display = 'none';
      if (connected) connected.style.display = 'block';
      await loadDriveFiles('root');
    } else {
      if (badge) { badge.textContent = '⚪ Not connected'; badge.className = 'intg-status-badge disconnected'; }
      if (notConnected) notConnected.style.display = 'block';
      if (connected) connected.style.display = 'none';
    }
  } catch (e) {
    console.error('Drive status error:', e);
  }
}

async function loadDriveFiles(folderId) {
  const list = document.getElementById('drive-file-list');
  if (!list) return;
  list.innerHTML = '<div class="panel-empty">Loading…</div>';
  try {
    const res = await fetch(`/api/drive/files?folder_id=${encodeURIComponent(folderId)}&max_results=30`);
    const data = await res.json();
    if (!data.ok) { list.innerHTML = `<div class="panel-empty">${data.error}</div>`; return; }
    const files = data.files || [];
    if (!files.length) { list.innerHTML = '<div class="panel-empty">Folder is empty.</div>'; return; }
    list.innerHTML = files.map(f => {
      const icon = f.is_folder ? '📁' : getDriveIcon(f.type);
      const meta = f.is_folder ? 'Folder' : (f.size_kb ? `${f.size_kb} KB` : '');
      return `
        <div class="drive-item" onclick="${f.is_folder ? `openDriveFolder('${f.id}','${escHtml(f.name).replace(/'/g,"\\'")}')` : `openDriveFile('${f.id}','${escHtml(f.url).replace(/'/g,"\\'")}')` }">
          <span class="drive-item-icon">${icon}</span>
          <span class="drive-item-name">${escHtml(f.name)}</span>
          <span class="drive-item-meta">${meta}</span>
        </div>
      `;
    }).join('');
  } catch (e) {
    list.innerHTML = `<div class="panel-empty">Error: ${e.message}</div>`;
  }
}

function openDriveFolder(id, name) {
  _driveFolderStack.push({id, name});
  updateDriveBreadcrumb();
  loadDriveFiles(id);
}

function openDriveFile(id, url) {
  if (url) window.open(url, '_blank');
}

function updateDriveBreadcrumb() {
  const bc = document.getElementById('drive-breadcrumb');
  if (!bc) return;
  const parts = [{id:'root', name:'My Drive'}, ..._driveFolderStack];
  bc.innerHTML = parts.map((p, i) =>
    i < parts.length - 1
      ? `<span style="color:var(--accent2);cursor:pointer" onclick="navDriveTo(${i})">${escHtml(p.name)}</span> / `
      : `<span>${escHtml(p.name)}</span>`
  ).join('');
}

function navDriveTo(idx) {
  if (idx === 0) { _driveFolderStack = []; loadDriveFiles('root'); }
  else { _driveFolderStack = _driveFolderStack.slice(0, idx); loadDriveFiles(_driveFolderStack[_driveFolderStack.length-1].id); }
  updateDriveBreadcrumb();
}

async function searchDrive(q) {
  if (!q || !q.trim()) { _driveFolderStack = []; loadDriveFiles('root'); return; }
  const list = document.getElementById('drive-file-list');
  if (!list) return;
  list.innerHTML = '<div class="panel-empty">Searching…</div>';
  try {
    const res = await fetch(`/api/drive/search?q=${encodeURIComponent(q)}&max_results=20`);
    const data = await res.json();
    if (!data.ok) { list.innerHTML = `<div class="panel-empty">${data.error}</div>`; return; }
    const files = data.files || [];
    if (!files.length) { list.innerHTML = `<div class="panel-empty">No files matching "${escHtml(q)}"</div>`; return; }
    list.innerHTML = files.map(f => {
      const icon = getDriveIcon(f.type);
      return `
        <div class="drive-item" onclick="openDriveFile('${f.id}','${escHtml(f.url).replace(/'/g,"\\'")}')">
          <span class="drive-item-icon">${icon}</span>
          <span class="drive-item-name">${escHtml(f.name)}</span>
          <span class="drive-item-meta">${f.size_kb ? f.size_kb + ' KB' : ''}</span>
        </div>
      `;
    }).join('');
  } catch (e) {
    list.innerHTML = `<div class="panel-empty">Error: ${e.message}</div>`;
  }
}

function getDriveIcon(mime) {
  if (!mime) return '📄';
  if (mime.includes('spreadsheet') || mime.includes('xlsx')) return '📊';
  if (mime.includes('document') || mime.includes('word')) return '📝';
  if (mime.includes('presentation') || mime.includes('pptx')) return '📊';
  if (mime.includes('pdf')) return '📕';
  if (mime.includes('image')) return '🖼️';
  if (mime.includes('video')) return '🎬';
  if (mime.includes('audio')) return '🎵';
  if (mime.includes('zip') || mime.includes('archive')) return '🗜️';
  if (mime.includes('folder')) return '📁';
  return '📄';
}

// ─────────────────────────────── Plugins ─────────────────────────────────────
let _editingPluginId = null;

async function loadPlugins() {
  const list = document.getElementById('plugin-list');
  if (!list) return;
  try {
    const res = await fetch('/api/plugins');
    const data = await res.json();
    const plugins = data.plugins || [];
    const badge = document.getElementById('badge-plugins');
    if (badge) { badge.textContent = plugins.length; badge.style.display = plugins.length ? 'inline-flex' : 'none'; }
    if (!plugins.length) {
      list.innerHTML = '<div class="panel-empty">No plugins yet. Create your first plugin above.</div>';
      return;
    }
    list.innerHTML = plugins.map(p => `
      <div class="plugin-item" id="plugin-${p.id}">
        <div class="plugin-item-header">
          <span class="plugin-item-icon">${p.icon || '🔌'}</span>
          <span class="plugin-item-name">${escHtml(p.name)}</span>
          <div class="plugin-enabled-dot ${p.enabled ? 'on' : ''}" title="${p.enabled ? 'Enabled' : 'Disabled'}"></div>
        </div>
        ${p.description ? `<div class="plugin-item-desc">${escHtml(p.description)}</div>` : ''}
        ${p.trigger_phrases && p.trigger_phrases.length ? `<div class="plugin-item-triggers">Triggers: ${p.trigger_phrases.map(t => `"${escHtml(t)}"`).join(', ')}</div>` : ''}
        <div class="plugin-item-btns">
          <button onclick="editPlugin('${p.id}')">✏️ Edit</button>
          <button onclick="testPlugin('${p.id}')">▶ Test</button>
          <button onclick="togglePlugin('${p.id}', ${!p.enabled})">${p.enabled ? '⏸ Disable' : '▶ Enable'}</button>
          <button onclick="deletePlugin('${p.id}')" style="color:var(--red,#f55)">🗑 Delete</button>
        </div>
      </div>
    `).join('');
  } catch (e) {
    list.innerHTML = `<div class="panel-empty">Error loading plugins: ${e.message}</div>`;
  }
}

function showPluginForm(plugin) {
  _editingPluginId = plugin ? plugin.id : null;
  document.getElementById('plugin-form-title').textContent = plugin ? 'Edit Plugin' : 'New Plugin';
  document.getElementById('plg-name').value = plugin?.name || '';
  document.getElementById('plg-desc').value = plugin?.description || '';
  document.getElementById('plg-triggers').value = plugin?.trigger_phrases?.join(', ') || '';
  document.getElementById('plg-url').value = plugin?.action || '';
  document.getElementById('plg-method').value = plugin?.method || 'POST';
  document.getElementById('plg-payload').value = plugin?.payload_template || '';
  document.getElementById('plugin-form').style.display = 'block';
  document.getElementById('plg-name').focus();
}

function hidePluginForm() {
  _editingPluginId = null;
  document.getElementById('plugin-form').style.display = 'none';
}

async function savePlugin() {
  const name = document.getElementById('plg-name').value.trim();
  if (!name) { if (typeof toast === 'function') toast('Plugin name is required', 'error'); return; }
  const triggersRaw = document.getElementById('plg-triggers').value;
  const triggers = triggersRaw.split(',').map(t => t.trim()).filter(Boolean);
  const payload = {
    name,
    description: document.getElementById('plg-desc').value.trim(),
    trigger_phrases: triggers,
    action: document.getElementById('plg-url').value.trim(),
    action_type: 'http',
    method: document.getElementById('plg-method').value,
    payload_template: document.getElementById('plg-payload').value,
  };
  try {
    const url = _editingPluginId ? `/api/plugins/${_editingPluginId}` : '/api/plugins';
    const method = _editingPluginId ? 'PUT' : 'POST';
    const res = await fetch(url, { method, headers: {'Content-Type':'application/json'}, body: JSON.stringify(payload) });
    const data = await res.json();
    if (data.ok) {
      if (typeof toast === 'function') toast(`✅ Plugin "${name}" saved!`, 'ok');
      hidePluginForm();
      await loadPlugins();
    } else {
      if (typeof toast === 'function') toast('❌ ' + (data.detail || data.error || 'Save failed'), 'error');
    }
  } catch (e) {
    if (typeof toast === 'function') toast('❌ ' + e.message, 'error');
  }
}

async function editPlugin(id) {
  try {
    const res = await fetch(`/api/plugins/${id}`);
    const p = await res.json();
    showPluginForm(p);
  } catch (e) {
    if (typeof toast === 'function') toast('Failed to load plugin', 'error');
  }
}

async function testPlugin(id) {
  if (typeof toast === 'function') toast('▶ Testing plugin…', 'info');
  try {
    const res = await fetch(`/api/plugins/${id}/test`, { method: 'POST' });
    const data = await res.json();
    if (data.ok) {
      if (typeof toast === 'function') toast(`✅ Test OK (HTTP ${data.status})`, 'ok');
    } else {
      if (typeof toast === 'function') toast(`❌ Test failed: ${data.error}`, 'error');
    }
  } catch (e) {
    if (typeof toast === 'function') toast('❌ ' + e.message, 'error');
  }
}

async function togglePlugin(id, enabled) {
  try {
    const res = await fetch(`/api/plugins/${id}`, {
      method: 'PUT',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ enabled }),
    });
    const data = await res.json();
    if (data.ok) await loadPlugins();
  } catch (e) {
    if (typeof toast === 'function') toast('❌ ' + e.message, 'error');
  }
}

async function deletePlugin(id) {
  if (!confirm('Delete this plugin?')) return;
  try {
    await fetch(`/api/plugins/${id}`, { method: 'DELETE' });
    await loadPlugins();
    if (typeof toast === 'function') toast('Plugin deleted.', 'info');
  } catch (e) {
    if (typeof toast === 'function') toast('❌ ' + e.message, 'error');
  }
}

// ─────────────────────────── Panel switch hooks ──────────────────────────────
// Hook into the existing switchPanel function to load data when panels open
const _origSwitchPanel = typeof switchPanel !== 'undefined' ? switchPanel : null;
document.addEventListener('DOMContentLoaded', () => {
  // Patch switchPanel to lazy-load integration panels
  const _base = window.switchPanel;
  if (_base) {
    window.switchPanel = function(name) {
      _base(name);
      if (name === 'gmail') loadGmail();
      else if (name === 'drive') loadDrive();
      else if (name === 'plugins') loadPlugins();
    };
  }
});

// ─────────────────────────── Voice auto-send ────────────────────────────────
// Upgrade: if mic transcription ends, auto-send after 1.2 second pause
(function patchVoiceAutoSend() {
  const patchInterval = setInterval(() => {
    if (typeof S === 'undefined' || !S.voice) return;
    clearInterval(patchInterval);
    const origOnResult = null;
    const checkRecognition = setInterval(() => {
      if (!S.voice.recognition) return;
      clearInterval(checkRecognition);
      const originalOnResult = S.voice.recognition.onresult;
      S.voice.recognition.onresult = function(e) {
        if (originalOnResult) originalOnResult.call(this, e);
        setTimeout(() => {
          const inp = document.getElementById('cmd-input');
          if (inp && inp.value.trim() && typeof sendCommand === 'function') {
            sendCommand();
          }
        }, 1200);
      };
    }, 300);
  }, 300);
})();

// ── Notion Panel ─────────────────────────────────────────────────────────────

async function loadNotion() {
  const res = await fetch('/api/notion/status');
  const data = await res.json();
  document.getElementById('notion-setup').style.display = data.configured ? 'none' : 'block';
  if (data.configured) searchNotion('');
}

async function searchNotion(q) {
  document.getElementById('notion-list').innerHTML = '<div class="panel-empty">Loading…</div>';
  const res = await fetch(`/api/notion/search?q=${encodeURIComponent(q)}&limit=20`);
  const data = await res.json();
  const el = document.getElementById('notion-list');
  if (!data.ok) { el.innerHTML = `<div class="panel-empty" style="color:#f87171">${data.error}</div>`; return; }
  if (!data.results.length) { el.innerHTML = '<div class="panel-empty">No pages found.</div>'; return; }
  el.innerHTML = data.results.map(p => `
    <div class="email-item" onclick="openNotionPage('${p.id}','${escJS(p.title)}')" style="cursor:pointer">
      <div style="display:flex;align-items:center;gap:6px">
        <span style="font-size:14px">${p.type==='database'?'🗄️':'📄'}</span>
        <div style="flex:1;min-width:0">
          <div class="email-subject">${esc(p.title)}</div>
          <div class="email-from" style="font-size:10px">${p.edited ? new Date(p.edited).toLocaleDateString() : ''}</div>
        </div>
        <a href="${p.url}" target="_blank" class="panel-btn" style="flex:0;font-size:10px;padding:2px 6px" onclick="event.stopPropagation()">↗</a>
      </div>
    </div>`).join('');
}

async function openNotionPage(pageId, title) {
  const el = document.getElementById('notion-list');
  el.innerHTML = `<div class="panel-empty">Loading "${title}"…</div>`;
  const res = await fetch(`/api/notion/page/${pageId}`);
  const data = await res.json();
  if (!data.ok) { el.innerHTML = `<div class="panel-empty" style="color:#f87171">${data.error}</div>`; return; }
  el.innerHTML = `
    <div style="background:var(--surface);border:1px solid var(--border);border-radius:var(--radius-sm);padding:10px">
      <div style="display:flex;align-items:center;gap:6px;margin-bottom:8px">
        <button class="panel-btn" onclick="searchNotion('')" style="flex:0">← Back</button>
        <strong style="flex:1;font-size:13px;color:var(--text)">${esc(data.title)}</strong>
        <a href="${data.url}" target="_blank" class="panel-btn" style="flex:0;font-size:10px;padding:2px 6px">Open ↗</a>
      </div>
      <pre style="white-space:pre-wrap;font-family:var(--font);font-size:11px;color:var(--text-dim);max-height:300px;overflow-y:auto">${esc(data.content||'(empty page)')}</pre>
    </div>`;
}

function showNotionCreateForm() {
  document.getElementById('notion-create-form').style.display = 'block';
  document.getElementById('notion-new-title').focus();
}

async function createNotionPage() {
  const title = document.getElementById('notion-new-title').value.trim();
  const content = document.getElementById('notion-new-content').value.trim();
  if (!title) return;
  const res = await fetch('/api/notion/page', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({title, content}) });
  const data = await res.json();
  if (data.ok) {
    document.getElementById('notion-create-form').style.display = 'none';
    document.getElementById('notion-new-title').value = '';
    document.getElementById('notion-new-content').value = '';
    searchNotion('');
  } else {
    alert('Error: ' + data.error);
  }
}

// ── Slack Panel ───────────────────────────────────────────────────────────────

let _slackChannels = [];

async function loadSlackChannels() {
  const statusRes = await fetch('/api/slack/status');
  const status = await statusRes.json();
  document.getElementById('slack-setup').style.display = status.configured ? 'none' : 'block';
  if (!status.configured) { document.getElementById('slack-channels-list').innerHTML = ''; return; }

  const res = await fetch('/api/slack/channels?limit=30');
  const data = await res.json();
  const el = document.getElementById('slack-channels-list');
  if (!data.ok) { el.innerHTML = `<div class="panel-empty" style="color:#f87171">${data.error}</div>`; return; }
  _slackChannels = data.channels || [];

  // Populate compose dropdown
  const sel = document.getElementById('slack-compose-channel');
  sel.innerHTML = _slackChannels.map(c => `<option value="${c.id}">#${esc(c.name)}</option>`).join('');

  el.innerHTML = _slackChannels.map(c => `
    <div class="email-item" onclick="loadSlackMessages('${c.id}','${escJS(c.name)}')" style="cursor:pointer">
      <div style="display:flex;align-items:center;gap:6px">
        <span style="font-size:13px">${c.is_private?'🔒':'#'}</span>
        <div style="flex:1">
          <div class="email-subject">#${esc(c.name)}</div>
          <div class="email-from">${c.members} members${c.topic?' · '+esc(c.topic.slice(0,40)):''}</div>
        </div>
      </div>
    </div>`).join('');
}

async function loadSlackMessages(channelId, channelName) {
  const el = document.getElementById('slack-messages-list');
  el.innerHTML = `<div style="display:flex;align-items:center;gap:6px;margin-bottom:8px"><button class="panel-btn" onclick="loadSlackChannels()" style="flex:0">← Back</button><strong style="font-size:12px;color:var(--text)">#${esc(channelName)}</strong></div><div class="panel-empty">Loading…</div>`;
  document.getElementById('slack-channels-list').innerHTML = '';
  const res = await fetch(`/api/slack/messages?channel=${channelId}&limit=20`);
  const data = await res.json();
  if (!data.ok) { el.innerHTML += `<div class="panel-empty" style="color:#f87171">${data.error}</div>`; return; }
  const msgs = (data.messages||[]).reverse();
  const msgsHtml = msgs.map(m => `
    <div style="padding:6px 0;border-bottom:1px solid var(--border-subtle)">
      <div style="font-size:11px;color:var(--accent);margin-bottom:2px">${esc(m.user)}</div>
      <div style="font-size:12px;color:var(--text)">${esc(m.text)}</div>
    </div>`).join('') || '<div class="panel-empty">No messages.</div>';
  el.innerHTML = `<div style="display:flex;align-items:center;gap:6px;margin-bottom:8px"><button class="panel-btn" onclick="loadSlackChannels();document.getElementById('slack-messages-list').innerHTML=''" style="flex:0">← Back</button><strong style="font-size:12px;color:var(--text)">#${esc(channelName)}</strong></div>${msgsHtml}`;
}

async function searchSlack(q) {
  if (!q.trim()) return;
  document.getElementById('slack-messages-list').innerHTML = '<div class="panel-empty">Searching…</div>';
  document.getElementById('slack-channels-list').innerHTML = '';
  const res = await fetch(`/api/slack/search?q=${encodeURIComponent(q)}&count=15`);
  const data = await res.json();
  const el = document.getElementById('slack-messages-list');
  if (!data.ok) { el.innerHTML = `<div class="panel-empty" style="color:#f87171">${data.error}</div>`; return; }
  const results = data.results || [];
  el.innerHTML = `<div style="display:flex;align-items:center;gap:6px;margin-bottom:8px"><button class="panel-btn" onclick="loadSlackChannels();document.getElementById('slack-messages-list').innerHTML=''" style="flex:0">← Back</button><strong style="font-size:12px;color:var(--text)">Results for "${esc(q)}"</strong></div>`
    + (results.map(r => `<div style="padding:6px 0;border-bottom:1px solid var(--border-subtle)"><div style="font-size:10px;color:var(--accent)">#${esc(r.channel)} · ${esc(r.user)}</div><div style="font-size:12px;color:var(--text)">${esc(r.text)}</div></div>`).join('') || '<div class="panel-empty">No results.</div>');
}

function showSlackCompose() {
  document.getElementById('slack-compose').style.display = 'block';
  document.getElementById('slack-compose-text').focus();
}

async function sendSlackMessage() {
  const channel = document.getElementById('slack-compose-channel').value;
  const text = document.getElementById('slack-compose-text').value.trim();
  if (!channel || !text) return;
  const res = await fetch('/api/slack/send', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({channel, text}) });
  const data = await res.json();
  if (data.ok) {
    document.getElementById('slack-compose').style.display = 'none';
    document.getElementById('slack-compose-text').value = '';
  } else {
    alert('Error: ' + data.error);
  }
}

// ── Trello Panel ──────────────────────────────────────────────────────────────

let _trelloCurrentBoard = null;
let _trelloLists = [];

async function loadTrelloBoards() {
  const statusRes = await fetch('/api/trello/status');
  const status = await statusRes.json();
  document.getElementById('trello-setup').style.display = status.configured ? 'none' : 'block';
  if (!status.configured) { document.getElementById('trello-boards-list').innerHTML = ''; return; }

  const res = await fetch('/api/trello/boards');
  const data = await res.json();
  const el = document.getElementById('trello-boards-list');
  if (!data.ok) { el.innerHTML = `<div class="panel-empty" style="color:#f87171">${data.error}</div>`; return; }
  el.innerHTML = (data.boards||[]).map(b => `
    <div class="email-item" onclick="loadTrelloBoard('${b.id}','${escJS(b.name)}')" style="cursor:pointer">
      <div class="email-subject">📋 ${esc(b.name)}</div>
      ${b.desc ? `<div class="email-from">${esc(b.desc.slice(0,60))}</div>` : ''}
    </div>`).join('') || '<div class="panel-empty">No boards found.</div>';
}

async function loadTrelloBoard(boardId, boardName) {
  _trelloCurrentBoard = {id: boardId, name: boardName};
  document.getElementById('trello-boards-list').style.display = 'none';
  document.getElementById('trello-board-detail').style.display = 'block';
  document.getElementById('trello-board-name').textContent = boardName;
  document.getElementById('trello-cards-list').innerHTML = '<div class="panel-empty">Loading…</div>';

  const [listsRes, cardsRes] = await Promise.all([
    fetch(`/api/trello/boards/${boardId}/lists`),
    fetch(`/api/trello/boards/${boardId}/cards`)
  ]);
  const listsData = await listsRes.json();
  const cardsData = await cardsRes.json();

  _trelloLists = listsData.ok ? listsData.lists : [];
  const listMap = Object.fromEntries(_trelloLists.map(l => [l.id, l.name]));

  // Populate add-card list dropdown
  const sel = document.getElementById('trello-card-list');
  sel.innerHTML = _trelloLists.map(l => `<option value="${l.id}">${esc(l.name)}</option>`).join('');

  if (!cardsData.ok) { document.getElementById('trello-cards-list').innerHTML = `<div class="panel-empty" style="color:#f87171">${cardsData.error}</div>`; return; }
  const byList = {};
  (cardsData.cards||[]).forEach(c => { (byList[c.list_id] = byList[c.list_id]||[]).push(c); });
  document.getElementById('trello-cards-list').innerHTML = _trelloLists.map(l => `
    <div style="margin-bottom:10px">
      <div style="font-size:11px;font-weight:700;color:var(--accent);margin-bottom:4px;text-transform:uppercase">${esc(l.name)}</div>
      ${(byList[l.id]||[]).map(c=>`<div class="email-item" style="cursor:default;margin-bottom:4px"><div class="email-subject">${esc(c.name)}</div>${c.due?`<div class="email-from">Due: ${new Date(c.due).toLocaleDateString()}</div>`:''}${c.labels.length?`<div class="email-from">${c.labels.map(l=>`<span style="background:#3b82f6;color:#fff;border-radius:3px;padding:0 4px;font-size:9px">${esc(l)}</span>`).join(' ')}</div>`:''}</div>`).join('')}
      ${(byList[l.id]||[]).length===0?'<div class="panel-empty" style="font-size:11px;padding:4px 0">No cards</div>':''}
    </div>`).join('');
}

function showTrelloBoards() {
  document.getElementById('trello-boards-list').style.display = '';
  document.getElementById('trello-board-detail').style.display = 'none';
  document.getElementById('trello-add-card-form').style.display = 'none';
}

function showTrelloAddCard() {
  document.getElementById('trello-add-card-form').style.display = 'block';
  document.getElementById('trello-card-name').focus();
}

async function addTrelloCard() {
  const name = document.getElementById('trello-card-name').value.trim();
  const desc = document.getElementById('trello-card-desc').value.trim();
  const listId = document.getElementById('trello-card-list').value;
  if (!name || !listId) return;
  const res = await fetch('/api/trello/cards', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({list_id:listId, name, desc}) });
  const data = await res.json();
  if (data.ok) {
    document.getElementById('trello-add-card-form').style.display = 'none';
    document.getElementById('trello-card-name').value = '';
    document.getElementById('trello-card-desc').value = '';
    if (_trelloCurrentBoard) loadTrelloBoard(_trelloCurrentBoard.id, _trelloCurrentBoard.name);
  } else { alert('Error: ' + data.error); }
}

// ── Spotify Panel ─────────────────────────────────────────────────────────────

async function loadSpotifyNowPlaying() {
  const statusRes = await fetch('/api/spotify/status');
  const status = await statusRes.json();
  document.getElementById('spotify-setup').style.display = status.configured ? 'none' : 'block';
  if (!status.configured) return;
  const res = await fetch('/api/spotify/current');
  const data = await res.json();
  const npEl = document.getElementById('spotify-now-playing');
  if (data.ok && data.playing) {
    npEl.style.display = 'block';
    document.getElementById('spotify-track-name').textContent = data.track || '';
    document.getElementById('spotify-track-artist').textContent = data.artist || '';
  } else {
    npEl.style.display = 'none';
  }
}

async function searchSpotify(q) {
  if (!q.trim()) return;
  document.getElementById('spotify-results').innerHTML = '<div class="panel-empty">Searching…</div>';
  const res = await fetch(`/api/spotify/search?q=${encodeURIComponent(q)}&limit=15`);
  const data = await res.json();
  const el = document.getElementById('spotify-results');
  if (!data.ok) { el.innerHTML = `<div class="panel-empty" style="color:#f87171">${data.error}</div>`; return; }
  el.innerHTML = (data.tracks||[]).map(t => `
    <div class="email-item" style="cursor:default">
      <div style="display:flex;align-items:center;gap:8px">
        <span style="font-size:18px">🎵</span>
        <div style="flex:1;min-width:0">
          <div class="email-subject">${esc(t.name)}</div>
          <div class="email-from">${esc(t.artist)} · ${esc(t.album)}</div>
        </div>
        ${t.url?`<a href="${t.url}" target="_blank" class="panel-btn" style="flex:0;font-size:10px;padding:2px 6px">▶ Open</a>`:''}
      </div>
    </div>`).join('') || '<div class="panel-empty">No results.</div>';
}

async function spotifyPlayPause(play) {
  const endpoint = play ? '/api/spotify/play' : '/api/spotify/pause';
  const res = await fetch(endpoint, {method:'POST'});
  const data = await res.json();
  if (!data.ok) alert('Playback control requires SPOTIFY_ACCESS_TOKEN in Secrets.');
  else setTimeout(loadSpotifyNowPlaying, 800);
}

// ── YouTube Panel ─────────────────────────────────────────────────────────────

async function loadYouTube() {
  const statusRes = await fetch('/api/youtube/status');
  const status = await statusRes.json();
  document.getElementById('youtube-setup').style.display = status.configured ? 'none' : 'block';
}

async function searchYouTube(q) {
  if (!q.trim()) return;
  document.getElementById('youtube-results').innerHTML = '<div class="panel-empty">Searching…</div>';
  const res = await fetch(`/api/youtube/search?q=${encodeURIComponent(q)}&max_results=12`);
  const data = await res.json();
  const el = document.getElementById('youtube-results');
  if (!data.ok) { el.innerHTML = `<div class="panel-empty" style="color:#f87171">${data.error}</div>`; return; }
  el.innerHTML = (data.videos||[]).map(v => `
    <div class="email-item" style="cursor:pointer" onclick="window.open('${v.url}','_blank')">
      <div style="display:flex;gap:8px;align-items:flex-start">
        ${v.thumbnail ? `<img src="${v.thumbnail}" style="width:80px;height:45px;border-radius:4px;object-fit:cover;flex-shrink:0">` : '<span style="font-size:24px;flex-shrink:0">▶️</span>'}
        <div style="flex:1;min-width:0">
          <div class="email-subject" style="white-space:normal;line-height:1.3">${esc(v.title)}</div>
          <div class="email-from">${esc(v.channel)} · ${v.published?new Date(v.published).toLocaleDateString():''}</div>
        </div>
      </div>
    </div>`).join('') || '<div class="panel-empty">No videos found.</div>';
}

// ══════════════════════════════════════════════════════════════════════════════
// SkillHub
// ══════════════════════════════════════════════════════════════════════════════

let _allSkills = [];
let _skillCatFilter = '';

async function loadSkillHub() {
  const el = document.getElementById('skillhub-list');
  if (el) el.innerHTML = '<div class="panel-empty">Loading…</div>';
  try {
    const res = await fetch('/api/skillhub');
    const data = await res.json();
    _allSkills = data.skills || [];
    renderSkillCats(data.categories || []);
    renderSkills(_allSkills);
  } catch (e) {
    if (el) el.innerHTML = `<div class="panel-empty" style="color:#f87171">Error loading skills</div>`;
  }
}

function renderSkillCats(cats) {
  const el = document.getElementById('skillhub-cats');
  if (!el) return;
  const all = ['All', ...cats];
  el.innerHTML = all.map(c => `
    <button class="skill-cat-btn${_skillCatFilter === c || (c === 'All' && !_skillCatFilter) ? ' active' : ''}"
      onclick="setSkillCat('${c}')">${c}</button>`).join('');
}

function setSkillCat(cat) {
  _skillCatFilter = cat === 'All' ? '' : cat;
  renderSkillCats(_allSkills.length ? [...new Set(_allSkills.map(s => s.category))] : []);
  const q = (document.getElementById('skillhub-search') || {}).value || '';
  filterSkills(q);
}

function filterSkills(q) {
  let skills = _allSkills;
  if (_skillCatFilter) skills = skills.filter(s => s.category === _skillCatFilter);
  if (q) {
    const lq = q.toLowerCase();
    skills = skills.filter(s =>
      s.name.toLowerCase().includes(lq) ||
      s.description.toLowerCase().includes(lq) ||
      (s.tags || []).some(t => t.includes(lq))
    );
  }
  renderSkills(skills);
}

function renderSkills(skills) {
  const el = document.getElementById('skillhub-list');
  if (!el) return;
  if (!skills.length) { el.innerHTML = '<div class="panel-empty">No skills found.</div>'; return; }
  el.innerHTML = skills.map(s => `
    <div class="skill-card" id="skill-card-${s.id}">
      <div class="skill-card-header">
        <span class="skill-icon">${s.icon}</span>
        <div style="flex:1;min-width:0">
          <div class="skill-name">${esc(s.name)}</div>
          <div class="skill-meta"><span class="skill-cat-tag">${esc(s.category)}</span> · v${esc(s.version)} · by ${esc(s.author)}</div>
        </div>
        <div class="skill-rating">⭐ ${s.rating}</div>
      </div>
      <div class="skill-desc">${esc(s.description)}</div>
      <div class="skill-footer">
        <span class="skill-installs">↓ ${s.installs.toLocaleString()}</span>
        ${s.installed
          ? `<button class="panel-btn skill-uninstall-btn" onclick="uninstallSkill('${s.id}')">Uninstall</button>`
          : `<button class="panel-btn primary skill-install-btn" onclick="installSkill('${s.id}')">Install</button>`}
      </div>
    </div>`).join('');
}

async function installSkill(id) {
  const btn = document.querySelector(`#skill-card-${id} .skill-install-btn`);
  if (btn) { btn.disabled = true; btn.textContent = 'Installing…'; }
  try {
    const res = await fetch(`/api/skillhub/${id}/install`, { method: 'POST' });
    const data = await res.json();
    if (data.ok) {
      if (typeof toast === 'function') toast(`✅ "${data.name}" installed as a workflow`, 'ok');
      await loadSkillHub();
    }
  } catch (e) {
    if (typeof toast === 'function') toast('Failed to install skill', 'err');
    if (btn) { btn.disabled = false; btn.textContent = 'Install'; }
  }
}

async function uninstallSkill(id) {
  try {
    const res = await fetch(`/api/skillhub/${id}/uninstall`, { method: 'POST' });
    const data = await res.json();
    if (data.ok) {
      if (typeof toast === 'function') toast('Skill uninstalled', 'info');
      await loadSkillHub();
    }
  } catch (e) {
    if (typeof toast === 'function') toast('Failed to uninstall skill', 'err');
  }
}

// ══════════════════════════════════════════════════════════════════════════════
// Channels (Telegram + Discord)
// ══════════════════════════════════════════════════════════════════════════════

async function loadChannels() {
  try {
    const res = await fetch('/api/channels');
    const data = await res.json();
    const channels = data.channels || [];

    const tg = channels.find(c => c.platform === 'telegram');
    const dc = channels.find(c => c.platform === 'discord');

    updateChannelUI('telegram', tg, data.telegram_configured);
    updateChannelUI('discord', dc, data.discord_configured);
  } catch (e) {
    // silently ignore — channels endpoint may not be needed
  }
}

function updateChannelUI(platform, ch, envConfigured) {
  const prefix = platform === 'telegram' ? 'tg' : 'dc';
  const badge = document.getElementById(`${prefix}-badge`);
  const handle = document.getElementById(`${prefix}-handle`);
  const setup = document.getElementById(`${prefix}-setup`);
  const actions = document.getElementById(`${prefix}-actions`);
  const routedEl = document.getElementById(`${prefix}-routed`);

  if (!badge) return;

  if (ch && ch.connected) {
    badge.textContent = 'Live';
    badge.className = 'channel-badge connected';
    if (handle) handle.textContent = ch.bot_username || 'Connected';
    if (setup) setup.style.display = 'none';
    if (actions) actions.style.display = 'flex';
    if (routedEl) routedEl.textContent = `${ch.messages_routed} messages routed`;
  } else if (ch && ch.enabled && !ch.connected) {
    badge.textContent = ch.error ? 'Error' : 'Connecting…';
    badge.className = `channel-badge ${ch.error ? 'error' : 'connecting'}`;
    if (handle) handle.textContent = ch.error || 'Connecting…';
    if (setup) setup.style.display = 'block';
    if (actions) actions.style.display = 'none';
  } else {
    badge.textContent = envConfigured ? 'Auto' : 'Off';
    badge.className = `channel-badge ${envConfigured ? 'connecting' : 'disconnected'}`;
    if (handle) handle.textContent = envConfigured ? 'Token from env' : 'Not connected';
    if (setup) setup.style.display = envConfigured ? 'none' : 'block';
    if (actions) actions.style.display = envConfigured ? 'flex' : 'none';
  }
}

async function startTelegram() {
  const tokenInput = document.getElementById('tg-token-input');
  const token = (tokenInput && tokenInput.value.trim()) || '';
  try {
    const res = await fetch('/api/channels/telegram/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token }),
    });
    const data = await res.json();
    if (res.ok) {
      if (typeof toast === 'function') toast('✈️ Telegram bot starting…', 'info');
      setTimeout(loadChannels, 2000);
    } else {
      if (typeof toast === 'function') toast(`Telegram error: ${data.detail || 'unknown'}`, 'err');
    }
  } catch (e) {
    if (typeof toast === 'function') toast('Failed to start Telegram', 'err');
  }
}

async function startDiscord() {
  const tokenInput = document.getElementById('dc-token-input');
  const token = (tokenInput && tokenInput.value.trim()) || '';
  try {
    const res = await fetch('/api/channels/discord/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token }),
    });
    const data = await res.json();
    if (res.ok) {
      if (typeof toast === 'function') toast('🎮 Discord bot starting…', 'info');
      setTimeout(loadChannels, 2000);
    } else {
      if (typeof toast === 'function') toast(`Discord error: ${data.detail || 'unknown'}`, 'err');
    }
  } catch (e) {
    if (typeof toast === 'function') toast('Failed to start Discord', 'err');
  }
}

async function stopChannel(name) {
  try {
    await fetch(`/api/channels/${name}/stop`, { method: 'POST' });
    if (typeof toast === 'function') toast(`${name} disconnected`, 'info');
    await loadChannels();
  } catch (e) {
    if (typeof toast === 'function') toast('Failed to stop channel', 'err');
  }
}

// ══════════════════════════════════════════════════════════════════════════════
// Live Canvas
// ══════════════════════════════════════════════════════════════════════════════

let _canvasSSE = null;

function connectCanvasSSE() {
  if (_canvasSSE) return;
  _canvasSSE = new EventSource('/api/canvas/stream');
  _canvasSSE.onmessage = (e) => {
    try {
      const msg = JSON.parse(e.data);
      if (msg.event === 'card') prependCanvasCard(msg.data);
      else if (msg.event === 'delete') removeCanvasCard(msg.id);
      else if (msg.event === 'clear') document.getElementById('canvas-cards') && (document.getElementById('canvas-cards').innerHTML = '<div class="panel-empty">Canvas cleared.</div>');
    } catch (_) {}
  };
  _canvasSSE.onerror = () => {
    _canvasSSE = null;
    setTimeout(connectCanvasSSE, 4000);
  };
}

async function loadCanvas() {
  const el = document.getElementById('canvas-cards');
  if (!el) return;
  try {
    const res = await fetch('/api/canvas');
    const data = await res.json();
    const cards = (data.cards || []).reverse();
    if (!cards.length) {
      el.innerHTML = '<div class="panel-empty">No cards yet. The agent will push content here automatically.</div>';
      return;
    }
    el.innerHTML = cards.map(c => renderCanvasCardHTML(c)).join('');
    el.querySelectorAll('.canvas-card-body.md').forEach(el => {
      if (typeof marked !== 'undefined') el.innerHTML = marked.parse(el.dataset.raw || '');
    });
  } catch (e) {
    if (el) el.innerHTML = '<div class="panel-empty" style="color:#f87171">Failed to load canvas</div>';
  }
  connectCanvasSSE();
}

function renderCanvasCardHTML(c) {
  const typeIcon = { markdown: '📝', research: '🔬', plan: '📋', chart: '📊', code: '💻' }[c.type] || '📝';
  const colorMap = { research: 'var(--accent)', plan: 'var(--warn)', chart: 'var(--success)', code: 'var(--muted)' };
  const borderColor = colorMap[c.type] || 'var(--border)';
  const ts = c.ts ? new Date(c.ts * 1000).toLocaleTimeString() : '';
  const isCode = c.type === 'code';
  return `
    <div class="canvas-card" id="cvs-${c.id}" style="border-left:3px solid ${borderColor}">
      <div class="canvas-card-hdr">
        <span style="font-size:13px">${typeIcon}</span>
        <span class="canvas-card-title">${esc(c.title || c.type)}</span>
        <span class="canvas-card-ts">${ts}</span>
        <button class="canvas-card-del" onclick="deleteCanvasCard('${c.id}')" title="Remove">✕</button>
      </div>
      ${isCode
        ? `<pre class="canvas-card-code"><code>${esc(c.content)}</code></pre>`
        : `<div class="canvas-card-body md" data-raw="${esc(c.content)}"></div>`}
    </div>`;
}

function prependCanvasCard(c) {
  const el = document.getElementById('canvas-cards');
  if (!el) return;
  const empty = el.querySelector('.panel-empty');
  if (empty) empty.remove();
  const div = document.createElement('div');
  div.innerHTML = renderCanvasCardHTML(c);
  const card = div.firstElementChild;
  el.insertBefore(card, el.firstChild);
  card.querySelectorAll('.canvas-card-body.md').forEach(b => {
    if (typeof marked !== 'undefined') b.innerHTML = marked.parse(b.dataset.raw || '');
  });
}

function removeCanvasCard(id) {
  const el = document.getElementById(`cvs-${id}`);
  if (el) el.remove();
}

async function deleteCanvasCard(id) {
  await fetch(`/api/canvas/${id}`, { method: 'DELETE' });
  removeCanvasCard(id);
}

async function clearCanvas() {
  if (!confirm('Clear all canvas cards?')) return;
  await fetch('/api/canvas', { method: 'DELETE' });
  const el = document.getElementById('canvas-cards');
  if (el) el.innerHTML = '<div class="panel-empty">Canvas cleared.</div>';
}

async function pushCanvasCard() {
  const title = (document.getElementById('canvas-card-title') || {}).value || '';
  const content = (document.getElementById('canvas-card-content') || {}).value || '';
  const type = (document.getElementById('canvas-card-type') || {}).value || 'markdown';
  if (!content.trim()) { if (typeof toast === 'function') toast('Enter card content first', 'warn'); return; }
  try {
    await fetch('/api/canvas', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, content, type }),
    });
    document.getElementById('canvas-card-title').value = '';
    document.getElementById('canvas-card-content').value = '';
    if (typeof toast === 'function') toast('Card added to canvas', 'ok');
  } catch (e) {
    if (typeof toast === 'function') toast('Failed to add card', 'err');
  }
}

// ── Panel auto-load hooks ─────────────────────────────────────────────────────

(function patchSwitchPanel() {
  const orig = window.switchPanel;
  if (typeof orig !== 'function') { setTimeout(patchSwitchPanel, 400); return; }
  window.switchPanel = function(name) {
    orig(name);
    if (name === 'notion') loadNotion();
    else if (name === 'slack') loadSlackChannels();
    else if (name === 'trello') loadTrelloBoards();
    else if (name === 'spotify') loadSpotifyNowPlaying();
    else if (name === 'youtube') loadYouTube();
    else if (name === 'skillhub') loadSkillHub();
    else if (name === 'channels') loadChannels();
    else if (name === 'canvas') loadCanvas();
  };
})();
