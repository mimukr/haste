import re
import subprocess
import sys
import time
from pathlib import Path

import requests
from github import Github, UnknownObjectException
from github.GitRef import GitRef
from github.Issue import Issue
from github.NamedUser import NamedUser
from github.Repository import Repository

################################################################
# Basic utility functions
################################################################


class RepoInfo:
    def __init__(self, owner: str, name: str) -> None:
        self.owner = owner
        self.name = name

    def __str__(self) -> str:
        return f"{self.owner}/{self.name}"


def get_args() -> tuple[RepoInfo, str]:
    args = sys.argv[1:]
    detected_repo = try_get_repo_info()
    if not len(args) == (1 if detected_repo else 2):
        raise Exception("Usage: haste <repo> <issue-title>")
    repo_info = detected_repo or RepoInfo("LEGO", args[0])
    issue_title = args[-1]
    return repo_info, issue_title


def get_github_token() -> str:
    git_creds_file = Path.home() / ".git-credentials"
    if not git_creds_file.exists():
        raise Exception("No ~/.git-credentials file found")
    with git_creds_file.open() as f:
        for line in f:
            if "github.com" in line:
                return line.split(":")[-1].split("@")[0].strip()
    raise Exception("No github.com token found in ~/.git-credentials")


def slugify(text: str) -> str:
    return text.lower().replace(" ", "-")


def run_command(command: str) -> str | None:
    """Executes a system command and returns the output."""
    result = subprocess.run(command, shell=True, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        # print(f"Command failed: {command}\nError: {result.stderr}")
        return None
    return result.stdout.strip()


def try_get_repo_info() -> RepoInfo | None:
    """Tries to get the repo name from the current git repository from the current working dir."""
    result = run_command("git rev-parse --is-inside-work-tree")
    if not result:
        return None
    is_inside = result.lower() == "true"
    if is_inside:
        remote_url = run_command("git config --get remote.origin.url")
        if not remote_url:
            return None
        # print(f"Detected remote URL: {remote_url}")
        # This regex matches both HTTPS and SSH URLs and extracts the owner and repo name
        match = re.search(r"github\.com[/:](?P<owner>.+?)/(?P<name>.+?)(\.git)?$", remote_url.strip("/"))
        if match:
            return RepoInfo(match.group("owner"), match.group("name"))
    return None


################################################################
# PyGithub wrappers
################################################################


def get_repo(gh: Github, repo_info: RepoInfo) -> Repository:
    try:
        return gh.get_repo(str(repo_info))
    except UnknownObjectException as ex:
        raise Exception(f"Repository {repo_info} not found") from ex


def create_issue(repo: Repository, title: str, assignee: NamedUser) -> Issue:
    issue = repo.create_issue(
        title=title,
        body="This issue was auto-created by https://github.com/mimukr/haste 🤖",
        assignee=assignee,
        labels=["bug"],
    )
    print(f"Created issue: {issue.html_url}")
    return issue


def create_branch(repo: Repository, issue: Issue) -> GitRef:
    main = repo.get_git_ref("heads/main")
    branch = repo.create_git_ref(f"refs/heads/{issue.number}/{slugify(issue.title)}", main.object.sha)
    print(f"Created branch: {branch.ref.removeprefix('refs/heads/')}")
    return branch


################################################################
# Helpers for GitHub Projects using GraphQL
################################################################


def graphql(token: str, query: str, variables: dict | None = None) -> dict:
    res = requests.post(
        "https://api.github.com/graphql",
        headers={"Authorization": f"bearer {token}"},
        json={"query": query, "variables": variables},
    )
    res.raise_for_status()
    res_json = res.json()
    if errors := res_json.get("errors"):
        raise Exception(errors)
    return res_json


def get_project_issue(token: str, repo_info: RepoInfo, issue_number: int) -> dict | None:
    query = """
    {
      repository(owner: "%s", name: "%s") {
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
        repo_info.owner,
        repo_info.name,
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


def wait_for_project_issue(token: str, repo_info: RepoInfo, issue_number: int) -> dict:
    wait_until = time.time() + 10
    while True:
        if time.time() > wait_until:
            raise Exception("Timed out waiting for issue to appear in project")
        res = get_project_issue(token, repo_info, issue_number)
        if res:
            return res
        print("Waiting for issue to appear in project...")
        time.sleep(1)


def get_project_fields(token: str, project_id: int) -> list[dict]:
    query = """
    {
      node(id: "%s") {
        ... on ProjectV2 {
          fields(first: 100) {
            nodes {
              ... on ProjectV2SingleSelectField {
                id
                name
                options {
                  id
                  name
                }
              }
            }
          }
        }
      }
    }
    """ % (
        project_id,
    )
    res = graphql(token, query)
    return res["data"]["node"]["fields"]["nodes"]


def get_status_option(token: str, project_id: int, option_name: str) -> tuple[dict, dict]:
    fields = get_project_fields(token, project_id)
    status_field = next((f for f in fields if f.get("name") == "Status"), None)
    if not status_field:
        raise Exception("Status field not found")
    option = next((o for o in status_field["options"] if o.get("name") == option_name), None)
    if not option:
        raise Exception(f"{option_name} option not found")
    return status_field, option


def set_status(token: str, project_id: int, item_id: int, field_id: str, option_id: str):
    query = """
    mutation {
      updateProjectV2ItemFieldValue(
        input: {projectId: "%s", itemId: "%s", fieldId: "%s", value: {singleSelectOptionId: "%s"}}
      ) {
        clientMutationId
      }
    }
    """ % (
        project_id,
        item_id,
        field_id,
        option_id,
    )
    graphql(token, query)


################################################################
# Main
################################################################

if __name__ == "__main__":
    repo_info, issue_title = get_args()
    token = get_github_token()
    gh = Github(token)

    auth_user = gh.get_user()
    me = gh.get_user_by_id(auth_user.id)
    repo = get_repo(gh, repo_info)

    # Create issue, branch
    issue = create_issue(repo, issue_title, me)
    new_branch = create_branch(repo, issue)

    # Set status in project
    project_issue = wait_for_project_issue(token, repo_info, issue.number)
    project = project_issue["project"]

    status_field, option = get_status_option(token, project["id"], "Done")
    set_status(token, project["id"], project_issue["id"], status_field["id"], option["id"])
