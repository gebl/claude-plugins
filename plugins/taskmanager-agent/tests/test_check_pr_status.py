"""Tests for check_pr_status.py script CLI interface."""


def test_check_pr_status_has_help(run_script):
    result = run_script("check_pr_status.py", "--help")
    assert result.returncode == 0
    assert "repo-url" in result.stdout
    assert "branch" in result.stdout


def test_check_pr_status_missing_args(run_script):
    result = run_script("check_pr_status.py")
    assert result.returncode != 0
