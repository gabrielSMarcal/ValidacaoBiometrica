"""Pipeline facial: quadros RGB vivos, recorte guiado e embedding TensorFlow.

Toda a lógica de imagem permanece neste módulo. A MobileNetV2 pré-treinada no
ImageNet funciona como extrator visual experimental; ela não é prova de vida
nem um modelo facial certificado. Fotos e telas ainda podem enganar o fluxo.
"""

from __future__ import annotations

import base64
import binascii
import math
from threading import Lock
from typing import Any

import numpy as np
import tensorflow as tf


GUIA = {"x": 0.25, "y": 0.10, "largura": 0.50, "altura": 0.80}
LIMIAR_EXPERIMENTAL = 0.20
MARGEM_EXPERIMENTAL = 0.03
LIMITE_CONSISTENCIA = 0.24
FOCO_MINIMO_EXPERIMENTAL = 1.5
ALGORITMO = "tensorflow-mobilenetv2-imagenet-face-roi-v2"
VERSAO = 2
DIMENSAO = 1280
_TAMANHO_MODELO = 160
_LARGURA_CANONICA = 160
_ALTURA_CANONICA = 192
_MODELO = None
_MODELO_LOCK = Lock()


class BiometriaErro(ValueError):
    """Captura, modelo ou assinatura incompatível com o pipeline."""


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
    
    return {"rgb": suavizada, "cinza": cinza}


def _mascara_eliptica(altura: int, largura: int) -> np.ndarray:
    
    y, x = np.ogrid[:altura, :largura]
    
    return ((x + 0.5 - largura / 2) / (largura / 2)) ** 2 + (
        (y + 0.5 - altura / 2) / (altura / 2)
    ) ** 2 <= 1


def _redimensionar(imagem: np.ndarray, altura: int, largura: int) -> np.ndarray:
    
    y = np.linspace(0, imagem.shape[0] - 1, altura)
    x = np.linspace(0, imagem.shape[1] - 1, largura)
    y0, x0 = y.astype(int), x.astype(int)
    y1 = np.minimum(y0 + 1, imagem.shape[0] - 1)
    x1 = np.minimum(x0 + 1, imagem.shape[1] - 1)
    fy, fx = (y - y0)[:, None], (x - x0)[None, :]
    
    if imagem.ndim == 3:
        fy, fx = fy[..., None], fx[..., None]
    
    acima = imagem[y0[:, None], x0] * (1 - fx) + imagem[y0[:, None], x1] * fx
    abaixo = imagem[y1[:, None], x0] * (1 - fx) + imagem[y1[:, None], x1] * fx
    
    return (acima * (1 - fy) + abaixo * fy).astype(np.float32)


def segmentacao(processado: dict[str, np.ndarray] | np.ndarray) -> dict[str, Any]:
    """
    3. Segmentação: controla qualidade e recorta a região facial da guia.
    """
    
    if isinstance(processado, np.ndarray):
        cinza = processado
        rgb = np.repeat(cinza[:, :, None], 3, axis=2)
    
    elif isinstance(processado, dict):
        cinza, rgb = processado.get("cinza"), processado.get("rgb")
    
    else:
        cinza = rgb = None
    
    if (not isinstance(cinza, np.ndarray) or cinza.ndim != 2 or min(cinza.shape) < 10
            or not isinstance(rgb, np.ndarray) or rgb.shape != (*cinza.shape, 3)):
        raise BiometriaErro("A segmentação requer uma imagem RGB pré-processada.")
    
    if not np.isfinite(cinza).all() or np.any(cinza < 0) or np.any(cinza > 255.001):
        raise BiometriaErro("A imagem contém valores inválidos.")

    altura, largura = cinza.shape
    x0, y0 = round(largura * GUIA["x"]), round(altura * GUIA["y"])
    x1 = round(largura * (GUIA["x"] + GUIA["largura"]))
    y1 = round(altura * (GUIA["y"] + GUIA["altura"]))
    regiao_cinza, regiao_rgb = cinza[y0:y1, x0:x1], rgb[y0:y1, x0:x1]
    mascara_original = _mascara_eliptica(*regiao_cinza.shape)
    valores = regiao_cinza[mascara_original]
    media, contraste = float(valores.mean()), float(valores.std())
    foco = float(laplaciano[mascara_original[1:-1, 1:-1]].std())
    saturacao = float(np.mean((valores <= 8) | (valores >= 247)))
    laplaciano = (
        regiao_cinza[:-2, 1:-1] + regiao_cinza[2:, 1:-1]
        + regiao_cinza[1:-1, :-2] + regiao_cinza[1:-1, 2:]
        - 4 * regiao_cinza[1:-1, 1:-1]
    )
    
    if not 35 <= media <= 225:
        raise BiometriaErro("Melhore a iluminação: evite ambiente escuro ou luz excessiva.")
    
    if contraste < 14:
        raise BiometriaErro("A região tem pouco contraste. Ajuste a iluminação e o enquadramento.")
    
    if saturacao > 0.55:
        raise BiometriaErro("Há muitos pixels saturados. Evite luz direta e sombras intensas.")
    
    if foco < FOCO_MINIMO_EXPERIMENTAL:
        raise BiometriaErro("A imagem está pouco nítida. Limpe a lente e permaneça imóvel.")

    imagem = _redimensionar(regiao_rgb, _ALTURA_CANONICA, _LARGURA_CANONICA)
    mascara = _mascara_eliptica(_ALTURA_CANONICA, _LARGURA_CANONICA)
    imagem[~mascara] = float(media)
    
    return {
        "imagem": np.clip(imagem, 0, 255).astype(np.float32),
        "mascara": mascara,
        "qualidade": {
            "iluminacao_media": round(media, 3),
            "contraste_desvio": round(contraste, 3),
            "foco_desvio_laplaciano": round(foco, 3),
            "fracao_saturada": round(saturacao, 4),
        },
    }


def _carregar_modelo():
    """
    Carrega uma única instância; os pesos ficam no cache padrão do Keras.
    """
    
    global _MODELO
    
    if _MODELO is not None:
        return _MODELO
    
    with _MODELO_LOCK:
    
        if _MODELO is not None:
            return _MODELO
    
        try:
            modelo = tf.keras.applications.MobileNetV2(
                input_shape=(_TAMANHO_MODELO, _TAMANHO_MODELO, 3),
                include_top=False, weights="imagenet", pooling="avg",
            )
    
        except Exception as exc:
            raise BiometriaErro(
                "Não foi possível carregar os pesos TensorFlow. Conecte-se à internet na primeira execução."
            ) from exc
    
        modelo.trainable = False
        _MODELO = modelo
    
    return _MODELO


def _inferir_embedding(imagem: np.ndarray) -> np.ndarray:
    """
    Executa inferência TensorFlow e devolve um embedding L2-normalizado.
    """
    
    modelo = _carregar_modelo()
    tensor = tf.convert_to_tensor(imagem[None, ...], dtype=tf.float32)
    tensor = tf.image.resize(tensor, (_TAMANHO_MODELO, _TAMANHO_MODELO), antialias=True)
    tensor = tf.keras.applications.mobilenet_v2.preprocess_input(tensor)
    vetor = np.asarray(modelo(tensor, training=False).numpy()[0], dtype=np.float64)
    norma = float(np.linalg.norm(vetor))
    
    if vetor.shape != (DIMENSAO,) or not np.isfinite(vetor).all() or norma <= 1e-12:
        raise BiometriaErro("O modelo TensorFlow produziu um embedding inválido.")
    
    return vetor / norma


def extracao_caracteristicas(segmento: dict[str, Any]) -> dict[str, Any]:
    """
    4. Extração: transforma a região facial em embedding TensorFlow.
    """
    
    if not isinstance(segmento, dict):
        raise BiometriaErro("A extração requer a saída da segmentação.")
    
    imagem, mascara = segmento.get("imagem"), segmento.get("mascara")
    esperado = (_ALTURA_CANONICA, _LARGURA_CANONICA, 3)
    
    if not isinstance(imagem, np.ndarray) or imagem.shape != esperado:
        raise BiometriaErro("Dimensões incompatíveis com o modelo TensorFlow.")
    
    if not isinstance(mascara, np.ndarray) or mascara.shape != esperado[:2] or mascara.dtype != np.bool_:
        raise BiometriaErro("Máscara incompatível com a região facial.")
    
    if not mascara.any() or not np.isfinite(imagem).all() or np.any(imagem < 0) or np.any(imagem > 255):
        raise BiometriaErro("A região facial segmentada está vazia ou inválida.")
    
    return _criar_assinatura(_inferir_embedding(imagem))


def _criar_assinatura(vetor: np.ndarray) -> dict[str, Any]:
    
    vetor = np.asarray(vetor, dtype=np.float64)
    norma = float(np.linalg.norm(vetor))
    
    if vetor.shape != (DIMENSAO,) or not np.isfinite(vetor).all() or norma <= 1e-12:
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


def comparar_assinaturas(a: dict[str, Any], b: dict[str, Any]) -> float:
    """
    Distância de cosseno em [0, 1]; zero indica embeddings iguais.
    """
    
    va, vb = _validar_assinatura(a), _validar_assinatura(b)
    
    return (1 - float(np.clip(np.dot(va, vb), -1, 1))) / 2


def classificacao_interpretacao(
    assinatura: dict[str, Any], candidatos: list[tuple[str, dict[str, Any]]],
    limiar: float = LIMIAR_EXPERIMENTAL, margem: float = MARGEM_EXPERIMENTAL,
) -> dict[str, Any]:
    """
    5. Classificação: vizinho mais próximo com limiar e margem.
    """
    
    _validar_assinatura(assinatura)
    
    for valor in (limiar, margem):
        if type(valor) not in (int, float) or not 0 <= valor <= 1 or not math.isfinite(valor):
            raise BiometriaErro("Limiar e margem devem estar entre zero e um.")
    
    if not isinstance(candidatos, list):
        raise BiometriaErro("Os candidatos devem ser uma lista de identificadores e assinaturas.")
    
    resultados, ids = [], set()
    
    for candidato in candidatos:
    
        if not isinstance(candidato, (tuple, list)) or len(candidato) != 2:
            raise BiometriaErro("Candidato biométrico inválido.")
    
        usuario_id, cadastrada = candidato
    
        if not isinstance(usuario_id, str) or not usuario_id or usuario_id in ids:
            raise BiometriaErro("Cada candidato deve possuir um identificador único.")
    
        ids.add(usuario_id)
        resultados.append((comparar_assinaturas(assinatura, cadastrada), usuario_id))
    
    resultados.sort()
    resultado = {"identificado": False, "usuario_id": None, "distancia": None,
                 "segunda_distancia": None, "motivo": "sem_candidatos"}
    
    if not resultados:
        return resultado
    
    melhor, usuario_id = resultados[0]
    segunda = resultados[1][0] if len(resultados) > 1 else None
    resultado.update(distancia=melhor, segunda_distancia=segunda)
    
    if melhor > limiar:
        resultado["motivo"] = "fora_do_limiar"
    
    elif segunda is not None and (segunda - melhor < margem or segunda == melhor):
        resultado["motivo"] = "captura_ambigua"
    
    else:
        resultado.update(identificado=True, usuario_id=usuario_id, motivo="identificado")
    
    return resultado


def processar_captura(frames: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Processa de três a cinco quadros vivos e agrega seus embeddings.
    """
    
    if not isinstance(frames, list) or not 3 <= len(frames) <= 5:
        raise BiometriaErro("Capture de três a cinco quadros da câmera.")
    
    assinaturas, qualidades = [], []
    formato = None
    
    for indice, frame in enumerate(frames, 1):
        try:
            rgb = sensoriamento(frame)
            if formato is not None and rgb.shape != formato:
                raise BiometriaErro("Todos os quadros devem ter as mesmas dimensões.")
            formato = rgb.shape
            segmento = segmentacao(pre_processamento(rgb))
            assinaturas.append(extracao_caracteristicas(segmento))
            qualidades.append(segmento["qualidade"])
        except BiometriaErro as exc:
            raise BiometriaErro(f"Quadro {indice}: {exc}") from exc
    
    maior_distancia = max(
        comparar_assinaturas(a, b)
        for indice, a in enumerate(assinaturas) for b in assinaturas[indice + 1:]
    )
    
    if maior_distancia > LIMITE_CONSISTENCIA:
        raise BiometriaErro("Os quadros diferem muito. Mantenha o rosto no guia durante a captura.")
    
    assinatura = _criar_assinatura(np.mean([item["vetor"] for item in assinaturas], axis=0))
    resumo = {
        "etapas": [
            {"fase": "Sensores", "descricao": f"{len(frames)} quadros RGB recebidos da câmera.",
             "largura": formato[1], "altura": formato[0], "canais": formato[2]},
            {"fase": "Pré-processamento", "descricao": "Suavização binomial e análise de luminância."},
            {"fase": "Segmentação", "descricao": "Região facial elíptica guiada, normalizada em 160×192."},
            {"fase": "Extração de características", "descricao": f"Embedding TensorFlow MobileNetV2 com {DIMENSAO} componentes."},
            {"fase": "Classificação/interpretação", "descricao": "Comparação por distância de cosseno normalizada."},
        ],
        "quadros": len(frames), "qualidade": qualidades,
        "modelo": "TensorFlow MobileNetV2 / pesos ImageNet", "algoritmo": ALGORITMO,
        "maior_distancia_entre_quadros": round(maior_distancia, 6),
        "limite_consistencia_experimental": LIMITE_CONSISTENCIA,
        "foco_minimo_experimental": FOCO_MINIMO_EXPERIMENTAL, "guia": GUIA.copy(),
        "aviso": "Protótipo experimental sem prova de vida; não usar como único fator em produção.",
    }
    
    return assinatura, resumo
