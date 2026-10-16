#!/usr/bin/env python3
"""Gera ou verifica o YAML de compatibilidade a partir do schema CSS canônico."""

import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true',
                        help='Verifica a sincronização sem alterar arquivos.')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    source = root / 'docs/certillion/css/certillion-openapi.yaml'
    target = root / 'docs/certillion/certillion-openapi.yaml'
    content = source.read_bytes()
    if args.check:
        if not target.exists() or target.read_bytes() != content:
            parser.exit(1, 'OpenAPI de compatibilidade desatualizado. '
                        'Execute python3 scripts/sync-css-openapi.py\n')
        print('OpenAPI de compatibilidade sincronizado.')
    else:
        target.write_bytes(content)
        print('OpenAPI de compatibilidade gerado a partir de css/.')


if __name__ == '__main__':
    main()
