"""python -m app.inicializar: cria somente tabelas ausentes, sem apagar dados."""
from sqlalchemy.exc import SQLAlchemyError
from .banco import Base, criar_engine
from .config import Settings


def main():
    
    engine = criar_engine(Settings())
    
    try:
        Base.metadata.create_all(engine)
    
    except SQLAlchemyError:
        raise SystemExit('Não foi possível criar as tabelas. Confira MySQL ativo, banco, usuário e senha no .env.') from None
    
    finally:
        engine.dispose()
    
    print('Tabelas prontas: usuarios, logs_acesso, sessoes e desafios_biometricos. Dados existentes preservados.')


if __name__ == '__main__':
    
    main()
