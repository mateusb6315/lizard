import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from PyQt6.QtCore import QStandardPaths, Qt
from PyQt6.QtWidgets import QApplication, QMessageBox

from interface import textos
from interface.componentes import JanelaPrincipal
from interface.controlador import Controlador
from services.metadados import carregar_formatos


def configurar_log():
    logger = logging.getLogger("lizard")
    if logger.handlers:
        return
    local = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.GenericDataLocation)
    caminho = Path(local) / textos.TITULO / "lizard.log"
    try:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        arquivo = RotatingFileHandler(caminho, maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    except OSError:
        logger.exception("Não foi possível iniciar o log em %s", caminho)
        return
    arquivo.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(arquivo)
    logger.setLevel(logging.INFO)
    logger.propagate = False


def _preferencias_compilado(raiz):
    portatil = raiz / "data" / "preferences.json"
    pastas_programas = (os.environ.get(nome) for nome in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432"))
    pasta_compartilhada = any(pasta and raiz.is_relative_to(Path(pasta)) for pasta in pastas_programas)
    instalado = any(arquivo.with_suffix(".dat").is_file() for arquivo in raiz.glob("unins*.exe"))
    if pasta_compartilhada or instalado:
        local = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.GenericDataLocation)
        return Path(local) / textos.TITULO / "preferences.json", portatil
    return portatil, None


def criar_janela(*, catalogos=None):
    compilado = getattr(sys, "frozen", False)
    raiz = Path(sys.executable if compilado else __file__).resolve().parent
    if catalogos is None:
        catalogos = carregar_formatos()
    preferencias, anteriores = _preferencias_compilado(raiz) if compilado else (None, None)
    janela = JanelaPrincipal(raiz / "resources")
    janela.controlador = Controlador(
        janela, raiz / "tools", preferencias, catalogos=catalogos, preferencias_anteriores=anteriores,
    )
    return janela


def main():
    app = QApplication(sys.argv)
    configurar_log()
    try:
        catalogos = carregar_formatos()
    except (OSError, ValueError):
        logging.getLogger("lizard").exception("Falha ao carregar os catálogos")
        caixa = QMessageBox(QMessageBox.Icon.Critical, textos.TITULO, textos.CATALOGOS_ERRO)
        caixa.setTextFormat(Qt.TextFormat.PlainText)
        caixa.exec()
        return 1
    janela = criar_janela(catalogos=catalogos)
    janela.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
