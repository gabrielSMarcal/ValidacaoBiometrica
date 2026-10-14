"""Confidencialidade e integridade; não requer banco nem dados pessoais reais."""

import base64

from cryptography.exceptions import InvalidTag
import pytest

from app.seguranca import Seguranca, hash_token


@pytest.fixture(scope='module')
def seguranca():
    return Seguranca(base64.urlsafe_b64encode(bytes(range(32))).decode())


def test_cifra_roundtrip_unicode_e_nonce_distinto(seguranca):
    original = {'algoritmo': 'didático', 'vetor': [0.25, 0.75]}
    primeiro = seguranca.cifrar(original, 'usuario-a', 'biometria')
    segundo = seguranca.cifrar(original, 'usuario-a', 'biometria')
    assert isinstance(primeiro, bytes)
    assert primeiro != segundo
    assert b'algoritmo' not in primeiro and b'vetor' not in primeiro
    assert seguranca.decifrar(primeiro, 'usuario-a', 'biometria') == original
    assert seguranca.decifrar(segundo, 'usuario-a', 'biometria') == original


def test_alteracao_ciphertext_e_contexto_nao_autenticam(seguranca):
    blob = seguranca.cifrar({'vetor': [0.25, 0.75]}, 'usuario-a', 'biometria')
    alterado = bytearray(blob)
    alterado[-1] ^= 1
    with pytest.raises(InvalidTag):
        seguranca.decifrar(bytes(alterado), 'usuario-a', 'biometria')
    with pytest.raises(InvalidTag):
        seguranca.decifrar(blob, 'usuario-b', 'biometria')
    with pytest.raises(InvalidTag):
        seguranca.decifrar(blob, 'usuario-a', 'cpf')


def test_outra_chave_nao_descriptografa(seguranca):
    blob = seguranca.cifrar({'vetor': [1.0]}, 'usuario-a', 'biometria')
    outra = Seguranca(base64.urlsafe_b64encode(b'x' * 32).decode())
    with pytest.raises(InvalidTag):
        outra.decifrar(blob, 'usuario-a', 'biometria')


@pytest.mark.parametrize('blob', [b'', b'APS1', b'????' + b'x' * 40, 'nao-sao-bytes'])
def test_envelope_invalido_e_rejeitado(seguranca, blob):
    with pytest.raises(ValueError):
        seguranca.decifrar(blob, 'usuario-a', 'biometria')


def test_descompactacao_tem_limite_mesmo_com_cifra_valida(seguranca):
    blob = seguranca.cifrar({'campo': 'x' * 1_000_001}, 'usuario-a', 'biometria')
    with pytest.raises(ValueError, match='limite'):
        seguranca.decifrar(blob, 'usuario-a', 'biometria')


def test_senha_usa_hash_argon2id_e_nao_criptografia_reversivel(seguranca):
    senha = 'Senha-sintetica-para-teste!'
    hashed = seguranca.senhas.hash(senha)
    assert hashed.startswith('$argon2id$')
    assert senha not in hashed
    assert seguranca.verificar_senha(senha, hashed)
    assert not seguranca.verificar_senha('senha-errada', hashed)
    assert not seguranca.verificar_senha(senha, None)
    assert not seguranca.verificar_senha(senha, 'hash-corrompido')


def test_indices_nao_guardam_identificadores_em_claro(seguranca):
    cpf = '52998224725'  # Sequência sintética comum em testes de dígitos verificadores.
    indice = seguranca.indice_cpf(cpf)
    assert len(indice) == 64
    assert indice == seguranca.indice_cpf(cpf)
    assert cpf not in indice
    assert indice != seguranca.indice_cpf('11144477735')
    token = 'token-aleatorio-de-sessao'
    assert len(hash_token(token)) == 64 and token not in hash_token(token)
