"""Release launcher for python -m sentinel.app.demo; no hardware on import."""
from pathlib import Path
import sys

if __name__ == '__main__':
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'ps'))
    from sentinel.app.demo import main
    raise SystemExit(main())
