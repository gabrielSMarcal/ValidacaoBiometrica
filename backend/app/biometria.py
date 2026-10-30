"""Detecção YuNet, alinhamento facial e reconhecimento AuraFace de 512 dimensões."""

from __future__ import annotations

import base64
import binascii
import json
import logging
import math
from typing import Any

import numpy as np

from .modelos_faciais import ModeloFacialIndisponivel, detectar_faces, inferir_embedding
from .politica_biometrica import (
    CONTRASTE_MINIMO,
    FOCO_MINIMO_EXPERIMENTAL,
    ILUMINACAO_MAXIMA,
    ILUMINACAO_MINIMA,
    LIMIAR_EXPERIMENTAL,
    LIMIAR_MAXIMO,
    LIMITE_CONSISTENCIA,
    MARGEM_EXPERIMENTAL,
    MOVIMENTO_MINIMO,
    POSE_FRONTAL_MAXIMA,
    POSE_MAXIMA,
    SATURACAO_MAXIMA,
)


GUIA = {"x": 0.25, "y": 0.10, "largura": 0.50, "altura": 0.80}
ALGORITMO = "auraface-v1-arcface-r100-yunet-112-v3"
VERSAO = 3
DIMENSAO = 512
_LARGURA_CANONICA = 112
_ALTURA_CANONICA = 112
_PONTOS_ALINHAMENTO = np.array([
    [38.2946, 51.6963], [73.5318, 51.5014], [56.0252, 71.7366],
    [41.5493, 92.3655], [70.7299, 92.2041],
], dtype=np.float64)

# Herda o handler do Uvicorn para aparecer no terminal com a inicialização atual.
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


def _detectar_faces(rgb: np.ndarray) -> np.ndarray:
    try:
        return detectar_faces(rgb)
    except ModeloFacialIndisponivel as exc:
        raise BiometriaIndisponivel(str(exc)) from None


def _alinhar_rosto(rgb: np.ndarray, pontos: np.ndarray) -> np.ndarray:
    origem = pontos - pontos.mean(axis=0)
    destino = _PONTOS_ALINHAMENTO - _PONTOS_ALINHAMENTO.mean(axis=0)
    variancia = float(np.sum(origem ** 2) / len(pontos))
    if variancia <= 1e-12:
        raise BiometriaErro("Pontos faciais inválidos para o alinhamento.")
    u, valores, vt = np.linalg.svd(destino.T @ origem / len(pontos))
    if valores[0] <= 1e-12 or valores[1] / valores[0] < 0.05:
        raise BiometriaErro("Pontos faciais inválidos para o alinhamento.")
    sinais = np.array([1.0, np.sign(np.linalg.det(u @ vt))])
    rotacao = u @ np.diag(sinais) @ vt
    escala = float(np.dot(valores, sinais) / variancia)
    translacao = _PONTOS_ALINHAMENTO.mean(axis=0) - escala * rotacao @ pontos.mean(axis=0)
    matriz = np.column_stack((escala * rotacao, translacao))
    try:
        import cv2
        return cv2.warpAffine(rgb, matriz, (112, 112), flags=cv2.INTER_LINEAR,
                              borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    except Exception as exc:
        raise BiometriaIndisponivel("Não foi possível alinhar o rosto no servidor.") from exc


def segmentacao(processado: dict[str, np.ndarray] | np.ndarray) -> dict[str, Any]:
    """
    3. Segmentação: exige um único rosto detectado e alinha cinco pontos faciais.
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
    
    if (not np.isfinite(cinza).all() or not np.isfinite(rgb).all()
            or np.any(cinza < 0) or np.any(cinza > 255.001)
            or np.any(rgb < 0) or np.any(rgb > 255)):
        raise BiometriaErro("A imagem contém valores inválidos.")

    altura, largura = cinza.shape
    faces = np.asarray(_detectar_faces(rgb))
    if faces.ndim != 2 or faces.shape[1] != 15 or not np.isfinite(faces).all():
        raise BiometriaErro("O detector retornou dados faciais inválidos.")
    if len(faces) == 0:
        iluminacao = float(cinza.mean())
        if iluminacao < ILUMINACAO_MINIMA:
            raise BiometriaErro("A imagem está muito escura. Aumente a iluminação sobre o rosto e tente novamente.")
        if iluminacao > ILUMINACAO_MAXIMA:
            raise BiometriaErro("A imagem está muito clara. Reduza a iluminação direta sobre o rosto e tente novamente.")
        raise BiometriaErro("Nenhum rosto detectado. Enquadre o rosto e ajuste a iluminação.")
    if len(faces) != 1:
        raise BiometriaErro("Capture apenas um rosto por vez. Afaste as outras pessoas e refaça toda a sequência.")
    x, y, face_largura, face_altura = faces[0, :4]
    if (faces[0, 14] < 0.90 or min(face_largura, face_altura) < 64
            or face_largura * face_altura < largura * altura * 0.02
            or x < -2 or y < -2 or x + face_largura > largura + 2 or y + face_altura > altura + 2):
        raise BiometriaErro("Aproxime e enquadre o rosto inteiro na câmera.")
    pontos = faces[0, 4:14].reshape(5, 2).astype(np.float64)
    if (np.any(pontos < [0, 0]) or np.any(pontos >= [largura, altura])
            or np.linalg.norm(pontos[1] - pontos[0]) < 16
            or pontos[1, 0] <= pontos[0, 0]
            or pontos[:2, 1].mean() >= pontos[3:, 1].mean()):
        raise BiometriaErro("Os pontos faciais não permitem validar o rosto.")
    eixo_olhos = pontos[1] - pontos[0]
    centro_olhos = (pontos[0] + pontos[1]) / 2
    pose_horizontal = float(np.dot(pontos[2] - centro_olhos, eixo_olhos) / np.dot(eixo_olhos, eixo_olhos))
    x0, y0 = max(0, int(x)), max(0, int(y))
    x1, y1 = min(largura, int(np.ceil(x + face_largura))), min(altura, int(np.ceil(y + face_altura)))
    regiao_cinza, regiao_rgb = cinza[y0:y1, x0:x1], rgb[y0:y1, x0:x1]
    mascara_original = _mascara_eliptica(*regiao_cinza.shape)
    valores = regiao_cinza[mascara_original]
    media, contraste = float(valores.mean()), float(valores.std())
    saturacao = float(np.mean((valores <= 8) | (valores >= 247)))
    laplaciano = (
        regiao_cinza[:-2, 1:-1] + regiao_cinza[2:, 1:-1]
        + regiao_cinza[1:-1, :-2] + regiao_cinza[1:-1, 2:]
        - 4 * regiao_cinza[1:-1, 1:-1]
    )
    foco = float(laplaciano[mascara_original[1:-1, 1:-1]].std())
    
    if media < ILUMINACAO_MINIMA:
        raise BiometriaErro("O rosto está com pouca iluminação. Aumente a luz sobre o rosto, evitando luz forte atrás de você.")

    if media > ILUMINACAO_MAXIMA:
        raise BiometriaErro("Há iluminação excessiva no rosto. Reduza a luz direta e os reflexos antes de tentar novamente.")
    
    if contraste < CONTRASTE_MINIMO:
        raise BiometriaErro("A região tem pouco contraste. Ajuste a iluminação e o enquadramento.")
    
    if saturacao > SATURACAO_MAXIMA:
        raise BiometriaErro("Há muitos pixels saturados. Evite luz direta e sombras intensas.")
    
    if foco < FOCO_MINIMO_EXPERIMENTAL:
        raise BiometriaErro("A imagem está pouco nítida. Limpe a lente e permaneça imóvel.")

    imagem = _alinhar_rosto(rgb.astype(np.float32), pontos)
    mascara = np.ones((_ALTURA_CANONICA, _LARGURA_CANONICA), dtype=np.bool_)
    
    return {
        "imagem": np.clip(imagem, 0, 255).astype(np.float32),
        "mascara": mascara,
        "pose_horizontal": pose_horizontal,
        "qualidade": {
            "iluminacao_media": round(media, 3),
            "contraste_desvio": round(contraste, 3),
            "foco_desvio_laplaciano": round(foco, 3),
            "fracao_saturada": round(saturacao, 4),
        },
    }


def _inferir_embedding(imagem: np.ndarray) -> np.ndarray:
    try:
        return inferir_embedding(imagem)
    except ModeloFacialIndisponivel as exc:
        raise BiometriaIndisponivel(str(exc)) from None


def extracao_caracteristicas(segmento: dict[str, Any]) -> dict[str, Any]:
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
    
    return _criar_assinatura(_inferir_embedding(imagem))


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


def comparar_assinaturas(a: dict[str, Any], b: dict[str, Any]) -> float:
    """
    Distância de cosseno em [0, 2]; zero indica embeddings iguais.
    """
    
    va, vb = _validar_assinatura(a), _validar_assinatura(b)
    
    return 1 - float(np.clip(np.dot(va, vb), -1, 1))


def classificacao_interpretacao(
    assinatura: dict[str, Any], candidatos: list[tuple[str, dict[str, Any]]],
    limiar: float = LIMIAR_EXPERIMENTAL, margem: float = MARGEM_EXPERIMENTAL,
) -> dict[str, Any]:
    """
    5. Classificação: vizinho mais próximo com limiar e margem.
    """
    
    _validar_assinatura(assinatura)
    
    for valor, maximo in ((limiar, LIMIAR_MAXIMO), (margem, 1)):
        if type(valor) not in (int, float) or not 0 <= valor <= maximo or not math.isfinite(valor):
            raise BiometriaErro("Limiar ou margem fora do intervalo permitido pelo modelo facial.")
    
    if not isinstance(candidatos, list):
        raise BiometriaErro("Os candidatos devem ser uma lista de identificadores e assinaturas.")
    
    resultados, ids, diagnosticos = [], set(), {}
    
    for candidato in candidatos:
    
        if not isinstance(candidato, (tuple, list)) or len(candidato) != 2:
            raise BiometriaErro("Candidato biométrico inválido.")
    
        usuario_id, cadastrada = candidato
    
        if not isinstance(usuario_id, str) or not usuario_id or usuario_id in ids:
            raise BiometriaErro("Cada candidato deve possuir um identificador único.")
    
        ids.add(usuario_id)
        distancia_media = comparar_assinaturas(assinatura, cadastrada)
        distancia = distancia_media
        distancias_quadros = []
        amostras = assinatura.get("amostras", [])
        if not isinstance(amostras, list) or (amostras and not 3 <= len(amostras) <= 5):
            raise BiometriaErro("Amostras da assinatura biométrica inválidas.")
        for vetor in amostras:
            amostra = {"versao": VERSAO, "algoritmo": ALGORITMO, "dimensao": DIMENSAO, "vetor": vetor}
            distancia_quadro = comparar_assinaturas(amostra, cadastrada)
            distancias_quadros.append(distancia_quadro)
            distancia = max(distancia, distancia_quadro)
        resultados.append((distancia, usuario_id))
        diagnosticos[usuario_id] = {
            "distancia_media": round(distancia_media, 6),
            "distancias_quadros": [round(valor, 6) for valor in distancias_quadros],
            "quadros_fora_do_limiar": [
                indice for indice, valor in enumerate(distancias_quadros, 1) if valor > limiar
            ],
        }
    
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

    _registrar_diagnostico(
        "comparacao", **diagnosticos[usuario_id],
        distancia_decisao=round(melhor, 6),
        segunda_distancia=round(segunda, 6) if segunda is not None else None,
        limiar=limiar, margem=margem, candidatos=len(resultados),
        identificado=resultado["identificado"], motivo=resultado["motivo"],
    )
    
    return resultado


def _validar_movimento(segmentos: list[dict[str, Any]]) -> None:
    """Exige poses opostas na sequência; não comprova presença nem prova de vida."""
    poses = [segmento["pose_horizontal"] for segmento in segmentos]
    frente, direita, esquerda = poses[:3]
    deslocamentos = [pose - frente for pose in poses]
    mensagem, motivo = None, "sequencia_valida"
    if any(abs(pose) > POSE_MAXIMA for pose in poses):
        mensagem = "Vire a cabeça apenas levemente e mantenha os dois olhos visíveis durante toda a captura."
        motivo = "rotacao_excessiva"
    elif abs(frente) > POSE_FRONTAL_MAXIMA:
        mensagem = "Comece a sequência olhando de frente para a câmera."
        motivo = "primeiro_quadro_nao_frontal"
    elif direita - frente > -MOVIMENTO_MINIMO:
        mensagem = "Na segunda captura, vire levemente a cabeça para a sua direita. Refaça toda a sequência."
        motivo = "movimento_direita_insuficiente"
    elif esquerda - frente < MOVIMENTO_MINIMO:
        mensagem = "Na terceira captura, vire levemente a cabeça para a sua esquerda. Refaça toda a sequência."
        motivo = "movimento_esquerda_insuficiente"

    _registrar_diagnostico(
        "movimento", aceita=mensagem is None, motivo=motivo,
        poses_horizontais=[round(pose, 6) for pose in poses],
        deslocamentos_horizontais=[round(valor, 6) for valor in deslocamentos],
        limite_frontal=POSE_FRONTAL_MAXIMA, limite_pose=POSE_MAXIMA,
        movimento_minimo=MOVIMENTO_MINIMO,
    )
    if mensagem:
        raise BiometriaErro(mensagem)


def processar_captura(
    frames: list[dict[str, Any]], *, exigir_movimento: bool = True,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Agrega três a cinco quadros; cadastro exige a sequência de movimento.
    """
    
    if not isinstance(frames, list) or not 3 <= len(frames) <= 5:
        raise BiometriaErro("Capture de três a cinco quadros da câmera.")
    
    imagens, segmentos, assinaturas, qualidades = [], [], [], []
    formato = None
    
    for indice, frame in enumerate(frames, 1):
        try:
            rgb = sensoriamento(frame)
            if formato is not None and rgb.shape != formato:
                raise BiometriaErro("Todos os quadros devem ter as mesmas dimensões.")
            formato = rgb.shape
            imagens.append(rgb)
        except BiometriaErro as exc:
            _registrar_diagnostico(
                "captura", aceita=False, quadro=indice, motivo=str(exc),
            )
            raise type(exc)(f"Quadro {indice}: {exc}") from exc

    for indice, rgb in enumerate(imagens, 1):
        try:
            segmento = segmentacao(pre_processamento(rgb))
            segmentos.append(segmento)
            qualidades.append(segmento["qualidade"])
        except BiometriaErro as exc:
            _registrar_diagnostico("captura", aceita=False, quadro=indice, motivo=str(exc))
            raise type(exc)(f"Quadro {indice}: {exc}") from exc

    if exigir_movimento:
        for indice, rgb in enumerate(imagens, 1):
            if any(np.array_equal(rgb, anterior) for anterior in imagens[:indice - 1]):
                mensagem = "Os quadros repetem a mesma imagem. Refaça a sequência: frente, sua direita e sua esquerda."
                _registrar_diagnostico("captura", aceita=False, quadro=indice, motivo=mensagem)
                raise BiometriaErro(f"Quadro {indice}: {mensagem}")
        _validar_movimento(segmentos)

    for indice, segmento in enumerate(segmentos, 1):
        try:
            assinaturas.append(extracao_caracteristicas(segmento))
        except BiometriaErro as exc:
            _registrar_diagnostico("captura", aceita=False, quadro=indice, motivo=str(exc))
            raise type(exc)(f"Quadro {indice}: {exc}") from exc
    
    maior_distancia = max(
        comparar_assinaturas(a, b)
        for indice, a in enumerate(assinaturas) for b in assinaturas[indice + 1:]
    )

    _registrar_diagnostico(
        "captura", aceita=maior_distancia <= LIMITE_CONSISTENCIA,
        qualidade_quadros=qualidades,
        maior_distancia_entre_quadros=round(maior_distancia, 6),
        limite_consistencia=LIMITE_CONSISTENCIA,
        motivo="quadros_consistentes" if maior_distancia <= LIMITE_CONSISTENCIA else "quadros_inconsistentes",
    )
    
    if maior_distancia > LIMITE_CONSISTENCIA:
        raise BiometriaErro("Os quadros diferem muito. Mantenha o rosto no guia durante a captura.")
    
    assinatura = _criar_assinatura(np.mean([item["vetor"] for item in assinaturas], axis=0))
    assinatura["amostras"] = [item["vetor"] for item in assinaturas]
    resumo = {
        "etapas": [
            {"fase": "Sensores", "descricao": f"{len(frames)} quadros RGB recebidos da câmera.",
             "largura": formato[1], "altura": formato[0], "canais": formato[2]},
            {"fase": "Pré-processamento", "descricao": "Suavização binomial e análise de luminância."},
            {"fase": "Segmentação", "descricao": "Detecção de um rosto com YuNet e alinhamento em 112×112."},
            {"fase": "Extração de características", "descricao": f"Embedding facial AuraFace com {DIMENSAO} componentes."},
            {"fase": "Classificação/interpretação", "descricao": "Comparação facial 1:1 por distância de cosseno."},
        ],
        "quadros": len(frames), "qualidade": qualidades,
        "modelo": "AuraFace v1 / ArcFace ResNet100 / ONNX Runtime", "algoritmo": ALGORITMO,
        "maior_distancia_entre_quadros": round(maior_distancia, 6),
        "limite_consistencia_experimental": LIMITE_CONSISTENCIA,
        "foco_minimo_experimental": FOCO_MINIMO_EXPERIMENTAL, "guia": GUIA.copy(),
        "aviso": "Protótipo experimental sem prova de vida; não usar como único fator em produção.",
    }
    
    return assinatura, resumo
