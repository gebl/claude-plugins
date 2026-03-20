"""CLI entry point for the task manager daemon."""

import click

from taskmanager.daemon.runner import DaemonRunner


@click.command()
@click.option("--no-daemon-log", is_flag=True, help="Disable daemon log file")
@click.option("--no-session-log", is_flag=True, help="Disable per-session log files")
@click.option(
    "--no-session-output", is_flag=True, help="Disable Claude session output capture"
)
@click.option(
    "--poll-interval", type=int, default=60, help="Initial poll interval in seconds"
)
@click.option("--timeout", type=int, default=1800, help="Session timeout in seconds")
def main(
    no_daemon_log: bool,
    no_session_log: bool,
    no_session_output: bool,
    poll_interval: int,
    timeout: int,
) -> None:
    """Task Manager Daemon — polls for issues and spawns Claude Code sessions."""
    log_channels = {
        "enable_daemon_log": not no_daemon_log,
        "enable_session_log": not no_session_log,
        "enable_session_output": not no_session_output,
    }

    runner = DaemonRunner(
        poll_interval=poll_interval,
        timeout=timeout,
        log_channels=log_channels,
    )
    runner.run()


if __name__ == "__main__":
    main()
