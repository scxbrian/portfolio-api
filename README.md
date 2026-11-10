# portfolio-api

The backend of my personal portfolio: a small Python service that keeps the project list on my site in step with my GitHub account. When I push to a repository, GitHub tells this service, the service stores the project's details, and the portfolio frontend reads them back through a public endpoint.

The frontend lives in a separate repository: [portfolio-web](https://github.com/scxbrian/portfolio-web).

**Status:** the code is complete and covered by 31 automated tests. It has not been deployed yet. It currently runs only on my development machine, and it is intended to run on a server at home.

## Contents

1. [How it works](#how-it-works)
2. [Repository layout](#repository-layout)
3. [Running it locally](#running-it-locally)
4. [Configuration](#configuration)
5. [Endpoints](#endpoints)
6. [What happens on a push](#what-happens-on-a-push)
7. [Importing existing repositories](#importing-existing-repositories)
8. [Tests](#tests)
9. [Design decisions](#design-decisions)
10. [Trade-offs and known limitations](#trade-offs-and-known-limitations)
11. [Deployment](#deployment)
12. [Roadmap](#roadmap)
13. [Licence and reuse](#licence-and-reuse)

## How it works

```
git push -> GitHub -> POST /webhook -> verify signature -> store in SQLite
                                                                 |
 visitor -> portfolio-web (Vercel) -> GET /api/projects <--------+
```

Two rules decide what the site shows. A repository appears only if it carries a chosen GitHub topic (`portfolio` by default), so I decide what is featured from GitHub itself. And a push only counts if it lands on the repository's default branch, so half-finished feature branches never reach the site.

## Repository layout

```
portfolio-api/
├── app/
│   ├── __init__.py
│   ├── config.py        # settings from environment variables
│   ├── db.py            # all SQLite access; the only file that writes SQL
│   ├── github.py        # signature check, README summaries, repo listing
│   └── main.py          # HTTP routes only
├── tests/
│   ├── conftest.py      # test settings and throwaway database
│   ├── test_api.py      # route tests
│   └── test_github.py   # signature and summary tests
├── seed.py              # one-time import of existing repositories
├── requirements.txt     # what the server needs
├── requirements-dev.txt # adds what the tests need
├── pytest.ini
├── .env.example         # settings template, safe to commit
└── .gitignore
```

Each file has one job. Routes call into `db.py` and `github.py` and contain no logic of their own, which keeps every layer easy to test and easy to replace.

## Running it locally

You need Python 3 and Git. The project was developed and tested on Python 3.14.

```bash
git clone https://github.com/scxbrian/portfolio-api.git
cd portfolio-api

python -m venv .venv
source .venv/bin/activate          # Windows Git Bash: source .venv/Scripts/activate
pip install -r requirements.txt

cp .env.example .env               # then edit WEBHOOK_SECRET (see below)
uvicorn app.main:app --reload --port 8000
```

Generate a secret with:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Check that it works:

```bash
curl http://127.0.0.1:8000/health
```

FastAPI also serves interactive documentation at `http://127.0.0.1:8000/docs` while the server runs.

## Configuration

All settings are environment variables. For local development they can live in a `.env` file, which Git ignores. In production the real environment is used, and values already set there are never overwritten by `.env`.

| Variable | Default | Meaning |
| :--- | :--- | :--- |
| `WEBHOOK_SECRET` | empty | Shared secret used to verify GitHub's signature. **If empty, every webhook is rejected.** |
| `GITHUB_USERNAME` | `scxbrian` | Account whose repositories are read. |
| `PUBLISH_TOPIC` | `portfolio` | A repository is shown on the site only if it has this GitHub topic. |
| `ALLOWED_ORIGINS` | the site and local test addresses | Comma-separated list of sites allowed to call the API from a browser. |
| `DB_PATH` | `data/portfolio.db` | Where the SQLite file lives. |

Note that `http://localhost:5500` and `http://127.0.0.1:5500` count as different origins to a browser, so list whichever one you actually use.

## Endpoints

| Method and path | Purpose |
| :--- | :--- |
| `GET /health` | Returns `{"status": "ok"}`. For monitoring and restart checks. |
| `GET /api/projects` | The published projects, newest push first. Public by design. |
| `POST /webhook` | Receives GitHub push events. Requires a valid `X-Hub-Signature-256` header. |

`GET /api/projects` returns an array of objects with exactly these fields, which is the contract the frontend depends on:

| Field | Type | Meaning |
| :--- | :--- | :--- |
| `repo_name` | string | Repository name. |
| `repo_url` | string | Link to the repository. |
| `language` | string or null | Main language as detected by GitHub. |
| `summary` | string or null | One-line description. |
| `updated_at` | string | ISO 8601 timestamp of the last push. |

A test pins this field set, so a change here fails the build before it can break the site.

## What happens on a push

1. The raw request body is checked against the signature header, using the shared secret. A missing or wrong signature gets a 401, and nothing is stored.
2. Events other than `push` are acknowledged and ignored.
3. A push to any branch other than the repository's default branch is ignored.
4. The summary is chosen: the repository's GitHub description if it has one. Otherwise the stored summary is kept if the push did not touch `README.md`. Otherwise the first paragraph of the README is fetched and trimmed.
5. The project is written with an upsert, so repeated or redelivered events update one row and never create duplicates.
6. The project is marked published only if it carries the publish topic, and this is re-evaluated on every push, so adding or removing the topic takes effect on the next push.

## Importing existing repositories

A webhook only fires on new pushes, so the database starts empty. `seed.py` reads all of the account's repositories from GitHub's API and fills it:

```bash
python seed.py
```

It skips forks and archived repositories, prints `published` or `hidden` for each repository, and is safe to run again at any time. Run it again whenever topics or descriptions change on GitHub without a push.

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest -v
```

There are 31 tests, and they need no network and no real settings. They use a fake secret and a throwaway database in a temporary folder, so a test run never touches real data. They cover:

- Signature checking: valid, wrong, missing, tampered body, malformed header, and an empty secret.
- The locked door: a rejected webhook stores nothing, and bad JSON returns a clean 400.
- The publish gate, in both directions, plus the default-branch filter.
- Idempotency: the same push twice leaves one row.
- Where the summary comes from, and when the README is fetched again.
- The response shape, and which sites CORS allows.

A deprecation warning from Starlette's test client about its HTTP package appears during test runs. It is harmless, and the tests are unaffected.

## Design decisions

### One job per file

Settings, storage, GitHub logic and HTTP routes are separate modules. The routes contain no business logic, so they are tiny, and the logic can be tested without any HTTP at all. The same split maps directly onto packages in the planned Go rewrite.

### Verifying the webhook

The endpoint is public, so anyone could post to it. GitHub signs each delivery with an HMAC of the exact bytes it sent, using the shared secret, and the service recomputes it and compares. Three details matter. The signature is computed over the raw body before any parsing, because re-serialising JSON changes the bytes. The comparison uses a constant-time function and works on bytes, so timing reveals nothing and a malformed header is refused cleanly instead of crashing. And an empty secret makes every request fail, so a forgotten setting leaves the endpoint closed and never open.

### Topics as the publish gate

Nothing reaches the portfolio unless I add a topic to the repository on GitHub. That removes any risk of an old experiment or a half-written README appearing under my name, and the decision stays with the repository, not with a configuration file here.

### Summaries are extraction, not AI

The summary is the repository description, or the first plain paragraph of the README, trimmed. It is honest, predictable and free. The logic is isolated in one function, `github.summarise`, so replacing it with a language-model call later changes nothing else.

### SQLite

The data is a few dozen small rows with very little write traffic, which suits SQLite: no separate server to run, one file to back up, and a perfect fit for a home server. A connection is opened per call, because a SQLite connection cannot be shared between threads by default and opening one is cheap. All SQL lives in `db.py`, so a move to PostgreSQL would touch only that file.

### Standard library for outbound requests

The service makes two simple GET requests, so it uses `urllib` and avoids an extra dependency to install and audit. Every call has a timeout, and any network failure means "no summary", never a crash.

### Not blocking the event loop

The webhook handler is asynchronous, and a README download or a database write inside it would stall every other request. That work runs in a thread pool instead.

### CORS allows only GET

Browsers apply CORS to pages calling the API. The only browser traffic is the frontend reading projects, so only `GET` is allowed, from listed origins. GitHub's webhook calls come from servers, not browsers, so they need no CORS rule.

## Trade-offs and known limitations

- **Editing a topic or description on GitHub does not trigger a webhook.** The change appears after the next push to that repository, or after running `seed.py`.
- **SQLite allows one writer at a time.** That is no problem at this scale, and it would matter only if the service ever handled heavy write traffic.
- **Private repositories cannot have their README fetched,** because the raw URL is public. A description still works for them.
- **GitHub's unauthenticated API allows 60 requests per hour per address.** That is plenty for `seed.py`, but repeated runs in quick succession can hit it.
- **`updated_at` means slightly different things depending on the path.** `seed.py` uses GitHub's last-push time, and the webhook uses the time it received the push. They agree closely enough that ordering stays sensible.
- **The interactive docs at `/docs` are on by default.** That is useful in development, and I plan to switch them off in production.
- **There is no rate limiting,** and the service does not speak HTTPS itself. HTTPS is provided by whatever sits in front of it in production.
- **A webhook must be added to each repository,** or once at the account level if using an organisation.

## Deployment

**Status: planned, not yet done.** The service will run on a home server inside a container, with a restart policy so it survives reboots. A tunnel such as Cloudflare Tunnel will provide a public HTTPS address without opening any router ports, because it only makes outbound connections from the server.

Once the service is reachable, each repository needs a webhook. On GitHub, open the repository, then Settings, then Webhooks, then Add webhook:

- **Payload URL:** `https://<public-address>/webhook`
- **Content type:** `application/json`
- **Secret:** the same value as `WEBHOOK_SECRET`
- **Events:** just the push event

The frontend then points at the same public address through its `apiBase` setting.

## Roadmap

- A Dockerfile and a restart policy for the home server.
- Pinned dependency versions, so the server installs exactly what was tested.
- Disable `/docs` in production, and add basic rate limiting.
- A contact-form endpoint and a private visit counter.
- A per-repository metadata file for richer project cards.
- A script that regenerates the frontend's fallback project list from this API.
- Nightly backups of the database file.
- A rewrite in Go, once I have learned the language well enough to do it properly.

## Licence and reuse

The code is public so that it can be read and reviewed. It is not licensed for reuse.