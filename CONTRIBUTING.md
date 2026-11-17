# Contributing to PharmAssist

These rules apply to all PharmAssist repositories (backend, client, data).
Every change is linked to a Jira issue and reviewed by at least one other team member (NFR-7.3).

## 1. Branches

- `main` always contains working, reviewed code. Nobody pushes to `main` directly.
- Create one short-lived branch per Jira issue, starting from the latest `main`.
- Branch name: `<type>/<JIRA-KEY>-<short-description>` in lowercase, words separated by `-`.

| Type | Use for | Example |
|---|---|---|
| `feature/` | New functionality | `feature/SCRUM-51-registration-api` |
| `fix/` | Bug fixes | `fix/SCRUM-60-login-error` |
| `docs/` | Documentation only | `docs/SCRUM-62-data-access-report` |
| `chore/` | Setup, configuration, dependencies | `chore/SCRUM-49-gitignore` |

- Delete the branch after it is merged.

## 2. Commit messages

- Start every commit message with the Jira issue key, followed by a short description in English:

  ```
  SCRUM-51: add registration endpoint
  SCRUM-60: fix empty password validation
  ```

- Use the imperative mood ("add", "fix", "update") and keep the first line under about 72 characters.
- The issue key makes the commit appear in the Jira issue's Development panel.

## 3. Pull requests

1. Push your branch and open a pull request into `main`.
2. Start the PR title with the issue key: `SCRUM-51: Registration API`.
3. Fill in the pull request template (linked issue, what changed, how it was tested).
4. Request a review from at least one other team member.
5. Merge only after at least **one approval** and after review comments are resolved.
6. Merge with **Squash and merge**, so that `main` gets one commit per issue with the issue key in its message.
7. After merging, delete the branch and move the Jira issue to the next status.

Keep pull requests small: one issue per pull request.

## 4. Never commit

- Passwords, API keys, database credentials or `.env` files. Use `.env.example` with placeholder values instead.
- Personal or health data of real people.
- TİTCK KÜB/KT PDF files in bulk (data repository): commit the scripts, the list of document URLs and a few sample documents only.

## 5. Branch protection

`main` is protected in all repositories: changes enter only through a pull request with at least one approval.
