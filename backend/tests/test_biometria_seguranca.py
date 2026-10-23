import copy
from dataclasses import replace
import hashlib

import numpy as np
from pydantic import ValidationError
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

import app.biometria as biometria
from app.biometria import _detectar_faces as detector_real
from app.biometria import _inferir_embedding as inferencia_real
import app.modelos_faciais as modelos
from app.banco import DesafioBiometrico, LogAcesso, Sessao, Usuario
from app.config import Settings
from tests.test_api import (
    CHAVE_TESTE, api, captura, cadastrar, contar, credenciais, gerenciar, verificar,
)


def vetor_angular(graus):
    angulo = np.deg2rad(graus)
    vetor = np.zeros(512, dtype=np.float64)
    vetor[:2] = [np.cos(angulo), np.sin(angulo)]
    return vetor


def assinatura_angular(graus):
    return {'versao': biometria.VERSAO, 'algoritmo': biometria.ALGORITMO,
            'dimensao': 512, 'vetor': vetor_angular(graus).tolist()}


def assert_sem_autenticacao(api):
    assert contar(api, Sessao) == 0
    assert contar(api, DesafioBiometrico) == 0
    assert not api.client.cookies.get('aps_sessao')
    assert not api.client.cookies.get('aps_desafio')
    assert api.client.get('/api/sessao').status_code == 401


def test_recadastro_durante_inferencia_nao_emite_sessao_com_assinatura_antiga(api, captura, monkeypatch):
    assert cadastrar(api, captura).status_code == 201
    assert credenciais(api).status_code == 200
    from app import main
    processar = main.processar_captura
    trocas = []

    def processar_com_troca_concorrente(frames):
        assinatura, resumo = processar(frames)
        with Session(api.engine) as db:
            usuario = db.get(Usuario, 1)
            original = usuario.assinatura_cifrada
            mesma_identidade = api.seguranca.decifrar(original, usuario.biometria_ref, 'biometria')
            usuario.assinatura_cifrada = api.seguranca.cifrar(
                mesma_identidade, usuario.biometria_ref, 'biometria')
            assert usuario.assinatura_cifrada != original
            db.commit()
            trocas.append(True)
        return assinatura, resumo

    monkeypatch.setattr(main, 'processar_captura', processar_com_troca_concorrente)

    resposta = verificar(api, captura)

    assert resposta.status_code == 401, resposta.text
    assert trocas == [True]
    assert_sem_autenticacao(api)
    with Session(api.engine) as db:
        assert db.scalar(select(LogAcesso.motivo).order_by(LogAcesso.id.desc()).limit(1)) == 'desafio_invalidado'


def test_template_mobilenet_legado_exige_recadastro_e_falha_fechado(api, captura):
    assert cadastrar(api, captura).status_code == 201
    legado = {'versao': 2, 'algoritmo': 'mobilenetv2', 'dimensao': 1280,
              'vetor': [1.0] + [0.0] * 1279}
    with Session(api.engine) as db:
        usuario = db.get(Usuario, 1)
        usuario.assinatura_cifrada = api.seguranca.cifrar(legado, usuario.biometria_ref, 'biometria')
        db.commit()
        original = usuario.assinatura_cifrada
    assert credenciais(api).status_code == 200

    resposta = verificar(api, captura)

    assert resposta.status_code == 503, resposta.text
    assert_sem_autenticacao(api)
    with Session(api.engine) as db:
        assert db.get(Usuario, 1).assinatura_cifrada == original
        assert 'assinatura_invalida' in db.scalars(select(LogAcesso.motivo)).all()


@pytest.mark.parametrize('artefato', ['detector', 'reconhecedor'])
@pytest.mark.parametrize('estado', ['ausente', 'corrompido'])
def test_modelo_ausente_ou_checksum_invalido_retorna_503_sem_fallback(
        api, captura, monkeypatch, tmp_path, artefato, estado):
    assert cadastrar(api, captura).status_code == 201
    assert credenciais(api).status_code == 200
    monkeypatch.setattr(modelos, 'DIRETORIO_MODELOS', tmp_path)
    esperado = b'artefato-modelo-sintetico-valido!!'
    nome = '_DETECTOR' if artefato == 'detector' else '_RECONHECEDOR'
    especificacao = replace(getattr(modelos, nome), tamanho=len(esperado),
                            sha256=hashlib.sha256(esperado).hexdigest())
    monkeypatch.setattr(modelos, nome, especificacao)
    if estado == 'corrompido':
        corrompido = bytes([esperado[0] ^ 1]) + esperado[1:]
        (tmp_path / especificacao.arquivo).write_bytes(corrompido)
    if artefato == 'detector':
        monkeypatch.setattr(modelos, '_detector', None)
        monkeypatch.setattr(biometria, '_detectar_faces', detector_real)
    else:
        monkeypatch.setattr(modelos, '_sessao', None)
        monkeypatch.setattr(biometria, '_inferir_embedding', inferencia_real)

    resposta = verificar(api, captura)

    assert resposta.status_code == 503, resposta.text
    assert_sem_autenticacao(api)
    with Session(api.engine) as db:
        assert 'modelo_indisponivel' in db.scalars(select(LogAcesso.motivo)).all()


@pytest.mark.parametrize('campo', ['vetor', 'assinatura', 'frame_vetor'])
def test_cliente_nao_pode_submeter_embedding_no_lugar_da_extracao_servidor(api, captura, campo):
    assert cadastrar(api, captura).status_code == 201
    assert credenciais(api).status_code == 200
    forjada = copy.deepcopy(captura)
    if campo == 'frame_vetor':
        forjada['frames'][0]['vetor'] = vetor_angular(0).tolist()
    else:
        forjada[campo] = assinatura_angular(0) if campo == 'assinatura' else vetor_angular(0).tolist()

    resposta = verificar(api, forjada)

    assert resposta.status_code == 422, resposta.text
    assert_sem_autenticacao(api)


def test_admin_tambem_nao_pode_substituir_biometria_com_vetor_enviado_pelo_cliente(api, captura):
    assert cadastrar(api, captura).status_code == 201
    with Session(api.engine) as db:
        original = db.get(Usuario, 1).assinatura_cifrada

    resposta = gerenciar(api, 'PUT', '/api/usuarios/1/biometria',
                         json={**captura, 'vetor': vetor_angular(0).tolist()})

    assert resposta.status_code == 422, resposta.text
    with Session(api.engine) as db:
        assert db.get(Usuario, 1).assinatura_cifrada == original


@pytest.mark.parametrize('limiar', [0.400001, 0.5, 1.0])
def test_configuracao_nao_permite_relaxar_limiar_acima_do_maximo(limiar):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, biometric_key=CHAVE_TESTE, face_threshold=limiar)
    with pytest.raises(biometria.BiometriaErro):
        biometria.classificacao_interpretacao(assinatura_angular(0), [('1', assinatura_angular(0))],
                                            limiar=limiar)


def test_um_quadro_fora_do_limiar_nao_e_aceito_pela_media_dos_outros(api, captura, monkeypatch):
    monkeypatch.setattr(biometria, '_inferir_embedding', lambda _imagem: vetor_angular(0))
    assert cadastrar(api, captura).status_code == 201
    assert credenciais(api).status_code == 200
    amostras = [vetor_angular(25), vetor_angular(25), vetor_angular(50)]
    media = np.mean(amostras, axis=0)
    media /= np.linalg.norm(media)
    assinatura_media = {**assinatura_angular(0), 'vetor': media.tolist()}
    assert biometria.comparar_assinaturas(assinatura_media, assinatura_angular(0)) < api.settings.face_threshold
    assert biometria.comparar_assinaturas(assinatura_angular(50), assinatura_angular(0)) > api.settings.face_threshold
    assert biometria.comparar_assinaturas(assinatura_angular(25), assinatura_angular(50)) < biometria.LIMITE_CONSISTENCIA
    restantes = iter(amostras)
    monkeypatch.setattr(biometria, '_inferir_embedding', lambda _imagem: next(restantes))

    resposta = verificar(api, captura)

    assert resposta.status_code == 401, resposta.text
    assert_sem_autenticacao(api)
    with Session(api.engine) as db:
        assert 'face_nao_corresponde' in db.scalars(select(LogAcesso.motivo)).all()
