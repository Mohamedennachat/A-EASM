# Contributing

Thanks for contributing. To keep `main` and `develop` stable, all changes land
through a feature branch and a pull request into `develop`. Never commit
directly to `main` or `develop`.

## Workflow

1. Sync `develop` before starting:
   ```bash
   git checkout develop
   git pull origin develop
   ```

2. Create a branch per feature. One branch is one focused change. Use a short,
   descriptive name prefixed by its type:
   ```bash
   git checkout -b feature/<short-description>
   ```
   Prefixes: `feature/` (new work), `fix/` (bug fix), `docs/` (documentation),
   `chore/` (tooling or maintenance). Example: `feature/postgres-state-layer`.

3. Commit your work. Keep commits focused and the message a concise, single
   sentence in the imperative mood. Do not sign commit messages.
   ```bash
   git add -A
   git commit -m "Add postgres service to compose"
   ```

4. Push your branch:
   ```bash
   git push -u origin feature/<short-description>
   ```

5. Open a pull request against `develop` from the GitHub web UI (the push output
   prints a compare link). Describe what changed and why.

6. Review and merge. At least one teammate reviews and approves, then the branch
   merges into `develop`. Delete the branch after merge.

## Guidelines

- Keep each branch scoped to a single feature or fix, since small pull requests
  review faster.
- Merge the latest `develop` into your branch before requesting review to avoid
  conflicts.
- Never commit secrets. `.env` is gitignored, so share config via `.env.example`.
- Validate compose changes locally before opening a pull request:
  ```bash
  docker compose config -q
  ```
