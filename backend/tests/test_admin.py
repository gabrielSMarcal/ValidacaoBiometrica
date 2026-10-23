from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, func, inspect, select
from sqlalchemy.dialects import mysql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import inicializar
from app.banco import DesafioBiometrico, Sessao, Usuario
from app.config import Settings
from app.seguranca import Seguranca, hash_token
from tests.test_api import (
    CHAVE_TESTE, CPF_TESTE, api, captura, cadastrar, contar, credenciais, verificar,
)

CPF_ADMIN_TESTE = '12345678909'
SENHA_ADMIN_TESTE = 'Senha-admin-sintetica-2026!'


@pytest.fixture(autouse=True)
def isolar_configuracao_admin(monkeypatch):
    monkeypatch.delenv('ADMIN_CPF', raising=False)
    monkeypatch.delenv('ADMIN_PASSWORD_HASH', raising=False)


@pytest.fixture(scope='module')
def hash_admin():
    return Seguranca(CHAVE_TESTE).senhas.hash(SENHA_ADMIN_TESTE)


@pytest.fixture
def settings_admin(hash_admin):
    return Settings(_env_file=None, biometric_key=CHAVE_TESTE,
                    admin_cpf=CPF_ADMIN_TESTE, admin_password_hash=hash_admin)


@pytest.fixture
def admin(api, settings_admin):
    inicializar.garantir_administrador(api.engine, settings_admin)
    return api


def test_preparacao_cria_admin_e_reexecucao_preserva_dados(tmp_path, monkeypatch, settings_admin):
    engine = create_engine('sqlite:///' + str(tmp_path / 'inicializacao.sqlite'))
    settings = settings_admin
    monkeypatch.setattr(inicializar, 'criar_engine', lambda _settings: engine)
    inicializar.preparar_banco(settings)
    seguranca = Seguranca(CHAVE_TESTE)
    with Session(engine) as db:
        admin = db.scalar(select(Usuario))
        assert admin.nivel == 4 and admin.ativo and admin.assinatura_cifrada is None
        assert admin.admin_unico == 1
        assert admin.cpf_indice == seguranca.indice_cpf(CPF_ADMIN_TESTE)
        assert seguranca.decifrar(admin.cpf_cifrado, admin.biometria_ref, 'cpf') == {'cpf': CPF_ADMIN_TESTE}
        assert CPF_ADMIN_TESTE.encode() not in admin.cpf_cifrado
        assert admin.senha_hash.startswith('$argon2id$')
        assert admin.senha_hash == settings.admin_password_hash.get_secret_value()
        assert seguranca.verificar_senha(SENHA_ADMIN_TESTE, admin.senha_hash)
        original = (admin.id, admin.biometria_ref, admin.cpf_cifrado, admin.senha_hash, admin.criado_em)
    inicializar.preparar_banco(settings)
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(Usuario)) == 1
        admin = db.scalar(select(Usuario))
        assert (admin.id, admin.biometria_ref, admin.cpf_cifrado, admin.senha_hash, admin.criado_em) == original
        admin.senha_hash = seguranca.senhas.hash('Senha-alterada-de-teste!')
        db.commit()
        senha_alterada = admin.senha_hash
    inicializar.preparar_banco(settings)
    with Session(engine) as db:
        assert db.scalar(select(Usuario.senha_hash)) == senha_alterada
    engine.dispose()


def test_cpf_existente_nao_e_promovido_automaticamente(api, captura, settings_admin):
    assert cadastrar(api, captura, cpf=CPF_ADMIN_TESTE).status_code == 201
    with pytest.raises(RuntimeError, match='outro cadastro'):
        inicializar.garantir_administrador(api.engine, settings_admin)
    with Session(api.engine) as db:
        assert db.scalar(select(Usuario.nivel)) == 2


@pytest.mark.parametrize('ausente', ['cpf', 'hash', 'ambos'])
def test_novo_admin_exige_configuracao_privada_sem_credenciais_padrao(api, hash_admin, ausente):
    settings = Settings(_env_file=None, biometric_key=CHAVE_TESTE,
                        admin_cpf=None if ausente in ('cpf', 'ambos') else CPF_ADMIN_TESTE,
                        admin_password_hash=None if ausente in ('hash', 'ambos') else hash_admin)
    with pytest.raises(RuntimeError, match='Defina ADMIN_CPF e ADMIN_PASSWORD_HASH'):
        inicializar.garantir_administrador(api.engine, settings)
    assert contar(api, Usuario) == 0


def test_admin_existente_preservado_sem_configuracao_de_criacao(admin):
    with Session(admin.engine) as db:
        original = db.scalar(select(Usuario.senha_hash))
    settings = Settings(_env_file=None, biometric_key=CHAVE_TESTE)
    assert settings.admin_cpf is None and settings.admin_password_hash is None
    inicializar.garantir_administrador(admin.engine, settings)
    assert contar(admin, Usuario) == 1
    with Session(admin.engine) as db:
        assert db.scalar(select(Usuario.senha_hash)) == original


def test_configuracao_privada_carregada_e_ocultada_em_representacoes(tmp_path, hash_admin):
    arquivo = tmp_path / '.env'
    arquivo.write_text(f'ADMIN_CPF=123.456.789-09\nADMIN_PASSWORD_HASH={hash_admin}\n', encoding='utf-8')
    settings = Settings(_env_file=arquivo, biometric_key=CHAVE_TESTE)
    assert settings.admin_cpf.get_secret_value() == CPF_ADMIN_TESTE
    assert settings.admin_password_hash.get_secret_value() == hash_admin
    for representacao in (repr(settings), str(settings), str(settings.model_dump()), settings.model_dump_json()):
        assert CPF_ADMIN_TESTE not in representacao
        assert hash_admin not in representacao
        assert 'admin_cpf' not in representacao and 'admin_password_hash' not in representacao


def test_variaveis_do_ambiente_tem_prioridade_sobre_arquivo_privado(tmp_path, hash_admin, monkeypatch):
    arquivo = tmp_path / '.env'
    arquivo.write_text(f'ADMIN_CPF={CPF_TESTE}\nADMIN_PASSWORD_HASH=hash-invalido\n', encoding='utf-8')
    monkeypatch.setenv('ADMIN_CPF', CPF_ADMIN_TESTE)
    monkeypatch.setenv('ADMIN_PASSWORD_HASH', hash_admin)
    settings = Settings(_env_file=arquivo, biometric_key=CHAVE_TESTE)
    assert settings.admin_cpf.get_secret_value() == CPF_ADMIN_TESTE
    assert settings.admin_password_hash.get_secret_value() == hash_admin


@pytest.mark.parametrize('campo', ['admin_cpf', 'admin_password_hash'])
def test_configuracao_invalida_nao_expoe_valor_secreto(campo):
    segredo = 'valor-privado-invalido-para-teste'
    with pytest.raises(ValidationError) as erro:
        Settings(_env_file=None, biometric_key=CHAVE_TESTE, **{campo: segredo})
    assert segredo not in str(erro.value)


def test_hash_admin_deve_usar_argon2id(hash_admin):
    with pytest.raises(ValidationError, match='hash Argon2id'):
        Settings(_env_file=None, biometric_key=CHAVE_TESTE,
                 admin_password_hash=hash_admin.replace('$argon2id$', '$argon2i$'))


def test_chave_incorreta_nao_cria_outro_administrador(admin, hash_admin):
    settings = Settings(_env_file=None, biometric_key='eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHg=',
                        admin_cpf=CPF_ADMIN_TESTE, admin_password_hash=hash_admin)
    with pytest.raises(RuntimeError, match='chave original'):
        inicializar.garantir_administrador(admin.engine, settings)
    assert contar(admin, Usuario) == 1


@pytest.mark.parametrize('cpf', ['123.456.789-09', CPF_ADMIN_TESTE])
def test_admin_autentica_sem_captura_e_preserva_contrato(admin, monkeypatch, cpf):
    processamento = Mock(side_effect=AssertionError('Administrador não deve processar biometria.'))
    monkeypatch.setattr('app.main.processar_captura', processamento)
    resposta = credenciais(admin, cpf=cpf, senha=SENHA_ADMIN_TESTE)
    assert resposta.status_code == 200
    assert set(resposta.json()) == {'mensagem', 'expira_em_segundos'}
    assert resposta.json()['expira_em_segundos'] == admin.settings.session_minutes * 60
    assert admin.client.cookies.get('aps_desafio') is None
    assert contar(admin, DesafioBiometrico) == 0
    token = admin.client.cookies.get('aps_sessao')
    assert token and contar(admin, Sessao) == 1
    with Session(admin.engine) as db:
        assert db.get(Sessao, hash_token(token)).usuario_id == 1
    sessao = admin.client.get('/api/sessao')
    assert sessao.status_code == 200
    assert sessao.json()['usuario'] == {'id': 1, 'nome': 'Administrador', 'nivel': 4}
    assert not any(segredo in resposta.text + sessao.text for segredo in [cpf, SENHA_ADMIN_TESTE, token])
    processamento.assert_not_called()


def test_senha_errada_revoga_sessao_admin_e_logout_impede_replay(admin):
    dados = {'cpf': CPF_ADMIN_TESTE, 'senha': SENHA_ADMIN_TESTE}
    assert admin.client.post('/api/autenticacao/credenciais', json=dados).status_code == 200
    assert credenciais(admin, cpf=CPF_ADMIN_TESTE, senha='Senha-incorreta!').status_code == 401
    assert contar(admin, Sessao) == contar(admin, DesafioBiometrico) == 0
    assert admin.client.get('/api/sessao').status_code == 401
    assert admin.client.post('/api/autenticacao/credenciais', json=dados).status_code == 200
    token = admin.client.cookies.get('aps_sessao')
    assert admin.client.post('/api/sair').status_code == 200
    assert admin.client.get('/api/sessao', headers={'Cookie': f'aps_sessao={token}'}).status_code == 401
    assert contar(admin, Sessao) == contar(admin, DesafioBiometrico) == 0


def test_admin_inativo_nao_autentica(admin):
    with Session(admin.engine) as db:
        db.get(Usuario, 1).ativo = False
        db.commit()
    assert credenciais(admin, cpf=CPF_ADMIN_TESTE, senha=SENHA_ADMIN_TESTE).status_code == 401
    assert contar(admin, Sessao) == contar(admin, DesafioBiometrico) == 0


@pytest.mark.parametrize('etapa', ['desafio', 'sessao'])
def test_login_admin_revoga_acesso_anterior(admin, captura, etapa):
    assert cadastrar(admin, captura).status_code == 201
    assert credenciais(admin).status_code == 200
    if etapa == 'sessao':
        assert verificar(admin, captura).status_code == 200
    assert credenciais(admin, cpf=CPF_ADMIN_TESTE, senha=SENHA_ADMIN_TESTE).status_code == 200
    assert contar(admin, DesafioBiometrico) == 0
    assert contar(admin, Sessao) == 1
    with Session(admin.engine) as db:
        assert db.scalar(select(Sessao.usuario_id)) == 1


@pytest.mark.parametrize('alteracao', [{'nivel': 1}, {'ativo': False}, {'senha': 'Outra-senha-2026!'}, {'nome': 'Outro nome'}])
def test_admin_protegido_de_alteracoes_pela_api(admin, alteracao):
    assert admin.client.patch('/api/usuarios/1', json=alteracao).status_code == 403
    with Session(admin.engine) as db:
        usuario = db.get(Usuario, 1)
        assert usuario.nivel == 4 and usuario.ativo and usuario.nome == 'Administrador'
        assert admin.seguranca.verificar_senha(SENHA_ADMIN_TESTE, usuario.senha_hash)


def test_admin_nao_pode_ser_excluido_ou_receber_biometria(admin, captura):
    assert admin.client.delete('/api/usuarios/1').status_code == 403
    assert admin.client.put('/api/usuarios/1/biometria', json=captura).status_code == 403
    with Session(admin.engine) as db:
        assert db.get(Usuario, 1).assinatura_cifrada is None


def test_nivel_4_nao_pode_ser_concedido_pela_api_nem_duplicado_no_banco(admin, captura):
    assert cadastrar(admin, captura, nivel=4).status_code == 422
    usuario = cadastrar(admin, captura).json()['usuario']
    assert admin.client.patch(f'/api/usuarios/{usuario["id"]}', json={'nivel': 4}).status_code == 422
    with Session(admin.engine) as db:
        db.get(Usuario, usuario['id']).nivel = 4
        with pytest.raises(IntegrityError):
            db.commit()
    assert contar(admin, Usuario) == 2


def test_usuario_comum_continua_exigindo_biometria_no_banco_e_no_login(admin, captura):
    usuario = cadastrar(admin, captura).json()['usuario']
    assert credenciais(admin, cpf=CPF_TESTE).status_code == 200
    assert admin.client.cookies.get('aps_desafio')
    assert admin.client.get('/api/sessao').status_code == 401
    with Session(admin.engine) as db:
        db.get(Usuario, usuario['id']).assinatura_cifrada = None
        with pytest.raises(IntegrityError):
            db.commit()
    assert verificar(admin, captura).status_code == 200


@pytest.mark.parametrize('mariadb', [False, True])
def test_migracao_mysql_atualiza_restricoes_sem_remover_dados(monkeypatch, mariadb):
    dialect = mysql.dialect()
    dialect.is_mariadb = mariadb
    executar = Mock()
    connection = SimpleNamespace(exec_driver_sql=executar)
    engine = SimpleNamespace(dialect=dialect, begin=lambda: nullcontext(connection))
    inspector = Mock()
    inspector.get_columns.return_value = [
        {'name': 'assinatura_cifrada', 'type': mysql.MEDIUMBLOB(), 'nullable': False},
    ]
    inspector.get_check_constraints.return_value = [
        {'name': 'ck_usuario_nivel', 'sqltext': '`nivel` between 1 and 3'},
    ]
    inspector.get_unique_constraints.return_value = []
    monkeypatch.setattr(inicializar, 'inspect', lambda _connection: inspector)
    inicializar.atualizar_esquema(engine)
    sql = executar.call_args.args[0]
    assert sql.startswith('ALTER TABLE usuarios ')
    assert ('DROP CONSTRAINT' if mariadb else 'DROP CHECK') + ' ck_usuario_nivel' in sql
    assert 'nivel BETWEEN 1 AND 4' in sql
    assert 'MODIFY COLUMN assinatura_cifrada MEDIUMBLOB NULL' in sql
    assert 'UNIQUE (admin_unico)' in sql
    assert 'DROP TABLE' not in sql and 'DELETE' not in sql and 'UPDATE' not in sql


def test_esquema_atual_nao_e_alterado_novamente(admin, monkeypatch):
    inspector = inspect(admin.engine)
    executar = Mock()
    dialect = mysql.dialect()
    engine = SimpleNamespace(dialect=dialect, begin=lambda: nullcontext(SimpleNamespace(exec_driver_sql=executar)))
    monkeypatch.setattr(inicializar, 'inspect', lambda _connection: inspector)
    inicializar.atualizar_esquema(engine)
    executar.assert_not_called()
