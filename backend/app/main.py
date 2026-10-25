from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import timedelta
import hashlib
import secrets
from threading import Lock
from time import monotonic
from uuid import uuid4

from cryptography.exceptions import InvalidTag
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import delete, select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .banco import DesafioBiometrico, LogAcesso, Sessao, Usuario, agora, criar_engine, fabrica_sessoes
from .biometria import ALGORITMO, BiometriaErro, BiometriaIndisponivel, classificacao_interpretacao, processar_captura
from .config import Settings
from .esquemas import Cadastro, Captura, Credenciais, UsuarioAtualizacao
from .seguranca import Seguranca, hash_token

COOKIE = 'aps_sessao'
DESAFIO_COOKIE = 'aps_desafio'
DESAFIO_SEGUNDOS = 120
MAX_BODY = 8 * 1024 * 1024


class ProtecoesHTTP:
 
    """
    Limita bytes antes do parser; bloqueia origens não autorizadas e rajadas.

    Limite em memória por IP/processo: executar um worker nesta demonstração.
    """
    def __init__(self, app, settings):
    
        self.app, self.settings = app, settings
        self.tentativas = defaultdict(deque)
        self.lock = Lock()

    async def __call__(self, scope, receive, send):
    
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
    
        scope.setdefault('state', {})['requisicao_id'] = str(uuid4())
        headers = dict(scope['headers'])
        api_write = scope['path'].startswith('/api/') and scope['method'] in {'POST', 'PUT', 'PATCH', 'DELETE'}

        async def reject(code, message):
            await JSONResponse({'detail': message}, status_code=code)(scope, receive, send_headers)

        async def send_headers(message):
    
            if message['type'] == 'http.response.start':
    
                message['headers'] = list(message.get('headers', [])) + [
                    (b'cache-control', b'no-store'), (b'x-content-type-options', b'nosniff'),
                    (b'x-frame-options', b'DENY'), (b'referrer-policy', b'no-referrer'),
                    (b'permissions-policy', b'camera=(self), microphone=()'),
                    (b'x-request-id', scope['state']['requisicao_id'].encode()),
                ]
    
            await send(message)

        if api_write:
    
            origin = headers.get(b'origin', b'').decode('latin-1').rstrip('/')
            site = headers.get(b'sec-fetch-site')
    
            if (origin and origin not in self.settings.origins) or (not origin and site == b'cross-site'):
                return await reject(403, 'Origem não autorizada.')
    
            requer_json = scope['method'] in {'POST', 'PUT', 'PATCH'} and scope['path'] != '/api/sair'
    
            if requer_json and headers.get(b'content-type', b'').split(b';')[0].strip().lower() != b'application/json':
                return await reject(415, 'Envie application/json com quadros RGB da câmera.')
    
            ip = (scope.get('client') or ('local', 0))[0]
            now = monotonic()
    
            with self.lock:
                
                if len(self.tentativas) > 1000:
                    self.tentativas = defaultdict(deque, {k: v for k, v in self.tentativas.items() if v and now - v[-1] < 60})
                
                fila = self.tentativas[ip]
                
                while fila and now - fila[0] >= 60:
                    fila.popleft()
                
                blocked = len(fila) >= self.settings.rate_limit_per_minute
                
                if not blocked:
                    fila.append(now)
            
            if blocked:
                return await reject(429, 'Muitas tentativas. Aguarde um minuto.')
            
            raw_length = headers.get(b'content-length')
            
            if raw_length:
            
                try:
                    length = int(raw_length)
            
                except ValueError:
                    return await reject(400, 'Tamanho da requisição inválido.')
            
                if length < 0 or length > MAX_BODY:
                    return await reject(413, 'Captura acima do limite de 8 MiB.')
            
            body = bytearray()
            
            while True:
            
                message = await receive()
            
                if message['type'] == 'http.disconnect':
                    return
            
                body.extend(message.get('body', b''))
            
                if len(body) > MAX_BODY:
                    return await reject(413, 'Captura acima do limite de 8 MiB.')
            
                if not message.get('more_body', False):
                    break
            
            original_receive = receive
            pending = True

            async def receive_body():
            
                nonlocal pending
            
                if pending:
                    pending = False
                    return {'type': 'http.request', 'body': bytes(body), 'more_body': False}
            
                return await original_receive()

            return await self.app(scope, receive_body, send_headers)
        
        return await self.app(scope, receive, send_headers)


def criar_app(settings: Settings | None = None, engine=None) -> FastAPI:
    
    settings = settings or Settings()
    db_engine = engine if engine is not None else criar_engine(settings)
    sessions = fabrica_sessoes(db_engine)
    seguranca = Seguranca(settings.biometric_key.get_secret_value())

    @asynccontextmanager
    async def lifespan(_app):
    
        try:
            with db_engine.connect() as connection:
                connection.execute(select(Usuario.id, Usuario.biometria_ref).limit(1))
                connection.execute(select(DesafioBiometrico.token_hash).limit(1))
    
        except SQLAlchemyError:
            raise RuntimeError('Banco indisponível ou esquema desatualizado. Confira MySQL/.env e execute a inicialização ou scripts.migrar_banco para bancos antigos.') from None
    
        yield
    
        db_engine.dispose()

    app = FastAPI(title='APS • Biometria por câmera', version='2.0.0', lifespan=lifespan,
                  description='Protótipo acadêmico: segmentação guiada, sem detector pronto e sem prova de vida. Níveis 1, 2 e 3 são grupos, sem permissões definidas.')
    app.state.engine = db_engine
    app.add_middleware(ProtecoesHTTP, settings=settings)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=['localhost', '127.0.0.1', '[::1]', 'testserver'])
    app.add_middleware(
        CORSMiddleware,
        allow_origins=sorted(settings.origins),
        allow_credentials=True,
        allow_methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE'],
        allow_headers=['Accept', 'Content-Type'],
    )

    def banco():
    
        with sessions() as session:
    
            try:
                yield session
    
            except Exception:
                session.rollback()
                raise

    def log(db, request, evento, sucesso, motivo, usuario_id=None):
    
        db.add(LogAcesso(usuario_id=usuario_id, evento=evento, sucesso=sucesso,
                        motivo=motivo, requisicao_id=request.state.requisicao_id))

    def negar(db, request, evento, motivo, status=401, mensagem='Não foi possível validar o usuário.', usuario_id=None):
    
        log(db, request, evento, False, motivo, usuario_id)
        db.commit()
    
        raise HTTPException(status, mensagem)

    def administrador(request: Request, db=Depends(banco)):
        token = request.cookies.get(COOKIE)
        sessao = db.get(Sessao, hash_token(token)) if token else None
        user = db.get(Usuario, sessao.usuario_id) if sessao and sessao.expira_em > agora() else None

        if not user or not user.ativo:
            negar(db, request, 'administracao', 'sessao_invalida', 401,
                  'Sessão ausente ou expirada. Entre novamente.')
        if user.nivel != 4:
            negar(db, request, 'administracao', 'nivel_insuficiente', 403,
                  'Acesso reservado ao administrador.', user.id)
        return user

    def captura(db, request, dados, evento):
    
        try:
            return processar_captura([frame.model_dump() for frame in dados.frames])
    
        except BiometriaIndisponivel as exc:
            negar(db, request, evento, 'modelo_indisponivel', 503, str(exc))
        except BiometriaErro as exc:
            negar(db, request, evento, 'captura_invalida', 422, str(exc))

    def assinatura(db, request, user, evento):
    
        try:
            return seguranca.decifrar(user.assinatura_cifrada, user.biometria_ref, 'biometria')
    
        except (InvalidTag, ValueError, TypeError):
            negar(db, request, evento, 'integridade_assinatura', 503,
                  'Assinatura indisponível. Confira a chave e a integridade do banco.', user.id)

    def publico(user):
        return {'id': user.id, 'nome': user.nome, 'nivel': user.nivel}

    def fingerprint_autorizacao(user):
        digest = hashlib.sha256(user.senha_hash.encode('utf-8') + b'\x00')
        digest.update(user.assinatura_cifrada or b'')
        return digest.hexdigest()

    def publico_administrativo(user):
        return {**publico(user), 'ativo': user.ativo,
                'criado_em': user.criado_em.isoformat(timespec='seconds') + 'Z'}

    def revogar_anterior(db, request):
    
        token = request.cookies.get(COOKIE)
    
        if token:
            db.execute(delete(Sessao).where(Sessao.token_hash == hash_token(token)))

    def revogar_desafio(db, request):
    
        token = request.cookies.get(DESAFIO_COOKIE)
    
        if token:
            db.execute(delete(DesafioBiometrico).where(DesafioBiometrico.token_hash == hash_token(token)))

    def limpar_cookies(response):
    
        for name in (COOKIE, DESAFIO_COOKIE):
            response.delete_cookie(name, path='/', secure=settings.cookie_secure,
                                   httponly=True, samesite='strict')

    def autenticar(db, request, response, user, processamento, evento, motivo='reconhecido'):
    
        token = secrets.token_urlsafe(32)
        db.execute(delete(Sessao).where(Sessao.expira_em <= agora()))
        db.add(Sessao(token_hash=hash_token(token), usuario_id=user.id,
                      expira_em=agora() + timedelta(minutes=settings.session_minutes)))
        log(db, request, evento, True, motivo, user.id)
        db.commit()
        response.set_cookie(COOKIE, token, max_age=settings.session_minutes * 60,
                            httponly=True, secure=settings.cookie_secure, samesite='strict', path='/')
        response.delete_cookie(DESAFIO_COOKIE, path='/', secure=settings.cookie_secure,
                               httponly=True, samesite='strict')
    
        return {'usuario': publico(user), 'processamento': processamento}

    @app.exception_handler(RequestValidationError)
    def validacao_erro(request, exc):
        
        erros = [{'loc': list(e['loc']), 'msg': e['msg'], 'type': e['type']} for e in exc.errors()]
        resposta = JSONResponse({'detail': erros}, status_code=422)
        
        if request.url.path in ('/api/autenticacao/credenciais', '/api/autenticacao/verificar'):
            
            try:
                with sessions() as db:
                    revogar_anterior(db, request)
                    revogar_desafio(db, request)
                    db.commit()
            
            except SQLAlchemyError:
                resposta = JSONResponse({'detail': 'Banco indisponível.'}, status_code=503)
            
            limpar_cookies(resposta)
        
        return resposta

    @app.exception_handler(SQLAlchemyError)
    async def banco_erro(request, exc):
        
        resposta = JSONResponse({'detail': 'Banco indisponível. Verifique o serviço MySQL e a configuração local.'}, status_code=503)
        
        if request.url.path.startswith('/api/autenticacao/'):
            limpar_cookies(resposta)
        
        return resposta

    @app.exception_handler(HTTPException)
    async def http_erro(request, exc):
        
        resposta = JSONResponse({'detail': exc.detail}, status_code=exc.status_code, headers=exc.headers)
        
        if request.url.path.startswith('/api/autenticacao/'):
            limpar_cookies(resposta)
        
        elif request.url.path == '/api/sessao':
            resposta.delete_cookie(COOKIE, path='/', secure=settings.cookie_secure, httponly=True, samesite='strict')
        
        return resposta

    @app.get('/api/saude', tags=['Sistema'])
    def saude(db=Depends(banco)):
        
        db.execute(text('SELECT 1'))
        
        return {'status': 'ok', 'banco': 'ok', 'algoritmo': ALGORITMO,
                'framework': 'ONNX Runtime', 'prova_de_vida': False}

    @app.post('/api/usuarios', status_code=201, tags=['Cadastro'], dependencies=[Depends(administrador)])
    def cadastrar(dados: Cadastro, request: Request, db=Depends(banco)):
        
        cpf_indice = seguranca.indice_cpf(dados.cpf)
        
        if db.scalar(select(Usuario.id).where(Usuario.cpf_indice == cpf_indice)):
            negar(db, request, 'cadastro', 'cpf_duplicado', 409, 'CPF já cadastrado.')
        if dados.frames is None:
            sig, processamento = None, {'etapas': [], 'quadros': 0}
        else:
            sig, processamento = captura(db, request, dados, 'cadastro')
        referencia = str(uuid4())
        
        user = Usuario(biometria_ref=referencia, nome=dados.nome, cpf_indice=cpf_indice,
                       cpf_cifrado=seguranca.cifrar({'cpf': dados.cpf}, referencia, 'cpf'),
                       senha_hash=seguranca.senhas.hash(dados.senha), nivel=dados.nivel,
                       assinatura_cifrada=(
                           seguranca.cifrar(sig, referencia, 'biometria')
                           if sig is not None else None
                       ))
        
        try:
            db.add(user)
            db.flush()
            log(db, request, 'cadastro', True, 'cadastrado', user.id)
            db.commit()
        
        except IntegrityError:
            db.rollback()
            negar(db, request, 'cadastro', 'conflito_cadastro', 409, 'Cadastro já existente ou dados em conflito.')
        
        return {'usuario': publico(user), 'processamento': processamento}

    @app.get('/api/usuarios', tags=['Usuários'], dependencies=[Depends(administrador)])
    def listar_usuarios(db=Depends(banco)):
        
        usuarios = db.scalars(select(Usuario).order_by(Usuario.id)).all()
        
        return {'usuarios': [publico_administrativo(user) for user in usuarios]}

    @app.patch('/api/usuarios/{usuario_id}', tags=['Usuários'], dependencies=[Depends(administrador)])
    def atualizar_usuario(usuario_id: int, dados: UsuarioAtualizacao,
                          request: Request, db=Depends(banco)):
        
        user = db.get(Usuario, usuario_id)
        
        if not user:
            raise HTTPException(404, 'Usuário não encontrado.')
        if user.nivel == 4:
            raise HTTPException(403, 'O administrador é reservado à inicialização do sistema.')
        
        if dados.nome is not None:
            user.nome = dados.nome
        
        if dados.nivel is not None:
            user.nivel = dados.nivel
        
        if dados.ativo is not None:
            user.ativo = dados.ativo
        
        if dados.senha is not None:
            user.senha_hash = seguranca.senhas.hash(dados.senha)
        
        if dados.senha is not None or dados.ativo is False:
            db.execute(delete(Sessao).where(Sessao.usuario_id == user.id))
            db.execute(delete(DesafioBiometrico).where(DesafioBiometrico.usuario_id == user.id))
        
        log(db, request, 'usuario_atualizado', True, 'atualizado', user.id)
        db.commit()
        
        return {'usuario': publico_administrativo(user)}

    @app.put('/api/usuarios/{usuario_id}/biometria', tags=['Usuários'], dependencies=[Depends(administrador)])
    def atualizar_biometria(usuario_id: int, dados: Captura,
                            request: Request, db=Depends(banco)):
        
        user = db.get(Usuario, usuario_id)
        
        if not user:
            raise HTTPException(404, 'Usuário não encontrado.')
        if user.nivel == 4:
            raise HTTPException(403, 'O administrador não utiliza biometria.')
        
        sig, processamento = captura(db, request, dados, 'biometria_atualizada')
        user.assinatura_cifrada = seguranca.cifrar(sig, user.biometria_ref, 'biometria')
        db.execute(delete(Sessao).where(Sessao.usuario_id == user.id))
        db.execute(delete(DesafioBiometrico).where(DesafioBiometrico.usuario_id == user.id))
        log(db, request, 'biometria_atualizada', True, 'recadastrada', user.id)
        db.commit()
        
        return {'usuario': publico_administrativo(user), 'processamento': processamento}

    @app.delete('/api/usuarios/{usuario_id}', status_code=204, tags=['Usuários'], dependencies=[Depends(administrador)])
    def excluir_usuario(usuario_id: int, request: Request, db=Depends(banco)):
        
        user = db.get(Usuario, usuario_id)
        
        if not user:
            raise HTTPException(404, 'Usuário não encontrado.')
        if user.nivel == 4:
            raise HTTPException(403, 'O administrador não pode ser excluído.')
        
        log(db, request, 'usuario_excluido', True, 'excluido', user.id)
        db.delete(user)
        db.commit()
        
        return Response(status_code=204)

    @app.post('/api/autenticacao/credenciais', tags=['Autenticação'])
    def validar_credenciais(dados: Credenciais, request: Request, response: Response, db=Depends(banco)):
        
        revogar_anterior(db, request)
        revogar_desafio(db, request)
        
        user = db.scalar(select(Usuario).where(Usuario.cpf_indice == seguranca.indice_cpf(dados.cpf)))
        
        if not seguranca.verificar_senha(dados.senha, user.senha_hash if user else None) or not user or not user.ativo:
            negar(db, request, 'credenciais', 'credenciais_invalidas', mensagem='CPF ou senha inválidos.')
        
        if seguranca.senhas.check_needs_rehash(user.senha_hash):
            user.senha_hash = seguranca.senhas.hash(dados.senha)
        if user.nivel == 4:
            autenticar(db, request, response, user, None, 'credenciais', motivo='administrador')
            return {'mensagem': 'CPF e senha confirmados. Sessão administrativa iniciada.',
                    'expira_em_segundos': settings.session_minutes * 60,
                    'usuario': publico(user)}
        
        token = secrets.token_urlsafe(32)
        db.execute(delete(DesafioBiometrico).where(DesafioBiometrico.expira_em <= agora()))
        db.add(DesafioBiometrico(token_hash=hash_token(token), usuario_id=user.id,
                                expira_em=agora() + timedelta(seconds=DESAFIO_SEGUNDOS),
                                senha_fingerprint=fingerprint_autorizacao(user)))
        log(db, request, 'credenciais', True, 'aguardando_biometria', user.id)
        db.commit()
        response.delete_cookie(COOKIE, path='/', secure=settings.cookie_secure, httponly=True, samesite='strict')
        response.set_cookie(DESAFIO_COOKIE, token, max_age=DESAFIO_SEGUNDOS,
                            httponly=True, secure=settings.cookie_secure, samesite='strict', path='/')
        
        return {'mensagem': 'CPF e senha confirmados. Continue com a biometria.',
                'expira_em_segundos': DESAFIO_SEGUNDOS}

    @app.post('/api/autenticacao/verificar', tags=['Autenticação'])
    def verificar(dados: Captura, request: Request, response: Response, db=Depends(banco)):
        
        revogar_anterior(db, request)
        
        token = request.cookies.get(DESAFIO_COOKIE)
        desafio = db.scalar(select(DesafioBiometrico).where(
            DesafioBiometrico.token_hash == hash_token(token)).with_for_update()) if token else None
        
        if not desafio:
            negar(db, request, 'verificacao', 'desafio_ausente', mensagem='Confirme CPF e senha antes da biometria.')
        user_id, fingerprint, expiracao = desafio.usuario_id, desafio.senha_fingerprint, desafio.expira_em
        
        db.delete(desafio)
        db.commit()
        
        if expiracao <= agora():
            negar(db, request, 'verificacao', 'desafio_expirado', mensagem='O prazo da biometria expirou. Informe CPF e senha novamente.')
        
        user = db.get(Usuario, user_id)
        
        if not user or not user.ativo or fingerprint_autorizacao(user) != fingerprint:
            negar(db, request, 'verificacao', 'desafio_invalidado', mensagem='A autorização mudou. Informe CPF e senha novamente.')
        sig, processamento = captura(db, request, dados, 'verificacao')
        
        armazenada = assinatura(db, request, user, 'verificacao')
        
        try:
            resultado = classificacao_interpretacao(sig, [(str(user.id), armazenada)], settings.face_threshold, settings.face_margin)
        
        except BiometriaErro:
            negar(db, request, 'verificacao', 'assinatura_invalida', 503, 'Assinatura incompatível. Contate o operador.')
        
        if not resultado['identificado']:
            negar(db, request, 'verificacao', 'face_nao_corresponde', mensagem='CPF e senha foram confirmados, mas a biometria não correspondeu. Repita a validação com o mesmo enquadramento e iluminação do cadastro.')
        
        processamento['classificacao_interpretacao'] = resultado
        db.refresh(user, with_for_update=True)
        
        if not user.ativo or fingerprint_autorizacao(user) != fingerprint:
            negar(db, request, 'verificacao', 'desafio_invalidado', mensagem='A autorização mudou. Informe CPF e senha novamente.')
        
        return autenticar(db, request, response, user, processamento, 'verificacao')

    @app.get('/api/sessao', tags=['Sessão'])
    def sessao(request: Request, db=Depends(banco)):
        token = request.cookies.get(COOKIE)
        session = db.get(Sessao, hash_token(token)) if token else None
        user = db.get(Usuario, session.usuario_id) if session and session.expira_em > agora() else None
        if not user or not user.ativo:
            raise HTTPException(401, 'Sessão ausente ou expirada. Valide seu rosto novamente.')
        return {'usuario': publico(user), 'mensagem': f'Você é do nível {user.nivel}'}

    @app.post('/api/sair', tags=['Sessão'])
    def sair(request: Request, response: Response, db=Depends(banco)):
        revogar_anterior(db, request)
        revogar_desafio(db, request)
        db.commit()
        limpar_cookies(response)
        return {'mensagem': 'Sessão encerrada.'}

    @app.get('/', include_in_schema=False)
    def inicio():
        return RedirectResponse('/docs')

    return app


app = criar_app()
