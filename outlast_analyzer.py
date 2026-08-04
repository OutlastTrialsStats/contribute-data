"""Legacy entry point.

The application now lives in src/totstats. This shim stays for one release so that anything
still invoking the old script path keeps working; it will be removed afterwards.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from totstats.__main__ import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
