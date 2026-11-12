import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from threading import Event
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

    def test_inspecao_recupera_apenas_sps_pps_com_h264_utilizavel_em_ts(self):
        h264 = {"index": 0, "codec_type": "video", "codec_name": "h264",
                "width": 1920, "height": 1080, "extradata_size": 120}
        diagnostico = ("[h264 @ abc] sps_id 0 out of range\n[h264 @ abc] non-existing PPS 0 referenced\n"
                       "    Last message repeated 5 times\n[h264 @ abc] no frame!")
        dados = {"format": {"format_name": "mpegts"}, "streams": [h264]}
        resultado = subprocess.CompletedProcess([], 0, json.dumps(dados), diagnostico)
        with patch.object(conversor, "_executar", return_value=resultado):
            inspecao = conversor.inspecionar_arquivo("entrada.ts", "ffprobe", detalhes=True, recuperar_inicio_ts=True)
            self.assertEqual(inspecao["diagnostico_inicio_ts"], diagnostico)
            with self.assertRaises(RuntimeError):
                conversor.inspecionar_arquivo("saida.ts", "ffprobe", detalhes=True)
        casos = (
            (dados, diagnostico + "\nError reading input"),
            (dados, "[h264 @ abc] sps_id 0 out of range"),
            (dict(dados, format={"format_name": "matroska"}), diagnostico),
            (dict(dados, streams=[dict(h264, extradata_size=0)]), diagnostico),
        )
        for metadados, stderr in casos:
            with self.subTest(metadados=metadados, stderr=stderr):
                falha = subprocess.CompletedProcess([], 0, json.dumps(metadados), stderr)
                with patch.object(conversor, "_executar", return_value=falha), self.assertRaises(RuntimeError):
                    conversor.inspecionar_arquivo("entrada.ts", "ffprobe", recuperar_inicio_ts=True)
        with (
            patch.object(conversor, "_executar", return_value=subprocess.CompletedProcess([], 0, "{", diagnostico)),
            self.assertRaisesRegex(ValueError, "JSON inválido"),
        ):
            conversor.inspecionar_arquivo("entrada.ts", "ffprobe", recuperar_inicio_ts=True)
        with (
            patch.object(conversor, "_executar", side_effect=subprocess.CalledProcessError(1, [], stderr=diagnostico)),
            self.assertRaisesRegex(RuntimeError, "Falha ao inspecionar"),
        ):
            conversor.inspecionar_arquivo("entrada.ts", "ffprobe", recuperar_inicio_ts=True)

    def test_valida_indices_antes_da_selecao_automatica(self):
        audio = {"index": 0, "codec_type": "audio", "codec_name": "pcm_s16le"}
        for outro in (audio, {"codec_type": "audio", "codec_name": "aac"}, dict(audio, index=True)):
            with self.subTest(outro=outro):
                with (
                    patch.object(conversor, "inspecionar_arquivo", return_value={"streams": [audio, outro]}),
                    patch.object(conversor, "_executar") as executar,
                    self.assertRaisesRegex(ValueError, "Índice de stream"),
                ):
                    conversor.converter("entrada.wav", "saida.wav", "audio", "wav", None, "ffmpeg", "ffprobe")
                executar.assert_not_called()

    def test_selecao_explicita_de_video_exige_faixa_que_nao_seja_capa(self):
        streams = [
            {"index": 0, "codec_type": "audio", "codec_name": "aac"},
            {"index": 1, "codec_type": "video", "codec_name": "mjpeg", "disposition": {"attached_pic": 1}},
            {"index": 2, "codec_type": "video", "codec_name": "h264"},
        ]
        for indices in ([0], [1], [0, 1]):
            with self.subTest(indices=indices):
                with (
                    patch.object(conversor, "inspecionar_arquivo", return_value={"streams": streams}),
                    self.assertRaisesRegex(ValueError, "Selecione pelo menos uma faixa de vídeo"),
                ):
                    conversor.converter(
                        "entrada.mkv", "saida.mp4", "video", "mp4",
                        dict.fromkeys(indices, "recodificar"), "ffmpeg", "ffprobe",
                    )
        plano = conversor.planejar_conversao(streams, "video", "mp4", [2, 0])
        self.assertEqual([item["index"] for item in plano], [2, 0])

    def test_recuperacao_latm_confirma_posicao_e_publica_apenas_saida_validada(self):
        video = {"index": 0, "codec_type": "video", "codec_name": "h264"}
        audios = [
            {"index": indice, "codec_type": "audio", "codec_name": "aac_latm",
             "channels": canais, "time_base": "1/90000"}
            for indice, canais in ((1, 2), (2, 6))
        ]
        streams = [video, *audios]
        entrada = {"format": {"format_name": "mpegts"}, "streams": streams}
        estimativa = {
            "format": {"format_name": "mpegts", "start_time": "1.5", "duration": "10"},
            "streams": [dict(s, start_time="1.5", duration="10") for s in streams],
        }
        resultado = [
            dict(s, start_time="0", duration="9.6", codec_name=codec)
            for s, codec in zip(streams, ("h264", "aac", "aac"))
        ]
        casos = {
            "fim confirmado": None,
            "permissão junto de LATM": "Permission denied",
            "progresso no meio": "Falha na conversão",
            "pacote no meio": "Falha na conversão",
            "pacote sem DTS": "Falha na conversão",
            "nova tentativa falha": "Falha ao recuperar",
            "falta uma faixa": "streams esperados",
            "áudio deslocado": "sincronismo",
            "saída indecodificável": "Falha ao decodificar",
            "cancelamento": conversor.ConversaoCancelada,
            "destino criado durante a recuperação": FileExistsError,
        }
        for caso, falha in casos.items():
            with self.subTest(caso=caso), tempfile.TemporaryDirectory() as pasta:
                destino = Path(pasta) / "saida.mp4"
                cancelamento = Event()
                tentativas = []
                avisos = []

                def inspecionar(arquivo, ffprobe, **opcoes):
                    if opcoes.get("estimar_duracao"):
                        return estimativa
                    if Path(arquivo).name == "entrada.ts":
                        return entrada
                    if caso == "falta uma faixa":
                        return {"streams": resultado[:2]}
                    if caso == "áudio deslocado":
                        return {"streams": [*resultado[:2], dict(resultado[2], start_time="0.4")]}
                    return {"streams": resultado}

                def executar(comando, evento):
                    def erro_decoder(indice):
                        return (f"[aist#0:{indice}/aac_latm @ abc] [dec:aac_latm @ def] Error submitting "
                                "packet to decoder: Invalid data found when processing input")

                    if "-encoders" in comando:
                        return subprocess.CompletedProcess(comando, 0, stdout=" A....D aac  AAC\n", stderr="")
                    if "-ss" in comando:
                        indice = int(comando[comando.index("-map") + 1].split(":")[-1])
                        dts = 500_000 if caso == "pacote no meio" else 1_017_000
                        pacote = f"[in#0/mpegts @ abc] Packet corrupt (stream = {indice}, dts = {dts})."
                        if caso == "pacote sem DTS":
                            pacote = ""
                        raise subprocess.CalledProcessError(1, comando, stderr=erro_decoder(indice) + "\n" + pacote)
                    if comando[-1] == "-":
                        self.assertIn("0:v?", comando)
                        self.assertIn("0:a?", comando)
                        stderr = "Invalid data found when processing input" if caso == "saída indecodificável" else ""
                        return subprocess.CompletedProcess(comando, 0, stderr=stderr)
                    temporario = Path(comando[-1])
                    tentativas.append(temporario)
                    temporario.write_bytes(b"midia")
                    if "-t" not in comando:
                        stderr = erro_decoder(1) + "\n" + erro_decoder(2)
                        if caso == "permissão junto de LATM":
                            stderr += "\nPermission denied"
                        progresso = "5000000" if caso == "progresso no meio" else "9900000"
                        raise subprocess.CalledProcessError(1, comando, f"out_time_us={progresso}\n", stderr)
                    self.assertNotIn("-ss", comando)
                    self.assertIn("9.600000", comando)
                    if caso == "cancelamento":
                        cancelamento.set()
                        raise conversor.ConversaoCancelada()
                    if caso == "nova tentativa falha":
                        raise subprocess.CalledProcessError(1, comando, stderr=erro_decoder(2))
                    if caso == "destino criado durante a recuperação":
                        destino.write_bytes(b"destino preexistente")
                    return subprocess.CompletedProcess(comando, 0, stderr="")

                with (
                    patch.object(conversor, "inspecionar_arquivo", side_effect=inspecionar),
                    patch.object(conversor, "_executar", side_effect=executar),
                    patch.object(conversor.LOG, "warning"),
                ):
                    def converter():
                        return conversor.converter(
                            "entrada.ts", destino, "video", "mp4", {0: "copiar", 1: "recodificar", 2: "recodificar"},
                            "ffmpeg", "ffprobe", cancelamento=cancelamento, avisar_fim_ts=avisos.append,
                        )

                    if isinstance(falha, str):
                        with self.assertRaisesRegex(RuntimeError, falha):
                            converter()
                    elif falha:
                        with self.assertRaises(falha):
                            converter()
                    else:
                        self.assertEqual(converter(), destino)
                        self.assertEqual(len(avisos), 1)
                        self.assertAlmostEqual(avisos[0], 0.4)
                if caso in ("permissão junto de LATM", "progresso no meio", "pacote no meio", "pacote sem DTS"):
                    self.assertEqual(len(tentativas), 1)
                else:
                    self.assertEqual(len(tentativas), 2)
                    self.assertNotEqual(*tentativas)
                if caso == "destino criado durante a recuperação":
                    self.assertEqual(destino.read_bytes(), b"destino preexistente")
                elif falha:
                    self.assertFalse(destino.exists())
                    self.assertEqual(avisos, [])
                self.assertFalse(list(destino.parent.glob(".blackberry-*")))

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
