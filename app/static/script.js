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