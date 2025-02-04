import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from subprocess import run
from typing import Callable, TypeAlias

import requests
from github import Github
from github.Branch import Branch
from github.Issue import Issue
from github.NamedUser import NamedUser
from github.PullRequest import PullRequest
from github.Repository import Repository

################################################################
# Basic utility functions
################################################################


def get_args() -> tuple[str, str]:
    # TODO: Use actual argparse
    args = sys.argv[1:]
    if not len(args) == 2 or args[0] not in FLOWS:
        raise Exception(f"Usage: haste {'|'.join(FLOWS)} \"<issue-title>\"")

    flow = args[0]
    issue_title = args[1]
    return flow, issue_title


def run_command(command: str, allow_error: bool = False, on_error: Exception | None = None) -> str:
    result = run(command, shell=True, text=True, capture_output=True, check=False if on_error else not allow_error)
    if result.returncode != 0 and on_error:
        raise on_error
    return result.stdout.strip()


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
# Git CLI wrappers
################################################################


def has_staged_changes() -> bool:
    result = run_command("git diff --staged")
    return bool(result)


def get_local_repo() -> str:
    run_command("git rev-parse --is-inside-work-tree", on_error=Exception("Haste only works inside a git repository"))

    remote_url = run_command("git config --get remote.origin.url")
    match = re.search(r"github\.com[/:](?P<owner>.+?)/(?P<name>.+?)(\.git)?$", remote_url.strip("/"))
    if not match:
        raise Exception(f"Don't know what to do with {remote_url}")
    return f"{match.group('owner')}/{match.group('name')}"


def checkout_branch(branch: Branch):
    run_command("git fetch origin")
    run_command(f"git checkout -b {branch.name} origin/{branch.name}")
    print(f"Checked out branch: {branch.name}")


def commit_changes(message: str):
    if not has_staged_changes():
        run_command("git add --all")
    run_command(f'git commit -m "{message}"')
    print("Committed changes")


def push_changes():
    run_command("git push")
    print("Pushed changes")


################################################################
# PyGithub wrappers
################################################################


def create_issue(repo: Repository, title: str, assignee: NamedUser) -> Issue:
    issue = repo.create_issue(
        title=title,
        body="This issue was auto-created by https://github.com/mimukr/haste 🤖",
        assignee=assignee,
        labels=["bug"],
    )
    print(f"Created issue: {issue.html_url}")
    return issue


def create_branch(repo: Repository, issue: Issue) -> Branch:
    main = repo.get_git_ref("heads/main")
    ref = repo.create_git_ref(f"refs/heads/{issue.number}/{slugify(issue.title)}", main.object.sha)
    branch = repo.get_branch(ref.ref)
    print(f"Created branch: {branch.name}")
    return branch


def create_pull_request(repo: Repository, branch: Branch, issue: Issue) -> PullRequest:
    pr = repo.create_pull(
        base="main",
        head=branch.name,
        title=issue.title,
        body=f"Resolves #{issue.number}",
    )
    print(f"Created PR: {pr.html_url}")
    return pr


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


def get_project_issue(token: str, repo: Repository, issue_number: int) -> dict | None:
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
        repo.owner.login,
        repo.name,
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


def wait_for_project_issue(token: str, repo: Repository, issue_number: int) -> dict:
    wait_until = time.time() + 10
    while True:
        if time.time() > wait_until:
            raise Exception("Timed out waiting for issue to appear in project")
        res = get_project_issue(token, repo, issue_number)
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


def do_status_boogaroo(token: str, repo: Repository, issue: Issue, status: str):
    project_issue = wait_for_project_issue(token, repo, issue.number)
    project = project_issue["project"]

    status_field, option = get_status_option(token, project["id"], status)
    set_status(token, project["id"], project_issue["id"], status_field["id"], option["id"])


################################################################
# Flows
################################################################


@dataclass
class FlowContext:
    token: str
    me: NamedUser
    repo: Repository
    issue_title: str


Flow: TypeAlias = Callable[[FlowContext], None]


def bug_flow(ctx: FlowContext):
    issue = create_issue(ctx.repo, ctx.issue_title, ctx.me)
    new_branch = create_branch(ctx.repo, issue)

    checkout_branch(new_branch)
    commit_changes(f"Fix: {ctx.issue_title}")
    push_changes()

    create_pull_request(ctx.repo, new_branch, issue)

    do_status_boogaroo(ctx.token, ctx.repo, issue, "In progress")


FLOWS: dict[str, Flow] = {
    "bug": bug_flow,
}

################################################################
# Main
################################################################


def main():
    local_repo = get_local_repo()

    flow_name, issue_title = get_args()
    token = get_github_token()
    gh = Github(token)

    auth_user = gh.get_user()
    me = gh.get_user_by_id(auth_user.id)
    repo = gh.get_repo(local_repo)

    FLOWS[flow_name](
        FlowContext(
            token=token,
            me=me,
            repo=repo,
            issue_title=issue_title,
        )
    )


if __name__ == "__main__":
    main()
