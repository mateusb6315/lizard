import os
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QMimeData, QPointF, Qt, QUrl
from PyQt6.QtGui import QDropEvent, QPalette
from PyQt6.QtTest import QSignalSpy
from PyQt6.QtWidgets import QApplication, QMessageBox

from interface import textos
from interface.componentes import DialogoProgresso
from interface.componentes import JanelaPrincipal
from interface.controlador import Controlador
from main import criar_janela


class TestInterface(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.janela = criar_janela()
        self.addCleanup(self.janela.close)

    def test_abrir_pelo_menu_seleciona_sem_converter(self):
        self.assertFalse(self.janela.botao_converter.isEnabled())
        with tempfile.TemporaryDirectory() as pasta:
            arquivo = Path(pasta) / "vídeo.MP4"
            arquivo.touch()
            with patch.object(self.janela, "escolher_entrada", return_value=str(arquivo)) as abrir:
                self.janela.acao_abrir.trigger()
            self.assertIn("*.mp4", abrir.call_args.args[0])
            self.assertNotIn("Todos os arquivos", abrir.call_args.args[0])
            self.assertEqual(self.janela.entrada.text(), arquivo.name)
            self.assertTrue(self.janela.botao_converter.isEnabled())
            self.assertIsNone(self.janela.controlador.tarefa)

    def test_arrastar_formato_invalido_preserva_selecao(self):
        with tempfile.TemporaryDirectory() as pasta:
            arquivo = Path(pasta) / "entrada.wav"
            arquivo.touch()
            self.janela.controlador.selecionar_entrada(arquivo)
            invalido = arquivo.with_suffix(".txt")
            invalido.touch()
            mime = QMimeData()
            mime.setUrls([QUrl.fromLocalFile(str(invalido))])
            evento = QDropEvent(QPointF(), Qt.DropAction.CopyAction, mime,
                                Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
            with patch.object(self.janela, "exibir_mensagem") as mensagem:
                self.janela.entrada.dropEvent(evento)
            mensagem.assert_called_once_with(textos.ENTRADA_INVALIDA, QMessageBox.Icon.Warning)
            self.assertEqual(self.janela.controlador.entrada, arquivo)

    def test_progresso_exibe_etapa_e_solicita_cancelamento_uma_vez(self):
        dialogo = DialogoProgresso(self.janela)
        sinal = QSignalSpy(dialogo.cancelamento_solicitado)
        dialogo.atualizar_etapa("conversao")
        self.assertEqual(dialogo.etapa.text(), textos.ETAPAS["conversao"])
        self.assertEqual(dialogo.barra.maximum(), 0)
        self.assertIn("00:00", dialogo.detalhes.text())
        dialogo.cancelar.click()
        dialogo.reject()
        self.assertEqual(len(sinal), 1)
        self.assertEqual(dialogo.etapa.text(), textos.CANCELANDO)
        dialogo.accept()

    def test_alterna_tema_e_troca_as_duas_imagens(self):
        logo_claro = self.janela.logo.pixmap().toImage()
        nome_claro = self.janela.nome.pixmap().toImage()
        fundo_claro = self.app.palette().color(QPalette.ColorRole.Window)
        grupo = self.janela.alternador_tema.grupo
        grupo.button(1).click()
        self.assertNotEqual(self.janela.logo.pixmap().toImage(), logo_claro)
        self.assertNotEqual(self.janela.nome.pixmap().toImage(), nome_claro)
        self.assertNotEqual(self.app.palette().color(QPalette.ColorRole.Window), fundo_claro)
        grupo.button(0).click()
        self.assertEqual(self.janela.logo.pixmap().toImage(), logo_claro)
        self.assertEqual(self.janela.nome.pixmap().toImage(), nome_claro)
        self.assertEqual(self.app.palette().color(QPalette.ColorRole.Window), fundo_claro)

    def test_sair_fecha_a_janela(self):
        self.janela.show()
        self.janela.acao_sair.trigger()
        self.assertFalse(self.janela.isVisible())

    def test_tema_persiste_no_fechamento_e_reabre(self):
        recursos = Path(__file__).resolve().parents[1] / "resources"
        with tempfile.TemporaryDirectory() as pasta:
            preferencias = Path(pasta) / "preferences.json"
            for indice, tema in ((1, "dark"), (0, "default")):
                janela = JanelaPrincipal(recursos)
                controlador = Controlador(janela, Path(pasta), preferencias)
                janela.alternador_tema.grupo.button(indice).click()
                if indice == 1:
                    self.assertFalse(preferencias.exists())
                janela.show()
                janela.acao_sair.trigger()
                self.assertEqual(json.loads(preferencias.read_text(encoding="utf-8")), {"theme": tema})
                reaberta = JanelaPrincipal(recursos)
                controlador_reaberto = Controlador(reaberta, Path(pasta), preferencias)
                self.assertEqual(reaberta.alternador_tema.grupo.checkedId(), indice)
                reaberta.close()

    def test_preferencias_invalidas_abrem_no_tema_claro(self):
        recursos = Path(__file__).resolve().parents[1] / "resources"
        with tempfile.TemporaryDirectory() as pasta:
            preferencias = Path(pasta) / "preferences.json"
            preferencias.write_text("{", encoding="utf-8")
            janela = JanelaPrincipal(recursos)
            controlador = Controlador(janela, Path(pasta), preferencias)
            self.assertEqual(janela.alternador_tema.grupo.checkedId(), 0)
            janela.close()
