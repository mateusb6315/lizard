"""Geração do instalador a partir de um pacote já publicado."""
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

TEMPLATE = Path(__file__).with_name("setup.iss")


def verificar(pacote):
    iscc = shutil.which("ISCC.exe")
    if not iscc:
        for raiz in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles")):
            if raiz:
                for nome in ("Inno Setup 6", "Inno Setup 7"):
                    candidato = Path(raiz) / nome / "ISCC.exe"
                    if candidato.is_file():
                        iscc = str(candidato)
                        break
            if iscc:
                break
    if not iscc or not TEMPLATE.is_file() or not (pacote / "Lizard.exe").is_file():
        raise FileNotFoundError("ISCC, template ou executável do pacote ausente")
    dados = json.loads((pacote / "build.json").read_text(encoding="utf-8"))
    versao, canal = dados["versao"], dados["canal"]
    if (not isinstance(versao, str) or not versao or canal not in ("beta", "release")
            or pacote.name != "lizard-converter-" + versao or pacote.parent.name != canal):
        raise ValueError("Metadados do pacote inconsistentes")
    # Restringe valores que poderiam alterar a sintaxe do pré-processador ou do ISS.
    if any(c in versao or c in str(pacote.resolve()) for c in ('"', "{", "}", "\n", "\r")):
        raise ValueError("Versão ou caminho incompatível com o Inno Setup")
    nome = pacote.name.replace(" ", "-") + "-setup"
    destino = pacote.parent / (nome + ".exe")
    if len(destino.name.encode("utf-16-le")) > 510:
        raise ValueError("Nome do instalador excede o limite do Windows")
    if destino.exists() or destino.is_symlink():
        raise FileExistsError(f"Instalador já existe: {destino}")
    return iscc, versao, nome, destino


def criar(pacote, requisitos):
    iscc, versao, nome, destino = requisitos
    with tempfile.TemporaryDirectory(prefix=".instalador-", dir=pacote.parent) as pasta:
        comando = [iscc, f"/DBuildVersion={versao}", f"/DPackageDir={pacote.resolve()}",
                   f"/O{pasta}", f"/F{nome}", str(TEMPLATE)]
        resultado = subprocess.run(comando, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
        if resultado.returncode:
            raise RuntimeError(resultado.stdout.strip() or f"ISCC retornou {resultado.returncode}")
        temporario = Path(pasta) / (nome + ".exe")
        if not temporario.is_file() or not temporario.stat().st_size:
            raise RuntimeError("ISCC não gerou um instalador válido")
        if destino.exists() or destino.is_symlink():
            raise FileExistsError(f"Instalador já existe: {destino}")
        temporario.rename(destino)
    return destino
