# implementa a lógica de conversão. decide se o arquivo será copiado ou re-encodificado, com auxílio do ffprobe e os metadados

from services.metadados import carregar_formatos
import json
import logging
import math
import subprocess
import os
import re
import tempfile
import warnings
from fractions import Fraction
from pathlib import Path

LOG = logging.getLogger("lizard")
PERFIS_AUDIO_FAIXA_UNICA = frozenset({"mp3", "wav", "flac", "aac", "aiff", "ac3", "mp2", "wv", "caf"})
PERFIS_COM_FAIXA_DE_CAPITULOS = frozenset({"mp4", "mov", "m4a", "m4v", "3gp"})
ERRO_INICIO_H264 = re.compile(
    r"\[h264 @ [0-9a-fA-F]+\] (?:non-existing PPS \d+ referenced|sps_id \d+ out of range"
    r"|decode_slice_header error|no frame!)"
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
ERRO_DECODER_LATM = re.compile(
    r"\[aist#0:(\d+)/aac_latm @ [0-9a-fA-F]+\] \[dec:aac_latm @ [0-9a-fA-F]+\] "
    r"(?:Error submitting packet to decoder|Error processing packet in decoder|"
    r"Task finished with error|Terminating thread with error): Invalid data found when processing input"
)
PACOTE_CORROMPIDO_TS = re.compile(
    r"^\[in#0/mpegts @ [0-9a-fA-F]+\] Packet corrupt \(stream = (\d+), dts = (-?\d+)\)\.$",
    re.M,
)
PERDA_MAXIMA_TS = 1.0
# A leitura adiantada do decoder pode alcançar um pacote defeituoso antes do fim solicitado.
MARGEM_CORTE_TS = 0.20
TOLERANCIA_TIMESTAMPS_TS = 0.12


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


def _diagnostico_inicio_h264(diagnostico):
    return "non-existing PPS" in diagnostico and all(
        ERRO_INICIO_H264.fullmatch(linha.strip()) for linha in diagnostico.splitlines()
    )


def _video_real(stream):
    return stream.get("codec_type") == "video" and not stream.get("disposition", {}).get("attached_pic")


def inspecionar_arquivo(
    arquivo, ffprobe, *, cancelamento=None, detalhes=False, recuperar_inicio_ts=False, estimar_duracao=False,
):
    """Consulta os streams e, opcionalmente, os metadados necessários à validação."""
    comando = [
        str(ffprobe), "-v", "error", "-protocol_whitelist", "file",
        "-show_streams",
    ]
    if detalhes and not estimar_duracao:
        comando.extend(["-skip_estimate_duration_from_pts", "1"])
    if detalhes or recuperar_inicio_ts:
        comando.append("-show_format")
    if detalhes:
        comando.append("-show_chapters")
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
        metadados = dados.get("format")
        inicio_recuperavel = (
            recuperar_inicio_ts and isinstance(metadados, dict) and metadados.get("format_name") == "mpegts"
            and _diagnostico_inicio_h264(diagnostico)
            and any(
                _video_real(s) and s.get("codec_name") == "h264"
                and all(type(s.get(campo)) is int and s[campo] > 0 for campo in ("width", "height", "extradata_size"))
                for s in streams
            )
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
    return _planejar_faixas(_indexar_streams(streams), categoria, catalogos[categoria][formato], indices)


def _indexar_streams(streams):
    originais = {}
    for stream in streams:
        indice = stream.get("index")
        if type(indice) is not int or indice < 0 or indice in originais:
            raise ValueError(f"Índice de stream ausente, inválido ou duplicado: {indice}")
        originais[indice] = stream
    return originais


def _planejar_faixas(originais, categoria, perfil, indices):
    if (not indices or any(type(indice) is not int for indice in indices)
            or len(set(indices)) != len(indices)):
        raise ValueError("Informe índices de streams distintos")
    plano = []
    for indice in indices:
        stream = originais.get(indice)
        if stream is None:
            raise ValueError(f"Stream não encontrado: {indice}")
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
    if categoria == "video" and not any(_video_real(originais[indice]) for indice in indices):
        raise ValueError("Selecione pelo menos uma faixa de vídeo")
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


def _tempo(valor):
    try:
        segundos = float(valor)
    except (TypeError, ValueError):
        return None
    return segundos if math.isfinite(segundos) else None


def _confirmar_fim_latm(entrada, ffmpeg, ffprobe, erro, faixas_latm, diagnostico_inicio, cancelamento):
    linhas_latm = [
        linha.strip() for linha in erro.stderr.strip().splitlines()
        if not (diagnostico_inicio and ERRO_INICIO_H264.fullmatch(linha.strip()))
    ]
    erros_latm = [ERRO_DECODER_LATM.fullmatch(linha) for linha in linhas_latm]
    if not erros_latm or not all(erros_latm):
        return None
    faixas = {int(linha[1]) for linha in erros_latm}
    if not faixas <= faixas_latm:
        return None

    origem = inspecionar_arquivo(
        entrada, ffprobe, cancelamento=cancelamento, detalhes=True, recuperar_inicio_ts=True, estimar_duracao=True,
    )
    formato = origem.get("format", {})
    inicio = _tempo(formato.get("start_time"))
    duracao = _tempo(formato.get("duration"))
    if formato.get("format_name") != "mpegts" or inicio is None or duracao is None or duracao <= PERDA_MAXIMA_TS:
        return None
    limite = duracao - PERDA_MAXIMA_TS
    progresso = re.findall(r"^out_time_us=(\d+)$", erro.stdout or "", re.M)
    if not progresso or not limite <= int(progresso[-1]) / 1_000_000 <= duracao + TOLERANCIA_TIMESTAMPS_TS:
        return None

    originais = _indexar_streams(origem["streams"])
    posicoes = {}
    # A busca serve somente para reproduzir o erro. A posição vem do DTS do pacote, não do progresso.
    for indice in sorted(faixas_latm):
        if originais.get(indice, {}).get("codec_name") != "aac_latm":
            return None
        try:
            base = Fraction(originais[indice]["time_base"])
        except (KeyError, TypeError, ValueError, ZeroDivisionError):
            return None
        try:
            _executar([
                str(ffmpeg), "-nostdin", "-v", "warning", "-xerror", "-ss", f"{limite:.6f}",
                "-protocol_whitelist", "file", "-i", str(entrada),
                "-map", f"0:{indice}", "-f", "null", "-",
            ], cancelamento)
        except subprocess.CalledProcessError as falha:
            linhas = falha.stderr.splitlines()
            if not any(
                (latm := ERRO_DECODER_LATM.fullmatch(linha.strip())) and int(latm[1]) == indice
                for linha in linhas
            ):
                return None
            pacotes = [
                float(int(dts) * base) - inicio
                for faixa, dts in PACOTE_CORROMPIDO_TS.findall(falha.stderr) if int(faixa) == indice
            ]
            if not pacotes or any(not limite <= posicao <= duracao for posicao in pacotes):
                return None
            posicoes[indice] = min(pacotes)
    if not faixas <= posicoes.keys():
        return None
    corte = round(min(posicoes.values()) - MARGEM_CORTE_TS, 6)
    if corte < limite:
        return None
    LOG.warning(
        "Falha LATM em %s. Progresso de saída %.3f s. DTS relativo por faixa %s. "
        "Nova tentativa de 0 a %.6f s de %.6f s estimados.\n%s",
        entrada, int(progresso[-1]) / 1_000_000, posicoes, corte, duracao, "\n".join(linhas_latm),
    )
    return origem, corte


def _primeiro_quadro_h264(entrada, ffprobe, indice, cancelamento):
    try:
        resultado = _executar([
            str(ffprobe), "-v", "error", "-protocol_whitelist", "file", "-select_streams", str(indice),
            "-skip_frame", "nokey", "-read_intervals", "%+5",
            "-show_entries", "frame=best_effort_timestamp_time", "-of", "json", str(entrada),
        ], cancelamento)
    except subprocess.CalledProcessError as erro:
        raise RuntimeError(f"Falha ao confirmar o início do vídeo: {erro.stderr.strip()}") from erro
    if resultado.stderr.strip() and not _diagnostico_inicio_h264(resultado.stderr.strip()):
        raise RuntimeError(f"Falha ao confirmar o início do vídeo: {resultado.stderr.strip()}")
    quadros = json.loads(resultado.stdout).get("frames", [])
    tempos = [_tempo(quadro.get("best_effort_timestamp_time")) for quadro in quadros]
    return min((tempo for tempo in tempos if tempo is not None), default=None)


def _validar_tempos_recuperados(entrada, ffprobe, origem, corte, plano, resultado, cancelamento):
    originais = _indexar_streams(origem["streams"])
    inicio = float(origem["format"]["start_time"])
    duracao = float(origem["format"]["duration"])
    fins = []
    for item, stream in zip(plano, resultado):
        indice = item["index"]
        original = originais[indice]
        inicio_original = _tempo(original.get("start_time"))
        duracao_original = _tempo(original.get("duration"))
        inicio_saida = _tempo(stream.get("start_time"))
        duracao_saida = _tempo(stream.get("duration"))
        if (None in (inicio_original, duracao_original, inicio_saida, duracao_saida)
                or duracao_original <= 0 or duracao_saida <= 0):
            raise RuntimeError(f"Não foi possível verificar os limites da faixa {indice} recuperada")
        inicio_esperado = inicio_original
        if origem.get("diagnostico_inicio_ts") and item["codec"] == "h264":
            inicio_esperado = _primeiro_quadro_h264(entrada, ffprobe, indice, cancelamento)
            if inicio_esperado is None:
                raise RuntimeError(f"Não foi possível localizar o primeiro quadro recuperável da faixa {indice}")
        fim_original = inicio_original - inicio + duracao_original
        fim_esperado = min(corte, fim_original)
        fim_saida = inicio_saida + duracao_saida
        if (abs(inicio_saida - (inicio_esperado - inicio)) > TOLERANCIA_TIMESTAMPS_TS
                or abs(fim_saida - fim_esperado) > TOLERANCIA_TIMESTAMPS_TS
                or fim_original - fim_saida > PERDA_MAXIMA_TS):
            raise RuntimeError(f"A recuperação alterou os limites ou o sincronismo da faixa {indice}")
        fins.append(fim_saida)
    perda = duracao - max(fins)
    if not 0 <= perda <= PERDA_MAXIMA_TS:
        raise RuntimeError("A duração recuperada ficou fora do limite de perda aprovado")
    return perda


def _decodificar_saida(arquivo, ffmpeg, cancelamento, *, somente_video):
    mapas = ["-map", "0:v"] if somente_video else ["-map", "0:v?", "-map", "0:a?"]
    try:
        resultado = _executar([
            str(ffmpeg), "-nostdin", "-v", "error", "-xerror", "-abort_on", "empty_output_stream",
            "-err_detect", "explode", "-protocol_whitelist", "file",
            "-i", str(arquivo), *mapas, "-f", "null", "-",
        ], cancelamento)
    except subprocess.CalledProcessError as erro:
        raise RuntimeError(f"Falha ao decodificar a saída recuperada: {erro.stderr.strip()}") from erro
    if resultado.stderr.strip():
        raise RuntimeError(f"Falha ao decodificar a saída recuperada: {resultado.stderr.strip()}")


def converter(
    entrada, saida, categoria, formato, acoes, ffmpeg, ffprobe, *,
    cancelamento=None, informar_etapa=None, avisar=None, catalogos=None, selecionar_faixas=None,
    avisar_inicio_ts=None, avisar_fim_ts=None,
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
    originais = _indexar_streams(inspecao["streams"])
    automatico = acoes is None
    faixa_unica = categoria == "audio" and formato in PERFIS_AUDIO_FAIXA_UNICA
    restricao = (
        f"O formato {formato.upper()} aceita somente uma faixa de áudio. "
        "Selecione uma faixa ou escolha um formato que aceite várias, como MKA."
    )
    if automatico:
        elegiveis = {}
        omitidas = []
        for indice, stream in originais.items():
            tipo = stream.get("codec_type")
            capa = tipo == "video" and not _video_real(stream)
            if tipo == "audio" or (categoria == "video" and _video_real(stream)):
                elegiveis[indice] = stream
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
            if faixa_unica and len(indices) != 1:
                raise RuntimeError(restricao)
        acoes = dict.fromkeys(indices, "automatico")
    plano = _planejar_faixas(originais, categoria, perfil, list(acoes))

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
        recuperacao = None
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
            faixas_latm = {
                item["index"] for item in plano if item["codec"] == "aac_latm" and item["decisao"] == "recodificar"
            } if inspecao.get("format", {}).get("format_name") == "mpegts" else set()
            if faixas_latm:
                argumentos.extend(["-progress", "pipe:1"])
            try:
                _executar(argumentos + ["-n", str(temporario)], cancelamento)
            except FileNotFoundError as erro:
                raise FileNotFoundError(f"FFmpeg não encontrado: {ffmpeg}") from erro
            except subprocess.CalledProcessError as erro:
                diagnostico = erro.stderr.strip()
                if faixas_latm:
                    recuperacao = _confirmar_fim_latm(
                        entrada, ffmpeg, ffprobe, erro, faixas_latm, inspecao.get("diagnostico_inicio_ts"), cancelamento,
                    )
                if recuperacao is not None:
                    _, corte = recuperacao
                    temporario.unlink(missing_ok=True)
                    temporario = pasta / ("recuperado" + saida.suffix)
                    try:
                        tentativa = _executar(argumentos + ["-t", f"{corte:.6f}", "-n", str(temporario)], cancelamento)
                    except subprocess.CalledProcessError as nova_falha:
                        raise RuntimeError(f"Falha ao recuperar o fim do TS: {nova_falha.stderr.strip()}") from nova_falha
                    restante = tentativa.stderr.strip()
                    if restante and not (
                        inspecao.get("diagnostico_inicio_ts") and _diagnostico_inicio_h264(restante)
                    ):
                        raise RuntimeError(f"Falha ao recuperar o fim do TS: {restante}")
                    break
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
        video_recuperado = diagnostico_inicio and any(item["tipo"] == "video" for item in plano)
        if recuperacao is not None:
            origem, corte = recuperacao
            perda = _validar_tempos_recuperados(entrada, ffprobe, origem, corte, plano, resultado, cancelamento)
            _decodificar_saida(temporario, ffmpeg, cancelamento, somente_video=False)
            if avisar_fim_ts:
                avisar_fim_ts(perda)
            else:
                warnings.warn(
                    f"Os últimos {perda:.2f} s estimados do MPEG-TS foram omitidos na recuperação.",
                    RuntimeWarning,
                )
        elif video_recuperado:
            _decodificar_saida(temporario, ffmpeg, cancelamento, somente_video=True)
        if video_recuperado:
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
    if recuperacao is not None:
        LOG.warning("Recuperação LATM validada e publicada em %s. Perda final estimada %.3f s.", saida, perda)
    return saida
