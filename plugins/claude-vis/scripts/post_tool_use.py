"""PostToolUse hook — logs tool usage, commands, and URLs."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import db


def main() -> None:
    data = json.load(sys.stdin)

    session_id = data.get("session_id")
    if not session_id:
        return

    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {})
    agent_id = data.get("agent_id")
    timestamp = db.now_iso()

    db.insert_tool_use(
        session_id=session_id,
        tool_name=tool_name,
        tool_use_id=data.get("tool_use_id"),
        timestamp=timestamp,
        success=1,
        agent_id=agent_id,
    )

    if tool_name == "Bash" and tool_input.get("command"):
        db.insert_command(
            session_id=session_id,
            command=tool_input["command"],
            timestamp=timestamp,
            agent_id=agent_id,
        )

    elif tool_name == "WebFetch" and tool_input.get("url"):
        db.insert_url(
            session_id=session_id,
            url=tool_input["url"],
            source="WebFetch",
            query=tool_input.get("prompt"),
            timestamp=timestamp,
            agent_id=agent_id,
        )

    elif tool_name == "WebSearch" and tool_input.get("query"):
        db.insert_url(
            session_id=session_id,
            url=tool_input.get("query", ""),
            source="WebSearch",
            query=tool_input["query"],
            timestamp=timestamp,
            agent_id=agent_id,
        )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
