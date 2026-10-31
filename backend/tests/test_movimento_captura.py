"""Sequência de cadastro, captura direta no login e recusas antes de autenticar."""

import json
import logging
from unittest.mock import Mock

import numpy as np
import pytest
from sqlalchemy.orm import Session

import app.biometria as biometria
from app.banco import DesafioBiometrico, Sessao, Usuario
from tests.test_api import api, captura, cadastrar, contar, credenciais, gerenciar, verificar
from tests.test_biometria import captura_sintetica, quadro_sintetico


@pytest.mark.parametrize('poses', [
    (0, -0.10, 0.10),
    (0, -0.10, 0.10, -0.05),
    (0, -0.10, 0.10, -0.05, 0.05),
])
def test_cadastro_aceita_sequencia_ordenada_sem_expor_poses_na_assinatura(poses, caplog):
    with caplog.at_level(logging.INFO, logger='uvicorn.error.biometria'):
        assinatura, resumo = biometria.processar_captura(captura_sintetica(poses=poses)['frames'])

    assert len(assinatura['amostras']) == len(poses)
    assert resumo['quadros'] == len(poses)
    assert set(assinatura) == {'versao', 'algoritmo', 'dimensao', 'vetor', 'amostras'}
    assert not any('pose' in chave or 'movimento' in chave for chave in resumo)
    registros = [
        json.loads(record.getMessage().split('biometria_diagnostico ', 1)[1])
        for record in caplog.records
        if record.name == 'uvicorn.error.biometria'
        and record.getMessage().startswith('biometria_diagnostico ')
    ]
    [movimento] = [registro for registro in registros if registro['evento'] == 'movimento']
    assert movimento['aceita'] is True
    assert movimento['poses_horizontais'] == pytest.approx(poses, abs=1e-6)


@pytest.mark.parametrize('indices', [(0, 0, 1), (0, 1, 0), (0, 1, 2, 0)])
def test_cadastro_rejeita_quadros_repetidos_inclusive_nao_consecutivos(indices, monkeypatch):
    frames = captura_sintetica()['frames']
    inferencia = Mock(side_effect=AssertionError('Não deve extrair assinatura de quadros repetidos.'))
    monkeypatch.setattr(biometria, '_inferir_embedding', inferencia)

    with pytest.raises(biometria.BiometriaErro, match='mesma imagem'):
        biometria.processar_captura([frames[indice] for indice in indices])

    inferencia.assert_not_called()


def test_cadastro_prioriza_iluminacao_sobre_movimento_em_quadros_escuros_repetidos(monkeypatch):
    frame = quadro_sintetico(brilho=-255)
    inferencia = Mock(side_effect=AssertionError('Imagem escura não deve chegar à inferência.'))
    monkeypatch.setattr(biometria, '_inferir_embedding', inferencia)

    with pytest.raises(biometria.BiometriaErro, match='pouca iluminação'):
        biometria.processar_captura([frame] * 3)

    inferencia.assert_not_called()


def test_cadastro_prioriza_segundo_rosto_sobre_movimento_em_quadros_repetidos(monkeypatch):
    frame = quadro_sintetico()
    detectar = biometria._detectar_faces
    monkeypatch.setattr(biometria, '_detectar_faces', lambda rgb: np.repeat(detectar(rgb), 2, axis=0))
    inferencia = Mock(side_effect=AssertionError('Dois rostos não devem chegar à inferência.'))
    monkeypatch.setattr(biometria, '_inferir_embedding', inferencia)

    with pytest.raises(biometria.BiometriaErro, match='apenas um rosto'):
        biometria.processar_captura([frame] * 3)

    inferencia.assert_not_called()


@pytest.mark.parametrize('poses,mensagem', [
    ((0, 0, 0), 'sua direita'),
    ((0, -0.10, -0.15), 'sua esquerda'),
    ((0, 0.10, -0.10), 'sua direita'),
    ((0, -0.05, 0.10), 'sua direita'),
    ((0, -0.10, 0.05), 'sua esquerda'),
    ((0.20, 0.10, 0.30), 'olhando de frente'),
    ((0, -0.10, 0.40), 'apenas levemente'),
    ((0, -0.10, 0.10, 0.40), 'apenas levemente'),
])
def test_cadastro_rejeita_movimento_ausente_lado_errado_ou_excessivo(poses, mensagem, monkeypatch):
    inferencia = Mock(side_effect=AssertionError('Movimento inválido não deve chegar à inferência.'))
    monkeypatch.setattr(biometria, '_inferir_embedding', inferencia)

    with pytest.raises(biometria.BiometriaErro, match=mensagem):
        biometria.processar_captura(captura_sintetica(poses=poses)['frames'])

    inferencia.assert_not_called()


def test_pose_horizontal_e_invariante_a_translacao_e_escala(monkeypatch):
    rgb = biometria.sensoriamento(quadro_sintetico(largura=640, altura=480))
    pontos = biometria._PONTOS_ALINHAMENTO / 112 * [160, 200]
    eixo = pontos[1] - pontos[0]
    centro = (pontos[0] + pontos[1]) / 2
    pose = -0.10
    atual = np.dot(pontos[2] - centro, eixo) / np.dot(eixo, eixo)
    pontos[2] += (pose - atual) * eixo
    medidas = []
    for escala, translacao in [(1.0, [100, 70]), (1.4, [180, 100])]:
        transformados = pontos * escala + translacao
        face = np.array([[
            *translacao, 160 * escala, 200 * escala, *transformados.reshape(-1), 0.99,
        ]])
        monkeypatch.setattr(biometria, '_detectar_faces', lambda _rgb, face=face: face)
        segmento = biometria.segmentacao(biometria.pre_processamento(rgb))
        medidas.append(segmento['pose_horizontal'])

    assert medidas == pytest.approx([pose, pose], abs=1e-10)


def test_login_direto_aceita_burst_identico_mas_cadastro_exige_movimento(api, captura):
    frame = quadro_sintetico()
    estatica = {'frames': [frame] * 3}
    rejeitada = cadastrar(api, estatica)
    assert rejeitada.status_code == 422, rejeitada.text
    assert 'mesma imagem' in rejeitada.json()['detail']
    assert contar(api, Usuario) == contar(api, Sessao) == 0

    assert cadastrar(api, captura).status_code == 201
    assert credenciais(api).status_code == 200
    aceita = verificar(api, estatica)

    assert aceita.status_code == 200, aceita.text
    assert contar(api, Sessao) == 1
    assert contar(api, DesafioBiometrico) == 0


@pytest.mark.parametrize('indice', [0, 1, 2])
@pytest.mark.parametrize('operacao', ['cadastro', 'recadastro', 'login'])
def test_segundo_rosto_em_qualquer_quadro_impede_gravacao_e_autenticacao(
    api, captura, monkeypatch, indice, operacao,
):
    anterior = None
    if operacao != 'cadastro':
        assert cadastrar(api, captura).status_code == 201
        with Session(api.engine) as db:
            anterior = db.get(Usuario, 1).assinatura_cifrada
    if operacao == 'login':
        assert credenciais(api).status_code == 200
        desafio = api.client.cookies.get('aps_desafio')

    detectar = biometria._detectar_faces
    alvo = biometria.sensoriamento(captura['frames'][indice])[0, 0].copy()

    def detectar_com_segundo_rosto(rgb):
        faces = detectar(rgb)
        return np.concatenate([faces, faces]) if np.array_equal(rgb[0, 0], alvo) else faces

    inferencia = Mock(side_effect=AssertionError('Dois rostos não devem chegar à extração.'))
    monkeypatch.setattr(biometria, '_detectar_faces', detectar_com_segundo_rosto)
    monkeypatch.setattr(biometria, '_inferir_embedding', inferencia)

    if operacao == 'cadastro':
        resposta = cadastrar(api, captura)
    elif operacao == 'recadastro':
        resposta = gerenciar(api, 'PUT', '/api/usuarios/1/biometria', json=captura)
    else:
        resposta = verificar(api, captura)

    assert resposta.status_code == 422, resposta.text
    assert f'Quadro {indice + 1}' in resposta.json()['detail']
    assert 'apenas um rosto' in resposta.json()['detail']
    assert contar(api, Sessao) == 0
    assert not api.client.cookies.get('aps_sessao')
    inferencia.assert_not_called()
    if operacao == 'cadastro':
        assert contar(api, Usuario) == 0
    else:
        with Session(api.engine) as db:
            assert db.get(Usuario, 1).assinatura_cifrada == anterior
    if operacao == 'login':
        assert api.client.cookies.get('aps_desafio') == desafio
        assert contar(api, DesafioBiometrico) == 1


@pytest.mark.parametrize('nivel,mensagem', [(0, 'pouca iluminação'), (255, 'iluminação excessiva')])
def test_qualidade_distingue_pouca_luz_e_luz_excessiva_com_rosto(nivel, mensagem):
    with pytest.raises(biometria.BiometriaErro, match=mensagem):
        biometria.segmentacao(biometria.pre_processamento(np.full((240, 320, 3), nivel, np.uint8)))


@pytest.mark.parametrize('nivel,mensagem', [(0, 'muito escura'), (255, 'muito clara'), (120, 'Nenhum rosto')])
def test_ausencia_de_rosto_informa_luz_quando_imagem_impede_deteccao(nivel, mensagem, monkeypatch):
    monkeypatch.setattr(biometria, '_detectar_faces', lambda _rgb: np.empty((0, 15)))
    with pytest.raises(biometria.BiometriaErro, match=mensagem):
        biometria.segmentacao(biometria.pre_processamento(np.full((240, 320, 3), nivel, np.uint8)))


def test_qualidade_rejeita_reflexos_saturados_mesmo_com_media_aceitavel():
    barras = ((np.indices((240, 320))[1] // 20) % 2 * 255).astype(np.uint8)
    rgb = np.repeat(barras[:, :, None], 3, axis=2)
    with pytest.raises(biometria.BiometriaErro, match='pixels saturados'):
        biometria.segmentacao(biometria.pre_processamento(rgb))
