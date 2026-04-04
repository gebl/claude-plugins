"""Fetch a YouTube video transcript and save it as a Markdown file."""

import re
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import click
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import Formatter


def fetch_video_metadata(video_id: str) -> dict | None:
    """Fetch video metadata (title, channel, description) via yt-dlp."""
    try:
        import yt_dlp
    except ImportError:
        return None

    url = f"https://www.youtube.com/watch?v={video_id}"
    opts = {"quiet": True, "no_warnings": True, "skip_download": True}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            data = ydl.extract_info(url, download=False)
        return {
            "title": data.get("title", ""),
            "channel": data.get("channel", ""),
            "channel_url": data.get("channel_url", ""),
            "description": data.get("description", ""),
        }
    except Exception:
        return None


class MarkdownFormatter(Formatter):
    """Format transcript as a readable Markdown document."""

    def format_transcript(self, transcript, **kwargs):
        include_timestamps = kwargs.get("timestamps", True)
        metadata = kwargs.get("metadata")
        video_id = transcript.video_id
        language = transcript.language
        language_code = transcript.language_code
        is_generated = transcript.is_generated

        video_url = f"https://www.youtube.com/watch?v={video_id}"

        if metadata and metadata.get("title"):
            title = metadata["title"]
            channel = metadata.get("channel", "")
            channel_url = metadata.get("channel_url", "")
            description = metadata.get("description", "")

            lines = [
                f"# {title}\n",
                f"**Source:** <{video_url}>  ",
            ]
            if channel and channel_url:
                lines.append(f"**Channel:** [{channel}]({channel_url})  ")
            elif channel:
                lines.append(f"**Channel:** {channel}  ")
            lines.extend([
                f"**Language:** {language} ({language_code})  ",
                f"**Auto-generated:** {'Yes' if is_generated else 'No'}\n",
            ])
            if description:
                lines.extend([
                    "<details>\n<summary>Description</summary>\n",
                    f"{description}\n",
                    "</details>\n",
                ])
            lines.append("---\n")
        else:
            lines = [
                f"# Transcript: {video_id}\n",
                f"**Source:** <{video_url}>  ",
                f"**Language:** {language} ({language_code})  ",
                f"**Auto-generated:** {'Yes' if is_generated else 'No'}\n",
                "---\n",
            ]

        if include_timestamps:
            for snippet in transcript:
                minutes = int(snippet.start // 60)
                seconds = int(snippet.start % 60)
                lines.append(f"**[{minutes}:{seconds:02d}]** {snippet.text}\n")
        else:
            # Group text into paragraphs (one per ~60 seconds of speech)
            paragraph = []
            last_start = 0.0
            for snippet in transcript:
                if snippet.start - last_start > 60 and paragraph:
                    lines.append(" ".join(paragraph) + "\n")
                    paragraph = []
                    last_start = snippet.start
                paragraph.append(snippet.text)
            if paragraph:
                lines.append(" ".join(paragraph) + "\n")

        return "\n".join(lines)

    def format_transcripts(self, transcripts, **kwargs):
        return "\n---\n\n".join(
            self.format_transcript(t, **kwargs) for t in transcripts
        )


def extract_video_id(url: str) -> str:
    """Extract the video ID from various YouTube URL formats."""
    parsed = urlparse(url)

    if parsed.hostname in ("youtu.be",):
        return parsed.path.lstrip("/")

    if parsed.hostname in ("www.youtube.com", "youtube.com", "m.youtube.com"):
        if parsed.path == "/watch":
            return parse_qs(parsed.query)["v"][0]
        if parsed.path.startswith(("/embed/", "/v/", "/shorts/")):
            return parsed.path.split("/")[2]

    # Maybe it's already a bare video ID
    if re.match(r"^[\w-]{11}$", url):
        return url

    raise click.BadParameter(f"Could not extract video ID from: {url}")


@click.command()
@click.argument("url")
@click.argument("output", type=click.Path())
@click.option(
    "--timestamps/--no-timestamps",
    default=True,
    help="Include timestamps in output (default: on).",
)
@click.option(
    "--language",
    "-l",
    default="en",
    help="Transcript language code (default: en).",
)
def main(url: str, output: str, timestamps: bool, language: str):
    """Fetch a YouTube transcript and save it as Markdown.

    URL is the YouTube video URL or video ID.
    OUTPUT is the filename to save to (e.g. notes/talk.md).
    """
    video_id = extract_video_id(url)
    output_path = Path(output)

    if not output_path.suffix:
        output_path = output_path.with_suffix(".md")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    click.echo("Fetching video metadata...")
    metadata = fetch_video_metadata(video_id)
    if metadata and metadata.get("title"):
        click.echo(f"  Title: {metadata['title']}")
        click.echo(f"  Channel: {metadata.get('channel', 'Unknown')}")
    else:
        click.echo("  Could not fetch metadata (yt-dlp missing?), continuing without it.")

    try:
        ytt_api = YouTubeTranscriptApi()
        transcript = ytt_api.fetch(video_id, languages=[language])
    except Exception as e:
        click.echo(f"Error fetching transcript: {e}", err=True)
        sys.exit(1)

    formatter = MarkdownFormatter()
    md = formatter.format_transcript(transcript, timestamps=timestamps, metadata=metadata)

    output_path.write_text(md, encoding="utf-8")
    click.echo(f"Saved transcript to {output_path}")


if __name__ == "__main__":
    main()
