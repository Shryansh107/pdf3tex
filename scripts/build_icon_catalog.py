"""Extract icon names and commands from the pinned CTAN mapping metadata."""
import argparse
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'compiler'))
from install_fontawesome import SHA256, URL, verified_archive


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    args = parser.parse_args()
    with verified_archive(args.archive.read_bytes()) as archive:
        mapping = archive.read('fontawesome5/tex/fontawesome5-mapping.def').decode()
    pattern = r'\\__fontawesome_def_icon:nnnnn\{([^}]*)\}\{([^}]+)\}\{([^}]+)\}\{[^}]+\}\{"([0-9A-F]+)\}'
    icons = {}
    for command, name, family, code in re.findall(pattern, mapping):
        if name == 'external-link-alt':
            command = r'\faExternalLink*'
        icons[name] = {'command': command or r'\faIcon{' + name + '}',
                       'unicode': int(code, 16), 'family': 'brands' if family.startswith('brands') else 'free'}
    if len(icons) < 1000:
        raise ValueError('The pinned mapping format was not recognized.')
    result = {'version': '5.15.4', 'source': URL, 'sha256': SHA256,
              'notice': 'Icon name/Unicode metadata from Font Awesome 5 Free (SIL OFL 1.1); TeX mapping by Marcel Krueger (LPPL 1.3c). No font programs included.',
              'icons': icons}
    output = Path(__file__).resolve().parents[1] / 'icon_fonts.json'
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(f'Wrote {len(icons)} icon mappings to {output.name}')


if __name__ == '__main__':
    main()
