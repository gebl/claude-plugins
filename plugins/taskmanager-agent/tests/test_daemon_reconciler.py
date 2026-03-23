"""Tests for daemon reconciler module."""

from taskmanager.daemon.reconciler import (
    _cleanup_worktree,
    _extract_pr_url,
    _mirror_pr_comments,
    _auto_close_review,
    reconcile_review_issues,
)


class TestExtractPrUrl:
    def test_standard_description(self):
        desc = (
            "PR submitted for review: https://forgejo.example.com/Org/repo/pulls/42\n\n"
            "Summary of work done\n\n"
            "Please review the PR and either merge it or add a comment with feedback."
        )
        assert _extract_pr_url(desc) == "https://forgejo.example.com/Org/repo/pulls/42"

    def test_with_port(self):
        desc = (
            "PR submitted for review: https://forgejo.example.com:3000/Org/repo/pulls/7"
        )
        assert (
            _extract_pr_url(desc) == "https://forgejo.example.com:3000/Org/repo/pulls/7"
        )

    def test_pull_singular(self):
        desc = "Check this PR: https://github.com/owner/repo/pull/123"
        assert _extract_pr_url(desc) == "https://github.com/owner/repo/pull/123"

    def test_no_url(self):
        desc = "Please review the design document and provide feedback."
        assert _extract_pr_url(desc) is None

    def test_non_pr_url(self):
        desc = "See https://example.com/docs for more info"
        assert _extract_pr_url(desc) is None

    def test_markdown_link_syntax(self):
        desc = (
            "PR submitted for review: "
            "[https://forgejo.example.com/Org/repo/pulls/29]"
            "(<https://forgejo.example.com/Org/repo/pulls/29>)"
        )
        assert _extract_pr_url(desc) == "https://forgejo.example.com/Org/repo/pulls/29"

    def test_empty_description(self):
        assert _extract_pr_url("") is None


class TestAutoCloseReview:
    def test_posts_comment_and_marks_done(self, monkeypatch):
        calls = []

        def mock_run(cmd, **kwargs):
            calls.append(cmd)

            class Result:
                returncode = 0

            return Result()

        monkeypatch.setattr("subprocess.run", mock_run)
        monkeypatch.setattr(
            "taskmanager.daemon.reconciler._find_scripts_dir",
            lambda: __import__("pathlib").Path("/scripts"),
        )
        monkeypatch.setattr(
            "taskmanager.daemon.reconciler._find_venv_python",
            lambda: "python",
        )
        # Stub out cleanup so it doesn't interfere
        monkeypatch.setattr(
            "taskmanager.daemon.reconciler._cleanup_worktree",
            lambda issue, identifier: None,
        )

        issue = {"id": "review-123", "identifier": "LAN-5"}
        _auto_close_review(issue, "PR was merged")

        assert len(calls) == 2
        # First call: post comment
        assert "tm_save_comment.py" in calls[0][1]
        assert "--issue-id" in calls[0]
        assert "review-123" in calls[0]
        assert "Auto-closed: PR was merged." in calls[0][-1]
        # Second call: mark done
        assert "tm_save_issue.py" in calls[1][1]
        assert "Done" in calls[1]

    def test_cleanup_called_only_for_merged(self, monkeypatch):
        def mock_run(cmd, **kwargs):
            class Result:
                returncode = 0

            return Result()

        monkeypatch.setattr("subprocess.run", mock_run)
        monkeypatch.setattr(
            "taskmanager.daemon.reconciler._find_scripts_dir",
            lambda: __import__("pathlib").Path("/scripts"),
        )
        monkeypatch.setattr(
            "taskmanager.daemon.reconciler._find_venv_python",
            lambda: "python",
        )

        cleanup_calls = []
        monkeypatch.setattr(
            "taskmanager.daemon.reconciler._cleanup_worktree",
            lambda issue, identifier: cleanup_calls.append(identifier),
        )

        issue = {"id": "review-123", "identifier": "LAN-5"}

        _auto_close_review(issue, "PR was merged")
        assert cleanup_calls == ["LAN-5"]

        cleanup_calls.clear()
        _auto_close_review(issue, "PR was closed")
        assert cleanup_calls == []


class TestCleanupWorktree:
    def test_removes_worktree_and_branch(self, monkeypatch, tmp_path):
        # Set up a fake repo with a worktree dir
        repo_path = tmp_path / "my-repo"
        repo_path.mkdir()
        worktree_dir = repo_path / ".worktrees" / "gabe/feature-branch"
        worktree_dir.mkdir(parents=True)

        monkeypatch.setattr(
            "taskmanager.daemon.reconciler._run_dict_script",
            lambda script, *args: {
                "identifier": "LAN-10",
                "branch_name": "gabe/feature-branch",
                "project_id": "proj-1",
            },
        )
        monkeypatch.setattr(
            "taskmanager.daemon.reconciler.load_config",
            lambda: {
                "projects": [
                    {"id": "proj-1", "local_path": str(repo_path)},
                ]
            },
        )

        git_calls = []

        def mock_run(cmd, **kwargs):
            git_calls.append(cmd)

            class Result:
                returncode = 0

            return Result()

        monkeypatch.setattr("subprocess.run", mock_run)

        issue = {"id": "review-1", "identifier": "LAN-11", "parent_id": "parent-1"}
        _cleanup_worktree(issue, "LAN-11")

        assert len(git_calls) == 2
        # Worktree remove
        assert git_calls[0][:3] == ["git", "worktree", "remove"]
        assert str(worktree_dir) in git_calls[0][3]
        assert "--force" in git_calls[0]
        # Branch delete
        assert git_calls[1] == ["git", "branch", "-d", "gabe/feature-branch"]

    def test_skips_when_no_parent(self, monkeypatch):
        git_calls = []
        monkeypatch.setattr(
            "subprocess.run",
            lambda cmd, **kw: git_calls.append(cmd),
        )

        issue = {"id": "review-1", "identifier": "LAN-11"}
        _cleanup_worktree(issue, "LAN-11")
        assert git_calls == []

    def test_skips_when_no_local_path(self, monkeypatch):
        monkeypatch.setattr(
            "taskmanager.daemon.reconciler._run_dict_script",
            lambda script, *args: {
                "identifier": "LAN-10",
                "branch_name": "gabe/feature-branch",
                "project_id": "proj-1",
            },
        )
        monkeypatch.setattr(
            "taskmanager.daemon.reconciler.load_config",
            lambda: {"projects": []},
        )

        git_calls = []
        monkeypatch.setattr(
            "subprocess.run",
            lambda cmd, **kw: git_calls.append(cmd),
        )

        issue = {"id": "review-1", "identifier": "LAN-11", "parent_id": "parent-1"}
        _cleanup_worktree(issue, "LAN-11")
        assert git_calls == []

    def test_skips_worktree_remove_when_dir_missing(self, monkeypatch, tmp_path):
        repo_path = tmp_path / "my-repo"
        repo_path.mkdir()
        # No worktree directory created

        monkeypatch.setattr(
            "taskmanager.daemon.reconciler._run_dict_script",
            lambda script, *args: {
                "identifier": "LAN-10",
                "branch_name": "gabe/feature-branch",
                "project_id": "proj-1",
            },
        )
        monkeypatch.setattr(
            "taskmanager.daemon.reconciler.load_config",
            lambda: {
                "projects": [
                    {"id": "proj-1", "local_path": str(repo_path)},
                ]
            },
        )

        git_calls = []

        def mock_run(cmd, **kwargs):
            git_calls.append(cmd)

            class Result:
                returncode = 0

            return Result()

        monkeypatch.setattr("subprocess.run", mock_run)

        issue = {"id": "review-1", "identifier": "LAN-11", "parent_id": "parent-1"}
        _cleanup_worktree(issue, "LAN-11")

        # Only branch delete, no worktree remove
        assert len(git_calls) == 1
        assert git_calls[0] == ["git", "branch", "-d", "gabe/feature-branch"]


class TestMirrorPrComments:
    def test_mirrors_new_comments(self, monkeypatch):
        monkeypatch.setattr(
            "taskmanager.daemon.reconciler._run_list_script",
            lambda *a: [],  # No existing comments
        )

        post_calls = []

        def mock_run(cmd, **kwargs):
            post_calls.append(cmd)

            class Result:
                returncode = 0

            return Result()

        monkeypatch.setattr("subprocess.run", mock_run)
        monkeypatch.setattr(
            "taskmanager.daemon.reconciler._find_scripts_dir",
            lambda: __import__("pathlib").Path("/scripts"),
        )
        monkeypatch.setattr(
            "taskmanager.daemon.reconciler._find_venv_python",
            lambda: "python",
        )

        issue = {"id": "review-1", "identifier": "LAN-5"}
        pr_comments = [
            {
                "author": "gabe",
                "body": "Fix the error handling",
                "state": "",
                "source": "comment",
            },
        ]
        _mirror_pr_comments(issue, pr_comments)

        assert len(post_calls) == 1
        body = post_calls[0][-1]
        assert body == "**[PR Comment]** @gabe: Fix the error handling"

    def test_skips_already_mirrored(self, monkeypatch):
        monkeypatch.setattr(
            "taskmanager.daemon.reconciler._run_list_script",
            lambda *a: [
                {"body": "**[PR Comment]** @gabe: Fix the error handling"},
            ],
        )

        post_calls = []

        def mock_run(cmd, **kwargs):
            post_calls.append(cmd)

            class Result:
                returncode = 0

            return Result()

        monkeypatch.setattr("subprocess.run", mock_run)
        monkeypatch.setattr(
            "taskmanager.daemon.reconciler._find_scripts_dir",
            lambda: __import__("pathlib").Path("/scripts"),
        )
        monkeypatch.setattr(
            "taskmanager.daemon.reconciler._find_venv_python",
            lambda: "python",
        )

        issue = {"id": "review-1", "identifier": "LAN-5"}
        pr_comments = [
            {
                "author": "gabe",
                "body": "Fix the error handling",
                "state": "",
                "source": "comment",
            },
        ]
        _mirror_pr_comments(issue, pr_comments)

        assert len(post_calls) == 0

    def test_skips_empty_body(self, monkeypatch):
        monkeypatch.setattr(
            "taskmanager.daemon.reconciler._run_list_script",
            lambda *a: [],
        )

        post_calls = []

        def mock_run(cmd, **kwargs):
            post_calls.append(cmd)

            class Result:
                returncode = 0

            return Result()

        monkeypatch.setattr("subprocess.run", mock_run)
        monkeypatch.setattr(
            "taskmanager.daemon.reconciler._find_scripts_dir",
            lambda: __import__("pathlib").Path("/scripts"),
        )
        monkeypatch.setattr(
            "taskmanager.daemon.reconciler._find_venv_python",
            lambda: "python",
        )

        issue = {"id": "review-1", "identifier": "LAN-5"}
        pr_comments = [
            {"author": "bot", "body": "", "state": "", "source": "review"},
        ]
        _mirror_pr_comments(issue, pr_comments)

        assert len(post_calls) == 0


class TestReconcileReviewIssues:
    def _make_review_issue(self, issue_id, description, status="Todo"):
        return {
            "id": issue_id,
            "identifier": f"LAN-{issue_id}",
            "description": description,
            "status": {"name": status},
        }

    def test_auto_closes_merged_pr(self, monkeypatch):
        review = self._make_review_issue(
            "r1",
            "PR submitted for review: https://forgejo.example.com/Org/repo/pulls/42\n\nSummary",
        )
        monkeypatch.setattr(
            "taskmanager.daemon.reconciler._run_list_script",
            lambda script, *args: [review] if "tm_list_issues" in script else [],
        )
        monkeypatch.setattr(
            "taskmanager.daemon.reconciler._run_dict_script",
            lambda script, *args: {
                "state": "merged",
                "comments": [],
                "pr_url": "https://forgejo.example.com/Org/repo/pulls/42",
                "pr_number": 42,
            },
        )

        closed = []
        monkeypatch.setattr(
            "taskmanager.daemon.reconciler._auto_close_review",
            lambda issue, reason: closed.append((issue["id"], reason)),
        )

        reconcile_review_issues()
        assert closed == [("r1", "PR was merged")]

    def test_mirrors_comments_on_open_pr(self, monkeypatch):
        review = self._make_review_issue(
            "r2",
            "PR submitted for review: https://forgejo.example.com/Org/repo/pulls/10\n\nSummary",
        )
        monkeypatch.setattr(
            "taskmanager.daemon.reconciler._run_list_script",
            lambda script, *args: [review] if "tm_list_issues" in script else [],
        )
        pr_comments = [
            {"author": "gabe", "body": "Needs work", "state": "", "source": "comment"},
        ]
        monkeypatch.setattr(
            "taskmanager.daemon.reconciler._run_dict_script",
            lambda script, *args: {
                "state": "open",
                "comments": pr_comments,
                "pr_url": "https://forgejo.example.com/Org/repo/pulls/10",
                "pr_number": 10,
            },
        )

        mirrored = []
        monkeypatch.setattr(
            "taskmanager.daemon.reconciler._mirror_pr_comments",
            lambda issue, comments: mirrored.append((issue["id"], len(comments))),
        )

        reconcile_review_issues()
        assert mirrored == [("r2", 1)]

    def test_skips_done_issues(self, monkeypatch):
        review = self._make_review_issue(
            "r3",
            "PR submitted for review: https://forgejo.example.com/Org/repo/pulls/5\n\nSummary",
            status="Done",
        )
        monkeypatch.setattr(
            "taskmanager.daemon.reconciler._run_list_script",
            lambda script, *args: [review] if "tm_list_issues" in script else [],
        )

        dict_calls = []
        monkeypatch.setattr(
            "taskmanager.daemon.reconciler._run_dict_script",
            lambda script, *args: dict_calls.append(args),
        )

        reconcile_review_issues()
        assert dict_calls == []

    def test_skips_non_pr_review(self, monkeypatch):
        review = self._make_review_issue(
            "r4",
            "Please review the design document and provide feedback.",
        )
        monkeypatch.setattr(
            "taskmanager.daemon.reconciler._run_list_script",
            lambda script, *args: [review] if "tm_list_issues" in script else [],
        )

        dict_calls = []
        monkeypatch.setattr(
            "taskmanager.daemon.reconciler._run_dict_script",
            lambda script, *args: dict_calls.append(args),
        )

        reconcile_review_issues()
        assert dict_calls == []

    def test_no_action_on_open_no_comments(self, monkeypatch):
        review = self._make_review_issue(
            "r5",
            "PR submitted for review: https://forgejo.example.com/Org/repo/pulls/1\n\nSummary",
        )
        monkeypatch.setattr(
            "taskmanager.daemon.reconciler._run_list_script",
            lambda script, *args: [review] if "tm_list_issues" in script else [],
        )
        monkeypatch.setattr(
            "taskmanager.daemon.reconciler._run_dict_script",
            lambda script, *args: {
                "state": "open",
                "comments": [],
                "pr_url": "https://forgejo.example.com/Org/repo/pulls/1",
                "pr_number": 1,
            },
        )

        closed = []
        mirrored = []
        monkeypatch.setattr(
            "taskmanager.daemon.reconciler._auto_close_review",
            lambda issue, reason: closed.append(issue["id"]),
        )
        monkeypatch.setattr(
            "taskmanager.daemon.reconciler._mirror_pr_comments",
            lambda issue, comments: mirrored.append(issue["id"]),
        )

        reconcile_review_issues()
        assert closed == []
        assert mirrored == []
