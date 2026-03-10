#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def read_jsonl(path: Path):
    with path.open('r', encoding='utf-8') as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def write_jsonl(path: Path, rows) -> int:
    count = 0
    with path.open('w', encoding='utf-8', newline='\n') as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + '\n')
            count += 1
    return count


def build_knowledge_text(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    if payload.get('topic_title'):
        lines.append(f"T\u00f3pico: {payload['topic_title']}")
    if payload.get('forum_title'):
        lines.append(f"F\u00f3rum: {payload['forum_title']}")
    if payload.get('author_display'):
        lines.append(f"Autor: {payload['author_display']}")
    if payload.get('posted_at'):
        lines.append(f"Data: {payload['posted_at']}")
    lines.append('')
    lines.append(payload.get('body_text') or '')
    return '\n'.join(lines).strip()


def iter_knowledge_rows(posts_path: Path):
    for payload in read_jsonl(posts_path):
        yield {
            'knowledge_key': payload['post_key'],
            'post_key': payload['post_key'],
            'topic_key': payload['topic_key'],
            'user_key': payload.get('author_key'),
            'architecture': payload['architecture'],
            'source_page_kind': payload['source_page_kind'],
            'topic_title': payload.get('topic_title') or '',
            'forum_title': payload.get('forum_title') or '',
            'author_display': payload.get('author_display') or '',
            'posted_at': payload.get('posted_at'),
            'text': build_knowledge_text(payload),
            'first_source_file': payload['first_source_file'],
        }


def main() -> int:
    parser = argparse.ArgumentParser(description='Rebuild knowledge_posts.jsonl from warehouse/posts.jsonl')
    parser.add_argument('--run-root', required=True, help='Existing run root containing warehouse/posts.jsonl')
    args = parser.parse_args()

    run_root = Path(args.run_root)
    posts_path = run_root / 'warehouse' / 'posts.jsonl'
    knowledge_dir = run_root / 'knowledge'
    knowledge_path = knowledge_dir / 'knowledge_posts.jsonl'

    if not posts_path.exists():
        raise SystemExit(f'posts.jsonl not found: {posts_path}')

    knowledge_dir.mkdir(parents=True, exist_ok=True)
    count = write_jsonl(knowledge_path, iter_knowledge_rows(posts_path))

    print(f'[ok] rebuilt {count} knowledge rows')
    print(f'[ok] output: {knowledge_path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
