---
name: certillion-flow-api
description: >
  Implementar e depurar integrações com Certillion Flow: login da conta, envio de
  PDFs, processos com signatários, modelos visuais, acompanhamento, callbacks e
  download ZIP. Aplicar a signature-request, process_id e rotas /flow/restful.
  Para OAuth/PKCE, PSCs e transações do módulo CSS, usar certillion-api.
metadata:
  version: "0.6-beta"
  language: pt-BR
  classification: público
---

# Skill — Integração com Certillion Flow

Integrar processos de assinatura de PDFs com participantes e acompanhamento
assíncrono. Um processo criado precisa da ação dos signatários antes de disponibilizar
os resultados. A autenticação da conta solicitante não assina pelos participantes.

## Referências sob demanda

Paths relativos a este arquivo:

| Necessidade | Ler |
|---|---|
| Campos, tipos, headers, enums e respostas | [OpenAPI canônico](certillion-flow-openapi.yaml) |
| Conta, modalidades, sessão, prazos e modelos | [Referência conceitual](certillion-flow-api-reference.md) |
| Dependências, callbacks, recuperação e visibilidade | [Fluxos de integração](certillion-flow-integration-flows.md) |
| Erros e diagnóstico | [Troubleshooting](certillion-flow-troubleshooting.md) |
| Código na linguagem do projeto | Exemplos [Python](certillion-flow-examples-python.md), [Node.js](certillion-flow-examples-nodejs.md), [PHP](certillion-flow-examples-php.md), [Java](certillion-flow-examples-java.md) ou [Ruby](certillion-flow-examples-ruby.md) |
| Identificar o módulo | [Seleção CSS/Flow](../certillion-module-selection.md) |

O OpenAPI é o contrato canônico de endpoints deste conjunto. Usar a referência para
conceitos e os exemplos como ponto de partida. Não preencher lacunas de contrato
com operações ou campos de outro módulo.

## Regras de integração

### F1 — Usar a conta e a autenticação Flow

Obter credenciais da conta Flow no backend. Fazer login com o header `credentials`
e usar o token no header `access_token`, incluindo o prefixo `Bearer`. A sessão é
própria do Flow; não adicionar PKCE, manager/client credentials, PSC ou URL de
ativação do app CSS ao fluxo Flow. Não inferir ambiente de desenvolvimento pela porta.

### F2 — Reutilizar a sessão e preservar o processo ao renovar

Calcular expiração pela validade efetiva retornada e reutilizar a sessão enquanto
válida. Fazer renovação controlada em expiração/erro de token; continuar a operação
pendente pelos mesmos IDs. Nunca relogar e recriar automaticamente processos como
tratamento de erro. Remover referências locais ao token ao encerrar o trabalho não
comprova revogação remota; não existe logout definido neste contrato.

### F3 — Persistir intenção e IDs entre etapas

Separar login, upload, criação, consulta e download. Salvar `document_id` por PDF e
`process_id` por solicitação em armazenamento durável, associados à conta/servidor.
Salvar intenção antes do POST e cada resultado aceito antes de avançar.

Se a conexão cair ou houver timeout/HTTP 5xx depois de enviar upload, cadastro de
modelo ou criação, o resultado pode ser indeterminado. Não repetir automaticamente
o POST. Reconciliar pelas consultas disponíveis e metadados locais; um título não
é chave de idempotência e a ausência na listagem não prova rejeição. Sem resultado
conclusivo, interromper a repetição e apresentar diagnóstico.

### F4 — Preservar cada PDF e seu vínculo

Preparar o PDF final antes do upload, inclusive QR Code/rodapé se o negócio exigir.
Cada novo processo deliberado precisa de novos uploads; um `document_id` vinculado
a outro processo não é reutilizável. Isso não autoriza reenviar documentos quando
apenas consulta ou download falharam. Não editar o arquivo assinado como correção
visual; preparar uma nova operação consciente quando necessário.

### F5 — Distinguir criação, andamento e conclusão

Aceitação de criação retorna um ID, não um documento assinado. Consultar o ID exato
e interpretar o estado retornado; filtro `SUCCESS` não é nome do estado de saída.
Só baixar automaticamente após conclusão com sucesso. Preservar estados desconhecidos,
sem tratá-los como sucesso. HTTP 403 no download pede conferência de estado e retomada
de consulta/download, sem recriação. ZIP recebido não prova validade criptográfica.

### F6 — Receber callback e reconciliar

Enviar uma URL pública controlada em `callback_url`. Em desenvolvimento local,
expor o receptor por HTTPS ou usar receptor estável acessível ao serviço. Correlacionar
eventos com IDs conhecidos e consultar o processo antes de mudar o estado local.
Processar notificações repetidas sem duplicar efeitos. Não supor autenticação,
assinatura do evento, lista completa de estados ou política de reentrega.

### F7 — Respeitar dependências ao paralelizar

Uploads de PDFs distintos e leituras independentes podem executar em paralelo com
concorrência configurável. Criar o processo somente após salvar todos os IDs usados
na solicitação. Coordenar concorrência por processo para evitar dois workers criando
a mesma operação. Nenhum limite de taxa ou tamanho de lote CSS se aplica por inferência.

### F8 — Tratar visibilidade como configuração adicional

Reutilizar modelos cadastrados e converter o ID textual retornado para o tipo
numérico requerido, validando intervalo e precisão. Associar cada par documento/
signatário com seus IDs/emails reais; se informar posição, completar os três campos.
Não prometer origem de coordenadas, aparência ou equivalência criptográfica sem
examinar o resultado. HTTP 500 em modalidade visível exige diagnóstico, não fallback
que crie outra assinatura ou altere a modalidade sem decisão do integrador.

### F9 — Preservar o diagnóstico nas camadas corretas

Tratar separadamente transporte/HTTP, `status.code/name/detail` de aplicação e
estado do processo. Erros também podem usar Problem Details. Não aceitar todo
`code=200` como sucesso: ele pode indicar erro de modelo. Mostrar mensagem útil e
detalhes redigidos por operação, sem senha, Basic, token ou conteúdo do PDF.
Valores e códigos completos estão no OpenAPI e no troubleshooting.

### F10 — Manter os limites do contrato

Conta solicitante, signatário, assinatura digital e assinatura eletrônica têm papéis
distintos. Não prometer que todo processo eletrônico usa certificado ICP-Brasil ou
que o ZIP inclui um original separado. Preços, quotas, retenção, cancelamento,
logout e política de idempotência dependem de contrato próprio; não herdar do CSS.
