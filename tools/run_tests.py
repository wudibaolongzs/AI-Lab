"""Run all tests, or --offline without opening loopback sockets."""

import argparse
import os
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    environment = os.environ.copy()
    environment["AI_LAB_OFFLINE_TESTS"] = "1" if args.offline else "0"
    return subprocess.call([sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests", "-v"],
                           cwd=Path(__file__).resolve().parent.parent, env=environment)


if __name__ == "__main__":
    sys.exit(main())
