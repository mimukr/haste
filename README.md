# Haste

Have a one-line fix and feel too busy to create an issue with the correct label and assignee, create a branch with the corresponding issue number and title, commit to that branch with an appropriate message, create a PR linked to that issue and set the issue to "In Progress" in the correct project?

Fear not! Use haste!

### Example

```bash
>: haste bug "The quickest fix of them all"
Created issue: https://github.com/ORG/repo/issues/1337
Created branch: 1337/the-quickest-fix-of-them-all
Checked out branch: 1337/the-quickest-fix-of-them-all
Committed changes with message: "Fix: The quickest fix of them all"
Pushed changes
Created PR: https://github.com/ORG/repo/pull/1337
```

## Installation

**1) Create virtual environment**

```bash
python3 -m venv ~/.cli-venv
source ~/.cli-venv/bin/activate
pip3 install pygithub requests
```

**2) Clone this repository**

```bash
cd ~/code
git clone https://github.com/mimukr/haste.git
```

**3) Add alias**

```bash
vim ~/.zshrc
alias haste="~/.cli-venv/bin/python3 ~/code/haste/haste.py"
```

## Usage

For haste to work, use within a git repository.

`haste <flow> <issue-title>`

### Flows

<ins>Base Flow</ins>

- Create an issue and a branch
- Commit and push either staged or all changes to that branch
- Create a PR for that issue and branch

<ins>Flows</ins>

- _issue:_ Issue without label
- _issue-safe:_ As above, but stop if no staged changes
- _issue-only:_ As above, but skip git commands and only create issue
- _bug:_ Issue with the bug label
- _bug-safe:_ As above, but stop if no staged changes
- _bug-only:_ As above, but skip git commands and only create issue
