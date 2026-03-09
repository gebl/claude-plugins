---
name: yt-transcript
description: "Fetch a YouTube video transcript and save it as a Markdown file. Use when the user shares a YouTube URL and wants the transcript, or asks to transcribe/capture/grab a YouTube video."
---

# YouTube Transcript

Fetch a YouTube video's transcript and save it as a clean Markdown document suitable for notes.

## When to Use

- User shares a YouTube URL and asks for the transcript
- User says "grab the transcript", "transcribe this video", "get captions from this video"
- User wants to save a YouTube video's content as notes

## Inputs

You need two things from the user (ask if not provided):

1. **YouTube URL or video ID** — any standard format (`youtube.com/watch?v=`, `youtu.be/`, bare 11-char ID)
2. **Output filename** — where to save the `.md` file (default to a slugified title in the current directory)

Also ask the user:
- **Timestamps?** — Include `[M:SS]` timestamps per line, or merge into clean paragraphs (default: no timestamps, clean paragraphs are better for notes)

## Steps

### 1. Extract the video ID

Parse the URL to get the 11-character video ID. Support these formats:
- `https://www.youtube.com/watch?v=VIDEO_ID`
- `https://youtu.be/VIDEO_ID`
- `https://www.youtube.com/embed/VIDEO_ID`
- `https://www.youtube.com/shorts/VIDEO_ID`
- `https://m.youtube.com/watch?v=VIDEO_ID`
- Bare 11-character video ID

### 2. Fetch video metadata

**Title and channel** — use the YouTube oEmbed endpoint (zero dependencies):

```bash
curl -s "https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v=VIDEO_ID&format=json"
```

This returns JSON with `title`, `author_name`, and `author_url`.

**Description** — extract from the YouTube page's embedded JSON (zero dependencies, stdlib only):

```bash
curl -s "https://www.youtube.com/watch?v=VIDEO_ID" -o /tmp/yt_page.html
```

Then parse the `ytInitialPlayerResponse` JSON blob from the HTML:

```python
import json, re
html = open("/tmp/yt_page.html").read()
m = re.search(r'var ytInitialPlayerResponse\s*=\s*(\{.*?\});', html)
if m:
    data = json.loads(m.group(1))
    description = data.get("videoDetails", {}).get("shortDescription", "")
```

If either metadata step fails, skip it gracefully — the transcript is what matters.

### 3. Fetch the transcript

Run this Python snippet via `uv run` (only dependency: `youtube-transcript-api`):

```bash
uv run --with youtube-transcript-api python3 -c "
import json
from youtube_transcript_api import YouTubeTranscriptApi
ytt = YouTubeTranscriptApi()
t = ytt.fetch('VIDEO_ID')
print(json.dumps([{'start': s.start, 'text': s.text} for s in t]))
"
```

This outputs a JSON array of `{"start": float, "text": string}` objects.

If the user requested a specific language, pass `languages=['XX']` to `ytt.fetch()`.

### 4. Format as Markdown

Build the document with this structure:

```markdown
# Video Title Here

**Source:** <https://www.youtube.com/watch?v=VIDEO_ID>
**Channel:** [Channel Name](channel_url)

<details>
<summary>Description</summary>

Video description text here...

</details>

---

Transcript body here...
```

If the description is empty or could not be fetched, omit the `<details>` block entirely.

**With timestamps** (`--timestamps`): Each snippet gets a bold timestamp prefix:

```markdown
**[0:00]** First line of speech

**[0:05]** Second line of speech
```

**Without timestamps** (default, better for notes): Merge consecutive snippets into paragraphs. Start a new paragraph roughly every 60 seconds of speech (when the gap between the current snippet's `start` and the paragraph's first snippet exceeds 60 seconds).

```markdown
First line of speech second line of speech third line continues the thought and flows naturally into a readable paragraph.

Next paragraph starts after a gap in the timeline and groups another minute of speech together into readable flowing text.
```

### 5. Write the file

Save the Markdown to the user's requested path. If no `.md` extension was given, add it. Create parent directories if needed.

Report the saved file path and a brief summary (title, channel, approximate word count).

## Error Handling

- If the transcript fetch fails, tell the user — the video may not have captions, or the language may not be available.
- If oEmbed fails, skip the metadata and use the video ID as the title. The transcript is what matters.
- If `uv` is not available, instruct the user to install it.

## Notes

- This skill is self-contained and only needs `uv` and `curl` on the system.
- The only Python dependency (`youtube-transcript-api`) is fetched on-the-fly by `uv run --with`.
- For a standalone CLI version of this tool, see `yt_transcript.py` in this repository.
