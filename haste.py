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


def slugify(text: str) -> str:
    return text.lower().replace(" ", "-")


################################################################
# PyGithub wrappers
################################################################


def get_repo(gh: Github, repo_name: str) -> Repository:
    try:
        return gh.get_repo(f"LEGO/{repo_name}")
    except UnknownObjectException as ex:
        raise Exception(f"Repository LEGO/{repo_name} not found") from ex


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
    branch = repo.create_git_ref(f"refs/heads/{issue.number}/{slugify(issue_title)}", main.object.sha)
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


def get_project_issue(token: str, repo_name: str, issue_number: int) -> dict | None:
    query = """
    {
      repository(owner: "LEGO", name: "%s") {
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
        if time.time() > wait_until:
            raise Exception("Timed out waiting for issue to appear in project")
        res = get_project_issue(token, repo_name, issue_number)
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
    repo_name, issue_title = get_args()
    token = get_github_token()
    gh = Github(token)

    auth_user = gh.get_user()
    me = gh.get_user_by_id(auth_user.id)
    repo = get_repo(gh, repo_name)

    # Create issue, branch
    issue = create_issue(repo, issue_title, me)
    new_branch = create_branch(repo, issue)

    # Set status in project
    project_issue = wait_for_project_issue(token, repo_name, issue.number)
    project = project_issue["project"]

    status_field, option = get_status_option(token, project["id"], "Done")
    set_status(token, project["id"], project_issue["id"], status_field["id"], option["id"])
