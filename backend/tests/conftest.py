"""Testes rápidos usam inferência sintética; modelo_real utiliza os pesos reais."""
import numpy as np
import pytest

import app.biometria as biometria


def pytest_configure(config):
    config.addinivalue_line('markers', 'modelo_real: executa detector e reconhecimento facial reais')


@pytest.fixture(autouse=True)
def embedding_facial_deterministico(monkeypatch, request):
    if request.node.get_closest_marker('modelo_real'):
        return

    def detectar(rgb):
        altura, largura = rgb.shape[:2]
        x, y, w, h = largura * 0.25, altura * 0.10, largura * 0.50, altura * 0.80
        pontos = biometria._PONTOS_ALINHAMENTO / 112 * [w, h] + [x, y]
        return np.array([[x, y, w, h, *pontos.reshape(-1), 0.99]])

    def inferir(imagem):
        cinza = imagem @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
        reduzida = biometria._redimensionar(cinza, 16, 32).reshape(-1).astype(np.float64)
        reduzida -= reduzida.mean()
        norma = np.linalg.norm(reduzida)
        return reduzida / norma

    monkeypatch.setattr(biometria, '_inferir_embedding', inferir)
    monkeypatch.setattr(biometria, '_detectar_faces', detectar)
