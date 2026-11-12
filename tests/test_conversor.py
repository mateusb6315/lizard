import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from services import conversor
from services.metadados import carregar_formatos


class TestConversor(unittest.TestCase):
    @patch("services.conversor.subprocess.run")
    def test_inspeciona_streams(self, executar):
        executar.return_value.stdout = json.dumps({"streams": [{"index": 0, "codec_name": "h264"}]})
        streams = conversor.inspecionar_arquivo("arquivo com espaços.mp4", "ffprobe")
        self.assertEqual(streams[0]["codec_name"], "h264")
        self.assertEqual(executar.call_args.args[0][-1], "arquivo com espaços.mp4")

    @patch("services.conversor.subprocess.run")
    def test_retorna_diagnostico_de_falha(self, executar):
        executar.side_effect = subprocess.CalledProcessError(1, "ffprobe", stderr="arquivo inválido")
        with self.assertRaisesRegex(RuntimeError, "arquivo inválido"):
            conversor.inspecionar_arquivo("entrada", "ffprobe")

    def test_integracao_com_catalogo_preserva_incerteza(self):
        self.assertEqual(conversor.formatos, carregar_formatos())
        streams = [{"index": 0, "codec_type": "audio", "codec_name": "aac"}]
        plano = conversor.planejar_conversao(streams, "audio", "mp3", [0])
        self.assertTrue(plano[0]["candidato_copia"])
        self.assertEqual(plano[0]["decisao"], "indefinido")

    def test_exige_indices_validos(self):
        with self.assertRaisesRegex(ValueError, "não encontrado"):
            conversor.planejar_conversao([], "audio", "mp3", [1])

    def test_falha_de_ambiente_na_sondagem_nao_dispara_recodificacao(self):
        for motivo in ("No space left on device", "Permission denied", "Input/output error"):
            with self.subTest(motivo=motivo), tempfile.TemporaryDirectory() as pasta:
                destino = Path(pasta) / "saida.mp3"

                def falhar(comando, cancelamento):
                    Path(comando[-1]).write_bytes(b"parcial")
                    raise subprocess.CalledProcessError(1, comando, stderr=motivo)

                with (
                    patch.object(conversor, "inspecionar_arquivo", return_value={"streams": [
                        {"index": 0, "codec_type": "audio", "codec_name": "aac"},
                    ]}),
                    patch.object(conversor, "_executar", side_effect=falhar) as executar,
                    self.assertRaisesRegex(RuntimeError, motivo),
                ):
                    conversor.converter("entrada.m4a", destino, "audio", "mp3", None, "ffmpeg", "ffprobe")
                executar.assert_called_once()
                self.assertIn("copy", executar.call_args.args[0])
                self.assertEqual(list(Path(pasta).iterdir()), [])

    def test_ffprobe_rejeita_diagnostico_de_erro_apos_saida_json(self):
        resultado = subprocess.CompletedProcess(
            [], 0, stdout='{"streams": []}', stderr="File ended prematurely",
        )
        with patch.object(conversor, "_executar", return_value=resultado) as executar:
            with self.assertRaisesRegex(RuntimeError, "File ended prematurely"):
                conversor.inspecionar_arquivo("entrada", "ffprobe")
        comando = executar.call_args.args[0]
        self.assertEqual(comando[comando.index("-protocol_whitelist") + 1], "file")

    def test_saida_sem_conteudo_nao_e_publicada(self):
        with tempfile.TemporaryDirectory() as pasta:
            destino = Path(pasta) / "saida.wav"

            def gerar_saida_vazia(comando, cancelamento):
                Path(comando[-1]).touch()

            with (
                patch.object(conversor, "inspecionar_arquivo", return_value={"streams": [
                    {"index": 0, "codec_type": "audio", "codec_name": "pcm_s16le"},
                ]}),
                patch.object(conversor, "_executar", side_effect=gerar_saida_vazia),
                self.assertRaisesRegex(RuntimeError, "saída com conteúdo"),
            ):
                conversor.converter("entrada.wav", destino, "audio", "wav", {0: "copiar"}, "ffmpeg", "ffprobe")
            self.assertEqual(list(Path(pasta).iterdir()), [])

    def test_rejeicao_em_saida_combinada_recodifica_so_a_faixa_identificada(self):
        video = {"index": 2, "codec_type": "video", "codec_name": "h264"}
        audio = {"index": 4, "codec_type": "audio", "codec_name": "mp3"}
        with tempfile.TemporaryDirectory() as pasta:
            destino = Path(pasta) / "saida.mp4"
            combinacoes = []
            avisos = []

            def executar(comando, cancelamento):
                if comando[-1] == "-encoders":
                    return subprocess.CompletedProcess(comando, 0, stdout=" A....D aac  AAC\n", stderr="")
                temporario = Path(comando[-1])
                if temporario.parent.name == "sondagem":
                    temporario.write_bytes(b"sondagem")
                    return
                self.assertFalse(temporario.exists())
                combinacoes.append(comando)
                temporario.write_bytes(b"saida")
                if len(combinacoes) == 1:
                    raise subprocess.CalledProcessError(
                        1, comando, stderr="[mp4 @ abc] pts (1) < dts (2) in stream 1\n"
                        "[out#0/mp4 @ def] Error muxing a packet: Invalid argument",
                    )

            with (
                patch.object(conversor, "inspecionar_arquivo", side_effect=[
                    {"streams": [video, audio]}, [video], [audio],
                    {"streams": [video, dict(audio, codec_name="aac")]},
                ]),
                patch.object(conversor, "_executar", side_effect=executar),
            ):
                self.assertEqual(
                    conversor.converter("entrada.mkv", destino, "video", "mp4", None, "ffmpeg", "ffprobe",
                                        avisar=avisos.append),
                    destino,
                )
            self.assertEqual(len(combinacoes), 2)
            self.assertEqual(len(avisos), 1)
            self.assertIn("faixa 4", avisos[0])
            for comando, codec_audio in zip(combinacoes, ("copy", "aac")):
                self.assertEqual(comando[comando.index("-c:0") + 1], "copy")
                self.assertEqual(comando[comando.index("-c:1") + 1], codec_audio)
            self.assertEqual(list(Path(pasta).iterdir()), [destino])

    def test_rejeicao_ambigua_ou_falha_de_disco_nao_identifica_faixa_para_recodificar(self):
        casos = (
            ("[out#0/mp4 @ def] Error muxing a packet: Invalid argument", (False, None)),
            ("[matroska @ abc] Can't write packet with unknown timestamp", (True, None)),
            ("[mp4 @ abc] pts (1) < dts (2) in stream 0\n"
             "[mp4 @ abc] pts (1) < dts (2) in stream 1", (False, None)),
            ("[mp4 @ abc] pts (1) < dts (2) in stream 1\n"
             "[out#0/mp4 @ def] Error writing trailer: No space left on device", (False, None)),
        )
        for diagnostico, esperado in casos:
            with self.subTest(diagnostico=diagnostico):
                self.assertEqual(conversor._rejeicao_de_copia(diagnostico), esperado)
