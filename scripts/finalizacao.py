"""Coordena os artefatos opcionais após a publicação do pacote."""
import subprocess
import sys
from compressao import comprimir, esperar
from instalador import verificar, criar


def finalizar(pacote):
    falhou = False
    try:
        print("[script] Fazendo compressão com 7zip...", flush=True)
        try:
            arquivo = comprimir(pacote)
            print("[script] Compressão concluída")
            print(f"[script] Arquivo: {arquivo.name}")
        except (OSError, RuntimeError, subprocess.SubprocessError) as erro:
            print(f"[script] Houve um erro ao comprimir o arquivo. Causa: {erro}")
            falhou = True
        print("[script] Verificando pré-requisitos para gerar o instalador...", flush=True)
        try:
            requisitos = verificar(pacote)
        except (FileNotFoundError, FileExistsError, ValueError, KeyError) as erro:
            print("[script] Os pré-requisitos não foram atendidos. Verifique e tente novamente.")
            print(f"[script] Causa: {erro}")
            falhou = True
        except (OSError, RuntimeError) as erro:
            print("[script] Houve um erro ao verificar os pré-requisitos. Tente novamente.")
            print(f"[script] Causa: {erro}")
            falhou = True
        else:
            print("[script] Iniciando o processo...", flush=True)
            try:
                arquivo = criar(pacote, requisitos)
            except (OSError, RuntimeError, subprocess.SubprocessError) as erro:
                print(f"[script] Causa: {erro}")
                if sys.stdin.isatty():
                    esperar("[script] Houve um erro ao compilar o instalador. Tente novamente. Pressione qualquer tecla para sair...")
                else:
                    print("[script] Houve um erro ao compilar o instalador. Tente novamente.")
                return 1
            print("[script] Compilação concluída.")
            print(f"[script] Instalador criado em: {arquivo}")
    except KeyboardInterrupt:
        print("[script] Operação interrompida.")
        return 130
    if sys.stdin.isatty():
        esperar("[script] Pressione qualquer tecla para sair...")
    return int(falhou)
