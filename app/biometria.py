"""As cinco fases de processamento, implementadas sem modelo pré-treinado.

Experimento didático: a pessoa posiciona o rosto dentro de uma elipse. A
segmentação é geométrica, não detecta rostos, e o descritor não verifica vida.
Fotos, telas e objetos podem produzir assinaturas válidas. Os limiares abaixo
precisam de calibração com pessoas e condições reais antes de qualquer avaliação
de desempenho; este módulo não serve como controle de acesso de produção.

Nenhuma função abre arquivos ou interpreta PNG/JPEG. O navegador transmite os
bytes RGB obtidos diretamente de getImageData(), codificados em base64.
"""

from __future__ import annotations

import base64
import binascii
import math
from typing import Any

import numpy as np


GUIA = {"x": 0.25, "y": 0.10, "largura": 0.50, "altura": 0.80}
LIMIAR_EXPERIMENTAL = 0.20
MARGEM_EXPERIMENTAL = 0.03
LIMITE_CONSISTENCIA = 0.35
# Filtro permissivo de qualidade após a suavização, sem calibração em pessoas.
FOCO_MINIMO_EXPERIMENTAL = 1.5
ALGORITMO = "aps-lbp59-gradientes-v1"
DIMENSAO = 4 * 4 * 59 + 4 * 4 * 8 + 8 * 8
_LARGURA_CANONICA = 96
_ALTURA_CANONICA = 112


class BiometriaErro(ValueError):
    """Captura ou assinatura incompatível com o pipeline didático."""


def sensoriamento(frame: dict[str, Any]) -> np.ndarray:
    """1. Sensores: valida e decodifica RGB cru enviado pela câmera.

    Entrada: {largura: int, altura: int, rgb_base64: str}. Saída: matriz
    uint8 [altura, largura, 3]. A origem física não pode ser atestada pela API.
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


def pre_processamento(rgb: np.ndarray) -> np.ndarray:
    """2. Pré-processamento: luminância e suavização binomial 3×3.

    Luminância = 0,299 R + 0,587 G + 0,114 B; o filtro [1,2,1] separável
    reduz ruído antes do cálculo de textura. Não utiliza detector externo.
    """
    if not isinstance(rgb, np.ndarray) or rgb.ndim != 3 or rgb.shape[2] != 3:
        raise BiometriaErro("O pré-processamento requer uma matriz RGB.")
    if rgb.dtype != np.uint8 or rgb.shape[0] < 3 or rgb.shape[1] < 3:
        raise BiometriaErro("A matriz RGB deve conter pixels uint8 válidos.")
    cinza = rgb.astype(np.float32) @ np.array([0.299, 0.587, 0.114], np.float32)
    bordas = np.pad(cinza, ((0, 0), (1, 1)), mode="reflect")
    horizontal = (bordas[:, :-2] + 2 * bordas[:, 1:-1] + bordas[:, 2:]) / 4
    bordas = np.pad(horizontal, ((1, 1), (0, 0)), mode="reflect")
    return (bordas[:-2] + 2 * bordas[1:-1] + bordas[2:]) / 4


def _mascara_eliptica(altura: int, largura: int) -> np.ndarray:
    y, x = np.ogrid[:altura, :largura]
    return ((x + 0.5 - largura / 2) / (largura / 2)) ** 2 + (
        (y + 0.5 - altura / 2) / (altura / 2)
    ) ** 2 <= 1


def _redimensionar(imagem: np.ndarray, altura: int, largura: int) -> np.ndarray:
    """Interpolação bilinear explícita, sem biblioteca de visão computacional."""
    y = np.linspace(0, imagem.shape[0] - 1, altura)
    x = np.linspace(0, imagem.shape[1] - 1, largura)
    y0, x0 = y.astype(int), x.astype(int)
    y1, x1 = np.minimum(y0 + 1, imagem.shape[0] - 1), np.minimum(x0 + 1, imagem.shape[1] - 1)
    fy, fx = (y - y0)[:, None], (x - x0)[None, :]
    acima = imagem[y0[:, None], x0] * (1 - fx) + imagem[y0[:, None], x1] * fx
    abaixo = imagem[y1[:, None], x0] * (1 - fx) + imagem[y1[:, None], x1] * fx
    return (acima * (1 - fy) + abaixo * fy).astype(np.float32)


def segmentacao(cinza: np.ndarray) -> dict[str, Any]:
    """3. Segmentação guiada: recorta e mascara a elipse indicada na tela.

    Verifica iluminação, contraste, nitidez e saturação na região; em seguida
    normaliza percentis 2..98 e redimensiona para 96×112. Essas verificações
    não comprovam a presença de um rosto, sua identidade ou sua vivacidade.
    """
    if not isinstance(cinza, np.ndarray) or cinza.ndim != 2 or min(cinza.shape) < 10:
        raise BiometriaErro("A segmentação requer uma imagem em escala de cinza.")
    if not np.isfinite(cinza).all() or np.any(cinza < 0) or np.any(cinza > 255.001):
        raise BiometriaErro("A imagem em escala de cinza contém valores inválidos.")
    altura, largura = cinza.shape
    x0, y0 = round(largura * GUIA["x"]), round(altura * GUIA["y"])
    x1 = round(largura * (GUIA["x"] + GUIA["largura"]))
    y1 = round(altura * (GUIA["y"] + GUIA["altura"]))
    regiao = cinza[y0:y1, x0:x1]
    mascara_original = _mascara_eliptica(*regiao.shape)
    valores = regiao[mascara_original]
    media, contraste = float(valores.mean()), float(valores.std())
    laplaciano = (
        regiao[:-2, 1:-1] + regiao[2:, 1:-1]
        + regiao[1:-1, :-2] + regiao[1:-1, 2:] - 4 * regiao[1:-1, 1:-1]
    )
    foco = float(laplaciano[mascara_original[1:-1, 1:-1]].std())
    saturacao = float(np.mean((valores <= 8) | (valores >= 247)))
    if not 35 <= media <= 225:
        raise BiometriaErro("Melhore a iluminação: evite ambiente escuro ou luz excessiva.")
    if contraste < 14:
        raise BiometriaErro("A região tem pouco contraste. Ajuste a iluminação e o enquadramento.")
    if saturacao > 0.55:
        raise BiometriaErro("Há muitos pixels saturados. Evite luz direta e sombras intensas.")
    if foco < FOCO_MINIMO_EXPERIMENTAL:
        raise BiometriaErro("A imagem está pouco nítida. Limpe a lente e permaneça imóvel.")
    minimo, maximo = np.percentile(valores, [2, 98])
    normalizada = np.clip((regiao - minimo) / max(float(maximo - minimo), 1.0), 0, 1)
    normalizada = _redimensionar(normalizada, _ALTURA_CANONICA, _LARGURA_CANONICA)
    mascara = _mascara_eliptica(_ALTURA_CANONICA, _LARGURA_CANONICA)
    return {
        "imagem": normalizada,
        "mascara": mascara,
        "qualidade": {
            "iluminacao_media": round(media, 3),
            "contraste_desvio": round(contraste, 3),
            "foco_desvio_laplaciano": round(foco, 3),
            "fracao_saturada": round(saturacao, 4),
        },
    }


def _mapa_lbp_uniforme() -> np.ndarray:
    mapa = np.full(256, 58, dtype=np.uint8)
    proximo = 0
    for codigo in range(256):
        bits = [(codigo >> indice) & 1 for indice in range(8)]
        transicoes = sum(bits[indice] != bits[(indice + 1) % 8] for indice in range(8))
        if transicoes <= 2:
            mapa[codigo] = proximo
            proximo += 1
    return mapa


_MAPA_LBP = _mapa_lbp_uniforme()


def _histogramas_espaciais(
    codigos: np.ndarray, mascara: np.ndarray, quantidade_bins: int, pesos: np.ndarray | None = None
) -> np.ndarray:
    histogramas = []
    altura, largura = codigos.shape
    for linha in range(4):
        for coluna in range(4):
            recorte = np.s_[linha * altura // 4:(linha + 1) * altura // 4,
                            coluna * largura // 4:(coluna + 1) * largura // 4]
            validos = mascara[recorte]
            hist = np.bincount(
                codigos[recorte][validos],
                weights=pesos[recorte][validos] if pesos is not None else None,
                minlength=quantidade_bins,
            ).astype(np.float64)
            total = hist.sum()
            histogramas.append(hist / total if total > 0 else np.full(quantidade_bins, 1 / quantidade_bins))
    return np.concatenate(histogramas) / 16


def extracao_caracteristicas(segmento: dict[str, Any]) -> dict[str, Any]:
    """4. Extração: descritor próprio de 1.136 componentes.

    Combina LBP uniforme (59 bins × 4×4 células, peso 0,55), orientações de
    gradiente (8 bins × 4×4 células, peso 0,30) e luminosidade relativa
    (8×8 células, peso 0,15). O vetor é uma distribuição não negativa.
    Não há rede neural, detector de terceiros ou pesos pré-treinados.
    """
    if not isinstance(segmento, dict):
        raise BiometriaErro("A extração requer a saída da segmentação.")
    imagem, mascara = segmento.get("imagem"), segmento.get("mascara")
    esperado = (_ALTURA_CANONICA, _LARGURA_CANONICA)
    if not isinstance(imagem, np.ndarray) or not isinstance(mascara, np.ndarray):
        raise BiometriaErro("A extração requer imagem e máscara válidas.")
    if imagem.shape != esperado or mascara.shape != esperado or mascara.dtype != np.bool_:
        raise BiometriaErro("Dimensões ou máscara incompatíveis com o descritor.")
    if not np.isfinite(imagem).all() or np.any(imagem < 0) or np.any(imagem > 1):
        raise BiometriaErro("A imagem normalizada deve conter valores entre zero e um.")
    if not mascara.any():
        raise BiometriaErro("A máscara da região de interesse está vazia.")
    # Exclui pixels que tocariam o exterior da elipse ao examinar vizinhos.
    validos = mascara.copy()
    validos[[0, -1], :] = False
    validos[:, [0, -1]] = False
    direcoes = [(-1, -1), (-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1), (0, -1)]
    codigo = np.zeros(esperado, dtype=np.uint8)
    for indice, (dy, dx) in enumerate(direcoes):
        vizinho = np.roll(imagem, shift=(-dy, -dx), axis=(0, 1))
        codigo |= ((vizinho >= imagem).astype(np.uint8) << indice)
        validos &= np.roll(mascara, shift=(-dy, -dx), axis=(0, 1))
    lbp = _histogramas_espaciais(_MAPA_LBP[codigo], validos, 59)
    gy, gx = np.gradient(imagem)
    magnitude = np.hypot(gx, gy)
    orientacoes = np.minimum(((np.arctan2(gy, gx) % np.pi) / np.pi * 8).astype(int), 7)
    gradientes = _histogramas_espaciais(orientacoes, validos, 8, magnitude)
    intensidade = []
    for linha in range(8):
        for coluna in range(8):
            recorte = np.s_[linha * esperado[0] // 8:(linha + 1) * esperado[0] // 8,
                            coluna * esperado[1] // 8:(coluna + 1) * esperado[1] // 8]
            pixels = imagem[recorte][mascara[recorte]]
            intensidade.append(float(pixels.mean()) + 0.05 if pixels.size else 0.05)
    intensidade = np.asarray(intensidade)
    intensidade /= intensidade.sum()
    vetor = np.concatenate((0.55 * lbp, 0.30 * gradientes, 0.15 * intensidade))
    return _criar_assinatura(vetor)


def _criar_assinatura(vetor: np.ndarray) -> dict[str, Any]:
    vetor = vetor / vetor.sum()
    return {"versao": 1, "algoritmo": ALGORITMO, "dimensao": DIMENSAO,
            "vetor": vetor.round(10).tolist()}


def _validar_assinatura(assinatura: dict[str, Any]) -> np.ndarray:
    if not isinstance(assinatura, dict):
        raise BiometriaErro("Assinatura biométrica inválida.")
    if (type(assinatura.get("versao")) is not int or assinatura["versao"] != 1
            or assinatura.get("algoritmo") != ALGORITMO
            or type(assinatura.get("dimensao")) is not int or assinatura["dimensao"] != DIMENSAO):
        raise BiometriaErro("Versão ou algoritmo da assinatura incompatível; refaça o cadastro.")
    vetor = assinatura.get("vetor")
    if not isinstance(vetor, list) or len(vetor) != DIMENSAO:
        raise BiometriaErro("Dimensão da assinatura biométrica inválida.")
    if any(type(valor) not in (int, float) for valor in vetor):
        raise BiometriaErro("A assinatura deve conter somente números reais.")
    try:
        valores = np.asarray(vetor, dtype=np.float64)
    except (ValueError, OverflowError) as exc:
        raise BiometriaErro("A assinatura contém números inválidos.") from exc
    if (not np.isfinite(valores).all() or np.any(valores < 0)
            or not np.isclose(valores.sum(), 1.0, atol=0.00001)):
        raise BiometriaErro("A assinatura biométrica não está normalizada.")
    return valores / valores.sum()


def comparar_assinaturas(a: dict[str, Any], b: dict[str, Any]) -> float:
    """Distância de Hellinger [0, 1]; zero é idêntico. Não é probabilidade."""
    va, vb = _validar_assinatura(a), _validar_assinatura(b)
    return float(np.sqrt(np.sum((np.sqrt(va) - np.sqrt(vb)) ** 2) / 2))


def classificacao_interpretacao(
    assinatura: dict[str, Any], candidatos: list[tuple[str, dict[str, Any]]],
    limiar: float = LIMIAR_EXPERIMENTAL, margem: float = MARGEM_EXPERIMENTAL,
) -> dict[str, Any]:
    """5. Classificação/interpretação: vizinho mais próximo com rejeição.

    Aceita somente distância <= limiar e diferença para o segundo >= margem.
    Defaults 0,20/0,03 são experimentais, não calibrados. O chamador consulta
    o grupo de permissões do usuário identificado no banco, nunca no descritor.
    """
    _validar_assinatura(assinatura)
    for valor in (limiar, margem):
        if type(valor) not in (int, float) or not 0 <= valor <= 1 or not math.isfinite(valor):
            raise BiometriaErro("Limiar e margem devem estar entre zero e um.")
    if not isinstance(candidatos, list):
        raise BiometriaErro("Os candidatos devem ser uma lista de identificadores e assinaturas.")
    resultados = []
    ids = set()
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
    """Processa 3..5 quadros, agrega descritores e devolve resumo sem pixels.

    A consistência entre descritores reduz capturas acidentalmente diferentes;
    não é prova de vida. A classificação entre usuários ocorre na fase 5 quando
    o chamador fornecer as assinaturas cadastradas.
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
        raise BiometriaErro("Os quadros diferem muito. Mantenha o rosto no guia durante toda a captura.")
    assinatura = _criar_assinatura(np.mean([item["vetor"] for item in assinaturas], axis=0))
    resumo = {
        "etapas": [
            {"fase": "Sensores", "descricao": f"{len(frames)} quadros RGB recebidos da câmera.",
             "largura": formato[1], "altura": formato[0], "canais": formato[2]},
            {"fase": "Pré-processamento", "descricao": "Luminância e suavização binomial 3×3."},
            {"fase": "Segmentação", "descricao": "Elipse central guiada; normalização e recorte 96×112."},
            {"fase": "Extração de características", "descricao": f"LBP, gradientes e luminosidade; {DIMENSAO} componentes."},
            {"fase": "Classificação/interpretação", "descricao": "Descritor preparado; comparação com os cadastros executada na validação."},
        ],
        "quadros": len(frames),
        "qualidade": qualidades,
        "maior_distancia_entre_quadros": round(maior_distancia, 6),
        "limite_consistencia_experimental": LIMITE_CONSISTENCIA,
        "foco_minimo_experimental": FOCO_MINIMO_EXPERIMENTAL,
        "guia": GUIA.copy(),
        "aviso": "Experimento sem detector facial, prova de vida ou limiares calibrados.",
    }
    return assinatura, resumo
