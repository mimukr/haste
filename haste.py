import sys
import time
from pathlib import Path

import requests
from github import Github, UnknownObjectException
from github.Issue import Issue
from github.NamedUser import NamedUser
from github.Repository import Repository

from constants import STATUS_FIELD_ID


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
    issue = repo.create_issue(
        title=title,
        body="This issue was created by https://github.com/mimukr/haste",
        assignee=assignee,
        labels=["bug"],
    )
    print(f"Created issue {issue.html_url}")
    return issue


def get_project_issue(
    token: str,
    repo_name: str,
    issue_number: int,
) -> dict | None:
    query = """
    query {
      repository(owner:"LEGO", name:"%s") {
        issue(number: %s) {
          projectItems(first: 2) {
            nodes {
              id
              project {
                id
              }
            }
          }
        }
      }
    }
    """ % (
        repo_name,
        issue_number,
    )
    res = graphql(token, query)
    project_issues = res["data"]["repository"]["issue"]["projectItems"]["nodes"]
    if len(project_issues) == 0:
        return None
    elif len(project_issues) > 1:
        raise Exception("More than one project issue found")
    else:
        return project_issues[0]


def wait_for_project_issue(token: str, repo_name: str, issue_number: int) -> dict:
    wait_until = time.time() + 10
    while True:
        print("Waiting for issue to appear in project...")
        if time.time() > wait_until:
            raise Exception("Timed out waiting for issue to appear in project")
        res = get_project_issue(token, repo_name, issue_number)
        if res:
            return res
        time.sleep(1)


def graphql(token: str, query: str, variables: dict | None = None) -> dict:
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
    project_issue = wait_for_project_issue(token, repo_name, issue.number)
    project_issue_id = project_issue["id"]
    project_id = project_issue["project"]["id"]
