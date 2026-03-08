#!/usr/bin/env python3
"""
SobreSites Archive Indexer
============================
Escaneia HTMLs do forum e cria um banco SQLite com metadados e texto
para navegacao e busca full-text no frontend.

Funcionalidades:
  - Indexacao incremental (so processa arquivos novos/modificados)
  - FTS5 para busca de texto
  - Extrai: forum, topico, pagina, autor, data, texto do post

Uso:
  python indexer.py "C:\\...\\forum" "C:\\...\\archive.db"
"""

import os
import re
import sys
import sqlite3
import hashlib
import time
from html.parser import HTMLParser


# ============================================================
# UTILITARIOS
# ============================================================

class HTMLTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self._result = []
        self._skip = False

    def handle_starttag(self, tag, attrs):
        if tag.lower() in ('script', 'style', 'noscript'):
            self._skip = True
        if tag.lower() in ('br', 'p', 'hr', 'tr', 'li'):
            self._result.append('\n')

    def handle_endtag(self, tag):
        if tag.lower() in ('script', 'style', 'noscript'):
            self._skip = False

    def handle_data(self, data):
        if not self._skip:
            self._result.append(data)

    def get_text(self):
        return ''.join(self._result).strip()


def html_to_text(html_content):
    if not html_content:
        return ''
    extractor = HTMLTextExtractor()
    try:
        extractor.feed(html_content)
        return extractor.get_text()
    except Exception:
        return re.sub(r'<[^>]+>', ' ', html_content)


def read_file(filepath):
    with open(filepath, 'rb') as f:
        raw = f.read()
    charset = re.search(rb'charset[="\s]+([\w-]+)', raw[:2000])
    declared = charset.group(1).decode('ascii').lower() if charset else None
    for enc in ([declared] if declared else []) + ['utf-8', 'iso-8859-1', 'cp1252']:
        try:
            if enc:
                return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode('iso-8859-1', errors='replace')


def file_hash(filepath):
    """Hash rapido baseado em tamanho + mtime para detectar mudancas."""
    st = os.stat(filepath)
    return f"{st.st_size}_{int(st.st_mtime)}"


# ============================================================
# DETECTORES
# ============================================================

def detect_source(filepath, content):
    filename = os.path.basename(filepath).lower()
    full_path = filepath.lower()
    if '.asp' in filename or '.asp' in full_path or 'pop_profile' in content[:3000].lower():
        return 'sobresites.com.br'
    return 'sobresites.com'


def detect_page_type(filepath, content):
    filename = os.path.basename(filepath).lower()
    full_path = filepath.lower().replace('\\', '/')
    cl = content.lower()

    if '429 too many requests' in cl or '502 bad gateway' in cl:
        return 'junk'
    if len(content.strip()) < 300:
        return 'junk'

    # Por nome de arquivo (ja renomeados)
    if filename.startswith('asp_topic_') or filename.startswith('phpbb_topic_') or filename.startswith('phpbb_post_'):
        return 'topic'
    if filename.startswith('asp_forum_') or filename.startswith('phpbb_forum_'):
        return 'forum_list'
    if filename.startswith('asp_profile_') or filename.startswith('phpbb_profile_'):
        return 'profile'
    if filename.startswith('asp_members') or filename.startswith('phpbb_memberlist'):
        return 'members'
    if filename.startswith('asp_post_') or filename.startswith('phpbb_posting_'):
        return 'post_reply'
    if filename.startswith('asp_index_') or filename.startswith('phpbb_index'):
        return 'index'

    # index.html dentro de pasta com nome de URL
    if filename in ('index.html', 'index.htm'):
        if 'post.asp' in full_path or 'posting.php' in full_path:
            return 'post_reply'
        if 'topic.asp' in full_path or 'viewtopic.php' in full_path:
            return 'topic'
        if 'forum.asp' in full_path or 'viewforum.php' in full_path:
            return 'forum_list'

    # Por conteudo
    if 'class="postbody"' in cl:
        return 'topic'
    if 'enviado em' in cl and 'topic_id' in cl:
        return 'topic'
    if 'name="method_type"' in cl and 'value="reply"' in cl:
        return 'post_reply'

    return 'other'


# ============================================================
# EXTRACTORES DE POSTS
# ============================================================

MONTHS_PT = {
    'jan': 1, 'fev': 2, 'mar': 3, 'abr': 4, 'mai': 5, 'jun': 6,
    'jul': 7, 'ago': 8, 'set': 9, 'out': 10, 'nov': 11, 'dez': 12
}


def parse_phpbb_date(date_str):
    try:
        date_str = date_str.strip()
        parts = date_str.split(' ', 1)
        if len(parts) > 1 and len(parts[0]) <= 4:
            date_str = parts[1].strip()
        m = re.match(r'(\w+)\s+(\d{1,2}),?\s+(\d{4})\s+(\d{1,2}):(\d{2})\s*(am|pm)?', date_str, re.IGNORECASE)
        if m:
            month = MONTHS_PT.get(m.group(1).lower()[:3], 0)
            if month == 0:
                return date_str
            day, year, hour, minute = int(m.group(2)), int(m.group(3)), int(m.group(4)), int(m.group(5))
            ampm = (m.group(6) or '').lower()
            if ampm == 'pm' and hour != 12:
                hour += 12
            elif ampm == 'am' and hour == 12:
                hour = 0
            return f"{year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}"
    except Exception:
        pass
    return date_str


def extract_posts_phpbb(content, filepath):
    posts = []

    topic_title = ''
    tm = re.search(r'Exibir t.pico\s*-\s*(.+?)</title>', content, re.IGNORECASE | re.DOTALL)
    if tm:
        topic_title = html_to_text(tm.group(1)).strip()

    topic_id = ''
    tid = re.search(r'viewtopic\.php\?t=(\d+)', content, re.IGNORECASE)
    if tid:
        topic_id = tid.group(1)
    if not topic_id:
        tid2 = re.search(r'posting\.php\?mode=\w+&(?:amp;)?t=(\d+)', content, re.IGNORECASE)
        if tid2:
            topic_id = tid2.group(1)

    forum_name = ''
    fm = re.search(r'viewforum\.php\?f=\d+[^>]*>([^<]+)', content, re.IGNORECASE)
    if fm:
        forum_name = html_to_text(fm.group(1))

    forum_id = ''
    fi = re.search(r'viewforum\.php\?f=(\d+)', content, re.IGNORECASE)
    if fi:
        forum_id = fi.group(1)

    page = 1
    sm = re.search(r'[?&]start=(\d+)', filepath, re.IGNORECASE)
    if sm:
        page = (int(sm.group(1)) // 15) + 1

    blocks = re.split(r'(?=<span\s+class="name"><a\s+name=")', content, flags=re.IGNORECASE)

    for block in blocks[1:]:
        post = {}

        pid = re.search(r'<a\s+name="(\d+)"', block, re.IGNORECASE)
        if pid:
            post['post_id'] = pid.group(1)

        am = re.search(r'<strong>([^<]+)</strong>', block)
        if am:
            post['author'] = am.group(1).strip()
        else:
            continue

        uid = re.search(r'profile\.php\?mode=viewprofile&(?:amp;)?u=(\d+)', block, re.IGNORECASE)
        if uid:
            post['author_id'] = uid.group(1)

        dm = re.search(r'Enviada:\s*\n?\s*(.+?)</td>', block, re.DOTALL | re.IGNORECASE)
        if dm:
            post['date_raw'] = html_to_text(dm.group(1)).strip()
            post['date'] = parse_phpbb_date(post['date_raw'])

        loc = re.search(r'Localiza[çc][ãa]o:\s*(.+?)(?:<|$)', block, re.IGNORECASE)
        if loc:
            post['location'] = html_to_text(loc.group(1)).strip()

        cm = re.search(r'class="postbody">\s*(?:<hr\s*/?>)?\s*(.*?)</td>', block, re.DOTALL | re.IGNORECASE)
        if cm:
            post['content_text'] = html_to_text(cm.group(1))

        sig_split = post.get('content_text', '').split('_________________')
        if len(sig_split) > 1:
            post['content_text'] = sig_split[0].strip()

        post['topic_title'] = topic_title
        post['topic_id'] = topic_id
        post['forum_name'] = forum_name
        post['forum_id'] = forum_id
        post['page'] = page
        post['source'] = 'sobresites.com'

        posts.append(post)

    return posts


def extract_posts_asp(content, filepath):
    posts = []

    topic_title = ''
    breadcrumb = re.search(r'topic\.asp\?TOPIC_ID=\d+[^>]*>([^<]+)', content, re.IGNORECASE)
    if breadcrumb:
        topic_title = html_to_text(breadcrumb.group(1))

    topic_id = ''
    tid = re.search(r'TOPIC_ID[=\'](\d+)', content, re.IGNORECASE)
    if tid:
        topic_id = tid.group(1)

    forum_name = ''
    fm = re.search(r'FORUM\.asp\?FORUM_ID=\d+[^>]*>([^<]+)', content, re.IGNORECASE)
    if fm:
        forum_name = html_to_text(fm.group(1))

    forum_id = ''
    fi = re.search(r'FORUM_ID=(\d+)', content, re.IGNORECASE)
    if fi:
        forum_id = fi.group(1)

    page = 1
    pm = re.search(r'OPTION SELECTED VALUE="(\d+)"', content)
    if pm:
        page = int(pm.group(1))

    date_splits = re.split(
        r'(Enviado\s+em(?:&nbsp;|\s)+\d{1,2}/\d{1,2}/\d{4}(?:&nbsp;|\s)+\S+\s+\d{1,2}:\d{2}:\d{2})',
        content, flags=re.IGNORECASE
    )

    for i in range(1, len(date_splits) - 1, 2):
        post = {}
        date_text = date_splits[i]
        post_area = date_splits[i + 1] if i + 1 < len(date_splits) else ''
        pre_area = date_splits[i - 1] if i - 1 >= 0 else ''

        dm = re.search(r'(\d{1,2}/\d{1,2}/\d{4})(?:&nbsp;|\s)+\S+\s+(\d{1,2}:\d{2}:\d{2})', date_text)
        if dm:
            post['date_raw'] = f"{dm.group(1)} {dm.group(2)}"
            try:
                from datetime import datetime
                dt = datetime.strptime(post['date_raw'], '%d/%m/%Y %H:%M:%S')
                post['date'] = dt.strftime('%Y-%m-%d %H:%M')
            except Exception:
                post['date'] = post['date_raw']

        authors = re.findall(r'pop_profile\.asp\?mode=display&(?:amp;)?id=(\d+)[^>]*>\s*(?:<[^>]*>)*\s*([^<]+)', pre_area, re.IGNORECASE)
        if authors:
            post['author_id'] = authors[-1][0]
            post['author'] = authors[-1][1].strip()

        anchor = re.search(r'<a\s+name="(\d+)"', pre_area + date_text)
        if anchor:
            post['post_id'] = anchor.group(1)

        cm = re.search(r'<hr[^>]*>\s*(.*?)(?:<a\s+href="#top"|</table>)', post_area, re.DOTALL | re.IGNORECASE)
        if cm:
            post['content_text'] = html_to_text(cm.group(1))

        post['topic_title'] = topic_title
        post['topic_id'] = topic_id
        post['forum_name'] = forum_name
        post['forum_id'] = forum_id
        post['page'] = page
        post['source'] = 'sobresites.com.br'

        if post.get('content_text') or post.get('author'):
            posts.append(post)

    return posts


def extract_reply_metadata(content, filepath):
    """Extrai metadados de paginas Reply/ReplyQuote."""
    meta = {}

    tid = re.search(r'name="TOPIC_ID"[^>]*value="(\d+)"', content, re.IGNORECASE)
    if tid:
        meta['topic_id'] = tid.group(1)
    fid = re.search(r'name="FORUM_ID"[^>]*value="(\d+)"', content, re.IGNORECASE)
    if fid:
        meta['forum_id'] = fid.group(1)
    tt = re.search(r'name="Topic_Title"[^>]*value="([^"]*)"', content, re.IGNORECASE)
    if tt:
        meta['topic_title'] = html_to_text(tt.group(1))
    ft = re.search(r'name="FORUM_Title"[^>]*value="([^"]*)"', content, re.IGNORECASE)
    if ft:
        meta['forum_name'] = html_to_text(ft.group(1))

    if not meta.get('topic_id'):
        t2 = re.search(r'TOPIC_ID=(\d+)', content, re.IGNORECASE)
        if t2:
            meta['topic_id'] = t2.group(1)
    if not meta.get('topic_title'):
        bc = re.search(r'topic\.asp\?TOPIC_ID=\d+[^>]*>([^<]+)', content, re.IGNORECASE)
        if bc:
            meta['topic_title'] = html_to_text(bc.group(1))

    # Texto quotado na textarea
    ta = re.search(r'<textarea[^>]*name="Message"[^>]*>(.*?)</textarea>', content, re.DOTALL | re.IGNORECASE)
    if ta and ta.group(1).strip():
        text = re.sub(r'\[/?quote[^\]]*\]', '', ta.group(1), flags=re.IGNORECASE).strip()
        if text:
            meta['quoted_text'] = text

    return meta


# ============================================================
# DATABASE
# ============================================================

def create_db(db_path):
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY,
            filepath TEXT UNIQUE,
            filename TEXT,
            file_hash TEXT,
            source TEXT,
            page_type TEXT,
            topic_id TEXT,
            topic_title TEXT,
            forum_id TEXT,
            forum_name TEXT,
            page_num INTEGER DEFAULT 1,
            post_count INTEGER DEFAULT 0,
            indexed_at REAL
        );

        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY,
            file_id INTEGER,
            post_id TEXT,
            author TEXT,
            author_id TEXT,
            date TEXT,
            date_raw TEXT,
            content_text TEXT,
            topic_id TEXT,
            topic_title TEXT,
            forum_id TEXT,
            forum_name TEXT,
            page_num INTEGER,
            source TEXT,
            FOREIGN KEY (file_id) REFERENCES files(id)
        );

        CREATE TABLE IF NOT EXISTS forums (
            id INTEGER PRIMARY KEY,
            forum_id TEXT,
            name TEXT,
            source TEXT,
            UNIQUE(forum_id, source)
        );

        CREATE TABLE IF NOT EXISTS topics (
            id INTEGER PRIMARY KEY,
            topic_id TEXT,
            title TEXT,
            forum_id TEXT,
            forum_name TEXT,
            source TEXT,
            UNIQUE(topic_id, source)
        );

        CREATE INDEX IF NOT EXISTS idx_posts_topic ON posts(topic_id, source);
        CREATE INDEX IF NOT EXISTS idx_posts_forum ON posts(forum_id, source);
        CREATE INDEX IF NOT EXISTS idx_posts_author ON posts(author);
        CREATE INDEX IF NOT EXISTS idx_posts_post_id ON posts(post_id, source);
        CREATE INDEX IF NOT EXISTS idx_files_filepath ON files(filepath);
    """)

    conn.commit()
    return conn


def file_already_indexed(conn, filepath, fhash):
    row = conn.execute(
        "SELECT file_hash FROM files WHERE filepath = ?", (filepath,)
    ).fetchone()
    return row and row[0] == fhash


def index_file(conn, filepath, content, source, page_type):
    fhash = file_hash(filepath)

    if file_already_indexed(conn, filepath, fhash):
        return 0  # Ja indexado, sem mudancas

    # Remover indexacao anterior se o arquivo mudou
    old = conn.execute("SELECT id FROM files WHERE filepath = ?", (filepath,)).fetchone()
    if old:
        old_id = old[0]
        conn.execute("DELETE FROM posts WHERE file_id = ?", (old_id,))
        conn.execute("DELETE FROM files WHERE id = ?", (old_id,))

    posts = []
    topic_id = ''
    topic_title = ''
    forum_id = ''
    forum_name = ''
    page_num = 1

    if page_type == 'topic':
        if source == 'sobresites.com':
            posts = extract_posts_phpbb(content, filepath)
        else:
            posts = extract_posts_asp(content, filepath)

        if posts:
            topic_id = posts[0].get('topic_id', '')
            topic_title = posts[0].get('topic_title', '')
            forum_id = posts[0].get('forum_id', '')
            forum_name = posts[0].get('forum_name', '')
            page_num = posts[0].get('page', 1)

    elif page_type == 'post_reply':
        meta = extract_reply_metadata(content, filepath)
        topic_id = meta.get('topic_id', '')
        topic_title = meta.get('topic_title', '')
        forum_id = meta.get('forum_id', '')
        forum_name = meta.get('forum_name', '')

        if source == 'sobresites.com':
            posts = extract_posts_phpbb(content, filepath)
        else:
            posts = extract_posts_asp(content, filepath)

        if meta.get('quoted_text'):
            posts.append({
                'post_id': '',
                'author': '',
                'date': '',
                'content_text': meta['quoted_text'],
                'topic_id': topic_id,
                'topic_title': topic_title,
                'forum_id': forum_id,
                'forum_name': forum_name,
                'page': 0,
                'source': source,
            })

    elif page_type == 'forum_list':
        # Extrair topicos listados
        if source == 'sobresites.com':
            topic_links = re.findall(r'viewtopic\.php\?t=(\d+)[^>]*class="topictitle"[^>]*>([^<]+)', content, re.IGNORECASE)
            if not topic_links:
                topic_links = re.findall(r'viewtopic\.php\?t=(\d+)[^>]*>([^<]+)', content, re.IGNORECASE)
            fid_match = re.search(r'viewforum\.php\?f=(\d+)', filepath, re.IGNORECASE)
            if fid_match:
                forum_id = fid_match.group(1)
        else:
            topic_links = re.findall(r'topic\.asp\?TOPIC_ID=(\d+)[^>]*>\s*(?:<[^>]*>)*\s*([^<]+)', content, re.IGNORECASE)
            fid_match = re.search(r'FORUM_ID=(\d+)', filepath, re.IGNORECASE)
            if fid_match:
                forum_id = fid_match.group(1)

        for t_id, t_title in topic_links:
            t_title = html_to_text(t_title).strip()
            if t_title:
                try:
                    conn.execute(
                        "INSERT OR IGNORE INTO topics (topic_id, title, forum_id, forum_name, source) VALUES (?,?,?,?,?)",
                        (t_id, t_title, forum_id, '', source)
                    )
                except sqlite3.IntegrityError:
                    pass

    # Inserir arquivo
    cur = conn.execute(
        """INSERT INTO files (filepath, filename, file_hash, source, page_type,
           topic_id, topic_title, forum_id, forum_name, page_num, post_count, indexed_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (filepath, os.path.basename(filepath), fhash, source, page_type,
         topic_id, topic_title, forum_id, forum_name, page_num, len(posts), time.time())
    )
    file_id = cur.lastrowid

    # Inserir posts
    seen_pids = set()
    for p in posts:
        pid = p.get('post_id', '')
        if pid:
            pk = (source, pid)
            if pk in seen_pids:
                continue
            seen_pids.add(pk)

        conn.execute(
            """INSERT INTO posts (file_id, post_id, author, author_id, date, date_raw,
               content_text, topic_id, topic_title, forum_id, forum_name, page_num, source)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (file_id, pid, p.get('author', ''), p.get('author_id', ''),
             p.get('date', ''), p.get('date_raw', ''),
             p.get('content_text', ''),
             p.get('topic_id', ''), p.get('topic_title', ''),
             p.get('forum_id', ''), p.get('forum_name', ''),
             p.get('page', 1), source)
        )

    # Registrar forum e topico
    if forum_id:
        try:
            conn.execute(
                "INSERT OR IGNORE INTO forums (forum_id, name, source) VALUES (?,?,?)",
                (forum_id, forum_name, source)
            )
        except sqlite3.IntegrityError:
            pass

    if topic_id:
        try:
            conn.execute(
                "INSERT OR IGNORE INTO topics (topic_id, title, forum_id, forum_name, source) VALUES (?,?,?,?,?)",
                (topic_id, topic_title, forum_id, forum_name, source)
            )
        except sqlite3.IntegrityError:
            pass

    return len(posts)


def rebuild_fts(conn):
    """Reconstroi o indice FTS5 a partir da tabela posts."""
    print("  Reconstruindo indice de busca full-text...")
    try:
        # Dropar e recriar para evitar inconsistencias
        conn.execute("DROP TABLE IF EXISTS posts_fts")
        conn.execute("""
            CREATE VIRTUAL TABLE posts_fts USING fts5(
                content_text,
                author,
                topic_title,
                content='posts',
                content_rowid='id',
                tokenize='unicode61'
            )
        """)
        conn.execute("""
            INSERT INTO posts_fts(rowid, content_text, author, topic_title)
            SELECT id, COALESCE(content_text, ''), COALESCE(author, ''), COALESCE(topic_title, '')
            FROM posts
            WHERE content_text IS NOT NULL AND content_text != ''
        """)
        conn.commit()
        count = conn.execute("SELECT COUNT(*) FROM posts_fts").fetchone()[0]
        print(f"  Indice FTS reconstruido ({count} registros indexados).")
    except Exception as e:
        print(f"  AVISO: Erro ao criar FTS: {e}")
        print(f"  A busca por texto nao estara disponivel.")


# ============================================================
# MAIN
# ============================================================

def run_indexer(html_dir, db_path):
    print(f"\n{'='*60}")
    print(f"  SobreSites Archive Indexer")
    print(f"{'='*60}")
    print(f"  Pasta HTML:  {html_dir}")
    print(f"  Banco SQLite: {db_path}")
    print(f"  Escaneando arquivos...\n")

    # Coletar todos os arquivos
    all_files = []
    for dirpath, dirnames, filenames in os.walk(html_dir):
        dirnames[:] = [d for d in dirnames if d != '_lixo' and not d.startswith('.')]
        for f in filenames:
            fp = os.path.join(dirpath, f)
            if os.path.isfile(fp):
                all_files.append(fp)

    print(f"  Arquivos encontrados: {len(all_files)}")

    conn = create_db(db_path)

    total_posts = 0
    indexed = 0
    skipped = 0
    errors = 0
    start_time = time.time()

    # Extensoes a ignorar
    skip_ext = {'.gif', '.jpg', '.jpeg', '.png', '.css', '.js', '.ico', '.svg',
                '.pdf', '.zip', '.rar', '.mp3', '.swf', '.ttf', '.woff'}

    for i, fp in enumerate(sorted(all_files)):
        _, ext = os.path.splitext(fp.lower())
        if ext in skip_ext:
            skipped += 1
            continue

        try:
            content = read_file(fp)
            source = detect_source(fp, content)
            ptype = detect_page_type(fp, content)

            if ptype == 'junk':
                skipped += 1
                continue

            n = index_file(conn, fp, content, source, ptype)
            total_posts += n
            indexed += 1

            if (i + 1) % 200 == 0:
                conn.commit()
                elapsed = time.time() - start_time
                rate = (i + 1) / elapsed if elapsed > 0 else 0
                print(f"  [{i+1}/{len(all_files)}] {indexed} indexados, "
                      f"{total_posts} posts, {rate:.0f} arq/s")

        except Exception as e:
            errors += 1
            if errors <= 10:
                print(f"  ERRO: {os.path.basename(fp)}: {e}")

    conn.commit()

    # Reconstruir FTS
    rebuild_fts(conn)

    # Stats
    elapsed = time.time() - start_time
    post_total = conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
    file_total = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
    forum_total = conn.execute("SELECT COUNT(*) FROM forums").fetchone()[0]
    topic_total = conn.execute("SELECT COUNT(*) FROM topics").fetchone()[0]

    print(f"\n{'='*60}")
    print(f"  INDEXACAO COMPLETA ({elapsed:.1f}s)")
    print(f"{'='*60}")
    print(f"  Arquivos indexados:  {file_total}")
    print(f"  Arquivos ignorados:  {skipped}")
    print(f"  Erros:               {errors}")
    print(f"  Posts no banco:      {post_total}")
    print(f"  Forums catalogados:  {forum_total}")
    print(f"  Topicos catalogados: {topic_total}")
    print(f"  Banco: {db_path} ({os.path.getsize(db_path) / (1024*1024):.1f}MB)")
    print(f"{'='*60}\n")

    conn.close()


def get_params():
    if len(sys.argv) >= 3:
        return sys.argv[1].strip('"').strip("'"), sys.argv[2].strip('"').strip("'")

    print()
    print("=" * 60)
    print("  SobreSites Archive Indexer")
    print("=" * 60)
    print()
    html_dir = input("  Pasta com os HTMLs: ").strip().strip('"').strip("'")
    db_path = input("  Caminho do banco SQLite (ex: archive.db): ").strip().strip('"').strip("'")
    if not db_path:
        db_path = os.path.join(os.path.dirname(html_dir), 'archive.db')
    return html_dir, db_path


if __name__ == '__main__':
    html_dir, db_path = get_params()
    if not html_dir or not os.path.isdir(html_dir):
        print(f"  ERRO: Pasta nao encontrada: {html_dir}")
    else:
        run_indexer(html_dir, db_path)
    print()
    input("  Pressione ENTER para sair...")
