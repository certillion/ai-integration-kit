# Certillion API — Exemplos de Integração (PHP)

> **Documento público** — distribuível a clientes e parceiros integradores. Não contém
> informação interna ou confidencial. Propósito: habilitar a integração com a API Certillion.
>
> Versão: 0.3-beta | Linguagem: PHP 8.0+
> Referenciado por `certillion-skill.md` e `certillion-api-reference.md`.
> A mecânica completa de cada endpoint (parâmetros, tipos, erros) está em `certillion-openapi.yaml`.

Este arquivo demonstra o **fluxo essencial** de assinatura: geração do par PKCE, os 6 passos
e a orquestração com retentativa por passo. As regras de implementação (R1–R12) estão na skill.

> ⚠️ As credenciais (`CLIENT_ID` / `CLIENT_SECRET`) devem vir de variáveis de ambiente.
> Base URL padrão: `https://cloud.certillion.com/css/restful/application`.
> Para `psc=CERTILLION_SIGNER`, usar `https://cloud-ws.certillion.com/css/restful/application`.

Os exemplos usam a extensão cURL (padrão no PHP).

---

## Configuração e guardrail de ambiente

```php
<?php
// CERTILLION_ENV — alterar para 'production' antes de ir para produção
const CERTILLION_ENV = 'test';
// const CERTILLION_ENV = 'production';

const BASE_URL = 'https://cloud.certillion.com/css/restful/application';
$CLIENT_ID     = getenv('CERTILLION_CLIENT_ID');
$CLIENT_SECRET = getenv('CERTILLION_CLIENT_SECRET');

function avisarAmbienteTeste(): void {
    if (CERTILLION_ENV === 'test') {
        error_log(
            '⚠️  Certillion: chave de TESTE ativa. Restrições: validade 90 dias, '
            . 'arquivo até 100 KB, 200 assinaturas/mês. Trocar para produção antes do go-live.'
        );
    }
}
```

## Geração do par PKCE

```php
<?php
function base64UrlEncode(string $data): string {
    return rtrim(strtr(base64_encode($data), '+/', '-_'), '=');
}

// Gerar UMA vez por fluxo de autorização
function generatePkce(): array {
    $verifier  = base64UrlEncode(random_bytes(32));
    $challenge = base64UrlEncode(hash('sha256', $verifier, true));
    return ['verifier' => $verifier, 'challenge' => $challenge];
    // challenge -> /authorize ; verifier -> /token
}
```

## Passo 1 — Client token (autenticação do sistema)

```php
<?php
function getClientToken(): string {
    global $CLIENT_ID, $CLIENT_SECRET;
    $ch = curl_init(BASE_URL . '/oauth/client_token');
    curl_setopt_array($ch, [
        CURLOPT_POST => true,
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_HTTPHEADER => ['Content-Type: application/x-www-form-urlencoded'],
        CURLOPT_POSTFIELDS => http_build_query([
            'client_id' => $CLIENT_ID,
            'client_secret' => $CLIENT_SECRET,
            'grant_type' => 'client_credentials',
            'lifetime' => '300',
        ]),
    ]);
    $data = json_decode(curl_exec($ch), true);
    curl_close($ch);
    if (empty($data['access_token'])) {
        throw new RuntimeException('client_token falhou: ' . json_encode($data));
    }
    return $data['access_token'];
}
```

## Passo 3 — URL de autorização (abrir no navegador do usuário)

```php
<?php
function buildAuthorizeUrl(string $challenge, string $psc, string $redirectUri): string {
    global $CLIENT_ID;
    $q = http_build_query([
        'response_type' => 'code',
        'manager_id' => $CLIENT_ID,
        'code_challenge' => $challenge,
        'code_challenge_method' => 'S256',
        'psc' => $psc,
        'scope' => 'signature_session',
        'redirect_uri' => $redirectUri,
    ]);
    return BASE_URL . '/oauth/authorize?' . $q;
}
// O usuário autentica no PSC e o navegador volta para redirect_uri?code=...&state=...
```

## Passo 4 — Token de assinatura (troca do code)

```php
<?php
function getSigningToken(string $code, string $verifier, string $psc, string $redirectUri): array {
    global $CLIENT_ID, $CLIENT_SECRET;
    $ch = curl_init(BASE_URL . '/oauth/token?' . http_build_query(['psc' => $psc]));
    curl_setopt_array($ch, [
        CURLOPT_POST => true,
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_HTTPHEADER => ['Content-Type: application/x-www-form-urlencoded'],
        CURLOPT_POSTFIELDS => http_build_query([
            'grant_type' => 'authorization_code',
            'code' => $code,
            'code_verifier' => $verifier,
            // manager_id/manager_secret: nomes de parâmetro da API (doc oficial); o valor é o seu client_id/client_secret. Não remover.
            'manager_id' => $CLIENT_ID,
            'manager_secret' => $CLIENT_SECRET,
            'redirect_uri' => $redirectUri,
        ]),
    ]);
    $data = json_decode(curl_exec($ch), true);
    curl_close($ch);
    if (empty($data['access_token'])) {
        throw new RuntimeException('token falhou: ' . json_encode($data));
    }
    // R6: usar expires_in como fonte de verdade, não o lifetime solicitado
    return ['accessToken' => $data['access_token'], 'expiresIn' => $data['expires_in']];
}
```

## Passo 2 — Upload do documento

```php
<?php
function uploadDocument(string $pdfPath, string $token): string {
    $ch = curl_init(BASE_URL . '/oauth/document');
    curl_setopt_array($ch, [
        CURLOPT_POST => true,
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_HTTPHEADER => ['Authorization: Bearer ' . $token],
        CURLOPT_POSTFIELDS => [
            'file' => new CURLFile($pdfPath, 'application/pdf', 'documento.pdf'),
        ],
    ]);
    $data = json_decode(curl_exec($ch), true);
    curl_close($ch);
    if (empty($data['document_hash'])) {
        throw new RuntimeException('upload falhou: ' . json_encode($data));
    }
    return $data['document_hash']; // R2: persistir
}
```

## Passo 5 — Solicitar assinatura

```php
<?php
function requestSignature(string $documentHash, string $signingToken): string {
    $body = [
        'signature_standard' => 'PADES',
        'signature_policy' => 'AD_RB',
        'pki_name' => 'ICP_BR',
        'detached' => false,
        'hashes' => [['id' => '1', 'alias' => 'documento', 'hash' => $documentHash]],
    ];
    $ch = curl_init(BASE_URL . '/oauth/signature');
    curl_setopt_array($ch, [
        CURLOPT_POST => true,
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_HTTPHEADER => [
            'Authorization: Bearer ' . $signingToken,
            'Content-Type: application/json',
        ],
        CURLOPT_POSTFIELDS => json_encode($body),
    ]);
    $data = json_decode(curl_exec($ch), true);
    curl_close($ch);
    $sig = $data['signatures'][0] ?? [];
    // R4: verificar status 140 (SIGNATURE_VALID) por entrada
    if (($sig['status']['code'] ?? null) !== 140) {
        throw new RuntimeException('assinatura inválida: ' . json_encode($sig['status'] ?? null));
    }
    return (string) $sig['transaction']; // API: transaction inteiro; variável interna em string
}
```

## Passo 6 — Download do documento assinado

```php
<?php
function downloadDocument(string $transactionId, string $token): string {
    $ch = curl_init(BASE_URL . '/oauth/document/' . $transactionId);
    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_HTTPHEADER => ['Authorization: Bearer ' . $token, 'Accept: application/octet-stream'],
    ]);
    $content = curl_exec($ch);
    $status = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);
    if ($status < 200 || $status >= 300) {
        throw new RuntimeException("download falhou: HTTP {$status}");
    }
    return $content;
}
```

## Orquestração com retentativa por passo (R1, R2)

```php
<?php
// ⚠️ Os IDs são persistidos entre passos — em caso de falha, retentar
// APENAS o passo que falhou, nunca reiniciar o fluxo do início.
function signDocument(string $pdfPath, string $signingToken): string {
    avisarAmbienteTeste();

    $clientToken = getClientToken();

    // Passo 2 — se falhar, repetir só este (novo upload)
    $documentHash = uploadDocument($pdfPath, $clientToken);

    // Passo 5 — se falhar, repetir só este com o $documentHash existente (NÃO re-upload)
    $transactionId = requestSignature($documentHash, $signingToken);

    // Passo 6 — se falhar, repetir só este com o $transactionId existente (NÃO re-assinar)
    return downloadDocument($transactionId, $clientToken);
}
```

---

*Os nomes de campo e valores de enum seguem `certillion-openapi.yaml` (fonte canônica). Em caso de divergência, o YAML prevalece.*
