# Contributing to Orrery

Orrery's core is open source under **AGPL-3.0-or-later**. Contributions are welcome by pull request.

## Before you start

- By contributing, you agree your contribution is licensed under AGPL-3.0-or-later.
- A **Contributor License Agreement (CLA)** is required. Evening Star Productions offers Orrery under
  a dual license (AGPL plus a commercial license), which is only possible if the project holds the
  rights to all contributions. The CLA preserves that. A maintainer will point you to it on your
  first pull request.

## The bar

- **Correctness first.** New behavior comes with tests. The suite is `pytest`; keep it green.
- **The core stays clean.** No runtime dependencies in the engines (Python standard library only);
  no identity, paths, or secrets baked into code (those belong in a profile or config the operator
  supplies). Security gates fail closed.
- **No em-dashes** in files or commit messages. Use a comma, a colon, parentheses, or a full stop.
- **Small, reviewable changes.** Explain the why in the pull request.

## Writing style

Plain, direct prose. Match the surrounding code and docs.

## Reporting a vulnerability

Please report security issues privately to Evening Star Productions rather than opening a public
issue.

Copyright Evening Star Productions.
