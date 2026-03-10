#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

CHARSET_RE = re.compile(r'(?is)charset\s*=\s*["\']?(?P<charset>[a-zA-Z0-9._-]+)')
XML_ENCODING_RE = re.compile(r'(?is)<\?xml\b[^>]*encoding=["\'](?P<charset>[^"\']+)')
SCRIPT_STYLE_RE = re.compile(r'(?is)<(script|style)\b.*?</\1>')
TAG_RE = re.compile(r'(?is)<[^>]+>')
PHPBB_POST_ROW_RE = re.compile(
    r'(?is)<tr>\s*<td\b[^>]*rowspan="2"[^>]*>(?P<author>.*?)</td>\s*<td\b[^>]*valign="top"[^>]*>(?P<message>.*?)</td>\s*</tr>\s*<tr>\s*<td\b(?=[^>]*valign="bottom")(?=[^>]*nowrap="nowrap")(?=[^>]*class="row[12]")[^>]*>(?P<footer>.*?)</td>\s*</tr>'
)


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


def normalize_whitespace(text: str | None) -> str:
    if not text:
        return ''
    value = text.replace('\r', '')
    value = value.replace('\xa0', ' ')
    value = re.sub(r'[ \t]+', ' ', value)
    value = re.sub(r'\n{3,}', '\n\n', value)
    return value.strip()


def html_to_text(raw_html: str | None) -> str:
    if not raw_html:
        return ''
    text = SCRIPT_STYLE_RE.sub('', raw_html)
    text = re.sub(r'(?i)<br\s*/?>', '\n', text)
    text = re.sub(r'(?i)</p\s*>', '\n\n', text)
    text = re.sub(r'(?i)</tr\s*>', '\n', text)
    text = re.sub(r'(?i)</td\s*>', ' ', text)
    text = TAG_RE.sub('', text)
    text = text.replace('&nbsp;', ' ')
    text = text.replace('&amp;', '&')
    text = text.replace('&quot;', '"')
    text = text.replace('&#39;', "'")
    return normalize_whitespace(text)


def get_charset_hint(data: bytes) -> str:
    head = data[:4096].decode('ascii', errors='ignore')
    xml_match = XML_ENCODING_RE.search(head)
    if xml_match:
        return xml_match.group('charset').lower()
    meta_match = CHARSET_RE.search(head)
    if meta_match:
        return meta_match.group('charset').lower()
    return ''


def read_archive_text(path: Path) -> str:
    data = path.read_bytes()
    charset_hint = get_charset_hint(data)
    candidates: list[str] = []
    if charset_hint:
        candidates.append(charset_hint)
    candidates.extend(['utf-8', 'cp1252', 'latin-1'])
    seen: set[str] = set()
    for candidate in candidates:
        key = candidate.lower()
        if key in seen:
            continue
        seen.add(key)
        try:
            return data.decode(candidate, errors='strict')
        except Exception:
            continue
    return data.decode('latin-1', errors='ignore')


def relative_path(root: Path, path: Path) -> str:
    return str(path.relative_to(root)).replace('/', '\\')


def iter_html_files(root: Path) -> Iterable[Path]:
    for current_root, dirnames, filenames in os.walk(root):
        dirnames.sort(key=str.casefold)
        for filename in sorted(filenames, key=str.casefold):
            if filename.lower().endswith('.html'):
                yield Path(current_root) / filename


def make_logger(run_root: Path) -> logging.Logger:
    logs_dir = run_root / 'logs'
    logs_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(f'user-signature-enrich-{run_root.name}')
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


def get_latest_signature_refine(run_root: Path) -> Path:
    refine_root = run_root / 'signature_refine'
    if not refine_root.exists():
        raise FileNotFoundError(f'signature_refine nao encontrado em {refine_root}')
    candidates = [path for path in refine_root.iterdir() if path.is_dir()]
    if not candidates:
        raise FileNotFoundError(f'nenhuma run em {refine_root}')
    return sorted(candidates, key=lambda item: item.stat().st_mtime, reverse=True)[0]


def enrich_users(args: argparse.Namespace) -> int:
    run_root = Path(args.run_root).resolve()
    manifest = json.loads((run_root / 'manifest.json').read_text(encoding='utf-8'))
    input_root = Path(manifest['input_root'])
    users_path = run_root / 'warehouse' / 'users.jsonl'
    if not users_path.exists():
        raise FileNotFoundError(f'users.jsonl nao encontrado em {users_path}')

    refine_root = Path(args.signature_refine_root).resolve() if args.signature_refine_root else get_latest_signature_refine(run_root)
    profiles_path = refine_root / 'warehouse' / 'signature_profiles.jsonl'
    if not profiles_path.exists():
        raise FileNotFoundError(f'signature_profiles.jsonl nao encontrado em {profiles_path}')

    stamp = datetime.now().strftime('%Y%m%d-%H%M%S-%f')[:19]
    enrich_root = run_root / 'user_signature_enrich' / f'run-{stamp}'
    logger = make_logger(enrich_root)
    logger.info('BOOT | Iniciando enriquecimento de assinaturas em users.jsonl. run_root=%s', run_root)

    users: list[dict[str, Any]] = []
    user_index: dict[str, dict[str, Any]] = {}
    with users_path.open('r', encoding='utf-8') as handle:
        for line in handle:
            if not line.strip():
                continue
            obj = json.loads(line)
            obj['signatures_observed'] = set()
            obj['signature_sources'] = set()
            users.append(obj)
            user_index[obj['user_key']] = obj

    summary = {
        'users_loaded': len(users),
        'asp_signatures_added': 0,
        'phpbb_signatures_added': 0,
        'phpbb_files_scanned': 0,
        'users_with_signatures': 0,
        'warnings': 0,
        'errors': 0,
    }

    with profiles_path.open('r', encoding='utf-8') as handle:
        for line in handle:
            if not line.strip():
                continue
            obj = json.loads(line)
            user = user_index.get(obj['user_key'])
            if not user:
                continue
            signature_text = normalize_whitespace(obj.get('signature_text_example'))
            if not signature_text:
                continue
            before = len(user['signatures_observed'])
            user['signatures_observed'].add(signature_text)
            user['signature_sources'].add('asp_repeated_suffix')
            if len(user['signatures_observed']) > before:
                summary['asp_signatures_added'] += 1

    processed = 0
    for path in iter_html_files(input_root):
        relative = relative_path(input_root, path)
        if '\\phpbb\\page\\viewtopic\\' not in relative.lower():
            continue
        if args.read_limit and processed >= args.read_limit:
            break
        processed += 1
        summary['phpbb_files_scanned'] = processed
        html_text = read_archive_text(path)
        for match in PHPBB_POST_ROW_RE.finditer(html_text):
            message_cell = match.group('message')
            footer_cell = match.group('footer')
            user_id_match = re.search(r'profile\.php\?mode=viewprofile(?:&amp;|&)u=(?P<id>\d+)', footer_cell, flags=re.IGNORECASE)
            if not user_id_match:
                continue
            user_key = f"phpbb:user:{user_id_match.group('id')}"
            user = user_index.get(user_key)
            if not user:
                continue
            signature_matches = re.findall(r'(?is)<td[^>]*height="40"[^>]*class="genmed"[^>]*>(.*?)</td>', message_cell)
            if not signature_matches:
                continue
            signature_text = html_to_text(signature_matches[-1])
            signature_text = re.sub(r'^_+\s*', '', signature_text).strip()
            signature_text = re.split(r'(?is)editado pela.*$', signature_text, maxsplit=1)[0].strip()
            if not signature_text or len(signature_text) < 6:
                continue
            before = len(user['signatures_observed'])
            user['signatures_observed'].add(signature_text)
            user['signature_sources'].add('phpbb_footer_signature')
            if len(user['signatures_observed']) > before:
                summary['phpbb_signatures_added'] += 1
        if processed % args.progress_every == 0:
            logger.info('PHPBB_SCAN | files=%s users_with_signatures=%s', processed, sum(1 for item in users if item['signatures_observed']))

    for user in users:
        user['signatures_observed'] = sorted(user['signatures_observed'], key=str.casefold)
        user['signature_sources'] = sorted(user['signature_sources'], key=str.casefold)
        user['signature_count_observed'] = len(user['signatures_observed'])
        if user['signature_count_observed']:
            summary['users_with_signatures'] += 1

    temp_path = users_path.with_name('users.jsonl.tmp')
    with temp_path.open('w', encoding='utf-8', newline='\n') as handle:
        for user in users:
            handle.write(json.dumps(user, ensure_ascii=False, separators=(',', ':')))
            handle.write('\n')
    temp_path.replace(users_path)

    signatures_writer = (enrich_root / 'warehouse')
    signatures_writer.mkdir(parents=True, exist_ok=True)
    with (signatures_writer / 'user_signatures.jsonl').open('w', encoding='utf-8', newline='\n') as handle:
        for user in users:
            if not user['signatures_observed']:
                continue
            handle.write(json.dumps({
                'user_key': user['user_key'],
                'architecture': user['architecture'],
                'primary_display_name': user.get('primary_display_name'),
                'signature_count_observed': user['signature_count_observed'],
                'signature_sources': user['signature_sources'],
                'signatures_observed': user['signatures_observed'],
            }, ensure_ascii=False, separators=(',', ':')))
            handle.write('\n')

    (enrich_root / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    (enrich_root / 'manifest.json').write_text(json.dumps({
        'run_root': str(run_root),
        'input_root': str(input_root),
        'signature_refine_root': str(refine_root),
        'read_limit': args.read_limit,
        'python_executable': sys.executable,
    }, ensure_ascii=False, indent=2), encoding='utf-8')
    logger.info('DONE | users_with_signatures=%s asp_added=%s phpbb_added=%s', summary['users_with_signatures'], summary['asp_signatures_added'], summary['phpbb_signatures_added'])
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Enriquece users.jsonl com assinaturas observadas de ASP e phpBB.')
    parser.add_argument('--run-root', required=True, help='Diretorio da run completa gerada pelo Build-ForumDataset.py')
    parser.add_argument('--signature-refine-root', default='', help='Run de signature_refine a usar para ASP; padrao: a mais recente')
    parser.add_argument('--read-limit', type=int, default=0, help='Limita quantos arquivos phpBB ler para debug')
    parser.add_argument('--progress-every', type=int, default=5000, help='Intervalo de progresso no console')
    return parser.parse_args()


if __name__ == '__main__':
    try:
        raise SystemExit(enrich_users(parse_args()))
    except Exception as exc:
        print(f'ERRO | {exc}', file=sys.stderr)
        raise
