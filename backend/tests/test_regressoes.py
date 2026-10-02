"""Regressões: erros não conservam autenticação antiga no terminal."""
import pytest
from app.banco import DesafioBiometrico, Sessao
from tests.test_api import api, captura, cadastrar, autenticar, credenciais, contar, verificar


@pytest.mark.parametrize('etapa', ['credenciais', 'verificar'])
@pytest.mark.parametrize('estado', ['desafio', 'sessao'])
def test_schema_invalido_revoga_desafio_ou_sessao_anterior(api, captura, etapa, estado):
    assert cadastrar(api, captura).status_code == 201
    if estado == 'desafio':
        assert credenciais(api).status_code == 200
        nome_cookie = 'aps_desafio'
    else:
        assert autenticar(api, captura).status_code == 200
        nome_cookie = 'aps_sessao'
    token = api.client.cookies.get(nome_cookie)
    dados = {'cpf': 'invalido', 'senha': 'curta'} if etapa == 'credenciais' else {'frames': []}
    response = api.client.post(f'/api/autenticacao/{etapa}', json=dados)
    assert response.status_code == 422
    assert 'max-age=0' in response.headers.get('set-cookie', '').lower()
    assert contar(api, DesafioBiometrico) == contar(api, Sessao) == 0
    assert api.client.get('/api/sessao').status_code == 401
    if estado == 'desafio':
        replay = verificar(api, captura, headers={'Cookie': f'{nome_cookie}={token}'})
    else:
        replay = api.client.get('/api/sessao', headers={'Cookie': f'{nome_cookie}={token}'})
    assert replay.status_code == 401


def test_cliente_nao_pode_trocar_usuario_na_segunda_etapa(api, captura):
    assert cadastrar(api, captura).status_code == 201
    assert credenciais(api).status_code == 200
    response = verificar(api, {**captura, 'usuario_id': 999})
    assert response.status_code == 422
    assert contar(api, DesafioBiometrico) == contar(api, Sessao) == 0


def test_logout_tambem_revoga_desafio_pendente(api, captura):
    assert cadastrar(api, captura).status_code == 201
    assert credenciais(api).status_code == 200
    token = api.client.cookies.get('aps_desafio')
    assert api.client.post('/api/sair').status_code == 200
    assert contar(api, DesafioBiometrico) == 0
    assert verificar(api, captura, headers={'Cookie': f'aps_desafio={token}'}).status_code == 401

