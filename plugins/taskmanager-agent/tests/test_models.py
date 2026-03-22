import json


from taskmanager.models import (
    Comment,
    Issue,
    Label,
    Project,
    ProjectLink,
    Status,
    Team,
    User,
    Document,
)


def make_status(type_: str = "started") -> Status:
    return Status(id="s1", name="In Progress", type=type_)


def make_label() -> Label:
    return Label(id="l1", name="bug", color="#ff0000")


def make_issue(**kwargs) -> Issue:
    defaults = dict(
        id="i1",
        identifier="LAN-42",
        title="Fix the thing",
        description="It is broken",
        status=make_status(),
        priority=2,
        project_id="p1",
        project_name="My Project",
        labels=[make_label()],
        parent_id=None,
    )
    defaults.update(kwargs)
    return Issue(**defaults)


class TestStatus:
    def test_to_dict_returns_dict(self):
        s = make_status()
        d = s.to_dict()
        assert isinstance(d, dict)

    def test_to_dict_contains_fields(self):
        s = Status(id="s1", name="Backlog", type="backlog")
        d = s.to_dict()
        assert d == {"id": "s1", "name": "Backlog", "type": "backlog"}

    def test_json_roundtrip(self):
        s = make_status()
        d = s.to_dict()
        restored = json.loads(json.dumps(d))
        assert restored["id"] == s.id
        assert restored["name"] == s.name
        assert restored["type"] == s.type


class TestLabel:
    def test_to_dict_default_scope(self):
        label = make_label()
        d = label.to_dict()
        assert d["scope"] == "issue"

    def test_to_dict_project_scope(self):
        label = Label(id="l2", name="feature", color="#00ff00", scope="project")
        d = label.to_dict()
        assert d["scope"] == "project"

    def test_json_roundtrip(self):
        label = make_label()
        restored = json.loads(json.dumps(label.to_dict()))
        assert restored["name"] == label.name
        assert restored["color"] == label.color


class TestComment:
    def test_to_dict_contains_all_fields(self):
        c = Comment(
            id="c1", issue_id="i1", body="Looks good", created_at="2026-01-01T00:00:00Z"
        )
        d = c.to_dict()
        assert d == {
            "id": "c1",
            "issue_id": "i1",
            "body": "Looks good",
            "created_at": "2026-01-01T00:00:00Z",
            "user_id": "",
            "user_name": "",
        }

    def test_to_dict_with_user(self):
        c = Comment(
            id="c1",
            issue_id="i1",
            body="Fix this",
            created_at="2026-01-01T00:00:00Z",
            user_id="u1",
            user_name="Gabe",
        )
        d = c.to_dict()
        assert d["user_id"] == "u1"
        assert d["user_name"] == "Gabe"

    def test_json_roundtrip(self):
        c = Comment(
            id="c2", issue_id="i2", body="Hello", created_at="2026-02-01T00:00:00Z"
        )
        restored = json.loads(json.dumps(c.to_dict()))
        assert restored["body"] == c.body
        assert restored["issue_id"] == c.issue_id


class TestIssue:
    def test_to_dict_basic_fields(self):
        issue = make_issue()
        d = issue.to_dict()
        assert d["id"] == "i1"
        assert d["identifier"] == "LAN-42"
        assert d["title"] == "Fix the thing"
        assert d["priority"] == 2

    def test_to_dict_nested_status(self):
        issue = make_issue()
        d = issue.to_dict()
        assert isinstance(d["status"], dict)
        assert d["status"]["id"] == "s1"
        assert d["status"]["type"] == "started"

    def test_to_dict_nested_labels(self):
        issue = make_issue()
        d = issue.to_dict()
        assert isinstance(d["labels"], list)
        assert len(d["labels"]) == 1
        assert d["labels"][0]["name"] == "bug"

    def test_to_dict_defaults(self):
        issue = make_issue()
        d = issue.to_dict()
        assert d["blocked_by"] == []
        assert d["url"] == ""
        assert d["branch_name"] is None

    def test_to_dict_optional_fields(self):
        issue = make_issue(
            blocked_by=["i2", "i3"],
            url="https://linear.app/issue/LAN-42",
            branch_name="fix/the-thing",
        )
        d = issue.to_dict()
        assert d["blocked_by"] == ["i2", "i3"]
        assert d["url"] == "https://linear.app/issue/LAN-42"
        assert d["branch_name"] == "fix/the-thing"

    def test_json_roundtrip(self):
        issue = make_issue()
        raw = json.dumps(issue.to_dict())
        restored = json.loads(raw)
        assert restored["identifier"] == "LAN-42"
        assert restored["status"]["name"] == "In Progress"
        assert restored["labels"][0]["color"] == "#ff0000"

    def test_none_project_fields(self):
        issue = make_issue(project_id=None, project_name=None)
        d = issue.to_dict()
        assert d["project_id"] is None
        assert d["project_name"] is None


class TestProject:
    def test_to_dict(self):
        p = Project(id="p1", name="My Project", url="https://linear.app/project/p1")
        d = p.to_dict()
        assert d["id"] == "p1"
        assert d["labels"] == []

    def test_json_roundtrip(self):
        p = Project(
            id="p2", name="Another", url="https://example.com", labels=[make_label()]
        )
        restored = json.loads(json.dumps(p.to_dict()))
        assert restored["labels"][0]["name"] == "bug"


class TestProjectLink:
    def test_to_dict(self):
        pl = ProjectLink(id="pl1", label="Docs", url="https://docs.example.com")
        d = pl.to_dict()
        assert d == {"id": "pl1", "label": "Docs", "url": "https://docs.example.com"}


class TestUser:
    def test_to_dict_with_email(self):
        u = User(id="u1", name="Alice", email="alice@example.com")
        d = u.to_dict()
        assert d["email"] == "alice@example.com"

    def test_to_dict_default_email(self):
        u = User(id="u2", name="Bob")
        d = u.to_dict()
        assert d["email"] == ""


class TestTeam:
    def test_to_dict(self):
        t = Team(id="t1", name="Engineering", key="ENG")
        d = t.to_dict()
        assert d == {"id": "t1", "name": "Engineering", "key": "ENG"}


class TestDocument:
    def test_to_dict_defaults(self):
        doc = Document(id="d1", title="My Doc")
        d = doc.to_dict()
        assert d["url"] == ""

    def test_to_dict_with_url(self):
        doc = Document(id="d2", title="Spec", url="https://linear.app/doc/d2")
        d = doc.to_dict()
        assert d["url"] == "https://linear.app/doc/d2"
