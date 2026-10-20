# Certillion — Kit de Integração para IA

Documentação e regras para assistentes de IA integrarem os módulos Certillion:
**CSS — Certillion Signature Server**, para operações de assinatura digital ICP-Brasil,
e **Flow**, para processos com PDFs, signatários, acompanhamento e download.
Os arquivos são neutros e podem ser usados nos diferentes assistentes de desenvolvimento.

> Versão: 0.6-beta · Documentação pública.

## Para que serve

Em vez de a IA adivinhar parâmetros e cometer erros comuns de integração (cobrança dupla por
encapsular passos, mensagens de erro genéricas, tamanho de arquivo mal gerenciado), você adiciona
estes arquivos ao contexto do seu assistente e ele passa a conhecer a API como um desenvolvedor
experiente nela.

## Escolher o módulo e os arquivos

Começar pelo [guia de seleção CSS/Flow](docs/certillion/certillion-module-selection.md).
Cada módulo tem skill e contrato próprios. Carregar os documentos complementares
conforme a tarefa; não é necessário incluir todos os exemplos no contexto.

| Papel | CSS | Flow |
|---|---|---|
| Regras de integração | [Skill CSS](docs/certillion/css/certillion-skill.md) | [Skill Flow](docs/certillion/flow/certillion-flow-skill.md) |
| Conceitos e decisões | [Referência CSS](docs/certillion/css/certillion-api-reference.md) | [Referência Flow](docs/certillion/flow/certillion-flow-api-reference.md) |
| Contrato canônico dos endpoints | [OpenAPI CSS](docs/certillion/css/certillion-openapi.yaml) | [OpenAPI Flow](docs/certillion/flow/certillion-flow-openapi.yaml) |
| Recuperação e acompanhamento | Skill e referência CSS | [Fluxos Flow](docs/certillion/flow/certillion-flow-integration-flows.md) |
| Diagnóstico | [Troubleshooting CSS](docs/certillion/css/certillion-troubleshooting.md) | [Troubleshooting Flow](docs/certillion/flow/certillion-flow-troubleshooting.md) |
| Exemplos | `docs/certillion/css/certillion-examples-<linguagem>.md` | `docs/certillion/flow/certillion-flow-examples-<linguagem>.md` |

Ambos incluem exemplos em Node.js, Python, PHP, Java e Ruby. Para campos, tipos,
enums e respostas, o OpenAPI do **respectivo módulo** é a fonte canônica deste kit.
A skill define as decisões de integração; referências e exemplos complementam o contrato.

O Flow inclui login, upload PDF, criação/consulta de processos, modelos visuais,
callback e download ZIP. Conclusão operacional não implica validação criptográfica.
Para modalidades visíveis, consultar as orientações de diagnóstico e conferir a
apresentação do artefato; não tratar erro HTTP500 como autorização para recriar pedidos.

## Migração dos caminhos CSS

A documentação anterior deste kit tratava do módulo **CSS — Certillion Signature Server**.
Os arquivos canônicos estão em `docs/certillion/css/`; atualize os caminhos no
`AGENTS.md`, nas regras do assistente e nas importações do OpenAPI.
Os nomes dos arquivos e o nome da skill `certillion-api` foram preservados.

Os arquivos dos caminhos anteriores foram removidos, incluindo a cópia antiga
do OpenAPI. Use diretamente `docs/certillion/css/` tanto nas instruções para o
assistente quanto nas importações do schema; atualize também links para seções
dos documentos. Cada artefato CSS existe somente nesse diretório.

O conjunto Flow fica exclusivamente em `docs/certillion/flow/`; seus campos, tokens
e IDs não são aliases dos usados pelo CSS.

## Como instalar no seu assistente

> Mecanismos de configuração verificados em junho/2026. Os harnesses evoluem rápido; se algum
> caminho não funcionar, confirme na documentação oficial da ferramenta. O princípio — adicionar
> os arquivos ao contexto/regras do projeto — permanece válido mesmo que o local exato mude.

### Conceito: AGENTS.md no centro

A maioria dos harnesses modernos lê nativamente um arquivo **`AGENTS.md`** na raiz do projeto —
padrão aberto adotado por Codex, Cursor, Windsurf, Copilot, Antigravity e outros. A forma mais
simples e portável de configurar:

1. Copie a pasta `docs/certillion/` para a raiz do seu projeto.
2. Crie (ou edite) um `AGENTS.md` na raiz apontando para os arquivos:

   ```markdown
   ## Integração Certillion
   Identificar o módulo com docs/certillion/certillion-module-selection.md.
   - CSS: seguir docs/certillion/css/certillion-skill.md.
     Contrato: docs/certillion/css/certillion-openapi.yaml.
   - Flow: seguir docs/certillion/flow/certillion-flow-skill.md.
     Contrato: docs/certillion/flow/certillion-flow-openapi.yaml.
   Consultar a referência, os fluxos e o exemplo da linguagem apenas quando necessários.
   ```

3. Para o Claude Code (que não lê `AGENTS.md` diretamente), referencie-o no `CLAUDE.md`
   com `@AGENTS.md`.

### Tabela rápida por harness

| Harness | Onde configurar | Lê AGENTS.md nativamente? |
|---------|-----------------|---------------------------|
| **Claude Code** | `CLAUDE.md` na raiz (importa via `@AGENTS.md`); ou pasta de Skills | Via import no `CLAUDE.md` |
| **OpenAI Codex** | `AGENTS.md` na raiz (e `~/.codex/AGENTS.md` global) | Sim |
| **Cursor** | `.cursor/rules/*.mdc` ou `AGENTS.md` na raiz | Sim |
| **Windsurf** (Devin Desktop) | `.windsurf/rules/` ou `AGENTS.md` na raiz | Sim |
| **GitHub Copilot** | `.github/copilot-instructions.md` | Sim (também lê AGENTS.md) |
| **Lovable** | GitHub sync: `AGENTS.md` na raiz; ou Project Knowledge (Settings → Knowledge) | Via GitHub sync |
| **Google Antigravity** | `AGENTS.md`, `GEMINI.md` ou `.agents/rules/`; suporta Skills em `.agents/skills/` | Sim (desde v1.20.3) |

### Notas por harness

- **Claude Code:** os documentos de skill têm frontmatter `name`/`description`.
  Para carregamento por instruções, usar a referência ao `AGENTS.md` acima.
- **Cursor:** para regra dedicada, use `.cursor/rules/certillion.mdc` com frontmatter
  (`description`, `alwaysApply`). Use `alwaysApply: true` se o projeto for dedicado à integração.
- **Windsurf:** arquivos de regra têm limite de tamanho — a regra deve **apontar** para os arquivos
  do kit, não copiá-los.
- **GitHub Copilot:** para regras por tipo de arquivo, use `.github/instructions/*.instructions.md`
  com frontmatter `applyTo`.
- **Formato nativo `SKILL.md`:** os nomes canônicos deste repositório são
  `certillion-skill.md` e `certillion-flow-skill.md`. Para empacotar como skill nativa,
  usar `SKILL.md` no diretório de destino e incluir as referências com links relativos
  resolvidos. Copiar somente o arquivo principal não torna o conjunto independente.
- **Lovable:** dois caminhos — (1) conecte o projeto ao GitHub (Settings → Connectors → GitHub,
  instale o Lovable GitHub App, sync bidirecional na branch `main`) e coloque `AGENTS.md` na raiz
  do repositório: o Lovable lê o arquivo automaticamente a cada request; (2) sem GitHub, cole o
  conteúdo da skill do módulo escolhido + as regras pertinentes da sua referência no
  **Project Knowledge** do projeto (Settings → Knowledge — limite de 10 000 caracteres; a skill
  sozinha cabe com margem para regras complementares). O Project Knowledge é enviado em todas as
  conversas — não é necessário repetir as instruções a cada sessão.

## Por onde começar

1. Copie `docs/certillion/` para o seu projeto e configure o `AGENTS.md` (acima).
2. Confirmar o módulo/ambiente e obter as credenciais adequadas à integração em
   https://certillion.com/fale-conosco-certillion/.
3. No CSS, seguir o guardrail de ambiente da skill. No Flow, configurar a conta,
   participantes controlados e callback público; não importar limites comerciais CSS.
4. Pedir ao assistente a integração do módulo escolhido. Os exemplos usam IDs
   persistidos para retomar operações sem repetir chamadas já aceitas.

## Fontes

Estes artefatos foram elaborados pela equipe Certillion com base na experiência de integração
da plataforma e **também na documentação oficial da API**, disponível em:

- Visão geral da API: https://certillion.com/certillion-api/documentacao-de-api/
- Tutoriais: https://certillion.com/certillion-api/tutoriais/
- Referência CSS: https://certillion.com/certillion-api/api-certillion-assinatura-digital-documentacao/
- Referência Flow: https://documenter.getpostman.com/view/14694000/2sA3JJAP5a

## Suporte

Dúvidas durante a integração: https://certillion.com/fale-conosco-certillion/

---

*Certillion é produto da e-Sec Tecnologia em Certificação Digital. Versão do kit: 0.6-beta.*
