# APS - API de autenticacao facial

API REST em Python 3.12, FastAPI e MySQL para cadastro e autenticacao biometrica facial. Este repositorio contem a API, os testes automatizados e os scripts de operacao. A interface web usada nos testes manuais nao faz parte do projeto publicado.

O processamento usa tecnicas classicas de imagem, sem detector de rostos, rede neural ou pesos pre-treinados. A biometria e experimental: o sistema nao comprova presenca de uma pessoa viva e nao deve ser usado sozinho para proteger recursos reais.

## Requisitos

- Python 3.12
- MySQL 8+ ou MariaDB para uma instalacao nova
- Uma chave `BIOMETRIC_KEY` com 32 bytes codificados em base64

As dependencias da aplicacao estao em `requirements.txt`. As dependencias adicionais para testes estao em `requirements-dev.txt`.

## Instalacao no Windows

Na raiz do repositorio, crie o ambiente virtual e instale as dependencias:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

Gere a configuracao local:

```powershell
.\.venv\Scripts\python.exe scripts\configurar.py
```

O script cria `.env` sem sobrescrever um arquivo existente. Ajuste nele a senha e os dados do banco:

```dotenv
DB_HOST=127.0.0.1
DB_PORT=3306
DB_NAME=aps_facial
DB_USER=aps_app
DB_PASSWORD=sua_senha
```

Prepare o banco executando `sql/criar_banco.sql` com uma conta administrativa. Depois crie as tabelas da versao atual:

```powershell
.\.venv\Scripts\python.exe -m app.inicializar
```

Nao versione `.env`, `BIOMETRIC_KEY`, bancos, backups ou o ambiente virtual.

## Executar a API

Inicie um unico worker do Uvicorn:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

O Swagger fica disponivel em:

- http://127.0.0.1:8000/docs
- http://127.0.0.1:8000/redoc
- http://127.0.0.1:8000/openapi.json

Verifique a conexao com o banco em `GET /api/saude`. O script abaixo executa uma verificacao integrada usando um usuario temporario:

```powershell
.\.venv\Scripts\python.exe -m scripts.verificar_mysql
```

## Endpoints

| Metodo | Rota | Finalidade |
| --- | --- | --- |
| `GET` | `/api/saude` | Verifica a disponibilidade do banco |
| `POST` | `/api/usuarios` | Cadastra um usuario e sua assinatura biometrica |
| `POST` | `/api/autenticacao/credenciais` | Valida CPF e senha e emite um desafio curto |
| `POST` | `/api/autenticacao/verificar` | Verifica os quadros contra a assinatura do desafio |
| `GET` | `/api/sessao` | Consulta o usuario da sessao atual |
| `POST` | `/api/sair` | Revoga a sessao e o desafio atual |

O fluxo de autenticacao ocorre em duas etapas:

1. Envie CPF e senha para `/api/autenticacao/credenciais`.
2. Preserve o cookie `aps_desafio` e envie os quadros RGB para `/api/autenticacao/verificar`.

Se a biometria for aceita, a API emite o cookie `aps_sessao`. O desafio expira em 120 segundos e a sessao dura 15 minutos.

Exemplo de corpo para cadastro ou verificacao:

```json
{
  "frames": [
    {"largura": 320, "altura": 240, "rgb_base64": "BYTES_RGB_EM_BASE64"},
    {"largura": 320, "altura": 240, "rgb_base64": "BYTES_RGB_EM_BASE64"},
    {"largura": 320, "altura": 240, "rgb_base64": "BYTES_RGB_EM_BASE64"}
  ]
}
```

Os quadros devem conter bytes RGB puros, sem cabecalho PNG ou JPEG. A API aceita de 3 a 5 quadros com dimensoes iguais, entre 160x120 e 640x480, e limita o corpo a 8 MiB. Consulte os schemas e experimente as requisicoes pelo Swagger.

## Testes

Os testes rapidos usam matrizes RGB sinteticas e bancos SQLite isolados; nao exigem MySQL nem camera:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Para executar apenas os testes basicos usados pelo inicializador local:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_biometria.py tests\test_seguranca.py
```

O teste de integracao MySQL e opt-in e usa tabelas temporarias com prefixo proprio:

```powershell
$env:APS_TEST_MYSQL = "1"
.\.venv\Scripts\python.exe -m pytest -q tests\test_migracao.py
```

Os testes verificam contratos, processamento, criptografia, sessoes, logs, limites HTTP e transacoes. Eles nao medem a acuracia biometrica em pessoas reais.

## Organizacao

| Local | Responsabilidade |
| --- | --- |
| `app/main.py` | Rotas, transacoes, sessoes e protecoes HTTP |
| `app/biometria.py` | Processamento, descritor e comparacao das capturas |
| `app/banco.py` | Modelos SQLAlchemy e conexao com o banco |
| `app/seguranca.py` | AES-GCM, HMAC, Argon2id e tokens |
| `app/esquemas.py` | Validacao dos dados recebidos pela API |
| `app/inicializar.py` | Criacao das tabelas da versao atual |
| `scripts/configurar.py` | Geracao da configuracao local |
| `scripts/verificar_mysql.py` | Verificacao integrada do banco |
| `tests/` | Testes automatizados |
| `docs/` | Documentacao tecnica do processamento |

## Seguranca

As assinaturas biometricas e os CPFs sao cifrados com AES-256-GCM. O CPF tambem possui um indice HMAC para busca sem armazenamento em texto claro. Senhas usam Argon2id; tokens de sessao e desafios sao armazenados apenas como hashes.

Respostas e logs nao incluem senha, CPF, token, imagem, pixels ou vetor biometrico. Em producao, use HTTPS e configure `COOKIE_SECURE=true`. A chave `BIOMETRIC_KEY` deve ser mantida em segredo e preservada junto aos dados cifrados.

Esta API nao implementa prova de vida, deteccao de apresentacao, gerenciamento de permissoes ou rotacao automatica de chaves.
