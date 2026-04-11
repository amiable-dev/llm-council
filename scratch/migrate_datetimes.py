import os
import re

targets = [
    r"src/llm_council/audition/store.py",
    r"src/llm_council/audition/tracker.py",
    r"src/llm_council/audition/types.py",
    r"src/llm_council/telemetry_client.py",
    r"src/llm_council/metadata/registry.py",
    r"src/llm_council/verification/api.py",
    r"src/llm_council/verification/context.py",
    r"src/llm_council/verification/transcript.py",
    r"tests/test_audition_tracker.py",
    r"tests/test_audition_transitions.py",
    r"tests/test_audition_types.py",
    r"tests/test_discovery.py",
    r"tests/test_registry.py",
    r"tests/unit/verification/test_context.py",
    r"tests/unit/verification/test_transcript.py",
    r"tests/unit/verification/test_types.py",
    r"tests/test_telemetry_alignment.py"
]

def migrate_file(filepath):
    if not os.path.exists(filepath):
        print(f"Skipping {filepath} (not found)")
        return
        
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
        
    # 1. Update imports
    # Handle "from datetime import datetime" -> "from datetime import datetime, UTC"
    content = re.sub(r"from datetime import ([\w, ]*)", lambda m: f"from datetime import {m.group(1)}, UTC" if "UTC" not in m.group(1) else m.group(0), content)
    # Cleanup potential double commas or spaces
    content = content.replace("datetime, , UTC", "datetime, UTC")
    content = content.replace("datetime, UTC, timedelta", "datetime, timedelta, UTC")
    
    # 2. Update usage
    content = content.replace("datetime.utcnow()", "datetime.now(UTC)")
    content = content.replace("datetime.now(datetime.UTC)", "datetime.now(UTC)")
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"Migrated {filepath}")

for target in targets:
    migrate_file(target)
