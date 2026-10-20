---
name: certillion-api
description: >
  Implementar e depurar integrações com o módulo CSS (Certillion Signature Server):
  OAuth/PKCE, PSCs, upload, assinatura e validação ICP-Brasil, sessão reutilizável,
  certificado local e app Assinador. Aplicar a chamadas CSS como client_token,
  authorize, document e signature. Para processos com signatários e process_id
  do módulo Flow, usar a skill certillion-flow-api.
metadata:
  version: "0.6-beta"
  language: pt-BR
  classification: público

---

# Skill — Integração com a API Certillion CSS

> **Documento público** — distribuível a clientes e parceiros integradores. Não contém
> informação interna ou confidencial. Propósito único: habilitar a integração com a API Certillion.

## Propósito

Esta skill guia a implementação correta e econômica de integração com a API do módulo
CSS — Certillion Signature Server — de assinatura digital ICP-Brasil. Ela encapsula:

- O fluxo completo de autenticação OAuth2 com PKCE
- A sequência correta de assinatura de documentos (upload → assinar → download)
- Regras críticas de tratamento de erros para evitar cobranças duplicadas
- O guardrail de ambiente (chave de teste vs. produção)
- Otimizações de custo: os 3 fatores (quantidade de assinaturas, padrão de assinatura, tamanho do arquivo) e o ponto de atenção das chamadas desnecessárias

## Quando aplicar

Aplicar **sempre** que a tarefa envolver qualquer um dos seguintes:

- Código que chama endpoints da API Certillion CSS (qualquer linguagem)
- Revisão de código de integração Certillion CSS existente
- Diagnóstico de erros em assinaturas digitais via Certillion
- Configuração de ambiente (chave de teste/produção)
- Geração de `code_verifier` / `code_challenge` para OAuth2 PKCE
- Escolha de PSC (provedor de certificado), scope ou padrão de assinatura
- Otimização de custo de assinaturas
- Implementação de QR Code e rodapé em PDFs antes da assinatura

## O kit de documentação — quando usar cada arquivo

Os arquivos desta tabela são relativos a `docs/certillion/css/`, exceto o README
da raiz do repositório. Esta skill faz parte de um conjunto de arquivos complementares. Cada um tem um papel
distinto; ao trabalhar numa integração, saber qual consultar evita retrabalho e contradição:

| Arquivo | Papel | Consultar quando |
|---------|-------|------------------|
| **`certillion-skill.md`** (este) | As **regras** que todo código deve seguir | Sempre — é o ponto de partida que governa o comportamento |
| **`certillion-api-reference.md`** | **Guia conceitual**: fluxos, o porquê das decisões, lógica de custo, diagnóstico | Para entender *como* e *por que* algo funciona (fluxo OAuth, sessão, custo) |
| **`certillion-openapi.yaml`** | **Schema canônico** (OpenAPI 3.0): a mecânica exata de cada endpoint | Para o detalhe preciso de um endpoint — parâmetros, tipos, enums, body, erros |
| **`certillion-examples-{linguagem}.md`** | **Exemplos de código** do fluxo essencial, por linguagem (Node.js, Python, PHP, Java, Ruby) | Ao escrever o código da integração na linguagem-alvo |
| **`README.md`** (raiz do repositório) | **Como configurar** o kit nos principais harnesses (Claude Code, Codex, Cursor, Windsurf, Copilot, Antigravity) | Ao instalar o kit no ambiente de desenvolvimento |

**Regra de precedência:** para qualquer detalhe sobre a mecânica de um endpoint (nome de campo,
tipo, valor de enum, código de erro), o **`certillion-openapi.yaml` é a fonte única de verdade**.
A skill, o guia e os exemplos não duplicam essas tabelas — apontam para o YAML. Em caso de
divergência, o YAML prevalece.

Se o módulo não estiver claro, consultar o [guia CSS/Flow](../certillion-module-selection.md).

Ao gerar código, partir do exemplo da linguagem-alvo (`certillion-examples-*.md`) e aplicar as
regras desta skill, usando os tipos do YAML em vez de inferir estruturas.

---

## Regras obrigatórias — aplicar a todo código gerado

### R1 — Guardrail de ambiente (sempre incluir em código novo)

Todo sistema novo deve incluir a configuração de ambiente no início:

```javascript
// CERTILLION_ENV — alterar para 'production' antes de ir para produção
const CERTILLION_ENV = 'test';
// const CERTILLION_ENV = 'production';
```

Se `CERTILLION_ENV === 'test'`, exibir aviso em console ao inicializar:

```
⚠️  AVISO: Chave de TESTE do Certillion ativa.
   Restrições da chave de teste:
   - Validade: 90 dias a partir da emissão (prorrogável mediante solicitação)
   - Tamanho máximo de arquivo: até 100 KB por documento (limite rígido nesta chave)
   - Volume: até 200 assinaturas por mês
   Trocar para 'production' e solicitar nova chave antes de produção.
```

Se `CERTILLION_ENV === 'production'`, omitir o aviso completamente.

Se o código já possui o guardrail e o desenvolvedor pede para ativar produção:
→ trocar o valor para `'production'` e remover o bloco de aviso.

Se o código já está em produção e pede para voltar a teste:
→ trocar para `'test'` e restaurar o bloco de aviso.

### R2 — Separar obrigatoriamente os 3 passos de assinatura

Implementar upload, assinatura e download como operações independentes. Um orquestrador
pode coordená-las, desde que persista o progresso e permita retomar cada etapa:

```
document_hash  ← retornado pelo POST /document (usar no POST /signature)
transaction_id ← valor de signatures[n].transaction no POST /signature (usar no GET /document/{id})
```

Após uma rejeição confirmada e corrigida, retentar **somente o passo correspondente**:
- Upload falhou → repetir POST /document
- Assinatura falhou → repetir POST /signature com o document_hash anterior
- Download falhou → repetir GET /document/{transaction_id}

Nunca reiniciar o fluxo do início se apenas o download falhou.

Timeout, desconexão ou HTTP 5xx após enviar `/signature` deixam o resultado
indeterminado: a assinatura pode ter sido processada. Salvar a intenção antes da
chamada e os IDs de cada entrada recebida; não repetir automaticamente as entradas
aceitas nem o POST sem reconciliar o resultado. Em lote, examinar as respostas por
entrada. Quando não houver ID suficiente para recuperação, interromper a repetição
e apresentar diagnóstico. Não presumir suporte a chave de idempotência.

`transaction_id` acima é nome de variável interna: a chave JSON retornada é
**`transaction`**, inteiro. No download, enviar `Accept: application/octet-stream`;
`Accept: application/json` pode causar HTTP 406 por incompatibilidade com o retorno binário.

### R3 — Em lotes, retomar a partir do item que falhou

Nunca reiniciar o lote do item 1 se o erro ocorreu no item N. Persistir o índice de progresso.

### R4 — Verificar status da assinatura na resposta

Verificar `signatures[n].status.code === 140` (SIGNATURE_VALID) para cada entrada. Não assumir
que toda a requisição bem-sucedida implica que todas as assinaturas são válidas.

### R5 — Tratar expiração de token durante sessão

O PSC pode cancelar o token antes do prazo. Ao receber HTTP 401 com código
`TOKEN_VALIDITY_INVALID` ou `INVALID_ACCESS_TOKEN`, reiniciar o fluxo de autorização
(/authorize → /token). Não abortar silenciosamente.

### R6 — Nunca assumir o lifetime retornado pelo PSC

Usar `expires_in` da resposta de `/token` como fonte de verdade, não o `lifetime` enviado.
O tempo efetivo é definido pelo PSC e não é necessariamente o solicitado — por exemplo, o
SerproID tem padrão de 15 minutos, enquanto o RemoteID admite até 24 horas.

### R7 — Rate limit por CPF

Os PSCs aplicam limite de taxa de chamadas para o mesmo CPF. O valor varia por provedor e
**pode mudar sem aviso** (atualmente observa-se algo em torno de ~80 chamadas/minuto). Em
sistemas de alto volume para um único usuário, implementar fila com throttling e tratar a
falha de rate limit como transitória (retentar com backoff).

### R8 — Tamanho de lote

Lotes acima de 5–10 documentos aumentam o risco de timeout no PSC. Preferir múltiplas
chamadas individuais. A diferença de performance é baixa.

### R9 — Tamanho do arquivo e cobrança de transferência

Cada assinatura **já inclui 200 KB de transferência** (upload do original + download do assinado). Apenas o **excedente acumulado no mês** é cobrado adicionalmente: cada 1 MB acima da franquia = 1 assinatura adicional.

O documento cresce ao ser assinado — cerca de **4 KB por assinatura** com os certificados atuais — e aumenta a cada nova assinatura adicionada ao mesmo documento. Não há tamanho fixo "seguro".

O impacto é baixo e proporcional (documentos com o dobro do tamanho médio elevam o custo em ~10% a mais), mas o sistema deve evitar pagar excedente desnecessária ou desavisadamente ao longo do volume mensal. Trabalhar com margem de folga e monitorar os tamanhos reais durante o desenvolvimento. Boa prática: incluir um caso de teste que dispare aviso quando a soma do arquivo enviado + baixado se aproximar dos 200 KB. Comprimir imagens e logos antes da geração do PDF.

### R10 — QR Code e rodapé são responsabilidade do integrador

O PDF deve chegar ao Certillion já com:
- Rodapé com texto ICP-Brasil
- QR Code apontando para URL do próprio sistema (nunca para o Certillion)

Nenhuma alteração pode ser feita no PDF após a assinatura — isso invalida a assinatura.

### R11 — Proteger credenciais

`CLIENT_ID` e `CLIENT_SECRET` devem ser variáveis de ambiente. Nunca em código-fonte ou
arquivos versionados.

### R12 — Escolher o padrão de assinatura pela necessidade do negócio

O `signature_standard` é um fator de custo: **PAdES e XAdES custam ~30% mais que CAdES**,
por serem mais pesados de processar. Escolher o padrão pela necessidade real do negócio
(ex: norma do setor ou experiência do usuário):
- **PAdES** quando o documento precisa de assinatura embutida e visível no PDF (prescrições,
  documentos médicos, contratos) — é o caso usual no Brasil.
- **XMLDSig** padrão da nota fiscal eletrônica brasileira.
- **CADES** apenas para os casos em que esse padrão é o tecnicamente adequado (envelope separado
  para arquivos não-PDF/XML). A seleção do padrão deve seguir o tipo de documento.

Os três fatores de custo são: quantidade de assinaturas (R2/R3 evitam inflar), padrão de
assinatura (esta regra) e tamanho do arquivo (R9). Chamadas desnecessárias não são um fator
à parte — são o ponto de atenção que infla os fatores 1 e 3 (ver R2).

### R13 — Nunca engolir o erro do Certillion: preservar e expor com camadas

Um erro comum de integração é capturar a falha da API e exibir ao usuário apenas uma mensagem
genérica ("Erro ao assinar. Tente novamente."), **descartando o retorno original do Certillion**.
Quando isso acontece, rastrear o que de fato ocorreu exige parar o time de desenvolvimento do
cliente para investigar — o que raramente acontece a tempo, e o usuário final fica sem resposta
e frustrado.

O tratamento de erro deve ter **três camadas**:

1. **Sempre preservar** o JSON de erro original retornado pelo Certillion (campos `status.code`,
   `status.name`, `status.detail` e o HTTP status). Registrar em log com correlação à transação.
2. **Exibir ao usuário uma mensagem específica mas não técnica**, mapeada a partir do código de
   erro — não uma mensagem genérica. Exemplos de mapeamento:
   - `218 USERS_EXCEEDED_MAXIMUM_ALLOWED` / `212 ACCOUNT_NO_CREDIT` → "Não há créditos disponíveis
     no seu provedor de certificado. Verifique sua conta no PSC."
   - `249 TOKEN_VALIDITY_INVALID` / `250 INVALID_ACCESS_TOKEN` → "Sua sessão de assinatura expirou.
     Autentique-se novamente."
   - `301 TIMEOUT` → "O provedor de certificado demorou a responder. Tente novamente em instantes."
   - `620 CERTIFICATE_NOT_FOUND` → "Nenhum certificado válido foi encontrado para assinar."
   - `400 USER_CANCELED` → "A assinatura foi cancelada."
3. **Oferecer um "Ver detalhes"** que abre o JSON de erro original (code, name, detail, HTTP status,
   id da transação) — permitindo ao próprio usuário ou ao suporte do cliente copiar e reportar sem
   depender de uma investigação no backend.

Isso transforma um beco sem saída ("erro genérico → ninguém sabe o que houve") em algo
autorrastreável, e reduz drasticamente o atrito de suporte. A lista completa de códigos está em
`certillion-openapi.yaml` e na referência rápida do `certillion-api-reference.md`.

> **A camada 3 é obrigatória e é um controle de UI, não só um log.** O "Ver detalhes / Avançado"
> deve **exibir** o JSON bruto (`status.code`, `status.name`, `status.detail`, HTTP status, id da
> transação) com ação de **copiar/salvar**. A mensagem amigável (camada 2) deve ser **derivada do
> `status.code` real** — nunca um texto fixo/palpite (ex.: "verifique se a URL está cadastrada").
> Código não mapeado → mensagem neutra + sempre o "Ver detalhes". Critério de aceite: o usuário
> consegue recuperar o `status.code` sem acionar o time de desenvolvimento.

### R14 — Credenciais: `client_id`/`client_secret` (e-mail) usados como `manager_id`/`manager_secret` (parâmetros da API)

As credenciais que a e-Sec envia por e-mail são **`client_id` e `client_secret`**. A
**documentação oficial da API** usa, em `/oauth/authorize` e `/oauth/token`, os nomes de parâmetro
**`manager_id` e `manager_secret`** — com os mesmos valores:

- `manager_id` ← valor do `client_id`
- `manager_secret` ← valor do `client_secret`

**Não omita `manager_id`/`manager_secret`** no fluxo intermediado pelo Certillion.
Em `/oauth/token`, não é necessário duplicar esses valores em `client_id`/`client_secret`.
Esse segundo par identifica credenciais próprias junto ao PSC no modo de conexão direta,
e depende da configuração de conexão direta com o provedor.

| Chamada | Parâmetros de credencial | Valor a enviar |
|---------|--------------------------|----------------|
| `/oauth/client_token`, `/oauth/find-psc-accounts` | `client_id`, `client_secret` | suas credenciais |
| `GET /oauth/authorize` | `manager_id` | valor do `client_id` |
| `POST /oauth/token` (intermediado) | `manager_id`, `manager_secret` | valores das credenciais recebidas da Certillion |
| `/oauth/token` (conexão direta com PSC) | além do par manager, `client_id`, `client_secret` | credenciais próprias junto ao PSC; confirmar configuração do provedor |

O nome `certillion_manager_id` **não existe** — é `manager_id`. Os exemplos por linguagem já enviam
o par manager no fluxo intermediado, sem duplicar as credenciais no par client.

> Fonte dos nomes `manager_id`/`manager_secret`: documentação oficial da API —
> https://certillion.com/certillion-api/api-certillion-assinatura-digital-documentacao/

### R15 — Sessão reaproveitável: persistir e reutilizar o token de assinatura

Para o usuário autenticar **uma vez** e assinar vários documentos sem repetir o login no PSC
(ex.: VIDAAS) a cada assinatura:

1. No `/authorize`, usar `scope=signature_session` e `lifetime` na duração desejada em **segundos**
   (ex.: `lifetime=43200` = 12 h).
2. **Persistir** o `access_token` **e** o `expires_in` retornados por `/token`.
3. **Reutilizar** esse `access_token` em **todas** as chamadas `/signature` enquanto válido —
   **não** refazer `/authorize` + `/token` por documento (isso força novo login e infla chamadas).
4. Reautenticar (passos 3–4) só ao expirar ou ao receber `249`/`250` (ver R5).

A duração **efetiva** é definida pelo PSC, não pelo `lifetime` pedido (R6): usar sempre o
`expires_in`. Se o PSC limitar a sessão abaixo do necessário, é característica do provedor — ver
`certillion-troubleshooting.md` para o que levantar antes de perguntar ao Certillion.

### R16 — Certificado local (`CERTILLION_SIGNER`): servidor `cloud-ws` e app Assinador

Para assinar com certificado **local** do usuário (A1 em arquivo `.pfx` ou A3 em hardware
USB/cartão), usar o fluxo de assinatura com:

- `psc=CERTILLION_SIGNER`;
- Base URL `https://cloud-ws.certillion.com/css/restful/application` (os demais PSCs usam
  `cloud.certillion.com`; servidor trocado → `404`).

**Restrição que o integrador precisa conhecer (e que a IA deve sinalizar):** por segurança, o
Certillion **não armazena chaves do usuário**. **Não** é possível subir um `.pfx` para o backend
do integrador e pedir que o Certillion assine com ele. O usuário final precisa instalar o app
**Assinador Certillion** na própria máquina (Windows, macOS, iOS, Android), que detém o acesso ao
certificado (download em `certillion.com`). Ao gerar código com `CERTILLION_SIGNER`, orientar o
integrador a instruir seus usuários a instalar o app antes de assinar. Na lista de PSCs apresentada
ao usuário (vinda de `/psc-info` ou `/find-psc-accounts`), incluir uma opção "Certificado Local /
Token Físico" que seleciona `CERTILLION_SIGNER`. **Nunca** transmita o arquivo de certificado com
chave privada (`.pfx`/`.p12`) nem a senha do certificado — para o seu backend, para o Certillion ou
para logs. A chave permanece com o usuário (no app Assinador, no caso local).

#### A1 no app Certillion em dispositivo móvel: ativação durante a assinatura

Ao integrar A1 pelo app Certillion (`psc=CERTILLION_SIGNER`), detectar se o usuário
está em dispositivo móvel. Em iOS e Android, a conexão do app pode ser interrompida
quando ele fica em segundo plano enquanto o usuário está no navegador.

Nesse cenário, iniciar a requisição de assinatura (`POST /oauth/signature`) e,
**logo após seu disparo, em paralelo e sem aguardar sua resposta**, acionar no
dispositivo do usuário a **URL fixa de ativação do app fornecida pela Certillion**.
Isso permite trazer o app para execução, reconectar e atender à assinatura em curso.
Usar execução assíncrona adequada à aplicação; uma thread é apenas uma possibilidade.
Se a assinatura for solicitada pelo backend, coordenar a ativação com o navegador
ou cliente móvel: uma requisição HTTP feita apenas no servidor não abre o app no celular.

Manter a requisição de assinatura original em andamento e tratar seu resultado.
Abrir o app não comprova assinatura concluída. Não esperar `/signature` terminar
ou falhar para só então ativar o app, nem disparar outra assinatura para ativá-lo.
Preservar as regras de recuperação por etapa e de resultado indeterminado (R2).

**Endereço de ativação:** `css://signer.certillion.com/mobile_signature`, documentado
na observação sobre iOS da seção `signature` da
[referência oficial](https://certillion.com/certillion-api/api-certillion-assinatura-digital-documentacao/).
Usar esse endereço sem inventar parâmetros ou substituí-lo pela base REST ou pelo
link de download do app. Essa ativação é uma ação no dispositivo, não um novo
endpoint de assinatura. A aplicação ao Android e a ordem de disparo em paralelo
seguem a orientação operacional da Certillion; não extrapolar a outros PSCs ou ao Flow.

---

## Exemplos de código e referência de endpoints

Esta skill define as regras; ela não duplica a mecânica de endpoints nem os exemplos de código.

- **Mecânica de cada endpoint** (paths, parâmetros, tipos, enums, erros, base URLs e fluxo
  dos 6 passos): consultar `certillion-openapi.yaml` (fonte canônica) e o `certillion-api-reference.md`.
- **Exemplos de código prontos** do fluxo essencial (PKCE + 6 passos + orquestração com
  retentativa por passo), por linguagem:
  - `certillion-examples-nodejs.md` (Node.js / TypeScript)
  - `certillion-examples-python.md` (Python)
  - `certillion-examples-php.md` (PHP)
  - `certillion-examples-java.md` (Java)
  - `certillion-examples-ruby.md` (Ruby)

Ao gerar código, partir do exemplo da linguagem-alvo e aplicar as regras desta skill (em especial
R1 guardrail, R2 separação dos 3 passos com retentativa por passo, R4 verificação de status,
R6 expires_in, R9 tamanho/transferência e R12 padrão de assinatura).

## Diagnóstico de problemas comuns

| Sintoma | Causa provável | Solução |
|---------|---------------|---------|
| Fatura maior que esperado | Método único `assinar()` reiniciando do upload a cada falha | Separar passos; retentar só onde falhou |
| HTTP 401 TOKEN_VALIDITY_INVALID | Token de sessão cancelado pelo PSC antes do prazo | Reiniciar /authorize + /token |
| PSC retorna falha em alta frequência | Rate limit por CPF (varia por provedor; ~80 req/min atualmente, pode mudar) | Adicionar throttling e retentar com backoff |
| Assinatura inválida após alteração no PDF | PDF modificado após envio ao Certillion | QR Code e rodapé devem ser adicionados ANTES do upload |
| Sistema trava após 90 dias | Chave de teste expirada sem aviso | Implementar o guardrail de ambiente (R1) |
| `document_hash` rejeitado no `/signature` | Documento foi apagado (>48h) | Re-fazer o upload |
| Sessão dura menos que o esperado | O PSC retorna um tempo de sessão diferente do solicitado | Usar `expires_in` da resposta como fonte de verdade |
| Timeout no lote | Lote muito grande | Reduzir para 5–10 itens por chamada |
| BirdID falha ao assinar mesmo com certificado válido | Conta sem créditos no PSC (retorna `218 USERS_EXCEEDED_MAXIMUM_ALLOWED` ou `212 ACCOUNT_NO_CREDIT`) | Orientar o usuário a verificar o saldo/contratação de créditos junto ao BirdID; tratar esses códigos com mensagem específica (ver R13) |
| Usuário final frustrado, sem saber o que deu errado | Sistema mostra erro genérico e descarta o retorno do Certillion | Tratar o erro conforme R13: mensagem específica + opção de ver o JSON original |
| `/token` falha logo após receber o `code` (`invalid_grant`/`invalid_client`) | Credenciais manager ausentes/incorretas, code consumido/expirado, verifier ou redirect divergente | Enviar o par manager com as credenciais Certillion; não duplicar o par client no fluxo intermediado (R14) |
| Usuário precisa reautenticar (VIDAAS etc.) a cada documento | Scope não é `signature_session`, ou o token não é reutilizado, ou `lifetime` curto | Usar `signature_session` + `lifetime` desejado e reutilizar o `access_token` (R15) |
| `404` ao usar certificado local | Servidor errado para `CERTILLION_SIGNER` | Usar `cloud-ws.certillion.com` com `psc=CERTILLION_SIGNER` (R16) |
| Certificado local não assina / não encontrado | App Assinador Certillion ausente na máquina do usuário | Instruir o usuário final a instalar o Assinador Certillion (R16) |
| A1 no celular falha ao solicitar assinatura pelo navegador após o app ficar em segundo plano | Conexão do app pode ter sido suspensa | Disparar `/signature` e logo após acionar a URL oficial de ativação no dispositivo, em paralelo e sem aguardar a resposta (R16) |

---

## Verificação final antes de geração de código

Antes de gerar qualquer código de integração, confirmar internamente:

- [ ] O guardrail de ambiente (R1) está incluído
- [ ] Os 3 passos de assinatura são funções independentes com IDs persistidos (R2)
- [ ] Há tratamento de falha por passo (R2)
- [ ] O status da assinatura (`code === 140`) é verificado (R4)
- [ ] Há tratamento de expiração de token (R5)
- [ ] O tamanho do PDF é monitorado, com folga em relação aos 200 KB de transferência por assinatura (R9)
- [ ] O padrão de assinatura foi escolhido pela necessidade do documento, ciente de que PAdES/XAdES custam ~30% mais que CAdES (R12)
- [ ] QR Code e rodapé são adicionados antes do upload (R10)
- [ ] Credenciais estão em variáveis de ambiente (R11)
- [ ] O erro do Certillion é preservado e exibido em camadas: mensagem específica (derivada do `status.code`) + "ver detalhes" com o JSON original e copiar/salvar (R13)
- [ ] `/authorize` leva `manager_id`; `/token` leva `manager_id`/`manager_secret` com as credenciais Certillion; o par client fica reservado à conexão direta com PSC (R14)
- [ ] Se o usuário assina vários documentos: `signature_session` + persistência/reutilização do `access_token` (R15)
- [ ] Se usa certificado local: `CERTILLION_SIGNER` + `cloud-ws` e o usuário é orientado a instalar o Assinador Certillion (R16)
- [ ] Se usa A1 no app em dispositivo móvel: iniciar `/signature` e acionar `css://signer.certillion.com/mobile_signature` no dispositivo em paralelo, sem esperar a resposta (R16)
