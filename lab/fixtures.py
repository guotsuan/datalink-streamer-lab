"""Deterministic synthetic products. Never reads real scientific data."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STORAGE = ROOT / "storage"
SCOPE = "lab.test"
DL_COMMIT = "997dfb03944b9c44283411264ca1c07b48b03a8e"
PS_COMMIT = "27df8cb247105faf67a6d278dd9819528f211dd3"


def public_base():
    config = ROOT / "public-access.json"
    return json.loads(config.read_text())["origin"] if config.exists() else "http://localhost:18080"


def contents():
    cards = ["SIMPLE  =                    T", "BITPIX  =                    8",
             "NAXIS   =                    2", "NAXIS1  =                   16",
             "NAXIS2  =                   16", "COMMENT Synthetic test fixture; not observational data", "END"]
    fits = "".join(card.ljust(80) for card in cards).ljust(2880).encode("ascii")
    fits += bytes(range(256)) + bytes(2880 - 256)
    return {"image.fits": fits,
            "readme.txt": b"Synthetic DataLink / Product Streamer laboratory fixture.\n",
            "metadata.json": b'{"synthetic":true,"instrument":"none"}\n',
            "range.bin": bytes(range(256)) * 4096}


def manifest():
    return [{"did": f"{SCOPE}:{name}", "name": name, "bytes": len(data),
             "sha256": hashlib.sha256(data).hexdigest()} for name, data in contents().items()]


def initialise():
    directory = STORAGE / SCOPE
    directory.mkdir(parents=True, exist_ok=True)
    for name, data in contents().items():
        target = directory / name
        if target.exists():
            if target.read_bytes() != data:
                raise RuntimeError(f"Existing fixture differs; refusing overwrite: {target}")
        else:
            target.write_bytes(data)
    (ROOT / "evidence").mkdir(exist_ok=True)


if __name__ == "__main__":
    initialise()
    print(json.dumps(manifest(), indent=2))
