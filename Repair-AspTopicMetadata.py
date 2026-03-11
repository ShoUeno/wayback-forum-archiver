#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Iterator, Any

BREADCRUMB_RE = re.compile(
    r'(?is)<a[^>]+class="linkstopo"[^>]+href="FORUM\.asp\?FORUM_ID=(?P<forum>\d+)"[^>]*>(?P<forum_title>.*?)</a>\s*&nbsp;>\s*&nbsp;(?P<topic_title>.*?)(?:<!--|</font>)'
)


def iter_concat(path: Path) -> Iterator[dict[str, Any]]:
    text = path.read_text(encoding='utf-8')
    dec = json.JSONDecoder()
    idx = 0
    while idx < len(text):
        while idx < len(text) and text[idx].isspace():
            idx += 1
        if idx >= len(text):
            break
        obj, end = dec.raw_decode(text, idx)
        yield obj
        idx = end


def dump_concat(path: Path, items: list[dict[str, Any]]) -> None:
    with path.open('w', encoding='utf-8', newline='\n') as out:
        for obj in items:
            out.write(json.dumps(obj, ensure_ascii=False, indent=4))
            out.write('\n')


def html_to_text(value: str) -> str:
    value = re.sub(r'(?is)<br\s*/?>', '\n', value)
    value = re.sub(r'(?is)<[^>]+>', '', value)
    value = value.replace('&nbsp;', ' ')
    value = value.replace('&gt;', '>')
    value = value.replace('&lt;', '<')
    value = value.replace('&amp;', '&')
    value = re.sub(r'\s+', ' ', value)
    return value.strip()


def read_html(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ('utf-8', 'cp1252', 'latin-1'):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode('cp1252', errors='replace')


def parse_breadcrumb(source_html: str) -> dict[str, str] | None:
    match = BREADCRUMB_RE.search(source_html)
    if not match:
        return None
    forum_id = match.group('forum').strip()
    forum_title = html_to_text(match.group('forum_title'))
    topic_title = html_to_text(match.group('topic_title'))
    if not forum_id:
        return None
    if not forum_title and not topic_title:
        return None
    return {
        'forum_key': f'asp:forum:{forum_id}',
        'forum_id': forum_id,
        'forum_title': forum_title,
        'topic_title': topic_title,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description='Repair ASP topic/forum metadata in topics.jsonl and posts.jsonl using raw breadcrumb HTML.')
    parser.add_argument('--final-root', required=True)
    parser.add_argument('--normalized-root', required=True)
    args = parser.parse_args()

    final_root = Path(args.final_root)
    normalized_root = Path(args.normalized_root)
    topics_path = final_root / 'topics.jsonl'
    posts_path = final_root / 'posts.jsonl'

    topics = list(iter_concat(topics_path))
    posts = list(iter_concat(posts_path))

    patch_by_topic: dict[str, dict[str, str]] = {}
    topic_sources_checked = 0
    topic_sources_patched = 0

    for topic in topics:
        if topic.get('architecture') != 'asp':
            continue
        if topic.get('forum_id') and topic.get('topic_title'):
            continue
        relative = topic.get('first_source_file') or ''
        if not relative:
            continue
        source_path = normalized_root / Path(relative)
        topic_sources_checked += 1
        if not source_path.exists():
            continue
        breadcrumb = parse_breadcrumb(read_html(source_path))
        if not breadcrumb:
            continue
        topic.update(breadcrumb)
        patch_by_topic[topic['topic_key']] = breadcrumb
        topic_sources_patched += 1

    post_patches = 0
    for post in posts:
        patch = patch_by_topic.get(post.get('topic_key', ''))
        if not patch:
            continue
        post.update(patch)
        post_patches += 1

    dump_concat(topics_path, topics)
    dump_concat(posts_path, posts)

    print(f'[ok] topics_checked={topic_sources_checked}')
    print(f'[ok] topics_patched={topic_sources_patched}')
    print(f'[ok] posts_patched={post_patches}')
    print(f'[ok] topics_file={topics_path}')
    print(f'[ok] posts_file={posts_path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
