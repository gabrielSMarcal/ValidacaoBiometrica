"""2. Pré-processamento: qualidade da captura e normalização fotométrica facial."""
from __future__ import annotations
import numpy as np
from .sensoriamento import BiometriaErro, BiometriaIndisponivel


_LUMINANCIA_ALVO = 128 / 255
_GAMMA_MINIMO = 0.6
_GAMMA_MAXIMO = 1.8


def pre_processamento(rgb: np.ndarray) -> dict[str, np.ndarray]:
    """
    Preserva o RGB original e suaviza somente a luminância usada na qualidade.

    A correção fotométrica é aplicada ao rosto alinhado, antes da extração,
    para não alterar a detecção nem esconder defeitos da captura original.
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


def normalizar_iluminacao(rgb: np.ndarray) -> np.ndarray:
    """Padroniza a luminância do rosto alinhado, preservando as cores em RGB.

    Gamma limitada compensa a exposição global; CLAHE moderado reduz diferenças
    locais de contraste. Cadastro e validação devem usar esta mesma operação.
    A função não recupera detalhes perdidos por saturação ou falta de luz.
    """
    if (not isinstance(rgb, np.ndarray) or rgb.ndim != 3 or rgb.shape[2] != 3
            or min(rgb.shape[:2]) < 3
            or not np.issubdtype(rgb.dtype, np.number)
            or np.issubdtype(rgb.dtype, np.complexfloating)):
        raise BiometriaErro("A normalização de iluminação requer uma imagem RGB válida.")
    if not np.isfinite(rgb).all() or np.any(rgb < 0) or np.any(rgb > 255):
        raise BiometriaErro("A imagem contém valores inválidos para normalizar a iluminação.")

    try:
        import cv2

        imagem = np.rint(rgb).astype(np.uint8)
        ycrcb = cv2.cvtColor(imagem, cv2.COLOR_RGB2YCrCb)
        luminancia = ycrcb[:, :, 0].copy()
        altura, largura = luminancia.shape
        y, x = np.ogrid[:altura, :largura]
        # Desconsidera cantos do alinhamento e pixels sem detalhes ao estimar luz.
        regiao_facial = ((x + 0.5 - largura / 2) / (largura / 2)) ** 2 + (
            (y + 0.5 - altura / 2) / (altura / 2)
        ) ** 2 <= 1
        valores = luminancia[regiao_facial & (luminancia > 8) & (luminancia < 247)]
        if valores.size == 0:
            return imagem.astype(np.float32)

        mediana = float(np.median(valores)) / 255
        gamma = float(np.clip(np.log(_LUMINANCIA_ALVO) / np.log(mediana),
                              _GAMMA_MINIMO, _GAMMA_MAXIMO))
        tabela = np.rint(255 * (np.arange(256, dtype=np.float64) / 255) ** gamma).astype(np.uint8)
        corrigida = cv2.LUT(luminancia, tabela)
        local = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(4, 4)).apply(corrigida)
        # Limita o efeito local para não acentuar excessivamente ruído/texturas.
        normalizada = cv2.addWeighted(corrigida, 0.5, local, 0.5, 0)
        normalizada[luminancia == 0] = 0
        normalizada[luminancia == 255] = 255
        ycrcb[:, :, 0] = normalizada
        return cv2.cvtColor(ycrcb, cv2.COLOR_YCrCb2RGB).astype(np.float32)
    except Exception as exc:
        # Não usar o RGB sem correção como fallback: geraria assinaturas distintas.
        raise BiometriaIndisponivel("Não foi possível normalizar a iluminação do rosto no servidor.") from exc
