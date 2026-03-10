#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import html
import json
import logging
import os
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import unquote_to_bytes

MONTHS = {
    'jan': 1, 'janeiro': 1,
    'fev': 2, 'fevereiro': 2,
    'mar': 3, 'marco': 3, 'marÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â§o': 3,
    'abr': 4, 'abril': 4,
    'mai': 5, 'maio': 5,
    'jun': 6, 'junho': 6,
    'jul': 7, 'julho': 7,
    'ago': 8, 'agosto': 8,
    'set': 9, 'setembro': 9,
    'out': 10, 'outubro': 10,
    'nov': 11, 'novembro': 11,
    'dez': 12, 'dezembro': 12,
}

SCRIPT_STYLE_RE = re.compile(r'(?is)<(script|style)\b.*?</\1>')
TAG_RE = re.compile(r'(?is)<[^>]+>')
HREF_RE = re.compile(r'(?is)<a\b[^>]*href\s*=\s*["\']?(?P<url>[^"\' >#]+)')
IMG_RE = re.compile(r'(?is)<img\b[^>]*src\s*=\s*["\']?(?P<url>[^"\' >#]+)')
CHARSET_RE = re.compile(r'(?is)charset\s*=\s*["\']?(?P<charset>[a-zA-Z0-9._-]+)')
XML_ENCODING_RE = re.compile(r'(?is)<\?xml\b[^>]*encoding=["\'](?P<charset>[^"\']+)')
MOJIBAKE_RE = re.compile(r'ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢.|ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡.|FÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢|PÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢|UsuÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢|EndereÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢|LocalizaÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢|NÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Âº')
EMAIL_RE = re.compile(r'(?i)(?P<email>[a-z0-9._%+-]+@[a-z0-9.-]+\\.[a-z]{2,})')
PROFILE_CHROME_PREFIX_RE = re.compile(r'(?i)^\s*(?:exibir\s+perfil|view\s+profile)\s*::\s*')
DISPLAY_NAME_NOISE_RE = re.compile(r'(?i)^(?:f[oÃ³]rum\s+de\s+)?anime\s*-\s*sobresites$')

ASP_TOPIC_ROW_RE = re.compile(
    r'(?is)<tr>\s*<td\b[^>]*bgcolor="?(?:F8F8F8|white)"?[^>]*>(?P<author>.*?)</td>\s*<td\b[^>]*colspan="2"[^>]*>(?P<message>.*?)</td>\s*</tr>'
)
PHPBB_POST_ROW_RE = re.compile(
    r'(?is)<tr>\s*<td\b[^>]*rowspan="2"[^>]*>(?P<author>.*?)</td>\s*<td\b[^>]*valign="top"[^>]*>(?P<message>.*?)</td>\s*</tr>\s*<tr>\s*<td\b(?=[^>]*valign="bottom")(?=[^>]*nowrap="nowrap")(?=[^>]*class="row[12]")[^>]*>(?P<footer>.*?)</td>\s*</tr>'
)
ASP_HIDDEN_RE = re.compile(r'(?is)<input\s+name="(?P<name>[^"]+)"\s+type="hidden"\s+value="(?P<value>[^"]*)">')


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


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
        ensure_dir(path.parent)
        self.path = path
        self.handle = path.open('w', encoding='utf-8', newline='\n', buffering=65536)

    def write(self, payload: dict[str, Any]) -> None:
        self.handle.write(json.dumps(payload, ensure_ascii=False, separators=(',', ':')))
        self.handle.write('\n')

    def close(self) -> None:
        self.handle.flush()
        self.handle.close()


def sort_values(values: Iterable[str]) -> list[str]:
    return sorted({value for value in values if value}, key=str.casefold)


def decode_html(text: str) -> str:
    return html.unescape(text or '')


def normalize_whitespace(text: str | None) -> str:
    if not text:
        return ''
    value = decode_html(text)
    value = value.replace('\r', '')
    value = value.replace('\xa0', ' ')
    value = re.sub(r'[ \t]+', ' ', value)
    value = re.sub(r'\n{3,}', '\n\n', value)
    return value.strip()

def sanitize_display_name(text: str | None) -> str:
    value = normalize_whitespace(text)
    while value:
        cleaned = PROFILE_CHROME_PREFIX_RE.sub('', value).strip()
        if cleaned == value:
            break
        value = cleaned
    if DISPLAY_NAME_NOISE_RE.match(value):
        return ''
    return value


def html_to_text(raw_html: str | None) -> str:
    if not raw_html:
        return ''
    text = SCRIPT_STYLE_RE.sub('', raw_html)
    text = re.sub(r'(?i)<br\s*/?>', '\n', text)
    text = re.sub(r'(?i)</p\s*>', '\n\n', text)
    text = re.sub(r'(?i)</tr\s*>', '\n', text)
    text = re.sub(r'(?i)</td\s*>', ' ', text)
    text = TAG_RE.sub('', text)
    return normalize_whitespace(text)


def markup_to_text(text: str | None) -> str:
    if not text:
        return ''
    value = decode_html(text)
    value = re.sub(r'(?is)\[img\](.*?)\[/img\]', r' \1 ', value)
    value = re.sub(r'(?is)\[url=(.*?)\](.*?)\[/url\]', r' \2 (\1) ', value)
    value = re.sub(r'(?is)\[url\](.*?)\[/url\]', r' \1 ', value)
    value = re.sub(r'(?is)\[[^\]]+\]', '', value)
    return normalize_whitespace(value)


def get_links(raw_html: str | None) -> list[str]:
    if not raw_html:
        return []
    links = {normalize_whitespace(match.group('url')) for match in HREF_RE.finditer(raw_html)}
    links.update(normalize_whitespace(match.group('url')) for match in IMG_RE.finditer(raw_html))
    return sort_values(links)


def extract_balanced_tag_contents(raw_html: str, start_pattern: str, tag_name: str) -> str:
    start_match = re.search(start_pattern, raw_html, flags=re.IGNORECASE | re.DOTALL)
    if not start_match:
        return ''

    token_re = re.compile(rf'(?is)<(/?){tag_name}\b[^>]*>')
    depth = 1
    for token in token_re.finditer(raw_html, start_match.end()):
        if token.group(1):
            depth -= 1
        else:
            depth += 1
        if depth == 0:
            return raw_html[start_match.end():token.start()]
    return ''


def extract_phpbb_author_metadata(author_cell: str) -> tuple[str, str]:
    detail_match = re.search(r'(?is)<span class="postdetails">(?P<details>.*?)</span>', author_cell)
    details_text = html_to_text(detail_match.group('details')) if detail_match else ''
    detail_lines = [line.strip() for line in details_text.splitlines() if line.strip()]

    role_label = ''
    location = ''
    for line in detail_lines:
        if re.match(r'(?i)^mensagens:\s*\d+\s*$', line):
            continue
        location_match = re.match(r'(?i)^localiza\S*:\s*(?P<loc>.+)$', line)
        if location_match:
            location = normalize_whitespace(location_match.group('loc'))
            continue
        if not role_label:
            role_label = normalize_whitespace(line)

    if not location:
        location_match = re.search(r'(?i)Localiza\S*:\s*(?P<loc>[^<]+)', author_cell)
        if location_match:
            location = normalize_whitespace(location_match.group('loc'))

    return role_label, location


def get_charset_hint(data: bytes) -> str:
    head = data[:4096].decode('ascii', errors='ignore')
    xml_match = XML_ENCODING_RE.search(head)
    if xml_match:
        return xml_match.group('charset').lower()
    meta_match = CHARSET_RE.search(head)
    if meta_match:
        return meta_match.group('charset').lower()
    return ''


def looks_mojibake(text: str) -> bool:
    if not text:
        return False
    if 'ÃƒÆ’Ã‚Â¯Ãƒâ€šÃ‚Â¿Ãƒâ€šÃ‚Â½' in text:
        return True
    strong_tokens = (
        'F?',
        'P?',
        'Usu?',
        'Endere?',
        'Localiza?',
        'N??',
        '??',
        '??',
        '??',
        '??',
        '??',
        '??',
        '??',
        '? ',
    )
    if any(token in text for token in strong_tokens):
        return True
    return len(MOJIBAKE_RE.findall(text)) >= 2


def text_score(text: str) -> int:
    if not text:
        return -999
    score = 0
    for token in ('UsuÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡rio', 'UsuÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡rios', 'PÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡gina', 'FÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³rum', 'SÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â£o', 'EndereÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â§o', 'LocalizaÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â§ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â£o', 'Registrado', 'Mensagens'):
        score += text.count(token) * 5
    score -= len(MOJIBAKE_RE.findall(text)) * 7
    score -= text.count('\ufffd') * 10
    return score


def maybe_repair_mojibake(text: str) -> tuple[str, str | None]:
    if not looks_mojibake(text):
        return text, None
    best_text = text
    best_score = text_score(text)
    best_tag = None
    for source_encoding in ('latin-1', 'cp1252'):
        try:
            candidate = text.encode(source_encoding, errors='strict').decode('utf-8', errors='strict')
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
        candidate_score = text_score(candidate)
        if candidate_score > best_score + 3:
            best_text = candidate
            best_score = candidate_score
            best_tag = f'{source_encoding}->utf-8'
    return best_text, best_tag


def read_archive_text(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    charset_hint = get_charset_hint(data)
    decoder = 'cp1252'
    if 'utf-8' in charset_hint:
        text = data.decode('utf-8', errors='strict')
        decoder = 'utf-8'
    elif any(token in charset_hint for token in ('iso-8859-1', 'latin-1', 'windows-1252', 'cp1252')):
        try:
            text = data.decode('cp1252', errors='strict')
        except UnicodeDecodeError:
            text = data.decode('latin-1', errors='strict')
            decoder = 'latin-1'
    else:
        try:
            text = data.decode('utf-8', errors='strict')
            decoder = 'utf-8'
        except UnicodeDecodeError:
            try:
                text = data.decode('cp1252', errors='strict')
            except UnicodeDecodeError:
                text = data.decode('latin-1', errors='strict')
                decoder = 'latin-1'
    text, repaired_from = maybe_repair_mojibake(text)
    return {
        'text': text,
        'decoder': decoder,
        'charset_hint': charset_hint,
        'mojibake': looks_mojibake(text),
        'repaired_from': repaired_from,
    }

def relative_path(root: Path, path: Path) -> str:
    return str(path.relative_to(root)).replace('/', '\\')


def get_domain(path: Path) -> str:
    parts = [part.lower() for part in path.parts]
    try:
        index = parts.index('normalized')
    except ValueError:
        return 'unknown_domain'
    if index + 1 < len(parts):
        return parts[index + 1]
    return 'unknown_domain'


def get_page_kind(relative: str) -> str:
    path = relative.replace('\\', '/').lower()
    if '/page/topic/' in path:
        return 'asp_topic'
    if '/page/post/' in path:
        return 'asp_post'
    if '/page/viewtopic/' in path:
        return 'phpbb_viewtopic'
    if '/page/profile/' in path and '/asp/' in path:
        return 'asp_profile'
    if '/page/profile/' in path and '/phpbb/' in path:
        return 'phpbb_profile'
    if '/page/members/' in path:
        return 'asp_members'
    if '/page/memberlist/' in path:
        return 'phpbb_memberlist'
    return 'skip'


def get_path_id(text: str, pattern: str) -> str:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    return match.group(1) if match else ''


def parse_date(raw: str | None) -> dict[str, str | None]:
    clean = normalize_whitespace(raw)
    result: dict[str, str | None] = {'raw': clean or None, 'iso_local': None}
    if not clean:
        return result

    match = re.search(r'(?P<d>\d{1,2})/(?P<m>\d{1,2})/(?P<y>\d{4})(?:\D+(?P<h>\d{1,2}):(?P<n>\d{2})(?::(?P<s>\d{2}))?)?', clean)
    if match:
        day = int(match.group('d'))
        month = int(match.group('m'))
        year = int(match.group('y'))
        hour = int(match.group('h') or 0)
        minute = int(match.group('n') or 0)
        second = int(match.group('s') or 0)
        result['iso_local'] = f'{year:04d}-{month:02d}-{day:02d}T{hour:02d}:{minute:02d}:{second:02d}'
        return result

    match = re.search(r'(?i)(?P<mon>jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)[a-zÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â§]*\s+(?P<d>\d{1,2}),\s+(?P<y>\d{4})\s+(?P<h>\d{1,2}):(?P<n>\d{2})\s*(?P<ampm>am|pm)', clean)
    if match:
        month = MONTHS[match.group('mon').lower()]
        day = int(match.group('d'))
        year = int(match.group('y'))
        hour = int(match.group('h'))
        minute = int(match.group('n'))
        ampm = match.group('ampm').lower()
        if ampm == 'pm' and hour < 12:
            hour += 12
        elif ampm == 'am' and hour == 12:
            hour = 0
        result['iso_local'] = f'{year:04d}-{month:02d}-{day:02d}T{hour:02d}:{minute:02d}:00'
        return result

    match = re.search(r'(?i)(?P<d>\d{1,2})\s+de\s+(?P<mon>[a-zÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â§]+)\s+de\s+(?P<y>\d{4})', clean)
    if match:
        month_name = match.group('mon').lower()
        if month_name in MONTHS:
            day = int(match.group('d'))
            month = MONTHS[month_name]
            year = int(match.group('y'))
            result['iso_local'] = f'{year:04d}-{month:02d}-{day:02d}T00:00:00'
    return result


def get_role_class(role_label: str | None) -> str:
    role = normalize_whitespace(role_label)
    if not role:
        return 'unknown'
    if re.fullmatch(r'Administrador', role, flags=re.IGNORECASE):
        return 'administrator'
    if re.fullmatch(r'Moderador', role, flags=re.IGNORECASE):
        return 'moderator'
    if re.fullmatch(r'Moderador\s+J[ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Âºu]nior', role, flags=re.IGNORECASE):
        return 'decorative_rank'
    if re.search(r'Estreante|J[ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Âºu]nior|Membro|Veterano', role, flags=re.IGNORECASE):
        return 'member_rank'
    return 'custom_rank'


def normalize_alias(value: str | None) -> str:
    text = normalize_whitespace(value)
    if not text:
        return ''
    text = unicodedata.normalize('NFKD', text)
    text = ''.join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r'\s+', ' ', text).strip().casefold()
    return text


def url_decode(text: str | None) -> str:
    if not text:
        return ''
    try:
        raw = unquote_to_bytes(text.replace('+', ' '))
    except Exception:
        return normalize_whitespace(text)
    try:
        value = raw.decode('utf-8', errors='strict')
    except UnicodeDecodeError:
        value = raw.decode('cp1252', errors='strict')
    value, _ = maybe_repair_mojibake(value)
    return normalize_whitespace(value)


def update_date_bounds(record: dict[str, Any], iso_local: str | None, raw: str | None) -> None:
    if not iso_local:
        return
    if not record['first_seen_at'] or iso_local < record['first_seen_at']:
        record['first_seen_at'] = iso_local
        record['first_seen_at_raw'] = raw
    if not record['last_seen_at'] or iso_local > record['last_seen_at']:
        record['last_seen_at'] = iso_local
        record['last_seen_at_raw'] = raw


class Context:
    def __init__(self, input_root: Path, run_root: Path, args: argparse.Namespace) -> None:
        self.input_root = input_root
        self.run_root = run_root
        self.args = args
        self.summary: dict[str, int] = {
            'processed_files': 0,
            'skipped_files': 0,
            'parsed_files': 0,
            'posts_emitted': 0,
            'salvage_records': 0,
            'salvage_promoted': 0,
            'topic_stubs_skipped': 0,
            'merged_identities': 0,
            'warnings': 0,
            'errors': 0,
        }
        self.topics: dict[str, dict[str, Any]] = {}
        self.users: dict[str, dict[str, Any]] = {}
        self.seen_post_keys: set[str] = set()
        self.seen_salvage_keys: set[str] = set()
        self.post_body_index: dict[str, str] = {}
        self.pending_salvage: dict[str, dict[str, Any]] = {}
        self.kind_filter = {kind.lower() for kind in args.kinds}
        self.logger = self._build_logger()
        self.writers = {
            'posts': JsonlWriter(run_root / 'warehouse' / 'posts.jsonl'),
            'post_salvage': JsonlWriter(run_root / 'warehouse' / 'post_salvage.jsonl'),
            'topics': JsonlWriter(run_root / 'warehouse' / 'topics.jsonl'),
            'users': JsonlWriter(run_root / 'warehouse' / 'users.jsonl'),
            'merged_identities': JsonlWriter(run_root / 'warehouse' / 'merged_identities.jsonl'),
            'knowledge_posts': JsonlWriter(run_root / 'knowledge' / 'knowledge_posts.jsonl'),
        }

    def _build_logger(self) -> logging.Logger:
        ensure_dir(self.run_root / 'logs')
        logger = logging.getLogger(f'forum-dataset-{self.run_root.name}')
        logger.setLevel(logging.INFO)
        logger.handlers.clear()
        logger.propagate = False

        formatter = logging.Formatter('%(asctime)s | %(levelname)s | %(message)s', '%Y-%m-%dT%H:%M:%S')

        console = logging.StreamHandler(sys.stdout)
        console.setLevel(logging.INFO)
        console.setFormatter(formatter)
        logger.addHandler(console)

        run_file = logging.FileHandler(self.run_root / 'logs' / 'run.log', encoding='utf-8')
        run_file.setLevel(logging.INFO)
        run_file.setFormatter(formatter)
        logger.addHandler(run_file)

        warning_file = logging.FileHandler(self.run_root / 'logs' / 'warnings.log', encoding='utf-8')
        warning_file.setLevel(logging.WARNING)
        warning_file.addFilter(ExactLevelFilter(logging.WARNING))
        warning_file.setFormatter(formatter)
        logger.addHandler(warning_file)

        error_file = logging.FileHandler(self.run_root / 'logs' / 'errors.log', encoding='utf-8')
        error_file.setLevel(logging.ERROR)
        error_file.addFilter(MinLevelFilter(logging.ERROR))
        error_file.setFormatter(formatter)
        logger.addHandler(error_file)
        return logger

    def info(self, message: str) -> None:
        self.logger.info(message)

    def warn(self, message: str) -> None:
        self.summary['warnings'] += 1
        self.logger.warning(message)

    def error(self, message: str) -> None:
        self.summary['errors'] += 1
        self.logger.error(message)

    def close(self) -> None:
        for writer in self.writers.values():
            writer.close()
        for handler in self.logger.handlers[:]:
            handler.flush()
            handler.close()
            self.logger.removeHandler(handler)

    def ensure_topic(self, topic_key: str, architecture: str, topic_id: str) -> dict[str, Any]:
        topic = self.topics.get(topic_key)
        if topic is None:
            topic = {
                'topic_key': topic_key,
                'architecture': architecture,
                'topic_id': topic_id,
                'forum_key': None,
                'forum_id': None,
                'forum_title': '',
                'topic_title': '',
                'post_count': 0,
                'author_keys': set(),
                'author_display_names': set(),
                'observed_domains': set(),
                'first_seen_at': None,
                'first_seen_at_raw': None,
                'last_seen_at': None,
                'last_seen_at_raw': None,
                'first_source_file': None,
                'source_page_count': 0,
                'has_primary_source': False,
                'has_salvage_source': False,
            }
            self.topics[topic_key] = topic
        return topic

    def ensure_user(self, user_key: str, architecture: str, user_id: str) -> dict[str, Any]:
        user = self.users.get(user_key)
        if user is None:
            user = {
                'user_key': user_key,
                'architecture': architecture,
                'user_id': user_id,
                'primary_display_name': None,
                'aliases': set(),
                'role_labels': set(),
                'role_classes': set(),
                'locations': set(),
                'homepages': set(),
                'emails': set(),
                'occupations': set(),
                'interests': set(),
                'member_since': None,
                'member_since_raw': None,
                'post_count_observed': 0,
                'profile_count': 0,
                'observed_domains': set(),
                'first_seen_at': None,
                'first_seen_at_raw': None,
                'last_seen_at': None,
                'last_seen_at_raw': None,
                'first_source_file': None,
                'source_page_count': 0,
            }
            self.users[user_key] = user
        return user

    def update_user(
        self,
        user: dict[str, Any],
        *,
        display_name: str = '',
        role_label: str = '',
        location: str = '',
        homepage: str = '',
        occupation: str = '',
        interests: str = '',
        member_since_iso: str | None = None,
        member_since_raw: str | None = None,
        observed_at_iso: str | None = None,
        observed_at_raw: str | None = None,
        domain: str = '',
        relative_path: str = '',
    ) -> None:
        name = sanitize_display_name(display_name)
        if name:
            if not user['primary_display_name']:
                user['primary_display_name'] = name
            user['aliases'].add(name)

        role = normalize_whitespace(role_label)
        if role:
            user['role_labels'].add(role)
            user['role_classes'].add(get_role_class(role))

        for field_name, raw_value in (
            ('locations', location),
            ('homepages', homepage),
            ('occupations', occupation),
            ('interests', interests),
        ):
            value = normalize_whitespace(raw_value)
            if value:
                user[field_name].add(value)

        if member_since_iso and (not user['member_since'] or member_since_iso < user['member_since']):
            user['member_since'] = member_since_iso
            user['member_since_raw'] = member_since_raw

        if domain:
            user['observed_domains'].add(domain)
        if relative_path and not user['first_source_file']:
            user['first_source_file'] = relative_path
        if relative_path:
            user['source_page_count'] += 1
        update_date_bounds(user, observed_at_iso, observed_at_raw)

    def add_observed_emails(self, user: dict[str, Any], html_fragment: str) -> None:
        for match in EMAIL_RE.finditer(html_fragment or ''):
            user['emails'].add(match.group('email').lower())

    def register_primary_post(self, payload: dict[str, Any]) -> bool:
        post_key = payload['post_key']
        if post_key in self.seen_post_keys:
            return False
        self.seen_post_keys.add(post_key)
        self.post_body_index[post_key] = normalize_whitespace(payload.get('body_text') or '')
        self.writers['posts'].write(payload)
        self.writers['knowledge_posts'].write({
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
            'text': self.build_knowledge_text(payload),
            'first_source_file': payload['first_source_file'],
        })
        self.summary['posts_emitted'] += 1
        return True

    def build_knowledge_text(self, payload: dict[str, Any]) -> str:
        lines = []
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

    def register_salvage(self, payload: dict[str, Any]) -> bool:
        salvage_key = payload['salvage_key']
        if salvage_key in self.seen_salvage_keys:
            return False
        self.seen_salvage_keys.add(salvage_key)
        self.pending_salvage[salvage_key] = payload
        return True


def parse_asp_topic(ctx: Context, relative: str, domain: str, source_html: str) -> None:
    topic_id = get_path_id(relative, r'TOPIC_ID_(\d+)')
    forum_id = get_path_id(relative, r'FORUM_ID_(\d+)')
    meta = re.search(
        r'post\.asp\?method=Reply[^\"]*TOPIC_ID=(?P<topic>\d+)&FORUM_ID=(?P<forum>\d+)(?:&CAT_ID=(?P<cat>\d+))?(?:&Forum_Title=(?P<forumTitle>[^\"&]+))?(?:&Topic_Title=(?P<topicTitle>[^\"&]+))?',
        source_html,
        flags=re.IGNORECASE,
    )
    forum_title = url_decode(meta.group('forumTitle')) if meta else ''
    topic_title = url_decode(meta.group('topicTitle')) if meta else ''
    if not topic_id and meta:
        topic_id = meta.group('topic')
    if not forum_id and meta:
        forum_id = meta.group('forum')
    if not topic_id:
        ctx.warn(f'PARSE | ASP topic sem TOPIC_ID | {relative}')
        return

    topic_key = f'asp:topic:{topic_id}'
    topic = ctx.ensure_topic(topic_key, 'asp', topic_id)
    if forum_id:
        topic['forum_key'] = f'asp:forum:{forum_id}'
        topic['forum_id'] = forum_id
    if forum_title:
        topic['forum_title'] = forum_title
    if topic_title:
        topic['topic_title'] = topic_title
    topic['observed_domains'].add(domain)
    if not topic['first_source_file']:
        topic['first_source_file'] = relative
    topic['source_page_count'] += 1
    topic['has_primary_source'] = True

    for match in ASP_TOPIC_ROW_RE.finditer(source_html):
        author_cell = match.group('author')
        message_cell = match.group('message')
        post_id_match = re.search(r'(?is)<a name="(?P<id>\d+)"></a>', message_cell)
        if not post_id_match:
            continue
        post_id = post_id_match.group('id')
        user_id_match = re.search(r'pop_profile\.asp\?mode=display&id=(?P<id>\d+)', author_cell, flags=re.IGNORECASE)
        user_id = user_id_match.group('id') if user_id_match else ''
        author_match = re.search(r'(?is)<b>(?P<name>.*?)</a>', author_cell)
        author_name = html_to_text(author_match.group('name')) if author_match else 'Visitante'
        smalls = re.findall(r'(?is)<small>(.*?)</small>', author_cell)
        role_label = html_to_text(smalls[0]) if len(smalls) >= 1 else ''
        location = html_to_text(smalls[1]) if len(smalls) >= 2 else ''
        message_count_text = html_to_text(smalls[2]) if len(smalls) >= 3 else ''
        count_match = re.search(r'(?P<n>\d+)', message_count_text)
        message_count = int(count_match.group('n')) if count_match else 0
        date_match = re.search(r'(?is)Enviado em\s*(?P<date>.*?)</font>', message_cell)
        date = parse_date(date_match.group('date') if date_match else '')
        body_match = re.search(r'(?is)<hr[^>]*>\s*(?P<body>.*)$', message_cell)
        body_html = body_match.group('body') if body_match else message_cell
        body_html = re.sub(r'(?is)<a href="#top".*$', '', body_html)
        body_text = html_to_text(body_html)
        if not body_text:
            continue

        author_key = None
        if user_id:
            author_key = f'asp:user:{user_id}'
            user = ctx.ensure_user(author_key, 'asp', user_id)
            ctx.update_user(
                user,
                display_name=author_name,
                role_label=role_label,
                location=location,
                observed_at_iso=date['iso_local'],
                observed_at_raw=date['raw'],
                domain=domain,
                relative_path=relative,
            )
            if message_count > user['post_count_observed']:
                user['post_count_observed'] = message_count

        topic['author_display_names'].add(author_name)
        if author_key:
            topic['author_keys'].add(author_key)
        topic['post_count'] += 1
        update_date_bounds(topic, date['iso_local'], date['raw'])

        ctx.register_primary_post({
            'post_key': f'asp:post:{post_id}',
            'architecture': 'asp',
            'source_page_kind': 'topic',
            'observed_domains': [domain],
            'topic_key': topic_key,
            'topic_id': topic_id,
            'topic_title': topic['topic_title'],
            'forum_key': topic['forum_key'],
            'forum_id': topic['forum_id'],
            'forum_title': topic['forum_title'],
            'author_key': author_key,
            'author_display': author_name,
            'role_label': role_label,
            'role_classification': get_role_class(role_label),
            'deleted_or_guest': not bool(user_id),
            'location_raw': location,
            'posted_at': date['iso_local'],
            'posted_at_raw': date['raw'],
            'body_text': body_text,
            'links': get_links(body_html),
            'first_source_file': relative,
        })


def parse_phpbb_viewtopic(ctx: Context, relative: str, domain: str, source_html: str) -> None:
    topic_id_match = re.search(r'viewtopic\.php\?t=(?P<id>\d+)', source_html, flags=re.IGNORECASE)
    if not topic_id_match:
        topic_id_match = re.search(r'viewtopic\.php_t_(?P<id>\d+)', relative, flags=re.IGNORECASE)
    if not topic_id_match:
        ctx.warn(f'PARSE | phpBB viewtopic sem topic id | {relative}')
        return
    topic_id = topic_id_match.group('id')
    forum_id_match = re.search(r'viewforum\.php\?f=(?P<id>\d+)', source_html, flags=re.IGNORECASE)
    forum_id = forum_id_match.group('id') if forum_id_match else ''
    forum_title_match = re.search(r'(?is)<td width="100%" class="nav"><a href="index\.php[^\"]*">.*?</a>\s*&gt;\s*<a href="viewforum\.php\?f=\d+[^\"]*">(?P<title>.*?)</a>', source_html)
    forum_title = html_to_text(forum_title_match.group('title')) if forum_title_match else ''
    topic_title_match = re.search(r'(?is)<td class="maintitle"[^>]*>(?P<title>.*?)</td>', source_html)
    topic_title = html_to_text(topic_title_match.group('title')) if topic_title_match else ''

    topic_key = f'phpbb:topic:{topic_id}'
    topic = ctx.ensure_topic(topic_key, 'phpbb', topic_id)
    if forum_id:
        topic['forum_key'] = f'phpbb:forum:{forum_id}'
        topic['forum_id'] = forum_id
    if forum_title:
        topic['forum_title'] = forum_title
    if topic_title:
        topic['topic_title'] = topic_title
    topic['observed_domains'].add(domain)
    if not topic['first_source_file']:
        topic['first_source_file'] = relative
    topic['source_page_count'] += 1
    topic['has_primary_source'] = True

    for match in PHPBB_POST_ROW_RE.finditer(source_html):
        author_cell = match.group('author')
        message_cell = match.group('message')
        footer_cell = match.group('footer')
        post_id_match = re.search(r'viewtopic\.php\?p=(?P<id>\d+)', message_cell, flags=re.IGNORECASE)
        if not post_id_match:
            post_id_match = re.search(r'viewtopic\.php_p_(?P<id>\d+)', relative, flags=re.IGNORECASE)
        if not post_id_match:
            continue
        post_id = post_id_match.group('id')
        author_name_match = re.search(r'(?is)<strong>(?P<name>.*?)</strong>', author_cell)
        author_name = html_to_text(author_name_match.group('name')) if author_name_match else 'Visitante'
        role_label, location = extract_phpbb_author_metadata(author_cell)
        messages_match = re.search(r'Mensagens:\s*(?P<n>\d+)', author_cell, flags=re.IGNORECASE)
        message_count = int(messages_match.group('n')) if messages_match else 0
        user_id_match = re.search(r'profile\.php\?mode=viewprofile(?:&amp;|&)u=(?P<id>\d+)', footer_cell, flags=re.IGNORECASE)
        user_id = user_id_match.group('id') if user_id_match else ''
        date_match = re.search(r'(?is)Enviada:\s*(?P<date>.*?)</td>', message_cell)
        date = parse_date(date_match.group('date') if date_match else '')
        body_html = extract_balanced_tag_contents(message_cell, r'<td[^>]*class="postbody"[^>]*>', 'td')
        body_html = re.sub(r'(?is)^\s*<hr\s*/?>', '', body_html)
        body_text = html_to_text(body_html)
        if not body_text:
            continue

        author_key = None
        if user_id:
            author_key = f'phpbb:user:{user_id}'
            user = ctx.ensure_user(author_key, 'phpbb', user_id)
            ctx.update_user(
                user,
                display_name=author_name,
                role_label=role_label,
                location=location,
                observed_at_iso=date['iso_local'],
                observed_at_raw=date['raw'],
                domain=domain,
                relative_path=relative,
            )
            if message_count > user['post_count_observed']:
                user['post_count_observed'] = message_count

        topic['author_display_names'].add(author_name)
        if author_key:
            topic['author_keys'].add(author_key)
        topic['post_count'] += 1
        update_date_bounds(topic, date['iso_local'], date['raw'])

        ctx.register_primary_post({
            'post_key': f'phpbb:post:{post_id}',
            'architecture': 'phpbb',
            'source_page_kind': 'viewtopic',
            'observed_domains': [domain],
            'topic_key': topic_key,
            'topic_id': topic_id,
            'topic_title': topic['topic_title'],
            'forum_key': topic['forum_key'],
            'forum_id': topic['forum_id'],
            'forum_title': topic['forum_title'],
            'author_key': author_key,
            'author_display': author_name,
            'role_label': role_label,
            'role_classification': get_role_class(role_label),
            'deleted_or_guest': bool(re.match(r'^(visitante|guest)$', author_name, flags=re.IGNORECASE)) or not bool(user_id),
            'location_raw': location,
            'posted_at': date['iso_local'],
            'posted_at_raw': date['raw'],
            'body_text': body_text,
            'links': get_links(body_html),
            'first_source_file': relative,
        })


def parse_asp_post(ctx: Context, relative: str, domain: str, source_html: str) -> None:
    topic_id = get_path_id(relative, r'TOPIC_ID_(\d+)')
    reply_id = get_path_id(relative, r'REPLY_ID_(\d+)')
    forum_id = get_path_id(relative, r'FORUM_ID_(\d+)')
    forum_title = ''
    topic_title = ''
    author_id = ''

    for match in ASP_HIDDEN_RE.finditer(source_html):
        key = match.group('name').upper()
        value = match.group('value')
        if key == 'TOPIC_ID' and not topic_id:
            topic_id = value
        elif key == 'REPLY_ID' and not reply_id:
            reply_id = value
        elif key == 'FORUM_ID' and not forum_id:
            forum_id = value
        elif key == 'FORUM_TITLE' and not forum_title:
            forum_title = normalize_whitespace(value)
        elif key == 'TOPIC_TITLE' and not topic_title:
            topic_title = normalize_whitespace(value)
        elif key == 'AUTHOR' and not author_id:
            author_id = value

    if not forum_title:
        forum_title = url_decode(get_path_id(relative, r'Forum_Title_([^_].*?)_M(?:_|\.|$)'))
    if not topic_title:
        topic_title = url_decode(get_path_id(relative, r'Topic_Title_([^_].*?)_method'))

    quote_match = re.search(r'(?is)<textarea[^>]*name="?(?:Message|message)"?[^>]*>(?P<body>.*?)</textarea>', source_html)
    quote_text = markup_to_text(quote_match.group('body')) if quote_match else ''
    if not topic_id:
        ctx.warn(f'PARSE | ASP post sem TOPIC_ID | {relative}')
        return

    topic_key = f'asp:topic:{topic_id}'
    topic = ctx.ensure_topic(topic_key, 'asp', topic_id)
    if forum_id:
        topic['forum_key'] = f'asp:forum:{forum_id}'
        topic['forum_id'] = forum_id
    if forum_title:
        topic['forum_title'] = forum_title
    if topic_title:
        topic['topic_title'] = topic_title
    topic['observed_domains'].add(domain)
    if not topic['first_source_file']:
        topic['first_source_file'] = relative
    topic['source_page_count'] += 1
    topic['has_salvage_source'] = True

    author_key = f'asp:user:{author_id}' if author_id else None
    candidate_post_key = f'asp:post:{reply_id}' if reply_id else None
    existing_body = ctx.post_body_index.get(candidate_post_key or '')
    quote_key_material = f'{relative}|{quote_text}'
    salvage_key = f'salvage:{hashlib.sha1(quote_key_material.encode("utf-8")).hexdigest()}'
    known_author_display = ''
    if author_key and author_key in ctx.users:
        known_author_display = ctx.users[author_key].get('primary_display_name') or ''

    if not quote_text:
        return
    if existing_body and normalize_whitespace(existing_body) == normalize_whitespace(quote_text):
        return
    ctx.register_salvage({
        'salvage_key': salvage_key,
        'candidate_post_key': candidate_post_key,
        'architecture': 'asp',
        'source_page_kind': 'post_quote_salvage',
        'topic_key': topic_key,
        'topic_id': topic_id,
        'topic_title': topic['topic_title'],
        'forum_key': topic['forum_key'],
        'forum_id': topic['forum_id'],
        'forum_title': topic['forum_title'],
        'author_key': author_key,
        'author_display': known_author_display or None,
        'body_text': quote_text,
        'links': [],
        'first_source_file': relative,
    })


def parse_asp_profile(ctx: Context, relative: str, domain: str, source_html: str) -> None:
    user_id = get_path_id(relative, r'id_(\d+)') or get_path_id(relative, r'id=(\d+)')
    if not user_id:
        user_id = get_path_id(source_html, r'pop_profile\.asp\?mode=display&id=(\d+)')
    if not user_id:
        ctx.warn(f'PARSE | ASP profile sem user id | {relative}')
        return

    user = ctx.ensure_user(f'asp:user:{user_id}', 'asp', user_id)
    display_match = re.search(r'(?is)Usu[aÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡]rio:?\s*</font></b></td>\s*<td[^>]*><font[^>]*>(?P<name>.*?)</font>', source_html)
    if not display_match:
        display_match = re.search(r'(?is)<td[^>]*valign=top[^>]*align=left[^>]*bgcolor="?618F9E"?[^>]*>\s*<font[^>]*><b>&nbsp;\s*(?P<name>.*?)\s*</b></font>\s*</td>', source_html)
    if not display_match:
        display_match = re.search(r'(?is)<title>[^<]*?(?:de|do)\s+(?P<name>[^<]+)</title>', source_html)
    display_name = sanitize_display_name(html_to_text(display_match.group('name')) if display_match else '')
    member_since_match = re.search(r'(?is)(?:Membro desde|Registrado em):&nbsp;</font></b></td>\s*<td[^>]*><font[^>]*>(?P<date>.*?)</font>', source_html)
    member_since = parse_date(member_since_match.group('date') if member_since_match else '')
    location_match = re.search(r'(?is)(?:Localiza(?:ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â§|&ccedil;)ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â£o|Cidade):&nbsp;</font></b></td>\s*<td[^>]*><font[^>]*>(?P<value>.*?)</font>', source_html)
    location = html_to_text(location_match.group('value')) if location_match else ''
    homepage_match = re.search(r'(?is)Homepage:&nbsp;</font></b></td>\s*<td[^>]*><font[^>]*><a href="(?P<url>[^"]+)"', source_html)
    homepage = normalize_whitespace(homepage_match.group('url')) if homepage_match else ''

    ctx.update_user(
        user,
        display_name=display_name,
        location=location,
        homepage=homepage,
        member_since_iso=member_since['iso_local'],
        member_since_raw=member_since['raw'],
        observed_at_iso=member_since['iso_local'],
        observed_at_raw=member_since['raw'],
        domain=domain,
        relative_path=relative,
    )
    user['profile_count'] += 1
    ctx.add_observed_emails(user, source_html)


def parse_phpbb_profile(ctx: Context, relative: str, domain: str, source_html: str) -> None:
    user_id = get_path_id(relative, r'u_(\d+)') or get_path_id(source_html, r'profile\.php\?mode=viewprofile(?:&amp;|&)u=(\d+)')
    if not user_id:
        ctx.warn(f'PARSE | phpBB profile sem user id | {relative}')
        return

    user = ctx.ensure_user(f'phpbb:user:{user_id}', 'phpbb', user_id)
    display_match = re.search(r'(?is)<th[^>]*colspan="2"[^>]*>(?P<name>.*?)</th>', source_html)
    display_name = sanitize_display_name(html_to_text(display_match.group('name')) if display_match else '')
    registered_match = re.search(r'(?is)Registrado em:</td>\s*<td[^>]*>(?P<value>.*?)</td>', source_html)
    registered = parse_date(registered_match.group('value') if registered_match else '')
    location_match = re.search(r'(?is)Localiza(?:ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â§|&ccedil;)ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â£o:</td>\s*<td[^>]*>(?P<value>.*?)</td>', source_html)
    location = html_to_text(location_match.group('value')) if location_match else ''
    occupation_match = re.search(r'(?is)Ocupa(?:ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â§|&ccedil;)ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â£o:</td>\s*<td[^>]*>(?P<value>.*?)</td>', source_html)
    occupation = html_to_text(occupation_match.group('value')) if occupation_match else ''
    interest_match = re.search(r'(?is)Interesses:</td>\s*<td[^>]*>(?P<value>.*?)</td>', source_html)
    interests = html_to_text(interest_match.group('value')) if interest_match else ''
    homepage_match = re.search(r'(?is)P[aÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡]gina/WWW:</td>\s*<td[^>]*>(?P<value>.*?)</td>', source_html)
    homepage = html_to_text(homepage_match.group('value')) if homepage_match else ''

    ctx.update_user(
        user,
        display_name=display_name,
        location=location,
        homepage=homepage,
        occupation=occupation,
        interests=interests,
        member_since_iso=registered['iso_local'],
        member_since_raw=registered['raw'],
        observed_at_iso=registered['iso_local'],
        observed_at_raw=registered['raw'],
        domain=domain,
        relative_path=relative,
    )
    user['profile_count'] += 1
    ctx.add_observed_emails(user, source_html)


def parse_asp_members(ctx: Context, relative: str, domain: str, source_html: str) -> None:
    row_re = re.compile(
        r'(?is)<tr>\s*<td[^>]*>.*?pop_profile\.asp\?mode=display&id=(?P<id>\d+).*?</td>\s*<td[^>]*>.*?<a href="pop_profile\.asp\?mode=display&id=\d+">(?P<name>.*?)</a>.*?</td>\s*<td[^>]*>(?P<rank>.*?)</td>\s*<td[^>]*>(?P<posts>.*?)</td>\s*<td[^>]*>(?P<last_seen>.*?)</td>\s*<td[^>]*>(?P<joined>.*?)</td>\s*<td[^>]*>(?P<location>.*?)</td>'
    )
    for match in row_re.finditer(source_html):
        user_id = match.group('id')
        name = html_to_text(match.group('name'))
        rank = html_to_text(match.group('rank'))
        joined = parse_date(html_to_text(match.group('joined')))
        last_seen = parse_date(html_to_text(match.group('last_seen')))
        posts_match = re.search(r'(?P<n>\d+)', html_to_text(match.group('posts')))
        post_count = int(posts_match.group('n')) if posts_match else 0
        location = html_to_text(match.group('location'))
        user = ctx.ensure_user(f'asp:user:{user_id}', 'asp', user_id)
        ctx.update_user(
            user,
            display_name=name,
            role_label=rank,
            location=location,
            member_since_iso=joined['iso_local'],
            member_since_raw=joined['raw'],
            observed_at_iso=last_seen['iso_local'] or joined['iso_local'],
            observed_at_raw=last_seen['raw'] or joined['raw'],
            domain=domain,
            relative_path=relative,
        )
        if post_count > user['post_count_observed']:
            user['post_count_observed'] = post_count


def parse_phpbb_memberlist(ctx: Context, relative: str, domain: str, source_html: str) -> None:
    row_re = re.compile(
        r'(?is)<tr>\s*<td[^>]*class="(?:row1|row2)"[^>]*>\s*<span class="name"><a href="profile\.php\?mode=viewprofile(?:&amp;|&)u=(?P<id>\d+)">(?P<name>.*?)</a></span>.*?<td[^>]*class="(?:row1|row2)"[^>]*>(?P<joined>.*?)</td>.*?<td[^>]*class="(?:row1|row2)"[^>]*>(?P<posts>.*?)</td>.*?<td[^>]*class="(?:row1|row2)"[^>]*>(?P<website>.*?)</td>',
    )
    for match in row_re.finditer(source_html):
        user_id = match.group('id')
        name = html_to_text(match.group('name'))
        joined = parse_date(match.group('joined'))
        posts_match = re.search(r'(?P<n>\d+)', html_to_text(match.group('posts')))
        post_count = int(posts_match.group('n')) if posts_match else 0
        website_match = re.search(r'(?is)<a href="(?P<url>[^"]+)"', match.group('website'))
        website = normalize_whitespace(website_match.group('url')) if website_match else ''
        user = ctx.ensure_user(f'phpbb:user:{user_id}', 'phpbb', user_id)
        ctx.update_user(
            user,
            display_name=name,
            homepage=website,
            member_since_iso=joined['iso_local'],
            member_since_raw=joined['raw'],
            observed_at_iso=joined['iso_local'],
            observed_at_raw=joined['raw'],
            domain=domain,
            relative_path=relative,
        )
        if post_count > user['post_count_observed']:
            user['post_count_observed'] = post_count


def find_parent(parents: dict[str, str], key: str) -> str:
    while parents[key] != key:
        parents[key] = parents[parents[key]]
        key = parents[key]
    return key


def union_parent(parents: dict[str, str], a: str, b: str) -> None:
    root_a = find_parent(parents, a)
    root_b = find_parent(parents, b)
    if root_a != root_b:
        parents[root_b] = root_a


def finalize_outputs(ctx: Context) -> None:
    merged_identity_map: dict[str, str] = {}

    for topic_key in sorted(ctx.topics):
        topic = ctx.topics[topic_key]
        if topic['post_count'] == 0:
            ctx.summary['topic_stubs_skipped'] += 1
            continue
        ctx.writers['topics'].write({
            'topic_key': topic['topic_key'],
            'architecture': topic['architecture'],
            'topic_id': topic['topic_id'],
            'forum_key': topic['forum_key'],
            'forum_id': topic['forum_id'],
            'forum_title': topic['forum_title'],
            'topic_title': topic['topic_title'],
            'post_count': topic['post_count'],
            'unique_author_count': len(topic['author_keys']),
            'author_keys': sort_values(topic['author_keys']),
            'author_display_names': sort_values(topic['author_display_names']),
            'observed_domains': sort_values(topic['observed_domains']),
            'first_seen_at': topic['first_seen_at'],
            'first_seen_at_raw': topic['first_seen_at_raw'],
            'last_seen_at': topic['last_seen_at'],
            'last_seen_at_raw': topic['last_seen_at_raw'],
            'first_source_file': topic['first_source_file'],
            'source_page_count': topic['source_page_count'],
        })

    parents = {user_key: user_key for user_key in ctx.users}
    alias_index: dict[str, set[str]] = {}
    for user_key, user in ctx.users.items():
        aliases = set(user['aliases'])
        if user['primary_display_name']:
            aliases.add(user['primary_display_name'])
        for alias in aliases:
            normalized = normalize_alias(alias)
            if not normalized:
                continue
            alias_index.setdefault(normalized, set()).add(user_key)

    for alias, keys in alias_index.items():
        if len(keys) < 2:
            continue
        architectures = {ctx.users[key]['architecture'] for key in keys}
        if len(architectures) < 2:
            continue
        keys_list = sorted(keys)
        anchor = keys_list[0]
        for candidate in keys_list[1:]:
            union_parent(parents, anchor, candidate)

    groups: dict[str, list[dict[str, Any]]] = {}
    for user_key, user in ctx.users.items():
        root = find_parent(parents, user_key)
        groups.setdefault(root, []).append(user)

    for root_key in sorted(groups):
        members = groups[root_key]
        architectures = {member['architecture'] for member in members}
        if len(members) < 2 or len(architectures) < 2:
            continue
        merged_identity_key = f'merged:{root_key.replace(":", "_")}'
        for member in members:
            merged_identity_map[member['user_key']] = merged_identity_key
        normalized_aliases = {normalize_alias(alias) for member in members for alias in member['aliases']}
        ctx.writers['merged_identities'].write({
            'merged_identity_key': merged_identity_key,
            'confidence': 'high_exact_alias_cross_architecture',
            'user_keys': sorted(member['user_key'] for member in members),
            'architectures': sort_values(architectures),
            'primary_display_names': sort_values(member['primary_display_name'] for member in members if member['primary_display_name']),
            'normalized_aliases': sort_values(normalized_aliases),
        })
        ctx.summary['merged_identities'] += 1

    for user_key in sorted(ctx.users):
        user = ctx.users[user_key]
        if not user['primary_display_name']:
            aliases = sort_values(user['aliases'])
            if aliases:
                user['primary_display_name'] = aliases[0]
        ctx.writers['users'].write({
            'user_key': user['user_key'],
            'architecture': user['architecture'],
            'user_id': user['user_id'],
            'merged_identity_key': merged_identity_map.get(user['user_key']),
            'primary_display_name': user['primary_display_name'],
            'aliases': sort_values(user['aliases']),
            'role_labels': sort_values(user['role_labels']),
            'role_classes': sort_values(user['role_classes']),
            'locations': sort_values(user['locations']),
            'homepages': sort_values(user['homepages']),
            'emails': sort_values(user['emails']),
            'occupations': sort_values(user['occupations']),
            'interests': sort_values(user['interests']),
            'member_since': user['member_since'],
            'member_since_raw': user['member_since_raw'],
            'post_count_observed': user['post_count_observed'],
            'profile_count': user['profile_count'],
            'observed_domains': sort_values(user['observed_domains']),
            'first_seen_at': user['first_seen_at'],
            'first_seen_at_raw': user['first_seen_at_raw'],
            'last_seen_at': user['last_seen_at'],
            'last_seen_at_raw': user['last_seen_at_raw'],
            'first_source_file': user['first_source_file'],
            'source_page_count': user['source_page_count'],
        })

    for salvage_key in sorted(ctx.pending_salvage):
        payload = dict(ctx.pending_salvage[salvage_key])
        candidate_post_key = payload.get('candidate_post_key')
        existing_body = ctx.post_body_index.get(candidate_post_key or '')
        if existing_body and normalize_whitespace(existing_body) == normalize_whitespace(payload.get('body_text') or ''):
            continue
        author_key = payload.get('author_key')
        if author_key and not payload.get('author_display') and author_key in ctx.users:
            payload['author_display'] = ctx.users[author_key].get('primary_display_name')
        ctx.writers['post_salvage'].write(payload)
        ctx.summary['salvage_records'] += 1

    (ctx.run_root / 'summary.json').write_text(json.dumps(ctx.summary, ensure_ascii=False, indent=2), encoding='utf-8')
    manifest = {
        'input_root': str(ctx.input_root),
        'output_root': str(ctx.run_root),
        'python_executable': sys.executable,
        'read_limit': ctx.args.read_limit,
        'kind_filter': sorted(ctx.kind_filter),
        'notes': [
            'sobresites_com e sobresites_com_br foram unificados como a mesma origem lÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³gica',
            'post pages entram como trilha de salvage para lost media',
            'users.jsonl preserva histÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³rico observÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡vel de aliases, homepages, locations e emails',
            'merged_identities.jsonl une automaticamente ASP e phpBB quando o apelido normalizado bate exatamente',
        ],
    }
    (ctx.run_root / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')


def iter_html_files(root: Path) -> Iterable[Path]:
    for current_root, dirnames, filenames in os.walk(root):
        dirnames.sort(key=str.casefold)
        for filename in sorted(filenames, key=str.casefold):
            if filename.lower().endswith('.html'):
                yield Path(current_root) / filename


def parse_kinds(raw_kinds: list[str]) -> list[str]:
    parsed: list[str] = []
    for item in raw_kinds:
        for part in item.split(','):
            value = normalize_whitespace(part).lower()
            if value:
                parsed.append(value)
    return parsed


def process_file(ctx: Context, path: Path) -> None:
    relative = relative_path(ctx.input_root, path)
    page_kind = get_page_kind(relative)
    if page_kind == 'skip':
        ctx.summary['skipped_files'] += 1
        return
    if ctx.kind_filter and page_kind not in ctx.kind_filter:
        ctx.summary['skipped_files'] += 1
        return
    if ctx.args.read_limit and ctx.summary['processed_files'] >= ctx.args.read_limit:
        raise StopIteration

    ctx.summary['processed_files'] += 1
    domain = get_domain(path)
    read_result = read_archive_text(path)
    if read_result['repaired_from']:
        ctx.info(f'ENCODING | reparo aplicado {read_result["repaired_from"]} | {relative}')
    elif read_result['mojibake']:
        ctx.warn(f'ENCODING | possÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­vel mojibake; decoder={read_result["decoder"]}; charset_hint={read_result["charset_hint"] or "none"} | {relative}')

    html_text = read_result['text']
    if page_kind == 'asp_topic':
        parse_asp_topic(ctx, relative, domain, html_text)
    elif page_kind == 'asp_post':
        parse_asp_post(ctx, relative, domain, html_text)
    elif page_kind == 'phpbb_viewtopic':
        parse_phpbb_viewtopic(ctx, relative, domain, html_text)
    elif page_kind == 'asp_profile':
        parse_asp_profile(ctx, relative, domain, html_text)
    elif page_kind == 'phpbb_profile':
        parse_phpbb_profile(ctx, relative, domain, html_text)
    elif page_kind == 'asp_members':
        parse_asp_members(ctx, relative, domain, html_text)
    elif page_kind == 'phpbb_memberlist':
        parse_phpbb_memberlist(ctx, relative, domain, html_text)
    ctx.summary['parsed_files'] += 1

    if ctx.summary['processed_files'] == 1 or ctx.summary['processed_files'] % ctx.args.progress_every == 0:
        ctx.info(
            'PROGRESS | processados=%s posts=%s salvage=%s topicos=%s usuarios=%s'
            % (
                ctx.summary['processed_files'],
                ctx.summary['posts_emitted'],
                ctx.summary['salvage_records'],
                len(ctx.topics),
                len(ctx.users),
            )
        )


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Extrai dataset auditÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡vel de arquivos HTML normalizados do fÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³rum.')
    parser.add_argument('--input-root', required=True, help='Raiz do acervo normalized')
    parser.add_argument('--output-root', required=True, help='Pasta onde as runs serÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â£o criadas')
    parser.add_argument('-r', '--read-limit', type=int, default=0, help='Limita quantos arquivos elegÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­veis serÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â£o lidos')
    parser.add_argument('--kinds', nargs='*', default=[], help='Filtra tipos, ex.: asp_topic asp_post phpbb_viewtopic')
    parser.add_argument('--progress-every', type=int, default=200, help='Intervalo de log de progresso')
    return parser


def main() -> int:
    parser = build_argument_parser()
    args = parser.parse_args()
    args.kinds = parse_kinds(args.kinds)

    input_root = Path(args.input_root).resolve()
    output_root = Path(args.output_root).resolve()
    ensure_dir(output_root)
    run_id = datetime.now().strftime('run-%Y%m%d-%H%M%S-%f')[:-3]
    run_root = output_root / run_id
    ensure_dir(run_root / 'warehouse')
    ensure_dir(run_root / 'knowledge')
    ensure_dir(run_root / 'logs')

    ctx = Context(input_root, run_root, args)
    ctx.info(f'BOOT | Iniciando extraÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â§ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â£o. input={input_root} output={run_root}')
    try:
        for path in iter_html_files(input_root):
            try:
                process_file(ctx, path)
            except StopIteration:
                break
            except Exception as exc:
                relative = relative_path(input_root, path)
                ctx.error(f'PARSE | {exc} | {relative}')
        finalize_outputs(ctx)
        ctx.info(
            'DONE | ConcluÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­do. posts=%s salvage=%s topicos=%s usuarios=%s merges=%s'
            % (
                ctx.summary['posts_emitted'],
                ctx.summary['salvage_records'],
                len(ctx.topics),
                len(ctx.users),
                ctx.summary['merged_identities'],
            )
        )
        return 0
    finally:
        ctx.close()


if __name__ == '__main__':
    raise SystemExit(main())


