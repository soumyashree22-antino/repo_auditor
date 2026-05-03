# Autonomous Multi-Agent Repository Auditor

Repo Auditor is a Streamlit proof of concept that reviews a public GitHub repository with three specialist AI agents:

- Mapper: understands the repo structure, language, frameworks, and entry points.
- Security Hunter: finds secrets, risky functions, SQL injection patterns, and other vulnerabilities.
- Code Critic: finds technical debt, complexity, duplication, weak error handling, and architecture issues.

The agents share one audit state and a final synthesizer turns their findings into an Intelligence Report with an executive summary and side-by-side code fix suggestions.

## Project Structure

```text
repo_auditor/
├── app.py
├── orchestrator.py
├── synthesizer.py
├── requirements.txt
├── agents/
├── models/
├── prompts/
└── tools/
```

## Code Ownership

- `AuditPipeline` in `orchestrator.py` coordinates the full audit workflow.
- `GitHubRepositoryFetcher` in `tools/github_fetcher.py` owns GitHub URL parsing and source-file fetching.
- `RepositoryMapper` in `agents/mapper.py` owns architecture, project structure, module mapping, and repo overview generation.
- `SecurityAuditor` in `agents/security.py` owns security scanning.
- `DebtAuditor` in `agents/debt.py` owns maintainability and architecture debt scanning.
- `ReportSynthesizer` in `synthesizer.py` owns final report generation.
- `LLMClient` in `tools/llm_client.py` owns Ollama/Anthropic provider calls.
- `RepositoryCodeAnalyzer` in `tools/code_parser.py` owns static code parsing, file trees, component maps, and limited LLM context.

## Setup

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

Edit `.env`. The project is set up to use Ollama with Qwen2.5-Coder:

```text
LLM_PROVIDER=ollama
OLLAMA_MODEL=qwen2.5-coder:7b
OLLAMA_URL=http://localhost:11434
ANTHROPIC_API_KEY=
GITHUB_TOKEN=ghp_...
```

`GITHUB_TOKEN` is optional, but it increases the GitHub API rate limit.

## Install Qwen2.5-Coder Locally

1. Install Ollama from https://ollama.com/download
2. Open a terminal and pull the model:

```bash
ollama pull qwen2.5-coder:7b
```

3. Keep Ollama running in the background. You can test the model with:

```bash
ollama run qwen2.5-coder:7b
```

Type `/bye` to exit the Ollama chat when you are done testing.

## Run

```bash
streamlit run app.py
```

Open the local Streamlit URL, paste a public GitHub repository URL, and run the audit.

## Notes

- Start with a small public repo while testing.
- Very large repositories may be sampled before being sent to the LLM to keep the proof of concept fast.
- The local regex and heuristic scans still inspect every fetched text file.
