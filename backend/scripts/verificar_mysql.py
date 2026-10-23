"""Teste opt-in MySQL: remove somente o cadastro sintético pertencente à execução.

Execute: python -m scripts.verificar_mysql
Requer modelos faciais preparados, configuração existente e administrador ativo.
Usa a fotografia pública da fixture facial; não testa prova de vida.
"""
import base64
from datetime import timedelta
import secrets
from uuid import uuid4

import cv2
from fastapi.testclient import TestClient
import numpy as np
from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from app.banco import DesafioBiometrico, LogAcesso, Sessao, Usuario, agora, criar_engine
from app.config import ROOT, Settings
from app.main import criar_app
from app.seguranca import Seguranca, hash_token


def cpf_sintetico():
    while True:
        numero = ''.join(str(secrets.randbelow(10)) for _ in range(9))
        if len(set(numero)) > 1:
            break
    for tamanho in (9, 10):
        soma = sum(int(numero[i]) * (tamanho + 1 - i) for i in range(tamanho))
        numero += str((soma * 10 % 11) % 10)
    return numero


def quadro_fotografia():
    caminho = ROOT / 'tests' / 'dados_faciais' / 'obama.jpg'
    bgr = cv2.imdecode(np.frombuffer(caminho.read_bytes(), dtype=np.uint8), cv2.IMREAD_COLOR)
    if bgr is None:
        raise RuntimeError('A imagem de teste facial está ausente ou inválida.')
    altura, largura = bgr.shape[:2]
    escala = min(640 / largura, 480 / altura)
    reduzida = cv2.resize(bgr, (round(largura * escala), round(altura * escala)),
                          interpolation=cv2.INTER_AREA)
    camera = np.full((480, 640, 3), 128, dtype=np.uint8)
    y, x = (480 - reduzida.shape[0]) // 2, (640 - reduzida.shape[1]) // 2
    camera[y:y + reduzida.shape[0], x:x + reduzida.shape[1]] = reduzida
    rgb = cv2.cvtColor(camera, cv2.COLOR_BGR2RGB)
    return {'largura': 640, 'altura': 480,
            'rgb_base64': base64.b64encode(rgb.tobytes()).decode('ascii')}


def main():
    settings = Settings()
    engine = criar_engine(settings)
    seguranca = Seguranca(settings.biometric_key.get_secret_value())
    marcador = 'TESTE_INTEGRACAO_' + str(uuid4())
    requisicoes = []
    cpf, senha = cpf_sintetico(), secrets.token_urlsafe(24)
    indice = seguranca.indice_cpf(cpf)
    frames = [quadro_fotografia()] * 3
    user_id = None
    admin_id = None
    token_admin = secrets.token_urlsafe(32)
    sessao_admin_hash = hash_token(token_admin)
    headers_admin = {'Cookie': f'aps_sessao={token_admin}'}

    def checar(response, esperado, etapa):
        request_id = response.headers.get('x-request-id')
        if request_id:
            requisicoes.append(request_id)
        if response.status_code != esperado:
            raise RuntimeError(f'{etapa}: HTTP {response.status_code}; esperado {esperado}.')
        print(etapa + ': OK')
        return response.json()

    try:
        with Session(engine) as db:
            if db.scalar(select(Usuario.id).where(Usuario.cpf_indice == indice)):
                raise SystemExit('Identificador já existe. Execute novamente; nenhum registro alterado.')
            admin = db.scalar(select(Usuario).where(Usuario.nivel == 4, Usuario.ativo.is_(True)))
            if admin is None:
                raise SystemExit('Administrador ativo de nível 4 não encontrado. Prepare o banco antes do teste.')
            admin_id = admin.id
            db.add(Sessao(token_hash=sessao_admin_hash, usuario_id=admin_id,
                          expira_em=agora() + timedelta(minutes=settings.session_minutes)))
            db.commit()
            print('Conexão MySQL OK; versão:', db.scalar(text('SELECT VERSION()')))

        # HTTPS virtual também permite testar COOKIE_SECURE sem abrir uma porta.
        with TestClient(criar_app(settings, engine), base_url='https://localhost') as client:
            dados = {'nome': marcador, 'cpf': cpf, 'senha': senha, 'nivel': 2, 'frames': frames}
            cadastro = checar(client.post('/api/usuarios', json=dados, headers=headers_admin),
                              201, 'Cadastro autorizado pelo administrador e log')
            user_id = cadastro['usuario']['id']
            assert type(user_id) is int
            with Session(engine) as db:
                user = db.get(Usuario, user_id)
                assert user.nome == marcador and user.cpf_indice == indice
                assert isinstance(user.assinatura_cifrada, bytes)
                assinatura = seguranca.decifrar(user.assinatura_cifrada, user.biometria_ref, 'biometria')
                assert assinatura['dimensao'] == len(assinatura['vetor']) == 512
                assert seguranca.decifrar(user.cpf_cifrado, user.biometria_ref, 'cpf') == {'cpf': cpf}
                assert seguranca.verificar_senha(senha, user.senha_hash)
            print('ID inteiro, BLOB, referência criptográfica e senha: OK')

            lista = checar(client.get('/api/usuarios', headers=headers_admin), 200, 'Listagem autorizada')
            assert any(usuario['id'] == user_id for usuario in lista['usuarios'])
            alteracao = checar(client.patch(f'/api/usuarios/{user_id}', json={'nivel': 3},
                                            headers=headers_admin), 200, 'Atualização autorizada do nível')
            assert alteracao['usuario']['nivel'] == 3
            checar(client.put(f'/api/usuarios/{user_id}/biometria', json={'frames': frames},
                              headers=headers_admin), 200, 'Recadastro biométrico autorizado com modelo real')

            cred = {'cpf': cpf, 'senha': senha}
            checar(client.post('/api/autenticacao/verificar', json={'frames': frames}), 401, 'Biometria sem credenciais recusada')
            checar(client.post('/api/autenticacao/credenciais', json=cred), 200, 'CPF e senha antes da câmera')
            assert client.cookies.get('aps_desafio') and not client.cookies.get('aps_sessao')
            checar(client.get('/api/sessao'), 401, 'Desafio não autoriza o nível')
            token_desafio = client.cookies.get('aps_desafio')
            checar(client.post('/api/autenticacao/verificar', json={'frames': frames}), 200, 'Verificação facial 1:1')
            sessao = checar(client.get('/api/sessao'), 200, 'Sessão completa')
            assert sessao['usuario']['id'] == user_id and sessao['usuario']['nivel'] == 3
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
            if admin_id is not None:
                db.execute(delete(Sessao).where(Sessao.token_hash == sessao_admin_hash,
                                               Sessao.usuario_id == admin_id))
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

