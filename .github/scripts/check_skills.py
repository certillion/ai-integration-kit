"""Verifica o formato das skills do kit: frontmatter, links relativos e OpenAPI.

Uso: python3 .github/scripts/check_skills.py (a partir da raiz do repositório).
"""
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SKILLS = ROOT / "skills"
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
LINK_RE = re.compile(r"\]\(([^)\s]+)\)")
errors = []


def check_frontmatter(skill_dir):
    text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not match:
        errors.append(f"{skill_dir.name}: SKILL.md sem frontmatter")
        return
    meta = yaml.safe_load(match.group(1)) or {}
    name, description = meta.get("name"), meta.get("description")
    if name != skill_dir.name or not NAME_RE.match(str(name)):
        errors.append(f"{skill_dir.name}: name '{name}' deve ser igual ao diretório, em minúsculas e hífens")
    if not description or len(description) > 1024:
        errors.append(f"{skill_dir.name}: description ausente ou acima de 1024 caracteres")


def check_links(md_file, boundary):
    for target in LINK_RE.findall(md_file.read_text(encoding="utf-8")):
        if re.match(r"^[a-z]+:", target) or target.startswith("#"):
            continue
        resolved = (md_file.parent / target.split("#")[0]).resolve()
        where = md_file.relative_to(ROOT)
        if not resolved.exists():
            errors.append(f"{where}: link quebrado para {target}")
        elif boundary not in (resolved, *resolved.parents):
            errors.append(f"{where}: link {target} sai do diretório da skill")


def check_openapi(yaml_file):
    spec = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
    if not isinstance(spec, dict) or "openapi" not in spec or not spec.get("paths"):
        errors.append(f"{yaml_file.relative_to(ROOT)}: OpenAPI sem 'openapi' ou 'paths'")


skill_dirs = sorted(p.parent for p in SKILLS.glob("*/SKILL.md"))
if not skill_dirs:
    errors.append("nenhuma skill encontrada em skills/")
for skill_dir in skill_dirs:
    check_frontmatter(skill_dir)
    for md_file in skill_dir.rglob("*.md"):
        check_links(md_file, skill_dir.resolve())
    for yaml_file in skill_dir.rglob("*.yaml"):
        check_openapi(yaml_file)
check_links(ROOT / "README.md", ROOT)

if errors:
    print("\n".join(errors))
    sys.exit(1)
print(f"OK: {len(skill_dirs)} skills verificadas")
