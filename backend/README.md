# APS - API de autenticacao facial

API em Python 3.12, FastAPI, TensorFlow e MySQL para cadastro e autenticacao biometrica facial.

O processamento em `app/biometria.py` usa TensorFlow e MobileNetV2 com pesos ImageNet para extrair um embedding de 1.280 componentes da regiao facial guiada. A biometria e experimental: o sistema nao comprova presenca de uma pessoa viva e nao deve ser usado sozinho para proteger recursos reais.

## Requisitos

- Python 3.12
- MySQL 8+ ou MariaDB para uma instalacao nova
- MySQL ativo e uma conta com acesso ao banco (permissão CREATE na primeira inicialização)

As dependencias da aplicacao estao em `requirements.txt`. As dependencias adicionais para testes estao em `requirements-dev.txt`.

## Instalacao no Windows

Na raiz do repositorio, crie o ambiente virtual e instale as dependencias:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

Com o MySQL local ativo, prepare o banco e as tabelas:

```powershell
.\.venv\Scripts\python.exe -m app.inicializar
```

Não é necessário `.env` nem `.env.example`. Em uma instalação nova, a conexão padrão é `127.0.0.1:3306`, banco `aps_facial`, usuário `root`, senha vazia (comum no MySQL local do XAMPP). Se o servidor usa outra conta ou senha, informe as credenciais reais por variáveis de ambiente antes de inicializar:

```powershell
$env:DB_USER = "seu_usuario_mysql"
$env:DB_PASSWORD = "sua_senha"
.\.venv\Scripts\python.exe -m app.inicializar
```

O inicializador cria o banco configurado somente se ele não existir, depois cria as tabelas ausentes, preservando dados. Não instala nem inicia o servidor MySQL e não cria contas ou altera senhas. Um banco já existente não exige permissão para criar outros bancos. `iniciar.bat` também executa essa preparação antes de iniciar a API.

Se preferir salvar a configuração em arquivo, execute o comando opcional:

```powershell
.\.venv\Scripts\python.exe scripts\configurar.py
```

Ele gera `.env` diretamente, sem template, e nunca sobrescreve um arquivo existente. Ajuste nele a conexão:

```dotenv
DB_HOST=127.0.0.1
DB_PORT=3306
DB_NAME=aps_facial
DB_USER=aps_app
DB_PASSWORD=sua_senha
```

Para um MySQL hospedado, basta mudar `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER` e `DB_PASSWORD` no ambiente ou no `.env`, sem alterar o código. Variáveis do ambiente têm prioridade. Use a conta fornecida pela hospedagem. O arquivo `sql/criar_banco.sql` continua disponível como alternativa manual para provisionar a conta `aps_app`; ajuste a senha no SQL e na conexão.

Quando `BIOMETRIC_KEY` não é informada, uma chave é gerada uma única vez em `.runtime/biometric.key` e reutilizada nas próximas execuções. Uma chave definida no ambiente ou no `.env` tem prioridade e nunca é substituída. O configurador utiliza essa mesma chave. Ao transferir um banco com dados cifrados para outra máquina/hospedagem, preserve a chave original e defina `BIOMETRIC_KEY` lá; uma chave nova não permite ler os dados antigos.

Nao versione `.env`, `.runtime/biometric.key`, bancos, backups ou o ambiente virtual.

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
| `GET` | `/api/usuarios` | Lista os dados de gerenciamento dos usuarios |
| `PATCH` | `/api/usuarios/{id}` | Edita nome, nivel, status ou senha |
| `PUT` | `/api/usuarios/{id}/biometria` | Recadastra a assinatura pela camera |
| `DELETE` | `/api/usuarios/{id}` | Exclui o usuario e revoga seus acessos |
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
| `app/biometria.py` | Qualidade, recorte, TensorFlow, embedding e comparacao |
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

Respostas e logs nao incluem senha, CPF, token, imagem, pixels ou vetor biometrico. A chave `BIOMETRIC_KEY` deve ser mantida em segredo e preservada junto aos dados cifrados.

Esta API nao implementa prova de vida, deteccao de apresentacao, gerenciamento de permissoes ou rotacao automatica de chaves. Assinaturas da versao anterior (`aps-lbp59-gradientes-v1`) sao incompatíveis com o embedding TensorFlow e precisam ser recadastradas.
