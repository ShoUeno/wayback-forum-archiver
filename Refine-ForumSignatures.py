#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


class ExactLevelFilter(logging.Filter):
    def __init__(self, level: int) -> None:
        super().__init__()
        self.level = level

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno == self.level


class MinLevelFilter(logging.Filter):
    def __init__(self, level: int) -> None:
        super().__init__()
        self.level = level

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno >= self.level


class JsonlWriter:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = path.open('w', encoding='utf-8', newline='\n', buffering=65536)

    def write(self, payload: dict[str, Any]) -> None:
        self.handle.write(json.dumps(payload, ensure_ascii=False, separators=(',', ':')))
        self.handle.write('\n')

    def close(self) -> None:
        self.handle.flush()
        self.handle.close()


@dataclass
class Candidate:
    normalized: str
    block_count: int
    raw_example: str
    count: int = 0


@dataclass
class Profile:
    user_key: str
    author_display: str
    normalized: str
    block_count: int
    raw_example: str
    count: int
    user_post_count: int


def normalize_whitespace(text: str | None) -> str:
    if not text:
        return ''
    value = text.replace('\r', '')
    value = value.replace('\xa0', ' ')
    value = re.sub(r'[ \t]+', ' ', value)
    value = re.sub(r'\n{3,}', '\n\n', value)
    return value.strip()


def normalize_signature(text: str) -> str:
    value = normalize_whitespace(text)
    if not value:
        return ''
    value = re.sub(r'\s+', ' ', value).casefold()
    return value


def split_blocks(body_text: str) -> list[str]:
    text = (body_text or '').replace('\r', '').strip()
    if not text:
        return []
    parts = re.split(r'\n\s*\n+', text)
    return [part.strip() for part in parts if part.strip()]


def join_blocks(blocks: list[str]) -> str:
    return '\n\n'.join(blocks).strip()


def is_candidate_shape(candidate_text: str, full_text: str, max_signature_chars: int) -> bool:
    candidate = normalize_whitespace(candidate_text)
    full = normalize_whitespace(full_text)
    if not candidate or not full:
        return False
    if len(candidate) < 8 or len(candidate) > max_signature_chars:
        return False
    if len(candidate.split()) < 2:
        return False
    if len(candidate) >= len(full):
        return False
    prefix_len = len(full) - len(candidate)
    if prefix_len < 12:
        return False
    line_count = candidate.count('\n') + 1
    if line_count > 8:
        return False
    if re.fullmatch(r'[-_=~. ]+', candidate):
        return False
    return True


def build_knowledge_text(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    if payload.get('topic_title'):
        lines.append(f"T?pico: {payload['topic_title']}")
    if payload.get('forum_title'):
        lines.append(f"F?rum: {payload['forum_title']}")
    if payload.get('author_display'):
        lines.append(f"Autor: {payload['author_display']}")
    if payload.get('posted_at'):
        lines.append(f"Data: {payload['posted_at']}")
    lines.append('')
    lines.append(payload.get('body_text') or '')
    return '\n'.join(lines).strip()


def make_logger(run_root: Path) -> logging.Logger:
    logs_dir = run_root / 'logs'
    logs_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(f'signature-refine-{run_root.name}')
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    logger.propagate = False

    formatter = logging.Formatter('%(asctime)s | %(levelname)s | %(message)s', '%Y-%m-%dT%H:%M:%S')

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(formatter)
    logger.addHandler(console)

    run_file = logging.FileHandler(logs_dir / 'run.log', encoding='utf-8')
    run_file.setLevel(logging.INFO)
    run_file.setFormatter(formatter)
    logger.addHandler(run_file)

    warning_file = logging.FileHandler(logs_dir / 'warnings.log', encoding='utf-8')
    warning_file.setLevel(logging.WARNING)
    warning_file.addFilter(ExactLevelFilter(logging.WARNING))
    warning_file.setFormatter(formatter)
    logger.addHandler(warning_file)

    error_file = logging.FileHandler(logs_dir / 'errors.log', encoding='utf-8')
    error_file.setLevel(logging.ERROR)
    error_file.addFilter(MinLevelFilter(logging.ERROR))
    error_file.setFormatter(formatter)
    logger.addHandler(error_file)
    return logger


def iter_posts(posts_path: Path, read_limit: int) -> tuple[int, Any]:
    processed = 0
    with posts_path.open('r', encoding='utf-8') as handle:
        for line in handle:
            if read_limit and processed >= read_limit:
                break
            if not line.strip():
                continue
            processed += 1
            yield processed, json.loads(line)


def collect_candidates(posts_path: Path, args: argparse.Namespace, logger: logging.Logger) -> tuple[dict[str, list[Profile]], dict[str, int], dict[str, str], int]:
    candidate_map: dict[str, dict[str, Candidate]] = defaultdict(dict)
    user_post_counts: dict[str, int] = defaultdict(int)
    user_names: dict[str, str] = {}
    processed = 0

    for processed, payload in iter_posts(posts_path, args.read_limit):
        if payload.get('architecture') != 'asp' or payload.get('source_page_kind') != 'topic':
            continue
        user_key = payload.get('author_key')
        if not user_key:
            continue
        body_text = payload.get('body_text') or ''
        blocks = split_blocks(body_text)
        if len(blocks) < 2:
            continue
        user_post_counts[user_key] += 1
        user_names[user_key] = payload.get('author_display') or user_names.get(user_key, '')
        for block_count in (1, 2, 3):
            if len(blocks) <= block_count:
                continue
            candidate_text = join_blocks(blocks[-block_count:])
            if not is_candidate_shape(candidate_text, body_text, args.max_signature_chars):
                continue
            normalized = normalize_signature(candidate_text)
            if not normalized:
                continue
            bucket = candidate_map[user_key]
            item = bucket.get(normalized)
            if item is None:
                item = Candidate(normalized=normalized, block_count=block_count, raw_example=candidate_text)
                bucket[normalized] = item
            item.count += 1

        if processed % args.progress_every == 0:
            logger.info('SCAN | posts=%s users=%s', processed, len(user_post_counts))

    profiles_by_user: dict[str, list[Profile]] = {}
    for user_key, candidates in candidate_map.items():
        total_posts = user_post_counts.get(user_key, 0)
        if total_posts < args.min_user_posts:
            continue
        selected: list[Profile] = []
        ranked = sorted(candidates.values(), key=lambda item: (-item.count, -len(item.raw_example), item.block_count))
        for item in ranked:
            coverage = item.count / total_posts if total_posts else 0.0
            if item.count < args.min_repeats:
                continue
            if coverage < args.min_coverage and item.count < args.strong_repeat_count:
                continue
            if any(item.normalized in prof.normalized or prof.normalized in item.normalized for prof in selected):
                continue
            selected.append(Profile(
                user_key=user_key,
                author_display=user_names.get(user_key, ''),
                normalized=item.normalized,
                block_count=item.block_count,
                raw_example=item.raw_example,
                count=item.count,
                user_post_count=total_posts,
            ))
            if len(selected) >= args.max_signatures_per_user:
                break
        if selected:
            profiles_by_user[user_key] = selected
    return profiles_by_user, user_post_counts, user_names, processed


def match_profile(body_text: str, profiles: list[Profile]) -> tuple[str | None, str | None]:
    blocks = split_blocks(body_text)
    if len(blocks) < 2:
        return None, None
    for profile in sorted(profiles, key=lambda item: (-item.block_count, -len(item.raw_example), -item.count)):
        if len(blocks) <= profile.block_count:
            continue
        candidate_raw = join_blocks(blocks[-profile.block_count:])
        if normalize_signature(candidate_raw) != profile.normalized:
            continue
        clean_text = join_blocks(blocks[:-profile.block_count])
        if not clean_text:
            continue
        return clean_text, candidate_raw
    return None, None


def refine_dataset(args: argparse.Namespace) -> int:
    run_root = Path(args.run_root).resolve()
    posts_path = run_root / 'warehouse' / 'posts.jsonl'
    if not posts_path.exists():
        raise FileNotFoundError(f'posts.jsonl nao encontrado em {posts_path}')

    stamp = datetime.now().strftime('%Y%m%d-%H%M%S-%f')[:19]
    refine_root = run_root / 'signature_refine' / f'run-{stamp}'
    logger = make_logger(refine_root)
    logger.info('BOOT | Iniciando refinamento de assinaturas. run_root=%s', run_root)

    profiles_by_user, user_post_counts, user_names, processed_scan = collect_candidates(posts_path, args, logger)
    logger.info('SCAN_DONE | posts_lidos=%s usuarios_com_assinatura=%s', processed_scan, len(profiles_by_user))

    posts_writer = JsonlWriter(refine_root / 'warehouse' / 'posts_clean.jsonl')
    knowledge_writer = JsonlWriter(refine_root / 'knowledge' / 'knowledge_posts_clean.jsonl')
    profiles_writer = JsonlWriter(refine_root / 'warehouse' / 'signature_profiles.jsonl')

    summary = {
        'posts_scanned': processed_scan,
        'users_considered': len(user_post_counts),
        'users_with_signature_profiles': len(profiles_by_user),
        'posts_with_signature_removed': 0,
        'signature_profiles_written': 0,
        'warnings': 0,
        'errors': 0,
    }

    for user_key in sorted(profiles_by_user):
        for index, profile in enumerate(profiles_by_user[user_key], start=1):
            profiles_writer.write({
                'signature_profile_key': f'{user_key}:sig:{index}',
                'user_key': user_key,
                'author_display': profile.author_display,
                'signature_text_example': profile.raw_example,
                'match_count': profile.count,
                'user_post_count': profile.user_post_count,
                'coverage_ratio': round(profile.count / profile.user_post_count, 6) if profile.user_post_count else 0.0,
                'block_count': profile.block_count,
                'heuristic': 'repeated_suffix_blocks',
            })
            summary['signature_profiles_written'] += 1

    processed_write = 0
    for processed_write, payload in iter_posts(posts_path, args.read_limit):
        refined = dict(payload)
        refined['body_text_full'] = payload.get('body_text') or ''
        refined['signature_text'] = None
        refined['signature_rule'] = None
        user_key = payload.get('author_key')
        if payload.get('architecture') == 'asp' and payload.get('source_page_kind') == 'topic' and user_key in profiles_by_user:
            clean_text, signature_text = match_profile(payload.get('body_text') or '', profiles_by_user[user_key])
            if clean_text and signature_text:
                refined['body_text'] = clean_text
                refined['signature_text'] = signature_text
                refined['signature_rule'] = 'repeated_user_suffix'
                summary['posts_with_signature_removed'] += 1
        posts_writer.write(refined)
        knowledge_writer.write({
            'knowledge_key': refined['post_key'],
            'post_key': refined['post_key'],
            'topic_key': refined['topic_key'],
            'user_key': refined.get('author_key'),
            'architecture': refined['architecture'],
            'source_page_kind': refined['source_page_kind'],
            'topic_title': refined.get('topic_title') or '',
            'forum_title': refined.get('forum_title') or '',
            'author_display': refined.get('author_display') or '',
            'posted_at': refined.get('posted_at'),
            'text': build_knowledge_text(refined),
            'first_source_file': refined['first_source_file'],
            'signature_removed': bool(refined.get('signature_text')),
        })
        if processed_write % args.progress_every == 0:
            logger.info('WRITE | posts=%s refined=%s', processed_write, summary['posts_with_signature_removed'])

    posts_writer.close()
    knowledge_writer.close()
    profiles_writer.close()

    (refine_root / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    (refine_root / 'manifest.json').write_text(json.dumps({
        'run_root': str(run_root),
        'posts_source': str(posts_path),
        'read_limit': args.read_limit,
        'min_repeats': args.min_repeats,
        'min_coverage': args.min_coverage,
        'strong_repeat_count': args.strong_repeat_count,
        'max_signature_chars': args.max_signature_chars,
        'max_signatures_per_user': args.max_signatures_per_user,
        'python_executable': sys.executable,
    }, ensure_ascii=False, indent=2), encoding='utf-8')
    logger.info('DONE | profiles=%s posts_refined=%s', summary['signature_profiles_written'], summary['posts_with_signature_removed'])
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Isola assinaturas repetidas de usuarios ASP no dataset do forum.')
    parser.add_argument('--run-root', required=True, help='Diretorio da run completa gerada pelo Build-ForumDataset.py')
    parser.add_argument('--read-limit', type=int, default=0, help='Limita quantos posts ler para debug')
    parser.add_argument('--progress-every', type=int, default=10000, help='Intervalo de progresso no console')
    parser.add_argument('--min-user-posts', type=int, default=4, help='Minimo de posts ASP topic por usuario para considerar assinatura')
    parser.add_argument('--min-repeats', type=int, default=3, help='Minimo de repeticoes do mesmo sufixo')
    parser.add_argument('--min-coverage', type=float, default=0.2, help='Cobertura minima do sufixo entre os posts do usuario')
    parser.add_argument('--strong-repeat-count', type=int, default=6, help='Aceita cobertura menor quando a repeticao absoluta e alta')
    parser.add_argument('--max-signature-chars', type=int, default=280, help='Tamanho maximo da assinatura candidata')
    parser.add_argument('--max-signatures-per-user', type=int, default=2, help='Maximo de assinaturas ativas por usuario')
    return parser.parse_args()


if __name__ == '__main__':
    try:
        raise SystemExit(refine_dataset(parse_args()))
    except Exception as exc:
        print(f'ERRO | {exc}', file=sys.stderr)
        raise
