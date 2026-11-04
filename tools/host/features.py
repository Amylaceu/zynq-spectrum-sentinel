"""Open the J6 live window; connecting does not automatically start a feature."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'tools/host'), str(ROOT/'src/ps'), str(ROOT)]
from product import app_instance
from sentinel_host.application_v61 import Window


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--connect')
    args = parser.parse_args()
    app = app_instance(); window = Window(ROOT); window.show()
    if args.connect:
        window.address.setText(args.connect); window.connect_board()
    return app.exec()


if __name__ == '__main__': raise SystemExit(main())
