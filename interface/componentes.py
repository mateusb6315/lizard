# componentes da interface de usuário

from pathlib import Path

from PyQt6.QtCore import (
    QByteArray, QEasingCurve, QElapsedTimer, QPoint, QPropertyAnimation, QRectF,
    QSize, Qt, QTimer, pyqtSignal,
)
from PyQt6.QtGui import QColor, QIcon, QKeySequence, QPainter, QPalette, QPixmap
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import (
    QApplication, QButtonGroup, QComboBox, QDialog, QFileDialog, QFrame, QHBoxLayout,
    QLabel, QMainWindow, QMessageBox, QProgressBar, QPushButton, QStyledItemDelegate,
    QToolButton, QVBoxLayout, QWidget,
)

from interface import textos
from interface.themes import dark, default


ESTILO = """
QWidget { font-size: 14px; }
QComboBox, QPushButton { padding: 9px 16px; border: 1px solid #a896c2; border-radius: 5px; }
QPushButton#entrada { background: #eee4ff; color: #402668; }
QPushButton#entrada:hover { background: #e1d0fa; }
QPushButton#principal {
    background: #245dcc; color: white; font-weight: bold; border-radius: 0;
}
QPushButton:disabled, QPushButton#principal:disabled {
    background: #e4e0ec; color: #645c73;
}
QProgressBar { border: 1px solid #a896c2; border-radius: 4px; text-align: center; }
QProgressBar::chunk { background: #9872ca; }
QWidget#alternadorTema { background: #eee4ff; border-radius: 12px; }
QFrame#realceTema { background: #e0ccfa; border-radius: 9px; }
QToolButton#botaoTema { background: transparent; border: 1px solid transparent; border-radius: 9px; }
QToolButton#botaoTema:hover { background: rgba(152, 114, 202, 28); }
QToolButton#botaoTema:focus { border-color: #8764b6; }
"""


def aplicar_tema(app):
    app.setStyle("Fusion")
    paleta = app.style().standardPalette()
    for papel, cor in (
        (QPalette.ColorRole.Window, "#f8f5fc"),
        (QPalette.ColorRole.WindowText, "#282037"),
        (QPalette.ColorRole.Base, "#ffffff"),
        (QPalette.ColorRole.Text, "#282037"),
        (QPalette.ColorRole.Button, "#eee4ff"),
        (QPalette.ColorRole.ButtonText, "#402668"),
        (QPalette.ColorRole.Highlight, "#e0ccfa"),
        (QPalette.ColorRole.HighlightedText, "#402668"),
    ):
        paleta.setColor(papel, QColor(cor))
    app.setPalette(paleta)
    app.setStyleSheet(ESTILO)


class OpcaoCompacta(QStyledItemDelegate):
    def sizeHint(self, opcao, indice):
        tamanho = super().sizeHint(opcao, indice)
        tamanho.setHeight(opcao.fontMetrics.height() + 3)
        return tamanho


class AlternadorTema(QWidget):
    tema_alterado = pyqtSignal(bool)

    def __init__(self, recursos):
        super().__init__()
        self.setObjectName("alternadorTema")
        self.setFixedSize(70, 36)
        self.realce = QFrame(self)
        self.realce.setObjectName("realceTema")
        self.realce.setGeometry(3, 3, 32, 30)
        self.animacao = QPropertyAnimation(self.realce, b"pos", self)
        self.animacao.setDuration(160)
        self.animacao.setEasingCurve(QEasingCurve.Type.OutCubic)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(0)
        self.grupo = QButtonGroup(self)
        self.icones = {}
        for indice, (arquivo, rotulo) in enumerate((
            ("sun.svg", textos.TEMA_CLARO), ("moon.svg", textos.TEMA_ESCURO),
        )):
            botao = QToolButton()
            botao.setObjectName("botaoTema")
            botao.setCheckable(True)
            botao.setFixedSize(32, 30)
            botao.setIconSize(QSize(18, 18))
            botao.setToolTip(rotulo)
            botao.setAccessibleName(rotulo)
            self.grupo.addButton(botao, indice)
            self.icones[botao] = (recursos / arquivo).read_bytes()
            layout.addWidget(botao)
        self.grupo.button(0).setChecked(True)
        self.grupo.idToggled.connect(self._alternar)
        self.realce.lower()

    def atualizar_icones(self, cor):
        for botao, dados in self.icones.items():
            svg = QSvgRenderer(QByteArray(dados.replace(b"currentColor", cor.name().encode("ascii"))))
            pixmap = QPixmap(36, 36)
            pixmap.setDevicePixelRatio(2)
            pixmap.fill(Qt.GlobalColor.transparent)
            pintor = QPainter(pixmap)
            svg.render(pintor, QRectF(0, 0, 18, 18))
            pintor.end()
            botao.setIcon(QIcon(pixmap))

    def _alternar(self, indice, marcado):
        if marcado:
            self.tema_alterado.emit(bool(indice))
            self.animacao.stop()
            self.animacao.setStartValue(self.realce.pos())
            self.animacao.setEndValue(QPoint(3 + indice * 32, 3))
            self.animacao.start()


class AreaEntrada(QPushButton):
    arquivo_solto = pyqtSignal(str)

    def __init__(self):
        super().__init__(textos.ENTRADA)
        self.setObjectName("entrada")
        self.setAcceptDrops(True)
        self.setMinimumSize(330, 140)

    def dragEnterEvent(self, evento):
        urls = evento.mimeData().urls()
        if len(urls) == 1 and urls[0].isLocalFile():
            evento.acceptProposedAction()

    def dropEvent(self, evento):
        urls = evento.mimeData().urls()
        if len(urls) == 1 and urls[0].isLocalFile():
            self.arquivo_solto.emit(urls[0].toLocalFile())
            evento.acceptProposedAction()


class DialogoProgresso(QDialog):
    cancelamento_solicitado = pyqtSignal()

    def __init__(self, pai):
        super().__init__(pai)
        self.setWindowTitle(textos.PROGRESSO)
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.setMinimumWidth(440)
        layout = QVBoxLayout(self)
        self.etapa = QLabel(textos.ETAPAS["inspecao"])
        self.barra = QProgressBar()
        self.barra.setRange(0, 0)
        self.detalhes = QLabel()
        self.cancelar = QPushButton(textos.CANCELAR)
        self.cancelar.clicked.connect(self.reject)
        for widget in (self.etapa, self.barra, self.detalhes, self.cancelar):
            layout.addWidget(widget)
        self.relogio = QElapsedTimer()
        self.relogio.start()
        self.timer = QTimer(self, interval=250)
        self.timer.timeout.connect(self.atualizar_tempo)
        self.atualizar_tempo()
        self.timer.start()

    def atualizar_tempo(self):
        minutos, segundos = divmod(self.relogio.elapsed() // 1000, 60)
        self.detalhes.setText(textos.TEMPO.format(tempo=f"{minutos:02d}:{segundos:02d}"))

    def atualizar_etapa(self, etapa):
        if self.cancelar.isEnabled():
            self.etapa.setText(textos.ETAPAS[etapa])

    def reject(self):
        if self.cancelar.isEnabled():
            self.cancelar.setEnabled(False)
            self.etapa.setText(textos.CANCELANDO)
            self.cancelamento_solicitado.emit()

    def closeEvent(self, evento):
        evento.ignore()
        self.reject()


class JanelaPrincipal(QMainWindow):
    abrir_solicitado = pyqtSignal()
    converter_solicitado = pyqtSignal()
    fechamento_confirmado = pyqtSignal()

    def __init__(self, recursos):
        super().__init__()
        self.recursos = recursos
        self.setWindowTitle(textos.TITULO)
        self.setMinimumSize(700, 350)
        self.ocupada = False
        menu_arquivo = self.menuBar().addMenu(textos.ARQUIVO)
        self.acao_abrir = menu_arquivo.addAction(textos.ABRIR)
        self.acao_abrir.setShortcut(QKeySequence.StandardKey.Open)
        self.acao_abrir.triggered.connect(self.abrir_solicitado.emit)
        menu_arquivo.addSeparator()
        self.acao_sair = menu_arquivo.addAction(textos.SAIR)
        self.acao_sair.setShortcut(QKeySequence.StandardKey.Quit)
        self.acao_sair.triggered.connect(self.close)
        menu_opcoes = self.menuBar().addMenu(textos.OPCOES)
        self.acao_atualizacoes = menu_opcoes.addAction(textos.ATUALIZACOES)
        self.acao_atualizacoes.triggered.connect(
            lambda: self.exibir_mensagem(textos.ATUALIZACOES_PENDENTES)
        )
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(24, 20, 24, 20)
        cabecalho = QHBoxLayout()
        self.logo = QLabel()
        self.nome = QLabel()
        self.nome.setAccessibleName(textos.TITULO)
        cabecalho.addWidget(self.logo, alignment=Qt.AlignmentFlag.AlignVCenter)
        cabecalho.addWidget(self.nome, alignment=Qt.AlignmentFlag.AlignVCenter)
        cabecalho.addStretch()
        self.alternador_tema = AlternadorTema(recursos)
        self.alternador_tema.tema_alterado.connect(self.definir_tema)
        cabecalho.addWidget(self.alternador_tema, alignment=Qt.AlignmentFlag.AlignTop)
        layout.addLayout(cabecalho)
        linha = QHBoxLayout()
        layout.addLayout(linha)
        self.entrada = AreaEntrada()
        self.entrada.clicked.connect(self.abrir_solicitado.emit)
        linha.addWidget(self.entrada, 1)
        formulario = QVBoxLayout()
        linha.addLayout(formulario, 1)
        self.perfil = QComboBox()
        self.perfil.setItemDelegate(OpcaoCompacta(self.perfil))
        rotulo = QLabel(textos.FORMATO)
        rotulo.setBuddy(self.perfil)
        formulario.addWidget(rotulo)
        formulario.addWidget(self.perfil)
        self.botao_converter = QPushButton(textos.CONVERTER)
        self.botao_converter.setObjectName("principal")
        self.botao_converter.setEnabled(False)
        self.botao_converter.clicked.connect(self.converter_solicitado.emit)
        formulario.addWidget(self.botao_converter)
        ajuda = QLabel(textos.AJUDA)
        ajuda.setWordWrap(True)
        formulario.addWidget(ajuda)
        formulario.addStretch()
        layout.addStretch()
        self.definir_tema(False)

    def definir_tema(self, escuro):
        app = QApplication.instance()
        if escuro:
            dark.aplicar_tema(app, ESTILO)
            tema = dark
            self.opcoes_dialogo = dark.OPCOES_DIALOGO
        else:
            aplicar_tema(app)
            tema = default
            self.opcoes_dialogo = QFileDialog.Option(0)
        caminho_logo = str(self.recursos / tema.LOGO)
        self.setWindowIcon(QIcon(caminho_logo))
        self.logo.setPixmap(QPixmap(caminho_logo).scaled(
            96, 64, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation,
        ))
        self.nome.setPixmap(QPixmap(str(self.recursos / tema.NOME)).scaled(
            180, 36, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation,
        ))
        cor = app.palette().color(QPalette.ColorRole.ButtonText)
        self.alternador_tema.atualizar_icones(cor)

    def mostrar_entrada(self, arquivo):
        self.entrada.setText(Path(arquivo).name)
        self.entrada.setToolTip(str(arquivo))
        self.botao_converter.setEnabled(True)

    def definir_ocupada(self, ocupada):
        self.ocupada = ocupada
        self.centralWidget().setEnabled(not ocupada)
        self.menuBar().setEnabled(not ocupada)

    def escolher_entrada(self, filtro):
        return QFileDialog.getOpenFileName(
            self, textos.ABRIR, "", filtro, options=self.opcoes_dialogo,
        )[0]

    def escolher_saida(self, sugestao, filtro):
        return QFileDialog.getSaveFileName(
            self, textos.SALVAR, str(sugestao), filtro,
            options=self.opcoes_dialogo | QFileDialog.Option.DontConfirmOverwrite,
        )[0]

    def exibir_mensagem(self, mensagem, icone=QMessageBox.Icon.Information):
        caixa = QMessageBox(icone, textos.TITULO, mensagem, QMessageBox.StandardButton.Ok, self)
        caixa.setTextFormat(Qt.TextFormat.PlainText)
        caixa.exec()

    def closeEvent(self, evento):
        if self.ocupada:
            evento.ignore()
        else:
            self.fechamento_confirmado.emit()
            super().closeEvent(evento)
