import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtTest import QSignalSpy, QTest
from PyQt6.QtWidgets import QApplication, QLabel, QMessageBox

from interface import textos
from main import criar_janela
from services.conversor import inspecionar_arquivo


class TestSoftware(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_erro_real_de_conversao_exibe_mensagem_curta_e_registra_diagnostico(self):
        janela = criar_janela()
        self.addCleanup(janela.close)
        controlador = janela.controlador
        self.assertTrue(controlador.ffmpeg.is_file() and controlador.ffprobe.is_file(),
                        "FFmpeg e FFprobe locais são necessários para este teste completo")
        with tempfile.TemporaryDirectory() as pasta:
            entrada = Path(pasta) / "mídia inválida.mkv"
            entrada.write_bytes(b"arquivo que nao e midia")
            destino = entrada.with_name("saida.mp4")
            controlador.selecionar_entrada(entrada)
            janela.perfil.setCurrentIndex(janela.perfil.findText("MP4"))
            with (
                patch.object(janela, "escolher_saida", return_value=str(destino)),
                patch.object(janela, "exibir_mensagem") as mensagem,
                self.assertLogs("lizard", level="ERROR") as log,
            ):
                janela.botao_converter.click()
                tarefa = controlador.tarefa
                self.assertIsNotNone(tarefa)
                fim = QSignalSpy(tarefa.finished)
                if not fim:
                    self.assertTrue(fim.wait(10000))
                self.app.processEvents()
                mensagem.assert_called_once_with(textos.ERRO, QMessageBox.Icon.Critical)
            self.assertIn(str(entrada), log.output[0])
            self.assertIn("Falha ao inspecionar", log.output[0])
            self.assertFalse(destino.exists())
            self.assertFalse(janela.ocupada)

    def test_converte_video_para_audio_pela_interface(self):
        app = self.app
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
                categoria = janela.categoria.findData("audio")
                self.assertGreaterEqual(categoria, 0)
                janela.categoria.setCurrentIndex(categoria)
                perfil = janela.perfil.findText("MKA")
                self.assertGreaterEqual(perfil, 0)
                janela.perfil.setCurrentIndex(perfil)
                self.assertEqual(janela.perfil.currentData(), ("audio", "mka", "mka"))
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

    def test_revisa_faixas_antes_de_converter_ou_cancelar(self):
        app = self.app
        janela = criar_janela()
        self.addCleanup(janela.close)
        controlador = janela.controlador
        self.assertTrue(controlador.ffmpeg.is_file() and controlador.ffprobe.is_file(),
                        "FFmpeg e FFprobe locais são necessários para este teste completo")
        with tempfile.TemporaryDirectory() as pasta:
            pasta = Path(pasta)
            legenda = pasta / "legenda.srt"
            legenda.write_text("1\n00:00:00,000 --> 00:00:00,500\nLegenda\n", encoding="utf-8")
            entrada = pasta / "mídia com faixas.mkv"
            subprocess.run(
                [str(controlador.ffmpeg), "-v", "error", "-f", "lavfi", "-i",
                 "color=size=32x32:rate=5:duration=0.6", "-f", "lavfi", "-i",
                 "sine=sample_rate=44100:duration=0.6", "-f", "lavfi", "-i",
                 "sine=sample_rate=48000:duration=0.6", "-i", str(legenda),
                 "-map", "0:v", "-map", "1:a", "-map", "2:a", "-map", "3:s",
                 "-c:v", "mpeg4", "-c:a:0", "aac", "-c:a:1", "pcm_s16le", "-c:s", "srt",
                 "-attach", str(legenda), "-metadata:s:t", "mimetype=text/plain", str(entrada)],
                check=True, capture_output=True,
            )
            janela.show()
            controlador.selecionar_entrada(entrada)
            for categoria, formato, cancelar in (("audio", "mp3", True), ("audio", "mp3", False),
                                                   ("video", "mp4", False)):
                with self.subTest(categoria=categoria, cancelar=cancelar):
                    saida = pasta / f"{categoria} selecionado.{formato}"
                    janela.categoria.setCurrentIndex(janela.categoria.findData(categoria))
                    janela.perfil.setCurrentIndex(janela.perfil.findText(formato.upper()))
                    with (
                        patch.object(janela, "escolher_saida", return_value=str(saida)),
                        patch.object(janela, "exibir_mensagem") as mensagem,
                    ):
                        janela.botao_converter.click()
                        tarefa = controlador.tarefa
                        self.assertIsNotNone(tarefa)
                        fim = QSignalSpy(tarefa.finished)
                        revisao = QSignalSpy(tarefa.faixas_disponiveis)
                        try:
                            app.processEvents()
                            if controlador.dialogo_faixas is None and not revisao:
                                self.assertTrue(revisao.wait(10000))
                            app.processEvents()
                            dialogo = controlador.dialogo_faixas
                            self.assertIsNotNone(dialogo)
                            avisos = "\n".join(rotulo.text() for rotulo in dialogo.findChildren(QLabel))
                            self.assertIn("legendas", avisos)
                            self.assertIn("anexos", avisos)
                            self.assertFalse(saida.exists())
                            if categoria == "audio":
                                self.assertIn(textos.FAIXA_UNICA, avisos)
                                self.assertEqual(dialogo.indices(), (1,))
                                dialogo.faixas[1][2].click()
                                self.assertEqual(dialogo.indices(), (2,))
                            else:
                                self.assertEqual(dialogo.indices(), (0, 1, 2))
                                dialogo.faixas[0][2].click()
                                self.assertFalse(dialogo.continuar.isEnabled())
                                dialogo.faixas[0][2].click()
                                dialogo.faixas[2][2].click()
                                self.assertEqual(dialogo.indices(), (0, 1))
                            if cancelar:
                                dialogo.reject()
                            else:
                                QTest.mouseClick(dialogo.continuar, Qt.MouseButton.LeftButton)
                            if not fim:
                                self.assertTrue(fim.wait(10000))
                            app.processEvents()
                            mensagem.assert_called_once_with(
                                textos.CANCELADO if cancelar else textos.SUCESSO.format(saida=saida),
                                QMessageBox.Icon.Information,
                            )
                        finally:
                            if controlador.tarefa is not None:
                                tarefa.cancelamento.set()
                                tarefa.wait(10000)
                                app.processEvents()
                    self.assertFalse(janela.ocupada)
                    if cancelar:
                        self.assertFalse(saida.exists())
                    else:
                        faixas = inspecionar_arquivo(saida, controlador.ffprobe)
                        if categoria == "audio":
                            faixa, = faixas
                            self.assertEqual((faixa["codec_name"], faixa["sample_rate"]), ("mp3", "48000"))
                        else:
                            self.assertEqual(
                                [(s["codec_type"], s["codec_name"]) for s in faixas],
                                [("video", "mpeg4"), ("audio", "aac")],
                            )
                    self.assertEqual(list(pasta.glob(".blackberry-*")), [])
