"""4. Extração: embedding AuraFace normalizado e formato da assinatura."""
from __future__ import annotations
import math
from typing import Any
import numpy as np
from .sensoriamento import BiometriaErro


ALGORITMO = "auraface-v1-arcface-r100-yunet-112-v3"
VERSAO = 3
DIMENSAO = 512
_LARGURA_CANONICA = 112
_ALTURA_CANONICA = 112


def extracao_caracteristicas(segmento: dict[str, Any], inferir_embedding) -> dict[str, Any]:
    """
    4. Extração: transforma o rosto alinhado em embedding facial AuraFace.
    """

    if not isinstance(segmento, dict):
        raise BiometriaErro("A extração requer a saída da segmentação.")

    imagem, mascara = segmento.get("imagem"), segmento.get("mascara")
    esperado = (_ALTURA_CANONICA, _LARGURA_CANONICA, 3)

    if not isinstance(imagem, np.ndarray) or imagem.shape != esperado:
        raise BiometriaErro("Dimensões incompatíveis com o modelo facial.")

    if not isinstance(mascara, np.ndarray) or mascara.shape != esperado[:2] or mascara.dtype != np.bool_:
        raise BiometriaErro("Máscara incompatível com a região facial.")

    if not mascara.any() or not np.isfinite(imagem).all() or np.any(imagem < 0) or np.any(imagem > 255):
        raise BiometriaErro("A região facial segmentada está vazia ou inválida.")

    return _criar_assinatura(inferir_embedding(imagem))


def _criar_assinatura(vetor: np.ndarray) -> dict[str, Any]:

    vetor = np.asarray(vetor, dtype=np.float64)
    norma = float(np.linalg.norm(vetor))

    if (vetor.shape != (DIMENSAO,) or not np.isfinite(vetor).all()
            or not math.isfinite(norma) or norma <= 1e-12):
        raise BiometriaErro("Não foi possível normalizar o embedding biométrico.")

    vetor = vetor / norma

    return {"versao": VERSAO, "algoritmo": ALGORITMO, "dimensao": DIMENSAO,
            "vetor": vetor.round(10).tolist()}


def _validar_assinatura(assinatura: dict[str, Any]) -> np.ndarray:

    if not isinstance(assinatura, dict):
        raise BiometriaErro("Assinatura biométrica inválida.")

    if (type(assinatura.get("versao")) is not int or assinatura["versao"] != VERSAO
            or assinatura.get("algoritmo") != ALGORITMO
            or type(assinatura.get("dimensao")) is not int or assinatura["dimensao"] != DIMENSAO):
        raise BiometriaErro("Versão ou algoritmo incompatível; recadastre a biometria do usuário.")

    vetor = assinatura.get("vetor")

    if not isinstance(vetor, list) or len(vetor) != DIMENSAO:
        raise BiometriaErro("Dimensão da assinatura biométrica inválida.")

    if any(type(valor) not in (int, float) for valor in vetor):
        raise BiometriaErro("A assinatura deve conter somente números reais.")

    try:
        valores = np.asarray(vetor, dtype=np.float64)

    except (ValueError, OverflowError) as exc:
        raise BiometriaErro("A assinatura contém números inválidos.") from exc

    norma = float(np.linalg.norm(valores))

    if not np.isfinite(valores).all() or not np.isclose(norma, 1.0, atol=0.00001):
        raise BiometriaErro("A assinatura biométrica não está normalizada.")

    return valores / norma
