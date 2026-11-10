"""Gera um pacote local do LizardConverter para Windows x64."""

import argparse
import hashlib
import importlib.metadata as metadata
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


RAIZ = Path(__file__).resolve().parent.parent
PRODUTO = "LizardConverter"
EXECUTAVEL = "Lizard"
ICONE = RAIZ / "resources" / "lizard.ico"
PASTA_FFMPEG = "tools/ffmpeg"
BINARIOS_FFMPEG = (
    "ffmpeg.exe", "ffprobe.exe", "avcodec-63.dll", "avdevice-63.dll",
    "avfilter-12.dll", "avformat-63.dll", "avutil-61.dll", "swresample-7.dll",
    "swscale-10.dll",
)
RECURSOS = (
    "data/formatos/audio.json",
    "data/formatos/video.json",
    "resources/logo_default.png",
    "resources/name_default.png",
    "resources/logo_dark.png",
    "resources/name_dark.png",
    "resources/sun.svg",
    "resources/moon.svg",
    "resources/LICENSE-Lucide.txt",
) + tuple(
    f"{PASTA_FFMPEG}/{nome}" for nome in (*BINARIOS_FFMPEG, "LICENSE", "COPYING.LGPLv3", "ORIGEM.md")
)
DEPENDENCIAS = ("PyInstaller", "PyQt6", "PyQt6-Qt6", "PyQt6-sip")


def _sha256(arquivo):
    with arquivo.open("rb") as conteudo:
        return hashlib.file_digest(conteudo, "sha256").hexdigest()


def _ambiente(staging):
    ambiente = {
        chave: valor for chave, valor in os.environ.items()
        if not chave.upper().startswith(("PYTHON", "QT_", "QML", "PYINSTALLER", "_PYI_"))
    }
    raiz_windows = os.environ.get("SystemRoot")
    if not raiz_windows:
        raise RuntimeError("O ambiente de compilação precisa definir SystemRoot.")
    windows = Path(raiz_windows)
    ambiente["PATH"] = os.pathsep.join(map(str, (windows / "System32", windows)))
    ambiente["PYTHONNOUSERSITE"] = "1"
    ambiente["PYINSTALLER_CONFIG_DIR"] = str(staging / "cache")
    return ambiente


def _validar_pacote(pacote, ambiente, cwd):
    versoes = {}
    for ferramenta in ("ffmpeg", "ffprobe"):
        comando = [str(pacote / PASTA_FFMPEG / f"{ferramenta}.exe"), "-version"]
        resultado = subprocess.run(
            comando, cwd=cwd, env=ambiente, timeout=15, check=True,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        versoes[ferramenta] = resultado.stdout.splitlines()[0]

    ambiente_teste = {**ambiente, "QT_QPA_PLATFORM": "offscreen"}
    with subprocess.Popen(
        [str(pacote / f"{EXECUTAVEL}.exe")], cwd=cwd, env=ambiente_teste,
        creationflags=subprocess.CREATE_NO_WINDOW,
    ) as processo:
        try:
            codigo = processo.wait(timeout=3)
        except subprocess.TimeoutExpired:
            processo.terminate()
            processo.wait(timeout=10)
        else:
            raise RuntimeError(f"{EXECUTAVEL}.exe encerrou durante a inicialização (código {codigo}).")
    return versoes


def compilar(versao, canal):
    if sys.platform != "win32" or platform.machine().upper() != "AMD64" or sys.maxsize <= 2**32:
        raise RuntimeError("Use Python x64 no Windows para empacotar os binários deste projeto.")
    dependencias = {nome: metadata.distribution(nome) for nome in DEPENDENCIAS}
    if not ICONE.is_file():
        raise FileNotFoundError(f"Ícone obrigatório ausente: {ICONE}")
    for recurso in RECURSOS:
        if not (RAIZ / recurso).is_file():
            raise FileNotFoundError(f"Recurso obrigatório ausente: {recurso}")

    origem = (RAIZ / PASTA_FFMPEG / "ORIGEM.md").read_text(encoding="utf-8")
    hashes = {recurso: _sha256(RAIZ / recurso) for recurso in RECURSOS}
    for ferramenta in BINARIOS_FFMPEG:
        esperado = re.search(rf"SHA-256 de {re.escape(ferramenta)}: `([0-9a-f]{{64}})`", origem)
        if esperado is None or hashes[f"{PASTA_FFMPEG}/{ferramenta}"] != esperado[1]:
            raise ValueError(f"SHA-256 de {ferramenta} diverge do registro em {PASTA_FFMPEG}/ORIGEM.md.")

    # Preserve o rótulo no manifesto e adapte apenas o nome da pasta ao Windows.
    rotulo = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", versao)[:80].strip().rstrip(". ")
    destino = (RAIZ / "dist" / canal / f"build-{rotulo or 'local'}-win64").resolve()
    if not destino.is_relative_to(RAIZ):
        raise ValueError("A pasta de entrega precisa estar dentro do projeto.")
    destino.mkdir(parents=True, exist_ok=True)
    final = destino / PRODUTO
    if final.exists():
        raise FileExistsError(f"Já existe um pacote em {final}.")
    with tempfile.TemporaryDirectory(prefix=".build-", dir=destino) as pasta:
        staging = Path(pasta)
        ambiente = _ambiente(staging)
        comando = [
            sys.executable, "-m", "PyInstaller", "--onedir", "--windowed", "--noupx",
            "--name", EXECUTAVEL, "--icon", str(ICONE), "--contents-directory", "lib",
            "--distpath", str(staging / "dist"), "--workpath", str(staging / "work"),
            "--specpath", str(staging),
        ]
        subprocess.run(comando + [str(RAIZ / "main.py")], cwd=RAIZ, env=ambiente, check=True)
        pacote = staging / "dist" / EXECUTAVEL
        for recurso, esperado in hashes.items():
            copia = pacote / recurso
            copia.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(RAIZ / recurso, copia)
            if _sha256(copia) != esperado:
                raise ValueError(f"Recurso empacotado diverge do original: {recurso}")

        for nome, dist in dependencias.items():
            for arquivo in dist.files or ():
                if arquivo.name.upper().startswith(("LICENSE", "COPYING", "NOTICE")):
                    pasta_licenca = pacote / "license" / nome
                    pasta_licenca.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(dist.locate_file(arquivo), pasta_licenca / arquivo.name)
        if (RAIZ / "LICENSE").stat().st_size:
            shutil.copyfile(RAIZ / "LICENSE", pacote / "license" / f"{PRODUTO}.txt")

        # A execução pode manter arquivos da cópia de teste abertos no Windows.
        copia_teste = shutil.copytree(pacote, staging / "smoke")
        versoes = _validar_pacote(copia_teste, ambiente, staging)
        registro = {
            "versao": versao,
            "canal": canal,
            "plataforma": "windows-x64",
            "python": platform.python_version(),
            "dependencias": {nome: dist.version for nome, dist in dependencias.items()},
            "ferramentas": versoes,
            "sha256_recursos": hashes,
        }
        (pacote / "build.json").write_text(
            json.dumps(registro, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
        )
        # No Windows, rename falha se outra compilação já publicou este destino.
        if not pacote.resolve().is_relative_to(destino) or final.parent != destino:
            raise ValueError("Os caminhos de publicação precisam estar na pasta de entrega.")
        pacote.rename(final)
    return final


def main(canal="producao"):
    parser = argparse.ArgumentParser(description=f"Empacota o {PRODUTO} localmente ({canal}).")
    parser.add_argument("--versao", default="local", help="Rótulo livre do pacote (padrão: local).")
    versao = parser.parse_args().versao

    try:
        pacote = compilar(versao, canal)
    except metadata.PackageNotFoundError as erro:
        print(f"Dependência ausente: {erro.name}. Instale PyQt6 e PyInstaller no ambiente de build.",
              file=sys.stderr)
        return 1
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as erro:
        print(f"Falha na compilação: {erro}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Compilação cancelada.", file=sys.stderr)
        return 130
    print(f"Pacote local gerado em {pacote}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
