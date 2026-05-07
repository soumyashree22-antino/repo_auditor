from typing import Literal

from pydantic import BaseModel, Field


Severity = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
DebtType = Literal[
    "complexity",
    "duplication",
    "naming",
    "error_handling",
    "architecture",
    "dead_code",
]


class SecurityIssue(BaseModel):
    file: str = ""
    line: int = 1
    issue: str = ""
    severity: Severity = "LOW"
    snippet: str = ""
    explanation: str = ""


class DebtIssue(BaseModel):
    file: str = ""
    line: int = 1
    issue: str = ""
    type: DebtType = "architecture"
    snippet: str = ""
    suggestion: str = ""


class ArchitectureLayer(BaseModel):
    layer: str = ""
    name: str = ""
    role: str = ""

class ArchitectureInfo(BaseModel):
    title: str = ""
    layers: list[ArchitectureLayer] = Field(default_factory=list)

class TechStackItem(BaseModel):
    category: str = ""
    technology: str = ""
    purpose: str = ""



class RepoOverview(BaseModel):
    # --- New LLM Prompt Fields ---
    overview: str = ""
    architecture: ArchitectureInfo | dict = Field(default_factory=dict)
    flowchart: list[str] = Field(default_factory=list)
    graphviz_flowchart: str = ""
    how_to_run: list[str] = Field(default_factory=list)
    tech_stack: list[TechStackItem | dict] = Field(default_factory=list)

    # --- Technical fields ---
    analysis_source: str = ""



class CodeDiff(BaseModel):
    issue_title: str = ""
    file: str = ""
    original_code: str = ""
    refactored_code: str = ""
    explanation: str = ""


class FinalReport(BaseModel):
    repo_overview: RepoOverview = Field(default_factory=RepoOverview)
    security_issues: list[SecurityIssue] = Field(default_factory=list)
    debt_issues: list[DebtIssue] = Field(default_factory=list)
    executive_summary: str = ""
    code_diffs: list[CodeDiff] = Field(default_factory=list)
