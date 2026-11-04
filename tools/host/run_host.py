"""Repository entry; PyInstaller adds these same roots via --paths."""
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(Path(__file__).resolve().parent), str(root/'src/ps'), str(root)]
from product import main

if __name__ == '__main__':
    raise SystemExit(main())
