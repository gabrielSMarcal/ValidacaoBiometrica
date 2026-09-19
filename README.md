# APS — API de autenticação facial

Protótipo acadêmico em **Python 3.12 + FastAPI + MySQL**, com três páginas mínimas para testar cadastro, autenticação por CPF/senha e rosto, e consulta do nível de acesso. As cinco fases ficam em [`app/biometria.py`](app/biometria.py). Não há detector, rede neural ou pesos pré-treinados: o código implementa processamento clássico, descritor e comparação. A pessoa deve posicionar o rosto na elipse da câmera; o sistema **não localiza automaticamente rostos nem comprova presença de uma pessoa viva**.

## Começar no Windows

Nesta pasta já foi criado `.venv` com **Python 3.12.14**, usando o interpretador local disponível. Não precisa ativar o ambiente para executar os comandos abaixo. Em outra máquina, instale Python 3.12 e crie novamente com `py -3.12 -m venv .venv`: ambientes virtuais não são portáveis.

**Estado desta instalação:** o `.env` ajustado por você foi preservado. A migração para IDs inteiros já foi aplicada no MySQL 8.4.11, mantendo o cadastro existente com ID 1 e seus dados criptografados. Os passos de criação e migração abaixo são para outras instalações; nesta máquina basta iniciar a API.

1. Instale os requisitos:

   ```powershell
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

2. Crie a configuração local:

   ```powershell
   .\.venv\Scripts\python.exe scripts\configurar.py
   ```

   O script gera `BIOMETRIC_KEY` em `.env`, sem sobrescrever um arquivo existente. Nesta entrega ele já foi executado. Guarde essa chave; sua perda impede a leitura dos CPFs e assinaturas existentes. Não comite `.env`, banco, backups ou capturas.

3. Inicie **MySQL** no XAMPP, abra `http://localhost/phpmyadmin` e execute [`sql/criar_banco.sql`](sql/criar_banco.sql), após trocar a senha de exemplo. Configure a mesma senha em `DB_PASSWORD` no `.env`. Para MySQL instalado separadamente, execute o SQL como administrador nesse servidor e ajuste host/porta. A aplicação usa um usuário próprio, `aps_app`.

4. Crie as tabelas e inicie a API:

   ```powershell
   .\.venv\Scripts\python.exe -m app.inicializar
   .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
   ```

   Deixe o terminal aberto. Use **um worker** nesta demonstração. `Ctrl+C` encerra a API. O processo usa Uvicorn como servidor ASGI; o Apache pode encaminhar as requisições a ele. [Execução oficial do FastAPI](https://fastapi.tiangolo.com/deployment/manually/).

5. Abra:

   - Cadastro: <http://127.0.0.1:8000/cadastro>
   - Validação: <http://127.0.0.1:8000/validacao>
   - Documentação interativa: <http://127.0.0.1:8000/docs>
   - Estado da API/banco: <http://127.0.0.1:8000/api/saude>

## Testar com a câmera

O cadastro é público no ambiente local e não exige autenticação prévia. Informe nome, CPF com dígitos verificadores válidos, senha de 8 a 128 caracteres e selecione o nível 1/2/3 para o teste. Os níveis são apenas grupos registrados, sem permissões implementadas. A atribuição de permissões reais dependerá de administração em uma etapa futura.

Clique em **Abrir câmera**, autorize o navegador, use luz frontal e mantenha o rosto na elipse. Ao acionar o botão de cadastro, aguarde a contagem de **3 segundos**: em seguida o navegador captura três quadros RGB, e a API calcula a assinatura agregada e grava usuário e log na mesma transação. Nenhuma foto é gravada. O resumo das cinco fases aparece após o cadastro.

Na validação, informe primeiro **CPF e senha**. Somente após a API aceitar as credenciais a página libera a etapa da câmera. Abra a câmera, enquadre o rosto e acione a verificação; a captura começa após a contagem de **3 segundos**. A comparação usa apenas a assinatura do usuário identificado pelas credenciais (1:1). O fluxo não oferece login somente com o rosto.

Credenciais aceitas geram um desafio de uso único, válido por **120 segundos**, no cookie `HttpOnly` `aps_desafio`. Esse desafio apenas libera a tentativa biométrica; ele não permite consultar o nível. Depois da face aceita, a API cria a sessão completa e a página mostra **“Você é do nível x”**. O nível vem do banco, e a sessão dura 15 minutos; o botão Sair a revoga. Se o desafio expirar ou a tentativa biométrica falhar, valide CPF e senha novamente antes de outra tentativa.

A prévia da câmera é espelhada somente na apresentação por CSS. Os bytes enviados continuam na orientação original, mantendo a compatibilidade com as assinaturas já cadastradas. Uma captura fora do limiar, escura, pouco nítida ou inconsistente pode ser recusada. A contagem e o espelhamento não demonstram melhora da precisão biométrica.

**Os limiares são experimentais.** Aprovação de testes de software não mede reconhecimento de pessoas. Antes de apresentar resultados de acurácia, siga o protocolo com pessoas e capturas independentes em [`docs/PROCESSAMENTO_IMAGENS.md`](docs/PROCESSAMENTO_IMAGENS.md). Fotos/telas podem passar: não há detecção de apresentação, prova de vida ou garantia de origem física dos bytes enviados à API. Este protótipo não protege um cofre real.

## Organização

| Local | Responsabilidade |
| --- | --- |
| `app/biometria.py` | Sensores, pré-processamento, segmentação, extração e classificação/interpretação |
| `app/main.py` | Rotas, transações, sessões, proteções HTTP e páginas |
| `app/banco.py` | Conexão SQLAlchemy, usuários, logs, sessões e desafios biométricos |
| `app/seguranca.py` | AES-GCM, índice HMAC do CPF, hash Argon2 e hash dos tokens de sessão |
| `app/esquemas.py` | Validação de CPF, dados de cadastro e quadros RGB |
| `app/config.py` | Configuração pelo `.env` |
| `web/` | Telas locais de teste e captura com `getUserMedia` |
| `tests/` | Testes de processamento, segurança e integração da API |

O banco é obrigatório na execução normal: não existe troca silenciosa por SQLite. O script de inicialização cria tabelas ausentes, mas uma base da versão anterior precisa da migração explícita abaixo.

## IDs e migração do banco existente

`usuarios.id` é um inteiro com incremento automático. Cada usuário também mantém `biometria_ref`, um UUID imutável utilizado na autenticação dos dados criptografados. Na migração, o UUID que antes era a chave primária passa a ser essa referência: os BLOBs são preservados sem precisar recadastrar a biometria.

Com a API parada, consulte primeiro o plano:

```powershell
.\.venv\Scripts\python.exe -m scripts.migrar_banco
```

O comando sem argumentos apenas inspeciona a estrutura. Para aplicar a migração planejada:

```powershell
.\.venv\Scripts\python.exe -m scripts.migrar_banco --aplicar
```

O processo conserva as tabelas antigas com prefixo `aps_backup_` e cria um arquivo criptografado `.aesgcm` em `.runtime/backups/`. Preserve esses backups e a mesma `BIOMETRIC_KEY`. Esta migração de bases antigas é validada para MySQL 8+; bases novas também podem ser criadas no MariaDB do XAMPP. O script precisa de privilégios para leitura, criação, cópia, bloqueio e renomeação das tabelas; detalhes estão no [guia do XAMPP](docs/GUIA_XAMPP.md). Reinicie a API depois de concluir a migração.

Para excluir um cadastro pelo cliente SQL local, consulte seu ID e execute uma exclusão específica, por exemplo:

```sql
SELECT id, nome, nivel FROM usuarios ORDER BY id;
DELETE FROM usuarios WHERE id = 123;
```

Substitua `123` pelo ID desejado. Os logs são preservados com `usuario_id = NULL`; sessões e desafios vinculados são removidos por cascata. Não há endpoint público de exclusão.

## Contrato da API

| Método/rota | Entrada | Resultado |
| --- | --- | --- |
| `GET /api/saude` | — | Estado do banco |
| `POST /api/usuarios` | Nome, CPF, senha, nível e frames | Cadastro e resumo do processamento |
| `POST /api/autenticacao/credenciais` | CPF e senha | Desafio de 120 segundos no cookie `aps_desafio` |
| `POST /api/autenticacao/verificar` | Frames e cookie `aps_desafio` | Verificação facial 1:1, resumo e cookie `aps_sessao` |
| `GET /api/sessao` | Cookie `aps_sessao` | Nome e nível atuais do usuário |
| `POST /api/sair` | Cookie | Revogação da sessão |

Valide primeiro as credenciais com um corpo JSON contendo `cpf` e `senha`. Preserve os cookies entre as duas requisições. O desafio não é enviado no JSON nem exibido ao JavaScript. A rota `/api/autenticacao/identificar` foi removida.

Corpo da segunda etapa (`POST /api/autenticacao/verificar`, `application/json`):

```json
{
  "frames": [
    {"largura": 320, "altura": 240, "rgb_base64": "BYTES_RGB_EM_BASE64"},
    {"largura": 320, "altura": 240, "rgb_base64": "BYTES_RGB_EM_BASE64"},
    {"largura": 320, "altura": 240, "rgb_base64": "BYTES_RGB_EM_BASE64"}
  ]
}
```

O texto acima é ilustrativo; a página captura os bytes reais. Cada pixel deve ter exatamente três bytes R,G,B, sem cabeçalho de arquivo nem canal alfa. A API admite 3 a 5 quadros de dimensões iguais, entre 160×120 e 640×480, e no máximo 8 MiB por requisição. Nenhuma rota aceita PNG/JPEG ou upload de arquivos.

Erros principais: `401` credenciais, desafio, face ou sessão recusados; `403` origem recusada; `409` CPF repetido; `413` corpo grande; `415` formato HTTP incorreto; `422` campos/captura inválidos; `429` limite de tentativas; `503` banco ou assinatura indisponível. Respostas não devolvem senhas, CPF, vetores biométricos nem pixels.

## Dados e segurança

A assinatura JSON é codificada em UTF-8, compactada com zlib, cifrada com **AES-256-GCM** e armazenada em **MEDIUMBLOB**. O envelope contém versão, nonce aleatório e ciphertext autenticado; `biometria_ref` e o tipo do dado são autenticados também, impedindo trocar blobs entre usuários. O ID inteiro é independente dessa referência criptográfica. JSON→bytes/BLOB não garante maior velocidade por si só: o ganho de compactação e custo de criptografia precisam ser medidos. [AES-GCM e dados associados](https://cryptography.io/en/latest/hazmat/primitives/aead/).

O CPF também é cifrado; a busca/unicidade usa HMAC, sem guardar CPF em texto claro. Nome e nível permanecem campos normais. A senha recebe Argon2id, que é verificado sem precisar reverter o hash. Sessões e desafios guardam somente hash de token aleatório no banco, com expiração, e o navegador recebe cookies `HttpOnly`, `SameSite=Strict`. O desafio é consumido pela tentativa de verificação. Em HTTPS ajuste `COOKIE_SECURE=true`. Não há armazenamento de token em `localStorage`.

Logs de cadastro e decisões de autenticação registram evento, resultado, motivo, ID do usuário quando pertinente, ID da requisição e horário UTC; não guardam CPF, senha, token, imagem ou assinatura. Campos inválidos rejeitados pelo parser HTTP/Pydantic não geram log de decisão biométrica. Se a gravação obrigatória do log falhar, o cadastro/autenticação não é confirmado. Não há endpoint público de listagem de usuários ou logs; consulte localmente no banco.

O limite de 20 POSTs/minuto é por IP e processo, reinicia com a API e pode agrupar clientes atrás de proxy. A verificação recupera somente a assinatura vinculada ao desafio; não percorre uma galeria de rostos. Origem permitida não substitui autenticação: ferramentas HTTP sem navegador ainda podem chamar as rotas públicas. TLS, gestão/rotação de chaves, políticas de retenção, administração de permissões e prova de vida ficam para a evolução do sistema.

## Testes e Apache

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
```

Os testes rápidos usam matrizes RGB sintéticas e banco SQLite isolado para verificar algoritmos/contratos/transações. Isso não equivale a calibrar biometria ou a testar uma instalação real do XAMPP.

Na revisão atual, **76 testes passaram** e um teste adicional de migração MySQL ficou desabilitado por padrão. Esse teste adicional também foi executado separadamente e passou: conferiu a migração, sua repetição sem alterações e a exclusão com preservação dos logs, em tabelas isoladas. Os testes não medem acurácia facial; a câmera real e o proxy Apache precisam de verificação no ambiente de uso.

Para repetir a integração com o banco configurado, após instalar `requirements-dev.txt`:

```powershell
.\.venv\Scripts\python.exe -m scripts.verificar_mysql
```

Esse comando cria um usuário sintético temporário e seus registros relacionados e remove apenas os dados dessa execução. Não altera `.env` nem apaga usuários existentes. As verificações usam o cadastro de teste específico.

- [`docs/GUIA_XAMPP.md`](docs/GUIA_XAMPP.md): documento separado com MySQL/MariaDB, Apache como proxy e solução de erros.
- [`docs/PROCESSAMENTO_IMAGENS.md`](docs/PROCESSAMENTO_IMAGENS.md): explicação das funções e protocolo de avaliação.

A documentação original foi usada para definir as três categorias e as cinco fases. Dissertação, relatórios acadêmicos finais e regras de entrega da faculdade não foram tratados como solicitação de gerar uma monografia.
