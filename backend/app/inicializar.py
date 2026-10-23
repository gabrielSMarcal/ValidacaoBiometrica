"""python -m app.inicializar: prepara MySQL sem apagar dados existentes."""
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from .banco import Base, Usuario, criar_engine, fabrica_sessoes
from .config import Settings
from .seguranca import Seguranca


def atualizar_esquema(engine):
    if engine.dialect.name not in ('mysql', 'mariadb'):
        return
    with engine.begin() as connection:
        inspector = inspect(connection)
        colunas = {coluna['name']: coluna for coluna in inspector.get_columns('usuarios')}
        checks = {check['name']: check for check in inspector.get_check_constraints('usuarios')}
        unicos = {indice['name'] for indice in inspector.get_unique_constraints('usuarios')}
        alteracoes = []
        nivel = checks.get('ck_usuario_nivel')
        expressao = ''.join(nivel['sqltext'].translate(str.maketrans('', '', '`()')).lower().split()) if nivel else ''
        if expressao != 'nivelbetween1and4':
            if nivel:
                comando = 'DROP CONSTRAINT' if engine.dialect.is_mariadb else 'DROP CHECK'
                alteracoes.append(f'{comando} ck_usuario_nivel')
            alteracoes.append('ADD CONSTRAINT ck_usuario_nivel CHECK (nivel BETWEEN 1 AND 4)')
        if not colunas['assinatura_cifrada']['nullable']:
            tipo = colunas['assinatura_cifrada']['type'].compile(dialect=engine.dialect)
            alteracoes.append(f'MODIFY COLUMN assinatura_cifrada {tipo} NULL')
        if 'admin_unico' not in colunas:
            alteracoes.append('ADD COLUMN admin_unico INTEGER GENERATED ALWAYS AS '
                              '(CASE WHEN nivel = 4 THEN 1 ELSE NULL END) STORED')
        if 'uq_usuario_admin_unico' not in unicos:
            alteracoes.append('ADD CONSTRAINT uq_usuario_admin_unico UNIQUE (admin_unico)')
        if 'ck_usuario_assinatura' not in checks:
            alteracoes.append('ADD CONSTRAINT ck_usuario_assinatura '
                              'CHECK (nivel = 4 OR assinatura_cifrada IS NOT NULL)')
        if alteracoes:
            connection.exec_driver_sql('ALTER TABLE usuarios ' + ', '.join(alteracoes))


def garantir_administrador(engine, settings):
    seguranca = Seguranca(settings.biometric_key.get_secret_value())
    sessions = fabrica_sessoes(engine)
    with sessions() as db:
        administrador = db.scalar(select(Usuario).where(Usuario.nivel == 4))
        if administrador:
            if settings.admin_cpf is not None and administrador.cpf_indice != seguranca.indice_cpf(
                    settings.admin_cpf.get_secret_value()):
                raise RuntimeError('Já existe um administrador com outro CPF. Confira o banco e a chave original.')
            return
        if settings.admin_cpf is None or settings.admin_password_hash is None:
            raise RuntimeError('Defina ADMIN_CPF e ADMIN_PASSWORD_HASH no ambiente ou no .env '
                               'privado do backend para criar o administrador.')
        cpf = settings.admin_cpf.get_secret_value()
        indice = seguranca.indice_cpf(cpf)
        existente = db.scalar(select(Usuario).where(Usuario.cpf_indice == indice))
        if existente:
            raise RuntimeError('O CPF reservado ao administrador já pertence a outro cadastro.')
        referencia = str(uuid4())
        db.add(Usuario(
            biometria_ref=referencia, nome='Administrador', cpf_indice=indice,
            cpf_cifrado=seguranca.cifrar({'cpf': cpf}, referencia, 'cpf'),
            senha_hash=settings.admin_password_hash.get_secret_value(), nivel=4, ativo=True,
            assinatura_cifrada=None,
        ))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            existente = db.scalar(select(Usuario).where(Usuario.cpf_indice == indice))
            if not existente or existente.nivel != 4:
                raise


def codigo_mysql(exc):
    return getattr(getattr(exc, 'orig', None), 'args', (None,))[0]


def preparar_banco(settings):
    engine = criar_engine(settings)
    try:
        try:
            with engine.connect():
                pass
        except SQLAlchemyError as exc:
            if codigo_mysql(exc) != 1049:  # Apenas banco inexistente.
                raise
            servidor = create_engine(settings.database_url._replace(database=None),
                                     connect_args={'connect_timeout': 5}, hide_parameters=True)
            try:
                nome = servidor.dialect.identifier_preparer.quote_identifier(settings.db_name)
                with servidor.begin() as connection:
                    connection.exec_driver_sql(
                        f'CREATE DATABASE IF NOT EXISTS {nome} '
                        'CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci')
            finally:
                servidor.dispose()
        Base.metadata.create_all(engine)
        atualizar_esquema(engine)
        garantir_administrador(engine, settings)
    finally:
        engine.dispose()


def main():
    try:
        settings = Settings()
    except ValidationError:
        raise SystemExit('Configuração inválida. Confira DB_PORT, DB_NAME, BIOMETRIC_KEY, '
                         'ADMIN_CPF e ADMIN_PASSWORD_HASH, '
                         'se definidos no ambiente ou no .env.') from None
    try:
        preparar_banco(settings)
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from None
    except SQLAlchemyError as exc:
        codigo = codigo_mysql(exc)
        if codigo in (1044, 1142):
            motivo = 'O usuário precisa de permissão para criar/atualizar as tabelas ou acessar o banco indicado.'
        elif codigo in (1045, 1698):
            motivo = 'Usuário ou senha recusados. Ajuste DB_USER e DB_PASSWORD.'
        elif codigo in (2002, 2003, 2005):
            motivo = 'Servidor indisponível. Inicie o MySQL e confira DB_HOST e DB_PORT.'
        else:
            motivo = f'Falha na preparação do MySQL (código {codigo}). Confira conexão e permissões.'
        raise SystemExit(motivo + ' Use variáveis de ambiente ou um .env opcional '
                         '(python scripts/configurar.py).') from None
    print('Banco MySQL e tabelas prontos. Dados existentes preservados.')


if __name__ == '__main__':
    main()
