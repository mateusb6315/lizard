"""Compressão opcional dos pacotes já publicados pelo compilador."""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def comprimir(pacote):
    executavel = shutil.which("7z")
    if not executavel:
        padrao = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "7-Zip" / "7z.exe"
        if not padrao.is_file():
            raise FileNotFoundError("7-Zip não encontrado no PATH nem em Program Files.")
        executavel = str(padrao)
    arquivo = pacote.parent / (pacote.name + ".7z")
    if arquivo.exists() or arquivo.is_symlink():
        raise FileExistsError(f"Já existe um arquivo em {arquivo}.")
    with tempfile.TemporaryDirectory(prefix=".compressao-", dir=pacote.parent) as pasta:
        temporario = Path(pasta) / arquivo.name
        comando = [
            executavel, "a", "-t7z", "-mx=9", "-m0=LZMA", "-md=256m",
            "-mfb=64", "-mmt=2", "-mmemuse=p80", "-sse", "--",
            str(temporario), pacote.name,
        ]
        resultado = subprocess.run(
            comando, cwd=pacote.parent, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            encoding="utf-8", errors="replace", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if resultado.returncode:
            raise RuntimeError(resultado.stdout.strip() or f"código {resultado.returncode}")
        if not temporario.is_file() or not temporario.stat().st_size:
            raise RuntimeError("O 7-Zip não gerou o arquivo compactado.")
        # No Windows, rename não substitui um arquivo criado por outra execução.
        temporario.rename(arquivo)
    return arquivo


def esperar(mensagem):
    print(mensagem, end="", flush=True)
    try:
        if sys.platform == "win32" and sys.stdin.isatty():
            import msvcrt

            msvcrt.getwch()
            print()
        else:
            input()
    except EOFError:
        pass


def finalizar(pacote):
    print("[script] Fazendo compressão com 7zip...", flush=True)
    try:
        arquivo = comprimir(pacote)
    except (OSError, RuntimeError, subprocess.SubprocessError) as erro:
        print(f"[script] Houve um erro ao comprimir o arquivo. Causa: {erro}")
        esperar("[script] Compressão cancelada. Compilação concluída anteriormente. Pressione qualquer tecla para sair...")
        return 1
    except KeyboardInterrupt:
        print("[script] Houve um erro ao comprimir o arquivo. Causa: operação interrompida")
        esperar("[script] Compressão cancelada. Compilação concluída anteriormente. Pressione qualquer tecla para sair...")
        return 130
    print("[script] Compressão concluída")
    print(f"[script] Arquivo: {arquivo.name}")
    esperar("[script] Pressione qualquer tecla para sair...")
    return 0
