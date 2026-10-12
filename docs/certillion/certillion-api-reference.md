# Certillion API — Guia de Integração

> **Documento público** — distribuível a clientes e parceiros integradores.
> Não contém informação interna ou confidencial. Propósito: habilitar a integração com a API Certillion.

> Guia conceitual para integração da assinatura digital ICP-Brasil do Certillion.
> Versão: 0.4-beta | Base URL padrão: `https://cloud.certillion.com/css/restful/application`
> ⚠️ Quando o PSC for `CERTILLION_SIGNER`, usar obrigatoriamente: `https://cloud-ws.certillion.com/css/restful/application`

> **Como este guia se relaciona com os demais arquivos.**
> Este documento cobre o **conhecimento que um schema não expressa**: fluxos,
> regras de implementação, lógica de custo, decisões de arquitetura e
> diagnóstico. A **mecânica exata de cada endpoint** — paths, parâmetros, tipos,
> enums, bodies de request/response e códigos de erro — está em
> **`certillion-openapi.yaml`**, que é a referência canônica e única para isso.
> Os **exemplos de código** do fluxo essencial, por linguagem, estão nos arquivos
> **`certillion-examples-{linguagem}.md`** (Node.js, Python, PHP, Java, Ruby).
> A **instalação** do kit em cada assistente (Claude Code, Codex, Cursor, Windsurf, Copilot,
> Antigravity) está no **README.md** do repositório.
> Em caso de divergência sobre um campo ou tipo, o YAML prevalece.


---

## Índice

1. [Visão Geral](#1-visão-geral)
2. [Guardrail de Ambiente](#2-guardrail-de-ambiente)
3. [Fluxo Completo de Assinatura](#3-fluxo-completo-de-assinatura)
4. [Regras Críticas de Implementação](#4-regras-críticas-de-implementação)
5. [Endpoints — Referência Canônica](#5-endpoints--referência-canônica)
6. [Padrões de Assinatura](#6-padrões-de-assinatura)
7. [Escopos de Autorização](#7-escopos-de-autorização)
8. [Geração de code_verifier e code_challenge (PKCE)](#8-geração-de-code_verifier-e-code_challenge-pkce)
9. [Códigos de Status Internos do Certillion](#9-códigos-de-status-internos-do-certillion)
10. [Otimização de Custo](#10-otimização-de-custo)
11. [Modo Certillion Agent (sem upload de documento)](#11-modo-certillion-agent-sem-upload-de-documento)

---

## 1. Visão Geral

A API Certillion é uma API REST que permite a integração de assinatura digital ICP-Brasil em qualquer sistema. O Certillion atua como intermediário entre o sistema integrador e os PSCs (Prestadores de Serviço de Confiança), abstraindo a complexidade de cada provedor de certificado.

```
Sistema Integrador
      │
      │  REST/HTTPS
      ▼
Certillion API  ←──→  PSC (VIDAAS, SafeID, RemoteID, NeoID, etc.)
                            │
                            ▼
                     Certificado ICP-Brasil do usuário
```

**Conceito importante:** para o Certillion, o "cliente" é o sistema integrador (servidor), não o usuário final. O usuário final (médico, advogado, contador, etc.) é quem possui o certificado e autoriza o sistema a utilizá-lo.

---

## 2. Guardrail de Ambiente

> ⚠️ Este guardrail deve ser implementado no sistema integrador. Ele notifica o sistema que está sendo usada uma chave de teste que deve ser substituída antes de iniciar a produção.

### Configuração (definir no início do sistema)

```javascript
// ===========================================================
// CONFIGURAÇÃO DE AMBIENTE — CERTILLION
// ===========================================================
// Altere para 'production' antes de ir para produção.
// Se este valor for 'test', o sistema exibirá avisos ativos.
const CERTILLION_ENV = 'test';
// const CERTILLION_ENV = 'production'; // descomente para produção
// ===========================================================
```

### Comportamento

**Se `CERTILLION_ENV === 'test'`:**

O sistema deve exibir um aviso em console e, se aplicável, na interface:

```
⚠️  AVISO: Você está usando uma chave de TESTE do Certillion.

   Restrições da chave de teste:
   - Validade: 90 dias a partir da emissão da chave (prorrogável mediante solicitação)
   - Tamanho máximo de arquivo: até 100 KB por documento
   - Limite de volume: até 200 assinaturas por mês

   Ação necessária antes de ir para produção:
   - Solicite a virada para chave de produção ao suporte Certillion
   - Substitua as credenciais (CLIENT_ID / CLIENT_SECRET) no ambiente
   - Altere CERTILLION_ENV para 'production'

   NÃO use esta chave com usuários reais ou em ambiente produtivo.
```

> **Nota sobre o limite de 100 KB:** na chave de teste, 100 KB é um limite **rígido** de tamanho de arquivo — uploads acima disso são rejeitados. Em **produção** não há limite rígido: os 200 KB são uma franquia de transferência por assinatura, e ultrapassá-la gera apenas custo proporcional (ver Regra 7 e Seção 10), não bloqueio.

**Se `CERTILLION_ENV === 'production'`:**

- Nenhum aviso é exibido
- O guardrail é completamente ignorado pelo sistema
- O sistema opera normalmente sem verificações adicionais

### Instruções para a IA implementadora

- Se o sistema ainda **não possui** o guardrail e `CERTILLION_ENV` não está definido → **adicionar** o bloco acima com valor `'test'`
- Se o sistema já possui o guardrail e o desenvolvedor solicitar **ativar produção** → alterar o valor para `'production'` e remover (ou comentar) o bloco de exibição de aviso
- Se o sistema já possui o guardrail em produção e o desenvolvedor solicitar **voltar para teste** → alterar para `'test'` e restaurar o bloco de aviso

### Chave de teste vs. chave de produção

Não existe ambiente *sandbox*: **todas as assinaturas, inclusive as de teste, são assinaturas ICP-Brasil reais com validade legal.** A diferença está nos limites da credencial:

| Aspecto | Chave de teste | Chave de produção |
|---------|----------------|-------------------|
| Validade | 90 dias da emissão (prorrogável mediante solicitação) | Indefinida |
| Volume | até 200 assinaturas/mês | sem limite (segue o escalonamento por volume) |
| Tamanho de arquivo | limite rígido de 100 KB (upload acima é rejeitado) | sem limite rígido (excedente de transferência é cobrado proporcionalmente) |
| Custo | gratuito no período de integração | sem custo mínimo mensal — consumo zero, fatura zero |

A chave de produção é liberada após aprovação contratual. A migração de teste para produção é só uma troca de credenciais (`CLIENT_ID` / `CLIENT_SECRET`) e a mudança da flag de ambiente.

### Certificados e PSCs aceitos

O Certillion aceita **qualquer certificado ICP-Brasil** vinculado ao CPF do titular, em diferentes formas:

- **Certificado em nuvem**, via PSC (VIDAAS, SafeID, RemoteID, NeoID, VaultID, BirdID, DSCloud, etc.) — fluxo OAuth2 padrão.
- **Certificado local** (A3 em hardware USB/cartão, ou A1 em arquivo `.pfx`), via `psc=CERTILLION_SIGNER` — usa o servidor `cloud-ws.certillion.com` e **exige o app Assinador Certillion na máquina do usuário** (ver abaixo).

A lista de PSCs suportados é mantida pelo Certillion e exposta por `GET /oauth/psc-info` — **novos provedores passam a funcionar sem alteração de código** no sistema integrador. Por isso, popular a seleção de provedor a partir desse endpoint, em vez de manter uma lista fixa no código.

#### Certificado local (`CERTILLION_SIGNER`) e o app Assinador Certillion

Por decisão de segurança, **o Certillion não armazena nenhuma chave/certificado do usuário na plataforma**. Portanto, **não é possível** o sistema integrador subir um arquivo `.pfx` para o seu backend e pedir que o Certillion assine com ele.

Para usar um certificado **local** (A1 `.pfx` ou A3 em hardware), o **usuário final** instala o app **Assinador Certillion** na própria máquina (disponível para Windows, macOS, iOS e Android). O app detém o acesso ao certificado — a chave nunca sai do dispositivo do usuário.

Do ponto de vista do **código**, o fluxo é **idêntico** ao de um certificado em nuvem. A única diferença:

| | Certificado em nuvem (VIDAAS, SerproID, etc.) | Certificado local (Assinador) |
|---|---|---|
| `psc` | o PSC escolhido | `CERTILLION_SIGNER` |
| Base URL | `cloud.certillion.com` | `cloud-ws.certillion.com` |
| App na máquina do usuário | não | **sim — Assinador Certillion** |

> Servidor trocado → `404`. Usar `cloud-ws.certillion.com` **somente** com `CERTILLION_SIGNER`; `cloud.certillion.com` para os demais.

> **Orientação ao integrador:** se a sua aplicação oferece certificado local, informe ao usuário final que ele precisa instalar o Assinador Certillion **antes** de assinar. O app está disponível em `certillion.com` (Windows, macOS, iOS e Android).

#### Seleção de PSC pelo usuário final

Recomenda-se que **o próprio usuário final** (o médico, por exemplo) escolha o provedor de certificado. Como montar a lista de opções:

1. **Padrão:** popular a lista a partir de `GET /oauth/psc-info`, que retorna todos os PSCs em nuvem suportados — assim novos provedores aparecem sem alterar código.
2. **Lista enxuta (se o sistema souber o CPF):** chamar `POST /oauth/find-psc-accounts` para descobrir em **quais** PSCs aquele CPF tem certificado, e mostrar só esses.
3. **Certificado local:** acrescentar à lista uma opção do tipo **"Certificado Local" / "Token Físico"** que, ao ser escolhida, usa `psc=CERTILLION_SIGNER` (e o servidor `cloud-ws.certillion.com`).

O fluxo de assinatura é **o mesmo** para qualquer opção escolhida — muda apenas o `psc` (e a base URL, no caso do `CERTILLION_SIGNER`). Um código que já funciona com um PSC (ex.: VIDAAS) passa a funcionar com todos os demais.

---

## 3. Fluxo Completo de Assinatura

### 3.1 Fluxo padrão (certificado em nuvem — PSC)

```
[Sistema]                    [Certillion]              [PSC / Usuário]
   │                              │                          │
   │── POST /client_token ───────>│                          │
   │<── access_token (sistema) ───│                          │
   │                              │                          │
   │── GET /psc-info ────────────>│                          │
   │<── lista de PSCs ────────────│                          │
   │                              │                          │
   │  [usuário escolhe PSC]       │                          │
   │                              │                          │
   │── GET /authorize ───────────>│──── redireciona ────────>│
   │                              │                    [usuário autentica]
   │<── callback com ?code= ──────────────────────────────────
   │                              │                          │
   │── POST /token ──────────────>│                          │
   │<── access_token (assinatura) │                          │
   │                              │                          │
   │── POST /document ───────────>│  [upload do PDF]         │
   │<── document_hash ────────────│                          │
   │                              │                          │
   │── POST /signature ──────────>│──── solicita assinatura >│
   │                              │<── assinatura concluída ─│
   │<── transaction_id ───────────│                          │
   │                              │                          │
   │── GET /document/{id} ───────>│  [download PDF assinado] │
   │<── arquivo PDF assinado ─────│                          │
```

### 3.2 Numeração oficial dos passos (conforme e-mail de integração)

```
(1) POST /oauth/client_token          ← autenticação do sistema
(2) POST /oauth/document              ← upload do documento
(3) GET  /oauth/authorize             ← início da autorização do usuário
(4) POST /oauth/token                 ← conclusão da autorização (troca do code)
(5) POST /oauth/signature             ← solicitação de assinatura
(6) GET  /oauth/document/{id}         ← download do documento assinado

(7) POST /oauth/find-psc-accounts     ← opcional: descobrir PSCs do usuário
```

> Parâmetros e respostas de cada passo: ver `certillion-openapi.yaml`.

> **Parâmetros de credencial — mapeamento:** as credenciais recebidas da Certillion são usadas como `client_id`/`client_secret` em `/client_token`, e como `manager_id`/`manager_secret` no fluxo OAuth intermediado. `/authorize` leva `manager_id`; `/token` leva o par manager, sem exigir duplicação no par client. No modo de conexão direta, `client_id`/`client_secret` em `/token` identificam as credenciais próprias junto ao PSC. O fluxo intermediado manager-only foi confirmado em cloud/VIDAAS em 12/10/2026. Ver R14 da skill.

---

## 4. Regras Críticas de Implementação

### ⚠️ Regra 1 — Nunca encapsular os 3 passos de assinatura em um único método

**ERRADO:**
```javascript
async function assinar(arquivo, cpf) {
  const hash = await uploadDocumento(arquivo);      // passo 2
  const txId = await solicitarAssinatura(hash);     // passo 5
  const pdf  = await downloadDocumento(txId);       // passo 6
  return pdf;
}
```

**CORRETO:** os três passos devem ser chamados de forma independente, com IDs persistidos entre as chamadas:

```javascript
// Passo 2 — persiste document_hash
const documentHash = await uploadDocumento(arquivo);

// Passo 5 — persiste transaction_id
const transactionId = await solicitarAssinatura(documentHash);

// Passo 6 — usa transaction_id, não reexecuta os passos anteriores
const pdfAssinado = await downloadDocumento(transactionId);
```

Se qualquer passo falhar, **retentar apenas esse passo** usando o ID já obtido:

```
Passo 2 falhou? → repetir POST /document (novo upload é necessário)
Passo 5 falhou? → repetir POST /signature com o document_hash anterior (NÃO re-upload)
Passo 6 falhou? → repetir GET /document/{transaction_id} (NÃO re-assinar)
```

### ⚠️ Regra 2 — Em lotes, retomar a partir do item que falhou

```javascript
for (let i = 0; i < documentos.length; i++) {
  try {
    await processarDocumento(documentos[i]);
  } catch (e) {
    // Retomar daqui — não reiniciar o loop do início
    await retentarDocumento(documentos[i], e);
  }
}
```

### ⚠️ Regra 3 — Verificar validade do token durante a sessão

O PSC pode cancelar uma autorização antes do prazo solicitado. O sistema deve verificar o status do token a cada uso e, ao receber erro de autorização (`401` com código `TOKEN_VALIDITY_INVALID` ou `INVALID_ACCESS_TOKEN`), reiniciar o fluxo de autorização (passos 3 e 4).

### ⚠️ Regra 4 — Nunca assumir o tempo de sessão retornado

O `lifetime` passado em `/authorize` é uma **sugestão**; o tempo de sessão efetivo é definido pelo PSC e **não é necessariamente o solicitado**. Cada PSC tem seu próprio comportamento — por exemplo, o SerproID tem tempo de sessão padrão de 15 minutos, enquanto o RemoteID admite até 24 horas. O sistema deve sempre usar o `expires_in` retornado em `/token` como fonte de verdade, em vez de presumir o valor pedido.

### ⚠️ Regra 5 — Rate limit por CPF

Os PSCs aplicam limite de taxa de chamadas para o mesmo CPF. O valor varia por provedor e **pode mudar sem aviso** — atualmente, observa-se algo em torno de ~80 chamadas por minuto. Acima do limite, as chamadas passam a falhar. Em sistemas com alto volume para um mesmo usuário, implementar fila com throttling e tratar a falha de rate limit como transitória (retentar com backoff).

### ⚠️ Regra 6 — Tamanho de lotes

Lotes muito grandes aumentam o tempo de resposta do PSC e podem causar timeout HTTP. Histórico da plataforma: lotes de **até 5–10 documentos** são tratados com segurança por todos os PSCs. Para volumes maiores, prefira múltiplas chamadas individuais — a diferença de desempenho é baixa.

### ⚠️ Regra 7 — Tamanho do arquivo e cobrança de transferência

Cada assinatura **já inclui 200 KB de transferência**, somando o upload do documento original e o download do documento assinado. Esse valor faz parte do custo da assinatura — não é cobrado à parte.

Apenas o **excedente acumulado no período (mensal)** é cobrado adicionalmente, segundo a regra: cada 1 MB que ultrapassar a franquia equivale a 1 assinatura adicional na fatura.

É importante saber que o documento **cresce de tamanho** ao longo do processo: a assinatura insere bytes no arquivo — o quanto depende do tamanho do certificado, porém com os certificados atuais o acréscimo costuma ficar em torno de **4 KB a mais por assinatura**. Esse tamanho aumenta a cada nova assinatura adicionada ao mesmo documento. Por isso não existe um tamanho de PDF "seguro" fixo.

**Esse custo adicional, porém, é baixo.** A cobrança por transferência é proporcional: documentos com o dobro do tamanho médio elevariam o custo total em aproximadamente 10% a mais. O ponto de atenção não é o impacto unitário, e sim evitar que a empresa pague excedente de forma desnecessária ou sem perceber, ao longo do volume mensal.

**Recomendação durante o desenvolvimento:** trabalhe com uma margem de folga e acompanhe os tamanhos reais. Uma boa prática é incluir um caso de teste que dispare um aviso sempre que a soma do arquivo enviado mais o baixado se aproximar ou ultrapassar os 200 KB — assim qualquer crescimento inesperado aparece ainda em desenvolvimento, não na fatura.

### ⚠️ Regra 8 — QR Code e rodapé: responsabilidade do integrador

O Certillion **não adiciona** rodapé nem QR Code. O PDF deve chegar ao Certillion **já com o rodapé e o QR Code** apontando para a URL do sistema integrador. Qualquer alteração no PDF após a assinatura invalida a assinatura digital.

O QR Code **nunca deve apontar para o Certillion** — o usuário final (paciente, farmacêutico, contraparte) não tem relação com o Certillion, apenas com o sistema do cliente. O fluxo correto é: gerar o PDF completo → adicionar rodapé + QR Code apontando para uma URL própria → enviar ao Certillion para assinar → armazenar o PDF assinado vinculado ao protocolo do QR Code.

Exemplo de texto de rodapé:

```
Documento assinado digitalmente conforme ICP-Brasil (MP 2.200-2/2001).
O documento digital original está disponível em: https://[seu-dominio]/doc/[protocolo]
```

### ⚠️ Regra 9 — Proteger a chave de API

A `client_secret` deve ser armazenada como variável de ambiente, nunca em código-fonte. Vazamento de chave pode gerar consumo não autorizado com cobrança real.

---

## 5. Endpoints — Referência Canônica

A descrição completa de cada endpoint — método, path, headers, parâmetros, tipos, enums, bodies de request/response e códigos de erro — está em **`certillion-openapi.yaml`** (OpenAPI 3.0). Esse arquivo é a fonte única de verdade para a mecânica da API; este guia não duplica essas tabelas para evitar divergência de manutenção.

O YAML é importável diretamente em Postman/Insomnia e consumível por geradores de SDK e por assistentes de IA. Os exemplos de request prontos (incl. assinatura visível) também estão lá, no endpoint `/oauth/signature`. Para código pronto do fluxo completo, ver os arquivos `certillion-examples-{linguagem}.md` (Node.js, Python, PHP, Java, Ruby).

### Mapa de endpoints

Visão de orientação rápida. Para qualquer detalhe de campo, abrir o YAML.

| Endpoint | Método | Para que serve | Token |
|----------|--------|----------------|-------|
| `/oauth/client_token` | POST | Autentica o sistema (server-to-server) | — |
| `/oauth/psc-info` | GET | Lista todos os PSCs suportados | sistema |
| `/oauth/find-psc-accounts` | POST | Descobre em quais PSCs um CPF/CNPJ tem certificado | sistema |
| `/oauth/user-discovery` | POST | Verifica certificado em um PSC específico | sistema |
| `/certificate-discovery` | GET | Recupera o certificado autorizado pelo usuário | assinatura |
| `/oauth/authorize` | GET | Inicia OAuth2 (abrir no navegador do usuário) | — |
| `/oauth/token` | POST | Troca o `code` por token de assinatura | — |
| `/oauth/otp_authorize` | POST | Autorização via OTP do app Certillion (sem navegador) | — |
| `/oauth/pwd_authorize` | POST | Autorização via senha/OTP do PSC (opcional) | — |
| `/oauth/document` | POST | Upload do documento a assinar | sistema ou assinatura |
| `/oauth/document/{transaction_id}` | GET | Download do documento assinado | sistema ou assinatura |
| `/oauth/signature` | POST | Solicita a assinatura | **assinatura** |
| `/oauth/signature/validate` | POST | Valida assinatura ICP-Brasil (inclusive externa) | sistema ou assinatura |
| `/oauth/token-command` | POST | Invalida um token ativo | assinatura |
| `/oauth/client_maintenance` | POST | Atualiza dados cadastrais da aplicação | sistema |

> "Token: sistema" = `access_token` de `/oauth/client_token`.
> "Token: assinatura" = `access_token` de `/oauth/token`, `/oauth/otp_authorize` ou `/oauth/pwd_authorize`.
> O `/oauth/signature` exige **obrigatoriamente** o token de assinatura.

---

## 6. Padrões de Assinatura

| Padrão | Tipo de arquivo | Assinatura dentro do arquivo | Uso típico |
|--------|----------------|------------------------------|-----------|
| `PADES` | PDF | Sim | Prescrições, documentos médicos, contratos |
| `PADES_ICP_BR` | PDF | Sim | Igual ao PAdES com conformidade específica ICP-Brasil |
| `CADES` | Qualquer | Não (envelope separado) | Arquivos genéricos; permite omitir upload |
| `XADES` | XML | Sim | Documentos XML (NF-e, etc.) |
| `XMLDSIG_ENVELOPED` | XML | Sim (enveloped) | XML com assinatura interna |
| `XMLDSIG_ENVELOPING` | XML | Sim (enveloping) | XML com assinatura externa envolvendo o conteúdo |
| `RAW` | Qualquer | N/A | Assinatura binária bruta |

> Os campos exatos de `signature_standard`, `signature_policy` e as opções de assinatura visível (`visible_signature_options`, incl. as variáveis de texto `CERT_CN`, `CERT_CPF`, `SIGN_DATE`) estão tipados em `certillion-openapi.yaml`.

### CAdES detached — assinatura sem upload

Para CAdES detached, calcular o hash SHA-256 do arquivo localmente e passar no campo `hash`. Nenhum upload é necessário:

```bash
# Bash
sha256sum arquivo.jpg | awk '{ print $1 }' | xxd -r -p | base64
```

```javascript
// Node.js
const hash = crypto.createHash('sha256').update(fileBuffer).digest('base64');
```

---

## 7. Escopos de Autorização

| Scope | Descrição |
|-------|-----------|
| `single_signature` | Autoriza 1 chamada `/signature` para 1 documento |
| `multi_signature` | Autoriza 1 chamada `/signature` para lote de documentos |
| `signature_session` | Autoriza N chamadas durante o período de `lifetime`. Uso recomendado para sistemas onde o usuário assina múltiplos documentos em sequência |

### Padrão recomendado: sessão reaproveitável (não reautenticar a cada documento)

Para o usuário autenticar **uma vez** e assinar vários documentos sem repetir o login no PSC (ex.: VIDAAS) a cada assinatura:

1. No `/authorize`, usar `scope=signature_session` e `lifetime` na duração desejada em **segundos** (ex.: `lifetime=43200` = 12 h = 12 × 60 × 60).
2. Em `/token`, **persistir** o `access_token` **e** o `expires_in` retornados.
3. Reutilizar esse `access_token` em **todas** as chamadas `/signature` enquanto não expirar — **não** refazer os passos 3–4 (`/authorize` + `/token`) a cada documento.
4. Reautenticar (passos 3–4) só quando o `expires_in` se esgotar ou ao receber `249`/`250`.

> **A duração efetiva é definida pelo PSC, não pelo `lifetime` pedido** (Regra 4): o `lifetime` é uma sugestão. Alguns PSCs admitem horas (RemoteID, até 24 h); outros cortam para minutos (SerproID, ~15 min). Sempre tratar o `expires_in` de `/token` como a verdade. Se o PSC escolhido limitar a sessão abaixo do necessário, isso é característica do provedor — ver `certillion-troubleshooting.md` (perguntas de capacidade ao Certillion) para o que levantar antes de abrir a dúvida.

---

## 8. Geração de code_verifier e code_challenge (PKCE)

Devem ser gerados **uma vez por fluxo de autorização**:

```javascript
// Node.js
const crypto = require('crypto');

function base64URLEncode(str) {
  return str.toString('base64')
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '');
}

const verifier   = base64URLEncode(crypto.randomBytes(32));
const challenge  = base64URLEncode(
  crypto.createHash('sha256').update(verifier).digest()
);

// challenge → enviar em /authorize como code_challenge
// verifier  → enviar em /token como code_verifier
```

O mesmo algoritmo (S256) nas demais linguagens está em `certillion-examples-{linguagem}.md`.

---

## 9. Códigos de Status Internos do Certillion

Tabela de referência rápida. A lista completa de códigos por endpoint está em `certillion-openapi.yaml`.

| Código | Nome | Descrição |
|--------|------|-----------|
| 100 | REQUEST_OK | Requisição aceita com sucesso |
| 110 | TRANSACTION_IN_PROGRESS | Processando |
| 130 | CERTIFICATE_VALID | Certificado válido |
| 140 | SIGNATURE_VALID | Assinatura válida |
| 200 | REQUEST_MISSING_PARAM | Parâmetro obrigatório ausente |
| 205 | REQUEST_BAD_DATA | Dados da requisição inválidos |
| 209 | BAD_AUTHENTICATION | Falha de autenticação |
| 212 | ACCOUNT_NO_CREDIT | Conta do usuário sem crédito no PSC (ex.: BirdID) |
| 218 | USERS_EXCEEDED_MAXIMUM_ALLOWED | Limite de acessos/créditos contratados ao PSC esgotado |
| 223 | TRANSACTION_NOT_AUTHORIZED | Transação não autorizada |
| 249 | TOKEN_VALIDITY_INVALID | Token expirado |
| 250 | INVALID_ACCESS_TOKEN | Token inválido |
| 301 | TIMEOUT | Timeout na comunicação com o PSC |
| 400 | USER_CANCELED | Usuário cancelou a transação |
| 600 | CERTIFICATE_INVALID | Certificado inválido |
| 604 | CERTIFICATE_REVOKED | Certificado revogado |
| 605 | CERTIFICATE_EXPIRED | Certificado expirado |
| 620 | CERTIFICATE_NOT_FOUND | Nenhum certificado encontrado |
| 700 | SIGNATURE_INVALID | Assinatura inválida |
| 711 | DOCUMENT_NOT_FOUND | Documento não encontrado no servidor |
| 712 | WRONG_DOCUMENT_HASH | Hash do documento divergente |
| 713 | WRONG_DOCUMENT_TYPE | Tipo de documento incompatível |

### Tratamento e exibição de erros — preservar o retorno do Certillion

Um erro frequente de integração é capturar a falha e mostrar ao usuário apenas uma mensagem
genérica ("Erro ao assinar"), descartando o retorno original do Certillion. Quando isso ocorre,
descobrir o que de fato aconteceu exige parar o time de desenvolvimento do cliente para investigar
— o que raramente acontece a tempo, e o usuário final fica sem resposta.

Recomenda-se tratar o erro em três camadas:

1. **Preservar** o JSON original (`status.code`, `status.name`, `status.detail` e o HTTP status)
   em log, correlacionado à transação.
2. **Exibir uma mensagem específica e não-técnica**, mapeada pelo código. Exemplos: `218`/`212`
   → "Não há créditos no seu provedor de certificado; verifique sua conta no PSC"; `249`/`250`
   → "Sua sessão de assinatura expirou; autentique-se novamente"; `301` → "O provedor demorou a
   responder; tente em instantes"; `620` → "Nenhum certificado válido encontrado"; `400`
   (USER_CANCELED) → "A assinatura foi cancelada".
3. **Oferecer "Ver detalhes"** que exibe o JSON de erro original — para o usuário ou o suporte
   do cliente reportar sem depender de investigação no backend.

Isso transforma um erro genérico opaco em algo autorrastreável e reduz o atrito de suporte.

---

## 10. Otimização de Custo

O custo de cada mês é calculado por três fatores: a quantidade de assinaturas, o padrão de assinatura e o tamanho do arquivo. As chamadas desnecessárias não são um fator à parte, mas um ponto de atenção que infla esses fatores — ver o final desta seção.

### Fator 1 — Quantidade de assinaturas

Cada chamada com sucesso a `/signature` é cobrada. O preço por assinatura é **escalonado por volume mensal**: quanto maior o volume, menor o preço unitário, com ajuste automático de faixa (sem necessidade de solicitação). Os valores de cada faixa constam da proposta comercial. Para o código, o que importa é não inflar a contagem de assinaturas desnecessariamente (ver [Ponto de atenção](#ponto-de-atenção--chamadas-desnecessárias)).

### Fator 2 — Padrão de assinatura

O padrão escolhido afeta o preço unitário: **PAdES e XAdES custam cerca de 30% mais que CAdES**, por serem mais pesados de processar. A escolha do padrão deve seguir a adequação técnica ao documento — PAdES para PDF, XAdES para XML, CAdES para outros formatos.

### Fator 3 — Tamanho do arquivo

Cada assinatura **já inclui 200 KB de transferência** (upload do original + download do assinado). Apenas o **excedente acumulado no mês** é cobrado adicionalmente: cada 1 MB acima da franquia equivale a 1 assinatura adicional.

O documento cresce ao ser assinado — cerca de **4 KB por assinatura** com os certificados atuais — e aumenta a cada nova assinatura adicionada ao mesmo documento. Não há, portanto, um tamanho fixo "seguro".

O impacto no custo é baixo e proporcional: documentos com o dobro do tamanho médio elevariam o custo total em aproximadamente 10% a mais. O cuidado não é com o impacto unitário, mas com não pagar excedente de forma desnecessária ou sem perceber ao longo do volume mensal.

**Meta durante o desenvolvimento:** trabalhar com margem de folga e monitorar os tamanhos. Comprimir imagens e logos antes de gerar o PDF. Ver a [Regra 7](#️-regra-7--tamanho-do-arquivo-e-cobrança-de-transferência) para a recomendação de caso de teste de monitoramento.

### Ponto de atenção — Chamadas desnecessárias

Não é um fator de custo em si, mas a principal causa de custo inflado na prática. Encapsular os 3 passos de assinatura num único método e reiniciar o fluxo a cada falha faz o sistema repetir uploads e assinaturas já concluídos — inflando o Fator 1 (quantidade) e o Fator 3 (transferência). Tratar cada falha no passo exato em que ocorreu. Ver [Regra 1](#️-regra-1--nunca-encapsular-os-3-passos-de-assinatura-em-um-único-método).

---

## 11. Modo Certillion Agent (sem upload de documento)

Para sistemas que não podem enviar documentos a servidores externos (compliance, LGPD, documentos sigilosos), o Certillion Agent processa o documento localmente:

```
[Sistema]      [Certillion Agent (local)]      [Certillion Server]
   │                      │                           │
   │── POST /document ───>│                           │
   │                      │── calcula hash ───────────│
   │── POST /signature ──>│── POST /signature ───────>│
   │                      │<── assinatura ────────────│
   │<── GET /document ────│                           │
   │         (gerado localmente)
```

Vantagens: sem transmissão do conteúdo do documento; assinatura mais rápida; compliance com políticas internas. O código de integração **não precisa ser alterado** — o Agent atua como proxy neutro de rede. Solicitar instalação ao suporte após concluir a integração padrão.

---

*Guia conceitual baseado na documentação oficial Certillion, tutoriais, e-mail de integração e vídeo tutorial técnico da e-Sec. Mecânica de endpoints: ver `certillion-openapi.yaml`.*
