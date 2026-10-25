"""A política facial versionada prevalece sobre configurações locais legadas."""

import json
import logging

import numpy as np
import pytest

import app.biometria as biometria
import app.politica_biometrica as politica
from app.config import Settings
from tests.test_api import CHAVE_TESTE, api, captura, cadastrar, credenciais, verificar


LOGGER = 'uvicorn.error.biometria'
PREFIXO = 'biometria_diagnostico '


def test_politica_versionada_preserva_valores_e_exports_do_pipeline():
    esperados = {
        'LIMIAR_EXPERIMENTAL': 0.30,
        'LIMIAR_MAXIMO': 0.40,
        'MARGEM_EXPERIMENTAL': 0.03,
        'LIMITE_CONSISTENCIA': 0.25,
        'FOCO_MINIMO_EXPERIMENTAL': 1.5,
    }
    for nome, esperado in esperados.items():
        assert getattr(politica, nome) == esperado
        assert getattr(biometria, nome) == esperado


@pytest.mark.parametrize('limiar,margem', [
    ('0.20', '0.90'),
    ('0.99', '1.50'),
    ('valor-invalido', 'valor-invalido'),
])
def test_variaveis_de_ambiente_legadas_nao_alteram_politica(monkeypatch, limiar, margem):
    monkeypatch.setenv('FACE_THRESHOLD', limiar)
    monkeypatch.setenv('FACE_MARGIN', margem)

    settings = Settings(_env_file=None, biometric_key=CHAVE_TESTE)

    assert settings.face_threshold == politica.LIMIAR_EXPERIMENTAL
    assert settings.face_margin == politica.MARGEM_EXPERIMENTAL


def test_env_legado_e_lido_sem_substituir_politica(tmp_path, monkeypatch):
    monkeypatch.delenv('FACE_THRESHOLD', raising=False)
    monkeypatch.delenv('FACE_MARGIN', raising=False)
    monkeypatch.delenv('DB_PORT', raising=False)
    arquivo = tmp_path / '.env'
    arquivo.write_text(
        'FACE_THRESHOLD=0.20\nFACE_MARGIN=0.90\nDB_PORT=3307\n', encoding='utf-8',
    )

    settings = Settings(_env_file=arquivo, biometric_key=CHAVE_TESTE)

    assert settings.db_port == 3307  # Confirma que o arquivo foi efetivamente carregado.
    assert settings.face_threshold == politica.LIMIAR_EXPERIMENTAL
    assert settings.face_margin == politica.MARGEM_EXPERIMENTAL


def test_limites_nao_sao_campos_configuraveis_nem_sobrescritos_no_construtor():
    settings = Settings(
        _env_file=None, biometric_key=CHAVE_TESTE, face_threshold=0.20, face_margin=0.90,
    )

    assert 'face_threshold' not in Settings.model_fields
    assert 'face_margin' not in Settings.model_fields
    assert settings.face_threshold == politica.LIMIAR_EXPERIMENTAL
    assert settings.face_margin == politica.MARGEM_EXPERIMENTAL


@pytest.mark.parametrize('nome,valor', [('face_threshold', 0.20), ('face_margin', 0.90)])
def test_propriedades_da_politica_sao_somente_leitura(nome, valor):
    settings = Settings(_env_file=None, biometric_key=CHAVE_TESTE)
    anterior = getattr(settings, nome)

    with pytest.raises(AttributeError):
        setattr(settings, nome, valor)

    assert getattr(settings, nome) == anterior


@pytest.fixture
def api_com_ambiente_legado(monkeypatch, request):
    # A dependência dinâmica garante que o ambiente exista antes de criar a API.
    monkeypatch.setenv('FACE_THRESHOLD', '0.20')
    monkeypatch.setenv('FACE_MARGIN', '0.90')
    return request.getfixturevalue('api')


def vetor_angular(graus):
    angulo = np.deg2rad(graus)
    vetor = np.zeros(biometria.DIMENSAO, dtype=np.float64)
    vetor[:2] = [np.cos(angulo), np.sin(angulo)]
    return vetor


def ultima_comparacao(caplog):
    comparacoes = [
        json.loads(record.getMessage()[len(PREFIXO):])
        for record in caplog.records
        if record.name == LOGGER and record.getMessage().startswith(PREFIXO)
    ]
    return [item for item in comparacoes if item['evento'] == 'comparacao'][-1]


def test_api_aplica_politica_versionada_mesmo_com_ambiente_legado(
    api_com_ambiente_legado, captura, monkeypatch, caplog,
):
    api_atual = api_com_ambiente_legado
    monkeypatch.setattr(biometria, '_inferir_embedding', lambda _imagem: vetor_angular(0))
    assert cadastrar(api_atual, captura).status_code == 201
    assert api_atual.settings.face_threshold == 0.30

    # Esta distância está entre o antigo limite local (0.20) e o versionado (0.30).
    monkeypatch.setattr(biometria, '_inferir_embedding', lambda _imagem: vetor_angular(43))
    assert credenciais(api_atual).status_code == 200
    with caplog.at_level(logging.INFO, logger=LOGGER):
        aceita = verificar(api_atual, captura)

    assert aceita.status_code == 200, aceita.text
    assert set(aceita.json()) == {'usuario', 'processamento'}
    comparacao = ultima_comparacao(caplog)
    assert comparacao['limiar'] == 0.30
    assert comparacao['margem'] == 0.03
    assert 0.20 < comparacao['distancia_decisao'] < 0.30
    assert comparacao['quadros_fora_do_limiar'] == []
    assert comparacao['identificado'] is True

    # A centralização não libera uma captura incompatível com a referência.
    monkeypatch.setattr(biometria, '_inferir_embedding', lambda _imagem: vetor_angular(70))
    assert credenciais(api_atual).status_code == 200
    caplog.clear()
    with caplog.at_level(logging.INFO, logger=LOGGER):
        rejeitada = verificar(api_atual, captura)

    assert rejeitada.status_code == 401, rejeitada.text
    assert set(rejeitada.json()) == {'detail'}
    comparacao = ultima_comparacao(caplog)
    assert comparacao['limiar'] == 0.30
    assert comparacao['distancia_decisao'] > 0.30
    assert comparacao['quadros_fora_do_limiar'] == [1, 2, 3]
    assert comparacao['identificado'] is False
    assert comparacao['motivo'] == 'fora_do_limiar'
