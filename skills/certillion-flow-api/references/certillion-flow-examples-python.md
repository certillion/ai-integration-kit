# Certillion Flow — Exemplos (Python 3.9+)

Documento público · Versão do kit: 0.7-beta. Biblioteca padrão, sem dependências externas.

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

```python
import base64
import hashlib
import io
import json
import os
import secrets
import time
import zipfile
from urllib.error import HTTPError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class FlowError(RuntimeError):
    def __init__(self, http, data):
        self.http, self.response = http, data  # Redigir antes de registrar/exibir.
        status = data.get('status') if isinstance(data, dict) else None
        code = status.get('code') if isinstance(status, dict) else None
        super().__init__(f'Flow HTTP={http}, código de aplicação={code}')


class FlowClient:
    def __init__(self, base_url, email, password, validity=900):
        self.base = base_url.rstrip('/')
        self.account = hashlib.sha256((self.base + '\n' + email).encode()).hexdigest()
        self.token, self.expires = None, 0
        self.http = build_opener(NoRedirect())
        started = time.monotonic()
        credentials = base64.b64encode((email + ':' + password).encode()).decode()
        status, content = self._request('GET', '/application/login?' + urlencode({'validity': validity}),
                                        headers={'credentials': 'Basic ' + credentials}, auth=False)
        data = self._json(status, content)
        if not isinstance(data.get('access_token'), str) or not data['access_token']:
            raise ValueError('Login sem token válido.')
        duration = data.get('validity')
        if not isinstance(duration, int) or isinstance(duration, bool) or duration <= 0:
            raise ValueError('Validade retornada não é inteiro positivo.')
        self.token, self.expires = data['access_token'], started + duration

    def close(self):
        self.token = None  # Limpeza local; não é logout remoto.

    def _request(self, method, path, body=None, headers=None, auth=True, binary=False):
        h = {'Accept': 'application/octet-stream' if binary else 'application/json', **(headers or {})}
        if auth:
            if not self.token or time.monotonic() >= self.expires:
                raise RuntimeError('Sessão indisponível; renovar de forma controlada e retomar os IDs.')
            h['access_token'] = 'Bearer ' + self.token
        try:
            response = self.http.open(Request(self.base + path, data=body, headers=h, method=method), timeout=30)
        except HTTPError as error:
            response = error
        with response:
            return response.code, response.read()

    @staticmethod
    def _json(status, content):
        try:
            data = json.loads(content)
        except (ValueError, UnicodeDecodeError):
            raise FlowError(status, {'body': content.decode(errors='replace')}) from None
        if not 200 <= status < 300 or not isinstance(data, dict) or not isinstance(data.get('status'), dict) or data['status'].get('code') != 100:
            raise FlowError(status, data)
        return data

    def call(self, method, path, body=None):
        payload = json.dumps(body).encode() if body is not None else None
        h = {'Content-Type': 'application/json'} if body is not None else {}
        return self._json(*self._request(method, path, payload, h))

    def upload(self, pdf):
        boundary = 'flow-' + secrets.token_hex(16)
        body = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="documento.pdf"\r\n'
                'Content-Type: application/pdf\r\n\r\n').encode() + pdf + f'\r\n--{boundary}--\r\n'.encode()
        data = self._json(*self._request('POST', '/application/upload', body,
                                         {'Content-Type': 'multipart/form-data; boundary=' + boundary}))
        if not isinstance(data.get('document_id'), str) or not data['document_id']:
            raise ValueError('Upload sem document_id válido.')
        return data['document_id']

    def create_process(self, body):
        data = self.call('POST', '/application/signature-request', body)
        if not isinstance(data.get('process_id'), str) or not data['process_id']:
            raise ValueError('Criação sem process_id válido; reconciliar antes de repetir.')
        return data['process_id']

    def models(self):
        return self.call('GET', '/application/models')['signature_model_list']

    def register_model(self, body):
        return self.call('POST', '/application/register-signature-model', body)['signature_model']

    def process(self, process_id):
        data = self.call('GET', '/application/process?' + urlencode({'id': process_id}))
        if 'process_list' not in data or (data['process_list'] is not None and not isinstance(data['process_list'], list)):
            raise ValueError('process_list ausente ou inválida.')
        return next((p for p in (data['process_list'] or []) if p.get('id') == process_id), None)

    def download(self, process_id):
        status, content = self._request('GET', '/application/download/' + quote(process_id, safe=''), binary=True)
        if status == 403:
            return None
        if status != 200:
            raise FlowError(status, {'bytes': len(content)})
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            if not archive.infolist() or archive.testzip() is not None:
                raise ValueError('ZIP vazio ou corrompido.')
        return content


def bind_state(client, state, save):
    if state and state.get('account_key') != client.account:
        raise ValueError('Estado de outra conta/servidor ou sem identificação.')
    state['account_key'] = client.account
    save(dict(state))


def create_once(client, pdf, signer, callback_url, state, save):
    bind_state(client, state, save)
    if state.get('process_id'):
        return state['process_id']
    callback = urlsplit(callback_url)
    if callback.scheme != 'https' or not callback.netloc:
        raise ValueError('Callback deve ser HTTPS público controlado.')
    if not state.get('document_id'):
        if state.get('upload_attempted'):
            raise RuntimeError('Upload anterior sem resultado conciliado.')
        state['upload_attempted'] = True
        save(dict(state))
        state['document_id'] = client.upload(pdf)
        save(dict(state))
    if state.get('create_attempted'):
        raise RuntimeError('Criação anterior sem resultado conciliado.')
    state['create_attempted'] = True
    save(dict(state))
    state['process_id'] = client.create_process({'title': 'Documento para assinatura', 'type': 'DIGITAL_SIGNATURE',
        'documents': [state['document_id']], 'signers': [signer], 'callback_url': callback_url})
    save(dict(state))
    return state['process_id']


def resume(client, state, save, store_zip, wait_seconds=300, interval=5):
    bind_state(client, state, save)
    process_id = state.get('process_id')
    if not process_id:
        raise ValueError('Retomada exige process_id; não cria dependências.')
    end = time.monotonic() + max(0, wait_seconds)
    while True:
        process = client.process(process_id)
        if process:
            state['process_status'] = process.get('status')
            save(dict(state))
            if process.get('status') == 'FINALIZED_WITH_SUCCESS':
                blob = client.download(process_id)
                if blob is not None:
                    store_zip(blob)  # Gravar bytes antes de marcar persistência do artefato.
                    state['download_saved'] = True
                    save(dict(state))
                    return True
        if time.monotonic() >= end:
            return False  # A espera terminou; o processo continua disponível para retomar.
        time.sleep(min(max(1, interval), max(0, end - time.monotonic())))


def integrate(state, save, store_zip, pdf_bytes=None):
    client = FlowClient(os.environ.get('CERTILLION_FLOW_BASE_URL', 'https://flow.certillion.com/flow/restful'),
                        os.environ['CERTILLION_FLOW_EMAIL'], os.environ['CERTILLION_FLOW_PASSWORD'])
    try:
        if pdf_bytes is not None:  # Somente para solicitação de negócio deliberadamente nova.
            signer = {'name': os.environ.get('CERTILLION_FLOW_SIGNER_NAME', 'Participante'),
                      'email': os.environ['CERTILLION_FLOW_SIGNER_EMAIL']}
            create_once(client, pdf_bytes, signer, os.environ['CERTILLION_FLOW_CALLBACK_URL'], state, save)
        return resume(client, state, save, store_zip)
    finally:
        client.close()
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
