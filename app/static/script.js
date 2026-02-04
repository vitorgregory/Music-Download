document.addEventListener("DOMContentLoaded", () => {
    // Inicializa controles
    setupEventListeners();
    // Inicia Loop de Estado
    setInterval(fetchState, 1500);
    // Attach CSRF token for axios (if present)
    try {
        const meta = document.querySelector('meta[name="csrf-token"]');
        if (meta) axios.defaults.headers.common['X-CSRFToken'] = meta.getAttribute('content');
    } catch (e) { /* ignore */ }
    
    // Initialize Socket.IO for real-time selection events
    initializeSocketIO();
});

// Socket.IO event handling
function initializeSocketIO() {
    try {
        // Try to connect to Socket.IO server
        const socket = io();
        
        // Listen for selection_required event from server
        socket.on('selection_required', (data) => {
            console.log('Selection required event received:', data);
            if (data.options && Array.isArray(data.options)) {
                // Sync the options with frontend
                syncSelectionOptions(data.options);
                // Show the selection area
                const selArea = document.getElementById('selection-area');
                if (selArea) {
                    selArea.classList.remove('d-none');
                    // Auto-focus search if available
                    const searchBox = document.getElementById('selection-search');
                    if (searchBox) setTimeout(() => searchBox.focus(), 100);
                }
            }
        });
        
        // Connection status logging
        socket.on('connect', () => {
            console.log('[Socket.IO] Connected to server');
        });
        
        socket.on('disconnect', () => {
            console.log('[Socket.IO] Disconnected from server');
        });
        
    } catch (e) {
        console.warn('Socket.IO initialization failed (not critical):', e);
    }
}

let selectionOptions = [];
let selectionSignature = "";

function setupEventListeners() {
    const clickParams = [
        ['analyze-btn', analyzeLink],
        ['download-btn', addToQueue],
        ['pause-btn', togglePause],
        ['submit-selection', submitSelection],
        ['submit-2fa', submit2FA],
        ['submit-login', submitLogin],
        ['stop-wrapper-btn', stopWrapper],
        ['nav-login-btn', () => { // <--- NOVO
            document.getElementById('login-form').classList.remove('d-none');
            toggleLogs(); // Abre a gaveta para ver o form
        }]
    ];

    clickParams.forEach(([id, fn]) => {
        const el = document.getElementById(id);
        if (el) el.addEventListener('click', fn);
    });

    const selectionFilters = [
        'selection-search',
        'selection-type-filter',
        'selection-tag-filter',
        'selection-year-filter'
    ];
    selectionFilters.forEach((id) => {
        const el = document.getElementById(id);
        if (el) el.addEventListener('input', renderSelectionList);
    });
}

// --- CORE LOGIC ---

async function fetchState() {
    try {
        const res = await axios.get('/api/state');
        const { wrapper, downloader, queue, wrapper_installed, downloader_installed } = res.data;

        updateWrapperUI(wrapper);
        updateDownloaderUI(downloader);
        updateQueueUI(queue);

        // Show installation warnings
        const warnContainer = getOrCreateWarnContainer();
        warnContainer.innerHTML = '';
        if (!wrapper_installed) {
            const el = document.createElement('div');
            el.className = 'alert alert-warning text-center mb-3';
            el.textContent = 'Wrapper binary not found. Place the wrapper at ./wrapper/wrapper to enable login.';
            warnContainer.appendChild(el);
        }
        if (!downloader_installed) {
            const el = document.createElement('div');
            el.className = 'alert alert-warning text-center mb-3';
            el.textContent = 'Go downloader not found. Clone the apple-music-downloader project into ./apple-music-downloader.';
            warnContainer.appendChild(el);
        }

    } catch (e) {
        console.error("Sync Error:", e);
    }
}

function getOrCreateWarnContainer() {
    let c = document.getElementById('install-warnings');
    if (!c) {
        c = document.createElement('div');
        c.id = 'install-warnings';
        const root = document.querySelector('.container');
        if (root) root.parentNode.insertBefore(c, root);
        else document.body.insertBefore(c, document.body.firstChild);
    }
    return c;
}

function updateWrapperUI(w) {
    // Status Dot
    const dot = document.getElementById('wrapper-status-dot');
    if (dot) {
        dot.style.backgroundColor = w.running ? '#28a745' : '#dc3545';
        dot.style.boxShadow = w.running ? '0 0 8px #28a745' : 'none';
        dot.title = w.running ? "Conectado" : "Desconectado";
    }

    // NOVO: Botão da Navbar
    const navBtn = document.getElementById('nav-login-btn');
    if (navBtn) {
        // Se estiver rodando, esconde. Se parou, mostra.
        navBtn.classList.toggle('d-none', w.running);
    }

    // Logs e Form (Mantém igual)
    const logBox = document.getElementById('wrapper-logs');
    if (logBox && w.logs.length) {
        logBox.innerHTML = w.logs.map(l => `<div>${l}</div>`).join('');
        logBox.scrollTop = logBox.scrollHeight;
    }

    // Mostra form de login dentro do drawer se não estiver rodando
    const loginForm = document.getElementById('login-form');
    if (loginForm && !w.running) {
        // Opcional: abrir automaticamente se quiser, mas pode ser intrusivo
    }

    document.getElementById('login-btn')?.classList.toggle('d-none', w.running);
    document.getElementById('stop-wrapper-btn')?.classList.toggle('d-none', !w.running);
    document.getElementById('twofa-modal')?.classList.toggle('d-none', !w.needs_2fa);
}

function updateDownloaderUI(d) {
    // Selection Modal
    const selArea = document.getElementById('selection-area');
    if (d.needs_selection) {
        selArea.classList.remove('d-none');
        syncSelectionOptions(d.options);
    } else {
        selArea.classList.add('d-none');
    }

    // Logs
    const logBox = document.getElementById('downloader-logs');
    if (logBox && d.logs.length) {
        logBox.innerHTML = d.logs.map(l => `<div>${l}</div>`).join('');
        logBox.scrollTop = logBox.scrollHeight;
    }
}

function updateQueueUI(q) {
    const tableActive = document.getElementById('queue-table-active');
    const tableHistory = document.getElementById('queue-table-history');
    
    // Pause Button State
    const pBtn = document.getElementById('pause-btn');
    if (pBtn) {
        pBtn.innerHTML = q.paused ? '<i class="fas fa-play"></i> Retomar' : '<i class="fas fa-pause"></i> Pausar';
        pBtn.className = q.paused ? 'btn btn-success btn-sm rounded-pill px-3' : 'btn btn-outline-warning btn-sm rounded-pill px-3';
    }

    // Atualiza badges
    let activeItems = q.items.filter(i => ['pending', 'processing'].includes(i.status));
    let historyItems = q.items.filter(i => !['pending', 'processing'].includes(i.status));

    document.getElementById('count-active').innerText = activeItems.length;
    document.getElementById('count-history').innerText = historyItems.length;

    // Render Table Rows
    activeItems = activeItems.sort((a, b) => (a.position ?? 0) - (b.position ?? 0));
    renderQueueTable(tableActive, activeItems, true);
    renderQueueTable(tableHistory, historyItems, false);
}

function renderQueueTable(container, items, isActiveTab) {
    if (!items.length) {
        container.innerHTML = `<tr><td colspan="6" class="text-center text-muted py-4">Nenhum item</td></tr>`;
        return;
    }

    const rows = items.map((item, index) => {
        const progress = item.progress || "0";
        const progressValue = Number(progress);
        const isValidProgress = Number.isFinite(progressValue);
        const progressPercent = isValidProgress ? Math.min(Math.max(progressValue, 0), 100) : 0;
        
        let statusBadge = "";
        let statusClass = "";
        
        if (item.status === 'processing') { 
            statusBadge = '<span class="badge bg-warning text-dark"><i class="fas fa-spinner fa-spin"></i> Processando</span>';
            statusClass = "status-processing";
        } else if (item.status === 'completed') { 
            statusBadge = '<span class="badge bg-success"><i class="fas fa-check"></i> Concluído</span>';
            statusClass = "status-completed";
        } else if (item.status === 'failed') { 
            statusBadge = '<span class="badge bg-danger"><i class="fas fa-times"></i> Falha</span>';
            statusClass = "status-failed";
        } else if (item.status === 'cancelled') { 
            statusBadge = '<span class="badge bg-danger"><i class="fas fa-ban"></i> Cancelado</span>';
            statusClass = "status-failed";
        } else if (item.status === 'pending') { 
            statusBadge = '<span class="badge bg-secondary"><i class="fas fa-clock"></i> Na fila</span>';
            statusClass = "status-pending";
        }

        let title = item.title === "Aguardando metadados..." ? "Carregando..." : item.title;
        const progressDisplay = isValidProgress ? `${progressPercent}%` : "—";
        
        // Action buttons
        let actionHtml = "";
        if (item.status === 'processing') {
            actionHtml = `<button onclick="stopTask(${item.id})" class="btn btn-sm btn-danger" title="Parar"><i class="fas fa-stop-circle"></i></button>`;
        } else if (item.status === 'pending') {
            actionHtml = `
                <div class="btn-group btn-group-sm" role="group">
                    <button onclick="moveTask(${item.id}, 'up')" class="btn btn-outline-secondary" title="Acima"><i class="fas fa-arrow-up"></i></button>
                    <button onclick="moveTask(${item.id}, 'down')" class="btn btn-outline-secondary" title="Abaixo"><i class="fas fa-arrow-down"></i></button>
                    <button onclick="cancelTask(${item.id}, 'pending')" class="btn btn-outline-danger" title="Cancelar"><i class="fas fa-ban"></i></button>
                </div>
            `;
        } else {
            actionHtml = `<button onclick="deleteHistory(${item.id})" class="btn btn-sm btn-outline-secondary" title="Remover"><i class="fas fa-trash"></i></button>`;
        }

        const formatBadge = `<span class="badge badge-soft">${item.format.toUpperCase()}</span>`;
        
        return `
            <tr class="queue-row ${statusClass}">
                <td><small>#${item.id}</small></td>
                <td>
                    <div class="text-truncate" title="${title}"><strong>${title}</strong></div>
                    <small class="text-muted text-truncate d-block" title="${item.link}">${item.link}</small>
                    ${item.existing_path ? `<small class="text-success d-block"><i class="fas fa-check-circle"></i> ${truncatePath(item.existing_path, 40)}</small>` : ''}
                </td>
                <td>${statusBadge}</td>
                <td>
                    ${item.status === 'processing' 
                        ? `<div class="progress" style="height: 20px;"><div class="progress-bar" style="width: ${progressPercent}%">${progressDisplay}</div></div>`
                        : `<small>${progressDisplay}</small>`
                    }
                </td>
                <td>${formatBadge}</td>
                <td>${actionHtml}</td>
            </tr>
        `;
    }).join('');

    container.innerHTML = rows;
}

// New function to remove items from history
function deleteHistory(id) {
    if(confirm("Remover item do histórico?")) {
        // Mark as deleted by moving to a special status or just hide
        // For now, we can call cancel to keep consistency
        axios.post('/api/cancel_task', {id, status: 'history'}).catch(() => {});
    }
}

// --- ACTIONS ---

async function analyzeLink() {
    const link = document.getElementById('link-box').value;
    if (!link) return;
    
    const btn = document.getElementById('analyze-btn');
    const originalHTML = btn.innerHTML;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
    btn.disabled = true;

    try {
        const res = await axios.post('/analyze_link', new URLSearchParams({link}));
        if (res.data.status === 'ok') {
            const m = res.data.metadata;
            document.getElementById('preview-area').classList.remove('d-none');
            document.getElementById('preview-title').innerText = m.title;
            document.getElementById('preview-type').innerText = m.type;
            const img = document.getElementById('preview-img');
            if (m.image) { img.src = m.image; img.classList.remove('d-none'); }
        } else {
            alert('Link inválido');
        }
    } catch { alert('Erro na análise'); } 
    finally {
        btn.innerHTML = originalHTML;
        btn.disabled = false;
    }
}

async function addToQueue() {
    const link = document.getElementById('link-box').value;
    const title = document.getElementById('preview-title').innerText;
    const quality = document.querySelector('input[name="dl_quality"]:checked').value;
    
    let fmt = 'alac', special = false;
    if (quality === 'aac') fmt = 'aac';
    if (quality === 'atmos') { fmt = 'atmos'; special = true; }

    const btn = document.getElementById('download-btn');
    btn.disabled = true;
    
    try {
        await axios.post('/download', new URLSearchParams({
            link, title, format: fmt, special_audio: special
        }));
        btn.innerText = "Adicionado!";
        btn.classList.add('btn-success');
        document.getElementById('preview-area').classList.add('d-none');
        document.getElementById('link-box').value = '';
        setTimeout(() => {
            btn.innerText = "Baixar";
            btn.classList.remove('btn-success');
            btn.disabled = false;
        }, 1500);
    } catch {
        alert("Erro ao adicionar");
        btn.disabled = false;
    }
}

// --- UTILS ---
function togglePause() {
    const btn = document.getElementById('pause-btn');
    const isPaused = btn.innerText.includes('Retomar');
    axios.post('/api/pause_queue', {paused: !isPaused});
}

function stopTask(id) {
    if(confirm("Parar download?")) axios.post('/api/cancel_task', {id, status: 'processing'});
}

function cancelTask(id, status) {
    if(confirm("Cancelar item da fila?")) axios.post('/api/cancel_task', {id, status});
}

function moveTask(id, direction) {
    axios.post('/api/move_queue', {id, direction});
}

function stopWrapper() { axios.post('/stop_wrapper'); }
function submitLogin() {
    const e = document.getElementById('email').value;
    const p = document.getElementById('password').value;
    axios.post('/login_wrapper', new URLSearchParams({email:e, password:p}));
    document.getElementById('login-form').classList.add('d-none');
}
function submit2FA() {
    axios.post('/submit_2fa', new URLSearchParams({twofa_code: document.getElementById('twofa-code').value}));
    document.getElementById('twofa-modal').classList.add('d-none');
}

function syncSelectionOptions(opts) {
    const signature = JSON.stringify(opts || []);
    if (signature === selectionSignature) return;
    selectionSignature = signature;
    selectionOptions = Array.isArray(opts) ? opts : [];
    updateSelectionFilters(selectionOptions);
    renderSelectionList();
}

function updateSelectionFilters(opts) {
    const tagFilter = document.getElementById('selection-tag-filter');
    const yearFilter = document.getElementById('selection-year-filter');
    if (!tagFilter || !yearFilter) return;

    const tags = new Set();
    const years = new Set();
    opts.forEach((opt) => {
        (opt.tags || []).forEach((tag) => tags.add(tag));
        if (opt.date) {
            const yearMatch = opt.date.match(/\b(\d{4})\b/);
            if (yearMatch) years.add(yearMatch[1]);
        }
    });

    const currentTag = tagFilter.value;
    const currentYear = yearFilter.value;

    tagFilter.innerHTML = '<option value="">Todas as edições</option>' +
        Array.from(tags).sort().map(tag => `<option value="${tag}">${tag}</option>`).join('');
    yearFilter.innerHTML = '<option value="">Todas as datas</option>' +
        Array.from(years).sort().reverse().map(year => `<option value="${year}">${year}</option>`).join('');

    if (currentTag) tagFilter.value = currentTag;
    if (currentYear) yearFilter.value = currentYear;
}

function truncatePath(p, len) {
    if (!p) return '';
    if (p.length <= (len || 60)) return p;
    return '...' + p.slice(- (len - 3));
}

function renderSelectionList() {
    const list = document.getElementById('selection-list');
    if (!list) return;

    const search = document.getElementById('selection-search')?.value?.toLowerCase() || '';
    const typeFilter = document.getElementById('selection-type-filter')?.value || '';
    const tagFilter = document.getElementById('selection-tag-filter')?.value || '';
    const yearFilter = document.getElementById('selection-year-filter')?.value || '';

    const filtered = selectionOptions.filter((opt) => {
        const matchesSearch = !search || `${opt.label} ${opt.extra || ''}`.toLowerCase().includes(search);
        const matchesType = !typeFilter || opt.type === typeFilter;
        const matchesTag = !tagFilter || (opt.tags || []).includes(tagFilter);
        const matchesYear = !yearFilter || (opt.date || '').includes(yearFilter);
        return matchesSearch && matchesType && matchesTag && matchesYear;
    });

    const summary = document.getElementById('selection-summary');
    if (summary) summary.textContent = `${filtered.length} itens`;

    if (!filtered.length) {
        list.innerHTML = `
            <tr>
                <td colspan="6" class="text-center text-muted py-4">Nenhum item encontrado.</td>
            </tr>`;
        return;
    }

    list.innerHTML = filtered.map(o => {
        let badgeColor = 'bg-secondary';
        if (o.type === 'Album') badgeColor = 'bg-primary';
        if (o.type === 'Single') badgeColor = 'bg-info text-dark';
        if (o.type === 'EP') badgeColor = 'bg-success';
        
        return `
        <tr>
            <td>
                <input class="form-check-input" type="checkbox" value="${o.id}" id="chk-${o.id}">
            </td>
            <td>
                <label class="form-check-label selection-label" for="chk-${o.id}">
                    <div class="fw-bold">${o.label}</div>
                    <div class="text-muted small">${o.extra || '—'}</div>
                </label>
            </td>
            <td><span class="badge ${badgeColor}">${o.type}</span></td>
            <td>
                ${(o.tags||[]).map(t=>`<span class="badge tag-pill me-1">${t}</span>`).join('') || '<span class="text-muted small">—</span>'}
            </td>
            <td class="text-muted small">${o.date || '—'}</td>
            <td class="text-muted small">${o.duration || '—'}</td>
        </tr>`;
    }).join('');
}

function submitSelection() {
    const checked = Array.from(document.querySelectorAll('#selection-list input:checked')).map(c=>c.value);
    if(checked.length) axios.post('/submit_selection', new URLSearchParams({selection: checked.join(',')}));
}
function skipSelection() {
    axios.post('/skip_selection');
}
