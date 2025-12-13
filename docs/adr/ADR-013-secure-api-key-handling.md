# ADR-013: Secure API Key Handling

**Status:** Accepted (Implemented via TDD)
**Date:** 2025-12-13
**Decision Makers:** Engineering, Security

---

## Context

The LLM Council requires an OpenRouter API key to function. Currently, the README recommends configuration patterns that expose the API key in insecure ways:

### Current (Insecure) Patterns in Documentation

**Pattern 1: CLI argument** (visible in process list)
```bash
claude mcp add --env OPENROUTER_API_KEY=sk-or-v1-xxx -- llm-council
```

**Pattern 2: JSON config file** (plaintext on disk)
```json
{
  "mcpServers": {
    "llm-council": {
      "env": {
        "OPENROUTER_API_KEY": "sk-or-v1-xxx"
      }
    }
  }
}
```

### Security Risks

| Pattern | Risk | Severity |
|---------|------|----------|
| CLI argument | Visible in `ps aux`, shell history, process monitors | High |
| JSON config | Plaintext file readable by any process, often in version control | High |
| Environment variable (shell export) | In shell history, inherited by child processes | Medium |

### Desired Properties

1. **No plaintext keys in config files** that might be committed to git
2. **No keys visible in process lists** (`ps`, Activity Monitor)
3. **Minimal friction** for developers (not too complex to set up)
4. **Cross-platform** (macOS, Linux, Windows)
5. **Compatible with MCP client expectations**

---

## Decision

Implement a multi-tier secure key resolution strategy with clear documentation prioritizing security.

### Key Resolution Priority (Council Recommendation)

**Original Proposal:** Keychain → .env → Env var → Config

**Revised (per Council):** Environment Variable → Keychain → .env → Config

```
1. Environment variable (explicit override, CI/CD standard)
   ↓
2. System Keychain/Credential Manager (desktop security)
   ↓
3. Environment variable from .env file (dotenv)
   ↓
4. Config file (least secure, warn user)
```

**Rationale:** Environment variables are the de facto standard in CI/CD and containerized environments. Operators expect `OPENROUTER_API_KEY=xxx ./server` to work. Users should not need to delete a keychain entry to test a different key in their terminal.

### Implementation

#### 1. System Keychain Support (Optional Dependency)

**Council Verdict:** `keyring` must be an **optional** dependency. It breaks in Docker containers and headless Linux servers.

Add optional keychain integration using the `keyring` library:

```python
# config.py additions
import sys

# Track which source the key came from (for diagnostics)
_key_source = None

def _get_api_key_from_keychain() -> Optional[str]:
    """Attempt to retrieve API key from system keychain."""
    try:
        import keyring
        from keyring.backends import fail

        # Check if we have a real backend (not the fail backend)
        if isinstance(keyring.get_keyring(), fail.Keyring):
            return None

        key = keyring.get_password("llm-council", "openrouter_api_key")
        if key:
            return key
    except ImportError:
        pass  # keyring not installed - this is fine
    except Exception:
        pass  # keychain access failed (headless, permissions, etc.)
    return None

def _get_api_key() -> Optional[str]:
    """
    Resolve API key with priority (per Council recommendation):
    1. Environment variable (explicit override, CI/CD standard)
    2. System keychain (desktop security)
    3. .env file (via dotenv, already loaded)
    4. Config file (warn if used)
    """
    global _key_source

    # 1. Environment variable takes priority (CI/CD standard)
    key = os.getenv("OPENROUTER_API_KEY")
    if key:
        _key_source = "environment"
        return key

    # 2. Try keychain (if available)
    key = _get_api_key_from_keychain()
    if key:
        _key_source = "keychain"
        return key

    # 3. .env file would have set the env var, so this is config file fallback
    if _user_config.get("openrouter_api_key"):
        _key_source = "config_file"
        # Emit warning to stderr (suppressible)
        if not os.getenv("LLM_COUNCIL_SUPPRESS_WARNINGS"):
            print(
                "Warning: API key loaded from config file. This is insecure. "
                "Consider using environment variables or keychain. "
                "Set LLM_COUNCIL_SUPPRESS_WARNINGS=1 to silence.",
                file=sys.stderr
            )
        return _user_config.get("openrouter_api_key")

    return None

OPENROUTER_API_KEY = _get_api_key()
```

#### 2. Keychain Setup CLI Command

Add a command to securely store the API key, with stdin support for CI/CD:

```python
# cli.py additions
def setup_key(from_stdin: bool = False):
    """Securely store API key in system keychain."""
    try:
        import keyring
        from keyring.backends import fail
        if isinstance(keyring.get_keyring(), fail.Keyring):
            print("Error: No keychain backend available.", file=sys.stderr)
            print("On headless servers, use environment variables instead.", file=sys.stderr)
            sys.exit(1)
    except ImportError:
        print("Error: keyring package not installed.", file=sys.stderr)
        print("Install with: pip install 'llm-council-core[secure]'", file=sys.stderr)
        sys.exit(1)

    import getpass

    # Support stdin for CI/CD (Council recommendation)
    if from_stdin:
        key = sys.stdin.read().strip()
    else:
        key = getpass.getpass("Enter your OpenRouter API key: ")

    if not key.startswith("sk-or-"):
        print("Warning: Key doesn't look like an OpenRouter key (expected sk-or-...)")
        if not from_stdin:
            confirm = input("Store anyway? [y/N]: ")
            if confirm.lower() != 'y':
                sys.exit(1)

    keyring.set_password("llm-council", "openrouter_api_key", key)
    print("API key stored securely in system keychain.")
```

**Usage**:
```bash
# Interactive (desktop)
llm-council setup-key
# Prompts for key securely (no echo)

# Non-interactive for CI/CD (Council recommendation)
echo "$OPENROUTER_API_KEY" | llm-council setup-key --stdin

# Integration with secret managers
vault read -field=key secret/openrouter | llm-council setup-key --stdin
aws secretsmanager get-secret-value --secret-id openrouter --query SecretString --output text | llm-council setup-key --stdin
```

#### 3. .env File Pattern (Recommended Default)

The `.env` file pattern is already supported via `python-dotenv`. Document this as the recommended approach for users who don't want keychain complexity:

```bash
# Create .env in your project or home directory
echo "OPENROUTER_API_KEY=sk-or-v1-xxx" >> ~/.config/llm-council/.env

# Add to .gitignore
echo ".env" >> .gitignore
```

#### 4. MCP Client Configuration (Secure Pattern)

For Claude Desktop and Claude Code, recommend environment variable inheritance rather than inline keys:

**Secure Claude Desktop Config**:
```json
{
  "mcpServers": {
    "llm-council": {
      "command": "llm-council"
    }
  }
}
```
(Key is inherited from shell environment or keychain - no `env` block needed)

**Secure Claude Code Setup**:
```bash
# First, set up the key securely
llm-council setup-key

# Then add MCP without exposing the key
claude mcp add --transport stdio llm-council --scope user -- llm-council
```

---

## Documentation Updates

### README Changes

Replace current insecure examples with:

```markdown
## Setup

### 1. Get an OpenRouter API Key

1. Sign up at [openrouter.ai](https://openrouter.ai/)
2. Get your API key from the dashboard

### 2. Store Your API Key Securely

**Option A: System Keychain (Recommended)**

The most secure option - key is encrypted by your OS:

```bash
pip install keyring  # If not already installed
llm-council setup-key
# Enter your key when prompted (input is hidden)
```

**Option B: Environment File**

Create a `.env` file (ensure it's in `.gitignore`):

```bash
# In your project directory or ~/.config/llm-council/
echo "OPENROUTER_API_KEY=sk-or-v1-your-key-here" > .env
```

**Option C: Environment Variable**

Set in your shell profile (`~/.zshrc`, `~/.bashrc`):

```bash
export OPENROUTER_API_KEY="sk-or-v1-your-key-here"
```

### Security Best Practices

- **Never** put API keys in command-line arguments
- **Never** commit API keys to version control
- **Never** put API keys in JSON config files that might be shared
- Use `.gitignore` to exclude `.env` files
```

---

## Package Changes

### New Optional Dependency

```toml
# pyproject.toml
[project.optional-dependencies]
secure = ["keyring>=23.0.0"]
```

**Installation**:
```bash
pip install "llm-council-core[secure]"
```

### New CLI Command

```toml
# pyproject.toml - no change needed, handled in cli.py
```

---

## Alternatives Considered

### Alternative 1: Require Keychain

**Rejected**: Too much friction for quick setup. Keychain should be optional but recommended.

### Alternative 2: Encrypted Config File

**Rejected**: Requires managing encryption keys, which creates a chicken-and-egg problem.

### Alternative 3: OAuth / Token Exchange

**Rejected**: OpenRouter uses API keys, not OAuth. Would require a proxy service.

### Alternative 4: HashiCorp Vault / Cloud Secret Manager Integration

**Rejected** (Council: YAGNI): Users already inject secrets via environment variables from their infrastructure (ECS, Lambda, Kubernetes). Stdin support covers the gap for automation:

```bash
# Users can integrate with any secret manager via stdin
vault read -field=key secret/openrouter | llm-council setup-key --stdin
```

---

## Migration Path

1. **v0.1.x (current)**: Document secure patterns, add deprecation warnings for insecure usage
2. **v0.2.x**: Add keychain support with `setup-key` command
3. **v0.3.x**: Log warnings when key is loaded from config file
4. **v1.0.0**: Consider removing config file key support entirely

---

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Keyring not available on all systems | Graceful fallback to env vars; clear error messages |
| Users copy insecure examples from old docs | Update all documentation simultaneously; add security warnings |
| Breaking change for existing users | Maintain backwards compatibility; warn but don't break |
| Keychain access requires user interaction on some systems | Document platform-specific behavior |

---

## Council Review Decisions

| Question | Council Verdict |
|----------|-----------------|
| Emit runtime warnings? | **Yes**, but suppressible via `LLM_COUNCIL_SUPPRESS_WARNINGS=1`. Warn to stderr (not stdout). |
| Keyring dependency? | **Optional only** via `pip install llm-council-core[secure]`. Must not break in headless/Docker. |
| Stdin support for CI/CD? | **Yes**, essential for automation. `echo $KEY \| llm-council setup-key --stdin` |
| Cloud secret managers? | **No** (YAGNI). Users inject secrets via env vars from their infrastructure. |
| Key resolution priority? | **Env var first** (not keychain). Respects CI/CD and 12-factor app standards. |

---

## References

- [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
- [Python keyring library](https://pypi.org/project/keyring/)
- [12-Factor App: Config](https://12factor.net/config)
