# implementa a lógica de conversão. decide se o arquivo será copiado ou re-encodificado, com auxílio do ffprobe e os metadados

from services.formatos import carregar_formatos
import json
import subprocess

formatos = carregar_formatos()


def inspecionar_arquivo(arquivo, ffprobe):
    """Consulta os streams de um arquivo usando o FFprobe informado."""
    comando = [str(ffprobe), "-v", "error", "-show_streams", "-of", "json", str(arquivo)]
    try:
        resultado = subprocess.run(comando, capture_output=True, text=True, check=True)
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
