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

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Primary language", self.overview.get("primary_language") or "Unknown")
        col2.metric("Security findings", len(self.security_issues))
        col3.metric("Critical / High", f"{critical_count} / {high_count}")
        col4.metric("Debt findings", len(self.debt_issues))


class OverviewRenderer:
    """Renders the repository overview section."""

    def __init__(self, overview: dict, executive_summary: str):
        self.overview = overview
        self.executive_summary = executive_summary

    def render(self) -> None:
        # ── SECTION 1: Plain-English Project Summary ──────────────────────────
        st.subheader("🧠 What Is This Project?")
        what_is = self.overview.get("what_is_this_project")
        aim = self.overview.get("project_aim")
        if what_is:
            st.success(what_is)
        if aim:
            st.info(f"**Why it exists:** {aim}")
        if not what_is and not aim:
            st.write(self.overview.get("overview") or "No overview was generated.")

        if self.overview.get("analysis_source"):
            st.caption(f"Analysis source: {self.overview.get('analysis_source')}")

        # ── SECTION 2: How It Works ───────────────────────────────────────────
        how_it_works = self.overview.get("how_it_works")
        if how_it_works:
            st.subheader("⚙️ How It Works")
            st.write("Here is what happens, step by step, when someone uses this project:")
            for step in how_it_works:
                st.write(f"➡️ {step}")

        # ── SECTION 3: Visual Architecture Flowchart ─────────────────────────
        mermaid_arch = self.overview.get("mermaid_architecture")
        if mermaid_arch and mermaid_arch.strip() and not mermaid_arch.startswith("No Mermaid"):
            st.subheader("🕸️ Architecture Visualizer")
            
            # Clean up the mermaid string to ensure it renders correctly
            # Sometimes LLMs wrap it in markdown codeblocks anyway despite instructions
            cleaned_mermaid = mermaid_arch.replace("```mermaid", "").replace("```", "").strip()
            
            # Render using Streamlit's native markdown support for mermaid
            st.markdown(f"```mermaid\n{cleaned_mermaid}\n```")

        # ── SECTION 4: Agents & Models ────────────────────────────────────────
        agents_used = self.overview.get("agents_used")
        models_used = self.overview.get("models_used")
        if agents_used or models_used:
            st.subheader("🤖 AI Workers & Models Used")
            agent_col, model_col = st.columns(2)
            with agent_col:
                if agents_used:
                    st.write("**AI Workers (Agents)**")
                    for agent in agents_used:
                        st.write(f"• {agent}")
                else:
                    st.caption("No AI agents detected.")
            with model_col:
                if models_used:
                    st.write("**AI Models Used**")
                    for model in models_used:
                        st.write(f"• {model}")
                else:
                    st.caption("No specific AI models detected.")

        # ── SECTION 4: README ─────────────────────────────────────────────────
        readme = self.overview.get("readme_content")
        if readme and readme.strip() and readme.strip() != "No README found.":
            st.subheader("📄 README")
            with st.expander("Click to read the full README", expanded=True):
                st.markdown(readme)

        st.divider()

        # ── SECTION 5: Stats & Technical Details ─────────────────────────────
        st.subheader("📊 Repository Stats")
        if self.overview.get("main_objective"):
            st.info(f"**Main Objective:** {self.overview.get('main_objective')}")

        stat1, stat2, stat3, stat4 = st.columns(4)
        stat1.metric("Repository type", self.overview.get("repository_type") or "Unknown")
        stat2.metric("Files read", self.overview.get("file_count") or 0)
        stat3.metric("Source files", self.overview.get("source_file_count") or 0)
        stat4.metric("Directories", self.overview.get("directory_count") or 0)

        col1, col2 = st.columns(2)
        with col1:
            st.write("Architecture style")
            st.info(self.overview.get("architecture_style") or "Unknown")
            self._render_list("Languages", self.overview.get("languages"))
            self._render_list("Frameworks", self.overview.get("frameworks"))
            self._render_list("Tech stack", self.overview.get("tech_stack"))

        with col2:
            self._render_list("Entry points", self.overview.get("entry_points"))
            self._render_list("Setup and runtime", self.overview.get("setup_and_runtime"))
            self._render_list("Environment variables", self.overview.get("environment_variables"))

        st.subheader("Architecture and Project Structure")
        arch_left, arch_right = st.columns([1, 1])
        with arch_left:
            self._render_list("Architectural layers", self.overview.get("architectural_layers"))
        with arch_right:
            project_structure = self.overview.get("project_structure")
            st.write("Project structure")
            if project_structure:
                st.code(project_structure, language="text")
            else:
                st.caption("No project structure was generated.")

        st.subheader("Modules and Data Flow")
        flow_left, flow_right = st.columns(2)
        with flow_left:
            self._render_list(
                "Main modules",
                self.overview.get("module_details") or self.overview.get("main_modules"),
            )
        with flow_right:
            self._render_list("Data flow", self.overview.get("data_flow"))

        st.subheader("Surface Area")
        surface_left, surface_right = st.columns(2)
        with surface_left:
            self._render_list("API endpoints", self.overview.get("api_endpoints"))
            self._render_list("External integrations", self.overview.get("external_integrations"))
        with surface_right:
            self._render_list("Config files", self.overview.get("config_files"))
            self._render_list("Test files", self.overview.get("test_files"))
            self._render_list("Files to read first", self.overview.get("notable_files"))

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


if __name__ == "__main__":
    UIController().run()
