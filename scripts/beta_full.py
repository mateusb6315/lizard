"""Compila o canal beta e compacta o pacote publicado."""

import sys

from compilar import main
from finalizacao import finalizar


if __name__ == "__main__":
    sys.exit(main("beta", apos_compilacao=finalizar))
