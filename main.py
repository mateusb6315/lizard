import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication

from interface.componentes import JanelaPrincipal
from interface.controlador import Controlador


def criar_janela():
    raiz = Path(sys.executable if getattr(sys, "frozen", False) else __file__).resolve().parent
    janela = JanelaPrincipal(raiz / "resources")
    preferencias = raiz / "data" / "preferences.json" if getattr(sys, "frozen", False) else None
    janela.controlador = Controlador(janela, raiz / "tools", preferencias)
    return janela


def main():
    app = QApplication(sys.argv)
    janela = criar_janela()
    janela.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
