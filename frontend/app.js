/* ═══════════════════════════════════════════════════════════════════════
   NeuralFlux — Multi-Agent AI Platform · Application Logic
   API: FastAPI @ http://localhost:8000/api/v1
   User: demo-user-id (hardcoded per backend design)
   ═══════════════════════════════════════════════════════════════════════ */

// ── Config ──────────────────────────────────────────────────────────────
// API_BASE se puede sobrescribir desde index.html para producción:
//   <script>window.API_BASE = 'https://tu-backend.onrender.com/api/v1'</script>
// Si no está definido, usa localhost para desarrollo local.
const API_BASE = window.API_BASE || 'http://localhost:8000/api/v1';
const USER_ID  = 'demo-user-id';
const TENANT_ID = 1;

// ── State ────────────────────────────────────────────────────────────────
const state = {
  currentPage: 'dashboard',
  agents: [],
  selectedDocAgent: null,
  chat: {
    sessionId: null,
    agentId: null,
    sending: false,
    sessions: [],
  },
};

// ════════════════════════════════════════════════════════════════════════
// NAVIGATION
// ════════════════════════════════════════════════════════════════════════

function navigate(page) {
  // Hide all pages
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  // Remove active from all nav items
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));

  document.getElementById('page-' + page).classList.add('active');
  document.getElementById('nav-' + page)?.classList.add('active');

  state.currentPage = page;

  // Lazy-load page data
  if (page === 'dashboard') loadDashboard();
  if (page === 'agents') loadAgents();
  if (page === 'documents') loadDocumentAgents();
  if (page === 'chat') loadChatPage();
}

// ════════════════════════════════════════════════════════════════════════
// API HELPERS
// ════════════════════════════════════════════════════════════════════════

async function apiFetch(path, options = {}) {
  const url = API_BASE + path;
  const opts = {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  };
  const res = await fetch(url, opts);
  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    try { const d = await res.json(); msg = d.detail || d.message || msg; } catch {}
    throw new Error(msg);
  }
  if (res.status === 204) return null;
  return res.json();
}

// ════════════════════════════════════════════════════════════════════════
// HEALTH CHECK
// ════════════════════════════════════════════════════════════════════════

async function checkApiHealth() {
  const dot  = document.getElementById('status-dot');
  const label = document.getElementById('status-label');
  dot.className = 'status-indicator checking';
  label.textContent = 'Connecting…';

  try {
    const res = await fetch(API_BASE.replace('/api/v1', '/health'), { signal: AbortSignal.timeout(5000) });
    if (res.ok) {
      dot.className = 'status-indicator online';
      label.textContent = 'API Online';
    } else { throw new Error(); }
  } catch {
    dot.className = 'status-indicator offline';
    label.textContent = 'API Offline';
  }
}

// ════════════════════════════════════════════════════════════════════════
// DASHBOARD
// ════════════════════════════════════════════════════════════════════════

async function loadDashboard() {
  try {
    const data = await apiFetch(`/agents?user_id=${USER_ID}&active_only=true`);
    state.agents = data.agents || [];

    // Stats
    document.getElementById('stat-agents').textContent = data.total ?? state.agents.length;

    let totalDocs = 0, totalChunks = 0;
    state.agents.forEach(a => {
      if (a.knowledge_base) {
        totalDocs   += a.knowledge_base.total_documents;
        totalChunks += a.knowledge_base.total_chunks;
      }
    });

    document.getElementById('stat-docs').textContent   = totalDocs;
    document.getElementById('stat-chunks').textContent = formatNum(totalChunks);

    // Sessions
    try {
      const sessions = await apiFetch(`/chat/sessions?user_id=${USER_ID}`);
      document.getElementById('stat-sessions').textContent = sessions.length;
    } catch { document.getElementById('stat-sessions').textContent = '0'; }

    // Agent preview list
    renderDashboardAgents(state.agents);
  } catch (err) {
    document.getElementById('stat-agents').textContent = '—';
    document.getElementById('stat-docs').textContent = '—';
    renderDashboardAgents([]);
  }
}

function renderDashboardAgents(agents) {
  const el = document.getElementById('dashboard-agents-list');
  if (!agents.length) {
    el.innerHTML = `<div class="empty-state"><div class="empty-icon">🤖</div><p>No agents yet. <span class="link-text" onclick="navigate('agents')">Create one →</span></p></div>`;
    return;
  }
  el.innerHTML = agents.slice(0, 5).map(a => `
    <div class="agent-preview-item" onclick="navigate('agents')">
      <div class="agent-avatar">${a.name.charAt(0).toUpperCase()}</div>
      <div style="flex:1">
        <div style="font-size:13px;font-weight:600;color:var(--text-primary)">${escHtml(a.name)}</div>
        <div style="font-size:11px;color:var(--text-secondary)">${escHtml(a.topic)}</div>
      </div>
      <div style="display:flex;gap:6px">
        <span class="meta-badge docs">${a.knowledge_base?.total_documents ?? 0} docs</span>
        <span class="meta-badge ${a.is_active ? 'active' : 'inactive'}">${a.is_active ? 'active' : 'off'}</span>
      </div>
    </div>
  `).join('');
}

// ════════════════════════════════════════════════════════════════════════
// AGENTS PAGE
// ════════════════════════════════════════════════════════════════════════

async function loadAgents() {
  const grid = document.getElementById('agents-grid');
  grid.innerHTML = `<div class="loading-state"><div class="spinner"></div><span>Loading agents…</span></div>`;
  try {
    const data = await apiFetch(`/agents?user_id=${USER_ID}&active_only=false`);
    state.agents = data.agents || [];
    renderAgentsGrid(state.agents);
  } catch (err) {
    grid.innerHTML = `<div class="empty-state"><div class="empty-icon">⚠️</div><p>${escHtml(err.message)}</p><button class="btn btn-ghost btn-sm" onclick="loadAgents()">Retry</button></div>`;
  }
}

function renderAgentsGrid(agents) {
  const grid = document.getElementById('agents-grid');
  if (!agents.length) {
    grid.innerHTML = `
      <div class="empty-state" style="grid-column:1/-1;padding:80px 24px">
        <div class="empty-icon">🤖</div>
        <p style="font-size:16px;font-weight:600;color:var(--text-primary);margin-bottom:6px">No agents yet</p>
        <p style="color:var(--text-muted);margin-bottom:20px">Create your first specialized AI agent to get started</p>
        <button class="btn btn-primary" onclick="openCreateAgentModal()">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          Create Agent
        </button>
      </div>`;
    return;
  }

  grid.innerHTML = agents.map(a => {
    const kb = a.knowledge_base;
    return `
      <div class="agent-card" onclick="openAgentDetail('${a.id}')">
        <div class="agent-card-header">
          <div class="agent-card-avatar">${a.name.charAt(0).toUpperCase()}</div>
          <div class="agent-card-actions">
            <button class="btn-icon" title="Edit agent" onclick="event.stopPropagation(); openEditAgentModal('${a.id}')">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
            </button>
            <button class="btn-icon" title="Chat with agent" onclick="event.stopPropagation(); startChatWithAgent('${a.id}', '${escHtml(a.name)}')">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
            </button>
            <button class="btn-icon btn-danger" title="Deactivate agent" onclick="event.stopPropagation(); deactivateAgent('${a.id}', '${escHtml(a.name)}')">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/></svg>
            </button>
          </div>
        </div>
        <div class="agent-card-name">${escHtml(a.name)}</div>
        <div class="agent-card-topic">⚡ ${escHtml(a.topic)}</div>
        <div class="agent-card-desc">${escHtml(a.description || 'No description provided.')}</div>
        <div class="agent-card-meta">
          <span class="meta-badge docs">📄 ${kb?.total_documents ?? 0} docs</span>
          <span class="meta-badge chunks">🧩 ${kb ? formatNum(kb.total_chunks) : 0} chunks</span>
          <span class="meta-badge ${a.is_active ? 'active' : 'inactive'}">${a.is_active ? '● Active' : '○ Inactive'}</span>
        </div>
      </div>
    `;
  }).join('');
}

// ── Create/Edit Modal ──────────────────────────────────────────────────

function openCreateAgentModal() {
  document.getElementById('modal-title').textContent = 'Create New Agent';
  document.getElementById('submit-agent-label').textContent = 'Create Agent';
  document.getElementById('edit-agent-id').value = '';
  document.getElementById('agent-form').reset();
  document.getElementById('temp-val').textContent = '0.3';
  document.getElementById('modal-overlay').classList.add('active');
}

function openEditAgentModal(agentId) {
  const agent = state.agents.find(a => a.id === agentId);
  if (!agent) return;

  document.getElementById('modal-title').textContent = 'Edit Agent';
  document.getElementById('submit-agent-label').textContent = 'Save Changes';
  document.getElementById('edit-agent-id').value = agentId;
  document.getElementById('agent-name').value = agent.name;
  document.getElementById('agent-topic').value = agent.topic;
  document.getElementById('agent-description').value = agent.description || '';
  document.getElementById('agent-system-prompt').value = agent.system_prompt;
  document.getElementById('agent-llm-model').value = agent.llm_model || '';
  document.getElementById('agent-temperature').value = agent.llm_temperature ?? 0.3;
  document.getElementById('temp-val').textContent = agent.llm_temperature ?? 0.3;
  document.getElementById('agent-max-tokens').value = agent.llm_max_tokens || '';
  document.getElementById('modal-overlay').classList.add('active');
}

function closeCreateAgentModal() {
  document.getElementById('modal-overlay').classList.remove('active');
}

function closeModal(e) {
  if (e.target === e.currentTarget) closeCreateAgentModal();
}

async function submitAgentForm(e) {
  e.preventDefault();

  const editId = document.getElementById('edit-agent-id').value;
  const isEdit = !!editId;

  const payload = {
    name:          document.getElementById('agent-name').value.trim(),
    topic:         document.getElementById('agent-topic').value.trim(),
    description:   document.getElementById('agent-description').value.trim(),
    system_prompt: document.getElementById('agent-system-prompt').value.trim(),
    llm_model:     document.getElementById('agent-llm-model').value || null,
    llm_temperature: parseFloat(document.getElementById('agent-temperature').value),
    llm_max_tokens:  parseInt(document.getElementById('agent-max-tokens').value) || null,
  };

  const spinner = document.getElementById('submit-agent-spinner');
  const label   = document.getElementById('submit-agent-label');
  const btn     = document.getElementById('submit-agent-btn');

  label.style.display = 'none';
  spinner.style.display = 'inline-block';
  btn.disabled = true;

  try {
    if (isEdit) {
      await apiFetch(`/agents/${editId}`, { method: 'PATCH', body: JSON.stringify(payload) });
      showToast('Agent updated successfully', 'success');
    } else {
      await apiFetch(`/agents?user_id=${USER_ID}&tenant_id=${TENANT_ID}`, {
        method: 'POST', body: JSON.stringify(payload),
      });
      showToast('Agent created successfully! 🎉', 'success');
    }
    closeCreateAgentModal();
    await loadAgents();
    loadDashboard();
  } catch (err) {
    showToast(`Error: ${err.message}`, 'error');
  } finally {
    label.style.display = 'inline';
    spinner.style.display = 'none';
    btn.disabled = false;
  }
}

async function deactivateAgent(agentId, name) {
  if (!confirm(`Deactivate agent "${name}"? It can be reactivated later.`)) return;
  try {
    await apiFetch(`/agents/${agentId}`, { method: 'DELETE' });
    showToast(`Agent "${name}" deactivated`, 'info');
    await loadAgents();
    loadDashboard();
  } catch (err) {
    showToast(`Error: ${err.message}`, 'error');
  }
}

// ── Agent Detail Modal ─────────────────────────────────────────────────

async function openAgentDetail(agentId) {
  const overlay = document.getElementById('agent-detail-overlay');
  const body    = document.getElementById('agent-detail-body');
  overlay.classList.add('active');
  body.innerHTML = `<div class="loading-state"><div class="spinner"></div></div>`;

  try {
    const a = await apiFetch(`/agents/${agentId}`);
    const kb = a.knowledge_base;

    document.getElementById('detail-agent-name').textContent  = a.name;
    document.getElementById('detail-agent-topic').textContent = a.topic;

    body.innerHTML = `
      <div class="kb-stats-row">
        <div class="kb-stat"><span class="kb-stat-val">${kb?.total_documents ?? 0}</span><span class="kb-stat-key">Documents</span></div>
        <div class="kb-stat"><span class="kb-stat-val">${formatNum(kb?.total_chunks ?? 0)}</span><span class="kb-stat-key">Chunks</span></div>
        <div class="kb-stat"><span class="kb-stat-val">${a.llm_temperature ?? '—'}</span><span class="kb-stat-key">Temperature</span></div>
        <div class="kb-stat"><span class="kb-stat-val">${a.llm_max_tokens ?? '—'}</span><span class="kb-stat-key">Max Tokens</span></div>
      </div>
      <div class="detail-grid">
        <div class="detail-field">
          <div class="detail-field-label">LLM Model</div>
          <div class="detail-field-value" style="font-size:11px;font-family:'JetBrains Mono',monospace;color:var(--accent-cyan)">${escHtml(a.llm_model)}</div>
        </div>
        <div class="detail-field">
          <div class="detail-field-label">Embedding Model</div>
          <div class="detail-field-value" style="font-size:11px;font-family:'JetBrains Mono',monospace;color:var(--accent-cyan)">${escHtml(a.embedding_model)}</div>
        </div>
        <div class="detail-field">
          <div class="detail-field-label">Pinecone Namespace</div>
          <div class="detail-field-value" style="font-size:10px;font-family:'JetBrains Mono',monospace">${escHtml(a.pinecone_namespace)}</div>
        </div>
        <div class="detail-field">
          <div class="detail-field-label">Status</div>
          <div class="detail-field-value"><span class="meta-badge ${a.is_active ? 'active' : 'inactive'}">${a.is_active ? '● Active' : '○ Inactive'}</span></div>
        </div>
        <div class="detail-field">
          <div class="detail-field-label">Created</div>
          <div class="detail-field-value">${formatDate(a.created_at)}</div>
        </div>
        <div class="detail-field">
          <div class="detail-field-label">Updated</div>
          <div class="detail-field-value">${formatDate(a.updated_at)}</div>
        </div>
      </div>

      <div style="margin-bottom:16px">
        <div class="section-label" style="margin-bottom:8px">System Prompt</div>
        <div class="detail-prompt-box">${escHtml(a.system_prompt)}</div>
      </div>

      <div style="display:flex;gap:10px;flex-wrap:wrap">
        <button class="btn btn-primary" onclick="startChatWithAgent('${a.id}', '${escHtml(a.name)}'); closeAgentDetail()">
          💬 Chat with this agent
        </button>
        <button class="btn btn-ghost" onclick="selectDocAgent('${a.id}', '${escHtml(a.name)}'); closeAgentDetail(); navigate('documents')">
          📄 Manage documents
        </button>
        <button class="btn btn-ghost" onclick="closeAgentDetail(); openEditAgentModal('${a.id}')">
          ✏️ Edit
        </button>
      </div>
    `;
  } catch (err) {
    body.innerHTML = `<div class="empty-state"><div class="empty-icon">⚠️</div><p>${escHtml(err.message)}</p></div>`;
  }
}

function closeAgentDetail(e) {
  if (e && e.target !== e.currentTarget) return;
  document.getElementById('agent-detail-overlay').classList.remove('active');
}

// ════════════════════════════════════════════════════════════════════════
// DOCUMENTS PAGE
// ════════════════════════════════════════════════════════════════════════

async function loadDocumentAgents() {
  const container = document.getElementById('doc-agent-selector');
  container.innerHTML = `<div class="loading-state small"><div class="spinner sm"></div></div>`;
  try {
    const data = await apiFetch(`/agents?user_id=${USER_ID}&active_only=true`);
    state.agents = data.agents || [];
    if (!state.agents.length) {
      container.innerHTML = `<div class="empty-state small" style="padding:20px"><p>No agents yet. <span class="link-text" onclick="navigate('agents')">Create one →</span></p></div>`;
      return;
    }
    container.innerHTML = state.agents.map(a => `
      <button class="agent-selector-btn ${state.selectedDocAgent?.id === a.id ? 'selected' : ''}"
              id="agent-sel-${a.id}"
              onclick="selectDocAgent('${a.id}', '${escHtml(a.name)}')">
        <div class="agent-avatar" style="width:26px;height:26px;font-size:11px">${a.name.charAt(0)}</div>
        ${escHtml(a.name)}
      </button>
    `).join('');

    if (state.selectedDocAgent) {
      selectDocAgent(state.selectedDocAgent.id, state.selectedDocAgent.name);
    }
  } catch (err) {
    container.innerHTML = `<div class="empty-state small"><p>${escHtml(err.message)}</p></div>`;
  }
}

function selectDocAgent(agentId, agentName) {
  state.selectedDocAgent = { id: agentId, name: agentName };

  // Update selector UI
  document.querySelectorAll('.agent-selector-btn').forEach(b => b.classList.remove('selected'));
  const btn = document.getElementById(`agent-sel-${agentId}`);
  if (btn) btn.classList.add('selected');

  // Show upload card
  document.getElementById('upload-card').style.display = 'block';
  document.getElementById('docs-list-card').style.display = 'block';
  document.getElementById('upload-agent-name').textContent = agentName;
  refreshDocuments();
}

async function refreshDocuments() {
  if (!state.selectedDocAgent) return;
  const container = document.getElementById('documents-table-container');
  container.innerHTML = `<div class="loading-state"><div class="spinner"></div></div>`;
  try {
    const docs = await apiFetch(`/agents/${state.selectedDocAgent.id}/documents`);
    renderDocumentsTable(docs);
  } catch (err) {
    // If endpoint not found or no docs, show empty
    container.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">📭</div>
        <p>${err.message.includes('404') || err.message.includes('Not Found') ? 'No documents uploaded yet.' : escHtml(err.message)}</p>
      </div>`;
  }
}

function renderDocumentsTable(docs) {
  const container = document.getElementById('documents-table-container');
  if (!docs || !docs.length) {
    container.innerHTML = `<div class="empty-state"><div class="empty-icon">📭</div><p>No documents uploaded yet. Drag & drop files above.</p></div>`;
    return;
  }
  container.innerHTML = `
    <table class="docs-table">
      <thead>
        <tr>
          <th>Filename</th>
          <th>Status</th>
          <th>Type</th>
          <th>Uploaded</th>
          <th>Actions</th>
        </tr>
      </thead>
      <tbody>
        ${docs.map(d => `
          <tr>
            <td class="doc-name">📄 ${escHtml(d.file_name)}</td>
            <td><span class="doc-status-badge ${d.status}">${d.status}</span></td>
            <td>${escHtml(d.mime_type || '—')}</td>
            <td>${formatDate(d.uploaded_at)}</td>
            <td>
              <button class="btn-icon btn-danger" title="Delete document" onclick="deleteDocument('${d.id}', '${escHtml(d.file_name)}')">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/></svg>
              </button>
            </td>
          </tr>
        `).join('')}
      </tbody>
    </table>
  `;
}

async function deleteDocument(docId, name) {
  if (!confirm(`Delete "${name}"? This will also remove its vectors from Pinecone.`)) return;
  try {
    await apiFetch(`/agents/${state.selectedDocAgent.id}/documents/${docId}`, { method: 'DELETE' });
    showToast(`"${name}" deleted`, 'info');
    refreshDocuments();
  } catch (err) {
    showToast(`Error: ${err.message}`, 'error');
  }
}

// ── Drag & Drop Upload ──────────────────────────────────────────────────

function initDropZone() {
  const zone = document.getElementById('drop-zone');
  if (!zone) return;

  zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('dragover'); });
  zone.addEventListener('dragleave', () => zone.classList.remove('dragover'));
  zone.addEventListener('drop', e => {
    e.preventDefault();
    zone.classList.remove('dragover');
    if (!state.selectedDocAgent) { showToast('Please select an agent first.', 'warning'); return; }
    uploadFiles(Array.from(e.dataTransfer.files));
  });
}

function handleFileSelect(e) {
  if (!state.selectedDocAgent) { showToast('Please select an agent first.', 'warning'); return; }
  uploadFiles(Array.from(e.target.files));
  e.target.value = '';
}

async function uploadFiles(files) {
  if (!files.length) return;

  const queueContainer = document.getElementById('upload-queue');
  const queueList = document.getElementById('upload-queue-list');
  queueContainer.style.display = 'block';

  for (const file of files) {
    const itemId = 'upload-' + Date.now() + '-' + Math.random().toString(36).slice(2);
    const item = document.createElement('div');
    item.className = 'upload-item';
    item.id = itemId;
    item.innerHTML = `
      <div class="upload-item-icon">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
          <polyline points="14 2 14 8 20 8"/>
        </svg>
      </div>
      <div class="upload-item-info">
        <div class="upload-item-name">${escHtml(file.name)}</div>
        <div class="upload-item-size">${formatSize(file.size)}</div>
        <div class="progress-bar-wrap"><div class="progress-bar" id="pb-${itemId}" style="width:0%"></div></div>
      </div>
      <span class="upload-status uploading" id="status-${itemId}">Uploading…</span>
    `;
    queueList.appendChild(item);

    // Animate progress (fake for UX)
    let prog = 0;
    const progInterval = setInterval(() => {
      prog = Math.min(prog + (Math.random() * 15 + 5), 90);
      const pb = document.getElementById('pb-' + itemId);
      if (pb) pb.style.width = prog + '%';
    }, 200);

    try {
      const formData = new FormData();
      formData.append('file', file);

      const res = await fetch(`${API_BASE}/agents/${state.selectedDocAgent.id}/documents?user_id=${USER_ID}`, {
        method: 'POST',
        body: formData,
      });

      clearInterval(progInterval);
      const pb = document.getElementById('pb-' + itemId);
      const st = document.getElementById('status-' + itemId);

      if (res.ok) {
        if (pb) pb.style.width = '100%';
        if (st) { st.textContent = 'Done ✓'; st.className = 'upload-status done'; }
        showToast(`"${file.name}" uploaded successfully`, 'success');
        refreshDocuments();
      } else {
        let errMsg = 'Upload failed';
        try { const d = await res.json(); errMsg = d.detail || errMsg; } catch {}
        if (pb) pb.style.width = '100%';
        if (st) { st.textContent = 'Failed'; st.className = 'upload-status error'; }
        showToast(`Failed: ${errMsg}`, 'error');
      }
    } catch (err) {
      clearInterval(progInterval);
      const st = document.getElementById('status-' + itemId);
      if (st) { st.textContent = 'Error'; st.className = 'upload-status error'; }
      showToast(`Upload error: ${err.message}`, 'error');
    }

    await sleep(300);
  }
}

// ════════════════════════════════════════════════════════════════════════
// CHAT PAGE
// ════════════════════════════════════════════════════════════════════════

async function loadChatPage() {
  await loadChatSessions();
  await loadChatAgentSelector();
}

async function loadChatSessions() {
  const list = document.getElementById('sessions-list');
  list.innerHTML = `<div class="loading-state small"><div class="spinner sm"></div></div>`;
  try {
    const sessions = await apiFetch(`/chat/sessions?user_id=${USER_ID}`);
    state.chat.sessions = sessions;
    renderSessionsList(sessions);
    document.getElementById('stat-sessions').textContent = sessions.length;
  } catch {
    list.innerHTML = `<div class="session-item" style="color:var(--text-muted);font-size:12px;text-align:center;padding:16px">No sessions yet</div>`;
  }
}

function renderSessionsList(sessions) {
  const list = document.getElementById('sessions-list');
  if (!sessions.length) {
    list.innerHTML = `<div style="padding:20px;text-align:center;font-size:12px;color:var(--text-muted)">No conversations yet.<br>Start a new chat below!</div>`;
    return;
  }
  list.innerHTML = sessions.map(s => `
    <div class="session-item ${state.chat.sessionId === s.id ? 'active' : ''}"
         id="session-${s.id}"
         onclick="loadSession('${s.id}')">
      <div class="session-item-title">💬 ${escHtml(s.title || 'Chat Session')}</div>
      <div class="session-item-meta">${formatDate(s.created_at)}</div>
    </div>
  `).join('');
}

async function loadChatAgentSelector() {
  const sel = document.getElementById('chat-agent-select');
  try {
    const data = await apiFetch(`/agents?user_id=${USER_ID}&active_only=true`);
    state.agents = data.agents || [];
    sel.innerHTML = `<option value="">🧠 Auto (Orchestrator)</option>` +
      state.agents.map(a => `<option value="${a.id}">${escHtml(a.name)}</option>`).join('');

    if (state.chat.agentId) {
      sel.value = state.chat.agentId;
      updateChatAgent();
    }
  } catch { /* silently fail */ }
}

function updateChatAgent() {
  const sel  = document.getElementById('chat-agent-select');
  const val  = sel.value;
  const label = document.getElementById('chat-agent-label');
  const badge = document.getElementById('chat-agent-badge');

  state.chat.agentId = val || null;

  if (val) {
    const agent = state.agents.find(a => a.id === val);
    label.textContent = agent ? `${agent.name}` : 'Selected Agent';
    badge.style.background = 'rgba(124,58,237,0.1)';
  } else {
    label.textContent = 'Orchestrator Mode';
    badge.style.background = '';
  }
}

async function loadSession(sessionId) {
  state.chat.sessionId = sessionId;

  // Update UI active state
  document.querySelectorAll('.session-item').forEach(s => s.classList.remove('active'));
  document.getElementById(`session-${sessionId}`)?.classList.add('active');
  document.getElementById('chat-session-id').textContent = `Session: ${sessionId.slice(0, 8)}…`;

  // Hide welcome
  document.getElementById('welcome-message')?.remove();

  const container = document.getElementById('messages-container');
  container.innerHTML = `<div class="loading-state"><div class="spinner"></div></div>`;

  try {
    const history = await apiFetch(`/chat/sessions/${sessionId}`);
    container.innerHTML = '';
    history.messages.forEach(msg => appendMessage(msg.role, msg.content, {
      agentName: msg.agent_name,
      sources:   msg.sources,
      timestamp: msg.created_at,
    }));
    container.scrollTop = container.scrollHeight;
  } catch (err) {
    container.innerHTML = `<div class="empty-state"><p>${escHtml(err.message)}</p></div>`;
  }
}

function newChatSession() {
  state.chat.sessionId = null;
  document.getElementById('chat-session-id').textContent = '';
  document.querySelectorAll('.session-item').forEach(s => s.classList.remove('active'));

  const container = document.getElementById('messages-container');
  container.innerHTML = `
    <div class="welcome-message" id="welcome-message">
      <div class="welcome-icon">
        <svg width="48" height="48" viewBox="0 0 28 28" fill="none">
          <path d="M14 2L25 8V20L14 26L3 20V8L14 2Z" fill="url(#wGrad2)" stroke="rgba(0,212,255,0.3)" stroke-width="0.5"/>
          <circle cx="14" cy="14" r="4" fill="rgba(0,212,255,0.9)"/>
          <path d="M14 6V10M14 18V22M6 14H10M18 14H22" stroke="rgba(0,212,255,0.6)" stroke-width="1.5" stroke-linecap="round"/>
          <defs><linearGradient id="wGrad2" x1="3" y1="2" x2="25" y2="26"><stop offset="0%" stop-color="#0a1628"/><stop offset="100%" stop-color="#0d2040"/></linearGradient></defs>
        </svg>
      </div>
      <h2 class="welcome-title">New Conversation</h2>
      <p class="welcome-text">Ask anything. The orchestrator will route your query to the best agent.</p>
      <div class="quick-prompts">
        <button class="quick-prompt" onclick="setQuickPrompt(this)">What topics can you help me with?</button>
        <button class="quick-prompt" onclick="setQuickPrompt(this)">Summarize the available knowledge</button>
      </div>
    </div>`;
}

function startChatWithAgent(agentId, agentName) {
  navigate('chat');
  const sel = document.getElementById('chat-agent-select');
  if (sel) {
    sel.value = agentId;
    updateChatAgent();
  }
  newChatSession();
}

function clearChatMessages() {
  newChatSession();
  state.chat.sessionId = null;
}

function setQuickPrompt(btn) {
  const input = document.getElementById('chat-input');
  input.value = btn.textContent;
  input.focus();
  autoResize(input);
}

// ── Send Message ───────────────────────────────────────────────────────

function handleChatKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
}

async function sendMessage() {
  if (state.chat.sending) return;

  const input = document.getElementById('chat-input');
  const msg   = input.value.trim();
  if (!msg) return;

  // Clear welcome
  document.getElementById('welcome-message')?.remove();

  // Clear input
  input.value = '';
  autoResize(input);

  // Show user message
  appendMessage('user', msg);

  // Disable send
  state.chat.sending = true;
  document.getElementById('send-btn').disabled = true;

  // Show typing indicator
  const typingId = showTypingIndicator();

  try {
    const body = {
      user_id:    USER_ID,
      message:    msg,
      session_id: state.chat.sessionId || undefined,
      agent_id:   state.chat.agentId   || undefined,
      tenant_id:  TENANT_ID,
    };

    const res = await apiFetch('/chat', { method: 'POST', body: JSON.stringify(body) });

    removeTypingIndicator(typingId);

    state.chat.sessionId = res.session_id;
    document.getElementById('chat-session-id').textContent = `Session: ${res.session_id.slice(0, 8)}…`;

    appendMessage('assistant', res.answer, {
      agentName:     res.agent_used?.name,
      agentTopic:    res.agent_used?.topic,
      sources:       res.sources,
      routingReason: res.routing_reason,
      tokens:        `${res.prompt_tokens + res.completion_tokens} tokens`,
    });

    await loadChatSessions();

  } catch (err) {
    removeTypingIndicator(typingId);
    appendMessage('assistant', `⚠️ Error: ${err.message}. Please check that the backend is running at \`${API_BASE}\`.`, {});
  } finally {
    state.chat.sending = false;
    document.getElementById('send-btn').disabled = false;
    input.focus();
  }
}

function appendMessage(role, content, meta = {}) {
  const container = document.getElementById('messages-container');

  const msgId = 'msg-' + Date.now() + '-' + Math.random().toString(36).slice(2);
  const el = document.createElement('div');
  el.className = `message ${role}`;
  el.id = msgId;

  const isUser = role === 'user';
  const avatarContent = isUser ? 'D' : '🤖';

  const agentTag = meta.agentName
    ? `<span class="agent-used-tag">⚡ ${escHtml(meta.agentName)}</span>`
    : '';

  const sourcesTag = (meta.sources && meta.sources.length)
    ? `<button class="sources-btn" onclick="showSources(${JSON.stringify(meta.sources || []).replace(/"/g, '&quot;')})">📚 ${meta.sources.length} source${meta.sources.length > 1 ? 's' : ''}</button>`
    : '';

  const tokensSpan = meta.tokens
    ? `<span style="font-size:10px;color:var(--text-muted)">${meta.tokens}</span>`
    : '';

  const timestamp = meta.timestamp
    ? `<span>${formatTime(meta.timestamp)}</span>`
    : `<span>${formatTime(new Date().toISOString())}</span>`;

  const formattedContent = formatMessageContent(content);

  el.innerHTML = `
    <div class="message-avatar">${avatarContent}</div>
    <div class="message-content">
      <div class="message-bubble">${formattedContent}</div>
      <div class="message-meta">
        ${timestamp}
        ${agentTag}
        ${sourcesTag}
        ${tokensSpan}
      </div>
    </div>
  `;

  container.appendChild(el);
  container.scrollTop = container.scrollHeight;
  return msgId;
}

function formatMessageContent(text) {
  if (!text) return '';
  // Basic markdown-like rendering
  return escHtml(text)
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/`(.+?)`/g, '<code>$1</code>')
    .replace(/\n\n/g, '</p><p>')
    .replace(/\n/g, '<br>')
    .replace(/^(.+)$/, '<p>$1</p>');
}

function showTypingIndicator() {
  const container = document.getElementById('messages-container');
  const id = 'typing-' + Date.now();
  const el = document.createElement('div');
  el.className = 'typing-indicator';
  el.id = id;
  el.innerHTML = `
    <div class="message-avatar" style="background:rgba(0,212,255,0.1);color:var(--accent-cyan);border:1px solid rgba(0,212,255,0.2)">🤖</div>
    <div class="typing-dots">
      <div class="typing-dot"></div>
      <div class="typing-dot"></div>
      <div class="typing-dot"></div>
    </div>
  `;
  container.appendChild(el);
  container.scrollTop = container.scrollHeight;
  return id;
}

function removeTypingIndicator(id) {
  document.getElementById(id)?.remove();
}

function showSources(sources) {
  const panel   = document.getElementById('sources-panel');
  const content = document.getElementById('sources-content');
  panel.style.display = 'block';

  content.innerHTML = sources.length
    ? sources.map(s => `
        <div class="source-item">
          <span class="source-score">${(s.score * 100).toFixed(0)}%</span>
          <div>
            <div class="source-filename">📄 ${escHtml(s.filename)}</div>
            <div class="source-pages">
              Chunk #${s.chunk_index}
              ${s.page_from != null ? `· Pages ${s.page_from}–${s.page_to ?? s.page_from}` : ''}
            </div>
          </div>
        </div>
      `).join('')
    : `<div class="empty-state" style="padding:16px"><p>No sources available.</p></div>`;
}

function autoResize(el) {
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, 160) + 'px';
}

// ════════════════════════════════════════════════════════════════════════
// TOAST NOTIFICATIONS
// ════════════════════════════════════════════════════════════════════════

function showToast(message, type = 'info') {
  const container = document.getElementById('toast-container');
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;

  const icons = { success: '✅', error: '❌', info: 'ℹ️', warning: '⚠️' };
  toast.innerHTML = `<span>${icons[type] || 'ℹ️'}</span><span>${escHtml(message)}</span>`;
  container.appendChild(toast);

  setTimeout(() => toast.remove(), 4200);
}

// ════════════════════════════════════════════════════════════════════════
// UTILITIES
// ════════════════════════════════════════════════════════════════════════

function escHtml(str) {
  if (str == null) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function formatNum(n) {
  if (n == null) return '0';
  return Number(n).toLocaleString();
}

function formatSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

function formatTime(iso) {
  if (!iso) return '';
  return new Date(iso).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

// ════════════════════════════════════════════════════════════════════════
// INIT
// ════════════════════════════════════════════════════════════════════════

document.addEventListener('DOMContentLoaded', () => {
  // Init drop zone
  initDropZone();

  // Check API health
  checkApiHealth();
  setInterval(checkApiHealth, 30000);

  // Load initial page
  navigate('dashboard');

  // Prevent nav-item default link behavior
  document.querySelectorAll('.nav-item').forEach(el => {
    el.addEventListener('click', e => e.preventDefault());
  });
});
