"""Diagnósticos internos sem alterar o contrato nem relaxar a decisão facial."""

import json
import logging

import numpy as np
import pytest

import app.biometria as biometria
from tests.test_api import api, captura, cadastrar, credenciais, verificar
from tests.test_biometria import quadro_sintetico


LOGGER = 'uvicorn.error.biometria'
PREFIXO = 'biometria_diagnostico '
CHAVES_RESULTADO = {'identificado', 'usuario_id', 'distancia', 'segunda_distancia', 'motivo'}


def vetor_angular(graus):
    angulo = np.deg2rad(graus)
    vetor = np.zeros(biometria.DIMENSAO, dtype=np.float64)
    vetor[:2] = [np.cos(angulo), np.sin(angulo)]
    return vetor


def assinatura_angular(graus):
    return {
        'versao': biometria.VERSAO, 'algoritmo': biometria.ALGORITMO,
        'dimensao': biometria.DIMENSAO, 'vetor': vetor_angular(graus).tolist(),
    }


def assinatura_com_quadros(graus):
    vetores = [vetor_angular(angulo) for angulo in graus]
    media = np.mean(vetores, axis=0)
    media /= np.linalg.norm(media)
    return {
        **assinatura_angular(0), 'vetor': media.tolist(),
        'amostras': [vetor.tolist() for vetor in vetores],
    }


def diagnosticos(caplog):
    return [
        json.loads(record.getMessage()[len(PREFIXO):])
        for record in caplog.records
        if record.name == LOGGER and record.getMessage().startswith(PREFIXO)
    ]


def test_diagnostico_identifica_quadro_reprovado_sem_aceitar_pela_media(caplog):
    assinatura = assinatura_com_quadros([25, 25, 50])
    referencia = assinatura_angular(0)
    with caplog.at_level(logging.INFO, logger=LOGGER):
        resultado = biometria.classificacao_interpretacao(
            assinatura, [('identidade-privada', referencia)], limiar=0.30,
        )

    [diagnostico] = diagnosticos(caplog)
    esperadas = [1 - np.cos(np.deg2rad(angulo)) for angulo in [25, 25, 50]]
    assert resultado['identificado'] is False
    assert resultado['motivo'] == 'fora_do_limiar'
    assert diagnostico['evento'] == 'comparacao'
    assert diagnostico['distancias_quadros'] == pytest.approx(esperadas, abs=1e-6)
    assert diagnostico['quadros_fora_do_limiar'] == [3]
    assert diagnostico['distancia_media'] < diagnostico['limiar'] < diagnostico['distancia_decisao']
    assert diagnostico['distancia_media'] == pytest.approx(
        biometria.comparar_assinaturas(assinatura, referencia), abs=1e-6,
    )
    assert diagnostico['distancia_decisao'] == pytest.approx(resultado['distancia'], abs=1e-6)


def test_diagnostico_tambem_registra_comparacao_aceita(caplog):
    with caplog.at_level(logging.INFO, logger=LOGGER):
        resultado = biometria.classificacao_interpretacao(
            assinatura_com_quadros([5, 10, 15]), [('referencia', assinatura_angular(0))],
            limiar=0.20, margem=0.04,
        )

    [diagnostico] = diagnosticos(caplog)
    assert resultado['identificado'] is True
    assert diagnostico['identificado'] is True
    assert diagnostico['motivo'] == 'identificado'
    assert diagnostico['limiar'] == 0.20
    assert diagnostico['margem'] == 0.04
    assert diagnostico['candidatos'] == 1
    assert diagnostico['segunda_distancia'] is None
    assert diagnostico['quadros_fora_do_limiar'] == []
    assert len(diagnostico['distancias_quadros']) == 3
    assert diagnostico['distancia_decisao'] <= diagnostico['limiar']


def test_diagnostico_usa_melhor_candidato_sem_expor_identidade_ou_assinatura(caplog):
    assinatura = assinatura_com_quadros([0, 1, 2])
    referencia = assinatura_angular(0)
    identidade = 'CPF-ou-identificador-privado-nao-deve-aparecer'
    outro = 'outro-identificador-privado'
    with caplog.at_level(logging.INFO, logger=LOGGER):
        resultado = biometria.classificacao_interpretacao(
            assinatura, [(identidade, referencia), (outro, assinatura_angular(80))],
        )

    [diagnostico] = diagnosticos(caplog)
    assert set(resultado) == CHAVES_RESULTADO
    assert resultado['identificado'] is True
    assert resultado['usuario_id'] == identidade
    assert diagnostico['candidatos'] == 2
    assert diagnostico['distancia_media'] == pytest.approx(
        biometria.comparar_assinaturas(assinatura, referencia), abs=1e-6,
    )
    assert diagnostico['distancia_decisao'] == pytest.approx(resultado['distancia'], abs=1e-6)
    assert diagnostico['segunda_distancia'] == pytest.approx(resultado['segunda_distancia'], abs=1e-6)
    assert diagnostico['distancias_quadros'] == pytest.approx(
        [1 - np.cos(np.deg2rad(angulo)) for angulo in [0, 1, 2]], abs=1e-6,
    )
    assert not any(dado in caplog.text for dado in [
        identidade, outro, '"vetor"', '"amostras"', 'rgb_base64', json.dumps(assinatura['vetor']),
    ])


def test_diagnostico_captura_registra_qualidade_e_consistencia(caplog):
    frame = quadro_sintetico()
    with caplog.at_level(logging.INFO, logger=LOGGER):
        assinatura, resumo = biometria.processar_captura([frame] * 3)

    [diagnostico] = diagnosticos(caplog)
    assert diagnostico['evento'] == 'captura'
    assert diagnostico['aceita'] is True
    assert diagnostico['motivo'] == 'quadros_consistentes'
    assert diagnostico['qualidade_quadros'] == resumo['qualidade']
    assert len(diagnostico['qualidade_quadros']) == 3
    assert diagnostico['maior_distancia_entre_quadros'] == 0
    assert diagnostico['limite_consistencia'] == biometria.LIMITE_CONSISTENCIA
    assert set(assinatura) == {'versao', 'algoritmo', 'dimensao', 'vetor', 'amostras'}
    assert 'diagnostico' not in resumo
    assert frame['rgb_base64'] not in caplog.text
    assert '"vetor"' not in caplog.text


def test_diagnostico_captura_inconsistente_preserva_rejeicao(caplog):
    primeiro, diferente = quadro_sintetico(), quadro_sintetico(tipo=1)
    with caplog.at_level(logging.INFO, logger=LOGGER):
        with pytest.raises(biometria.BiometriaErro, match='diferem muito'):
            biometria.processar_captura([primeiro, diferente, primeiro])

    [diagnostico] = diagnosticos(caplog)
    assert diagnostico['evento'] == 'captura'
    assert diagnostico['aceita'] is False
    assert diagnostico['motivo'] == 'quadros_inconsistentes'
    assert diagnostico['maior_distancia_entre_quadros'] > diagnostico['limite_consistencia']
    assert len(diagnostico['qualidade_quadros']) == 3


def test_diagnostico_erro_de_captura_identifica_quadro_sem_expor_imagem(caplog):
    frame = quadro_sintetico()
    invalido = {**frame, 'largura': True}
    with caplog.at_level(logging.INFO, logger=LOGGER):
        with pytest.raises(biometria.BiometriaErro, match='Quadro 2: Largura e altura'):
            biometria.processar_captura([frame, invalido, frame])

    [diagnostico] = diagnosticos(caplog)
    assert diagnostico == {
        'evento': 'captura', 'aceita': False, 'quadro': 2,
        'motivo': 'Largura e altura devem ser números inteiros.',
    }
    assert frame['rgb_base64'] not in caplog.text


def test_diagnostico_fica_no_servidor_e_api_preserva_formato(api, captura, monkeypatch, caplog):
    monkeypatch.setattr(biometria, '_inferir_embedding', lambda _imagem: vetor_angular(0))
    assert cadastrar(api, captura).status_code == 201
    assert credenciais(api).status_code == 200
    with caplog.at_level(logging.INFO, logger=LOGGER):
        aceita = verificar(api, captura)

    assert aceita.status_code == 200, aceita.text
    assert set(aceita.json()) == {'usuario', 'processamento'}
    assert set(aceita.json()['processamento']['classificacao_interpretacao']) == CHAVES_RESULTADO
    assert 'biometria_diagnostico' not in aceita.text
    assert 'distancias_quadros' not in aceita.text

    monkeypatch.setattr(biometria, '_inferir_embedding', lambda _imagem: vetor_angular(60))
    assert credenciais(api).status_code == 200
    caplog.clear()
    with caplog.at_level(logging.INFO, logger=LOGGER):
        rejeitada = verificar(api, captura)

    assert rejeitada.status_code == 401, rejeitada.text
    assert set(rejeitada.json()) == {'detail'}
    assert 'boné' in rejeitada.json()['detail']
    assert 'chapéu' in rejeitada.json()['detail']
    assert 'distancias_quadros' not in rejeitada.text
    [comparacao] = [item for item in diagnosticos(caplog) if item['evento'] == 'comparacao']
    assert comparacao['motivo'] == 'fora_do_limiar'
    assert comparacao['identificado'] is False
