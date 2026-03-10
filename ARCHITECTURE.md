# Arquitetura recomendada

## Objetivo

Extrair o forum antigo arquivado em HTML para um dataset:

- auditavel
- deduplicado
- rapido de gerar
- barato para consumo por GPT/RAG

## Principios

1. `sobresites_com` e `sobresites_com_br` sao a mesma origem logica.
   O dominio entra como evidencia de observacao e duplicata.

2. ASP e phpBB sao mundos separados.
   A migracao nao carregou os dados, entao a identidade entre arquiteturas nao e fundida implicitamente.

3. `topic/*` e `viewtopic/*` sao a fonte primaria.
   `post/*` entra como trilha de salvage para lost media, snapshots orfaos e citacoes pre-preenchidas.

4. O dataset tem duas camadas.
   `warehouse/` preserva rastreabilidade e granularidade.
   `knowledge/` entrega documentos curtos e baratos para GPT.

## Saidas

- `warehouse/posts.jsonl`
- `warehouse/post_salvage.jsonl`
- `warehouse/topics.jsonl`
- `warehouse/users.jsonl`
- `warehouse/merged_identities.jsonl`
- `knowledge/knowledge_posts.jsonl`
- `signature_refine/.../warehouse/posts_clean.jsonl`
- `signature_refine/.../knowledge/knowledge_posts_clean.jsonl`
- `user_signature_enrich/.../warehouse/user_signatures.jsonl`
- `logs/run.log`
- `logs/warnings.log`
- `logs/errors.log`
- `summary.json`
- `manifest.json`

## Chaves canonicas

- Post ASP: `asp:post:{REPLY_ID}`
- Post phpBB: `phpbb:post:{p}`
- Topico ASP: `asp:topic:{TOPIC_ID}`
- Topico phpBB: `phpbb:topic:{t}`
- Usuario ASP: `asp:user:{id}`
- Usuario phpBB: `phpbb:user:{u}`

## Deduplicacao

### Entre dominios

O mesmo post visto em `.com` e `.com.br` cai na mesma chave e so e emitido uma vez.

### Entre fonte primaria e salvage

- `post/*` ASP nao entra em `posts.jsonl` sem metadado minimamente confiavel de autor/data.
- `ReplyQuote` e `TopicQuote` vao por padrao para `post_salvage.jsonl`.
- Se o post canonico aparecer depois em `topic/*`, um salvage identico e descartado na finalizacao.
- `candidate_post_key` pode ser `null` em `TopicQuote`, porque o HTML nao traz `REPLY_ID` confiavel.
- Snapshots sem ID confiavel nunca sobrescrevem o canonico.

## Topicos

- `topics.jsonl` guarda apenas topicos com ao menos um post parseado.
- Stubs criados apenas por `post/*` e topicos canonicos sem post aproveitavel nao sao emitidos no arquivo final.
- O contexto de um salvage continua preservado dentro do proprio `post_salvage.jsonl`.

## Papeis e ranks

- `Moderador Junior` e preservado em `role_label`.
- A classificacao derivada vira `decorative_rank`.
- Nao e tratado como moderador real.

## Apelidos e identidade

Dentro da mesma arquitetura, o ID ancora a identidade e os nomes observados viram aliases.

Entre ASP e phpBB, esta versao cria merge automatico quando o apelido normalizado bate exatamente entre as duas arquiteturas. O merge fica explicito em `merged_identities.jsonl` e tambem em `merged_identity_key` dentro de `users.jsonl`.

## Consumo por GPT

Use primeiro `knowledge/knowledge_posts.jsonl`.

`users.jsonl` preserva historico observavel: aliases, perfis, localizacoes, homepages, multiplos e-mails e assinaturas observadas ao longo do tempo.

Cada linha de `knowledge_posts.jsonl` vem com:

- texto limpo
- titulo do topico
- forum
- autor
- data
- origem primaria (`topic` ou `viewtopic`)

## Assinaturas

- ASP: as assinaturas costumam estar concatenadas ao fim do `body_text` no Snitz.
- Para consumo por GPT, a etapa `Refine-ForumSignatures.py` gera `posts_clean.jsonl` e `knowledge_posts_clean.jsonl`, movendo a assinatura para `signature_text` quando detecta um sufixo repetido por usuario.
- phpBB: as assinaturas ficam em um rodape proprio no HTML do post e nao no corpo principal.
- A etapa `Enrich-ForumUserSignatures.py` popula `users.jsonl` com `signatures_observed`, `signature_count_observed` e `signature_sources`.
- Isso preserva a identidade do usuario sem contaminar o texto principal das mensagens.

## Execucao

Smoke test ASP `post/*`:

```powershell
python .\forum_dataset\Build-ForumDataset.py \
  --input-root 'D:\Projeto SS IA 2.0\archive\normalized' \
  --output-root .\py_out_post_recheck \
  --read-limit 120 \
  --kinds asp_post \
  --progress-every 40
```

Smoke test phpBB `viewtopic/*`:

```powershell
python .\forum_dataset\Build-ForumDataset.py \
  --input-root 'D:\Projeto SS IA 2.0\archive\normalized' \
  --output-root .\py_out_phpbb_large2 \
  --read-limit 160 \
  --kinds phpbb_viewtopic \
  --progress-every 40
```

Execucao completa sugerida:

```powershell
python .\forum_dataset\Build-ForumDataset.py \
  --input-root 'D:\Projeto SS IA 2.0\archive\normalized' \
  --output-root .\out \
  --progress-every 500
```
