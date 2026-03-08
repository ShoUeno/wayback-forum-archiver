#!/usr/bin/env python3
"""
SobreSites Junk Cleaner
=========================
Detecta e deleta paginas sem conteudo util do forum phpBB.

Tipos de lixo detectados:
  - Erro 429 (Too Many Requests) do Wayback Machine
  - Paginas de erro do phpBB ("Usuario nao existe", "Topico nao existe", etc.)
  - Paginas funcionais sem conteudo (login, registro, "quem esta online", etc.)
  - Paginas de mensagem privada (desativada/erro)
  - Paginas de posting sem conteudo (quote/reply com erro)

Uso:
  python cleaner.py                          (pede a pasta interativamente)
  python cleaner.py "C:\\Users\\...\\forum"    (recebe por argumento)
"""

import os
import re
import sys


# ============================================================
# PADROES DE LIXO
# ============================================================

# Mensagens de erro do phpBB que indicam pagina sem conteudo util
PHPBB_ERROR_MESSAGES = [
    # Erros de usuario/perfil
    r'Esse Usu.rio n.o existe',
    r'N.o foi especificado um Usu.rio',
    r'O Usu.rio especificado n.o existe',
    r'Este perfil n.o existe',

    # Erros de topico/mensagem/forum
    r'O t.pico ou mensagem que pretende exibir n.o existe',
    r'O t.pico n.o existe',
    r'A mensagem n.o existe',
    r'N.o foi especificado o ID da mensagem',
    r'Deve ser selecionado o T.pico a responder',
    r'N.o foi especificado um f.rum',
    r'O f.rum n.o existe',
    r'Este f.rum n.o existe',
    r'O f.rum selecionado n.o existe',

    # Mensagens privadas
    r'As Mensagens Particulares foram desativadas',
    r'Mensagens Particulares desativadas',
    r'N.o foi poss.vel enviar a mensagem',

    # Sessao/login
    r'A sess.o expirou',
    r'Voc. n.o est. autorizado',
    r'N.o est. logado',
    r'Deve estar logado para',
    r'Login inv.lido',
    r'Deve estar registrado e logado',

    # Busca
    r'Nenhum resultado encontrado',
    r'Termos de busca muito curtos',
    r'N.o houve resultados',

    # Erros genericos
    r'N.o foi poss.vel completar a opera',
    r'Erro de processamento',
    r'Opera..o n.o permitida',
]

# Paginas funcionais sem conteudo de forum (por titulo ou conteudo)
PHPBB_JUNK_PAGE_PATTERNS = [
    # Paginas de registro/termos
    r'Termos de Uso e Condi..es para Cadastro',
    r'Cadastre-se</title>',
    r'Li as regras e aceitos os termos',

    # Paginas de login
    r'<title>[^<]*Login[^<]*</title>',

    # Recuperacao de senha
    r'Envie-me uma nova senha',
    r'mode=sendpassword',

    # "Quem esta online"
    r'Quem est. ligado</title>',
    r'Usu.rios navegando neste f.rum</title>',

    # Paginas de FAQ do phpBB
    r'<title>[^<]*FAQ[^<]*</title>',

    # Paginas de busca (formulario vazio)
    r'<title>[^<]*Busca[^<]*</title>',
]

# Erro HTTP do Wayback Machine
WAYBACK_ERROR_PATTERNS = [
    r'429 Too Many Requests',
    r'502 Bad Gateway',
    r'503 Service Unavailable',
    r'404 Not Found',
    r'Got an HTTP 30[12]',
    r'Wayback Machine has not archived that URL',
    r'This URL has been excluded',
]


def read_file_safe(filepath):
    """Le arquivo com deteccao automatica de encoding."""
    with open(filepath, 'rb') as f:
        raw = f.read()

    # Arquivos muito pequenos sao suspeitos
    if len(raw) < 50:
        return raw.decode('utf-8', errors='replace'), len(raw)

    for enc in ['utf-8', 'iso-8859-1', 'cp1252']:
        try:
            return raw.decode(enc), len(raw)
        except (UnicodeDecodeError, UnicodeError):
            continue

    return raw.decode('iso-8859-1', errors='replace'), len(raw)


def classify_junk(filepath, content, filesize):
    """
    Classifica o arquivo como lixo ou conteudo util.

    Retorna:
        None se o arquivo tem conteudo util
        String com o motivo se for lixo
    """
    filename = os.path.basename(filepath).lower()

    # Ignorar arquivos com extensao real (nao-HTML)
    # O cleaner so analisa paginas do forum, nao imagens/css/etc
    non_html_extensions = {
        '.gif', '.jpg', '.jpeg', '.png', '.bmp', '.ico', '.svg', '.webp',
        '.css', '.js', '.json',
        '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.txt', '.xml',
        '.zip', '.rar', '.gz', '.tar',
        '.mp3', '.wav', '.ogg', '.mp4', '.avi', '.wmv', '.flv', '.swf',
        '.ttf', '.woff', '.woff2', '.eot',
    }
    _, ext = os.path.splitext(filename)
    if ext in non_html_extensions:
        return None  # Manter - nao e pagina HTML

    # -------------------------------------------------------
    # 1. Erros HTTP do Wayback Machine
    # -------------------------------------------------------
    for pattern in WAYBACK_ERROR_PATTERNS:
        if re.search(pattern, content, re.IGNORECASE):
            return f"Erro Wayback: {pattern.replace(chr(92), '')}"

    # -------------------------------------------------------
    # 2. Arquivos muito pequenos (< 500 bytes) sem HTML valido
    # -------------------------------------------------------
    if filesize < 500 and '<html' not in content.lower():
        return "Arquivo muito pequeno / nao-HTML"

    # -------------------------------------------------------
    # 3. Mensagens de erro do phpBB
    # -------------------------------------------------------
    # Paginas de erro phpBB tem a estrutura:
    #   <th>Informação</th> ... <td class="row1">MENSAGEM DE ERRO</td>
    # e NAO tem class="postbody" nem class="name" (que indicam posts reais)

    has_real_content = bool(
        re.search(r'class="postbody"', content, re.IGNORECASE) or
        re.search(r'class="name"', content, re.IGNORECASE) or
        re.search(r'Enviada:\s', content, re.IGNORECASE) or
        re.search(r'Enviado\s+em', content, re.IGNORECASE) or
        # phpBB profile real (tem dados do usuario)
        re.search(r'Registrado:\s', content, re.IGNORECASE) or
        re.search(r'Total\s+de\s+Mensagens', content, re.IGNORECASE) or
        # Forum listing com topicos reais
        re.search(r'class="topictitle"', content, re.IGNORECASE) or
        # ASP content markers
        re.search(r'pop_profile\.asp\?mode=display', content, re.IGNORECASE)
    )

    if not has_real_content:
        for pattern in PHPBB_ERROR_MESSAGES:
            if re.search(pattern, content, re.IGNORECASE):
                match = re.search(pattern, content, re.IGNORECASE)
                return f"Erro phpBB: {match.group(0)[:60]}"

        for pattern in PHPBB_JUNK_PAGE_PATTERNS:
            if re.search(pattern, content, re.IGNORECASE):
                match = re.search(pattern, content, re.IGNORECASE)
                return f"Pagina funcional: {match.group(0)[:60]}"

    # -------------------------------------------------------
    # 4. Paginas "viewonline" (quem esta online)
    # -------------------------------------------------------
    if 'viewonline' in filename:
        return "Pagina 'quem esta online'"

    # -------------------------------------------------------
    # 5. Paginas privmsg (mensagens privadas - sempre sem conteudo no WM)
    # -------------------------------------------------------
    if 'privmsg' in filename:
        if not has_real_content:
            return "Mensagem privada (sem conteudo)"

    # -------------------------------------------------------
    # Conteudo util - manter
    # -------------------------------------------------------
    return None


def scan_directory(pasta):
    """Escaneia a pasta e classifica todos os arquivos."""
    results = {
        'junk': [],      # (filepath, motivo)
        'keep': [],      # filepath
        'errors': [],    # (filepath, erro)
    }

    if not os.path.isdir(pasta):
        print(f"\n  ERRO: Pasta nao encontrada: {pasta}")
        return results

    for dirpath, dirnames, filenames in os.walk(pasta):
        # Ignorar pasta _lixo e ocultas
        dirnames[:] = [d for d in dirnames if d != '_lixo' and not d.startswith('.')]

        for filename in sorted(filenames):
            filepath = os.path.join(dirpath, filename)
            if not os.path.isfile(filepath):
                continue

            try:
                content, filesize = read_file_safe(filepath)
                motivo = classify_junk(filepath, content, filesize)

                if motivo:
                    results['junk'].append((filepath, motivo))
                else:
                    results['keep'].append(filepath)

            except Exception as e:
                results['errors'].append((filepath, str(e)))

    return results


def run_cleaner(pasta):
    """Executa o limpador completo."""

    print(f"\n{'='*70}")
    print(f"  SobreSites Junk Cleaner")
    print(f"{'='*70}")
    print(f"  Pasta: {pasta}")
    print(f"  Escaneando arquivos...\n")

    results = scan_directory(pasta)

    if not results['junk'] and not results['errors']:
        print(f"  Nenhum lixo encontrado!")
        print(f"  {len(results['keep'])} arquivos com conteudo util.")
        return

    # Mostrar resultados
    if results['junk']:
        print(f"  LIXO ENCONTRADO: {len(results['junk'])} arquivos")
        print(f"  {'-'*66}")

        # Agrupar por motivo
        by_reason = {}
        for filepath, motivo in results['junk']:
            by_reason.setdefault(motivo, []).append(filepath)

        for motivo, files in sorted(by_reason.items()):
            print(f"\n  [{motivo}] ({len(files)} arquivo{'s' if len(files) > 1 else ''})")
            for f in files[:10]:  # Mostrar ate 10 por categoria
                print(f"    - {os.path.basename(f)}")
            if len(files) > 10:
                print(f"    ... e mais {len(files) - 10} arquivos")

    if results['errors']:
        print(f"\n  ERROS ao ler: {len(results['errors'])} arquivos")
        for filepath, erro in results['errors'][:5]:
            print(f"    - {os.path.basename(filepath)}: {erro}")

    # Pasta de destino do lixo
    junk_folder = os.path.join(pasta, '_lixo')

    print(f"\n  {'-'*66}")
    print(f"  RESUMO:")
    print(f"    Lixo para mover:     {len(results['junk']):5d} arquivos")
    print(f"    Conteudo util:       {len(results['keep']):5d} arquivos")
    if results['errors']:
        print(f"    Erros:               {len(results['errors']):5d} arquivos")
    print(f"\n  Destino do lixo: {junk_folder}")
    print(f"{'='*70}")

    if not results['junk']:
        return

    # Pedir confirmacao
    resposta = input("\n  Mover os arquivos de lixo para _lixo? (s/n): ").strip().lower()

    if resposta not in ('s', 'sim', 'y', 'yes'):
        print("  Operacao cancelada. Nenhum arquivo foi movido.")
        return

    # Criar pasta _lixo
    os.makedirs(junk_folder, exist_ok=True)

    # Mover
    import shutil
    moved = 0
    failed = 0
    for filepath, motivo in results['junk']:
        try:
            dest = os.path.join(junk_folder, os.path.basename(filepath))
            # Se ja existe no destino, adicionar sufixo
            if os.path.exists(dest):
                base, ext = os.path.splitext(dest)
                counter = 2
                while os.path.exists(f"{base}_{counter}{ext}"):
                    counter += 1
                dest = f"{base}_{counter}{ext}"
            shutil.move(filepath, dest)
            moved += 1
        except OSError as e:
            print(f"  ERRO ao mover {os.path.basename(filepath)}: {e}")
            failed += 1

    print(f"\n  {moved} arquivos movidos para: {junk_folder}")
    if failed:
        print(f"  {failed} arquivos nao puderam ser movidos.")
    print(f"\n  Faca o double-check na pasta _lixo.")
    print(f"  Se estiver tudo certo, pode deletar a pasta manualmente.")


def get_pasta():
    """Obtem o caminho da pasta."""
    if len(sys.argv) > 1:
        pasta = ' '.join(sys.argv[1:])
        return pasta.strip().strip('"').strip("'")

    print()
    print("=" * 70)
    print("  SobreSites Junk Cleaner")
    print("  Remove paginas sem conteudo (erros, paginas vazias, etc.)")
    print("=" * 70)
    print()
    print("  Cole o caminho da pasta com os arquivos HTML do forum.")
    print(r"  Exemplo: C:\Users\shoit\websites\www.sobresites.com.br\anime\forum")
    print()

    return input("  Pasta: ").strip().strip('"').strip("'")


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == '__main__':
    pasta = get_pasta()

    if not pasta:
        print("  Nenhuma pasta informada.")
    else:
        run_cleaner(pasta)

    print()
    input("  Pressione ENTER para sair...")