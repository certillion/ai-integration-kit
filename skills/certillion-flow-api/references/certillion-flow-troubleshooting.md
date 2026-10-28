# Certillion Flow — Diagnóstico e suporte

Documento público · Versão do kit: 0.7-beta. Campos/códigos completos no
[OpenAPI](certillion-flow-openapi.yaml); recuperação nos [fluxos](certillion-flow-integration-flows.md).

## Triagem por operação

| Sintoma | Conferir | Recuperação |
|---|---|---|
| Login recusado, código de aplicação 300 | Conta habilitada para email/senha e header `credentials` Basic | Corrigir credenciais/configuração; não tentar credenciais CSS |
| “Missing request header access_token” ou HTTP401/código700 | Nome do header e prefixo Bearer | Usar o header Flow correto; não alternar formatos automaticamente |
| Código701/token expirado | Validade retornada, relógio e sessão em uso | Autenticar de forma controlada e continuar pelos IDs existentes |
| Upload HTTP400/código400 | PDF corrompido | Corrigir o arquivo antes de novo envio |
| Upload HTTP400/código401 | Arquivo não PDF | Converter/preparar PDF válido; código401 aqui é da aplicação, não HTTP401 |
| Modelo HTTP400/código200 | Nome do modelo vazio | Corrigir nome; código200 não é sucesso nessa operação |
| Modelo código201 | Nome duplicado | Listar modelos e reconciliar; não cadastrar outro em loop |
| Criação código504 | Campos obrigatórios, incluindo callback_url | Completar o corpo e usar receptor público controlado |
| Criação código519/INVALID_DOCUMENT | Documento já vinculado a outro processo | Para outro processo deliberado, fazer novo upload; para recuperar o existente, usar process_id |
| Consulta código601 | Enum do período | Usar o enum completo do OpenAPI, sem aliases numéricos |
| Consulta vazia/null | Filtros, período e ID consultado | Normalizar null na iteração; não assumir que uma criação não aconteceu |
| Processo não muda de estado | Participação dos signatários e prazo | Acompanhar sem recriar; não prometer entrega de convite só por HTTP200 |
| Download HTTP403 | Processo em andamento ou sem conclusão bem-sucedida | Consultar estado; repetir apenas leitura/download |
| Download HTTP400/404 | Formato/existência do process_id e conta | Conferir ID do processo, não document_id ou transação CSS |
| Modalidade visível HTTP500, “Visual signer definition not found” | Associação de documentos/signatários/modelo, payload e diagnóstico do servidor | Preservar estado indeterminado; não reenviar automaticamente nem alterar modalidade |
| Resposta sem status.code | Problem Details, proxy ou erro de transporte | Registrar HTTP e campos disponíveis redigidos; não interpretar como sucesso |

## Perguntas recorrentes

**Preciso manter alguém para assinar?** O processo depende da participação dos
signatários configurados. A autenticação da conta API não substitui essa ação.

**Por que o processo não retornou um PDF imediatamente?** A criação inicia um
processo assíncrono; o resultado é baixado em ZIP depois da conclusão.

**Posso usar o mesmo arquivo em outro processo?** O conteúdo pode ser o mesmo,
mas o novo processo precisa de novo upload. Não reutilizar document_id já vinculado.

**Posso usar Authorization Bearer como no CSS?** O header protegido do Flow chama-se
`access_token` e seu valor inclui `Bearer`. Consultar o schema do módulo.

**O lembrete igual ao prazo deve ser rejeitado?** Não depender dessa validação de
limite; preferir lembrete anterior ao prazo. Um sucesso de criação não prova envio
e horário do lembrete.

**Como faço logout?** Não há operação documentada neste contrato. Remover o token
local não comprova revogação no servidor; a sessão pode continuar válida até expirar.

**Recebi callback; posso considerar a assinatura válida?** Correlacionar o processo
e consultar seu estado. Conclusão operacional, integridade do ZIP, apresentação
visual e validade criptográfica são verificações diferentes.

## Evidências úteis para suporte

Guardar internamente horário com fuso, operação, host, HTTP, códigos/nome do erro,
ID local da solicitação e IDs de documentos/processo/modelo. Preservar o estado
conhecido antes/depois da falha e se houve resposta conclusiva do POST. Mostrar
ao operador detalhes redigidos para que possa diagnosticar a etapa exata.

Não expor senha, header Basic, token, emails pessoais, conteúdo de PDFs ou dados
sensíveis em logs externos/tickets. `detail` pode conter dados pessoais; redigir
antes de exibir/copiar. Não mascarar o nome/código do erro a ponto de perder a causa.
