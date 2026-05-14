let bookResults = [];

async function searchBooks() {
    const query = document.getElementById('book-query').value.trim();
    if (!query) { showToast('Enter a search term', 'warning'); return; }

    const btn = document.getElementById('book-search-btn');
    const skeleton = document.getElementById('book-skeleton');
    const results = document.getElementById('book-results');

    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i><span class="hidden sm:inline">Searching</span>';
    skeleton.classList.remove('hidden');
    results.classList.add('hidden');

    try {
        const searchType = document.getElementById('book-search-type').value;
        bookResults = await api('/api/books/search', {
            method: 'POST',
            body: JSON.stringify({ query, search_type: searchType }),
        });

        renderBooks(bookResults);
        results.classList.remove('hidden');
        if (bookResults.length > 0) {
            showToast(`Found ${bookResults.length} book(s)`, 'success');
        } else {
            showToast('No books found. Try different keywords.', 'warning');
        }
    } catch (e) {
        showToast(e.message, 'error');
    } finally {
        skeleton.classList.add('hidden');
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-search"></i><span class="hidden sm:inline">Search</span>';
    }
}

function renderBooks(books) {
    const container = document.getElementById('book-results');

    if (!books.length) {
        container.innerHTML = `
            <div class="col-span-full glass-card p-12 text-center text-gray-500">
                <i class="fas fa-book-open text-4xl mb-3 block"></i>
                <p class="font-medium">No books found</p>
                <p class="text-sm mt-1">Try different keywords or search by author</p>
            </div>`;
        return;
    }

    container.innerHTML = books.map((b, idx) => {
        const sourceTag = b.mirror === 'gutenberg' ? 'Gutenberg'
            : b.mirror === 'archive_public' ? 'Archive.org'
            : b.mirror === 'archive_borrow' ? 'Archive'
            : b.mirror === 'isbndb' ? 'ISBNdb'
            : 'OpenLibrary';
        const sourceClass = b.mirror === 'gutenberg' ? 'bg-amber-500/15 text-amber-400'
            : b.mirror === 'archive_public' ? 'bg-emerald-500/15 text-emerald-400'
            : b.mirror === 'isbndb' ? 'bg-purple-500/15 text-purple-400'
            : 'bg-blue-500/15 text-blue-400';

        return `
        <div class="glass-card book-card p-4">
            <div class="flex gap-4">
                <div class="w-20 h-28 rounded-lg overflow-hidden flex-shrink-0 bg-white/5">
                    ${b.cover_url
                        ? `<img src="${b.cover_url}" alt="" class="w-full h-full object-cover" loading="lazy"
                            onerror="this.parentElement.innerHTML='<div class=\\'w-full h-full flex items-center justify-center\\'><i class=\\'fas fa-book text-2xl text-gray-600\\'></i></div>'">`
                        : '<div class="w-full h-full flex items-center justify-center"><i class="fas fa-book text-2xl text-gray-600"></i></div>'}
                </div>
                <div class="flex-1 min-w-0">
                    <h4 class="font-semibold text-sm line-clamp-2">${escapeHtml(b.title)}</h4>
                    <p class="text-xs text-gray-400 mt-1">${escapeHtml(b.author || 'Unknown Author')}</p>
                    ${b.year ? `<p class="text-xs text-gray-500 mt-0.5">${b.year}</p>` : ''}
                    ${b.description ? `<p class="text-xs text-gray-500 mt-1 line-clamp-2">${escapeHtml(b.description)}</p>` : ''}
                    <div class="flex flex-wrap gap-1.5 mt-2">
                        <span class="px-2 py-0.5 ${sourceClass} text-[10px] rounded-md font-semibold">${sourceTag}</span>
                        ${b.formats.map(f => `<span class="px-2 py-0.5 bg-primary-500/15 text-primary-400 text-[10px] rounded-md font-semibold">${f}</span>`).join('')}
                    </div>
                </div>
            </div>
            <div class="mt-3 flex gap-2 justify-end">
                ${b.formats.includes('EPUB') ? `<button onclick="downloadBook(${idx}, this, 'epub')"
                    class="px-4 py-2 bg-gradient-to-r from-blue-600 to-blue-500 hover:from-blue-500 hover:to-blue-400 rounded-lg text-xs font-semibold transition-all shadow-lg shadow-blue-500/20 flex items-center gap-2">
                    <i class="fas fa-download"></i> EPUB
                </button>` : ''}
                ${b.formats.includes('PDF') ? `<button onclick="downloadBook(${idx}, this, 'pdf')"
                    class="px-4 py-2 bg-gradient-to-r from-emerald-600 to-emerald-500 hover:from-emerald-500 hover:to-emerald-400 rounded-lg text-xs font-semibold transition-all shadow-lg shadow-emerald-500/20 flex items-center gap-2">
                    <i class="fas fa-download"></i> PDF
                </button>` : ''}
            </div>
        </div>`;
    }).join('');
}

async function downloadBook(idx, btnEl, preferredFmt) {
    const book = bookResults[idx];
    if (!book) return;

    const origHtml = btnEl.innerHTML;
    btnEl.disabled = true;
    btnEl.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Loading...';
    showToast(`Downloading "${book.title}"...`, 'info');

    const fmt = preferredFmt || (book.ext || book.formats[0] || 'pdf').toLowerCase();
    const mirror = encodeURIComponent(book.mirror || '');
    const downloadUrl = `/api/books/download/${encodeURIComponent(book.id)}?fmt=${fmt}&mirror=${mirror}`;

    try {
        const resp = await fetch(downloadUrl);

        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Download failed' }));
            throw new Error(err.detail || 'Download failed');
        }

        const contentType = resp.headers.get('content-type') || '';
        if (contentType.includes('application/json')) {
            const err = await resp.json();
            throw new Error(err.detail || 'Download failed');
        }

        const blob = await resp.blob();
        if (blob.size < 500) {
            throw new Error('File too small — may not be available. Try a different format.');
        }

        const disposition = resp.headers.get('content-disposition');
        let filename = `${book.title.substring(0, 80)}.${fmt}`;
        if (disposition) {
            const match = disposition.match(/filename\*?=(?:UTF-8''|"?)([^";]+)/i);
            if (match) filename = decodeURIComponent(match[1].replace(/"/g, ''));
        }

        const blobUrl = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = blobUrl;
        a.download = filename;
        a.style.display = 'none';
        document.body.appendChild(a);
        a.click();
        setTimeout(() => {
            document.body.removeChild(a);
            URL.revokeObjectURL(blobUrl);
        }, 5000);

        showToast(`"${book.title}" downloaded! Check your downloads folder.`, 'success');
    } catch (e) {
        const msg = e.message || 'Download failed';
        if (msg.includes('not available') || msg.includes('not found') || msg.includes('Try a different')) {
            showToast(`${msg} — Try the other format button or a different edition.`, 'error');
        } else {
            showToast(msg, 'error');
        }
    } finally {
        btnEl.disabled = false;
        btnEl.innerHTML = origHtml;
    }
}
