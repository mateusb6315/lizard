# controlador intermediário entre a interface e os serviços. é sua única responsabilidade, seguindo o padrão SRP

import os
import json
from pathlib import Path
from threading import Event

from PyQt6.QtCore import QIODevice, QObject, QSaveFile, QThread, pyqtSignal
from PyQt6.QtWidgets import QMessageBox

from interface import textos
from interface.componentes import DialogoProgresso
from services import conversor


class ConversaoEmSegundoPlano(QThread):
    etapa_alterada = pyqtSignal(str)

    def __init__(self, pai, entrada, saida, categoria, formato, ffmpeg, ffprobe):
        super().__init__(pai)
        self.argumentos = (entrada, saida, categoria, formato, None, ffmpeg, ffprobe)
        self.cancelamento = Event()
        self.saida = None
        self.erro = None
        self.avisos = []

    def run(self):
        try:
            self.saida = conversor.converter(
                *self.argumentos, cancelamento=self.cancelamento,
                informar_etapa=self.etapa_alterada.emit, avisar=self.avisos.append,
            )
        except conversor.ConversaoCancelada:
            pass
        except Exception as erro:
            self.erro = erro


class Controlador(QObject):
    def __init__(self, janela, ferramentas, preferencias=None):
        super().__init__(janela)
        self.janela = janela
        self.preferencias = preferencias
        sufixo = ".exe" if os.name == "nt" else ""
        self.ffmpeg = ferramentas / f"ffmpeg{sufixo}"
        self.ffprobe = ferramentas / f"ffprobe{sufixo}"
        self.entrada = None
        self.tarefa = None
        self.progresso = None
        self.extensoes = set()
        for categoria, perfis in conversor.formatos.items():
            for formato, perfil in perfis.items():
                extensao = perfil["extension"]
                self.extensoes.add(f".{extensao.lower()}")
                titulo = textos.PERFIL.format(categoria=categoria.capitalize(), formato=formato.upper())
                janela.perfil.addItem(titulo, (categoria, formato, extensao))
        self.filtro_entrada = textos.FILTRO_ENTRADA.format(
            extensoes=" ".join(f"*{extensao}" for extensao in sorted(self.extensoes))
        )
        janela.abrir_solicitado.connect(self.abrir)
        janela.entrada.arquivo_solto.connect(self.selecionar_entrada)
        janela.converter_solicitado.connect(self.converter)
        if self.preferencias is not None:
            try:
                dados = json.loads(self.preferencias.read_text(encoding="utf-8"))
                if isinstance(dados, dict) and dados.get("theme") == "dark":
                    janela.alternador_tema.grupo.button(1).setChecked(True)
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                pass
            janela.fechamento_confirmado.connect(self.salvar_tema)

    def salvar_tema(self):
        tema = "dark" if self.janela.alternador_tema.grupo.checkedId() == 1 else "default"
        arquivo = QSaveFile(str(self.preferencias))
        conteudo = (json.dumps({"theme": tema}) + "\n").encode("utf-8")
        if not arquivo.open(QIODevice.OpenModeFlag.WriteOnly):
            self.janela.exibir_mensagem(textos.PREFERENCIAS_ERRO, QMessageBox.Icon.Warning)
            return
        if arquivo.write(conteudo) != len(conteudo) or not arquivo.commit():
            arquivo.cancelWriting()
            self.janela.exibir_mensagem(textos.PREFERENCIAS_ERRO, QMessageBox.Icon.Warning)

    def abrir(self):
        arquivo = self.janela.escolher_entrada(self.filtro_entrada)
        if arquivo:
            self.selecionar_entrada(arquivo)

    def selecionar_entrada(self, arquivo):
        if self.tarefa is not None:
            return
        entrada = Path(arquivo)
        if not entrada.is_file() or entrada.suffix.lower() not in self.extensoes:
            self.janela.exibir_mensagem(textos.ENTRADA_INVALIDA, QMessageBox.Icon.Warning)
            return
        self.entrada = entrada
        self.janela.mostrar_entrada(entrada)

    def converter(self):
        if self.entrada is None or self.tarefa is not None:
            return
        if not self.ffmpeg.is_file() or not self.ffprobe.is_file():
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
        if saida.suffix.lower() != f".{extensao.lower()}" or saida.exists():
            mensagem = textos.SAIDA_INVALIDA.format(extensao=extensao)
            self.janela.exibir_mensagem(mensagem, QMessageBox.Icon.Warning)
            return
        self.tarefa = ConversaoEmSegundoPlano(
            self, self.entrada, saida, categoria, formato, self.ffmpeg, self.ffprobe,
        )
        self.progresso = DialogoProgresso(self.janela)
        self.progresso.cancelamento_solicitado.connect(self.tarefa.cancelamento.set)
        self.tarefa.etapa_alterada.connect(self.progresso.atualizar_etapa)
        self.tarefa.finished.connect(self.finalizar)
        self.janela.definir_ocupada(True)
        self.progresso.show()
        self.tarefa.start()

    def finalizar(self):
        tarefa = self.tarefa
        self.tarefa = None
        self.progresso.accept()
        self.progresso.deleteLater()
        self.progresso = None
        self.janela.definir_ocupada(False)
        if tarefa.erro is not None:
            mensagem = textos.ERRO.format(motivo=tarefa.erro)
            icone = QMessageBox.Icon.Critical
        elif tarefa.saida is None:
            mensagem = textos.CANCELADO
            icone = QMessageBox.Icon.Information
        else:
            mensagem = textos.SUCESSO.format(saida=tarefa.saida)
            icone = QMessageBox.Icon.Information
        if tarefa.avisos:
            mensagem += "\n\n" + "\n\n".join(tarefa.avisos)
            if icone == QMessageBox.Icon.Information:
                icone = QMessageBox.Icon.Warning
        tarefa.deleteLater()
        self.janela.exibir_mensagem(mensagem, icone)
