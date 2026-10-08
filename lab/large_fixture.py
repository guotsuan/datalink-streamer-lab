"""Optional sparse FITS product; never included in the small fixture suite."""
import json
import os
from pathlib import Path
import stat

NAME = 'large-1tb.fits'
DID = 'lab.test:' + NAME
DATA_BYTES = 1_000_000_000_000  # decimal TB, not TiB
BLOCK = 2880
SIZE = BLOCK + ((DATA_BYTES + BLOCK - 1) // BLOCK) * BLOCK
PATH = Path(__file__).resolve().parent / 'storage' / 'lab.test' / NAME

def header():
    cards = ['SIMPLE  =                    T', 'BITPIX  =                    8',
             'NAXIS   =                    2', 'NAXIS1  =              1000000',
             'NAXIS2  =              1000000', 'EXTEND  =                    T',
             'COMMENT Synthetic sparse image; all pixels are zero.',
             'COMMENT Network/streaming benchmark, not physical disk throughput.', 'END']
    return ''.join(x.ljust(80) for x in cards).ljust(BLOCK).encode('ascii')

def describe():
    try:
        info = PATH.lstat()
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(info.st_mode) or info.st_size != SIZE:
        raise RuntimeError('Large fixture is not the expected regular file')
    return {'did': DID, 'name': NAME, 'bytes': SIZE, 'pixel_bytes': DATA_BYTES,
            'allocated_bytes': info.st_blocks * 512, 'sparse': True,
            'sha256': None, 'checksum_note': 'Full-file checksum not computed; bounded header/zero-region checks only.',
            'note': 'Approximately 1 decimal TB. Zero-filled sparse FITS; no compression. Network/streaming test, not physical disk I/O.'}

def create():
    PATH.parent.mkdir(parents=True, exist_ok=True)
    if PATH.parent.is_symlink() or PATH.parent.resolve() != PATH.parent:
        raise RuntimeError('Refusing storage through a symlink')
    try:
        fd = os.open(PATH, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except FileExistsError:
        info = describe()
        with PATH.open('rb') as f:
            if f.read(BLOCK) != header():
                raise RuntimeError('Existing FITS header differs; refusing overwrite')
        return info
    with os.fdopen(fd, 'r+b') as f:
        f.write(header())
        f.truncate(SIZE)
        f.flush()
        os.fsync(f.fileno())
    info = describe()
    if info['allocated_bytes'] > 1024 * 1024:
        raise RuntimeError('Unexpected allocation; stop before serving')
    return info

if __name__ == '__main__':
    print(json.dumps(create(), indent=2))
