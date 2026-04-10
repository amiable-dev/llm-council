import pytest
import yaml
from pathlib import Path
from llm_council.unified_config import load_config, UnifiedConfig

def test_adversarial_mode_config_loading(tmp_path):
    """
    Reproduce Bug BUG-022: adversarial_mode in YAML is ignored by load_config.
    """
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_file = config_dir / "llm_council.yaml"
    
    # Define a config matching the user's report
    config_data = {
        "council": {
            "adversarial_mode": True,
            "models": ["model1", "model2", "model3", "model4"]
        }
    }
    
    with open(config_file, "w") as f:
        yaml.dump(config_data, f)
    
    # Load the config
    config = load_config(config_file)
    
    # ASSERTION: The nested council.adversarial_mode should be True
    # If the bug exists, this will likely be False (the default) because 
    # load_config unpacked only the 'council' dict into UnifiedConfig.
    assert config.council.adversarial_mode is True, f"Expected adversarial_mode to be True from YAML, got {config.council.adversarial_mode}"
    assert "model1" in config.council.models, "Expected models to be loaded"

if __name__ == "__main__":
    pytest.main([__file__])
