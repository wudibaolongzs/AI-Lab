"""Run as: python tools/question_bank.py [--db PATH] validate|preview|import PACK."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from question_bank import main

if __name__ == '__main__':
    main()
