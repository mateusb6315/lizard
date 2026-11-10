import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from threading import Event, Timer

from services.conversor import ConversaoCancelada, _executar, converter, inspecionar_arquivo
from services.metadados import carregar_formatos


RAIZ = Path(__file__).resolve().parent.parent
FFMPEG = RAIZ / "tools" / "ffmpeg.exe"
FFPROBE = RAIZ / "tools" / "ffprobe.exe"


class TestCancelamento(unittest.TestCase):
    def test_cancela_subprocesso_ativo(self):
        cancelamento = Event()
        timer = Timer(0.3, cancelamento.set)
        timer.start()
        try:
            with self.assertRaises(ConversaoCancelada):
                _executar([sys.executable, "-c", "import time; time.sleep(5)"], cancelamento)
        finally:
            timer.cancel()
            timer.join()


@unittest.skipUnless(FFMPEG.is_file() and FFPROBE.is_file(), "FFmpeg e FFprobe locais ausentes")
class TestIntegracaoConversor(unittest.TestCase):
    def test_video_para_audio_automatico(self):
        with tempfile.TemporaryDirectory() as pasta:
            pasta = Path(pasta)
            entrada = pasta / "video.mkv"
            subprocess.run(
                [str(FFMPEG), "-v", "error", "-f", "lavfi", "-i",
                 "color=size=32x32:rate=5:duration=0.3", "-f", "lavfi", "-i",
                 "sine=frequency=440:duration=0.3", "-map", "0:v", "-map", "1:a",
                 "-map", "1:a", "-c:v", "mpeg4", "-c:a:0", "aac",
                 "-c:a:1", "pcm_s16le", str(entrada)],
                check=True, capture_output=True,
            )
            saida = pasta / "faixas.mka"
            converter(entrada, saida, "audio", "mka", None, FFMPEG, FFPROBE)
            streams = inspecionar_arquivo(saida, FFPROBE)
            self.assertEqual([(s["codec_type"], s["codec_name"]) for s in streams],
                             [("audio", "aac"), ("audio", "pcm_s16le")])
            video = pasta / "video convertido.mp4"
            etapas = []
            converter(entrada, video, "video", "mp4", None, FFMPEG, FFPROBE,
                      cancelamento=Event(), informar_etapa=etapas.append)
            streams = inspecionar_arquivo(video, FFPROBE)
            self.assertEqual([(s["codec_type"], s["codec_name"]) for s in streams],
                             [("video", "mpeg4"), ("audio", "aac"), ("audio", "aac")])
            self.assertEqual(etapas, ["inspecao", "planejamento", "conversao", "validacao"])
            cancelar = Event()
            cancelada = pasta / "cancelada.mp4"
            with self.assertRaises(ConversaoCancelada):
                converter(entrada, cancelada, "video", "mp4", None, FFMPEG, FFPROBE,
                          cancelamento=cancelar,
                          informar_etapa=lambda etapa: cancelar.set() if etapa == "conversao" else None)
            self.assertFalse(cancelada.exists())
            self.assertEqual(list(pasta.glob(".blackberry-*")), [])
            wav = pasta / "audio.wav"
            subprocess.run(
                [str(FFMPEG), "-v", "error", "-i", str(entrada), "-map", "0:a:0",
                 "-c:a", "pcm_s16le", str(wav)], check=True, capture_output=True,
            )
            convertido = pasta / "convertido.mp3"
            converter(wav, convertido, "audio", "mp3", None, FFMPEG, FFPROBE)
            self.assertEqual(inspecionar_arquivo(convertido, FFPROBE)[0]["codec_name"], "mp3")
            mp3 = pasta / "audio.mp3"
            with self.assertWarns(RuntimeWarning), self.assertRaises(RuntimeError):
                converter(entrada, mp3, "audio", "mp3", None, FFMPEG, FFPROBE)
            self.assertFalse(mp3.exists())

    def test_converte_e_consulta_metadados(self):
        with tempfile.TemporaryDirectory() as pasta:
            pasta = Path(pasta)
            entrada = pasta / "entrada com espaços.wav"
            saida = pasta / "saida.mp3"
            subprocess.run(
                [str(FFMPEG), "-v", "error", "-f", "lavfi", "-i",
                 "sine=frequency=440:duration=0.2", "-c:a", "pcm_s16le", str(entrada)],
                check=True, capture_output=True,
            )
            perfil = carregar_formatos()["audio"]["mp3"]
            self.assertEqual(perfil["audio"]["encode"][0], "libmp3lame")
            streams = inspecionar_arquivo(entrada, FFPROBE)
            converter(entrada, saida, "audio", "mp3",
                      {streams[0]["index"]: "recodificar"}, FFMPEG, FFPROBE)
            self.assertEqual(inspecionar_arquivo(saida, FFPROBE)[0]["codec_name"], "mp3")
            copia = pasta / "copia.wav"
            converter(entrada, copia, "audio", "wav",
                      {streams[0]["index"]: "copiar"}, FFMPEG, FFPROBE)
            self.assertEqual(inspecionar_arquivo(copia, FFPROBE)[0]["codec_name"], "pcm_s16le")
            with self.assertRaises(FileExistsError):
                converter(entrada, saida, "audio", "mp3",
                          {streams[0]["index"]: "recodificar"}, FFMPEG, FFPROBE)
