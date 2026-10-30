"""Regressões com detector e reconhecimento reais, sem substituir inferência."""

import base64
import copy
import json
import os
from pathlib import Path

import cv2
import numpy as np
import pytest

from app import biometria
from app.banco import DesafioBiometrico, Sessao, Usuario
from tests.test_api import api, cadastrar, contar


pytestmark = [
    pytest.mark.modelo_real,
    pytest.mark.skipif(
        os.environ.get("APS_TEST_MODELO_REAL") != "1",
        reason="Ative APS_TEST_MODELO_REAL=1 para executar os pesos faciais reais.",
    ),
]

# Fotografias dos testes/exemplos originais de ageitgey/face_recognition.
# O commit imutável registra a origem; nenhuma imagem de usuário foi coletada.
_ORIGEM = (
    "https://raw.githubusercontent.com/ageitgey/face_recognition/"
    "9f3061aaeed9a8756d2c970f5dfe066617a8281d/"
)
FONTES_IMAGENS = {
    "obama.jpg": _ORIGEM + "tests/test_images/obama.jpg",
    "obama2.jpg": _ORIGEM + "tests/test_images/obama2.jpg",
    "biden.jpg": _ORIGEM + "tests/test_images/biden.jpg",
    "obama_and_biden.jpg": _ORIGEM + "examples/knn_examples/test/obama_and_biden.jpg",
}
_DADOS = Path(__file__).parent / "dados_faciais"
_USUARIO = "usuario-autenticado-pelo-cpf"


def _frame(rgb):
    altura, largura = rgb.shape[:2]
    return {
        "largura": largura,
        "altura": altura,
        "rgb_base64": base64.b64encode(rgb.tobytes()).decode("ascii"),
    }


def _frame_fotografia(nome):
    assert nome in FONTES_IMAGENS
    conteudo = np.frombuffer((_DADOS / nome).read_bytes(), dtype=np.uint8)
    bgr = cv2.imdecode(conteudo, cv2.IMREAD_COLOR)
    assert bgr is not None, f"Fixture facial ausente ou inválida: {nome}"
    if nome == "biden.jpg":
        # Remove só a parte inferior do retrato para simular a face próxima à câmera.
        bgr = bgr[:1500]
    altura, largura = bgr.shape[:2]
    escala = min(640 / largura, 480 / altura)
    reduzida = cv2.resize(
        bgr,
        (round(largura * escala), round(altura * escala)),
        interpolation=cv2.INTER_AREA,
    )
    # A borda mantém o formato de câmera sem deformar a proporção dos rostos.
    camera = np.full((480, 640, 3), 128, dtype=np.uint8)
    y = (480 - reduzida.shape[0]) // 2
    x = (640 - reduzida.shape[1]) // 2
    camera[y:y + reduzida.shape[0], x:x + reduzida.shape[1]] = reduzida
    return _frame(cv2.cvtColor(camera, cv2.COLOR_BGR2RGB))


@pytest.fixture(scope="module")
def assinaturas_reais():
    # Isola detecção/alinhamento/embedding: fotos estáticas não cumprem o cadastro com movimento.
    return {
        nome: biometria.extracao_caracteristicas(biometria.segmentacao(
            biometria.pre_processamento(biometria.sensoriamento(_frame_fotografia(nome))),
        ))
        for nome in ("obama.jpg", "obama2.jpg", "biden.jpg")
    }


def test_modelo_real_produz_512_dimensoes_normalizadas(assinaturas_reais):
    for assinatura in assinaturas_reais.values():
        assert assinatura["algoritmo"] == biometria.ALGORITMO
        assert assinatura["dimensao"] == biometria.DIMENSAO == 512
        assert len(assinatura["vetor"]) == 512
        assert np.isfinite(assinatura["vetor"]).all()
        assert np.linalg.norm(assinatura["vetor"]) == pytest.approx(1, abs=1e-7)
        assert json.loads(json.dumps(assinatura, allow_nan=False)) == assinatura


def test_modelo_real_aceita_duas_fotos_distintas_da_mesma_pessoa(assinaturas_reais):
    cadastrada = assinaturas_reais["obama.jpg"]
    consulta = assinaturas_reais["obama2.jpg"]
    resultado = biometria.classificacao_interpretacao(consulta, [(_USUARIO, cadastrada)])
    assert resultado["identificado"] is True, resultado
    assert resultado["usuario_id"] == _USUARIO


def test_modelo_real_rejeita_celebridade_diferente_do_usuario(assinaturas_reais):
    cadastrada = assinaturas_reais["obama.jpg"]
    consulta = assinaturas_reais["biden.jpg"]
    resultado = biometria.classificacao_interpretacao(consulta, [(_USUARIO, cadastrada)])
    assert resultado["identificado"] is False, resultado
    assert resultado["usuario_id"] is None
    assert resultado["motivo"] == "fora_do_limiar"


def test_modelo_real_rejeita_textura_sem_rosto():
    aleatorio = np.random.default_rng(9406)
    rgb = aleatorio.integers(40, 216, size=(480, 640, 3), dtype=np.uint8)
    with pytest.raises(biometria.BiometriaErro, match="rosto"):
        biometria.segmentacao(biometria.pre_processamento(rgb))


def test_modelo_real_rejeita_dois_rostos_no_mesmo_quadro():
    frame = _frame_fotografia("obama_and_biden.jpg")
    with pytest.raises(biometria.BiometriaErro, match="rosto"):
        biometria.segmentacao(biometria.pre_processamento(biometria.sensoriamento(frame)))


def test_modelo_real_rejeita_assinatura_legada_mobilenet(assinaturas_reais):
    atual = assinaturas_reais["obama.jpg"]
    legada = copy.deepcopy(atual)
    legada.update(
        versao=2,
        algoritmo="tensorflow-mobilenetv2-imagenet-face-roi-v2",
        dimensao=1280,
        vetor=np.full(1280, 1 / np.sqrt(1280)).tolist(),
    )
    with pytest.raises(biometria.BiometriaErro):
        biometria.comparar_assinaturas(atual, legada)


def test_api_real_nao_aceita_fotografia_repetida_como_sequencia_de_cadastro(api):
    cadastro = {"frames": [_frame_fotografia("obama.jpg")] * 3}
    rejeitado = cadastrar(api, cadastro, nivel=3)
    assert rejeitado.status_code == 422, rejeitado.text
    assert 'mesma imagem' in rejeitado.json()['detail']
    assert contar(api, Usuario) == contar(api, Sessao) == contar(api, DesafioBiometrico) == 0
