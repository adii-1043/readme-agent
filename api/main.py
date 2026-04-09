from fastapi import FastAPI, Request, Header, BackgroundTasks
from tools.github_api import GitHubManager
import time

from agents.console_sections import print_section
from agents.llm_parser import (
    WRITER_AIMESSAGE_PREFIX,
    string_from_llm_content,
    strip_writer_prefix_stored,
)
from agents.orchestrator import graph  # Import the compiled graph
from langchain_core.messages import AIMessage, HumanMessage

app = FastAPI()


def _extract_final_readme(final_result: dict) -> str | None:
    messages = final_result.get("messages") or []
    for msg in reversed(messages):
        if not isinstance(msg, AIMessage):
            continue
        raw = string_from_llm_content(msg.content)
        if not raw.startswith(WRITER_AIMESSAGE_PREFIX):
            continue
        out = strip_writer_prefix_stored(raw)
        return out if out else None
    return None

manager = GitHubManager()

@app.post('/webhook')
async def github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_github_event: str = Header(None)
):
    if x_github_event != "push":
        return {'status': 'non push event... no README agentic involvement'}
    
    payload = await request.json()
    ref = payload.get("ref", "")

    if ref == "refs/heads/main":
        installation_id = payload["installation"]["id"]
        repo_name = payload["repository"]["full_name"]
        base_sha = payload["before"]
        head_sha = payload["after"]

        print(f"Push detected in {repo_name}. Handoff to agents.")
        
        background_tasks.add_task(
            start_agent_workflow, 
            installation_id, 
            repo_name, 
            base_sha, 
            head_sha
        )
    return {'status': 'Push event accepted'}

def start_agent_workflow(installation_id: int, repo_name: str, base_sha, head_sha):
    # before anything, sync ai-readme-update with main
    t_sync = time.perf_counter()
    manager.sync_ai_branch(installation_id, repo_name)
    print(f"[workflow] sync_ai_branch finished in {time.perf_counter() - t_sync:.2f}s")

    initial_message = HumanMessage(content=f"""
    NEW PUSH DETECTED:
    - Repository: {repo_name}
    - Installation ID: {installation_id}
    - Base SHA: {base_sha}
    - Head SHA: {head_sha}

    Researcher, please analyze the changes in this push and prepare notes for the Writer.
    """)

    # initial state needed for workflow in orchestrator.py
    initial_state = {
        "installation_id": installation_id,
        "repo_name": repo_name,
        "base_sha": base_sha,
        "head_sha": head_sha,
        "decision": False,
        "writer_attempts": 0,
        "messages": [initial_message]
    }

    print("All info gathered for agents!")
    print("Agent execution beginning...")

    t_graph = time.perf_counter()
    final_result = graph.invoke(initial_state)
    print(f"[workflow] graph.invoke finished in {time.perf_counter() - t_graph:.2f}s")
    final_readme = _extract_final_readme(final_result)
    print_section(
        "Final README (from workflow result)",
        final_readme
        if final_readme
        else "(No Writer Generation message found in final state.)",
    )

    if final_readme:
        readme_data = manager.get_readme_data(installation_id, repo_name, ref="ai-readme-update")
        manager.update_readme_on_branch(
            installation_id,
            repo_name,
            final_readme,
            readme_data.get("sha"),
        )
        print("[workflow] README pushed to ai-readme-update")
    else:
        print("[workflow] No README to push (final_readme empty)")
    