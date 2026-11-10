import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtTest import QSignalSpy, QTest
from PyQt6.QtWidgets import QApplication, QMessageBox

from interface import textos
from main import criar_janela
from services.conversor import inspecionar_arquivo


class TestSoftware(unittest.TestCase):
    def test_converte_video_para_audio_pela_interface(self):
        app = QApplication.instance() or QApplication([])
        janela = criar_janela()
        self.addCleanup(janela.close)
        controlador = janela.controlador
        if not controlador.ffmpeg.is_file() or not controlador.ffprobe.is_file():
            self.skipTest("FFmpeg e FFprobe locais ausentes")
        with tempfile.TemporaryDirectory() as pasta:
            pasta = Path(pasta)
            entrada = pasta / "vídeo de teste.mkv"
            saida = pasta / "áudio de teste.mka"
            subprocess.run(
                [str(controlador.ffmpeg), "-v", "error", "-f", "lavfi", "-i",
                 "color=size=32x32:rate=5:duration=0.4", "-f", "lavfi", "-i",
                 "sine=frequency=440:duration=0.4", "-c:v", "mpeg4", "-c:a", "aac",
                 str(entrada)],
                check=True, capture_output=True,
            )
            janela.show()
            app.processEvents()
            with (
                patch.object(janela, "escolher_entrada", return_value=str(entrada)),
                patch.object(janela, "escolher_saida", return_value=str(saida)),
                patch.object(janela, "exibir_mensagem") as mensagem,
            ):
                janela.acao_abrir.trigger()
                perfil = janela.perfil.findText(textos.PERFIL.format(categoria="Audio", formato="MKA"))
                self.assertGreaterEqual(perfil, 0)
                janela.perfil.setCurrentIndex(perfil)
                QTest.mouseClick(janela.botao_converter, Qt.MouseButton.LeftButton)
                tarefa = controlador.tarefa
                self.assertIsNotNone(tarefa)
                self.assertTrue(janela.ocupada)
                fim = QSignalSpy(tarefa.finished)
                if not fim:
                    self.assertTrue(fim.wait(10000))
                app.processEvents()
                mensagem.assert_called_once_with(
                    textos.SUCESSO.format(saida=saida), QMessageBox.Icon.Information,
                )
            self.assertFalse(janela.ocupada)
            self.assertEqual(controlador.entrada, entrada)
            self.assertEqual(
                [(s["codec_type"], s["codec_name"])
                 for s in inspecionar_arquivo(saida, controlador.ffprobe)],
                [("audio", "aac")],
            )
