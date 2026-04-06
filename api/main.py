from fastapi import FastAPI, Request, Header, BackgroundTasks
from tools.github_api import GitHubManager
import os
from pprint import pprint

app = FastAPI()
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
    manager.sync_ai_branch(installation_id, repo_name)

    # get differences
    context = manager.get_push_context(installation_id, repo_name, base_sha, head_sha)

    print("All information gathered for agents...")
    pprint(context)