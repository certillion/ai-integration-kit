# Certillion API — Exemplos de Integração (Java)

> **Documento público** — distribuível a clientes e parceiros integradores. Não contém
> informação interna ou confidencial. Propósito: habilitar a integração com a API Certillion.
>
> Versão: 0.3-beta | Linguagem: Java 11+ (java.net.http.HttpClient)
> Referenciado por `certillion-skill.md` e `certillion-api-reference.md`.
> A mecânica completa de cada endpoint (parâmetros, tipos, erros) está em `certillion-openapi.yaml`.

Este arquivo demonstra o **fluxo essencial** de assinatura: geração do par PKCE, os 6 passos
e a orquestração com retentativa por passo. As regras de implementação (R1–R12) estão na skill.

> ⚠️ As credenciais (`CLIENT_ID` / `CLIENT_SECRET`) devem vir de variáveis de ambiente.
> Base URL padrão: `https://cloud.certillion.com/css/restful/application`.
> Para `psc=CERTILLION_SIGNER`, usar `https://cloud-ws.certillion.com/css/restful/application`.

Usa o `HttpClient` nativo (Java 11+). Para parsing de JSON, os exemplos assumem uma
biblioteca como Jackson ou Gson; aqui o parsing é representado de forma simplificada.

---

## Configuração e guardrail de ambiente

```java
public class CertillionConfig {
    // CERTILLION_ENV — alterar para "production" antes de ir para produção
    public static final String CERTILLION_ENV = "test";
    // public static final String CERTILLION_ENV = "production";

    public static final String BASE_URL =
        "https://cloud.certillion.com/css/restful/application";
    public static final String CLIENT_ID     = System.getenv("CERTILLION_CLIENT_ID");
    public static final String CLIENT_SECRET = System.getenv("CERTILLION_CLIENT_SECRET");

    public static void avisarAmbienteTeste() {
        if ("test".equals(CERTILLION_ENV)) {
            System.err.println(
                "⚠️  Certillion: chave de TESTE ativa. Restrições: validade 90 dias, " +
                "arquivo até 100 KB, 200 assinaturas/mês. Trocar para produção antes do go-live."
            );
        }
    }
}
```

## Geração do par PKCE

```java
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Base64;

public class Pkce {
    public final String verifier;
    public final String challenge;

    private Pkce(String verifier, String challenge) {
        this.verifier = verifier;
        this.challenge = challenge;
    }

    private static String base64UrlEncode(byte[] data) {
        return Base64.getUrlEncoder().withoutPadding().encodeToString(data);
    }

    // Gerar UMA vez por fluxo de autorização
    public static Pkce generate() throws Exception {
        byte[] randomBytes = new byte[32];
        new SecureRandom().nextBytes(randomBytes);
        String verifier = base64UrlEncode(randomBytes);

        byte[] digest = MessageDigest.getInstance("SHA-256")
            .digest(verifier.getBytes("UTF-8"));
        String challenge = base64UrlEncode(digest);

        return new Pkce(verifier, challenge); // challenge -> /authorize ; verifier -> /token
    }
}
```

## Passo 1 — Client token (autenticação do sistema)

```java
import java.net.URI;
import java.net.http.*;

String getClientToken(HttpClient http) throws Exception {
    String body = "client_id=" + CLIENT_ID
        + "&client_secret=" + CLIENT_SECRET
        + "&grant_type=client_credentials"
        + "&lifetime=300";

    HttpRequest req = HttpRequest.newBuilder()
        .uri(URI.create(BASE_URL + "/oauth/client_token"))
        .header("Content-Type", "application/x-www-form-urlencoded")
        .POST(HttpRequest.BodyPublishers.ofString(body))
        .build();

    HttpResponse<String> resp = http.send(req, HttpResponse.BodyHandlers.ofString());
    String token = JsonUtil.getString(resp.body(), "access_token");
    if (token == null) throw new RuntimeException("client_token falhou: " + resp.body());
    return token;
}
```

## Passo 3 — URL de autorização (abrir no navegador do usuário)

```java
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;

String buildAuthorizeUrl(String challenge, String psc, String redirectUri) {
    String e = StandardCharsets.UTF_8.name();
    StringBuilder q = new StringBuilder();
    q.append("response_type=code");
    q.append("&manager_id=").append(CLIENT_ID);
    q.append("&code_challenge=").append(challenge);
    q.append("&code_challenge_method=S256");
    q.append("&psc=").append(psc);
    q.append("&scope=signature_session");
    q.append("&redirect_uri=").append(URLEncoder.encode(redirectUri, StandardCharsets.UTF_8));
    return BASE_URL + "/oauth/authorize?" + q;
}
// O usuário autentica no PSC e o navegador volta para redirect_uri?code=...&state=...
```

## Passo 4 — Token de assinatura (troca do code)

```java
String getSigningToken(HttpClient http, String code, String verifier,
                       String psc, String redirectUri) throws Exception {
    String body = "client_id=" + CLIENT_ID
        + "&client_secret=" + CLIENT_SECRET
        + "&grant_type=authorization_code"
        + "&code=" + code
        + "&code_verifier=" + verifier
        // manager_id/manager_secret: a API espera estes nomes aqui; o VALOR é o mesmo de client_id/client_secret (nome legado). Não remover.
        + "&manager_id=" + CLIENT_ID
        + "&manager_secret=" + CLIENT_SECRET
        + "&psc=" + psc
        + "&redirect_uri=" + URLEncoder.encode(redirectUri, StandardCharsets.UTF_8);

    HttpRequest req = HttpRequest.newBuilder()
        .uri(URI.create(BASE_URL + "/oauth/token"))
        .header("Content-Type", "application/x-www-form-urlencoded")
        .POST(HttpRequest.BodyPublishers.ofString(body))
        .build();

    HttpResponse<String> resp = http.send(req, HttpResponse.BodyHandlers.ofString());
    String token = JsonUtil.getString(resp.body(), "access_token");
    if (token == null) throw new RuntimeException("token falhou: " + resp.body());
    // R6: usar expires_in como fonte de verdade, não o lifetime solicitado
    return token;
}
```

## Passo 2 — Upload do documento

```java
import java.io.IOException;
import java.nio.file.*;

String uploadDocument(HttpClient http, Path pdfPath, String token) throws Exception {
    // multipart/form-data com um único campo "file"
    String boundary = "----CertillionBoundary" + System.currentTimeMillis();
    byte[] fileBytes = Files.readAllBytes(pdfPath);

    var baos = new java.io.ByteArrayOutputStream();
    baos.write(("--" + boundary + "\r\n").getBytes());
    baos.write(("Content-Disposition: form-data; name=\"file\"; "
        + "filename=\"documento.pdf\"\r\n").getBytes());
    baos.write("Content-Type: application/pdf\r\n\r\n".getBytes());
    baos.write(fileBytes);
    baos.write(("\r\n--" + boundary + "--\r\n").getBytes());

    HttpRequest req = HttpRequest.newBuilder()
        .uri(URI.create(BASE_URL + "/oauth/document"))
        .header("Authorization", "Bearer " + token)
        .header("Content-Type", "multipart/form-data; boundary=" + boundary)
        .POST(HttpRequest.BodyPublishers.ofByteArray(baos.toByteArray()))
        .build();

    HttpResponse<String> resp = http.send(req, HttpResponse.BodyHandlers.ofString());
    String hash = JsonUtil.getString(resp.body(), "document_hash");
    if (hash == null) throw new RuntimeException("upload falhou: " + resp.body());
    return hash; // R2: persistir
}
```

## Passo 5 — Solicitar assinatura

```java
String requestSignature(HttpClient http, String documentHash, String signingToken)
        throws Exception {
    String body = """
        {
          "signature_standard": "PADES",
          "signature_policy": "AD_RB",
          "pki_name": "ICP_BR",
          "detached": false,
          "hashes": [{ "id": "1", "alias": "documento", "hash": "%s" }]
        }
        """.formatted(documentHash);

    HttpRequest req = HttpRequest.newBuilder()
        .uri(URI.create(BASE_URL + "/oauth/signature"))
        .header("Authorization", "Bearer " + signingToken)
        .header("Content-Type", "application/json")
        .POST(HttpRequest.BodyPublishers.ofString(body))
        .build();

    HttpResponse<String> resp = http.send(req, HttpResponse.BodyHandlers.ofString());
    // R4: verificar status 140 (SIGNATURE_VALID) na primeira entrada de signatures[]
    Integer code = JsonUtil.getSignatureStatusCode(resp.body(), 0);
    if (code == null || code != 140) {
        throw new RuntimeException("assinatura inválida: " + resp.body());
    }
    return JsonUtil.getTransactionId(resp.body(), 0); // R2: persistir
}
```

## Passo 6 — Download do documento assinado

```java
byte[] downloadDocument(HttpClient http, String transactionId, String token)
        throws Exception {
    HttpRequest req = HttpRequest.newBuilder()
        .uri(URI.create(BASE_URL + "/oauth/document/" + transactionId))
        .header("Authorization", "Bearer " + token)
        .GET()
        .build();

    HttpResponse<byte[]> resp = http.send(req, HttpResponse.BodyHandlers.ofByteArray());
    if (resp.statusCode() < 200 || resp.statusCode() >= 300) {
        throw new RuntimeException("download falhou: HTTP " + resp.statusCode());
    }
    return resp.body();
}
```

## Orquestração com retentativa por passo (R1, R2)

```java
// ⚠️ Os IDs são persistidos entre passos — em caso de falha, retentar
// APENAS o passo que falhou, nunca reiniciar o fluxo do início.
byte[] signDocument(Path pdfPath, String signingToken) throws Exception {
    CertillionConfig.avisarAmbienteTeste();
    HttpClient http = HttpClient.newHttpClient();

    String clientToken = getClientToken(http);

    // Passo 2 — se falhar, repetir só este (novo upload)
    String documentHash = uploadDocument(http, pdfPath, clientToken);

    // Passo 5 — se falhar, repetir só este com o documentHash existente (NÃO re-upload)
    String transactionId = requestSignature(http, documentHash, signingToken);

    // Passo 6 — se falhar, repetir só este com o transactionId existente (NÃO re-assinar)
    return downloadDocument(http, transactionId, clientToken);
}
```

> `JsonUtil` representa o parsing de JSON via sua biblioteca preferida (Jackson, Gson).
> Substitua pelos métodos equivalentes do seu projeto.

---

*Os nomes de campo e valores de enum seguem `certillion-openapi.yaml` (fonte canônica). Em caso de divergência, o YAML prevalece.*
