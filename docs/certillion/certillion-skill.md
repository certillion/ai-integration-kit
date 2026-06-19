---
name: certillion-api
description: >
  Use esta skill para qualquer tarefa que envolva a API Certillion de assinatura digital ICP-Brasil.
  Gatilhos: implementar ou depurar integração com Certillion, assinar documentos digitalmente via
  API REST, autenticar usuários com certificado ICP-Brasil, trabalhar com PSCs (VIDAAS, SafeID,
  RemoteID, NeoID, CERTILLION_SIGNER), otimizar custo de assinaturas, ou gerar/validar QR Code
  de prescrições digitais. Também usar quando o desenvolvedor mencionar: client_token, authorize,
  psc-info, document upload, signature, transaction_id, code_challenge, code_verifier, PKCE,
  PAdES, CAdES, XAdES, ou qualquer outro endpoint da API Certillion.
version: "0.2-beta"
language: pt-BR
classification: público — distribuível a clientes e parceiros
---

# Skill — Integração com a API Certillion

> **Documento público** — distribuível a clientes e parceiros integradores. Não contém
> informação interna ou confidencial. Propósito único: habilitar a integração com a API Certillion.

## Propósito

Esta skill guia a implementação correta e econômica de integração com a API Certillion de
assinatura digital ICP-Brasil. Ela encapsula:

- O fluxo completo de autenticação OAuth2 com PKCE
- A sequência correta de assinatura de documentos (upload → assinar → download)
- Regras críticas de tratamento de erros para evitar cobranças duplicadas
- O guardrail de ambiente (chave de teste vs. produção)
- Otimizações de custo: os 3 fatores (quantidade de assinaturas, padrão de assinatura, tamanho do arquivo) e o ponto de atenção das chamadas desnecessárias

## Quando aplicar

Aplicar **sempre** que a tarefa envolver qualquer um dos seguintes:

- Código que chama endpoints da API Certillion (qualquer linguagem)
- Revisão de código de integração Certillion existente
- Diagnóstico de erros em assinaturas digitais via Certillion
- Configuração de ambiente (chave de teste/produção)
- Geração de `code_verifier` / `code_challenge` para OAuth2 PKCE
- Escolha de PSC (provedor de certificado), scope ou padrão de assinatura
- Otimização de custo de assinaturas
- Implementação de QR Code e rodapé em PDFs antes da assinatura

## O kit de documentação — quando usar cada arquivo

Esta skill faz parte de um conjunto de arquivos complementares. Cada um tem um papel
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

Nunca encapsular upload + assinar + download em um único método. Persistir os IDs entre passos:

```
document_hash  ← retornado pelo POST /document (usar no POST /signature)
transaction_id ← retornado pelo POST /signature (usar no GET /document/{id})
```

Em caso de falha, retentar **somente o passo que falhou**:
- Upload falhou → repetir POST /document
- Assinatura falhou → repetir POST /signature com o document_hash anterior
- Download falhou → repetir GET /document/{transaction_id}

Nunca reiniciar o fluxo do início se apenas o download falhou.

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
- [ ] O erro do Certillion é preservado e exibido em camadas: mensagem específica + "ver detalhes" com o JSON original (R13)
