import sys
from pathlib import Path

import requests
from github import Github, UnknownObjectException
from github.Issue import Issue
from github.NamedUser import NamedUser
from github.Repository import Repository

from constants import CAP_PROJECT_ID, STATUS_FIELD_ID


def get_args() -> tuple[str, str]:
    args = sys.argv[1:]
    if not len(args) == 2:
        raise Exception("Usage: haste <repo> <issue-title>")
    repo_name = args[0]
    issue_title = args[1]
    return repo_name, issue_title


def get_github_token() -> str:
    git_creds_file = Path.home() / ".git-credentials"
    if not git_creds_file.exists():
        raise Exception("No ~/.git-credentials file found")
    with git_creds_file.open() as f:
        for line in f:
            if "github.com" in line:
                return line.split(":")[-1].split("@")[0].strip()
    raise Exception("No github.com token found in ~/.git-credentials")


def get_repo(gh: Github, repo_name: str) -> Repository:
    try:
        return gh.get_repo(f"LEGO/{repo_name}")
    except UnknownObjectException as ex:
        raise Exception(f"Repository LEGO/{repo_name} not found") from ex


def create_issue(repo: Repository, title: str, assignee: NamedUser) -> Issue:
    return repo.create_issue(
        title=title,
        body="This issue was created by https://github.com/mimukr/haste",
        assignee=assignee,
        labels=["bug"],
    )


def graphql(token: str, query: str, variables: dict) -> dict:
    req = requests.post(
        "https://api.github.com/graphql",
        headers={"Authorization": f"bearer {token}"},
        json={"query": query, "variables": variables},
    )
    req.raise_for_status()
    return req.json()


if __name__ == "__main__":
    repo_name, issue_title = get_args()
    token = get_github_token()
    gh = Github(token)

    auth_user = gh.get_user()
    me = gh.get_user_by_id(auth_user.id)
    repo = get_repo(gh, repo_name)

    issue = create_issue(repo, issue_title, me)
    print(f"Created issue {issue.html_url}")
