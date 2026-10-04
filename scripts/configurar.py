"""Gera configuração opcional sem template e sem sobrescrever arquivos existentes."""
from pathlib import Path
import sys

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))

from app.config import Settings


def main():
    target = root / '.env'
    if target.exists():
        print('.env já existe; nenhuma configuração ou chave foi alterada.')
        return
    settings = Settings()

    def valor(texto):
        return "'" + texto.replace('\\', '\\\\').replace("'", "\\'") + "'"

    conteudo = '\n'.join([
        '# Opcional: variáveis do ambiente têm prioridade sobre este arquivo.',
        f'DB_HOST={valor(settings.db_host)}',
        f'DB_PORT={settings.db_port}',
        f'DB_NAME={valor(settings.db_name)}',
        f'DB_USER={valor(settings.db_user)}',
        f'DB_PASSWORD={valor(settings.db_password.get_secret_value())}',
        f'BIOMETRIC_KEY={valor(settings.biometric_key.get_secret_value())}',
        '',
    ])
    try:
        with target.open('x', encoding='utf-8', newline='\n') as arquivo:
            arquivo.write(conteudo)
    except FileExistsError:
        print('.env já existe; nenhuma configuração ou chave foi alterada.')
    else:
        print('.env criado. Ajuste a conexão MySQL se necessário; preserve a chave biométrica.')


if __name__ == '__main__':
    main()
