# Certillion API — Exemplos de Integração (Node.js / TypeScript)

> **Documento público** — distribuível a clientes e parceiros integradores. Não contém
> informação interna ou confidencial. Propósito: habilitar a integração com a API Certillion.
>
> Versão: 0.5-beta | Linguagem: Node.js 18+ / TypeScript
> Referenciado por `certillion-skill.md` e `certillion-api-reference.md`.
> A mecânica completa de cada endpoint (parâmetros, tipos, erros) está em `certillion-openapi.yaml`.

Este arquivo demonstra o **fluxo essencial** de assinatura: geração do par PKCE, os 6 passos
e a orquestração com retentativa por passo. As regras de implementação (R1–R16) estão na skill;
aqui está a materialização delas em código.

> ⚠️ As credenciais (`CLIENT_ID` / `CLIENT_SECRET`) devem vir de variáveis de ambiente.
> Base URL padrão: `https://cloud.certillion.com/css/restful/application`.
> Para `psc=CERTILLION_SIGNER`, usar `https://cloud-ws.certillion.com/css/restful/application`.
>
> **A1 no app em dispositivo móvel (iOS/Android):** além do fluxo REST abaixo,
> detectar o ambiente móvel, iniciar `/signature` e logo após acionar no dispositivo
> a URL fixa oficial de ativação do app, em paralelo e sem esperar a resposta.
> Coordenar o cliente móvel/navegador com o backend; uma thread apenas no servidor
> não abre o app no celular. Manter a assinatura original e tratar seu resultado.
> URL de ativação: `css://signer.certillion.com/mobile_signature`. Consultar R16
> da skill e a seção de A1 móvel na referência para a sequência de integração.

---

## Configuração e guardrail de ambiente

```typescript
// CERTILLION_ENV — alterar para 'production' antes de ir para produção
const CERTILLION_ENV = 'test';
// const CERTILLION_ENV = 'production';

const BASE_URL = 'https://cloud.certillion.com/css/restful/application';
const CLIENT_ID = process.env.CERTILLION_CLIENT_ID!;
const CLIENT_SECRET = process.env.CERTILLION_CLIENT_SECRET!;

function avisarAmbienteTeste(): void {
  if (CERTILLION_ENV === 'test') {
    console.warn(
      '⚠️  Certillion: chave de TESTE ativa. Restrições: validade 90 dias, ' +
      'arquivo até 100 KB, 200 assinaturas/mês. Trocar para produção antes do go-live.'
    );
  }
}
```

## Geração do par PKCE

```typescript
import crypto from 'crypto';

function base64URLEncode(buf: Buffer): string {
  return buf.toString('base64')
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '');
}

// Gerar UMA vez por fluxo de autorização
export function generatePKCE() {
  const verifier  = base64URLEncode(crypto.randomBytes(32));
  const challenge = base64URLEncode(
    crypto.createHash('sha256').update(verifier).digest()
  );
  return { verifier, challenge }; // challenge → /authorize ; verifier → /token
}
```

## Passo 1 — Client token (autenticação do sistema)

```typescript
async function getClientToken(): Promise<string> {
  const params = new URLSearchParams({
    client_id: CLIENT_ID,
    client_secret: CLIENT_SECRET,
    grant_type: 'client_credentials',
    lifetime: '300',
  });

  const res = await fetch(`${BASE_URL}/oauth/client_token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: params,
  });
  const data = await res.json();
  if (!data.access_token) throw new Error(`client_token falhou: ${JSON.stringify(data)}`);
  return data.access_token;
}
```

## Passo 3 — URL de autorização (abrir no navegador do usuário)

```typescript
function buildAuthorizeUrl(challenge: string, psc: string, redirectUri: string): string {
  const q = new URLSearchParams({
    response_type: 'code',
    manager_id: CLIENT_ID,
    code_challenge: challenge,
    code_challenge_method: 'S256',
    psc,
    scope: 'signature_session',
    redirect_uri: redirectUri,
  });
  return `${BASE_URL}/oauth/authorize?${q.toString()}`;
}
// O usuário autentica no PSC e o navegador volta para redirect_uri?code=...&state=...
```

## Passo 4 — Token de assinatura (troca do code)

```typescript
async function getSigningToken(
  code: string, verifier: string, psc: string, redirectUri: string
): Promise<{ accessToken: string; expiresIn: number }> {
  const params = new URLSearchParams({
    grant_type: 'authorization_code',
    code,
    code_verifier: verifier,
    // manager_id/manager_secret: nomes de parâmetro da API (doc oficial); o valor é o seu client_id/client_secret. Não remover.
    manager_id: CLIENT_ID,
    manager_secret: CLIENT_SECRET,
    redirect_uri: redirectUri,
  });

  const res = await fetch(`${BASE_URL}/oauth/token?${new URLSearchParams({ psc })}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: params,
  });
  const data = await res.json();
  if (!data.access_token) throw new Error(`token falhou: ${JSON.stringify(data)}`);
  // R6: usar expires_in como fonte de verdade, não o lifetime solicitado
  return { accessToken: data.access_token, expiresIn: data.expires_in };
}
```

## Passo 2 — Upload do documento

```typescript
async function uploadDocument(pdf: Buffer, token: string): Promise<string> {
  const form = new FormData();
  form.append('file', new Blob([pdf], { type: 'application/pdf' }), 'documento.pdf');

  const res = await fetch(`${BASE_URL}/oauth/document`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: form,
  });
  const data = await res.json();
  if (!data.document_hash) throw new Error(`upload falhou: ${JSON.stringify(data)}`);
  return data.document_hash; // R2: persistir
}
```

## Passo 5 — Solicitar assinatura

```typescript
async function requestSignature(documentHash: string, signingToken: string): Promise<string> {
  const body = {
    signature_standard: 'PADES',
    signature_policy: 'AD_RB',
    pki_name: 'ICP_BR',
    detached: false,
    hashes: [{ id: '1', alias: 'documento', hash: documentHash }],
  };

  const res = await fetch(`${BASE_URL}/oauth/signature`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${signingToken}`, 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = await res.json();

  const sig = data.signatures?.[0];
  // R4: verificar status 140 (SIGNATURE_VALID) por entrada
  if (sig?.status?.code !== 140) {
    throw new Error(`assinatura inválida: ${JSON.stringify(sig?.status)}`);
  }
  return String(sig.transaction); // API: transaction inteiro; variável interna em string
}
```

## Passo 6 — Download do documento assinado

```typescript
async function downloadDocument(transactionId: string, token: string): Promise<Buffer> {
  const res = await fetch(`${BASE_URL}/oauth/document/${transactionId}`, {
    headers: { Authorization: `Bearer ${token}`, Accept: 'application/octet-stream' },
  });
  if (!res.ok) throw new Error(`download falhou: HTTP ${res.status}`);
  return Buffer.from(await res.arrayBuffer());
}
```

## Orquestração com retentativa por passo (R1, R2)

```typescript
// ⚠️ Os IDs são persistidos entre passos — em caso de falha, retentar
// APENAS o passo que falhou, nunca reiniciar o fluxo do início.
async function signDocument(
  pdf: Buffer, signingToken: string
): Promise<Buffer> {
  avisarAmbienteTeste();

  const clientToken = await getClientToken();

  // Passo 2 — se falhar, repetir só este (novo upload)
  const documentHash = await uploadDocument(pdf, clientToken);

  // Passo 5 — se falhar, repetir só este com o documentHash existente (NÃO re-upload)
  const transactionId = await requestSignature(documentHash, signingToken);

  // Passo 6 — se falhar, repetir só este com o transactionId existente (NÃO re-assinar)
  return await downloadDocument(transactionId, clientToken);
}
```

---

*Os nomes de campo e valores de enum seguem `certillion-openapi.yaml` (fonte canônica). Em caso de divergência, o YAML prevalece.*
