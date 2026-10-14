"""Use the statement parser shipped with the server from local crawler scripts."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "feat"))
from api.acm_api.problem_content import parse_atcoder
