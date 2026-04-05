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
    parser.add_argument("--confidence", choices=["quick", "balanced", "high", "reasoning"], 
                        default="high", help="Confidence level (default: high)")
    
    args = parser.parse_args()

    print(f"\n[Council] Query: {args.query}")
    print("-" * 50)
    
    # Run the council process
    try:
        # We'll use the core function run_full_council
        # Note: In newer versions, metadata is returned as a dict in the 4th position
        # stage1_results, stage2_results, stage3_result, metadata = await run_full_council(args.query)
        
        print("[*] Stage 1: Collecting initial opinions...")
        # Actually calling run_full_council (v0.3.0+)
        # Based on src/llm_council/__init__.py: run_full_council returns (stage1, stage2, stage3, metadata)
        stage1, stage2, stage3, metadata = await run_full_council(args.query)
        
        print("[*] Stage 2: Peer reviewing and ranking...")
        print("[*] Stage 3: Synthesizing final consensus...")
        
        synthesis = stage3.get("response", "No synthesis provided.") if isinstance(stage3, dict) else stage3
        
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
        
        if args.details:
            print("\n" + "=" * 50)
            print("### INDIVIDUAL RESPONSES")
            for res in stage1:
                print(f"\n--- {res['model']} ---")
                print(res['response'])

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
