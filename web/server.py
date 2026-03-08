#!/usr/bin/env python3
"""
SobreSites Archive Browser
=============================
Servidor web local para navegar o acervo do forum SobreSites.

Uso:
  python server.py "C:\\...\\forum" "C:\\...\\archive.db"
  python server.py   (interativo)

Abra http://localhost:5000 no navegador.
"""

import os
import sys
import sqlite3
from flask import Flask, render_template_string, request, send_file, abort, g

app = Flask(__name__)

# Configuração global
HTML_DIR = ''
DB_PATH = ''


def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exception):
    db = g.pop('db', None)
    if db:
        db.close()


# ============================================================
# TEMPLATE BASE
# ============================================================

BASE_TEMPLATE = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ title }} - SobreSites Archive</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&family=Noto+Sans:wght@400;600;700&display=swap');

  * { margin: 0; padding: 0; box-sizing: border-box; }

  :root {
    --bg: #0d1117;
    --surface: #161b22;
    --surface2: #1c2333;
    --border: #30363d;
    --text: #e6edf3;
    --text2: #8b949e;
    --accent: #58a6ff;
    --accent2: #3fb950;
    --accent3: #d29922;
    --danger: #f85149;
    --mono: 'JetBrains Mono', monospace;
    --sans: 'Noto Sans', sans-serif;
  }

  body {
    font-family: var(--sans);
    background: var(--bg);
    color: var(--text);
    line-height: 1.6;
  }

  a { color: var(--accent); text-decoration: none; }
  a:hover { text-decoration: underline; }

  .container { max-width: 1100px; margin: 0 auto; padding: 0 20px; }

  /* Header */
  header {
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    padding: 16px 0;
    position: sticky;
    top: 0;
    z-index: 100;
  }
  header .inner {
    display: flex;
    align-items: center;
    gap: 24px;
    max-width: 1100px;
    margin: 0 auto;
    padding: 0 20px;
  }
  header h1 {
    font-size: 18px;
    font-weight: 700;
    white-space: nowrap;
  }
  header h1 a { color: var(--text); }
  header h1 span { color: var(--accent); }
  header nav { display: flex; gap: 16px; font-size: 14px; }
  header nav a { color: var(--text2); }
  header nav a:hover, header nav a.active { color: var(--accent); }

  .search-box {
    margin-left: auto;
    position: relative;
  }
  .search-box input {
    background: var(--bg);
    border: 1px solid var(--border);
    color: var(--text);
    padding: 6px 12px;
    border-radius: 6px;
    font-size: 14px;
    width: 260px;
    font-family: var(--sans);
  }
  .search-box input:focus {
    outline: none;
    border-color: var(--accent);
  }

  /* Breadcrumb */
  .breadcrumb {
    padding: 12px 0;
    font-size: 13px;
    color: var(--text2);
  }
  .breadcrumb a { color: var(--text2); }
  .breadcrumb a:hover { color: var(--accent); }
  .breadcrumb span { margin: 0 6px; }

  /* Content */
  main { padding: 20px 0 60px; }

  h2 { font-size: 22px; margin-bottom: 16px; font-weight: 700; }

  /* Cards / Lists */
  .card-list { display: flex; flex-direction: column; gap: 2px; }
  .card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 14px 18px;
    display: flex;
    align-items: center;
    gap: 14px;
    transition: border-color 0.15s;
  }
  .card:hover { border-color: var(--accent); }
  .card .icon {
    width: 36px; height: 36px;
    background: var(--surface2);
    border-radius: 8px;
    display: flex; align-items: center; justify-content: center;
    font-size: 16px;
    flex-shrink: 0;
  }
  .card .info { flex: 1; min-width: 0; }
  .card .info .name { font-weight: 600; font-size: 15px; }
  .card .info .meta { font-size: 12px; color: var(--text2); margin-top: 2px; }
  .card .badge {
    background: var(--surface2);
    padding: 3px 10px;
    border-radius: 12px;
    font-size: 12px;
    color: var(--text2);
    font-family: var(--mono);
    white-space: nowrap;
  }

  /* Post display */
  .post {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 6px;
    margin-bottom: 8px;
    overflow: hidden;
  }
  .post-header {
    background: var(--surface2);
    padding: 10px 16px;
    display: flex;
    align-items: center;
    gap: 12px;
    font-size: 13px;
    border-bottom: 1px solid var(--border);
  }
  .post-author {
    font-weight: 700;
    color: var(--accent);
  }
  .post-date { color: var(--text2); margin-left: auto; font-family: var(--mono); font-size: 12px; }
  .post-id { color: var(--text2); font-family: var(--mono); font-size: 11px; }
  .post-body {
    padding: 14px 16px;
    font-size: 14px;
    line-height: 1.7;
    white-space: pre-wrap;
    word-break: break-word;
  }

  /* Iframe viewer */
  .viewer-frame {
    width: 100%;
    height: 80vh;
    border: 1px solid var(--border);
    border-radius: 6px;
    background: #fff;
  }

  /* Stats */
  .stats-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 12px;
    margin-bottom: 24px;
  }
  .stat-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 16px;
    text-align: center;
  }
  .stat-card .number {
    font-size: 28px;
    font-weight: 700;
    font-family: var(--mono);
    color: var(--accent);
  }
  .stat-card .label {
    font-size: 12px;
    color: var(--text2);
    margin-top: 4px;
  }

  /* Pagination */
  .pagination {
    display: flex;
    gap: 6px;
    margin-top: 16px;
    justify-content: center;
    flex-wrap: wrap;
  }
  .pagination a, .pagination span {
    padding: 6px 12px;
    border-radius: 6px;
    font-size: 13px;
    font-family: var(--mono);
  }
  .pagination a {
    background: var(--surface);
    border: 1px solid var(--border);
    color: var(--text2);
  }
  .pagination a:hover { border-color: var(--accent); color: var(--accent); text-decoration: none; }
  .pagination .current {
    background: var(--accent);
    color: var(--bg);
    font-weight: 700;
  }

  /* Search highlight */
  mark {
    background: rgba(210, 153, 34, 0.3);
    color: var(--accent3);
    padding: 1px 3px;
    border-radius: 3px;
  }

  .source-tag {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 11px;
    font-family: var(--mono);
    font-weight: 600;
  }
  .source-tag.com { background: #1a3a2a; color: var(--accent2); }
  .source-tag.combr { background: #3a2a1a; color: var(--accent3); }

  .empty-state {
    text-align: center;
    padding: 60px 20px;
    color: var(--text2);
  }
  .empty-state .big { font-size: 48px; margin-bottom: 12px; }
</style>
</head>
<body>
<header>
  <div class="inner">
    <h1><a href="/">Sobre<span>Sites</span> Archive</a></h1>
    <nav>
      <a href="/" class="{{ 'active' if active == 'home' else '' }}">Inicio</a>
      <a href="/forums" class="{{ 'active' if active == 'forums' else '' }}">Forums</a>
      <a href="/topics" class="{{ 'active' if active == 'topics' else '' }}">Topicos</a>
      <a href="/authors" class="{{ 'active' if active == 'authors' else '' }}">Autores</a>
    </nav>
    <div class="search-box">
      <form action="/search" method="get">
        <input type="text" name="q" placeholder="Buscar nos posts..." value="{{ query or '' }}">
      </form>
    </div>
  </div>
</header>
<div class="container">
  <main>
    {% block content %}{% endblock %}
  </main>
</div>
</body>
</html>
"""


# ============================================================
# ROUTES
# ============================================================

@app.route('/')
def home():
    db = get_db()
    stats = {
        'posts': db.execute("SELECT COUNT(*) FROM posts").fetchone()[0],
        'files': db.execute("SELECT COUNT(*) FROM files").fetchone()[0],
        'forums': db.execute("SELECT COUNT(*) FROM forums").fetchone()[0],
        'topics': db.execute("SELECT COUNT(*) FROM topics").fetchone()[0],
        'authors': db.execute("SELECT COUNT(DISTINCT author) FROM posts WHERE author != ''").fetchone()[0],
    }
    recent = db.execute("""
        SELECT DISTINCT topic_id, topic_title, forum_name, source,
               MAX(date) as last_date, COUNT(*) as post_count
        FROM posts WHERE topic_id != '' AND topic_title != ''
        GROUP BY topic_id, source
        ORDER BY last_date DESC LIMIT 20
    """).fetchall()

    return render_template_string(BASE_TEMPLATE + """
    {% block content %}
    <div class="stats-grid">
      <div class="stat-card"><div class="number">{{ stats.posts }}</div><div class="label">Posts</div></div>
      <div class="stat-card"><div class="number">{{ stats.topics }}</div><div class="label">Topicos</div></div>
      <div class="stat-card"><div class="number">{{ stats.forums }}</div><div class="label">Forums</div></div>
      <div class="stat-card"><div class="number">{{ stats.authors }}</div><div class="label">Autores</div></div>
      <div class="stat-card"><div class="number">{{ stats.files }}</div><div class="label">Arquivos HTML</div></div>
    </div>
    <h2>Topicos recentes</h2>
    <div class="card-list">
    {% for t in recent %}
      <a href="/topic/{{ t.source }}/{{ t.topic_id }}" class="card" style="text-decoration:none;color:inherit">
        <div class="icon">💬</div>
        <div class="info">
          <div class="name">{{ t.topic_title }}</div>
          <div class="meta">
            <span class="source-tag {{ 'com' if 'com.br' not in t.source else 'combr' }}">{{ t.source }}</span>
            {{ t.forum_name or '' }} · {{ t.last_date or '' }}
          </div>
        </div>
        <div class="badge">{{ t.post_count }} posts</div>
      </a>
    {% endfor %}
    </div>
    {% endblock %}
    """, title="Inicio", active="home", stats=stats, recent=recent, query='')


@app.route('/forums')
def forums():
    db = get_db()
    rows = db.execute("""
        SELECT f.forum_id, f.name, f.source,
               (SELECT COUNT(DISTINCT topic_id) FROM posts WHERE forum_id=f.forum_id AND source=f.source AND topic_id != '') as topic_count,
               (SELECT COUNT(*) FROM posts WHERE forum_id=f.forum_id AND source=f.source) as post_count
        FROM forums f ORDER BY f.name
    """).fetchall()

    return render_template_string(BASE_TEMPLATE + """
    {% block content %}
    <h2>Forums ({{ rows|length }})</h2>
    <div class="card-list">
    {% for f in rows %}
      <a href="/forum/{{ f.source }}/{{ f.forum_id }}" class="card" style="text-decoration:none;color:inherit">
        <div class="icon">📁</div>
        <div class="info">
          <div class="name">{{ f.name or 'Forum ' + f.forum_id }}</div>
          <div class="meta">
            <span class="source-tag {{ 'com' if 'com.br' not in f.source else 'combr' }}">{{ f.source }}</span>
            {{ f.topic_count }} topicos · {{ f.post_count }} posts
          </div>
        </div>
      </a>
    {% endfor %}
    </div>
    {% endblock %}
    """, title="Forums", active="forums", rows=rows, query='')


@app.route('/forum/<source>/<forum_id>')
def forum_detail(source, forum_id):
    db = get_db()
    forum = db.execute("SELECT * FROM forums WHERE forum_id=? AND source=?", (forum_id, source)).fetchone()
    topics = db.execute("""
        SELECT DISTINCT topic_id, topic_title, MAX(date) as last_date, COUNT(*) as post_count
        FROM posts WHERE forum_id=? AND source=? AND topic_id != ''
        GROUP BY topic_id ORDER BY last_date DESC
    """, (forum_id, source)).fetchall()

    forum_name = forum['name'] if forum else f'Forum {forum_id}'
    return render_template_string(BASE_TEMPLATE + """
    {% block content %}
    <div class="breadcrumb"><a href="/forums">Forums</a><span>›</span>{{ forum_name }}</div>
    <h2>{{ forum_name }} ({{ topics|length }} topicos)</h2>
    <div class="card-list">
    {% for t in topics %}
      <a href="/topic/{{ source }}/{{ t.topic_id }}" class="card" style="text-decoration:none;color:inherit">
        <div class="icon">💬</div>
        <div class="info">
          <div class="name">{{ t.topic_title or 'Topico ' + t.topic_id }}</div>
          <div class="meta">{{ t.last_date or '' }}</div>
        </div>
        <div class="badge">{{ t.post_count }}</div>
      </a>
    {% endfor %}
    </div>
    {% endblock %}
    """, title=forum_name, active="forums", forum_name=forum_name, topics=topics, source=source, query='')


@app.route('/topics')
def topics():
    db = get_db()
    page = int(request.args.get('page', 1))
    per_page = 50
    offset = (page - 1) * per_page

    total = db.execute("SELECT COUNT(*) FROM topics").fetchone()[0]
    rows = db.execute("""
        SELECT t.topic_id, t.title, t.forum_name, t.source,
               (SELECT COUNT(*) FROM posts p WHERE p.topic_id=t.topic_id AND p.source=t.source) as post_count
        FROM topics t ORDER BY t.title LIMIT ? OFFSET ?
    """, (per_page, offset)).fetchall()

    total_pages = (total + per_page - 1) // per_page
    return render_template_string(BASE_TEMPLATE + """
    {% block content %}
    <h2>Topicos ({{ total }})</h2>
    <div class="card-list">
    {% for t in rows %}
      <a href="/topic/{{ t.source }}/{{ t.topic_id }}" class="card" style="text-decoration:none;color:inherit">
        <div class="icon">💬</div>
        <div class="info">
          <div class="name">{{ t.title }}</div>
          <div class="meta">
            <span class="source-tag {{ 'com' if 'com.br' not in t.source else 'combr' }}">{{ t.source }}</span>
            {{ t.forum_name or '' }}
          </div>
        </div>
        <div class="badge">{{ t.post_count }}</div>
      </a>
    {% endfor %}
    </div>
    <div class="pagination">
    {% if page > 1 %}<a href="?page={{ page-1 }}">← Anterior</a>{% endif %}
    {% for p in range(1, total_pages+1) %}
      {% if p == page %}<span class="current">{{ p }}</span>
      {% elif p <= 3 or p >= total_pages-2 or (p >= page-2 and p <= page+2) %}<a href="?page={{ p }}">{{ p }}</a>
      {% elif p == 4 or p == total_pages-3 %}<span style="color:var(--text2)">...</span>{% endif %}
    {% endfor %}
    {% if page < total_pages %}<a href="?page={{ page+1 }}">Proximo →</a>{% endif %}
    </div>
    {% endblock %}
    """, title="Topicos", active="topics", rows=rows, page=page, total=total, total_pages=total_pages, query='')


@app.route('/topic/<source>/<topic_id>')
def topic_detail(source, topic_id):
    db = get_db()
    topic = db.execute("SELECT * FROM topics WHERE topic_id=? AND source=?", (topic_id, source)).fetchone()
    posts = db.execute("""
        SELECT * FROM posts WHERE topic_id=? AND source=?
        ORDER BY page_num, date, id
    """, (topic_id, source)).fetchall()

    # Agrupar por página
    pages = {}
    for p in posts:
        pg = p['page_num'] or 1
        if pg not in pages:
            pages[pg] = []
        pages[pg].append(p)

    # HTMLs originais disponíveis
    files = db.execute("""
        SELECT * FROM files WHERE topic_id=? AND source=? AND page_type='topic'
        ORDER BY page_num
    """, (topic_id, source)).fetchall()

    topic_title = topic['title'] if topic else f'Topico {topic_id}'
    forum_name = topic['forum_name'] if topic else ''
    forum_id = topic['forum_id'] if topic else ''

    return render_template_string(BASE_TEMPLATE + """
    {% block content %}
    <div class="breadcrumb">
      <a href="/forums">Forums</a><span>›</span>
      {% if forum_id %}<a href="/forum/{{ source }}/{{ forum_id }}">{{ forum_name or 'Forum' }}</a><span>›</span>{% endif %}
      {{ topic_title }}
    </div>
    <h2>{{ topic_title }}</h2>

    {% if files %}
    <details style="margin-bottom:16px">
      <summary style="cursor:pointer;color:var(--text2);font-size:13px">📄 Ver HTML original ({{ files|length }} pagina{{ 's' if files|length > 1 else '' }})</summary>
      <div style="margin-top:8px">
      {% for f in files %}
        <a href="/raw/{{ f.id }}" target="_blank" style="margin-right:12px;font-size:13px">Pagina {{ f.page_num }} ({{ f.filename }})</a>
      {% endfor %}
      </div>
    </details>
    {% endif %}

    {% for pg_num in pages|sort %}
    {% if pages|length > 1 %}
    <div style="color:var(--text2);font-size:12px;margin:16px 0 8px;font-family:var(--mono)">— Pagina {{ pg_num }} —</div>
    {% endif %}
    {% for p in pages[pg_num] %}
    <div class="post">
      <div class="post-header">
        {% if p.author %}<a href="/author/{{ p.author }}" class="post-author">{{ p.author }}</a>{% endif %}
        {% if p.post_id %}<span class="post-id">#{{ p.post_id }}</span>{% endif %}
        <span class="post-date">{{ p.date or p.date_raw or '' }}</span>
      </div>
      <div class="post-body">{{ p.content_text or '(sem conteudo)' }}</div>
    </div>
    {% endfor %}
    {% endfor %}

    {% if not posts %}
    <div class="empty-state">
      <div class="big">📭</div>
      Nenhum post extraido para este topico.
      {% if files %}
      <br><a href="/raw/{{ files[0].id }}">Ver HTML original</a>
      {% endif %}
    </div>
    {% endif %}
    {% endblock %}
    """, title=topic_title, active="topics", topic_title=topic_title,
         forum_name=forum_name, forum_id=forum_id, source=source,
         posts=posts, pages=pages, files=files, query='')


@app.route('/authors')
def authors():
    db = get_db()
    page = int(request.args.get('page', 1))
    per_page = 50
    offset = (page - 1) * per_page
    total = db.execute("SELECT COUNT(DISTINCT author) FROM posts WHERE author != ''").fetchone()[0]
    rows = db.execute("""
        SELECT author, COUNT(*) as post_count, MIN(date) as first_date, MAX(date) as last_date
        FROM posts WHERE author != ''
        GROUP BY author ORDER BY post_count DESC LIMIT ? OFFSET ?
    """, (per_page, offset)).fetchall()
    total_pages = (total + per_page - 1) // per_page

    return render_template_string(BASE_TEMPLATE + """
    {% block content %}
    <h2>Autores ({{ total }})</h2>
    <div class="card-list">
    {% for a in rows %}
      <a href="/author/{{ a.author }}" class="card" style="text-decoration:none;color:inherit">
        <div class="icon">👤</div>
        <div class="info">
          <div class="name">{{ a.author }}</div>
          <div class="meta">{{ a.first_date or '?' }} — {{ a.last_date or '?' }}</div>
        </div>
        <div class="badge">{{ a.post_count }} posts</div>
      </a>
    {% endfor %}
    </div>
    <div class="pagination">
    {% if page > 1 %}<a href="?page={{ page-1 }}">← Anterior</a>{% endif %}
    {% for p in range(1, min(total_pages+1, 20)) %}
      {% if p == page %}<span class="current">{{ p }}</span>
      {% else %}<a href="?page={{ p }}">{{ p }}</a>{% endif %}
    {% endfor %}
    {% if page < total_pages %}<a href="?page={{ page+1 }}">Proximo →</a>{% endif %}
    </div>
    {% endblock %}
    """, title="Autores", active="authors", rows=rows, page=page, total=total, total_pages=total_pages, query='')


@app.route('/author/<name>')
def author_detail(n):
    db = get_db()
    posts = db.execute("""
        SELECT * FROM posts WHERE author=? ORDER BY date DESC LIMIT 200
    """, (n,)).fetchall()

    return render_template_string(BASE_TEMPLATE + """
    {% block content %}
    <div class="breadcrumb"><a href="/authors">Autores</a><span>›</span>{{ n }}</div>
    <h2>{{ n }} ({{ posts|length }} posts)</h2>
    {% for p in posts %}
    <div class="post">
      <div class="post-header">
        <span class="post-author">{{ p.author }}</span>
        {% if p.topic_title %}<a href="/topic/{{ p.source }}/{{ p.topic_id }}" style="font-size:12px;color:var(--text2)">{{ p.topic_title }}</a>{% endif %}
        <span class="post-date">{{ p.date or '' }}</span>
      </div>
      <div class="post-body">{{ p.content_text[:500] }}{% if p.content_text|length > 500 %}...{% endif %}</div>
    </div>
    {% endfor %}
    {% endblock %}
    """, title=n, active="authors", n=n, posts=posts, query='')


@app.route('/search')
def search():
    q = request.args.get('q', '').strip()
    page = int(request.args.get('page', 1))
    per_page = 30
    offset = (page - 1) * per_page

    if not q:
        return render_template_string(BASE_TEMPLATE + """
        {% block content %}
        <div class="empty-state"><div class="big">🔍</div>Digite algo para buscar.</div>
        {% endblock %}
        """, title="Busca", active="", query=q)

    db = get_db()
    # FTS5 search
    total = db.execute(
        "SELECT COUNT(*) FROM posts_fts WHERE posts_fts MATCH ?", (q,)
    ).fetchone()[0]

    results = db.execute("""
        SELECT p.*, snippet(posts_fts, 0, '<mark>', '</mark>', '...', 40) as snippet
        FROM posts_fts
        JOIN posts p ON p.id = posts_fts.rowid
        WHERE posts_fts MATCH ?
        ORDER BY rank
        LIMIT ? OFFSET ?
    """, (q, per_page, offset)).fetchall()

    total_pages = (total + per_page - 1) // per_page

    return render_template_string(BASE_TEMPLATE + """
    {% block content %}
    <h2>Busca: "{{ query }}" ({{ total }} resultados)</h2>
    {% for r in results %}
    <div class="post">
      <div class="post-header">
        {% if r.author %}<a href="/author/{{ r.author }}" class="post-author">{{ r.author }}</a>{% endif %}
        {% if r.topic_title %}<a href="/topic/{{ r.source }}/{{ r.topic_id }}" style="font-size:12px;color:var(--text2)">{{ r.topic_title }}</a>{% endif %}
        <span class="source-tag {{ 'com' if 'com.br' not in r.source else 'combr' }}">{{ r.source }}</span>
        <span class="post-date">{{ r.date or '' }}</span>
      </div>
      <div class="post-body">{{ r.snippet|safe }}</div>
    </div>
    {% endfor %}
    {% if not results %}
    <div class="empty-state"><div class="big">😶</div>Nenhum resultado para "{{ query }}".</div>
    {% endif %}
    <div class="pagination">
    {% if page > 1 %}<a href="?q={{ query }}&page={{ page-1 }}">← Anterior</a>{% endif %}
    {% for p in range(1, min(total_pages+1, 20)) %}
      {% if p == page %}<span class="current">{{ p }}</span>
      {% else %}<a href="?q={{ query }}&page={{ p }}">{{ p }}</a>{% endif %}
    {% endfor %}
    {% if page < total_pages %}<a href="?q={{ query }}&page={{ page+1 }}">Proximo →</a>{% endif %}
    </div>
    {% endblock %}
    """, title=f"Busca: {q}", active="", results=results, total=total,
         page=page, total_pages=total_pages, query=q)


@app.route('/raw/<int:file_id>')
def raw_file(file_id):
    """Serve o HTML original para visualização."""
    db = get_db()
    row = db.execute("SELECT filepath FROM files WHERE id=?", (file_id,)).fetchone()
    if not row:
        abort(404)
    filepath = row['filepath']
    if not os.path.isfile(filepath):
        abort(404)
    return send_file(filepath, mimetype='text/html')


# ============================================================
# MAIN
# ============================================================

def get_params():
    if len(sys.argv) >= 3:
        return sys.argv[1].strip('"').strip("'"), sys.argv[2].strip('"').strip("'")

    print()
    print("=" * 60)
    print("  SobreSites Archive Browser")
    print("=" * 60)
    print()
    html_dir = input("  Pasta com os HTMLs: ").strip().strip('"').strip("'")
    db_path = input("  Caminho do banco SQLite: ").strip().strip('"').strip("'")
    return html_dir, db_path


if __name__ == '__main__':
    html_dir, db_path = get_params()

    if not os.path.isfile(db_path):
        print(f"\n  ERRO: Banco nao encontrado: {db_path}")
        print(f"  Execute primeiro: python indexer.py \"{html_dir}\" \"{db_path}\"")
        sys.exit(1)

    HTML_DIR = html_dir
    DB_PATH = db_path

    print(f"\n  Servidor iniciando...")
    print(f"  Abra no navegador: http://localhost:5000")
    print(f"  Pressione Ctrl+C para parar.\n")

    app.run(host='0.0.0.0', port=5000, debug=False)
