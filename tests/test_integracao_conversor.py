import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from threading import Event, Timer

from services.conversor import (
    ConversaoCancelada, _executar, caminhos_ferramentas, converter, inspecionar_arquivo,
)
from services.metadados import carregar_formatos


RAIZ = Path(__file__).resolve().parent.parent
FFMPEG, FFPROBE = caminhos_ferramentas(RAIZ / "tools")


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
    def test_ts_com_inicio_sem_quadro_chave_gera_mkv_decodificavel(self):
        with tempfile.TemporaryDirectory() as pasta:
            pasta = Path(pasta)
            completo = pasta / "gravacao.ts"
            entrada = pasta / "gravação cortada.ts"
            saida = pasta / "recuperada.mkv"
            subprocess.run(
                [str(FFMPEG), "-v", "error", "-f", "lavfi", "-i",
                 "testsrc2=size=176x144:rate=25:duration=3", "-f", "lavfi", "-i",
                 "sine=sample_rate=48000:duration=3", "-c:v", "libopenh264", "-g", "25",
                 "-c:a", "aac", str(completo)], check=True, capture_output=True,
            )
            entrada.write_bytes(completo.read_bytes()[188 * 50:])
            with self.assertRaisesRegex(RuntimeError, "non-existing PPS"):
                inspecionar_arquivo(entrada, FFPROBE)
            avisos = []
            converter(entrada, saida, "video", "mkv", None, FFMPEG, FFPROBE, avisar_inicio_ts=avisos.append)
            self.assertEqual(len(avisos), 1)
            self.assertIn("no frame!", avisos[0])
            faixas = inspecionar_arquivo(saida, FFPROBE)
            self.assertEqual([s["codec_name"] for s in faixas], ["h264", "aac"])
            decodificacao = subprocess.run(
                [str(FFMPEG), "-v", "error", "-xerror", "-i", str(saida), "-map", "0:v",
                 "-map", "0:a", "-f", "null", "-"], check=True, capture_output=True,
            )
            self.assertEqual(decodificacao.stderr, b"")
            self.assertEqual(list(pasta.glob(".blackberry-*")), [])

    def test_ts_para_vob_preserva_audio_com_duracoes_estimadas_diferentes(self):
        with tempfile.TemporaryDirectory() as pasta:
            pasta = Path(pasta)
            entrada = pasta / "entrada.ts"
            saida = pasta / "saida.vob"
            subprocess.run(
                [str(FFMPEG), "-v", "error", "-f", "lavfi", "-i",
                 "testsrc2=size=176x144:rate=25:duration=1.5", "-f", "lavfi", "-i",
                 "sine=sample_rate=48000:duration=1.5", "-c:v", "libopenh264",
                 "-c:a", "aac", str(entrada)], check=True, capture_output=True,
            )
            converter(entrada, saida, "video", "vob", None, FFMPEG, FFPROBE)
            original = inspecionar_arquivo(entrada, FFPROBE)[1]
            convertido = inspecionar_arquivo(saida, FFPROBE)[1]
            self.assertEqual(convertido["codec_name"], "ac3")
            self.assertGreater(abs(float(original["duration"]) - float(convertido["duration"])), 0.25)
            tamanhos = []
            for arquivo in (entrada, saida):
                pcm = subprocess.run(
                    [str(FFMPEG), "-v", "error", "-xerror", "-i", str(arquivo), "-map", "0:a",
                     "-c:a", "pcm_s16le", "-f", "s16le", "-"], check=True, capture_output=True,
                ).stdout
                tamanhos.append(len(pcm))
            self.assertGreater(tamanhos[0], 100_000)
            self.assertAlmostEqual(*tamanhos, delta=2 * 1536)

    def test_ts_latm_integro_preserva_audio_estereo_e_multicanal_sem_recorte(self):
        with tempfile.TemporaryDirectory() as pasta:
            entrada = Path(pasta) / "LATM.ts"
            saida = Path(pasta) / "LATM.mp4"
            subprocess.run([
                str(FFMPEG), "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=176x144:r=25:d=2",
                "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo:d=2",
                "-f", "lavfi", "-i", "anullsrc=r=48000:cl=5.1:d=2",
                "-map", "0:v", "-map", "1:a", "-map", "2:a",
                "-c:v", "libopenh264", "-c:a", "aac", "-mpegts_flags", "+latm", str(entrada),
            ], check=True, capture_output=True)
            origem = inspecionar_arquivo(entrada, FFPROBE, detalhes=True, estimar_duracao=True)
            self.assertEqual([s["codec_name"] for s in origem["streams"]], ["h264", "aac_latm", "aac_latm"])
            avisos = []
            converter(entrada, saida, "video", "mp4", None, FFMPEG, FFPROBE, avisar_fim_ts=avisos.append)
            self.assertEqual(avisos, [])
            resultado = inspecionar_arquivo(saida, FFPROBE, detalhes=True)
            self.assertEqual([(s["codec_name"], s.get("channels")) for s in resultado["streams"]],
                             [("h264", None), ("aac", 2), ("aac", 6)])
            self.assertAlmostEqual(float(origem["format"]["duration"]), float(resultado["format"]["duration"]),
                                   delta=0.08)

    def test_mkv_com_capitulos_copia_faixas_para_mp4_e_m4a(self):
        with tempfile.TemporaryDirectory() as pasta:
            pasta = Path(pasta)
            entrada = pasta / "capítulos.mkv"
            metadados = pasta / "capitulos.txt"
            metadados.write_text(
                ";FFMETADATA1\n[CHAPTER]\nTIMEBASE=1/1000\nSTART=0\nEND=900\ntitle=Capitulo\n",
                encoding="utf-8",
            )
            subprocess.run(
                [str(FFMPEG), "-v", "error", "-f", "lavfi", "-i",
                 "testsrc2=size=176x144:rate=25:duration=1", "-f", "lavfi", "-i",
                 "sine=sample_rate=48000:duration=1", "-f", "ffmetadata", "-i", str(metadados),
                 "-map", "0:v", "-map", "1:a", "-map_chapters", "2", "-c:v", "libopenh264",
                 "-c:a", "aac", str(entrada)], check=True, capture_output=True,
            )
            for categoria, formato, esperados in (
                ("video", "mp4", ["h264", "aac", "bin_data"]), ("audio", "m4a", ["aac", "bin_data"]),
            ):
                with self.subTest(formato=formato):
                    saida = pasta / f"saida.{formato}"
                    avisos = []
                    converter(entrada, saida, categoria, formato, None, FFMPEG, FFPROBE, avisar=avisos.append)
                    dados = inspecionar_arquivo(saida, FFPROBE, detalhes=True)
                    self.assertEqual([s["codec_name"] for s in dados["streams"]], esperados)
                    self.assertEqual(dados["chapters"][0]["tags"]["title"], "Capitulo")
                    self.assertEqual(avisos, [])

    def test_mkv_h264_para_avi_copia_video_com_filtro_de_pacotes(self):
        with tempfile.TemporaryDirectory() as pasta:
            pasta = Path(pasta)
            entrada = pasta / "avc.mkv"
            saida = pasta / "video.avi"
            subprocess.run(
                [str(FFMPEG), "-v", "error", "-f", "lavfi", "-i",
                 "testsrc2=size=176x144:rate=25:duration=0.6", "-c:v", "libopenh264", str(entrada)],
                check=True, capture_output=True,
            )
            self.assertEqual(inspecionar_arquivo(entrada, FFPROBE)[0]["is_avc"], "true")
            converter(entrada, saida, "video", "avi", None, FFMPEG, FFPROBE)
            self.assertEqual(inspecionar_arquivo(saida, FFPROBE)[0]["codec_name"], "h264")
            hashes = [
                subprocess.run(
                    [str(FFMPEG), "-v", "error", "-xerror", "-i", str(arquivo), "-map", "0:v",
                     "-f", "hash", "-"], check=True, capture_output=True,
                ).stdout
                for arquivo in (entrada, saida)
            ]
            self.assertEqual(*hashes)

    def test_mkv_com_dts_repetido_para_mp4_recodifica_so_o_video(self):
        with tempfile.TemporaryDirectory() as pasta:
            pasta = Path(pasta)
            entrada = pasta / "DTS repetido.mkv"
            saida = pasta / "convertido.mp4"
            filtros = r"setts=pts=if(eq(N\,8)\,PREV_OUTPTS\,PTS):dts=if(eq(N\,8)\,PREV_OUTDTS\,DTS)"
            subprocess.run(
                [str(FFMPEG), "-v", "error", "-f", "lavfi", "-i",
                 "testsrc2=size=176x144:rate=25:duration=1", "-f", "lavfi", "-i",
                 "sine=duration=1", "-c:v", "mpeg4", "-c:a", "aac", "-bsf:v", filtros, str(entrada)],
                check=True, capture_output=True,
            )
            copia = subprocess.run(
                [str(FFMPEG), "-v", "error", "-xerror", "-i", str(entrada), "-c", "copy",
                 str(pasta / "copia direta.mp4")], capture_output=True,
            )
            self.assertNotEqual(copia.returncode, 0)
            self.assertIn(b"Non-monotonic DTS", copia.stderr)
            self.assertIn(b"Error muxing a packet", copia.stderr)
            avisos = []
            converter(entrada, saida, "video", "mp4", None, FFMPEG, FFPROBE, avisar=avisos.append)
            self.assertEqual(len(avisos), 1)
            self.assertIn("Cópia da faixa 0 falhou", avisos[0])
            self.assertEqual([s["codec_name"] for s in inspecionar_arquivo(saida, FFPROBE)], ["h264", "aac"])
            hashes_audio = [
                subprocess.run(
                    [str(FFMPEG), "-v", "error", "-i", str(arquivo), "-map", "0:a", "-c", "copy",
                     "-f", "hash", "-"], check=True, capture_output=True,
                ).stdout
                for arquivo in (entrada, saida)
            ]
            self.assertEqual(*hashes_audio)

    def test_recodifica_aac_para_mp3_sem_colidir_com_sondagem(self):
        with tempfile.TemporaryDirectory() as pasta:
            pasta = Path(pasta)
            entrada = pasta / "entrada AAC.m4a"
            subprocess.run(
                [str(FFMPEG), "-v", "error", "-f", "lavfi", "-i", "sine=duration=0.4",
                 "-c:a", "aac", str(entrada)], check=True, capture_output=True,
            )
            for nome in ("teste-0.mp3", "áudio convertido.mp3"):
                with self.subTest(nome=nome):
                    saida = pasta / nome
                    with self.assertWarnsRegex(RuntimeWarning, "exige recodificação"):
                        self.assertEqual(converter(entrada, saida, "audio", "mp3", None, FFMPEG, FFPROBE), saida)
                    streams = inspecionar_arquivo(saida, FFPROBE)
                    self.assertEqual([(s["codec_type"], s["codec_name"], s["channels"]) for s in streams],
                                     [("audio", "mp3", 1)])
                    conteudo = saida.read_bytes()
                    with self.assertRaises(FileExistsError):
                        converter(entrada, saida, "audio", "mp3", None, FFMPEG, FFPROBE)
                    self.assertEqual(saida.read_bytes(), conteudo)
                    self.assertEqual(list(pasta.glob(".blackberry-*")), [])

    def test_rejeita_video_sem_audio_e_entrada_truncada(self):
        with tempfile.TemporaryDirectory() as pasta:
            pasta = Path(pasta)
            entrada = pasta / "entrada.mp4"
            subprocess.run(
                [str(FFMPEG), "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=64x64:duration=0.8",
                 "-c:v", "mpeg4", "-movflags", "+faststart", str(entrada)], check=True, capture_output=True,
            )
            with self.assertRaisesRegex(ValueError, "não contém faixas de áudio"):
                converter(entrada, pasta / "audio.mp3", "audio", "mp3", None, FFMPEG, FFPROBE)
            dados = entrada.read_bytes()
            truncada = pasta / "truncada.mp4"
            truncada.write_bytes(dados[:len(dados) // 2])
            with self.assertRaisesRegex(RuntimeError, "inspecionar|Cópia|conversão"):
                converter(truncada, pasta / "saida.mp4", "video", "mp4", None, FFMPEG, FFPROBE)
            self.assertEqual(set(pasta.iterdir()), {entrada, truncada})

    def test_copia_audio_multicanal_preservando_canais_e_duracao(self):
        with tempfile.TemporaryDirectory() as pasta:
            pasta = Path(pasta)
            entrada = pasta / "5.1.wav"
            saida = pasta / "5.1 copia.wav"
            subprocess.run(
                [str(FFMPEG), "-v", "error", "-f", "lavfi", "-i", "anullsrc=cl=5.1:d=0.5",
                 "-c:a", "pcm_s16le", str(entrada)], check=True, capture_output=True,
            )
            converter(entrada, saida, "audio", "wav", None, FFMPEG, FFPROBE)
            faixa, = inspecionar_arquivo(saida, FFPROBE)
            self.assertEqual((faixa["codec_name"], faixa["channels"]), ("pcm_s16le", 6))
            self.assertAlmostEqual(float(faixa["duration"]), 0.5, delta=0.01)

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
            h264 = pasta / "recodificado.mp4"
            converter(entrada, h264, "video", "mp4", {0: "recodificar"}, FFMPEG, FFPROBE)
            self.assertEqual(inspecionar_arquivo(h264, FFPROBE)[0]["codec_name"], "h264")
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
