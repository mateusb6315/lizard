"""Gera um pacote beta local e separado do canal release."""

import sys

from compilar import main


if __name__ == "__main__":
    sys.exit(main("beta"))
