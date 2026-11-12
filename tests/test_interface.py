import os
import json
import logging
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QMimeData, QPointF, QSize, Qt, QUrl
from PyQt6.QtGui import QDropEvent, QPalette
from PyQt6.QtTest import QSignalSpy, QTest
from PyQt6.QtWidgets import QApplication, QFileDialog, QMessageBox

import main as aplicativo
from interface import textos
from interface.componentes import DialogoProgresso
from main import criar_janela
from services import logger as armazenamento
from services.metadados import carregar_formatos


class TestInterface(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.janela = criar_janela()
        self.addCleanup(self.janela.close)

    def _janela_compilada(self, destino, anterior=None):
        executavel = self.janela.recursos.parent / "Lizard.exe"
        with (
            patch.object(aplicativo.sys, "frozen", True, create=True),
            patch.object(aplicativo.sys, "executable", str(executavel)),
            patch.object(aplicativo, "config_preferencias", return_value=(destino, anterior)),
        ):
            return criar_janela()

    def test_abrir_pelo_menu_seleciona_sem_converter(self):
        self.assertFalse(self.janela.botao_converter.isEnabled())
        with tempfile.TemporaryDirectory() as pasta:
            arquivo = Path(pasta) / "vídeo.MP4"
            arquivo.touch()
            with patch.object(self.janela, "escolher_entrada", return_value=str(arquivo)) as abrir:
                self.janela.acao_abrir.trigger()
            self.assertIn("*.mp4", abrir.call_args.args[0])
            self.assertNotIn("Todos os arquivos", abrir.call_args.args[0])
            self.assertEqual(self.janela.entrada.text(), arquivo.name)
            self.assertTrue(self.janela.botao_converter.isEnabled())
            self.assertIsNone(self.janela.controlador.tarefa)

    def test_arrastar_formato_invalido_preserva_selecao(self):
        with tempfile.TemporaryDirectory() as pasta:
            arquivo = Path(pasta) / "entrada.wav"
            arquivo.touch()
            self.janela.controlador.selecionar_entrada(arquivo)
            invalido = arquivo.with_suffix(".txt")
            invalido.touch()
            mime = QMimeData()
            mime.setUrls([QUrl.fromLocalFile(str(invalido))])
            evento = QDropEvent(QPointF(), Qt.DropAction.CopyAction, mime,
                                Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
            with patch.object(self.janela, "exibir_mensagem") as mensagem:
                self.janela.entrada.dropEvent(evento)
            mensagem.assert_called_once_with(textos.ENTRADA_INVALIDA, QMessageBox.Icon.Warning)
            self.assertEqual(self.janela.controlador.entrada, arquivo)

    def test_categoria_filtra_perfis_por_teclado_e_preserva_entrada(self):
        categoria = self.janela.categoria
        perfil = self.janela.perfil
        catalogos = carregar_formatos()
        self.assertEqual(categoria.currentData(), "video")
        with tempfile.TemporaryDirectory() as pasta:
            entrada = Path(pasta) / "vídeo.mp4"
            entrada.touch()
            self.janela.controlador.selecionar_entrada(entrada)
            self.janela.show()
            for tecla, esperada in ((None, "video"), (Qt.Key.Key_Down, "audio"), (Qt.Key.Key_Up, "video")):
                if tecla is not None:
                    QTest.keyClick(categoria, tecla)
                self.assertEqual(categoria.currentData(), esperada)
                self.assertEqual(
                    [perfil.itemData(i) for i in range(perfil.count())],
                    [(esperada, nome, dados["extension"]) for nome, dados in catalogos[esperada].items()],
                )
                self.assertEqual(perfil.currentIndex(), 0)
                self.assertEqual(self.janela.controlador.entrada, entrada)
                self.assertTrue(self.janela.botao_converter.isEnabled())
            self.janela.definir_ocupada(True)
            self.assertFalse(categoria.isEnabled())
            self.assertFalse(perfil.isEnabled())
            self.janela.definir_ocupada(False)
            self.assertTrue(categoria.isEnabled())
            self.assertTrue(perfil.isEnabled())

    def test_categoria_sem_perfis_desabilita_conversao(self):
        catalogos = carregar_formatos()
        catalogos["audio"] = {}
        janela = criar_janela(catalogos=catalogos)
        self.addCleanup(janela.close)
        with tempfile.TemporaryDirectory() as pasta:
            entrada = Path(pasta) / "video.mp4"
            entrada.touch()
            janela.controlador.selecionar_entrada(entrada)
            janela.categoria.setCurrentIndex(janela.categoria.findData("audio"))
            self.assertEqual(janela.perfil.count(), 0)
            self.assertFalse(janela.botao_converter.isEnabled())
            self.assertEqual(janela.ajuda.text(), textos.CATEGORIA_INDISPONIVEL)
            janela.categoria.setCurrentIndex(janela.categoria.findData("video"))
            self.assertTrue(janela.botao_converter.isEnabled())

    def test_icones_das_categorias_sao_visiveis_nos_dois_temas(self):
        imagens = []
        for tema in (0, 1):
            self.janela.alternador_tema.grupo.button(tema).click()
            imagens_tema = []
            for indice in range(self.janela.categoria.count()):
                icone = self.janela.categoria.itemIcon(indice)
                imagem = icone.pixmap(QSize(18, 18)).toImage()
                self.assertTrue(any(imagem.pixelColor(x, y).alpha() for x in range(18) for y in range(18)))
                imagens_tema.append(imagem)
            self.assertNotEqual(*imagens_tema)
            imagens.append(imagens_tema)
        self.assertTrue(all(claro != escuro for claro, escuro in zip(*imagens)))

    def test_abrir_usa_dialogo_nativo_tambem_no_tema_escuro(self):
        self.janela.alternador_tema.grupo.button(1).click()
        with patch.object(QFileDialog, "getOpenFileName", return_value=("", "")) as abrir:
            self.janela.acao_abrir.trigger()
        abrir.assert_called_once_with(self.janela, textos.ABRIR, "", self.janela.controlador.filtro_entrada)

    def test_salvar_usa_dialogo_nativo_nos_dois_temas(self):
        sugestao = Path("mídia convertida.mp4")
        filtro = "MP4 (*.mp4)"
        for tema in (0, 1):
            with self.subTest(tema=tema):
                self.janela.alternador_tema.grupo.button(tema).click()
                with patch.object(QFileDialog, "getSaveFileName", return_value=(str(sugestao), filtro)) as salvar:
                    self.assertEqual(self.janela.escolher_saida(sugestao, filtro), str(sugestao))
                salvar.assert_called_once_with(
                    self.janela, textos.SALVAR, str(sugestao), filtro,
                    options=QFileDialog.Option.DontConfirmOverwrite,
                )

    def test_progresso_exibe_etapa_e_solicita_cancelamento_uma_vez(self):
        dialogo = DialogoProgresso(self.janela)
        sinal = QSignalSpy(dialogo.cancelamento_solicitado)
        dialogo.atualizar_etapa("conversao")
        self.assertEqual(dialogo.etapa.text(), textos.ETAPAS["conversao"])
        self.assertEqual(dialogo.barra.maximum(), 0)
        self.assertIn("00:00", dialogo.detalhes.text())
        dialogo.cancelar.click()
        dialogo.reject()
        self.assertEqual(len(sinal), 1)
        self.assertEqual(dialogo.etapa.text(), textos.CANCELANDO)
        dialogo.accept()

    def test_alterna_tema_e_troca_as_duas_imagens(self):
        logo_claro = self.janela.logo.pixmap().toImage()
        nome_claro = self.janela.nome.pixmap().toImage()
        fundo_claro = self.app.palette().color(QPalette.ColorRole.Window)
        grupo = self.janela.alternador_tema.grupo
        grupo.button(1).click()
        self.assertNotEqual(self.janela.logo.pixmap().toImage(), logo_claro)
        self.assertNotEqual(self.janela.nome.pixmap().toImage(), nome_claro)
        self.assertNotEqual(self.app.palette().color(QPalette.ColorRole.Window), fundo_claro)
        grupo.button(0).click()
        self.assertEqual(self.janela.logo.pixmap().toImage(), logo_claro)
        self.assertEqual(self.janela.nome.pixmap().toImage(), nome_claro)
        self.assertEqual(self.app.palette().color(QPalette.ColorRole.Window), fundo_claro)

    def test_sair_fecha_a_janela(self):
        self.janela.show()
        self.janela.acao_sair.trigger()
        self.assertFalse(self.janela.isVisible())

    def test_tema_persiste_no_fechamento_e_reabre(self):
        with tempfile.TemporaryDirectory() as pasta:
            preferencias = Path(pasta) / "preferences.json"
            for indice, tema in ((1, "dark"), (0, "default")):
                janela = self._janela_compilada(preferencias)
                janela.alternador_tema.grupo.button(indice).click()
                if indice == 1:
                    self.assertFalse(preferencias.exists())
                janela.show()
                janela.acao_sair.trigger()
                self.assertEqual(json.loads(preferencias.read_text(encoding="utf-8")), {"theme": tema})
                reaberta = self._janela_compilada(preferencias)
                self.assertEqual(reaberta.alternador_tema.grupo.checkedId(), indice)
                reaberta.close()

    def test_preferencias_invalidas_abrem_no_tema_claro(self):
        with tempfile.TemporaryDirectory() as pasta:
            preferencias = Path(pasta) / "preferences.json"
            preferencias.write_text("{", encoding="utf-8")
            janela = self._janela_compilada(preferencias)
            self.assertEqual(janela.alternador_tema.grupo.checkedId(), 0)
            janela.close()

    def test_instalacao_compartilhada_salva_tema_por_usuario(self):
        with tempfile.TemporaryDirectory() as pasta:
            pasta = Path(pasta)
            programas = pasta / "Program Files"
            pacote = programas / textos.TITULO
            antiga = pacote / "data" / "preferences.json"
            antiga.parent.mkdir(parents=True)
            antiga.write_text('{"theme": "dark"}', encoding="utf-8")
            usuario = pasta / "LocalAppData"
            with patch.dict(os.environ, {"ProgramFiles": str(programas)}):
                destino, anterior = armazenamento.config_preferencias(pacote, usuario)
                self.assertEqual(destino, usuario / "LizardConverter" / "preferences.json")
                self.assertEqual(anterior, antiga)
                self.assertEqual(
                    armazenamento.config_preferencias(pasta / "portatil", usuario),
                    (pasta / "portatil" / "data" / "preferences.json", None),
                )
                personalizado = pasta / "instalacao personalizada"
                personalizado.mkdir()
                (personalizado / "unins000.exe").touch()
                (personalizado / "unins000.dat").touch()
                self.assertEqual(armazenamento.config_preferencias(personalizado, usuario)[0], destino)
            janela = self._janela_compilada(destino, anterior)
            self.assertEqual(janela.alternador_tema.grupo.checkedId(), 1)
            self.assertFalse(destino.exists())
            janela.alternador_tema.grupo.button(0).click()
            janela.close()
            self.assertEqual(json.loads(destino.read_text(encoding="utf-8")), {"theme": "default"})
            self.assertEqual(json.loads(antiga.read_text(encoding="utf-8")), {"theme": "dark"})
            reaberta = self._janela_compilada(destino, anterior)
            self.assertEqual(reaberta.alternador_tema.grupo.checkedId(), 0)
            reaberta.close()

    def test_falha_ao_gravar_tema_exibe_aviso_e_registra_caminho(self):
        with tempfile.TemporaryDirectory() as pasta:
            destino = Path(pasta) / "arquivo" / "preferences.json"
            destino.parent.touch()
            janela = self._janela_compilada(destino)
            with patch.object(janela, "exibir_mensagem") as mensagem, self.assertLogs("lizard") as log:
                janela.close()
            mensagem.assert_called_once_with(textos.PREFERENCIAS_ERRO, QMessageBox.Icon.Warning)
            self.assertIn(str(destino), log.output[0])
            self.assertNotIn(str(destino), mensagem.call_args.args[0])

    def test_inicio_exibe_erro_generico_de_catalogo_e_registra_detalhes(self):
        with tempfile.TemporaryDirectory() as pasta:
            catalogo = Path(pasta) / "video.json"
            for conteudo, esperado in (
                (None, "Catálogo de formatos ausente"),
                ("{", "JSON inválido"),
                (PermissionError("Acesso negado"), "Sem permissão para ler"),
            ):
                with self.subTest(esperado=esperado):
                    if isinstance(conteudo, str):
                        catalogo.write_text(conteudo, encoding="utf-8")
                    exibidas = []
                    with (
                        patch("services.metadados.METADADOS", catalogo.parent),
                        patch.object(aplicativo, "QApplication", return_value=self.app),
                        patch.object(QMessageBox, "exec", lambda caixa: exibidas.append(caixa.text())),
                        self.assertLogs("lizard") as log,
                    ):
                        if isinstance(conteudo, PermissionError):
                            with patch.object(Path, "open", side_effect=conteudo):
                                self.assertEqual(aplicativo.main(), 1)
                        else:
                            self.assertEqual(aplicativo.main(), 1)
                    mensagem, = exibidas
                    self.assertEqual(mensagem, textos.CATALOGOS_ERRO)
                    self.assertNotIn(str(catalogo), mensagem)
                    self.assertNotIn(esperado, mensagem)
                    self.assertIn(str(catalogo), log.output[0])
                    self.assertIn(esperado, log.output[0])

    def test_configura_log_local_em_utf8(self):
        with tempfile.TemporaryDirectory() as pasta:
            logger = logging.Logger("teste-lizard")
            with patch.object(armazenamento, "LOG", logger):
                armazenamento.config_logger(pasta)
                armazenamento.config_logger(pasta)
            try:
                self.assertEqual(len(logger.handlers), 1)
                self.assertEqual(logger.handlers[0].maxBytes, 1_000_000)
                self.assertEqual(logger.handlers[0].backupCount, 2)
                logger.error("Falha ao converter a faixa de áudio")
                log = Path(pasta) / "LizardConverter" / "lizard.log"
                self.assertIn("Falha ao converter a faixa de áudio", log.read_text(encoding="utf-8"))
            finally:
                for handler in logger.handlers:
                    handler.close()

    def test_base_local_ausente_preserva_leitura_legada_sem_gravar_em_instalacao(self):
        with tempfile.TemporaryDirectory() as pasta:
            programas = Path(pasta)
            pacote = programas / "LizardConverter"
            antiga = pacote / "data" / "preferences.json"
            antiga.parent.mkdir(parents=True)
            antiga.write_text('{"theme": "dark"}', encoding="utf-8")
            with patch.dict(os.environ, {"ProgramFiles": str(programas)}):
                self.assertEqual(armazenamento.config_preferencias(pacote, ""), (None, antiga))
            with patch.object(armazenamento, "RotatingFileHandler") as handler:
                armazenamento.config_logger("")
                handler.assert_not_called()
            janela = self._janela_compilada(None, antiga)
            self.assertEqual(janela.alternador_tema.grupo.checkedId(), 1)
            janela.alternador_tema.grupo.button(0).click()
            janela.close()
            self.assertEqual(json.loads(antiga.read_text(encoding="utf-8")), {"theme": "dark"})

    def test_falha_na_substituicao_atomica_preserva_preferencia(self):
        with tempfile.TemporaryDirectory() as pasta:
            destino = Path(pasta) / "preferences.json"
            destino.write_text('{"theme": "dark"}', encoding="utf-8")
            with patch.object(Path, "replace", side_effect=PermissionError), self.assertLogs("lizard"):
                self.assertFalse(armazenamento.gravar_tema(destino, "default"))
            self.assertEqual(armazenamento.ler_tema(destino, None), "dark")
            self.assertEqual(list(destino.parent.iterdir()), [destino])
