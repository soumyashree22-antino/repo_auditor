import json

from dotenv import load_dotenv
from pydantic import ValidationError

from models.report import CodeDiff, FinalReport
from tools.json_utils import extract_json_object
from tools.llm_client import call_llm

load_dotenv()


class ReportSynthesizer:
    """Combines mapper, security, and debt outputs into the final audit report."""

    def run(self, state: dict) -> dict:
        """Generate a final report combining all analysis findings."""
        combined_findings = self._prepare_findings(state)
        synthesis = self._generate_synthesis(combined_findings)

        final_report = {
            "repo_overview": state.get("mapper_output", {}),
            "security_issues": state.get("security_findings", []),
            "debt_issues": state.get("debt_findings", []),
            "executive_summary": synthesis.get("executive_summary", ""),
            "code_diffs": synthesis.get("code_diffs", []),
        }

        try:
            final_report = FinalReport.model_validate(final_report).model_dump()
        except ValidationError as error:
            print(f"Final report validation warning: {error}")

        return {**state, "final_report": final_report}

    def _prepare_findings(self, state: dict) -> dict:
        """Prepare findings for synthesis."""
        return {
            "repo_overview": state.get("mapper_output", {}),
            "security_findings": state.get("security_findings", []),
            "debt_findings": state.get("debt_findings", []),
        }

    def _generate_synthesis(self, combined_findings: dict) -> dict:
        """Generate synthesis using LLM or fallback method."""
        synthesis = self._llm_synthesis(combined_findings)
        if not synthesis:
            synthesis = self._fallback_synthesis(combined_findings)
        return synthesis

    def _llm_synthesis(self, combined_findings: dict) -> dict:
        """Generate synthesis using LLM."""
        try:
            raw_text = call_llm(
                system_prompt=self._load_prompt("synthesis_prompt.txt"),
                user_message=json.dumps(combined_findings, indent=2),
                max_tokens=800,
            )
            if not raw_text:
                return {}

            parsed = self._parse_json_response(raw_text)
            code_diffs = self._validate_code_diffs(parsed.get("code_diffs", []))

            return {
                "executive_summary": parsed.get("executive_summary", ""),
                "code_diffs": code_diffs,
            }
        except Exception as error:
            print(f"Synthesizer failed: {error}")
            return {}

    def _fallback_synthesis(self, combined_findings: dict) -> dict:
        """Generate synthesis using heuristic fallback."""
        overview = combined_findings.get("repo_overview", {})
        security_findings = combined_findings.get("security_findings", [])
        debt_findings = combined_findings.get("debt_findings", [])

        executive_summary = self._build_executive_summary(overview, security_findings, debt_findings)
        code_diffs = self._build_fallback_diffs(security_findings, debt_findings)

        return {
            "executive_summary": executive_summary,
            "code_diffs": code_diffs,
        }

    def _build_executive_summary(self, overview: dict, security_findings: list, debt_findings: list) -> str:
        """Build executive summary text."""
        critical_count = self._count_severity(security_findings, "CRITICAL")
        high_count = self._count_severity(security_findings, "HIGH")

        project_line = overview.get("overview") or "The repository was analyzed with the local mapper."
        architecture_line = overview.get("architecture_style") or "The architecture style was not clearly identified."
        module_line = self._summarize_items(overview.get("module_details") or overview.get("main_modules"), 4)
        runtime_line = self._summarize_items(overview.get("setup_and_runtime") or overview.get("entry_points"), 4)
        integration_line = self._summarize_items(overview.get("external_integrations"), 4)

        return (
            f"{project_line}\n\n"
            f"Architecture: {architecture_line}. "
            f"Major modules: {module_line or 'no major modules were detected from the fetched files'}. "
            f"Runtime clues: {runtime_line or 'no setup or runtime commands were detected'}."
            f"{' External integrations: ' + integration_line + '.' if integration_line else ''}\n\n"
            f"The audit found {len(security_findings)} security finding(s), including "
            f"{critical_count} critical and {high_count} high severity item(s). These should be reviewed first "
            "because exposed secrets and unsafe execution paths can create direct business risk.\n\n"
            f"The code critic found {len(debt_findings)} technical debt item(s). The highest priority improvements "
            "are to simplify complex code, remove duplication, and turn unresolved maintenance notes into tracked work."
        )

    def _build_fallback_diffs(self, security_findings: list, debt_findings: list) -> list[dict]:
        """Build code diffs from findings."""
        issues = security_findings + debt_findings
        diffs = []

        for issue in issues[:5]:
            snippet = issue.get("snippet", "")
            suggestion = issue.get("suggestion") or issue.get("explanation") or "Refactor this code to remove the risk."
            diffs.append(
                {
                    "issue_title": issue.get("issue", "Suggested fix"),
                    "file": issue.get("file", ""),
                    "original_code": snippet,
                    "refactored_code": f"# Suggested change:\n# {suggestion}",
                    "explanation": suggestion,
                }
            )

        return diffs

    def _validate_code_diffs(self, diffs: list) -> list[dict]:
        """Validate code diffs against schema."""
        validated = []
        for item in diffs:
            try:
                validated.append(CodeDiff.model_validate(item).model_dump())
            except ValidationError:
                continue
        return validated

    @staticmethod
    def _count_severity(findings: list[dict], severity: str) -> int:
        """Count findings by severity level."""
        return sum(1 for finding in findings if finding.get("severity") == severity)

    @staticmethod
    def _summarize_items(items, limit: int) -> str:
        """Summarize a list of items."""
        if not isinstance(items, list):
            return ""
        return "; ".join(str(item) for item in items[:limit] if str(item).strip())

    @staticmethod
    def _load_prompt(name: str) -> str:
        """Load prompt template from file."""
        with open(f"prompts/{name}", "r", encoding="utf-8") as file:
            return file.read()

    @staticmethod
    def _parse_json_response(raw_text: str) -> dict:
        """Parse JSON response from LLM."""
        try:
            return extract_json_object(raw_text)
        except ValueError:
            return {}
