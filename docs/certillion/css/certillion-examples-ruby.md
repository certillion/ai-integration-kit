# Certillion API — Exemplos de Integração (Ruby)

> **Documento público** — distribuível a clientes e parceiros integradores. Não contém
> informação interna ou confidencial. Propósito: habilitar a integração com a API Certillion.
>
> Versão: 0.5-beta | Linguagem: Ruby 3.0+
> Referenciado por `certillion-skill.md` e `certillion-api-reference.md`.
> A mecânica completa de cada endpoint (parâmetros, tipos, erros) está em `certillion-openapi.yaml`.

Este arquivo demonstra o **fluxo essencial** de assinatura: geração do par PKCE, os 6 passos
e a orquestração com retentativa por passo. As regras de implementação (R1–R16) estão na skill.

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

Usa a biblioteca padrão `net/http`. Para multipart, os exemplos usam `Net::HTTP::Post::Multipart`
(gem `multipart-post`) ou a montagem manual mostrada no passo 2.

---

## Configuração e guardrail de ambiente

```ruby
# CERTILLION_ENV — alterar para 'production' antes de ir para produção
CERTILLION_ENV = 'test'
# CERTILLION_ENV = 'production'

BASE_URL      = 'https://cloud.certillion.com/css/restful/application'
CLIENT_ID     = ENV.fetch('CERTILLION_CLIENT_ID')
CLIENT_SECRET = ENV.fetch('CERTILLION_CLIENT_SECRET')

def avisar_ambiente_teste
  if CERTILLION_ENV == 'test'
    warn '⚠️  Certillion: chave de TESTE ativa. Restrições: validade 90 dias, ' \
         'arquivo até 100 KB, 200 assinaturas/mês. Trocar para produção antes do go-live.'
  end
end
```

## Geração do par PKCE

```ruby
require 'securerandom'
require 'digest'
require 'base64'

def base64_url_encode(data)
  Base64.urlsafe_encode64(data).delete('=')
end

# Gerar UMA vez por fluxo de autorização
def generate_pkce
  verifier  = base64_url_encode(SecureRandom.random_bytes(32))
  challenge = base64_url_encode(Digest::SHA256.digest(verifier))
  [verifier, challenge] # challenge -> /authorize ; verifier -> /token
end
```

## Passo 1 — Client token (autenticação do sistema)

```ruby
require 'net/http'
require 'uri'
require 'json'

def get_client_token
  uri = URI("#{BASE_URL}/oauth/client_token")
  res = Net::HTTP.post_form(uri, {
    'client_id' => CLIENT_ID,
    'client_secret' => CLIENT_SECRET,
    'grant_type' => 'client_credentials',
    'lifetime' => '300'
  })
  data = JSON.parse(res.body)
  raise "client_token falhou: #{data}" unless data['access_token']
  data['access_token']
end
```

## Passo 3 — URL de autorização (abrir no navegador do usuário)

```ruby
def build_authorize_url(challenge, psc, redirect_uri)
  params = URI.encode_www_form(
    'response_type' => 'code',
    'manager_id' => CLIENT_ID,
    'code_challenge' => challenge,
    'code_challenge_method' => 'S256',
    'psc' => psc,
    'scope' => 'signature_session',
    'redirect_uri' => redirect_uri
  )
  "#{BASE_URL}/oauth/authorize?#{params}"
end
# O usuário autentica no PSC e o navegador volta para redirect_uri?code=...&state=...
```

## Passo 4 — Token de assinatura (troca do code)

```ruby
def get_signing_token(code, verifier, psc, redirect_uri)
  uri = URI("#{BASE_URL}/oauth/token?#{URI.encode_www_form(psc: psc)}")
  res = Net::HTTP.post_form(uri, {
    'grant_type' => 'authorization_code',
    'code' => code,
    'code_verifier' => verifier,
    # manager_id/manager_secret: nomes de parâmetro da API (doc oficial); o valor é o seu client_id/client_secret. Não remover.
    'manager_id' => CLIENT_ID,
    'manager_secret' => CLIENT_SECRET,
    'redirect_uri' => redirect_uri
  })
  data = JSON.parse(res.body)
  raise "token falhou: #{data}" unless data['access_token']
  # R6: usar expires_in como fonte de verdade, não o lifetime solicitado
  [data['access_token'], data['expires_in']]
end
```

## Passo 2 — Upload do documento

```ruby
def upload_document(pdf_path, token)
  uri = URI("#{BASE_URL}/oauth/document")
  boundary = "----CertillionBoundary#{SecureRandom.hex(8)}"
  file = File.binread(pdf_path)

  body = +""
  body << "--#{boundary}\r\n"
  body << "Content-Disposition: form-data; name=\"file\"; filename=\"documento.pdf\"\r\n"
  body << "Content-Type: application/pdf\r\n\r\n"
  body << file
  body << "\r\n--#{boundary}--\r\n"

  req = Net::HTTP::Post.new(uri)
  req['Authorization'] = "Bearer #{token}"
  req['Content-Type'] = "multipart/form-data; boundary=#{boundary}"
  req.body = body

  res = Net::HTTP.start(uri.hostname, uri.port, use_ssl: true) { |http| http.request(req) }
  data = JSON.parse(res.body)
  raise "upload falhou: #{data}" unless data['document_hash']
  data['document_hash'] # R2: persistir
end
```

## Passo 5 — Solicitar assinatura

```ruby
def request_signature(document_hash, signing_token)
  uri = URI("#{BASE_URL}/oauth/signature")
  body = {
    'signature_standard' => 'PADES',
    'signature_policy' => 'AD_RB',
    'pki_name' => 'ICP_BR',
    'detached' => false,
    'hashes' => [{ 'id' => '1', 'alias' => 'documento', 'hash' => document_hash }]
  }

  req = Net::HTTP::Post.new(uri)
  req['Authorization'] = "Bearer #{signing_token}"
  req['Content-Type'] = 'application/json'
  req.body = JSON.generate(body)

  res = Net::HTTP.start(uri.hostname, uri.port, use_ssl: true) { |http| http.request(req) }
  data = JSON.parse(res.body)
  sig = (data['signatures'] || [{}]).first
  # R4: verificar status 140 (SIGNATURE_VALID) por entrada
  unless sig.dig('status', 'code') == 140
    raise "assinatura inválida: #{sig['status']}"
  end
  sig['transaction'].to_s # API: transaction inteiro; variável interna em string
end
```

## Passo 6 — Download do documento assinado

```ruby
def download_document(transaction_id, token)
  uri = URI("#{BASE_URL}/oauth/document/#{transaction_id}")
  req = Net::HTTP::Get.new(uri)
  req['Authorization'] = "Bearer #{token}"
  req['Accept'] = 'application/octet-stream'

  res = Net::HTTP.start(uri.hostname, uri.port, use_ssl: true) { |http| http.request(req) }
  unless res.is_a?(Net::HTTPSuccess)
    raise "download falhou: HTTP #{res.code}"
  end
  res.body
end
```

## Orquestração com retentativa por passo (R1, R2)

```ruby
# ⚠️ Os IDs são persistidos entre passos — em caso de falha, retentar
# APENAS o passo que falhou, nunca reiniciar o fluxo do início.
def sign_document(pdf_path, signing_token)
  avisar_ambiente_teste

  client_token = get_client_token

  # Passo 2 — se falhar, repetir só este (novo upload)
  document_hash = upload_document(pdf_path, client_token)

  # Passo 5 — se falhar, repetir só este com o document_hash existente (NÃO re-upload)
  transaction_id = request_signature(document_hash, signing_token)

  # Passo 6 — se falhar, repetir só este com o transaction_id existente (NÃO re-assinar)
  download_document(transaction_id, client_token)
end
```

---

*Os nomes de campo e valores de enum seguem `certillion-openapi.yaml` (fonte canônica). Em caso de divergência, o YAML prevalece.*
