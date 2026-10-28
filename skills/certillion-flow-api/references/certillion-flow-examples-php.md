# Certillion Flow — Exemplos (PHP 8.1+)

Documento público · Versão do kit: 0.7.1-beta. Extensão cURL habilitada. Salvar como flow_php.php.

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

```php
<?php
final class FlowError extends RuntimeException {
    public function __construct(public int $http, public mixed $response) {
        $status = is_array($response) ? ($response['status'] ?? null) : null;
        $code = is_array($status) ? ($status['code'] ?? 'ausente') : 'ausente';
        parent::__construct("Flow HTTP={$http}, código de aplicação={$code}");
    }
}

final class FlowClient {
    public string $base;
    public string $account;
    private ?string $token = null;
    private float $expires = 0;
    public function __construct(string $base, string $email, string $password, int $validity = 900) {
        $this->base = rtrim($base, '/');
        $this->account = hash('sha256', $this->base . "\n" . $email);
        $started = hrtime(true) / 1e9;
        $credentials = base64_encode($email . ':' . $password);
        [$http, $raw] = $this->request('GET', '/application/login?validity=' . $validity, null,
            ['credentials: Basic ' . $credentials], false);
        $data = $this->json($http, $raw);
        if (!is_string($data['access_token'] ?? null) || $data['access_token'] === '' ||
            !is_int($data['validity'] ?? null) || $data['validity'] <= 0) throw new RuntimeException('Token ou validade retornada inválidos.');
        $this->token = $data['access_token'];
        $this->expires = $started + $data['validity'];
    }
    public function close(): void { $this->token = null; } // Não revoga no servidor.
    private function request(string $method, string $path, mixed $body = null, array $headers = [], bool $auth = true, bool $binary = false): array {
        $headers[] = 'Accept: ' . ($binary ? 'application/octet-stream' : 'application/json');
        if ($auth) {
            if (!$this->token || hrtime(true) / 1e9 >= $this->expires) throw new RuntimeException('Sessão indisponível; renovar e retomar IDs.');
            $headers[] = 'access_token: Bearer ' . $this->token;
        }
        $curl = curl_init($this->base . $path);
        curl_setopt_array($curl, [CURLOPT_CUSTOMREQUEST => $method, CURLOPT_HTTPHEADER => $headers,
            CURLOPT_RETURNTRANSFER => true, CURLOPT_FOLLOWLOCATION => false, CURLOPT_TIMEOUT => 30]);
        if ($body !== null) curl_setopt($curl, CURLOPT_POSTFIELDS, $body);
        try {
            $raw = curl_exec($curl);
            if ($raw === false) throw new RuntimeException('Falha de transporte Flow; resultado de POST pode ser indeterminado.');
            return [curl_getinfo($curl, CURLINFO_HTTP_CODE), $raw];
        } finally { curl_close($curl); }
    }
    private function json(int $http, string $raw): array {
        try { $data = json_decode($raw, true, 512, JSON_THROW_ON_ERROR); }
        catch (JsonException $error) { throw new FlowError($http, ['body' => $raw]); }
        if ($http < 200 || $http >= 300 || !is_array($data) || !is_array($data['status'] ?? null) || ($data['status']['code'] ?? null) !== 100)
            throw new FlowError($http, $data);
        return $data;
    }
    private function call(string $method, string $path, ?array $body = null): array {
        return $this->json(...$this->request($method, $path, $body === null ? null : json_encode($body, JSON_THROW_ON_ERROR),
            $body === null ? [] : ['Content-Type: application/json']));
    }
    public function upload(string $pdfPath): string {
        $data = $this->json(...$this->request('POST', '/application/upload', ['file' => new CURLFile($pdfPath, 'application/pdf', 'documento.pdf')]));
        if (!is_string($data['document_id'] ?? null) || $data['document_id'] === '') throw new RuntimeException('Upload sem document_id válido.');
        return $data['document_id'];
    }
    public function createProcess(array $body): string {
        $data = $this->call('POST', '/application/signature-request', $body);
        if (!is_string($data['process_id'] ?? null) || $data['process_id'] === '') throw new RuntimeException('Criação sem process_id; reconciliar.');
        return $data['process_id'];
    }
    public function models(): array { return $this->call('GET', '/application/models')['signature_model_list']; }
    public function registerModel(array $body): array { return $this->call('POST', '/application/register-signature-model', $body)['signature_model']; }
    public function process(string $id): ?array {
        $data = $this->call('GET', '/application/process?' . http_build_query(['id' => $id]));
        if (!array_key_exists('process_list', $data) || ($data['process_list'] !== null && !is_array($data['process_list'])))
            throw new RuntimeException('process_list ausente ou inválida.');
        foreach ($data['process_list'] ?? [] as $p) if (($p['id'] ?? null) === $id) return $p;
        return null;
    }
    public function download(string $id): ?string {
        [$http, $bytes] = $this->request('GET', '/application/download/' . rawurlencode($id), null, [], true, true);
        if ($http === 403) return null;
        if ($http !== 200) throw new FlowError($http, []);
        if (substr($bytes, 0, 4) !== "PK\x03\x04") throw new RuntimeException('Resposta não parece ZIP.');
        return $bytes; // Conferir CRC/inventário com biblioteca ZIP do projeto.
    }
}

function bindFlowState(FlowClient $client, array &$state, callable $save): void {
    if ($state && ($state['account_key'] ?? null) !== $client->account) throw new RuntimeException('Estado de outra conta/servidor.');
    $state['account_key'] = $client->account;
    $save($state);
}
function createOnce(FlowClient $client, string $pdfPath, array $signer, string $callback, array &$state, callable $save): string {
    bindFlowState($client, $state, $save);
    if (!empty($state['process_id'])) return $state['process_id'];
    if (parse_url($callback, PHP_URL_SCHEME) !== 'https' || !parse_url($callback, PHP_URL_HOST)) throw new RuntimeException('Callback deve ser HTTPS público controlado.');
    if (empty($state['document_id'])) {
        if (!empty($state['upload_attempted'])) throw new RuntimeException('Upload anterior sem resultado conciliado.');
        $state['upload_attempted'] = true; $save($state);
        $state['document_id'] = $client->upload($pdfPath); $save($state);
    }
    if (!empty($state['create_attempted'])) throw new RuntimeException('Criação anterior sem resultado conciliado.');
    $state['create_attempted'] = true; $save($state);
    $state['process_id'] = $client->createProcess(['title' => 'Documento para assinatura', 'type' => 'DIGITAL_SIGNATURE',
        'documents' => [$state['document_id']], 'signers' => [$signer], 'callback_url' => $callback]);
    $save($state);
    return $state['process_id'];
}
function resume(FlowClient $client, array &$state, callable $save, callable $storeZip, int $waitSeconds = 300, int $interval = 5): bool {
    bindFlowState($client, $state, $save);
    if (empty($state['process_id'])) throw new RuntimeException('Retomada exige process_id; não cria dependências.');
    $end = hrtime(true) / 1e9 + max(0, $waitSeconds);
    while (true) {
        $process = $client->process($state['process_id']);
        if ($process !== null) {
            $state['process_status'] = $process['status'] ?? null; $save($state);
            if (($process['status'] ?? null) === 'FINALIZED_WITH_SUCCESS') {
                $blob = $client->download($state['process_id']);
                if ($blob !== null) {
                    $storeZip($blob);
                    $state['download_saved'] = true; $save($state);
                    return true;
                }
            }
        }
        $remaining = $end - hrtime(true) / 1e9;
        if ($remaining <= 0) return false;
        usleep((int)(min(max(1, $interval), $remaining) * 1e6));
    }
}


function integrate(array &$state, callable $save, callable $storeZip, ?string $pdfPath = null): bool {
    $required = static function(string $name): string {
        $value = getenv($name);
        if ($value === false || $value === '') throw new RuntimeException("Configuração ausente: {$name}");
        return $value;
    };
    $client = new FlowClient(getenv('CERTILLION_FLOW_BASE_URL') ?: 'https://flow.certillion.com/flow/restful',
        $required('CERTILLION_FLOW_EMAIL'), $required('CERTILLION_FLOW_PASSWORD'));
    try {
        if ($pdfPath !== null) createOnce($client, $pdfPath, [
            'name' => getenv('CERTILLION_FLOW_SIGNER_NAME') ?: 'Participante',
            'email' => $required('CERTILLION_FLOW_SIGNER_EMAIL')], $required('CERTILLION_FLOW_CALLBACK_URL'), $state, $save);
        return resume($client, $state, $save, $storeZip);
    } finally { $client->close(); }
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
