"""TDD Tests for One-Click Deployment (ADR-038).

These tests verify:
1. API token authentication for incoming requests
2. Deployment configuration files exist and are valid
3. Docker and Docker Compose configurations are correct
4. Deployment documentation exists

Following TDD methodology: tests are written first (RED), then implementation (GREEN).
"""

import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import yaml

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
DOCS_ROOT = PROJECT_ROOT / "docs"
DEPLOY_DIR = PROJECT_ROOT / "deploy"
RAILWAY_DIR = DEPLOY_DIR / "railway"


# Skip HTTP tests if deps not installed
fastapi = pytest.importorskip(
    "fastapi",
    reason="HTTP dependencies not installed. Install with: pip install 'llm-council[http]'",
)
from fastapi.testclient import TestClient


class TestAPIAuthentication:
    """Tests for API token authentication (ADR-038 Security Requirement)."""

    def test_health_endpoint_bypasses_auth(self):
        """GET /health should always be accessible without auth."""
        from llm_council.http_server import app

        # Even with token configured, health should work without auth
        with patch.dict(os.environ, {"LLM_COUNCIL_API_TOKEN": "secret-token"}):
            client = TestClient(app)
            response = client.get("/health")

            assert response.status_code == 200
            assert response.json()["status"] == "ok"

    def test_requires_api_token_when_configured(self):
        """Requests without token should return 401 when LLM_COUNCIL_API_TOKEN is set."""
        from llm_council.http_server import app

        with patch.dict(
            os.environ,
            {"LLM_COUNCIL_API_TOKEN": "secret-token", "OPENROUTER_API_KEY": "sk-test"},
        ):
            client = TestClient(app)
            response = client.post("/v1/council/run", json={"prompt": "test question"})

            assert response.status_code == 401
            assert "Invalid or missing API token" in response.json()["detail"]

    def test_accepts_valid_bearer_token(self):
        """Requests with valid Bearer token should succeed."""
        from llm_council.http_server import app

        mock_result = (
            [{"model": "test", "response": "response1"}],
            [{"model": "test", "ranking": "1. A", "parsed_ranking": {"ranking": ["A"]}}],
            {"final_answer": "synthesized answer"},
            {"aggregate_rankings": []},
        )

        with patch.dict(
            os.environ,
            {"LLM_COUNCIL_API_TOKEN": "secret-token", "OPENROUTER_API_KEY": "sk-test"},
        ):
            with patch("llm_council.http_server.run_full_council", new_callable=AsyncMock) as mock:
                mock.return_value = mock_result
                client = TestClient(app)
                response = client.post(
                    "/v1/council/run",
                    json={"prompt": "test question"},
                    headers={"Authorization": "Bearer secret-token"},
                )

                assert response.status_code == 200

    def test_rejects_invalid_bearer_token(self):
        """Requests with invalid Bearer token should return 401."""
        from llm_council.http_server import app

        with patch.dict(
            os.environ,
            {"LLM_COUNCIL_API_TOKEN": "secret-token", "OPENROUTER_API_KEY": "sk-test"},
        ):
            client = TestClient(app)
            response = client.post(
                "/v1/council/run",
                json={"prompt": "test question"},
                headers={"Authorization": "Bearer wrong-token"},
            )

            assert response.status_code == 401

    def test_no_auth_required_when_token_not_configured(self):
        """Without LLM_COUNCIL_API_TOKEN, auth should be optional (backwards compatible)."""
        from llm_council.http_server import app

        mock_result = (
            [{"model": "test", "response": "response1"}],
            [{"model": "test", "ranking": "1. A", "parsed_ranking": {"ranking": ["A"]}}],
            {"final_answer": "synthesized answer"},
            {"aggregate_rankings": []},
        )

        # Ensure API token is NOT set
        env = {"OPENROUTER_API_KEY": "sk-test"}
        if "LLM_COUNCIL_API_TOKEN" in os.environ:
            env["LLM_COUNCIL_API_TOKEN"] = ""

        with patch.dict(os.environ, env, clear=False):
            # Temporarily remove LLM_COUNCIL_API_TOKEN if it exists
            original = os.environ.pop("LLM_COUNCIL_API_TOKEN", None)
            try:
                with patch(
                    "llm_council.http_server.run_full_council", new_callable=AsyncMock
                ) as mock:
                    mock.return_value = mock_result
                    client = TestClient(app)
                    response = client.post(
                        "/v1/council/run",
                        json={"prompt": "test question"},
                    )

                    assert response.status_code == 200
            finally:
                if original is not None:
                    os.environ["LLM_COUNCIL_API_TOKEN"] = original

    def test_stream_endpoint_requires_auth_when_configured(self):
        """GET /v1/council/stream should require auth when token configured."""
        from llm_council.http_server import app

        with patch.dict(
            os.environ,
            {"LLM_COUNCIL_API_TOKEN": "secret-token", "OPENROUTER_API_KEY": "sk-test"},
        ):
            client = TestClient(app)
            response = client.get("/v1/council/stream?prompt=test")

            assert response.status_code == 401


class TestRailwayTemplate:
    """Tests for Railway deployment template (Phase 2)."""

    def test_railway_directory_exists(self):
        """deploy/railway/ directory should exist."""
        assert RAILWAY_DIR.exists(), f"Expected directory: {RAILWAY_DIR}"
        assert RAILWAY_DIR.is_dir()

    def test_railway_json_exists(self):
        """railway.json should exist at project root (required by Railway)."""
        railway_json = PROJECT_ROOT / "railway.json"
        assert railway_json.exists(), f"Expected file: {railway_json}"

    def test_railway_json_valid(self):
        """railway.json should be valid JSON."""
        railway_json = PROJECT_ROOT / "railway.json"
        if not railway_json.exists():
            pytest.skip("railway.json not yet created")

        content = railway_json.read_text()
        try:
            data = json.loads(content)
            assert isinstance(data, dict), "railway.json should be a JSON object"
        except json.JSONDecodeError as e:
            pytest.fail(f"Invalid JSON in railway.json: {e}")

    def test_railway_json_has_required_fields(self):
        """railway.json should have build and deploy sections."""
        railway_json = PROJECT_ROOT / "railway.json"
        if not railway_json.exists():
            pytest.skip("railway.json not yet created")

        data = json.loads(railway_json.read_text())

        assert "build" in data, "railway.json missing 'build' section"
        assert "deploy" in data, "railway.json missing 'deploy' section"

        # Verify build section
        assert "builder" in data["build"], "build section missing 'builder'"

        # Verify deploy section
        assert "healthcheckPath" in data["deploy"], "deploy section missing 'healthcheckPath'"
        assert data["deploy"]["healthcheckPath"] == "/health"

    def test_dockerfile_exists(self):
        """deploy/railway/Dockerfile should exist."""
        dockerfile = RAILWAY_DIR / "Dockerfile"
        assert dockerfile.exists(), f"Expected file: {dockerfile}"

    def test_dockerfile_has_required_content(self):
        """Dockerfile should have required directives."""
        dockerfile = RAILWAY_DIR / "Dockerfile"
        if not dockerfile.exists():
            pytest.skip("Dockerfile not yet created")

        content = dockerfile.read_text()

        # Must use Python base image
        assert "FROM python:" in content, "Dockerfile should use Python base image"

        # Must install http dependencies
        assert "[http]" in content, "Dockerfile should install [http] dependencies"

        # Must expose PORT
        assert "EXPOSE" in content, "Dockerfile should expose port"

        # Must run as non-root user for security
        assert "USER" in content, "Dockerfile should run as non-root user"

        # Must have HEALTHCHECK
        assert (
            "HEALTHCHECK" in content or "healthcheck" in content.lower()
        ), "Dockerfile should include healthcheck"


class TestRenderBlueprint:
    """Tests for Render deployment blueprint (Phase 3)."""

    def test_render_yaml_exists(self):
        """render.yaml should exist in repository root."""
        render_yaml = PROJECT_ROOT / "render.yaml"
        assert render_yaml.exists(), f"Expected file: {render_yaml}"

    def test_render_yaml_valid(self):
        """render.yaml should be valid YAML."""
        render_yaml = PROJECT_ROOT / "render.yaml"
        if not render_yaml.exists():
            pytest.skip("render.yaml not yet created")

        content = render_yaml.read_text()
        try:
            data = yaml.safe_load(content)
            assert isinstance(data, dict), "render.yaml should be a YAML object"
        except yaml.YAMLError as e:
            pytest.fail(f"Invalid YAML in render.yaml: {e}")

    def test_render_yaml_has_services(self):
        """render.yaml should define services."""
        render_yaml = PROJECT_ROOT / "render.yaml"
        if not render_yaml.exists():
            pytest.skip("render.yaml not yet created")

        data = yaml.safe_load(render_yaml.read_text())

        assert "services" in data, "render.yaml missing 'services'"
        assert isinstance(data["services"], list), "'services' should be a list"
        assert len(data["services"]) > 0, "render.yaml should have at least one service"

    def test_render_yaml_has_autodeploy_false(self):
        """render.yaml should set autoDeploy: false to prevent cascading deploys."""
        render_yaml = PROJECT_ROOT / "render.yaml"
        if not render_yaml.exists():
            pytest.skip("render.yaml not yet created")

        data = yaml.safe_load(render_yaml.read_text())
        services = data.get("services", [])

        for service in services:
            if service.get("type") == "web":
                assert (
                    service.get("autoDeploy") is False
                ), "Web service should have autoDeploy: false"

    def test_render_yaml_has_health_check(self):
        """render.yaml should define health check."""
        render_yaml = PROJECT_ROOT / "render.yaml"
        if not render_yaml.exists():
            pytest.skip("render.yaml not yet created")

        data = yaml.safe_load(render_yaml.read_text())
        services = data.get("services", [])

        for service in services:
            if service.get("type") == "web":
                assert "healthCheckPath" in service, "Web service should have healthCheckPath"
                assert service["healthCheckPath"] == "/health"


class TestDockerCompose:
    """Tests for Docker Compose local deployment (Phase 4)."""

    def test_docker_compose_exists(self):
        """docker-compose.yml should exist in repository root."""
        compose_file = PROJECT_ROOT / "docker-compose.yml"
        assert compose_file.exists(), f"Expected file: {compose_file}"

    def test_docker_compose_valid(self):
        """docker-compose.yml should be valid YAML."""
        compose_file = PROJECT_ROOT / "docker-compose.yml"
        if not compose_file.exists():
            pytest.skip("docker-compose.yml not yet created")

        content = compose_file.read_text()
        try:
            data = yaml.safe_load(content)
            assert isinstance(data, dict), "docker-compose.yml should be a YAML object"
        except yaml.YAMLError as e:
            pytest.fail(f"Invalid YAML in docker-compose.yml: {e}")

    def test_docker_compose_has_services(self):
        """docker-compose.yml should define services."""
        compose_file = PROJECT_ROOT / "docker-compose.yml"
        if not compose_file.exists():
            pytest.skip("docker-compose.yml not yet created")

        data = yaml.safe_load(compose_file.read_text())

        assert "services" in data, "docker-compose.yml missing 'services'"
        assert (
            "llm-council" in data["services"]
        ), "docker-compose.yml should have 'llm-council' service"

    def test_docker_compose_has_healthcheck(self):
        """docker-compose.yml llm-council service should have healthcheck."""
        compose_file = PROJECT_ROOT / "docker-compose.yml"
        if not compose_file.exists():
            pytest.skip("docker-compose.yml not yet created")

        data = yaml.safe_load(compose_file.read_text())
        service = data.get("services", {}).get("llm-council", {})

        assert "healthcheck" in service, "llm-council service should have healthcheck"

    def test_docker_compose_exposes_port(self):
        """docker-compose.yml should expose port 8000."""
        compose_file = PROJECT_ROOT / "docker-compose.yml"
        if not compose_file.exists():
            pytest.skip("docker-compose.yml not yet created")

        data = yaml.safe_load(compose_file.read_text())
        service = data.get("services", {}).get("llm-council", {})

        assert "ports" in service, "llm-council service should expose ports"
        ports = service["ports"]
        # Check that 8000 is mapped
        port_str = str(ports) if isinstance(ports, list) else ports
        assert "8000" in port_str, "llm-council should expose port 8000"


class TestDeploymentDocs:
    """Tests for deployment documentation (Phase 5)."""

    def test_deployment_directory_exists(self):
        """docs/deployment/ directory should exist."""
        deployment_dir = DOCS_ROOT / "deployment"
        assert deployment_dir.exists(), f"Expected directory: {deployment_dir}"
        assert deployment_dir.is_dir()

    def test_deployment_index_exists(self):
        """docs/deployment/index.md should exist."""
        index_file = DOCS_ROOT / "deployment" / "index.md"
        assert index_file.exists(), f"Expected file: {index_file}"

    def test_railway_guide_exists(self):
        """docs/deployment/railway.md should exist."""
        railway_doc = DOCS_ROOT / "deployment" / "railway.md"
        assert railway_doc.exists(), f"Expected file: {railway_doc}"

    def test_render_guide_exists(self):
        """docs/deployment/render.md should exist."""
        render_doc = DOCS_ROOT / "deployment" / "render.md"
        assert render_doc.exists(), f"Expected file: {render_doc}"

    def test_local_guide_exists(self):
        """docs/deployment/local.md should exist."""
        local_doc = DOCS_ROOT / "deployment" / "local.md"
        assert local_doc.exists(), f"Expected file: {local_doc}"


class TestReadmeDeployButtons:
    """Tests for README deploy buttons (Phase 6)."""

    def test_readme_has_deploy_section(self):
        """README.md should have a deployment section."""
        readme = PROJECT_ROOT / "README.md"
        assert readme.exists(), "README.md should exist"

        content = readme.read_text().lower()
        assert "deploy" in content, "README.md should mention deployment"

    def test_readme_has_railway_button(self):
        """README.md should have Railway deploy button."""
        readme = PROJECT_ROOT / "README.md"
        if not readme.exists():
            pytest.skip("README.md not found")

        content = readme.read_text()

        # Check for Railway button SVG or link
        assert (
            "railway.com" in content.lower() or "railway.app" in content.lower()
        ), "README.md should include Railway deploy button"

    def test_readme_has_render_button(self):
        """README.md should have Render deploy button."""
        readme = PROJECT_ROOT / "README.md"
        if not readme.exists():
            pytest.skip("README.md not found")

        content = readme.read_text()

        # Check for Render button SVG or link
        assert "render.com" in content.lower(), "README.md should include Render deploy button"


class TestCIWorkflow:
    """Tests for CI validation workflow (Phase 7)."""

    def test_validate_templates_workflow_exists(self):
        """validate-templates.yml workflow should exist."""
        workflow_file = PROJECT_ROOT / ".github" / "workflows" / "validate-templates.yml"
        assert workflow_file.exists(), f"Expected file: {workflow_file}"

    def test_workflow_validates_railway_json(self):
        """Workflow should validate railway.json."""
        workflow_file = PROJECT_ROOT / ".github" / "workflows" / "validate-templates.yml"
        if not workflow_file.exists():
            pytest.skip("validate-templates.yml not yet created")

        content = workflow_file.read_text()
        assert "railway.json" in content, "Workflow should validate railway.json"

    def test_workflow_validates_render_yaml(self):
        """Workflow should validate render.yaml."""
        workflow_file = PROJECT_ROOT / ".github" / "workflows" / "validate-templates.yml"
        if not workflow_file.exists():
            pytest.skip("validate-templates.yml not yet created")

        content = workflow_file.read_text()
        assert "render.yaml" in content, "Workflow should validate render.yaml"

    def test_workflow_builds_docker(self):
        """Workflow should build Docker image."""
        workflow_file = PROJECT_ROOT / ".github" / "workflows" / "validate-templates.yml"
        if not workflow_file.exists():
            pytest.skip("validate-templates.yml not yet created")

        content = workflow_file.read_text()
        assert "docker build" in content.lower(), "Workflow should build Docker image"


class TestBlogPost:
    """Tests for blog post (Phase 8)."""

    def test_blog_post_exists(self):
        """docs/blog/09-one-click-deployment.md should exist."""
        blog_post = DOCS_ROOT / "blog" / "09-one-click-deployment.md"
        assert blog_post.exists(), f"Expected file: {blog_post}"

    def test_blog_post_has_required_content(self):
        """Blog post should cover key topics."""
        blog_post = DOCS_ROOT / "blog" / "09-one-click-deployment.md"
        if not blog_post.exists():
            pytest.skip("Blog post not yet created")

        content = blog_post.read_text().lower()

        required_terms = [
            "railway",
            "render",
            "docker",
            "deploy",
        ]

        for term in required_terms:
            assert term in content, f"Blog post should mention '{term}'"

    def test_blog_post_has_repo_link(self):
        """Blog post should include repo link."""
        blog_post = DOCS_ROOT / "blog" / "09-one-click-deployment.md"
        if not blog_post.exists():
            pytest.skip("Blog post not yet created")

        content = blog_post.read_text()
        assert "github.com/amiable-dev/llm-council" in content, "Blog post should include repo link"


class TestMkdocsNavigation:
    """Tests for mkdocs.yml navigation updates."""

    def test_mkdocs_has_deployment_section(self):
        """mkdocs.yml should have Deployment section in nav."""
        mkdocs_file = PROJECT_ROOT / "mkdocs.yml"
        assert mkdocs_file.exists(), "mkdocs.yml should exist"

        data = yaml.safe_load(mkdocs_file.read_text())
        nav = data.get("nav", [])

        # Look for Deployment in nav
        nav_names = []
        for item in nav:
            if isinstance(item, dict):
                nav_names.extend(item.keys())
            elif isinstance(item, str):
                nav_names.append(item)

        assert "Deployment" in nav_names, "mkdocs.yml should have Deployment section in nav"

    def test_mkdocs_has_blog_entry(self):
        """mkdocs.yml should have one-click deployment blog entry."""
        mkdocs_file = PROJECT_ROOT / "mkdocs.yml"
        assert mkdocs_file.exists(), "mkdocs.yml should exist"

        content = mkdocs_file.read_text()
        assert (
            "09-one-click-deployment" in content
        ), "mkdocs.yml should reference one-click deployment blog post"
