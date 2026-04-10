import asyncio
import sys
import argparse
from typing import Dict, Any

try:
    from llm_council import run_full_council
except ImportError:
    print("Error: llm-council is not installed in the current environment.")
    print("Run: uv sync --all-extras")
    sys.exit(1)


async def main():
    parser = argparse.ArgumentParser(description="LLM Council CLI Query Tool")
    parser.add_argument("query", help="The question to ask the council")
    parser.add_argument("--details", action="store_true", help="Show individual model responses")
    parser.add_argument(
        "--confidence",
        choices=["quick", "balanced", "high", "reasoning"],
        default="high",
        help="Confidence level (default: high)",
    )
    parser.add_argument("--no-cache", action="store_true", help="Bypass cache")
    parser.add_argument(
        "--adversary",
        action="store_true",
        default=None,
        help="Enable Reactive Devil's Advocate mode",
    )
    parser.add_argument(
        "--no-adversary",
        action="store_false",
        dest="adversary",
        help="Disable Reactive Devil's Advocate mode",
    )
    parser.add_argument(
        "--dissent",
        action="store_true",
        help="Enable Constructive Dissent (detects minority opinions during voting)",
    )

    args = parser.parse_args()

    # Run the council process
    try:
        from llm_council.unified_config import get_config

        config = get_config()

        target_models = None
        if args.confidence in config.tiers.pools:
            target_models = config.tiers.pools[args.confidence].models

        if target_models:
            config.council.models = target_models

        print(f"\n[Council] Query: {args.query}")
        print(f"[*] Stage 1: Collecting initial opinions (Confidence: {args.confidence})...")

        stage1, stage2, stage3, metadata = await run_full_council(
            args.query,
            bypass_cache=args.no_cache,
            models=target_models,
            adversarial_mode=args.adversary,
            include_dissent=args.dissent,
        )

        print("[*] Stage 2: Peer reviewing and ranking...")
        print("[*] Stage 3: Synthesizing final consensus...")

        synthesis = (
            stage3.get("response", "No synthesis provided.") if isinstance(stage3, dict) else stage3
        )

        print("-" * 50)
        print("\n### CHAIRMAN'S SYNTHESIS\n")
        print(synthesis)
        print("\n" + "-" * 50)

        # Display Rankings if available
        rankings = metadata.get("aggregate_rankings", [])
        if rankings:
            print("\n### COUNCIL RANKINGS (Borda Score)")
            for r in rankings[:5]:
                model_name = r.get("model", "Unknown")
                score = r.get("borda_score", 0.0)
                print(f" - {model_name}: {score:.2f}")

        # ADR-DA: Display Devil's Advocate Critique if available
        dissent_report = metadata.get("dissent_report")
        if dissent_report:
            print("\n" + "!" * 50)
            print("### DEVIL'S ADVOCATE - DISSENTING REPORT")
            print("-" * 50)
            print(dissent_report)
            print("!" * 50)

        # ADR-CD: Display Constructive Dissent if available
        dissent_text = metadata.get("dissent")
        if dissent_text:
            print("\n" + "." * 50)
            print("### CONSTRUCTIVE DISSENT (Minority Opinion)")
            print("-" * 50)
            print(dissent_text)
            print("." * 50)

        if args.details:
            print("\n" + "=" * 50)
            print("### INDIVIDUAL RESPONSES")
            for res in stage1:
                print(f"\n--- {res['model']} ---")
                print(res["response"])

    except Exception as e:
        print(f"\n[!] Error during council deliberation: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nDeliberation cancelled by user.")
        sys.exit(0)
