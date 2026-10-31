"""Instala os modelos faciais oficiais com verificação de integridade."""
from pathlib import Path
import sys

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))

from app.main import ModeloFacialIndisponivel, preparar_modelos


def main():
    try:
        preparar_modelos(mostrar_progresso=True)
    except ModeloFacialIndisponivel as exc:
        raise SystemExit(str(exc)) from None
    print('Modelos faciais preparados e verificados.')


if __name__ == '__main__':
    main()
