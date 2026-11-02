"""Testes de autorização dos dossiês: python -m unittest discover -s backend/tests -v

Usa SQLite em memória; não depende do MySQL, da câmera nem dos modelos faciais.
Requer o pacote httpx (usado pelo TestClient do FastAPI): pip install httpx
"""
import base64
import importlib.util
import os
import sys
import unittest
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pydantic import SecretStr  # noqa: E402
from sqlalchemy import create_engine, func, select  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.inicializar import garantir_dossies  # noqa: E402
from app.main import (Base, Dossie, LogAcesso, Sessao, Settings, Usuario, agora, criar_app,  # noqa: E402
                      fabrica_sessoes, hash_token)

HTTPX = importlib.util.find_spec('httpx') is not None


@unittest.skipUnless(HTTPX, 'Instale httpx para executar os testes da API (pip install httpx).')
class DossiesTest(unittest.TestCase):

    def setUp(self):
        from fastapi.testclient import TestClient

        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False},
                                    poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        garantir_dossies(self.engine)
        self.sessions = fabrica_sessoes(self.engine)
        self.tokens = {nivel: self.criar_usuario(nivel) for nivel in (1, 2, 3, 4)}
        chave = base64.urlsafe_b64encode(os.urandom(32)).decode()
        app = criar_app(Settings(biometric_key=SecretStr(chave)), engine=self.engine)
        self.client = TestClient(app, base_url='http://localhost')
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.engine.dispose()

    def criar_usuario(self, nivel, expira_em_minutos=10):
        token = f'token-nivel-{nivel}-{expira_em_minutos}'
        with self.sessions() as db:
            user = Usuario(nome=f'Usuário {nivel}', cpf_indice=f'indice-{nivel}-{expira_em_minutos}',
                           cpf_cifrado=b'x', senha_hash='x', nivel=nivel, ativo=True,
                           assinatura_cifrada=None if nivel == 4 else b'x')
            db.add(user)
            db.flush()
            db.add(Sessao(token_hash=hash_token(token), usuario_id=user.id,
                          expira_em=agora() + timedelta(minutes=expira_em_minutos)))
            db.commit()
        return token

    def get(self, caminho, nivel=None, token=None):
        token = token or (self.tokens[nivel] if nivel else None)
        headers = {'Cookie': f'aps_sessao={token}'} if token else {}
        return self.client.get(caminho, headers=headers)

    def codigos(self, nivel):
        resposta = self.get('/api/dossies', nivel)
        self.assertEqual(resposta.status_code, 200)
        return [d['codigo'] for d in resposta.json()['dossies']]

    def test_exige_sessao_biometrica(self):
        self.assertEqual(self.get('/api/dossies').status_code, 401)
        self.assertEqual(self.get('/api/dossies/DOS-2026-014').status_code, 401)

    def test_sessao_expirada_e_negada(self):
        token = self.criar_usuario(1, expira_em_minutos=-1)
        self.assertEqual(self.get('/api/dossies', token=token).status_code, 401)

    def test_administrador_nao_consulta_dossies(self):
        self.assertEqual(self.get('/api/dossies', 4).status_code, 403)
        self.assertEqual(self.get('/api/dossies/DOS-2026-031', 4).status_code, 403)

    def test_cada_nivel_lista_somente_seus_recortes(self):
        self.assertEqual(sorted(self.codigos(1)), ['DOS-2026-014', 'DOS-2026-021'])
        self.assertEqual(sorted(self.codigos(2)), ['DOS-2026-014', 'DOS-2026-021', 'DOS-2026-027'])
        self.assertEqual(sorted(self.codigos(3)),
                         ['DOS-2026-014', 'DOS-2026-021', 'DOS-2026-027', 'DOS-2026-031'])

    def test_indicadores_calculados_dos_registros(self):
        por_codigo = {d['codigo']: d for d in self.get('/api/dossies', 2).json()['dossies']}
        self.assertEqual(por_codigo['DOS-2026-014']['pendencias_abertas'], 2)
        self.assertEqual(por_codigo['DOS-2026-014']['decisoes_pendentes'], 0)
        nivel3 = {d['codigo']: d for d in self.get('/api/dossies', 3).json()['dossies']}
        self.assertEqual(nivel3['DOS-2026-027']['decisoes_pendentes'], 2)
        self.assertEqual(nivel3['DOS-2026-031']['decisoes_pendentes'], 1)

    def test_mesmo_dossie_tem_recortes_diferentes(self):
        recortes = {n: self.get('/api/dossies/dos-2026-014', n).json()['recorte'] for n in (1, 2, 3)}
        self.assertEqual([r['nivel'] for r in recortes.values()], [1, 2, 3])
        self.assertEqual(recortes[1]['pendencias'], [])
        self.assertEqual(recortes[1]['decisoes'], [])
        self.assertEqual(len(recortes[2]['pendencias']), 3)
        self.assertEqual(recortes[2]['decisoes'], [])
        self.assertEqual(recortes[3]['pendencias'], [])
        self.assertEqual(len(recortes[3]['decisoes']), 1)
        texto_nivel1 = str(recortes[1])
        self.assertNotIn('Equipe técnica 3', texto_nivel1)
        self.assertNotIn('comunicação preventiva', texto_nivel1)

    def test_tentativa_nao_autorizada_e_negada_e_registrada(self):
        resposta = self.get('/api/dossies/DOS-2026-027', 1)
        inexistente = self.get('/api/dossies/DOS-2026-999', 1)
        self.assertEqual(resposta.status_code, 404)
        self.assertEqual(inexistente.status_code, 404)
        self.assertEqual(resposta.json(), inexistente.json())  # Não revela se o dossiê existe.
        self.assertEqual(self.get('/api/dossies/DOS-2026-031', 2).status_code, 404)
        with self.sessions() as db:
            motivos = set(db.scalars(select(LogAcesso.motivo).where(
                LogAcesso.evento == 'dossie', LogAcesso.sucesso.is_(False))))
        self.assertIn('sem_recorte DOS-2026-027', motivos)
        self.assertIn('inexistente DOS-2026-999', motivos)

    def test_codigo_invalido(self):
        self.assertEqual(self.get('/api/dossies/abc', 1).status_code, 404)

    def test_carga_idempotente(self):
        self.assertEqual(garantir_dossies(self.engine), 0)
        with self.sessions() as db:
            self.assertEqual(db.scalar(select(func.count(Dossie.id))), 4)


if __name__ == '__main__':
    unittest.main()
