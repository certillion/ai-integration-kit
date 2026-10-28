# Certillion Flow — Exemplos (Node.js 20+)

Documento público · Versão do kit: 0.7.1-beta. ES modules e fetch nativo. Salvar o módulo como flow_nodejs.mjs.

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

```javascript
import { createHash, randomBytes } from 'node:crypto';

export class FlowError extends Error {
  constructor(http, data) {
    super(`Flow HTTP=${http}, código de aplicação=${data?.status?.code ?? 'ausente'}`);
    this.http = http;
    this.response = data; // Redigir antes de registrar/exibir.
  }
}

export class FlowClient {
  constructor(baseUrl, email) {
    this.base = baseUrl.replace(/\/$/, '');
    this.account = createHash('sha256').update(`${this.base}\n${email}`).digest('hex');
    this.token = null;
    this.expires = 0;
  }
  static async login(base, email, password, validity = 900) {
    const client = new FlowClient(base, email);
    const started = performance.now();
    const credentials = Buffer.from(`${email}:${password}`).toString('base64');
    const res = await client.request('GET', `/application/login?validity=${validity}`,
      null, { credentials: `Basic ${credentials}` }, false);
    const data = await client.json(res);
    if (typeof data.access_token !== 'string' || !data.access_token || !Number.isInteger(data.validity) || data.validity <= 0)
      throw new Error('Token ou validade retornada inválidos.');
    client.token = data.access_token;
    client.expires = started + data.validity * 1000;
    return client;
  }
  close() { this.token = null; } // Limpeza local, sem revogação remota.
  async request(method, path, body = null, headers = {}, auth = true, binary = false) {
    const h = { Accept: binary ? 'application/octet-stream' : 'application/json', ...headers };
    if (auth) {
      if (!this.token || performance.now() >= this.expires) throw new Error('Sessão indisponível; renovar e retomar IDs.');
      h.access_token = `Bearer ${this.token}`;
    }
    return await fetch(`${this.base}${path}`, { method, headers: h, body,
      redirect: 'error', signal: AbortSignal.timeout(30000) });
  }
  async json(res) {
    const raw = await res.text();
    let data;
    try { data = JSON.parse(raw); } catch { throw new FlowError(res.status, { body: raw }); }
    if (!res.ok || data?.status?.code !== 100) throw new FlowError(res.status, data);
    return data;
  }
  async call(method, path, body = null) {
    return await this.json(await this.request(method, path, body === null ? null : JSON.stringify(body),
      body === null ? {} : { 'Content-Type': 'application/json' }));
  }
  async upload(pdf) {
    const boundary = `flow-${randomBytes(16).toString('hex')}`;
    const body = Buffer.concat([
      Buffer.from(`--${boundary}\r\nContent-Disposition: form-data; name="file"; filename="documento.pdf"\r\nContent-Type: application/pdf\r\n\r\n`),
      pdf, Buffer.from(`\r\n--${boundary}--\r\n`)]);
    const data = await this.json(await this.request('POST', '/application/upload', body,
      { 'Content-Type': `multipart/form-data; boundary=${boundary}` }));
    if (typeof data.document_id !== 'string' || !data.document_id) throw new Error('Upload sem document_id válido.');
    return data.document_id;
  }
  async createProcess(body) {
    const data = await this.call('POST', '/application/signature-request', body);
    if (typeof data.process_id !== 'string' || !data.process_id) throw new Error('Criação sem process_id; reconciliar.');
    return data.process_id;
  }
  async models() { return (await this.call('GET', '/application/models')).signature_model_list; }
  async registerModel(body) { return (await this.call('POST', '/application/register-signature-model', body)).signature_model; }
  async process(id) {
    const data = await this.call('GET', `/application/process?${new URLSearchParams({ id })}`);
    if (!Object.hasOwn(data, 'process_list') || (data.process_list !== null && !Array.isArray(data.process_list)))
      throw new Error('process_list ausente ou inválida.');
    return (data.process_list ?? []).find(p => p.id === id) ?? null;
  }
  async download(id) {
    const res = await this.request('GET', `/application/download/${encodeURIComponent(id)}`, null, {}, true, true);
    if (res.status === 403) return null;
    if (res.status !== 200) throw new FlowError(res.status, {});
    const bytes = Buffer.from(await res.arrayBuffer());
    if (!bytes.subarray(0, 4).equals(Buffer.from([80, 75, 3, 4]))) throw new Error('Resposta não parece ZIP.');
    return bytes; // Verificar CRC/inventário com a biblioteca ZIP do projeto.
  }
}

async function bindState(client, state, save) {
  if (Object.keys(state).length && state.account_key !== client.account) throw new Error('Estado de outra conta/servidor.');
  state.account_key = client.account;
  await save({ ...state });
}

export async function createOnce(client, pdf, signer, callbackUrl, state, save) {
  await bindState(client, state, save);
  if (state.process_id) return state.process_id;
  if (new URL(callbackUrl).protocol !== 'https:') throw new Error('Callback deve ser HTTPS público controlado.');
  if (!state.document_id) {
    if (state.upload_attempted) throw new Error('Upload anterior sem resultado conciliado.');
    state.upload_attempted = true;
    await save({ ...state });
    state.document_id = await client.upload(pdf);
    await save({ ...state });
  }
  if (state.create_attempted) throw new Error('Criação anterior sem resultado conciliado.');
  state.create_attempted = true;
  await save({ ...state });
  state.process_id = await client.createProcess({ title: 'Documento para assinatura', type: 'DIGITAL_SIGNATURE',
    documents: [state.document_id], signers: [signer], callback_url: callbackUrl });
  await save({ ...state });
  return state.process_id;
}

export async function resume(client, state, save, storeZip, waitSeconds = 300, interval = 5) {
  await bindState(client, state, save);
  if (!state.process_id) throw new Error('Retomada exige process_id; não cria dependências.');
  const end = performance.now() + Math.max(0, waitSeconds) * 1000;
  while (true) {
    const process = await client.process(state.process_id);
    if (process) {
      state.process_status = process.status;
      await save({ ...state });
      if (process.status === 'FINALIZED_WITH_SUCCESS') {
        const blob = await client.download(state.process_id);
        if (blob !== null) {
          await storeZip(blob);
          state.download_saved = true;
          await save({ ...state });
          return true;
        }
      }
    }
    if (performance.now() >= end) return false;
    await new Promise(resolve => setTimeout(resolve, Math.min(Math.max(1, interval) * 1000, Math.max(0, end - performance.now()))));
  }
}


export async function integrate(state, save, storeZip, pdf = null) {
  const required = name => { const value = process.env[name]; if (!value) throw new Error(`Configuração ausente: ${name}`); return value; };
  const client = await FlowClient.login(process.env.CERTILLION_FLOW_BASE_URL ?? 'https://flow.certillion.com/flow/restful',
    required('CERTILLION_FLOW_EMAIL'), required('CERTILLION_FLOW_PASSWORD'));
  try {
    if (pdf !== null) { // Somente para solicitação deliberadamente nova.
      await createOnce(client, pdf, { name: process.env.CERTILLION_FLOW_SIGNER_NAME ?? 'Participante',
        email: required('CERTILLION_FLOW_SIGNER_EMAIL') }, required('CERTILLION_FLOW_CALLBACK_URL'), state, save);
    }
    return await resume(client, state, save, storeZip);
  } finally { client.close(); }
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
