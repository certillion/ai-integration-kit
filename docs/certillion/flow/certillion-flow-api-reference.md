# Certillion Flow — Referência de integração

Documento público · Versão do kit: 0.6-beta.

Consultar conforme a tarefa: [conta e sessão](#conta-e-sessão), [documentos e participantes](#documentos-e-participantes),
[modalidades](#modalidades), [modelos visuais](#modelos-visuais), [prazos](#prazos-e-lembretes)
e [recuperação](certillion-flow-integration-flows.md). Campos e respostas completos
ficam no [OpenAPI](certillion-flow-openapi.yaml).

## Conta e sessão

Flow organiza um processo de assinatura com PDFs, signatários e acompanhamento.
A conta que chama a API é a solicitante. O participante recebe um convite e precisa
concluir sua parte; login API não substitui essa ação. A conta deve estar configurada
para email/senha. Uma conta criada apenas por login social pode precisar de configuração
própria antes de utilizar a API.

O token de acesso atende várias operações da mesma conta. Usar a validade retornada
para expiração e manter uma margem operacional. Quando a sessão expirar, autenticar
novamente de forma controlada e retomar IDs existentes. As credenciais e o token
ficam no backend; não enviá-los ao navegador ou incluir em logs.

A base do contrato é HTTPS no host Flow. Para outro ambiente, obter endereço e
credenciais oficiais. Mudar uma flag local não transforma uma conta em conta de
homologação, e a porta não identifica por si só o ambiente.

## Documentos e participantes

O arquivo enviado precisa ser PDF. Upload devolve um identificador de documento,
não hash CSS nem assinatura. Persistir o ID por arquivo e vincular os documentos
à solicitação de negócio antes de criar o processo.

A criação associa PDFs e signatários, pode enviar convites e devolve um identificador
de processo. Cada participante tem nome/email próprios; não confundir email de login
com email de signatário. Para vários signatários, preservar a configuração explícita
e confirmar com o produto a ordem efetiva desejada. A ordem do array e os prazos
individuais, por si sós, não definem todo o algoritmo de assinatura.

Interessados (`stakeholders`) são partes informadas no processo, distintas dos
signatários. Não atribuir assinatura a uma parte apenas por constar nessa lista.
A entrega de emails e o comportamento de campos adicionais dependem do fluxo configurado.

Um ID de documento já consumido por processo não pode ser usado para criar outro.
Novo processo intencional requer novo upload. Retomar um processo existente usa
seu ID; não consome novos documentos nem gera novos convites de criação.

## Modalidades

| Modalidade | Uso |
|---|---|
| Digital | Processo de assinatura digital conforme configuração do participante e serviço |
| Eletrônica | Processo de assinatura eletrônica; não presumir uso de certificado ICP-Brasil |
| Variante visível de cada modalidade | Acrescenta modelo e detalhes de apresentação no PDF |

Os nomes exatos de modalidade estão no schema. Visibilidade é apresentação: não
substitui validação da assinatura nem permite concluir sua validade jurídica ou
criptográfica. Não mudar a modalidade para contornar erro sem decisão de negócio.

## Modelos visuais

Modelo define texto, dimensões, fonte/alinhamento e opções de imagem. Listar modelos
antes de cadastrar outro para evitar duplicação de nomes. O cadastro devolve modelo
aninhado e ID textual; o campo usado na solicitação visual é numérico. Validar a
conversão sem perda de precisão, especialmente em JavaScript/int64.

Texto e posicionamento são conceitos diferentes. Para um processo visual, informar
um detalhe por par documento/signatário. Os emails devem corresponder a `signers`,
e os IDs, aos documentos da própria solicitação. Se escolher posicionamento manual,
fornecer página e as duas coordenadas juntas. Não assumir origem das coordenadas
com base nas regras CSS; conferir página, rotação e resultado visual.

Um HTTP 500 com mensagem de definição visual não encontrada pode ocorrer mesmo
com estrutura aparentemente consistente. Preservar IDs/modelo e a requisição
redigida para diagnóstico. Como a resposta pode ser indeterminada, não cadastrar
modelos nem recriar processos automaticamente como tentativa de correção.

## Prazos e lembretes

Pode haver prazo geral ou prazos individuais. Não combinar as duas formas. Evitar
prazos individuais parcialmente preenchidos e configurações incompatíveis com a
ordem desejada. Limites e enum de lembretes estão no OpenAPI.

Como regra de configuração do integrador, preferir lembrete estritamente anterior
ao prazo aplicável. A rejeição de lembrete igual ao prazo não é uniforme; não depender
desse limite como mecanismo de controle. Receber sucesso de criação não comprova
que o lembrete foi enviado no momento esperado.

## Acompanhamento e resultado

Persistir o estado retornado pela consulta. A API usa vocabulário distinto para
filtros e estados de saída: não transformar `SUCCESS` de filtro em regra para
interpretar a resposta. Lista sem resultados pode vir `null`. A consulta por ID
precisa ser correlacionada ao ID exato; não escolher simplesmente o primeiro item.

Notificação de callback é um sinal para reconciliar o processo conhecido. Pode
haver consultas/eventos repetidos; persistir transições sem repetir efeitos de
negócio. O contrato do evento não define aqui autenticação ou política de entrega.

Depois da conclusão com sucesso, o download devolve ZIP. Guardar os bytes, conferir
a integridade e examinar os membros conforme o negócio; não interpretar o retorno
como JSON ou PDF único. Não pressupor cópia original separada em todo ZIP eletrônico.
Se o aplicativo extrair arquivos, controlar paths, tamanho expandido e quantidade
de membros conforme sua política. Verificação do ZIP e validade criptográfica dos
PDFs são etapas diferentes.

## Contratos adicionais

Não há endpoint de logout, cancelamento ou exclusão de processo neste conjunto.
A existência de estados cancelado/expirado em filtros não define operações para
provocá-los. Encerrar uso local do token não garante encerramento da sessão remota.
Limites de volume, preços, retenção e autenticação de callbacks devem ser acordados
para a integração específica.
