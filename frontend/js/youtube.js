let playlistData = null;
let selectedVideos = new Set();

async function fetchYouTubeInfo() {
    const url = document.getElementById('yt-url').value.trim();
    if (!url) { showToast('Please enter a URL', 'warning'); return; }

    const btn = document.getElementById('yt-fetch-btn');
    const skeleton = document.getElementById('yt-skeleton');
    const results = document.getElementById('yt-results');

    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i><span class="hidden sm:inline">Loading</span>';
    skeleton.classList.remove('hidden');
    results.classList.add('hidden');
    selectedVideos.clear();

    try {
        playlistData = await api('/api/youtube/info', {
            method: 'POST',
            body: JSON.stringify({ url }),
        });

        renderPlaylist();
        results.classList.remove('hidden');
        showToast(`Found ${playlistData.video_count} video(s)`, 'success');
    } catch (e) {
        showToast(e.message, 'error');
    } finally {
        skeleton.classList.add('hidden');
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-search"></i><span class="hidden sm:inline">Fetch</span>';
    }
}

function estimateSize(durationSec, quality) {
    if (!durationSec) return null;
    const bitrates = { "144": 0.2, "360": 0.7, "480": 1.2, "720": 2.5, "1080": 5.0, "best": 5.0 };
    const mbps = bitrates[quality] || 2.5;
    const sizeMB = (mbps * durationSec) / 8;
    return sizeMB > 1024 ? (sizeMB / 1024).toFixed(1) + ' GB' : Math.round(sizeMB) + ' MB';
}

function renderPlaylist() {
    if (!playlistData) return;

    document.getElementById('yt-playlist-title').textContent = playlistData.title;
    document.getElementById('yt-video-count').textContent = playlistData.video_count + ' video(s)';

    if (selectedVideos.size === 0) {
        selectedVideos = new Set(playlistData.videos.map(function(v) { return v.id; }));
    }

    var quality = document.getElementById('yt-quality').value;
    var list = document.getElementById('yt-video-list');
    var html = '';
    playlistData.videos.forEach(function(v) {
        var size = estimateSize(v.duration_seconds, quality);
        var isSelected = selectedVideos.has(v.id);
        var cardClass = 'video-card' + (isSelected ? ' selected' : '');
        var thumb = v.thumbnail
            ? '<img src="' + v.thumbnail + '" alt="" loading="lazy">'
            : '<div class="w-full h-full flex items-center justify-center"><i class="fas fa-film text-3xl text-gray-600"></i></div>';
        var durationHtml = v.duration ? '<span class="duration-badge">' + v.duration + '</span>' : '';
        var sizeHtml = size ? '<span class="size-badge">' + size + '</span>' : '';
        var sizeInfo = size ? '<span><i class="fas fa-hard-drive mr-1"></i>' + size + '</span>' : '';

        html += '<div class="' + cardClass + '" data-id="' + v.id + '" onclick="toggleVideo(\'' + v.id + '\')">'
            + '<div class="check-overlay"><i class="fas fa-check text-xs"></i></div>'
            + '<div class="thumbnail-wrapper">' + thumb + durationHtml + sizeHtml + '</div>'
            + '<div class="p-3">'
            + '<h4 class="text-sm font-medium line-clamp-2 leading-tight">' + escapeHtml(v.title) + '</h4>'
            + '<div class="flex items-center gap-2 mt-2 text-xs text-gray-400">' + sizeInfo + '</div>'
            + '</div></div>';
    });
    list.innerHTML = html;
}

function toggleVideo(id) {
    if (selectedVideos.has(id)) selectedVideos.delete(id);
    else selectedVideos.add(id);

    var card = document.querySelector('.video-card[data-id="' + id + '"]');
    if (card) card.classList.toggle('selected', selectedVideos.has(id));
}

function selectAllVideos() {
    if (!playlistData) return;
    playlistData.videos.forEach(function(v) { selectedVideos.add(v.id); });
    document.querySelectorAll('.video-card').forEach(function(c) { c.classList.add('selected'); });
}

function deselectAllVideos() {
    selectedVideos.clear();
    document.querySelectorAll('.video-card').forEach(function(c) { c.classList.remove('selected'); });
}

async function downloadSelected() {
    if (selectedVideos.size === 0) { showToast('No videos selected', 'warning'); return; }

    var url = document.getElementById('yt-url').value.trim();
    var quality = document.getElementById('yt-quality').value;
    var format = document.getElementById('yt-format').value;

    try {
        var tasks = await api('/api/youtube/download', {
            method: 'POST',
            body: JSON.stringify({
                url: url,
                quality: quality,
                format: format,
                video_ids: Array.from(selectedVideos),
            }),
        });

        showToast(tasks.length + ' download(s) started', 'success');
        switchTab('queue');
        loadQueue();
    } catch (e) {
        showToast(e.message, 'error');
    }
}

function onQualityChange() {
    if (playlistData) renderPlaylist();
}

function escapeHtml(text) {
    var d = document.createElement('div');
    d.textContent = text;
    return d.innerHTML;
}
