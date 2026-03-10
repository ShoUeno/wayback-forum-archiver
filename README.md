# Wayback Forum Archiver

Toolkit para transformar HTMLs antigos do Wayback Machine em um dataset auditável, deduplicado e barato para consumo por GPT, busca e reconstrução histórica de fóruns.

O pipeline atual foi fechado em cima do acervo do SobreSites e cobre duas arquiteturas clássicas da época:

- ASP / Snitz-like
- phpBB 2.x

O foco deste repositório hoje não é mais "navegar HTML bruto". O foco é gerar um dataset confiável, com rastreabilidade, separando conteúdo canônico de salvage, preservando usuários, aliases, e-mails observados, assinaturas e metadados históricos.

## Estado atual

Pipeline ativo:

1. `prepare_archive.py`
2. `Build-ForumDataset.py`
3. `Refine-ForumSignatures.py`
4. `Enrich-ForumUserSignatures.py`

Documentação complementar:

- `ARCHITECTURE.md`: decisões de modelagem e regras do dataset
- `STATUS.md`: handoff operacional e pontos já validados

## Objetivo

Gerar um acervo estruturado com estas propriedades:

- auditável
- rápido de rodar
- deduplicado entre snapshots e domínios
- conservador com lixo do Wayback
- útil tanto para GPT quanto para uma futura aplicação web

## Princípios do pipeline

- `.com` e `.com.br` são tratados como a mesma origem lógica para deduplicação de conteúdo.
- ASP e phpBB continuam sendo plataformas distintas.
- `topic/*` e `viewtopic/*` são a fonte primária.
- `post/*` ASP entra como trilha de salvage, para casos de lost media, quote pages e snapshots órfãos.
- O dataset final é dividido em duas camadas:
  - `warehouse/`: preservação e rastreabilidade
  - `knowledge/`: documentos mais baratos para GPT

## Scripts

### `prepare_archive.py`
Inventaria o acervo bruto e materializa uma árvore `normalized/` conservadora.

Responsabilidades:

- percorrer `sobresites_com` e `sobresites_com_br`
- decodificar nomes de arquivos do Wayback
- classificar arquivos relevantes
- materializar páginas candidatas em uma árvore estável
- gerar `manifest.json`, resumos e logs

Entrada esperada:

- raiz com as fontes brutas do arquivo Wayback

Saídas típicas:

- `normalized/`
- `work/manifest.json`
- `work/summary.json`
- `logs/prepare.log`

### `Build-ForumDataset.py`
Extrai o dataset principal a partir do acervo `normalized/`.

Responsabilidades:

- parsear ASP `topic`, `post`, `members`, `profile`
- parsear phpBB `viewtopic`, `profile`, `memberlist`
- deduplicar conteúdo entre snapshots e domínios
- separar corpus principal de salvage
- gerar `warehouse/`, `knowledge/`, `summary.json`, `manifest.json` e logs
- oferecer modo de debug com `-r/--read-limit`
- oferecer recorte por tipo com `--kinds`

Argumentos principais:

- `--input-root`
- `--output-root`
- `-r` / `--read-limit`
- `--kinds`
- `--progress-every`

### `Refine-ForumSignatures.py`
Isola assinaturas repetidas de usuários ASP sem perder a informação histórica.

Responsabilidades:

- analisar posts ASP da run principal
- detectar sufixos repetidos por usuário
- remover assinatura do corpo principal quando a confiança for suficiente
- gerar uma versão mais limpa do corpus para GPT

Saídas:

- `signature_refine/.../warehouse/posts_clean.jsonl`
- `signature_refine/.../knowledge/knowledge_posts_clean.jsonl`
- `signature_refine/.../warehouse/signature_profiles.jsonl`

### `Enrich-ForumUserSignatures.py`
Enriquece `users.jsonl` com assinaturas observadas em ASP e phpBB.

Responsabilidades:

- reaproveitar assinaturas ASP detectadas no refine
- minerar assinaturas phpBB do rodapé dos posts
- consolidar isso no perfil do usuário

Campos adicionados em `users.jsonl`:

- `signatures_observed`
- `signature_count_observed`
- `signature_sources`

## Estrutura das saídas

### `warehouse/`
Camada de preservação e rastreabilidade.

Arquivos principais:

- `posts.jsonl`
- `post_salvage.jsonl`
- `topics.jsonl`
- `users.jsonl`
- `merged_identities.jsonl`

### `knowledge/`
Camada otimizada para consumo por LLM.

Arquivos principais:

- `knowledge_posts.jsonl`
- `signature_refine/.../knowledge_posts_clean.jsonl`

### logs e auditoria

- `logs/run.log`
- `logs/warnings.log`
- `logs/errors.log`
- `summary.json`
- `manifest.json`

## Regras importantes do dataset

### Deduplicação

- o mesmo post observado em `.com` e `.com.br` é emitido uma vez só
- snapshots pobres de `post/*` não sobrescrevem o canônico
- salvage idêntico ao post principal é descartado na finalização

### Tópicos

- `topics.jsonl` só mantém tópicos com pelo menos um post parseado
- tópicos-stub gerados apenas por páginas pobres não entram no arquivo final

### Usuários e identidade

- dentro da mesma plataforma, o ID ancora a identidade
- aliases observados são preservados
- e-mails múltiplos observados são preservados
- assinaturas observadas entram no perfil do usuário
- merges ASP/phpBB por apelido exato ficam explícitos em `merged_identities.jsonl`

### Ranks

- `Moderador Junior` não é tratado como moderador real
- o rótulo é preservado, mas a leitura semântica é conservadora

## Fluxo recomendado

```text
Wayback raw archive
    -> prepare_archive.py
    -> normalized/
    -> Build-ForumDataset.py
    -> warehouse/ + knowledge/
    -> Refine-ForumSignatures.py
    -> knowledge_posts_clean.jsonl
    -> Enrich-ForumUserSignatures.py
    -> users.jsonl enriquecido
```

## Requisitos

- Python 3.10+
- sem dependências externas obrigatórias

Observação:

- nesta máquina o fluxo foi validado com `python` apontando para Python 3.14 no PATH

## Uso rápido

### 1. Preparar o acervo bruto

```powershell
python .\prepare_archive.py \
  --archive-root "D:\Projeto SS IA 2.0\archive" \
  --normalized-root "D:\Projeto SS IA 2.0\archive\normalized" \
  --work-root ".\work" \
  --logs-root ".\logs" \
  --progress-every 250
```

### 2. Smoke test do dataset

```powershell
python .\Build-ForumDataset.py \
  --input-root "D:\Projeto SS IA 2.0\archive\normalized" \
  --output-root ".\out_test" \
  --read-limit 200 \
  --progress-every 50
```

### 3. Smoke test por tipo

ASP `post/*`:

```powershell
python .\Build-ForumDataset.py \
  --input-root "D:\Projeto SS IA 2.0\archive\normalized" \
  --output-root ".\out_post_debug" \
  --read-limit 120 \
  --kinds asp_post \
  --progress-every 40
```

phpBB `viewtopic/*`:

```powershell
python .\Build-ForumDataset.py \
  --input-root "D:\Projeto SS IA 2.0\archive\normalized" \
  --output-root ".\out_phpbb_debug" \
  --read-limit 160 \
  --kinds phpbb_viewtopic \
  --progress-every 40
```

### 4. Run completa

```powershell
python .\Build-ForumDataset.py \
  --input-root "D:\Projeto SS IA 2.0\archive\normalized" \
  --output-root ".\out" \
  --progress-every 500
```

### 5. Refinar assinaturas ASP

```powershell
python .\Refine-ForumSignatures.py \
  --run-root ".\out\run-YYYYMMDD-HHMMSS-XXX"
```

### 6. Enriquecer usuários com assinaturas

```powershell
python .\Enrich-ForumUserSignatures.py \
  --run-root ".\out\run-YYYYMMDD-HHMMSS-XXX"
```

## Uso recomendado para GPT

Para um GPT no ChatGPT, o corpus preferencial é:

- `signature_refine/.../knowledge/knowledge_posts_clean.jsonl`

Arquivos auxiliares úteis:

- `warehouse/users.jsonl`
- `warehouse/topics.jsonl`
- um `README_FORUM_CONTEXT.md` curto com regras históricas e limitações do acervo

## O que já foi validado neste pipeline

- parser ASP de `topic/*`
- parser ASP de `post/*` como salvage conservador
- parser ASP de `members/*`
- parser ASP de `profile/*`
- parser phpBB de `viewtopic/*`
- parser phpBB de `profile/*`
- parser phpBB de `memberlist/*`
- refinamento de assinaturas ASP
- enriquecimento de usuários com assinaturas ASP e phpBB

## Estrutura do repositório

```text
scripts/
├── README.md
├── LICENSE
├── .gitignore
├── ARCHITECTURE.md
├── STATUS.md
├── prepare_archive.py
├── Build-ForumDataset.py
├── Refine-ForumSignatures.py
└── Enrich-ForumUserSignatures.py
```

## Limitações conhecidas

- o pipeline foi desenhado em cima do acervo do SobreSites e pode precisar de adaptação para outros fóruns
- parte do salvage ASP não possui `REPLY_ID` confiável
- merges cross-architecture por apelido exato devem ser tratados como heurística explícita, não como verdade absoluta
- tópicos e perfis continuam sujeitos às lacunas naturais do Wayback Machine

## Licença

MIT
