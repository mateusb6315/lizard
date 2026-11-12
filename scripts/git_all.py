"""Adiciona os arquivos, cria um commit e envia a branch atual à main remota."""

import subprocess
import sys
from pathlib import Path


RAIZ = Path(__file__).resolve().parent.parent


def executar(*comando):
    resultado = subprocess.run(
        comando, cwd=RAIZ, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if resultado.returncode:
        raise RuntimeError(resultado.stderr.strip() or resultado.stdout.strip() or f"código {resultado.returncode}")
    return resultado.stdout.strip()


def main():
    print("[script] Verificando pré-requisitos...")
    try:
        executar("git", "rev-parse", "--show-toplevel")
        branch = executar("git", "symbolic-ref", "--short", "HEAD")
        executar("git", "remote", "get-url", "origin")
        executar("git", "var", "GIT_AUTHOR_IDENT")
        executar("git", "var", "GIT_COMMITTER_IDENT")
    except (OSError, RuntimeError) as erro:
        print(f"[script] Ocorreu um erro de validação. Causa: {erro}")
        return 1

    try:
        executar("gh", "auth", "status", "--hostname", "github.com")
    except (OSError, RuntimeError):
        print("[script] Erro de login. Faça login no GitHub CLI e tente novamente")
        return 1
    print("[script] Login validado")
    print("[script] Validação concluída")

    mensagem = input("[script] Digite a mensagem do commit: ")
    print(f"[script] Fazendo commit na {branch}...")
    try:
        executar("git", "add", ".")
        executar("git", "commit", "-m", mensagem)
    except (OSError, RuntimeError) as erro:
        print(f"[script] Erro ao fazer o commit. Causa: {erro}")
        return 1

    print("[script] Commit feito, enviando para o GitHub...")
    try:
        executar("git", "push", "origin", "HEAD:main")
    except (OSError, RuntimeError) as erro:
        print(f"[script] Erro ao fazer o git push. Causa: {erro}")
        return 1
    print("[script] git push concluído")
    return 0


if __name__ == "__main__":
    try:
        codigo = main()
    finally:
        print("[script] Pressione qualquer tecla para continuar...", end="", flush=True)
        try:
            if sys.platform == "win32" and sys.stdin.isatty():
                import msvcrt

                msvcrt.getwch()
                print()
            else:
                input()
        except EOFError:
            pass
    sys.exit(codigo)
