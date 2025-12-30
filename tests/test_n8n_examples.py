"""
TDD Tests for n8n Integration Examples (Issue #78)

These tests verify:
1. Workflow JSON files exist and are valid
2. Integration documentation exists with required sections
3. Workflow JSONs have required n8n node structure
"""

import json
from pathlib import Path

import pytest

# Paths
DOCS_ROOT = Path(__file__).parent.parent / "docs"
EXAMPLES_DIR = DOCS_ROOT / "examples" / "n8n"
INTEGRATIONS_DIR = DOCS_ROOT / "integrations"

# Expected workflow files
EXPECTED_WORKFLOWS = [
    "code-review-workflow.json",
    "support-triage-workflow.json",
    "design-decision-workflow.json",
]


class TestN8nWorkflowExamples:
    """Tests for n8n workflow JSON files."""

    def test_examples_directory_exists(self):
        """docs/examples/n8n/ directory exists."""
        assert EXAMPLES_DIR.exists(), f"Expected directory: {EXAMPLES_DIR}"
        assert EXAMPLES_DIR.is_dir()

    @pytest.mark.parametrize("workflow_file", EXPECTED_WORKFLOWS)
    def test_workflow_json_files_exist(self, workflow_file: str):
        """All expected workflow JSON files exist."""
        filepath = EXAMPLES_DIR / workflow_file
        assert filepath.exists(), f"Expected workflow file: {filepath}"

    @pytest.mark.parametrize("workflow_file", EXPECTED_WORKFLOWS)
    def test_workflow_json_valid(self, workflow_file: str):
        """All workflow JSONs are valid JSON."""
        filepath = EXAMPLES_DIR / workflow_file
        if not filepath.exists():
            pytest.skip(f"Workflow file not yet created: {workflow_file}")

        content = filepath.read_text()
        try:
            data = json.loads(content)
            assert isinstance(data, dict), "Workflow should be a JSON object"
        except json.JSONDecodeError as e:
            pytest.fail(f"Invalid JSON in {workflow_file}: {e}")

    @pytest.mark.parametrize("workflow_file", EXPECTED_WORKFLOWS)
    def test_workflow_has_required_structure(self, workflow_file: str):
        """Each workflow has required n8n structure (nodes, connections)."""
        filepath = EXAMPLES_DIR / workflow_file
        if not filepath.exists():
            pytest.skip(f"Workflow file not yet created: {workflow_file}")

        data = json.loads(filepath.read_text())

        # n8n workflow structure requires 'nodes' array
        assert "nodes" in data, f"Workflow missing 'nodes' key: {workflow_file}"
        assert isinstance(data["nodes"], list), "'nodes' should be a list"
        assert len(data["nodes"]) > 0, "Workflow should have at least one node"

    @pytest.mark.parametrize("workflow_file", EXPECTED_WORKFLOWS)
    def test_workflow_has_http_request_node(self, workflow_file: str):
        """Each workflow has an HTTP Request node to council endpoint."""
        filepath = EXAMPLES_DIR / workflow_file
        if not filepath.exists():
            pytest.skip(f"Workflow file not yet created: {workflow_file}")

        data = json.loads(filepath.read_text())
        nodes = data.get("nodes", [])

        # Look for HTTP Request node
        http_nodes = [
            n
            for n in nodes
            if n.get("type") in ("n8n-nodes-base.httpRequest", "n8n-nodes-base.httpRequestV2")
        ]

        assert (
            len(http_nodes) > 0
        ), f"Workflow should have at least one HTTP Request node: {workflow_file}"

    @pytest.mark.parametrize("workflow_file", EXPECTED_WORKFLOWS)
    def test_workflow_targets_council_endpoint(self, workflow_file: str):
        """Workflow HTTP node targets /v1/council/run or similar endpoint."""
        filepath = EXAMPLES_DIR / workflow_file
        if not filepath.exists():
            pytest.skip(f"Workflow file not yet created: {workflow_file}")

        data = json.loads(filepath.read_text())
        nodes = data.get("nodes", [])

        # Find HTTP Request nodes
        http_nodes = [
            n
            for n in nodes
            if n.get("type") in ("n8n-nodes-base.httpRequest", "n8n-nodes-base.httpRequestV2")
        ]

        # Check at least one targets council endpoint
        council_endpoints = ["/v1/council/run", "/v1/council/stream"]
        found_council = False

        for node in http_nodes:
            params = node.get("parameters", {})
            url = params.get("url", "")
            if any(ep in url for ep in council_endpoints):
                found_council = True
                break

        assert found_council, (
            f"No HTTP node targets council endpoint in {workflow_file}. "
            f"Expected one of: {council_endpoints}"
        )

    @pytest.mark.parametrize("workflow_file", EXPECTED_WORKFLOWS)
    def test_workflow_uses_environment_variables(self, workflow_file: str):
        """Workflows use environment variables for secrets, not hardcoded values."""
        filepath = EXAMPLES_DIR / workflow_file
        if not filepath.exists():
            pytest.skip(f"Workflow file not yet created: {workflow_file}")

        content = filepath.read_text()

        # Check for common API key patterns that shouldn't be hardcoded
        bad_patterns = [
            "sk-or-v1-",  # OpenRouter key prefix
            "sk-ant-",  # Anthropic key prefix
            "sk-proj-",  # OpenAI project key prefix
        ]

        for pattern in bad_patterns:
            assert (
                pattern not in content
            ), f"Workflow contains hardcoded API key pattern '{pattern}': {workflow_file}"


class TestIntegrationDocs:
    """Tests for integration documentation."""

    def test_integrations_directory_exists(self):
        """docs/integrations/ directory exists."""
        assert INTEGRATIONS_DIR.exists(), f"Expected directory: {INTEGRATIONS_DIR}"
        assert INTEGRATIONS_DIR.is_dir()

    def test_integrations_index_exists(self):
        """docs/integrations/index.md exists."""
        index_file = INTEGRATIONS_DIR / "index.md"
        assert index_file.exists(), f"Expected file: {index_file}"

    def test_n8n_doc_exists(self):
        """docs/integrations/n8n.md exists."""
        n8n_doc = INTEGRATIONS_DIR / "n8n.md"
        assert n8n_doc.exists(), f"Expected file: {n8n_doc}"

    def test_n8n_doc_has_required_sections(self):
        """n8n.md has all required sections."""
        n8n_doc = INTEGRATIONS_DIR / "n8n.md"
        if not n8n_doc.exists():
            pytest.skip("n8n.md not yet created")

        content = n8n_doc.read_text().lower()

        required_sections = [
            "overview",
            "prerequisites",
            "quick start",
            "hmac",  # HMAC verification
            "webhook",
        ]

        for section in required_sections:
            assert section in content, f"n8n.md missing required section containing '{section}'"

    def test_n8n_doc_has_code_examples(self):
        """n8n.md contains code examples."""
        n8n_doc = INTEGRATIONS_DIR / "n8n.md"
        if not n8n_doc.exists():
            pytest.skip("n8n.md not yet created")

        content = n8n_doc.read_text()

        # Should have code blocks
        assert "```" in content, "n8n.md should contain code examples"


class TestBlogPost:
    """Tests for n8n integration blog post."""

    def test_blog_post_exists(self):
        """docs/blog/08-n8n-workflow-automation.md exists."""
        blog_post = DOCS_ROOT / "blog" / "08-n8n-workflow-automation.md"
        assert blog_post.exists(), f"Expected file: {blog_post}"

    def test_blog_post_has_required_content(self):
        """Blog post has required structure following existing format."""
        blog_post = DOCS_ROOT / "blog" / "08-n8n-workflow-automation.md"
        if not blog_post.exists():
            pytest.skip("Blog post not yet created")

        content = blog_post.read_text().lower()

        # Should mention key concepts
        required_terms = [
            "n8n",
            "workflow",
            "council",
            "webhook",
        ]

        for term in required_terms:
            assert term in content, f"Blog post should mention '{term}'"

    def test_blog_post_has_code_examples(self):
        """Blog post contains code examples."""
        blog_post = DOCS_ROOT / "blog" / "08-n8n-workflow-automation.md"
        if not blog_post.exists():
            pytest.skip("Blog post not yet created")

        content = blog_post.read_text()
        assert "```" in content, "Blog post should contain code examples"

    def test_blog_post_has_repo_link(self):
        """Blog post ends with repo attribution (following existing format)."""
        blog_post = DOCS_ROOT / "blog" / "08-n8n-workflow-automation.md"
        if not blog_post.exists():
            pytest.skip("Blog post not yet created")

        content = blog_post.read_text()
        assert "github.com/amiable-dev/llm-council" in content, "Blog post should include repo link"
