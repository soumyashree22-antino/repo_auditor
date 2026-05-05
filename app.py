import streamlit as st
import os
os.environ["NO_PROXY"] = "*"


from orchestrator import run_audit


st.set_page_config(page_title="Repo Auditor", layout="wide")


class UIController:
    """Controls the main UI flow and state management."""

    def __init__(self):
        self.report = None

    def run(self) -> None:
        st.title("Autonomous Multi-Agent Repository Auditor")
        self._render_input_section()
        self._load_and_render_report()

    def _render_input_section(self) -> None:
        with st.container(border=True):
            github_url = st.text_input(
                "GitHub repository URL",
                placeholder="https://github.com/owner/repo",
            )
            run_clicked = st.button("Run Audit", type="primary", use_container_width=True)

        if run_clicked:
            self._handle_audit_request(github_url)

    def _handle_audit_request(self, github_url: str) -> None:
        if not github_url.strip():
            st.warning("Enter a GitHub repository URL first.")
            return

        try:
            with st.spinner("Running repository audit..."):
                st.session_state["report"] = run_audit(github_url)
        except RuntimeError as error:
            error_msg = str(error)
            st.error(error_msg)
            # Show extra help when the issue is likely a private repo / bad token
            if any(keyword in error_msg for keyword in ("private", "401", "403", "404", "token", "permission", "not found")):
                st.info(
                    "**Accessing a private repository?**  \n"
                    "Make sure your `.env` file contains a valid `GITHUB_TOKEN` with the **`repo` scope** enabled.  \n"
                    "You can create or update a token at: "
                    "GitHub → Settings → Developer settings → Personal access tokens."
                )
        except Exception as error:
            st.error(f"An unexpected error occurred: {error}")

    def _load_and_render_report(self) -> None:
        report = st.session_state.get("report")
        if report:
            ReportRenderer(report).render()


class ReportRenderer:
    """Renders the complete audit report with all sections."""

    def __init__(self, report: dict):
        self.report = report
        self.overview = report.get("repo_overview", {})
        self.security_issues = report.get("security_issues", [])
        self.debt_issues = report.get("debt_issues", [])
        self.architecture_issues = [
            issue for issue in self.debt_issues if issue.get("type") == "architecture"
        ]

    def render(self) -> None:
        st.divider()
        ScoreboardRenderer(self.overview, self.security_issues, self.debt_issues).render()

        overview_tab, security_tab, architecture_tab, debt_tab, fixes_tab = st.tabs(
            ["Repo Overview", "Security Flaws", "Architecture", "Technical Debt", "AI Fixes"]
        )

        with overview_tab:
            OverviewRenderer(self.overview, self.report.get("executive_summary", "")).render()

        with security_tab:
            SecurityRenderer(self.security_issues).render()

        with architecture_tab:
            ArchitectureRenderer(self.architecture_issues, self.overview).render()

        with debt_tab:
            DebtRenderer(self.debt_issues).render()

        with fixes_tab:
            CodeDiffRenderer(self.report.get("code_diffs", [])).render()




class ScoreboardRenderer:
    """Renders the metrics scoreboard."""

    def __init__(self, overview: dict, security_issues: list, debt_issues: list):
        self.overview = overview
        self.security_issues = security_issues
        self.debt_issues = debt_issues

    def render(self) -> None:
        critical_count = sum(1 for issue in self.security_issues if issue.get("severity") == "CRITICAL")
        high_count = sum(1 for issue in self.security_issues if issue.get("severity") == "HIGH")

        col1, col2, col3 = st.columns(3)
        col1.metric("Security findings", len(self.security_issues))
        col2.metric("Critical / High", f"{critical_count} / {high_count}")
        col3.metric("Debt findings", len(self.debt_issues))


class OverviewRenderer:
    """Renders the repository overview section."""

    def __init__(self, overview: dict, executive_summary: str):
        self.overview = overview
        self.executive_summary = executive_summary

    def render(self) -> None:
        # ── SECTION 1: Plain-English Project Summary ──────────────────────────
        st.subheader("🧠 Project Overview")
        overview = self.overview.get("overview")
        if overview:
            st.success(overview)
        else:
            st.write("No overview was generated.")

        if self.overview.get("analysis_source"):
            st.caption(f"Analysis source: {self.overview.get('analysis_source')}")

        # ── SECTION 2: Flowchart ───────────────────────────────────────────
        flowchart = self.overview.get("flowchart")
        if flowchart:
            st.subheader("⚙️ How It Works")
            for step in flowchart:
                st.write(f"➡️ {step}")

        # ── SECTION 3: Architecture ─────────────────────────
        architecture = self.overview.get("architecture")
        if architecture and isinstance(architecture, dict):
            arch_title = architecture.get("title", "Architecture")
            st.subheader(f"🏗️ {arch_title}")
            layers = architecture.get("layers", [])
            for layer in layers:
                st.write(f"**{layer.get('layer', 'Layer')} ({layer.get('name', 'Unknown')})**: {layer.get('role', '')}")

        # ── SECTION 4: How to Run ────────────────────────────────────────
        how_to_run = self.overview.get("how_to_run")
        if how_to_run:
            st.subheader("🚀 How to Run")
            for step in how_to_run:
                st.write(f"• {step}")

        # ── SECTION 5: Tech Stack ────────────────────────────────────────
        tech_stack = self.overview.get("tech_stack")
        if tech_stack:
            st.subheader("💻 Tech Stack")
            for item in tech_stack:
                if isinstance(item, dict):
                    st.write(f"**{item.get('category', 'Technology')} - {item.get('technology', 'Unknown')}**: {item.get('purpose', '')}")
                else:
                    st.write(f"• {item}")

        st.divider()

        st.divider()

        st.subheader("Executive Summary")
        st.write(self.executive_summary or "No executive summary was generated.")

    @staticmethod
    def _render_list(title: str, items, empty_text: str = "None detected.") -> None:
        st.write(title)
        normalized_items = UIUtils.normalize_items(items)
        if not normalized_items:
            st.caption(empty_text)
            return

        for item in normalized_items:
            st.write(f"- {item}")


class SecurityRenderer:
    """Renders security issues."""

    def __init__(self, security_issues: list):
        self.security_issues = security_issues

    def render(self) -> None:
        st.subheader("Security Flaws")
        if not self.security_issues:
            st.success("No security issues were found.")
            return

        for issue in self.security_issues:
            severity = issue.get("severity", "LOW")
            title = f"[{severity}] {issue.get('issue', 'Security issue')} - {issue.get('file', '')}:{issue.get('line', '')}"
            with st.expander(title):
                st.code(issue.get("snippet", ""), language=UIUtils.detect_code_language(issue.get("file", "")))
                st.write(issue.get("explanation", ""))


class ArchitectureRenderer:
    """Renders architecture issues."""

    def __init__(self, architecture_issues: list, overview: dict):
        self.architecture_issues = architecture_issues
        self.overview = overview

    def render(self) -> None:
        st.subheader("Architecture Issues")
        st.write(self.overview.get("architecture_style") or "Architecture style could not be determined.")

        if not self.architecture_issues:
            st.success("No architecture-specific debt was found.")
            return

        for issue in self.architecture_issues:
            title = f"{issue.get('issue', 'Architecture issue')} - {issue.get('file', '')}:{issue.get('line', '')}"
            with st.expander(title):
                st.code(issue.get("snippet", ""), language=UIUtils.detect_code_language(issue.get("file", "")))
                st.info(issue.get("suggestion", ""))


class DebtRenderer:
    """Renders technical debt issues."""

    def __init__(self, debt_issues: list):
        self.debt_issues = debt_issues

    def render(self) -> None:
        st.subheader("Technical Debt")
        if not self.debt_issues:
            st.success("No technical debt was found.")
            return

        for issue in self.debt_issues:
            issue_type = issue.get("type", "debt").replace("_", " ").title()
            title = f"[{issue_type}] {issue.get('issue', 'Debt issue')} - {issue.get('file', '')}:{issue.get('line', '')}"
            with st.expander(title):
                st.code(issue.get("snippet", ""), language=UIUtils.detect_code_language(issue.get("file", "")))
                st.info(issue.get("suggestion", ""))


class CodeDiffRenderer:
    """Renders code diff suggestions."""

    def __init__(self, code_diffs: list):
        self.code_diffs = code_diffs

    def render(self) -> None:
        st.subheader("Original Code vs AI-Suggested Code")
        if not self.code_diffs:
            st.info("No code fixes were generated.")
            return

        for diff in self.code_diffs:
            st.write(f"**{diff.get('issue_title', 'Suggested fix')}**")
            st.caption(diff.get("file", ""))
            left, right = st.columns(2)

            with left:
                st.write("Original")
                st.code(diff.get("original_code", ""), language=UIUtils.detect_code_language(diff.get("file", "")))

            with right:
                st.write("Suggested")
                st.code(diff.get("refactored_code", ""), language=UIUtils.detect_code_language(diff.get("file", "")))

            st.write(diff.get("explanation", ""))
            st.divider()


class UIUtils:
    """Utility functions for UI rendering."""

    @staticmethod
    def detect_code_language(filepath: str) -> str:
        extension = filepath.rsplit(".", 1)[-1].lower() if "." in filepath else ""
        return {
            "py": "python",
            "js": "javascript",
            "jsx": "javascript",
            "ts": "typescript",
            "tsx": "typescript",
            "java": "java",
            "go": "go",
            "rs": "rust",
            "rb": "ruby",
            "php": "php",
            "cs": "csharp",
            "cpp": "cpp",
            "c": "c",
            "sql": "sql",
            "html": "html",
            "css": "css",
            "json": "json",
            "yaml": "yaml",
            "yml": "yaml",
        }.get(extension, "text")

    @staticmethod
    def normalize_items(items) -> list[str]:
        if isinstance(items, list):
            return [str(item) for item in items if str(item).strip()]
        if isinstance(items, str) and items.strip():
            return [items.strip()]
        return []

    @staticmethod
    def fix_unicode_escapes(text: str) -> str:
        if not text:
            return text
        replacements = {
            r"\u2014": "—",
            r"\u2013": "–",
            r"\u2192": "→",
            r"\u26a0": "⚠",
            r"\u2705": "✅",
            r"\u251c": "├",
            r"\u2500": "─",
            r"\u2502": "│",
            r"\u2514": "└"
        }
        for escaped, actual in replacements.items():
            text = text.replace(escaped, actual)
        return text


if __name__ == "__main__":
    UIController().run()
