import tempfile
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import compilar


class TestPublicacao(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "O empacotamento e os códigos WinError exigem Windows")
    def test_publica_apos_recusa_temporaria(self):
        with tempfile.TemporaryDirectory(dir=compilar.RAIZ) as pasta:
            final = Path(pasta) / "lizard-converter-teste"
            renomear = Path.rename
            falhas = [PermissionError(13, "acesso negado", None, 5) for _ in range(2)]

            def pyinstaller(comando, **kwargs):
                produto = Path(comando[comando.index("--distpath") + 1]) / compilar.EXECUTAVEL
                (produto / "license").mkdir(parents=True)
                (produto / "Lizard.exe").write_bytes(b"teste")

            def renomear_com_falha(caminho, destino):
                if falhas:
                    raise falhas.pop()
                return renomear(caminho, destino)

            with (
                patch.object(compilar, "_ambiente", return_value={}),
                patch.object(compilar.subprocess, "run", side_effect=pyinstaller),
                patch.object(compilar, "_validar_pacote", return_value={}),
                patch.object(compilar.time, "sleep"),
                patch.object(Path, "rename", renomear_com_falha),
            ):
                resultado = compilar.compilar("teste", "beta", final, {}, {})
            self.assertEqual(resultado, final)
            self.assertEqual((final / "Lizard.exe").read_bytes(), b"teste")
            self.assertFalse(falhas)
