"""python -m app.inicializar: prepara MySQL sem apagar dados existentes."""
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError

from .banco import Base, criar_engine
from .config import Settings


<<<<<<< HEAD
def main():
    
    engine = criar_engine(Settings())
    
=======
def codigo_mysql(exc):
    return getattr(getattr(exc, 'orig', None), 'args', (None,))[0]


def preparar_banco(settings):
    engine = criar_engine(settings)
>>>>>>> 2e146cbcc14270a7ec9a8b5da932827f9ad7ff12
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
<<<<<<< HEAD
    
    except SQLAlchemyError:
        raise SystemExit('Não foi possível criar as tabelas. Confira MySQL ativo, banco, usuário e senha no .env.') from None
    
    finally:
        engine.dispose()
    
    print('Tabelas prontas: usuarios, logs_acesso, sessoes e desafios_biometricos. Dados existentes preservados.')
=======
    finally:
        engine.dispose()


def main():
    try:
        settings = Settings()
    except ValidationError:
        raise SystemExit('Configuração inválida. Confira DB_PORT, DB_NAME e BIOMETRIC_KEY, '
                         'se definidos no ambiente ou no .env.') from None
    try:
        preparar_banco(settings)
    except SQLAlchemyError as exc:
        codigo = codigo_mysql(exc)
        if codigo in (1044, 1142):
            motivo = 'O usuário precisa de permissão para criar o banco/tabelas ou acessar o banco indicado.'
        elif codigo in (1045, 1698):
            motivo = 'Usuário ou senha recusados. Ajuste DB_USER e DB_PASSWORD.'
        elif codigo in (2002, 2003, 2005):
            motivo = 'Servidor indisponível. Inicie o MySQL e confira DB_HOST e DB_PORT.'
        else:
            motivo = f'Falha na preparação do MySQL (código {codigo}). Confira conexão e permissões.'
        raise SystemExit(motivo + ' Use variáveis de ambiente ou um .env opcional '
                         '(python scripts/configurar.py).') from None
    print('Banco MySQL e tabelas prontos. Dados existentes preservados.')
>>>>>>> 2e146cbcc14270a7ec9a8b5da932827f9ad7ff12


if __name__ == '__main__':
    
    main()
