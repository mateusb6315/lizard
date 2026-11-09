import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from services.formatos import METADADOS, carregar_formatos


class TestCarregarFormatos(unittest.TestCase):
    def test_carrega_catalogos_sem_alterar_os_dados(self):
        formatos = carregar_formatos()

        self.assertEqual(set(formatos), {"video", "audio"})
        self.assertIn("mp4", formatos["video"])
        self.assertIn("mp3", formatos["audio"])
        for categoria in ("video", "audio"):
            with (METADADOS / f"{categoria}.json").open(encoding="utf-8") as arquivo:
                self.assertEqual(formatos[categoria], json.load(arquivo))

    def test_conversor_consulta_catalogos_fora_da_raiz(self):
        origem = Path.cwd()
        with tempfile.TemporaryDirectory() as pasta:
            try:
                os.chdir(pasta)
                from services.conversor import formatos

                self.assertEqual(formatos, carregar_formatos())
                self.assertEqual(formatos["video"]["mp4"]["extension"], "mp4")
                self.assertEqual(formatos["audio"]["mp3"]["extension"], "mp3")
            finally:
                os.chdir(origem)

    def test_catalogo_ausente_identifica_o_arquivo(self):
        with tempfile.TemporaryDirectory() as pasta:
            with patch("services.formatos.METADADOS", Path(pasta)):
                with self.assertRaisesRegex(FileNotFoundError, r"ausente: .*video\.json"):
                    carregar_formatos()

    def test_json_malformado_informa_arquivo_linha_e_coluna(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta)
            (caminho / "video.json").write_text("{", encoding="utf-8")
            with patch("services.formatos.METADADOS", caminho):
                with self.assertRaisesRegex(ValueError, r"video\.json: JSON inválido na linha 1, coluna 2"):
                    carregar_formatos()

    def test_codificacao_invalida_identifica_o_arquivo(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta)
            (caminho / "video.json").write_bytes(b"\xff")
            with patch("services.formatos.METADADOS", caminho):
                with self.assertRaisesRegex(ValueError, r"video\.json: conteúdo inválido em UTF-8"):
                    carregar_formatos()

    def test_estrutura_invalida_identifica_o_campo(self):
        bloco = {"copy": [], "encode": ["aac"]}
        casos = (
            ([], r"audio\.json: esperado um objeto"),
            ({}, r"audio\.json: esperado um objeto"),
            ({"aac": []}, r"\[aac\]: esperado um objeto"),
            ({"aac": {"audio": bloco}}, r"\[aac\]\.extension"),
            ({"aac": {"extension": "aac"}}, r"\[aac\]\.audio:"),
            ({"aac": {"extension": "aac", "audio": {"encode": ["aac"]}}}, r"\.audio\.copy"),
            ({"aac": {"extension": "aac", "audio": dict(bloco, encode="aac")}}, r"\.audio\.encode"),
            ({"aac": {"extension": "aac", "audio": dict(bloco, args=[1])}}, r"\.audio\.args"),
        )
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta)
            (caminho / "video.json").write_bytes((METADADOS / "video.json").read_bytes())
            with patch("services.formatos.METADADOS", caminho):
                for catalogo, erro in casos:
                    with self.subTest(catalogo=catalogo):
                        (caminho / "audio.json").write_text(json.dumps(catalogo), encoding="utf-8")
                        with self.assertRaisesRegex(ValueError, erro):
                            carregar_formatos()
