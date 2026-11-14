"""Install the pinned Font Awesome 5 Free TeX package during image creation."""
import hashlib
from io import BytesIO
from pathlib import Path
import urllib.request
from zipfile import ZipFile

URL = 'https://mirrors.ctan.org/fonts/fontawesome5.zip'
SHA256 = '83c86c8a92d80e0b2c84af78a055d10798f8294f63b397ba8225351b9eaaa500'


def verified_archive(data):
    if hashlib.sha256(data).hexdigest() != SHA256:
        raise ValueError('Font Awesome archive checksum changed; review before updating the pin.')
    return ZipFile(BytesIO(data))


def install():
    # A fixed HTTPS mirror avoids CTAN redirects to HTTP-only mirrors inside
    # container build networks. Every download still requires the exact hash.
    mirror = 'https://mirrors.in3.sahilister.net/ctan/fonts/fontawesome5.zip'
    data = urllib.request.urlopen(mirror, timeout=90).read()
    root = Path('/usr/local/share/texmf')
    destinations = {
        '.enc': 'fonts/enc/dvips/fontawesome5', '.map': 'fonts/map/dvips/fontawesome5',
        '.otf': 'fonts/opentype/public/fontawesome5', '.pfb': 'fonts/type1/public/fontawesome5',
        '.tfm': 'fonts/tfm/public/fontawesome5', '.sty': 'tex/latex/fontawesome5',
        '.fd': 'tex/latex/fontawesome5', '.def': 'tex/latex/fontawesome5',
        '.lua': 'tex/latex/fontawesome5', '.md': 'doc/fonts/fontawesome5',
    }
    with verified_archive(data) as archive:
        for entry in archive.infolist():
            name = Path(entry.filename)
            if entry.is_dir() or name.suffix not in destinations:
                continue
            target = root / destinations[name.suffix] / name.name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(entry))


if __name__ == '__main__':
    install()
