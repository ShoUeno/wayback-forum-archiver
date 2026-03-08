# 🏛️ Wayback Forum Archiver

**Toolkit para extrair, limpar e navegar conteúdo de fóruns antigos salvos pelo Wayback Machine.**

Transforma páginas HTML brutas do [Wayback Machine](https://web.archive.org/) em dados estruturados navegáveis — preservando posts, usuários, metadados e o conteúdo original de fóruns que já não existem mais.

Desenvolvido originalmente para preservar o acervo dos fóruns de anime do [SobreSites](http://web.archive.org/web/*/www.sobresites.com/anime/forum/*) (~2001-2006), mas a arquitetura é adaptável a outros fóruns ASP e phpBB da mesma era.

---

## O problema

O Wayback Machine salva páginas da web, mas de uma forma que dificulta a navegação:

- Nomes de arquivo são URLs codificadas (`viewtopic.php%3ft%3d1377%26amp%3bsid%3dabc123`)
- Muitas páginas são erros HTTP (429, 502) ou páginas do fórum sem conteúdo ("Usuário não existe", formulários de login, etc.)
- Conteúdo de fontes diferentes pode ter arquivos com o mesmo nome
- Os HTMLs brutos não são facilmente pesquisáveis
- Páginas ficam espalhadas em subpastas que replicam a estrutura de URLs do site original

Este toolkit resolve cada um desses problemas com um pipeline de 5 etapas.

## Pipeline

```
Wayback Machine HTMLs
        │
        ▼
  ┌─────────────┐
  │  renamer.py  │  Renomeia arquivos URL-encoded para nomes legíveis
  └──────┬──────┘  topic.asp%3fTOPIC_ID%3d79  →  asp_topic_79_p2.html
         │
         ▼
  ┌──────────────┐
  │ dedup_names  │  Resolve colisão de nomes entre fontes diferentes
  └──────┬───────┘  phpbb_topic_100.html  →  phpbb_topic_100_combr.html
         │
         ▼
  ┌─────────────┐
  │ cleaner.py  │  Move páginas sem conteúdo para _lixo/
  └──────┬──────┘  Erros HTTP, "Usuário não existe", formulários, etc.
         │
         ▼
  ┌───────────────┐
  │ extractor.py  │  Extrai dados estruturados → JSONs divididos
  └──────┬────────┘  Posts, usuários, fóruns, tópicos, metadados
         │
         ▼
  ┌────────────────────────┐
  │ indexer.py + server.py │  Frontend web com busca full-text
  └────────────────────────┘  Navegação por fórum/tópico/autor
```

## Funcionalidades

### renamer.py
- Decodifica nomes URL-encoded do Wayback Machine
- Gera nomes descritivos (`asp_topic_79_p2.html`, `phpbb_profile_42_viewprofile.html`)
- Busca recursiva em subpastas
- Ignora arquivos com extensão real (`.gif`, `.css`, `.js`, etc.)
- Idempotente — rodar novamente não reprocessa arquivos já renomeados
- Pede confirmação antes de executar

### dedup_names.py
- Compara duas pastas de fontes diferentes
- Adiciona sufixo configurável (`_combr`) aos arquivos com nomes duplicados
- Busca recursiva
- Não altera a pasta de referência

### cleaner.py
- Detecta páginas sem conteúdo útil por análise de conteúdo (não apenas por nome)
- Identifica erros HTTP (429, 502, 503, 404), erros do phpBB ("Usuário não existe", "Tópico não existe", etc.), páginas funcionais (login, registro, recuperação de senha, "quem está online")
- Move para subpasta `_lixo/` em vez de deletar (double-check seguro)
- Ignora arquivos com extensão real
- Busca recursiva, ignora `_lixo/` em execuções subsequentes

### extractor.py
- Dois parsers independentes: fórum ASP customizado e phpBB 2.x
- Deduplicação robusta em duas camadas: chave primária `(source, post_id)` + fallback por hash de conteúdo
- Detecta posts editados — mantém a versão com mais conteúdo
- Extrai conteúdo quotado de formulários Reply/ReplyQuote (pode ser a única cópia sobrevivente de um post)
- Escrita incremental em chunks de ~10MB (suporta volumes grandes sem estourar memória)
- Detecta tipo de página por nome de arquivo, caminho de diretório ou conteúdo HTML
- Indexação incremental
- Extrai: post_id, topic_id, página, fórum, autor, data, texto, assinatura, localização, e-mail, ICQ

### web/ (indexer.py + server.py)
- **indexer.py**: Cria banco SQLite com FTS5 (Full-Text Search) a partir dos HTMLs
- **server.py**: Frontend Flask com navegação por fórum → tópico → posts, busca full-text, visualização do HTML original, ranking de autores
- Indexação incremental — só processa arquivos novos/modificados
- Suporta volumes grandes (testado com 3.5GB+ de HTML)

## Plataformas suportadas

- **Fórum ASP customizado** (ex: Snitz Forums 2000) — `topic.asp`, `forum.asp`, `pop_profile.asp`, `members.asp`, `post.asp`
- **phpBB 2.x** — `viewtopic.php`, `viewforum.php`, `profile.php`, `posting.php`, `groupcp.php`

## Instalação

```bash
git clone https://github.com/SEU_USUARIO/wayback-forum-archiver.git
cd wayback-forum-archiver

# Para o extrator (sem dependências externas)
python renamer.py

# Para o frontend web
pip install flask
python web/indexer.py
python web/server.py
```

**Requisitos**: Python 3.7+ — nenhuma dependência externa exceto Flask para o frontend.

## Uso rápido

```bash
# 1. Renomear arquivos do Wayback Machine
python renamer.py "C:\caminho\para\htmls"

# 2. (Opcional) Resolver nomes duplicados entre fontes
python dedup_names.py "pasta_fonte1" "pasta_fonte2" "combr"

# 3. Limpar páginas sem conteúdo
python cleaner.py "C:\caminho\para\htmls"

# 4. Extrair dados estruturados
python extractor.py "C:\caminho\para\htmls" "C:\saida"

# 5. Indexar e navegar no browser
python web/indexer.py "C:\caminho\para\htmls" "archive.db"
python web/server.py "C:\caminho\para\htmls" "archive.db"
# Abra http://localhost:5000
```

Todos os scripts funcionam de forma interativa (pedem os caminhos) ou por argumentos de linha de comando.

## Estrutura do projeto

```
wayback-forum-archiver/
├── README.md
├── renamer.py          # Renomeia arquivos URL-encoded → nomes legíveis
├── dedup_names.py      # Resolve colisão de nomes entre fontes
├── cleaner.py          # Remove/move páginas sem conteúdo
├── extractor.py        # Extrai dados estruturados → JSON
└── web/
    ├── indexer.py       # Indexa HTMLs → SQLite com FTS5
    └── server.py        # Frontend Flask para navegação e busca
```

## Dados extraídos

### Por post
| Campo | Descrição |
|-------|-----------|
| `post_id` | ID único do post na plataforma |
| `topic_id` | ID do tópico |
| `page` | Número da página no tópico |
| `author` | Nome do autor |
| `date` | Data em formato ISO |
| `content_text` | Texto do post (limpo) |
| `content_html` | HTML original do post |
| `forum_name` / `forum_id` | Fórum de origem |
| `source` | Plataforma de origem |
| `signature` | Assinatura do autor |

### Por usuário
| Campo | Descrição |
|-------|-----------|
| `username` | Nome de exibição |
| `email` | E-mail (decodificado do CloudFlare quando necessário) |
| `location` | Localização informada |
| `member_since` | Data de registro |
| `icq` / `homepage` | Contatos da época |
| `sources` | Em quais plataformas aparece |

## Adaptando para outros fóruns

O código foi escrito para o SobreSites, mas a estrutura é modular. Para adaptar a outro fórum:

1. **renamer.py**: Adicione regras de nomeação em `generate_clean_name()` para os padrões de URL do seu fórum
2. **cleaner.py**: Adicione mensagens de erro específicas em `PHPBB_ERROR_MESSAGES` ou crie uma nova lista
3. **extractor.py**: Crie uma nova classe parser (seguindo o padrão de `ASPForumParser` ou `PhpBBParser`) com regexes adaptados à estrutura HTML do fórum
4. **web/indexer.py**: Adicione a chamada ao novo parser em `index_file()`

Fóruns que devem funcionar com pouca ou nenhuma adaptação:
- phpBB 2.x e 3.x
- Snitz Forums 2000 (ASP)
- Outros fóruns ASP com estrutura similar

## Contexto

Este projeto nasceu da vontade de preservar o conteúdo de fóruns brasileiros de anime do início dos anos 2000 — uma era de ICQ, MSN Messenger, assinaturas com citações de anime, e comunidades que existiam antes das redes sociais. O Wayback Machine salvou as páginas, mas navegar por elas no estado bruto é praticamente impossível. Este toolkit torna esse acervo acessível novamente.

## Licença

MIT

---

---

# 🏛️ Wayback Forum Archiver

**A toolkit to extract, clean, and browse content from old forums archived by the Wayback Machine.**

Transforms raw HTML pages from the [Wayback Machine](https://web.archive.org/) into structured, navigable data — preserving posts, users, metadata, and original content from forums that no longer exist.

Originally developed to preserve the anime forum archives from [SobreSites](http://web.archive.org/web/*/www.sobresites.com/anime/forum/*) (~2001-2006), but the architecture is adaptable to other ASP and phpBB forums from the same era.

---

## The Problem

The Wayback Machine saves web pages, but in a way that makes navigation difficult:

- Filenames are URL-encoded (`viewtopic.php%3ft%3d1377%26amp%3bsid%3dabc123`)
- Many pages are HTTP errors (429, 502) or empty forum pages ("User does not exist", login forms, etc.)
- Content from different sources may share the same filename
- Raw HTML files are not easily searchable
- Pages are scattered across subfolders that mirror the original site's URL structure

This toolkit solves each of these problems with a 5-step pipeline.

## Pipeline

```
Wayback Machine HTMLs
        │
        ▼
  ┌─────────────┐
  │  renamer.py  │  Renames URL-encoded files to human-readable names
  └──────┬──────┘  topic.asp%3fTOPIC_ID%3d79  →  asp_topic_79_p2.html
         │
         ▼
  ┌──────────────┐
  │ dedup_names  │  Resolves name collisions between different sources
  └──────┬───────┘  phpbb_topic_100.html  →  phpbb_topic_100_combr.html
         │
         ▼
  ┌─────────────┐
  │ cleaner.py  │  Moves empty pages to _trash/
  └──────┬──────┘  HTTP errors, "User does not exist", forms, etc.
         │
         ▼
  ┌───────────────┐
  │ extractor.py  │  Extracts structured data → split JSONs
  └──────┬────────┘  Posts, users, forums, topics, metadata
         │
         ▼
  ┌────────────────────────┐
  │ indexer.py + server.py │  Web frontend with full-text search
  └────────────────────────┘  Browse by forum / topic / author
```

## Features

### renamer.py
- Decodes URL-encoded filenames from the Wayback Machine
- Generates descriptive names (`asp_topic_79_p2.html`, `phpbb_profile_42_viewprofile.html`)
- Recursive subfolder search
- Ignores files with real extensions (`.gif`, `.css`, `.js`, etc.)
- Idempotent — re-running does not reprocess already-renamed files
- Asks for confirmation before executing

### dedup_names.py
- Compares two folders from different sources
- Adds a configurable suffix (`_combr`) to files with duplicate names
- Recursive search
- Does not modify the reference folder

### cleaner.py
- Detects pages without useful content by analyzing page content (not just filenames)
- Identifies HTTP errors (429, 502, 503, 404), phpBB errors ("User does not exist", "Topic does not exist", etc.), and functional pages (login, registration, password recovery, "who is online")
- Moves to a `_trash/` subfolder instead of deleting (safe for double-checking)
- Ignores files with real extensions
- Recursive search, ignores `_trash/` on subsequent runs

### extractor.py
- Two independent parsers: custom ASP forum and phpBB 2.x
- Robust two-layer deduplication: primary key `(source, post_id)` + content hash fallback
- Detects edited posts — keeps the version with more content
- Extracts quoted content from Reply/ReplyQuote forms (may be the only surviving copy of a post)
- Incremental writing in ~10MB chunks (handles large volumes without running out of memory)
- Detects page type by filename, directory path, or HTML content
- Incremental indexing
- Extracts: post_id, topic_id, page, forum, author, date, text, signature, location, email, ICQ

### web/ (indexer.py + server.py)
- **indexer.py**: Creates a SQLite database with FTS5 (Full-Text Search) from the HTML files
- **server.py**: Flask frontend with forum → topic → posts navigation, full-text search, original HTML viewer, author rankings
- Incremental indexing — only processes new/modified files
- Supports large volumes (tested with 3.5GB+ of HTML)

## Supported Platforms

- **Custom ASP forum** (e.g. Snitz Forums 2000) — `topic.asp`, `forum.asp`, `pop_profile.asp`, `members.asp`, `post.asp`
- **phpBB 2.x** — `viewtopic.php`, `viewforum.php`, `profile.php`, `posting.php`, `groupcp.php`

## Installation

```bash
git clone https://github.com/YOUR_USERNAME/wayback-forum-archiver.git
cd wayback-forum-archiver

# For the extractor (no external dependencies)
python renamer.py

# For the web frontend
pip install flask
python web/indexer.py
python web/server.py
```

**Requirements**: Python 3.7+ — no external dependencies except Flask for the frontend.

## Quick Start

```bash
# 1. Rename Wayback Machine files
python renamer.py "/path/to/htmls"

# 2. (Optional) Resolve duplicate names between sources
python dedup_names.py "source_folder1" "source_folder2" "combr"

# 3. Clean pages without content
python cleaner.py "/path/to/htmls"

# 4. Extract structured data
python extractor.py "/path/to/htmls" "/output"

# 5. Index and browse in the browser
python web/indexer.py "/path/to/htmls" "archive.db"
python web/server.py "/path/to/htmls" "archive.db"
# Open http://localhost:5000
```

All scripts work interactively (prompting for paths) or via command-line arguments.

## Project Structure

```
wayback-forum-archiver/
├── README.md
├── renamer.py          # Renames URL-encoded files → readable names
├── dedup_names.py      # Resolves name collisions between sources
├── cleaner.py          # Removes/moves pages without content
├── extractor.py        # Extracts structured data → JSON
└── web/
    ├── indexer.py       # Indexes HTMLs → SQLite with FTS5
    └── server.py        # Flask frontend for browsing and search
```

## Extracted Data

### Per post
| Field | Description |
|-------|-------------|
| `post_id` | Unique post ID on the platform |
| `topic_id` | Topic ID |
| `page` | Page number within the topic |
| `author` | Author's username |
| `date` | Date in ISO format |
| `content_text` | Post text (cleaned) |
| `content_html` | Original post HTML |
| `forum_name` / `forum_id` | Source forum |
| `source` | Source platform |
| `signature` | Author's signature |

### Per user
| Field | Description |
|-------|-------------|
| `username` | Display name |
| `email` | Email (CloudFlare-decoded when necessary) |
| `location` | User-provided location |
| `member_since` | Registration date |
| `icq` / `homepage` | Period-era contact info |
| `sources` | Which platforms the user appears on |

## Adapting to Other Forums

The code was written for SobreSites, but the structure is modular. To adapt to another forum:

1. **renamer.py**: Add naming rules in `generate_clean_name()` for your forum's URL patterns
2. **cleaner.py**: Add platform-specific error messages to `PHPBB_ERROR_MESSAGES` or create a new list
3. **extractor.py**: Create a new parser class (following the `ASPForumParser` or `PhpBBParser` pattern) with regexes adapted to your forum's HTML structure
4. **web/indexer.py**: Add the call to your new parser in `index_file()`

Forums that should work with little or no adaptation:
- phpBB 2.x and 3.x
- Snitz Forums 2000 (ASP)
- Other ASP forums with a similar structure

## Background

This project was born from the desire to preserve content from early 2000s Brazilian anime forums — an era of ICQ, MSN Messenger, anime quote signatures, and communities that existed before social media. The Wayback Machine saved the pages, but navigating them in their raw state is practically impossible. This toolkit makes that archive accessible again.

## License

MIT