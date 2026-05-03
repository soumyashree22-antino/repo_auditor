from typing import TypedDict

from agents.debt import DebtAuditor
from agents.mapper import RepositoryMapper
from agents.security import SecurityAuditor
from synthesizer import ReportSynthesizer
from tools.github_fetcher import GitHubRepositoryFetcher


class AuditState(TypedDict):
    """State container for audit pipeline."""
    github_url: str
    file_contents: dict
    mapper_output: dict
    security_findings: list
    debt_findings: list
    final_report: dict


class RepositoryFetcher:
    """Handles repository fetching from GitHub using API with optional git clone."""

    def __init__(self, fetcher: GitHubRepositoryFetcher | None = None):
        self.fetcher = fetcher or GitHubRepositoryFetcher(use_git_clone=False)

    def fetch(self, github_url: str) -> dict:
        return self.fetcher.fetch_all_files(github_url)


class AuditPipeline:
    """Orchestrates the complete repository audit workflow using ADK principles."""

    def __init__(
        self,
        fetcher: RepositoryFetcher | None = None,
        mapper: RepositoryMapper | None = None,
        security_auditor: SecurityAuditor | None = None,
        debt_auditor: DebtAuditor | None = None,
        synthesizer: ReportSynthesizer | None = None,
    ) -> None:
        self.fetcher = fetcher or RepositoryFetcher()
        self.mapper = mapper or RepositoryMapper()
        self.security_auditor = security_auditor or SecurityAuditor()
        self.debt_auditor = debt_auditor or DebtAuditor()
        self.synthesizer = synthesizer or ReportSynthesizer()

    def run(self, github_url: str) -> dict:
        """Execute the complete audit pipeline and return the final report using ADK workflow."""
        state = self._create_initial_state(github_url)
        try:
            state = self._execute_pipeline(state)
            return state["final_report"]
        finally:
            # Cleanup temporary cloned repository
            self._cleanup_temp_dir()

    def _create_initial_state(self, github_url: str) -> AuditState:
        return {
            "github_url": github_url,
            "file_contents": {},
            "mapper_output": {},
            "security_findings": [],
            "debt_findings": [],
            "final_report": {},
        }

    def _execute_pipeline(self, state: AuditState) -> AuditState:
        """Execute all audit stages in sequence as an ADK workflow with git clone support."""
        state = self._fetch_repository(state)
        state = self.mapper.run(state)
        state = self.security_auditor.run(state)
        state = self.debt_auditor.run(state)
        state = self.synthesizer.run(state)
        return state

    def _fetch_repository(self, state: AuditState) -> AuditState:
        """Fetch all repository files from GitHub using git clone."""
        files = self.fetcher.fetch(state["github_url"])
        return {**state, "file_contents": files}

    def _cleanup_temp_dir(self) -> None:
        """Clean up temporary cloned repository."""
        if hasattr(self.fetcher, 'fetcher') and hasattr(self.fetcher.fetcher, 'temp_dir'):
            if self.fetcher.fetcher.temp_dir:
                import shutil
                try:
                    shutil.rmtree(self.fetcher.fetcher.temp_dir, ignore_errors=True)
                except Exception as error:
                    print(f"Warning: Could not cleanup temp directory: {error}")


def build_adk_workflow():
    """Build ADK-compatible workflow for agent orchestration."""
    # ADK workflow definition using the AuditPipeline
    # This maintains a modular, agent-based approach with NVIDIA integration
    
    class ADKWorkflow:
        """Encapsulates the ADK workflow for repository auditing."""
        
        def __init__(self):
            self.pipeline = AuditPipeline()
        
        def execute(self, github_url: str) -> dict:
            """Execute the workflow with NVIDIA-powered agents."""
            return self.pipeline.run(github_url)
    
    return ADKWorkflow()


def run_audit(github_url: str) -> dict:
    """Main entry point for running a repository audit using ADK + NVIDIA."""
    pipeline = AuditPipeline()
    return pipeline.run(github_url)
