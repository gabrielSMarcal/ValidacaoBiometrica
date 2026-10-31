"""2. Pré-processamento: suavização binomial e luminância da captura."""
from __future__ import annotations
import numpy as np
from .sensoriamento import BiometriaErro


def pre_processamento(rgb: np.ndarray) -> dict[str, np.ndarray]:
    """
    2. Pré-processamento: gera RGB suavizado e luminância para qualidade.
    """

    if not isinstance(rgb, np.ndarray) or rgb.ndim != 3 or rgb.shape[2] != 3:
        raise BiometriaErro("O pré-processamento requer uma matriz RGB.")

    if rgb.dtype != np.uint8 or rgb.shape[0] < 3 or rgb.shape[1] < 3:
        raise BiometriaErro("A matriz RGB deve conter pixels uint8 válidos.")

    imagem = rgb.astype(np.float32)
    bordas = np.pad(imagem, ((0, 0), (1, 1), (0, 0)), mode="reflect")
    horizontal = (bordas[:, :-2] + 2 * bordas[:, 1:-1] + bordas[:, 2:]) / 4
    bordas = np.pad(horizontal, ((1, 1), (0, 0), (0, 0)), mode="reflect")
    suavizada = (bordas[:-2] + 2 * bordas[1:-1] + bordas[2:]) / 4
    cinza = suavizada @ np.array([0.299, 0.587, 0.114], np.float32)

    return {"rgb": imagem, "cinza": cinza}
