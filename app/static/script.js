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
    // API key removed; no client-side header to attach.
});

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
    const gridActive = document.getElementById('queue-grid-active');
    const gridHistory = document.getElementById('queue-grid-history');
    
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

    // Render Cards
    activeItems = activeItems.sort((a, b) => (a.position ?? 0) - (b.position ?? 0));
    renderGrid(gridActive, activeItems, true);
    renderGrid(gridHistory, historyItems, false);
}

function renderGrid(container, items, isActiveTab) {
    if (!items.length) {
        container.innerHTML = `<div class="text-center text-secondary py-5 w-100">Nada aqui.</div>`;
        return;
    }

    const html = items.map((item, index) => {
        const progress = item.progress || "0";
        let statusColor = "secondary";
        let icon = "clock";
        
        if (item.status === 'processing') { statusColor = "warning text-dark"; icon = "spinner fa-spin"; }
        if (item.status === 'completed') { statusColor = "success"; icon = "check"; }
        if (item.status === 'failed') { statusColor = "danger"; icon = "triangle-exclamation"; }
        if (item.status === 'cancelled') { statusColor = "danger"; icon = "ban"; }

        let title = item.title === "Aguardando metadados..." ? "Carregando..." : item.title;

        // Lógica de Mensagem
        let statusMsg = "";
        if (item.status === 'processing') {
            statusMsg = Number.isFinite(Number(progress))
                ? `<small class="text-warning fw-bold">${progress}%</small>`
                : `<small class="text-warning fw-bold">Processando</small>`;
        } else if (item.status === 'pending') {
            statusMsg = `<small class="text-muted fw-bold">Na fila</small>`;
        } else if (item.status === 'failed' || item.status === 'cancelled') {
            // Mostra o erro em vermelho
            statusMsg = `<small class="text-danger fw-bold" style="font-size:0.75em;" title="${progress}">${progress}</small>`;
        } else if (item.status === 'completed') {
            statusMsg = `<small class="text-success fw-bold">Concluído</small>`;
        }

        const orderLabel = isActiveTab ? `<span class="queue-order">#${index + 1}</span>` : '';
        const progressValue = Number(progress);
        const progressPercent = Number.isFinite(progressValue) ? Math.min(Math.max(progressValue, 0), 100) : 0;
        const progressBar = item.status === 'processing'
            ? `<div class="card-progress-bg" style="width:${progressPercent}%"></div>`
            : '';
        const actionButtons = item.status === 'processing'
            ? `<button onclick="stopTask(${item.id})" class="btn btn-link text-danger position-absolute top-0 end-0 p-2"><i class="fas fa-stop-circle"></i></button>`
            : item.status === 'pending'
                ? `<div class="queue-actions position-absolute top-0 end-0 p-2">
                        <button onclick="moveTask(${item.id}, 'up')" class="btn btn-sm btn-dark"><i class="fas fa-arrow-up"></i></button>
                        <button onclick="moveTask(${item.id}, 'down')" class="btn btn-sm btn-dark"><i class="fas fa-arrow-down"></i></button>
                        <button onclick="cancelTask(${item.id}, 'pending')" class="btn btn-sm btn-outline-danger"><i class="fas fa-ban"></i></button>
                   </div>`
                : '';

        const existingHtml = item.existing_path ? `<div class="text-truncate text-muted small" title="${item.existing_path}">Existe em: ${truncatePath(item.existing_path, 60)}</div>` : '';

        return `
        <div class="col-md-6 col-lg-4">
            <div class="queue-card p-3 d-flex align-items-center gap-3 position-relative overflow-hidden">
                <div class="d-flex align-items-center justify-content-center queue-icon" style="width:50px; height:50px; flex-shrink:0;">
                    <i class="fas fa-music fa-lg"></i>
                </div>
                <div class="flex-grow-1 overflow-hidden" style="min-width:0;">
                    <div class="d-flex justify-content-between">
                        <div class="track-title text-truncate fw-semibold" title="${title}">${title}</div>
                        ${orderLabel}
                    </div>
                    <div class="text-truncate text-secondary small">${item.link}</div>
                    ${existingHtml}
                    <div class="d-flex justify-content-between align-items-center mt-1">
                        <div>
                            <span class="badge badge-soft" style="font-size:0.7em">${item.format.toUpperCase()}</span>
                            <span class="badge bg-${statusColor}" style="font-size:0.7em"><i class="fas fa-${icon}"></i> ${item.status}</span>
                        </div>
                        ${statusMsg}
                    </div>
                </div>
                ${progressBar}
                ${actionButtons}
            </div>
        </div>`;
    }).join('');

    if (container.innerHTML !== html) container.innerHTML = html;
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
