"""Generate the public artifact, or synchronize the portable local HTML."""
import argparse
from pathlib import Path
from price_data import ROOT, atomic_write, publish, read_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sync", action="store_true", help="Sync root HTML/JSON/manifest from canonical JSON")
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    output = ROOT if args.sync else args.output
    publish(read_json(ROOT / "data.json"), read_json(ROOT / "plans.json"), output)
    if not args.sync:
        atomic_write(output / ".nojekyll", "")
    print(f"Validated and built: {output}")


if __name__ == "__main__":
    main()
