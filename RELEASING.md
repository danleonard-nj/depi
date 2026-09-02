# Releasing

Five distributions, released independently. Publishing uses **PyPI Trusted Publishing** (OIDC), so there are no API tokens stored in this repository and nothing to rotate.

| Distribution     | Source directory       | Tag prefix        |
| ---------------- | ---------------------- | ----------------- |
| `pydepi`         | `packages/depi-core`   | `pydepi-v`        |
| `pydepi-flask`   | `packages/depi-flask`  | `pydepi-flask-v`  |
| `pydepi-quart`   | `packages/depi-quart`  | `pydepi-quart-v`  |
| `pydepi-fastapi` | `packages/depi-fastapi`| `pydepi-fastapi-v`|
| `pydepi-django`  | `packages/depi-django` | `pydepi-django-v` |

---

## One-time setup

### 1. Create the GitHub environments

Repository → **Settings** → **Environments** → **New environment**. Create one per distribution, named after the distribution:

- `pydepi`
- `pydepi-flask`
- `pydepi-quart`
- `pydepi-fastapi`
- `pydepi-django`

PyPI treats owner/repo/workflow/environment as the publisher identity, so five projects publishing from one workflow file need five distinct environments. That also narrows blast radius: a run in the `pydepi-flask` environment can only mint a token for that one project.

The name must match what you enter on PyPI exactly. Consider adding yourself as a **required reviewer** on each — that turns every publish into a one-click approval and makes an accidental tag push harmless.

### 2. Register the trusted publishers on PyPI

All five distributions are already registered and published on PyPI, so trusted
publishing is fully set up — nothing to do here for a normal release. This
section is kept for adding a **new** distribution (e.g. the planned `pydepi-aiohttp`):
a project that does not exist on PyPI yet needs a **pending publisher** — a trust
relationship registered *before* the first upload, which PyPI converts into a
real project on first publish.

> **PyPI allows only 3 pending publishers at a time.** This constrained the first
> release into two waves (see "First release, in two waves" below, kept as a
> record); it only matters again if you register several new distributions at once.

Go to <https://pypi.org/manage/account/publishing/> and add a pending publisher for the new distribution. For reference, the five existing distributions were registered as:

| PyPI Project Name | Environment name |
| ----------------- | ---------------- |
| `pydepi`          | `pydepi`         |
| `pydepi-flask`    | `pydepi-flask`   |
| `pydepi-quart`    | `pydepi-quart`   |
| `pydepi-fastapi`  | `pydepi-fastapi` |
| `pydepi-django`   | `pydepi-django`  |

Owner is `danleonard-nj`, Repository name is `depi`, and Workflow name is `release.yml` for every one; the PyPI project name and environment name are what change per distribution.

Workflow name is the **filename**, not the `name:` inside the file — `release.yml`, not `Release`. The environment must differ per project: PyPI rejects a second publisher reusing the same owner/repo/workflow/environment combination.

### 3. Optional: the same again on TestPyPI

Only if you want a rehearsal. TestPyPI is a separate site with a separate account: <https://test.pypi.org/manage/account/publishing/>. Same pattern, with the environment prefixed `testpypi-` — e.g. project `pydepi`, environment `testpypi-pydepi`. The prefix keeps the two indexes' environments distinct. Create the matching GitHub environment too.

Worth doing once for `pydepi` alone, to watch the pipeline work end to end. Not worth doing for all five.

---

## Cutting a release

### 1. Bump the version and update the changelog

Edit `version` in that package's `pyproject.toml`, and move that package's `unreleased` heading in [CHANGELOG.md](CHANGELOG.md) to the version and date you are shipping.

The workflow refuses to publish if the tag and the `pyproject.toml` disagree, so the version cannot silently drift. The changelog is not enforced — it is on you.

### 2. Tag and push

```bash
git tag pydepi-flask-v0.2.0 && git push origin pydepi-flask-v0.2.0
```

That is the whole trigger. The workflow resolves the package from the tag, builds an sdist and a wheel, runs `twine check --strict`, installs the built wheel into a clean virtualenv and imports it, then publishes.

### 3. Approve, if you enabled required reviewers

The run pauses at the `publish` job until you approve it in the Actions tab.

---

## First release, in two waves

> **Done.** All five distributions shipped 0.1.0 on 2026-09-02. This section is a
> record of how the first release was sequenced, and the template for a future
> batch of new distributions.

Two constraints shape the order:

1. **Core first.** The adapters declare `pydepi>=0.1,<0.2`, so an adapter published before core exists is installable-but-broken. This is self-enforcing, not just documented — the build job installs the finished wheel into a clean virtualenv, so tagging an adapter too early fails *before* anything uploads:

   ```
   ERROR: Could not find a version that satisfies the requirement pydepi<0.2,>=0.1
   ```

2. **Only 3 pending publishers at a time.** Publishing converts a pending publisher into a real project and frees the slot.

There is no need to let any run fail. Create all five GitHub environments up front (they have no limit), then:

### Wave 1 — the three pending publishers you can register now

```bash
git tag pydepi-v0.1.0 && git push origin pydepi-v0.1.0
```

Wait for that run to go green — everything else depends on core being on PyPI. Then:

```bash
git tag pydepi-flask-v0.1.0 && git push origin pydepi-flask-v0.1.0
git tag pydepi-quart-v0.1.0 && git push origin pydepi-quart-v0.1.0
```

### Wave 2 — register the remaining two, then tag

All three slots are now free. Back to <https://pypi.org/manage/account/publishing/>, add pending publishers for `pydepi-fastapi` (environment `pydepi-fastapi`) and `pydepi-django` (environment `pydepi-django`), then:

```bash
git tag pydepi-fastapi-v0.1.0 && git push origin pydepi-fastapi-v0.1.0
git tag pydepi-django-v0.1.0  && git push origin pydepi-django-v0.1.0
```

### If a publish does fail

Fix the cause, delete the tag locally and remotely, and re-push it — the version number has not been consumed unless the upload actually succeeded. PyPI refuses to accept the same version twice, so a genuinely uploaded version needs a version bump instead.

```bash
git tag -d pydepi-flask-v0.1.0 && git push origin :refs/tags/pydepi-flask-v0.1.0
```

---

## Dry run

Actions → **Release** → **Run workflow**, pick a package and `testpypi`. This uses the same build and verification path, so it exercises everything except the final upload target. Requires the step 3 setup.

---

## Version compatibility between packages

Adapters pin `pydepi>=0.1,<0.2` and build against `depi.integration.BaseInjector` and `depi.context`. That range is the contract:

- A **core** change that alters either of those is a breaking change for all four adapters. Widen the adapter pins in the same PR that makes it, and release core first.
- An **adapter** change touching only its own framework needs no core release at all. That independence is the reason for the split.

---

## What is not automated

- **No GitHub Release is created.** Tags trigger publishing; release notes are still manual.
- **The changelog is not enforced.** [CHANGELOG.md](CHANGELOG.md) exists and has a section per distribution, but the workflow does not check it — updating it before a tag is on you.
- **`contents: write` is never granted.** The workflow only reads the repo and mints an OIDC token; it cannot push commits or tags.
