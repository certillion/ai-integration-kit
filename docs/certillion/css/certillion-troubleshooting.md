# Certillion API — FAQ, Troubleshooting e Suporte

> **Documento público** — distribuível a clientes e parceiros integradores.
> Não contém informação interna ou confidencial. Propósito: responder às perguntas frequentes de
> integração, diagnosticar falhas com a API Certillion e padronizar a abertura de suporte com o
> time Certillion.

> Guia de diagnóstico para integração da assinatura digital ICP-Brasil do Certillion.
> Versão: 0.6-beta | Base URL padrão: `https://cloud.certillion.com/css/restful/application`
> ⚠️ Quando o PSC for `CERTILLION_SIGNER`, usar obrigatoriamente: `https://cloud-ws.certillion.com/css/restful/application`

> **Como este guia se relaciona com os demais arquivos.**
> Este documento é a **porta de entrada** para perguntas recorrentes de integração (a FAQ abaixo)
> e o **runbook de falhas**: o que a IA deve fazer quando uma chamada ao Certillion falha, o que
> coletar e como acionar o suporte. Ele **não duplica** os demais arquivos — a FAQ **roteia** para
> a seção autoritativa de cada tema. A lista canônica de códigos de erro está em
> `certillion-openapi.yaml` e o resumo conceitual em `certillion-api-reference.md` (Seção 9); o
> princípio de tratamento de erro em 3 camadas é a **Regra 13** da `certillion-skill.md`.
> Em caso de divergência sobre um campo, tipo ou código, o `certillion-openapi.yaml` prevalece.

---

## Índice

**[Perguntas frequentes de integração (FAQ)](#perguntas-frequentes-de-integração-faq) — comece aqui.**

1. [Princípio: nunca engolir o erro](#1-princípio-nunca-engolir-o-erro)
2. [O que capturar em TODA falha (pacote de evidências)](#2-o-que-capturar-em-toda-falha-pacote-de-evidências)
3. [O que NUNCA incluir (segurança e LGPD)](#3-o-que-nunca-incluir-segurança-e-lgpd)
4. [Triagem rápida (auto-diagnóstico)](#4-triagem-rápida-auto-diagnóstico)
5. [Integração (teste) vs. produção](#5-integração-teste-vs-produção)
6. [Quando resolver sozinho × quando escalar](#6-quando-resolver-sozinho--quando-escalar)
7. [Modelo de relatório de suporte](#7-modelo-de-relatório-de-suporte)
8. [Instruções para a IA (runbook automático)](#8-instruções-para-a-ia-runbook-automático)
9. [Exemplo de UI: painel "Ver detalhes" (camada 3 do R13)](#9-exemplo-de-ui-painel-ver-detalhes-camada-3-do-r13)

---

## Perguntas frequentes de integração (FAQ)

Respostas curtas que **roteiam** para a fonte autoritativa (o detalhe não é duplicado aqui).

| Pergunta | Resposta curta | Detalhe |
|----------|----------------|---------|
| Como evitar que o usuário reautentique a cada documento? | `scope=signature_session` + `lifetime` desejado (ex.: `43200` = 12 h); **persistir e reutilizar** o `access_token` nas chamadas `/signature`. | skill **R15**; api-reference §7 |
| Quanto tempo dura a sessão? | É definida pelo **PSC**, não pelo `lifetime` pedido — usar o `expires_in` de `/token` como verdade. | skill **R6**; api-reference §7 |
| Como usar o certificado **local** do usuário (A1 `.pfx` / A3)? | `psc=CERTILLION_SIGNER` + base URL `cloud-ws.certillion.com`. A plataforma **não** guarda a chave; o usuário instala o app **Assinador Certillion**. | skill **R16**; api-reference §2 |
| Onde baixo o app Assinador Certillion? | Em `certillion.com` — Windows, macOS, iOS e Android. | api-reference §2 |
| Como o usuário escolhe o provedor (PSC)? | Popular a lista de `GET /psc-info` (ou `/find-psc-accounts` para filtrar pelo CPF) e **acrescentar uma opção "Certificado Local / Token Físico"** que seleciona `CERTILLION_SIGNER`. O mesmo código serve a todos. | api-reference §2 |
| O `/token` falha logo após receber o `code` (`invalid_grant`/`invalid_client`). | Faltam `manager_id`/`manager_secret`, ou o `redirect_uri` difere do enviado no `/authorize`. | skill **R14**; §4.1 |
| Preciso cadastrar o `redirect_uri`? | **Não.** Qualquer URL funciona, desde que **idêntica** em `/authorize` e `/token`. O cadastro é opcional. | openapi (`client_maintenance`); §4.1 |
| Como tratar e exibir os erros? | 3 camadas: preservar o JSON bruto; mensagem **derivada do `status.code`** (nunca fixa); botão "Ver detalhes" com copiar/salvar. | skill **R13**; §1, §8 |
| O erro caiu numa mensagem genérica e não sei a causa. | Capturar o retorno bruto (`status.code`/`name`/`detail` + HTTP) e seguir a triagem. | §1, §2, §4 |
| Preciso perguntar algo ao Certillion (não é um erro). | Reúna objetivo, ambiente, `CLIENT_ID` (últimos 4), PSC e o que observou — sem segredos/PII. | §7 (perguntas de capacidade) |

---

## 1. Princípio: nunca engolir o erro

O artefato mais valioso de qualquer falha é a **resposta bruta do Certillion**: o corpo JSON com
`status.code`, `status.name`, `status.detail` (ou os campos OAuth `error` / `error_description` /
`error_uri`) **mais o HTTP status**. Esse conjunto aponta a causa em segundos.

O erro de integração mais caro **não é técnico, é de diagnóstico**: capturar a falha e mostrar ao
usuário apenas "Erro ao assinar", descartando o retorno original. Isso obriga o time do cliente e o
do Certillion a investigarem do zero — exatamente as "idas e vindas" que este guia existe para
evitar. Preserve o retorno original em log **antes** de qualquer tradução de mensagem (camada 1 da
Regra 13).

> Sintoma clássico de erro engolido: a tela do usuário diz algo genérico ("autorização recusada"),
> mas o `status.code` real (ex.: `620 CERTIFICATE_NOT_FOUND`, `249 TOKEN_VALIDITY_INVALID`,
> `invalid_grant`) nunca foi registrado. Sem ele, qualquer hipótese é chute.

---

## 2. O que capturar em TODA falha (pacote de evidências)

Reúna estes campos no momento da falha. Eles são o suficiente para o Certillion correlacionar nos
logs sem pedir mais nada:

| Campo | Exemplo | Por que importa |
|-------|---------|-----------------|
| Ambiente (`CERTILLION_ENV`) | `test` / `production` | Limites e credenciais diferem por ambiente |
| `CLIENT_ID` (**apenas últimos 4 dígitos**) | `...0120` | Identifica a aplicação sem expor a credencial |
| Servidor base | `cloud.certillion.com` / `cloud-ws.certillion.com` | Servidor errado → 404 |
| `psc` utilizado | `VAULTID`, `VIDAAS`, `CERTILLION_SIGNER`… | Comportamento e limites variam por PSC |
| Passo / endpoint que falhou | `(4) POST /oauth/token` | Localiza a etapa exata do fluxo de 6 passos |
| Data/hora **com fuso** (ISO 8601) | `2026-06-23T14:32:10-03:00` | Correlação direta com o log do servidor |
| HTTP status | `400` | Primeira pista da categoria do erro |
| Corpo bruto da resposta | `status.code/name/detail` ou `error`/`error_description` | A causa em si |
| IDs da transação (quando houver) | `transaction_id`, `document_hash` | Rastreia a operação no backend |
| `code` (OAuth) — **mascarado** | `a9ef****9457` | Confirma que houve callback, sem expor o segredo |
| Parâmetros da requisição (**sem segredos**) | `scope`, `lifetime`, `redirect_uri`, `code_challenge_method`, `grant_type`, `response_type` | Revela mismatch de configuração |
| `expires_in` retornado | `900` | Essencial em falhas de expiração de sessão |
| Reprodutibilidade | "sempre" / "intermitente" / "primeira vez" | Distingue bug de config × falha transitória |
| Mudança recente | "subimos versão hoje", "viramos a chave", "nada" | Aponta regressões |

> **ID de correlação / protocolo:** gere um identificador por transação e registre-o junto da
> evidência. Ele liga a tela do usuário, o seu log e o ticket de suporte em uma única busca.

---

## 3. O que NUNCA incluir (segurança e LGPD)

Relatórios de suporte trafegam por e-mail e sistemas de ticket. **Jamais** inclua segredos ou dados
pessoais. Mascare ou remova antes de exibir, logar em destino externo ou anexar:

- **O arquivo de certificado com chave privada (`.pfx` / `.p12`) e a senha do certificado** —
  **nunca** transmita ao Certillion, em tickets, em logs ou a qualquer servidor. A chave privada
  fica com o usuário (em nuvem, no PSC; local, no app Assinador na máquina do usuário). O Certillion
  **não armazena chaves** (ver skill R16) e não precisa delas para assinar.
- `client_secret` e `manager_secret` — **nunca**, em nenhuma hipótese.
- `access_token` completo (de sistema ou de assinatura) — se indispensável, apenas os últimos 4 caracteres.
- `code_verifier` (PKCE) completo — é o par secreto do `code_challenge`.
- **Conteúdo do documento / PDF** — e, sobretudo em saúde, **qualquer dado de paciente** (LGPD).
  Nunca anexe o documento a um ticket. Envie no máximo `document_hash` e tamanho.
- **CPF/CNPJ completo** do titular (`authorized_identification`) — mascare (ex.: `***.***.***-12`).
- `code` de uso único completo — mascare.

> Princípio: o time Certillion diagnostica pelo **código de erro + metadados da transação**, nunca
> pelo conteúdo assinado nem por segredos. Se um campo é segredo ou dado pessoal, ele não pertence
> ao ticket.

---

## 4. Triagem rápida (auto-diagnóstico)

Antes de abrir suporte, identifique o passo e tente o auto-fix. A lista completa de códigos está em
`certillion-openapi.yaml` / `api-reference` §9 — abaixo está a leitura **orientada à ação**.

### 4.1 Por passo do fluxo

| Passo | Sintoma típico | Causas prováveis | Primeira ação (auto-fix) |
|-------|----------------|------------------|--------------------------|
| **(1) `POST /oauth/client_token`** | `209 BAD_AUTHENTICATION` ou `404` | Credencial errada; ambiente trocado; servidor errado; chave de teste expirada (90 dias) | Conferir `CLIENT_ID`/`CLIENT_SECRET` em variável de ambiente, `CERTILLION_ENV` e servidor base |
| **(3) `GET /oauth/authorize`** | `404` (parâmetros/credencial); navegador não volta | Falta `response_type`/`code_challenge`/`code_challenge_method`; **`manager_id` omitido** (valor = CLIENT_ID); `psc` inválido | Conferir parâmetros obrigatórios — em especial enviar `manager_id` (= CLIENT_ID) —, o PKCE e o `psc` |
| **(4) `POST /oauth/token`** | `400 invalid_grant` / `invalid_client` **após** receber o `code` | `code` expirado/reutilizado; verifier divergente; callback diferente; credenciais manager ausentes/incorretas; PSC divergente | Usar PKCE e callback consistentes, enviar o par manager com as credenciais Certillion. No fluxo intermediado, não é obrigatório duplicar o par client; este identifica credenciais próprias junto ao PSC no modo direto |
| **(2) `POST /oauth/document`** | Upload rejeitado; `713 WRONG_DOCUMENT_TYPE` | Em **teste**, arquivo > 100 KB (limite rígido); tipo incompatível com o padrão | Conferir tamanho (teste) e o `signature_standard` vs. tipo do arquivo |
| **(5) `POST /oauth/signature`** | `250 INVALID_ACCESS_TOKEN` / `401`; `249`; `212`/`218`; `223`; `301`; `400`; `6xx` | Uso do **token errado** (precisa ser o de assinatura, não o de sistema); sessão expirada; crédito do PSC; certificado | Usar o token de `/oauth/token`; tratar expiração (re-autorizar passos 3–4); backoff em `301`/rate limit |
| **(6) `GET /oauth/document/{id}`** | `711 DOCUMENT_NOT_FOUND`; `712 WRONG_DOCUMENT_HASH` | `transaction_id` errado; hash divergente | Repetir o download com o `transaction_id` correto — **sem** reassinar (Regra 1) |
| **(6) Download com HTTP 406** | `Could not find acceptable representation` | Header Accept incompatível com retorno binário, como application/json | Usar Accept application/octet-stream e repetir só o download. Ler o ID em signatures[n].transaction |

### Resultado indeterminado e operações administrativas

- Timeout/desconexão/HTTP 5xx depois de enviar `/signature`: preservar IDs e intenção;
  conferir entradas retornadas e reconciliar antes de nova assinatura. A espera pelo
  app no celular não autoriza emitir outra assinatura.
- HTTP 400/código 205 em `/token-command`: preservar também o `name` real (pode ser
  `INTERNAL_ERROR`), pois código numérico isolado não explica a causa. Não considerar
  o token revogado após erro; eliminar a referência local não encerra a sessão remota.
- HTTP 400/`INVALID_ACCESS_TOKEN` em `/application`: confirmar credencial/perfil
  administrativo; não atribuir o erro a email ou CNPJ ausentes sem resposta específica.
- HTTP 500 em `/health-check`: a causa pode não ser identificada pela resposta;
  conferir o fluxo solicitado e recolher horário/HTTP/corpo redigido para suporte.
- HTTP 501 em `/application_cert`: endpoint descontinuado; não usar para cadastrar
  uma aplicação. Corpo vazio pode ser barrado com HTTP 400 antes desse retorno.

### 4.2 Por família de código (quem resolve)

- **Autenticação** (`209`, `250 INVALID_ACCESS_TOKEN`, `249 TOKEN_VALIDITY_INVALID`) → integrador: credencial, token correto, re-autorizar.
- **Parâmetros** (`200 REQUEST_MISSING_PARAM`, `205 REQUEST_BAD_DATA`, OAuth `invalid_request`) → integrador: corrigir a requisição.
- **OAuth `/token`** (`invalid_grant`, `invalid_client`) → integrador: PKCE, `code`, `redirect_uri`, `manager_*`, `psc`.
- **Documento** (`711`, `712`, `713`) → integrador: id/hash/tipo.
- **Certificado** (`600`, `604`, `605`, `620`) → **usuário no PSC**: certificado inválido/revogado/expirado/ausente.
- **Crédito/limite do PSC** (`212 ACCOUNT_NO_CREDIT`, `218 USERS_EXCEEDED_MAXIMUM_ALLOWED`) → **usuário no PSC** (ex.: BirdID).
- **PSC/transação** (`223 TRANSACTION_NOT_AUTHORIZED`, `301 TIMEOUT`, `400 USER_CANCELED`) → fluxo do usuário / transitório (backoff em `301`).

### 4.3 Cenários específicos (sessão e certificado local)

| Sintoma | Causa provável | Primeira ação (auto-fix) | Escalar? |
|---------|----------------|--------------------------|----------|
| Usuário reautentica no PSC (ex.: VIDAAS) a cada documento | Scope não é `signature_session`; token não reutilizado; `lifetime` curto | `scope=signature_session` + `lifetime` desejado (ex.: `43200` = 12 h); **persistir e reutilizar** o `access_token` nas chamadas `/signature` | Não — auto-fix do integrador |
| Sessão expira antes do `lifetime` pedido | O PSC define a duração real, não o `lifetime` | Usar o `expires_in` de `/token` como verdade e reautenticar ao expirar | Se o teto do PSC for insuficiente → **pergunta de capacidade** ao Certillion (ver §7) |
| `404` com certificado local | Servidor errado | Usar `cloud-ws.certillion.com` com `psc=CERTILLION_SIGNER` (os demais PSCs usam `cloud.certillion.com`) | Não |
| Certificado local não assina / não encontrado | App **Assinador Certillion** ausente ou sem o certificado na máquina do usuário | Confirmar que o usuário final instalou o Assinador Certillion (Win/macOS/iOS/Android) e que o certificado está disponível nele | Se o app estiver ok e ainda falhar → suporte Certillion |
| A1 no celular falha ao solicitar assinatura pelo navegador depois de o app ficar em segundo plano | A conexão do app Certillion pode ter sido interrompida | Detectar ambiente móvel, iniciar `/signature` e logo após acionar `css://signer.certillion.com/mobile_signature` no dispositivo, em paralelo e sem esperar a resposta; tratar a requisição original (R16) | Se persistir, registrar a resposta original e verificar a abertura/reconexão do app |

A ativação deve ocorrer durante a assinatura, sem aguardar timeout ou erro. Abrir
o app não significa que o documento foi assinado; não disparar uma nova assinatura
para realizar essa ativação. Uma chamada HTTP apenas no backend não abre o app
no dispositivo do usuário. Ver R16 e a seção de A1 móvel na referência.

---

## 5. Integração (teste) vs. produção

As causas mais prováveis mudam conforme o ambiente. Confirme `CERTILLION_ENV` antes de diagnosticar.

### Chave de teste

- **Validade de 90 dias:** falhas de autenticação que surgem "de repente" após semanas funcionando
  costumam ser a chave expirada. Prorrogável mediante solicitação ao suporte.
- **Limite rígido de 100 KB:** upload acima é **rejeitado**. Não confundir com a franquia de
  transferência de 200 KB de produção (esta não bloqueia, apenas gera custo proporcional).
- **200 assinaturas/mês:** ao atingir o teto, novas assinaturas falham — checar o volume do mês.
- **Certificado de teste é real:** não há sandbox; a assinatura de teste é ICP-Brasil com validade
  legal. O certificado/CPF precisa estar de fato associado à conta e ao PSC.

### Chave de produção

- **Sem limite rígido de tamanho:** o excedente de transferência é cobrado proporcionalmente, não
  bloqueia — então "arquivo grande" não é causa de falha em produção.
- **Rate limit por CPF** (~80/min atualmente, **varia por PSC e muda sem aviso**): tratar como
  **transitório** — fila com throttling e retry com backoff.
- **Tempo de sessão é do PSC:** usar sempre o `expires_in` de `/token`, não o `lifetime` pedido.
- **Crédito no PSC** (`212`/`218`): o usuário resolve na conta do PSC, não no Certillion.
- **Pós-virada teste→produção:** confirmar que `CLIENT_ID`/`CLIENT_SECRET` e a flag de ambiente
  foram trocados juntos — credencial de um ambiente com a flag do outro gera falha de autenticação.

---

## 6. Quando resolver sozinho × quando escalar

### Resolver sozinho (integrador — sem ticket)

Bugs de código ou configuração do próprio integrador. Corrija e **retente apenas o passo que
falhou** (Regra 1):

- PKCE: `code_verifier` é o par exato do `code_challenge` (S256) do **mesmo** fluxo.
- `code` de uso único: trocar imediatamente, nunca reutilizar.
- `redirect_uri` **idêntico** entre `/authorize` e `/token` (cuidado com barra final, `http`/`https`, maiúsculas). **Não precisa ser pré-cadastrado** — a única regra é usar o mesmo valor nas duas chamadas.
- `manager_id`/`manager_secret` **enviados**: recebem as credenciais fornecidas pela Certillion. No `/authorize`, `manager_id`; no `/token` intermediado, o par manager basta. Não confundir com o par client do modo de conexão direta ao PSC. `certillion_manager_id` não existe.
- `psc` igual ao informado no `/authorize`.
- `/signature` com o **token de assinatura** (de `/oauth/token`), não o token de sistema.
- Tamanho de arquivo (teste, 100 KB) e tipo de documento vs. `signature_standard`.
- Rate limit (`~80/min`) e `301 TIMEOUT`: backoff (transitório).

### Escalar para o **Certillion** (com o pacote da §7)

Coisas que dependem da configuração da conta ou da plataforma:

- Credencial parece correta mas a autenticação falha (suspeita de chave desativada/expirada).
- Prorrogação da chave de teste, virada teste→produção, dúvida sobre faixa/limite da conta.
- Erro persistente de plataforma **após** aplicar os auto-fixes acima.

### Escalar para o **PSC** (não o Certillion)

O Certillion intermedia, mas estes pertencem ao provedor de certificado do usuário:

- Crédito/limite do PSC (`212`, `218`).
- Certificado do usuário inválido/revogado/expirado/ausente (`600`, `604`, `605`, `620`).
- Autenticação do usuário no app/portal do próprio PSC.

---

## 7. Modelo de relatório de suporte

Bloco copiável para abrir suporte com o time Certillion. Preencher com a evidência (§2), já
**redigido** conforme a §3 (sem segredos e sem dados pessoais):

```
=== RELATÓRIO DE SUPORTE — INTEGRAÇÃO CERTILLION ===
Ambiente: test | production           (valor de CERTILLION_ENV)
CLIENT_ID (últimos 4 dígitos): ...0120
Servidor base: cloud.certillion.com | cloud-ws.certillion.com
PSC: VAULTID
Passo que falhou: (4) POST /oauth/token
Data/hora (ISO 8601, com fuso): 2026-06-23T14:32:10-03:00
ID de correlação/protocolo: <seu-id>
Reprodutibilidade: sempre | intermitente | primeira vez
Mudança recente: <ex.: "viramos a chave hoje" | "nada">

--- Resposta do Certillion (corpo bruto) ---
HTTP status: 400
{
  "status": { "code": <n>, "name": "<NOME>", "detail": "<detalhe>" }
  // ou, no fluxo OAuth:
  // "error": "invalid_grant", "error_description": "<...>", "error_uri": "<...>"
}

--- Parâmetros da requisição (SEM segredos) ---
grant_type: authorization_code
response_type/scope/lifetime: <...>
code_challenge_method: S256
redirect_uri (enviado no /token): https://seudominio.com.br/callback
redirect_uri (enviado no /authorize): <igual? sim/não>
code (mascarado): a9ef****9457
transaction_id / document_hash: <quando houver>
expires_in retornado: <quando aplicável>

--- Auto-fixes já verificados ---
[ ] code_verifier é o par do code_challenge do MESMO fluxo (S256)
[ ] redirect_uri idêntico em /authorize e /token (não precisa cadastro)
[ ] manager_id enviado no /authorize; manager_id + manager_secret enviados no /token (valores = CLIENT_ID/CLIENT_SECRET)
[ ] psc igual ao do /authorize
[ ] code trocado imediatamente, sem reuso
[ ] /signature usando o token de assinatura (não o de sistema)

--- NÃO incluído (por política) ---
client_secret, manager_secret, access_token completo, code_verifier,
conteúdo do documento / dados do paciente, CPF/CNPJ completo.
=== FIM ===
```

### Perguntas de capacidade ou conta ao Certillion (não-erros)

Nem toda dúvida é um erro. Para perguntas de **capacidade/configuração** (ex.: "qual o tempo
máximo de sessão do PSC X?", "como meus usuários obtêm o app Assinador Certillion?", "como faço a
virada para produção?", "quais os limites da minha conta?"), envie de uma vez:

- **Objetivo** em uma frase (o que você quer alcançar).
- **Ambiente** (`test`/`production`) e **`CLIENT_ID`** (últimos 4 dígitos).
- **PSC** envolvido.
- **O que já tentou e o que observou.** Para sessão: `scope` e `lifetime` enviados e o `expires_in`
  retornado. Para certificado local: endpoint usado e se o Assinador está instalado.
- A **dúvida específica** (sim/não ou um número), não um relato aberto.

> Como nos erros (§§2–3), **não** inclua segredos nem dados de paciente. O time Certillion responde
> com base em ambiente + PSC + `CLIENT_ID`, nunca pelo conteúdo assinado.

---

## 8. Instruções para a IA (runbook automático)

Quando **qualquer** chamada à API Certillion falhar, a IA deve:

1. **Preservar o retorno bruto** (`status.code/name/detail` + HTTP status, ou `error`/`error_description`)
   em log, correlacionado à transação — **antes** de traduzir a mensagem (camada 1 da Regra 13).
   Nunca exibir apenas mensagem genérica.
2. **Identificar o passo** (1–6 / endpoint) e consultar a triagem (§4).
3. **Se a causa for auto-fixável** (§6), aplicar a correção e **retentar apenas aquele passo** com
   os IDs já obtidos (Regra 1) — não reiniciar o fluxo nem reprocessar passos concluídos.
4. **Se não for auto-fixável** ou persistir após o auto-fix, **gerar automaticamente** o relatório
   de suporte no formato da §7, preenchido com o pacote de evidências (§2).
5. **Antes de exibir ou anexar**, aplicar a §3: mascarar/remover segredos e dados pessoais; **nunca**
   anexar o documento nem dados do paciente.
6. Registrar **data/hora com fuso** e um **ID de correlação** em todo o caminho (tela → log → ticket).
7. Direcionar a escalada corretamente (§6): Certillion (conta/plataforma) × PSC (crédito/certificado
   do usuário).
8. **Exibir a mensagem traduzida a partir do `status.code` real** — nunca um palpite fixo (ex.:
   "verifique se a URL de retorno está cadastrada"). Código não mapeado → mensagem neutra **e**
   sempre o controle "Ver detalhes".
9. **Camada 3 da Regra 13 = controle obrigatório de UI:** um botão "Ver detalhes / Avançado" que
   revela o JSON bruto (`status.code/name/detail` + HTTP) com ação de **copiar/salvar**, para o
   usuário acionar o suporte sem depender do time de desenvolvimento. Um erro só está bem tratado
   quando o usuário consegue recuperar o `status.code` sozinho.

> Objetivo do runbook: que a primeira mensagem ao suporte já contenha tudo para o diagnóstico —
> transformando um erro opaco em um caso autorrastreável e resolvível sem idas e vindas.

---

## 9. Exemplo de UI: painel "Ver detalhes" (camada 3 do R13)

Snippet agnóstico de framework para honrar a camada 3 da Regra 13: mensagem amigável **derivada do
`status.code`** + botão "Ver detalhes" com o JSON bruto e ação de copiar. Adapte o estilo ao seu app.

```html
<div id="cert-error"></div>
```

```javascript
// `raw` = JSON bruto preservado do Certillion (camada 1). `httpStatus` = status HTTP.
// `mapErrorMessage(code)` traduz status.code → mensagem (ver R13 / api-reference §9).
function renderCertillionError(raw, httpStatus, container) {
  const code = raw?.status?.code;
  // camada 2: mensagem vem do código REAL, nunca um texto fixo/palpite
  const msg = mapErrorMessage(code) || 'Não foi possível concluir a assinatura.';

  // camada 3: só metadados da transação — nunca segredos, .pfx/senha, token ou dados do paciente (ver §3)
  const detalhes = JSON.stringify(
    { http: httpStatus, status: raw?.status, transaction_id: raw?.transaction_id },
    null, 2
  );

  container.innerHTML =
    '<p>' + msg + '</p>' +
    '<button type="button" id="cert-toggle">Ver detalhes</button> ' +
    '<button type="button" id="cert-copy">Copiar</button>' +
    '<pre id="cert-json" hidden></pre>';
  container.querySelector('#cert-json').textContent = detalhes; // textContent evita injeção de HTML
  container.querySelector('#cert-toggle').onclick = () => {
    const el = container.querySelector('#cert-json'); el.hidden = !el.hidden;
  };
  container.querySelector('#cert-copy').onclick = () => navigator.clipboard.writeText(detalhes);
}
```

> A mensagem (camada 2) vem sempre do `status.code` real — nunca um texto fixo. Os detalhes
> (camada 3) trazem apenas metadados da transação; aplique a §3 antes de exibir ou salvar.

---

*Guia de troubleshooting baseado na documentação oficial Certillion, tutoriais, e-mail de
integração e na experiência da equipe e-Sec. Lista canônica de códigos e mecânica de endpoints:
`certillion-openapi.yaml`; resumo conceitual de erros: `certillion-api-reference.md` (Seção 9);
regra de tratamento de erro: `certillion-skill.md` (Regra 13). Documento público — versão 0.6-beta.*
