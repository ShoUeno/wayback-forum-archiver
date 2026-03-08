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
