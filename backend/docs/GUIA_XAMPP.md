# Guia local: XAMPP, banco de dados e FastAPI

Este guia permite testar o projeto no Windows com uma câmera, primeiro diretamente pela API e depois pelo Apache do XAMPP. Os comandos são para o PowerShell, executados na pasta do projeto. Nenhuma alteração no Apache é aplicada automaticamente pelos arquivos do projeto.

## 1. Entenda o papel de cada componente

| Componente | Responsabilidade neste projeto |
| --- | --- |
| Navegador | Exibir cadastro e validação; conferir CPF/senha antes da etapa biométrica; solicitar a câmera e enviar quadros RGB à API. |
| Apache do XAMPP | Receber a navegação na porta 8080 e encaminhar as requisições ao Uvicorn. |
| Uvicorn + FastAPI | Executar Python, processar a biometria, cadastrar, validar e registrar eventos. |
| SQLAlchemy + PyMySQL | Conectar o código Python ao banco. |
| MySQL ou MariaDB | Armazenar usuários, assinaturas criptografadas e logs. |

FastAPI precisa de um servidor ASGI, como Uvicorn. Colocar arquivos `.py` em `htdocs` não executa esta aplicação. Nesta configuração o Uvicorn continua em execução em um terminal, mesmo quando o acesso é feito pelo Apache. [FastAPI: execução manual e servidores ASGI](https://fastapi.tiangolo.com/deployment/manually/).

O XAMPP distribui **MariaDB**, embora seu painel mantenha o rótulo “MySQL”. O projeto usa o protocolo MySQL pelo PyMySQL e pode utilizar esse banco local. [XAMPP: perguntas frequentes para Windows](https://www.apachefriends.org/faq_windows.html).

Fluxo final:

```text
Câmera → navegador → http://localhost:8080
                         Apache
                            ↓
                    http://127.0.0.1:8000
                     Uvicorn / FastAPI
                            ↓
                     MySQL / MariaDB
```

## 2. Prepare Python e o banco

1. Se for usar o banco fornecido pelo XAMPP, abra o **XAMPP Control Panel** e inicie **MySQL**. Para usar o phpMyAdmin, inicie também **Apache**. Se você já possui MySQL instalado e configurado no `.env`, como na instalação atual deste projeto, mantenha esse servidor e use somente o Apache do XAMPP: não inicie um segundo banco na mesma porta nem repita a criação de um banco que já está pronto.
2. Abra um PowerShell na pasta `APS Leitura Facial`.
3. Ative o ambiente Python 3.12 já existente na pasta `.venv` do projeto:

   ```powershell
   .\.venv\Scripts\Activate.ps1
   python --version
   python -m pip install -r requirements.txt
   python scripts/configurar.py
   ```

   Em uma nova cópia do projeto que ainda não tenha ambiente, crie-o antes com `py -3.12 -m venv .venv`. Não é necessário recriar o ambiente que já existe. Se a política do PowerShell impedir a ativação, utilize diretamente o executável do ambiente, por exemplo `& .\.venv\Scripts\python.exe -m pip install -r requirements.txt`, e faça o mesmo com os demais comandos Python. Não é necessário mudar a política do Windows. O configurador preserva um `.env` existente; mantenha os dados de conexão e as chaves que você já ajustou.

4. Abra `sql/criar_banco.sql`, ajuste a senha de exemplo conforme as instruções no arquivo e execute seu conteúdo no cliente de banco ou na aba **SQL** do phpMyAdmin. Use a conta administrativa apenas para preparar banco e usuário da aplicação.
5. Edite o `.env` criado pelo configurador e preencha os dados da conexão de acordo com o banco e o usuário preparados no passo anterior. Confira também a porta do MySQL no painel do XAMPP: normalmente é `3306`, mas outra instalação pode usar uma porta diferente.

   ```dotenv
   DB_HOST=127.0.0.1
   DB_PORT=3306
   DB_NAME=aps_facial
   DB_USER=aps_app
   DB_PASSWORD=sua_senha_definida_no_sql
   ```

   O texto `troque_a_senha_no_sql_e_no_env` é um marcador no SQL, não uma senha para manter. Substitua-o pelo mesmo valor usado em `DB_PASSWORD`.
6. Preserve `BIOMETRIC_KEY`, gerada no `.env` para proteger os dados cifrados. Guarde a chave com os backups do banco em local protegido: perder ou substituir `BIOMETRIC_KEY` impede descriptografar assinaturas e CPFs existentes. `scripts/configurar.py` não sobrescreve um `.env` que já existe.
7. Crie as tabelas com:

   ```powershell
   python -m app.inicializar
   ```

O SQL inicial cria banco e acesso; o comando Python cria a estrutura de tabelas da aplicação. A conta utilizada pela API deve corresponder à configurada no SQL. Não coloque o projeto inteiro, o `.env`, o ambiente virtual ou backups do banco em `C:\xampp\htdocs`.

### Banco de uma versão anterior: migrar os IDs

Na versão atual, `usuarios.id` é inteiro com incremento automático, e o UUID usado pela criptografia fica em `biometria_ref`. Uma base antiga com ID UUID precisa de migração. `app.inicializar` não faz essa conversão.

Pare a API e execute primeiro o plano de leitura:

```powershell
python -m scripts.migrar_banco
```

Depois de conferir o plano, aplique:

```powershell
python -m scripts.migrar_banco --aplicar
```

A migração preserva os BLOBs e move o UUID anterior para `biometria_ref`. Cria um backup criptografado do esquema e dos dados em `.runtime/backups/`, com extensão `.aesgcm`, e conserva as tabelas originais com prefixo `aps_backup_`. Preserve esses arquivos, as tabelas de backup e a mesma `BIOMETRIC_KEY`; a aplicação usa as tabelas novas depois da troca. O script de conversão de bases antigas foi validado para MySQL 8+ e recusa MariaDB; uma instalação nova no MariaDB usa `app.inicializar` diretamente.

A conta de migração precisa de privilégios `SELECT`, `INSERT`, `CREATE`, `ALTER`, `DROP`, `REFERENCES` e `LOCK TABLES`. O privilégio `DROP` é exigido pelo MySQL para a renomeação; a migração conserva as tabelas antigas. Antes da troca, o script bloqueia as tabelas e confere que os dados não mudaram desde a cópia; se mudaram, interrompe a migração preservando os originais. Mantenha a API parada até o comando terminar e então reinicie o Uvicorn. Em uma instalação nova, `app.inicializar` já cria o formato atual.

Os IDs inteiros permitem excluir um cadastro específico no cliente SQL local, por exemplo `DELETE FROM usuarios WHERE id = 123;`, substituindo `123` pelo ID conferido em `SELECT id, nome, nivel FROM usuarios ORDER BY id;`. Os logs permanecem com vínculo de usuário nulo (`ON DELETE SET NULL`); sessões e desafios são removidos por cascata. Não existe rota pública de exclusão.

## 3. Teste a API antes de configurar o Apache

Com o ambiente Python ativo e o banco em execução:

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Mantenha o terminal aberto. Acesse:

| Página | Endereço |
| --- | --- |
| Cadastro | <http://localhost:8000/cadastro> |
| Validação | <http://localhost:8000/validacao> |
| Documentação interativa | <http://localhost:8000/docs> |

O cadastro é público no ambiente local e não exige autenticação prévia. Preencha os campos, selecione um dos três níveis para teste e capture a câmera após a contagem de três segundos. Na validação, informe primeiro CPF e senha; quando forem aceitos, a página libera a câmera para a verificação facial 1:1. Após a face aceita, a página `/nivel` apresenta “Você é do nível x”. Os níveis são grupos registrados, sem permissões de negócio implementadas nesta versão; a atribuição de permissões reais dependerá de administração em uma etapa futura.

O fluxo usa duas requisições: `/api/autenticacao/credenciais` recebe CPF e senha e emite o cookie `HttpOnly` `aps_desafio`, de uso único e validade de 120 segundos. `/api/autenticacao/verificar` recebe apenas os quadros e esse cookie, compara com a assinatura do usuário e cria a sessão completa se aceitar a face. O desafio sozinho não autoriza consultar o nível. Não há login somente por rosto.

Se o acesso direto não funcionar, resolva o erro antes de acrescentar o Apache. O guia [Processamento de imagens](PROCESSAMENTO_IMAGENS.md) explica o enquadramento e as limitações da comparação biométrica.

## 4. Configure o Apache como proxy reverso

O exemplo considera XAMPP em `C:\xampp`. Se sua instalação estiver em outro local, ajuste os caminhos. Salve uma cópia dos arquivos de configuração antes de editá-los.

### 4.1. Habilite os módulos necessários

No painel XAMPP, use **Apache → Config → Apache (httpd.conf)**. Localize estas linhas e remova o `#` inicial, caso exista:

```apache
LoadModule proxy_module modules/mod_proxy.so
LoadModule proxy_http_module modules/mod_proxy_http.so
```

Não adicione outra cópia de uma linha que já esteja ativa. Confirme também que este `Include` está habilitado:

```apache
Include conf/extra/httpd-vhosts.conf
```

`mod_proxy` realiza o encaminhamento; `mod_proxy_http` atende o destino HTTP. `ProxyRequests Off` mantém desativado o proxy aberto de navegação. [Apache: mod_proxy](https://httpd.apache.org/docs/2.4/mod/mod_proxy.html).

### 4.2. Reserve a porta 8080 para o projeto

No mesmo `httpd.conf`, adicione **uma única vez**, fora de qualquer bloco `VirtualHost`:

```apache
Listen 127.0.0.1:8080
```

Essa linha limita a nova porta ao próprio computador. Não duplique uma diretiva existente que já escute em `8080`; nesse caso, adapte a existente. As portas originais do Apache podem continuar configuradas para os outros serviços do XAMPP. [Apache: diretiva Listen](https://httpd.apache.org/docs/2.4/mod/mpm_common.html#listen).

### 4.3. Adicione o host do projeto

Em `C:\xampp\apache\conf\extra\httpd-vhosts.conf`, acrescente:

```apache
<VirtualHost 127.0.0.1:8080>
    ServerName localhost

    ProxyRequests Off
    ProxyPreserveHost On
    ProxyPass "/" "http://127.0.0.1:8000/"
    ProxyPassReverse "/" "http://127.0.0.1:8000/"

    LimitRequestBody 8388608

    ErrorLog "logs/aps-error.log"
    CustomLog "logs/aps-access.log" combined
</VirtualHost>
```

`ProxyPass` encaminha todas as rotas, incluindo `/cadastro`, `/validacao`, `/nivel`, `/api`, `/static` e `/docs`. `ProxyPassReverse` ajusta cabeçalhos de redirecionamento devolvidos pelo destino. As barras finais dos dois lados devem ser mantidas. Não é preciso copiar as páginas para `htdocs`: a API já as serve. [Apache: guia de proxy reverso](https://httpd.apache.org/docs/2.4/howto/reverse_proxy.html).

O limite de corpo acima é de 8 MiB, suficiente para o lote de quadros deste protótipo. `LimitRequestBody` recebe um valor em bytes e rejeita requisições maiores. [Apache: LimitRequestBody](https://httpd.apache.org/docs/2.4/mod/core.html#limitrequestbody).

### 4.4. Configure a origem no projeto

No `.env`, inclua a origem pela qual o navegador fará o acesso. Preserve as origens locais que você já usa, seguindo o formato de `.env.example`:

```dotenv
ALLOWED_ORIGINS=http://localhost:8000,http://127.0.0.1:8000,http://localhost:8080,http://127.0.0.1:8080
```

Uma origem inclui protocolo, host e porta; não inclui `/cadastro`. Reinicie o Uvicorn após alterar o `.env`. Use sempre a mesma origem durante cadastro e validação para manter o contexto de sessão do navegador. Não substitua a lista por `*`.

### 4.5. Valide a configuração e reinicie

No PowerShell:

```powershell
& 'C:\xampp\apache\bin\httpd.exe' -t
```

Prossiga quando o resultado for `Syntax OK`. No painel XAMPP, pare e inicie o Apache. Mantenha MySQL e o processo Uvicorn em execução. Agora abra:

- Cadastro: <http://localhost:8080/cadastro>
- Validação: <http://localhost:8080/validacao>
- Documentação da API: <http://localhost:8080/docs>

O phpMyAdmin permanece no endereço original do XAMPP, como <http://localhost/phpmyadmin>. O endereço `localhost:8080/phpmyadmin` será encaminhado à API e não é o caminho do painel do banco.

## 5. Câmera e sequência de teste

O navegador deve receber permissão para a câmera. `getUserMedia()` exige um contexto seguro; `localhost` permite o teste local por HTTP. Acesso a partir de outro computador por um IP comum via HTTP não recebe essa exceção e requer configuração HTTPS. [MDN: getUserMedia e requisitos de segurança](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia).

1. Use `http://localhost:8080/cadastro`, conceda acesso à câmera e aguarde a imagem estabilizar.
2. Posicione uma única pessoa de frente, com o rosto dentro da elipse. Mantenha iluminação frontal, câmera na altura dos olhos e fundo simples.
3. Preencha nome, CPF e senha; selecione o nível 1, 2 ou 3 para testar o grupo registrado.
4. Acione o cadastro e aguarde a contagem de três segundos antes da captura do lote. Quadros da câmera são enviados em memória; não há seleção de PNG ou JPEG.
5. Abra a validação e envie CPF e senha. A câmera fica disponível após as credenciais aceitas.
6. Mantenha distância e enquadramento semelhantes, abra a câmera e acione a verificação. Aguarde a contagem de três segundos sem sair da guia.
7. Confira o nível apresentado. Se o desafio expirar ou a tentativa falhar, valide novamente CPF e senha antes de repetir a captura.
8. Encerre a câmera ao concluir. Pare o Uvicorn com `Ctrl+C`; depois pare Apache e MySQL no painel se não estiverem atendendo outro trabalho.

A prévia é espelhada por CSS para facilitar o posicionamento. O canvas continua enviando os pixels originais, na mesma orientação usada pelos cadastros anteriores. O timer e o espelhamento alteram a interação da tela; não calibram o algoritmo biométrico.

Várias capturas não comprovam prova de vida. Este experimento depende do enquadramento manual e de um limiar ainda não calibrado; uma execução sem erro da API não demonstra precisão biométrica.

## 6. Problemas comuns

| Sintoma | Verificação |
| --- | --- |
| Apache não inicia | Execute `httpd.exe -t`; examine `C:\xampp\apache\logs\error.log`; procure porta ocupada ou diretiva `Listen` duplicada. |
| Porta 80 já está ocupada | A porta 8080 do projeto pode estar livre, mas o Apache ainda tenta abrir as demais portas configuradas. Resolva o conflito da configuração original ou ajuste a porta original conscientemente. |
| `502` ou `503` ao abrir pelo Apache | Confirme o terminal do Uvicorn e teste primeiro `http://localhost:8000/cadastro`. |
| Página XAMPP em vez do cadastro | Use a porta `8080`, confirme o `Include` de hosts e reinicie o Apache. |
| Falha de conexão ao banco | Confirme MySQL ativo, host, porta, usuário e senha do `.env`; execute a inicialização após criar o banco. |
| Banco ou tabela inexistente | Execute `sql/criar_banco.sql` e depois `python -m app.inicializar`, na ordem indicada. |
| Banco antigo com IDs UUID | Pare a API e consulte `python -m scripts.migrar_banco`; aplique a migração antes de usar a versão com IDs inteiros. |
| Câmera bloqueada | Confira a permissão do site e do Windows, feche outro programa que esteja usando a câmera e use `localhost`. |
| Câmera ainda não liberada na validação | Envie CPF e senha primeiro; a etapa biométrica é liberada após a confirmação da API. |
| Desafio ausente, expirado ou já utilizado | Valide CPF e senha novamente. O desafio vale 120 segundos e serve para uma única tentativa biométrica. |
| Requisição rejeitada por origem | Compare a origem exibida na barra do navegador com `ALLOWED_ORIGINS`; reinicie a API após a alteração. |
| `413` | A requisição excedeu um limite de tamanho. Use a captura da página, que envia quadros de 320×240, e confira se o Apache foi reiniciado com o limite proposto. |
| Cadastro não descriptografa depois de reinstalar | Restaure a mesma chave usada para criptografar. A senha do usuário e a senha do banco não substituem essa chave. |
| Pessoa cadastrada não é reconhecida | Repita o enquadramento e a iluminação; consulte a qualidade do processamento. Não aumente o limiar sem medir falsos aceites. |

## 7. Quando houver um frontend definitivo

A mesma arquitetura aceita novas páginas servidas pela aplicação. Se futuramente você optar por arquivos estáticos diretamente no Apache, poderá separar o atendimento do frontend e manter um proxy apenas para `/api`. Essa mudança exige revisar caminhos, origem e sessão; a configuração de proxy de todas as rotas acima é suficiente para a versão de teste atual.

Este guia descreve execução local. O endereço `127.0.0.1` do Uvicorn e da nova porta Apache foi escolhido para isso. Publicação em rede exige uma implantação própria, com HTTPS, política de cadastro e autorização efetivas, e avaliação biométrica antes de usar o resultado para controlar acesso real.
