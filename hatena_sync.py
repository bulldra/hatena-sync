import sys
from pathlib import Path

# Allow running without installing the package
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from hatena_sync import cli

if __name__ == "__main__":
    cli()
