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
PERFIS_COM_FAIXA_DE_CAPITULOS = frozenset({"mp4", "mov", "m4a", "m4v", "3gp"})
ERRO_INICIO_H264 = re.compile(
    r"\[h264 @ [0-9a-fA-F]+\] (?:non-existing PPS \d+ referenced|decode_slice_header error|no frame!)"
    r"|Last message repeated \d+ times?"
)
ERRO_MUXER = re.compile(
    r"^\[(?:mp4|mov|ipod|3gp|matroska|webm|avi|flv|mpegts|vob|mpeg) @ [0-9a-fA-F]+\] "
    r"(?:Application provided invalid, non monotonically increasing dts to muxer in stream (\d+):[^\n]+"
    r"|pts \([^\n)]+\) < dts \([^\n)]+\) in stream (\d+)"
    r"|Application provided duration: -?\d+ in stream (\d+) is invalid"
    r"|Could not find tag for codec [\w-]+ in stream #(\d+), codec not currently supported in container"
    r"|Can't write packet with unknown timestamp)$"
    r"|^\[[av]ost#0:(\d+)/copy @ [0-9a-fA-F]+\] "
    r"Non-monotonic DTS; previous: -?\d+, current: -?\d+;",
    re.M,
)
ERRO_MP3 = re.compile(
    r"^\[mp3 @ [0-9a-fA-F]+\] Invalid audio stream\. Exactly one MP3 audio stream is required\.$",
    re.M,
)
ERRO_DE_LEITURA_OU_GRAVACAO = re.compile(
    r"No space left|Permission denied|Input/output error|Error reading|Error opening input|Packet corrupt"
    r"|Invalid data found|No such file|Read-only file system",
    re.I,
)


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


def inspecionar_arquivo(arquivo, ffprobe, *, cancelamento=None, detalhes=False, recuperar_inicio_ts=False):
    """Consulta os streams e, opcionalmente, os metadados necessários à validação."""
    comando = [
        str(ffprobe), "-v", "error", "-protocol_whitelist", "file",
        "-show_streams",
    ]
    if detalhes:
        comando.extend(["-skip_estimate_duration_from_pts", "1", "-show_format", "-show_chapters"])
    comando.extend(["-of", "json", str(arquivo)])
    try:
        resultado = _executar(comando, cancelamento)
    except FileNotFoundError as erro:
        raise FileNotFoundError(f"FFprobe não encontrado: {ffprobe}") from erro
    except subprocess.CalledProcessError as erro:
        raise RuntimeError(f"Falha ao inspecionar {arquivo}: {erro.stderr.strip()}") from erro
    diagnostico = resultado.stderr.strip() if isinstance(resultado.stderr, str) else ""
    try:
        dados = json.loads(resultado.stdout)
    except json.JSONDecodeError as erro:
        raise ValueError("FFprobe retornou JSON inválido") from erro
    streams = dados.get("streams") if isinstance(dados, dict) else None
    if not isinstance(streams, list) or any(not isinstance(stream, dict) for stream in streams):
        raise ValueError("FFprobe retornou streams inválidos")
    if diagnostico:
        formato = dados.get("format", {}).get("format_name")
        inicio_recuperavel = (
            recuperar_inicio_ts and formato == "mpegts"
            and "non-existing PPS" in diagnostico
            and all(ERRO_INICIO_H264.fullmatch(linha.strip()) for linha in diagnostico.splitlines())
            and any(s.get("codec_name") == "h264" and s.get("width") and s.get("height") for s in streams)
        )
        if not inicio_recuperavel:
            raise RuntimeError(f"Falha ao inspecionar {arquivo}: {diagnostico}")
        dados["diagnostico_inicio_ts"] = diagnostico
    return dados if detalhes else streams


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


def _rejeicao_de_copia(diagnostico):
    if ERRO_DE_LEITURA_OU_GRAVACAO.search(diagnostico):
        return False, None
    rejeicoes = ERRO_MUXER.findall(diagnostico)
    indices = {int(indice) for rejeicao in rejeicoes for indice in rejeicao if indice}
    indice = next(iter(indices)) if len(indices) == 1 and all(any(r) for r in rejeicoes) else None
    return bool(rejeicoes) and len(indices) <= 1, indice


def _avisar_recodificacao(mensagem, avisar):
    mensagem += "\nEste formato exige recodificação da faixa."
    if avisar:
        avisar(mensagem)
    else:
        warnings.warn(mensagem, RuntimeWarning)


def _consultar_encoders(ffmpeg, cancelamento):
    try:
        lista = _executar([str(ffmpeg), "-hide_banner", "-encoders"], cancelamento)
    except FileNotFoundError as erro:
        raise FileNotFoundError(f"FFmpeg não encontrado: {ffmpeg}") from erro
    except subprocess.CalledProcessError as erro:
        raise RuntimeError(f"Falha ao consultar encoders: {erro.stderr.strip()}") from erro
    encoders = {}
    linhas = re.findall(r"^[ \t]+[VAS][.A-Z]{5}[ \t]+(\S+)[ \t]+(.+)$", lista.stdout, re.M)
    for nome, descricao in linhas:
        alias = re.search(r"\(codec (\S+)\)$", descricao)
        encoders[nome] = alias[1] if alias else nome
    return encoders


def converter(
    entrada, saida, categoria, formato, acoes, ffmpeg, ffprobe, *,
    cancelamento=None, informar_etapa=None, avisar=None, catalogos=None, selecionar_faixas=None,
    avisar_inicio_ts=None,
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
    inspecao = inspecionar_arquivo(
        entrada, ffprobe, cancelamento=cancelamento, detalhes=True, recuperar_inicio_ts=True,
    )
    streams = inspecao["streams"]
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
    originais = {stream.get("index"): stream for stream in streams}

    comando = [
        str(ffmpeg), "-nostdin", "-v", "error", "-xerror", "-abort_on", "empty_output_stream",
        "-protocol_whitelist", "file", "-i", str(entrada),
    ]
    if categoria == "audio":
        comando.append("-vn")
    with tempfile.TemporaryDirectory(dir=saida.parent, prefix=".blackberry-") as pasta:
        pasta = Path(pasta)
        sondagem = pasta / "sondagem"
        sondagem.mkdir()
        encoders_disponiveis = None
        filtros_copia = {}
        if informar_etapa:
            informar_etapa("planejamento")
        for posicao, item in enumerate(plano):
            indice = item["index"]
            acao = acoes[indice]
            if (categoria == "video" and formato == "avi" and item["codec"] == "h264"
                    and originais[indice].get("is_avc") in (True, "true")):
                filtros_copia[indice] = "h264_mp4toannexb"
            if automatico:
                acao = "recodificar"
                if item["candidato_copia"]:
                    teste = sondagem / f"teste-{posicao}{saida.suffix}"
                    argumentos = ["-map", f"0:{indice}", "-map_chapters", "-1", "-c", "copy"]
                    if indice in filtros_copia:
                        argumentos.extend(["-bsf:0", filtros_copia[indice]])
                    try:
                        _executar(comando + argumentos + ["-n", str(teste)], cancelamento)
                    except FileNotFoundError as erro:
                        raise FileNotFoundError(f"FFmpeg não encontrado: {ffmpeg}") from erro
                    except subprocess.CalledProcessError as erro:
                        diagnostico = erro.stderr.strip()
                        mensagem = f"Cópia da faixa {indice} falhou. {diagnostico}"
                        rejeitou, faixa = _rejeicao_de_copia(diagnostico)
                        rejeitou_aac = (
                            categoria == "audio" and formato == "mp3" and item["codec"] == "aac"
                            and ERRO_MP3.search(diagnostico) and not ERRO_DE_LEITURA_OU_GRAVACAO.search(diagnostico)
                        )
                        if not rejeitou_aac and not (rejeitou and faixa in (None, 0)):
                            raise RuntimeError(mensagem) from erro
                        _avisar_recodificacao(mensagem, avisar)
                    else:
                        verificado = inspecionar_arquivo(teste, ffprobe, cancelamento=cancelamento)
                        if len(verificado) != 1 or (
                            verificado[0].get("codec_type"), verificado[0].get("codec_name")
                        ) != (item["tipo"], item["codec"]):
                            raise RuntimeError(f"Cópia do stream {indice} não validada")
                        acao = "copiar"
                    finally:
                        teste.unlink(missing_ok=True)
            item["decisao"] = acao
        if faixa_unica and len(plano) != 1:
            raise RuntimeError(restricao)
        temporario = pasta / ("resultado" + saida.suffix)
        if informar_etapa:
            informar_etapa("conversao")
        while True:
            argumentos = comando.copy()
            codecs_esperados = []
            for posicao, item in enumerate(plano):
                indice = item["index"]
                argumentos.extend(["-map", f"0:{indice}"])
                acao = item["decisao"]
                if acao == "copiar":
                    if not item["candidato_copia"]:
                        raise ValueError(f"Stream {indice} não é candidato à cópia")
                    argumentos.extend([f"-c:{posicao}", "copy"])
                    if indice in filtros_copia:
                        argumentos.extend([f"-bsf:{posicao}", filtros_copia[indice]])
                    codecs_esperados.append(item["codec"])
                elif acao == "recodificar":
                    encoders = perfil[item["tipo"]]["encode"]
                    if not encoders:
                        raise ValueError(f"Nenhum encoder no perfil para {item['tipo']}")
                    if encoders_disponiveis is None:
                        encoders_disponiveis = _consultar_encoders(ffmpeg, cancelamento)
                    codec = next((nome for nome in encoders if nome in encoders_disponiveis), None)
                    if codec is None:
                        raise ValueError(f"Encoders indisponíveis para {item['tipo']}: {', '.join(encoders)}")
                    argumentos.extend([f"-c:{posicao}", codec])
                    codecs_esperados.append(encoders_disponiveis[codec])
                else:
                    raise ValueError(f"Ação inválida para stream {indice}: {acao}")
            try:
                _executar(argumentos + ["-n", str(temporario)], cancelamento)
            except FileNotFoundError as erro:
                raise FileNotFoundError(f"FFmpeg não encontrado: {ffmpeg}") from erro
            except subprocess.CalledProcessError as erro:
                diagnostico = erro.stderr.strip()
                rejeitou, posicao = _rejeicao_de_copia(diagnostico)
                if (not automatico or not rejeitou or posicao is None or posicao >= len(plano)
                        or plano[posicao]["decisao"] != "copiar"):
                    raise RuntimeError(f"Falha na conversão: {diagnostico}") from erro
                item = plano[posicao]
                item["decisao"] = "recodificar"
                temporario.unlink(missing_ok=True)
                _avisar_recodificacao(f"Cópia da faixa {item['index']} falhou. {diagnostico}", avisar)
            else:
                break
        if informar_etapa:
            informar_etapa("validacao")
        if not temporario.is_file() or temporario.stat().st_size == 0:
            raise RuntimeError("O FFmpeg não gerou uma saída com conteúdo")
        dados_saida = inspecionar_arquivo(temporario, ffprobe, cancelamento=cancelamento, detalhes=True)
        resultado = dados_saida["streams"]
        if formato in PERFIS_COM_FAIXA_DE_CAPITULOS and dados_saida.get("chapters"):
            # O muxer MOV/MP4 pode criar uma faixa de texto para os capítulos mapeados por padrão.
            resultado = [
                stream for stream in resultado
                if (stream.get("codec_type"), stream.get("codec_name"), stream.get("codec_tag_string"))
                != ("data", "bin_data", "text")
            ]
        if len(resultado) != len(plano) or any(
            stream.get("codec_type") != item["tipo"]
            for stream, item in zip(resultado, plano)
        ):
            raise RuntimeError("A saída não contém os streams esperados")
        if [stream.get("codec_name") for stream in resultado] != codecs_esperados:
            raise RuntimeError("A saída não contém os codecs esperados")
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
        diagnostico_inicio = inspecao.get("diagnostico_inicio_ts")
        if diagnostico_inicio and any(item["tipo"] == "video" for item in plano):
            try:
                decodificacao = _executar([
                    str(ffmpeg), "-nostdin", "-v", "error", "-xerror", "-protocol_whitelist", "file",
                    "-i", str(temporario), "-map", "0:v", "-f", "null", "-",
                ], cancelamento)
            except subprocess.CalledProcessError as erro:
                raise RuntimeError(f"Falha ao decodificar o vídeo recuperado: {erro.stderr.strip()}") from erro
            if decodificacao.stderr.strip():
                raise RuntimeError(f"Falha ao decodificar o vídeo recuperado: {decodificacao.stderr.strip()}")
            if avisar_inicio_ts:
                avisar_inicio_ts(diagnostico_inicio)
            else:
                warnings.warn("O vídeo convertido começa no primeiro quadro recuperável.", RuntimeWarning)
        if cancelamento is not None and cancelamento.is_set():
            raise ConversaoCancelada()
        if os.name == "nt":
            os.rename(temporario, saida)
        else:
            os.link(temporario, saida)
    return saida
