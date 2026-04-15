document.addEventListener("DOMContentLoaded", () => { // Inicializa controles
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