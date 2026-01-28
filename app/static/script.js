document.addEventListener("DOMContentLoaded", () => {
    // Inicializa controles
    setupEventListeners();
    // Inicia Loop de Estado
    setInterval(fetchState, 1500);
});

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
}

// --- CORE LOGIC ---

async function fetchState() {
    try {
        const res = await axios.get('/api/state');
        const { wrapper, downloader, queue } = res.data;

        updateWrapperUI(wrapper);
        updateDownloaderUI(downloader);
        updateQueueUI(queue);

    } catch (e) {
        console.error("Sync Error:", e);
    }
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
        renderSelectionList(d.options);
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
    renderGrid(gridActive, activeItems, true);
    renderGrid(gridHistory, historyItems, false);
}

function renderGrid(container, items, isActiveTab) {
    if (!items.length) {
        container.innerHTML = `<div class="text-center text-secondary py-5 w-100">Nada aqui.</div>`;
        return;
    }

    const html = items.map(item => {
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
            statusMsg = `<small class="text-warning fw-bold">${progress}%</small>`;
        } else if (item.status === 'failed' || item.status === 'cancelled') {
            // Mostra o erro em vermelho
            statusMsg = `<small class="text-danger fw-bold" style="font-size:0.75em;" title="${progress}">${progress}</small>`;
        } else if (item.status === 'completed') {
            statusMsg = `<small class="text-success fw-bold">Concluído</small>`;
        }

        return `
        <div class="col-md-6 col-lg-4">
            <div class="queue-card p-3 d-flex align-items-center gap-3 position-relative overflow-hidden">
                <div class="d-flex align-items-center justify-content-center bg-dark text-secondary rounded" style="width:50px; height:50px; flex-shrink:0;">
                    <i class="fas fa-music fa-lg"></i>
                </div>
                <div class="flex-grow-1 overflow-hidden" style="min-width:0;">
                    <div class="d-flex justify-content-between">
                        <div class="track-title text-white text-truncate" title="${title}">${title}</div>
                    </div>
                    <div class="text-truncate text-secondary small">${item.link}</div>
                    <div class="d-flex justify-content-between align-items-center mt-1">
                        <div>
                            <span class="badge bg-dark border border-secondary" style="font-size:0.7em">${item.format.toUpperCase()}</span>
                            <span class="badge bg-${statusColor}" style="font-size:0.7em"><i class="fas fa-${icon}"></i> ${item.status}</span>
                        </div>
                        ${statusMsg}
                    </div>
                </div>
                ${item.status === 'processing' ? `<div class="card-progress-bg" style="width:${progress}%"></div>` : ''}
                ${item.status === 'processing' ? `<button onclick="stopTask(${item.id})" class="btn btn-link text-danger position-absolute top-0 end-0 p-2"><i class="fas fa-stop-circle"></i></button>` : ''}
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
    if(confirm("Parar download?")) axios.post('/api/cancel_task', {id});
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

// Render Selection List (Bootstrap styled)
function renderSelectionList(opts) {
    const list = document.getElementById('selection-list');
    // Verifica se a lista mudou pelo tamanho, para evitar repintar
    if(list.childElementCount === opts.length) return;

    list.innerHTML = opts.map(o => {
        let badgeColor = 'bg-secondary';
        if (o.type === 'Album') badgeColor = 'bg-primary';
        if (o.type === 'Single') badgeColor = 'bg-info text-dark';
        if (o.type === 'EP') badgeColor = 'bg-success';
        
        return `
        <div class="form-check border-bottom border-secondary py-2">
            <input class="form-check-input mt-2" type="checkbox" value="${o.id}" id="chk-${o.id}">
            <label class="form-check-label w-100 ps-2" for="chk-${o.id}" style="cursor:pointer">
                <div class="d-flex justify-content-between">
                    <div>
                        <div class="fw-bold text-white">${o.label}</div>
                        <span class="badge ${badgeColor}">${o.type}</span>
                        ${(o.tags||[]).map(t=>`<span class="badge bg-dark border border-secondary ms-1">${t}</span>`).join('')}
                    </div>
                    <small class="text-muted">${o.date || ''}</small>
                </div>
            </label>
        </div>`;
    }).join('');
}

function submitSelection() {
    const checked = Array.from(document.querySelectorAll('#selection-list input:checked')).map(c=>c.value);
    if(checked.length) axios.post('/submit_selection', new URLSearchParams({selection: checked.join(',')}));
}
function skipSelection() {
    axios.post('/skip_selection');
}