async function loadQueue() {
    try {
        const tasks = await api('/api/downloads/?limit=50');
        const active = tasks.filter(t => t.status === 'pending' || t.status === 'downloading');
        renderQueue(active);
        updateQueueBadge();
    } catch (e) {
        console.error('Failed to load queue:', e);
    }
}

function renderQueue(tasks) {
    const container = document.getElementById('queue-list');
    const zipBtn = document.getElementById('zip-btn');

    if (!tasks.length) {
        container.innerHTML = '<div class="glass-card p-12 text-center text-gray-500"><i class="fas fa-inbox text-4xl mb-3 block"></i><p>No active downloads</p></div>';
        if (zipBtn) zipBtn.classList.add('hidden');
        return;
    }

    container.innerHTML = tasks.map(t => renderTaskItem(t)).join('');
}

function renderTaskItem(t) {
    const isActive = t.status === 'downloading';
    const isComplete = t.status === 'completed';
    const isFailed = t.status === 'failed';

    const typeIcon = t.task_type.includes('youtube') ? 'fab fa-youtube text-red-400' :
                     t.task_type === 'book' ? 'fas fa-book text-emerald-400' : 'fas fa-file text-gray-400';

    const formatBadge = t.format ? `<span class="px-1.5 py-0.5 bg-white/10 rounded text-[10px] uppercase font-bold">${t.format}</span>` : '';
    const qualityBadge = t.quality && t.quality !== 'best' ? `<span class="px-1.5 py-0.5 bg-white/10 rounded text-[10px]">${t.quality}p</span>` : '';

    return `
        <div class="glass-card queue-item p-4 ${isActive ? 'downloading-pulse' : ''}" id="task-${t.id}" data-status="${t.status}">
            <div class="flex items-start gap-3">
                <div class="w-12 h-12 rounded-lg overflow-hidden flex-shrink-0 bg-white/5 flex items-center justify-center">
                    ${t.thumbnail ? `<img src="${t.thumbnail}" alt="" class="w-full h-full object-cover">` : `<i class="${typeIcon} text-lg"></i>`}
                </div>
                <div class="flex-1 min-w-0">
                    <div class="flex items-start justify-between gap-2">
                        <div class="min-w-0">
                            <h4 class="font-medium text-sm truncate">${escapeHtml(t.title)}</h4>
                            <div class="flex items-center gap-2 mt-1">
                                <span class="status-badge px-2 py-0.5 rounded-md text-xs font-medium ${getStatusClass(t.status)}">${capitalize(t.status)}</span>
                                ${formatBadge}
                                ${qualityBadge}
                                ${t.duration ? `<span class="text-xs text-gray-500">${t.duration}</span>` : ''}
                            </div>
                        </div>
                        <div class="flex items-center gap-1 flex-shrink-0">
                            ${isComplete ? `<a href="/api/downloads/${t.id}/file" download class="download-btn p-2 rounded-lg hover:bg-white/10 transition text-emerald-400" title="Download"><i class="fas fa-download"></i></a>` : ''}
                            ${isActive || t.status === 'pending' ? `<button onclick="cancelTask('${t.id}')" class="p-2 rounded-lg hover:bg-white/10 transition text-red-400" title="Cancel"><i class="fas fa-xmark"></i></button>` : ''}
                            ${isComplete || isFailed ? `<button onclick="deleteTask('${t.id}')" class="p-2 rounded-lg hover:bg-white/10 transition text-gray-500" title="Remove"><i class="fas fa-trash-can"></i></button>` : ''}
                        </div>
                    </div>
                    <div class="mt-2">
                        <div class="flex items-center justify-between text-xs text-gray-400 mb-1">
                            <span class="speed-text">${t.file_size ? formatSize(t.file_size) : ''}</span>
                            <span class="progress-text">${Math.round(t.progress)}%</span>
                        </div>
                        <div class="progress-bar">
                            <div class="progress-bar-fill ${isComplete ? 'completed' : ''} ${isFailed ? 'failed' : ''}" style="width: ${t.progress}%"></div>
                        </div>
                    </div>
                    ${t.error_message ? `<p class="text-xs text-red-400 mt-1 truncate">${escapeHtml(t.error_message)}</p>` : ''}
                </div>
            </div>
        </div>
    `;
}

function getStatusClass(status) {
    const map = {
        pending: 'bg-gray-500/20 text-gray-400',
        downloading: 'bg-blue-500/20 text-blue-400',
        completed: 'bg-emerald-500/20 text-emerald-400',
        failed: 'bg-red-500/20 text-red-400',
        cancelled: 'bg-gray-500/20 text-gray-400',
    };
    return map[status] || map.pending;
}

function capitalize(s) {
    return s.charAt(0).toUpperCase() + s.slice(1);
}

async function cancelTask(id) {
    try {
        await api(`/api/downloads/${id}/cancel`, { method: 'POST' });
        showToast('Download cancelled', 'info');
        loadQueue();
    } catch (e) {
        showToast(e.message, 'error');
    }
}

async function deleteTask(id) {
    try {
        await api(`/api/downloads/${id}`, { method: 'DELETE' });
        const el = document.getElementById(`task-${id}`);
        if (el) el.remove();
        showToast('Removed from history', 'info');
    } catch (e) {
        showToast(e.message, 'error');
    }
}

async function loadHistory() {
    const filter = document.getElementById('history-filter')?.value || '';
    try {
        let url = '/api/downloads/?limit=50';
        if (filter) url += `&status=${filter}`;
        const tasks = await api(url);
        const container = document.getElementById('history-list');

        if (!tasks.length) {
            container.innerHTML = '<div class="glass-card p-12 text-center text-gray-500"><i class="fas fa-clock-rotate-left text-4xl mb-3 block"></i><p>No download history</p></div>';
            return;
        }

        container.innerHTML = tasks.map(t => renderTaskItem(t)).join('');
    } catch (e) {
        showToast('Failed to load history', 'error');
    }
}

async function downloadAllAsZip() {
    try {
        const tasks = await api('/api/downloads/?status=completed&limit=50');
        const ids = tasks.map(t => t.id);
        if (!ids.length) { showToast('No completed downloads', 'warning'); return; }

        const resp = await fetch('/api/downloads/bulk-zip', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(ids),
        });

        if (!resp.ok) throw new Error('Failed to create ZIP');

        const blob = await resp.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'downloads.zip';
        a.click();
        URL.revokeObjectURL(url);
        showToast('ZIP downloaded', 'success');
    } catch (e) {
        showToast(e.message, 'error');
    }
}

// Auto-refresh queue every 5 seconds
setInterval(() => {
    if (currentTab === 'queue') loadQueue();
}, 5000);
