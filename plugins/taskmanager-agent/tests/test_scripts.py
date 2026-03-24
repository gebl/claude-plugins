"""Tests for CLI scripts in scripts/."""

import pytest

SCRIPTS = [
    "tm_list_issues.py",
    "tm_get_issue.py",
    "tm_save_issue.py",
    "tm_list_comments.py",
    "tm_save_comment.py",
    "tm_list_projects.py",
    "tm_save_project.py",
    "tm_get_project_links.py",
    "tm_create_project_link.py",
    "tm_list_statuses.py",
    "tm_create_status.py",
    "tm_list_labels.py",
    "tm_create_label.py",
    "tm_create_document.py",
    "tm_get_user.py",
]


@pytest.mark.parametrize("script", SCRIPTS)
def test_script_has_help(run_script, script):
    result = run_script(script, "--help")
    assert result.returncode == 0
    assert "usage" in result.stdout.lower() or "options" in result.stdout.lower()


def test_create_forgejo_pr_missing_token(run_script):
    result = run_script(
        "create_forgejo_pr.py",
        "--repo-url",
        "https://forgejo.example.com/Org/repo",
        "--branch",
        "test",
        "--title",
        "test",
        "--body",
        "test",
        env_override={"TASKMANAGER_AGENT_FORGEJO_TOKEN": ""},
    )
    assert result.returncode != 0
    assert "TASKMANAGER_AGENT_FORGEJO_TOKEN" in result.stderr


def test_create_forgejo_pr_has_help(run_script):
    result = run_script("create_forgejo_pr.py", "--help")
    assert result.returncode == 0


def test_create_pr_has_help(run_script):
    result = run_script("create_pr.py", "--help")
    assert result.returncode == 0


def test_create_pr_missing_token(run_script):
    result = run_script(
        "create_pr.py",
        "--repo-url",
        "https://forgejo.example.com/Org/repo",
        "--branch",
        "test",
        "--title",
        "test",
        "--body",
        "test",
        env_override={"TASKMANAGER_AGENT_FORGEJO_TOKEN": ""},
    )
    assert result.returncode != 0
    assert "TASKMANAGER_AGENT_FORGEJO_TOKEN" in result.stderr


def test_create_forgejo_repo_has_help(run_script):
    result = run_script("create_forgejo_repo.py", "--help")
    assert result.returncode == 0
    assert "name" in result.stdout.lower()


def test_create_forgejo_repo_missing_token(run_script):
    result = run_script(
        "create_forgejo_repo.py",
        "--name",
        "test-repo",
        env_override={"TASKMANAGER_AGENT_FORGEJO_TOKEN": "", "TASKMANAGER_AGENT_FORGEJO_URL": "https://example.com"},
    )
    assert result.returncode != 0
    assert "TASKMANAGER_AGENT_FORGEJO_TOKEN" in result.stderr


def test_create_forgejo_repo_missing_url(run_script):
    result = run_script(
        "create_forgejo_repo.py",
        "--name",
        "test-repo",
        env_override={"TASKMANAGER_AGENT_FORGEJO_TOKEN": "test-token", "TASKMANAGER_AGENT_FORGEJO_URL": ""},
    )
    assert result.returncode != 0
    assert "TASKMANAGER_AGENT_FORGEJO_URL" in result.stderr
