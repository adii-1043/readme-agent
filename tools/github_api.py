import os
import time
from pprint import pprint
from pathlib import Path

from github import Github, Auth, GithubIntegration, GithubException
from dotenv import load_dotenv

# ALL AI README CHANGES PUSH TO PR BRANCH NAMED -> ai-readme-update

# Resolve paths from repo root so manual runs work regardless of cwd (e.g. `python tools/github_api.py` vs `cd tools && python github_api.py`).
_REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_REPO_ROOT / ".env")

class GitHubManager:
    # --- SETUP AND AUTH ---
    def __init__(self):
        self.app_id = os.getenv("GITHUB_APP_ID")
        raw_path = os.getenv("GITHUB_PRIVATE_KEY_PATH")
        self.private_key_path = (
            Path(raw_path).expanduser()
            if raw_path and Path(raw_path).expanduser().is_absolute()
            else (_REPO_ROOT / raw_path).resolve()
            if raw_path
            else None
        )

        # Load the private key
        with open(self.private_key_path, 'r') as f:
            self.private_key = f.read()

        # This uses the .pem file to prove to GitHub that YOU are this App
        self.auth = Auth.AppAuth(self.app_id, self.private_key)
        self.integration = GithubIntegration(auth=self.auth)

    def get_installation_client(self, installation_id: int):
        """
        Creates a GitHub client for a specific user's installation
        This is what agents will use to read/write code
        """
        return self.integration.get_github_for_installation(installation_id)
    
    # --- READ ---
    def get_push_context(self, installation_id: int, repo_name: str, base_sha, head_sha, branch: str = "main"):
        """
        FUNCTION FOR ALL CONTEXT OF CHANGE
        """
        gh = self.get_installation_client(installation_id)
        repo = gh.get_repo(repo_name)

        comparison = repo.compare(base_sha, head_sha)

        messages = [commit.commit.message for commit in comparison.commits]

        relevant_files = []
        for file in comparison.files:
            if file.filename.endswith((
                '.py', '.pyi', '.js', '.jsx', '.ts', '.tsx', '.go', '.java', '.kt',
                '.rb', '.php', '.rs', '.c', '.cc', '.cpp', '.h', '.hpp', '.cs',
                '.swift', '.scala', '.sh', '.sql', '.html', '.css', '.scss',
                '.json', '.yaml', '.yml', '.toml', '.ini', '.cfg', '.xml',
                '.md', '.mdx'
            )):
                relevant_files.append({
                    "filename": file.filename,
                    "status": file.status,  # added, modified, or removed
                    "patch": file.patch  # the actual diff in string
                })
        return {
            "files": relevant_files,
            "commit_summary": messages,
            "total_changes": comparison.total_commits
        }

    def get_repo_tree(self, installation_id:int, repo_name: str, branch:str = "main"):
        gh = self.get_installation_client(installation_id)
        repo = gh.get_repo(repo_name)

        tree = repo.get_git_tree(branch, recursive=True)
        return tree.tree
    
    def get_readme_data(self, installation_id: int, repo_name: str, ref: str = None):
        gh = self.get_installation_client(installation_id)
        repo = gh.get_repo(repo_name)

        try:
            # If ref is None, PyGithub defaults to the repo's default branch
            content_file = repo.get_contents("README.md", ref=ref)
            return {
                "content": content_file.decoded_content.decode("utf-8"),
                "sha": content_file.sha,
                "exists": True
            }
        except GithubException as e:
            if e.status == 404:
                return {"content": "", "sha": None, "exists": False}
            raise
    
    def get_file_content(self, installation_id: int, repo_name: str, file_path: str, ref: str = "main"):
        """Fetches and decodes the full content of a single file."""
        gh = self.get_installation_client(installation_id)
        repo = gh.get_repo(repo_name)
        content_file = repo.get_contents(file_path, ref=ref)
        return content_file.decoded_content.decode("utf-8")
    # --- WRITE ---
    def update_readme_on_branch(self, installation_id: int, repo_name: str, content: str, sha: str):
        """Pushes the new README content to the 'ai-readme-update' branch."""
        gh = self.get_installation_client(installation_id)
        repo = gh.get_repo(repo_name)
        
        return repo.update_file(
            path="README.md",
            message="🤖 AI: Update README documentation",
            content=content,
            sha=sha,
            branch="ai-readme-update"
        )

    def create_pull_request(self, installation_id: int, repo_name: str, title: str, body: str):
        """Opens a PR from 'ai-readme-update' to 'main'."""
        gh = self.get_installation_client(installation_id)
        repo = gh.get_repo(repo_name)
        
        try:
            pr = repo.create_pull(title=title, body=body, head="ai-readme-update", base="main")
            return pr.html_url
        except GithubException as e:
            if "A pull request already exists" in str(e):
                # If PR exists, just return the link to the existing one
                pulls = repo.get_pulls(state='open', head=f"{repo.owner.login}:ai-readme-update", base="main")
                return pulls[0].html_url
            raise

    # --- CHECK ---   
    def sync_ai_branch(self, installation_id: int, repo_name: str):
        gh = self.get_installation_client(installation_id)
        repo = gh.get_repo(repo_name)

        try:
            ai_branch = repo.get_branch(branch="ai-readme-update")
            print("ai-readme-update already exists! Merging main and this branch...")
            try:
                repo.merge(
                    base=ai_branch.name,
                    head="main",
                    commit_message="sync ai-readme-update with the latest main"
                )
                print("Successfully synced ai-readme-update with main!")
            except GithubException as merge_error:
                if merge_error.status != 409:
                    raise

                print("Merge conflict detected. Accepting main version and retrying merge...")
                comparison = repo.compare("ai-readme-update", "main")

                for file_info in comparison.files:
                    path = file_info.filename
                    previous_path = getattr(file_info, "previous_filename", None)

                    if file_info.status == "removed":
                        try:
                            branch_file = repo.get_contents(path, ref="ai-readme-update")
                            repo.delete_file(
                                path=path,
                                message=f"Resolve merge conflict by accepting main for {path}",
                                sha=branch_file.sha,
                                branch="ai-readme-update",
                            )
                        except GithubException as file_error:
                            if file_error.status != 404:
                                raise
                        continue

                    source_file = repo.get_contents(path, ref="main")
                    source_content = source_file.decoded_content

                    if file_info.status == "renamed" and previous_path:
                        try:
                            old_branch_file = repo.get_contents(previous_path, ref="ai-readme-update")
                            repo.delete_file(
                                path=previous_path,
                                message=f"Resolve merge conflict by accepting main rename from {previous_path} to {path}",
                                sha=old_branch_file.sha,
                                branch="ai-readme-update",
                            )
                        except GithubException as file_error:
                            if file_error.status != 404:
                                raise

                    try:
                        branch_file = repo.get_contents(path, ref="ai-readme-update")
                        repo.update_file(
                            path=path,
                            message=f"Resolve merge conflict by accepting main for {path}",
                            content=source_content,
                            sha=branch_file.sha,
                            branch="ai-readme-update",
                        )
                    except GithubException as file_error:
                        if file_error.status != 404:
                            raise

                        repo.create_file(
                            path=path,
                            message=f"Resolve merge conflict by accepting main for {path}",
                            content=source_content,
                            branch="ai-readme-update",
                        )

                repo.merge(
                    base=ai_branch.name,
                    head="main",
                    commit_message="sync ai-readme-update with the latest main"
                )
                print("Successfully resolved conflicts by accepting main and synced ai-readme-update!")
        except GithubException as e:
            if e.status == 404:
                print("AI PR branch doesn't exist. Creating one...")
                source_branch = repo.get_branch("main")
                base_sha = source_branch.commit.sha

                repo.create_git_ref(ref="refs/heads/ai-readme-update", sha=base_sha)
                print("AI Branch Created!")
            else:
                print(f"Unknown error...{e}")

# --- FOR FUNCTION SANITY TESTING ---
if __name__ == "__main__":
    # Test if we can actually see your repo
    test_id = int(os.environ["GITHUB_INSTALLATION_ID"])
    manager = GitHubManager()

    # List repos granted to this app installation instead (GET /installation/repositories)
    installation = manager.integration.get_app_installation(test_id)
    for repo in installation.get_repos():
        # commits = list(repo.get_commits()[:2]) # Get last two commits
        # head = commits[0].sha
        # base = commits[1].sha
        # context = manager.get_push_context(test_id, repo.full_name, base, head)
        # print(context)
        pprint(manager.get_repo_tree(test_id, repo.full_name))
