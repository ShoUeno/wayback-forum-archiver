# Status: pipeline dataset forum

## Objetivo
Transformar o acervo HTML do forum antigo em um dataset auditavel, deduplicado e barato para consumo por GPT/RAG.

Documento de arquitetura: `forum_dataset/ARCHITECTURE.md`
Implementacao ativa: `forum_dataset/Build-ForumDataset.py`
Script legado/prototipo: `forum_dataset/Build-ForumDataset.ps1`

## Decisao atual
A continuacao do trabalho esta no script Python.

Motivos:
- ja gera logs, `summary.json`, `manifest.json`, `warehouse/` e `knowledge/`
- ja aceita `--read-limit` e `--kinds`
- ficou mais simples corrigir parsing sujo e edge cases do acervo Wayback

## O que mudou em 2026-03-10
- correcao do parser phpBB `viewtopic/*` para nao truncar posts com quote aninhado
- correcao do parser phpBB para nao tratar `Mensagens: N` como `role_label`
- fallback de decode mais resiliente para HTML quebrado (`cp1252` com queda para `latin-1`)
- politica mais conservadora para ASP `post/*`:
  - quote pages nao sao mais promovidas para `posts.jsonl` sem autor/data confiaveis
  - elas ficam em `post_salvage.jsonl`
  - salvage identico ao post canonico e descartado na finalizacao
- topicos stub gerados so por `post/*` deixaram de ser emitidos em `topics.jsonl`
- topicos com `post_count = 0` tambem foram removidos do arquivo final de topicos
- etapa de refinamento de assinaturas criada para limpar `body_text` ASP sem perder a assinatura
- etapa de enriquecimento de usuarios criada para guardar assinaturas observadas em `users.jsonl`

## O que ja parece concluido
- parser ASP de `topic/*` emitindo posts, topicos e usuarios observados
- parser ASP de `post/*` emitindo salvage com `candidate_post_key` quando houver `REPLY_ID`
- parser ASP de `members/*`
- parser ASP de `profile/*`
- parser phpBB de `profile/*`
- parser phpBB de `memberlist/*`
- parser phpBB de `viewtopic/*` validado com amostra maior
- merge cross-architecture por alias exato ja implementado na finalizacao

## O que ainda falta validar em run grande
- execucao completa pos-correcoes do Python
- taxa real de `merged_identities`
- qualidade final de `knowledge/knowledge_posts.jsonl`
- ruido real dos warnings de mojibake em ASP `post/*`

## Evidencias locais desta sessao
- `py_out_viewtopic2/run-20260310-101343-184/`:
  - 12 arquivos phpBB
  - 30 posts
  - confirmou correcao de quote embutido
- `py_out_phpbb_large2/run-20260310-104232-952/`:
  - 160 arquivos phpBB
  - 627 posts
  - 54 topicos
  - 135 usuarios
  - amostra com `author_display`, `posted_at` e `posted_at_raw` preenchidos
- `py_out_post_recheck/run-20260310-104232-967/`:
  - 120 arquivos ASP `post/*`
  - `posts_emitted = 0`
  - `salvage_records = 5`
  - `topic_stubs_skipped = 111`
  - confirmou que registros pobres nao entram mais em `posts.jsonl` nem poluem `topics.jsonl`
- `out_full_rebuilt/run-20260310-104614-519/`:
  - 68.278 arquivos processados
  - 111.017 posts principais
  - 9.723 salvages
  - 271 merges ASP/phpBB
  - `posted_at: null` em `posts.jsonl` = 0
  - `author_display: null` em `posts.jsonl` = 0
  - `first_seen_at: null` em `topics.jsonl` = 0 apos filtrar topicos com `post_count = 0`
- `out_full_rebuilt/run-20260310-104614-519/signature_refine/run-20260310-111148-633/`:
  - 35.620 posts ASP com assinatura isolada em `signature_text`
  - 848 perfis de assinatura detectados
  - `knowledge_posts_clean.jsonl` pronto para consumo mais limpo por GPT
- `out_full_rebuilt/run-20260310-104614-519/user_signature_enrich/run-20260310-111741-286/`:
  - `users.jsonl` enriquecido com `signatures_observed`
  - 1.280 usuarios com assinatura observada
  - 848 assinaturas ASP reaproveitadas do refinamento
  - 1.574 assinaturas phpBB mineradas do rodape `genmed`
- `out_py_full/`:
  - run completa interrompida manualmente
  - nao considerar como dataset final

## Leitura correta dos campos sensiveis
- `author_display`, `posted_at` e `posted_at_raw` nulos em `posts.jsonl` eram um problema no caminho ASP `post/*`; isso foi corrigido removendo a promocao desses registros para o corpus principal
- `candidate_post_key = null` em `post_salvage.jsonl` continua valido para `TopicQuote`, porque esse HTML nao traz `REPLY_ID`
- `first_seen_at` e `last_seen_at` nulos em `topics.jsonl` vinham de stubs e topicos sem post parseado; esses registros agora sao descartados no arquivo final de topicos

## Python nesta maquina
Preferir `C:\Program Files\Python314\python.exe` se o `python` da sessao do Codex nao resolver.

## Proximo passo recomendado
1. rodar um smoke combinado de cobertura maior (`asp_topic`, `asp_post`, `phpbb_viewtopic`, perfis e membros)
2. usar `signature_refine/.../knowledge/knowledge_posts_clean.jsonl` como corpus preferencial para o GPT
3. usar `warehouse/users.jsonl` enriquecido com `signatures_observed` para contexto de identidade dos usuarios
4. opcionalmente reduzir o ruido de assinaturas phpBB quase duplicadas se voce quiser um perfil ainda mais compacto
