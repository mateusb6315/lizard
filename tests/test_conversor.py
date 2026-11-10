import json
import subprocess
import unittest
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
