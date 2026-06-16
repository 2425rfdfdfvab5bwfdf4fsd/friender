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
  if (!inp) return;

  const question = inp.value.trim() || 'What do you see on this browser page? Describe it in detail.';
  if (btn) btn.classList.add('active');

  if (typeof prefill === 'function') {
    prefill(`capture_and_analyze: ${question}`);
  } else {
    inp.value = `capture_and_analyze: ${question}`;
  }

  if (typeof toast === 'function') {
    toast('👁 Vision: capturing current browser page…', 'info');
  }

  if (btn) setTimeout(() => btn.classList.remove('active'), 2000);

  if (typeof sendCommand === 'function') {
    sendCommand();
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
