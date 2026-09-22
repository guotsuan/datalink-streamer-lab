"""Prepare fresh, isolated laboratory environments; never start public services.

Requires Python 3.13. Run --dry-run first. Historical snapshots are version-pinned,
not hash-locked. No existing environment or installation directory is overwritten.
"""
import argparse
from pathlib import Path
import re
import subprocess
import sys

LAB = Path(__file__).resolve().parents[1] / "lab"
INDEXES = [
    "https://artefact.skao.int/repository/pypi-internal/simple",
    "https://gitlab.com/api/v4/projects/48060714/packages/pypi/simple",
    "https://gitlab.com/api/v4/projects/77541150/packages/pypi/simple",
]
SOURCES = {
    "datalink": ("ska-src-dm-datalink", "997dfb03944b9c44283411264ca1c07b48b03a8e"),
    "streamer": ("ska-src-dm-product-streamer-api", "27df8cb247105faf67a6d278dd9819528f211dd3"),
}


def install_lines(kind):
    lines = (LAB / f"requirements-{kind}.lock.txt").read_text().splitlines()
    result = []
    replacements = 0
    for line in lines:
        if not line.strip() or line.startswith("#"):
            continue
        if " @ file:" in line:
            package, commit = SOURCES[kind]
            if not line.startswith(package + " @ file:///home/gq/datalink-streamer-lab/upstream/"):
                raise ValueError("Unexpected local source reference")
            result.append(f"{package} @ git+https://gitlab.com/ska-telescope/src/src-dm/{package}.git@{commit}")
            replacements += 1
        elif re.fullmatch(r"[A-Za-z0-9_.-]+==[A-Za-z0-9_.+!-]+", line):
            result.append(line)
        else:
            raise ValueError(f"Unexpected requirement syntax in {kind}")
    if replacements != (0 if kind == "portal" else 1):
        raise ValueError("Unexpected number of local source references")
    return "\n".join(result) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    targets = {"portal": LAB / ".venv", "datalink": LAB / ".venv-datalink", "streamer": LAB / ".venv-streamer"}
    inputs = {kind: install_lines(kind) for kind in targets}
    print("Lab directory:", LAB)
    for kind, directory in targets.items():
        print(f"{kind}: {directory}; {len(inputs[kind].splitlines())} pinned requirements")
    for kind, (package, commit) in SOURCES.items():
        print(f"{kind} source: {package} @ {commit}")
    print("No service startup, public exposure or credential creation is performed.")
    if args.dry_run:
        return
    if sys.version_info[:2] != (3, 13):
        raise SystemExit("Use Python 3.13 to match the recorded server baseline.")
    staging = LAB / ".install"
    for directory in [*targets.values(), staging]:
        if directory.exists() or directory.is_symlink():
            raise SystemExit(f"Refusing to overwrite existing path: {directory}")
    staging.mkdir(mode=0o700)
    for kind, directory in targets.items():
        requirement_file = staging / f"{kind}.txt"
        with requirement_file.open("x") as output:
            output.write(inputs[kind])
        subprocess.run([sys.executable, "-m", "venv", str(directory)], check=True)
        command = [str(directory / "bin/python"), "-m", "pip", "install", "--index-url", "https://pypi.org/simple"]
        if kind != "portal":
            for index in INDEXES:
                command += ["--extra-index-url", index]
        subprocess.run(command + ["-r", str(requirement_file)], check=True)
        subprocess.run([str(directory / "bin/python"), "-m", "pip", "check"], check=True)
    print("Preparation complete. Review docs/DEPLOYMENT.md before starting the private lab.")


if __name__ == "__main__":
    main()
