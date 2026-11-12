import logging
import sys
from pathlib import Path

from PyQt6.QtCore import QStandardPaths, Qt
from PyQt6.QtWidgets import QApplication, QMessageBox

from interface import textos
from interface.componentes import JanelaPrincipal
from interface.controlador import Controlador
from services.logger import config_logger, config_preferencias, gravar_tema, ler_tema
from services.metadados import carregar_formatos


def criar_janela(*, catalogos=None, base_local=None):
    compilado = getattr(sys, "frozen", False)
    raiz = Path(sys.executable if compilado else __file__).resolve().parent
    if catalogos is None:
        catalogos = carregar_formatos()
    janela = JanelaPrincipal(raiz / "resources")
    janela.controlador = Controlador(janela, raiz / "tools", catalogos=catalogos)
    if compilado:
        preferencias, anteriores = config_preferencias(raiz, base_local)
        grupo = janela.alternador_tema.grupo
        if ler_tema(preferencias, anteriores) == "dark":
            grupo.button(1).setChecked(True)
        if preferencias is not None:
            def salvar_tema():
                tema = "dark" if grupo.checkedId() == 1 else "default"
                if not gravar_tema(preferencias, tema):
                    janela.exibir_mensagem(textos.PREFERENCIAS_ERRO, QMessageBox.Icon.Warning)

            janela.fechamento_confirmado.connect(salvar_tema)
    return janela


def main():
    app = QApplication(sys.argv)
    base_local = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.GenericDataLocation)
    config_logger(base_local)
    try:
        catalogos = carregar_formatos()
    except (OSError, ValueError):
        logging.getLogger("lizard").exception("Falha ao carregar os catálogos")
        caixa = QMessageBox(QMessageBox.Icon.Critical, textos.TITULO, textos.CATALOGOS_ERRO)
        caixa.setTextFormat(Qt.TextFormat.PlainText)
        caixa.exec()
        return 1
    janela = criar_janela(catalogos=catalogos, base_local=base_local)
    janela.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
