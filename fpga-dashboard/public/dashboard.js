'use strict';

// ── Config ────────────────────────────────────────────────────────────────────
const REFRESH_INTERVAL_S   = 5;
const MAX_HISTORY           = 40;
const HEARTBEAT_TIMEOUT_S   = 120; // workers silent >2 min considered offline

// ── State ─────────────────────────────────────────────────────────────────────
let token          = sessionStorage.getItem('fpga_token') || '';
let autoRefresh    = true;
let refreshTimer   = null;
let countdown      = REFRESH_INTERVAL_S;
let userRole       = 'viewer';
const charts       = {};

// ── Theme ─────────────────────────────────────────────────────────────────────
let isDark = localStorage.getItem('fpga_theme') !== 'light';

function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function applyTheme() {
  document.documentElement.setAttribute('data-theme', isDark ? 'dark' : 'light');
  const btn = document.getElementById('theme-btn');
  if (btn) btn.textContent = isDark ? '☀' : '🌙';
  updateChartsTheme();
}

function toggleTheme() {
  isDark = !isDark;
  localStorage.setItem('fpga_theme', isDark ? 'dark' : 'light');
  applyTheme();
}

function updateChartsTheme() {
  const muted = cssVar('--muted');
  const grid  = cssVar('--border');
  const axisOpts = {
    ticks: { color: muted, font: { size: 11 } },
    grid:  { color: grid },
  };
  Object.values(charts).forEach(chart => {
    if (!chart) return;
    if (chart.options.scales) {
      if (chart.options.scales.x) Object.assign(chart.options.scales.x, axisOpts);
      if (chart.options.scales.y) Object.assign(chart.options.scales.y, axisOpts);
    }
    if (chart.options.plugins?.legend?.labels) {
      chart.options.plugins.legend.labels.color = muted;
    }
    chart.update();
  });
}

// ── API proxy ─────────────────────────────────────────────────────────────────
// All requests go to /api/* — nginx proxies to master with X-API-Token forwarded.
const API = {
  _headers() {
    return { 'X-API-Token': token, 'Content-Type': 'application/json' };
  },
  async _req(method, path, body) {
    const opts = { method, headers: this._headers() };
    if (body !== undefined) opts.body = JSON.stringify(body);
    const r = await fetch('/api' + path, opts);
    if (r.status === 401) { doLogout(); throw new Error('Unauthorized'); }
    if (!r.ok) {
      let msg = `HTTP ${r.status}`;
      try { const j = await r.json(); msg = j.detail || JSON.stringify(j); } catch {}
      throw new Error(msg);
    }
    return r.json();
  },
  get:  (path)       => API._req('GET',    path),
  post: (path, body) => API._req('POST',   path, body),
  del:  (path)       => API._req('DELETE', path),
};

// ── Login / Logout ────────────────────────────────────────────────────────────
async function doLogin() {
  const t    = (document.getElementById('token-input').value || '').trim();
  const errEl = document.getElementById('login-error');
  errEl.textContent = '';
  if (!t) { errEl.textContent = 'Введите токен'; return; }

  token = t;
  try {
    await API.get('/health');
    sessionStorage.setItem('fpga_token', token);
    document.getElementById('login').classList.add('hidden');
    document.getElementById('app').classList.remove('hidden');
    initCharts();
    startAutoRefresh();
    await refresh();
  } catch (e) {
    errEl.textContent = `Ошибка: ${e.message}. Проверьте токен и доступность кластера.`;
    token = '';
  }
}

function doLogout() {
  sessionStorage.removeItem('fpga_token');
  location.reload();
}

// ── Auto-refresh ──────────────────────────────────────────────────────────────
function startAutoRefresh() {
  if (refreshTimer) clearInterval(refreshTimer);
  countdown = REFRESH_INTERVAL_S;
  refreshTimer = setInterval(() => {
    countdown--;
    const el = document.getElementById('countdown');
    if (el) el.textContent = autoRefresh ? `${countdown}s` : '';
    if (autoRefresh && countdown <= 0) {
      countdown = REFRESH_INTERVAL_S;
      refresh();
    }
  }, 1000);
}

function toggleAutoRefresh() {
  autoRefresh = !autoRefresh;
  const btn = document.getElementById('refresh-btn');
  btn.classList.toggle('inactive', !autoRefresh);
  const el = document.getElementById('countdown');
  if (el) el.textContent = autoRefresh ? `${REFRESH_INTERVAL_S}s` : '';
}

// ── Chart.js helpers ──────────────────────────────────────────────────────────
function getChartCfg() {
  const muted = cssVar('--muted');
  const grid  = cssVar('--border');
  return {
    scales: {
      x: { ticks: { color: muted, font: { size: 11 } }, grid: { color: grid } },
      y: { ticks: { color: muted, font: { size: 11 } }, grid: { color: grid } },
    },
    plugins: { legend: { labels: { color: muted, font: { size: 12 } } } },
    responsive: true, maintainAspectRatio: false,
  };
}

function initCharts() {
  const cfg = getChartCfg();

  // Queue depth history
  charts.queue = new Chart(document.getElementById('chart-queue'), {
    type: 'line',
    data: { labels: [], datasets: [{
      label: 'Задач в очереди', data: [],
      borderColor: cssVar('--accent'), backgroundColor: 'rgba(56,139,253,.12)',
      tension: 0.4, fill: true, pointRadius: 2, borderWidth: 2,
    }]},
    options: { ...cfg },
  });

  // Task status doughnut
  charts.tasksStatus = new Chart(document.getElementById('chart-tasks-status'), {
    type: 'doughnut',
    data: {
      labels: ['Выполнено', 'Ошибка', 'В работе', 'Ожидание'],
      datasets: [{
        data: [0, 0, 0, 0],
        backgroundColor: ['#3fb950', '#f85149', '#d29922', '#388bfd'],
        borderWidth: 0, hoverOffset: 4,
      }],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { position: 'bottom', labels: { color: cssVar('--muted'), font: { size: 11 }, padding: 10 } } },
    },
  });

  // Workers load bar
  charts.workers = new Chart(document.getElementById('chart-workers'), {
    type: 'bar',
    data: { labels: [], datasets: [{
      label: 'Текущая загрузка', data: [],
      backgroundColor: cssVar('--accent'), borderRadius: 4,
    }]},
    options: {
      ...cfg,
      indexAxis: 'y',
      plugins: { legend: { display: false } },
      scales: {
        ...cfg.scales,
        x: { ...cfg.scales.x, suggestedMax: 1 },
      },
    },
  });
}

// ── Render helpers ────────────────────────────────────────────────────────────
function dot(online) {
  return `<span class="dot ${online ? 'green' : 'red'}"></span>`;
}

function badge(text, cls) {
  return `<span class="badge badge-${cls}">${escHtml(text)}</span>`;
}

function timeAgo(ts) {
  if (!ts) return '—';
  const diff = Math.floor(Date.now() / 1000) - ts;
  if (diff < 5)    return 'только что';
  if (diff < 60)   return `${diff}с назад`;
  if (diff < 3600) return `${Math.floor(diff / 60)}м назад`;
  return `${Math.floor(diff / 3600)}ч назад`;
}

function escHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// ── Section renderers ─────────────────────────────────────────────────────────
function renderHealth(h) {
  const ok = h.quorum_ok;
  document.getElementById('cluster-badge').className = `badge badge-${ok ? 'online' : 'warning'}`;
  document.getElementById('cluster-badge').textContent = `● ${ok ? 'Online' : 'Warning'}`;

  const activeW = h._active_workers ?? h.workers_count;
  document.getElementById('health-body').innerHTML = `
    <div class="stat-row">${dot(true)}
      <span>Мастер-узлов: <b>${h.masters_count}</b></span>
    </div>
    <div class="stat-row">${dot(activeW > 0)}
      <span>Воркеров: <b>${activeW}</b> активных</span>
    </div>
    <div class="stat-row">${dot(ok)}
      <span>Кворум: <b>${escHtml(h.quorum_state)}</b></span>
    </div>
    <div class="stat-row">
      <span class="muted">Отказоустойчивость: ${h.fault_tolerance ?? '—'} узла</span>
    </div>
    ${h.quorum_warning ? `<div class="warning-msg">⚠ ${escHtml(h.quorum_warning)}</div>` : ''}
  `;
}

function renderQuorum(h) {
  const cls = h.quorum_ok ? 'green' : (h.quorum_state === 'warning' ? 'warn' : 'red');
  document.getElementById('quorum-body').innerHTML = `
    <div class="quorum-state ${cls}">${escHtml(h.quorum_state)}</div>
    <div class="stat-row"><span class="muted">Узел: ${escHtml(h.node_id || '—')}</span></div>
    <div class="stat-row"><span class="muted">Мастеров: ${h.masters_count}</span></div>
    <div class="stat-row"><span class="muted">Допустимо сбоев: ${h.fault_tolerance ?? 0}</span></div>
  `;
}

function renderTasksSummary(tasks) {
  const el = document.getElementById('tasks-summary-body');
  if (!Array.isArray(tasks)) { el.innerHTML = '<span class="muted">—</span>'; return; }

  const c = { completed: 0, failed: 0, running: 0, pending: 0, scheduling_error: 0 };
  tasks.forEach(t => {
    const s = (t.status || '').toLowerCase();
    if (['completed', 'success'].includes(s))     c.completed++;
    else if (s === 'scheduling_error')             c.scheduling_error++;
    else if (['failed', 'error'].includes(s))      c.failed++;
    else if (['running', 'executing', 'assigned'].includes(s)) c.running++;
    else c.pending++;
  });

  const anyErr = c.failed + c.scheduling_error;
  el.innerHTML = `
    <div class="stat-row">${dot(true)}<span>Выполнено: <b class="green">${c.completed}</b></span></div>
    <div class="stat-row">${dot(anyErr === 0)}<span>Ошибки: <b class="${anyErr > 0 ? 'red' : ''}">${anyErr}</b></span></div>
    ${c.scheduling_error > 0 ? `<div class="stat-row"><span class="muted" style="font-size:11px;padding-left:16px">Нет ПЛИС: ${c.scheduling_error}</span></div>` : ''}
    <div class="stat-row">${dot(c.running > 0)}<span>В работе: <b>${c.running}</b></span></div>
    <div class="stat-row"><span class="muted">Всего: ${tasks.length}</span></div>
  `;

  if (charts.tasksStatus) {
    charts.tasksStatus.data.datasets[0].data = [c.completed, anyErr, c.running, c.pending];
    charts.tasksStatus.update('none');
  }
}

function isOnline(w) {
  const hb = w.last_heartbeat || 0;
  const sinceSec = Math.floor(Date.now() / 1000) - hb;
  return sinceSec < HEARTBEAT_TIMEOUT_S && (w.status || '').toLowerCase() === 'online';
}

function fpgaStatusBadge(status) {
  const s = (status || 'idle').toLowerCase();
  if (s === 'uploading') return badge('uploading', 'warn');
  if (s === 'testing')   return `<span class="badge" style="background:rgba(188,140,255,.15);color:#bc8cff">testing</span>`;
  if (s === 'running')   return `<span class="badge" style="background:rgba(56,139,253,.15);color:#388bfd">running</span>`;
  if (s === 'busy')      return badge('busy', 'err');
  return badge('idle', 'ok');
}

function fpgaTypeBadge(fpga_id) {
  const id = fpga_id || '';
  if (id.startsWith('prod_'))      return `<span class="badge badge-warn" style="font-size:10px">prod</span>`;
  if (id.startsWith('dev_'))       return `<span class="badge badge-ok"   style="font-size:10px">dev</span>`;
  if (id.startsWith('fpga-test-')) return `<span class="badge badge-role" style="font-size:10px">тест</span>`;
  return '';
}

function workerCard(w, workerFpgas, isAdmin) {
  const rawTags = Array.isArray(w.tags) ? w.tags
                : (typeof w.tags === 'string' && w.tags ? w.tags.split(',') : []);
  const tags   = rawTags.map(t => `<span class="tag">${escHtml(t.trim())}</span>`).join('');
  const load   = w.current_load || 0;
  const max    = w.max_capacity || 4;
  const pct    = Math.min(100, Math.round(load / Math.max(max, 1) * 100));
  const online = isOnline(w);

  const fpgaList = workerFpgas.length
    ? workerFpgas.map(f => `
        <div class="fpga-inline">
          <span class="mono" style="font-size:11px">${escHtml(f.fpga_id)}</span>
          ${fpgaTypeBadge(f.fpga_id)}
          ${fpgaStatusBadge(f.status)}
        </div>`).join('')
    : '<span class="muted" style="font-size:11px">нет ПЛИС</span>';

  const deleteBtn = isAdmin
    ? `<button class="btn-small btn-danger" style="font-size:11px;padding:2px 6px"
         onclick="deleteWorker('${escHtml(w.worker_id)}')">✕</button>`
    : '';

  return `
    <div class="worker-card${online ? '' : ' offline'}">
      <div class="worker-header">
        ${dot(online)}
        <span class="worker-name">${escHtml(w.worker_id || '?')}</span>
        <span class="muted worker-ip">${escHtml(w.node_ip || '')}</span>
        ${deleteBtn}
      </div>
      <div class="tags-row">${tags || '<span class="muted">нет тегов</span>'}</div>
      <div class="fpga-list">${fpgaList}</div>
      <div class="worker-meta">
        <span class="muted">${timeAgo(w.last_heartbeat)}</span>
      </div>
    </div>`;
}

function renderWorkers(workers, fpgas, isAdmin) {
  const now    = Math.floor(Date.now() / 1000);
  const active = workers.filter(w => (now - (w.last_heartbeat || 0)) < HEARTBEAT_TIMEOUT_S);
  const inactive = workers.filter(w => (now - (w.last_heartbeat || 0)) >= HEARTBEAT_TIMEOUT_S);
  const el     = document.getElementById('workers-grid');

  document.getElementById('workers-count').textContent =
    inactive.length > 0
      ? `${active.length} активных / ${workers.length} зарегистрировано`
      : `${active.length} активных`;

  const fpgasByWorker = {};
  (fpgas || []).forEach(f => {
    if (!fpgasByWorker[f.worker_id]) fpgasByWorker[f.worker_id] = [];
    fpgasByWorker[f.worker_id].push(f);
  });

  let html = '';

  if (active.length) {
    html += active.map(w => workerCard(w, fpgasByWorker[w.worker_id] || [], isAdmin)).join('');
  } else {
    html += '<span class="muted">Нет активных воркеров (heartbeat > 2 мин)</span>';
  }

  if (inactive.length) {
    html += `<div class="workers-inactive-header">
      <span class="muted" style="font-size:12px">Неактивные (${inactive.length})</span>
    </div>`;
    html += inactive.map(w => workerCard(w, fpgasByWorker[w.worker_id] || [], isAdmin)).join('');
  }

  el.innerHTML = html;

  if (charts.workers) {
    charts.workers.data.labels = active.map(w => escHtml(w.worker_id || '?'));
    charts.workers.data.datasets[0].data = active.map(w => w.current_load || 0);
    charts.workers.update('none');
  }
}

function renderFPGAs(fpgas) {
  document.getElementById('fpgas-count').textContent = `${fpgas.length} устройств`;
  const el = document.getElementById('fpgas-grid');

  if (!fpgas.length) {
    el.innerHTML = '<span class="muted">Нет зарегистрированных ПЛИС</span>';
    return;
  }

  el.innerHTML = fpgas.map(f => {
    const st   = (f.status || 'idle').toLowerCase();
    const busy = st !== 'idle';
    const id   = f.fpga_id || '?';
    const cls  = id.startsWith('prod') ? 'prod' : id.startsWith('dev') ? 'dev' : 'test';

    return `
      <div class="fpga-card tag-${cls}">
        <div class="fpga-header">
          ${dot(!busy)}
          <span class="fpga-id">${escHtml(id)}</span>
          ${fpgaTypeBadge(id)}
          ${fpgaStatusBadge(st)}
        </div>
        <div class="fpga-meta">
          <div><span class="muted">Модель:</span> ${escHtml(f.model || '—')}</div>
          <div><span class="muted">Вендор:</span> ${escHtml(f.vendor || '—')}</div>
          <div><span class="muted">Интерфейс:</span> ${escHtml(f.interface || '—')}</div>
          ${f.board_name ? `<div><span class="muted">Плата:</span> ${escHtml(f.board_name)}</div>` : ''}
          <div><span class="muted">Воркер:</span> ${escHtml(f.worker_id || '—')}</div>
          ${f.last_programmed_at ? `<div><span class="muted">Прошивка:</span> ${timeAgo(f.last_programmed_at)}</div>` : ''}
        </div>
      </div>`;
  }).join('');
}

function renderTasks(tasks) {
  const el = document.getElementById('tasks-table-wrap');
  if (!Array.isArray(tasks) || !tasks.length) {
    el.innerHTML = '<span class="muted" style="padding:16px;display:block">Нет задач</span>';
    return;
  }

  // Sort by created_at descending so newest tasks appear first
  const rows = [...tasks]
    .sort((a, b) => (b.created_at || 0) - (a.created_at || 0))
    .slice(0, 30)
    .map(t => {
    const s   = (t.status || 'pending').toLowerCase();
    const cls = ['completed', 'success'].includes(s) ? 'ok'
              : ['failed', 'error', 'scheduling_error'].includes(s) ? 'err' : 'warn';
    return `
      <tr>
        <td class="mono">${escHtml((t.task_id || '?').slice(0, 8))}…</td>
        <td>${escHtml(t.project_name || '—')}</td>
        <td><span class="tag">${escHtml(t.worker_tag || '—')}</span></td>
        <td class="mono">${escHtml((t.fpga_tag || t.target_fpga_id || '—').slice(0, 24))}</td>
        <td>${t.is_test ? 'тест' : 'деплой'}</td>
        <td>${badge(t.status || 'pending', cls)}</td>
        <td class="muted">${timeAgo(t.created_at)}</td>
      </tr>`;
  }).join('');

  el.innerHTML = `
    <table class="data-table">
      <thead>
        <tr>
          <th>ID</th><th>Проект</th><th>Тег</th>
          <th>ПЛИС</th><th>Тип</th><th>Статус</th><th>Создана</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>`;
}

function renderTokens(tokens) {
  const el = document.getElementById('tokens-table-wrap');
  if (!tokens.length) {
    el.innerHTML = '<span class="muted" style="padding:16px;display:block">Нет активных токенов</span>';
    return;
  }

  const rows = tokens.map(t => `
    <tr>
      <td class="mono">${escHtml(t.token_id.slice(0, 8))}…</td>
      <td>${badge(t.role, t.role === 'admin' ? 'err' : t.role === 'operator' ? 'warn' : 'ok')}</td>
      <td>${escHtml(t.description || '—')}</td>
      <td class="muted">${timeAgo(t.created_at)}</td>
      <td class="muted">${t.expires_at ? new Date(t.expires_at * 1000).toLocaleString('ru') : '∞'}</td>
      <td>${t.is_root ? 'root' : ''}</td>
      <td>
        ${!t.is_root
          ? `<button class="btn-small btn-danger" onclick="revokeToken('${escHtml(t.token_id)}')">Отозвать</button>`
          : ''}
      </td>
    </tr>`).join('');

  el.innerHTML = `
    <table class="data-table">
      <thead>
        <tr><th>ID</th><th>Роль</th><th>Описание</th><th>Создан</th><th>Истекает</th><th></th><th></th></tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>`;
}

// ── Queue chart history ───────────────────────────────────────────────────────
function updateQueueChart(queueData) {
  if (!charts.queue) return;
  const depth = Array.isArray(queueData) ? queueData.length : 0;
  const now   = new Date().toLocaleTimeString('ru', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  const { labels, datasets } = charts.queue.data;
  labels.push(now);
  datasets[0].data.push(depth);
  if (labels.length > MAX_HISTORY) { labels.shift(); datasets[0].data.shift(); }
  charts.queue.update('none');
}

// ── Token management UI ───────────────────────────────────────────────────────
function showIssueForm() { document.getElementById('issue-form').classList.remove('hidden'); }
function hideIssueForm()  { document.getElementById('issue-form').classList.add('hidden'); }

async function issueToken() {
  const role = document.getElementById('new-role').value;
  const desc = document.getElementById('new-desc').value.trim();
  const ttl  = document.getElementById('new-ttl').value;
  const resEl = document.getElementById('new-token-result');
  resEl.className = 'token-result';

  try {
    const body = { role, description: desc };
    if (ttl) body.ttl_seconds = parseInt(ttl, 10);
    const t = await API.post('/auth/tokens', body);
    resEl.innerHTML = `
      Токен выпущен (роль: <b>${escHtml(t.role)}</b>):<br>
      <code class="token-value">${escHtml(t.token)}</code>
      <small class="muted">Сохраните сейчас — значение больше не будет показано</small>`;
    resEl.classList.remove('hidden');
    await loadTokens();
  } catch (e) {
    resEl.className = 'token-result error';
    resEl.textContent = `Ошибка: ${e.message}`;
    resEl.classList.remove('hidden');
  }
}

async function revokeToken(tokenId) {
  if (!confirm(`Отозвать токен ${tokenId.slice(0, 8)}…?`)) return;
  try {
    await API.del(`/auth/tokens/${tokenId}`);
    await loadTokens();
  } catch (e) {
    alert(`Ошибка: ${e.message}`);
  }
}

async function loadTokens() {
  try {
    const tokens = await API.get('/auth/tokens');
    renderTokens(tokens);
  } catch (e) {
    console.warn('loadTokens error:', e);
  }
}

// ── Worker deletion ───────────────────────────────────────────────────────────
async function deleteWorker(workerId) {
  if (!confirm(`Удалить воркер ${workerId} из кластера?`)) return;
  try {
    await API.del(`/workers/${workerId}`);
    await refresh();
  } catch (e) {
    alert(`Ошибка: ${e.message}`);
  }
}

// ── Task history clear ────────────────────────────────────────────────────────
async function clearTasks() {
  if (!confirm('Удалить всю историю задач? Это действие необратимо.')) return;
  try {
    await API.del('/tasks');
    await refresh();
  } catch (e) {
    alert(`Ошибка очистки: ${e.message}`);
  }
}

// ── Main refresh ──────────────────────────────────────────────────────────────
async function refresh() {
  try {
    const [health, workers, fpgas, queueResp, tasks, whoami] = await Promise.all([
      API.get('/health'),
      API.get('/get_workers'),
      API.get('/fpgas'),
      API.get('/get_queue'),
      API.get('/tasks'),
      API.get('/auth/whoami'),
    ]);

    const allWorkers = Array.isArray(workers) ? workers : [];
    const now = Math.floor(Date.now() / 1000);
    const activeWorkers = allWorkers.filter(w => (now - (w.last_heartbeat || 0)) < HEARTBEAT_TIMEOUT_S);
    // Override workers_count with heartbeat-filtered count
    health._active_workers = activeWorkers.length;

    renderHealth(health);
    renderQuorum(health);
    renderTasksSummary(tasks);
    renderWorkers(allWorkers, Array.isArray(fpgas) ? fpgas : [], userRole === 'admin');
    renderFPGAs(Array.isArray(fpgas) ? fpgas : []);
    renderTasks(tasks);
    updateQueueChart(queueResp.queue || queueResp);

    userRole = whoami.role || 'viewer';
    const wb = document.getElementById('whoami-badge');
    wb.style.display = '';
    wb.textContent   = userRole;
    wb.className = `badge badge-${userRole === 'admin' ? 'err' : userRole === 'operator' ? 'warn' : 'ok'}`;

    if (userRole === 'admin') {
      document.getElementById('tokens-section').classList.remove('hidden');
      document.getElementById('clear-tasks-btn').classList.remove('hidden');
      await loadTokens();
    }

    document.getElementById('last-update').textContent =
      `Обновлено: ${new Date().toLocaleTimeString('ru')}`;

  } catch (e) {
    console.error('Refresh error:', e);
    document.getElementById('cluster-badge').className = 'badge badge-offline';
    document.getElementById('cluster-badge').textContent = '● Ошибка';
  }
}

// ── Boot ──────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  applyTheme();
  document.getElementById('token-input').addEventListener('keydown', e => {
    if (e.key === 'Enter') doLogin();
  });
  if (token) {
    document.getElementById('token-input').value = token;
    doLogin();
  }
});
