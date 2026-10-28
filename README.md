# Certillion — Kit de Integração para IA

Documentação e regras para assistentes de IA integrarem os módulos Certillion:
**CSS — Certillion Signature Server**, para operações de assinatura digital ICP-Brasil,
e **Flow**, para processos com PDFs, signatários, acompanhamento e download.
Os arquivos são neutros e podem ser usados nos diferentes assistentes de desenvolvimento.

> Versão: 0.7.1-beta · Documentação pública.

## Para que serve

Em vez de a IA adivinhar parâmetros e cometer erros comuns de integração (cobrança dupla por
encapsular passos, mensagens de erro genéricas, tamanho de arquivo mal gerenciado), você adiciona
estes arquivos ao contexto do seu assistente e ele passa a conhecer a API como um desenvolvedor
experiente nela.

## Instalação rápida

Com Node.js 18+ instalado, rode na raiz do seu projeto:

```bash
npx skills add certillion/ai-integration-kit
```

O instalador mostra as skills do kit e os assistentes compatíveis (Claude Code,
Codex, Cursor, entre outros). Escolha onde instalar e pronto: o assistente passa
a usar a skill do módulo quando a tarefa envolver o Certillion.

| Para | Comando |
|---|---|
| Instalar só um módulo | `npx skills add certillion/ai-integration-kit --skill certillion-api` (CSS) ou `--skill certillion-flow-api` (Flow) |
| Instalar para todos os seus projetos | acrescentar `-g` |
| Ver as skills instaladas | `npx skills list` |
| Atualizar para a versão mais recente | `npx skills check` e `npx skills update` |

Para pular o menu, indique os assistentes com `-a` (pode repetir):

| Assistente | Opção | Pasta de instalação no projeto |
|---|---|---|
| Claude Code | `-a claude-code` | `.claude/skills/` |
| OpenAI Codex | `-a codex` | `.agents/skills/` |
| Cursor | `-a cursor` | `.agents/skills/` |
| GitHub Copilot | `-a github-copilot` | `.agents/skills/` |
| Google Antigravity | `-a antigravity` | `.agents/skills/` |
| Windsurf | `-a windsurf` | `.windsurf/skills/` |

Exemplo para Claude Code e Codex:

```bash
npx skills add certillion/ai-integration-kit -a claude-code -a codex
```

Codex, Cursor, Copilot e Antigravity leem a mesma pasta `.agents/skills/`. No
modo padrão (links), o instalador grava a cópia principal das skills nessa pasta,
mesmo que você escolha só outro assistente; por isso eles podem não aparecer como
opção separada no menu. A ordem do menu e a pré-seleção são
definidas pelo instalador, não por este kit.

O instalador é uma ferramenta aberta do ecossistema de skills, não da Certillion.
Ele coleta dados anônimos de uso; para desativar, defina `DISABLE_TELEMETRY=1`.

> **Mudança na 0.7-beta:** os arquivos saíram de `docs/certillion/` e agora ficam em
> `skills/`. Se você configurou uma versão anterior manualmente, atualize os caminhos.

## O que vem no kit

Cada módulo é uma skill independente, com regras no `SKILL.md` e material de apoio
em `references/`, lido pelo assistente somente quando necessário.

| Papel | CSS — `skills/certillion-api/` | Flow — `skills/certillion-flow-api/` |
|---|---|---|
| Regras de integração e escolha do módulo | [SKILL.md](skills/certillion-api/SKILL.md) | [SKILL.md](skills/certillion-flow-api/SKILL.md) |
| Conceitos e decisões | [Referência CSS](skills/certillion-api/references/certillion-api-reference.md) | [Referência Flow](skills/certillion-flow-api/references/certillion-flow-api-reference.md) |
| Contrato canônico dos endpoints | [OpenAPI CSS](skills/certillion-api/references/certillion-openapi.yaml) | [OpenAPI Flow](skills/certillion-flow-api/references/certillion-flow-openapi.yaml) |
| Recuperação e acompanhamento | Skill e referência CSS | [Fluxos Flow](skills/certillion-flow-api/references/certillion-flow-integration-flows.md) |
| Diagnóstico | [Troubleshooting CSS](skills/certillion-api/references/certillion-troubleshooting.md) | [Troubleshooting Flow](skills/certillion-flow-api/references/certillion-flow-troubleshooting.md) |
| Exemplos | `references/certillion-examples-<linguagem>.md` | `references/certillion-flow-examples-<linguagem>.md` |

**Qual módulo?** CSS para assinatura digital ICP-Brasil feita pelo seu sistema
(OAuth/PKCE, PSCs, `client_token`, `/oauth/signature`). Flow para enviar PDFs a
participantes e acompanhar o processo (`process_id`, `/flow/restful`). Uma
integração pode usar os dois; cada um tem conta, tokens e contrato próprios.

Ambos incluem exemplos em Node.js, Python, PHP, Java e Ruby. Para campos, tipos,
enums e respostas, o OpenAPI do **respectivo módulo** é a fonte canônica deste kit.
A skill define as decisões de integração; referências e exemplos complementam o contrato.

O Flow inclui login, upload PDF, criação/consulta de processos, modelos visuais,
callback e download ZIP. Conclusão operacional não implica validação criptográfica.
Para modalidades visíveis, consultar as orientações de diagnóstico e conferir a
apresentação do artefato; não tratar erro HTTP500 como autorização para recriar pedidos.

## Instalação manual

Para assistentes sem terminal (como Lovable ou Copilot no navegador), sem Node.js,
ou se preferir controlar os arquivos.

> Mecanismos de configuração verificados em junho/2026. Os harnesses evoluem rápido; se algum
> caminho não funcionar, confirme na documentação oficial da ferramenta. O princípio — adicionar
> os arquivos ao contexto/regras do projeto — permanece válido mesmo que o local exato mude.

### Conceito: AGENTS.md no centro

A maioria dos harnesses modernos lê nativamente um arquivo **`AGENTS.md`** na raiz do projeto —
padrão aberto adotado por Codex, Cursor, Windsurf, Copilot, Antigravity e outros. A forma mais
simples e portável de configurar:

1. Copie a pasta `skills/` deste repositório para a raiz do seu projeto (ou só a
   pasta do módulo que vai usar, que é independente).
2. Crie (ou edite) um `AGENTS.md` na raiz apontando para os arquivos:

   ```markdown
   ## Integração Certillion
   - CSS: seguir skills/certillion-api/SKILL.md.
     Contrato: skills/certillion-api/references/certillion-openapi.yaml.
   - Flow: seguir skills/certillion-flow-api/SKILL.md.
     Contrato: skills/certillion-flow-api/references/certillion-flow-openapi.yaml.
   Cada SKILL.md indica como escolher o módulo. Consultar a referência, os fluxos
   e o exemplo da linguagem apenas quando necessários.
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

- **Pastas de skills:** cada diretório em `skills/` já está no formato `SKILL.md` +
  `references/`. Nos assistentes que leem pastas de skills, copie o diretório
  inteiro; copiar somente o `SKILL.md` deixa a skill sem as referências.
- **Cursor:** para regra dedicada, use `.cursor/rules/certillion.mdc` com frontmatter
  (`description`, `alwaysApply`). Use `alwaysApply: true` se o projeto for dedicado à integração.
- **Windsurf:** arquivos de regra têm limite de tamanho — a regra deve **apontar** para os arquivos
  do kit, não copiá-los.
- **GitHub Copilot:** para regras por tipo de arquivo, use `.github/instructions/*.instructions.md`
  com frontmatter `applyTo`.
- **Lovable:** dois caminhos — (1) conecte o projeto ao GitHub (Settings → Connectors → GitHub,
  instale o Lovable GitHub App, sync bidirecional na branch `main`) e coloque `AGENTS.md` na raiz
  do repositório: o Lovable lê o arquivo automaticamente a cada request; (2) sem GitHub, cole o
  conteúdo da skill do módulo escolhido + as regras pertinentes da sua referência no
  **Project Knowledge** do projeto (Settings → Knowledge — limite de 10 000 caracteres; a skill
  Flow cabe com margem; da skill CSS, selecione as regras pertinentes). O Project Knowledge é
  enviado em todas as conversas — não é necessário repetir as instruções a cada sessão.

## Por onde começar

1. Instale as skills com `npx skills add certillion/ai-integration-kit` ou
   manualmente (acima).
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

*Certillion é produto da e-Sec Tecnologia em Certificação Digital. Versão do kit: 0.7.1-beta.*
