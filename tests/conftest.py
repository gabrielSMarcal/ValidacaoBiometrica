"""A suíte valida contratos sem baixar os pesos; a inferência real é integrada manualmente."""
import numpy as np
import pytest

import app.biometria as biometria


@pytest.fixture(autouse=True)
def embedding_tensorflow_deterministico(monkeypatch):
    def inferir(imagem):
        cinza = imagem @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
        reduzida = biometria._redimensionar(cinza, 32, 40).reshape(-1).astype(np.float64)
        reduzida -= reduzida.mean()
        norma = np.linalg.norm(reduzida)
        return reduzida / norma

    monkeypatch.setattr(biometria, '_inferir_embedding', inferir)
