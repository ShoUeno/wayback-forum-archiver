#!/usr/bin/env python3
"""
SobreSites Duplicate Name Fixer
=================================
Compara duas pastas de fontes diferentes (ex: sobresites.com e sobresites.com.br)
e renomeia arquivos com nomes iguais na segunda pasta adicionando um sufixo.

Exemplo:
  Pasta 1 (sobresites.com):    phpbb_topic_100.html
  Pasta 2 (sobresites.com.br): phpbb_topic_100.html  ->  phpbb_topic_100_combr.html

Uso:
  python dedup_names.py                    (interativo)
  python dedup_names.py "pasta1" "pasta2"  (por argumento)
"""

import os
import sys


def collect_filenames(pasta):
    """Coleta todos os nomes de arquivo recursivamente, indexados por nome."""
    names = {}  # filename_lower -> [(dirpath, filename)]
    
    for dirpath, dirnames, filenames in os.walk(pasta):
        dirnames[:] = [d for d in dirnames if d != '_lixo' and not d.startswith('.')]
        for f in filenames:
            key = f.lower()
            if key not in names:
                names[key] = []
            names[key].append((dirpath, f))
    
    return names


def add_suffix(filename, suffix):
    """Adiciona sufixo antes da extensao."""
    base, ext = os.path.splitext(filename)
    return f"{base}_{suffix}{ext}"


def find_duplicates(pasta1, pasta2):
    """Encontra arquivos com nomes iguais entre as duas pastas."""
    names1 = collect_filenames(pasta1)
    names2 = collect_filenames(pasta2)
    
    duplicates = []  # (dirpath, filename, new_filename)
    
    for key, entries2 in names2.items():
        if key in names1:
            for dirpath, filename in entries2:
                duplicates.append((dirpath, filename))
    
    return duplicates


def run(pasta1, pasta2, suffix):
    """Executa a comparacao e renomeacao."""
    
    if not os.path.isdir(pasta1):
        print(f"\n  ERRO: Pasta nao encontrada: {pasta1}")
        return
    if not os.path.isdir(pasta2):
        print(f"\n  ERRO: Pasta nao encontrada: {pasta2}")
        return
    
    print(f"\n{'='*70}")
    print(f"  SobreSites Duplicate Name Fixer")
    print(f"{'='*70}")
    print(f"  Pasta referencia: {pasta1}")
    print(f"  Pasta a renomear: {pasta2}")
    print(f"  Sufixo:           _{suffix}")
    print(f"  Escaneando...\n")
    
    duplicates = find_duplicates(pasta1, pasta2)
    
    if not duplicates:
        names1 = collect_filenames(pasta1)
        names2 = collect_filenames(pasta2)
        print(f"  Nenhum nome duplicado encontrado!")
        print(f"  Pasta 1: {sum(len(v) for v in names1.values())} arquivos")
        print(f"  Pasta 2: {sum(len(v) for v in names2.values())} arquivos")
        return
    
    # Gerar novos nomes
    renames = []  # (dirpath, old_name, new_name)
    for dirpath, filename in duplicates:
        new_name = add_suffix(filename, suffix)
        # Verificar se o novo nome tambem colide
        while os.path.exists(os.path.join(dirpath, new_name)):
            new_name = add_suffix(new_name, '2')
        renames.append((dirpath, filename, new_name))
    
    # Preview
    print(f"  DUPLICATAS ENCONTRADAS: {len(renames)} arquivos\n")
    
    for dirpath, old_name, new_name in renames[:30]:
        rel = os.path.relpath(dirpath, pasta2)
        if rel == '.':
            print(f"  {old_name:45s} -> {new_name}")
        else:
            print(f"  {os.path.join(rel, old_name):45s} -> {new_name}")
    
    if len(renames) > 30:
        print(f"  ... e mais {len(renames) - 30} arquivos")
    
    # Confirmar
    print(f"\n{'='*70}")
    resposta = input(f"  Renomear {len(renames)} arquivos na pasta 2? (s/n): ").strip().lower()
    
    if resposta not in ('s', 'sim', 'y', 'yes'):
        print("  Operacao cancelada.")
        return
    
    # Executar
    renamed = 0
    for dirpath, old_name, new_name in renames:
        src = os.path.join(dirpath, old_name)
        dst = os.path.join(dirpath, new_name)
        try:
            os.rename(src, dst)
            renamed += 1
        except OSError as e:
            print(f"  ERRO: {old_name} -> {e}")
    
    print(f"\n  {renamed} arquivos renomeados com sufixo _{suffix}")


def get_params():
    """Obtem parametros por argumento ou interativamente."""
    if len(sys.argv) >= 3:
        pasta1 = sys.argv[1].strip().strip('"').strip("'")
        pasta2 = sys.argv[2].strip().strip('"').strip("'")
        suffix = sys.argv[3].strip().strip('"').strip("'") if len(sys.argv) > 3 else 'combr'
        return pasta1, pasta2, suffix
    
    print()
    print("=" * 70)
    print("  SobreSites Duplicate Name Fixer")
    print("  Adiciona sufixo a arquivos com nomes iguais entre duas pastas")
    print("=" * 70)
    print()
    print("  Pasta 1 = referencia (nao sera alterada)")
    print("  Pasta 2 = onde os arquivos serao renomeados")
    print()
    
    pasta1 = input("  Pasta 1 (referencia, ex: sobresites.com):    ").strip().strip('"').strip("'")
    pasta2 = input("  Pasta 2 (a renomear, ex: sobresites.com.br): ").strip().strip('"').strip("'")
    
    print()
    print("  Sufixo para adicionar aos duplicatas da Pasta 2.")
    print("  Padrao: combr (arquivo.html -> arquivo_combr.html)")
    print()
    suffix = input("  Sufixo [combr]: ").strip().strip('"').strip("'")
    if not suffix:
        suffix = 'combr'
    
    return pasta1, pasta2, suffix


if __name__ == '__main__':
    pasta1, pasta2, suffix = get_params()
    
    if not pasta1 or not pasta2:
        print("  Pastas nao informadas.")
    else:
        run(pasta1, pasta2, suffix)
    
    print()
    input("  Pressione ENTER para sair...")