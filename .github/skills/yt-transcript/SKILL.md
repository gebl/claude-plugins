---
name: yt-transcript
description: "Fetch a YouTube video transcript and save it as a Markdown file. Use when the user shares a YouTube URL and wants the transcript, or asks to transcribe/capture/grab a YouTube video."
allowed-tools:
  - bash
---

# YouTube Transcript

Fetch a YouTube video's transcript and save it as a clean Markdown document.

## When to Use

- User shares a YouTube URL and asks for the transcript
- User says "grab the transcript", "transcribe this video", "get captions from this video"
- User wants to save a YouTube video's content as notes

## How to Run

Use the CLI script at `yt_transcript.py`. Run it from this skill directory:

```bash
python3 yt_transcript.py [OPTIONS] URL OUTPUT
```

### Arguments

| Argument | Description |
|----------|-------------|
| `URL` | YouTube video URL or bare 11-char video ID |
| `OUTPUT` | Output filename (e.g. `notes/talk.md`). `.md` extension added automatically if missing. |

### Options

| Option | Default | Description |
|--------|---------|-------------|
| `--timestamps / --no-timestamps` | `--timestamps` | Include `[M:SS]` timestamps per line, or merge into clean paragraphs |
| `--language, -l` | `en` | Transcript language code |

### Defaults

- Use `--no-timestamps` unless the user explicitly asks for timestamps. Clean paragraphs are better for notes.
- If the user doesn't specify an output file, generate one by slugifying the video ID (e.g. `hnwM01CpzmA.md`) in the current working directory.

## Example

```bash
python3 yt_transcript.py --no-timestamps "https://www.youtube.com/watch?v=dQw4w9WgXcQ" ~/notes/rick-roll.md
```

## After Running

- view the saved file and provide a brief summary (title, key points) if the user asked for one.
- Report the saved file path, title, channel, and approximate word count.

## Error Handling

- If the transcript fetch fails, tell the user -- the video may not have captions, or the language may not be available.
- If `python3` is not available, tell the user the transcript helper cannot run in the current environment.
