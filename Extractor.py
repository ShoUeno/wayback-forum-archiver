#!/usr/bin/env python3
"""
SobreSites Forum Archive Extractor
===================================
Extrai dados estruturados de páginas HTML salvas do Wayback Machine
dos fóruns sobresites.com.br (ASP) e sobresites.com (phpBB).

Autor: Projeto de preservação digital
"""

import os
import re
import sys
import json
import hashlib
from html.parser import HTMLParser
from html import unescape
from datetime import datetime
from collections import defaultdict
from urllib.parse import unquote


# ============================================================
# UTILITÁRIOS
# ============================================================

class HTMLTextExtractor(HTMLParser):
    """Extrai texto limpo de HTML, removendo tags e scripts."""
    def __init__(self):
        super().__init__()
        self._result = []
        self._skip = False
        self._skip_tags = {'script', 'style', 'noscript'}

    def handle_starttag(self, tag, attrs):
        if tag.lower() in self._skip_tags:
            self._skip = True
        if tag.lower() == 'br':
            self._result.append('\n')
        if tag.lower() == 'p':
            self._result.append('\n\n')
        if tag.lower() == 'hr':
            self._result.append('\n---\n')

    def handle_endtag(self, tag):
        if tag.lower() in self._skip_tags:
            self._skip = False

    def handle_data(self, data):
        if not self._skip:
            self._result.append(data)

    def get_text(self):
        return ''.join(self._result).strip()


def html_to_text(html_content):
    """Converte HTML para texto limpo."""
    if not html_content:
        return ''
    extractor = HTMLTextExtractor()
    try:
        extractor.feed(html_content)
        text = extractor.get_text()
    except Exception:
        # Fallback: regex simples
        text = re.sub(r'<[^>]+>', ' ', html_content)
    # Limpa espaços excessivos
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def read_file_auto_encoding(filepath):
    """Lê arquivo tentando múltiplos encodings (ISO-8859-1 é o padrão dos fóruns BR antigos).
    
    Muitos arquivos do Wayback Machine têm encoding ISO-8859-1 original mas foram
    re-salvos em UTF-8 com caracteres corrompidos (mojibake). Tentamos detectar e corrigir.
    """
    # Primeiro ler os bytes brutos para detectar encoding
    with open(filepath, 'rb') as f:
        raw = f.read()
    
    # Verificar se o arquivo declara charset
    charset_match = re.search(rb'charset[="\s]+([\w-]+)', raw[:2000])
    declared_charset = charset_match.group(1).decode('ascii').lower() if charset_match else None
    
    # Tentar na ordem de prioridade
    encodings = []
    if declared_charset:
        encodings.append(declared_charset)
    encodings.extend(['utf-8', 'iso-8859-1', 'cp1252', 'latin-1'])
    
    for enc in encodings:
        try:
            content = raw.decode(enc, errors='strict')
            return content, enc
        except (UnicodeDecodeError, UnicodeError, LookupError):
            continue
    
    # Último recurso
    return raw.decode('iso-8859-1', errors='replace'), 'iso-8859-1-fallback'


def content_hash(text):
    """Gera hash do conteúdo para deduplicação."""
    normalized = re.sub(r'\s+', ' ', text.lower().strip())
    return hashlib.md5(normalized.encode('utf-8')).hexdigest()


def detect_source(filepath, content):
    """Detecta se o arquivo é do fórum ASP (sobresites.com.br) ou phpBB (sobresites.com)."""
    filename = os.path.basename(filepath).lower()
    
    # Detecção por extensão no nome do arquivo
    if '.asp' in filename:
        return 'asp'  # sobresites.com.br
    if '.php' in filename:
        return 'phpbb'  # sobresites.com
    
    # Detecção por conteúdo
    if 'phpbb' in content.lower() or 'class="postbody"' in content:
        return 'phpbb'
    if 'pop_profile.asp' in content or 'Fórum de Anime - SobreSites' in content:
        return 'asp'
    
    return 'unknown'


def detect_page_type(filepath, content):
    """Detecta o tipo da página: topic, forum_list, profile, members, index, post, etc."""
    filename = os.path.basename(filepath).lower()
    content_lower = content.lower()
    
    # Caminho completo (para detectar index.html dentro de pastas com nome de URL)
    full_path_lower = filepath.lower().replace('\\', '/')
    
    # Verificar se é lixo (erro 429, página vazia, etc.)
    if '429 too many requests' in content_lower:
        return 'error_429'
    if len(content.strip()) < 200:
        return 'empty'
    
    # === Detecção pelo caminho completo (Wayback Machine salva index.html em pastas) ===
    # Ex: .../post.asp%3fmethod%3dReply.../index.html
    if filename in ('index.html', 'index.htm'):
        if 'post.asp' in full_path_lower or 'post_info.asp' in full_path_lower:
            return 'post_reply'
        if 'topic.asp' in full_path_lower:
            return 'topic'
        if 'forum.asp' in full_path_lower:
            return 'forum_list'
        if 'pop_profile.asp' in full_path_lower:
            return 'profile'
        if 'members.asp' in full_path_lower:
            return 'members_list'
        if 'default.asp' in full_path_lower:
            return 'index'
        if 'viewtopic.php' in full_path_lower:
            return 'topic'
        if 'viewforum.php' in full_path_lower:
            return 'forum_list'
        if 'posting.php' in full_path_lower:
            return 'post_reply'
        if 'profile.php' in full_path_lower:
            return 'profile'
    
    # Verificar se é lixo (erro 429, página vazia, etc.)
    if '429 too many requests' in content_lower:
        return 'error_429'
    if len(content.strip()) < 200:
        return 'empty'
    
    # === Detecção por nomes originais (URL-encoded) ===
    
    # ASP pages (original filenames)
    if 'topic.asp' in filename or 'topic_id' in filename:
        return 'topic'
    if 'forum.asp' in filename or ('forum_id' in filename and 'topic' not in filename):
        return 'forum_list'
    if 'pop_profile.asp' in filename:
        return 'profile'
    if 'members.asp' in filename:
        return 'members_list'
    if 'post.asp' in filename:
        return 'post_reply'
    if 'default.asp' in filename:
        return 'index'
    
    # phpBB pages (original filenames)
    if 'viewtopic.php' in filename:
        return 'topic'
    if 'viewforum.php' in filename:
        return 'forum_list'
    if 'profile.php' in filename and 'viewprofile' in filename:
        return 'profile'
    if 'memberlist.php' in filename:
        return 'members_list'
    if 'posting.php' in filename:
        return 'post_reply'
    if 'groupcp.php' in filename:
        return 'group'
    if 'index.php' in filename:
        return 'index'
    if 'login.php' in filename:
        return 'login'
    
    # === Detecção por nomes renomeados (clean names) ===
    
    # ASP renamed: asp_topic_*, asp_forum_*, asp_profile_*, etc.
    if filename.startswith('asp_topic_'):
        return 'topic'
    if filename.startswith('asp_forum_'):
        return 'forum_list'
    if filename.startswith('asp_profile_'):
        return 'profile'
    if filename.startswith('asp_members'):
        return 'members_list'
    if filename.startswith('asp_post_'):
        return 'post_reply'
    if filename.startswith('asp_index_'):
        return 'index'
    
    # phpBB renamed: phpbb_topic_*, phpbb_post_*, phpbb_forum_*, etc.
    if filename.startswith('phpbb_topic_') or filename.startswith('phpbb_post_'):
        return 'topic'
    if filename.startswith('phpbb_forum_'):
        return 'forum_list'
    if filename.startswith('phpbb_profile_'):
        return 'profile'
    if filename.startswith('phpbb_memberlist'):
        return 'members_list'
    if filename.startswith('phpbb_posting_'):
        return 'post_reply'
    if filename.startswith('phpbb_group_'):
        return 'group'
    if filename.startswith('phpbb_index'):
        return 'index'
    if filename.startswith('phpbb_login'):
        return 'login'
    
    # === Fallback: detecção por conteúdo ===
    if 'class="postbody"' in content_lower:
        return 'topic'
    if 'enviado em' in content_lower and ('topic_id' in content_lower or 'pop_profile' in content_lower):
        return 'topic'
    if 'dados do usu' in content_lower:
        return 'profile'
    # Formulário de Reply/ReplyQuote ASP (detectar pela action e hidden fields)
    if 'name="method_type"' in content_lower and ('value="reply"' in content_lower or 'value="topic"' in content_lower):
        return 'post_reply'
    if 'action="post_info.asp"' in content_lower or 'action="post.asp"' in content_lower:
        return 'post_reply'
    
    return 'unknown'


def is_junk_page(page_type):
    """Retorna True se a página é lixo (sem conteúdo útil)."""
    return page_type in ('error_429', 'empty', 'login')


# ============================================================
# PARSER: FÓRUM ASP (sobresites.com.br)
# ============================================================

class ASPForumParser:
    """Parser para o fórum customizado ASP do sobresites.com.br"""
    
    def parse_topic(self, content, filepath=''):
        """Extrai posts de uma página de tópico ASP."""
        posts = []
        
        # Extrair título do tópico
        topic_title = ''
        title_match = re.search(r'<title>(.*?)</title>', content, re.IGNORECASE | re.DOTALL)
        if title_match:
            topic_title = html_to_text(title_match.group(1)).replace('Fórum de Anime - SobreSites', '').strip(' -')
        
        # Extrair breadcrumb para nome do fórum
        forum_name = ''
        breadcrumb = re.search(r'FORUM\.asp\?FORUM_ID=\d+[^>]*>([^<]+)', content, re.IGNORECASE)
        if breadcrumb:
            forum_name = html_to_text(breadcrumb.group(1))
        
        # Extrair TOPIC_ID
        topic_id = ''
        tid = re.search(r'TOPIC_ID[=\'](\d+)', content, re.IGNORECASE)
        if tid:
            topic_id = tid.group(1)
        
        # Extrair página atual
        page_num = 1
        page_match = re.search(r'OPTION SELECTED VALUE="(\d+)"', content)
        if page_match:
            page_num = int(page_match.group(1))
        
        # Padrão de posts ASP: blocos com autor e conteúdo
        # Cada post tem: pop_profile link -> autor -> rank -> local -> mensagens count -> data -> conteúdo
        
        # Buscar blocos de post (cada post começa com pop_profile e termina antes do próximo)
        post_blocks = re.split(
            r'(?=<td\s+bgcolor="F8F8F8"\s+valign="top">\s*\n?\s*<a\s+href="pop_profile)',
            content, flags=re.IGNORECASE
        )
        
        for block in post_blocks[1:]:  # Pular o primeiro (header)
            post = self._parse_asp_post_block(block)
            if post:
                post['topic_title'] = topic_title
                post['topic_id'] = topic_id
                post['forum_name'] = forum_name
                post['page'] = page_num
                post['source'] = 'sobresites.com.br'
                post['source_file'] = os.path.basename(filepath)
                posts.append(post)
        
        # Se o split não encontrou, tentar padrão alternativo
        if not posts:
            posts = self._parse_asp_topic_fallback(content, topic_title, topic_id, forum_name, page_num, filepath)
        
        return posts

    def _parse_asp_post_block(self, block):
        """Extrai dados de um bloco individual de post ASP."""
        post = {}
        
        # Autor
        author_match = re.search(
            r'pop_profile\.asp\?mode=display&(?:amp;)?id=(\d+)[^>]*>\s*'
            r'(?:<[^>]*>)*\s*([^<]+)',
            block, re.IGNORECASE | re.DOTALL
        )
        if author_match:
            post['author_id'] = author_match.group(1)
            post['author'] = author_match.group(2).strip()
        else:
            return None
        
        # Rank
        rank_match = re.search(r'<small>(\w[\w\s]*?)</small>', block)
        if rank_match:
            rank_text = rank_match.group(1).strip()
            if rank_text not in ('', 'Mensagens'):
                post['author_rank'] = rank_text
        
        # Localização
        loc_blocks = re.findall(r'<small>([^<]+)</small>', block)
        for loc in loc_blocks:
            loc = loc.strip()
            if loc and 'Mensagen' not in loc and loc not in ('Administrador', 'Moderador', 'Estreante', 'Membro', 'Membro Avançado'):
                if not loc.isdigit():
                    post['author_location'] = loc
                    break
        
        # Contagem de mensagens
        msg_count = re.search(r'(\d+)\s*Mensagen', block)
        if msg_count:
            post['author_post_count'] = int(msg_count.group(1))
        
        # Data do post (lida com &nbsp; e encoding quebrado do "às")
        date_match = re.search(
            r'Enviado\s+em(?:&nbsp;|\s)+(\d{1,2}/\d{1,2}/\d{4})(?:&nbsp;|\s)+\S+\s+(\d{1,2}:\d{2}:\d{2})',
            block, re.IGNORECASE
        )
        if date_match:
            post['date_raw'] = f"{date_match.group(1)} {date_match.group(2)}"
            try:
                post['date'] = datetime.strptime(post['date_raw'], '%d/%m/%Y %H:%M:%S').isoformat()
            except ValueError:
                post['date'] = post['date_raw']
        
        # Homepage do autor
        homepage = re.search(r'href="(https?://[^"]+)"[^>]*>.*?Homepage', block, re.IGNORECASE)
        if homepage:
            post['author_homepage'] = homepage.group(1)
        
        # Post ID (anchor)
        anchor = re.search(r'<a\s+name="(\d+)"', block)
        if anchor:
            post['post_id'] = anchor.group(1)
        
        # Conteúdo do post (entre <hr> e o final do bloco ou próximo post)
        content_match = re.search(
            r'<hr[^>]*>\s*(.*?)(?:<a\s+href="#top"|</table>)',
            block, re.DOTALL | re.IGNORECASE
        )
        if content_match:
            raw_content = content_match.group(1)
            post['content_html'] = raw_content.strip()
            post['content_text'] = html_to_text(raw_content)
        
        # Assinatura (geralmente após o conteúdo principal, com citações ou texto fixo)
        sig_match = re.search(
            r'(?:<BR>|<br\s*/?>)\s*"([^"]*)".*?$',
            post.get('content_text', ''), re.DOTALL
        )
        if sig_match:
            post['signature'] = sig_match.group(0).strip()
        
        # Hash para deduplicação
        dedupe_text = f"{post.get('author', '')}|{post.get('date_raw', '')}|{post.get('content_text', '')[:200]}"
        post['content_hash'] = content_hash(dedupe_text)
        
        return post

    def _parse_asp_topic_fallback(self, content, topic_title, topic_id, forum_name, page_num, filepath):
        """Fallback parser para tópicos ASP com estrutura diferente."""
        posts = []
        
        # Tentar encontrar posts pelo padrão de data
        date_splits = re.split(r'(Enviado\s+em(?:&nbsp;|\s)+\d{1,2}/\d{1,2}/\d{4}(?:&nbsp;|\s)+\S+\s+\d{1,2}:\d{2}:\d{2})', content, flags=re.IGNORECASE)
        
        for i in range(1, len(date_splits) - 1, 2):
            date_raw_text = date_splits[i]
            post_content_area = date_splits[i + 1] if i + 1 < len(date_splits) else ''
            pre_area = date_splits[i - 1] if i - 1 >= 0 else ''
            
            post = {}
            
            # Data
            dm = re.search(r'(\d{1,2}/\d{1,2}/\d{4})(?:&nbsp;|\s)+\S+\s+(\d{1,2}:\d{2}:\d{2})', date_raw_text)
            if dm:
                post['date_raw'] = f"{dm.group(1)} {dm.group(2)}"
                try:
                    post['date'] = datetime.strptime(post['date_raw'], '%d/%m/%Y %H:%M:%S').isoformat()
                except ValueError:
                    post['date'] = post['date_raw']
            
            # Autor (no bloco anterior)
            author_match = re.findall(r'pop_profile\.asp\?mode=display&(?:amp;)?id=(\d+)[^>]*>\s*(?:<[^>]*>)*\s*([^<]+)', pre_area, re.IGNORECASE)
            if author_match:
                last_author = author_match[-1]
                post['author_id'] = last_author[0]
                post['author'] = last_author[1].strip()
            
            # Conteúdo
            content_match = re.search(r'<hr[^>]*>\s*(.*?)(?:<a\s+href="#top"|</table>)', post_content_area, re.DOTALL | re.IGNORECASE)
            if content_match:
                raw = content_match.group(1)
                post['content_html'] = raw.strip()
                post['content_text'] = html_to_text(raw)
            
            if post.get('content_text') or post.get('author'):
                post['topic_title'] = topic_title
                post['topic_id'] = topic_id
                post['forum_name'] = forum_name
                post['page'] = page_num
                post['source'] = 'sobresites.com.br'
                post['source_file'] = os.path.basename(filepath)
                dedupe_text = f"{post.get('author', '')}|{post.get('date_raw', '')}|{post.get('content_text', '')[:200]}"
                post['content_hash'] = content_hash(dedupe_text)
                posts.append(post)
        
        return posts

    def parse_profile(self, content, filepath=''):
        """Extrai dados de perfil de uma página pop_profile.asp."""
        profile = {}
        profile['source'] = 'sobresites.com.br'
        profile['source_file'] = os.path.basename(filepath)
        
        # ID do perfil (do nome do arquivo)
        id_match = re.search(r'id[=](\d+)', filepath, re.IGNORECASE)
        if id_match:
            profile['user_id'] = id_match.group(1)
        
        # Nome do usuário (no cabeçalho do perfil)
        name_match = re.search(
            r'bgcolor="618F9E"[^>]*>.*?<b>\s*&nbsp;\s*\n?\s*(.+?)\s*\n?\s*</b>',
            content, re.DOTALL | re.IGNORECASE
        )
        if name_match:
            profile['username'] = html_to_text(name_match.group(1)).strip()
        
        # Data de registro
        reg_match = re.search(r'Membro\s+desde\s+(\d{1,2}/\d{1,2}/\d{4})', content, re.IGNORECASE)
        if reg_match:
            profile['member_since'] = reg_match.group(1)
        
        # E-mail
        email_match = re.search(r'E-Mail:.*?([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)', content, re.IGNORECASE | re.DOTALL)
        if email_match:
            profile['email'] = email_match.group(1)
        else:
            # CloudFlare email protection
            cf_match = re.search(r'data-cfemail="([0-9a-f]+)"', content)
            if cf_match:
                profile['email_encoded_cf'] = cf_match.group(1)
                profile['email'] = self._decode_cf_email(cf_match.group(1))
        
        # Localização
        loc_match = re.search(r'Localiza[çc][ãa]o:.*?<font[^>]*>(.*?)</font>', content, re.IGNORECASE | re.DOTALL)
        if loc_match:
            profile['location'] = html_to_text(loc_match.group(1))
        
        # ICQ
        icq_match = re.search(r'ICQ[=:].*?(\d{5,12})', content, re.IGNORECASE)
        if icq_match:
            profile['icq'] = icq_match.group(1)
        
        # Homepage
        hp_match = re.search(r'Homepage:.*?href="(https?://[^"]+)"', content, re.IGNORECASE | re.DOTALL)
        if hp_match:
            profile['homepage'] = hp_match.group(1)
        
        # Hash
        profile['content_hash'] = content_hash(json.dumps(profile, sort_keys=True))
        
        return profile

    def _decode_cf_email(self, encoded):
        """Decodifica e-mail protegido pelo CloudFlare."""
        try:
            r = int(encoded[:2], 16)
            email = ''
            for i in range(2, len(encoded), 2):
                email += chr(int(encoded[i:i+2], 16) ^ r)
            return email
        except Exception:
            return f'[cf-encoded:{encoded}]'

    def parse_members_list(self, content, filepath=''):
        """Extrai lista de membros de members.asp."""
        members = []
        
        pattern = re.finditer(
            r'pop_profile\.asp\?mode=display&(?:amp;)?id=(\d+)[^>]*>\s*'
            r'(?:<[^>]*>)*\s*([^<]+)</a>.*?'
            r'<font[^>]*>(Estreante|Membro|Moderador|Administrador|Membro Avan[çc]ado)[^<]*</font>.*?'
            r'(\d+)\s*<br',
            content, re.IGNORECASE | re.DOTALL
        )
        
        seen_ids = set()
        for m in pattern:
            uid = m.group(1)
            if uid in seen_ids:
                continue
            seen_ids.add(uid)
            
            member = {
                'user_id': uid,
                'username': m.group(2).strip(),
                'rank': m.group(3).strip(),
                'post_count': int(m.group(4)),
                'source': 'sobresites.com.br',
                'source_file': os.path.basename(filepath),
            }
            # ICQ
            icq = re.search(rf'M_NAME={re.escape(m.group(2).strip())}[^"]*ICQ=(\d+)', content)
            if icq:
                member['icq'] = icq.group(1)
            
            members.append(member)
        
        return members

    def parse_forum_list(self, content, filepath=''):
        """Extrai lista de tópicos de uma página forum.asp."""
        topics = []
        
        pattern = re.finditer(
            r'topic\.asp\?TOPIC_ID=(\d+)[^>]*>\s*(?:<[^>]*>)*\s*([^<]+)',
            content, re.IGNORECASE
        )
        
        seen = set()
        for m in pattern:
            tid = m.group(1)
            if tid in seen:
                continue
            seen.add(tid)
            
            title = html_to_text(m.group(2)).strip()
            if title:
                topics.append({
                    'topic_id': tid,
                    'title': title,
                    'source': 'sobresites.com.br',
                    'source_file': os.path.basename(filepath),
                })
        
        return topics

    def parse_reply_page(self, content, filepath=''):
        """Extrai metadados e conteúdo quotado de páginas Reply/ReplyQuote/NewTopic ASP.
        
        Essas páginas são formulários de resposta que contêm:
        - Metadados do tópico (TOPIC_ID, Forum_Title, Topic_Title, etc.)
        - Texto quotado na textarea (em páginas ReplyQuote)
        
        O texto quotado pode ser a única cópia sobrevivente de um post.
        """
        result = {
            'topic_metadata': None,
            'quoted_post': None,
        }
        
        # === Extrair metadados do formulário ===
        topic_id = ''
        forum_id = ''
        cat_id = ''
        topic_title = ''
        forum_title = ''
        method = ''
        reply_id = ''
        
        # Dos hidden fields
        tid = re.search(r'name="TOPIC_ID"[^>]*value="(\d+)"', content, re.IGNORECASE)
        if tid:
            topic_id = tid.group(1)
        
        fid = re.search(r'name="FORUM_ID"[^>]*value="(\d+)"', content, re.IGNORECASE)
        if fid:
            forum_id = fid.group(1)
        
        cid = re.search(r'name="CAT_ID"[^>]*value="(\d+)"', content, re.IGNORECASE)
        if cid:
            cat_id = cid.group(1)
        
        tt = re.search(r'name="Topic_Title"[^>]*value="([^"]*)"', content, re.IGNORECASE)
        if tt:
            topic_title = html_to_text(tt.group(1))
        
        ft = re.search(r'name="FORUM_Title"[^>]*value="([^"]*)"', content, re.IGNORECASE)
        if ft:
            forum_title = html_to_text(ft.group(1))
        
        mt = re.search(r'name="Method_Type"[^>]*value="(\w+)"', content, re.IGNORECASE)
        if mt:
            method = mt.group(1)
        
        rid = re.search(r'name="REPLY_ID"[^>]*value="(\d+)"', content, re.IGNORECASE)
        if rid:
            reply_id = rid.group(1)
        
        # Também do breadcrumb
        if not topic_title:
            bc = re.search(r'topic\.asp\?TOPIC_ID=\d+[^>]*>([^<]+)', content, re.IGNORECASE)
            if bc:
                topic_title = html_to_text(bc.group(1))
        if not forum_title:
            bc_f = re.search(r'forum\.asp\?FORUM_ID=\d+[^>]*>([^<]+)', content, re.IGNORECASE)
            if bc_f:
                forum_title = html_to_text(bc_f.group(1))
        
        # Também da action URL
        if not topic_id:
            action_tid = re.search(r'TOPIC_ID=(\d+)', content, re.IGNORECASE)
            if action_tid:
                topic_id = action_tid.group(1)
        if not forum_id:
            action_fid = re.search(r'FORUM_ID=(\d+)', content, re.IGNORECASE)
            if action_fid:
                forum_id = action_fid.group(1)
        
        if topic_id:
            result['topic_metadata'] = {
                'topic_id': topic_id,
                'title': topic_title,
                'forum_id': forum_id,
                'forum_name': forum_title,
                'cat_id': cat_id,
                'source': 'sobresites.com.br',
                'source_file': os.path.basename(filepath),
            }
        
        # === Extrair conteúdo quotado da textarea ===
        textarea = re.search(
            r'<textarea[^>]*name="Message"[^>]*>(.*?)</textarea>',
            content, re.DOTALL | re.IGNORECASE
        )
        if textarea:
            quoted_text = textarea.group(1).strip()
            if quoted_text:
                # Limpar BBCode quote tags
                clean_text = quoted_text
                # Extrair autor do quote se disponível
                quoted_author = ''
                author_match = re.search(r'\[quote\s*=\s*"?([^"\]]+)"?\]', clean_text, re.IGNORECASE)
                if author_match:
                    quoted_author = author_match.group(1).strip()
                
                # Remover tags [quote] e [/quote]
                clean_text = re.sub(r'\[/?quote[^\]]*\]', '', clean_text, flags=re.IGNORECASE).strip()
                
                if clean_text:
                    post = {
                        'content_text': clean_text,
                        'content_format': 'bbcode',
                        'topic_id': topic_id,
                        'topic_title': topic_title,
                        'forum_id': forum_id,
                        'forum_name': forum_title,
                        'source': 'sobresites.com.br',
                        'source_file': os.path.basename(filepath),
                        'extracted_from': 'reply_quote_textarea',
                    }
                    if quoted_author:
                        post['author'] = quoted_author
                    if reply_id:
                        post['post_id'] = reply_id
                    
                    # Hash para deduplicação
                    dedupe_text = f"{post.get('author', '')}|{clean_text[:200]}"
                    post['content_hash'] = content_hash(dedupe_text)
                    
                    result['quoted_post'] = post
        
        return result


# ============================================================
# PARSER: FÓRUM phpBB (sobresites.com)
# ============================================================

class PhpBBParser:
    """Parser para o fórum phpBB do sobresites.com"""
    
    MONTHS_PT = {
        'jan': 1, 'fev': 2, 'mar': 3, 'abr': 4, 'mai': 5, 'jun': 6,
        'jul': 7, 'ago': 8, 'set': 9, 'out': 10, 'nov': 11, 'dez': 12
    }
    
    DAYS_PT = {'seg': 'Mon', 'ter': 'Tue', 'qua': 'Wed', 'qui': 'Thu', 'sex': 'Fri', 'sab': 'Sat', 'dom': 'Sun'}
    
    def parse_topic(self, content, filepath=''):
        """Extrai posts de uma página viewtopic.php."""
        posts = []
        
        # Título do tópico
        topic_title = ''
        title_match = re.search(r'<title>.*?Exibir t[oó]pico\s*-\s*(.+?)</title>', content, re.IGNORECASE | re.DOTALL)
        if title_match:
            topic_title = html_to_text(title_match.group(1))
        
        # Forum name
        forum_name = ''
        forum_match = re.search(r'viewforum\.php\?f=\d+[^>]*>([^<]+)', content, re.IGNORECASE)
        if forum_match:
            forum_name = html_to_text(forum_match.group(1))
        
        # Topic ID - tentar do filepath e do conteúdo
        topic_id = ''
        tid = re.search(r'[?&]t=(\d+)', filepath, re.IGNORECASE)
        if tid:
            topic_id = tid.group(1)
        if not topic_id:
            # Extrair do conteúdo: links reply/quote contêm o topic_id
            tid_content = re.search(r'viewtopic\.php\?t=(\d+)', content, re.IGNORECASE)
            if tid_content:
                topic_id = tid_content.group(1)
        if not topic_id:
            # Tentar do link "posting.php?mode=reply&t=NNN" 
            tid_posting = re.search(r'posting\.php\?mode=\w+&(?:amp;)?t=(\d+)', content, re.IGNORECASE)
            if tid_posting:
                topic_id = tid_posting.group(1)
        
        # Página atual
        page = 1
        # phpBB usa ?start=N onde N é offset (0, 15, 30...), posts_per_page geralmente 15
        start_match = re.search(r'[?&]start=(\d+)', filepath, re.IGNORECASE)
        if start_match:
            start_val = int(start_match.group(1))
            page = (start_val // 15) + 1  # phpBB padrão: 15 posts por página
        else:
            # Tentar detectar página pelo seletor no conteúdo
            page_match = re.search(r'<b>(\d+)</b></td>\s*</tr>\s*</table>\s*</td>\s*</tr>\s*</table>', content)
            if page_match:
                page = int(page_match.group(1))
        
        # Forum ID
        forum_id = ''
        fid = re.search(r'viewforum\.php\?f=(\d+)', content, re.IGNORECASE)
        if fid:
            forum_id = fid.group(1)
        
        # Extrair blocos de post usando os anchors de post ID
        # Cada post phpBB tem: <a name="POST_ID"> dentro de <span class="name">
        post_blocks = re.split(r'(?=<span\s+class="name"><a\s+name=")', content, flags=re.IGNORECASE)
        
        for block in post_blocks[1:]:
            post = self._parse_phpbb_post_block(block)
            if post:
                post['topic_title'] = topic_title
                post['topic_id'] = topic_id
                post['forum_name'] = forum_name
                post['forum_id'] = forum_id
                post['page'] = page
                post['source'] = 'sobresites.com'
                post['source_file'] = os.path.basename(filepath)
                posts.append(post)
        
        return posts

    def _parse_phpbb_post_block(self, block):
        """Extrai dados de um bloco individual de post phpBB."""
        post = {}
        
        # Post ID
        pid = re.search(r'<a\s+name="(\d+)"\s+id="(\d+)"', block, re.IGNORECASE)
        if pid:
            post['post_id'] = pid.group(1)
        
        # Autor
        author_match = re.search(r'<strong>([^<]+)</strong>', block)
        if author_match:
            post['author'] = author_match.group(1).strip()
        else:
            return None
        
        # Author ID (do link profile)
        uid = re.search(r'profile\.php\?mode=viewprofile&(?:amp;)?u=(\d+)', block, re.IGNORECASE)
        if uid:
            post['author_id'] = uid.group(1)
        
        # Detalhes do autor
        details = re.search(r'class="postdetails">(.*?)</span>', block, re.DOTALL | re.IGNORECASE)
        if details:
            detail_text = details.group(1)
            
            # Mensagens
            msg_count = re.search(r'Mensagens:\s*(\d+)', detail_text)
            if msg_count:
                post['author_post_count'] = int(msg_count.group(1))
            
            # Localização
            loc = re.search(r'Localiza[çc][ãa]o:\s*(.+?)(?:<|$)', detail_text)
            if loc:
                post['author_location'] = html_to_text(loc.group(1)).strip()
        
        # Data
        date_match = re.search(r'Enviada:\s*\n?\s*(.+?)</td>', block, re.DOTALL | re.IGNORECASE)
        if date_match:
            date_raw = html_to_text(date_match.group(1)).strip()
            post['date_raw'] = date_raw
            post['date'] = self._parse_phpbb_date(date_raw)
        
        # Conteúdo
        content_match = re.search(
            r'class="postbody">\s*(?:<hr\s*/?>)?\s*(.*?)</td>',
            block, re.DOTALL | re.IGNORECASE
        )
        if content_match:
            raw = content_match.group(1)
            post['content_html'] = raw.strip()
            post['content_text'] = html_to_text(raw)
        
        # Assinatura (separada por _________________)
        if post.get('content_text'):
            sig_split = post['content_text'].split('_________________')
            if len(sig_split) > 1:
                post['content_text'] = sig_split[0].strip()
                post['signature'] = sig_split[1].strip()
        
        # E-mail link
        email_link = re.search(r'profile\.php\?mode=email&(?:amp;)?u=(\d+)', block, re.IGNORECASE)
        if email_link:
            post['author_email_available'] = True
        
        # ICQ
        icq = re.search(r'icq=(\d+)', block, re.IGNORECASE)
        if icq:
            post['author_icq'] = icq.group(1)
        
        # MSN
        msn = re.search(r'icon_msnm\.gif', block, re.IGNORECASE)
        if msn:
            post['author_has_msn'] = True
        
        # Hash para deduplicação
        dedupe_text = f"{post.get('author', '')}|{post.get('date_raw', '')}|{post.get('content_text', '')[:200]}"
        post['content_hash'] = content_hash(dedupe_text)
        
        return post

    def _parse_phpbb_date(self, date_str):
        """Converte data phpBB em PT-BR para ISO format."""
        # Formato: "Qui Abr 21, 2005 8:24 pm"
        date_str = date_str.strip()
        
        try:
            # Remover dia da semana
            parts = date_str.split(' ', 1)
            if len(parts) > 1 and parts[0].lower().rstrip(',') in self.DAYS_PT:
                date_str = parts[1].strip()
            
            # Parse: "Abr 21, 2005 8:24 pm"
            match = re.match(
                r'(\w+)\s+(\d{1,2}),?\s+(\d{4})\s+(\d{1,2}):(\d{2})\s*(am|pm)?',
                date_str, re.IGNORECASE
            )
            if match:
                month_str = match.group(1).lower()[:3]
                month = self.MONTHS_PT.get(month_str, 0)
                if month == 0:
                    return date_str
                
                day = int(match.group(2))
                year = int(match.group(3))
                hour = int(match.group(4))
                minute = int(match.group(5))
                ampm = (match.group(6) or '').lower()
                
                if ampm == 'pm' and hour != 12:
                    hour += 12
                elif ampm == 'am' and hour == 12:
                    hour = 0
                
                return datetime(year, month, day, hour, minute).isoformat()
        except Exception:
            pass
        
        return date_str

    def parse_forum_index(self, content, filepath=''):
        """Extrai lista de fóruns do index phpBB."""
        forums = []
        
        pattern = re.finditer(
            r'viewforum\.php\?f=(\d+)[^"]*"\s+class="nav">([^<]+)',
            content, re.IGNORECASE
        )
        
        seen = set()
        for m in pattern:
            fid = m.group(1)
            if fid in seen:
                continue
            seen.add(fid)
            
            # Buscar descrição
            desc = ''
            desc_match = re.search(
                rf'viewforum\.php\?f={fid}[^"]*"[^>]*>[^<]*</a>.*?class="genmed">([^<]+)',
                content, re.DOTALL | re.IGNORECASE
            )
            if desc_match:
                desc = html_to_text(desc_match.group(1))
            
            forums.append({
                'forum_id': fid,
                'name': html_to_text(m.group(2)),
                'description': desc,
                'source': 'sobresites.com',
                'source_file': os.path.basename(filepath),
            })
        
        return forums

    def parse_group(self, content, filepath=''):
        """Extrai informações de grupo."""
        group = {}
        
        title = re.search(r'<title>(.*?)</title>', content, re.IGNORECASE | re.DOTALL)
        if title:
            group['title'] = html_to_text(title.group(1))
        
        # Membros do grupo
        members = re.findall(r'profile\.php\?mode=viewprofile&(?:amp;)?u=(\d+)[^>]*>([^<]+)', content, re.IGNORECASE)
        group['members'] = [{'user_id': m[0], 'username': m[1].strip()} for m in members]
        group['source'] = 'sobresites.com'
        group['source_file'] = os.path.basename(filepath)
        
        return group


# ============================================================
# PIPELINE PRINCIPAL
# ============================================================

class ForumArchiveExtractor:
    """Pipeline principal de extração e deduplicação."""
    
    # Tamanho máximo por arquivo de posts (em bytes, ~10MB)
    MAX_CHUNK_BYTES = 10 * 1024 * 1024

    def __init__(self, input_dir, output_dir='./output'):
        self.input_dir = input_dir
        self.output_dir = output_dir
        self.asp_parser = ASPForumParser()
        self.phpbb_parser = PhpBBParser()
        
        # Dados extraídos (leves - ficam em memória)
        self.users = {}         # username -> user data (merge de fontes)
        self.topics = {}        # topic_id -> topic metadata
        self.forums = {}        # forum_id -> forum metadata
        self.groups = []
        self.errors = []
        self.stats = defaultdict(int)
        
        # Deduplicação (só hashes e IDs, não posts inteiros)
        self._seen_post_hashes = set()          # content_hash (fallback)
        self._seen_post_ids = {}                # (source, post_id) -> post (chave primária)
        self._seen_user_ids = {}                # (source, user_id) -> user data
        
        # Controle de escrita incremental de posts
        self._post_buffer = []
        self._post_buffer_bytes = 0
        self._post_chunk_index = 0
        self._total_posts_written = 0
    
    def run(self, verbose=True):
        """Executa o pipeline completo."""
        os.makedirs(self.output_dir, exist_ok=True)
        
        files = self._list_html_files()
        if verbose:
            print(f"\n{'='*60}")
            print(f"  SobreSites Forum Archive Extractor")
            print(f"{'='*60}")
            print(f"  Diretório de entrada: {self.input_dir}")
            print(f"  Arquivos encontrados: {len(files)}")
            print(f"  Tamanho max por JSON:  {self.MAX_CHUNK_BYTES // (1024*1024)}MB")
            print(f"{'='*60}\n")
        
        for i, filepath in enumerate(files):
            self._process_file(filepath, verbose)
            
            # Progresso a cada 500 arquivos
            if verbose and (i + 1) % 500 == 0:
                print(f"  ... {i+1}/{len(files)} arquivos processados, "
                      f"{self._total_posts_written + len(self._post_buffer)} posts extraídos")
        
        # Flush posts restantes no buffer
        self._flush_post_buffer()
        
        # Consolidar e salvar dados leves
        self._consolidate_users()
        self._save_metadata()
        
        if verbose:
            self._print_summary()
    
    def _list_html_files(self):
        """Lista todos os arquivos HTML no diretório e subdiretórios (recursivo).
        
        O Wayback Machine salva arquivos em estrutura de pastas do site original,
        então os HTMLs podem estar espalhados em subdiretórios.
        Ignora pastas _lixo (criadas pelo cleaner).
        """
        files = []
        for dirpath, dirnames, filenames in os.walk(self.input_dir):
            # Ignorar pasta _lixo e pastas ocultas
            dirnames[:] = [d for d in dirnames if d != '_lixo' and not d.startswith('.')]
            
            for f in filenames:
                fpath = os.path.join(dirpath, f)
                if os.path.isfile(fpath):
                    files.append(fpath)
        return sorted(files)
    
    def _process_file(self, filepath, verbose=True):
        """Processa um arquivo individual."""
        filename = os.path.basename(filepath)
        
        content, encoding = read_file_auto_encoding(filepath)
        source = detect_source(filepath, content)
        page_type = detect_page_type(filepath, content)
        
        self.stats['total_files'] += 1
        
        if is_junk_page(page_type):
            self.stats['junk_files'] += 1
            if verbose:
                print(f"  [LIXO]    {filename[:60]}... ({page_type})")
            return
        
        if verbose:
            print(f"  [{source.upper():5s}] [{page_type:12s}] {filename[:50]}...")
        
        try:
            if source == 'asp':
                self._process_asp_file(content, filepath, page_type)
            elif source == 'phpbb':
                self._process_phpbb_file(content, filepath, page_type)
            else:
                self.stats['unknown_files'] += 1
                self.errors.append({'file': filename, 'error': 'Fonte desconhecida'})
        except Exception as e:
            self.stats['error_files'] += 1
            self.errors.append({'file': filename, 'error': str(e)})
            if verbose:
                print(f"    ERRO: {e}")
    
    def _process_asp_file(self, content, filepath, page_type):
        """Processa arquivo do fórum ASP."""
        if page_type == 'topic':
            posts = self.asp_parser.parse_topic(content, filepath)
            self._add_posts(posts)
            self.stats['asp_posts'] += len(posts)
            
        elif page_type == 'profile':
            profile = self.asp_parser.parse_profile(content, filepath)
            if profile.get('username'):
                key = ('asp', profile.get('user_id', ''))
                self._seen_user_ids[key] = profile
                self.stats['asp_profiles'] += 1
                
        elif page_type == 'members_list':
            members = self.asp_parser.parse_members_list(content, filepath)
            for m in members:
                key = ('asp', m.get('user_id', ''))
                if key not in self._seen_user_ids:
                    self._seen_user_ids[key] = m
                else:
                    self._seen_user_ids[key].update({k: v for k, v in m.items() if v})
            self.stats['asp_members'] += len(members)
            
        elif page_type == 'forum_list':
            topics = self.asp_parser.parse_forum_list(content, filepath)
            for t in topics:
                self.topics[f"asp_{t['topic_id']}"] = t
            self.stats['asp_topics_indexed'] += len(topics)
            
        elif page_type == 'post_reply':
            # Primeiro tentar extrair posts normais (caso a página tenha posts visíveis)
            posts = self.asp_parser.parse_topic(content, filepath)
            self._add_posts(posts)
            self.stats['asp_posts'] += len(posts)
            
            # Também extrair metadados e conteúdo quotado do formulário
            reply_data = self.asp_parser.parse_reply_page(content, filepath)
            
            if reply_data['topic_metadata']:
                meta = reply_data['topic_metadata']
                tid = meta.get('topic_id', '')
                if tid:
                    key = f"asp_{tid}"
                    if key not in self.topics:
                        self.topics[key] = meta
                    else:
                        # Merge: preencher campos vazios
                        for k, v in meta.items():
                            if v and not self.topics[key].get(k):
                                self.topics[key][k] = v
                    self.stats['asp_topics_indexed'] = self.stats.get('asp_topics_indexed', 0) + 1
                
                # Registrar fórum
                fid = meta.get('forum_id', '')
                if fid:
                    fkey = f"asp_{fid}"
                    if fkey not in self.forums:
                        self.forums[fkey] = {
                            'forum_id': fid,
                            'name': meta.get('forum_name', ''),
                            'cat_id': meta.get('cat_id', ''),
                            'source': 'sobresites.com.br',
                        }
            
            if reply_data['quoted_post']:
                self._add_posts([reply_data['quoted_post']])
                self.stats['asp_quoted_posts'] = self.stats.get('asp_quoted_posts', 0) + 1
            
        elif page_type == 'index':
            # Extrair lista de fóruns se disponível
            forum_links = re.findall(
                r'FORUM\.asp\?FORUM_ID=(\d+)[^>]*>([^<]+)',
                content, re.IGNORECASE
            )
            for fid, fname in forum_links:
                self.forums[f"asp_{fid}"] = {
                    'forum_id': fid,
                    'name': html_to_text(fname),
                    'source': 'sobresites.com.br'
                }
        
        self.stats['asp_files'] += 1
    
    def _process_phpbb_file(self, content, filepath, page_type):
        """Processa arquivo do fórum phpBB."""
        if page_type == 'topic':
            posts = self.phpbb_parser.parse_topic(content, filepath)
            self._add_posts(posts)
            self.stats['phpbb_posts'] += len(posts)
            
        elif page_type == 'profile':
            # Perfis phpBB podem estar vazios ("Esse Usuário não existe")
            if 'não existe' not in content.lower():
                self.stats['phpbb_profiles'] += 1
                
        elif page_type == 'index':
            forums = self.phpbb_parser.parse_forum_index(content, filepath)
            for f in forums:
                self.forums[f"phpbb_{f['forum_id']}"] = f
            self.stats['phpbb_forums_indexed'] += len(forums)
            
        elif page_type == 'group':
            group = self.phpbb_parser.parse_group(content, filepath)
            if group.get('members'):
                self.groups.append(group)
                self.stats['phpbb_groups'] += 1
                # Registrar membros do grupo
                for m in group['members']:
                    key = ('phpbb', m['user_id'])
                    if key not in self._seen_user_ids:
                        self._seen_user_ids[key] = m
                        
        elif page_type == 'post_reply':
            posts = self.phpbb_parser.parse_topic(content, filepath)
            self._add_posts(posts)
            self.stats['phpbb_posts'] += len(posts)
        
        self.stats['phpbb_files'] += 1
    
    def _add_posts(self, posts):
        """Adiciona posts ao buffer com deduplicação robusta.
        
        Estratégia de deduplicação em duas camadas:
        
        1. CHAVE PRIMÁRIA: (source, post_id) - identifica o post unicamente.
           Se o mesmo post_id aparece em dois HTMLs diferentes (ex: páginas
           diferentes do Wayback Machine), mantém a versão com mais conteúdo
           (que pode ser uma versão editada).
        
        2. FALLBACK: content_hash - para posts sem post_id, usa hash do
           conteúdo para evitar duplicatas exatas.
        
        Quando o buffer atinge MAX_CHUNK_BYTES, grava em disco automaticamente.
        """
        for post in posts:
            post_id = post.get('post_id', '')
            source = post.get('source', '')
            
            # === Camada 1: dedup por post_id ===
            if post_id:
                primary_key = (source, post_id)
                
                if primary_key in self._seen_post_ids:
                    prev = self._seen_post_ids[primary_key]
                    prev_len = len(prev.get('content_text', ''))
                    curr_len = len(post.get('content_text', ''))
                    
                    if curr_len > prev_len:
                        # Versão mais completa (possível edit) - substituir
                        self._replace_post_in_buffer(prev, post)
                        self._seen_post_ids[primary_key] = post
                        self.stats['updated_posts'] = self.stats.get('updated_posts', 0) + 1
                    else:
                        # Duplicata idêntica ou menor - descartar
                        self.stats['duplicate_posts'] = self.stats.get('duplicate_posts', 0) + 1
                    continue
                
                self._seen_post_ids[primary_key] = post
            
            # === Camada 2: dedup por content_hash (fallback) ===
            else:
                h = post.get('content_hash', '')
                if h:
                    if h in self._seen_post_hashes:
                        self.stats['duplicate_posts'] = self.stats.get('duplicate_posts', 0) + 1
                        continue
                    self._seen_post_hashes.add(h)
            
            # Extrair dados de usuário antes de bufferizar
            self._collect_user_from_post(post)
            
            # Estimar tamanho em bytes
            post_json = json.dumps(post, ensure_ascii=False, default=str)
            post_bytes = len(post_json.encode('utf-8'))
            
            self._post_buffer.append(post)
            self._post_buffer_bytes += post_bytes
            
            # Flush se atingiu o limite
            if self._post_buffer_bytes >= self.MAX_CHUNK_BYTES:
                self._flush_post_buffer()
    
    def _replace_post_in_buffer(self, old_post, new_post):
        """Substitui um post no buffer por uma versão atualizada (edit).
        
        Se o post antigo já foi gravado em disco (flush anterior),
        não conseguimos substituir retroativamente - mas isso é raro
        e aceitável, pois a versão mais recente será a última encontrada.
        Se ainda está no buffer, substitui diretamente.
        """
        old_id = old_post.get('post_id', '')
        for i, buffered in enumerate(self._post_buffer):
            if buffered.get('post_id') == old_id and buffered.get('source') == old_post.get('source'):
                # Recalcular bytes
                old_json = json.dumps(buffered, ensure_ascii=False, default=str)
                new_json = json.dumps(new_post, ensure_ascii=False, default=str)
                self._post_buffer_bytes += len(new_json.encode('utf-8')) - len(old_json.encode('utf-8'))
                self._post_buffer[i] = new_post
                return
        
        # Post já foi flushed - adicionar a nova versão como entrada separada
        # (a versão antiga fica no arquivo já gravado, mas com conteúdo menor)
        post_json = json.dumps(new_post, ensure_ascii=False, default=str)
        self._post_buffer.append(new_post)
        self._post_buffer_bytes += len(post_json.encode('utf-8'))
    
    def _collect_user_from_post(self, post):
        """Extrai dados de usuário de um post para consolidação posterior."""
        author = post.get('author', '').strip()
        if not author:
            return
        uname = author.lower()
        
        user_data = {
            'username': author,
            'source': post.get('source', ''),
        }
        if post.get('author_id'):
            user_data['user_id'] = post['author_id']
        if post.get('author_location'):
            user_data['location'] = post['author_location']
        if post.get('author_post_count'):
            user_data['post_count'] = post['author_post_count']
        if post.get('author_icq'):
            user_data['icq'] = post['author_icq']
        if post.get('author_homepage'):
            user_data['homepage'] = post['author_homepage']
        if post.get('author_rank'):
            user_data['rank'] = post['author_rank']
        
        # Acumular em _seen_user_ids para merge depois
        key = (post.get('source', ''), post.get('author_id', uname))
        if key not in self._seen_user_ids:
            self._seen_user_ids[key] = user_data
        else:
            # Merge: preencher campos vazios
            existing = self._seen_user_ids[key]
            for k, v in user_data.items():
                if v and (k not in existing or not existing[k]):
                    existing[k] = v

    def _flush_post_buffer(self):
        """Grava o buffer de posts em disco como um arquivo JSON numerado."""
        if not self._post_buffer:
            return
        
        self._post_chunk_index += 1
        chunk_file = os.path.join(
            self.output_dir, 
            f'posts_{self._post_chunk_index:04d}.json'
        )
        
        with open(chunk_file, 'w', encoding='utf-8') as f:
            json.dump(self._post_buffer, f, ensure_ascii=False, indent=2, default=str)
        
        count = len(self._post_buffer)
        size_mb = self._post_buffer_bytes / (1024 * 1024)
        self._total_posts_written += count
        
        print(f"    -> Gravado {chunk_file}: {count} posts ({size_mb:.1f}MB)")
        
        # Limpar buffer
        self._post_buffer = []
        self._post_buffer_bytes = 0
    
    def _consolidate_users(self):
        """Consolida dados de usuários de múltiplas fontes, fazendo merge por nome."""
        # Indexar por username normalizado
        by_username = defaultdict(list)
        
        for (source, uid), data in self._seen_user_ids.items():
            uname = data.get('username', '').strip().lower()
            if uname:
                by_username[uname].append(data)
        
        # Merge: combinar dados de todas as fontes para cada usuário
        for uname, entries in by_username.items():
            merged = {}
            for entry in entries:
                for k, v in entry.items():
                    if v and (k not in merged or not merged[k]):
                        merged[k] = v
            
            # Preservar IDs de ambas as fontes
            asp_ids = [e.get('user_id') for e in entries if e.get('source') == 'sobresites.com.br' and e.get('user_id')]
            phpbb_ids = [e.get('user_id') for e in entries if e.get('source') == 'sobresites.com' and e.get('user_id')]
            
            if asp_ids:
                merged['asp_user_id'] = asp_ids[0]
            if phpbb_ids:
                merged['phpbb_user_id'] = phpbb_ids[0]
            
            # Fontes onde o usuário aparece
            sources = list(set(e.get('source', '') for e in entries if e.get('source')))
            merged['sources'] = sources
            
            self.users[uname] = merged
        
        self.stats['unique_users'] = len(self.users)
    
    def _save_metadata(self):
        """Salva metadados (usuários, fóruns, tópicos, stats).
        
        Posts já foram salvos incrementalmente em posts_NNNN.json.
        """
        # Atualizar stats finais
        self.stats['unique_posts'] = self._total_posts_written
        self.stats['post_files'] = self._post_chunk_index
        
        # Usuários
        users_file = os.path.join(self.output_dir, 'users.json')
        with open(users_file, 'w', encoding='utf-8') as f:
            json.dump(self.users, f, ensure_ascii=False, indent=2, default=str)
        
        # Tópicos indexados
        topics_file = os.path.join(self.output_dir, 'topics.json')
        with open(topics_file, 'w', encoding='utf-8') as f:
            json.dump(self.topics, f, ensure_ascii=False, indent=2, default=str)
        
        # Fóruns
        forums_file = os.path.join(self.output_dir, 'forums.json')
        with open(forums_file, 'w', encoding='utf-8') as f:
            json.dump(self.forums, f, ensure_ascii=False, indent=2, default=str)
        
        # Grupos
        if self.groups:
            groups_file = os.path.join(self.output_dir, 'groups.json')
            with open(groups_file, 'w', encoding='utf-8') as f:
                json.dump(self.groups, f, ensure_ascii=False, indent=2, default=str)
        
        # Erros
        if self.errors:
            errors_file = os.path.join(self.output_dir, 'extraction_errors.json')
            with open(errors_file, 'w', encoding='utf-8') as f:
                json.dump(self.errors, f, ensure_ascii=False, indent=2)
        
        # Estatísticas
        stats_file = os.path.join(self.output_dir, 'stats.json')
        with open(stats_file, 'w', encoding='utf-8') as f:
            json.dump(dict(self.stats), f, ensure_ascii=False, indent=2)
    
    def _print_summary(self):
        """Imprime resumo da extração."""
        s = self.stats
        print(f"\n{'='*60}")
        print(f"  RESUMO DA EXTRAÇÃO")
        print(f"{'='*60}")
        print(f"  Arquivos processados:     {s.get('total_files', 0)}")
        print(f"    - ASP (sobresites.com.br): {s.get('asp_files', 0)}")
        print(f"    - phpBB (sobresites.com):  {s.get('phpbb_files', 0)}")
        print(f"    - Lixo descartado:         {s.get('junk_files', 0)}")
        print(f"    - Erros:                   {s.get('error_files', 0)}")
        print(f"")
        print(f"  Posts extraídos:")
        print(f"    - ASP:    {s.get('asp_posts', 0)}")
        print(f"    - phpBB:  {s.get('phpbb_posts', 0)}")
        print(f"    - Duplicatas removidas: {s.get('duplicate_posts', 0)}")
        print(f"    - Posts atualizados:    {s.get('updated_posts', 0)} (edits)")
        print(f"    - Posts únicos:         {self._total_posts_written}")
        print(f"    - Arquivos gerados:     {self._post_chunk_index} (posts_NNNN.json)")
        print(f"")
        print(f"  Usuários únicos:          {s.get('unique_users', 0)}")
        print(f"    - Perfis ASP:           {s.get('asp_profiles', 0)}")
        print(f"    - Membros ASP:          {s.get('asp_members', 0)}")
        print(f"    - Grupos phpBB:         {s.get('phpbb_groups', 0)}")
        print(f"")
        print(f"  Catálogo:")
        print(f"    - Tópicos indexados:    {len(self.topics)}")
        print(f"    - Fóruns mapeados:      {len(self.forums)}")
        print(f"{'='*60}")
        print(f"  Resultados salvos em: {self.output_dir}/")
        print(f"{'='*60}\n")


# ============================================================
# ENTRY POINT
# ============================================================

def get_paths():
    """Obtém caminhos de entrada e saída, por argumento ou interativamente."""
    
    if len(sys.argv) > 1:
        # Recebeu por argumento
        input_dir = sys.argv[1].strip().strip('"').strip("'")
        if len(sys.argv) > 2:
            output_dir = sys.argv[2].strip().strip('"').strip("'")
        else:
            output_dir = None
        return input_dir, output_dir
    
    # Modo interativo
    print()
    print("=" * 70)
    print("  SobreSites Forum Archive Extractor")
    print("  Extrai posts, usuarios e dados de paginas HTML do forum")
    print("=" * 70)
    print()
    print("  Informe a pasta com os arquivos HTML do forum.")
    print(r"  Exemplo: C:\Users\shoit\websites\www.sobresites.com.br\anime\forum")
    print()
    
    input_dir = input("  Pasta de entrada: ").strip().strip('"').strip("'")
    
    print()
    print("  Informe a pasta de saida para os JSONs extraidos.")
    print(r"  Exemplo: C:\Users\shoit\SS")
    print()
    
    output_dir = input("  Pasta de saida: ").strip().strip('"').strip("'")
    
    return input_dir, output_dir or None


if __name__ == '__main__':
    input_dir, output_dir = get_paths()
    
    if not input_dir:
        print("  Nenhuma pasta informada.")
    elif not os.path.isdir(input_dir):
        print(f"\n  ERRO: Pasta nao encontrada: {input_dir}")
    else:
        if not output_dir:
            # Default: criar pasta 'output' ao lado da pasta de entrada
            output_dir = os.path.join(os.path.dirname(input_dir), 'SS_output')
        
        extractor = ForumArchiveExtractor(input_dir, output_dir)
        extractor.run(verbose=True)
    
    print()
    input("  Pressione ENTER para sair...")