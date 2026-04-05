"""
Tests for directory expansion in verification API (ADR-034 v2.6).

These tests verify the directory expansion functionality that allows
the verification API to handle directory paths by expanding them to
constituent text files.

Issues: #307, #308, #309, #310, #311, #312, #313
"""

import asyncio
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

# =============================================================================
# Issue #307: _get_git_object_type() Tests
# =============================================================================


class TestGetGitObjectType:
    """Tests for _get_git_object_type() helper (Issue #307)."""

    @pytest.mark.asyncio
    async def test_returns_blob_for_file(self):
        """Should return 'blob' for a regular file."""
        from llm_council.verification.api import _get_git_object_type

        # Use a known file in this repo
        result = await _get_git_object_type("HEAD", "pyproject.toml")
        assert result == "blob"

    @pytest.mark.asyncio
    async def test_returns_tree_for_directory(self):
        """Should return 'tree' for a directory."""
        from llm_council.verification.api import _get_git_object_type

        result = await _get_git_object_type("HEAD", "docs")
        assert result == "tree"

    @pytest.mark.asyncio
    async def test_returns_none_for_nonexistent_path(self):
        """Should return None for a path that doesn't exist."""
        from llm_council.verification.api import _get_git_object_type

        result = await _get_git_object_type("HEAD", "nonexistent/path/file.txt")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_for_invalid_commit(self):
        """Should return None for an invalid commit SHA."""
        from llm_council.verification.api import _get_git_object_type

        result = await _get_git_object_type("0000000", "pyproject.toml")
        assert result is None

    @pytest.mark.asyncio
    async def test_handles_path_with_spaces(self):
        """Should handle paths with spaces correctly."""
        from llm_council.verification.api import _get_git_object_type

        # Create a mock for a path with spaces
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.communicate.return_value = (b"blob\n", b"")
            mock_proc.returncode = 0
            mock_exec.return_value = mock_proc

            result = await _get_git_object_type("HEAD", "path with spaces/file.txt")
            assert result == "blob"

    @pytest.mark.asyncio
    async def test_respects_semaphore(self):
        """Should acquire semaphore before git operation."""
        from llm_council.verification.api import _get_git_object_type, _get_git_semaphore

        semaphore = await _get_git_semaphore()
        initial_value = semaphore._value

        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.communicate.return_value = (b"blob\n", b"")
            mock_proc.returncode = 0
            mock_exec.return_value = mock_proc

            await _get_git_object_type("HEAD", "file.txt")

            # Semaphore should be released after operation
            assert semaphore._value == initial_value


# =============================================================================
# Issue #308: _git_ls_tree_z_name_only() Tests
# =============================================================================


class TestGitLsTreeZNameOnly:
    """Tests for _git_ls_tree_z_name_only() helper (Issue #308)."""

    @pytest.mark.asyncio
    async def test_lists_files_in_directory(self):
        """Should list files in a directory recursively."""
        from llm_council.verification.api import _git_ls_tree_z_name_only

        result = await _git_ls_tree_z_name_only("HEAD", "src/llm_council/verification")
        assert isinstance(result, list)
        assert len(result) > 0
        # Should contain Python files
        assert any(f.endswith(".py") for f in result)

    @pytest.mark.asyncio
    async def test_returns_empty_for_nonexistent_directory(self):
        """Should return empty list for nonexistent directory."""
        from llm_council.verification.api import _git_ls_tree_z_name_only

        result = await _git_ls_tree_z_name_only("HEAD", "nonexistent/dir")
        assert result == []

    @pytest.mark.asyncio
    async def test_handles_filenames_with_spaces(self):
        """Should handle filenames with spaces using NUL delimiter."""
        from llm_council.verification.api import _git_ls_tree_z_name_only

        with patch("asyncio.create_subprocess_exec") as mock_exec:
            # Simulate git ls-tree -rz output format: "mode type hash\tpath\0..."
            mock_proc = AsyncMock()
            mock_proc.communicate.return_value = (
                b"100644 blob abc123\tfile with spaces.txt\x00"
                b"100644 blob def456\tnormal_file.py\x00"
                b"100644 blob ghi789\tanother file.md\x00",
                b"",
            )
            mock_proc.returncode = 0
            mock_exec.return_value = mock_proc

            result = await _git_ls_tree_z_name_only("HEAD", "docs")

            assert "docs/file with spaces.txt" in result
            assert "docs/normal_file.py" in result
            assert "docs/another file.md" in result

    @pytest.mark.asyncio
    async def test_handles_filenames_with_newlines(self):
        """Should handle filenames with embedded newlines using NUL delimiter."""
        from llm_council.verification.api import _git_ls_tree_z_name_only

        with patch("asyncio.create_subprocess_exec") as mock_exec:
            # Simulate git ls-tree -rz output with newlines in filename
            mock_proc = AsyncMock()
            mock_proc.communicate.return_value = (
                b"100644 blob abc123\tfile\nwith\nnewlines.txt\x00"
                b"100644 blob def456\tnormal.py\x00",
                b"",
            )
            mock_proc.returncode = 0
            mock_exec.return_value = mock_proc

            result = await _git_ls_tree_z_name_only("HEAD", "test")

            assert "test/file\nwith\nnewlines.txt" in result
            assert "test/normal.py" in result

    @pytest.mark.asyncio
    async def test_skips_symlinks(self):
        """Should skip symlinks (mode 120000)."""
        from llm_council.verification.api import _git_ls_tree_z_name_only

        with patch("asyncio.create_subprocess_exec") as mock_exec:
            # Simulate git ls-tree output with symlinks (mode 120000)
            mock_proc = AsyncMock()
            mock_proc.communicate.return_value = (
                b"100644 blob abc123\tregular_file.py\x00"
                b"120000 blob def456\tsymlink_to_file\x00",  # Symlink
                b"",
            )
            mock_proc.returncode = 0
            mock_exec.return_value = mock_proc

            result = await _git_ls_tree_z_name_only("HEAD", "dir")

            # Should only contain regular file, not symlink
            assert "dir/regular_file.py" in result
            assert "dir/symlink_to_file" not in result

    @pytest.mark.asyncio
    async def test_skips_submodules(self):
        """Should skip submodules (mode 160000)."""
        from llm_council.verification.api import _git_ls_tree_z_name_only

        with patch("asyncio.create_subprocess_exec") as mock_exec:
            # Simulate git ls-tree output with submodules (mode 160000)
            mock_proc = AsyncMock()
            mock_proc.communicate.return_value = (
                b"100644 blob abc123\tregular_file.py\x00"
                b"160000 commit def456\tvendor/submodule\x00",  # Submodule
                b"",
            )
            mock_proc.returncode = 0
            mock_exec.return_value = mock_proc

            result = await _git_ls_tree_z_name_only("HEAD", "dir")

            # Should only contain regular file, not submodule
            assert "dir/regular_file.py" in result
            assert "dir/vendor/submodule" not in result

    @pytest.mark.asyncio
    async def test_prepends_tree_path(self):
        """Should prepend tree path to all returned filenames."""
        from llm_council.verification.api import _git_ls_tree_z_name_only

        with patch("asyncio.create_subprocess_exec") as mock_exec:
            # Simulate git ls-tree output
            mock_proc = AsyncMock()
            mock_proc.communicate.return_value = (
                b"100644 blob abc123\tfile1.py\x00100644 blob def456\tfile2.py\x00",
                b"",
            )
            mock_proc.returncode = 0
            mock_exec.return_value = mock_proc

            result = await _git_ls_tree_z_name_only("HEAD", "src/module")

            assert "src/module/file1.py" in result
            assert "src/module/file2.py" in result


# =============================================================================
# Issue #309: _expand_target_paths() Tests
# =============================================================================


class TestExpandTargetPaths:
    """Tests for _expand_target_paths() with text filtering (Issue #309)."""

    @pytest.mark.asyncio
    async def test_passes_through_single_file(self):
        """Single file path should pass through unchanged."""
        from llm_council.verification.api import _expand_target_paths

        files, truncated, warnings = await _expand_target_paths("HEAD", ["pyproject.toml"])
        assert "pyproject.toml" in files
        assert truncated is False

    @pytest.mark.asyncio
    async def test_expands_single_directory(self):
        """Single directory should expand to constituent files."""
        from llm_council.verification.api import _expand_target_paths

        files, truncated, warnings = await _expand_target_paths(
            "HEAD", ["src/llm_council/verification"]
        )
        assert len(files) > 0
        # All files should be under the directory
        assert all(f.startswith("src/llm_council/verification/") for f in files)
        # Should contain Python files
        assert any(f.endswith(".py") for f in files)

    @pytest.mark.asyncio
    async def test_expands_mixed_paths(self):
        """Mixed file and directory paths should be handled correctly."""
        from llm_council.verification.api import _expand_target_paths

        files, truncated, warnings = await _expand_target_paths(
            "HEAD", ["pyproject.toml", "src/llm_council/verification"]
        )
        assert "pyproject.toml" in files
        # Should also have expanded directory files
        assert any(f.startswith("src/llm_council/verification/") for f in files)

    @pytest.mark.asyncio
    async def test_filters_binary_extensions(self):
        """Should filter out files with binary extensions."""
        from llm_council.verification.api import _expand_target_paths, TEXT_EXTENSIONS

        with patch("llm_council.verification.api._git_ls_tree_z_name_only") as mock_ls:
            mock_ls.return_value = [
                "docs/file.md",
                "docs/image.png",
                "docs/doc.pdf",
                "docs/script.py",
            ]

            with patch("llm_council.verification.api._get_git_object_type") as mock_type:
                mock_type.return_value = "tree"

                files, _, _ = await _expand_target_paths("HEAD", ["docs"])

                # Should include text files
                assert "docs/file.md" in files
                assert "docs/script.py" in files
                # Should exclude binary files
                assert "docs/image.png" not in files
                assert "docs/doc.pdf" not in files

    @pytest.mark.asyncio
    async def test_excludes_garbage_files(self):
        """Should exclude garbage files like package-lock.json."""
        from llm_council.verification.api import _expand_target_paths, GARBAGE_FILENAMES

        with patch("llm_council.verification.api._git_ls_tree_z_name_only") as mock_ls:
            mock_ls.return_value = [
                "src/index.js",
                "src/package-lock.json",
                "src/yarn.lock",
                "src/app.ts",
            ]

            with patch("llm_council.verification.api._get_git_object_type") as mock_type:
                mock_type.return_value = "tree"

                files, _, _ = await _expand_target_paths("HEAD", ["src"])

                # Should include normal files
                assert "src/index.js" in files
                assert "src/app.ts" in files
                # Should exclude garbage files
                assert "src/package-lock.json" not in files
                assert "src/yarn.lock" not in files

    @pytest.mark.asyncio
    async def test_truncates_at_max_files(self):
        """Should truncate at MAX_FILES_EXPANSION and set flag."""
        from llm_council.verification.api import (
            _expand_target_paths,
            MAX_FILES_EXPANSION,
        )

        # Generate more files than the limit
        many_files = [f"src/file_{i}.py" for i in range(MAX_FILES_EXPANSION + 50)]

        with patch("llm_council.verification.api._git_ls_tree_z_name_only") as mock_ls:
            mock_ls.return_value = many_files

            with patch("llm_council.verification.api._get_git_object_type") as mock_type:
                mock_type.return_value = "tree"

                files, truncated, warnings = await _expand_target_paths("HEAD", ["src"])

                assert len(files) == MAX_FILES_EXPANSION
                assert truncated is True
                assert any("truncated" in w.lower() for w in warnings)

    @pytest.mark.asyncio
    async def test_warns_on_nonexistent_path(self):
        """Should add warning for nonexistent paths."""
        from llm_council.verification.api import _expand_target_paths

        files, truncated, warnings = await _expand_target_paths(
            "HEAD", ["nonexistent/path/file.txt"]
        )

        assert "nonexistent/path/file.txt" not in files
        assert any("nonexistent" in w.lower() for w in warnings)

    @pytest.mark.asyncio
    async def test_handles_empty_directory(self):
        """Should handle empty directories gracefully."""
        from llm_council.verification.api import _expand_target_paths

        with patch("llm_council.verification.api._git_ls_tree_z_name_only") as mock_ls:
            mock_ls.return_value = []

            with patch("llm_council.verification.api._get_git_object_type") as mock_type:
                mock_type.return_value = "tree"

                files, truncated, warnings = await _expand_target_paths("HEAD", ["empty_dir"])

                assert files == []
                assert truncated is False


# =============================================================================
# Issue #310: Integration with _fetch_files_for_verification_async() Tests
# =============================================================================


class TestFetchFilesIntegration:
    """Tests for directory expansion in _fetch_files_for_verification_async()."""

    @pytest.mark.asyncio
    async def test_directory_path_fetches_file_contents(self):
        """Directory path should result in file contents, not tree listing."""
        from llm_council.verification.api import _fetch_files_for_verification_async

        # Test with actual directory in this repo
        result = await _fetch_files_for_verification_async("HEAD", ["src/llm_council/verification"])

        # Should contain actual code, not tree listing
        assert "```" in result  # Code blocks present
        # Should NOT contain tree listing patterns
        assert "040000 tree" not in result
        assert "100644 blob" not in result

    @pytest.mark.asyncio
    async def test_returns_expansion_metadata(self):
        """Should return expansion metadata along with contents."""
        from llm_council.verification.api import (
            _fetch_files_for_verification_async_with_metadata,
        )

        result, metadata = await _fetch_files_for_verification_async_with_metadata(
            "HEAD", ["src/llm_council/verification"]
        )

        assert "expanded_paths" in metadata
        assert isinstance(metadata["expanded_paths"], list)
        assert "paths_truncated" in metadata
        assert "expansion_warnings" in metadata


# =============================================================================
# Issue #311: VerifyResponse Schema Tests
# =============================================================================


class TestVerifyResponseSchema:
    """Tests for expanded_paths in VerifyResponse schema (Issue #311)."""

    def test_schema_includes_expanded_paths(self):
        """VerifyResponse should include expanded_paths field."""
        from llm_council.verification.api import VerifyResponse

        # Check field exists in model
        fields = VerifyResponse.model_fields
        assert "expanded_paths" in fields

    def test_schema_includes_paths_truncated(self):
        """VerifyResponse should include paths_truncated field."""
        from llm_council.verification.api import VerifyResponse

        fields = VerifyResponse.model_fields
        assert "paths_truncated" in fields

    def test_schema_includes_expansion_warnings(self):
        """VerifyResponse should include expansion_warnings field."""
        from llm_council.verification.api import VerifyResponse

        fields = VerifyResponse.model_fields
        assert "expansion_warnings" in fields

    def test_expanded_fields_are_optional(self):
        """New fields should be optional for backward compatibility."""
        from llm_council.verification.api import VerifyResponse, RubricScoresResponse

        # Should be able to create response without new fields
        response = VerifyResponse(
            verification_id="test-123",
            verdict="pass",
            confidence=0.85,
            exit_code=0,
            rubric_scores=RubricScoresResponse(),
            blocking_issues=[],
            rationale="Test rationale",
            transcript_location="/tmp/test",
        )
        assert response.expanded_paths is None
        assert response.paths_truncated is None
        assert response.expansion_warnings is None


# =============================================================================
# Constants Tests
# =============================================================================


# =============================================================================
# Issue #313: Integration Test with docs/ Directory
# =============================================================================


class TestDocsDirectoryIntegration:
    """Integration tests verifying docs/ directory expansion (Issue #313)."""

    @pytest.mark.asyncio
    async def test_docs_directory_expands_to_markdown_files(self):
        """Verify docs/ expands to markdown files, not tree listing."""
        from llm_council.verification.api import (
            _expand_target_paths,
            _fetch_files_for_verification_async,
        )

        # Expand docs/ directory
        files, truncated, warnings = await _expand_target_paths("HEAD", ["docs"])

        # Should have found files
        assert len(files) > 0

        # Should contain markdown files
        md_files = [f for f in files if f.endswith(".md")]
        assert len(md_files) > 0

        # Should be actual file paths, not tree listing entries
        for f in files:
            assert "\t" not in f  # No git tree format tabs
            assert " blob " not in f  # No git object info

    @pytest.mark.asyncio
    async def test_docs_directory_fetches_actual_content(self):
        """Verify docs/ returns file contents, not git tree listing."""
        from llm_council.verification.api import _fetch_files_for_verification_async

        # Fetch docs/ content
        content = await _fetch_files_for_verification_async("HEAD", ["docs"])

        # Should contain markdown content (code blocks with actual text)
        assert "```" in content

        # Should NOT contain tree listing patterns
        assert "040000 tree" not in content
        assert "100644 blob" not in content

        # Should contain recognizable documentation content
        # (at least one of these should be in the docs)
        assert any(
            keyword in content.lower()
            for keyword in ["api", "guide", "install", "getting started", "adr", "architecture"]
        )

    @pytest.mark.asyncio
    async def test_docs_expansion_respects_text_filter(self):
        """Verify docs/ expansion only includes text files."""
        from llm_council.verification.api import _expand_target_paths, TEXT_EXTENSIONS

        files, _, _ = await _expand_target_paths("HEAD", ["docs"])

        for f in files:
            # All files should have text extensions
            suffix = Path(f).suffix.lower()
            name = Path(f).name.lower()
            assert (
                suffix in TEXT_EXTENSIONS
                or name in TEXT_EXTENSIONS
                or f".{name}" in TEXT_EXTENSIONS
            ), f"Non-text file included: {f}"

    @pytest.mark.asyncio
    async def test_src_directory_expands_to_python_files(self):
        """Verify src/ expands to Python files."""
        from llm_council.verification.api import _expand_target_paths

        files, _, _ = await _expand_target_paths("HEAD", ["src/llm_council/verification"])

        # Should have Python files
        py_files = [f for f in files if f.endswith(".py")]
        assert len(py_files) > 0

        # Should include api.py
        assert any("api.py" in f for f in py_files)


# =============================================================================
# Constants Tests
# =============================================================================


class TestConstants:
    """Tests for module constants."""

    def test_text_extensions_defined(self):
        """TEXT_EXTENSIONS should be defined and non-empty."""
        from llm_council.verification.api import TEXT_EXTENSIONS

        assert isinstance(TEXT_EXTENSIONS, (set, frozenset))
        assert len(TEXT_EXTENSIONS) > 50  # Should have 80+ extensions
        assert ".py" in TEXT_EXTENSIONS
        assert ".md" in TEXT_EXTENSIONS
        assert ".js" in TEXT_EXTENSIONS

    def test_garbage_filenames_defined(self):
        """GARBAGE_FILENAMES should be defined with common lock files."""
        from llm_council.verification.api import GARBAGE_FILENAMES

        assert isinstance(GARBAGE_FILENAMES, (set, frozenset))
        assert "package-lock.json" in GARBAGE_FILENAMES
        assert "yarn.lock" in GARBAGE_FILENAMES
        assert "poetry.lock" in GARBAGE_FILENAMES

    def test_max_files_expansion_defined(self):
        """MAX_FILES_EXPANSION should be 100."""
        from llm_council.verification.api import MAX_FILES_EXPANSION

        assert MAX_FILES_EXPANSION == 100
