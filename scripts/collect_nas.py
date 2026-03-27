"""
NAS Knowledge Base Search — collect_nas.py
============================================
Search internal NAS storage for relevant documents by keyword.
Supports MD (full-text) and PDF (parsed text) files.

Features:
  - Full-text search (brute-force for small sets, whoosh index for large)
  - Date range filtering via filename pattern
  - Context preview snippets around keyword matches
  - Incremental index building (only indexes new files)

Usage:
  # Build/update index (run once, then incrementally)
  python collect_nas.py --build-index

  # Search by keyword (uses index if available, else brute-force)
  python collect_nas.py --keyword "智谱"

  # Search with date range
  python collect_nas.py --keyword "大模型" --after 20260301

  # List recent files (no keyword)
  python collect_nas.py --recent 7

  # Read specific file content
  python collect_nas.py --read "~/NAS/.../report.md"
"""
import os
import re
import json
import argparse
import time
import hashlib
from datetime import datetime, timedelta

# ============================================================
# Config
# ============================================================
DEFAULT_NAS_PATH = os.environ.get("NAS_PATH", os.path.expanduser("~/NAS/wechat_info_diary2"))
LOCAL_INDEX_DIR = os.path.expanduser("~/nas_search_index")
SUPPORTED_EXTENSIONS = {".md", ".pdf", ".txt"}
MAX_PREVIEW_CHARS = 300
MAX_CONTEXT_CHARS = 5000
INDEX_STATE_FILE = os.path.join(LOCAL_INDEX_DIR, "indexed_files.json")


# ============================================================
# File Discovery
# ============================================================

def discover_files(base_path, extensions=None, after=None, before=None):
    """Walk NAS directory and return file metadata list."""
    if extensions is None:
        extensions = SUPPORTED_EXTENSIONS
    files = []
    try:
        for entry in os.scandir(base_path):
            if not entry.is_file():
                continue
            ext = os.path.splitext(entry.name)[1].lower()
            if ext not in extensions:
                continue
            date_match = re.search(r'(\d{8})', entry.name)
            date_str = date_match.group(1) if date_match else ""
            if after and date_str and date_str < after:
                continue
            if before and date_str and date_str > before:
                continue
            stat = entry.stat()
            files.append({
                "path": entry.path, "name": entry.name, "ext": ext,
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "date_str": date_str,
            })
    except (PermissionError, FileNotFoundError, OSError) as e:
        print(f"  [NAS] Error: {e}")
    files.sort(key=lambda f: f.get("date_str", ""), reverse=True)
    return files


# ============================================================
# Content Reading (MD direct, PDF parsed)
# ============================================================

def read_file_content(filepath, max_chars=None):
    """Read file content. MD/TXT = direct; PDF = parse first."""
    if max_chars is None:
        max_chars = MAX_CONTEXT_CHARS
    ext = os.path.splitext(filepath)[1].lower()
    if ext in (".md", ".txt"):
        return _read_text(filepath, max_chars)
    elif ext == ".pdf":
        return _read_pdf(filepath, max_chars)
    return f"[Unsupported: {ext}]"


def _read_text(filepath, max_chars):
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            return f.read(max_chars)
    except Exception as e:
        return f"[Read error: {e}]"


def _read_pdf(filepath, max_chars):
    # Try pdfplumber first
    try:
        import pdfplumber
        parts = []
        with pdfplumber.open(filepath) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    parts.append(t)
                if sum(len(p) for p in parts) >= max_chars:
                    break
        return "\n".join(parts)[:max_chars]
    except ImportError:
        pass
    # Fallback: PyPDF2
    try:
        from PyPDF2 import PdfReader
        reader = PdfReader(filepath)
        parts = []
        for page in reader.pages:
            t = page.extract_text()
            if t:
                parts.append(t)
            if sum(len(p) for p in parts) >= max_chars:
                break
        return "\n".join(parts)[:max_chars]
    except ImportError:
        return "[PDF parsing unavailable: install pdfplumber or PyPDF2]"
    except Exception as e:
        return f"[PDF error: {e}]"


# ============================================================
# Whoosh Full-Text Index
# ============================================================

def _get_whoosh_schema():
    """Define the search index schema."""
    from whoosh.fields import Schema, TEXT, ID, STORED
    from whoosh.analysis import RegexTokenizer, LowercaseFilter
    # Simple analyzer that works for both Chinese and English
    analyzer = RegexTokenizer(r"[\w\u4e00-\u9fff]+") | LowercaseFilter()
    return Schema(
        path=ID(stored=True, unique=True),
        filename=STORED,
        date_str=ID(stored=True),
        size=STORED,
        content=TEXT(analyzer=analyzer, stored=False),
        # Store a preview snippet
        preview=STORED,
    )


def build_index(base_path=None, force=False):
    """
    Build or update the whoosh full-text index.
    Incremental: only indexes new/modified files.
    """
    try:
        from whoosh.index import create_in, open_dir, exists_in
    except ImportError:
        print("  [Index] whoosh not installed. Run: python -m pip install whoosh")
        return False

    if base_path is None:
        base_path = DEFAULT_NAS_PATH
    os.makedirs(LOCAL_INDEX_DIR, exist_ok=True)

    # Load previously indexed files state
    indexed = {}
    if os.path.exists(INDEX_STATE_FILE) and not force:
        with open(INDEX_STATE_FILE, "r") as f:
            indexed = json.load(f)

    # Open or create index
    schema = _get_whoosh_schema()
    if exists_in(LOCAL_INDEX_DIR) and not force:
        ix = open_dir(LOCAL_INDEX_DIR)
        print(f"  [Index] Opened existing index at {LOCAL_INDEX_DIR}")
    else:
        ix = create_in(LOCAL_INDEX_DIR, schema)
        indexed = {}
        print(f"  [Index] Created new index at {LOCAL_INDEX_DIR}")

    # Discover all files
    files = discover_files(base_path)
    print(f"  [Index] Found {len(files)} files on NAS")

    # Find new/modified files
    new_files = []
    for f in files:
        key = f["path"]
        prev = indexed.get(key, {})
        if prev.get("modified") == f["modified"] and prev.get("size") == f["size"]:
            continue  # Already indexed, no change
        new_files.append(f)

    if not new_files:
        print(f"  [Index] All files already indexed. Nothing to do.")
        return True

    print(f"  [Index] {len(new_files)} new/modified files to index...")
    writer = ix.writer()
    t0 = time.time()

    for i, f in enumerate(new_files):
        content = read_file_content(f["path"], max_chars=200000)  # Index up to 200K chars
        if not content or content.startswith("["):
            continue

        # Store a 500-char preview
        preview = content[:500].replace("\n", " ").strip()

        writer.update_document(
            path=f["path"],
            filename=f["name"],
            date_str=f["date_str"],
            size=f["size"],
            content=content,
            preview=preview,
        )

        # Track indexed state
        indexed[f["path"]] = {"modified": f["modified"], "size": f["size"]}

        if (i + 1) % 10 == 0:
            print(f"    Indexed {i+1}/{len(new_files)}...")

    writer.commit()
    elapsed = time.time() - t0
    print(f"  [Index] Indexed {len(new_files)} files in {elapsed:.1f}s")

    # Save state
    with open(INDEX_STATE_FILE, "w") as f:
        json.dump(indexed, f)

    return True


def search_index(keyword, after=None, before=None, max_results=20):
    """Search using the whoosh index. Returns results in ~0.1s."""
    try:
        from whoosh.index import open_dir
        from whoosh.qparser import QueryParser
    except ImportError:
        return None  # Fallback to brute-force

    if not os.path.exists(LOCAL_INDEX_DIR):
        return None

    try:
        ix = open_dir(LOCAL_INDEX_DIR)
    except Exception:
        return None

    results = []
    with ix.searcher() as searcher:
        qp = QueryParser("content", ix.schema)
        q = qp.parse(keyword)
        hits = searcher.search(q, limit=max_results * 3)  # Over-fetch for date filtering

        for hit in hits:
            date_str = hit.get("date_str", "")
            if after and date_str and date_str < after:
                continue
            if before and date_str and date_str > before:
                continue

            results.append({
                "path": hit["path"],
                "name": hit["filename"],
                "date_str": date_str,
                "size": hit["size"],
                "size_readable": _fmt_size(hit["size"]),
                "score": round(hit.score, 2),
                "preview": hit.get("preview", "")[:200],
                "match_count": 0,  # Whoosh doesn't give exact count
                "previews": [f"...{hit.get('preview', '')[:200]}..."],
            })

            if len(results) >= max_results:
                break

    return results


# ============================================================
# Brute-Force Search (fallback when no index)
# ============================================================

def search_files(keyword, base_path=None, after=None, before=None, max_results=20):
    """Search by reading every file. Slow on NAS but works without index."""
    if base_path is None:
        base_path = DEFAULT_NAS_PATH
    print(f"  [NAS Search] Keyword: '{keyword}'")
    print(f"  [NAS Search] Path: {base_path}")
    files = discover_files(base_path, after=after, before=before)
    print(f"  [NAS Search] Found {len(files)} files to scan")

    results = []
    t0 = time.time()
    for f in files:
        content = read_file_content(f["path"])
        if not content:
            continue
        matches = list(re.finditer(re.escape(keyword), content, re.IGNORECASE))
        if not matches:
            continue
        previews = []
        for m in matches[:3]:
            start = max(0, m.start() - 80)
            end = min(len(content), m.end() + 220)
            snippet = content[start:end].replace("\n", " ").strip()
            previews.append(f"...{snippet}...")
        results.append({
            "path": f["path"], "name": f["name"],
            "date_str": f["date_str"], "size": f["size"],
            "size_readable": _fmt_size(f["size"]),
            "match_count": len(matches), "previews": previews,
        })
        if len(results) >= max_results:
            break

    elapsed = time.time() - t0
    print(f"  [NAS Search] {len(results)} matches in {elapsed:.1f}s")
    return results


# ============================================================
# Smart Search (index first, fallback to brute-force)
# ============================================================

def smart_search(keyword, base_path=None, after=None, before=None, max_results=20):
    """
    Try indexed search first (instant). If no index, fall back to brute-force.
    Returns (results, method) where method is 'index' or 'brute-force'.
    """
    idx_results = search_index(keyword, after=after, before=before, max_results=max_results)
    if idx_results is not None:
        print(f"  [Search] Using index → {len(idx_results)} results (instant)")
        return idx_results, "index"

    print(f"  [Search] No index found, falling back to brute-force scan...")
    return search_files(keyword, base_path, after, before, max_results), "brute-force"


def list_recent(base_path=None, days=7):
    """List recent files without keyword search."""
    if base_path is None:
        base_path = DEFAULT_NAS_PATH
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
    files = discover_files(base_path, after=cutoff)
    return [{"name": f["name"], "date_str": f["date_str"],
             "size_readable": _fmt_size(f["size"]), "path": f["path"]} for f in files]


def _fmt_size(b):
    if b >= 1048576:
        return f"{b/1048576:.1f}MB"
    elif b >= 1024:
        return f"{b/1024:.0f}KB"
    return f"{b}B"


# ============================================================
# Main (CLI)
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="NAS Knowledge Base Search")
    parser.add_argument("--keyword", "-k", help="Search keyword")
    parser.add_argument("--path", "-p", default=DEFAULT_NAS_PATH)
    parser.add_argument("--after", help="Files after YYYYMMDD")
    parser.add_argument("--before", help="Files before YYYYMMDD")
    parser.add_argument("--recent", type=int, default=0, help="List recent N days")
    parser.add_argument("--max-results", "-n", type=int, default=20)
    parser.add_argument("--read", help="Read specific file content")
    parser.add_argument("--output", "-o", help="Save results to JSON")

    # Index commands
    parser.add_argument("--build-index", action="store_true",
                        help="Build/update whoosh full-text index")
    parser.add_argument("--force-rebuild", action="store_true",
                        help="Force full rebuild of index")
    parser.add_argument("--no-index", action="store_true",
                        help="Skip index, force brute-force search")

    args = parser.parse_args()

    # Mode: Build index
    if args.build_index or args.force_rebuild:
        ok = build_index(args.path, force=args.force_rebuild)
        if ok:
            print(f"\n  ✅ Index ready at {LOCAL_INDEX_DIR}")
        else:
            print(f"\n  ❌ Index build failed")
        return

    # Mode: Read specific file
    if args.read:
        print(read_file_content(args.read, max_chars=MAX_CONTEXT_CHARS))
        return

    # Mode: List recent
    if args.recent > 0:
        files = list_recent(args.path, args.recent)
        print(f"\n  最近 {args.recent} 天的文件 ({len(files)} 份):\n")
        for i, f in enumerate(files, 1):
            print(f"  {i:3d}. [{f['date_str']}] {f['name']} ({f['size_readable']})")
        return

    # Mode: Keyword search
    if not args.keyword:
        parser.error("Need --keyword, --recent, --build-index, or --read")

    if args.no_index:
        results = search_files(args.keyword, args.path, args.after, args.before, args.max_results)
        method = "brute-force"
    else:
        results, method = smart_search(args.keyword, args.path, args.after, args.before, args.max_results)

    if not results:
        print(f"\n  未找到包含 '{args.keyword}' 的文件")
        return

    print(f"\n  找到 {len(results)} 份文件包含 '{args.keyword}' (via {method}):\n")
    for i, r in enumerate(results, 1):
        score_str = f", score={r['score']}" if 'score' in r and r['score'] else ""
        mc_str = f", {r['match_count']}处匹配" if r.get('match_count') else ""
        print(f"  {i}. [{r['date_str']}] {r['name']} ({r['size_readable']}{mc_str}{score_str})")
        for preview in r.get("previews", [])[:2]:
            print(f"     → {preview[:150]}")
        print()

    if args.output:
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"  📁 JSON saved: {args.output}")


if __name__ == "__main__":
    main()
