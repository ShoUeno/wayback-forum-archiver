#!/usr/bin/env python3
"""
SobreSites File Renamer
========================
Renomeia arquivos salvos do Wayback Machine (com nomes URL-encoded)
para nomes legiveis com extensao .html, diretamente na mesma pasta.

Uso:
  python renamer.py                         (pede a pasta interativamente)
  python renamer.py "C:\\Users\\...\\forum"   (recebe a pasta por argumento)
"""

import os
import re
import sys
from urllib.parse import unquote


def decode_filename(encoded_name):
    """Decodifica nome URL-encoded (pode ter dupla codificacao do Wayback Machine)."""
    decoded = unquote(unquote(encoded_name))
    return decoded


def extract_params(decoded_name):
    """Extrai o nome base e parametros da query string."""
    if '?' in decoded_name:
        base, query = decoded_name.split('?', 1)
    else:
        return decoded_name, {}

    params = {}
    for pair in re.split(r'[&;]', query):
        pair = pair.replace('amp;', '')
        if '=' in pair:
            key, val = pair.split('=', 1)
            params[key.strip()] = val.strip()
        elif pair:
            params[pair] = ''

    return base, params


def generate_clean_name(decoded_name):
    """Gera nome limpo e descritivo para o arquivo."""
    base, params = extract_params(decoded_name)
    base_lower = base.lower()

    # ========================
    # PAGINAS ASP (sobresites.com.br)
    # ========================

    if 'topic.asp' in base_lower:
        topic_id = params.get('TOPIC_ID', params.get('topic_id', 'unknown'))
        page = params.get('whichpage', '1')
        archive = '_archive' if params.get('ARCHIVEVIEW') or params.get('ARCHIVE') else ''
        return f"asp_topic_{topic_id}_p{page}{archive}.html"

    if 'forum.asp' in base_lower:
        forum_id = params.get('FORUM_ID', params.get('forum_id', 'unknown'))
        page = params.get('whichpage', '1')
        return f"asp_forum_{forum_id}_p{page}.html"

    if 'pop_profile.asp' in base_lower:
        mode = params.get('mode', 'display')
        uid = params.get('id', 'unknown')
        return f"asp_profile_{uid}_{mode}.html"

    if 'members.asp' in base_lower:
        m_name = params.get('M_NAME', params.get('m_name', 'all'))
        method = params.get('method', '')
        suffix = f"_{m_name}" if m_name else ''
        if method:
            suffix += f"_{method}"
        return f"asp_members{suffix}.html"

    if 'post.asp' in base_lower:
        method = params.get('method', 'unknown')
        topic_id = params.get('TOPIC_ID', params.get('topic_id', ''))
        reply_id = params.get('REPLY_ID', params.get('reply_id', ''))
        return f"asp_post_{method}_t{topic_id}_r{reply_id}.html"

    if 'default.asp' in base_lower:
        cat_id = params.get('CAT_ID', params.get('cat_id', ''))
        return f"asp_index_cat{cat_id}.html"

    if 'active.asp' in base_lower:
        return "asp_active.html"

    if 'search.asp' in base_lower:
        return "asp_search.html"

    if 'faq.asp' in base_lower:
        return "asp_faq.html"

    if 'policy.asp' in base_lower:
        return "asp_policy.html"

    if 'pop_pword.asp' in base_lower:
        return "asp_password_recovery.html"

    if 'pop_mail.asp' in base_lower:
        uid = params.get('id', 'unknown')
        return f"asp_mail_{uid}.html"

    if 'pop_messengers.asp' in base_lower:
        return "asp_messengers.html"

    # ========================
    # PAGINAS phpBB (sobresites.com)
    # ========================

    if 'viewtopic.php' in base_lower:
        topic_id = params.get('t', '')
        post_id = params.get('p', '')
        start = params.get('start', '')
        if topic_id:
            suffix = f"_s{start}" if start else ''
            return f"phpbb_topic_{topic_id}{suffix}.html"
        elif post_id:
            return f"phpbb_post_{post_id}.html"
        return "phpbb_viewtopic_unknown.html"

    if 'viewforum.php' in base_lower:
        forum_id = params.get('f', 'unknown')
        start = params.get('start', '')
        suffix = f"_s{start}" if start else ''
        return f"phpbb_forum_{forum_id}{suffix}.html"

    if 'profile.php' in base_lower:
        mode = params.get('mode', 'viewprofile')
        uid = params.get('u', 'unknown')
        return f"phpbb_profile_{uid}_{mode}.html"

    if 'posting.php' in base_lower:
        mode = params.get('mode', 'unknown')
        post_id = params.get('p', '')
        return f"phpbb_posting_{mode}_p{post_id}.html"

    if 'memberlist.php' in base_lower:
        start = params.get('start', '')
        suffix = f"_s{start}" if start else ''
        return f"phpbb_memberlist{suffix}.html"

    if 'groupcp.php' in base_lower:
        gid = params.get('g', 'unknown')
        return f"phpbb_group_{gid}.html"

    if 'login.php' in base_lower:
        return "phpbb_login.html"

    if 'search.php' in base_lower:
        return "phpbb_search.html"

    if 'faq.php' in base_lower:
        return "phpbb_faq.html"

    if 'index.php' in base_lower:
        cat = params.get('c', '')
        rubrik = params.get('iRubrikID', '')
        if rubrik:
            return f"phpbb_index_rubrik{rubrik}.html"
        elif cat:
            return f"phpbb_index_c{cat}.html"
        return "phpbb_index.html"

    # ========================
    # FALLBACK: limpar caracteres invalidos
    # ========================
    clean = re.sub(r'[^\w.-]', '_', decoded_name)
    clean = re.sub(r'_+', '_', clean).strip('_')
    if not clean.endswith('.html'):
        clean += '.html'
    return clean


def has_real_extension(filename):
    """Verifica se o arquivo tem uma extensao real (nao query string)."""
    # Extensoes reais de arquivos que NAO devem ser renomeados
    real_extensions = {
        '.gif', '.jpg', '.jpeg', '.png', '.bmp', '.ico', '.svg', '.webp',
        '.css', '.js',
        '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.txt', '.xml',
        '.zip', '.rar', '.gz', '.tar',
        '.mp3', '.wav', '.ogg', '.mp4', '.avi', '.wmv', '.flv', '.swf',
        '.ttf', '.woff', '.woff2', '.eot',
        '.html', '.htm',
    }
    # Pegar a extensao real do nome (ignorando query strings)
    # Ex: "imagem.gif" -> .gif (real)
    # Ex: "topic.asp%3fTOPIC_ID%3d79" -> nenhuma extensao real
    # Ex: "asp_topic_79_p2.html" -> .html (real)
    
    # Se tem % ou ? ou & no nome, a "extensao" pode ser falsa
    # Primeiro decodificar para ver o nome real
    clean = filename.split('%')[0].split('?')[0].split('&')[0]
    
    _, ext = os.path.splitext(clean)
    ext = ext.lower()
    
    # .asp e .php NAO sao extensoes reais no contexto do Wayback Machine
    # (sao paginas dinamicas que precisam virar .html)
    if ext in ('.asp', '.php'):
        return False
    
    return ext in real_extensions


def needs_renaming(filename):
    """Verifica se o arquivo precisa ser renomeado.
    
    So renomeia arquivos que sao paginas do forum salvas do Wayback Machine:
    - Nomes URL-encoded (com %3f, %3d, etc.)
    - Paginas .asp e .php (com query strings no nome)
    
    NAO renomeia:
    - Arquivos com extensao real (.gif, .jpg, .css, .html, etc.)
    - Arquivos ja renomeados pelo script (asp_*, phpbb_*)
    """
    # Ja foi renomeado antes (padrao asp_* ou phpbb_*)
    if filename.startswith(('asp_', 'phpbb_')) and filename.endswith('.html'):
        return False
    
    # Tem extensao real -> nao mexer
    if has_real_extension(filename):
        return False
    
    # A partir daqui, so renomear se tiver sinais claros de pagina do forum
    
    # Tem sinais de URL-encoding
    if '%' in filename:
        return True
    
    # Tem query string no nome (paginas dinamicas salvas como arquivo)
    if '?' in filename or '&' in filename:
        return True
    
    # Nome contem .asp ou .php (paginas dinamicas do forum)
    if re.search(r'\.(asp|php)', filename, re.IGNORECASE):
        return True
    
    # Qualquer outro arquivo (sem extensao ou extensao desconhecida) -> nao mexer
    return False


def rename_files(pasta):
    """Renomeia todos os arquivos URL-encoded da pasta e subpastas, in-place."""

    if not os.path.isdir(pasta):
        print(f"\n  ERRO: Pasta nao encontrada: {pasta}")
        return []

    # Coletar arquivos recursivamente
    to_rename = []      # (dirpath, original_filename)
    already_clean = 0

    for dirpath, dirnames, filenames in os.walk(pasta):
        # Ignorar pastas _lixo e ocultas
        dirnames[:] = [d for d in dirnames if d != '_lixo' and not d.startswith('.')]

        for original in sorted(filenames):
            filepath = os.path.join(dirpath, original)
            if not os.path.isfile(filepath):
                continue
            if needs_renaming(original):
                to_rename.append((dirpath, original))
            else:
                already_clean += 1

    if not to_rename:
        print(f"\n  Nenhum arquivo para renomear em: {pasta}")
        if already_clean > 0:
            print(f"  ({already_clean} arquivos ja estao com nomes limpos)")
        return []

    # Gerar novos nomes e verificar colisoes (por pasta)
    name_map = {}  # (dirpath, original) -> new_name
    used_names_per_dir = {}  # dirpath -> set of used names

    for dirpath, original in to_rename:
        decoded = decode_filename(original)
        new_name = generate_clean_name(decoded)

        # Colisoes por pasta
        if dirpath not in used_names_per_dir:
            used_names_per_dir[dirpath] = set()
        used = used_names_per_dir[dirpath]

        if new_name in used or (
            os.path.exists(os.path.join(dirpath, new_name)) and new_name != original
        ):
            base, ext = os.path.splitext(new_name)
            counter = 2
            while f"{base}_{counter}{ext}" in used:
                counter += 1
            new_name = f"{base}_{counter}{ext}"

        used.add(new_name)
        name_map[(dirpath, original)] = new_name

    # Mostrar preview
    print(f"\n{'='*70}")
    print(f"  SobreSites File Renamer")
    print(f"{'='*70}")
    print(f"  Pasta raiz: {pasta}")
    print(f"  Arquivos para renomear: {len(name_map)}")
    if already_clean > 0:
        print(f"  Arquivos ja limpos:     {already_clean} (ignorados)")
    print(f"{'='*70}\n")

    for (dirpath, original), new_name in sorted(name_map.items()):
        # Mostrar caminho relativo para clareza
        rel_dir = os.path.relpath(dirpath, pasta)
        if rel_dir == '.':
            display_orig = original
        else:
            display_orig = os.path.join(rel_dir, original)

        if len(display_orig) > 48:
            display_orig = display_orig[:22] + '...' + display_orig[-22:]

        if rel_dir == '.':
            display_new = new_name
        else:
            display_new = os.path.join(rel_dir, new_name)

        print(f"  {display_orig:50s} -> {display_new}")

    # Pedir confirmacao
    print(f"\n{'='*70}")
    resposta = input("  Confirma renomear? (s/n): ").strip().lower()

    if resposta not in ('s', 'sim', 'y', 'yes'):
        print("  Operacao cancelada.")
        return []

    # Executar renomeacao em 2 passos (evitar colisao circular)
    # Passo 1: renomear para nomes temporarios
    temp_map = {}
    for (dirpath, original), new_name in name_map.items():
        src = os.path.join(dirpath, original)
        temp_name = f"__temp_rename__{new_name}"
        temp_path = os.path.join(dirpath, temp_name)
        try:
            os.rename(src, temp_path)
            temp_map[(dirpath, temp_name)] = new_name
        except OSError as e:
            print(f"  ERRO ao renomear '{original}': {e}")

    # Passo 2: renomear de temporario para final
    renamed = 0
    for (dirpath, temp_name), final_name in temp_map.items():
        src = os.path.join(dirpath, temp_name)
        dst = os.path.join(dirpath, final_name)
        try:
            os.rename(src, dst)
            renamed += 1
        except OSError as e:
            print(f"  ERRO ao finalizar '{final_name}': {e}")

    print(f"\n  {renamed} arquivos renomeados com sucesso!")
    return list(name_map.values())


def get_pasta():
    """Obtem o caminho da pasta, por argumento ou interativamente."""

    # Se recebeu por argumento
    if len(sys.argv) > 1:
        pasta = ' '.join(sys.argv[1:])
        pasta = pasta.strip().strip('"').strip("'")
        return pasta

    # Senao, pedir interativamente
    print()
    print("=" * 70)
    print("  SobreSites File Renamer")
    print("  Renomeia arquivos do Wayback Machine para nomes legiveis .html")
    print("=" * 70)
    print()
    print("  Cole o caminho da pasta com os arquivos do forum.")
    print(r"  Exemplo: C:\Users\shoit\websites\www.sobresites.com.br\anime\forum")
    print()

    pasta = input("  Pasta: ").strip().strip('"').strip("'")
    return pasta


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == '__main__':
    pasta = get_pasta()

    if not pasta:
        print("  Nenhuma pasta informada.")
    else:
        rename_files(pasta)

    print()
    input("  Pressione ENTER para sair...")