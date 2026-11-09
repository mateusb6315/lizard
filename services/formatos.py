# recupera os metadados dos formatos e fornece para conversor.py

import json
from pathlib import Path

METADADOS = Path(__file__).resolve().parent.parent / "data" / "formatos"


def carregar_formatos():
    """Carrega os catálogos nas chaves 'video' e 'audio'."""
    formatos = {}
    for categoria, blocos in (("video", ("video", "audio")), ("audio", ("audio",))):
        caminho = METADADOS / f"{categoria}.json"
        try:
            with caminho.open(encoding="utf-8") as arquivo:
                catalogo = json.load(arquivo)
        except FileNotFoundError as erro:
            raise FileNotFoundError(f"Catálogo de formatos ausente: {caminho}") from erro
        except json.JSONDecodeError as erro:
            raise ValueError(
                f"{caminho}: JSON inválido na linha {erro.lineno}, coluna {erro.colno}"
            ) from erro
        except UnicodeDecodeError as erro:
            raise ValueError(f"{caminho}: conteúdo inválido em UTF-8") from erro

        _validar_catalogo(catalogo, caminho, blocos)
        formatos[categoria] = catalogo
    return formatos


def _validar_catalogo(catalogo, caminho, blocos):
    if not isinstance(catalogo, dict) or not catalogo:
        raise ValueError(f"{caminho}: esperado um objeto com pelo menos um formato")

    for nome, perfil in catalogo.items():
        local = f"{caminho} [{nome}]"
        if not isinstance(perfil, dict):
            raise ValueError(f"{local}: esperado um objeto de formato")
        extensao = perfil.get("extension")
        if not isinstance(extensao, str) or not extensao.strip():
            raise ValueError(f"{local}.extension: esperado um texto não vazio")

        for bloco in blocos:
            dados = perfil.get(bloco)
            if not isinstance(dados, dict):
                raise ValueError(f"{local}.{bloco}: esperado um objeto")
            for campo in ("copy", "encode", "args"):
                if campo == "args" and campo not in dados:
                    continue
                valores = dados.get(campo)
                if not isinstance(valores, list) or not all(
                    isinstance(valor, str) for valor in valores
                ):
                    raise ValueError(
                        f"{local}.{bloco}.{campo}: esperada uma lista de textos"
                    )
