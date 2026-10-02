"""Cria .env uma única vez; nunca sobrescreve chaves existentes."""
import base64
from pathlib import Path
import secrets

root = Path(__file__).resolve().parent.parent
target = root / '.env'
conteudo = (root / '.env.example').read_text(encoding='utf-8')
conteudo = conteudo.replace('BIOMETRIC_KEY=\n', 'BIOMETRIC_KEY=' + base64.urlsafe_b64encode(secrets.token_bytes(32)).decode() + '\n')
try:
    with target.open('x', encoding='utf-8', newline='\n') as arquivo:
        arquivo.write(conteudo)
except FileExistsError:
    print('.env já existe; nenhuma chave foi alterada.')
else:
    print('.env criado. Configure DB_PASSWORD e guarde uma cópia segura deste arquivo.')
