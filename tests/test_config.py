"""Tests for llm_council_mcp configuration."""
import os
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
import pytest


def test_config_loads_from_env():
    """Test that API key is loaded from environment variable."""
    with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}):
        # Re-import to pick up env var
        import importlib
        import llm_council_mcp.config as config
        importlib.reload(config)
        
        assert config.OPENROUTER_API_KEY == "test-key"


def test_council_models_from_env():
    """Test that council models can be set via environment variable."""
    test_models = "model1,model2,model3"
    with patch.dict(os.environ, {"LLM_COUNCIL_MODELS": test_models}):
        import importlib
        import llm_council_mcp.config as config
        importlib.reload(config)
        
        assert config.COUNCIL_MODELS == ["model1", "model2", "model3"]


def test_chairman_model_from_env():
    """Test that chairman model can be set via environment variable."""
    with patch.dict(os.environ, {"LLM_COUNCIL_CHAIRMAN": "test-chairman"}):
        import importlib
        import llm_council_mcp.config as config
        importlib.reload(config)
        
        assert config.CHAIRMAN_MODEL == "test-chairman"


def test_config_file_loading():
    """Test that configuration can be loaded from JSON file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_dir = Path(tmpdir) / ".config" / "llm-council"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.json"
        
        test_config = {
            "council_models": ["custom1", "custom2"],
            "chairman_model": "custom-chairman"
        }
        
        with open(config_file, 'w') as f:
            json.dump(test_config, f)
        
        # Mock Path.home() to return our temp directory
        with patch.object(Path, 'home', return_value=Path(tmpdir)):
            import importlib
            import llm_council_mcp.config as config
            importlib.reload(config)
            
            assert config.COUNCIL_MODELS == ["custom1", "custom2"]
            assert config.CHAIRMAN_MODEL == "custom-chairman"


def test_default_models_used():
    """Test that defaults are used when no config is provided."""
    with patch.dict(os.environ, {}, clear=True):
        with patch.object(Path, 'home', return_value=Path("/nonexistent")):
            import importlib
            import llm_council_mcp.config as config
            importlib.reload(config)
            
            assert config.COUNCIL_MODELS == config.DEFAULT_COUNCIL_MODELS
            assert config.CHAIRMAN_MODEL == config.DEFAULT_CHAIRMAN_MODEL


def test_api_url_constant():
    """Test that OpenRouter API URL is properly defined."""
    import llm_council_mcp.config as config
    
    assert config.OPENROUTER_API_URL == "https://openrouter.ai/api/v1/chat/completions"
