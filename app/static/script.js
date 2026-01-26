setInterval(updateLogs, 1000);

function updateLogs() {
    axios.get("/get_logs").then(res => {
        const dBox = document.getElementById("downloader-logs");
        const wBox = document.getElementById("wrapper-logs");
        
        if (res.data.downloader.length) dBox.innerHTML = res.data.downloader.map(fmt).join("");
        if (res.data.wrapper.length) wBox.innerHTML = res.data.wrapper.map(fmt).join("");
        dBox.scrollTop = dBox.scrollHeight; wBox.scrollTop = wBox.scrollHeight;
        
        updateWrapperStatus(res.data.wrapper_running);
        
        const dlBtn = document.getElementById("download-btn");
        const cancelBtn = document.getElementById("cancel-dl-btn");
        
        if (res.data.download_running) {
            dlBtn.disabled = true; dlBtn.textContent = "Downloading...";
            cancelBtn.classList.remove('d-none');
            document.getElementById("analyze-btn").disabled = true;
        } else if (res.data.wrapper_running) {
            dlBtn.disabled = false; dlBtn.textContent = "Download";
            cancelBtn.classList.add('d-none');
            document.getElementById("analyze-btn").disabled = false;
        }

        if (res.data.wrapper_needs_2fa) document.getElementById('twofa-modal').classList.remove('d-none');
        else document.getElementById('twofa-modal').classList.add('d-none');

        const area = document.getElementById('selection-area');
        if (res.data.download_needs_selection) {
            if (area.classList.contains('d-none')) {
                renderSelection(res.data.selection_options);
                area.classList.remove('d-none');
                area.scrollIntoView({behavior:'smooth', block:'center'});
            }
        } else area.classList.add('d-none');
    });
}

function fmt(l) {
    if (l.includes("✅") || l.includes("completed") || l.includes("success")) return `<div class="text-success border-start border-success ps-2">> ${l}</div>`;
    if (l.includes("❌") || l.includes("Error") || l.includes("failed")) return `<div class="text-danger border-start border-danger ps-2">> ${l}</div>`;
    if (l.includes("AGUARDANDO")) return `<div class="text-warning bg-dark fw-bold ps-2">> ${l}</div>`;
    return `<div>> ${l}</div>`;
}

// Preview
document.getElementById('analyze-btn').onclick = () => {
    const link = document.getElementById('link-box').value;
    if(!link) return;
    const btn = document.getElementById('analyze-btn');
    btn.disabled = true; btn.textContent = "...";
    
    axios.post('/analyze_link', new URLSearchParams({link})).then(r => {
        btn.disabled = false; btn.textContent = "🔍 Analyze";
        if(r.data.status === 'ok') {
            const m = r.data.metadata;
            document.getElementById('preview-title').textContent = m.title;
            document.getElementById('preview-type').textContent = m.type;
            const img = document.getElementById('preview-img');
            if(m.image) { img.src = m.image; img.classList.remove('d-none'); }
            document.getElementById('preview-area').classList.remove('d-none');
        }
    });
};

// Selection Render (COM DATA)
function renderSelection(opts) {
    const list = document.getElementById('selection-list');
    list.innerHTML = '';
    if (opts && opts.length) {
        document.getElementById('manual-input-container').classList.add('d-none');
        document.getElementById('selection-container').classList.remove('d-none');
        opts.forEach(o => {
            let badgeClass = "badge-album";
            if (o.type === "Single") badgeClass = "badge-single";
            if (o.type === "EP") badgeClass = "badge-ep";
            
            let tagsHtml = "";
            if (o.tags && o.tags.length) {
                tagsHtml = o.tags.map(t => `<span class="badge badge-tag">${t}</span>`).join("");
            }
            
            // Tratamento da Data
            let dateHtml = "";
            if (o.date) {
                // Tenta extrair apenas o ano se for uma data completa
                const year = o.date.split('-')[0]; 
                dateHtml = `<span class="list-date">${year}</span>`;
            }

            list.innerHTML += `
            <div class="form-check border-bottom border-secondary py-1" style="border-color:#333!important">
                <input class="form-check-input i-chk fs-5" type="checkbox" value="${o.id}" id="c-${o.id}">
                <label class="form-check-label text-light" for="c-${o.id}">
                    <div class="list-row">
                        <span class="badge bg-secondary me-2">${o.id}</span>
                        <span class="badge ${badgeClass} me-2">${o.type}</span>
                        <div class="list-info">
                            ${o.label} ${tagsHtml}
                        </div>
                        ${dateHtml}
                    </div>
                </label>
            </div>`;
        });
    } else {
        document.getElementById('selection-container').classList.add('d-none');
        document.getElementById('manual-input-container').classList.remove('d-none');
    }
}
function toggleSelectAll() {
    const chks = document.querySelectorAll('.i-chk');
    const all = Array.from(chks).every(c => c.checked);
    chks.forEach(c => c.checked = !all);
}
function skipSelection() {
    if(confirm("Skip this step?")) {
        axios.post("/skip_selection").then(() => document.getElementById('selection-area').classList.add('d-none'));
    }
}
document.getElementById('submit-selection').onclick = () => {
    let val = "";
    if (document.getElementById('selection-container').classList.contains('d-none')) {
        val = document.getElementById('selection-input').value;
    } else {
        const chked = document.querySelectorAll('.i-chk:checked');
        const total = document.querySelectorAll('.i-chk').length;
        if (!chked.length) return alert("Select one.");
        val = (chked.length === total) ? "all" : Array.from(chked).map(c => c.value).join(",");
    }
    if (val) axios.post('/submit_selection', new URLSearchParams({selection: val}));
};

// Global Cancel
document.getElementById('cancel-dl-btn').onclick = () => {
    if(confirm("Abort download completely?")) axios.post("/cancel_download");
};

// Auth
document.getElementById('submit-2fa').onclick = () => axios.post('/submit_2fa', new URLSearchParams({twofa_code:document.getElementById('twofa-code').value}));
document.getElementById("login-btn").onclick = () => document.getElementById("login-form").classList.toggle("d-none");
document.getElementById("submit-login").onclick = () => axios.post("/login_wrapper", new URLSearchParams({email:document.getElementById("email").value, password:document.getElementById("password").value}));
document.getElementById("stop-wrapper-btn").onclick = () => axios.post("/stop_wrapper");
document.getElementById("download-btn").onclick = () => {
    const link = document.getElementById("link-box").value;
    const fmt = document.querySelector("input[name='format']:checked").value;
    const sp = document.getElementById("special-audio").checked;
    if(link) axios.post("/download", new URLSearchParams({link, format:fmt, special_audio:sp}));
};
function updateWrapperStatus(run) {
    const ind = document.getElementById("wrapper-indicator");
    ind.className = run ? "badge bg-success" : "badge bg-danger";
    ind.innerText = run ? "Running" : "Stopped";
    document.getElementById("stop-wrapper-btn").classList.toggle('d-none', !run);
}
axios.get('/check_saved_credentials').then(r => {
    if(r.data.has_credentials) {
        document.getElementById('saved-credentials-info').classList.remove('d-none');
        document.getElementById('saved-email-display').textContent = r.data.email;
        document.getElementById('auto-login-btn').classList.remove('d-none');
        document.getElementById('forget-credentials-btn').classList.remove('d-none');
    }
});
document.getElementById('special-audio').onchange = function() {
    const ops = document.getElementById('format-options');
    ops.style.opacity = this.checked ? '1' : '0.5';
    ops.querySelectorAll('input').forEach(i => i.disabled = !this.checked);
};