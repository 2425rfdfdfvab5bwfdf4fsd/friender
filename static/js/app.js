'use strict';

// ── Marked config ────────────────────────────────────────────────────────────
if (typeof marked !== 'undefined') {
  marked.setOptions({ breaks: true, gfm: true });
}
function renderMD(text) {
  if (!text) return '';
  try {
    return typeof marked !== 'undefined' ? marked.parse(text) : `<pre>${esc(text)}</pre>`;
  } catch(e) { return `<pre>${esc(text)}</pre>`; }
}

// ── State ────────────────────────────────────────────────────────────────────
const S = {
  ws: null, wsReady: false, running: false,
  taskId: null, activeBubble: null, activeGoalBubble: null,
  cmdHistory: [], histIdx: -1, acItems: [], acIdx: -1,
  dryRun: false, goalMode: false, termMode: false,
  term: null, fit: null,
  notifOpen: false, sidebarOpen: true,
  profile: null, currentNote: null,
  briefShown: false, sysMonInterval: null,
  PAL: { open: false, items: [], idx: -1 },
  voice: { active: false, recognition: null },
  // T007: interactive plan editor
  currentPlanSteps: [], currentPlanTaskId: null,
  // T008: trace
  traceTaskId: null,
};

// ── Utilities ────────────────────────────────────────────────────────────────
function esc(s) { return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
function tsLabel(ts) { return new Date(ts*1000).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'}); }
function fmtRelTime(ts) {
  const d = Math.floor((Date.now()/1000 - ts));
  if (d < 60) return 'just now';
  if (d < 3600) return Math.floor(d/60) + 'm ago';
  if (d < 86400) return Math.floor(d/3600) + 'h ago';
  return new Date(ts*1000).toLocaleDateString();
}
function scrollToBottom() {
  const t = document.getElementById('chat-thread');
  if (t) t.scrollTop = t.scrollHeight;
}
function autoResize(el) {
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, 200) + 'px';
}

// Toast
function toast(msg, type='info', dur=3200) {
  const c = document.getElementById('toast-container');
  const d = document.createElement('div');
  d.className = 'toast ' + type;
  d.textContent = msg;
  c.appendChild(d);
  setTimeout(() => {
    d.style.animation = 'toastOut .3s ease forwards';
    setTimeout(() => d.remove(), 300);
  }, dur);
}

// ── WebSocket ────────────────────────────────────────────────────────────────
let _wsRetry = 0;
function connectWS() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  S.ws = new WebSocket(`${proto}://${location.host}/ws`);
  S.ws.onopen = () => { S.wsReady = true; _wsRetry = 0; };
  S.ws.onclose = () => {
    S.wsReady = false; S.running = false; setSendBtn(false);
    document.getElementById('status-dot').className = 'err';
    const delay = Math.min(30000, 1000 * Math.pow(2, _wsRetry++));
    setTimeout(connectWS, delay);
  };
  S.ws.onerror = () => {};
  S.ws.onmessage = e => {
    try { const m = JSON.parse(e.data); dispatch(m.type, m.data || {}); }
    catch(_) {}
  };
}
function wsSend(obj) {
  if (S.ws && S.wsReady) S.ws.send(JSON.stringify(obj));
}

// ── Event dispatcher ─────────────────────────────────────────────────────────
function dispatch(type, data) {
  switch(type) {
    case 'welcome': onWelcome(data); break;
    case 'thinking': onThinking(data); break;
    case 'plan': onPlan(data); break;
    case 'step_start': onStepStart(data); break;
    case 'step_complete': onStepComplete(data); break;
    case 'step_error': onStepError(data); break;
    case 'completed': onCompleted(data); break;
    case 'error': onError(data); break;
    case 'advisory': onAdvisory(data); break;
    case 'advisory_thinking': onAdvisoryThinking(data); break;
    case 'confirmation_required': onConfirmRequired(data); break;
    case 'cancelled': onCancelled(data); break;
    case 'dry_run_complete': onDryRunComplete(data); break;
    case 'goal_start': onGoalStart(data); break;
    case 'subtask_start': onSubtaskStart(data); break;
    case 'subtask_complete': onSubtaskComplete(data); break;
    case 'subtask_failed': onSubtaskFailed(data); break;
    case 'subtask_reflected': onSubtaskReflected(data); break;
    case 'goal_complete': onGoalComplete(data); break;
    case 'goal_error': onGoalError(data); break;
    case 'goal_cancelled': onGoalCancelled(data); break;
    case 'goal_rollback': onGoalRollback(data); break;
    case 'skill_saved': onSkillSaved(data); break;
    case 'memory_data': onMemoryData(data); break;
    case 'status_info': onStatusInfo(data); break;
    case 'help': onHelp(data); break;
    case 'tools_txt': onToolsTxt(data); break;
    case 'preference_updated': toast('Preference saved ✓', 'ok'); break;
    default: break;
  }
}

// ── Chat Engine ───────────────────────────────────────────────────────────────
const chatThread = document.getElementById('chat-thread');

function addUserMsg(text) {
  const div = document.createElement('div');
  div.className = 'msg msg-user';
  div.innerHTML = `<div class="msg-bubble">${esc(text)}</div>`;
  chatThread.appendChild(div);
  scrollToBottom();
}

function createAssistantBubble(taskId, thinkingText) {
  const div = document.createElement('div');
  div.className = 'msg msg-asst';
  div.dataset.task = taskId || '';
  div.innerHTML = `
    <div class="msg-avatar msg-avatar-logo"><img src="/static/logo.png" style="width:100%;height:100%;object-fit:cover;border-radius:50%;display:block"></div>
    <div class="msg-body">
      <div class="msg-thinking"><div class="thinking-dots"><b></b><b></b><b></b></div><span class="thinking-text">${esc(thinkingText||'Thinking…')}</span></div>
      <div class="msg-exec-card" style="display:none"></div>
      <div class="msg-text" style="display:none"></div>
      <div class="msg-meta" style="display:none">
        <span class="msg-time-lbl">${new Date().toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'})}</span>
        <span class="msg-steps-lbl"></span>
        <button class="msg-copy-btn" onclick="copyMsgText(this)">Copy</button>
      </div>
    </div>`;
  chatThread.appendChild(div);
  scrollToBottom();
  return div;
}

function getBubble(taskId) {
  if (S.activeBubble && (S.activeBubble.dataset.task === taskId || !taskId)) return S.activeBubble;
  if (taskId) return chatThread.querySelector(`[data-task="${taskId}"]`);
  return S.activeBubble;
}

function showExecCard(bubble, title, steps, risk) {
  const b = bubble.querySelector('.msg-body');
  b.querySelector('.msg-thinking').style.display = 'none';
  const ec = b.querySelector('.msg-exec-card');
  ec.style.display = 'block';
  const riskCls = risk > 60 ? 'crit' : risk > 30 ? 'high' : '';
  const stepsHtml = (steps||[]).map((s,i) => `
    <div class="exec-step" id="es-${i}-${bubble.dataset.task||'x'}">
      <div class="step-status" title="pending">⋯</div>
      <div class="step-info">
        <div class="step-tool">${esc(s.tool||s)}</div>
        <div class="step-desc">${esc(s.description||s.args_summary||'')}</div>
        <div class="step-result"></div>
      </div>
    </div>`).join('');
  ec.innerHTML = `
    <div class="exec-header" onclick="toggleExecCard(this)">
      <span class="exec-icon">▶</span>
      <span class="exec-title">${steps ? steps.length+'-step plan' : title||'Executing…'}</span>
      ${risk ? `<span class="exec-risk ${riskCls}">Risk: ${risk}</span>` : ''}
      <button class="exec-toggle">▾</button>
    </div>
    <div class="exec-steps">${stepsHtml}</div>`;
  scrollToBottom();
}

function toggleExecCard(header) {
  const steps = header.nextElementSibling;
  steps.classList.toggle('hidden');
  const btn = header.querySelector('.exec-toggle');
  btn.classList.toggle('collapsed');
}

function updateStep(bubble, idx, status, tool, result) {
  if (!bubble) return;
  const tid = bubble.dataset.task || 'x';
  const stepEl = document.getElementById(`es-${idx}-${tid}`);
  if (!stepEl) return;
  const dot = stepEl.querySelector('.step-status');
  const resultEl = stepEl.querySelector('.step-result');
  if (tool) stepEl.querySelector('.step-tool').textContent = tool;
  dot.className = 'step-status ' + status;
  if (status === 'running') dot.textContent = '◌';
  else if (status === 'done') dot.textContent = '✓';
  else if (status === 'err') dot.textContent = '✕';
  if (result) {
    const r = typeof result === 'object' ? (result.error ? '✗ ' + result.error.slice(0,80) : '✓') : String(result).slice(0,100);
    resultEl.textContent = r;
  }
  scrollToBottom();
}

function showTextResponse(bubble, markdown) {
  if (!bubble) return;
  const b = bubble.querySelector('.msg-body');
  b.querySelector('.msg-thinking').style.display = 'none';
  b.querySelector('.msg-exec-card').style.display = 'none';
  const mt = b.querySelector('.msg-text');
  mt.style.display = 'block';
  mt.innerHTML = renderMD(markdown);
  const meta = b.querySelector('.msg-meta');
  meta.style.display = 'flex';
  scrollToBottom();
  // TTS hook — dispatch event for integrations.js to consume
  document.dispatchEvent(new CustomEvent('arix:assistant-message', { detail: { text: markdown } }));
}

function showErrorMsg(bubble, message) {
  if (!bubble) return;
  const b = bubble.querySelector('.msg-body');
  b.querySelector('.msg-thinking').style.display = 'none';
  b.querySelector('.msg-exec-card').style.display = 'none';
  const mt = b.querySelector('.msg-text');
  mt.style.display = 'block';
  mt.innerHTML = `<div class="msg-error"><span class="msg-error-icon">❌</span><span>${esc(message||'An error occurred')}</span></div>`;
  b.querySelector('.msg-meta').style.display = 'flex';
  scrollToBottom();
}

function finalizeExecBubble(bubble, stepsOk, stepsTotal, hasText) {
  if (!bubble) return;
  const b = bubble.querySelector('.msg-body');
  b.querySelector('.msg-thinking').style.display = 'none';
  const ec = b.querySelector('.msg-exec-card');
  const taskId = bubble.dataset.task || '';
  if (ec.style.display !== 'none') {
    // fold steps on completion
    const stepsDiv = ec.querySelector('.exec-steps');
    if (stepsDiv) stepsDiv.classList.add('hidden');
    const toggle = ec.querySelector('.exec-toggle');
    if (toggle) toggle.classList.add('collapsed');
    const hdr = ec.querySelector('.exec-header .exec-icon');
    if (hdr) hdr.textContent = '✓';
    // T008: add trace button to exec card header
    const execHdr = ec.querySelector('.exec-header');
    if (execHdr && taskId && !execHdr.querySelector('.exec-trace-btn')) {
      const traceBtn = document.createElement('button');
      traceBtn.className = 'exec-trace-btn';
      traceBtn.title = 'Show execution trace';
      traceBtn.textContent = '🔍 Trace';
      traceBtn.onclick = (e) => { e.stopPropagation(); showTraceModal(taskId); };
      execHdr.appendChild(traceBtn);
    }
  }
  if (!hasText) {
    const mt = b.querySelector('.msg-text');
    mt.style.display = 'block';
    const ok = stepsOk === stepsTotal;
    mt.innerHTML = `<div class="msg-done-bar ${ok?'':'partial'}">
      ${ok?'✅':'⚠️'} ${stepsOk} of ${stepsTotal} step${stepsTotal!==1?'s':''} completed
    </div>`;
  }
  const meta = b.querySelector('.msg-meta');
  meta.style.display = 'flex';
  meta.querySelector('.msg-steps-lbl').textContent = `· ${stepsOk}/${stepsTotal} steps`;
  scrollToBottom();
}

// T008: Trace modal
async function showTraceModal(taskId) {
  S.traceTaskId = taskId;
  let modal = document.getElementById('trace-modal');
  if (!modal) {
    modal = document.createElement('div');
    modal.id = 'trace-modal';
    modal.className = 'trace-modal-overlay';
    modal.innerHTML = `
      <div class="trace-modal">
        <div class="trace-modal-hdr">
          <span>🔍 Execution Trace</span>
          <button class="trace-modal-close" onclick="document.getElementById('trace-modal').remove()">✕</button>
        </div>
        <div class="trace-modal-body" id="trace-modal-body">
          <div style="color:var(--text2);padding:16px">Loading trace…</div>
        </div>
      </div>`;
    document.body.appendChild(modal);
    modal.addEventListener('click', (e) => { if (e.target === modal) modal.remove(); });
  }
  const body = document.getElementById('trace-modal-body');
  try {
    const r = await fetch(`/api/trace/${encodeURIComponent(taskId)}`);
    const data = await r.json();
    const entries = data.entries || [];
    if (!entries.length) {
      body.innerHTML = '<div style="color:var(--text2);padding:16px">No trace entries found.</div>';
      return;
    }
    let html = '<div class="trace-entries">';
    let startTs = entries[0].ts || 0;
    entries.forEach((e, i) => {
      const dt = e.ts ? ((e.ts - startTs) * 1000).toFixed(0) + 'ms' : '';
      const typeLabel = {
        command: '💬', plan: '📋', step_start: '▶',
        step_complete: '✓', step_error: '✕', completed: '🏁',
        subtask_complete: '✓', subtask_failed: '✗', error: '❌',
        subtask_reflected: '🔄', goal_start: '🎯', goal_complete: '🏆',
      }[e.type] || '•';
      const isCrit = e.type === 'step_error' || e.type === 'error';
      const snippet = JSON.stringify(e.data || {}).slice(0, 120);
      html += `<div class="trace-entry ${isCrit ? 'trace-err' : ''}">
        <span class="trace-icon">${typeLabel}</span>
        <span class="trace-type">${esc(e.type)}</span>
        <span class="trace-dt">${dt ? '+' + dt : ''}</span>
        <div class="trace-data">${esc(snippet)}${snippet.length>=120?'…':''}</div>
      </div>`;
    });
    html += '</div>';
    body.innerHTML = html;
  } catch (err) {
    body.innerHTML = `<div style="color:#e55;padding:16px">Failed to load trace: ${esc(String(err))}</div>`;
  }
}

function showConfirmInBubble(bubble, data) {
  if (!bubble) return;
  const b = bubble.querySelector('.msg-body');
  b.querySelector('.msg-thinking').style.display = 'none';
  const mt = b.querySelector('.msg-text');
  mt.style.display = 'block';
  const msg = (data.message||'').replace(/^Confirmation required.*?:\s*/i,'');
  const isPlanRisk = data.type === 'plan_risk';
  const confId = data.confirmation_id || 'x';
  const taskId = data.task_id || '';

  // T007: Show step checkboxes for plan-level risk confirmation
  let planEditorHtml = '';
  if (isPlanRisk && S.currentPlanSteps.length > 0) {
    const stepRows = S.currentPlanSteps.map((s, i) => {
      const sid = esc(s.step_id || `step-${i}`);
      const riskCls = s.risk_level === 'critical' ? 'color:#e55' : s.risk_level === 'high' ? 'color:#e99' : 'color:var(--text2)';
      return `<label class="plan-step-row">
        <input type="checkbox" class="plan-step-chk" data-step-id="${sid}" checked>
        <span class="plan-step-tool">${esc(s.tool||'')}</span>
        <span class="plan-step-desc" style="${riskCls}">${esc(s.description||'')}</span>
      </label>`;
    }).join('');
    planEditorHtml = `<div class="plan-editor">
      <div class="plan-editor-header">
        <span>📋 Deselect any steps to skip them:</span>
        <button class="plan-editor-all-btn" onclick="toggleAllPlanSteps('${confId}', true)">All</button>
        <button class="plan-editor-all-btn" onclick="toggleAllPlanSteps('${confId}', false)">None</button>
      </div>
      <div class="plan-step-list" id="plan-editor-${confId}">${stepRows}</div>
    </div>`;
  }

  mt.innerHTML = `
    <div class="msg-confirm">
      <div class="msg-confirm-text">⚠️ ${esc(msg)}</div>
      ${planEditorHtml}
      <div class="msg-confirm-row">
        <input class="msg-confirm-input" id="conf-input-${confId}" placeholder="Type YES to confirm…">
        <button class="conf-yes-btn" onclick="sendConfirmFromBubble('${esc(taskId)}','${confId}',true)">YES</button>
        <button class="conf-no-btn" onclick="sendConfirmFromBubble('${esc(taskId)}','${confId}',false)">NO</button>
      </div>
    </div>`;
  scrollToBottom();
}

function toggleAllPlanSteps(confId, checked) {
  const list = document.getElementById(`plan-editor-${confId}`);
  if (!list) return;
  list.querySelectorAll('.plan-step-chk').forEach(cb => { cb.checked = checked; });
}

function addSystemMsg(html) {
  const div = document.createElement('div');
  div.className = 'msg msg-asst';
  div.innerHTML = `<div class="msg-avatar msg-avatar-logo"><img src="/static/logo.png" style="width:100%;height:100%;object-fit:cover;border-radius:50%;display:block"></div><div class="msg-body"><div class="msg-text" style="display:block">${html}</div></div>`;
  chatThread.appendChild(div);
  scrollToBottom();
  return div;
}

// ── Event Handlers ────────────────────────────────────────────────────────────
function onWelcome(d) {
  document.getElementById('status-dot').className = d.llm_available ? 'ok' : 'warn';
  const pb = document.getElementById('provider-badge');
  pb.textContent = (d.provider||'—') + ' / ' + (d.model||'—');
  pb.className = d.llm_available ? 'live' : '';
  if (d.memory_count) updateBadge('mem', d.memory_count);
  if (!d.onboarding_complete) showOnboarding();
  else if (!S.briefShown) { S.briefShown = true; loadMorningBrief(); }
  loadAssistantPanel();
  openDetailSidebar('assistant');
  setTimeout(loadNotifications, 500);
  startSysmon();
}

function onThinking(d) {
  if (S.activeBubble) {
    const tt = S.activeBubble.querySelector('.thinking-text');
    if (tt) tt.textContent = d.message || 'Thinking…';
  }
}

function onPlan(d) {
  if (!S.activeBubble) return;
  const steps = d.steps || [];
  // T007: store plan steps so the confirmation UI can show checkboxes
  S.currentPlanSteps = steps;
  S.currentPlanTaskId = d.task_id;
  showExecCard(S.activeBubble, `${steps.length}-step plan`, steps, d.risk_score);
}

function onStepStart(d) {
  const b = getBubble(d.task_id);
  if (!b) return;
  const idx = (d.step_index !== undefined ? d.step_index : (d.step||1)-1);
  const execCard = b.querySelector('.msg-exec-card');
  if (execCard && execCard.style.display === 'none') showExecCard(b, 'Executing…', null, 0);
  updateStep(b, idx, 'running', d.tool, null);
}

function onStepComplete(d) {
  const b = getBubble(d.task_id);
  if (!b) return;
  const idx = (d.step_index !== undefined ? d.step_index : (d.step||1)-1);
  updateStep(b, idx, 'done', d.tool, d.result);
}

function onStepError(d) {
  const b = getBubble(d.task_id);
  if (!b) return;
  const idx = (d.step_index !== undefined ? d.step_index : (d.step||1)-1);
  updateStep(b, idx, 'err', null, {error: d.error||'Error'});
}

function onCompleted(d) {
  S.running = false; setSendBtn(false);
  const b = S.activeBubble;
  finalizeExecBubble(b, d.steps_executed||0, d.steps_executed||0, false);
  if (b) showContextualChips(b, d.output || '');
  S.activeBubble = null;
  refreshSidePanels();
}

function onError(d) {
  S.running = false; setSendBtn(false);
  showErrorMsg(S.activeBubble, d.message || d.error || 'Unknown error');
  S.activeBubble = null;
}

function onAdvisoryThinking(d) {
  if (S.activeBubble) {
    const tt = S.activeBubble.querySelector('.thinking-text');
    if (tt) tt.textContent = d.message || 'Consulting AI…';
  }
}

function onAdvisory(d) {
  S.running = false; setSendBtn(false);
  const b = S.activeBubble;
  showTextResponse(b, d.response || '');
  if (b) showContextualChips(b, d.response || '');
  S.activeBubble = null;
}

// ── Contextual action chips after assistant response ──────────────────────────
function showContextualChips(bubble, responseText) {
  if (!bubble) return;
  const text = (responseText || '').toLowerCase();
  const chips = [];
  chips.push({icon:'📌', label:'Save to Notes', action:() => {
    switchPanel('notes');
    openNoteEditor(null);
    const snip = (responseText||'').slice(0,200).replace(/\n+/g,' ').trim();
    document.getElementById('note-content-input').value = responseText || '';
    document.getElementById('note-title-input').value = 'Arix — ' + new Date().toLocaleDateString();
    toast('Note editor opened — edit and save', 'info');
  }});
  chips.push({icon:'✓', label:'Create Task', action:() => {
    const inp = document.getElementById('cmd-input');
    inp.value = 'add task: ';
    inp.focus();
    autoResize(inp);
  }});
  if (text.includes('meeting') || text.includes('schedule') || text.includes('calendar') || text.includes('event')) {
    chips.push({icon:'📅', label:'Add to Calendar', action:() => {
      switchPanel('calendar');
      toast('Open Google Calendar to add this event', 'info');
    }});
  }
  chips.push({icon:'↩', label:'Follow up', action:() => {
    document.getElementById('cmd-input').focus();
  }});
  const bar = document.createElement('div');
  bar.className = 'ctx-chips';
  bar.innerHTML = chips.map((c,i) =>
    `<button class="ctx-chip" id="ctxc-${i}">${c.icon} ${c.label}</button>`
  ).join('');
  const msgBody = bubble.querySelector('.msg-body');
  if (msgBody) {
    msgBody.appendChild(bar);
    chips.forEach((c,i) => {
      const btn = document.getElementById('ctxc-'+i);
      if (btn) btn.addEventListener('click', () => { c.action(); bar.remove(); });
    });
    scrollToBottom();
  }
}

function onConfirmRequired(d) {
  showConfirmModal(d);
  // Also show inline stub in bubble so user sees context
  if (S.activeBubble) {
    const b = S.activeBubble.querySelector('.msg-body');
    const thinking = b.querySelector('.msg-thinking');
    if (thinking) thinking.style.display = 'none';
    const mt = b.querySelector('.msg-text');
    mt.style.display = 'block';
    mt.innerHTML = `<div class="msg-confirm"><div class="msg-confirm-text">⚠️ Approval dialog opened — review and confirm above.</div></div>`;
  }
  toast('Action requires your approval', 'warn', 5000);
}

// ── Confirmation Modal ─────────────────────────────────────────────────────
let _confModalData = null;
let _confRequiresYes = false;

function showConfirmModal(d) {
  _confModalData = d;
  const overlay = document.getElementById('confirm-modal-overlay');
  const rawMsg = (d.message || '').replace(/^Confirmation required.*?:\s*/i, '').trim();
  const isPlanRisk = d.type === 'plan_risk';
  const requiresYes = !!(d.requires_yes) || isPlanRisk;
  _confRequiresYes = requiresYes;
  const riskScore = d.risk_score || 0;

  // Risk level + icon
  let riskLevel = 'low', icon = '✅';
  if (riskScore > 100 || d.requires_yes) { riskLevel = 'critical'; icon = '🚨'; }
  else if (riskScore > 60)               { riskLevel = 'high';     icon = '🔴'; }
  else if (riskScore > 30)               { riskLevel = 'medium';   icon = '⚠️'; }

  document.getElementById('cm-icon').textContent = icon;
  document.getElementById('cm-title').textContent = _getSensitiveActionTitle(d, rawMsg);
  const badge = document.getElementById('cm-risk-badge');
  badge.className = `cm-risk-badge ${riskLevel}`;
  badge.textContent = riskLevel;
  document.getElementById('cm-desc').textContent = rawMsg || 'Review the details below before approving.';

  // Steps list (plan_risk)
  const stepsSection = document.getElementById('cm-steps-section');
  const stepsList = document.getElementById('cm-steps-list');
  const steps = d.steps || S.currentPlanSteps || [];
  if (isPlanRisk && steps.length > 0) {
    stepsList.innerHTML = steps.map((s, i) => {
      const sid = esc(s.step_id || `step-${i}`);
      const riskCls = s.risk_level === 'critical' ? 'risk-critical' : s.risk_level === 'high' ? 'risk-high' : '';
      return `<li class="cm-step-item ${riskCls}">
        <input type="checkbox" class="cm-step-chk" data-step-id="${sid}" checked onclick="event.stopPropagation()">
        <span class="cm-step-num">${i+1}</span>
        <span class="cm-step-tool">${esc(s.tool || '')}</span>
        <span class="cm-step-desc">${esc(s.description || '')}</span>
      </li>`;
    }).join('');
    stepsSection.style.display = 'block';
  } else {
    stepsSection.style.display = 'none';
  }

  // YES input for critical / plan_risk actions
  const yesWrap = document.getElementById('cm-yes-wrap');
  const yesInput = document.getElementById('cm-yes-input');
  const approveBtn = document.getElementById('cm-approve-btn');
  if (requiresYes) {
    yesWrap.style.display = 'flex';
    yesInput.value = '';
    approveBtn.className = 'cm-approve-btn danger-action';
    approveBtn.textContent = '✓ Confirm';
    setTimeout(() => yesInput.focus(), 120);
  } else {
    yesWrap.style.display = 'none';
    approveBtn.className = 'cm-approve-btn';
    approveBtn.textContent = '✓ Approve';
    setTimeout(() => approveBtn.focus(), 80);
  }

  overlay.classList.add('show');

  // Keyboard: Esc → cancel, Enter → approve (only when no YES input needed)
  overlay._keyFn = (e) => {
    if (e.key === 'Escape') { e.preventDefault(); dismissConfirmModal(false); }
    if (e.key === 'Enter' && !requiresYes) { e.preventDefault(); submitConfirmModal(true); }
    if (e.key === 'Enter' && requiresYes) { e.preventDefault(); submitConfirmModal(true); }
  };
  document.addEventListener('keydown', overlay._keyFn);
}

function _getSensitiveActionTitle(d, msg) {
  const m = (msg || d.message || '').toLowerCase();
  if (m.includes('send') && (m.includes('message') || m.includes('whatsapp') || m.includes('email') || m.includes('dm'))) return 'Send a message?';
  if (m.includes('delete') || m.includes('trash') || m.includes('remove') || m.includes('temp file')) return 'Delete files?';
  if (m.includes('purchase') || m.includes('buy') || m.includes('payment') || m.includes('checkout')) return 'Make a purchase?';
  if (m.includes('system') && (m.includes('setting') || m.includes('change') || m.includes('modify'))) return 'Change system settings?';
  if (m.includes('post') || m.includes('publish') || m.includes('upload') || m.includes('share')) return 'Post / publish content?';
  if (m.includes('commit') || m.includes('push')) return 'Commit & push code?';
  if (d.type === 'plan_risk') return 'Approve this execution plan?';
  return 'Action requires your approval';
}

function submitConfirmModal(yes) {
  const d = _confModalData;
  if (!d) return;
  if (yes && _confRequiresYes) {
    const yesWrap = document.getElementById('cm-yes-wrap');
    if (yesWrap && yesWrap.style.display !== 'none') {
      const yesInput = document.getElementById('cm-yes-input');
      if (yesInput.value.trim().toUpperCase() !== 'YES') {
        yesInput.style.borderColor = 'var(--danger)';
        yesInput.style.boxShadow = '0 0 0 3px rgba(240,82,82,.25)';
        yesInput.placeholder = 'Type YES exactly';
        yesInput.focus();
        return;
      }
    }
  }
  _dismissConfirmModalInternal(yes);
}

function dismissConfirmModal(yes) {
  _dismissConfirmModalInternal(yes);
}

function _dismissConfirmModalInternal(yes) {
  const d = _confModalData;
  const overlay = document.getElementById('confirm-modal-overlay');
  overlay.classList.remove('show');
  if (overlay._keyFn) {
    document.removeEventListener('keydown', overlay._keyFn);
    overlay._keyFn = null;
  }
  _confRequiresYes = false;
  if (!d) return;

  const confId = d.confirmation_id || 'x';
  const taskId = d.task_id || '';

  // Collect deselected step IDs
  let skipSteps = [];
  if (yes && d.type === 'plan_risk') {
    const stepsList = document.getElementById('cm-steps-list');
    if (stepsList) {
      stepsList.querySelectorAll('.cm-step-chk').forEach(cb => {
        if (!cb.checked) skipSteps.push(cb.dataset.stepId);
      });
    }
  }

  wsSend({type:'confirm', data:{task_id:taskId, confirmation_id:confId, response: yes ? 'YES' : 'NO', skip_steps:skipSteps}});

  // Update inline bubble stub
  const confirmEl = document.querySelector('.msg-confirm');
  if (confirmEl) {
    const skippedMsg = skipSteps.length > 0 ? ` (${skipSteps.length} step${skipSteps.length>1?'s':''} skipped)` : '';
    confirmEl.innerHTML = `<div class="msg-confirm-text">${yes ? `✅ Approved — proceeding…${skippedMsg}` : '🚫 Cancelled by user.'}</div>`;
  }
  _confModalData = null;
}

function onCancelled(d) {
  S.running = false; setSendBtn(false);
  if (S.activeBubble) {
    showErrorMsg(S.activeBubble, 'Task cancelled.');
    S.activeBubble = null;
  }
}

function onDryRunComplete(d) {
  S.running = false; setSendBtn(false);
  if (!S.activeBubble) return;
  const b = S.activeBubble.querySelector('.msg-body');
  b.querySelector('.msg-thinking').style.display = 'none';
  const mt = b.querySelector('.msg-text');
  mt.style.display = 'block';
  const steps = d.steps || [];
  const stepsHtml = steps.map((s,i)=>`<li><b>${esc(s.tool||s)}</b>${s.description?' — '+esc(s.description):''}</li>`).join('');
  mt.innerHTML = `<div class="msg-dryrun"><div class="msg-dryrun-title">🔍 Dry-run — ${steps.length} steps planned (risk: ${d.risk_score||0})</div><ol style="padding-left:18px;color:var(--text2);font-size:11.5px;line-height:1.6">${stepsHtml}</ol></div>`;
  b.querySelector('.msg-meta').style.display = 'flex';
  scrollToBottom();
  S.activeBubble = null;
}

// ── Goal supervisor ───────────────────────────────────────────────────────────
function onGoalStart(d) {
  S.running = true; setSendBtn(true);
  S.activeGoalBubble = S.activeBubble;
  const subtasks = d.subtasks || [];
  if (!S.activeGoalBubble) return;
  const b = S.activeGoalBubble.querySelector('.msg-body');
  b.querySelector('.msg-thinking').style.display = 'none';
  const mt = b.querySelector('.msg-text');
  mt.style.display = 'block';
  const dotsHtml = subtasks.map((_,i)=>`<div class="goal-subtask-dot" id="gdot-${i}-${d.goal_id||'g'}"></div>`).join('');
  const tasksHtml = subtasks.map((t,i)=>`<div class="goal-subtask"><div class="goal-subtask-dot" id="gst-${i}-${d.goal_id||'g'}"></div><div class="goal-subtask-text">${esc(t.description||t)}</div></div>`).join('');
  mt.innerHTML = `<div class="msg-goal-card">
    <div class="goal-card-header">
      <div class="goal-title-row"><span class="goal-card-icon">🎯</span><span class="goal-card-title">${esc(d.goal||'')}</span><span class="goal-card-status" id="gs-status-${d.goal_id||'g'}">0/${subtasks.length}</span></div>
      <div class="goal-progress-bar"><div class="goal-progress-fill" id="gp-fill-${d.goal_id||'g'}" style="width:0"></div></div>
      <div class="goal-progress-label"><span id="gp-label-${d.goal_id||'g'}">Planning…</span></div>
    </div>
    <div class="goal-subtasks">${tasksHtml}</div>
  </div>`;
  // Update floating bar
  document.getElementById('goal-bar').classList.add('show');
  document.getElementById('goal-title-label').textContent = (d.goal||'').slice(0,60);
  document.getElementById('goal-count').textContent = '0/' + subtasks.length;
  scrollToBottom();
}

function onSubtaskStart(d) {
  const i = (d.step||1) - 1;
  const gid = d.goal_id || 'g';
  const dot = document.getElementById(`gst-${i}-${gid}`);
  if (dot) dot.className = 'goal-subtask-dot running';
  document.getElementById('goal-count').textContent = (d.step||1) + '/' + (d.total||'?');
  const fill = document.getElementById(`gp-fill-${gid}`);
  if (fill) fill.style.width = Math.round(((d.step||1)-1)/(d.total||1)*100) + '%';
  const lbl = document.getElementById(`gp-label-${gid}`);
  if (lbl) lbl.textContent = `Step ${d.step} of ${d.total}: ${(d.description||'').slice(0,50)}`;
}

function onSubtaskComplete(d) {
  const i = (d.step||1) - 1;
  const gid = d.goal_id || 'g';
  const dot = document.getElementById(`gst-${i}-${gid}`);
  if (dot) dot.className = 'goal-subtask-dot done';
  const fill = document.getElementById(`gp-fill-${gid}`);
  if (fill) fill.style.width = Math.round((d.step||1)/(d.total||1)*100) + '%';
  document.getElementById('goal-fill').style.width = Math.round((d.step||1)/(d.total||1)*100) + '%';
}

function onSubtaskFailed(d) {
  const i = (d.step||1) - 1;
  const gid = d.goal_id || 'g';
  const dot = document.getElementById(`gst-${i}-${gid}`);
  if (dot) dot.className = 'goal-subtask-dot failed';
}

function onGoalComplete(d) {
  S.running = false; setSendBtn(false);
  document.getElementById('goal-bar').classList.remove('show');
  document.getElementById('goal-fill').style.width = '0';
  const ok = d.steps_completed||0, tot = d.steps_total||0;
  if (S.activeGoalBubble) {
    const mt = S.activeGoalBubble.querySelector('.msg-text');
    if (mt) {
      const card = mt.querySelector('.msg-goal-card');
      if (card) {
        const gid = d.goal_id || 'g';
        const fill = document.getElementById(`gp-fill-${gid}`);
        if (fill) fill.style.width = '100%';
        const lbl = document.getElementById(`gp-label-${gid}`);
        if (lbl) lbl.textContent = `✅ Completed — ${ok}/${tot} steps`;
      }
    }
    const meta = S.activeGoalBubble.querySelector('.msg-meta');
    if (meta) { meta.style.display = 'flex'; meta.querySelector('.msg-steps-lbl').textContent = `· ${ok}/${tot} steps`; }
  }
  S.activeGoalBubble = null; S.activeBubble = null;
  toast('🎯 Goal complete — ' + ok + '/' + tot + ' steps', 'ok', 4000);
  refreshSidePanels();
}

function onGoalError(d) {
  S.running = false; setSendBtn(false);
  document.getElementById('goal-bar').classList.remove('show');
  if (S.activeGoalBubble) showErrorMsg(S.activeGoalBubble, 'Goal failed: ' + (d.error||''));
  S.activeGoalBubble = null; S.activeBubble = null;
  toast('Goal failed: ' + (d.error||''), 'err', 5000);
}

function onGoalCancelled(d) {
  S.running = false; setSendBtn(false);
  document.getElementById('goal-bar').classList.remove('show');
  if (S.activeGoalBubble) showErrorMsg(S.activeGoalBubble, 'Goal cancelled.');
  S.activeGoalBubble = null; S.activeBubble = null;
}

// T003: Self-reflection notification (supervisor retrying after failure)
function onSubtaskReflected(d) {
  const gid = d.goal_id || 'g';
  const i = (d.step || 1) - 1;
  const dot = document.getElementById(`gst-${i}-${gid}`);
  if (dot) { dot.className = 'goal-subtask-dot running'; dot.title = '🔄 Reflecting…'; }
  const lbl = document.getElementById(`gp-label-${gid}`);
  if (lbl) lbl.textContent = `🔄 Reflecting on step ${d.step||'?'}: ${(d.reflection||'').slice(0,60)}`;
  toast('🔄 Retrying after reflection…', 'info', 3000);
}

// T009: Goal rollback notification
function onGoalRollback(d) {
  toast('↩ Goal rolled back — files restored to pre-goal state', 'warn', 5000);
  const gid = d.goal_id || 'g';
  const lbl = document.getElementById(`gp-label-${gid}`);
  if (lbl) lbl.textContent = `↩ Rolled back: ${d.reason || ''}`;
}

// T012: Skill saved notification
function onSkillSaved(d) {
  toast(`💾 Skill saved: "${d.name || 'Unnamed'}"`, 'ok', 4000);
  const skillBtn = document.createElement('button');
  skillBtn.className = 'ctx-chip';
  skillBtn.innerHTML = `💾 View skill: ${esc((d.name||'').slice(0,20))}`;
  skillBtn.onclick = () => loadSkillsPanel();
  if (S.activeGoalBubble) {
    const mb = S.activeGoalBubble.querySelector('.msg-body');
    if (mb) mb.appendChild(skillBtn);
  }
}

function loadSkillsPanel() {
  toast('Skills panel — see /api/skills', 'info', 2500);
}

function cancelGoal() {
  if (S.taskId) wsSend({type:'cancel', data:{task_id:S.taskId}});
  document.getElementById('goal-bar').classList.remove('show');
  S.running = false; setSendBtn(false);
}

// ── Memory / status events (for terminal compat) ──────────────────────────────
function onMemoryData(d) { renderMemory(d); switchPanel('memory'); }
function onStatusInfo(d) {
  document.getElementById('status-dot').className = d.llm_available ? 'ok' : 'warn';
  const pb = document.getElementById('provider-badge');
  pb.textContent = (d.provider||'—') + ' / ' + (d.model||'—');
  pb.className = d.llm_available ? 'live' : '';
  if (d.memory_count !== undefined) updateBadge('mem', d.memory_count);
  if (d.workflow_count !== undefined) updateBadge('wf', d.workflow_count);
}
function onHelp(d) { addSystemMsg(`<div style="font-size:11.5px;color:var(--text2);line-height:1.7;white-space:pre-wrap">${esc(d.text||'')}</div>`); }
function onToolsTxt(d) { addSystemMsg(`<div style="font-size:11.5px;color:var(--text2);line-height:1.7"><b style="color:var(--text)">Available Tools</b><br><br><pre style="font-size:10.5px;color:var(--text2)">${esc(d.text||'')}</pre></div>`); }

// ── Send command ──────────────────────────────────────────────────────────────
function sendCommand() {
  const input = document.getElementById('cmd-input');
  let cmd = (input.value || '').trim();
  if (!cmd) return;
  if (S.dryRun && !cmd.toLowerCase().startsWith('dry-run:') && !cmd.toLowerCase().startsWith('dry run:')) cmd = 'dry-run: ' + cmd;
  S.cmdHistory.unshift(cmd.replace(/^dry-run:\s*/i,''));
  if (S.cmdHistory.length > 200) S.cmdHistory.pop();
  S.histIdx = -1;
  addUserMsg(cmd.replace(/^dry-run:\s*/i,''));
  const taskId = 'task-' + Date.now();
  S.taskId = taskId;
  S.activeBubble = createAssistantBubble(taskId, 'Thinking…');
  S.running = true; setSendBtn(true);
  const mode = S.goalMode ? 'goal' : 'command';
  wsSend({type: mode, data: {command: cmd, task_id: taskId}});
  input.value = '';
  autoResize(input);
  document.getElementById('char-count').textContent = '';
  input.focus();
  scrollToBottom();
}

function sendConfirmFromBubble(taskId, confId, yes) {
  const input = document.getElementById(`conf-input-${confId}`);
  const val = yes ? (input ? (input.value.trim() || 'YES') : 'YES') : 'NO';

  // T007: collect deselected step IDs from plan editor checkboxes
  let skipSteps = [];
  if (yes && confId === 'plan_risk') {
    const list = document.getElementById(`plan-editor-${confId}`);
    if (list) {
      list.querySelectorAll('.plan-step-chk').forEach(cb => {
        if (!cb.checked) skipSteps.push(cb.dataset.stepId);
      });
    }
  }

  wsSend({type:'confirm', data:{task_id:taskId, confirmation_id:confId, response:val, skip_steps:skipSteps}});
  // Update confirm UI
  const confirmEl = document.querySelector('.msg-confirm');
  if (confirmEl) {
    const skippedMsg = skipSteps.length > 0 ? ` (${skipSteps.length} step${skipSteps.length>1?'s':''} skipped)` : '';
    confirmEl.innerHTML = `<div class="msg-confirm-text">${yes ? `✅ Confirmed — proceeding…${skippedMsg}` : '🚫 Cancelled.'}</div>`;
  }
}

// Terminal mode send
function sendTermCommand() {
  const input = document.getElementById('term-input');
  const cmd = input.value.trim();
  if (!cmd) return;
  if (S.term) { S.term.writeln('\r\n\x1b[1;34m› \x1b[0m\x1b[1;37m' + cmd + '\x1b[0m'); }
  wsSend({type:'command', data:{command:cmd}});
  input.value = '';
}

function setSendBtn(running) {
  const btn = document.getElementById('send-btn');
  btn.disabled = false;
  if (running) {
    btn.textContent = '■';
    btn.classList.add('running');
    btn.title = 'Stop';
    btn.onclick = () => { if (S.taskId) wsSend({type:'cancel',data:{task_id:S.taskId}}); };
  } else {
    btn.textContent = '▲';
    btn.classList.remove('running');
    btn.title = 'Send (Enter)';
    btn.onclick = sendCommand;
  }
}

// ── Input handling ────────────────────────────────────────────────────────────
function onInputKey(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    if (S.acIdx >= 0) { pickAC(S.acIdx); closeAC(); }
    else sendCommand();
    return;
  }
  if (e.key === 'Escape') { closeAC(); return; }
  if (e.key === 'ArrowUp') {
    if (S.acItems.length) { e.preventDefault(); acNav(-1); return; }
    S.histIdx = Math.min(S.histIdx+1, S.cmdHistory.length-1);
    e.target.value = S.cmdHistory[S.histIdx] || '';
    autoResize(e.target); e.preventDefault(); return;
  }
  if (e.key === 'ArrowDown') {
    if (S.acItems.length) { e.preventDefault(); acNav(1); return; }
    S.histIdx = Math.max(S.histIdx-1, -1);
    e.target.value = S.histIdx >= 0 ? S.cmdHistory[S.histIdx] : '';
    autoResize(e.target); e.preventDefault(); return;
  }
  if (e.key === 'Tab') { e.preventDefault(); if (S.acIdx < 0 && S.acItems.length) acNav(1); else if (S.acIdx >= 0) pickAC(S.acIdx); return; }
}

function onInputChange(el) {
  autoResize(el);
  const len = el.value.length;
  const cc = document.getElementById('char-count');
  if (len > 400) { cc.textContent = len; cc.className = len > 800 ? 'warn' : ''; } else { cc.textContent = ''; }
  updateAC(el.value);
}

// ── Quick chips ───────────────────────────────────────────────────────────────
const QUICK_CHIPS = [
  {icon:'🔍', label:'Research', cmd:'research_topic: '},
  {icon:'💻', label:'Code', cmd:'generate_code: '},
  {icon:'🌐', label:'Browse', cmd:'browser_open_url: '},
  {icon:'📋', label:'System', cmd:'system monitor'},
  {icon:'📁', label:'Files', cmd:'list_directory ~/'},
  {icon:'🔀', label:'Git', cmd:'git status'},
  {icon:'📊', label:'Analyze', cmd:'analyze_code_quality: '},
  {icon:'📄', label:'Summarize URL', cmd:'summarize_url: '},
];

function buildQuickChips() {
  const bar = document.getElementById('quick-chips');
  bar.innerHTML = QUICK_CHIPS.map(c =>
    `<button class="qchip" onclick="prefill(${JSON.stringify(c.cmd)})"><span class="qchip-icon">${c.icon}</span>${esc(c.label)}</button>`
  ).join('');
}

function prefill(cmd) {
  const inp = document.getElementById('cmd-input');
  inp.value = cmd;
  inp.focus();
  autoResize(inp);
}

// ── Autocomplete ──────────────────────────────────────────────────────────────
const TOOL_HINTS = [
  {label:'research_topic:', hint:'Research topic', icon:'🔬'},
  {label:'summarize_url:', hint:'Summarize a URL', icon:'📄'},
  {label:'browser_open_url:', hint:'Open URL', icon:'🌐'},
  {label:'browser_web_search:', hint:'Web search', icon:'🔍'},
  {label:'generate_code:', hint:'Generate code', icon:'💻'},
  {label:'explain_code:', hint:'Explain code', icon:'📖'},
  {label:'refactor_code:', hint:'Refactor code', icon:'🔧'},
  {label:'analyze_code_quality:', hint:'Code quality', icon:'📊'},
  {label:'create_file:', hint:'Create file', icon:'📄'},
  {label:'read_file:', hint:'Read file', icon:'📂'},
  {label:'list_directory:', hint:'List files', icon:'📁'},
  {label:'search_files:', hint:'Search files', icon:'🔎'},
  {label:'system monitor', hint:'System stats', icon:'💻'},
  {label:'git status', hint:'Git status', icon:'🌿'},
  {label:'git diff', hint:'Git diff', icon:'🔀'},
  {label:'analyze_image:', hint:'Analyze image', icon:'🖼'},
  {label:'send_whatsapp_message:', hint:'Send WhatsApp', icon:'💬'},
  {label:'dry-run:', hint:'Plan without executing', icon:'🔍'},
  {label:'help', hint:'Show help', icon:'❓'},
  {label:'status', hint:'Agent status', icon:'ℹ️'},
];

const acEl = document.getElementById('autocomplete');
function updateAC(val) {
  if (!val || val.length < 2) { closeAC(); return; }
  const q = val.toLowerCase();
  S.acItems = TOOL_HINTS.filter(h => h.label.toLowerCase().startsWith(q) || h.hint.toLowerCase().includes(q)).slice(0, 8);
  if (!S.acItems.length) { closeAC(); return; }
  acEl.innerHTML = S.acItems.map((h,i) =>
    `<div class="ac-item" onclick="pickAC(${i})"><span class="ac-icon">${h.icon}</span><span class="ac-label">${esc(h.label)}</span><span class="ac-hint">${esc(h.hint)}</span></div>`
  ).join('');
  acEl.classList.add('show');
  S.acIdx = -1;
}
function closeAC() { acEl.classList.remove('show'); S.acItems = []; S.acIdx = -1; }
function acNav(dir) {
  S.acIdx = Math.max(-1, Math.min(S.acItems.length-1, S.acIdx+dir));
  acEl.querySelectorAll('.ac-item').forEach((el,i) => el.classList.toggle('selected', i===S.acIdx));
}
function pickAC(i) {
  const inp = document.getElementById('cmd-input');
  inp.value = S.acItems[i].label;
  inp.focus(); closeAC(); autoResize(inp);
}
document.addEventListener('click', e => {
  const inp = document.getElementById('cmd-input');
  if (!acEl.contains(e.target) && e.target !== inp) closeAC();
  if (!document.getElementById('notif-dropdown').contains(e.target) &&
      e.target !== document.getElementById('notif-btn')) closeNotifDropdown();
});

// ── Dev mode / sidebar ───────────────────────────────────────────────────────
function toggleDevMode() {
  S.termMode = !S.termMode;
  const cv = document.getElementById('chat-view');
  const tv = document.getElementById('terminal-view');
  const btn = document.getElementById('dev-mode-btn');
  if (S.termMode) {
    cv.style.display = 'none'; tv.classList.add('show');
    btn.classList.add('active'); btn.textContent = '💬 Chat';
    if (!S.term) initTerm();
    if (S.fit) S.fit.fit();
    document.getElementById('term-input').focus();
  } else {
    cv.style.display = ''; tv.classList.remove('show');
    btn.classList.remove('active'); btn.textContent = '⌨ Console';
    document.getElementById('cmd-input').focus();
  }
}

function toggleSidebar() {
  S.sidebarOpen = !S.sidebarOpen;
  const sb = document.getElementById('sidebar');
  const bd = document.getElementById('sidebar-backdrop');
  if (window.innerWidth <= 768) {
    sb.classList.toggle('mobile-open', S.sidebarOpen);
    bd.classList.toggle('show', S.sidebarOpen);
  } else {
    sb.classList.toggle('collapsed', !S.sidebarOpen);
  }
  if (S.termMode && S.fit) setTimeout(() => S.fit.fit(), 230);
}
function closeSidebarMobile() {
  if (window.innerWidth <= 768) {
    S.sidebarOpen = false;
    document.getElementById('sidebar').classList.remove('mobile-open');
    document.getElementById('sidebar-backdrop').classList.remove('show');
  }
}

// ── Tasks Sidebar (second left panel) ────────────────────────────────────────
function toggleTasksSidebar() {
  const tsb = document.getElementById('tasks-sidebar');
  const btn = document.getElementById('tsb-toggle-btn');
  const isOpen = !tsb.classList.contains('tsb-collapsed');
  tsb.classList.toggle('tsb-collapsed', isOpen);
  btn && btn.classList.toggle('active', !isOpen);
  if (!isOpen) loadTsbPanel();
  if (S.termMode && S.fit) setTimeout(() => S.fit.fit(), 230);
}

async function loadTsbPanel() {
  try {
    const [todosRes, remsRes] = await Promise.all([
      fetch('/api/todos?include_done=false'),
      fetch('/api/reminders')
    ]);
    const todosData = await todosRes.json();
    const remsData  = await remsRes.json();
    renderTsbTodoList(todosData.todos || []);
    renderTsbRemList(remsData.reminders || []);
  } catch(e) {}
}

function renderTsbTodoList(todos) {
  const el = document.getElementById('tsb-todo-list');
  if (!el) return;
  if (!todos.length) { el.innerHTML = '<div class="panel-empty">No tasks yet — add one above!</div>'; return; }
  el.innerHTML = todos.map(t => `
    <div class="asst-todo-item">
      <input type="checkbox" class="asst-todo-check" ${t.done?'checked':''} onchange="toggleTodoDoneTsb('${esc(t.id)}',this.checked)">
      <span class="asst-todo-text ${t.done?'done':''}">${esc(t.text)}</span>
      <span class="asst-todo-pri ptask-pri ${esc(t.priority)}">${esc(t.priority)}</span>
      <button style="background:transparent;border:none;color:var(--muted);cursor:pointer;font-size:11px;padding:2px 4px" onclick="deleteTodoTsb('${esc(t.id)}')">✕</button>
    </div>`).join('');
}

function renderTsbRemList(rems) {
  const el = document.getElementById('tsb-rem-list');
  if (!el) return;
  const now = new Date();
  const active = rems.filter(r => !r.done);
  if (!active.length) { el.innerHTML = '<div class="panel-empty">No reminders set.</div>'; return; }
  el.innerHTML = active.map(r => {
    const due = new Date(r.due);
    const overdue = due < now;
    const dueStr = due.toLocaleString([],{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'});
    return `<div class="asst-rem-item">
      <div style="flex:1">
        <div class="asst-rem-text">${esc(r.text)}</div>
        <div class="asst-rem-when ${overdue?'overdue':''}">${overdue?'⚠ Overdue — ':''}${dueStr}</div>
      </div>
      <button style="background:transparent;border:none;color:var(--muted);cursor:pointer;font-size:11px;padding:2px 4px" onclick="doneReminderTsb('${esc(r.id)}')">✓</button>
      <button style="background:transparent;border:none;color:var(--muted);cursor:pointer;font-size:11px;padding:2px 4px" onclick="deleteReminderTsb('${esc(r.id)}')">✕</button>
    </div>`;
  }).join('');
}

async function addTsbTodo() {
  const inp = document.getElementById('tsb-todo-input');
  const pri = document.getElementById('tsb-todo-pri');
  const text = inp.value.trim();
  if (!text) { inp.focus(); return; }
  try {
    await fetch('/api/todos', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({text, priority:pri.value})});
    inp.value = ''; toast('Task added ✓','ok');
    loadAssistantPanel(); loadTsbPanel(); loadRsbPanel();
  } catch(e) { toast('Failed to add task','err'); }
}

async function addTsbReminder() {
  const inp  = document.getElementById('tsb-rem-input');
  const when = document.getElementById('tsb-rem-when');
  const text = inp.value.trim();
  const whenVal = when.value.trim() || 'in 1 hour';
  if (!text) { inp.focus(); return; }
  try {
    await fetch('/api/reminders', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({text, when:whenVal})});
    inp.value = ''; toast('Reminder set ✓','ok');
    loadAssistantPanel(); loadTsbPanel(); loadRsbPanel();
  } catch(e) { toast('Failed to add reminder','err'); }
}

async function toggleTodoDoneTsb(id, done) {
  if (done) await fetch(`/api/todos/${id}/done`, {method:'POST'});
  else await fetch(`/api/todos/${id}`, {method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify({done:false})});
  loadAssistantPanel(); loadTsbPanel(); loadRsbPanel();
}
async function deleteTodoTsb(id) {
  await fetch(`/api/todos/${id}`, {method:'DELETE'});
  loadAssistantPanel(); loadTsbPanel(); loadRsbPanel();
}
async function doneReminderTsb(id) {
  await fetch(`/api/reminders/${id}/done`, {method:'POST'});
  loadAssistantPanel(); loadTsbPanel(); loadRsbPanel();
}
async function deleteReminderTsb(id) {
  await fetch(`/api/reminders/${id}`, {method:'DELETE'});
  loadAssistantPanel(); loadTsbPanel(); loadRsbPanel();
}

// ── Right Sidebar ─────────────────────────────────────────────────────────────
function toggleRightSidebar() {
  const rsb = document.getElementById('right-sidebar');
  const btn = document.getElementById('rsb-toggle-btn');
  const isOpen = !rsb.classList.contains('rsb-collapsed');
  rsb.classList.toggle('rsb-collapsed', isOpen);
  btn && btn.classList.toggle('active', !isOpen);
  if (!isOpen) loadRsbPanel();
  if (S.termMode && S.fit) setTimeout(() => S.fit.fit(), 230);
}

async function loadRsbPanel() {
  buildRsbActions();
  try {
    const [todosRes, remsRes] = await Promise.all([
      fetch('/api/todos?include_done=false'),
      fetch('/api/reminders')
    ]);
    const todosData = await todosRes.json();
    const remsData  = await remsRes.json();
    renderRsbTodoList(todosData.todos || []);
    renderRsbRemList(remsData.reminders || []);
  } catch(e) {}
}

function buildRsbActions() {
  const el = document.getElementById('rsb-actions-grid');
  if (!el) return;
  const actions = [
    {icon:'🌄', label:'Morning Brief',   fn:'loadMorningBrief()'},
    {icon:'📱', label:'Apps',            fn:"switchPanel('apps')"},
    {icon:'📈', label:'Insights',        fn:"switchPanel('insights')"},
    {icon:'🧠', label:'Memory',          fn:"switchPanel('memory')"},
    {icon:'🔄', label:'Workflows',       fn:"switchPanel('workflows')"},
    {icon:'📊', label:'System',          fn:"switchPanel('sysmon')"},
    {icon:'📝', label:'Notes',           fn:"switchPanel('notes')"},
    {icon:'📅', label:'Calendar',        fn:"switchPanel('calendar')"},
    {icon:'📧', label:'Gmail',           fn:"switchPanel('gmail')"},
    {icon:'📋', label:'Trello',          fn:"switchPanel('trello')"},
  ];
  el.innerHTML = actions.map(a =>
    `<button class="rsb-action-btn" onclick="${a.fn}">
       <span class="rsb-action-icon">${a.icon}</span>${esc(a.label)}
     </button>`
  ).join('');
}

function renderRsbTodoList(todos) {
  const el = document.getElementById('rsb-todo-list');
  if (!el) return;
  if (!todos.length) { el.innerHTML = '<div class="panel-empty">No tasks yet!</div>'; return; }
  el.innerHTML = todos.map(t => `
    <div class="asst-todo-item">
      <input type="checkbox" class="asst-todo-check" ${t.done?'checked':''} onchange="toggleTodoDoneRsb('${esc(t.id)}',this.checked)">
      <span class="asst-todo-text ${t.done?'done':''}">${esc(t.text)}</span>
      <span class="asst-todo-pri ptask-pri ${esc(t.priority)}">${esc(t.priority)}</span>
      <button style="background:transparent;border:none;color:var(--muted);cursor:pointer;font-size:11px;padding:2px 4px" onclick="deleteTodoRsb('${esc(t.id)}')">✕</button>
    </div>`).join('');
}

function renderRsbRemList(rems) {
  const el = document.getElementById('rsb-rem-list');
  if (!el) return;
  const now = new Date();
  const active = rems.filter(r => !r.done);
  if (!active.length) { el.innerHTML = '<div class="panel-empty">No reminders.</div>'; return; }
  el.innerHTML = active.map(r => {
    const due = new Date(r.due);
    const overdue = due < now;
    const dueStr = due.toLocaleString([],{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'});
    return `<div class="asst-rem-item">
      <div style="flex:1">
        <div class="asst-rem-text">${esc(r.text)}</div>
        <div class="asst-rem-when ${overdue?'overdue':''}">${overdue?'⚠ Overdue — ':''}${dueStr}</div>
      </div>
      <button style="background:transparent;border:none;color:var(--muted);cursor:pointer;font-size:11px;padding:2px 4px" onclick="doneReminderRsb('${esc(r.id)}')">✓</button>
      <button style="background:transparent;border:none;color:var(--muted);cursor:pointer;font-size:11px;padding:2px 4px" onclick="deleteReminderRsb('${esc(r.id)}')">✕</button>
    </div>`;
  }).join('');
}

async function addRsbTodo() {
  const inp = document.getElementById('rsb-todo-input');
  const pri = document.getElementById('rsb-todo-pri');
  const text = inp.value.trim();
  if (!text) { inp.focus(); return; }
  try {
    await fetch('/api/todos', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({text, priority:pri.value})});
    inp.value = ''; toast('Task added ✓','ok');
    loadAssistantPanel(); loadRsbPanel();
  } catch(e) { toast('Failed to add task','err'); }
}

async function addRsbReminder() {
  const inp  = document.getElementById('rsb-rem-input');
  const when = document.getElementById('rsb-rem-when');
  const text = inp.value.trim();
  const whenVal = when.value.trim() || 'in 1 hour';
  if (!text) { inp.focus(); return; }
  try {
    await fetch('/api/reminders', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({text, when:whenVal})});
    inp.value = ''; toast('Reminder set ✓','ok');
    loadAssistantPanel(); loadRsbPanel();
  } catch(e) { toast('Failed to add reminder','err'); }
}

async function toggleTodoDoneRsb(id, done) {
  if (done) await fetch(`/api/todos/${id}/done`, {method:'POST'});
  else await fetch(`/api/todos/${id}`, {method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify({done:false})});
  loadAssistantPanel(); loadRsbPanel();
}
async function deleteTodoRsb(id) {
  await fetch(`/api/todos/${id}`, {method:'DELETE'});
  loadAssistantPanel(); loadRsbPanel();
}
async function doneReminderRsb(id) {
  await fetch(`/api/reminders/${id}/done`, {method:'POST'});
  loadAssistantPanel(); loadRsbPanel();
}
async function deleteReminderRsb(id) {
  await fetch(`/api/reminders/${id}`, {method:'DELETE'});
  loadAssistantPanel(); loadRsbPanel();
}

const PANEL_TITLES = {
  assistant:'🤖 Assistant', apps:'📱 Apps', projects:'✓ Projects',
  notes:'📝 Notes', calendar:'📅 Calendar', workflows:'🔄 Workflows',
  memory:'🧠 Memory', insights:'📈 Insights', reports:'📄 Reports',
  gmail:'📧 Gmail', drive:'📁 Drive', notion:'📒 Notion',
  slack:'💬 Slack', trello:'📋 Trello', spotify:'🎵 Spotify',
  youtube:'▶️ YouTube', plugins:'🔌 Plugins',
  settings:'⚙️ Settings', audit:'🔍 Audit', sysmon:'📊 System Monitor'
};

function switchPanel(name) {
  document.querySelectorAll('.snav-btn').forEach(b => b.classList.toggle('active', b.dataset.panel === name));
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  const panel = document.getElementById('panel-' + name);
  if (panel) panel.classList.add('active');
  if (!S.sidebarOpen) toggleSidebar();
  // Open detail sidebar and set title
  openDetailSidebar(name);
  if (name === 'memory') loadMemory();
  else if (name === 'workflows') loadWorkflows();
  else if (name === 'insights') loadInsights();
  else if (name === 'reports') loadReports();
  else if (name === 'settings') loadSettings();
  else if (name === 'sysmon') loadSysmon();
  else if (name === 'audit') loadAudit();
  else if (name === 'projects') loadProjects();
  else if (name === 'notes') loadNotes();
  else if (name === 'calendar') loadCalendar();
  else if (name === 'assistant') loadAssistantPanel();
  else if (name === 'apps') loadAppsPanel();
}

function openDetailSidebar(name) {
  const dsb = document.getElementById('detail-sidebar');
  if (!dsb) return;
  dsb.classList.remove('dsb-collapsed');
  const titleEl = document.getElementById('dsb-panel-title');
  if (titleEl) titleEl.textContent = PANEL_TITLES[name] || name;
}

function closeDetailSidebar() {
  const dsb = document.getElementById('detail-sidebar');
  if (dsb) dsb.classList.add('dsb-collapsed');
  document.querySelectorAll('.snav-btn').forEach(b => b.classList.remove('active'));
}

function toggleDryRun() {
  S.dryRun = !S.dryRun;
  document.getElementById('dryrun-btn').classList.toggle('on', S.dryRun);
  document.getElementById('dryrun-btn').textContent = S.dryRun ? '🔍 DryRun ON' : '🔍 Dry';
  toast(S.dryRun ? 'Dry-run ON — plans will not execute' : 'Dry-run OFF', 'info', 2000);
}

function toggleGoalMode() {
  S.goalMode = !S.goalMode;
  const btn = document.getElementById('goal-toggle-btn');
  btn.classList.toggle('on', S.goalMode);
  btn.title = S.goalMode ? 'Goal mode ON — will decompose into sub-tasks' : 'Execute as autonomous multi-step goal';
  toast(S.goalMode ? '🎯 Goal mode ON' : 'Goal mode OFF', 'info', 1800);
}

function updateBadge(key, count) {
  const el = document.getElementById('badge-' + key);
  if (!el) return;
  if (count > 0) { el.style.display = ''; el.textContent = count > 99 ? '99+' : count; }
  else el.style.display = 'none';
}

function refreshSidePanels() {
  loadAssistantPanel();
  const activePanel = document.querySelector('.snav-btn.active');
  if (activePanel) {
    const p = activePanel.dataset.panel;
    if (['memory','insights','reports','workflows','projects','notes'].includes(p)) switchPanel(p);
  }
}

// ── Copy helpers ──────────────────────────────────────────────────────────────
function copyMsgText(btn) {
  const body = btn.closest('.msg-body');
  const textEl = body.querySelector('.msg-text');
  if (textEl) navigator.clipboard.writeText(textEl.innerText||textEl.textContent||'').then(()=>toast('Copied','ok',1500));
}
function copyReportText() {
  const el = document.getElementById('rep-full-body');
  if (el) navigator.clipboard.writeText(el.innerText||'').then(()=>toast('Report copied','ok',1500));
}

// ── Notifications ─────────────────────────────────────────────────────────────
async function loadNotifications() {
  try {
    const r = await fetch('/api/notifications?limit=30');
    const d = await r.json();
    renderNotifications(d.notifications||[]);
    const cnt = d.unread_count || 0;
    const badge = document.getElementById('notif-badge');
    if (cnt > 0) { badge.textContent = cnt; badge.classList.add('show'); }
    else badge.classList.remove('show');
    // Show browser notification for new unread items
    if (cnt > 0 && cnt > (S.notifCount||0) && Notification.permission === 'granted') {
      const newest = (d.notifications||[]).find(n => !n.read);
      if (newest) {
        new Notification('Arix — ' + (newest.title||'New notification'), {
          body: newest.message || '',
          icon: '/static/favicon.ico',
          tag: 'pacca-notif-' + newest.id,
          silent: false,
        });
      }
    }
    S.notifCount = cnt;
    // Update desktop alerts link
    const lnk = document.getElementById('desktop-notif-link');
    if (lnk) {
      if (Notification.permission === 'granted') { lnk.textContent = '✓ Desktop alerts on'; lnk.style.color = 'var(--success)'; }
      else if (Notification.permission === 'denied') { lnk.textContent = '🚫 Alerts blocked'; lnk.style.color = 'var(--danger)'; }
    }
  } catch(_){}
}

async function requestBrowserNotifications() {
  if (!('Notification' in window)) { toast('Browser notifications not supported', 'warn'); return; }
  if (Notification.permission === 'granted') { toast('Desktop notifications already enabled ✓', 'ok'); return; }
  if (Notification.permission === 'denied') { toast('Notifications blocked — enable in browser settings', 'warn'); return; }
  const perm = await Notification.requestPermission();
  if (perm === 'granted') {
    toast('Desktop notifications enabled ✓', 'ok');
    new Notification('Arix notifications active', {body: 'You\'ll be notified of reminders and alerts.', silent: true});
    loadNotifications();
  } else {
    toast('Notification permission denied', 'warn');
  }
}

function renderNotifications(notifs) {
  const list = document.getElementById('notif-list');
  const empty = document.getElementById('notif-empty');
  if (!notifs.length) { list.innerHTML = '<div id="notif-empty">No notifications</div>'; return; }
  list.innerHTML = notifs.map(n => `
    <div class="notif-item ${n.read?'':'unread'}" id="notif-${n.id}">
      <div class="notif-dot"></div>
      <div class="notif-body">
        <div class="notif-title">${esc(n.title)}</div>
        ${n.message?`<div class="notif-msg">${esc(n.message)}</div>`:''}
        <div class="notif-time">${fmtRelTime(n.created_at)}</div>
      </div>
      <button class="notif-close" onclick="dismissNotif(${n.id})">✕</button>
    </div>`).join('');
}

function toggleNotifDropdown() {
  const dd = document.getElementById('notif-dropdown');
  S.notifOpen = !S.notifOpen;
  dd.classList.toggle('show', S.notifOpen);
  if (S.notifOpen) loadNotifications();
}
function closeNotifDropdown() { document.getElementById('notif-dropdown').classList.remove('show'); S.notifOpen = false; }

async function dismissNotif(id) {
  document.getElementById('notif-'+id)?.remove();
  await fetch(`/api/notifications/${id}/dismiss`, {method:'POST'});
  loadNotifications();
}
async function dismissAllNotifs() {
  await fetch('/api/notifications/dismiss-all', {method:'POST'});
  loadNotifications(); closeNotifDropdown();
}

// ── Morning Brief ────────────────────────────────────────────────────────────
async function loadMorningBrief() {
  try {
    const r = await fetch('/api/morning-brief');
    const d = await r.json();
    if (d.total_items > 0 || d.nudges?.length) renderBriefCard(d);
    else renderWelcomeMsg();
  } catch(_) { renderWelcomeMsg(); }
}

function renderWelcomeMsg() {
  const name = S.profile?.name ? `, ${S.profile.name.split(' ')[0]}` : '';
  const hour = new Date().getHours();
  const greeting = hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening';
  const featuredApps = [
    {icon:'🎵',name:'TikTok',cmd:'Open TikTok'},
    {icon:'📸',name:'Instagram',cmd:'Open Instagram'},
    {icon:'💬',name:'WhatsApp',cmd:'Open WhatsApp messages'},
    {icon:'💼',name:'LinkedIn',cmd:'Open LinkedIn feed'},
    {icon:'📊',name:'Excel',cmd:'Open Microsoft Excel'},
    {icon:'🎥',name:'OBS Studio',cmd:'Open OBS Studio'},
    {icon:'🌐',name:'Chrome',cmd:'Open Google Chrome'},
  ];
  const pillsHtml = featuredApps.map(a =>
    `<button class="home-app-pill" onclick="setInputAndSend('${a.cmd}')"><span class="hap-icon">${a.icon}</span>${esc(a.name)}</button>`
  ).join('');

  const examples = [
    '"Delete temp files from my PC"',
    '"Open TikTok and go to upload"',
    '"Send a WhatsApp message to John saying I\'ll be late"',
    '"Open LinkedIn and check my messages"',
    '"Start recording on OBS"',
  ];
  const exIdx = Math.floor(Math.random() * examples.length);

  addSystemMsg(`<div style="max-width:660px">
    <div style="font-size:18px;font-weight:700;color:var(--text);margin-bottom:4px;letter-spacing:-.3px">${greeting}${name} 👋</div>
    <div style="font-size:12.5px;color:var(--text2);margin-bottom:12px">I'm <b style="color:var(--accent2)">Arix</b> — ready to execute tasks, open apps, manage files, browse the web, and more.</div>
    <div style="font-size:10px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.7px;margin-bottom:6px">Quick-launch</div>
    <div class="home-apps-row">${pillsHtml}<button class="home-app-pill" onclick="switchPanel('apps')" style="border-style:dashed"><span class="hap-icon">📱</span>All Apps</button></div>
    <div style="font-size:11px;color:var(--muted);background:var(--surface2);border:1px solid var(--border);border-radius:8px;padding:7px 11px;display:flex;align-items:center;gap:7px">
      <span>💡</span><span>Try: <span style="color:var(--accent2)">${examples[exIdx]}</span> — or press <b style="color:var(--text2)">⌘K</b></span>
    </div>
  </div>`);
}

function setInputAndSend(text) {
  const inp = document.getElementById('cmd-input');
  inp.value = text;
  autoResize(inp);
  inp.focus();
}

function setAppInput(text) {
  const inp = document.getElementById('cmd-input');
  inp.value = text;
  autoResize(inp);
  inp.focus();
  toast('Edit the command then press Enter to run', 'info', 2200);
}

function renderBriefCard(d) {
  const initials = S.profile?.initials || 'P';
  const div = document.createElement('div');
  div.className = 'msg msg-asst';
  const sectionsHtml = (d.sections||[]).map(s => {
    if (s.type === 'activity') return `<div class="brief-section"><div class="brief-section-title">${esc(s.title)}</div><div class="brief-text">${esc(s.text||'')}</div></div>`;
    const itemsHtml = (s.items||[]).slice(0,5).map(it => `<div class="brief-item"><span class="brief-item-dot">•</span><span>${esc(it.text||it.title||'')}</span></div>`).join('');
    return `<div class="brief-section"><div class="brief-section-title">${esc(s.title)} <span style="font-size:9px;font-weight:400;color:var(--muted)">(${s.count||s.items?.length||''})</span></div>${itemsHtml}</div>`;
  }).join('');
  const nudgesHtml = (d.nudges||[]).map(n => `<div class="brief-nudge">${n.icon||'💡'} ${esc(n.title)}: ${esc(n.message)}</div>`).join('');
  const llmHtml = d.llm_summary ? `<div class="brief-llm">${renderMD(d.llm_summary)}</div>` : '';
  div.innerHTML = `
    <div class="msg-avatar msg-avatar-logo"><img src="/static/logo.png" style="width:100%;height:100%;object-fit:cover;border-radius:50%;display:block"></div>
    <div class="msg-body">
      <div class="brief-card">
        <button class="brief-close" onclick="this.closest('.msg').remove()">✕</button>
        <div class="brief-greeting">${esc(d.greeting||'Good morning!')}</div>
        <div class="brief-date">${esc(d.date||'')} — Daily Brief</div>
        <div class="brief-sections">${sectionsHtml}</div>
        ${nudgesHtml}
        ${llmHtml}
        <button class="brief-refresh" onclick="refreshBrief()">↺ Refresh</button>
      </div>
    </div>`;
  chatThread.appendChild(div);
  scrollToBottom();
}

async function refreshBrief() {
  try {
    const r = await fetch('/api/morning-brief?force=true');
    const d = await r.json();
    chatThread.querySelectorAll('.brief-card').forEach(c => c.closest('.msg').remove());
    if (d.total_items > 0 || d.nudges?.length) renderBriefCard(d);
    toast('Brief refreshed', 'ok', 1800);
  } catch(e) { toast('Failed to refresh brief', 'err'); }
}

// ── Profile ────────────────────────────────────────────────────────────────────
async function loadProfile() {
  try {
    const r = await fetch('/api/profile');
    S.profile = await r.json();
    renderProfileSection(S.profile);
  } catch(_) {}
}

function renderProfileSection(p) {
  if (!p) return;
  const av = document.getElementById('profile-avatar');
  const nm = document.getElementById('profile-name');
  const rl = document.getElementById('profile-role');
  const initials = p.initials || (p.name ? p.name[0].toUpperCase() : 'P');
  nm.textContent = p.name || 'User';
  rl.textContent = p.role || 'Personal AI Assistant';
  // Try to show profile photo in sidebar avatar
  fetch('/api/profile/photo', {method:'HEAD'}).then(r => {
    if (r.ok) {
      av.innerHTML = `<img src="/api/profile/photo?t=${Date.now()}" style="width:100%;height:100%;object-fit:cover;border-radius:10px;display:block">`;
      av.style.background = 'none';
    } else {
      av.textContent = initials;
      av.style.background = `linear-gradient(135deg, ${p.avatar_color||'#4f8ef7'}, ${p.avatar_color||'#7eb8fa'})`;
    }
  }).catch(() => {
    av.textContent = initials;
    av.style.background = `linear-gradient(135deg, ${p.avatar_color||'#4f8ef7'}, ${p.avatar_color||'#7eb8fa'})`;
  });
}

let _pfPendingPhoto = null;

function previewProfilePhoto(input) {
  const file = input.files[0];
  if (!file) return;
  if (file.size > 5 * 1024 * 1024) { toast('Photo must be under 5 MB', 'err'); return; }
  _pfPendingPhoto = file;
  const reader = new FileReader();
  reader.onload = e => {
    const img = document.getElementById('pf-photo-img');
    const ini = document.getElementById('pf-photo-initials');
    const rm  = document.getElementById('pf-photo-remove');
    img.src = e.target.result;
    img.style.display = 'block';
    ini.style.display = 'none';
    rm.style.display = 'inline';
  };
  reader.readAsDataURL(file);
}

async function removeProfilePhoto() {
  _pfPendingPhoto = null;
  try { await fetch('/api/profile/photo', {method:'DELETE'}); } catch(_) {}
  const img = document.getElementById('pf-photo-img');
  const ini = document.getElementById('pf-photo-initials');
  const rm  = document.getElementById('pf-photo-remove');
  const ring = document.getElementById('pf-photo-ring');
  img.src = ''; img.style.display = 'none';
  ini.style.display = '';
  rm.style.display = 'none';
  document.getElementById('pf-photo-input').value = '';
  // Reset sidebar avatar
  const p = S.profile || {};
  const av = document.getElementById('profile-avatar');
  const initials = p.initials || (p.name ? p.name[0].toUpperCase() : 'P');
  av.innerHTML = initials;
  av.style.background = `linear-gradient(135deg, ${p.avatar_color||'#4f8ef7'}, ${p.avatar_color||'#7eb8fa'})`;
  toast('Photo removed', 'ok');
}

function openProfileEditor() {
  const p = S.profile || {};
  _pfPendingPhoto = null;
  document.getElementById('pf-name').value = p.name || '';
  document.getElementById('pf-role').value = p.role || '';
  document.getElementById('pf-company').value = p.company || '';
  document.getElementById('pf-tz').value = p.timezone || 'UTC';
  document.getElementById('pf-style').value = p.communication_style || 'balanced';
  // Reset photo UI then load current photo if exists
  const img = document.getElementById('pf-photo-img');
  const ini = document.getElementById('pf-photo-initials');
  const rm  = document.getElementById('pf-photo-remove');
  const initials = p.initials || (p.name ? p.name[0].toUpperCase() : 'P');
  ini.textContent = initials;
  img.src = ''; img.style.display = 'none'; ini.style.display = ''; rm.style.display = 'none';
  fetch('/api/profile/photo', {method:'HEAD'}).then(r => {
    if (r.ok) {
      img.src = `/api/profile/photo?t=${Date.now()}`;
      img.style.display = 'block';
      ini.style.display = 'none';
      rm.style.display = 'inline';
    }
  }).catch(()=>{});
  document.getElementById('profile-overlay').classList.add('show');
}
function closeProfileEditor() { document.getElementById('profile-overlay').classList.remove('show'); }
async function saveProfile() {
  const data = {
    name: document.getElementById('pf-name').value.trim(),
    role: document.getElementById('pf-role').value.trim(),
    company: document.getElementById('pf-company').value.trim(),
    timezone: document.getElementById('pf-tz').value,
    communication_style: document.getElementById('pf-style').value,
    onboarding_complete: true,
  };
  try {
    // Upload photo first if one was selected
    if (_pfPendingPhoto) {
      const fd = new FormData();
      fd.append('file', _pfPendingPhoto);
      await fetch('/api/profile/photo', {method:'POST', body: fd});
      _pfPendingPhoto = null;
    }
    const r = await fetch('/api/profile', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
    const d = await r.json();
    S.profile = d.profile;
    renderProfileSection(d.profile);
    closeProfileEditor();
    toast('Profile saved ✓', 'ok');
  } catch(e) { toast('Failed to save profile', 'err'); }
}

// ── Projects panel ────────────────────────────────────────────────────────────
let _projects = [];
async function loadProjects() {
  try {
    const r = await fetch('/api/projects');
    const d = await r.json();
    _projects = d.projects || [];
    renderProjects(_projects);
    updateBadge('projects', d.total||0);
  } catch(e) { document.getElementById('project-list').innerHTML = `<div class="panel-empty">Error loading projects</div>`; }
}

function renderProjects(projects) {
  const el = document.getElementById('project-list');
  if (!projects.length) { el.innerHTML = '<div class="panel-empty">No projects yet. Create one above!</div>'; return; }
  el.innerHTML = projects.map(p => {
    const tc = p.task_counts || {};
    const total = tc.total || 0;
    const done = tc.done || 0;
    const pct = total > 0 ? Math.round(done/total*100) : 0;
    const tasksHtml = (p.tasks||[]).map(t => `
      <div class="ptask-item">
        <div class="ptask-check ${t.status==='done'?'done':''}" onclick="toggleProjectTask(${t.id},'${t.status}')"></div>
        <span class="ptask-text ${t.status==='done'?'done':''}">${esc(t.title)}</span>
        <span class="ptask-pri ${t.priority}">${t.priority}</span>
        <button class="ptask-del" onclick="deleteProjectTask(${p.id},${t.id})">✕</button>
      </div>`).join('');
    return `<div class="project-card" id="proj-${p.id}">
      <div class="project-header">
        <div class="project-color-dot" style="background:${esc(p.color)}"></div>
        <span class="project-name">${esc(p.name)}</span>
        <span class="project-counts">${done}/${total}</span>
        <button class="project-del-btn" onclick="deleteProject(${p.id},event)">✕</button>
        <button class="project-expand-btn" onclick="toggleProject(this)">▶</button>
      </div>
      <div class="project-progress"><div class="project-progress-fill" style="width:${pct}%;background:${esc(p.color)}"></div></div>
      <div class="project-tasks">
        ${tasksHtml}
        <div class="ptask-add-row">
          <input class="ptask-add-input" id="ptask-input-${p.id}" placeholder="Add task…" onkeydown="if(event.key==='Enter')addProjectTask(${p.id})">
          <button class="ptask-add-btn" onclick="addProjectTask(${p.id})">+</button>
        </div>
      </div>
    </div>`;
  }).join('');
}

function toggleProject(btn) {
  const tasks = btn.closest('.project-card').querySelector('.project-tasks');
  tasks.classList.toggle('open');
  btn.classList.toggle('open');
}

async function createProjectFromUI() {
  const inp = document.getElementById('new-proj-input');
  const name = inp.value.trim();
  if (!name) { inp.focus(); return; }
  try {
    await fetch('/api/projects', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name})});
    inp.value = '';
    toast('Project created', 'ok');
    loadProjects();
  } catch(e) { toast('Failed to create project', 'err'); }
}

async function deleteProject(id, e) {
  e.stopPropagation();
  if (!confirm('Delete this project and all its tasks?')) return;
  await fetch(`/api/projects/${id}`, {method:'DELETE'});
  toast('Project deleted', 'ok');
  loadProjects();
}

async function addProjectTask(projectId) {
  const inp = document.getElementById(`ptask-input-${projectId}`);
  const title = (inp.value||'').trim();
  if (!title) return;
  try {
    await fetch(`/api/projects/${projectId}/tasks`, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title})});
    inp.value = '';
    loadProjects();
  } catch(e) { toast('Failed to add task', 'err'); }
}

async function toggleProjectTask(taskId, currentStatus) {
  const newStatus = currentStatus === 'done' ? 'todo' : 'done';
  try {
    await fetch(`/api/projects/0/tasks/${taskId}`, {method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({status:newStatus})});
    loadProjects();
  } catch(e) { toast('Failed to update task', 'err'); }
}

async function deleteProjectTask(projectId, taskId) {
  await fetch(`/api/projects/${projectId}/tasks/${taskId}`, {method:'DELETE'});
  loadProjects();
}

// ── Notes panel ───────────────────────────────────────────────────────────────
let _currentNoteId = null;
async function loadNotes(search) {
  try {
    const q = search ? `?search=${encodeURIComponent(search)}` : '';
    const r = await fetch('/api/notes' + q);
    const d = await r.json();
    renderNotes(d.notes||[]);
    updateBadge('notes', d.total||0);
  } catch(e) { document.getElementById('notes-list').innerHTML = '<div class="panel-empty">Error loading notes</div>'; }
}

function renderNotes(notes) {
  const el = document.getElementById('notes-list');
  if (!notes.length) { el.innerHTML = '<div class="panel-empty">No notes yet. Create one above!</div>'; return; }
  el.innerHTML = notes.map(n => {
    const preview = (n.content||'').replace(/[#*`_\[\]]/g,'').slice(0,80);
    const tagsHtml = (n.tags||[]).map(t=>`<span class="note-tag">${esc(t)}</span>`).join('');
    const d = new Date(n.updated_at*1000).toLocaleDateString();
    return `<div class="note-card ${n.pinned?'pinned':''}" onclick="openNoteEditor(${JSON.stringify(n)})">
      <div class="note-title">${n.pinned?'<span class="note-pin-icon">📌</span>':''}${esc(n.title)}</div>
      ${preview?`<div class="note-preview">${esc(preview)}</div>`:''}
      <div class="note-meta">${tagsHtml}<span class="note-date">${d}</span>
        <button class="note-del-btn" title="${n.pinned?'Unpin':'Pin'}" onclick="toggleNotePin(event,${n.id},${n.pinned?'true':'false'})">${n.pinned?'📌':'📍'}</button>
        <button class="note-del-btn" onclick="deleteNote(event,${n.id})">✕</button>
      </div>
    </div>`;
  }).join('');
}

async function toggleNotePin(e, id, currentlyPinned) {
  e.stopPropagation();
  try {
    await fetch(`/api/notes/${id}`, {method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({pinned:!currentlyPinned})});
    toast(currentlyPinned ? 'Note unpinned' : 'Note pinned 📌', 'ok');
    loadNotes();
  } catch(e) { toast('Failed to update note', 'err'); }
}

function openNoteEditor(note) {
  _currentNoteId = note ? note.id : null;
  document.getElementById('note-title-input').value = note ? note.title : '';
  document.getElementById('note-content-input').value = note ? note.content : '';
  document.getElementById('note-tags-input').value = note ? (note.tags||[]).join(', ') : '';
  document.getElementById('notes-list-view').style.display = 'none';
  document.getElementById('note-editor').classList.add('open');
}
function closeNoteEditor() {
  document.getElementById('notes-list-view').style.display = '';
  document.getElementById('note-editor').classList.remove('open');
  _currentNoteId = null;
}

async function saveNoteFromUI() {
  const title = document.getElementById('note-title-input').value.trim();
  if (!title) { toast('Title required', 'warn'); return; }
  const content = document.getElementById('note-content-input').value;
  const tags = document.getElementById('note-tags-input').value.split(',').map(t=>t.trim()).filter(Boolean);
  try {
    if (_currentNoteId) {
      await fetch(`/api/notes/${_currentNoteId}`, {method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({title,content,tags})});
    } else {
      await fetch('/api/notes', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title,content,tags})});
    }
    toast(_currentNoteId ? 'Note updated ✓' : 'Note saved ✓', 'ok');
    closeNoteEditor(); loadNotes();
  } catch(e) { toast('Failed to save note', 'err'); }
}

async function deleteNote(e, id) {
  e.stopPropagation();
  await fetch(`/api/notes/${id}`, {method:'DELETE'});
  toast('Note deleted', 'ok'); loadNotes();
}

function searchNotes(q) { clearTimeout(searchNotes._t); searchNotes._t = setTimeout(() => loadNotes(q), 300); }

// ── Calendar panel ────────────────────────────────────────────────────────────
let _calConfigured = false;

async function loadCalendar() {
  try {
    const r = await fetch('/api/calendar/status');
    const d = await r.json();
    _calConfigured = d.configured;
    const badge = document.getElementById('cal-status-badge');
    const addBtn = document.getElementById('cal-add-btn');
    if (!d.configured) {
      if (badge) { badge.className='cal-status-badge disconnected'; badge.textContent='⚪ Not connected'; }
      if (addBtn) addBtn.style.display='none';
      document.getElementById('cal-content').innerHTML = `
        <div class="cal-setup">
          <div class="cal-setup-title">📅 Google Calendar — Not Connected</div>
          <ol class="cal-setup-steps">
            <li>Go to <a href="https://console.cloud.google.com/" target="_blank">Google Cloud Console</a> and enable the <strong>Google Calendar API</strong></li>
            <li>Create <strong>OAuth 2.0 credentials</strong> (Desktop app type) → download the JSON</li>
            <li>Use <a href="https://developers.google.com/oauthplayground/" target="_blank">OAuth Playground</a> to get a refresh token<br>
              <span style="font-size:10px;color:var(--muted)">Scope: https://www.googleapis.com/auth/calendar</span></li>
            <li>Add these three secrets in <strong>Replit → Secrets</strong>:<br>
              <span class="cal-setup-copy">GOOGLE_CALENDAR_CLIENT_ID</span><br>
              <span class="cal-setup-copy">GOOGLE_CALENDAR_CLIENT_SECRET</span><br>
              <span class="cal-setup-copy">GOOGLE_CALENDAR_REFRESH_TOKEN</span></li>
            <li>Restart the app — Calendar will connect automatically</li>
          </ol>
        </div>`;
      return;
    }
    if (badge) { badge.className='cal-status-badge connected'; badge.textContent='🟢 Connected'; }
    if (addBtn) addBtn.style.display='';
    await loadCalendarEvents();
  } catch(e) {
    document.getElementById('cal-content').innerHTML = '<div class="panel-empty">Error loading calendar</div>';
  }
}

async function loadCalendarEvents() {
  const el = document.getElementById('cal-content');
  if (!_calConfigured) return;
  el.innerHTML = '<div class="panel-empty">Loading events…</div>';
  const days = document.getElementById('cal-days-select')?.value || 7;
  try {
    const r2 = await fetch(`/api/calendar/events?days=${days}`);
    const d2 = await r2.json();
    if (!d2.ok) { el.innerHTML = `<div class="panel-empty">⚠️ ${esc(d2.error||'Unknown error')}</div>`; return; }
    const events = d2.events || [];
    if (!events.length) { el.innerHTML = `<div class="panel-empty">No events in the next ${days} day${days>1?'s':''}.</div>`; return; }

    // Group by day
    const byDay = {};
    for (const ev of events) {
      const start = ev.start ? new Date(ev.start) : null;
      const dayKey = start ? start.toLocaleDateString([],{weekday:'long',month:'long',day:'numeric'}) : 'No date';
      if (!byDay[dayKey]) byDay[dayKey] = [];
      byDay[dayKey].push({...ev, _startDate: start});
    }

    let html = '';
    for (const [day, evs] of Object.entries(byDay)) {
      html += `<div class="cal-day-header">${esc(day)}</div>`;
      for (const ev of evs) {
        const timeStr = ev._startDate
          ? (ev.all_day ? 'All day' : ev._startDate.toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'}))
          : '';
        const endDate = ev.end ? new Date(ev.end) : null;
        const endStr = endDate && !ev.all_day ? ' – ' + endDate.toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'}) : '';
        html += `<div class="cal-event">
          <button class="cal-event-del" onclick="deleteCalEvent('${esc(ev.id||'')}', this)" title="Delete event">✕</button>
          <div class="cal-event-title">${esc(ev.title)}</div>
          <div class="cal-event-time">🕐 ${esc(timeStr+endStr)}</div>
          ${ev.location?`<div class="cal-event-loc">📍 ${esc(ev.location)}</div>`:''}
          ${ev.description?`<div class="cal-event-loc" style="color:var(--muted)">💬 ${esc(ev.description.slice(0,80))}</div>`:''}
          ${ev.meeting_link?`<a href="${esc(ev.meeting_link)}" target="_blank" style="font-size:10px;color:var(--accent);display:block;margin-top:3px">🎥 Join meeting</a>`:''}
        </div>`;
      }
    }
    el.innerHTML = html;
  } catch(e) {
    el.innerHTML = '<div class="panel-empty">Error loading events</div>';
  }
}

function toggleCalAddForm() {
  const f = document.getElementById('cal-add-form');
  f.classList.toggle('open');
  if (f.classList.contains('open')) {
    // Default start = now + 1h, end = now + 2h
    const now = new Date();
    const pad = n => String(n).padStart(2,'0');
    const fmt = d => `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
    const s = new Date(now.getTime() + 3600000);
    const e = new Date(now.getTime() + 7200000);
    document.getElementById('cal-start').value = fmt(s);
    document.getElementById('cal-end').value = fmt(e);
    document.getElementById('cal-title').focus();
  }
}

async function submitCalEvent() {
  const title = document.getElementById('cal-title').value.trim();
  const start = document.getElementById('cal-start').value;
  const end   = document.getElementById('cal-end').value;
  if (!title) { toast('Event title is required', 'warn'); return; }
  if (!start) { toast('Start time is required', 'warn'); return; }
  const body = {
    title,
    start: start + ':00',
    end:   (end || start) + ':00',
    location: document.getElementById('cal-location').value.trim(),
    description: document.getElementById('cal-desc').value.trim(),
  };
  try {
    const r = await fetch('/api/calendar/events', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
    const d = await r.json();
    if (d.ok) {
      toast('Event created ✓', 'success');
      document.getElementById('cal-title').value='';
      document.getElementById('cal-location').value='';
      document.getElementById('cal-desc').value='';
      document.getElementById('cal-add-form').classList.remove('open');
      await loadCalendarEvents();
    } else {
      toast('Failed: ' + (d.error||'Unknown'), 'error');
    }
  } catch(e) { toast('Network error', 'error'); }
}

async function deleteCalEvent(eventId, btn) {
  if (!eventId) { toast('No event ID', 'warn'); return; }
  if (!confirm('Delete this event from Google Calendar?')) return;
  try {
    const r = await fetch(`/api/calendar/events/${encodeURIComponent(eventId)}`, {method:'DELETE'});
    const d = await r.json();
    if (d.ok) { toast('Event deleted', 'success'); await loadCalendarEvents(); }
    else toast('Delete failed: ' + (d.error||'Unknown'), 'error');
  } catch(e) { toast('Network error', 'error'); }
}

// ── Memory panel ──────────────────────────────────────────────────────────────
async function loadMemory() {
  try {
    const r = await fetch('/api/memory?limit=25');
    const d = await r.json();
    renderMemory(d);
  } catch(e){}
}

function renderMemory(d) {
  const cnt = d.task_count || 0;
  document.getElementById('mem-count-label').innerHTML = `🧠 ${cnt} memories stored`;
  updateBadge('mem', cnt);
  const tasks = d.recent_tasks || [];
  const el = document.getElementById('mem-list');
  if (!tasks.length) { el.innerHTML = '<div class="panel-empty">No tasks remembered yet.</div>'; }
  else el.innerHTML = tasks.map(t => {
    const ok = t.outcome === 'completed';
    const d2 = new Date(t.created_at*1000).toLocaleDateString();
    return `<div class="mem-task-item">
      <div class="mem-task-cmd">${esc((t.command||'').slice(0,90))}</div>
      <div class="mem-task-meta">
        <span class="mem-outcome ${ok?'ok':'fail'}">${ok?'✓':'✗'} ${esc(t.outcome||'')}</span>
        <span>${esc(t.intent_domain||'')}</span>
        <span>${d2}</span>
      </div>
    </div>`;
  }).join('');
  const prefs = d.preferences || {};
  const prefEl = document.getElementById('pref-section');
  const prefKeys = Object.keys(prefs);
  if (prefKeys.length) {
    prefEl.innerHTML = `<div class="panel-title" style="margin-top:8px">Learned Preferences</div>` +
      prefKeys.map(k => `<div class="pref-item"><span class="pref-key">${esc(k)}</span><span class="pref-val">${esc(String(prefs[k]).slice(0,60))}</span></div>`).join('');
  }
}

async function searchMemory(q) {
  clearTimeout(searchMemory._t);
  searchMemory._t = setTimeout(async () => {
    if (!q) { loadMemory(); return; }
    try {
      const r = await fetch('/api/memory/search?q=' + encodeURIComponent(q) + '&top_k=10');
      const d = await r.json();
      const el = document.getElementById('mem-list');
      const results = d.results||[];
      el.innerHTML = results.length ? results.map(r2=>
        `<div class="mem-task-item"><div class="mem-task-cmd">${esc((r2.content||'').slice(0,90))}</div><div class="mem-task-meta"><span style="color:var(--accent)">score: ${(r2.score||0).toFixed(2)}</span></div></div>`
      ).join('') : '<div class="panel-empty">No matches found.</div>';
    } catch(_){}
  }, 300);
}

// ── Memory actions ────────────────────────────────────────────────────────────
async function triggerMemoryCompress() {
  const btn = event.currentTarget;
  const orig = btn.textContent;
  btn.textContent = '⏳ Compressing…';
  btn.disabled = true;
  try {
    const r = await fetch('/api/memory/compress?days=7', {method:'POST'});
    const d = await r.json();
    if (d.error) {
      showToast('❌ Compress failed: ' + d.error, 'error');
    } else if (d.compressed === 0) {
      showToast('ℹ️ Nothing to compress — no tasks older than 7 days', 'info');
    } else {
      showToast(`🗜️ Compressed ${d.compressed} task(s) across ${d.groups} group(s) into memory`, 'success');
      loadMemory();
    }
  } catch(e) {
    showToast('❌ Compress error: ' + e.message, 'error');
  } finally {
    btn.textContent = orig;
    btn.disabled = false;
  }
}

async function triggerDetectPrefs() {
  const btn = event.currentTarget;
  const orig = btn.textContent;
  btn.textContent = '⏳ Scanning…';
  btn.disabled = true;
  try {
    const r = await fetch('/api/memory/detect-preferences', {method:'POST'});
    const d = await r.json();
    if (d.count > 0) {
      showToast(`🔍 Detected ${d.count} implicit preference(s)`, 'success');
      loadMemory();
    } else {
      showToast('ℹ️ No new implicit preferences detected yet', 'info');
    }
  } catch(e) {
    showToast('❌ Detect prefs error: ' + e.message, 'error');
  } finally {
    btn.textContent = orig;
    btn.disabled = false;
  }
}

// ── Workflows panel ───────────────────────────────────────────────────────────
async function loadWorkflows() {
  try {
    const r = await fetch('/api/workflows');
    const d = await r.json();
    const wfs = d.workflows||[];
    updateBadge('wf', wfs.length);
    renderWorkflows(wfs);
  } catch(e){}
}

function renderWorkflows(wfs) {
  const el = document.getElementById('wf-list');
  if (!wfs.length) { el.innerHTML = '<div class="panel-empty">No workflows. Create one above!</div>'; return; }
  el.innerHTML = wfs.map(w => {
    const lastRun = w.last_run ? fmtRelTime(w.last_run) : 'never';
    return `<div class="wf-item">
      <div class="wf-header">
        <span class="wf-name">${esc(w.name)}</span>
        <button class="wf-toggle ${w.enabled?'enabled':''}" onclick="toggleWorkflow('${esc(w.workflow_id)}',${!w.enabled})">${w.enabled?'Enabled':'Disabled'}</button>
        <button class="wf-del" onclick="deleteWorkflow('${esc(w.name)}')">✕</button>
      </div>
      <div class="wf-meta">
        <span class="wf-type-badge">${esc(w.trigger?.type||'manual')}</span>
        ${w.trigger?.schedule?`<span>${esc(w.trigger.schedule)}</span>`:''}
        <span>Runs: ${w.run_count||0}</span>
        <span>Last: ${lastRun}</span>
      </div>
    </div>`;
  }).join('');
}

async function createWorkflowFromUI() {
  const inp = document.getElementById('wf-input');
  const cmd = inp.value.trim();
  if (!cmd) { inp.focus(); return; }
  try {
    const r = await fetch('/api/workflows', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({command:cmd})});
    const d = await r.json();
    if (d.status==='ok') { inp.value=''; toast('Workflow created','ok'); loadWorkflows(); }
    else toast('Could not parse workflow command','warn');
  } catch(e){ toast('Failed','err'); }
}

async function deleteWorkflow(name) {
  await fetch(`/api/workflows/${encodeURIComponent(name)}`, {method:'DELETE'});
  toast('Workflow deleted','ok'); loadWorkflows();
}

async function toggleWorkflow(id, enabled) {
  await fetch(`/api/workflows/${id}/toggle`, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({enabled})});
  loadWorkflows();
}

// ── Insights panel ────────────────────────────────────────────────────────────
const GOAL_TEMPLATES = [
  {icon:'🔬',label:'Research AI tools and save a report',cmd:'research_topic: best AI development tools 2026'},
  {icon:'🌿',label:'Git status → add → commit',cmd:'check git status then add all changed files then commit'},
  {icon:'📁',label:'Organize downloads folder',cmd:'list files in ~/Downloads and find large files'},
  {icon:'📊',label:'System health check',cmd:'system monitor'},
  {icon:'💻',label:'Generate and explain code',cmd:'generate_code: '},
  {icon:'🌐',label:'Browse and screenshot a site',cmd:'browser_open_url: https://news.ycombinator.com'},
];

async function loadInsights() {
  const panel = document.getElementById('panel-insights');
  try {
    const r = await fetch('/api/memory/stats');
    const d = await r.json();
    if (d.error || !d.total_tasks) {
      panel.innerHTML = `<div class="panel-empty" style="text-align:left">No insights yet. Complete some tasks first!<br><br>
        <div class="panel-title" style="margin-top:12px">Goal Templates</div>
        ${GOAL_TEMPLATES.map(t=>`<div class="insight-goal-pill" onclick="qa('${esc(t.cmd)}')"><span class="pill-icon">${t.icon}</span>${esc(t.label)}</div>`).join('')}
      </div>`;
      return;
    }
    const total=d.total_tasks||0, rate=d.success_rate||0, avg=d.avg_steps||0;
    const domains=d.domains||[], daily=d.daily_activity||[], recent=d.recent_commands||[];
    const maxDay = Math.max(...daily.map(x=>x.count),1);
    const chartBars = daily.slice(0,14).reverse().map(x=>{
      const h=Math.round(x.count/maxDay*36)+2;
      return `<div class="day-bar" style="height:${h}px" title="${x.day}: ${x.count}"></div>`;
    }).join('');
    const domRows = domains.slice(0,8).map(x=>{
      const w=Math.round(x.count/Math.max(...domains.map(d=>d.count),1)*100);
      const rc=x.success_rate>=80?'high':x.success_rate>=50?'mid':'low';
      return `<div class="domain-row"><div class="domain-name">${esc(x.domain)}</div><div class="domain-bar-wrap"><div class="domain-bar-fill" style="width:${w}%"></div></div><div class="domain-count">${x.count}</div><div class="domain-rate ${rc}">${x.success_rate}%</div></div>`;
    }).join('');
    panel.innerHTML = `
      <div class="insights-section">
        <div class="insight-stat-row">
          <div class="insight-stat-card"><div class="insight-stat-val">${total}</div><div class="insight-stat-lbl">Total Tasks</div></div>
          <div class="insight-stat-card"><div class="insight-stat-val ${rate>=80?'green':rate>=50?'yellow':''}">${rate}%</div><div class="insight-stat-lbl">Success Rate</div></div>
          <div class="insight-stat-card"><div class="insight-stat-val" style="color:var(--muted)">${avg}</div><div class="insight-stat-lbl">Avg Steps</div></div>
          <div class="insight-stat-card"><div class="insight-stat-val" style="color:var(--accent2)">${d.semantic_memory_count||0}</div><div class="insight-stat-lbl">Memories</div></div>
          <div class="insight-stat-card"><div class="insight-stat-val" style="color:var(--accent)">${d.vector_embedding_count||0}</div><div class="insight-stat-lbl">Vectors</div></div>
        </div>
        <div style="font-size:10px;color:var(--muted);margin-top:4px;text-align:right">
          Search: <span style="color:${(d.search_mode||'tfidf')==='vector'?'var(--accent)':'var(--muted)'};font-weight:600">${(d.search_mode||'tfidf')==='vector'?'⚡ Neural ('+esc(d.vector_provider||'')+')':'🔡 TF-IDF'}</span>
        </div>
      </div>
      ${daily.length?`<div class="insights-section"><div class="insights-section-title">14-Day Activity</div><div class="daily-chart">${chartBars}</div></div>`:''}
      ${domRows?`<div class="insights-section"><div class="insights-section-title">By Domain</div>${domRows}</div>`:''}
      ${recent.length?`<div class="insights-section"><div class="insights-section-title">Recent Commands</div>${recent.map(c=>`<div class="recent-cmd-item" onclick="qa('${esc(c)}')">${esc(c)}</div>`).join('')}</div>`:''}
      <div class="insights-section"><div class="insights-section-title">Goal Templates</div>${GOAL_TEMPLATES.map(t=>`<div class="insight-goal-pill" onclick="qa('${esc(t.cmd)}')"><span class="pill-icon">${t.icon}</span>${esc(t.label)}</div>`).join('')}</div>
      <button class="insights-refresh-btn" onclick="loadInsights()">↺ Refresh</button>`;
  } catch(e){ panel.innerHTML='<div class="panel-empty">Error loading insights</div>'; }
}

function qa(cmd) {
  const inp = document.getElementById('cmd-input');
  inp.value = cmd; inp.focus(); autoResize(inp);
  if (S.termMode) toggleDevMode();
}

// ── Reports panel ─────────────────────────────────────────────────────────────
async function loadReports() {
  try {
    const r = await fetch('/api/reports?limit=30');
    const d = await r.json();
    const el = document.getElementById('reports-list');
    const reps = d.reports||[];
    if (!reps.length) { el.innerHTML = '<div class="panel-empty">No research reports yet.</div>'; return; }
    el.innerHTML = reps.map(r2 => {
      const d2 = new Date(r2.created_at*1000).toLocaleDateString();
      return `<div class="report-item" onclick="viewReport(${r2.id})">
        <div class="report-title">${esc(r2.topic)}</div>
        <div class="report-meta"><span>${d2}</span><span>${r2.sources_count||0} sources</span><button onclick="event.stopPropagation();deleteReport(${r2.id})" style="margin-left:auto;background:transparent;border:none;color:var(--muted);cursor:pointer;font-size:11px">✕</button></div>
      </div>`;
    }).join('');
  } catch(e){}
}

async function viewReport(id) {
  try {
    const r = await fetch(`/api/reports/${id}`);
    const d = await r.json();
    document.getElementById('rep-full-title').textContent = d.topic||'Report';
    document.getElementById('rep-full-body').innerHTML = typeof marked !== 'undefined' ? marked.parse(d.content||'') : `<pre>${esc(d.content||'')}</pre>`;
    document.getElementById('rep-full-overlay').classList.add('show');
  } catch(e){ toast('Failed to load report','err'); }
}
function closeReport() { document.getElementById('rep-full-overlay').classList.remove('show'); }
async function deleteReport(id) {
  await fetch(`/api/reports/${id}`, {method:'DELETE'});
  toast('Report deleted','ok'); loadReports();
}

// ── History / Audit ────────────────────────────────────────────────────────────
async function loadHistory() {
  try {
    const r = await fetch('/api/task-history?n=20');
    const d = await r.json();
    // used by terminal mode; not shown in chat but kept for compat
  } catch(_){}
}

async function loadAudit() {
  try {
    const r = await fetch('/api/audit-log?n=30');
    const d = await r.json();
    const el = document.getElementById('audit-list');
    const entries = d.entries||[];
    if (!entries.length) { el.innerHTML = '<div class="panel-empty">No audit entries.</div>'; return; }
    el.innerHTML = entries.map(e2 => {
      const t = e2.ts ? new Date(e2.ts*1000).toLocaleTimeString() : '';
      return `<div class="audit-entry">
        <span class="audit-time">${esc(t)}</span>
        <span class="audit-action"> ${esc(e2.action||e2.event||'')}</span>
        <span class="audit-detail"> ${esc((e2.detail||e2.tool||e2.command||'').toString().slice(0,60))}</span>
      </div>`;
    }).join('');
  } catch(e){}
}

// ── Sysmon ────────────────────────────────────────────────────────────────────
async function loadSysmon() {
  try {
    const r = await fetch('/api/sysmon');
    const d = await r.json();
    if (d.error) { document.getElementById('sysmon-content').innerHTML = `<div class="panel-empty">${esc(d.error)}</div>`; return; }
    const cpu = d.cpu_percent||0, ram = d.virtual_memory||{};
    const ramPct = ram.percent||0;
    const cpuCls = cpu>80?'#f04b4b':cpu>50?'#f59e0b':'var(--accent)';
    const ramCls = ramPct>80?'#f04b4b':ramPct>50?'#f59e0b':'var(--accent2)';
    // update header stats
    const cpuBar = document.getElementById('cpu-bar');
    const ramBar = document.getElementById('ram-bar');
    const cpuVal = document.getElementById('cpu-val');
    const ramVal = document.getElementById('ram-val');
    if (cpuBar) { cpuBar.style.width=cpu+'%'; cpuBar.style.background=cpuCls; }
    if (ramBar) { ramBar.style.width=ramPct+'%'; ramBar.style.background=ramCls; }
    if (cpuVal) { cpuVal.textContent=cpu+'%'; cpuVal.className='stat-val '+(cpu>80?'crit':cpu>50?'warn':'ok'); }
    if (ramVal) { ramVal.textContent=ramPct+'%'; ramVal.className='stat-val '+(ramPct>80?'crit':ramPct>50?'warn':'ok'); }
    const procs = d.top_processes||[];
    const procsHtml = procs.slice(0,10).map(p=>`<div class="proc-row"><div class="proc-name">${esc(p.name||p.pid)}</div><div class="proc-cpu">${(p.cpu_percent||0).toFixed(1)}%</div><div class="proc-mem">${(p.memory_percent||0).toFixed(1)}%</div></div>`).join('');
    document.getElementById('sysmon-content').innerHTML = `
      <div class="sysmon-card"><div class="sysmon-title">CPU</div><div class="sysmon-val" style="color:${cpuCls}">${cpu}%</div><div class="sysmon-bar"><div class="sysmon-fill" style="width:${cpu}%;background:${cpuCls}"></div></div></div>
      <div class="sysmon-card"><div class="sysmon-title">RAM</div><div class="sysmon-val" style="color:${ramCls}">${ramPct}% <span style="font-size:12px;font-weight:400;color:var(--muted)">(${Math.round((ram.used||0)/1073741824*10)/10} / ${Math.round((ram.total||0)/1073741824*10)/10} GB)</span></div><div class="sysmon-bar"><div class="sysmon-fill" style="width:${ramPct}%;background:${ramCls}"></div></div></div>
      ${procs.length?`<div class="sysmon-card"><div class="sysmon-title">Top Processes</div><div class="proc-row" style="font-weight:700"><div class="proc-name">Name</div><div class="proc-cpu">CPU</div><div class="proc-mem">MEM</div></div>${procsHtml}</div>`:''}`;
  } catch(e){}
}

function startSysmon() {
  loadSysmon();
  if (!S.sysMonInterval) S.sysMonInterval = setInterval(loadSysmon, 15000);
}

// ── Settings panel ────────────────────────────────────────────────────────────
async function loadSettings() {
  try {
    const r = await fetch('/api/status');
    const d = await r.json();
    renderSettings(d);
  } catch(e){}
}

function renderSettings(d) {
  const panel = document.getElementById('panel-settings');
  panel.innerHTML = `
    <div class="setting-group">
      <label class="setting-label">AI Provider</label>
      <select class="setting-select" id="cfg-provider" onchange="updateProviderModel()">
        <option value="anthropic" ${d.provider==='anthropic'?'selected':''}>Anthropic (Claude)</option>
        <option value="openai" ${d.provider==='openai'?'selected':''}>OpenAI (GPT)</option>
        <option value="gemini" ${d.provider==='gemini'?'selected':''}>Google (Gemini)</option>
      </select>
    </div>
    <div class="setting-group">
      <label class="setting-label">Model</label>
      <input class="setting-input" id="cfg-model" value="${esc(d.model||'')}">
    </div>
    <div class="setting-divider"></div>
    <div class="setting-group">
      <label class="setting-label">Risk Confirm Threshold: <span id="risk-conf-val">${d.risk_confirm_threshold||100}</span></label>
      <input class="setting-range" type="range" min="10" max="200" step="5" value="${d.risk_confirm_threshold||100}" oninput="document.getElementById('risk-conf-val').textContent=this.value" id="cfg-risk-confirm">
      <div class="setting-desc">Actions scoring above this require YES/NO confirmation</div>
    </div>
    <div class="setting-group">
      <label class="setting-label">Risk Proceed Threshold: <span id="risk-proc-val">${d.risk_proceed_threshold||30}</span></label>
      <input class="setting-range" type="range" min="5" max="100" step="5" value="${d.risk_proceed_threshold||30}" oninput="document.getElementById('risk-proc-val').textContent=this.value" id="cfg-risk-proceed">
      <div class="setting-desc">Actions below this proceed without acknowledgment</div>
    </div>
    <button class="settings-save-btn" onclick="saveSettings()">Save Settings</button>
    <div class="setting-divider"></div>
    <div style="font-size:10px;color:var(--muted);line-height:1.6">
      <div>LLM: <span style="color:${d.llm_available?'var(--success)':'var(--danger)'}">${d.llm_available?'✓ Connected':'✗ Not connected'}</span></div>
      ${d.llm_error?`<div style="color:var(--danger);margin-top:3px">${esc(d.llm_error)}</div>`:''}
      <div style="margin-top:6px">v${esc(d.version||'7.0.0')} · ${d.tool_count||0} tools</div>
    </div>`;
}

async function saveSettings() {
  const body = {
    provider: document.getElementById('cfg-provider').value,
    model: document.getElementById('cfg-model').value,
    risk_confirm_threshold: parseFloat(document.getElementById('cfg-risk-confirm').value),
    risk_proceed_threshold: parseFloat(document.getElementById('cfg-risk-proceed').value),
  };
  try {
    await fetch('/api/settings', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    toast('Settings saved ✓', 'ok');
    loadSettings();
  } catch(e){ toast('Failed to save','err'); }
}

// ── Assistant panel (todo + reminders) ───────────────────────────────────────
async function loadAssistantPanel() {
  try {
    const [todosRes, remsRes] = await Promise.all([fetch('/api/todos?include_done=false'), fetch('/api/reminders')]);
    const todosData = await todosRes.json();
    const remsData = await remsRes.json();
    renderTodoList(todosData.todos||[]);
    renderReminderList(remsData.reminders||[]);
    // Quick actions
    buildQuickActionList();
  } catch(e){}
}

function buildQuickActionList() {
  const el = document.getElementById('quick-action-list');
  const actions = [
    {icon:'🌄',label:'Morning Brief',action:()=>loadMorningBrief()},
    {icon:'📱',label:'Apps',action:()=>switchPanel('apps')},
    {icon:'📈',label:'Activity Insights',action:()=>switchPanel('insights')},
    {icon:'🧠',label:'Search Memory',action:()=>switchPanel('memory')},
    {icon:'🔄',label:'View Workflows',action:()=>switchPanel('workflows')},
    {icon:'📊',label:'System Monitor',action:()=>switchPanel('sysmon')},
  ];
  el.innerHTML = `<div style="display:grid;grid-template-columns:1fr 1fr;gap:5px">${actions.map(a=>`<button class="panel-btn" onclick="(${a.action.toString()})()">${a.icon} ${esc(a.label)}</button>`).join('')}</div>`;
}

// ── Apps Panel ────────────────────────────────────────────────────────────────
const APP_CATALOG = [
  {
    category: 'Social Media',
    apps: [
      { icon: '🎵', name: 'TikTok',     actions: [['Open','Open TikTok'],['Upload','Open TikTok upload page'],['Messages','Open TikTok messages']] },
      { icon: '📸', name: 'Instagram',  actions: [['Open','Open Instagram'],['Reels','Open Instagram reels'],['DMs','Open Instagram messages']] },
      { icon: '💬', name: 'WhatsApp',   actions: [['Open','Open WhatsApp'],['New message','Send a WhatsApp message to '],['Groups','Open WhatsApp groups']] },
      { icon: '💼', name: 'LinkedIn',   actions: [['Feed','Open LinkedIn feed'],['Jobs','Open LinkedIn job search'],['Messages','Open LinkedIn messages']] },
      { icon: '👥', name: 'Facebook',   actions: [['Open','Open Facebook'],['Messages','Open Facebook Messenger'],['Marketplace','Open Facebook Marketplace']] },
      { icon: '🐦', name: 'X / Twitter',actions: [['Home','Open Twitter home'],['Compose','Compose a tweet'],['DMs','Open Twitter messages']] },
      { icon: '👻', name: 'Snapchat',   actions: [['Open','Open Snapchat']] },
      { icon: '💬', name: 'Discord',    actions: [['Open','Open Discord'],['Messages','Open Discord messages']] },
      { icon: '✈️', name: 'Telegram',   actions: [['Open','Open Telegram'],['Messages','Open Telegram messages']] },
    ]
  },
  {
    category: 'Productivity',
    apps: [
      { icon: '📧', name: 'Gmail',         actions: [['Inbox','Open Gmail inbox'],['Compose','Compose a new email in Gmail'],['Sent','Open Gmail sent mail']] },
      { icon: '📂', name: 'Google Drive',  actions: [['Open','Open Google Drive'],['New doc','Open Google Docs new document']] },
      { icon: '📄', name: 'Google Docs',   actions: [['Open','Open Google Docs'],['New','Create a new Google Doc']] },
      { icon: '📊', name: 'Google Sheets', actions: [['Open','Open Google Sheets'],['New','Create a new Google Sheet']] },
      { icon: '📝', name: 'Notion',        actions: [['Open','Open Notion'],['New page','Open Notion and create a new page']] },
      { icon: '💬', name: 'Slack',         actions: [['Open','Open Slack'],['Messages','Open Slack messages']] },
      { icon: '📹', name: 'Zoom',          actions: [['Open','Open Zoom'],['New meeting','Start a new Zoom meeting']] },
      { icon: '🗂️', name: 'Trello',        actions: [['Open','Open Trello']] },
    ]
  },
  {
    category: 'Office',
    apps: [
      { icon: '📊', name: 'Excel',       actions: [['Open','Open Microsoft Excel'],['New workbook','Open Excel and create a new workbook'],['Recent','Open Excel recent files']] },
      { icon: '📝', name: 'Word',        actions: [['Open','Open Microsoft Word'],['New doc','Open Word and create a new document']] },
      { icon: '📑', name: 'PowerPoint',  actions: [['Open','Open Microsoft PowerPoint'],['New','Open PowerPoint and create a new presentation']] },
      { icon: '📓', name: 'OneNote',     actions: [['Open','Open Microsoft OneNote']] },
      { icon: '📬', name: 'Outlook',     actions: [['Open','Open Microsoft Outlook'],['Compose','Compose a new email in Outlook']] },
    ]
  },
  {
    category: 'Creative & Media',
    apps: [
      { icon: '🎥', name: 'OBS Studio',     actions: [['Open','Open OBS Studio'],['Start recording','Open OBS Studio and start recording'],['Stream','Open OBS Studio and start streaming']] },
      { icon: '▶️', name: 'YouTube',        actions: [['Open','Open YouTube'],['Studio','Open YouTube Studio'],['Upload','Open YouTube upload page']] },
      { icon: '🎵', name: 'Spotify',        actions: [['Open','Open Spotify'],['Search','Open Spotify and search for ']] },
      { icon: '🎬', name: 'Netflix',        actions: [['Open','Open Netflix'],['Search','Open Netflix and search for ']] },
      { icon: '🎮', name: 'Twitch',         actions: [['Open','Open Twitch'],['Dashboard','Open Twitch streaming dashboard']] },
      { icon: '🎨', name: 'Canva',          actions: [['Open','Open Canva'],['New design','Open Canva and create a new design']] },
      { icon: '✏️', name: 'Figma',          actions: [['Open','Open Figma']] },
    ]
  },
  {
    category: 'Browsers',
    apps: [
      { icon: '🌐', name: 'Chrome',   actions: [['Open','Open Google Chrome'],['Search','Search the web for '],['New tab','Open Google Chrome new tab']] },
      { icon: '🦊', name: 'Firefox',  actions: [['Open','Open Firefox'],['Search','Open Firefox and search for ']] },
      { icon: '🔵', name: 'Edge',     actions: [['Open','Open Microsoft Edge']] },
      { icon: '🦁', name: 'Brave',    actions: [['Open','Open Brave browser']] },
    ]
  },
  {
    category: 'Developer Tools',
    apps: [
      { icon: '💻', name: 'VS Code',   actions: [['Open','Open Visual Studio Code'],['Current folder','Open VS Code in current folder']] },
      { icon: '🐙', name: 'GitHub',    actions: [['Open','Open GitHub'],['Pull requests','Open GitHub pull requests'],['Issues','Open GitHub issues']] },
      { icon: '🖥️', name: 'Terminal',  actions: [['Open','Open Terminal']] },
      { icon: '🤖', name: 'ChatGPT',   actions: [['Open','Open ChatGPT']] },
    ]
  },
  {
    category: 'System & Utilities',
    apps: [
      { icon: '🗑️', name: 'Cleanup Temp', actions: [['Scan','Scan for temp files on my PC'],['Clean','Delete temp files from my PC'],['Browser cache','Clean browser cache and temp files']] },
      { icon: '📊', name: 'System Monitor',actions: [['Status','Show system CPU and memory status'],['Processes','Show running processes']] },
      { icon: '📱', name: 'Find App',      actions: [['Search','Find installed apps on my computer'],['Running','List all running applications']] },
    ]
  },
];

let _appsRendered = false;
function loadAppsPanel() {
  if (_appsRendered) return;
  _appsRendered = true;
  const grid = document.getElementById('apps-grid');
  if (!grid) return;
  grid.innerHTML = APP_CATALOG.map(cat => {
    const rows = [];
    for (let i = 0; i < cat.apps.length; i += 2) {
      const pair = cat.apps.slice(i, i + 2);
      rows.push(`<div class="apps-grid-row">${pair.map(app => renderAppCard(app)).join('')}</div>`);
    }
    return `<div class="apps-category" data-category="${esc(cat.category.toLowerCase())}">
      <div class="apps-cat-label">${esc(cat.category)}</div>
      ${rows.join('')}
    </div>`;
  }).join('');
}

function renderAppCard(app) {
  const chipsHtml = app.actions.map(([label, cmd]) =>
    `<button class="app-action-chip" onclick="setAppInput('${esc(cmd).replace(/'/g,"\\'")}');event.stopPropagation()">${esc(label)}</button>`
  ).join('');
  return `<div class="app-card" onclick="setInputAndSend('Open ${esc(app.name)}')" data-name="${esc(app.name.toLowerCase())}">
    <div class="app-card-top">
      <span class="app-card-icon">${app.icon}</span>
      <span class="app-card-name">${esc(app.name)}</span>
    </div>
    <div class="app-card-actions">${chipsHtml}</div>
  </div>`;
}

function filterApps(q) {
  const query = q.toLowerCase().trim();
  const grid = document.getElementById('apps-grid');
  if (!grid) return;
  let anyVisible = false;
  grid.querySelectorAll('.app-card').forEach(card => {
    const name = card.dataset.name || '';
    const match = !query || name.includes(query);
    card.classList.toggle('hidden', !match);
    if (match) anyVisible = true;
  });
  grid.querySelectorAll('.apps-category').forEach(cat => {
    const hasVisible = [...cat.querySelectorAll('.app-card')].some(c => !c.classList.contains('hidden'));
    cat.style.display = hasVisible ? '' : 'none';
  });
  let emptyEl = grid.querySelector('.apps-empty');
  if (!anyVisible && query) {
    if (!emptyEl) {
      emptyEl = document.createElement('div');
      emptyEl.className = 'apps-empty';
      grid.appendChild(emptyEl);
    }
    emptyEl.textContent = `No apps found for "${q}". Try typing the task in the chat instead.`;
  } else if (emptyEl) {
    emptyEl.remove();
  }
}

function renderTodoList(todos) {
  const el = document.getElementById('asst-todo-list');
  if (!el) return;
  if (!todos.length) { el.innerHTML = '<div class="panel-empty">No tasks yet!</div>'; return; }
  el.innerHTML = todos.map(t => `
    <div class="asst-todo-item">
      <input type="checkbox" class="asst-todo-check" ${t.done?'checked':''} onchange="toggleTodoDone('${esc(t.id)}',this.checked)">
      <span class="asst-todo-text ${t.done?'done':''}" onclick="toggleTodoDone('${esc(t.id)}',${!t.done})">${esc(t.text)}</span>
      <span class="asst-todo-pri ptask-pri ${esc(t.priority)}">${esc(t.priority)}</span>
      <button style="background:transparent;border:none;color:var(--muted);cursor:pointer;font-size:11px;padding:2px 4px" onclick="deleteTodo('${esc(t.id)}')">✕</button>
    </div>`).join('');
}

function renderReminderList(rems) {
  const el = document.getElementById('asst-rem-list');
  if (!el) return;
  const now = new Date();
  if (!rems.length) { el.innerHTML = '<div class="panel-empty">No reminders.</div>'; return; }
  el.innerHTML = rems.filter(r=>!r.done).map(r => {
    const due = new Date(r.due);
    const overdue = due < now;
    const dueStr = due.toLocaleString([],{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'});
    return `<div class="asst-rem-item">
      <div style="flex:1">
        <div class="asst-rem-text">${esc(r.text)}</div>
        <div class="asst-rem-when ${overdue?'overdue':''}">${overdue?'⚠ Overdue — ':''}${dueStr}</div>
      </div>
      <button style="background:transparent;border:none;color:var(--muted);cursor:pointer;font-size:11px;padding:2px 4px" onclick="doneReminder('${esc(r.id)}')">✓</button>
      <button style="background:transparent;border:none;color:var(--muted);cursor:pointer;font-size:11px;padding:2px 4px" onclick="deleteReminder('${esc(r.id)}')">✕</button>
    </div>`;
  }).join('');
}

async function addTodoFromUI() {
  const inp = document.getElementById('asst-todo-input');
  const pri = document.getElementById('asst-todo-pri');
  const text = inp.value.trim();
  if (!text) { inp.focus(); return; }
  try {
    await fetch('/api/todos', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text,priority:pri.value})});
    inp.value = ''; toast('Task added ✓','ok'); loadAssistantPanel();
  } catch(e){ toast('Failed to add task','err'); }
}

async function addReminderFromUI() {
  const inp = document.getElementById('asst-rem-input');
  const when = document.getElementById('asst-rem-when');
  const text = inp.value.trim();
  const whenVal = when.value.trim() || 'in 1 hour';
  if (!text) { inp.focus(); return; }
  try {
    await fetch('/api/reminders', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text,when:whenVal})});
    inp.value = ''; toast('Reminder set ✓','ok'); loadAssistantPanel();
  } catch(e){ toast('Failed to add reminder','err'); }
}

async function toggleTodoDone(id, done) {
  if (done) await fetch(`/api/todos/${id}/done`, {method:'POST'});
  else await fetch(`/api/todos/${id}`, {method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({done:false})});
  loadAssistantPanel();
}
async function deleteTodo(id) {
  await fetch(`/api/todos/${id}`, {method:'DELETE'}); loadAssistantPanel();
}
async function doneReminder(id) {
  await fetch(`/api/reminders/${id}/done`, {method:'POST'}); loadAssistantPanel();
}
async function deleteReminder(id) {
  await fetch(`/api/reminders/${id}`, {method:'DELETE'}); loadAssistantPanel();
}

// ── Onboarding wizard ─────────────────────────────────────────────────────────
const _OB = { step: 1, data: {} };

async function showOnboarding() {
  try {
    const r = await fetch('/api/disclosure');
    const d = await r.json();
    const box = document.getElementById('ob-disclosure-box');
    if (box) box.textContent = d.text || '';
  } catch(_){}
  _OB.step = 1;
  _obShowStep(1);
  document.getElementById('onboarding-overlay').classList.remove('hidden');
}

function _obShowStep(n) {
  [1,2,3,4].forEach(i => {
    document.getElementById('ob-step-'+i).style.display = i === n ? '' : 'none';
    const dot = document.getElementById('ob-dot-'+i);
    if (dot) dot.className = 'ob-step-dot' + (i < n ? ' done' : i === n ? ' active' : '');
    if (i < 4) {
      const line = document.getElementById('ob-line-'+i);
      if (line) line.className = 'ob-step-line' + (i < n ? ' done' : '');
    }
  });
}

function obNext(fromStep) {
  if (fromStep === 1) {
    _OB.data.name = (document.getElementById('ob-name').value||'').trim();
    _OB.data.role = (document.getElementById('ob-role').value||'').trim();
    _OB.data.company = (document.getElementById('ob-company').value||'').trim();
    _OB.step = 2; _obShowStep(2);
  } else if (fromStep === 2) {
    _OB.data.timezone = document.getElementById('ob-tz').value;
    _OB.data.communication_style = document.getElementById('ob-style').value;
    _OB.data.use_cases = (document.getElementById('ob-usecases').value||'').trim();
    _OB.step = 3; _obShowStep(3);
  } else if (fromStep === 3) {
    _OB.data.provider = document.getElementById('ob-provider').value;
    const name = _OB.data.name || 'there';
    const readyTitle = document.getElementById('ob-ready-title');
    const readyMsg = document.getElementById('ob-ready-msg');
    if (readyTitle) readyTitle.textContent = `You're all set${name !== 'there' ? ', ' + name : ''}!`;
    if (readyMsg) readyMsg.textContent = `Arix is ready to help you with ${_OB.data.use_cases || 'tasks, research, and more'}.`;
    _OB.step = 4; _obShowStep(4);
  }
}

function obBack(fromStep) {
  _OB.step = fromStep - 1; _obShowStep(_OB.step);
}

async function obFinish() {
  const payload = {
    name: _OB.data.name,
    role: _OB.data.role,
    company: _OB.data.company,
    timezone: _OB.data.timezone || 'UTC',
    communication_style: _OB.data.communication_style || 'balanced',
    onboarding_complete: true,
    provider: _OB.data.provider || 'anthropic',
  };
  try {
    await fetch('/api/profile', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    await fetch('/api/onboard', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({provider: payload.provider})});
    if (payload.name) {
      S.profile = S.profile || {};
      S.profile.name = payload.name;
      S.profile.initials = payload.name[0].toUpperCase();
      renderProfileSection(S.profile);
    }
  } catch(_){}
  document.getElementById('onboarding-overlay').classList.add('hidden');
  toast(`Welcome${_OB.data.name ? ', ' + _OB.data.name : ''}! 👋`, 'ok', 3000);
  if (!S.briefShown) { S.briefShown = true; loadMorningBrief(); }
}

function declineOnboarding() {
  document.getElementById('onboarding-overlay').classList.add('hidden');
  addSystemMsg(`<div style="color:var(--muted);font-size:12px">Running in offline mode — no data will be sent to cloud AI providers.</div>`);
}

// ── Voice ─────────────────────────────────────────────────────────────────────
function initVoice() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) { document.getElementById('mic-btn').style.display='none'; return; }
  S.voice.recognition = new SR();
  S.voice.recognition.continuous = false;
  S.voice.recognition.interimResults = false;
  S.voice.recognition.lang = 'en-US';
  S.voice.recognition.onresult = e => {
    const transcript = e.results[0][0].transcript;
    const inp = document.getElementById('cmd-input');
    inp.value = (inp.value + ' ' + transcript).trim();
    autoResize(inp);
    document.getElementById('mic-btn').classList.remove('active');
    S.voice.active = false;
  };
  S.voice.recognition.onerror = () => { document.getElementById('mic-btn').classList.remove('active'); S.voice.active = false; };
  S.voice.recognition.onend = () => { document.getElementById('mic-btn').classList.remove('active'); S.voice.active = false; };
}

function toggleMic() {
  if (!S.voice.recognition) return;
  if (S.voice.active) { S.voice.recognition.stop(); } 
  else { S.voice.recognition.start(); document.getElementById('mic-btn').classList.add('active'); S.voice.active = true; }
}

// ── File attach ───────────────────────────────────────────────────────────────
function handleFileAttach(input) {
  const file = input.files[0];
  if (!file) return;
  const inp = document.getElementById('cmd-input');
  inp.value = `read_file: ~/Downloads/${file.name}`;
  autoResize(inp);
  toast(`File selected: ${file.name}`, 'info');
  input.value = '';
}

// ── Drag-drop on chat ─────────────────────────────────────────────────────────
function setupDragDrop() {
  const area = document.getElementById('chat-view');
  area.addEventListener('dragover', e => { e.preventDefault(); area.style.outline='2px dashed var(--accent)'; });
  area.addEventListener('dragleave', () => { area.style.outline=''; });
  area.addEventListener('drop', e => {
    e.preventDefault(); area.style.outline='';
    const file = e.dataTransfer?.files?.[0];
    if (file) {
      const inp = document.getElementById('cmd-input');
      inp.value = `read_file: ~/Downloads/${file.name}`;
      autoResize(inp);
      toast(`Dropped: ${file.name}`, 'info');
    }
  });
}

// ── Command Palette ───────────────────────────────────────────────────────────
const PAL_ITEMS = [
  {icon:'🌄', label:'Morning Brief', desc:'Show today\'s briefing', action:()=>{loadMorningBrief();closePalette();}},
  {icon:'📱', label:'Apps', desc:'Launch apps — TikTok, Instagram, WhatsApp, Excel…', action:()=>{switchPanel('apps');closePalette();}},
  {icon:'🗑️', label:'Clean Temp Files', desc:'Delete temp files and free up disk space', action:()=>{prefill('Delete temp files from my PC');closePalette();}},
  {icon:'🎵', label:'Open TikTok', desc:'Launch TikTok in browser', action:()=>{prefill('Open TikTok');closePalette();}},
  {icon:'📸', label:'Open Instagram', desc:'Launch Instagram in browser', action:()=>{prefill('Open Instagram');closePalette();}},
  {icon:'💬', label:'Send WhatsApp message', desc:'Open WhatsApp to send a message', action:()=>{prefill('Send a WhatsApp message to ');closePalette();}},
  {icon:'💼', label:'Open LinkedIn', desc:'Launch LinkedIn in browser', action:()=>{prefill('Open LinkedIn feed');closePalette();}},
  {icon:'📊', label:'Open Excel', desc:'Launch Microsoft Excel', action:()=>{prefill('Open Microsoft Excel');closePalette();}},
  {icon:'🎥', label:'Open OBS Studio', desc:'Launch OBS Studio for recording/streaming', action:()=>{prefill('Open OBS Studio');closePalette();}},
  {icon:'📊', label:'System Monitor', desc:'Open system panel', action:()=>{switchPanel('sysmon');closePalette();}},
  {icon:'🧠', label:'Memory', desc:'View task memory', action:()=>{switchPanel('memory');closePalette();}},
  {icon:'📈', label:'Insights', desc:'Activity analytics', action:()=>{switchPanel('insights');closePalette();}},
  {icon:'🔄', label:'Workflows', desc:'Manage automations', action:()=>{switchPanel('workflows');closePalette();}},
  {icon:'📄', label:'Reports', desc:'Research reports', action:()=>{switchPanel('reports');closePalette();}},
  {icon:'✓', label:'Projects', desc:'Project management', action:()=>{switchPanel('projects');closePalette();}},
  {icon:'📝', label:'Notes', desc:'Knowledge base', action:()=>{switchPanel('notes');closePalette();}},
  {icon:'📅', label:'Calendar', desc:'Google Calendar', action:()=>{switchPanel('calendar');closePalette();}},
  {icon:'⚙️', label:'Settings', desc:'Configure Arix', action:()=>{switchPanel('settings');closePalette();}},
  {icon:'🔍', label:'Audit Log', desc:'Security audit', action:()=>{switchPanel('audit');closePalette();}},
  {icon:'⌨', label:'Developer Console', desc:'Terminal mode', action:()=>{toggleDevMode();closePalette();}},
  {icon:'🔬', label:'Research topic', desc:'AI-powered research', action:()=>{prefill('research_topic: ');closePalette();}},
  {icon:'💻', label:'Generate code', desc:'AI code generation', action:()=>{prefill('generate_code: ');closePalette();}},
  {icon:'🌐', label:'Browse URL', desc:'Open a website', action:()=>{prefill('browser_open_url: ');closePalette();}},
  {icon:'🔎', label:'Web search', desc:'Search the web', action:()=>{prefill('browser_web_search: ');closePalette();}},
  {icon:'📂', label:'List files', desc:'List directory', action:()=>{prefill('list_directory ~/');closePalette();}},
  {icon:'🌿', label:'Git status', desc:'Git repository status', action:()=>{prefill('git status');closePalette();}},
  {icon:'🔍', label:'Toggle dry-run', desc:'Plan without executing', action:()=>{toggleDryRun();closePalette();}},
  {icon:'🎯', label:'Toggle goal mode', desc:'Autonomous multi-step execution', action:()=>{toggleGoalMode();closePalette();}},
  {icon:'📧', label:'Gmail', desc:'Read and send emails', action:()=>{switchPanel('gmail');closePalette();}},
  {icon:'📁', label:'Google Drive', desc:'Browse and manage Drive files', action:()=>{switchPanel('drive');closePalette();}},
  {icon:'🔌', label:'Plugins', desc:'Custom tool builder — connect any webhook', action:()=>{switchPanel('plugins');closePalette();}},
  {icon:'👁', label:'Screen Vision', desc:'Capture browser page + AI analysis', action:()=>{triggerVisionCapture();closePalette();}},
  {icon:'🔊', label:'Toggle TTS', desc:'Speak responses aloud', action:()=>{toggleTTS();closePalette();}},
  {icon:'📧', label:'Compose Email', desc:'Write and send an email via Gmail', action:()=>{showComposeModal();closePalette();}},
];

function openPalette() {
  S.PAL.open = true; S.PAL.idx = -1;
  document.getElementById('cmd-palette').classList.add('show');
  document.getElementById('palette-input').value = '';
  renderPalette(PAL_ITEMS);
  setTimeout(() => document.getElementById('palette-input').focus(), 50);
}
function closePalette() {
  S.PAL.open = false;
  document.getElementById('cmd-palette').classList.remove('show');
}
function renderPalette(items) {
  const res = document.getElementById('palette-results');
  if (!items.length) { res.innerHTML = '<div class="pal-empty">No results</div>'; return; }
  res.innerHTML = items.map((it,i) =>
    `<div class="pal-item ${i===S.PAL.idx?'active':''}" onclick="runPalItem(${i})"><div class="pal-item-icon">${it.icon}</div><div class="pal-item-info"><div class="pal-item-label">${esc(it.label)}</div><div class="pal-item-desc">${esc(it.desc)}</div></div></div>`
  ).join('');
}
function filterPalette(q) {
  const filtered = q ? PAL_ITEMS.filter(i => i.label.toLowerCase().includes(q.toLowerCase()) || i.desc.toLowerCase().includes(q.toLowerCase())) : PAL_ITEMS;
  S.PAL.items = filtered; S.PAL.idx = -1;
  renderPalette(filtered);
}
function palKey(e) {
  const items = S.PAL.items.length ? S.PAL.items : PAL_ITEMS;
  if (e.key === 'ArrowDown') { e.preventDefault(); S.PAL.idx = Math.min(S.PAL.idx+1, items.length-1); renderPalette(items); }
  else if (e.key === 'ArrowUp') { e.preventDefault(); S.PAL.idx = Math.max(S.PAL.idx-1, 0); renderPalette(items); }
  else if (e.key === 'Enter') { if (S.PAL.idx >= 0) runPalItem(S.PAL.idx); else if (items.length) runPalItem(0); }
  else if (e.key === 'Escape') closePalette();
}
function runPalItem(i) {
  const items = S.PAL.items.length ? S.PAL.items : PAL_ITEMS;
  if (items[i]) items[i].action();
}

// ── xterm (dev mode) ──────────────────────────────────────────────────────────
function initTerm() {
  S.term = new Terminal({
    cursorBlink: true, fontSize: 12, fontFamily: "'Cascadia Code','Fira Code',monospace",
    theme: { background:'#090c12', foreground:'#dce6f5', cursor:'#4f8ef7', selection:'rgba(79,142,247,.3)' },
    scrollback: 2000,
  });
  S.fit = new FitAddon.FitAddon();
  S.term.loadAddon(S.fit);
  S.term.open(document.getElementById('xterm-container'));
  S.fit.fit();
  S.term.writeln('\x1b[1;34m Arix Developer Console\x1b[0m\x1b[2m — raw output mode\x1b[0m');
  S.term.writeln('\x1b[2m Type commands in the input bar below.\x1b[0m\r\n');
  window.addEventListener('resize', () => { if (S.termMode && S.fit) S.fit.fit(); });
}

// ── Keyboard shortcuts ────────────────────────────────────────────────────────
document.addEventListener('keydown', e => {
  if ((e.ctrlKey||e.metaKey) && e.key==='k') { e.preventDefault(); openPalette(); }
  if ((e.ctrlKey||e.metaKey) && e.key==='/') { e.preventDefault(); document.getElementById('cmd-input').focus(); }
  if ((e.ctrlKey||e.metaKey) && e.key==='m') { e.preventDefault(); toggleMic(); }
  if (e.key==='Escape') {
    if (S.PAL.open) { closePalette(); return; }
    if (document.getElementById('profile-overlay').classList.contains('show')) { closeProfileEditor(); return; }
    if (document.getElementById('rep-full-overlay').classList.contains('show')) { closeReport(); return; }
  }
});

// ── Init ──────────────────────────────────────────────────────────────────────
connectWS();
loadProfile();
initVoice();
buildQuickChips();
setupDragDrop();
loadAssistantPanel();

// Periodic notification check
setInterval(loadNotifications, 60000);

// ── Bridge status polling ──────────────────────────────────────────────────
async function pollBridgeStatus() {
  try {
    const r = await fetch('/api/bridge/status');
    if (!r.ok) return;
    const d = await r.json();
    const badge = document.getElementById('bridge-badge');
    if (!badge) return;
    if (d.connected) {
      badge.className = 'bridge-badge connected';
      const plat = d.platform ? ` (${d.platform})` : '';
      const sz = (d.screen_width && d.screen_height) ? ` ${d.screen_width}×${d.screen_height}` : '';
      badge.textContent = `🖥 Bridge: On${plat}${sz}`;
      badge.title = `Local bridge connected — ${d.platform} ${d.screen_width}×${d.screen_height}`;
    } else {
      badge.className = 'bridge-badge disconnected';
      badge.textContent = '🖥 Bridge: Off';
      badge.title = 'Local bridge not connected — click for setup instructions';
    }
  } catch(e) {}
}
pollBridgeStatus();
setInterval(pollBridgeStatus, 10000);

function showBridgeHelp() {
  let el = document.getElementById('bridge-help-overlay');
  if (!el) {
    el = document.createElement('div');
    el.id = 'bridge-help-overlay';
    el.innerHTML = `
      <div id="bridge-help-box">
        <button id="bridge-help-close" onclick="document.getElementById('bridge-help-overlay').classList.remove('show')">✕</button>
        <h3>🖥 Connect Your Computer to Arix</h3>
        <div class="step"><b>Step 1</b> — Install the bridge on your computer:</div>
        <pre>pip install pyautogui pillow websockets</pre>
        <div class="step"><b>Step 2</b> — Download and run the bridge agent:</div>
        <pre>python local_bridge/bridge_agent.py --server ${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws/bridge</pre>
        <div class="step"><b>Step 3</b> — The Bridge badge above will turn green when connected.</div>
        <div class="step" style="margin-top:14px;color:var(--muted)">
          Once connected, Arix can take screenshots of your screen, click, type,
          press keyboard shortcuts, and control any app — just like a human would.
          Move your mouse to the top-left corner at any time to abort an action.
        </div>
      </div>
    `;
    document.body.appendChild(el);
    el.addEventListener('click', e => { if (e.target === el) el.classList.remove('show'); });
  }
  el.classList.add('show');
}

