"""3. Segmentação: detecta, verifica qualidade, alinha e valida movimento."""
from __future__ import annotations
from typing import Any
import numpy as np
from .sensoriamento import BiometriaErro, BiometriaIndisponivel, _registrar_diagnostico
from .extracao_caracteristicas import _ALTURA_CANONICA, _LARGURA_CANONICA


FOCO_MINIMO_EXPERIMENTAL = 1.5
ILUMINACAO_MINIMA = 35
ILUMINACAO_MAXIMA = 225
CONTRASTE_MINIMO = 14
SATURACAO_MAXIMA = 0.55
POSE_FRONTAL_MAXIMA = 0.12
POSE_MAXIMA = 0.35
MOVIMENTO_MINIMO = 0.075
GUIA = {"x": 0.25, "y": 0.10, "largura": 0.50, "altura": 0.80}
_PONTOS_ALINHAMENTO = np.array([
    [38.2946, 51.6963], [73.5318, 51.5014], [56.0252, 71.7366],
    [41.5493, 92.3655], [70.7299, 92.2041],
], dtype=np.float64)


def _mascara_eliptica(altura: int, largura: int) -> np.ndarray:

    y, x = np.ogrid[:altura, :largura]

    return ((x + 0.5 - largura / 2) / (largura / 2)) ** 2 + (
        (y + 0.5 - altura / 2) / (altura / 2)
    ) ** 2 <= 1


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


def segmentacao(processado: dict[str, np.ndarray] | np.ndarray, detectar_faces) -> dict[str, Any]:
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
    faces = np.asarray(detectar_faces(rgb))
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
