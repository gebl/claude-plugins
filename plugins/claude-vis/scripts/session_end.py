"""SessionEnd hook — parses transcript for token totals and summary, finalizes session."""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import db


def parse_transcript(transcript_path: str) -> dict:
    """Parse a transcript JSONL file for token usage and summary info."""
    result = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_creation_tokens": 0,
        "cache_read_tokens": 0,
        "summary": None,
    }

    path = Path(transcript_path)
    if not path.exists():
        return result

    first_user_message = None

    for line in path.read_text().splitlines():
        if not line.strip():
            continue

        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue

        # Collect token usage from assistant messages
        usage = entry.get("usage", {})
        if usage:
            result["input_tokens"] += usage.get("input_tokens", 0)
            result["output_tokens"] += usage.get("output_tokens", 0)
            result["cache_creation_tokens"] += usage.get("cache_creation_input_tokens", 0)
            result["cache_read_tokens"] += usage.get("cache_read_input_tokens", 0)

        # Capture first user message for summary
        if first_user_message is None and entry.get("role") == "user":
            content = entry.get("content", "")
            if isinstance(content, list):
                text_parts = [
                    block.get("text", "")
                    for block in content
                    if isinstance(block, dict) and block.get("type") == "text"
                ]
                content = " ".join(text_parts)
            if isinstance(content, str) and content.strip():
                first_user_message = content.strip()[:200]

    result["summary"] = first_user_message
    return result


def main() -> None:
    data = json.load(sys.stdin)

    session_id = data.get("session_id")
    if not session_id:
        return

    ended_at = db.now_iso()

    # Calculate duration from started_at
    duration_ms = None
    started_at = db.get_session_started_at(session_id)
    if started_at:
        try:
            start = datetime.fromisoformat(started_at)
            end = datetime.now(timezone.utc)
            duration_ms = int((end - start).total_seconds() * 1000)
        except (ValueError, TypeError):
            pass

    # Parse transcript for token totals and summary
    transcript_path = data.get("transcript_path", "")
    transcript_data = parse_transcript(transcript_path) if transcript_path else {}

    db.update_session_end(
        session_id=session_id,
        ended_at=ended_at,
        duration_ms=duration_ms,
        summary=transcript_data.get("summary"),
        total_input_tokens=transcript_data.get("input_tokens", 0),
        total_output_tokens=transcript_data.get("output_tokens", 0),
        cache_creation_tokens=transcript_data.get("cache_creation_tokens", 0),
        cache_read_tokens=transcript_data.get("cache_read_tokens", 0),
    )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
