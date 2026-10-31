"""1. Aquisição: recebe e valida os quadros RGB enviados pela câmera."""
from __future__ import annotations
import base64
import binascii
import json
import logging
from typing import Any
import numpy as np


_LOGGER = logging.getLogger("uvicorn.error.biometria")


def _registrar_diagnostico(evento: str, **metricas: Any) -> None:
    _LOGGER.info("biometria_diagnostico %s", json.dumps(
        {"evento": evento, **metricas}, ensure_ascii=False, allow_nan=False,
    ))


class BiometriaErro(ValueError):
    """Captura, modelo ou assinatura incompatível com o pipeline."""


class BiometriaIndisponivel(BiometriaErro):
    pass


def sensoriamento(frame: dict[str, Any]) -> np.ndarray:

    """
    1. Sensoriamento: valida e decodifica os bytes RGB da câmera.
    """

    if not isinstance(frame, dict):
        raise BiometriaErro("Cada quadro deve conter largura, altura e rgb_base64.")

    largura, altura = frame.get("largura"), frame.get("altura")

    if type(largura) is not int or type(altura) is not int:
        raise BiometriaErro("Largura e altura devem ser números inteiros.")
    if not (160 <= largura <= 640 and 120 <= altura <= 480):
        raise BiometriaErro("Use quadros entre 160×120 e 640×480 pixels.")

    conteudo = frame.get("rgb_base64")
    tamanho = largura * altura * 3

    if not isinstance(conteudo, str) or len(conteudo) != 4 * ((tamanho + 2) // 3):
        raise BiometriaErro("O tamanho do quadro RGB não corresponde às dimensões.")

    try:
        dados = base64.b64decode(conteudo, validate=True)

    except (binascii.Error, ValueError) as exc:
        raise BiometriaErro("O quadro RGB contém base64 inválido.") from exc

    if len(dados) != tamanho:
        raise BiometriaErro("Envie exatamente três bytes RGB por pixel, sem alfa.")

    return np.frombuffer(dados, dtype=np.uint8).reshape(altura, largura, 3)
