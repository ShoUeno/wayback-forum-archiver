# Wayback Forum Archiver

Toolkit para transformar HTMLs antigos do Wayback Machine em um dataset auditável de fóruns históricos, com foco em preservação, busca e consumo por GPT.

## Português

### Visão geral

O `wayback-forum-archiver` foi reorganizado para gerar datasets históricos confiáveis a partir de capturas antigas do Wayback Machine.

O foco atual do projeto não é mais navegar HTML bruto diretamente. O foco é:

- normalizar acervo antigo
- extrair dados estruturados
- deduplicar snapshots e domínios
- preservar rastreabilidade
- gerar uma camada otimizada para GPT / RAG
- servir de base para futuras aplicações web de reconstrução histórica

O pipeline foi fechado sobre o acervo do SobreSites e cobre principalmente:

- ASP / Snitz-like
- phpBB 2.x

### Estado atual

Pipeline principal:

1. `prepare_archive.py`
2. `Build-ForumDataset.py`
3. `Refine-ForumSignatures.py`
4. `Enrich-ForumUserSignatures.py`

Documentação complementar:

- `ARCHITECTURE.md`
- `STATUS.md`

### Objetivos do pipeline

- gerar um dataset auditável
- ser conservador com HTML quebrado e lixo do Wayback
- separar conteúdo canônico de salvage
- preservar usuários, aliases, e-mails e assinaturas observadas
- produzir saídas úteis para GPT, busca e backend futuro

### Princípios de modelagem

- `.com` e `.com.br` são tratados como a mesma origem lógica para deduplicação de conteúdo
- ASP e phpBB continuam sendo plataformas distintas
- `topic/*` e `viewtopic/*` são a fonte primária
- `post/*` ASP entra como trilha de salvage
- o dataset é dividido em duas camadas:
  - `warehouse/`: preservação e rastreabilidade
  - `knowledge/`: documentos mais baratos para LLM

### Scripts

#### `prepare_archive.py`

Inventaria o acervo bruto, classifica arquivos relevantes e materializa uma árvore `normalized/` estável.

Principais responsabilidades:

- percorrer fontes brutas do Wayback
- decodificar nomes e estrutura do acervo
- classificar páginas úteis
- gerar `manifest.json`, resumos e logs

#### `Build-ForumDataset.py`

Extrai o dataset principal a partir de `normalized/`.

Principais responsabilidades:

- parsear ASP `topic`, `post`, `members`, `profile`
- parsear phpBB `viewtopic`, `profile`, `memberlist`
- deduplicar entre snapshots e domínios
- separar posts canônicos de `post_salvage`
- gerar `warehouse/`, `knowledge/`, logs e sumários
- oferecer debug com `--read-limit`
- oferecer recorte por tipo com `--kinds`

#### `Refine-ForumSignatures.py`

Isola assinaturas repetidas de usuários ASP para limpar o corpus principal sem perder a identidade histórica.

Saídas principais:

- `signature_refine/.../warehouse/posts_clean.jsonl`
- `signature_refine/.../knowledge/knowledge_posts_clean.jsonl`
- `signature_refine/.../warehouse/signature_profiles.jsonl`

#### `Enrich-ForumUserSignatures.py`

Enriquece `users.jsonl` com assinaturas observadas em ASP e phpBB.

Campos adicionados ao perfil do usuário:

- `signatures_observed`
- `signature_count_observed`
- `signature_sources`

### Estrutura das saídas

#### `warehouse/`

Camada de preservação e rastreabilidade.

Arquivos principais:

- `posts.jsonl`
- `post_salvage.jsonl`
- `topics.jsonl`
- `users.jsonl`
- `merged_identities.jsonl`

#### `knowledge/`

Camada otimizada para consumo por LLM.

Arquivos principais:

- `knowledge_posts.jsonl`
- `signature_refine/.../knowledge_posts_clean.jsonl`

#### auditoria

- `logs/run.log`
- `logs/warnings.log`
- `logs/errors.log`
- `summary.json`
- `manifest.json`

### Uso rápido

#### 1. Preparar o acervo bruto

```powershell
python .\prepare_archive.py \
  --archive-root "C:\path\to\archive" \
  --normalized-root "C:\path\to\archive\normalized" \
  --work-root ".\work" \
  --logs-root ".\logs" \
  --progress-every 250
```

#### 2. Smoke test do dataset

```powershell
python .\Build-ForumDataset.py \
  --input-root "C:\path\to\archive\normalized" \
  --output-root ".\out_test" \
  --read-limit 200 \
  --progress-every 50
```

#### 3. Smoke test por tipo

ASP `post/*`:

```powershell
python .\Build-ForumDataset.py \
  --input-root "C:\path\to\archive\normalized" \
  --output-root ".\out_post_debug" \
  --read-limit 120 \
  --kinds asp_post \
  --progress-every 40
```

phpBB `viewtopic/*`:

```powershell
python .\Build-ForumDataset.py \
  --input-root "C:\path\to\archive\normalized" \
  --output-root ".\out_phpbb_debug" \
  --read-limit 160 \
  --kinds phpbb_viewtopic \
  --progress-every 40
```

#### 4. Run completa

```powershell
python .\Build-ForumDataset.py \
  --input-root "C:\path\to\archive\normalized" \
  --output-root ".\out" \
  --progress-every 500
```

#### 5. Refinar assinaturas ASP

```powershell
python .\Refine-ForumSignatures.py \
  --run-root ".\out\run-YYYYMMDD-HHMMSS-XXX"
```

#### 6. Enriquecer usuários com assinaturas

```powershell
python .\Enrich-ForumUserSignatures.py \
  --run-root ".\out\run-YYYYMMDD-HHMMSS-XXX"
```

### Uso recomendado para GPT

Para GPT / ChatGPT, o corpus preferencial é:

- `signature_refine/.../knowledge/knowledge_posts_clean.jsonl`

Arquivos auxiliares úteis:

- `warehouse/users.jsonl`
- `warehouse/topics.jsonl`
- um `README_FORUM_CONTEXT.md` curto com regras históricas e limitações do acervo

### Limitações conhecidas

- o pipeline foi desenhado sobre o acervo do SobreSites e pode precisar de adaptação para outros fóruns
- parte do salvage ASP não possui `REPLY_ID` confiável
- merges cross-architecture por apelido exato são heurísticos explícitos, não equivalência garantida
- tópicos e perfis continuam sujeitos às lacunas naturais do Wayback Machine

---

## English

### Overview

`wayback-forum-archiver` has been reorganized to generate reliable historical datasets from old Wayback Machine captures.

The project is no longer centered on directly browsing raw archived HTML. Its current focus is to:

- normalize legacy archive material
- extract structured data
- deduplicate snapshots and domains
- preserve traceability
- generate an LLM-friendly layer for GPT / RAG
- provide a foundation for future historical web reconstruction projects

The pipeline was finalized against the SobreSites archive and primarily covers:

- ASP / Snitz-like forums
- phpBB 2.x

### Current status

Main pipeline:

1. `prepare_archive.py`
2. `Build-ForumDataset.py`
3. `Refine-ForumSignatures.py`
4. `Enrich-ForumUserSignatures.py`

Supporting documentation:

- `ARCHITECTURE.md`
- `STATUS.md`

### Pipeline goals

- produce an auditable dataset
- be conservative with broken HTML and Wayback noise
- separate canonical content from salvage
- preserve users, aliases, observed emails, and signatures
- generate outputs useful for GPT, search, and future backends

### Modeling principles

- `.com` and `.com.br` are treated as the same logical source for content deduplication
- ASP and phpBB remain distinct platforms
- `topic/*` and `viewtopic/*` are the primary source
- ASP `post/*` is treated as a salvage trail
- the dataset is split into two layers:
  - `warehouse/`: preservation and traceability
  - `knowledge/`: cheaper LLM-facing documents

### Scripts

#### `prepare_archive.py`

Inventories the raw archive, classifies relevant files, and materializes a stable `normalized/` tree.

Main responsibilities:

- traverse raw Wayback sources
- decode filenames and archive structure
- classify useful pages
- generate `manifest.json`, summaries, and logs

#### `Build-ForumDataset.py`

Extracts the main dataset from `normalized/`.

Main responsibilities:

- parse ASP `topic`, `post`, `members`, and `profile`
- parse phpBB `viewtopic`, `profile`, and `memberlist`
- deduplicate across snapshots and domains
- separate canonical posts from `post_salvage`
- generate `warehouse/`, `knowledge/`, logs, and summaries
- provide debug mode with `--read-limit`
- provide kind filtering with `--kinds`

#### `Refine-ForumSignatures.py`

Isolates repeated ASP user signatures so the main corpus becomes cleaner without losing historical identity.

Main outputs:

- `signature_refine/.../warehouse/posts_clean.jsonl`
- `signature_refine/.../knowledge/knowledge_posts_clean.jsonl`
- `signature_refine/.../warehouse/signature_profiles.jsonl`

#### `Enrich-ForumUserSignatures.py`

Enriches `users.jsonl` with observed ASP and phpBB signatures.

Fields added to user profiles:

- `signatures_observed`
- `signature_count_observed`
- `signature_sources`

### Output structure

#### `warehouse/`

Preservation and traceability layer.

Main files:

- `posts.jsonl`
- `post_salvage.jsonl`
- `topics.jsonl`
- `users.jsonl`
- `merged_identities.jsonl`

#### `knowledge/`

LLM-optimized layer.

Main files:

- `knowledge_posts.jsonl`
- `signature_refine/.../knowledge_posts_clean.jsonl`

#### audit trail

- `logs/run.log`
- `logs/warnings.log`
- `logs/errors.log`
- `summary.json`
- `manifest.json`

### Quick start

#### 1. Prepare the raw archive

```powershell
python .\prepare_archive.py \
  --archive-root "C:\path\to\archive" \
  --normalized-root "C:\path\to\archive\normalized" \
  --work-root ".\work" \
  --logs-root ".\logs" \
  --progress-every 250
```

#### 2. Dataset smoke test

```powershell
python .\Build-ForumDataset.py \
  --input-root "C:\path\to\archive\normalized" \
  --output-root ".\out_test" \
  --read-limit 200 \
  --progress-every 50
```

#### 3. Kind-specific smoke tests

ASP `post/*`:

```powershell
python .\Build-ForumDataset.py \
  --input-root "C:\path\to\archive\normalized" \
  --output-root ".\out_post_debug" \
  --read-limit 120 \
  --kinds asp_post \
  --progress-every 40
```

phpBB `viewtopic/*`:

```powershell
python .\Build-ForumDataset.py \
  --input-root "C:\path\to\archive\normalized" \
  --output-root ".\out_phpbb_debug" \
  --read-limit 160 \
  --kinds phpbb_viewtopic \
  --progress-every 40
```

#### 4. Full run

```powershell
python .\Build-ForumDataset.py \
  --input-root "C:\path\to\archive\normalized" \
  --output-root ".\out" \
  --progress-every 500
```

#### 5. Refine ASP signatures

```powershell
python .\Refine-ForumSignatures.py \
  --run-root ".\out\run-YYYYMMDD-HHMMSS-XXX"
```

#### 6. Enrich users with observed signatures

```powershell
python .\Enrich-ForumUserSignatures.py \
  --run-root ".\out\run-YYYYMMDD-HHMMSS-XXX"
```

### Recommended GPT usage

For GPT / ChatGPT use, the preferred corpus is:

- `signature_refine/.../knowledge/knowledge_posts_clean.jsonl`

Useful supporting files:

- `warehouse/users.jsonl`
- `warehouse/topics.jsonl`
- a short `README_FORUM_CONTEXT.md` with historical rules and archive limitations

### Known limitations

- the pipeline was designed around the SobreSites archive and may need adaptation for other forums
- part of the ASP salvage trail has no reliable `REPLY_ID`
- exact-name ASP/phpBB merges are explicit heuristics, not guaranteed identity equivalence
- topics and profiles remain subject to natural Wayback Machine gaps

## License

MIT
