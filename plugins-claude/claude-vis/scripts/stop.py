"""Stop hook — increments turn count. Always approves stopping."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import db


def main() -> None:
    data = json.load(sys.stdin)
    session_id = data.get("session_id")
    if session_id:
        db.increment_turn_count(session_id)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    finally:
        print(json.dumps({"decision": "approve"}))
