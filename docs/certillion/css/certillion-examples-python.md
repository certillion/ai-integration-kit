# Certillion API — Exemplos de Integração (Python)

> **Documento público** — distribuível a clientes e parceiros integradores. Não contém
> informação interna ou confidencial. Propósito: habilitar a integração com a API Certillion.
>
> Versão: 0.6-beta | Linguagem: Python 3.9+
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

Dependência: `pip install requests`

---

## Configuração e guardrail de ambiente

```python
import os

# CERTILLION_ENV — alterar para 'production' antes de ir para produção
CERTILLION_ENV = 'test'
# CERTILLION_ENV = 'production'

BASE_URL = 'https://cloud.certillion.com/css/restful/application'
CLIENT_ID = os.environ['CERTILLION_CLIENT_ID']
CLIENT_SECRET = os.environ['CERTILLION_CLIENT_SECRET']


def avisar_ambiente_teste():
    if CERTILLION_ENV == 'test':
        print(
            '⚠️  Certillion: chave de TESTE ativa. Restrições: validade 90 dias, '
            'arquivo até 100 KB, 200 assinaturas/mês. Trocar para produção antes do go-live.'
        )
```

## Geração do par PKCE

```python
import os
import hashlib
import base64


def base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip('=')


# Gerar UMA vez por fluxo de autorização
def generate_pkce():
    verifier = base64url_encode(os.urandom(32))
    challenge = base64url_encode(hashlib.sha256(verifier.encode()).digest())
    return verifier, challenge  # challenge -> /authorize ; verifier -> /token
```

## Passo 1 — Client token (autenticação do sistema)

```python
import requests


def get_client_token() -> str:
    resp = requests.post(
        f'{BASE_URL}/oauth/client_token',
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
        data={
            'client_id': CLIENT_ID,
            'client_secret': CLIENT_SECRET,
            'grant_type': 'client_credentials',
            'lifetime': '300',
        },
    )
    data = resp.json()
    if not data.get('access_token'):
        raise RuntimeError(f'client_token falhou: {data}')
    return data['access_token']
```

## Passo 3 — URL de autorização (abrir no navegador do usuário)

```python
from urllib.parse import urlencode


def build_authorize_url(challenge: str, psc: str, redirect_uri: str) -> str:
    q = urlencode({
        'response_type': 'code',
        'manager_id': CLIENT_ID,
        'code_challenge': challenge,
        'code_challenge_method': 'S256',
        'psc': psc,
        'scope': 'signature_session',
        'redirect_uri': redirect_uri,
    })
    return f'{BASE_URL}/oauth/authorize?{q}'
# O usuário autentica no PSC e o navegador volta para redirect_uri?code=...&state=...
```

## Passo 4 — Token de assinatura (troca do code)

```python
def get_signing_token(code: str, verifier: str, psc: str, redirect_uri: str):
    resp = requests.post(
        f'{BASE_URL}/oauth/token',
        params={'psc': psc},
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
        data={
            'grant_type': 'authorization_code',
            'code': code,
            'code_verifier': verifier,
            # manager_id/manager_secret: nomes de parâmetro da API (doc oficial); o valor é o seu client_id/client_secret. Não remover.
            'manager_id': CLIENT_ID,
            'manager_secret': CLIENT_SECRET,
            'redirect_uri': redirect_uri,
        },
    )
    data = resp.json()
    if not data.get('access_token'):
        raise RuntimeError(f'token falhou: {data}')
    # R6: usar expires_in como fonte de verdade, não o lifetime solicitado
    return data['access_token'], data['expires_in']
```

## Passo 2 — Upload do documento

```python
def upload_document(pdf_bytes: bytes, token: str) -> str:
    resp = requests.post(
        f'{BASE_URL}/oauth/document',
        headers={'Authorization': f'Bearer {token}'},
        files={'file': ('documento.pdf', pdf_bytes, 'application/pdf')},
    )
    data = resp.json()
    if not data.get('document_hash'):
        raise RuntimeError(f'upload falhou: {data}')
    return data['document_hash']  # R2: persistir
```

## Passo 5 — Solicitar assinatura

```python
def request_signature(document_hash: str, signing_token: str) -> str:
    body = {
        'signature_standard': 'PADES',
        'signature_policy': 'AD_RB',
        'pki_name': 'ICP_BR',
        'detached': False,
        'hashes': [{'id': '1', 'alias': 'documento', 'hash': document_hash}],
    }
    resp = requests.post(
        f'{BASE_URL}/oauth/signature',
        headers={'Authorization': f'Bearer {signing_token}',
                 'Content-Type': 'application/json'},
        json=body,
    )
    data = resp.json()
    sig = (data.get('signatures') or [{}])[0]
    # R4: verificar status 140 (SIGNATURE_VALID) por entrada
    if sig.get('status', {}).get('code') != 140:
        raise RuntimeError(f'assinatura inválida: {sig.get("status")}')
    return str(sig['transaction'])  # API: transaction inteiro; variável interna em string
```

## Passo 6 — Download do documento assinado

```python
def download_document(transaction_id: str, token: str) -> bytes:
    resp = requests.get(
        f'{BASE_URL}/oauth/document/{transaction_id}',
        headers={'Authorization': f'Bearer {token}', 'Accept': 'application/octet-stream'},
    )
    if not resp.ok:
        raise RuntimeError(f'download falhou: HTTP {resp.status_code}')
    return resp.content
```

## Orquestração com estado persistido (R1, R2)

Carregar o estado salvo para o mesmo documento, conta e servidor. `save` deve gravar
em armazenamento durável antes de retornar; não recriar um estado vazio para repetir
uma execução. O marcador de intenção permanece se o resultado do POST for incerto.
Só liberá-lo após reconciliar ou confirmar que a requisição foi rejeitada. Nenhuma
retentativa de assinatura é automática. Os tokens não pertencem ao estado abaixo.

```python
def sign_document(pdf_bytes, signing_token, state, save):
    avisar_ambiente_teste()
    client_token = get_client_token()
    if not state.get('transaction_id'):
        if not state.get('document_hash'):
            if state.get('upload_attempted'):
                raise RuntimeError('Upload anterior sem resultado conciliado.')
            state['upload_attempted'] = True
            save(dict(state))
            state['document_hash'] = upload_document(pdf_bytes, client_token)
            save(dict(state))
        if state.get('signature_attempted'):
            raise RuntimeError('Assinatura anterior sem resultado conciliado.')
        state['signature_attempted'] = True
        save(dict(state))
        state['transaction_id'] = request_signature(state['document_hash'], signing_token)
        save(dict(state))
    return download_document(state['transaction_id'], client_token)
```

---

*Os nomes de campo e valores de enum seguem `certillion-openapi.yaml` (fonte canônica). Em caso de divergência, o YAML prevalece.*
