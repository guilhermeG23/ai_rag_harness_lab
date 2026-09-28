# Manual de uso do AI RAG Harness

Este manual explica como iniciar e utilizar o ambiente, conversar com a IA, administrar bases RAG, gerenciar usuários e acompanhar a operação técnica.

## 1. Perfis e interfaces

O sistema possui três níveis de utilização:

| Perfil | Interface | Capacidades principais |
|---|---|---|
| Cliente | `/chat` | Conversar, selecionar bases autorizadas, recuperar sessões e alterar o próprio perfil |
| Administrador de grupo | `/chat` e `/lab` | Tudo do cliente, mais usuários, bases RAG, documentos, permissões, jobs e cache do próprio grupo |
| Administrador global | Identity Manager | Criar e administrar grupos e usuários de todos os grupos |

Os relacionamentos e o isolamento usam o UID do grupo. O nome do grupo é apenas descritivo e pode ser alterado sem mudar seu UID.

## 2. Iniciar o ambiente

Na raiz do projeto, execute:

```bash
chmod +x start.sh scripts/*.sh
./start.sh
```

Na primeira inicialização, o script:

1. Cria o arquivo `.env`, caso ainda não exista.
2. Gera os segredos operacionais.
3. Baixa as imagens Docker.
4. Inicia Ollama e baixa os modelos de chat e embeddings.
5. Constrói e inicia todos os containers.
6. Aguarda as interfaces principais responderem.

O primeiro início pode demorar devido ao download dos modelos. Para conferir o estado posteriormente:

```bash
./start.sh status
```

## 3. Endereços

Substitua `HOST` pelo IP ou nome da máquina. No ambiente remoto atual, use `192.168.1.200`.

| Recurso | Endereço atual |
|---|---|
| Chat | `http://192.168.1.200:8080/chat` |
| Laboratório | `http://192.168.1.200:8080/lab` |
| Identity Manager | `http://192.168.1.200:8082` |
| Acessos iniciais | `http://192.168.1.200:8083` |
| Mapa de serviços | `http://192.168.1.200:8081` |
| Grafana | `http://192.168.1.200:3000` |
| RabbitMQ Management | `http://192.168.1.200:15672` |
| OpenAPI/FastAPI | `http://192.168.1.200:8080/api/docs` |

## 4. Credenciais iniciais

### Administração global

- Usuário: `admin`
- Senha: `admin`

### Grupo admin1

| Usuário | Senha | Nível |
|---|---|---|
| `admin1@admin.com` | `admin1` | Administrador do grupo |
| `teste1@teste.com` | `teste1` | Cliente |
| `teste2@teste.com` | `teste2` | Cliente |
| `teste3@teste.com` | `teste3` | Cliente |

### Grupo admin2

| Usuário | Senha | Nível |
|---|---|---|
| `admin2@admin.com` | `admin2` | Administrador do grupo |
| `teste4@teste.com` | `teste4` | Cliente |
| `teste5@teste.com` | `teste5` | Cliente |
| `teste6@teste.com` | `teste6` | Cliente |

Estas credenciais são didáticas. Troque-as antes de disponibilizar o ambiente em uma rede não confiável.

O portal **Acessos iniciais**, na porta `8083`, reúne essas contas e as credenciais iniciais de Grafana, RabbitMQ, PostgreSQL e Valkey, separadas por serviço. Ele não possui autenticação e mostra apenas valores de bootstrap: se uma senha for alterada na aplicação, o portal pode ficar desatualizado.

## 5. Usar o chat

1. Abra `/chat`.
2. Entre com um e-mail e senha de um dos grupos.
3. Clique em **Nova conversa**.
4. Em **Bases consultadas**, marque somente as bases RAG que devem participar da resposta.
5. Digite a pergunta em português e clique em **Enviar**.

A resposta é transmitida gradualmente. Quando houver recuperação RAG, as fontes aparecem abaixo da mensagem com o nome da base, arquivo e score de similaridade.

Se nenhuma base for selecionada, a resposta utiliza o modelo e o histórico da conversa, sem recuperação de documentos. Bases desativadas ou sem permissão não são consultadas, mesmo que seus IDs tenham sido salvos anteriormente na sessão.

### Gerenciar conversas

Na barra lateral estão as conversas **Ativas**, **Arquivadas** e na **Lixeira**.

- **Renomear:** use o botão com lápis.
- **Fixar ou desafixar:** use o losango. Isso muda somente a organização visual.
- **Arquivar:** retira a conversa da lista ativa sem agendar sua exclusão.
- **Excluir:** move a conversa para a lixeira e aplica a retenção configurada para o grupo.
- **Restaurar:** abra a lixeira e use a seta de retorno antes do prazo de expurgo.
- **Excluir definitivamente:** na lixeira, use `×` e confirme a remoção das mensagens.
- **Buscar:** digite parte do título no campo **Buscar conversas**.

### Alterar o próprio perfil

Clique em **Minha conta**, informe o nome desejado e, opcionalmente, uma nova senha. Deixe a senha vazia para manter a atual. A alteração de senha revoga as sessões de autenticação existentes e pode exigir novo login.

## 6. Usar o laboratório

O `/lab` é acessível somente a usuários com nível `admin`. Toda administração feita nessa interface permanece limitada ao UID do grupo autenticado.

### 6.1 Criar uma base RAG

1. Acesse `/lab` com `admin1@admin.com` ou `admin2@admin.com`.
2. Abra a guia **Bases RAG**.
3. Digite o nome da base.
4. Confirme o grupo exibido.
5. Clique em **Criar base**.

Cada base possui uma coleção vetorial separada no Qdrant. Isso permite ativar, desativar ou excluir uma base sem misturar seus vetores com os de outra base.

### 6.2 Adicionar documentos

1. Na base desejada, clique em **Adicionar documento**.
2. Selecione um arquivo `.pdf`, `.txt` ou `.md`.
3. O arquivo será enviado para uma fila RabbitMQ.
4. Consulte **Jobs/RabbitMQ** até o job aparecer como `completed`.
5. Use **Ver documentos** para conferir o arquivo e a quantidade de chunks.

O limite padrão é 25 MB por arquivo e pode ser alterado por `UPLOAD_MAX_MB` no `.env`. PDF digitalizado somente como imagem precisa de OCR externo; esta versão não possui OCR integrado.

### 6.3 Permissões da base

Clique em **Permissões** e marque ou desmarque os usuários do grupo que podem consultar a base. Usuários de outro grupo não aparecem nessa relação e não conseguem acessar a base pela API.

Após mudar permissões, novas consultas já utilizam a regra atual. A versão de ACL também participa das chaves de cache para evitar o reaproveitamento de resultados autorizados anteriormente.

### 6.4 Ativar, desativar, renomear ou excluir

- **Renomear:** altera apenas o nome exibido.
- **Desativar:** mantém documentos e vetores, mas impede consultas à base.
- **Ativar:** volta a permitir consultas para usuários autorizados.
- **Excluir:** agenda a remoção da base, documentos e vetores pelo processamento assíncrono.
- **Remover documento:** elimina o documento selecionado e seus vetores, sem apagar os demais documentos da base.

### 6.5 Ver jobs

Na guia **Jobs/RabbitMQ**, clique em **Atualizar**. Os estados mais comuns são:

| Estado | Significado |
|---|---|
| `queued` | Aguardando o worker |
| `processing` | Documento ou exclusão em processamento |
| `completed` | Operação concluída |
| `failed` | Operação falhou; consulte o erro e os logs |

O worker tenta novamente operações com falha. Após o limite configurado, a mensagem segue para a dead-letter queue.

### 6.6 Cache

Na guia **Cache**:

- **Consultar** mostra informações do cache Valkey.
- **Limpar cache** remove dados descartáveis de embeddings e buscas.

Limpar o cache não remove conversas, documentos nem vetores. As próximas consultas apenas precisarão recalcular os resultados.

### 6.7 Última requisição

Depois de enviar uma mensagem no chat, a guia **Última requisição** apresenta dados como:

- modelo utilizado;
- bases consultadas;
- fontes recuperadas;
- hit ou miss de cache;
- estimativas de tokens;
- tempo de recuperação;
- tempo até o primeiro token;
- duração total.

Esses dados servem para estudar o pipeline sem expor raciocínio privado do modelo.

## 7. Administrar usuários do próprio grupo

No `/lab`, abra **Clientes e usuários**.

### Criar usuário

Preencha e-mail, nome, senha e nível:

- `client`: acessa chat, bases permitidas e o próprio perfil;
- `admin`: também acessa o laboratório e administra recursos do grupo.

E-mails são normalizados para minúsculas e não podem ser duplicados, inclusive entre grupos diferentes.

### Editar ou desativar

- **Editar:** permite mudar nome, e-mail, nível e opcionalmente senha.
- **Desativar:** bloqueia imediatamente o login e revoga tokens existentes.
- **Ativar:** restaura o acesso e cancela uma exclusão agendada que ainda não tenha sido executada.

### Excluir usuário

Ao clicar em **Excluir**:

- confirme com **OK** para remover permanentemente agora;
- escolha **Cancelar** na primeira confirmação para desativar agora e excluir após 30 dias.

A exclusão permanente remove também tokens e relacionamentos de permissão do usuário. O administrador do grupo não pode excluir a própria conta por essa tela.

### Retenção das conversas

Em **Retenção do grupo**, escolha `0`, `7`, `15`, `30`, `60` ou `90` dias. O valor define por quanto tempo uma conversa permanece recuperável na lixeira. O valor `0` representa expurgo imediato.

## 8. Administração global de identidades

Abra o Identity Manager na porta `8082` e entre com a conta administrativa global.

### Grupos

- **Criar:** informe um nome descritivo.
- **Renomear:** altera o nome sem mudar o UID.
- **Desativar:** bloqueia o acesso de todos os usuários do grupo e revoga seus tokens.
- **Ativar:** libera novamente o grupo, respeitando o estado individual de cada usuário.

Copie o UID com atenção quando precisar relacionar ou mover usuários. Grupos diferentes podem ter nomes semelhantes; o UID é a identidade efetiva.

### Usuários globais

O administrador global pode:

- criar usuário em qualquer grupo;
- mudar nome, e-mail, senha e nível;
- mover um usuário para outro UID de grupo;
- ativar ou desativar acesso;
- excluir imediatamente;
- desativar agora e excluir após 30 dias.

Ao mover um usuário de grupo, as permissões antigas de RAG são removidas e os relacionamentos passam a respeitar o novo grupo.

Use **Alterar senha** no cabeçalho para trocar a senha do administrador global.

## 9. Acompanhar os serviços

### Mapa de serviços

A porta `8081` apresenta os componentes, seus estados e as relações principais. Um serviço saudável confirma disponibilidade técnica, mas não substitui um teste completo de chat e RAG.

### Acessos iniciais

A porta `8083` apresenta usuários, senhas, endpoints e links separados por tipo de serviço. As senhas aparecem ocultas e podem ser reveladas ou copiadas. Use essa interface apenas na LAN de estudo; remova o container em qualquer ambiente real.

### Grafana

A porta `3000` reúne métricas, logs e traces por meio de Prometheus, Loki e Tempo. As credenciais são definidas por `GRAFANA_ADMIN_USER` e `GRAFANA_ADMIN_PASSWORD` no `.env`.

### RabbitMQ Management

A porta `15672` permite observar filas, consumidores, mensagens pendentes e a DLQ. As credenciais são `RABBITMQ_USER` e `RABBITMQ_PASSWORD` do `.env`.

## 10. Comandos de operação

Execute os comandos na raiz do projeto:

```bash
./start.sh                 # cria o que estiver ausente e inicia o ambiente
./start.sh status          # mostra os containers
./start.sh logs            # acompanha logs agregados
./start.sh restart         # reinicia os serviços
./start.sh stop            # encerra os containers sem apagar volumes
./start.sh pull-model      # baixa os modelos configurados
./start.sh smoke-test      # valida os serviços básicos
./start.sh identity-test   # valida RBAC, isolamento e ciclo de usuários
./start.sh e2e-test        # valida chat, RAG, embeddings, fila e cache
```

O comando `stop` não remove os volumes persistentes. Não execute `docker compose down -v` se quiser preservar usuários, sessões, documentos, vetores, métricas e modelos.

## 11. Solução de problemas

### Não consigo entrar

1. Confirme e-mail e senha.
2. Verifique se o usuário e o grupo estão ativos no Identity Manager.
3. Consulte o estado do container `identity`.

```bash
docker compose ps identity
docker compose logs --tail=200 identity
```

### Documento permanece em `queued`

Verifique API, RabbitMQ e worker:

```bash
docker compose ps api rabbitmq worker
docker compose logs --tail=200 api rabbitmq worker
```

### Documento aparece como `failed`

Consulte o erro na guia **Jobs/RabbitMQ** e os logs do worker. Confirme também se o arquivo é suportado e se o Ollama está saudável.

### Resposta está lenta

O primeiro uso do modelo costuma ser mais lento. Verifique CPU, memória, tamanho do contexto, quantidade de bases selecionadas e estado do Ollama:

```bash
docker stats --no-stream
docker compose exec ollama ollama list
docker compose logs --tail=200 ollama api
```

### A resposta não usa o documento

Confirme que:

1. o job de ingestão terminou como `completed`;
2. a base está ativa;
3. o usuário possui permissão;
4. a base está marcada em **Bases consultadas** no chat;
5. o arquivo produziu chunks;
6. a pergunta usa termos semanticamente relacionados ao conteúdo.

### Verificação geral

```bash
docker compose config --quiet
./start.sh smoke-test
./start.sh identity-test
./start.sh e2e-test
```

## 12. Boas práticas

- Troque todas as senhas padrão.
- Não publique as portas diretamente na Internet; use proxy reverso com TLS.
- Mantenha uma base e um grupo separados para cada cliente quando houver risco de mistura de dados.
- Conceda somente as permissões necessárias.
- Desative uma base antes de manutenção ou revisão de conteúdo.
- Faça backup dos volumes persistentes e teste a restauração.
- Use documentos de teste com respostas conhecidas para avaliar recuperação, fontes e isolamento.
- Consulte [README.md](README.md), [STRUCT.md](STRUCT.md) e [docs/README.md](docs/README.md) para aprofundar a arquitetura e os conceitos.
