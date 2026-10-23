"""Carregamento local de detector facial e reconhecimento AuraFace verificados."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import tempfile
from threading import Lock
from urllib.request import Request, urlopen

import numpy as np

from .config import ROOT


class ModeloFacialIndisponivel(RuntimeError):
    """Os modelos locais ou suas dependências não estão disponíveis."""


@dataclass(frozen=True)
class _Modelo:
    arquivo: str
    url: str
    sha256: str
    tamanho: int


DIRETORIO_MODELOS = ROOT / '.runtime' / 'modelos'
_DETECTOR = _Modelo(
    'face_detection_yunet_2023mar.onnx',
    'https://media.githubusercontent.com/media/opencv/opencv_zoo/'
    '48b10fa505aeb51fbd127fc60a5c660040e823b7/models/'
    'face_detection_yunet/face_detection_yunet_2023mar.onnx',
    '8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4',
    232589,
)
_RECONHECEDOR = _Modelo(
    'glintr100.onnx',
    'https://huggingface.co/fal/AuraFace-v1/resolve/'
    'af6d057c9b0ec4071d4c49c80e3539258798b609/glintr100.onnx',
    'a7933ea5330113b01c9b60351d8f4c33003f145d8470ac5f0e52ee2effe25c60',
    260694151,
)
_MODELOS = (_DETECTOR, _RECONHECEDOR)
_PREPARACAO_LOCK = Lock()
_CARGA_LOCK = Lock()
_DETECCAO_LOCK = Lock()
_detector = None
_sessao = None


def _arquivo_valido(modelo: _Modelo) -> bool:
    caminho = DIRETORIO_MODELOS / modelo.arquivo
    try:
        if not caminho.is_file() or caminho.stat().st_size != modelo.tamanho:
            return False
        checksum = hashlib.sha256()
        with caminho.open('rb') as arquivo:
            for bloco in iter(lambda: arquivo.read(1024 * 1024), b''):
                checksum.update(bloco)
        return checksum.hexdigest() == modelo.sha256
    except OSError:
        return False


def _exigir_arquivo(modelo: _Modelo) -> Path:
    if not _arquivo_valido(modelo):
        raise ModeloFacialIndisponivel(
            'Modelo facial ausente ou inválido. Execute python scripts/preparar_modelos.py '
            'no diretório backend.'
        )
    return DIRETORIO_MODELOS / modelo.arquivo


def _baixar_modelo(modelo: _Modelo) -> None:
    parcial = None
    try:
        DIRETORIO_MODELOS.mkdir(parents=True, exist_ok=True)
        checksum = hashlib.sha256()
        recebidos = 0
        requisicao = Request(modelo.url, headers={'User-Agent': 'APS-Facial/1.0'})
        with tempfile.NamedTemporaryFile(
            mode='wb', prefix=modelo.arquivo + '.', suffix='.part',
            dir=DIRETORIO_MODELOS, delete=False,
        ) as destino:
            parcial = Path(destino.name)
            with urlopen(requisicao, timeout=60) as resposta:
                while True:
                    bloco = resposta.read(min(1024 * 1024, modelo.tamanho - recebidos + 1))
                    if not bloco:
                        break
                    recebidos += len(bloco)
                    if recebidos > modelo.tamanho:
                        raise ModeloFacialIndisponivel('O modelo recebido ultrapassou o tamanho permitido.')
                    checksum.update(bloco)
                    destino.write(bloco)
            if recebidos != modelo.tamanho or checksum.hexdigest() != modelo.sha256:
                raise ModeloFacialIndisponivel('O modelo recebido falhou na verificação de integridade.')
            destino.flush()
            os.fsync(destino.fileno())
        os.replace(parcial, DIRETORIO_MODELOS / modelo.arquivo)
        parcial = None
    except ModeloFacialIndisponivel:
        raise
    except Exception:
        raise ModeloFacialIndisponivel(
            'Não foi possível preparar os modelos faciais. Confira a conexão e a pasta .runtime/modelos.'
        ) from None
    finally:
        if parcial is not None:
            try:
                parcial.unlink(missing_ok=True)
            except OSError:
                pass


def preparar_modelos() -> None:
    """Baixa somente os artefatos fixados e instala após verificar SHA-256."""
    with _PREPARACAO_LOCK:
        for modelo in _MODELOS:
            if not _arquivo_valido(modelo):
                _baixar_modelo(modelo)


def _carregar_detector():
    global _detector
    if _detector is not None:
        return _detector
    with _CARGA_LOCK:
        if _detector is not None:
            return _detector
        caminho = _exigir_arquivo(_DETECTOR)
        try:
            import cv2
            detector = cv2.FaceDetectorYN_create(
                'onnx', np.frombuffer(caminho.read_bytes(), dtype=np.uint8),
                np.empty(0, dtype=np.uint8), (320, 240), 0.90, 0.3, 5000,
            )
            if detector is None:
                raise ValueError
        except Exception:
            raise ModeloFacialIndisponivel(
                'Não foi possível carregar o detector YuNet. Confira os modelos e as dependências do backend.'
            ) from None
        _detector = detector
    return _detector


def _carregar_sessao():
    global _sessao
    if _sessao is not None:
        return _sessao
    with _CARGA_LOCK:
        if _sessao is not None:
            return _sessao
        caminho = _exigir_arquivo(_RECONHECEDOR)
        try:
            import onnxruntime as ort
            opcoes = ort.SessionOptions()
            opcoes.intra_op_num_threads = min(4, max(1, os.cpu_count() or 1))
            opcoes.inter_op_num_threads = 1
            opcoes.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
            sessao = ort.InferenceSession(
                str(caminho), sess_options=opcoes, providers=['CPUExecutionProvider'],
            )
            if len(sessao.get_inputs()) != 1:
                raise ValueError
        except Exception:
            raise ModeloFacialIndisponivel(
                'Não foi possível carregar AuraFace. Confira os modelos e o ONNX Runtime do backend.'
            ) from None
        _sessao = sessao
    return _sessao


def _validar_rgb(imagem: np.ndarray, tamanho: tuple[int, int] | None = None) -> None:
    if (not isinstance(imagem, np.ndarray) or imagem.ndim != 3 or imagem.shape[2] != 3
            or min(imagem.shape[:2]) < 1 or not np.issubdtype(imagem.dtype, np.number)
            or np.issubdtype(imagem.dtype, np.complexfloating)
            or (tamanho is not None and imagem.shape[:2] != tamanho)):
        raise ValueError('A inferência facial requer uma imagem RGB de dimensões válidas.')
    if not np.isfinite(imagem).all() or np.any(imagem < 0) or np.any(imagem > 255):
        raise ValueError('A imagem RGB contém pixels inválidos.')


def detectar_faces(rgb: np.ndarray) -> np.ndarray:
    """Retorna caixas, cinco pontos faciais e confiança YuNet em linhas de 15 valores."""
    _validar_rgb(rgb)
    detector = _carregar_detector()
    bgr = np.ascontiguousarray(rgb[:, :, ::-1], dtype=np.uint8)
    try:
        with _DETECCAO_LOCK:
            detector.setInputSize((rgb.shape[1], rgb.shape[0]))
            _, faces = detector.detect(bgr)
        if faces is None:
            return np.empty((0, 15), dtype=np.float32)
        faces = np.asarray(faces)
        if (faces.ndim != 2 or faces.shape[1] != 15
                or not np.issubdtype(faces.dtype, np.floating) or not np.isfinite(faces).all()):
            raise ValueError
        return faces.astype(np.float32, copy=False)
    except Exception:
        raise ModeloFacialIndisponivel('O detector facial não conseguiu processar a captura.') from None


def inferir_embedding(imagem112rgb: np.ndarray) -> np.ndarray:
    """Executa AuraFace em RGB NCHW e devolve 512 componentes L2 normalizados."""
    _validar_rgb(imagem112rgb, (112, 112))
    sessao = _carregar_sessao()
    tensor = (imagem112rgb.astype(np.float32) - 127.5) / 127.5
    tensor = np.ascontiguousarray(tensor.transpose(2, 0, 1)[None, ...])
    try:
        saidas = sessao.run(None, {sessao.get_inputs()[0].name: tensor})
        if len(saidas) != 1:
            raise ValueError
        saida = np.asarray(saidas[0])
        if saida.shape != (1, 512) or not np.issubdtype(saida.dtype, np.floating):
            raise ValueError
        vetor = saida[0].astype(np.float64)
        norma = float(np.linalg.norm(vetor))
        if not np.isfinite(vetor).all() or not np.isfinite(norma) or norma <= 1e-12:
            raise ValueError
        return vetor / norma
    except Exception:
        raise ModeloFacialIndisponivel('AuraFace produziu um embedding facial inválido.') from None
