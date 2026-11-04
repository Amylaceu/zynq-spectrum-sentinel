"""Release-only B demo wrapper; no hardware activity on import."""
from pathlib import Path
import sys

if __name__ == '__main__':
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'ps'))
    from sentinel.app.demo_b import main
    raise SystemExit(main())
