"""FastAPI/SQLite com foreign keys e pipeline NumPy real sobre texturas sintéticas."""
import base64
from datetime import timedelta
import json
import secrets
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient
from httpx import Cookies
import pytest
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.banco import Base, DesafioBiometrico, LogAcesso, Sessao, Usuario, agora
from app.biometria import DIMENSAO
from app.config import Settings
from app.seguranca import Seguranca, hash_token
from tests.test_biometria import quadro_sintetico

CHAVE_TESTE = base64.urlsafe_b64encode(bytes(range(32))).decode()
SENHA_TESTE = 'Senha-sintetica-2026!'
CPF_TESTE, OUTRO_CPF = '52998224725', '11144477735'


@pytest.fixture
def api(monkeypatch):
    # Desabilita inclusive leitura implícita do .env na instância ASGI padrão.
    monkeypatch.setitem(Settings.model_config, 'env_file', None)
    monkeypatch.setenv('BIOMETRIC_KEY', CHAVE_TESTE)
    from app.main import criar_app
    settings = Settings(_env_file=None, biometric_key=CHAVE_TESTE, rate_limit_per_minute=300)
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)

    @event.listens_for(engine, 'connect')
    def ativar_fks(connection, _record):
        cursor = connection.cursor()
        cursor.execute('PRAGMA foreign_keys=ON')
        cursor.close()

    Base.metadata.create_all(engine)
    with TestClient(criar_app(settings, engine)) as client:
        yield SimpleNamespace(client=client, engine=engine, settings=settings, seguranca=Seguranca(CHAVE_TESTE))
    engine.dispose()


@pytest.fixture(scope='module')
def captura():
    return {'frames': [quadro_sintetico()] * 3}


@pytest.fixture(scope='module')
def outra_captura():
    return {'frames': [quadro_sintetico(tipo=1)] * 3}


def gerenciar(api, metodo, rota, **kwargs):
    """Executa CRUD com administrador e sessão reais, sem substituir dependências."""
    token = secrets.token_urlsafe(32)
    token_hash = hash_token(token)
    cookies_antes = Cookies(api.client.cookies)
    with Session(api.engine) as db:
        administrador = db.scalar(select(Usuario).where(Usuario.nivel == 4))
        temporario = administrador is None
        if temporario:
            referencia = str(uuid4())
            cpf = '39053344705'
            administrador = Usuario(
                id=0, biometria_ref=referencia, nome='Administrador de teste',
                cpf_indice=api.seguranca.indice_cpf(cpf),
                cpf_cifrado=api.seguranca.cifrar({'cpf': cpf}, referencia, 'cpf'),
                senha_hash=api.seguranca.hash_ficticio, assinatura_cifrada=None,
                nivel=4, ativo=True,
            )
            db.add(administrador)
            db.flush()
        administrador_id = administrador.id
        db.add(Sessao(token_hash=token_hash, usuario_id=administrador_id,
                      expira_em=agora() + timedelta(minutes=5)))
        db.commit()
    try:
        headers = {**kwargs.pop('headers', {}), 'Cookie': f'aps_sessao={token}'}
        return api.client.request(metodo, rota, headers=headers, **kwargs)
    finally:
        api.client.cookies = cookies_antes
        with Session(api.engine) as db:
            sessao = db.get(Sessao, token_hash)
            if sessao is not None:
                db.delete(sessao)
            if temporario:
                db.delete(db.get(Usuario, administrador_id))
            db.commit()


def cadastrar(api, captura, cpf=CPF_TESTE, nivel=2):
    return gerenciar(api, 'POST', '/api/usuarios', json={**captura, 'nome': 'Pessoa de Teste',
                           'cpf': cpf, 'senha': SENHA_TESTE, 'nivel': nivel})


def credenciais(api, cpf=CPF_TESTE, senha=SENHA_TESTE):
    return api.client.post('/api/autenticacao/credenciais', json={'cpf': cpf, 'senha': senha})


def verificar(api, captura, **kwargs):
    return api.client.post('/api/autenticacao/verificar', json=captura, **kwargs)


def autenticar(api, captura, cpf=CPF_TESTE):
    response = credenciais(api, cpf=cpf)
    assert response.status_code == 200, response.text
    return verificar(api, captura)


def contar(api, modelo):
    with Session(api.engine) as db:
        return db.scalar(select(func.count()).select_from(modelo))


def test_cadastro_pipeline_cifra_banco_e_logs_sem_dados_crus(api, captura):
    response = cadastrar(api, captura)
    assert response.status_code == 201, response.text
    assert response.json()['usuario'] == {'id': 1, 'nome': 'Pessoa de Teste', 'nivel': 2}
    assert len(response.json()['processamento']['etapas']) == 5
    with Session(api.engine) as db:
        user = db.scalar(select(Usuario))
        assert isinstance(user.assinatura_cifrada, bytes) and b'vetor' not in user.assinatura_cifrada
        sig = api.seguranca.decifrar(user.assinatura_cifrada, user.biometria_ref, 'biometria')
        assert sig['dimensao'] == len(sig['vetor']) == DIMENSAO == 512
        assert api.seguranca.decifrar(user.cpf_cifrado, user.biometria_ref, 'cpf') == {'cpf': CPF_TESTE}
        assert CPF_TESTE.encode() not in user.cpf_cifrado and CPF_TESTE not in user.cpf_indice
        assert api.seguranca.verificar_senha(SENHA_TESTE, user.senha_hash)
        assert SENHA_TESTE not in user.senha_hash
        logs = db.scalars(select(LogAcesso)).all()
        assert len(logs) == 1 and logs[0].sucesso
        assert logs[0].requisicao_id == response.headers['x-request-id']
        dados_logs = json.dumps([{c.name: str(getattr(log, c.name))
                                 for c in LogAcesso.__table__.columns} for log in logs])
        assert not any(s in dados_logs for s in [CPF_TESTE, SENHA_TESTE, 'rgb_base64', 'vetor'])
    assert not any(s in response.text for s in [CPF_TESTE, SENHA_TESTE, 'rgb_base64', '"vetor"'])


def test_cadastro_autorizado_ids_sequenciais_e_cpf_duplicado_rejeitado(api, captura):
    assert cadastrar(api, captura).json()['usuario']['id'] == 1
    assert cadastrar(api, captura, cpf=OUTRO_CPF).json()['usuario']['id'] == 2
    response = cadastrar(api, captura, cpf='529.982.247-25')
    assert response.status_code == 409 and contar(api, Usuario) == 2


def test_credenciais_emitem_apenas_desafio_curto_sem_autorizar_sessao(api, captura):
    assert cadastrar(api, captura).status_code == 201
    antes = agora()
    response = credenciais(api)
    assert response.status_code == 200 and response.json()['expira_em_segundos'] == 120
    token = api.client.cookies.get('aps_desafio')
    assert token and not api.client.cookies.get('aps_sessao')
    cookie = next(c for c in response.headers.get_list('set-cookie') if c.startswith('aps_desafio='))
    assert 'httponly' in cookie.lower() and 'samesite=strict' in cookie.lower() and 'Max-Age=120' in cookie
    assert 'usuario' not in response.json() and token not in response.text
    with Session(api.engine) as db:
        desafio = db.get(DesafioBiometrico, hash_token(token))
        assert desafio and desafio.usuario_id == 1 and desafio.token_hash != token
        assert antes + timedelta(seconds=119) <= desafio.expira_em <= agora() + timedelta(seconds=121)
    assert contar(api, Sessao) == 0
    assert api.client.get('/api/sessao').status_code == 401
    assert api.client.cookies.get('aps_desafio') == token


def test_login_administrador_retorna_usuario_e_inicia_sessao(api):
    with Session(api.engine) as db:
        administrador = db.scalar(select(Usuario).where(Usuario.nivel == 4))
        cpf = '39053344705'
        senha = 'Senha-admin-teste!'
        if administrador is None:
            referencia = str(uuid4())
            administrador = Usuario(
                biometria_ref=referencia, nome='Administrador de teste',
                cpf_indice=api.seguranca.indice_cpf(cpf),
                cpf_cifrado=api.seguranca.cifrar({'cpf': cpf}, referencia, 'cpf'),
                senha_hash=api.seguranca.senhas.hash(senha),
                assinatura_cifrada=None, nivel=4, ativo=True,
            )
            db.add(administrador)
        else:
            administrador.senha_hash = api.seguranca.senhas.hash(senha)
        db.commit()

    response = credenciais(api, cpf=cpf, senha=senha)

    assert response.status_code == 200
    assert response.json()['usuario']['nivel'] == 4
    assert api.client.cookies.get('aps_sessao')


def test_fluxo_dois_passos_nivel_sessao_e_logout(api, captura):
    assert cadastrar(api, captura, nivel=3).status_code == 201
    response = autenticar(api, captura)
    assert response.status_code == 200, response.text
    assert response.json()['usuario']['nivel'] == 3
    assert api.client.cookies.get('aps_desafio') is None and contar(api, DesafioBiometrico) == 0
    token = api.client.cookies.get('aps_sessao')
    with Session(api.engine) as db:
        assert db.get(Sessao, hash_token(token)) is not None
    sessao = api.client.get('/api/sessao')
    assert sessao.status_code == 200 and sessao.json()['mensagem'] == 'Você é do nível 3'
    assert api.client.post('/api/sair').status_code == 200
    assert contar(api, Sessao) == 0
    assert api.client.get('/api/sessao', headers={'Cookie': f'aps_sessao={token}'}).status_code == 401


def test_senha_errada_revoga_sessao_e_nao_emite_desafio(api, captura):
    assert cadastrar(api, captura).status_code == 201
    assert autenticar(api, captura).status_code == 200
    antigo = api.client.cookies.get('aps_sessao')
    assert credenciais(api, senha='incorreta').status_code == 401
    assert contar(api, Sessao) == contar(api, DesafioBiometrico) == 0
    assert api.client.get('/api/sessao', headers={'Cookie': f'aps_sessao={antigo}'}).status_code == 401
    assert credenciais(api, cpf=OUTRO_CPF).status_code == 401
    with Session(api.engine) as db:
        assert 'credenciais_invalidas' in db.scalars(select(LogAcesso.motivo)).all()


def test_rosto_sozinho_nao_autentica_e_antiga_rota_nao_existe(api, captura):
    assert cadastrar(api, captura).status_code == 201
    assert api.client.post('/api/autenticacao/identificar', json=captura).status_code == 404
    assert verificar(api, captura).status_code == 401
    assert contar(api, Sessao) == 0


def test_desafio_fixa_usuario_e_rosto_de_outro_cadastro_e_recusado(api, captura, outra_captura):
    assert cadastrar(api, captura).status_code == 201
    assert cadastrar(api, outra_captura, cpf=OUTRO_CPF).status_code == 201
    assert credenciais(api).status_code == 200
    token = api.client.cookies.get('aps_desafio')
    response = verificar(api, outra_captura)
    assert response.status_code == 401 and contar(api, Sessao) == 0
    assert contar(api, DesafioBiometrico) == 1
    assert api.client.cookies.get('aps_desafio') == token
    assert verificar(api, captura).status_code == 200
    assert autenticar(api, outra_captura, cpf=OUTRO_CPF).json()['usuario']['id'] == 2


def test_desafio_persiste_para_nova_tentativa_quando_captura_invalida(api, captura):
    assert cadastrar(api, captura).status_code == 201
    assert credenciais(api).status_code == 200
    token = api.client.cookies.get('aps_desafio')
    invalida = {'frames': [{'largura': 320, 'altura': 240, 'rgb_base64': 'buffer-invalido'}] * 3}
    assert verificar(api, invalida).status_code == 422
    assert contar(api, DesafioBiometrico) == 1
    assert api.client.cookies.get('aps_desafio') == token
    assert verificar(api, captura).status_code == 200
    assert contar(api, DesafioBiometrico) == 0


def test_desafio_expirado_e_replay_apos_sucesso_nao_autorizam(api, captura):
    assert cadastrar(api, captura).status_code == 201
    assert credenciais(api).status_code == 200
    with Session(api.engine) as db:
        db.scalar(select(DesafioBiometrico)).expira_em = agora() - timedelta(seconds=1)
        db.commit()
    assert verificar(api, captura).status_code == 401
    assert contar(api, DesafioBiometrico) == 0
    assert credenciais(api).status_code == 200
    token = api.client.cookies.get('aps_desafio')
    assert verificar(api, captura).status_code == 200
    api.client.cookies.clear()
    assert verificar(api, captura, headers={'Cookie': f'aps_desafio={token}'}).status_code == 401


@pytest.mark.parametrize('alteracao', ['inativo', 'senha'])
def test_desafio_invalida_quando_usuario_muda_apos_credenciais(api, captura, alteracao):
    assert cadastrar(api, captura).status_code == 201
    assert credenciais(api).status_code == 200
    with Session(api.engine) as db:
        user = db.get(Usuario, 1)
        if alteracao == 'inativo':
            user.ativo = False
        else:
            user.senha_hash = api.seguranca.senhas.hash('Outra-senha-de-teste!')
        db.commit()
    assert verificar(api, captura).status_code == 401
    assert contar(api, Sessao) == contar(api, DesafioBiometrico) == 0


def test_sessao_expirada_nao_autoriza(api, captura):
    assert cadastrar(api, captura).status_code == 201
    assert autenticar(api, captura).status_code == 200
    with Session(api.engine) as db:
        db.scalar(select(Sessao)).expira_em = agora() - timedelta(seconds=1)
        db.commit()
    assert api.client.get('/api/sessao').status_code == 401


def test_delete_sql_preserva_logs_e_remove_sessao_desafio_por_cascata(api, captura):
    assert cadastrar(api, captura).status_code == 201
    assert cadastrar(api, captura, cpf=OUTRO_CPF).status_code == 201
    assert autenticar(api, captura).status_code == 200
    token_sessao = api.client.cookies.get('aps_sessao')
    api.client.cookies.clear()  # Outro navegador inicia desafio sem revogar a sessão existente.
    assert credenciais(api).status_code == 200
    token_desafio = api.client.cookies.get('aps_desafio')
    with Session(api.engine) as db:
        logs_antes = list(db.scalars(select(LogAcesso.id).where(LogAcesso.usuario_id == 1)))
        assert db.scalar(select(func.count()).select_from(Sessao)) == 1
        assert db.scalar(select(func.count()).select_from(DesafioBiometrico)) == 1
        db.execute(text('DELETE FROM usuarios WHERE id = :id'), {'id': 1})
        db.commit()
        assert db.get(Usuario, 1) is None and db.get(Usuario, 2) is not None
        logs = db.scalars(select(LogAcesso).where(LogAcesso.id.in_(logs_antes))).all()
        assert len(logs) == len(logs_antes) and all(log.usuario_id is None for log in logs)
    assert contar(api, Sessao) == contar(api, DesafioBiometrico) == 0
    assert api.client.get('/api/sessao', headers={'Cookie': f'aps_sessao={token_sessao}'}).status_code == 401
    assert verificar(api, captura, headers={'Cookie': f'aps_desafio={token_desafio}'}).status_code == 401


def test_corrupcao_de_assinatura_falha_fechada_e_registra_evento(api, captura):
    assert cadastrar(api, captura).status_code == 201
    with Session(api.engine) as db:
        user = db.get(Usuario, 1)
        blob = bytearray(user.assinatura_cifrada)
        blob[-1] ^= 1
        user.assinatura_cifrada = bytes(blob)
        db.commit()
    assert credenciais(api).status_code == 200
    assert verificar(api, captura).status_code == 503
    assert contar(api, Sessao) == contar(api, DesafioBiometrico) == 0
    with Session(api.engine) as db:
        assert 'integridade_assinatura' in db.scalars(select(LogAcesso.motivo)).all()


def test_resposta_422_nao_retorna_senha_cpf_ou_pixels(api):
    senha, pixels = 'NAO_ECOAR_SENHA_PRIVADA', 'NAO_ECOAR_PIXELS_PRIVADOS'
    payload = {'nome': 'Pessoa de Teste', 'cpf': CPF_TESTE, 'senha': senha, 'nivel': 4,
               'frames': [{'largura': 320, 'altura': 240, 'rgb_base64': pixels}] * 3}
    response = gerenciar(api, 'POST', '/api/usuarios', json=payload)
    assert response.status_code == 422
    assert not any(s in response.text for s in [senha, pixels, CPF_TESTE, '"input"'])
    assert contar(api, Usuario) == 0


def test_origem_externa_e_content_type_incorreto_bloqueados(api, captura):
    assert verificar(api, captura, headers={'Origin': 'https://malicioso.example'}).status_code == 403
    assert verificar(api, captura, headers={'Sec-Fetch-Site': 'cross-site'}).status_code == 403
    response = api.client.post('/api/autenticacao/verificar', content=b'{}', headers={'Content-Type': 'image/png'})
    assert response.status_code == 415 and contar(api, Sessao) == 0


def test_cors_permite_cliente_web_em_origem_separada(api):
    origin = 'http://127.0.0.1:5500'
    preflight = api.client.options('/api/autenticacao/credenciais', headers={
        'Origin': origin,
        'Access-Control-Request-Method': 'POST',
        'Access-Control-Request-Headers': 'content-type',
    })
    assert preflight.status_code == 200
    assert preflight.headers['access-control-allow-origin'] == origin
    assert preflight.headers['access-control-allow-credentials'] == 'true'

    response = api.client.get('/api/saude', headers={'Origin': origin})
    assert response.status_code == 200
    assert response.headers['access-control-allow-origin'] == origin
    assert response.headers['access-control-allow-credentials'] == 'true'


def test_backend_nao_serve_arquivos_da_interface(api):
    assert api.client.get('/cadastro.html').status_code == 404
    assert api.client.get('/static/style.css').status_code == 404


def test_corpo_grande_rejeitado_com_e_sem_content_length(api):
    from app.main import MAX_BODY
    response = api.client.post('/api/autenticacao/verificar', content=b'{}',
                               headers={'Content-Type': 'application/json', 'Content-Length': str(MAX_BODY + 1)})
    assert response.status_code == 413
    chunks = (b'x' * (1024 * 1024) for _ in range(9))
    response = api.client.post('/api/autenticacao/verificar', content=chunks,
                               headers={'Content-Type': 'application/json'})
    assert response.status_code == 413 and contar(api, Usuario) == 0


def test_saude_confere_banco_e_deixa_limite_biometrico_explicito(api):
    response = api.client.get('/api/saude')
    assert response.status_code == 200
    assert response.json()['banco'] == 'ok' and response.json()['prova_de_vida'] is False
    assert response.json()['framework'] == 'ONNX Runtime'
    assert response.headers['cache-control'] == 'no-store'


def test_crud_de_usuarios_e_recadastro_biometrico(api, captura, outra_captura):
    assert cadastrar(api, captura).status_code == 201
    lista = gerenciar(api, 'GET', '/api/usuarios')
    assert lista.status_code == 200
    assert next(u for u in lista.json()['usuarios'] if u['id'] == 1)['nome'] == 'Pessoa de Teste'
    atualizada = gerenciar(api, 'PATCH', '/api/usuarios/1', json={
        'nome': 'Pessoa Editada', 'nivel': 3, 'ativo': False,
    })
    assert atualizada.status_code == 200
    assert atualizada.json()['usuario']['nome'] == 'Pessoa Editada'
    assert atualizada.json()['usuario']['ativo'] is False
    biometria = gerenciar(api, 'PUT', '/api/usuarios/1/biometria', json=outra_captura)
    assert biometria.status_code == 200
    assert 'AuraFace' in biometria.json()['processamento']['modelo']
    exclusao = gerenciar(api, 'DELETE', '/api/usuarios/1')
    assert exclusao.status_code == 204 and exclusao.content == b''
    assert [u for u in gerenciar(api, 'GET', '/api/usuarios').json()['usuarios'] if u['nivel'] != 4] == []
