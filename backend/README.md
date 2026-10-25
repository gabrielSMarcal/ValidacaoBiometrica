# APS — Backend de autenticação facial

API em Python 3.12, FastAPI e MySQL/MariaDB para cadastro e autenticação biométrica facial. O processamento usa **YuNet** para detectar e localizar o rosto e **AuraFace v1 / ArcFace ResNet100** para extrair assinaturas de **512 dimensões**, com inferência local por OpenCV e ONNX Runtime.

O fluxo segue **aquisição → pré-processamento → segmentação → extração de características → classificação e interpretação**. A descrição dos estágios e do papel dos modelos está no [README da raiz](../README.md).

## Diretório de execução

**Todos os comandos deste README, exceto o primeiro `cd`, devem ser executados dentro da pasta `backend`.** A partir da raiz do repositório:

```powershell
cd .\backend
```

O ambiente virtual utilizado pelo `iniciar.bat` fica em `backend/.venv`. Um ambiente criado somente na raiz do repositório não é o ambiente que esse script procura.

## Requisitos

- Python 3.12 disponível pelo comando `py -3.12`.
- MySQL 8+ ou MariaDB ativo, com uma conta que possa acessar o banco e criar as tabelas. Atualizações de estrutura também exigem permissão `ALTER`.
- Internet para instalar as dependências e baixar os modelos na primeira preparação.
- Configuração local em `backend/.env` ou em variáveis de ambiente, conforme a seção de configuração.

O backend não instala nem inicia o servidor MySQL. Inicie-o antes da preparação do banco e da API.

## Inicialização pelo `.bat`

### Primeira execução nesta máquina

Dentro de `backend`, crie o ambiente virtual:

```powershell
py -3.12 -m venv .venv
```

Salve o `.env` recebido da equipe em **`backend/.env`**. Confira a conexão MySQL e preserve a chave biométrica original se estiver usando uma cópia de um banco existente. Para configurar uma instalação nova, consulte a seção de configuração abaixo.

Com o MySQL ativo e a configuração pronta, execute:

```powershell
.\iniciar.bat
```

O script realiza esta sequência:

1. Verifica a existência de `.venv\Scripts\python.exe` dentro de `backend`.
2. Instala as dependências de `requirements.txt` nesse ambiente virtual.
3. Executa `scripts\preparar_modelos.py`, que verifica os modelos locais e baixa os ausentes ou inválidos.
4. Executa `python -m app.inicializar`, que prepara o banco, atualiza a estrutura conhecida e cria o administrador quando necessário.
5. Inicia a API em `http://127.0.0.1:8000` e aguarda a resposta da verificação de saúde.

Se a instalação, a preparação dos modelos ou a preparação do banco falhar, o script interrompe a inicialização. Confira a mensagem exibida no terminal.

Nas próximas execuções, utilize novamente `iniciar.bat`. A `.venv` já existente é reutilizada, e os modelos válidos permanecem no disco.

## Execução manual

Com a `.venv` criada, o MySQL ativo e a configuração pronta, execute nesta ordem, **dentro de `backend`**:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts\preparar_modelos.py
.\.venv\Scripts\python.exe -m app.inicializar
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

**Executar apenas o Uvicorn não prepara os modelos nem atualiza o banco.** A `main` verifica o acesso ao esquema existente; o download dos pesos pertence ao preparador. Se os modelos estiverem ausentes ou inválidos, a operação biométrica retorna indisponibilidade e solicita a preparação.

Depois de concluir a preparação, é possível iniciar somente o último comando. Utilize um único worker: o controle de tentativas por IP é mantido em memória por processo.

## Configuração local

As variáveis de ambiente têm prioridade sobre os valores de `backend/.env`. O arquivo `.env` e a pasta `.runtime` são privados e ignorados pelo Git; eles não acompanham o `git pull`.

| Variável | Finalidade |
| --- | --- |
| `DB_HOST` | Endereço do MySQL; padrão `127.0.0.1`. |
| `DB_PORT` | Porta do MySQL; padrão `3306`. |
| `DB_NAME` | Nome do banco; padrão `aps_facial`. |
| `DB_USER` | Conta de acesso ao MySQL; padrão `root`. |
| `DB_PASSWORD` | Senha da conta MySQL; padrão vazio. |
| `ADMIN_CPF` | CPF válido reservado à criação do administrador de nível 4. |
| `ADMIN_PASSWORD_HASH` | Hash Argon2id da senha inicial do administrador. |
| `BIOMETRIC_KEY` | Chave de 32 bytes em base64 utilizada para proteger os dados cifrados. |
| `ALLOWED_ORIGINS` | Origens do cliente web autorizadas, separadas por vírgulas, incluindo protocolo, host e porta. |

Os padrões de conexão atendem a algumas instalações locais do XAMPP. Ajuste-os para a conta e o servidor efetivamente utilizados. O arquivo `sql/criar_banco.sql` é uma alternativa manual para provisionar a conta MySQL `aps_app`; ajuste a senha desse arquivo e a configuração da conexão antes de utilizá-lo.

Os parâmetros do reconhecimento facial ficam versionados em `app/politica_biometrica.py`: limite de correspondência `0.30`, margem `0.03`, limite de consistência entre quadros `0.25` e foco mínimo `1.5`. Entradas antigas `FACE_THRESHOLD` e `FACE_MARGIN` no `.env` ou nas variáveis de ambiente são ignoradas. A equipe recebe esses mesmos valores ao atualizar o código, sem compartilhar o `.env` privado. Mudanças futuras dessa política devem ser acompanhadas de testes com capturas genuínas e de pessoas diferentes.

### Criação do administrador

Quando ainda não existe um administrador no banco, a inicialização exige `ADMIN_CPF` e `ADMIN_PASSWORD_HASH`. O nível 4 é exclusivo desse administrador, cujo login usa CPF e senha sem exigir biometria.

Se o `.env` já foi fornecido pela equipe, mantenha os valores recebidos. Para definir uma nova senha inicial, instale primeiro `requirements.txt` e gere um hash com entrada oculta:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -c "from getpass import getpass; from argon2 import PasswordHasher; print(PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2).hash(getpass('Senha inicial do administrador: ')))"
```

Cole o hash gerado em `ADMIN_PASSWORD_HASH` no `.env` e informe o CPF em `ADMIN_CPF`. No login, utilize a senha original digitada, e não o hash. Nenhuma credencial real deve ser incluída no código ou neste README.

Um administrador já existente é preservado: reexecutar o inicializador não redefine sua senha. Se `ADMIN_CPF` estiver configurado e não corresponder ao administrador existente, a inicialização informa o conflito.

### Chave biométrica e banco compartilhado

Se `BIOMETRIC_KEY` não estiver definida no ambiente ou no `.env`, a aplicação gera uma chave uma única vez em `backend/.runtime/biometric.key` e a reutiliza.

**Uma cópia de um banco existente exige a mesma chave original.** Quando a chave não estiver no `.env`, transfira também o arquivo `.runtime/biometric.key` para o mesmo caminho na outra instalação. Uma chave nova não permite ler os CPFs e as assinaturas já cifrados.

### Configurador opcional

Após instalar as dependências, é possível gerar um `.env` inicial com a conexão e a chave biométrica:

```powershell
.\.venv\Scripts\python.exe scripts\configurar.py
```

O configurador não sobrescreve um `.env` existente. Ele também não preenche `ADMIN_CPF` nem `ADMIN_PASSWORD_HASH`; acrescente esses campos para a primeira criação do administrador.

### Cliente web

Inclua em `ALLOWED_ORIGINS` a origem real do front. Por exemplo, se ele estiver em `http://localhost:4200`, essa origem precisa estar autorizada; os padrões atuais incluem apenas os endereços locais das portas 5500 e 8080.

As chamadas de autenticação devem preservar os cookies. As operações de gerenciamento precisam enviar o cookie de uma sessão administrativa válida. Em requisições entre origens diferentes, o cliente deve habilitar o envio de credenciais; autorizar a origem no backend, isoladamente, não faz o navegador enviar cookies.

## Modelos locais e uso sem internet

Os modelos ficam em `backend/.runtime/modelos`:

| Arquivo | Função | Tamanho aproximado |
| --- | --- | --- |
| `face_detection_yunet_2023mar.onnx` | Detecção do rosto e localização de cinco pontos faciais. | 233 KB |
| `glintr100.onnx` | Reconhecimento AuraFace e extração de vetores de 512 dimensões. | 261 MB |

O preparador utiliza versões fixadas e confere tamanho e SHA-256. Arquivos válidos são reutilizados; somente os ausentes ou inválidos são baixados. A preparação pode ser executada novamente sem apagar a pasta dos modelos.

Com dependências, modelos e banco disponíveis, a inferência funciona sem internet e as capturas são processadas localmente. Para iniciar offline após a preparação, use o comando manual do Uvicorn. O `.bat` sempre executa a etapa de instalação das dependências, que pode precisar de acesso à internet.

## Atualizar uma instalação existente

Depois de obter a versão atualizada do código:

1. Preserve o `.env`, a chave biométrica e o banco existentes.
2. Execute `iniciar.bat` dentro de `backend`, com internet disponível para dependências e modelos que ainda não estejam instalados.
3. Entre com o administrador e recadastre as biometrias dos usuários que utilizavam o modelo anterior.

**Não é necessário limpar a base.** O inicializador preserva os cadastros, cria tabelas ausentes e adapta a estrutura conhecida de usuários. A conta MySQL precisa das permissões correspondentes, incluindo `ALTER` quando houver atualização estrutural.

Assinaturas produzidas pela MobileNet anterior, de 1.280 dimensões, ou por algoritmos legados são incompatíveis com o AuraFace. Elas são recusadas até o recadastro autorizado; não há conversão automática desses vetores para o modelo de 512 dimensões.

## API e autenticação

Com a API em execução:

- Swagger: http://127.0.0.1:8000/docs
- ReDoc: http://127.0.0.1:8000/redoc
- Contrato OpenAPI: http://127.0.0.1:8000/openapi.json
- Saúde do banco: http://127.0.0.1:8000/api/saude

| Método | Rota | Finalidade e acesso |
| --- | --- | --- |
| `GET` | `/api/saude` | Verifica a conexão com o banco. |
| `POST` | `/api/usuarios` | Cadastra usuário e biometria; exige administrador. |
| `GET` | `/api/usuarios` | Lista usuários; exige administrador. |
| `PATCH` | `/api/usuarios/{id}` | Edita nome, nível, status ou senha; exige administrador. |
| `PUT` | `/api/usuarios/{id}/biometria` | Recadastra a biometria; exige administrador. |
| `DELETE` | `/api/usuarios/{id}` | Exclui usuário; exige administrador. |
| `POST` | `/api/autenticacao/credenciais` | Confirma CPF e senha. Para usuários comuns, emite o desafio biométrico; para o admin, inicia a sessão. |
| `POST` | `/api/autenticacao/verificar` | Valida a captura contra a assinatura do usuário vinculado ao desafio. |
| `GET` | `/api/sessao` | Consulta o usuário da sessão válida. |
| `POST` | `/api/sair` | Revoga a sessão e o desafio do cliente. |

Para um usuário comum, confirme CPF e senha, preserve o cookie `aps_desafio` e envie a captura à verificação. O desafio dura 120 segundos e é consumido na tentativa. Se a biometria for aceita, a API emite `aps_sessao`; a duração padrão é de 15 minutos.

A comparação é facial **1:1**, exclusivamente com o usuário vinculado às credenciais. Alterar sua senha ou biometria invalida desafios anteriores; o recadastro biométrico também revoga suas sessões existentes. O administrador é protegido contra alteração e exclusão pelas APIs de gerenciamento.

### Formato da captura

A verificação e o recadastro biométrico recebem um objeto com `frames`. Cada quadro contém `largura`, `altura` e `rgb_base64`, com bytes RGB puros codificados em base64, sem cabeçalho PNG, JPEG ou prefixo de URL de dados.

São aceitos de três a cinco quadros com dimensões iguais, entre 160 × 120 e 640 × 480, com limite de requisição de 8 MiB. No cadastro inicial, o corpo inclui também `nome`, `cpf`, `senha` e `nivel`, conforme o Swagger. A assinatura de 512 dimensões é gerada no servidor a partir dos pixels recebidos.

### Diagnóstico de óculos e variações na captura

O terminal do Uvicorn exibe linhas com o prefixo `biometria_diagnostico`, em JSON. São registros internos: não acrescentam campos às respostas da API nem à tabela `logs_acesso` e não contêm CPF, senha, identificadores de usuários, imagens ou vetores biométricos.

O evento `captura` informa a qualidade dos quadros, a maior distância entre eles e o limite de consistência. Se o processamento de um quadro falhar, informa seu número e o motivo da recusa.

O evento `comparacao` é emitido tanto nas correspondências aceitas quanto nas recusadas. Ele descreve a comparação com o candidato de menor distância:

| Campo | Como interpretar |
| --- | --- |
| `distancia_media` | Distância entre o vetor médio da captura e a referência cadastrada. Não é a média das distâncias dos quadros. |
| `distancias_quadros` | Distância de cada quadro para a referência, na ordem de captura. Quanto menor, maior a semelhança. |
| `quadros_fora_do_limiar` | Números dos quadros que excederam o limite, começando em 1. |
| `distancia_decisao` | Maior valor entre `distancia_media` e `distancias_quadros`, todos calculados contra a referência cadastrada; é o valor usado na decisão. |
| `limiar` | Limite configurado de aceitação. Os valores exibidos são arredondados; a decisão usa a precisão original. |
| `identificado` e `motivo` | Resultado da comparação e motivo da aceitação ou recusa. |

Para investigar óculos, compare tentativas da mesma pessoa com e sem óculos, mantendo câmera, enquadramento e iluminação semelhantes, e repita testes com pessoas diferentes. Confirme CPF e senha novamente antes de cada tentativa: o desafio é consumido mesmo quando a biometria é recusada. Tentativas com `desafio_ausente` não chegam à comparação e não geram suas métricas.

Um quadro isolado acima do limite e todos os quadros acima do limite são situações diferentes; as métricas ajudam a distingui-las. Elas não detectam automaticamente óculos nem comprovam a causa da recusa. Esta instrumentação não muda os limiares, a assinatura cadastrada ou a exigência de correspondência de todos os quadros. O reconhecimento com óculos ainda precisa ser avaliado com capturas reais antes de qualquer calibração.

Confira o campo `limiar` no log: ele deve mostrar o valor `0.30` centralizado em `app/politica_biometrica.py`, mesmo em instalações que ainda tenham `FACE_THRESHOLD=0.20` no `.env`. Uma distância de decisão `0.28` fica dentro desse limite numa comparação 1:1. Depois de atualizar o código, reinicie a API e teste tanto a mesma pessoa com e sem óculos quanto pessoas diferentes; uma tentativa aceita não comprova a acurácia geral.

## Testes

Instale as dependências adicionais de desenvolvimento:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

### Suíte rápida

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Os testes rápidos utilizam SQLite isolado e substituem a detecção e a inferência facial por implementações sintéticas. Verificam contratos, autorização, criptografia, sessões, desafios, validação de entrada e falhas de integridade. Os testes com os pesos reais ficam desabilitados por padrão.

### Reconhecimento com os modelos reais

Com os modelos preparados:

```powershell
.\.venv\Scripts\python.exe scripts\preparar_modelos.py
$env:APS_TEST_MODELO_REAL = "1"
.\.venv\Scripts\python.exe -m pytest -q tests\test_biometria_modelo_real.py
Remove-Item Env:\APS_TEST_MODELO_REAL
```

Os sete testes reais usam as fotografias de teste em `tests/dados_faciais` e verificam embeddings de 512 dimensões, correspondência da mesma pessoa em fotos diferentes, rejeição de outra pessoa, imagens sem rosto, múltiplos rostos, assinaturas antigas e o fluxo completo pela API. Esses exemplos não constituem uma medição populacional de acurácia nem um teste de prova de vida.

### Integração com MySQL

Com MySQL configurado, esquema preparado, administrador ativo, dependências de desenvolvimento e modelos disponíveis:

```powershell
.\.venv\Scripts\python.exe -m scripts.verificar_mysql
```

Esse comando atua no banco configurado, cria um cadastro temporário e uma sessão administrativa de teste, verifica armazenamento e autenticação com o modelo real e remove os dados identificados como pertencentes à execução.

## Organização do backend

| Local | Responsabilidade |
| --- | --- |
| `app/main.py` | Rotas, autorização, transações, sessões e proteções HTTP. |
| `app/biometria.py` | Estágios do processamento, qualidade, alinhamento e comparação facial. |
| `app/modelos_faciais.py` | Preparação, integridade e inferência local dos modelos YuNet e AuraFace. |
| `app/banco.py` | Modelos SQLAlchemy e conexão com o banco. |
| `app/seguranca.py` | AES-GCM, HMAC, Argon2id e hashes de tokens. |
| `app/esquemas.py` | Validação dos dados recebidos pela API. |
| `app/config.py` | Leitura da configuração e gestão da chave local. |
| `app/politica_biometrica.py` | Parâmetros versionados do reconhecimento facial, sem sobrescrita pelo ambiente. |
| `app/inicializar.py` | Preparação do banco, atualização de estrutura e criação do admin. |
| `scripts/preparar_modelos.py` | Preparação explícita dos modelos faciais. |
| `scripts/configurar.py` | Geração opcional da configuração local. |
| `scripts/verificar_mysql.py` | Verificação integrada no banco MySQL configurado. |
| `iniciar.bat` | Instalação das dependências, preparação dos modelos e do banco e início da API. |
| `tests/` | Testes rápidos, de segurança e com os modelos reais. |

## Proteção dos dados e limites

CPFs e assinaturas biométricas são cifrados com AES-256-GCM. A busca por CPF utiliza índice HMAC, as senhas utilizam Argon2id e os tokens de sessão e desafio são armazenados como hashes. As respostas de autenticação e os logs não expõem senha, CPF, imagens ou vetores biométricos.

Guarde `.env`, `.runtime/biometric.key`, bancos e backups em locais privados. Esses arquivos e o ambiente virtual não devem ser versionados.

A prova de vida ainda não está implementada. Uma fotografia da própria identidade cadastrada pode ser reconhecida; a validação de identidade facial não comprova a presença de uma pessoa viva diante da câmera.
