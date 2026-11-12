import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import instalador


class TestInstalador(unittest.TestCase):
    def test_parametros_e_colisao(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent.parent) as pasta:
            pacote = Path(pasta) / 'beta' / 'lizard-converter-0.9 beta4'
            pacote.mkdir(parents=True)
            (pacote / 'Lizard.exe').write_bytes(b'app')
            (pacote / 'build.json').write_text(json.dumps({'versao': '0.9 beta4', 'canal': 'beta'}), encoding='utf-8')
            with patch.object(instalador.shutil, 'which', return_value='ISCC.exe'):
                requisitos = instalador.verificar(pacote)
                self.assertEqual(requisitos[3].name, 'lizard-converter-0.9-beta4-setup.exe')
                requisitos[3].write_bytes(b'existente')
                with self.assertRaises(FileExistsError):
                    instalador.verificar(pacote)
                self.assertEqual(requisitos[3].read_bytes(), b'existente')

    def test_metadados_inconsistentes(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent.parent) as pasta:
            pacote = Path(pasta) / 'beta' / 'lizard-converter-1'
            pacote.mkdir(parents=True)
            (pacote / 'Lizard.exe').touch()
            (pacote / 'build.json').write_text('{"versao":"1", "canal":"release"}', encoding='utf-8')
            with patch.object(instalador.shutil, 'which', return_value='ISCC.exe'):
                with self.assertRaises(ValueError):
                    instalador.verificar(pacote)

