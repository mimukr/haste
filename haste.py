import sys
from pathlib import Path

from github import Github, UnknownObjectException
from github.Repository import Repository


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


if __name__ == "__main__":
    repo_name, issue_title = get_args()
    gh = Github(get_github_token())

    repo = get_repo(gh, repo_name)
