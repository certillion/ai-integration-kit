# Certillion Flow — Exemplos (Ruby 3.1+)

Documento público · Versão do kit: 0.7.1-beta. Biblioteca padrão. Salvar como flow_ruby.rb.

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

```ruby
require 'base64'
require 'digest'
require 'json'
require 'net/http'
require 'securerandom'
require 'uri'

class FlowError < StandardError
  attr_reader :http, :response
  def initialize(http, data)
    @http, @response = http, data # Redigir antes de registrar/exibir.
    status = data.is_a?(Hash) ? data['status'] : nil
    code = status.is_a?(Hash) ? status['code'] : nil
    super("Flow HTTP=#{http}, código de aplicação=#{code || 'ausente'}")
  end
end

class FlowClient
  attr_reader :base, :account
  def initialize(base, email, password, validity = 900)
    @base = base.sub(%r{/$}, '')
    @account = Digest::SHA256.hexdigest("#{@base}\n#{email}")
    @token, @expires = nil, 0
    started = clock
    credentials = Base64.strict_encode64("#{email}:#{password}")
    data = json(request('GET', "/application/login?validity=#{validity}", nil,
                        { 'credentials' => "Basic #{credentials}" }, false))
    unless data['access_token'].is_a?(String) && !data['access_token'].empty? && data['validity'].is_a?(Integer) && data['validity'] > 0
      raise 'Token ou validade retornada inválidos.'
    end
    @token, @expires = data['access_token'], started + data['validity']
  end
  def clock = Process.clock_gettime(Process::CLOCK_MONOTONIC)
  def close = @token = nil # Não revoga sessão remota.
  def request(method, path, body = nil, headers = {}, auth = true, binary = false)
    h = { 'Accept' => binary ? 'application/octet-stream' : 'application/json' }.merge(headers)
    if auth
      raise 'Sessão indisponível; renovar e retomar IDs.' if !@token || clock >= @expires
      h['access_token'] = "Bearer #{@token}"
    end
    uri = URI(@base + path)
    http = Net::HTTP.new(uri.host, uri.port)
    http.use_ssl = uri.scheme == 'https'
    http.open_timeout = 30; http.read_timeout = 30; http.max_retries = 0
    req = Net::HTTPGenericRequest.new(method, !body.nil?, true, uri.request_uri, h)
    req.body = body unless body.nil?
    http.request(req) # Net::HTTP não segue redirects automaticamente.
  end
  def json(res)
    begin
      data = JSON.parse(res.body)
    rescue JSON::ParserError
      raise FlowError.new(res.code.to_i, { 'body' => res.body })
    end
    unless res.code.to_i.between?(200, 299) && data.is_a?(Hash) && data['status'].is_a?(Hash) && data['status']['code'] == 100
      raise FlowError.new(res.code.to_i, data)
    end
    data
  end
  def call(method, path, body = nil)
    json(request(method, path, body.nil? ? nil : JSON.generate(body), body.nil? ? {} : { 'Content-Type' => 'application/json' }))
  end
  def upload(pdf)
    boundary = 'flow-' + SecureRandom.hex(16)
    body = "--#{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"documento.pdf\"\r\nContent-Type: application/pdf\r\n\r\n".b + pdf.b + "\r\n--#{boundary}--\r\n".b
    data = json(request('POST', '/application/upload', body, { 'Content-Type' => "multipart/form-data; boundary=#{boundary}" }))
    raise 'Upload sem document_id válido.' unless data['document_id'].is_a?(String) && !data['document_id'].empty?
    data['document_id']
  end
  def create_process(body)
    data = call('POST', '/application/signature-request', body)
    raise 'Criação sem process_id; reconciliar.' unless data['process_id'].is_a?(String) && !data['process_id'].empty?
    data['process_id']
  end
  def models = call('GET', '/application/models')['signature_model_list']
  def register_model(body) = call('POST', '/application/register-signature-model', body)['signature_model']
  def process(id)
    data = call('GET', '/application/process?' + URI.encode_www_form('id' => id))
    unless data.key?('process_list') && (data['process_list'].nil? || data['process_list'].is_a?(Array))
      raise 'process_list ausente ou inválida.'
    end
    (data['process_list'] || []).find { |p| p['id'] == id }
  end
  def download(id)
    res = request('GET', '/application/download/' + URI.encode_www_form_component(id), nil, {}, true, true)
    return nil if res.code.to_i == 403
    raise FlowError.new(res.code.to_i, {}) unless res.code.to_i == 200
    raise 'Resposta não parece ZIP.' unless res.body.b.start_with?("PK\x03\x04".b)
    res.body.b # Conferir CRC/inventário com biblioteca ZIP do projeto.
  end
end

def bind_flow_state(client, state, save)
  raise 'Estado de outra conta/servidor.' if !state.empty? && state['account_key'] != client.account
  state['account_key'] = client.account
  save.call(state.dup)
end

def create_once(client, pdf, signer, callback, state, save)
  bind_flow_state(client, state, save)
  return state['process_id'] if state['process_id']
  uri = URI(callback)
  raise 'Callback deve ser HTTPS público controlado.' unless uri.scheme == 'https' && uri.host
  unless state['document_id']
    raise 'Upload anterior sem resultado conciliado.' if state['upload_attempted']
    state['upload_attempted'] = true; save.call(state.dup)
    state['document_id'] = client.upload(pdf); save.call(state.dup)
  end
  raise 'Criação anterior sem resultado conciliado.' if state['create_attempted']
  state['create_attempted'] = true; save.call(state.dup)
  state['process_id'] = client.create_process('title' => 'Documento para assinatura', 'type' => 'DIGITAL_SIGNATURE',
    'documents' => [state['document_id']], 'signers' => [signer], 'callback_url' => callback)
  save.call(state.dup)
  state['process_id']
end

def resume(client, state, save, store_zip, wait_seconds = 300, interval = 5)
  bind_flow_state(client, state, save)
  raise 'Retomada exige process_id; não cria dependências.' unless state['process_id']
  deadline = client.clock + [0, wait_seconds].max
  loop do
    process = client.process(state['process_id'])
    if process
      state['process_status'] = process['status']; save.call(state.dup)
      if process['status'] == 'FINALIZED_WITH_SUCCESS'
        blob = client.download(state['process_id'])
        unless blob.nil?
          store_zip.call(blob)
          state['download_saved'] = true; save.call(state.dup)
          return true
        end
      end
    end
    remaining = deadline - client.clock
    return false if remaining <= 0
    sleep [[1, interval].max, remaining].min
  end
end


def integrate(state, save, store_zip, pdf = nil)
  client = FlowClient.new(ENV.fetch('CERTILLION_FLOW_BASE_URL', 'https://flow.certillion.com/flow/restful'),
                         ENV.fetch('CERTILLION_FLOW_EMAIL'), ENV.fetch('CERTILLION_FLOW_PASSWORD'))
  begin
    unless pdf.nil?
      create_once(client, pdf, { 'name' => ENV.fetch('CERTILLION_FLOW_SIGNER_NAME', 'Participante'),
                                'email' => ENV.fetch('CERTILLION_FLOW_SIGNER_EMAIL') },
                  ENV.fetch('CERTILLION_FLOW_CALLBACK_URL'), state, save)
    end
    resume(client, state, save, store_zip)
  ensure
    client.close
  end
end
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
