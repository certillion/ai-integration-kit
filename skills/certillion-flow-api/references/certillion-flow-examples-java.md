# Certillion Flow — Exemplos (Java 17+)

Documento público · Versão do kit: 0.7.1-beta. Jackson Databind 2.x no classpath (dependência com.fasterxml.jackson.core:jackson-databind gerenciada pelo projeto). Salvar como FlowExample.java.

Consultar [skill](../SKILL.md), [OpenAPI](certillion-flow-openapi.yaml)
e [fluxos](certillion-flow-integration-flows.md) para regras e recuperação.
O módulo abaixo não executa chamadas ao ser carregado. Sua aplicação decide quando
criar um processo e quando somente acompanhar um ID existente.

## Estado e dependências

- Ler credenciais da conta Flow de variáveis de ambiente/gestor de segredos do backend.
- Usar a base `https://flow.certillion.com/flow/restful`, ou a base oficial da conta/ambiente.
- `save` é uma função fornecida pelo projeto que grava um snapshot **durável** e só
  retorna após concluir a gravação. Carregar o mesmo estado nas retomadas, vinculado
  à mesma conta/servidor e ao mesmo PDF/operação local. Não reiniciar estado vazio
  para repetir um pedido. Coordenar workers por operação.
- `store_zip`/`storeZip` grava os bytes do ZIP antes de marcar o artefato como salvo.
  Não fazer extração automática de paths fornecidos pelo servidor.
- Guardar estado e artefatos em armazenamento privado. O exemplo não salva senha/token
  nos checkpoints. A referência local ao token é removida por `close`; isso não revoga
  a sessão no servidor.

## Cliente e operações independentes

```java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.io.ByteArrayOutputStream;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Duration;
import java.util.Base64;
import java.util.HexFormat;
import java.util.Map;
import java.util.UUID;

public class FlowExample {
    static final ObjectMapper JSON = new ObjectMapper();
    interface Save { void write(ObjectNode snapshot) throws Exception; }
    interface StoreZip { void write(byte[] bytes) throws Exception; }
    record Reply(int status, byte[] body) {}
    static class FlowError extends RuntimeException {
        final int http;
        final JsonNode response; // Redigir antes de registrar/exibir.
        FlowError(int http, JsonNode data) {
            super("Flow HTTP=" + http + ", código de aplicação=" + data.path("status").path("code").asText("ausente"));
            this.http = http; this.response = data;
        }
    }
    public static class Client implements AutoCloseable {
        final String base, account;
        private String token;
        private long expires;
        private final HttpClient http = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(30))
            .followRedirects(HttpClient.Redirect.NEVER).build();
        public Client(String base, String email, String password, int validity) throws Exception {
            this.base = base.replaceAll("/$", "");
            account = HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                .digest((this.base + "\n" + email).getBytes(StandardCharsets.UTF_8)));
            long started = System.nanoTime();
            String credentials = Base64.getEncoder().encodeToString((email + ":" + password).getBytes(StandardCharsets.UTF_8));
            JsonNode data = json(request("GET", "/application/login?validity=" + validity, null,
                Map.of("credentials", "Basic " + credentials), false, false));
            token = requiredText(data, "access_token");
            if (!data.path("validity").isIntegralNumber() || data.path("validity").asLong() <= 0)
                throw new IllegalStateException("Validade retornada inválida.");
            expires = started + Math.multiplyExact(data.path("validity").asLong(), 1_000_000_000L);
        }
        @Override public void close() { token = null; } // Não é revogação remota.
        Reply request(String method, String path, byte[] body, Map<String, String> headers, boolean auth, boolean binary) throws Exception {
            HttpRequest.Builder b = HttpRequest.newBuilder(URI.create(base + path)).timeout(Duration.ofSeconds(30))
                .header("Accept", binary ? "application/octet-stream" : "application/json");
            headers.forEach(b::header);
            if (auth) {
                if (token == null || System.nanoTime() >= expires)
                    throw new IllegalStateException("Sessão indisponível; renovar e retomar IDs.");
                b.header("access_token", "Bearer " + token);
            }
            b.method(method, body == null ? HttpRequest.BodyPublishers.noBody() : HttpRequest.BodyPublishers.ofByteArray(body));
            HttpResponse<byte[]> r = http.send(b.build(), HttpResponse.BodyHandlers.ofByteArray());
            return new Reply(r.statusCode(), r.body());
        }
        JsonNode json(Reply r) throws Exception {
            JsonNode data;
            try { data = JSON.readTree(r.body()); }
            catch (Exception e) { throw new FlowError(r.status(), JSON.createObjectNode().put("body", new String(r.body(), StandardCharsets.UTF_8))); }
            if (data == null) data = JSON.createObjectNode();
            if (r.status() < 200 || r.status() >= 300 || !data.path("status").path("code").isIntegralNumber() || data.path("status").path("code").asInt() != 100)
                throw new FlowError(r.status(), data);
            return data;
        }
        JsonNode call(String method, String path, JsonNode body) throws Exception {
            return json(request(method, path, body == null ? null : JSON.writeValueAsBytes(body),
                body == null ? Map.of() : Map.of("Content-Type", "application/json"), true, false));
        }
        public String upload(byte[] pdf) throws Exception {
            String boundary = "flow-" + UUID.randomUUID();
            ByteArrayOutputStream out = new ByteArrayOutputStream();
            out.write(("--" + boundary + "\r\nContent-Disposition: form-data; name=\"file\"; filename=\"documento.pdf\"\r\nContent-Type: application/pdf\r\n\r\n").getBytes(StandardCharsets.UTF_8));
            out.write(pdf); out.write(("\r\n--" + boundary + "--\r\n").getBytes(StandardCharsets.UTF_8));
            return requiredText(json(request("POST", "/application/upload", out.toByteArray(),
                Map.of("Content-Type", "multipart/form-data; boundary=" + boundary), true, false)), "document_id");
        }
        public String createProcess(JsonNode body) throws Exception {
            return requiredText(call("POST", "/application/signature-request", body), "process_id");
        }
        public JsonNode models() throws Exception { return call("GET", "/application/models", null).get("signature_model_list"); }
        public JsonNode registerModel(JsonNode body) throws Exception { return call("POST", "/application/register-signature-model", body).get("signature_model"); }
        public JsonNode process(String id) throws Exception {
            JsonNode data = call("GET", "/application/process?id=" + encode(id), null);
            JsonNode list = data.get("process_list");
            if (list == null || (!list.isNull() && !list.isArray())) throw new IllegalStateException("process_list ausente ou inválida.");
            if (!list.isNull()) for (JsonNode p : list) if (id.equals(p.path("id").asText())) return p;
            return null;
        }
        public byte[] download(String id) throws Exception {
            Reply r = request("GET", "/application/download/" + encode(id), null, Map.of(), true, true);
            if (r.status() == 403) return null;
            if (r.status() != 200) throw new FlowError(r.status(), JSON.createObjectNode());
            byte[] bytes = r.body();
            if (bytes.length < 4 || bytes[0] != 80 || bytes[1] != 75 || bytes[2] != 3 || bytes[3] != 4)
                throw new IllegalStateException("Resposta não parece ZIP.");
            return bytes; // Conferir CRC/inventário com biblioteca ZIP do projeto.
        }
    }
    static String encode(String s) { return URLEncoder.encode(s, StandardCharsets.UTF_8).replace("+", "%20"); }
    static String requiredText(JsonNode data, String field) {
        if (!data.path(field).isTextual() || data.path(field).asText().isEmpty())
            throw new IllegalStateException("Retorno sem " + field + "; reconciliar antes de repetir POST.");
        return data.path(field).asText();
    }
    static void bindState(Client client, ObjectNode state, Save save) throws Exception {
        if (!state.isEmpty() && !client.account.equals(state.path("account_key").asText()))
            throw new IllegalStateException("Estado de outra conta/servidor.");
        state.put("account_key", client.account); save.write(state.deepCopy());
    }
    static String createOnce(Client client, byte[] pdf, JsonNode signer, String callback, ObjectNode state, Save save) throws Exception {
        bindState(client, state, save);
        if (state.hasNonNull("process_id")) return requiredText(state, "process_id");
        URI cb = URI.create(callback);
        if (!"https".equals(cb.getScheme()) || cb.getHost() == null) throw new IllegalArgumentException("Callback deve ser HTTPS público controlado.");
        if (!state.hasNonNull("document_id")) {
            if (state.path("upload_attempted").asBoolean()) throw new IllegalStateException("Upload anterior sem resultado conciliado.");
            state.put("upload_attempted", true); save.write(state.deepCopy());
            state.put("document_id", client.upload(pdf)); save.write(state.deepCopy());
        }
        if (state.path("create_attempted").asBoolean()) throw new IllegalStateException("Criação anterior sem resultado conciliado.");
        state.put("create_attempted", true); save.write(state.deepCopy());
        ObjectNode body = JSON.createObjectNode().put("title", "Documento para assinatura")
            .put("type", "DIGITAL_SIGNATURE").put("callback_url", callback);
        body.putArray("documents").add(requiredText(state, "document_id"));
        body.putArray("signers").add(signer);
        state.put("process_id", client.createProcess(body)); save.write(state.deepCopy());
        return requiredText(state, "process_id");
    }
    static boolean resume(Client client, ObjectNode state, Save save, StoreZip storeZip, int waitSeconds, int interval) throws Exception {
        bindState(client, state, save);
        String id = requiredText(state, "process_id");
        long end = System.nanoTime() + Math.max(0, waitSeconds) * 1_000_000_000L;
        while (true) {
            JsonNode process = client.process(id);
            if (process != null) {
                state.set("process_status", process.path("status")); save.write(state.deepCopy());
                if ("FINALIZED_WITH_SUCCESS".equals(process.path("status").asText())) {
                    byte[] blob = client.download(id);
                    if (blob != null) {
                        storeZip.write(blob);
                        state.put("download_saved", true); save.write(state.deepCopy());
                        return true;
                    }
                }
            }
            long remaining = end - System.nanoTime();
            if (remaining <= 0) return false;
            Thread.sleep(Math.min(Math.max(1, interval) * 1000L, Math.max(1, remaining / 1_000_000L)));
        }
    }

    static String requiredEnv(String key) {
        String value = System.getenv(key);
        if (value == null || value.isEmpty()) throw new IllegalStateException("Configuração ausente: " + key);
        return value;
    }
    static boolean integrate(ObjectNode state, Save save, StoreZip storeZip, byte[] pdf) throws Exception {
        String base = System.getenv().getOrDefault("CERTILLION_FLOW_BASE_URL", "https://flow.certillion.com/flow/restful");
        try (Client client = new Client(base, requiredEnv("CERTILLION_FLOW_EMAIL"), requiredEnv("CERTILLION_FLOW_PASSWORD"), 900)) {
            if (pdf != null) { // Somente para solicitação deliberadamente nova.
                ObjectNode signer = JSON.createObjectNode().put("name", System.getenv().getOrDefault("CERTILLION_FLOW_SIGNER_NAME", "Participante"))
                    .put("email", requiredEnv("CERTILLION_FLOW_SIGNER_EMAIL"));
                createOnce(client, pdf, signer, requiredEnv("CERTILLION_FLOW_CALLBACK_URL"), state, save);
            }
            return resume(client, state, save, storeZip, 300, 5);
        }
    }
}
```

## Uso na aplicação

`integrate` retoma o estado existente quando o argumento PDF é omitido/null. Para
nova solicitação deliberada, fornecer o PDF e um estado novo vinculado ao negócio.
O método retorna conclusão ou pendência; não executar de novo com estado vazio
para recuperar um processo conhecido.

Criar uma instância autenticada e reutilizá-la nas operações da mesma execução;
encerrá-la em `finally`/`ensure` ou pelo mecanismo de fechamento da linguagem.
Não recriar a instância por documento. Obter os valores de configuração em:

| Configuração do exemplo | Origem sugerida |
|---|---|
| base/servidor | `CERTILLION_FLOW_BASE_URL`, default HTTPS acima |
| email da conta | `CERTILLION_FLOW_EMAIL` |
| senha da conta | `CERTILLION_FLOW_PASSWORD` |
| participante real, nome/email | Configuração do negócio ou `CERTILLION_FLOW_SIGNER_NAME`/`CERTILLION_FLOW_SIGNER_EMAIL` |
| callback público controlado | `CERTILLION_FLOW_CALLBACK_URL` |
| estado | Registro durável da operação local; vazio somente para operação deliberadamente nova |

Para nova solicitação, chamar a função de criação única com PDF, participante e
callback. Ela salva a intenção antes de cada POST e recusa repetição com resultado
incerto. Para acompanhar/download, chamar somente a função de retomada com o estado
salvo; ela não faz upload nem criação. A espera padrão do exemplo é uma escolha do
cliente, não um prazo do serviço. Espera encerrada retorna pendência e preserva o ID.

Os métodos de modelos permitem listar/cadastrar para uma integração visual. A
montagem do objeto visual está nos [fluxos](certillion-flow-integration-flows.md#preparação-visual);
validar a conversão de `signature_model.id` textual para o número requerido antes
de preencher `signature_model_id`. Em JavaScript, rejeitar conversão que não seja
inteiro seguro ou usar serialização numérica adequada para int64 sem perda.

O exemplo mínimo escolhe a modalidade digital sem visibilidade. Outras modalidades
seguem o schema e a decisão de negócio. Conclusão com sucesso e bytes ZIP recebidos
não validam criptograficamente os PDFs; usar ferramenta adequada para esse objetivo.
A verificação inicial de assinatura ZIP em algumas linguagens não substitui CRC e
inventário pela biblioteca de arquivos do projeto. Erros carregam resposta original
para diagnóstico interno; redigir seus dados antes de registrar ou exibir.
