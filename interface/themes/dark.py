"""Paleta e ajustes visuais do tema escuro."""

from PyQt6.QtGui import QColor, QPalette


LOGO = "logo_dark.png"
NOME = "name_dark.png"

ESTILO = """
QComboBox, QPushButton { border-color: #625272; }
QComboBox { background: #2d2635; }
QComboBox QAbstractItemView {
    background: #2d2635; color: #eee7f3; selection-background-color: #594474;
    selection-color: #f8efff;
}
QPushButton#entrada { background: #382d45; color: #eadcf5; }
QPushButton#entrada:hover { background: #483757; }
QPushButton#principal { background: #365ba0; color: #f5f2fb; }
QPushButton:disabled, QPushButton#principal:disabled {
    background: #322c39; color: #a298ae;
}
QProgressBar { border-color: #625272; }
QProgressBar::chunk { background: #9b79c4; }
QWidget#alternadorTema { background: #302639; }
QFrame#realceTema { background: #594474; }
QToolButton#botaoTema:hover { background: rgba(188, 150, 230, 32); }
QToolButton#botaoTema:focus { border-color: #b795da; }
"""


def aplicar_tema(app):
    paleta = app.style().standardPalette()
    for papel, cor in (
        (QPalette.ColorRole.Window, "#0b0a0e"),
        (QPalette.ColorRole.WindowText, "#eee7f3"),
        (QPalette.ColorRole.Base, "#110f13"),
        (QPalette.ColorRole.AlternateBase, "#332b3d"),
        (QPalette.ColorRole.Text, "#eee7f3"),
        (QPalette.ColorRole.Button, "#2e2438"),
        (QPalette.ColorRole.ButtonText, "#eadcf5"),
        (QPalette.ColorRole.Highlight, "#594474"),
        (QPalette.ColorRole.HighlightedText, "#f8efff"),
        (QPalette.ColorRole.ToolTipBase, "#382d45"),
        (QPalette.ColorRole.ToolTipText, "#eee7f3"),
        (QPalette.ColorRole.Link, "#c9a8ed"),
    ):
        paleta.setColor(papel, QColor(cor))
    for papel in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText):
        paleta.setColor(QPalette.ColorGroup.Disabled, papel, QColor("#a298ae"))
    app.setPalette(paleta)
