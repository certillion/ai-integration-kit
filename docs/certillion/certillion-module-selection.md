# Certillion — Selecionar o módulo de integração

Documento público · Versão do kit: 0.6-beta.

| Objetivo ou sinal no código | Módulo e entrada |
|---|---|
| OAuth/PKCE, PSCs, `client_token`, `document_hash`, `/oauth/signature`, transação de assinatura | [CSS — skill `certillion-api`](css/certillion-skill.md) |
| Processo com PDFs, signatários, prazos, convites, `document_id`, `process_id`, `/application/signature-request` | [Flow — skill `certillion-flow-api`](flow/certillion-flow-skill.md) |
| Base `/css/restful/application` | [OpenAPI CSS](css/certillion-openapi.yaml) |
| Base `/flow/restful` | [OpenAPI Flow](flow/certillion-flow-openapi.yaml) |

Exemplos: “assinar PDF com certificado VIDAAS e reutilizar sessão” seleciona CSS;
“enviar contrato para participantes e acompanhar a conclusão” seleciona Flow.

Se o pedido disser somente “Certillion”, consultar as rotas/IDs e o objetivo do
projeto. Persistindo ambiguidade, esclarecer o módulo antes de escolher autenticação
e contrato. Não misturar tokens, nomes de campos, erros, preços ou limites dos módulos.
Uma integração pode utilizar ambos; cada trecho segue seu próprio contrato.
