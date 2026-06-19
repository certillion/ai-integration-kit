# Certillion — Kit de Integração para IA

Conjunto de arquivos que habilitam assistentes de IA (Claude Code, Codex, Cursor, Windsurf,
GitHub Copilot, Antigravity e outros) a integrar a **API Certillion de assinatura digital
ICP-Brasil** de forma rápida e correta — gerando código que já respeita o fluxo de autenticação,
os padrões de assinatura, as regras de custo e os pontos de atenção da plataforma.

> Versão: 0.2-beta · Documentação pública.

## Para que serve

Em vez de a IA adivinhar parâmetros e cometer erros comuns de integração (cobrança dupla por
encapsular passos, mensagens de erro genéricas, tamanho de arquivo mal gerenciado), você adiciona
estes arquivos ao contexto do seu assistente e ele passa a conhecer a API como um desenvolvedor
experiente nela.

## Os arquivos

Ficam em [`docs/certillion/`](docs/certillion/). Cada um tem um papel distinto e complementar:

| Arquivo | Papel | Quando usar |
|---------|-------|-------------|
| `certillion-skill.md` | As **regras** (R1–R13) que todo código de integração deve seguir | Sempre — governa o comportamento da IA |
| `certillion-api-reference.md` | **Guia conceitual**: fluxos, custo, decisões, diagnóstico | Para entender *como* e *por que* algo funciona |
| `certillion-openapi.yaml` | **Schema canônico** (OpenAPI 3.0) — a mecânica exata de cada endpoint | Para o detalhe preciso de um endpoint; importar em Postman/Insomnia; gerar SDK |
| `certillion-examples-nodejs.md` | Exemplos de código — Node.js / TypeScript | Ao escrever o código na linguagem-alvo |
| `certillion-examples-python.md` | Exemplos de código — Python | idem |
| `certillion-examples-php.md` | Exemplos de código — PHP | idem |
| `certillion-examples-java.md` | Exemplos de código — Java | idem |
| `certillion-examples-ruby.md` | Exemplos de código — Ruby | idem |

**Precedência:** para qualquer detalhe sobre a mecânica de um endpoint (campo, tipo, enum, erro),
o `certillion-openapi.yaml` é a **fonte única de verdade**. Os demais apontam para ele — assim as
fontes não se contradizem.

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
   ## Integração Certillion (assinatura digital ICP-Brasil)
   Ao trabalhar na integração com a API Certillion, seguir:
   - Regras: docs/certillion/certillion-skill.md
   - Guia conceitual: docs/certillion/certillion-api-reference.md
   - Schema (fonte canônica de endpoints): docs/certillion/certillion-openapi.yaml
   - Exemplos de código: docs/certillion/certillion-examples-<linguagem>.md
   A skill define as regras (R1–R13); o schema é a fonte de verdade para campos e tipos.
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
| **Google Antigravity** | `AGENTS.md`, `GEMINI.md` ou `.agents/rules/`; suporta Skills em `.agents/skills/` | Sim (desde v1.20.3) |

### Notas por harness

- **Claude Code:** o `certillion-skill.md` já tem formato de Skill (frontmatter `name`/`description`)
  e pode ser usado como skill, para carregamento sob demanda.
- **Cursor:** para regra dedicada, use `.cursor/rules/certillion.mdc` com frontmatter
  (`description`, `alwaysApply`). Use `alwaysApply: true` se o projeto for dedicado à integração.
- **Windsurf:** arquivos de regra têm limite de tamanho — a regra deve **apontar** para os arquivos
  do kit, não copiá-los.
- **GitHub Copilot:** para regras por tipo de arquivo, use `.github/instructions/*.instructions.md`
  com frontmatter `applyTo`.
- **Antigravity:** como suporta o formato `SKILL.md`, o `certillion-skill.md` funciona como skill
  nativa em `.agents/skills/`.

## Por onde começar

1. Copie `docs/certillion/` para o seu projeto e configure o `AGENTS.md` (acima).
2. Solicite suas credenciais de teste em https://certillion.com/fale-conosco-certillion/.
   Nossa equipe envia as credenciais e orienta sobre as condições de uso no período de integração.
3. Mantenha a flag `CERTILLION_ENV = 'test'` durante o desenvolvimento (a skill orienta a IA a
   incluir o guardrail de ambiente automaticamente).
4. Peça a integração ao seu assistente — ele já conhece o fluxo, o custo e os pontos de atenção.

## Fontes

Estes artefatos foram elaborados pela equipe Certillion com base na experiência de integração
da plataforma e **também na documentação oficial da API**, disponível em:

- Visão geral da API: https://certillion.com/certillion-api/documentacao-de-api/
- Tutoriais: https://certillion.com/certillion-api/tutoriais/
- Referência da API: https://certillion.com/certillion-api/api-certillion-assinatura-digital-documentacao/

## Suporte

Dúvidas durante a integração: https://certillion.com/fale-conosco-certillion/

---

*Certillion é produto da e-Sec Tecnologia em Certificação Digital. Versão do kit: 0.2-beta.*
