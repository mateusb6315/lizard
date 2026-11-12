# implementa a lógica de conversão. decide se o arquivo será copiado ou re-encodificado, com auxílio do ffprobe e os metadados

from services.metadados import carregar_formatos
import json
import subprocess
import os
import re
import tempfile
import warnings
from pathlib import Path

PERFIS_AUDIO_FAIXA_UNICA = frozenset({"mp3", "wav", "flac", "aac", "aiff", "ac3", "mp2", "wv", "caf"})


def __getattr__(nome):
    # Mantém o acesso existente aos catálogos sem ler arquivos durante o import.
    if nome == "formatos":
        return carregar_formatos()
    raise AttributeError(nome)


def caminhos_ferramentas(pasta_tools):
    pasta = Path(pasta_tools) / "ffmpeg"
    sufixo = ".exe" if os.name == "nt" else ""
    return pasta / f"ffmpeg{sufixo}", pasta / f"ffprobe{sufixo}"


class ConversaoCancelada(Exception):
    """A operação foi interrompida antes de publicar o resultado."""


def _executar(comando, cancelamento):
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    if cancelamento is None:
        return subprocess.run(
            comando, capture_output=True, encoding="utf-8", errors="replace",
            check=True, creationflags=flags,
        )
    if cancelamento.is_set():
        raise ConversaoCancelada()
    with subprocess.Popen(
        comando, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        encoding="utf-8", errors="replace", creationflags=flags,
    ) as processo:
        while True:
            try:
                stdout, stderr = processo.communicate(timeout=0.1)
                break
            except subprocess.TimeoutExpired:
                if cancelamento.is_set():
                    processo.kill()
                    processo.communicate()
                    raise ConversaoCancelada() from None
        if cancelamento.is_set():
            raise ConversaoCancelada()
        if processo.returncode:
            raise subprocess.CalledProcessError(processo.returncode, comando, stdout, stderr)
        return subprocess.CompletedProcess(comando, processo.returncode, stdout, stderr)


def inspecionar_arquivo(arquivo, ffprobe, *, cancelamento=None):
    """Consulta os streams de um arquivo usando o FFprobe informado."""
    comando = [
        str(ffprobe), "-v", "error", "-protocol_whitelist", "file",
        "-show_streams", "-of", "json", str(arquivo),
    ]
    try:
        resultado = _executar(comando, cancelamento)
    except FileNotFoundError as erro:
        raise FileNotFoundError(f"FFprobe não encontrado: {ffprobe}") from erro
    except subprocess.CalledProcessError as erro:
        raise RuntimeError(f"Falha ao inspecionar {arquivo}: {erro.stderr.strip()}") from erro
    if isinstance(resultado.stderr, str) and resultado.stderr.strip():
        raise RuntimeError(f"Falha ao inspecionar {arquivo}: {resultado.stderr.strip()}")
    try:
        dados = json.loads(resultado.stdout)
    except json.JSONDecodeError as erro:
        raise ValueError("FFprobe retornou JSON inválido") from erro
    streams = dados.get("streams") if isinstance(dados, dict) else None
    if not isinstance(streams, list) or any(not isinstance(stream, dict) for stream in streams):
        raise ValueError("FFprobe retornou streams inválidos")
    return streams


def planejar_conversao(streams, categoria, formato, indices, *, catalogos=None):
    """Examina os streams explicitamente selecionados para um perfil."""
    if catalogos is None:
        catalogos = carregar_formatos()
    if formato not in catalogos.get(categoria, {}):
        raise ValueError(f"Formato desconhecido: {categoria}/{formato}")
    if not indices or len(set(indices)) != len(indices):
        raise ValueError("Informe índices de streams distintos")
    perfil = catalogos[categoria][formato]
    plano = []
    for indice in indices:
        encontrados = [stream for stream in streams if stream.get("index") == indice]
        if len(encontrados) != 1:
            raise ValueError(f"Stream não encontrado ou duplicado: {indice}")
        stream = encontrados[0]
        tipo = stream.get("codec_type")
        codec = stream.get("codec_name")
        if tipo not in perfil or not isinstance(codec, str) or not codec:
            raise ValueError(f"Stream {indice} não é compatível com o perfil ou está incompleto")
        candidato = codec in perfil[tipo]["copy"]
        plano.append({
            "index": indice,
            "tipo": tipo,
            "codec": codec,
            "candidato_copia": candidato,
            "decisao": "indefinido",
        })
    return plano


def converter(
    entrada, saida, categoria, formato, acoes, ffmpeg, ffprobe, *,
    cancelamento=None, informar_etapa=None, avisar=None, catalogos=None, selecionar_faixas=None,
):
    """Converte streams selecionados por índice, com ações 'copiar' ou 'recodificar'.

    Com acoes=None, seleciona áudio e, para saída de vídeo, vídeo sem capas.
    selecionar_faixas permite revisar os índices elegíveis antes de executar.
    A recodificação usa o primeiro encoder disponível do perfil.
    """
    entrada = Path(entrada)
    saida = Path(saida)
    if entrada.resolve() == saida.resolve():
        raise ValueError("A saída deve ser diferente da entrada")
    if saida.exists() or saida.is_symlink():
        raise FileExistsError(f"A saída já existe: {saida}")
    if catalogos is None:
        catalogos = carregar_formatos()
    perfil = catalogos.get(categoria, {}).get(formato)
    if perfil is None:
        raise ValueError(f"Formato desconhecido: {categoria}/{formato}")
    if saida.suffix.lower() != "." + perfil["extension"].lower():
        raise ValueError("A extensão da saída não corresponde ao perfil")
    if informar_etapa:
        informar_etapa("inspecao")
    streams = inspecionar_arquivo(entrada, ffprobe, cancelamento=cancelamento)
    automatico = acoes is None
    faixa_unica = categoria == "audio" and formato in PERFIS_AUDIO_FAIXA_UNICA
    restricao = (
        f"O formato {formato.upper()} aceita somente uma faixa de áudio. "
        "Selecione uma faixa ou escolha um formato que aceite várias, como MKA."
    )
    if automatico:
        elegiveis = {}
        omitidas = []
        for stream in streams:
            tipo = stream.get("codec_type")
            capa = tipo == "video" and stream.get("disposition", {}).get("attached_pic")
            if tipo == "audio" or (categoria == "video" and tipo == "video" and not capa):
                elegiveis[stream["index"]] = stream
            elif tipo != "video" or capa:
                omitidas.append("capa" if capa else tipo)
        if categoria == "video" and not any(s["codec_type"] == "video" for s in elegiveis.values()):
            raise ValueError("A entrada não contém faixa de vídeo")
        if not elegiveis:
            raise ValueError("A entrada não contém faixas de áudio")
        indices = elegiveis
        if selecionar_faixas is not None:
            revisadas = selecionar_faixas(tuple(elegiveis.values()), tuple(omitidas), faixa_unica)
            if revisadas is None:
                raise ConversaoCancelada()
            indices = dict.fromkeys(revisadas)
            if not indices or len(indices) != len(revisadas) or indices.keys() - elegiveis.keys():
                raise ValueError("Seleção de faixas inválida")
            if categoria == "video" and not any(elegiveis[i]["codec_type"] == "video" for i in indices):
                raise ValueError("Selecione pelo menos uma faixa de vídeo")
            if faixa_unica and len(indices) != 1:
                raise RuntimeError(restricao)
        acoes = dict.fromkeys(indices, "automatico")
    plano = planejar_conversao(streams, categoria, formato, list(acoes), catalogos=catalogos)

    comando = [
        str(ffmpeg), "-nostdin", "-v", "error", "-xerror", "-abort_on", "empty_output_stream",
        "-protocol_whitelist", "file", "-i", str(entrada),
    ]
    if categoria == "audio":
        comando.append("-vn")
    comando_teste = comando.copy()
    for item in plano:
        comando.extend(["-map", f"0:{item['index']}"])

    with tempfile.TemporaryDirectory(dir=saida.parent, prefix=".blackberry-") as pasta:
        pasta = Path(pasta)
        sondagem = pasta / "sondagem"
        sondagem.mkdir()
        encoders_disponiveis = None
        codecs_esperados = []
        if informar_etapa:
            informar_etapa("planejamento")
        for posicao, item in enumerate(plano):
            acao = acoes[item["index"]]
            if automatico:
                acao = "recodificar"
                if item["candidato_copia"]:
                    teste = sondagem / f"teste-{posicao}{saida.suffix}"
                    try:
                        _executar(
                            comando_teste + ["-map", f"0:{item['index']}", "-c", "copy",
                                            "-n", str(teste)],
                            cancelamento,
                        )
                    except FileNotFoundError as erro:
                        raise FileNotFoundError(f"FFmpeg não encontrado: {ffmpeg}") from erro
                    except subprocess.CalledProcessError as erro:
                        diagnostico = erro.stderr.strip()
                        mensagem = f"Cópia da faixa {item['index']} falhou. {diagnostico}"
                        # O muxer MP3 rejeita AAC mesmo quando o catálogo o indica como candidato.
                        incompatibilidade = (
                            categoria == "audio" and formato == "mp3" and item["codec"] == "aac"
                            and re.search(
                                r"^\[mp3 @ [0-9a-fA-F]+\] Invalid audio stream\. "
                                r"Exactly one MP3 audio stream is required\.$",
                                diagnostico, re.M,
                            )
                        )
                        if not incompatibilidade:
                            raise RuntimeError(mensagem) from erro
                        mensagem += "\nEste formato exige recodificação da faixa."
                        if avisar:
                            avisar(mensagem)
                        else:
                            warnings.warn(mensagem, RuntimeWarning)
                    else:
                        verificado = inspecionar_arquivo(teste, ffprobe, cancelamento=cancelamento)
                        if len(verificado) != 1 or verificado[0].get("codec_name") != item["codec"]:
                            raise RuntimeError(f"Cópia do stream {item['index']} não validada")
                        acao = "copiar"
                    finally:
                        teste.unlink(missing_ok=True)
                acoes[item["index"]] = acao
            if acao == "copiar":
                if not item["candidato_copia"]:
                    raise ValueError(f"Stream {item['index']} não é candidato à cópia")
                codec = "copy"
                codecs_esperados.append(item["codec"])
            elif acao == "recodificar":
                encoders = perfil[item["tipo"]]["encode"]
                if not encoders:
                    raise ValueError(f"Nenhum encoder no perfil para {item['tipo']}")
                if encoders_disponiveis is None:
                    try:
                        lista = _executar([str(ffmpeg), "-hide_banner", "-encoders"], cancelamento)
                    except FileNotFoundError as erro:
                        raise FileNotFoundError(f"FFmpeg não encontrado: {ffmpeg}") from erro
                    except subprocess.CalledProcessError as erro:
                        raise RuntimeError(f"Falha ao consultar encoders: {erro.stderr.strip()}") from erro
                    encoders_disponiveis = {}
                    for nome, descricao in re.findall(r"^[ \t]+[VAS][.A-Z]{5}[ \t]+(\S+)[ \t]+(.+)$",
                                                       lista.stdout, re.M):
                        alias = re.search(r"\(codec (\S+)\)$", descricao)
                        encoders_disponiveis[nome] = alias[1] if alias else nome
                codec = next((nome for nome in encoders if nome in encoders_disponiveis), None)
                if codec is None:
                    raise ValueError(f"Encoders indisponíveis para {item['tipo']}: {', '.join(encoders)}")
                codecs_esperados.append(encoders_disponiveis[codec])
            else:
                raise ValueError(f"Ação inválida para stream {item['index']}: {acao}")
            comando.extend([f"-c:{posicao}", codec])
        if faixa_unica and len(plano) != 1:
            raise RuntimeError(restricao)
        temporario = pasta / ("resultado" + saida.suffix)
        if informar_etapa:
            informar_etapa("conversao")
        try:
            _executar(comando + ["-n", str(temporario)], cancelamento)
        except FileNotFoundError as erro:
            raise FileNotFoundError(f"FFmpeg não encontrado: {ffmpeg}") from erro
        except subprocess.CalledProcessError as erro:
            raise RuntimeError(f"Falha na conversão: {erro.stderr.strip()}") from erro
        if informar_etapa:
            informar_etapa("validacao")
        if not temporario.is_file() or temporario.stat().st_size == 0:
            raise RuntimeError("O FFmpeg não gerou uma saída com conteúdo")
        resultado = inspecionar_arquivo(temporario, ffprobe, cancelamento=cancelamento)
        if len(resultado) != len(plano) or any(
            stream.get("codec_type") != item["tipo"]
            for stream, item in zip(resultado, plano)
        ):
            raise RuntimeError("A saída não contém os streams esperados")
        if [stream.get("codec_name") for stream in resultado] != codecs_esperados:
            raise RuntimeError("A saída não contém os codecs esperados")
        originais = {stream.get("index"): stream for stream in streams}
        for stream, item in zip(resultado, plano):
            if item["tipo"] != "audio":
                continue
            original = originais[item["index"]]
            canais = original.get("channels")
            if canais and stream.get("channels") != canais:
                raise RuntimeError(f"A saída alterou o número de canais da faixa {item['index']}")
            duracao_original = original.get("duration")
            duracao_saida = stream.get("duration")
            if duracao_original not in (None, "N/A") and duracao_saida not in (None, "N/A"):
                duracao_original = float(duracao_original)
                tolerancia = max(0.25, duracao_original * 0.02)
                if duracao_original > 0 and abs(float(duracao_saida) - duracao_original) > tolerancia:
                    raise RuntimeError(f"A saída alterou a duração da faixa {item['index']}")
        if cancelamento is not None and cancelamento.is_set():
            raise ConversaoCancelada()
        if os.name == "nt":
            os.rename(temporario, saida)
        else:
            os.link(temporario, saida)
    return saida
