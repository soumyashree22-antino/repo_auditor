import json
import re
import sys
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from models.report import RepoOverview
from tools.code_parser import (
    LANGUAGE_BY_EXTENSION,
    get_extension,
    get_file_tree,
    get_key_files,
    get_project_tree,
    guess_primary_language,
    is_code_file,
)
from tools.json_utils import extract_json_object
from tools.llm_client import call_llm
from tools.github_fetcher import get_readme_content

load_dotenv()


def load_prompt(name: str) -> str:
    with open(f"prompts/{name}", "r", encoding="utf-8") as file:
        return file.read()


def run_mapper(state: dict) -> dict:
    return RepositoryMapper().run(state)


class RepositoryMapper:
    """Builds the repository overview shown in the Repo Overview tab."""

    def run(self, state: dict) -> dict:
        file_contents = state["file_contents"]
        fallback = build_fallback_overview(file_contents)

        try:
            raw_text = call_llm(
                system_prompt=load_prompt("mapper_prompt.txt"),
                user_message=build_mapper_message(file_contents, fallback),
                max_tokens=3000,
            )
            if not raw_text:
                print("LLM call failed or returned empty response")
                mapper_output = fallback
            else:
                print(f"LLM Response (first 200 chars):\n{raw_text[:200]}")
                parsed = parse_json(raw_text, fallback)
                
                if parsed is fallback:
                    mapper_output = fallback
                else:
                    final = dict(fallback)
                    non_technical_fields = [
                        "what_is_this_project", "project_aim", "main_objective",
                        "overview", "how_it_works", "agents_used", "models_used",
                        "architecture_style", "main_modules", "module_details",
                        "architectural_layers", "data_flow", "external_integrations",
                        "frameworks", "tech_stack", "repository_type", "notable_files"
                    ]
                    for field in non_technical_fields:
                        if field in parsed and parsed[field] not in ("", [], {}, None):
                            final[field] = parsed[field]
                            
                    import os
                    final["analysis_source"] = os.getenv("LLM_PROVIDER", "nvidia")
                    mapper_output = RepoOverview.model_validate(final).model_dump()
        except Exception as error:
            print(f"Mapper failed: {error}")
            mapper_output = fallback

        # Override readme_content with the raw fetched text to prevent LLM truncation
        mapper_output["readme_content"] = get_readme_content(file_contents)

        return {**state, "mapper_output": mapper_output}

def build_mapper_message(file_contents: dict[str, str], local_analysis: dict) -> str:
    key_files = get_key_files(file_contents)
    file_tree = get_file_tree(file_contents)

    message = f"FILE TREE:\n{file_tree}\n\nKEY FILES:\n"
    for path, content in key_files.items():
        message += f"\n--- {path} ---\n{content[:3000]}\n"
    return message


def build_fallback_overview(file_contents: dict[str, str]) -> dict:
    file_paths = sorted(file_contents.keys())
    top_folders = sorted({path.split("/", 1)[0] for path in file_paths if "/" in path})
    entry_points = [
        path
        for path in file_paths
        if path.rsplit("/", 1)[-1].lower()
        in {
            "app.py",
            "main.py",
            "index.js",
            "index.ts",
            "server.js",
            "server.ts",
            "main.go",
            "main.rs",
            "manage.py",
            "wsgi.py",
            "asgi.py",
        }
    ]
    frameworks = detect_frameworks(file_contents)
    dependencies = detect_dependencies(file_contents)
    source_file_count = sum(1 for path in file_paths if is_code_file(path))
    directory_count = count_directories(file_paths)
    architecture_style = detect_architecture_style(frameworks, top_folders, file_paths)
    primary_language = guess_primary_language(file_contents)

    return {
        "analysis_source": "Local static analysis",
        "primary_language": primary_language,
        "repository_type": detect_repository_type(frameworks, top_folders, file_paths),
        "file_count": len(file_paths),
        "source_file_count": source_file_count,
        "directory_count": directory_count,
        "languages": summarize_languages(file_contents),
        "frameworks": frameworks,
        "tech_stack": merge_unique(frameworks + dependencies)[:30],
        "architecture_style": architecture_style,
        "project_structure": get_project_tree(file_contents),
        "architectural_layers": detect_architectural_layers(frameworks, top_folders, file_paths),
        "main_modules": [humanize_path_name(folder) for folder in top_folders[:10]],
        "module_details": build_module_details(top_folders, file_paths),
        "entry_points": entry_points[:10],
        "api_endpoints": detect_api_endpoints(file_contents),
        "data_flow": infer_data_flow(frameworks, entry_points),
        "external_integrations": detect_external_integrations(file_contents, dependencies),
        "environment_variables": detect_environment_variables(file_contents),
        "setup_and_runtime": detect_setup_and_runtime(file_contents),
        "config_files": detect_config_files(file_paths),
        "test_files": detect_test_files(file_paths),
        "notable_files": detect_notable_files(file_paths, entry_points),
        "overview": build_local_overview(
            primary_language,
            frameworks,
            architecture_style,
            len(file_paths),
            source_file_count,
            top_folders,
            entry_points,
        ),
    }


def detect_frameworks(file_contents: dict[str, str]) -> list[str]:
    dependency_text = "\n".join(
        content
        for path, content in file_contents.items()
        if path.rsplit("/", 1)[-1].lower()
        in {"package.json", "requirements.txt", "pyproject.toml", "poetry.lock", "pom.xml", "go.mod"}
    ).lower()
    combined = (dependency_text or "\n".join(file_contents.values())).lower()
    framework_checks = {
        "Streamlit": "streamlit",
        "FastAPI": "fastapi",
        "Flask": "flask",
        "Django": "django",
        "React": "react",
        "Next.js": "next",
        "Express": "express",
        "LangGraph": "langgraph",
        "Pydantic": "pydantic",
    }
    return [name for name, marker in framework_checks.items() if marker in combined]


def summarize_languages(file_contents: dict[str, str]) -> list[str]:
    counts: Counter[str] = Counter()
    for path, content in file_contents.items():
        language = LANGUAGE_BY_EXTENSION.get(get_extension(path))
        if language:
            counts[language] += max(1, len(content.splitlines()))
    return [f"{language} ({line_count} lines)" for language, line_count in counts.most_common()]


def detect_dependencies(file_contents: dict[str, str]) -> list[str]:
    dependencies: list[str] = []
    for path, content in file_contents.items():
        filename = path.rsplit("/", 1)[-1].lower()
        if filename == "requirements.txt":
            dependencies.extend(parse_requirements(content))
        elif filename == "package.json":
            dependencies.extend(parse_package_json(content))
        elif filename == "pyproject.toml":
            dependencies.extend(parse_pyproject_dependencies(content))
    return merge_unique(dependencies)


def parse_requirements(content: str) -> list[str]:
    dependencies = []
    for line in content.splitlines():
        stripped = line.split("#", 1)[0].strip()
        if not stripped or stripped.startswith("-"):
            continue
        dependencies.append(re.split(r"[<>=~!]", stripped, maxsplit=1)[0].strip())
    return dependencies


def parse_package_json(content: str) -> list[str]:
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return []

    dependencies = []
    for section in ("dependencies", "devDependencies"):
        values = data.get(section, {})
        if isinstance(values, dict):
            dependencies.extend(values.keys())
    return dependencies


def parse_pyproject_dependencies(content: str) -> list[str]:
    dependencies = []
    for line in content.splitlines():
        stripped = line.strip().strip('"').strip("'")
        if not stripped or stripped.startswith(("[", "#")):
            continue
        if re.match(r"^[A-Za-z0-9_.-]+[<>=~!]", stripped):
            dependencies.append(re.split(r"[<>=~!]", stripped, maxsplit=1)[0])
    return dependencies


def count_directories(file_paths: list[str]) -> int:
    directories = set()
    for path in file_paths:
        parts = path.split("/")[:-1]
        for index in range(1, len(parts) + 1):
            directories.add("/".join(parts[:index]))
    return len(directories)


def detect_repository_type(frameworks: list[str], top_folders: list[str], file_paths: list[str]) -> str:
    lower_folders = {folder.lower() for folder in top_folders}
    if "FastAPI" in frameworks and "Next.js" in frameworks:
        return "Full-stack AI/web application"
    if "FastAPI" in frameworks:
        return "Python API service"
    if "Next.js" in frameworks or "React" in frameworks:
        return "JavaScript web application"
    if "Streamlit" in frameworks:
        return "Streamlit data application"
    if {"frontend", "backend"} & lower_folders or {"api", "web"} & lower_folders:
        return "Client/server application"
    if any(path.lower().startswith("agents/") for path in file_paths):
        return "AI agent application"
    return "Software project"



def detect_architecture_style(frameworks: list[str], top_folders: list[str], file_paths: list[str]) -> str:
    """Detect and describe the overall architectural style in detail."""
    analyzer = ArchitectureStyleAnalyzer(frameworks, top_folders, file_paths)
    return analyzer.get_detailed_style_description()


class ArchitectureStyleAnalyzer:
    """Analyzes and describes the overall architecture style of a repository."""

    def __init__(self, frameworks: list[str], top_folders: list[str], file_paths: list[str]):
        self.frameworks = frameworks
        self.top_folders = top_folders
        self.lower_folders = {folder.lower() for folder in top_folders}
        self.file_paths = file_paths

    def get_detailed_style_description(self) -> str:
        """Determine architecture style and provide detailed explanation."""
        if "FastAPI" in self.frameworks and "Next.js" in self.frameworks:
            return self._describe_fullstack_architecture()
        elif "FastAPI" in self.frameworks or "Flask" in self.frameworks:
            return self._describe_rest_api_architecture()
        elif "Next.js" in self.frameworks or "React" in self.frameworks:
            return self._describe_spa_architecture()
        elif "Streamlit" in self.frameworks:
            return self._describe_streamlit_architecture()
        elif {"agents", "tools", "prompts"} <= self.lower_folders:
            return self._describe_multiagent_pipeline_architecture()
        elif any(path.endswith("docker-compose.yml") for path in self.file_paths):
            return self._describe_containerized_architecture()
        else:
            return self._describe_modular_architecture()

    def _describe_fullstack_architecture(self) -> str:
        return (
            "Full-stack client/server architecture with FastAPI backend and Next.js frontend. "
            "This architecture separates concerns into independent frontend and backend applications. "
            "The backend provides REST API endpoints with automatic OpenAPI documentation, request validation, and async processing. "
            "The frontend implements file-based routing with server-side rendering and static generation capabilities. "
            "Communication flows through HTTP APIs with JSON payloads. This separation enables independent deployment, scaling, "
            "and technology choices for each layer. TypeScript ensures type safety across both frontend and backend when used consistently. "
            "The architecture supports progressive enhancement and can serve multiple client types (web, mobile, desktop)."
        )

    def _describe_rest_api_architecture(self) -> str:
        api_framework = "FastAPI" if "FastAPI" in self.frameworks else "Flask" if "Flask" in self.frameworks else "custom"
        return (
            f"REST API service architecture built with {api_framework} following RESTful principles. "
            "This architecture focuses on exposing resources through HTTP endpoints organized by entity types. "
            "Each endpoint supports standard HTTP methods (GET, POST, PUT, DELETE) with appropriate status codes and error responses. "
            "The API layer handles request validation, authentication, and response serialization. Service classes contain business logic "
            "while models define data contracts. This architectural style enables easy integration with diverse client applications, supports "
            "API versioning for backward compatibility, and facilitates testing through HTTP clients. The API can be documented with OpenAPI/Swagger "
            "specifications for client code generation and interactive exploration."
        )

    def _describe_spa_architecture(self) -> str:
        framework = "Next.js" if "Next.js" in self.frameworks else "React"
        return (
            f"Single Page Application (SPA) architecture built with {framework}. "
            f"This architecture delivers the entire UI as a single HTML page with dynamic content updates using JavaScript. "
            f"The {framework} framework manages routing, component rendering, and state management on the client side. "
            "API calls are made to backend services to fetch and persist data. The browser handles all routing and navigation without "
            "full page reloads, providing a smooth user experience. Build tools bundle and optimize JavaScript for efficient loading. "
            "The architecture supports offline capabilities with service workers and progressive web app patterns. Client-side state management "
            "handles UI state while server state resides in backend databases. This approach enables responsive interfaces and reduces server load."
        )

    def _describe_streamlit_architecture(self) -> str:
        return (
            "Single-page Streamlit data application architecture. "
            "Streamlit provides a declarative framework for building interactive data applications with minimal frontend code. "
            "The entire application is a single Python script that runs top-to-bottom for each user interaction. Streamlit manages session state, "
            "widget state, and UI rendering automatically. The architecture combines UI definition, business logic, and data fetching in one layer. "
            "This approach is ideal for rapid prototyping, data visualization, and interactive dashboards where quick iteration is valued. "
            "Streamlit handles caching for performance optimization and supports deployment on cloud platforms. The architecture simplifies development "
            "for data scientists and analysts who prefer Python over web development frameworks."
        )

    def _describe_multiagent_pipeline_architecture(self) -> str:
        framework_desc = (
            "with LangGraph state machines" if "LangGraph" in self.frameworks 
            else "using sequential or parallel orchestration"
        )
        return (
            f"Multi-agent pipeline architecture {framework_desc} enabling complex AI-powered workflows. "
            "This architecture orchestrates multiple specialized agents that collaborate to solve complex problems. "
            "Each agent handles specific tasks and can call tools or other agents. Agents maintain conversation history and context "
            "across interactions. The pipeline architecture supports both sequential execution (one agent after another) and parallel execution (multiple agents concurrently). "
            "Shared tools provide consistent interfaces to external systems and databases. Prompts are templated and injected at runtime for flexibility. "
            "The architecture enables systematic error handling with fallbacks and retries. This pattern is ideal for complex reasoning tasks, multi-step workflows, "
            "and applications requiring iterative refinement of results."
        )

    def _describe_containerized_architecture(self) -> str:
        return (
            "Containerized application architecture using Docker and docker-compose for orchestration. "
            "Services are packaged as independent Docker containers with defined dependencies in docker-compose configuration. "
            "Each container encapsulates a service with its runtime, dependencies, and code. The architecture enables consistent deployment "
            "across development, testing, and production environments. Services communicate through defined networks and shared volumes. "
            "Docker enables easy scaling by running multiple container instances. The compose file defines service configuration, environment variables, "
            "port mappings, and inter-service dependencies. This architecture supports microservices patterns where different services handle different concerns. "
            "Container orchestration enables automatic service discovery, load balancing, and service restarts on failure."
        )

    def _describe_modular_architecture(self) -> str:
        return (
            "Modular application architecture organized by top-level folders and entry files. "
            "This architecture structures the codebase into logical modules based on functional boundaries or domain areas. "
            "Each module groups related files and encapsulates specific functionality. The architecture relies on clear separation of concerns "
            "with defined interfaces between modules. Entry points (main.py, app.py, index.js) bootstrap the application and coordinate module initialization. "
            "This pattern is common in smaller applications and libraries. To improve maintainability, consider introducing explicit architectural layers "
            "(presentation, business logic, data access) or adopting established patterns like MVC, MVVM, or hexagonal architecture as the codebase grows."
        )



def detect_architectural_layers(frameworks: list[str], top_folders: list[str], file_paths: list[str]) -> list[str]:
    """Detect and describe architectural layers with detailed explanations."""
    analyzer = ArchitecturalLayerAnalyzer(frameworks, top_folders, file_paths)
    return analyzer.generate_layer_descriptions()


class ArchitecturalLayerAnalyzer:
    """Analyzes repository structure and generates detailed architectural layer descriptions."""

    def __init__(self, frameworks: list[str], top_folders: list[str], file_paths: list[str]):
        self.frameworks = frameworks
        self.top_folders = top_folders
        self.lower_folders = {folder.lower() for folder in top_folders}
        self.file_paths = file_paths

    def generate_layer_descriptions(self) -> list[str]:
        """Generate comprehensive architectural layer descriptions."""
        layers = []

        # Presentation layer
        if self._has_presentation_layer():
            layers.append(self._describe_presentation_layer())

        # API/Backend layer
        if self._has_api_layer():
            layers.append(self._describe_api_layer())

        # Service/Business logic layer
        if self._has_service_layer():
            layers.append(self._describe_service_layer())

        # AI/LLM layer
        if self._has_ai_layer():
            layers.append(self._describe_ai_layer())

        # Domain/Data layer
        if self._has_domain_layer():
            layers.append(self._describe_domain_layer())

        # Infrastructure/Utilities layer
        if self._has_infrastructure_layer():
            layers.append(self._describe_infrastructure_layer())

        # Test layer
        if self._has_test_layer():
            layers.append(self._describe_test_layer())

        if not layers:
            layers.append(
                "Module layer: Repository behavior is organized primarily by top-level folders and entry files. "
                "Each module encapsulates specific functionality. Consider introducing explicit architectural layers "
                "(presentation, business logic, data access) to improve code organization and maintainability."
            )

        return layers

    def _has_presentation_layer(self) -> bool:
        return ("Next.js" in self.frameworks or "React" in self.frameworks or 
                "Streamlit" in self.frameworks or {"frontend", "web", "client", "ui"} & self.lower_folders)

    def _has_api_layer(self) -> bool:
        return ("FastAPI" in self.frameworks or "Flask" in self.frameworks or 
                "Express" in self.frameworks or {"api", "backend", "server", "routes"} & self.lower_folders)

    def _has_service_layer(self) -> bool:
        return any("service" in folder.lower() for folder in self.top_folders)

    def _has_ai_layer(self) -> bool:
        return {"agents", "prompts", "ai"} & self.lower_folders or "LangGraph" in self.frameworks

    def _has_domain_layer(self) -> bool:
        return ({"models", "schemas", "entities", "domain"} & self.lower_folders or 
                "Pydantic" in self.frameworks or any("model" in path.lower() for path in self.file_paths))

    def _has_infrastructure_layer(self) -> bool:
        return {"tools", "utils", "lib", "helpers", "common", "config"} & self.lower_folders

    def _has_test_layer(self) -> bool:
        return any(path.lower().startswith(("tests/", "test/", "__tests__/")) or 
                  ".test." in path.lower() or path.endswith(("_test.py", ".spec.py")) 
                  for path in self.file_paths)

    def _describe_presentation_layer(self) -> str:
        """Detailed presentation layer description."""
        if "Streamlit" in self.frameworks:
            return (
                "Presentation layer: Streamlit-based user interface that renders interactive dashboards and forms. "
                "This layer handles all user-facing components including input widgets, data visualizations, and navigation. "
                "Streamlit manages state, session variables, and real-time updates. The UI communicates directly with backend "
                "services to fetch data and trigger business logic execution. No complex frontend routing logic is needed as "
                "Streamlit handles the entire UI lifecycle."
            )
        elif "Next.js" in self.frameworks:
            return (
                "Presentation layer: Next.js frontend with file-based routing and server-side rendering capabilities. "
                "This layer includes React components for UI rendering, page layouts, and client-side interactivity. "
                "The layer handles form submission, data fetching via API routes or client-side calls, and manages client-side state. "
                "Next.js enables static site generation and incremental static regeneration for performance optimization. "
                "TypeScript may be used for type safety across components."
            )
        else:
            return (
                "Presentation layer: Browser-based user interface built with frontend technologies. "
                "This layer contains all visual components, routing, state management, and user interactions. "
                "It communicates with backend services through HTTP APIs or WebSockets. The layer is responsible for "
                "rendering data, handling user input validation, managing UI state, and providing responsive layouts. "
                "Modern frontend frameworks handle component lifecycle, event handling, and DOM management."
            )

    def _describe_api_layer(self) -> str:
        """Detailed API layer description."""
        if "FastAPI" in self.frameworks:
            return (
                "API layer: FastAPI-based REST API providing HTTP endpoints for business operations. "
                "This layer defines routes with automatic OpenAPI documentation, request/response validation using Pydantic models, "
                "and dependency injection for middleware and authentication. FastAPI handles async request processing, enabling "
                "high-performance concurrent request handling. The layer manages HTTP status codes, error responses, and follows "
                "RESTful conventions. CORS policies and security headers are configured here."
            )
        elif "Flask" in self.frameworks:
            return (
                "API layer: Flask-based REST API providing lightweight HTTP endpoints. "
                "This layer defines routes, handles request parsing and response serialization, and manages middleware. "
                "Flask enables flexible request handling with decorators for routing, authentication, and error handling. "
                "The layer manages HTTP method handling (GET, POST, PUT, DELETE), request validation, and error responses. "
                "Blueprints may be used to organize routes into logical groups."
            )
        elif "Express" in self.frameworks:
            return (
                "API layer: Express.js-based REST API providing Node.js HTTP endpoints. "
                "This layer defines routes with middleware support for authentication, logging, and request processing. "
                "Express handles request parsing, response formatting, and HTTP status management. The layer supports "
                "async/await patterns for non-blocking I/O operations. Middleware chains enable layered request processing, "
                "error handling, and cross-cutting concerns like CORS and compression."
            )
        else:
            return (
                "API layer: HTTP routes and backend request handling. "
                "This layer exposes endpoints for client applications and external integrations. "
                "It manages request validation, authentication, authorization, and response formatting. "
                "The layer handles business logic invocation, error processing, and appropriate HTTP status responses. "
                "API contracts are defined through documentation or schema specifications."
            )

    def _describe_service_layer(self) -> str:
        """Detailed service layer description."""
        return (
            "Service layer: Application workflow and business logic modules. "
            "This layer contains the core business rules, data processing logic, and orchestration of operations. "
            "Services coordinate between API endpoints and data access layers, implementing domain-specific workflows. "
            "The layer is responsible for transaction management, validation rules, caching strategies, and external service calls. "
            "Services are designed to be testable and reusable across different API endpoints. Domain objects and value objects "
            "flow through this layer, and business exceptions are handled here."
        )

    def _describe_ai_layer(self) -> str:
        """Detailed AI layer description."""
        if "LangGraph" in self.frameworks:
            return (
                "AI layer: LangGraph-based multi-agent system with stateful workflows and tool integration. "
                "This layer defines agent behavior through prompt templates, LLM model calls, and tool definitions. "
                "Agents coordinate complex tasks through graph-based state machines where nodes represent operations and edges "
                "represent transitions. The layer manages LLM interactions, token usage, and response parsing. Tool calls enable "
                "agents to interact with external systems and databases. Memory and context management maintain state across "
                "agent invocations."
            )
        else:
            return (
                "AI layer: Agent prompts, model calls, and LLM-based analysis steps. "
                "This layer encapsulates all interaction with language models and AI services. "
                "It manages prompt engineering, model selection, token usage optimization, and response parsing. "
                "The layer handles temperature and parameter tuning for different use cases. Prompt templates are stored separately "
                "and injected at runtime. The layer manages retries for transient failures and implements circuit breakers for "
                "external AI service calls."
            )

    def _describe_domain_layer(self) -> str:
        """Detailed domain layer description."""
        return (
            "Domain/data layer: Typed models, validation schemas, and shared data contracts. "
            "This layer defines the core data structures using Pydantic models or equivalent type systems. "
            "Models include validation rules, default values, and field constraints. The layer establishes contracts between "
            "API and service layers, ensuring type safety and data consistency. Models are serializable to JSON for API responses. "
            "Business entities are represented here with their attributes and relationships. Database models and ORM entities may "
            "coexist with API request/response schemas for clear separation of concerns."
        )

    def _describe_infrastructure_layer(self) -> str:
        """Detailed infrastructure layer description."""
        return (
            "Infrastructure/helper layer: Reusable utilities, external API clients, and parsing code. "
            "This layer provides cross-cutting services including database connections, HTTP client setup, logging configuration, "
            "and authentication utilities. External API integrations are handled here with standardized client patterns. "
            "Code parsing, file handling, and text processing utilities are located in this layer. Configuration management, "
            "environment variable handling, and secret management are centralized. The layer provides low-level abstractions that "
            "higher layers depend on."
        )

    def _describe_test_layer(self) -> str:
        """Detailed test layer description."""
        return (
            "Test layer: Automated tests and verification files. "
            "This layer includes unit tests for individual functions and classes, integration tests for service interactions, "
            "and end-to-end tests for complete workflows. Test fixtures and factories provide test data setup. Mock objects and "
            "stubs enable isolated testing of components. Test coverage reports identify untested code paths. The layer validates "
            "business logic correctness, error handling, and edge cases. Performance and load testing may also be included."
        )


def build_module_details(top_folders: list[str], file_paths: list[str]) -> list[str]:
    details = []
    for folder in top_folders[:12]:
        module_files = [path for path in file_paths if path.startswith(f"{folder}/")]
        important_files = [
            path
            for path in module_files
            if path.rsplit("/", 1)[-1].lower()
            in {"main.py", "app.py", "index.js", "index.ts", "route.ts", "package.json", "requirements.txt"}
        ][:4]
        description = describe_folder(folder)
        file_note = f"{len(module_files)} file(s)"
        if important_files:
            file_note += f"; key files: {', '.join(important_files)}"
        details.append(f"{humanize_path_name(folder)}: {description} ({file_note}).")
    return details



def describe_folder(folder: str) -> str:
    name = folder.lower()
    if "api" in name or "service" in name or "backend" in name:
        return "backend service or API code"
    if "web" in name or "frontend" in name or "client" in name or "node" in name:
        return "frontend or Node.js integration code"
    if "agent" in name:
        return "AI agent logic"
    if "model" in name or "schema" in name:
        return "data models and schemas"
    if "tool" in name or "util" in name:
        return "shared helper utilities"
    if "prompt" in name:
        return "LLM prompt templates"
    if "test" in name:
        return "tests and verification code"
    return "project module"


def detect_api_endpoints(file_contents: dict[str, str]) -> list[str]:
    endpoints = []
    route_pattern = re.compile(
        r"[@\s](?:app|router)\.(get|post|put|patch|delete|options|head)\(\s*['\"]([^'\"]+)['\"]",
        flags=re.IGNORECASE,
    )
    express_pattern = re.compile(
        r"(?:app|router)\.(get|post|put|patch|delete|options|head)\(\s*['\"]([^'\"]+)['\"]",
        flags=re.IGNORECASE,
    )
    next_method_pattern = re.compile(r"export\s+(?:async\s+)?function\s+(GET|POST|PUT|PATCH|DELETE)")

    for path, content in file_contents.items():
        for method, route in route_pattern.findall(content):
            endpoints.append(f"{method.upper()} {route} ({path})")
        for method, route in express_pattern.findall(content):
            endpoints.append(f"{method.upper()} {route} ({path})")
        if path.endswith(("/route.ts", "/route.js")):
            for method in next_method_pattern.findall(content):
                endpoints.append(f"{method.upper()} {path}")
    return merge_unique(endpoints)[:30]


def detect_environment_variables(file_contents: dict[str, str]) -> list[str]:
    patterns = [
        re.compile(r"os\.getenv\(\s*['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]"),
        re.compile(r"os\.environ(?:\.get)?\(\s*['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]"),
        re.compile(r"os\.environ\[\s*['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]\s*\]"),
        re.compile(r"process\.env\.([A-Za-z_][A-Za-z0-9_]*)"),
        re.compile(r"import\.meta\.env\.([A-Za-z_][A-Za-z0-9_]*)"),
    ]
    variables = []
    for content in file_contents.values():
        for pattern in patterns:
            variables.extend(pattern.findall(content))
    return merge_unique(variables)[:40]


def detect_external_integrations(file_contents: dict[str, str], dependencies: list[str]) -> list[str]:
    combined = "\n".join(file_contents.values()).lower()
    dependency_text = " ".join(dependencies).lower()
    checks = {
        "GitHub API": ["api.github.com", "github_token", "github"],
        "Ollama": ["ollama", "localhost:11434"],
        "OpenAI": ["openai"],
        "Anthropic": ["anthropic", "sk-ant"],
        "PostgreSQL": ["postgres", "psycopg"],
        "MongoDB": ["mongodb", "mongoose"],
        "Redis": ["redis"],
        "Stripe": ["stripe"],
        "Supabase": ["supabase"],
        "Firebase": ["firebase"],
    }
    integrations = []
    for name, markers in checks.items():
        haystack = f"{combined}\n{dependency_text}"
        if any(marker in haystack for marker in markers):
            integrations.append(name)
    return integrations


def detect_setup_and_runtime(file_contents: dict[str, str]) -> list[str]:
    commands = []
    for path, content in file_contents.items():
        filename = path.rsplit("/", 1)[-1].lower()
        if filename in {"readme.md", "readme.txt", "readme"}:
            for line in content.splitlines():
                stripped = line.strip().strip("`")
                if re.match(r"^(python|pip|uv|poetry|npm|pnpm|yarn|docker|streamlit|uvicorn)\b", stripped):
                    commands.append(stripped)
        if filename == "package.json":
            commands.extend(parse_package_scripts(content))
    if any(path.endswith("requirements.txt") for path in file_contents):
        commands.append("pip install -r requirements.txt")
    return merge_unique(commands)[:20]


def parse_package_scripts(content: str) -> list[str]:
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return []
    scripts = data.get("scripts", {})
    if not isinstance(scripts, dict):
        return []
    return [f"npm run {name}: {command}" for name, command in scripts.items()]


def detect_config_files(file_paths: list[str]) -> list[str]:
    config_names = {
        ".env.example",
        "dockerfile",
        "docker-compose.yml",
        "package.json",
        "requirements.txt",
        "pyproject.toml",
        "tsconfig.json",
        "next.config.js",
        "next.config.ts",
        "vite.config.ts",
        "tailwind.config.js",
    }
    return [
        path
        for path in file_paths
        if path.rsplit("/", 1)[-1].lower() in config_names
        or path.lower().endswith((".config.js", ".config.ts", ".config.json", ".yml", ".yaml", ".toml"))
    ][:30]


def detect_test_files(file_paths: list[str]) -> list[str]:
    return [
        path
        for path in file_paths
        if re.search(r"(^|/)(tests?|__tests__)/", path.lower())
        or re.search(r"(\.test|\.spec|_test)\.", path.lower())
        or path.lower().startswith("test_")
    ][:30]


def detect_notable_files(file_paths: list[str], entry_points: list[str]) -> list[str]:
    notable_names = {
        "readme.md",
        "package.json",
        "requirements.txt",
        "pyproject.toml",
        "dockerfile",
        "docker-compose.yml",
        "main.py",
        "app.py",
        "server.js",
        "index.js",
    }
    notable = [
        path
        for path in file_paths
        if path in entry_points or path.rsplit("/", 1)[-1].lower() in notable_names
    ]
    return merge_unique(notable)[:30]


def infer_data_flow(frameworks: list[str], entry_points: list[str]) -> list[str]:
    flow = []
    if entry_points:
        flow.append(f"Execution starts from {', '.join(entry_points[:3])}.")
    if "Next.js" in frameworks and "FastAPI" in frameworks:
        flow.append("The frontend likely sends user actions to backend API routes exposed by FastAPI.")
    elif "FastAPI" in frameworks:
        flow.append("HTTP requests enter through FastAPI route handlers and are delegated into service modules.")
    elif "Streamlit" in frameworks:
        flow.append("Users interact through the Streamlit page, which calls Python functions directly on each run.")
    if "Pydantic" in frameworks:
        flow.append("Pydantic models are used to validate or structure data crossing module boundaries.")
    return flow


def build_local_overview(
    primary_language: str,
    frameworks: list[str],
    architecture_style: str,
    file_count: int,
    source_file_count: int,
    top_folders: list[str],
    entry_points: list[str],
) -> str:
    language = primary_language or "mixed-language"
    framework_text = ", ".join(frameworks) if frameworks else "no major framework detected"
    module_text = ", ".join(top_folders[:5]) if top_folders else "root-level files"
    entry_text = ", ".join(entry_points[:3]) if entry_points else "no obvious entry point"
    return (
        f"This repository appears to be a {language} project using {framework_text}. "
        f"It contains {file_count} readable file(s), including {source_file_count} source file(s), "
        f"organized mainly around {module_text}. "
        f"The likely architecture is: {architecture_style}. Primary runtime entry point(s): {entry_text}."
    )


def humanize_path_name(path: str) -> str:
    return path.replace("_", " ").replace("-", " ").strip().title()


def merge_unique(items: list[str]) -> list[str]:
    seen = set()
    unique = []
    for item in items:
        if not item:
            continue
        normalized = str(item).strip()
        key = normalized.lower()
        if normalized and key not in seen:
            seen.add(key)
            unique.append(normalized)
    return unique


def merge_overview(fallback: dict, parsed: dict) -> dict:
    merged = dict(fallback)
    for key, value in parsed.items():
        if value not in ("", [], {}, None):
            merged[key] = value

    for key in (
        "agents_used",
        "models_used",
        "how_it_works",
        "frameworks",
        "tech_stack",
        "languages",
        "architectural_layers",
        "main_modules",
        "module_details",
        "component_map",
        "entry_points",
        "api_endpoints",
        "data_flow",
        "external_integrations",
        "environment_variables",
        "setup_and_runtime",
        "config_files",
        "test_files",
        "notable_files",
    ):
        merged[key] = merge_unique(as_list(fallback.get(key)) + as_list(parsed.get(key)))
    return merged


def as_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def parse_json(raw_text: str, fallback: dict) -> dict:
    try:
        result = extract_json_object(raw_text)
        print(f"Successfully parsed LLM JSON with keys: {list(result.keys())}")
        return result
    except Exception as e:
        print(f"Failed to parse LLM response: {type(e).__name__}: {e}")
        print(f"Raw LLM text was: {raw_text[:500]}")
        return fallback


if __name__ == "__main__":
    sample_state = {
        "file_contents": {
            "README.md": "# Demo app",
            "app.py": "import streamlit as st\nst.title('Demo')",
        }
    }
    print(run_mapper(sample_state)["mapper_output"])
