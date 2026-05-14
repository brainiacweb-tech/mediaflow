import httpx
import re
import asyncio
from pathlib import Path
from backend.config import settings

COVER_OL = "https://covers.openlibrary.org/b/olid/{}-M.jpg"
COVER_ISBN = "https://covers.openlibrary.org/b/isbn/{}-M.jpg"


async def search_books(query: str, search_type: str = "title") -> list[dict]:
    results = []

    tasks = [
        _search_openlibrary(query, search_type),
        _search_gutenberg(query),
        _search_archive_org(query),
        _search_archive_fulltext(query),
        _search_isbndb(query, search_type),
    ]

    all_results = await asyncio.gather(*tasks, return_exceptions=True)

    for r in all_results:
        if isinstance(r, list):
            results.extend(r)

    seen_titles = set()
    unique = []
    for b in results:
        key = b["title"].lower().strip()[:50]
        if key not in seen_titles:
            seen_titles.add(key)
            unique.append(b)

    return unique[:40]


async def _search_openlibrary(query: str, search_type: str) -> list[dict]:
    params = {"limit": 40}
    if search_type == "title":
        params["title"] = query
    elif search_type == "author":
        params["author"] = query
    elif search_type == "isbn":
        params["isbn"] = query
    else:
        params["q"] = query

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get("https://openlibrary.org/search.json", params=params)
        resp.raise_for_status()
        data = resp.json()

    books = []
    for doc in data.get("docs", []):
        ia_ids = doc.get("ia", [])
        olid = doc.get("cover_edition_key") or (doc.get("edition_key", [None])[0])
        cover_url = COVER_OL.format(olid) if olid else None
        isbns = doc.get("isbn", [])
        ia_id = ia_ids[0] if ia_ids else None

        ebook_access = doc.get("ebook_access", "no_ebook")
        can_download = ebook_access == "public"
        source = "archive_public" if can_download else ("archive_borrow" if ia_id else "openlibrary")

        first_sentence = doc.get("first_sentence", "")
        if isinstance(first_sentence, dict):
            first_sentence = first_sentence.get("value", "")
        elif isinstance(first_sentence, list):
            first_sentence = first_sentence[0] if first_sentence else ""

        pages = doc.get("number_of_pages_median", "")
        lang = ", ".join(doc.get("language", [])[:2]) if doc.get("language") else ""
        desc_parts = [str(first_sentence)[:200]] if first_sentence else []
        if pages:
            desc_parts.append(f"{pages} pages")
        if lang:
            desc_parts.append(lang)

        books.append({
            "id": ia_id or doc.get("key", "").replace("/works/", ""),
            "title": doc.get("title", "Unknown"),
            "author": ", ".join(doc.get("author_name", ["Unknown"])),
            "cover_url": cover_url or (COVER_ISBN.format(isbns[0]) if isbns else None),
            "description": " | ".join(desc_parts) if desc_parts else "",
            "formats": ["PDF", "EPUB"],
            "file_size": None,
            "year": str(doc.get("first_publish_year", "")) if doc.get("first_publish_year") else None,
            "isbn": isbns[0] if isbns else None,
            "ia_id": ia_id,
            "ext": "pdf",
            "mirror": source,
        })

        if len(books) >= 20:
            break

    return books


async def _search_gutenberg(query: str) -> list[dict]:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get("https://gutendex.com/books/", params={"search": query})
            if resp.status_code != 200:
                return []
            data = resp.json()
    except Exception:
        return []

    books = []
    for b in data.get("results", [])[:10]:
        formats = b.get("formats", {})

        epub_url = formats.get("application/epub+zip", "")
        pdf_url = ""
        for key, url in formats.items():
            if "pdf" in key.lower():
                pdf_url = url
                break

        if not epub_url and not pdf_url:
            continue

        cover_url = formats.get("image/jpeg", "")
        authors = b.get("authors", [])
        author_name = authors[0]["name"] if authors else "Unknown"

        avail_formats = []
        if pdf_url:
            avail_formats.append("PDF")
        if epub_url:
            avail_formats.append("EPUB")

        books.append({
            "id": f"gut_{b['id']}",
            "title": b.get("title", "Unknown"),
            "author": author_name,
            "cover_url": cover_url,
            "description": f"Project Gutenberg | Downloads: {b.get('download_count', 0):,}",
            "formats": avail_formats,
            "file_size": None,
            "year": None,
            "isbn": None,
            "ia_id": str(b["id"]),
            "ext": "epub" if epub_url else "pdf",
            "mirror": "gutenberg",
            "_epub_url": epub_url,
            "_pdf_url": pdf_url,
        })

    return books


async def _search_archive_org(query: str) -> list[dict]:
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            params = {
                "q": f"{query} AND mediatype:texts AND format:(PDF OR EPUB)",
                "fl[]": ["identifier", "title", "creator", "year", "downloads", "format"],
                "rows": 15,
                "output": "json",
            }
            resp = await client.get("https://archive.org/advancedsearch.php", params=params)
            if resp.status_code != 200:
                return []
            data = resp.json()
    except Exception:
        return []

    books = []
    for doc in data.get("response", {}).get("docs", []):
        identifier = doc.get("identifier", "")
        if not identifier:
            continue

        title = doc.get("title", "Unknown")
        creator = doc.get("creator", "Unknown")
        if isinstance(creator, list):
            creator = ", ".join(creator)
        year = str(doc.get("year", "")) if doc.get("year") else None

        formats_list = doc.get("format", [])
        if isinstance(formats_list, str):
            formats_list = [formats_list]

        avail = []
        has_pdf = any("pdf" in f.lower() for f in formats_list)
        has_epub = any("epub" in f.lower() for f in formats_list)
        if has_pdf:
            avail.append("PDF")
        if has_epub:
            avail.append("EPUB")
        if not avail:
            avail = ["PDF"]

        downloads = doc.get("downloads", 0)
        desc = f"Internet Archive | Downloads: {downloads:,}" if downloads else "Internet Archive"

        cover_url = f"https://archive.org/services/img/{identifier}"

        books.append({
            "id": identifier,
            "title": title,
            "author": creator,
            "cover_url": cover_url,
            "description": desc,
            "formats": avail,
            "file_size": None,
            "year": year,
            "isbn": None,
            "ia_id": identifier,
            "ext": "pdf" if has_pdf else "epub",
            "mirror": "archive_public",
        })

    return books


async def _search_archive_fulltext(query: str) -> list[dict]:
    """Search Archive.org using the full-text search / scraping API."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            params = {
                "q": query,
                "mediatype": "texts",
                "sort": "-downloads",
                "rows": 15,
                "page": 1,
                "output": "json",
            }
            resp = await client.get(
                "https://archive.org/services/search/v1/scrape",
                params={"q": f"{query} AND mediatype:texts", "fields": "identifier,title,creator,date,downloads", "count": 15},
            )
            if resp.status_code != 200:
                return []
            data = resp.json()
    except Exception:
        return []

    books = []
    for item in data.get("items", []):
        identifier = item.get("identifier", "")
        if not identifier:
            continue

        title = item.get("title", "Unknown")
        creator = item.get("creator", "Unknown")
        if isinstance(creator, list):
            creator = ", ".join(creator)

        year = None
        date_str = item.get("date", "")
        if date_str:
            year = str(date_str)[:4]

        books.append({
            "id": identifier,
            "title": title,
            "author": creator,
            "cover_url": f"https://archive.org/services/img/{identifier}",
            "description": f"Internet Archive | Downloads: {item.get('downloads', 0):,}",
            "formats": ["PDF", "EPUB"],
            "file_size": None,
            "year": year,
            "isbn": None,
            "ia_id": identifier,
            "ext": "pdf",
            "mirror": "archive_public",
        })

    return books


async def _search_isbndb(query: str, search_type: str = "title") -> list[dict]:
    """Search ISBNdb API if API key is configured."""
    api_key = settings.isbndb_api_key
    if not api_key:
        return []

    try:
        headers = {"Authorization": api_key}
        async with httpx.AsyncClient(timeout=15) as client:
            if search_type == "isbn":
                resp = await client.get(
                    f"https://api2.isbndb.com/book/{query}",
                    headers=headers,
                )
                if resp.status_code != 200:
                    return []
                data = resp.json()
                book_list = [data.get("book", {})] if data.get("book") else []
            else:
                endpoint = "books" if search_type == "title" else "author"
                search_path = query.replace(" ", "+")
                resp = await client.get(
                    f"https://api2.isbndb.com/{endpoint}/{search_path}",
                    headers=headers,
                    params={"page": 1, "pageSize": 15},
                )
                if resp.status_code != 200:
                    return []
                data = resp.json()
                book_list = data.get("books", []) or data.get("data", [])
    except Exception:
        return []

    books = []
    for b in book_list[:15]:
        isbn13 = b.get("isbn13") or b.get("isbn") or ""
        isbn10 = b.get("isbn10", "")
        title = b.get("title", "Unknown")
        authors = b.get("authors", [])
        author = ", ".join(authors) if authors else "Unknown"
        cover = COVER_ISBN.format(isbn13) if isbn13 else None

        pages = b.get("pages")
        publisher = b.get("publisher", "")
        desc_parts = []
        if publisher:
            desc_parts.append(publisher)
        if pages:
            desc_parts.append(f"{pages} pages")
        desc_parts.append("ISBNdb")

        books.append({
            "id": isbn13 or isbn10 or title[:30],
            "title": title,
            "author": author,
            "cover_url": cover,
            "description": " | ".join(desc_parts),
            "formats": ["PDF", "EPUB"],
            "file_size": None,
            "year": str(b.get("date_published", ""))[:4] if b.get("date_published") else None,
            "isbn": isbn13 or isbn10,
            "ia_id": None,
            "ext": "pdf",
            "mirror": "isbndb",
        })

    return books


async def download_book_file(book_id: str, fmt: str = "pdf", mirror: str = "") -> dict | None:
    if mirror == "gutenberg":
        return await _download_gutenberg(book_id, fmt)

    if mirror == "isbndb":
        return await _download_by_isbn(book_id, fmt)

    result = await _download_archive(book_id, fmt)
    if result:
        return result

    result = await _try_alternative_downloads(book_id, fmt)
    if result:
        return result

    other_fmt = "epub" if fmt == "pdf" else "pdf"
    result = await _download_archive(book_id, other_fmt)
    if result:
        return result

    return None


async def _download_by_isbn(isbn: str, fmt: str) -> dict | None:
    """Try to find and download a book by ISBN from Archive.org."""
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        try:
            resp = await client.get(
                "https://archive.org/advancedsearch.php",
                params={
                    "q": f"isbn:{isbn} AND mediatype:texts",
                    "fl[]": ["identifier", "title"],
                    "rows": 5,
                    "output": "json",
                }
            )
            if resp.status_code == 200:
                docs = resp.json().get("response", {}).get("docs", [])
                for doc in docs:
                    ident = doc.get("identifier")
                    if ident:
                        result = await _download_archive(ident, fmt)
                        if result:
                            return result
        except Exception:
            pass

    result = await _try_alternative_downloads(isbn, fmt)
    return result


async def _download_gutenberg(book_id: str, fmt: str) -> dict | None:
    gut_id = book_id.replace("gut_", "")
    output_dir = settings.download_path

    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        resp = await client.get("https://gutendex.com/books/", params={"ids": gut_id})
        if resp.status_code != 200:
            return None
        data = resp.json()
        results = data.get("results", [])
        if not results:
            return None

        book = results[0]
        formats = book.get("formats", {})
        title = book.get("title", "Unknown")

        file_url = None
        if fmt == "epub":
            file_url = formats.get("application/epub+zip")
        if not file_url:
            for key, url in formats.items():
                if "pdf" in key.lower():
                    file_url = url
                    fmt = "pdf"
                    break
        if not file_url and fmt != "epub":
            file_url = formats.get("application/epub+zip")
            if file_url:
                fmt = "epub"
        if not file_url:
            txt_url = formats.get("text/plain; charset=utf-8") or formats.get("text/plain")
            if txt_url:
                file_url = txt_url
                fmt = "txt"

        if not file_url:
            return None

        resp = await client.get(file_url)
        if resp.status_code != 200:
            return None

        safe_title = "".join(c if c.isalnum() or c in (' ', '-', '_') else '_' for c in title)[:150].strip()
        filename = f"{safe_title}.{fmt}"
        out_path = output_dir / filename
        out_path.write_bytes(resp.content)

        return {
            "title": title,
            "file_path": str(out_path),
            "file_size": len(resp.content),
            "format": fmt,
            "filename": filename,
        }


async def _download_archive(ia_id: str, fmt: str) -> dict | None:
    if not ia_id:
        return None
    output_dir = settings.download_path
    ext = fmt.lower()

    async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
        try:
            resp = await client.get(f"https://archive.org/metadata/{ia_id}")
            if resp.status_code != 200:
                return None
            metadata = resp.json()
        except Exception:
            return None

        files = metadata.get("files", [])
        title = metadata.get("metadata", {}).get("title", ia_id)

        encrypted = ("encrypted", "lcp", "acs", "_encrypted")

        download_file = None
        for f in files:
            name = f.get("name", "").lower()
            if name.endswith(f".{ext}") and not any(kw in name for kw in encrypted):
                download_file = f
                break

        if not download_file:
            other = ".epub" if ext == "pdf" else ".pdf"
            for f in files:
                name = f.get("name", "").lower()
                if name.endswith(other) and not any(kw in name for kw in encrypted):
                    download_file = f
                    ext = other[1:]
                    break

        if not download_file:
            for f in files:
                name = f.get("name", "").lower()
                if name.endswith(".txt") and not any(kw in name for kw in encrypted):
                    download_file = f
                    ext = "txt"
                    break

        if not download_file:
            return None

        file_url = f"https://archive.org/download/{ia_id}/{download_file['name']}"
        try:
            resp = await client.get(file_url)
        except Exception:
            return None

        if resp.status_code != 200 or len(resp.content) < 500:
            return None

        content_type = resp.headers.get("content-type", "")
        if "text/html" in content_type and ext != "txt":
            return None

        safe_title = "".join(c if c.isalnum() or c in (' ', '-', '_') else '_' for c in title)[:150].strip()
        filename = f"{safe_title}.{ext}"
        out_path = output_dir / filename
        out_path.write_bytes(resp.content)

        return {
            "title": title,
            "file_path": str(out_path),
            "file_size": len(resp.content),
            "format": ext,
            "filename": filename,
        }


async def _try_alternative_downloads(book_id: str, fmt: str) -> dict | None:
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        try:
            resp = await client.get(f"https://openlibrary.org/works/{book_id}.json")
            if resp.status_code == 200:
                data = resp.json()
                ocaid = data.get("ocaid")
                if ocaid:
                    return await _download_archive(ocaid, fmt)
        except Exception:
            pass

        try:
            resp = await client.get(
                "https://archive.org/advancedsearch.php",
                params={
                    "q": f"identifier:{book_id} OR title:{book_id}",
                    "fl[]": ["identifier"],
                    "rows": 3,
                    "output": "json",
                }
            )
            if resp.status_code == 200:
                docs = resp.json().get("response", {}).get("docs", [])
                for doc in docs:
                    ident = doc.get("identifier")
                    if ident and ident != book_id:
                        result = await _download_archive(ident, fmt)
                        if result:
                            return result
        except Exception:
            pass

    return None
