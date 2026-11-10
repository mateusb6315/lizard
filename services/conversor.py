# implementa a lógica de conversão. decide se o arquivo será copiado ou re-encodificado, com auxílio do ffprobe e os metadados

from services.metadados import carregar_formatos
import json
import subprocess
import os
import re
import tempfile
import warnings
from pathlib import Path

formatos = carregar_formatos()


def caminhos_ferramentas(pasta_tools):
    pasta = Path(pasta_tools) / "ffmpeg"
    sufixo = ".exe" if os.name == "nt" else ""
    return pasta / f"ffmpeg{sufixo}", pasta / f"ffprobe{sufixo}"


class ConversaoCancelada(Exception):
    """A operação foi interrompida antes de publicar o resultado."""


def _executar(comando, cancelamento):
    if cancelamento is None:
        return subprocess.run(comando, capture_output=True, text=True, check=True)
    if cancelamento.is_set():
        raise ConversaoCancelada()
    with subprocess.Popen(
        comando, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
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
    comando = [str(ffprobe), "-v", "error", "-show_streams", "-of", "json", str(arquivo)]
    try:
        resultado = _executar(comando, cancelamento)
    except FileNotFoundError as erro:
        raise FileNotFoundError(f"FFprobe não encontrado: {ffprobe}") from erro
    except subprocess.CalledProcessError as erro:
        raise RuntimeError(f"Falha ao inspecionar {arquivo}: {erro.stderr.strip()}") from erro
    try:
        dados = json.loads(resultado.stdout)
    except json.JSONDecodeError as erro:
        raise ValueError("FFprobe retornou JSON inválido") from erro
    if not isinstance(dados, dict) or not isinstance(dados.get("streams"), list):
        raise ValueError("FFprobe retornou streams inválidos")
    return dados["streams"]


def planejar_conversao(streams, categoria, formato, indices):
    """Examina os streams explicitamente selecionados para um perfil."""
    if categoria not in formatos or formato not in formatos[categoria]:
        raise ValueError(f"Formato desconhecido: {categoria}/{formato}")
    if not indices or len(set(indices)) != len(indices):
        raise ValueError("Informe índices de streams distintos")
    perfil = formatos[categoria][formato]
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
    cancelamento=None, informar_etapa=None, avisar=None,
):
    """Converte streams selecionados por índice, com ações 'copiar' ou 'recodificar'.

    Com acoes=None, seleciona áudio e, para saída de vídeo, vídeo sem capas.
    A recodificação usa o primeiro encoder disponível do perfil.
    """
    entrada = Path(entrada)
    saida = Path(saida)
    if entrada.resolve() == saida.resolve():
        raise ValueError("A saída deve ser diferente da entrada")
    if saida.exists():
        raise FileExistsError(f"A saída já existe: {saida}")
    if informar_etapa:
        informar_etapa("inspecao")
    streams = inspecionar_arquivo(entrada, ffprobe, cancelamento=cancelamento)
    automatico = acoes is None
    if automatico:
        acoes = {}
        tem_video = False
        for stream in streams:
            tipo = stream.get("codec_type")
            if categoria == "video" and tipo == "video":
                if stream.get("disposition", {}).get("attached_pic"):
                    continue
                tem_video = True
            elif tipo != "audio":
                continue
            acoes[stream["index"]] = "automatico"
        if categoria == "video" and not tem_video:
            raise ValueError("A entrada não contém faixa de vídeo")
        if not acoes:
            raise ValueError("A entrada não contém faixas de áudio")
    plano = planejar_conversao(streams, categoria, formato, list(acoes))
    perfil = formatos[categoria][formato]
    if saida.suffix.lower() != "." + perfil["extension"].lower():
        raise ValueError("A extensão da saída não corresponde ao perfil")

    comando = [str(ffmpeg), "-nostdin", "-v", "error", "-i", str(entrada)]
    if categoria == "audio":
        comando.append("-vn")
    comando_teste = comando.copy()
    for item in plano:
        comando.extend(["-map", f"0:{item['index']}"])

    with tempfile.TemporaryDirectory(dir=saida.parent, prefix=".blackberry-") as pasta:
        encoders_disponiveis = None
        if informar_etapa:
            informar_etapa("planejamento")
        for posicao, item in enumerate(plano):
            acao = acoes[item["index"]]
            if automatico:
                acao = "recodificar"
                if item["candidato_copia"]:
                    teste = Path(pasta) / f"teste-{posicao}{saida.suffix}"
                    try:
                        _executar(
                            comando_teste + ["-map", f"0:{item['index']}", "-c", "copy",
                                            "-n", str(teste)],
                            cancelamento,
                        )
                    except FileNotFoundError as erro:
                        raise FileNotFoundError(f"FFmpeg não encontrado: {ffmpeg}") from erro
                    except subprocess.CalledProcessError as erro:
                        mensagem = f"Cópia da faixa {item['index']} falhou. {erro.stderr.strip()}"
                        if categoria == "video":
                            raise RuntimeError(mensagem) from erro
                        mensagem += "\nA faixa será recodificada."
                        if avisar:
                            avisar(mensagem)
                        else:
                            warnings.warn(mensagem, RuntimeWarning)
                    else:
                        verificado = inspecionar_arquivo(teste, ffprobe, cancelamento=cancelamento)
                        if len(verificado) != 1 or verificado[0].get("codec_name") != item["codec"]:
                            raise RuntimeError(f"Cópia do stream {item['index']} não validada")
                        acao = "copiar"
                        teste.unlink()
                acoes[item["index"]] = acao
            if acao == "copiar":
                if not item["candidato_copia"]:
                    raise ValueError(f"Stream {item['index']} não é candidato à cópia")
                codec = "copy"
            elif acao == "recodificar":
                encoders = perfil[item["tipo"]]["encode"]
                if not encoders:
                    raise ValueError(f"Nenhum encoder no perfil para {item['tipo']}")
                if encoders_disponiveis is None:
                    try:
                        lista = _executar([str(ffmpeg), "-hide_banner", "-encoders"], cancelamento)
                    except subprocess.CalledProcessError as erro:
                        raise RuntimeError(f"Falha ao consultar encoders: {erro.stderr.strip()}") from erro
                    encoders_disponiveis = set(re.findall(r"^\s+[VAS][.A-Z]{5}\s+(\S+)", lista.stdout, re.M))
                codec = next((nome for nome in encoders if nome in encoders_disponiveis), None)
                if codec is None:
                    raise ValueError(f"Encoders indisponíveis para {item['tipo']}: {', '.join(encoders)}")
            else:
                raise ValueError(f"Ação inválida para stream {item['index']}: {acao}")
            comando.extend([f"-c:{posicao}", codec])
        temporario = Path(pasta) / saida.name
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
        resultado = inspecionar_arquivo(temporario, ffprobe, cancelamento=cancelamento)
        if len(resultado) != len(plano) or any(
            stream.get("codec_type") != item["tipo"]
            for stream, item in zip(resultado, plano)
        ):
            raise RuntimeError("A saída não contém os streams esperados")
        if any(
            acoes[item["index"]] == "copiar" and stream.get("codec_name") != item["codec"]
            for stream, item in zip(resultado, plano)
        ):
            raise RuntimeError("A saída não preservou os codecs copiados")
        if cancelamento is not None and cancelamento.is_set():
            raise ConversaoCancelada()
        if os.name == "nt":
            os.rename(temporario, saida)
        else:
            os.link(temporario, saida)
    return saida
