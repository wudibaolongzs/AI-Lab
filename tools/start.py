"""Load local .env configuration and start AI-Lab from any working directory."""

import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
KEYS = {"AGENTARTS_WORKFLOW_URL", "AGENTARTS_API_KEY", "AGENTARTS_EXERCISES",
        "AI_PROVIDER", "AI_TIMEOUT", "TENCENT_API_KEY", "TENCENT_MODEL", "TENCENT_API_URL",
        "DEEPSEEK_API_KEY", "DEEPSEEK_MODEL", "DEEPSEEK_API_URL"}


def load_env(path, environment):
    if not path.exists():
        return
    for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if not separator or key not in KEYS:
            raise ValueError(f".env 第 {number} 行需使用示例文件中的变量名。")
        if value.startswith(('"', "'")):
            if len(value) < 2 or value[-1] != value[0]:
                raise ValueError(f".env 第 {number} 行引号不完整。")
            value = value[1:-1]
        environment.setdefault(key, value)


def main():
    environment = os.environ.copy()
    try:
        load_env(ROOT / ".env", environment)
    except (ValueError, OSError) as error:
        print(error, file=sys.stderr)
        return 2
    return subprocess.call([sys.executable, "-B", str(ROOT / "app.py"), *sys.argv[1:]],
                           cwd=ROOT, env=environment)


if __name__ == "__main__":
    sys.exit(main())
