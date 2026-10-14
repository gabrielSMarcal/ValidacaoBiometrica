"""Teste opt-in MySQL: remove somente o cadastro sintético pertencente à execução.

Execute: python -m scripts.verificar_mysql
Requer requirements-dev.txt, configuração existente e esquema v2.
As imagens são texturas sintéticas; o teste não mede precisão facial.
"""
import secrets
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from app.banco import DesafioBiometrico, LogAcesso, Sessao, Usuario, criar_engine
from app.config import Settings
from app.main import criar_app
from app.seguranca import Seguranca
from tests.test_biometria import quadro_sintetico


def cpf_sintetico():
    while True:
        numero = ''.join(str(secrets.randbelow(10)) for _ in range(9))
        if len(set(numero)) > 1:
            break
    for tamanho in (9, 10):
        soma = sum(int(numero[i]) * (tamanho + 1 - i) for i in range(tamanho))
        numero += str((soma * 10 % 11) % 10)
    return numero


def main():
    settings = Settings()
    engine = criar_engine(settings)
    seguranca = Seguranca(settings.biometric_key.get_secret_value())
    marcador = 'TESTE_INTEGRACAO_' + str(uuid4())
    requisicoes = []
    cpf, senha = cpf_sintetico(), secrets.token_urlsafe(24)
    indice = seguranca.indice_cpf(cpf)
    frames = [quadro_sintetico()] * 3
    user_id = None
    with Session(engine) as db:
        if db.scalar(select(Usuario.id).where(Usuario.cpf_indice == indice)):
            raise SystemExit('Identificador já existe. Execute novamente; nenhum registro alterado.')
        print('Conexão MySQL OK; versão:', db.scalar(text('SELECT VERSION()')))

    def checar(response, esperado, etapa):
        request_id = response.headers.get('x-request-id')
        if request_id:
            requisicoes.append(request_id)
        if response.status_code != esperado:
            raise RuntimeError(f'{etapa}: HTTP {response.status_code}; esperado {esperado}.')
        print(etapa + ': OK')
        return response.json()

    try:
        # HTTPS virtual também permite testar COOKIE_SECURE sem abrir uma porta.
        with TestClient(criar_app(settings, engine), base_url='https://localhost') as client:
            dados = {'nome': marcador, 'cpf': cpf, 'senha': senha, 'nivel': 2, 'frames': frames}
            cadastro = checar(client.post('/api/usuarios', json=dados), 201, 'Cadastro público e log')
            user_id = cadastro['usuario']['id']
            assert type(user_id) is int
            with Session(engine) as db:
                user = db.get(Usuario, user_id)
                assert user.nome == marcador and user.cpf_indice == indice
                assert isinstance(user.assinatura_cifrada, bytes)
                assert seguranca.decifrar(user.assinatura_cifrada, user.biometria_ref, 'biometria')['dimensao'] == 1136
                assert seguranca.decifrar(user.cpf_cifrado, user.biometria_ref, 'cpf') == {'cpf': cpf}
                assert seguranca.verificar_senha(senha, user.senha_hash)
            print('ID inteiro, BLOB, referência criptográfica e senha: OK')

            cred = {'cpf': cpf, 'senha': senha}
            checar(client.post('/api/autenticacao/verificar', json={'frames': frames}), 401, 'Biometria sem credenciais recusada')
            checar(client.post('/api/autenticacao/credenciais', json=cred), 200, 'CPF e senha antes da câmera')
            assert client.cookies.get('aps_desafio') and not client.cookies.get('aps_sessao')
            checar(client.get('/api/sessao'), 401, 'Desafio não autoriza o nível')
            token_desafio = client.cookies.get('aps_desafio')
            checar(client.post('/api/autenticacao/verificar', json={'frames': frames}), 200, 'Verificação facial 1:1')
            sessao = checar(client.get('/api/sessao'), 200, 'Sessão completa')
            assert sessao['usuario']['id'] == user_id and sessao['usuario']['nivel'] == 2
            checar(client.post('/api/sair'), 200, 'Logout')
            checar(client.get('/api/sessao'), 401, 'Sessão revogada')
            checar(client.post('/api/autenticacao/verificar', json={'frames': frames},
                                headers={'Cookie': f'aps_desafio={token_desafio}'}), 401, 'Desafio consumido não pode ser reutilizado')
            checar(client.post('/api/autenticacao/credenciais', json={**cred, 'senha': 'incorreta'}),
                    401, 'Senha errada recusada')

            # Cria sessão e desafio em contextos de navegador separados para testar
            # DELETE por ID inteiro sobre EXATAMENTE o cadastro temporário criado.
            checar(client.post('/api/autenticacao/credenciais', json=cred), 200, 'Credenciais para teste de exclusão')
            checar(client.post('/api/autenticacao/verificar', json={'frames': frames}), 200, 'Sessão para teste de exclusão')
            token_sessao = client.cookies.get('aps_sessao')
            client.cookies.clear()
            checar(client.post('/api/autenticacao/credenciais', json=cred), 200, 'Desafio para teste de exclusão')
            token_desafio = client.cookies.get('aps_desafio')
            with Session(engine) as db:
                owned = db.scalar(select(Usuario).where(Usuario.id == user_id,
                                  Usuario.nome == marcador, Usuario.cpf_indice == indice))
                assert owned is not None
                logs_antes = list(db.scalars(select(LogAcesso.id).where(LogAcesso.usuario_id == user_id)))
                assert logs_antes
                assert db.scalar(select(func.count()).select_from(Sessao).where(Sessao.usuario_id == user_id)) == 1
                assert db.scalar(select(func.count()).select_from(DesafioBiometrico).where(DesafioBiometrico.usuario_id == user_id)) == 1
                resultado = db.execute(text('DELETE FROM usuarios WHERE id = :id AND nome = :nome AND cpf_indice = :indice'),
                                       {'id': user_id, 'nome': marcador, 'indice': indice})
                assert resultado.rowcount == 1
                db.commit()
                assert db.get(Usuario, user_id) is None
                assert db.scalar(select(func.count()).select_from(Sessao).where(Sessao.usuario_id == user_id)) == 0
                assert db.scalar(select(func.count()).select_from(DesafioBiometrico).where(DesafioBiometrico.usuario_id == user_id)) == 0
                logs = db.scalars(select(LogAcesso).where(LogAcesso.id.in_(logs_antes))).all()
                assert len(logs) == len(logs_antes) and all(log.usuario_id is None for log in logs)
            print('DELETE do cadastro temporário: logs preservados; sessão/desafio removidos: OK')
            checar(client.get('/api/sessao', headers={'Cookie': f'aps_sessao={token_sessao}'}), 401, 'Cookie antigo após exclusão recusado')
            checar(client.post('/api/autenticacao/verificar', json={'frames': frames},
                                headers={'Cookie': f'aps_desafio={token_desafio}'}), 401, 'Desafio antigo após exclusão recusado')
    finally:
        # O marcador aleatório e o índice devem coincidir; nunca exclui por ID isolado.
        # Logs tornados órfãos pelo teste também têm request IDs exclusivos desta execução.
        with Session(engine) as db:
            ids = list(db.scalars(select(Usuario.id).where(Usuario.cpf_indice == indice, Usuario.nome == marcador)))
            if ids:
                db.execute(delete(DesafioBiometrico).where(DesafioBiometrico.usuario_id.in_(ids)))
                db.execute(delete(Sessao).where(Sessao.usuario_id.in_(ids)))
                db.execute(delete(LogAcesso).where(LogAcesso.usuario_id.in_(ids)))
                db.execute(delete(Usuario).where(Usuario.id.in_(ids), Usuario.cpf_indice == indice, Usuario.nome == marcador))
            if requisicoes:
                db.execute(delete(LogAcesso).where(LogAcesso.requisicao_id.in_(requisicoes)))
            db.commit()
        engine.dispose()
        print('Limpeza exclusiva dos dados desta execução: OK')


if __name__ == '__main__':
    main()

