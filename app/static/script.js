document.addEventListener("DOMContentLoaded", () => {
    // Inicializa controles
    setupEventListeners();
    // Inicia Loop de Estado
    setInterval(fetchState, 1500);
    // Inicia detector de queda de internet e reconexão automática
    initializeOfflineDetection();
    // Attach CSRF token for axios (if present)
    try {
        const meta = document.querySelector('meta[name="csrf-token"]');
        if (meta) axios.defaults.headers.common['X-CSRFToken'] = meta.getAttribute('content');
    } catch (e) { /* ignore */ }
    
    // Initialize Socket.IO for real-time selection events
    initializeSocketIO();
});

// --- OFFLINE DETECTION & AUTO-RECONNECT ---
let offlineRetryCount = 0;
const MAX_OFFLINE_RETRIES = 3;
let lastConnectedStatus = null;

function initializeOfflineDetection() {
    // Detecta mudanças de status online/offline do navegador
    window.addEventListener('online', () => {
        console.log('[Offline Detection] Internet restaurada');
        offlineRetryCount = 0;
        // Tenta reconectar imediatamente
        attemptOfflineReconnect();
    });
    
    window.addEventListener('offline', () => {
        console.log('[Offline Detection] Internet perdida');
        offlineRetryCount = 0;
    });
}

async function attemptOfflineReconnect() {
    if (offlineRetryCount >= MAX_OFFLINE_RETRIES) {
        console.log('[Offline Reconnect] Tentativas exauridas');
        return;
    }
    
    try {
        console.log('[Offline Reconnect] Tentativa ' + (offlineRetryCount + 1));
        const res = await axios.post('/reconnect_offline');
        if (res.data.status === 'ok') {
            console.log('[Offline Reconnect] Reconectado com sucesso');
            console.log('[Offline Reconnect] 2FA cache usado:', res.data.used_2fa_cache);
            offlineRetryCount = 0;
        }
    } catch (e) {
        offlineRetryCount++;
        console.log('[Offline Reconnect] Falha - Tentativa ' + offlineRetryCount + '/' + MAX_OFFLINE_RETRIES);
        if (offlineRetryCount < MAX_OFFLINE_RETRIES) {
            // Tenta novamente após 3 segundos
            setTimeout(attemptOfflineReconnect, 3000);
        }
    }
}


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
            document.getElementById('email')?.focus();
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

    // UX: atalhos de teclado (não alteram a lógica de rede)
    const linkBox = document.getElementById('link-box');
    if (linkBox) {
        linkBox.addEventListener('keydown', (ev) => {
            if (ev.key === 'Enter') { ev.preventDefault(); analyzeLink(); }
        });
    }

    const twofaInput = document.getElementById('twofa-code');
    if (twofaInput) {
        twofaInput.addEventListener('input', () => {
            twofaInput.value = twofaInput.value.replace(/\D/g, '').slice(0, 6);
        });
        twofaInput.addEventListener('keydown', (ev) => {
            if (ev.key === 'Enter') { ev.preventDefault(); submit2FA(); }
        });
    }

    const passwordInput = document.getElementById('password');
    if (passwordInput) {
        passwordInput.addEventListener('keydown', (ev) => {
            if (ev.key === 'Enter') { ev.preventDefault(); submitLogin(); }
        });
    }

    const searchBox = document.getElementById('selection-search');
    if (searchBox) {
        searchBox.addEventListener('keydown', (ev) => {
            if (ev.key === 'Enter') { ev.preventDefault(); submitSelection(); }
        });
    }
}

// --- FEEDBACK VISUAL (toasts) ---
function showToast(message, type = 'info', timeout = 4000) {
    const stack = document.getElementById('toast-stack');
    if (!stack) { console.log('[toast]', type, message); return; }

    const icons = {
        success: 'fa-circle-check',
        error: 'fa-circle-exclamation',
        info: 'fa-circle-info',
        warning: 'fa-triangle-exclamation'
    };

    const el = document.createElement('div');
    el.className = `app-toast app-toast-${type}`;
    el.setAttribute('role', type === 'error' ? 'alert' : 'status');
    el.innerHTML = `
        <i class="fas ${icons[type] || icons.info}" aria-hidden="true"></i>
        <span class="app-toast-msg"></span>
        <button type="button" class="app-toast-close" aria-label="Fechar aviso">&times;</button>
    `;
    el.querySelector('.app-toast-msg').textContent = message;

    const dismiss = () => {
        el.classList.add('is-leaving');
        setTimeout(() => el.remove(), 220);
    };
    el.querySelector('.app-toast-close').addEventListener('click', dismiss);

    stack.appendChild(el);
    requestAnimationFrame(() => el.classList.add('is-visible'));
    setTimeout(dismiss, timeout);
}

// --- CORE LOGIC ---

async function fetchState() {
    try {
        const res = await axios.get('/api/state');
        const { wrapper, downloader, queue, wrapper_installed, downloader_installed } = res.data;

        // Reset offline retry count on successful connection
        offlineRetryCount = 0;
        
        // Detecta se wrapper caiu e tenta reconectar
        if (!wrapper.running && lastConnectedStatus && lastConnectedStatus.running) {
            console.log('[Offline Detection] Wrapper desconectou - tentando reconectar offline');
            setTimeout(() => attemptOfflineReconnect(), 1000);
        }
        
        lastConnectedStatus = wrapper;

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
        // Detecta erros de conexão (network error, timeout, etc)
        if (e.code === 'ECONNABORTED' || e.code === 'ENOTFOUND' || e.message.includes('Network') || e.message.includes('timeout')) {
            console.log('[Offline Detection] Erro de conexão detectado - tentando reconectar');
            attemptOfflineReconnect();
        }
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

let lastTwofaVisible = false;

function updateWrapperUI(w) {
    // Status Dot + rótulo textual
    const dot = document.getElementById('wrapper-status-dot');
    if (dot) {
        dot.classList.toggle('is-online', !!w.running);
        dot.classList.toggle('is-offline', !w.running);
    }
    const chip = document.getElementById('wrapper-status-chip');
    if (chip) {
        chip.classList.toggle('is-online', !!w.running);
        chip.classList.toggle('is-offline', !w.running);
        chip.title = w.running ? 'Wrapper conectado' : 'Wrapper desconectado';
    }
    const statusText = document.getElementById('wrapper-status-text');
    if (statusText) statusText.textContent = w.running ? 'Conectado' : 'Desconectado';

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

    // Foco automático no campo 2FA quando o modal abre
    if (w.needs_2fa && !lastTwofaVisible) {
        setTimeout(() => document.getElementById('twofa-code')?.focus(), 120);
    }
    lastTwofaVisible = !!w.needs_2fa;
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
        pBtn.innerHTML = q.paused
            ? '<i class="fas fa-play me-1"></i> Retomar'
            : '<i class="fas fa-pause me-1"></i> Pausar';
        pBtn.className = q.paused ? 'btn btn-success btn-sm rounded-pill px-3' : 'btn btn-outline-warning btn-sm rounded-pill px-3';
        pBtn.title = q.paused ? 'Retomar a fila de downloads' : 'Pausar a fila de downloads';
    }
    document.body.classList.toggle('queue-paused', !!q.paused);

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

function queueEmptyState(isActiveTab) {
    return isActiveTab
        ? `<tr><td colspan="6" class="p-0">
             <div class="empty-state">
               <i class="fas fa-compact-disc" aria-hidden="true"></i>
               <p class="fw-semibold mb-1">Nenhum download ativo</p>
               <p class="text-muted small mb-0">Cole um link do Apple Music acima para começar.</p>
             </div>
           </td></tr>`
        : `<tr><td colspan="6" class="p-0">
             <div class="empty-state">
               <i class="fas fa-clock-rotate-left" aria-hidden="true"></i>
               <p class="fw-semibold mb-1">Histórico vazio</p>
               <p class="text-muted small mb-0">Downloads concluídos ou cancelados aparecem aqui.</p>
             </div>
           </td></tr>`;
}

function renderQueueTable(container, items, isActiveTab) {
    if (!items.length) {
        container.innerHTML = queueEmptyState(isActiveTab);
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
            statusBadge = '<span class="badge status-badge bg-warning text-dark"><i class="fas fa-spinner fa-spin"></i> Processando</span>';
            statusClass = "status-processing";
        } else if (item.status === 'completed') { 
            statusBadge = '<span class="badge status-badge bg-success"><i class="fas fa-check"></i> Concluído</span>';
            statusClass = "status-completed";
        } else if (item.status === 'failed') { 
            statusBadge = '<span class="badge status-badge bg-danger"><i class="fas fa-times"></i> Falha</span>';
            statusClass = "status-failed";
        } else if (item.status === 'cancelled') { 
            statusBadge = '<span class="badge status-badge bg-danger"><i class="fas fa-ban"></i> Cancelado</span>';
            statusClass = "status-failed";
        } else if (item.status === 'pending') { 
            statusBadge = '<span class="badge status-badge bg-secondary"><i class="fas fa-clock"></i> Na fila</span>';
            statusClass = "status-pending";
        }

        let title = item.title === "Aguardando metadados..." ? "Carregando..." : item.title;
        const progressDisplay = isValidProgress ? `${progressPercent}%` : "—";
        
        // Action buttons
        let actionHtml = "";
        if (item.status === 'processing') {
            actionHtml = `<button type="button" onclick="stopTask(${item.id})" class="btn btn-sm btn-danger" title="Parar download" aria-label="Parar download ${item.id}"><i class="fas fa-stop-circle"></i></button>`;
        } else if (item.status === 'pending') {
            actionHtml = `
                <div class="btn-group btn-group-sm" role="group" aria-label="Ações do item ${item.id}">
                    <button type="button" onclick="moveTask(${item.id}, 'up')" class="btn btn-outline-secondary" title="Mover para cima" aria-label="Mover item ${item.id} para cima"><i class="fas fa-arrow-up"></i></button>
                    <button type="button" onclick="moveTask(${item.id}, 'down')" class="btn btn-outline-secondary" title="Mover para baixo" aria-label="Mover item ${item.id} para baixo"><i class="fas fa-arrow-down"></i></button>
                    <button type="button" onclick="cancelTask(${item.id}, 'pending')" class="btn btn-outline-danger" title="Cancelar item" aria-label="Cancelar item ${item.id}"><i class="fas fa-ban"></i></button>
                </div>
            `;
        } else {
            actionHtml = `<button type="button" onclick="deleteHistory(${item.id})" class="btn btn-sm btn-outline-secondary" title="Remover do histórico" aria-label="Remover item ${item.id} do histórico"><i class="fas fa-trash"></i></button>`;
        }

        const formatBadge = `<span class="badge badge-soft">${item.format.toUpperCase()}</span>`;
        
        return `
            <tr class="queue-row ${statusClass}">
                <td data-label="ID"><small class="text-muted">#${item.id}</small></td>
                <td data-label="Título">
                    <div class="queue-title" title="${title}"><strong>${title}</strong></div>
                    <small class="text-muted d-block queue-link" title="${item.link}">${item.link}</small>
                    ${item.existing_path ? `<small class="text-success d-block"><i class="fas fa-check-circle"></i> ${truncatePath(item.existing_path, 40)}</small>` : ''}
                </td>
                <td data-label="Status">${statusBadge}</td>
                <td data-label="Progresso">
                    ${item.status === 'processing' 
                        ? `<div class="progress" style="height: 20px;" role="progressbar" aria-valuenow="${progressPercent}" aria-valuemin="0" aria-valuemax="100"><div class="progress-bar" style="width: ${progressPercent}%">${progressDisplay}</div></div>`
                        : `<small>${progressDisplay}</small>`
                    }
                </td>
                <td data-label="Formato">${formatBadge}</td>
                <td data-label="Ações" class="text-lg-end">${actionHtml}</td>
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
        axios.post('/api/cancel_task', {id, status: 'history'})
            .then(() => showToast('Item removido do histórico.', 'success'))
            .catch(() => showToast('Não foi possível remover o item.', 'error'));
    }
}

// --- ACTIONS ---

async function analyzeLink() {
    const link = document.getElementById('link-box').value.trim();
    const box = document.getElementById('link-box');
    if (!link) {
        box?.classList.add('is-invalid-soft');
        setTimeout(() => box?.classList.remove('is-invalid-soft'), 1200);
        showToast('Cole um link do Apple Music para analisar.', 'warning');
        box?.focus();
        return;
    }

    const btn = document.getElementById('analyze-btn');
    const originalHTML = btn.innerHTML;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
    btn.disabled = true;
    btn.setAttribute('aria-busy', 'true');

    const skeleton = document.getElementById('preview-skeleton');
    document.getElementById('preview-area')?.classList.add('d-none');
    skeleton?.classList.remove('d-none');

    try {
        const res = await axios.post('/analyze_link', new URLSearchParams({link}));
        if (res.data.status === 'ok') {
            const m = res.data.metadata;
            const area = document.getElementById('preview-area');
            area.classList.remove('d-none');
            area.classList.add('is-entering');
            setTimeout(() => area.classList.remove('is-entering'), 400);
            document.getElementById('preview-title').innerText = m.title;
            document.getElementById('preview-type').innerText = m.type;
            const img = document.getElementById('preview-img');
            if (m.image) { img.src = m.image; img.alt = `Capa de ${m.title}`; img.classList.remove('d-none'); }
            else { img.classList.add('d-none'); }
            document.getElementById('download-btn')?.focus();
        } else {
            showToast('Link inválido. Verifique a URL do Apple Music.', 'error');
        }
    } catch { showToast('Erro ao analisar o link. Tente novamente.', 'error'); }
    finally {
        skeleton?.classList.add('d-none');
        btn.innerHTML = originalHTML;
        btn.disabled = false;
        btn.removeAttribute('aria-busy');
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
    const originalHTML = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> <span>Adicionando…</span>';
    
    try {
        await axios.post('/download', new URLSearchParams({
            link, title, format: fmt, special_audio: special
        }));
        btn.innerHTML = '<i class="fas fa-check"></i> <span>Adicionado!</span>';
        btn.classList.add('btn-success');
        document.getElementById('preview-area').classList.add('d-none');
        document.getElementById('link-box').value = '';
        showToast(`"${title}" adicionado à fila em ${fmt.toUpperCase()}.`, 'success');
        setTimeout(() => {
            btn.innerHTML = originalHTML;
            btn.classList.remove('btn-success');
            btn.disabled = false;
        }, 1500);
    } catch {
        showToast('Erro ao adicionar o item à fila.', 'error');
        btn.innerHTML = originalHTML;
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
    if(confirm("Parar download?")) {
        axios.post('/api/cancel_task', {id, status: 'processing'})
            .then(() => showToast('Download interrompido.', 'info'))
            .catch(() => showToast('Não foi possível parar o download.', 'error'));
    }
}

function cancelTask(id, status) {
    if(confirm("Cancelar item da fila?")) {
        axios.post('/api/cancel_task', {id, status})
            .then(() => showToast('Item cancelado.', 'info'))
            .catch(() => showToast('Não foi possível cancelar o item.', 'error'));
    }
}

function moveTask(id, direction) {
    axios.post('/api/move_queue', {id, direction});
}

function stopWrapper() { axios.post('/stop_wrapper'); }
function submitLogin() {
    const e = document.getElementById('email').value;
    const p = document.getElementById('password').value;
    if (!e || !p) { showToast('Informe email e senha para conectar.', 'warning'); return; }
    axios.post('/login_wrapper', new URLSearchParams({email:e, password:p}));
    document.getElementById('login-form').classList.add('d-none');
    showToast('Conectando ao wrapper…', 'info');
}
function submit2FA() {
    const input = document.getElementById('twofa-code');
    const code = input.value.trim();
    if (code.length < 6) {
        input.classList.add('is-invalid-soft');
        setTimeout(() => input.classList.remove('is-invalid-soft'), 1200);
        showToast('Digite os 6 dígitos do código.', 'warning');
        return;
    }
    axios.post('/submit_2fa', new URLSearchParams({twofa_code: code}));
    document.getElementById('twofa-modal').classList.add('d-none');
    input.value = '';
    showToast('Código enviado.', 'success');
}

// Marca/desmarca todos os itens visíveis do modal de seleção (apenas UI)
function toggleAllSelection() {
    const boxes = Array.from(document.querySelectorAll('#selection-list input[type="checkbox"]'));
    if (!boxes.length) return;
    const shouldCheck = boxes.some(b => !b.checked);
    boxes.forEach(b => { b.checked = shouldCheck; });
    updateSelectionCount();
    const btn = document.getElementById('selection-toggle-all');
    if (btn) {
        btn.innerHTML = shouldCheck
            ? '<i class="fas fa-xmark me-1"></i>Limpar seleção'
            : '<i class="fas fa-check-double me-1"></i>Marcar todos';
    }
}

function updateSelectionCount() {
    const checked = document.querySelectorAll('#selection-list input[type="checkbox"]:checked').length;
    const btn = document.getElementById('submit-selection');
    if (!btn) return;
    btn.disabled = checked === 0;
    btn.innerHTML = checked
        ? `<i class="fas fa-check me-2"></i>Confirmar seleção (${checked})`
        : '<i class="fas fa-check me-2"></i>Selecione ao menos um item';
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
    const typeFilter = document.getElementById('selection-type-filter');
    if (!tagFilter || !yearFilter) return;

    const tags = new Set();
    const years = new Set();
    const types = new Set();
    
    opts.forEach((opt) => {
        // Extrair tags
        (opt.tags || []).forEach((tag) => tags.add(tag));
        
        // Extrair anos
        if (opt.date) {
            const yearMatch = opt.date.match(/\b(\d{4})\b/);
            if (yearMatch) years.add(yearMatch[1]);
        }
        
        // Extrair tipos
        if (opt.type) {
            types.add(opt.type);
        }
    });

    const currentTag = tagFilter.value;
    const currentYear = yearFilter.value;
    const currentType = typeFilter?.value;

    // Atualizar filtro de tags
    tagFilter.innerHTML = '<option value="">Todas as edições</option>' +
        Array.from(tags).sort().map(tag => `<option value="${tag}">${tag}</option>`).join('');
    
    // Atualizar filtro de datas
    yearFilter.innerHTML = '<option value="">Todas as datas</option>' +
        Array.from(years).sort().reverse().map(year => `<option value="${year}">${year}</option>`).join('');
    
    // Atualizar filtro de tipos (se existir o elemento)
    if (typeFilter) {
        typeFilter.innerHTML = '<option value="">Todos os tipos</option>' +
            Array.from(types).sort().map(type => `<option value="${type}">${type}</option>`).join('');
        if (currentType) typeFilter.value = currentType;
    }

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
    if (summary) {
        summary.textContent = filtered.length === selectionOptions.length
            ? `${filtered.length} itens`
            : `${filtered.length} de ${selectionOptions.length} itens`;
    }

    if (!filtered.length) {
        list.innerHTML = `
            <tr>
                <td colspan="6" class="p-0">
                    <div class="empty-state empty-state-sm">
                        <i class="fas fa-magnifying-glass" aria-hidden="true"></i>
                        <p class="fw-semibold mb-1">Nenhum item encontrado</p>
                        <p class="text-muted small mb-0">Ajuste a busca ou limpe os filtros.</p>
                    </div>
                </td>
            </tr>`;
        updateSelectionCount();
        return;
    }

    list.innerHTML = filtered.map(o => {
        let badgeColor = 'bg-secondary';
        if (o.type === 'Album') badgeColor = 'bg-primary';
        if (o.type === 'Single') badgeColor = 'bg-info text-dark';
        if (o.type === 'EP') badgeColor = 'bg-success';
        if (o.type === 'MusicVideo' || o.type === 'Video' || o.type === 'MUSIC_VIDEO') badgeColor = 'bg-warning text-dark';
        
        return `
        <tr class="selection-row">
            <td data-label="">
                <input class="form-check-input" type="checkbox" value="${o.id}" id="chk-${o.id}" aria-label="Selecionar ${o.label}">
            </td>
            <td data-label="Título">
                <label class="form-check-label selection-label" for="chk-${o.id}">
                    <div class="fw-bold">${o.label}</div>
                    <div class="text-muted small">${o.extra || '—'}</div>
                </label>
            </td>
            <td data-label="Tipo"><span class="badge ${badgeColor}">${o.type}</span></td>
            <td data-label="Edição">
                ${(o.tags||[]).map(t=>`<span class="badge tag-pill me-1">${t}</span>`).join('') || '<span class="text-muted small">—</span>'}
            </td>
            <td data-label="Data" class="text-muted small">${o.date || '—'}</td>
            <td data-label="Tempo" class="text-muted small">${o.duration || '—'}</td>
        </tr>`;
    }).join('');

    list.querySelectorAll('input[type="checkbox"]').forEach((cb) => {
        cb.addEventListener('change', updateSelectionCount);
    });
    updateSelectionCount();
}

function submitSelection() {
    const checked = Array.from(document.querySelectorAll('#selection-list input:checked')).map(c=>c.value);
    if(checked.length) {
        // Desabilitar botão e esconder modal para evitar múltiplos cliques/reenviios
        const btn = document.getElementById('submit-selection');
        const selArea = document.getElementById('selection-area');
        if(btn) btn.disabled = true;
        if(selArea) selArea.classList.add('d-none');
        
        // Enviar TODAS as seleções de uma vez, separadas por VÍRGULA
        // Formato esperado pelo CLI: "1,2,3,4" ou "1,3,5" para múltiplas seleções
        const selectionString = checked.join(',');
        
        showToast(`${checked.length} item(ns) enviados para download.`, 'success');

        axios.post('/submit_selection', new URLSearchParams({selection: selectionString}))
            .catch(err => {
                console.error('Selection error:', err);
                showToast('Erro ao enviar a seleção.', 'error');
            })
            .finally(() => {
                if(btn) btn.disabled = false;
            });
    } else {
        showToast('Selecione ao menos um item para continuar.', 'warning');
    }
}

function skipSelection() {
    const btn = document.getElementById('skip-selection');
    if(btn) btn.disabled = true;
    
    axios.post('/skip_selection')
        .catch(err => {
            console.error('Skip error:', err);
            showToast('Erro ao pular a seleção.', 'error');
        })
        .finally(() => {
            if(btn) btn.disabled = false;
        });
}
