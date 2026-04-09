import time

from agents.base.base_agent import BaseAgent
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from agents.console_sections import print_section
from agents.llm_parser import bind_output_tokens, string_from_llm_content
from agents.llms import RESEARCHER_MODEL
from tools.github_api import GitHubManager

RESEARCHER_PROMPT = """
You are the repository researcher supporting README generation.

Your job is to study the provided repository context and produce concise, trustworthy research notes that a README writer can rely on.
Extract only facts supported by the repository context you are given.
If something is not clearly supported, label it as unknown instead of guessing.

Focus on:
1. What the project is and who it is for
2. Core capabilities and notable workflows
3. Setup, runtime, and configuration signals
4. Important files, modules, and entry points
5. What changed recently based on diffs or commit context
6. Gaps or open questions the writer should avoid speculating about

Prefer compact notes with useful headings and bullets.
Make the notes actionable for a downstream writer, not promotional.
"""

MAX_CHANGED_FILES = 3
MAX_FILE_CHARS = 6000
MAX_TREE_PATHS = 150
# Keep researcher prompt small so Groq stays fast; full patches can be huge.
MAX_PATCH_CHARS_PER_FILE = 3500
MAX_FILES_WITH_PATCHES = 12
MAX_COMMIT_MESSAGES = 15
RESEARCHER_MAX_OUTPUT_TOKENS = 2500


class Researcher(BaseAgent):
    def __init__(self):
        super().__init__(
            name="Researcher",
            description=RESEARCHER_PROMPT,
            model=RESEARCHER_MODEL,
        )
        self.github = GitHubManager()

    def _select_files(self, push_context):
        changed_files = push_context.get("files") or []
        paths_order = [f.get("filename", "") for f in changed_files if f.get("filename")]
        if not paths_order:
            paths_order = list(push_context.get("all_changed_paths") or [])

        prioritized = []
        for filename in paths_order:
            if filename.lower() == "readme.md":
                continue
            if filename.endswith((".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".java", ".rs", ".yml", ".yaml", ".toml", ".json", ".md")):
                prioritized.append(filename)

        if not prioritized:
            prioritized = [p for p in paths_order if p and p.lower() != "readme.md"]

        return prioritized[:MAX_CHANGED_FILES]

    def _trim_push_files(self, files):
        """Limit patch volume: huge diffs dominate tokens and slow the researcher LLM."""
        trimmed = []
        for file_info in files[:MAX_FILES_WITH_PATCHES]:
            patch = file_info.get("patch") or ""
            if len(patch) > MAX_PATCH_CHARS_PER_FILE:
                patch = patch[:MAX_PATCH_CHARS_PER_FILE] + "\n...[patch truncated]..."
            trimmed.append({
                "filename": file_info.get("filename"),
                "status": file_info.get("status"),
                "patch": patch,
            })
        omitted = max(0, len(files) - len(trimmed))
        return trimmed, omitted

    def _get_trimmed_file_content(self, installation_id, repo_name, file_path):
        try:
            content = self.github.get_file_content(installation_id, repo_name, file_path)
        except Exception as exc:
            return f"[unavailable: {exc}]"

        if len(content) <= MAX_FILE_CHARS:
            return content
        return content[:MAX_FILE_CHARS] + "\n\n...[truncated]..."

    def _build_research_context(self, state):
        installation_id = state["installation_id"]
        repo_name = state["repo_name"]
        base_sha = state["base_sha"]
        head_sha = state["head_sha"]

        t0 = time.perf_counter()
        push_context = self.github.get_push_context(
            installation_id,
            repo_name,
            base_sha,
            head_sha,
        )
        readme_data = self.github.get_readme_data(installation_id, repo_name)

        raw_files = push_context.get("files") or []
        trimmed_files, omitted_patches = self._trim_push_files(raw_files)
        all_paths = push_context.get("all_changed_paths") or []
        commits = (push_context.get("commit_summary") or [])[:MAX_COMMIT_MESSAGES]

        changed_files = self._select_files(push_context)
        selected_contents = {}
        for file_path in changed_files:
            selected_contents[file_path] = self._get_trimmed_file_content(
                installation_id,
                repo_name,
                file_path,
            )

        # Avoid get_repo_tree(recursive=True) unless needed — it is slow on large repos.
        repo_tree_paths = []
        if not raw_files and not all_paths:
            tree = self.github.get_repo_tree(installation_id, repo_name)
            repo_tree_paths = [item.path for item in tree[:MAX_TREE_PATHS]]

        elapsed = time.perf_counter() - t0
        print(f"[Researcher] GitHub context built in {elapsed:.2f}s (patches omitted from count: {omitted_patches})")

        patch_note = f" ({omitted_patches} more files with patches omitted)" if omitted_patches else ""

        return f"""
Repository:
{repo_name}

Current README:
{readme_data.get("content", "")}

README metadata:
exists={readme_data.get("exists")}
sha={readme_data.get("sha")}

Commit messages (up to {MAX_COMMIT_MESSAGES}):
{commits}

All changed paths in this push ({len(all_paths)} files):
{all_paths[:80]}{" ..." if len(all_paths) > 80 else ""}

Changed files and patches (trimmed for token budget){patch_note}:
{trimmed_files}

Selected changed file contents (for writer depth):
{selected_contents}

Repository tree preview (only if no file list from compare):
{repo_tree_paths}
"""

    def run(self, state):
        research_context = self._build_research_context(state)
        message_stream = [
            SystemMessage(content=self.description),
            *state["messages"],
            HumanMessage(
                content=(
                    "Use the repository context below to produce writer-ready research notes.\n\n"
                    f"{research_context}"
                )
            ),
        ]
        t_llm = time.perf_counter()
        bound = bind_output_tokens(self.model, RESEARCHER_MAX_OUTPUT_TOKENS)
        response = string_from_llm_content(bound.invoke(message_stream).content)
        print(f"[Researcher] LLM done in {time.perf_counter() - t_llm:.2f}s")
        print_section("Research hypothesis (writer-ready notes)", response)

        return {
            "research_notes": response,
            "messages": [AIMessage(content=f"Researcher Notes: {response}")]
        }
