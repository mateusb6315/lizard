# Configura o log local e mantém a preferência de tema da aplicação.

import json
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path
from tempfile import NamedTemporaryFile


LOG = logging.getLogger("lizard")
PASTA_APLICACAO = "LizardConverter"


def config_logger(base_local):
    if not base_local or LOG.handlers:
        return
    caminho = Path(base_local) / PASTA_APLICACAO / "lizard.log"
    try:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        arquivo = RotatingFileHandler(caminho, maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    except OSError:
        LOG.exception("Não foi possível iniciar o log em %s", caminho)
        return
    arquivo.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    LOG.addHandler(arquivo)
    LOG.setLevel(logging.INFO)
    LOG.propagate = False


def config_preferencias(raiz, base_local):
    portatil = raiz / "data" / "preferences.json"
    pastas_programas = (os.environ.get(nome) for nome in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432"))
    pasta_compartilhada = any(pasta and raiz.is_relative_to(Path(pasta)) for pasta in pastas_programas)
    instalado = any(arquivo.with_suffix(".dat").is_file() for arquivo in raiz.glob("unins*.exe"))
    if pasta_compartilhada or instalado:
        destino = Path(base_local) / PASTA_APLICACAO / "preferences.json" if base_local else None
        return destino, portatil
    return portatil, None


def ler_tema(destino, anterior):
    caminho = anterior if destino is None or (anterior is not None and not destino.exists()) else destino
    if caminho is not None:
        try:
            dados = json.loads(caminho.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            pass
        else:
            if isinstance(dados, dict) and dados.get("theme") == "dark":
                return "dark"
    return "default"


def gravar_tema(destino, tema):
    temporario = None
    try:
        destino.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=destino.parent, prefix=".preferences-", delete=False,
        ) as arquivo:
            temporario = Path(arquivo.name)
            json.dump({"theme": tema}, arquivo)
            arquivo.write("\n")
        temporario.replace(destino)
        return True
    except OSError:
        LOG.exception("Falha ao gravar o tema em %s", destino)
        if temporario is not None:
            try:
                temporario.unlink(missing_ok=True)
            except OSError:
                LOG.exception("Falha ao remover a preferência temporária em %s", temporario)
        return False
