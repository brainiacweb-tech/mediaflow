// State
let currentTab = 'youtube';
let ws = null;
let darkMode = true;

// Tab switching
function switchTab(tab) {
    currentTab = tab;
    document.querySelectorAll('.tab-content').forEach(el => el.classList.add('hidden'));
    document.getElementById(`tab-${tab}`).classList.remove('hidden');

    document.querySelectorAll('.nav-item, .mobile-nav-item').forEach(el => {
        el.classList.toggle('active', el.dataset.tab === tab);
    });

    if (tab === 'queue') loadQueue();
    if (tab === 'history') loadHistory();
}

// Theme toggle
function toggleTheme() {
    darkMode = !darkMode;
    document.documentElement.classList.toggle('dark', darkMode);
    const icon = darkMode ? 'fa-moon' : 'fa-sun';
    const label = darkMode ? 'Dark Mode' : 'Light Mode';
    document.querySelectorAll('#theme-icon-mobile, #theme-icon-desktop').forEach(el => {
        el.className = `fas ${icon}`;
    });
    const labelEl = document.getElementById('theme-label');
    if (labelEl) labelEl.textContent = label;
    localStorage.setItem('theme', darkMode ? 'dark' : 'light');
}

// Toast notifications
function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const colors = {
        success: 'bg-emerald-500/90 border-emerald-400/50',
        error: 'bg-red-500/90 border-red-400/50',
        info: 'bg-primary-500/90 border-primary-400/50',
        warning: 'bg-amber-500/90 border-amber-400/50',
    };
    const icons = { success: 'fa-check-circle', error: 'fa-exclamation-circle', info: 'fa-info-circle', warning: 'fa-triangle-exclamation' };

    const toast = document.createElement('div');
    toast.className = `toast flex items-center gap-3 px-4 py-3 rounded-xl border ${colors[type]} text-white text-sm font-medium shadow-2xl`;
    toast.innerHTML = `<i class="fas ${icons[type]}"></i><span>${message}</span>`;
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 4000);
}

// WebSocket connection
function connectWebSocket() {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    ws = new WebSocket(`${proto}://${location.host}/ws/progress`);

    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        updateTaskProgress(data);
    };

    ws.onclose = () => {
        setTimeout(connectWebSocket, 3000);
    };

    ws.onerror = () => ws.close();
}

// Update task progress in UI
function updateTaskProgress(data) {
    const el = document.getElementById(`task-${data.task_id}`);
    if (!el) return;

    const bar = el.querySelector('.progress-bar-fill');
    const pctText = el.querySelector('.progress-text');
    const statusEl = el.querySelector('.status-badge');
    const speedEl = el.querySelector('.speed-text');

    if (bar) {
        bar.style.width = `${data.progress}%`;
        bar.classList.toggle('completed', data.status === 'completed');
        bar.classList.toggle('failed', data.status === 'failed');
    }
    if (pctText) pctText.textContent = `${Math.round(data.progress)}%`;

    if (statusEl) {
        const statusConfig = {
            pending: { text: 'Pending', class: 'bg-gray-500/20 text-gray-400' },
            downloading: { text: 'Downloading', class: 'bg-blue-500/20 text-blue-400' },
            completed: { text: 'Completed', class: 'bg-emerald-500/20 text-emerald-400' },
            failed: { text: 'Failed', class: 'bg-red-500/20 text-red-400' },
            cancelled: { text: 'Cancelled', class: 'bg-gray-500/20 text-gray-400' },
        };
        const cfg = statusConfig[data.status] || statusConfig.pending;
        statusEl.className = `status-badge px-2 py-0.5 rounded-md text-xs font-medium ${cfg.class}`;
        statusEl.textContent = cfg.text;
    }

    if (speedEl && data.speed) speedEl.textContent = data.speed;

    if (data.status === 'completed') {
        showToast('Download completed!', 'success');
        const dlBtn = el.querySelector('.download-btn');
        if (dlBtn) dlBtn.classList.remove('hidden');
        el.classList.remove('downloading-pulse');
    }
    if (data.status === 'failed') {
        showToast('Download failed', 'error');
        el.classList.remove('downloading-pulse');
    }

    updateQueueBadge();
}

// Queue badge
function updateQueueBadge() {
    const items = document.querySelectorAll('.queue-item[data-status="downloading"], .queue-item[data-status="pending"]');
    const count = items.length;
    document.querySelectorAll('#queue-badge, #queue-badge-mobile').forEach(el => {
        el.textContent = count;
        el.classList.toggle('hidden', count === 0);
    });
}

// Format file size
function formatSize(bytes) {
    if (!bytes) return '';
    if (bytes > 1073741824) return `${(bytes / 1073741824).toFixed(1)} GB`;
    if (bytes > 1048576) return `${(bytes / 1048576).toFixed(1)} MB`;
    return `${(bytes / 1024).toFixed(0)} KB`;
}

// Format date
function formatDate(dateStr) {
    if (!dateStr) return '';
    const d = new Date(dateStr);
    return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

// API helper
async function api(path, options = {}) {
    const resp = await fetch(path, {
        headers: { 'Content-Type': 'application/json', ...options.headers },
        ...options,
    });
    if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: 'Request failed' }));
        throw new Error(err.detail || 'Request failed');
    }
    return resp.json();
}

// Drag & drop for URL
function setupDragDrop() {
    const zone = document.getElementById('yt-drop-zone');
    if (!zone) return;
    ['dragenter', 'dragover'].forEach(e => {
        zone.addEventListener(e, (ev) => { ev.preventDefault(); zone.classList.add('drop-active'); });
    });
    ['dragleave', 'drop'].forEach(e => {
        zone.addEventListener(e, (ev) => { ev.preventDefault(); zone.classList.remove('drop-active'); });
    });
    zone.addEventListener('drop', (ev) => {
        const text = ev.dataTransfer.getData('text/plain');
        if (text) {
            document.getElementById('yt-url').value = text;
            fetchYouTubeInfo();
        }
    });
}

// Init
document.addEventListener('DOMContentLoaded', () => {
    const saved = localStorage.getItem('theme');
    if (saved === 'light') { darkMode = false; document.documentElement.classList.remove('dark'); }
    connectWebSocket();
    setupDragDrop();
    loadQueue();
});
