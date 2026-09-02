# Releasing ess-orrery

Releases are **signed** with [PEP 740 digital attestations](https://peps.python.org/pep-0740/) via
[PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/) (keyless OIDC). There is no
long-lived signing key to lose or leak: a release is signed by the identity of the release workflow
(`.github/workflows/release.yml`), and PyPI records a verifiable attestation for every artifact.

> PyPI removed PGP signature uploads in 2023, so `gpg`/`twine --sign` is not the mechanism. Attestations
> replace it and are stronger (bound to a workflow identity, not a detached key).

## The distribution name

The import package is `orrery`; the **published distribution and command are `ess-orrery`** (the PyPI
name `orrery` belongs to an unrelated project). PyPI normalizes separators, so `ess-orrery`,
`ess_orrery`, and `ess.orrery` are the same project.

## Cutting a release

1. Bump the single version authority: `__version__` in `orrery/__init__.py`.
2. Update `CHANGES.md`.
3. Commit, then create a **signed, annotated tag** and push it:
   ```
   git tag -s vX.Y.Z -m "ess-orrery X.Y.Z"
   git push origin vX.Y.Z
   ```
   The `release` workflow builds the sdist + wheel, runs `twine check`, and publishes to PyPI with
   attestations. Nothing is uploaded from a laptop; the tag is the trigger.

Signed tags: configure once with an SSH signing key (`git config gpg.format ssh`,
`git config user.signingkey <key>`, `git config tag.gpgSign true`), so the source tag is verifiable
independently of PyPI.

## One-time PyPI setup (gated: first-public-exposure, owner's go)

Before the first publish, on PyPI (account owner):
1. Add a **Trusted Publisher** for this project: repo `Evening-Star-System/Orrery`, workflow
   `release.yml`, environment `pypi`. Use a *pending* publisher to also claim the `ess-orrery` name
   before the first upload.
2. Optionally register a GitHub Actions environment named `pypi` with required reviewers, so a publish
   needs a human click.

No API token is ever created or stored; publishing authenticates via OIDC.

## How a user verifies a release

- `pip install ess-orrery` pulls the attested artifact; pip verifies PyPI attestations automatically.
- The attestation is visible on the project's PyPI page, bound to this repo's release workflow.
- `ess-orrery version` and `ess-orrery doctor` confirm the installed version and that the install is
  intact.

## Defensive name registrations

To reduce typo-squat risk, a few adjacent PyPI names that normalize *differently* from `ess-orrery`
(for example `essorrery`, `orrery-ess`) are registered as empty placeholders. They are not the product;
they exist only so no one else can ship malware under a confusable name.
