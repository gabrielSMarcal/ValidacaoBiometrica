import base64
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.banco import Base, DesafioBiometrico, LogAcesso, Sessao, Usuario, agora
from app.config import Settings
from app.inicializar import garantir_administrador
from app.seguranca import Seguranca, hash_token


CHAVE = base64.urlsafe_b64encode(bytes(range(32))).decode()
CPF_ADMIN = '12345678909'
CPF_VITIMA = '52998224725'
CPF_OPERADOR = '11144477735'
SENHA = 'Senha-autorizacao-sintetica-2026!'
CAPTURA = {'frames': [{'largura': 160, 'altura': 120, 'rgb_base64': 'AAAA'}] * 3}
CADASTRO = {**CAPTURA, 'nome': 'Novo cadastro', 'cpf': '98765432100', 'senha': SENHA, 'nivel': 2}
OPERACOES = [
    ('post', '/api/usuarios', CADASTRO),
    ('get', '/api/usuarios', None),
    ('patch', '/api/usuarios/2', {'senha': 'Outra-senha-sintetica-2026!', 'nivel': 3}),
    ('put', '/api/usuarios/2/biometria', CAPTURA),
    ('delete', '/api/usuarios/2', None),
]


@pytest.fixture(scope='module')
def hash_senha():
    return Seguranca(CHAVE).senhas.hash(SENHA)


@pytest.fixture
def api_autorizacao(monkeypatch, hash_senha):
    monkeypatch.setitem(Settings.model_config, 'env_file', None)
    monkeypatch.setenv('BIOMETRIC_KEY', CHAVE)
    from app.main import criar_app

    settings = Settings(_env_file=None, biometric_key=CHAVE, rate_limit_per_minute=300,
                        admin_cpf=CPF_ADMIN, admin_password_hash=hash_senha)
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)

    @event.listens_for(engine, 'connect')
    def ativar_fks(connection, _record):
        connection.execute('PRAGMA foreign_keys=ON')

    Base.metadata.create_all(engine)
    garantir_administrador(engine, settings)
    seguranca = Seguranca(CHAVE)
    assinatura = {'dimensao': 512, 'vetor': [1.0] + [0.0] * 511, 'modelo': 'modelo-de-teste'}
    with Session(engine) as db:
        for cpf, nome in [(CPF_VITIMA, 'Cadastro original'), (CPF_OPERADOR, 'Usuário comum')]:
            referencia = str(uuid4())
            db.add(Usuario(
                biometria_ref=referencia, nome=nome, cpf_indice=seguranca.indice_cpf(cpf),
                cpf_cifrado=seguranca.cifrar({'cpf': cpf}, referencia, 'cpf'),
                senha_hash=hash_senha, nivel=2,
                assinatura_cifrada=seguranca.cifrar(assinatura, referencia, 'biometria'),
            ))
        db.commit()

    processamento = Mock(return_value=(
        {**assinatura, 'vetor': [0.0, 1.0] + [0.0] * 510}, {'modelo': 'modelo-de-teste'}))
    monkeypatch.setattr('app.main.processar_captura', processamento)
    with TestClient(criar_app(settings, engine)) as client:
        yield SimpleNamespace(client=client, engine=engine, seguranca=seguranca,
                              processamento=processamento)
    engine.dispose()


def requisitar(api, operacao):
    metodo, caminho, dados = operacao
    return api.client.request(metodo, caminho, **({'json': dados} if dados is not None else {}))


def iniciar_admin(api):
    resposta = api.client.post('/api/autenticacao/credenciais', json={'cpf': CPF_ADMIN, 'senha': SENHA})
    assert resposta.status_code == 200, resposta.text
    assert api.client.cookies.get('aps_sessao') and not api.client.cookies.get('aps_desafio')


def criar_sessao(api, usuario_id, token='token-sintetico-sessao', expirada=False):
    with Session(api.engine) as db:
        db.add(Sessao(token_hash=hash_token(token), usuario_id=usuario_id,
                      expira_em=agora() + timedelta(minutes=-1 if expirada else 5)))
        db.commit()
    api.client.cookies.set('aps_sessao', token)
    return token


def snapshot_usuarios(api):
    with Session(api.engine) as db:
        return [(user.id, user.nome, user.nivel, user.ativo, user.senha_hash, user.assinatura_cifrada)
                for user in db.scalars(select(Usuario).order_by(Usuario.id))]


@pytest.mark.parametrize('operacao', OPERACOES, ids=['cadastro', 'lista', 'alteracao', 'biometria', 'exclusao'])
@pytest.mark.parametrize('acesso', ['ausente', 'forjado', 'expirado', 'inativo', 'desafio', 'desafio_como_sessao'])
def test_crud_exige_sessao_administrativa_ativa(api_autorizacao, operacao, acesso):
    api = api_autorizacao
    if acesso in ('expirado', 'inativo'):
        criar_sessao(api, 1, expirada=acesso == 'expirado')
    if acesso == 'inativo':
        with Session(api.engine) as db:
            db.get(Usuario, 1).ativo = False
            db.commit()
    if acesso == 'forjado':
        api.client.cookies.set('aps_sessao', 'sessao-inexistente')
    if acesso in ('desafio', 'desafio_como_sessao'):
        resposta = api.client.post('/api/autenticacao/credenciais', json={'cpf': CPF_OPERADOR, 'senha': SENHA})
        assert resposta.status_code == 200
        assert not api.client.cookies.get('aps_sessao')
        if acesso == 'desafio_como_sessao':
            api.client.cookies.set('aps_sessao', api.client.cookies.get('aps_desafio'))
    antes = snapshot_usuarios(api)

    resposta = requisitar(api, operacao)

    assert resposta.status_code == 401, resposta.text
    assert snapshot_usuarios(api) == antes
    api.processamento.assert_not_called()
    with Session(api.engine) as db:
        assert 'sessao_invalida' in db.scalars(select(LogAcesso.motivo)).all()


@pytest.mark.parametrize('operacao', OPERACOES, ids=['cadastro', 'lista', 'alteracao', 'biometria', 'exclusao'])
@pytest.mark.parametrize('nivel', [1, 2, 3])
def test_usuarios_comuns_nao_podem_gerenciar_outros_usuarios(api_autorizacao, operacao, nivel):
    api = api_autorizacao
    with Session(api.engine) as db:
        db.get(Usuario, 3).nivel = nivel
        db.commit()
    criar_sessao(api, 3)
    antes = snapshot_usuarios(api)

    resposta = requisitar(api, operacao)

    assert resposta.status_code == 403, resposta.text
    assert snapshot_usuarios(api) == antes
    api.processamento.assert_not_called()
    with Session(api.engine) as db:
        assert db.scalar(select(LogAcesso.motivo)) == 'nivel_insuficiente'


def test_admin_autenticado_mantem_crud_e_formatos_de_resposta(api_autorizacao):
    api = api_autorizacao
    iniciar_admin(api)
    resposta = api.client.post('/api/usuarios', json=CADASTRO)
    assert resposta.status_code == 201, resposta.text
    assert set(resposta.json()) == {'usuario', 'processamento'}
    usuario_id = resposta.json()['usuario']['id']
    assert resposta.json()['usuario']['nivel'] == 2

    lista = api.client.get('/api/usuarios')
    assert lista.status_code == 200
    assert set(lista.json()) == {'usuarios'}
    usuario = next(user for user in lista.json()['usuarios'] if user['id'] == usuario_id)
    assert set(usuario) == {'id', 'nome', 'nivel', 'ativo', 'criado_em'}
    alteracao = api.client.patch(f'/api/usuarios/{usuario_id}', json={'nome': 'Nome alterado', 'nivel': 3})
    assert alteracao.status_code == 200
    assert alteracao.json()['usuario']['nome'] == 'Nome alterado'
    assert alteracao.json()['usuario']['nivel'] == 3
    biometria = api.client.put(f'/api/usuarios/{usuario_id}/biometria', json=CAPTURA)
    assert biometria.status_code == 200
    assert set(biometria.json()) == {'usuario', 'processamento'}
    exclusao = api.client.delete(f'/api/usuarios/{usuario_id}')
    assert exclusao.status_code == 204 and exclusao.content == b''


def test_troca_biometrica_autorizada_revoga_sessoes_e_desafios_da_vitima(api_autorizacao):
    api = api_autorizacao
    token_sessao = criar_sessao(api, 2)
    api.client.cookies.clear()
    credenciais = api.client.post('/api/autenticacao/credenciais', json={'cpf': CPF_VITIMA, 'senha': SENHA})
    assert credenciais.status_code == 200
    token_desafio = api.client.cookies.get('aps_desafio')
    api.client.cookies.clear()
    iniciar_admin(api)
    token_admin = api.client.cookies.get('aps_sessao')
    with Session(api.engine) as db:
        original = db.get(Usuario, 2).assinatura_cifrada
        assert db.get(Sessao, hash_token(token_sessao)) is not None
        assert db.get(DesafioBiometrico, hash_token(token_desafio)) is not None

    resposta = api.client.put('/api/usuarios/2/biometria', json=CAPTURA)

    assert resposta.status_code == 200, resposta.text
    with Session(api.engine) as db:
        assert db.get(Usuario, 2).assinatura_cifrada != original
        assert db.get(Sessao, hash_token(token_sessao)) is None
        assert db.get(DesafioBiometrico, hash_token(token_desafio)) is None
        assert db.get(Sessao, hash_token(token_admin)) is not None
    api.client.cookies.clear()
    api.client.cookies.set('aps_sessao', token_sessao)
    assert api.client.get('/api/sessao').status_code == 401
    api.client.cookies.set('aps_desafio', token_desafio)
    assert api.client.post('/api/autenticacao/verificar', json=CAPTURA).status_code == 401


@pytest.mark.parametrize('operacao', [
    ('patch', '/api/usuarios/1', {'nivel': 1}),
    ('put', '/api/usuarios/1/biometria', CAPTURA),
    ('delete', '/api/usuarios/1', None),
])
def test_admin_continua_protegido_apos_autorizacao(api_autorizacao, operacao):
    api = api_autorizacao
    iniciar_admin(api)
    antes = snapshot_usuarios(api)
    assert requisitar(api, operacao).status_code == 403
    assert snapshot_usuarios(api) == antes
    api.processamento.assert_not_called()


def test_autorizacao_nao_introduz_parametros_publicos_no_openapi(api_autorizacao):
    schema = api_autorizacao.client.get('/openapi.json').json()
    for metodo, caminho, _ in OPERACOES:
        caminho = caminho.replace('/2', '/{usuario_id}')
        operacao = schema['paths'][caminho][metodo]
        parametros = operacao.get('parameters', [])
        assert all(parametro['in'] == 'path' and parametro['name'] == 'usuario_id' for parametro in parametros)
        assert 'security' not in operacao
