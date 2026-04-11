from llm_council.unified_config import get_config, get_api_key, get_key_source


def main():
    cfg = get_config()
    provider = cfg.gateways.providers.get("openrouter")

    print(f"--- Global Configuration ---")
    print(f"Default Gateway: {cfg.gateways.default}")
    print(f"OpenRouter Enabled: {provider.enabled if provider else 'None'}")

    # Check key resolution
    direct_key = provider.api_key if provider else None
    helper_key = get_api_key("openrouter")
    source = get_key_source()

    print(f"\n--- Key Resolution ---")
    print(f"Direct Config Key: {'[SET]' if direct_key else '[MISSING]'}")
    print(f"Resolved Helper Key: {'[SET]' if helper_key else '[MISSING]'}")
    print(f"Resolution Source: {source}")

    if helper_key:
        print(f"Key Prefix: {helper_key[:8]}...")


if __name__ == "__main__":
    main()
