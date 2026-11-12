# controlador intermediário entre a interface e os serviços. é sua única responsabilidade, seguindo o padrão SRP

import logging
from pathlib import Path
from threading import Event

from PyQt6.QtCore import QObject, QThread, pyqtSignal
from PyQt6.QtWidgets import QMessageBox

from interface import textos
from interface.componentes import DialogoFaixas, DialogoProgresso
from services import conversor
from services.metadados import carregar_formatos


LOG = logging.getLogger("lizard")


class ConversaoEmSegundoPlano(QThread):
    etapa_alterada = pyqtSignal(str)
    faixas_disponiveis = pyqtSignal(object, object, bool)

    def __init__(self, pai, entrada, saida, categoria, formato, ffmpeg, ffprobe, catalogos):
        super().__init__(pai)
        self.argumentos = (entrada, saida, categoria, formato, None, ffmpeg, ffprobe)
        self.catalogos = catalogos
        self.cancelamento = Event()
        self.revisao_concluida = Event()
        self.indices_revisados = None
        self.saida = None
        self.erro = None
        self.avisos = []
        self.inicio_ts_recuperado = False
        self.perda_fim_ts = None

    def run(self):
        try:
            self.saida = conversor.converter(
                *self.argumentos, cancelamento=self.cancelamento,
                informar_etapa=self.etapa_alterada.emit, avisar=self.avisos.append,
                catalogos=self.catalogos, selecionar_faixas=self.revisar_faixas,
                avisar_inicio_ts=self.avisar_inicio_ts,
                avisar_fim_ts=self.avisar_fim_ts,
            )
        except conversor.ConversaoCancelada:
            pass
        except Exception as erro:
            self.erro = erro

    def avisar_inicio_ts(self, diagnostico):
        self.inicio_ts_recuperado = True
        LOG.warning("Início de TS recuperado em %s\n%s", self.argumentos[0], diagnostico)

    def avisar_fim_ts(self, perda):
        self.perda_fim_ts = perda

    def revisar_faixas(self, faixas, omitidas, faixa_unica):
        if len(faixas) == 1 and not omitidas:
            return (faixas[0]["index"],)
        self.faixas_disponiveis.emit(faixas, omitidas, faixa_unica)
        while not self.cancelamento.is_set():
            if self.revisao_concluida.wait(0.1):
                return self.indices_revisados
        return None

    def concluir_revisao(self, indices):
        self.indices_revisados = indices
        self.revisao_concluida.set()


class Controlador(QObject):
    def __init__(self, janela, ferramentas, *, catalogos=None):
        super().__init__(janela)
        self.janela = janela
        self.catalogos = carregar_formatos() if catalogos is None else catalogos
        self.ffmpeg, self.ffprobe = conversor.caminhos_ferramentas(ferramentas)
        self.entrada = None
        self.tarefa = None
        self.progresso = None
        self.dialogo_faixas = None
        self.extensoes = {
            f".{perfil['extension'].lower()}"
            for perfis in self.catalogos.values()
            for perfil in perfis.values()
        }
        self.filtro_entrada = textos.FILTRO_ENTRADA.format(
            extensoes=" ".join(f"*{extensao}" for extensao in sorted(self.extensoes))
        )
        janela.abrir_solicitado.connect(self.abrir)
        janela.entrada.arquivo_solto.connect(self.selecionar_entrada)
        janela.converter_solicitado.connect(self.converter)
        janela.categoria.currentIndexChanged.connect(self.atualizar_perfis)
        self.atualizar_perfis()

    def atualizar_perfis(self):
        categoria = self.janela.categoria.currentData()
        seletor = self.janela.perfil
        seletor.clear()
        for formato, perfil in self.catalogos.get(categoria, {}).items():
            seletor.addItem(formato.upper(), (categoria, formato, perfil["extension"]))
        self.janela.atualizar_disponibilidade(self.entrada is not None)

    def abrir(self):
        arquivo = self.janela.escolher_entrada(self.filtro_entrada)
        if arquivo:
            self.selecionar_entrada(arquivo)

    def selecionar_entrada(self, arquivo):
        if self.tarefa is not None:
            return
        entrada = Path(arquivo)
        if not entrada.is_file() or entrada.suffix.lower() not in self.extensoes:
            LOG.warning("Entrada ausente ou fora do filtro de formatos: %s", entrada)
            self.janela.exibir_mensagem(textos.ENTRADA_INVALIDA, QMessageBox.Icon.Warning)
            return
        self.entrada = entrada
        self.janela.mostrar_entrada(entrada)
        self.janela.atualizar_disponibilidade(True)

    def converter(self):
        if self.entrada is None or self.tarefa is not None:
            return
        if not self.ffmpeg.is_file() or not self.ffprobe.is_file():
            LOG.error("Ferramenta ausente. FFmpeg: %s. FFprobe: %s", self.ffmpeg, self.ffprobe)
            self.janela.exibir_mensagem(textos.FERRAMENTA_AUSENTE, QMessageBox.Icon.Critical)
            return
        perfil = self.janela.perfil.currentData()
        if perfil is None:
            return
        categoria, formato, extensao = perfil
        sugestao = self.entrada.with_name(f"{self.entrada.stem}-convertido.{extensao}")
        filtro = textos.FILTRO_SAIDA.format(formato=formato.upper(), extensao=extensao)
        arquivo = self.janela.escolher_saida(sugestao, filtro)
        if not arquivo:
            return
        saida = Path(arquivo)
        if not saida.suffix:
            saida = saida.with_suffix(f".{extensao}")
        if saida.suffix.lower() != f".{extensao.lower()}" or saida.exists() or saida.is_symlink():
            LOG.warning("Destino já ocupado ou extensão diferente de .%s: %s", extensao, saida)
            self.janela.exibir_mensagem(textos.SAIDA_INVALIDA, QMessageBox.Icon.Warning)
            return
        self.tarefa = ConversaoEmSegundoPlano(
            self, self.entrada, saida, categoria, formato, self.ffmpeg, self.ffprobe, self.catalogos,
        )
        self.progresso = DialogoProgresso(self.janela)
        self.progresso.cancelamento_solicitado.connect(self.tarefa.cancelamento.set)
        self.tarefa.etapa_alterada.connect(self.progresso.atualizar_etapa)
        self.tarefa.faixas_disponiveis.connect(self.solicitar_faixas)
        self.tarefa.finished.connect(self.finalizar)
        self.janela.definir_ocupada(True)
        self.progresso.show()
        self.tarefa.start()

    def solicitar_faixas(self, faixas, omitidas, faixa_unica):
        if self.tarefa is None or self.tarefa.cancelamento.is_set():
            return
        categoria, formato, _ = self.janela.perfil.currentData()
        dialogo = DialogoFaixas(self.progresso, categoria, formato, faixas, omitidas, faixa_unica)
        self.dialogo_faixas = dialogo
        dialogo.finished.connect(self.concluir_revisao)
        dialogo.open()

    def concluir_revisao(self, resultado):
        dialogo = self.dialogo_faixas
        self.dialogo_faixas = None
        if self.tarefa is not None:
            indices = dialogo.indices() if resultado else None
            self.tarefa.concluir_revisao(indices)
        dialogo.deleteLater()

    def finalizar(self):
        tarefa = self.tarefa
        self.tarefa = None
        if self.dialogo_faixas is not None:
            self.dialogo_faixas.reject()
        self.progresso.accept()
        self.progresso.deleteLater()
        self.progresso = None
        self.janela.definir_ocupada(False)
        entrada, saida, categoria, formato = tarefa.argumentos[:4]
        for aviso in tarefa.avisos:
            LOG.warning("Conversão de %s para %s (%s/%s): %s", entrada, saida, categoria, formato, aviso)
        if tarefa.erro is not None:
            LOG.error("Falha na conversão de %s para %s (%s/%s): %s",
                      entrada, saida, categoria, formato, tarefa.erro)
            mensagem = textos.ERRO
            icone = QMessageBox.Icon.Critical
        elif tarefa.saida is None:
            mensagem = textos.CANCELADO
            icone = QMessageBox.Icon.Information
        else:
            mensagem = textos.SUCESSO.format(saida=tarefa.saida)
            icone = QMessageBox.Icon.Information
            if tarefa.avisos or tarefa.inicio_ts_recuperado or tarefa.perda_fim_ts is not None:
                icone = QMessageBox.Icon.Warning
            if tarefa.avisos:
                mensagem += "\n\n" + textos.AVISO_RECODIFICACAO
            if tarefa.inicio_ts_recuperado:
                mensagem += "\n\n" + textos.AVISO_INICIO_TS
            if tarefa.perda_fim_ts is not None:
                perda = f"{tarefa.perda_fim_ts:.2f}".replace(".", ",")
                mensagem += "\n\n" + textos.AVISO_FIM_TS.format(perda=perda)
        tarefa.deleteLater()
        self.janela.exibir_mensagem(mensagem, icone)
