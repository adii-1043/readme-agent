# GitHub README Agent (GitHub App)

An agentic GitHub App that listens to `push` events on `main`, researches the repository changes, drafts an updated `README.md`, iterates with a judge loop, and writes the final README to a dedicated branch: **`ai-readme-update`**.

## Project status

This project is **in progress**. The current codebase is optimized for developers/self-hosting (create a GitHub App, run the webhook server, configure env vars). Future work focuses on making the “app experience” easier so users can install and configure it with minimal setup rather than cloning/running everything themselves.

## What it does

On every push to `main`:

- **Sync branch**: ensures `ai-readme-update` is up to date with `main` (merge with conflict-resolution strategy).
- **Researcher**: pulls GitHub compare data (commit messages + changed files/patches) and a small set of file contents, then produces grounded research notes.
- **Writer**: generates a README draft from the conversation context.
- **Judge**: reviews the latest draft and either approves or sends feedback back to the writer.
- **Loop cap**: stops after **5** writer attempts and uses the latest draft.
- **Write output**: updates (or creates) `README.md` on the `ai-readme-update` branch.

Workflow is implemented using **LangGraph** (`agents/orchestrator.py`), with agents implemented in `agents/roles/`.

## Architecture

- **API server**: FastAPI webhook receiver in `api/main.py`
- **Orchestration**: LangGraph workflow in `agents/orchestrator.py`
- **Agents**:
  - `agents/roles/researcher.py`
  - `agents/roles/writer.py`
  - `agents/roles/judge.py`
- **GitHub integration (GitHub App auth)**: `tools/github_api.py` (PyGithub)
- **LLM parsing utilities**: `agents/llm_parser.py`
- **Models**: configured in `agents/llms.py` (currently Google GenAI / Gemini)

## Deployment & onboarding (important)

This project is triggered by **GitHub webhooks** (on `push` to `main`). That means it must run on an **always-on server** that GitHub can reach, and the server must be able to call the LLM provider at webhook time.

- **Repo selection is handled by GitHub**: When a user installs your GitHub App, GitHub already lets them choose **All repositories** vs **Only select repositories**. You do not need to build a custom UI for “which repos can be modified”.
- **Collecting a Gemini key is not handled by GitHub**: GitHub’s GitHub App installation/config screens do not provide a place for users to enter and persist a third-party API key (like a Gemini / Google GenAI key) for your service.

### Choose one of these deployment models

#### Option A (recommended): Self-hosted GitHub App backend

Best if you want **users to run this with their own credentials** and you don’t want them to depend on your hosted API.

- Users deploy this webhook server to their own infrastructure (a long-lived service such as Render/Fly/AWS/etc.)
- Users set environment variables (including their Gemini key) in **their** deployment
- Your GitHub App can still be public; each installation is configured by the installer on their own runtime

#### Option B: Hosted SaaS (your backend) + per-install secret storage

Best if you want a “one-click” experience for non-technical users, but it means users are relying on your hosted service.

- You host the webhook receiver and run the workflow
- You must associate a Gemini key (or other provider credential) with each installation
  - Practically this means storing it (ideally encrypted at rest with strict access controls), because webhooks fire when the user is not present
- A Vercel frontend can be used as a post-install setup/status page, but GitHub will still be the source of truth for repo access

## Setup

### 1) Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2) Create a GitHub App

Create a GitHub App in GitHub Settings and configure it to receive **push webhooks**.

Minimum permissions (recommended starting point):

- **Repository contents**: Read & Write (to update `README.md` on `ai-readme-update`)
- **Pull requests**: optional (only needed if/when you enable PR creation)

Subscribe to events:

- **Push**

Install the app on the repositories you want it to operate on.

### 3) Environment variables

Create a `.env` file at the repo root (same folder as `requirements.txt`).

Required:

- **`GOOGLE_API_KEY`**: Google GenAI (Gemini) API key used by `agents/llms.py`
- **`GITHUB_APP_ID`**: GitHub App ID
- **`GITHUB_PRIVATE_KEY_PATH`**: path to the GitHub App private key `.pem` file
  - Can be absolute, or relative to the repo root.

Optional (only used in `tools/github_api.py` manual tests):

- **`GITHUB_INSTALLATION_ID`**

## Run locally

Start the webhook server:

```bash
uvicorn api.main:app --reload --port 8000
```

Expose your local server to GitHub (e.g. using `ngrok`) and set the GitHub App webhook URL to:

- `POST /webhook` (example: `https://<your-ngrok-domain>/webhook`)

## Output behavior

- The app only reacts to `push` events where `ref == "refs/heads/main"`.
- The final README is the last `Writer Generation:` message from the workflow.
- The README is written to **`README.md` on the `ai-readme-update` branch**.

## Notes / limitations

- **Webhook signature verification is not implemented** yet. Do not expose this endpoint publicly without adding signature validation.
- If you run this as a hosted service for other users, you will need a secure way to manage **per-install credentials** (e.g. encryption-at-rest, rotation, and access controls). For a student project, consider keeping it **self-hosted** to avoid handling other users’ secrets.
- LLM outputs are best-effort. The judge loop improves quality, but cannot guarantee correctness.
- `sync_ai_branch` contains a conflict-resolution strategy that prefers accepting `main` during conflicts.

## Repo map

```text
api/main.py               FastAPI webhook handler + workflow entrypoint
agents/orchestrator.py    LangGraph workflow (Researcher → Writer → Judge loop)
agents/roles/*            Agent implementations
tools/github_api.py       GitHub App auth + read/write operations (PyGithub)
agents/llms.py            Model configuration
agents/llm_parser.py      Provider-agnostic token binding + output parsing helpers
```

## Future work

- Webhook signature verification (`X-Hub-Signature-256`)
- Deduplication/locking for concurrent pushes
- Optional PR creation (`ai-readme-update` → `main`)
- Document and streamline **self-hosting** (deploy templates, minimal required env vars, local dev + ngrok guide)
- Optional **hosted mode**: encrypted per-install credential storage for LLM keys (rotation, access controls, audit logging)
- Optional **onboarding frontend** (e.g. Vercel): post-install redirect, installation status page, and configuration guidance (repo access remains managed by GitHub). Note: this is separate from the webhook backend, which should run as an always-on service.