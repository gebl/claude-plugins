# yt-transcript

Fetch YouTube video transcripts and save them as clean Markdown files, ready to drop into your notes. Includes video title, channel link, and description in the header.

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) (optional, for video metadata — title, channel, description)

Clone the repo, then `uv sync` to create the venv and install dependencies. After that, `uv run` is all you need.

## Usage

```bash
uv run python yt_transcript.py URL OUTPUT
```

| Argument | Description |
|----------|-------------|
| `URL` | YouTube video URL or bare video ID |
| `OUTPUT` | Output filename (`.md` extension added automatically if omitted) |

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--timestamps` | on | Each subtitle line gets a bold `[M:SS]` timestamp |
| `--no-timestamps` | — | Groups text into ~60-second paragraphs for cleaner reading |
| `-l` / `--language` | `en` | Transcript language code |

### Examples

```bash
# Timestamped transcript
uv run python yt_transcript.py \
  "https://www.youtube.com/watch?v=dQw4w9WgXcQ" transcript.md

# Clean paragraphs (better for notes)
uv run python yt_transcript.py \
  --no-timestamps "https://youtu.be/dQw4w9WgXcQ" notes/talk.md

# Spanish transcript
uv run python yt_transcript.py \
  -l es "https://www.youtube.com/watch?v=dQw4w9WgXcQ" charla.md

# Using a bare video ID
uv run python yt_transcript.py \
  dQw4w9WgXcQ transcript.md
```

### Supported URL formats

- `https://www.youtube.com/watch?v=VIDEO_ID`
- `https://youtu.be/VIDEO_ID`
- `https://www.youtube.com/embed/VIDEO_ID`
- `https://www.youtube.com/shorts/VIDEO_ID`
- Bare 11-character video ID

## Output

When yt-dlp is available, the Markdown header includes the video title, channel link, and a collapsible description:

```markdown
# 45 People, $200M Revenue. The Question Nobody's Asking About AI and Your Team Size.

**Source:** <https://www.youtube.com/watch?v=hnwM01CpzmA>
**Channel:** [AI News & Strategy Daily | Nate B Jones](https://www.youtube.com/channel/UC0C-17n9iuUQPylguM1d-lQ)
**Language:** English (auto-generated) (en)
**Auto-generated:** Yes

<details>
<summary>Description</summary>

Video description text here...

</details>

---

**[0:00]** All those AI note-taking apps are
**[0:02]** barnacles. They're just wrong.
```

If yt-dlp is not installed, the script still works — it just falls back to using the video ID as the title.

With `--no-timestamps`, subtitle fragments are merged into readable paragraphs split roughly every 60 seconds of speech.
