# componentes da interface de usuário

from pathlib import Path

from PyQt6.QtCore import (
    QByteArray, QEasingCurve, QElapsedTimer, QPoint, QPropertyAnimation, QRectF,
    QSize, Qt, QTimer, pyqtSignal,
)
from PyQt6.QtGui import QColor, QIcon, QKeySequence, QPainter, QPalette, QPixmap
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFrame, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QProgressBar,
    QPushButton, QRadioButton, QScrollArea, QStyledItemDelegate, QToolButton, QVBoxLayout, QWidget,
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
    if app.style().objectName().lower() != "fusion":
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


def _icone_svg(dados, cor):
    svg = QSvgRenderer(QByteArray(dados.replace(b"currentColor", cor.name().encode("ascii"))))
    pixmap = QPixmap(36, 36)
    pixmap.setDevicePixelRatio(2)
    pixmap.fill(Qt.GlobalColor.transparent)
    pintor = QPainter(pixmap)
    svg.render(pintor, QRectF(0, 0, 18, 18))
    pintor.end()
    return QIcon(pixmap)


class OpcaoCompacta(QStyledItemDelegate):
    def sizeHint(self, opcao, indice):
        tamanho = super().sizeHint(opcao, indice)
        tamanho.setHeight(max(opcao.fontMetrics.height(), opcao.decorationSize.height()) + 3)
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
            botao.setIcon(_icone_svg(dados, cor))

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


class DialogoFaixas(QDialog):
    def __init__(self, pai, categoria, formato, faixas, omitidas, faixa_unica):
        super().__init__(pai)
        self.setWindowTitle(textos.FAIXAS)
        self.setMinimumWidth(460)
        self.categoria = categoria
        layout = QVBoxLayout(self)
        mensagens = [textos.SELECIONAR_FAIXAS.format(formato=formato.upper())]
        if faixa_unica:
            mensagens.append(textos.FAIXA_UNICA)
        if omitidas:
            tipos = dict.fromkeys(textos.TIPOS_OMITIDOS.get(tipo, textos.OUTRAS_FAIXAS) for tipo in omitidas)
            mensagens.append(textos.FAIXAS_OMITIDAS.format(tipos=", ".join(tipos)))
        aviso = QLabel("\n\n".join(mensagens))
        aviso.setWordWrap(True)
        layout.addWidget(aviso)

        conteudo = QWidget()
        lista = QVBoxLayout(conteudo)
        rolagem = QScrollArea()
        rolagem.setWidgetResizable(True)
        rolagem.setWidget(conteudo)
        layout.addWidget(rolagem)
        self.faixas = []
        for posicao, faixa in enumerate(faixas):
            indice = faixa["index"]
            tipo = faixa["codec_type"]
            tags = faixa.get("tags", {})
            detalhes = [textos.CATEGORIAS[tipo], faixa.get("codec_name", "")]
            detalhes.extend(tags[chave] for chave in ("language", "title") if tags.get(chave))
            rotulo = f"{indice} · " + " · ".join(filter(None, detalhes))
            botao = QRadioButton(rotulo) if faixa_unica else QCheckBox(rotulo)
            botao.setChecked(not faixa_unica or posicao == 0)
            self.faixas.append((indice, tipo, botao))
            lista.addWidget(botao)
        lista.addStretch()

        botoes = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
        )
        self.continuar = botoes.button(QDialogButtonBox.StandardButton.Ok)
        self.continuar.setText(textos.CONTINUAR)
        botoes.button(QDialogButtonBox.StandardButton.Cancel).setText(textos.CANCELAR)
        botoes.accepted.connect(self.accept)
        botoes.rejected.connect(self.reject)
        layout.addWidget(botoes)
        for _, _, botao in self.faixas:
            botao.toggled.connect(self._atualizar_continuar)
        self._atualizar_continuar()

    def _atualizar_continuar(self):
        self.continuar.setEnabled(any(
            tipo == self.categoria and botao.isChecked() for _, tipo, botao in self.faixas
        ))

    def indices(self):
        return tuple(indice for indice, _, botao in self.faixas if botao.isChecked())


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
        self.categoria = QComboBox()
        self.categoria.setItemDelegate(OpcaoCompacta(self.categoria))
        self.categoria.setIconSize(QSize(18, 18))
        self.icones_categoria = [
            (recursos / arquivo).read_bytes() for arquivo in ("video.svg", "music.svg")
        ]
        for tipo, rotulo in textos.CATEGORIAS.items():
            self.categoria.addItem(rotulo, tipo)
        rotulo = QLabel(textos.CATEGORIA)
        rotulo.setBuddy(self.categoria)
        formulario.addWidget(rotulo)
        formulario.addWidget(self.categoria)
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
        self.ajuda = QLabel(textos.AJUDA)
        self.ajuda.setWordWrap(True)
        formulario.addWidget(self.ajuda)
        formulario.addStretch()
        layout.addStretch()
        self.definir_tema(False)

    def definir_tema(self, escuro):
        app = QApplication.instance()
        if escuro:
            dark.aplicar_tema(app)
            tema = dark
        else:
            aplicar_tema(app)
            tema = default
        self.setStyleSheet(ESTILO + dark.ESTILO if escuro else ESTILO)
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
        for indice, dados in enumerate(self.icones_categoria):
            self.categoria.setItemIcon(indice, _icone_svg(dados, cor))

    def mostrar_entrada(self, arquivo):
        self.entrada.setText(Path(arquivo).name)
        self.entrada.setToolTip(str(arquivo))

    def atualizar_disponibilidade(self, tem_entrada):
        disponivel = self.perfil.count() > 0
        self.perfil.setEnabled(disponivel)
        self.botao_converter.setEnabled(tem_entrada and disponivel)
        self.ajuda.setText(textos.AJUDA if disponivel else textos.CATEGORIA_INDISPONIVEL)

    def definir_ocupada(self, ocupada):
        self.ocupada = ocupada
        self.centralWidget().setEnabled(not ocupada)
        self.menuBar().setEnabled(not ocupada)

    def escolher_entrada(self, filtro):
        return QFileDialog.getOpenFileName(self, textos.ABRIR, "", filtro)[0]

    def escolher_saida(self, sugestao, filtro):
        return QFileDialog.getSaveFileName(
            self, textos.SALVAR, str(sugestao), filtro,
            options=QFileDialog.Option.DontConfirmOverwrite,
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
