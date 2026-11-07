# APS — Processamento de imagens e reconhecimento facial

Autenticação com CPF, senha e verificação facial 1:1. O frontend usa Angular; o backend usa FastAPI, MySQL, YuNet e AuraFace com ONNX Runtime. TensorFlow e Keras não fazem parte da execução atual.

## Requisitos de instalação

Para executar o projeto após clonar o repositório, instale e configure:

| Requisito | Configuração necessária |
| --- | --- |
| Python | **3.12**, com `pip`, `venv` e `ensurepip`. No Windows, habilite o launcher `py` ou adicione o Python ao `PATH`. |
| Node.js | **22**, na versão **22.22.3 ou superior da linha 22.x**, com npm. |
| MySQL | Servidor instalado e ativo. O usuário indicado no `.env` precisa existir e ter permissões para acessar o banco e criar/atualizar suas tabelas. |
| Configuração | Arquivo `.env` disponibilizado pela equipe, salvo em **`backend/.env`**, com conexão MySQL e administrador inicial configurados. |
| Internet | Necessária para instalar dependências, baixar os modelos faciais e carregar os recursos MediaPipe usados pelo navegador. |
| Câmera | Disponível e autorizada no navegador para cadastro e reconhecimento facial. |
| Portas | **8000** e **4200** disponíveis para a API e o frontend. |

As pastas `.venv`, `node_modules` e `.runtime` **não precisam acompanhar o repositório**. Os inicializadores criam o ambiente e os diretórios necessários, instalam as dependências e baixam os modelos ausentes. Instalar somente `backend/requirements.txt` cobre as dependências Python; o frontend também depende dos pacotes npm.

## Primeira execução no Windows

1. Instale os requisitos acima e clone o repositório.
2. Copie o `.env` disponibilizado para a pasta `backend`, mantendo o nome exato `.env`.
3. Confira se a conexão do `.env` corresponde ao MySQL dessa máquina e inicie o serviço do banco.
4. Abra um terminal na raiz do projeto, onde está o arquivo `iniciar.bat`, e execute:

```powershell
.\iniciar.bat
```

O inicializador realiza automaticamente estas etapas:

1. Cria a `.venv` na raiz usando o Python 3.12 instalado, quando não houver um ambiente funcional.
2. Instala as dependências de `backend/requirements.txt`.
3. Cria `backend/.runtime/modelos` e baixa os modelos YuNet e AuraFace ausentes, verificando tamanho e SHA-256.
4. Prepara o banco, as tabelas, o administrador inicial e os dossiês demonstrativos.
5. Instala as dependências npm do frontend.
6. Inicia a API e o frontend e abre a aplicação no navegador após a compilação.

O download inicial dos modelos soma aproximadamente **261 MB** e pode demorar conforme a conexão. Nas próximas execuções, modelos locais íntegros são reutilizados. Se já existir uma `.venv` funcional na raiz ou em `backend`, ela também é reutilizada. Uma `.venv` existente e inválida na raiz é preservada e precisa ser revisada antes de continuar.

- Aplicação: http://localhost:4200
- API e Swagger: http://localhost:8000/docs

Mantenha o terminal aberto e use **Ctrl+C** para encerrar os servidores. Os logs ficam em `backend/.runtime/` e são renovados a cada inicialização.

## Primeira execução no Linux

Instale os mesmos requisitos, coloque o `.env` em `backend/.env` e inicie o MySQL. Na raiz do projeto, execute:

```bash
bash ./iniciar.sh
```

O Python 3.12 deve estar disponível como `python3.12`, `python3` ou `python`, com os módulos `venv` e `ensurepip`. O script executa a mesma preparação automática do ambiente, dependências, modelos e banco. Use uma `.venv` própria do Linux; um ambiente criado no Windows não é compatível.

## Configuração do banco e do administrador

O `.env` é disponibilizado separadamente pela equipe e deve ficar em `backend/.env`; ele é ignorado pelo Git. Use somente esse arquivo; não é necessário manter um `.env` na raiz do projeto. Preserve a configuração fornecida e ajuste os dados de conexão quando o MySQL estiver em outra máquina ou usar credenciais diferentes:

| Variável | Finalidade |
| --- | --- |
| `DB_HOST`, `DB_PORT` | Endereço e porta do MySQL; padrões `127.0.0.1` e `3306`. |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD` | Banco e credenciais de conexão. |
| `ADMIN_CPF` | CPF válido do administrador inicial. |
| `ADMIN_PASSWORD_HASH` | Hash Argon2id da senha inicial. |
| `BIOMETRIC_KEY` | Chave original de 32 bytes em base64 para os dados cifrados. |
| `ALLOWED_ORIGINS` | Origens web autorizadas; os padrões incluem `http://localhost:4200`. |

O `.env` fornecido deve conter `ADMIN_CPF` e `ADMIN_PASSWORD_HASH` válidos para a criação do administrador no primeiro acesso ao banco. Se precisar gerar outro hash de senha, com a `.venv` e as dependências Python já instaladas, execute na raiz e cole o resultado em `ADMIN_PASSWORD_HASH`:

```powershell
.\.venv\Scripts\python.exe -c "from getpass import getpass; from argon2 import PasswordHasher; print(PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2).hash(getpass('Senha inicial do administrador: ')))"
```

**Não é necessário criar um perfil “Database Connection” na interface do MySQL para executar o projeto.** Esse perfil salva os dados de acesso em um cliente gráfico, como MySQL Workbench ou MySQL Shell for VS Code, para consultar e administrar o servidor. O backend abre sua própria conexão usando `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER` e `DB_PASSWORD` de `backend/.env`. Os scripts não criam perfis de conexão nos clientes gráficos, e esses clientes são opcionais para executar a aplicação.

O **MySQL Server** precisa estar instalado e ativo antes da execução; os inicializadores não instalam o servidor nem criam o usuário de conexão. Na máquina de avaliação, o usuário indicado no `.env` precisa existir no servidor, aceitar a senha configurada e ter as permissões necessárias. Se precisar preparar o banco e o usuário, execute `backend/sql/criar_banco.sql` como administrador em um cliente MySQL, ajustando o nome do banco, o usuário e a senha para corresponder ao `.env`. Esse SQL é uma etapa manual e não é executado automaticamente pelos inicializadores. Se usar um cliente gráfico para executar esse SQL, abra ou crie nele uma conexão administrativa com o servidor; o nome dado a esse perfil é livre e não é usado pela aplicação.

Com o servidor e o usuário preparados, execute `iniciar.bat` ou `iniciar.sh` na raiz. O inicializador cria o banco quando necessário e permitido, prepara as tabelas e insere o administrador inicial e os dossiês demonstrativos. Um administrador existente mantém sua senha. Alterações conhecidas de estrutura preservam os cadastros existentes.

Uma cópia de um banco existente exige a **mesma chave biométrica**. Quando não houver `BIOMETRIC_KEY` no ambiente ou no `.env`, a chave fica em `backend/.runtime/biometric.key`; preserve esse arquivo ao transferir o banco. Assinaturas de algoritmos anteriores exigem recadastro biométrico.

## Organização do código

`backend/app/main.py` concentra a API, configuração, validação das entradas, persistência, criptografia, preparação dos modelos e coordenação da captura. `backend/app/inicializar.py` é o comando de preparação do banco.

As cinco fases ficam reunidas na pasta `backend/app/processamento/`:

| Fase | Arquivo | Operação |
| --- | --- | --- |
| 1. Aquisição | `sensoriamento.py` | Valida dimensões e decodifica os bytes RGB. |
| 2. Pré-processamento | `pre_processamento.py` | Calcula luminância suavizada para avaliar qualidade e fornece a normalização de iluminação do rosto alinhado. |
| 3. Segmentação | `segmentacao.py` | Detecta um rosto, confere qualidade e alinha cinco pontos faciais em 112 × 112 pixels. |
| 4. Extração de características | `extracao_caracteristicas.py` | Normaliza a iluminação do rosto alinhado antes de produzir e normalizar o vetor AuraFace de 512 dimensões. |
| 5. Classificação/interpretação | `classificacao_interpretacao.py` | Compara assinaturas por distância de cosseno e aplica os limites de aceitação. |

O cadastro recebe cinco quadros: **frente → um lado → lado oposto → frente → frente**. O primeiro lado é livre, sem depender do espelhamento da câmera. Os giros leves servem como barreira contra uma foto estática; a assinatura facial e sua consistência usam somente os três quadros frontais, evitando rejeitar uma pessoa por diferenças entre as poses laterais. O login recebe três quadros de frente. O servidor verifica rosto único, qualidade, movimento no cadastro e imagens repetidas.

Cadastro e login usam a mesma normalização fotométrica: após o alinhamento em 112 × 112 pixels, o rosto passa por correção gamma adaptativa limitada e CLAHE no canal de luminância Y do espaço YCrCb, antes da extração AuraFace. O objetivo é reduzir o efeito de variações moderadas de iluminação. A detecção e as métricas de qualidade continuam usando a captura original; os limites de iluminação, contraste, saturação e foco são preservados. Áreas completamente escuras ou estouradas podem ter perdido detalhes e continuam exigindo nova captura. A normalização não exige reproduzir a iluminação do cadastro.

Os dados do novo cadastro ficam somente na memória do frontend durante a captura. Nome, CPF, senha, nível e os cinco quadros são enviados juntos em `POST /api/usuarios`, e o usuário só é salvo após a validação facial. Sair antes do envio descarta os dados. Cadastros antigos sem biometria ficam fora da lista administrativa e podem ser concluídos refazendo o cadastro com o mesmo CPF; um cadastro completo com esse CPF continua sendo recusado.

Durante a captura, a orientação da etapa atual aparece acima do círculo de enquadramento. Após concluir o cadastro, a aplicação retorna ao gerenciamento de usuários e exibe a confirmação de sucesso.

Os modelos em `backend/.runtime/modelos` são preservados com tamanho e SHA-256 verificados:

| Modelo | Arquivo | Tamanho |
| --- | --- | --- |
| YuNet | `face_detection_yunet_2023mar.onnx` | 232.589 bytes |
| AuraFace | `glintr100.onnx` | 260.694.151 bytes |

Os pesos não foram convertidos ou reduzidos. Os limites de comparação permanecem em `0.30`, margem `0.03`, consistência `0.25` e foco mínimo `1.5`. A assinatura mantém versão 3 e algoritmo `auraface-v1-arcface-r100-yunet-112-v3`.

A atualização de iluminação não exige recadastro nem altera assinaturas armazenadas. As novas capturas recebem o tratamento antes de gerar o vetor no mesmo modelo e espaço de características; a comparação continua usando as biometrias existentes. O banco e os demais dados do usuário são preservados.

Durante a preparação, o terminal informa o tamanho de cada modelo. Se precisar baixá-lo, mostra os MB recebidos, o total e o percentual de progresso, com aviso de que o download pode demorar. Arquivos já instalados e íntegros são reutilizados; a instalação só é confirmada após a verificação de integridade.

## Endpoints preservados

| Método | Rota | Uso |
| --- | --- | --- |
| `GET` | `/api/saude` | Saúde do banco. |
| `POST` | `/api/usuarios` | Cadastro administrativo com cinco quadros obrigatórios. |
| `GET` | `/api/usuarios` | Lista administrativa. |
| `PATCH` | `/api/usuarios/{id}` | Edição administrativa. |
| `PUT` | `/api/usuarios/{id}/biometria` | Recadastro biométrico administrativo. |
| `DELETE` | `/api/usuarios/{id}` | Exclusão administrativa. |
| `POST` | `/api/autenticacao/credenciais` | Confirma CPF e senha. |
| `POST` | `/api/autenticacao/verificar` | Verificação facial vinculada ao desafio. |
| `GET` | `/api/sessao` | Consulta da sessão. |
| `POST` | `/api/sair` | Revoga sessão e desafio. |

As chamadas preservam os cookies `HttpOnly`. O desafio biométrico dura 120 segundos; a sessão dura 15 minutos por padrão. O administrador de nível 4 entra com CPF e senha e gerencia usuários de níveis 1 a 3. Os formatos das requisições e respostas permanecem no Swagger.

A confirmação de credenciais retorna o nome do usuário para a saudação. Para funcionários, isso identifica apenas o desafio pendente: a sessão de acesso só é concedida após a verificação facial.

Os quadros são processados em memória. CPF e assinatura são cifrados com AES-GCM; senhas usam Argon2id e tokens são armazenados como hashes. A comparação facial e a sequência de movimento não constituem prova de vida.

## Gerar o arquivo de entrega

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\empacotar_projeto.ps1
```

O resultado fica em `.runtime/entrega/APS-Leitura-Facial.zip`. O script inclui código, documentação, `.venv` e modelos; exclui caches, `node_modules`, builds, logs e arquivos privados. Confere a integridade dos modelos e recusa um ZIP acima de **500.000.000 bytes**. O projeto local mantém seus arquivos de configuração e as chaves.
