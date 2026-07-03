"""CLI entry point with graceful degradation for optional dependencies (ADR-009).

Usage:
    llm-council               # Start MCP server (default)
    llm-council serve         # Start HTTP server
    llm-council serve --port 9000 --host 127.0.0.1
    llm-council setup-key     # Store API key in system keychain (ADR-013)
    llm-council bias-report   # Cross-session bias analysis (ADR-018)
    llm-council install-skills --target .github/skills  # Install bundled skills
    llm-council gate --snapshot abc123  # Quality gate for CI/CD
"""

import argparse
import sys

from llm_council import __version__

# Optional keyring import - may not be installed
keyring = None
try:
    import keyring as _keyring_module

    keyring = _keyring_module
except ImportError:
    pass  # keyring not installed - this is fine


def _is_fail_backend() -> bool:
    """Check if keyring has a fail backend (headless/Docker)."""
    if keyring is None:
        return True
    try:
        from keyring.backends import fail

        return isinstance(keyring.get_keyring(), fail.Keyring)
    except Exception:
        return True


def bench_command(
    action: str,
    dataset: str,
    items: str,
    max_usd,
    set_flag: bool,
    output_format: str,
    configs: str = "council",
    publish: str = None,
) -> int:
    """ADR-048 bench CLI. Returns the process exit code (0/1/2)."""
    import asyncio
    import json as _json
    from pathlib import Path

    from .bench import harness

    runs_dir = harness.DEFAULT_RUNS_DIR

    def _latest_run():
        artefacts = sorted(runs_dir.glob("run-*.json"))
        if not artefacts:
            sys.stdout.write("No bench runs recorded yet — run `llm-council bench run` first.\n")
            return None
        return _json.loads(artefacts[-1].read_text())

    if action == "matrix":
        import json as _json2

        from .bench.matrix import MatrixConfig, format_matrix_table, run_matrix

        matrix_configs = []
        for name in [c.strip() for c in configs.split(",") if c.strip()]:
            if name == "solo-members":
                from .council import _get_council_models

                for model in _get_council_models():
                    matrix_configs.append(
                        MatrixConfig(name=f"solo:{model}", kind="solo")
                    )
            elif name.startswith("solo:"):
                matrix_configs.append(MatrixConfig(name=name, kind="solo"))
            elif name in ("council", "graduated"):
                matrix_configs.append(MatrixConfig(name=name, kind=name))
            else:
                sys.stdout.write(f"Unknown matrix config: {name}\n")
                return 2
        items_filter = [i.strip() for i in items.split(",")] if items else None
        rows = asyncio.run(
            run_matrix(
                matrix_configs,
                dataset_dir=Path(dataset),
                max_usd=max_usd,
                items_filter=items_filter,
            )
        )
        if output_format == "json":
            sys.stdout.write(_json2.dumps(rows, indent=2) + "\n")
        else:
            sys.stdout.write(format_matrix_table(rows) + "\n")
        return 0 if all(not r.get("aborted") for r in rows) else 2

    if action == "run":
        items_filter = [i.strip() for i in items.split(",")] if items else None
        run = asyncio.run(
            harness.run_bench(
                dataset_dir=Path(dataset),
                items_filter=items_filter,
                max_usd=max_usd,
            )
        )
        comparison = harness.compare_to_baseline(run)
        sys.stdout.write(harness.format_report(run, comparison, output_format) + "\n")
        return run.exit_code

    if action == "baseline":
        data = _latest_run()
        if data is None:
            return 2
        if not set_flag:
            sys.stdout.write("Pass --set to snapshot the latest run as baseline.\n")
            return 0
        run = harness.BenchRun(
            started_at=data["started_at"],
            items_total=data["items_total"],
            items_run=data["items_run"],
            items_passed=data["items_passed"],
            total_cost_usd=data["total_cost_usd"],
            cost_known=data["cost_known"],
            aborted=data.get("aborted"),
            results=[harness.ItemResult(**r) for r in data.get("results", [])],
        )
        path = harness.set_baseline(run)
        sys.stdout.write(f"Baseline written to {path}\n")
        return 0

    # report
    data = _latest_run()
    if data is None:
        return 2
    run = harness.BenchRun(
        started_at=data["started_at"],
        items_total=data["items_total"],
        items_run=data["items_run"],
        items_passed=data["items_passed"],
        total_cost_usd=data["total_cost_usd"],
        cost_known=data["cost_known"],
        aborted=data.get("aborted"),
        results=[harness.ItemResult(**r) for r in data.get("results", [])],
    )
    comparison = harness.compare_to_baseline(run)
    sys.stdout.write(harness.format_report(run, comparison, output_format) + "\n")
    if publish:
        from .bench.publication import write_results_page

        page = write_results_page(run, Path(publish), dataset_version=Path(dataset).name)
        sys.stdout.write(f"Results page regenerated at {page}\n")
    return run.exit_code


def calibration_report(
    logs: str,
    fit: bool,
    dispositions: str,
    output: str,
    output_format: str,
) -> None:
    """ADR-047 P2: reproducible confidence-calibration analysis + optional fit."""
    import json as _json
    from pathlib import Path

    from .verification.calibration import (
        analyze_corpus,
        fit_from_dispositions,
        load_corpus,
        load_dispositions,
    )

    records = load_corpus(Path(logs))
    summary = analyze_corpus(records)
    disp = load_dispositions(Path(dispositions))
    summary["dispositions_recorded"] = len(disp)

    if fit:
        mapping = fit_from_dispositions(records, disp)
        if mapping.is_identity:
            summary["fit"] = "skipped — no (confidence, disposition) pairs"
        else:
            out_path = Path(output)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(mapping.to_json())
            summary["fit"] = f"mapping with {len(mapping.points)} points -> {out_path}"

    if output_format == "json":
        sys.stdout.write(_json.dumps(summary, indent=2) + "\n")
        return
    sys.stdout.write(f"Calibration corpus: {summary['n']} results from {logs}\n")
    sys.stdout.write(f"Verdicts: {summary.get('verdicts')}\n")
    sys.stdout.write(f"Mean confidence by verdict: {summary.get('mean_confidence')}\n")
    zb = summary.get("zero_blocking_fail_rate")
    sys.stdout.write(
        f"Zero-blocking FAIL rate: {zb} ({summary.get('zero_blocking_fails')} results) "
        "- FAILs with no blocking issue are the over-confidence anomaly (ADR-047)\n"
    )
    sys.stdout.write(f"Human dispositions recorded: {summary['dispositions_recorded']}\n")
    if "fit" in summary:
        sys.stdout.write(f"Fit: {summary['fit']}\n")


def main():
    """Main CLI entry point - dispatches to MCP or HTTP server."""
    parser = argparse.ArgumentParser(
        prog="llm-council",
        description="LLM Council - Multi-model deliberation system",
    )
    parser.add_argument(
        "--version",
        "-V",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    subparsers = parser.add_subparsers(dest="command")

    # HTTP serve command
    serve_parser = subparsers.add_parser(
        "serve",
        help="Start HTTP server for REST API access",
    )
    serve_parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host to bind to (default: 0.0.0.0)",
    )
    serve_parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to bind to (default: 8000)",
    )

    # Setup key command (ADR-013)
    setup_key_parser = subparsers.add_parser(
        "setup-key",
        help="Securely store API key in system keychain",
    )
    setup_key_parser.add_argument(
        "--stdin",
        action="store_true",
        dest="from_stdin",
        help="Read API key from stdin (for CI/CD automation)",
    )

    # Bias report command (ADR-018)
    bias_parser = subparsers.add_parser(
        "bias-report",
        help="Analyze cross-session bias metrics",
    )
    bias_parser.add_argument(
        "--input",
        type=str,
        dest="input_path",
        help="Path to JSONL store (default: ~/.llm-council/bias_metrics.jsonl)",
    )
    bias_parser.add_argument(
        "--sessions",
        type=int,
        dest="max_sessions",
        help="Limit to last N sessions",
    )
    bias_parser.add_argument(
        "--days",
        type=int,
        dest="max_days",
        help="Limit to last N days",
    )
    bias_parser.add_argument(
        "--format",
        choices=["text", "json", "csv"],
        default="text",
        dest="output_format",
        help="Output format (default: text)",
    )
    bias_parser.add_argument(
        "--verbose",
        action="store_true",
        help="Include detailed reviewer profiles",
    )
    bias_parser.add_argument(
        "--amplification",
        action="store_true",
        help="Append the reviewer-agreement decomposition (ADR-047 P4, report-only)",
    )

    # Install skills command
    install_parser = subparsers.add_parser(
        "install-skills",
        help="Install bundled skills to a target directory",
    )
    install_parser.add_argument(
        "--target",
        type=str,
        default=".github/skills",
        help="Target directory for skills (default: .github/skills)",
    )
    install_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing skills",
    )
    install_parser.add_argument(
        "--list",
        action="store_true",
        dest="list_only",
        help="List available skills without installing",
    )

    # Server Card generation (ADR-045 P2)
    card_parser = subparsers.add_parser(
        "server-card",
        help="Print the MCP Server Card JSON (generated from the tool registry)",
    )
    card_parser.add_argument(
        "--output",
        type=str,
        default="-",
        help="Write to a file instead of stdout (default: stdout)",
    )

    # Bench harness (ADR-048)
    bench_parser = subparsers.add_parser(
        "bench",
        help="Golden-dataset quality benchmark (ADR-048) — costs real API spend",
    )
    bench_parser.add_argument(
        "action", choices=["run", "baseline", "report", "matrix"],
        help="run: execute the dataset; baseline: snapshot last run as baseline; report: render last run",
    )
    bench_parser.add_argument("--dataset", type=str, default="bench/dataset/v1")
    bench_parser.add_argument("--items", type=str, default=None, help="Comma-separated item ids")
    bench_parser.add_argument("--max-usd", type=float, default=None, dest="max_usd")
    bench_parser.add_argument("--set", action="store_true", dest="set_baseline_flag",
                              help="(baseline) write the snapshot")
    bench_parser.add_argument("--format", choices=["md", "json"], default="md", dest="bench_format")
    bench_parser.add_argument(
        "--publish", type=str, default=None,
        help="(report) also regenerate the docs results page at this path",
    )
    bench_parser.add_argument(
        "--configs", type=str, default="council",
        help="(matrix) comma list: council, graduated, solo:<model>, solo-members",
    )

    # Calibration report (ADR-047 P2)
    cal_parser = subparsers.add_parser(
        "calibration-report",
        help="Analyze verify-confidence calibration from .council/logs (ADR-047 P2)",
    )
    cal_parser.add_argument(
        "--logs", type=str, default=".council/logs", help="Transcript logs directory"
    )
    cal_parser.add_argument(
        "--fit",
        action="store_true",
        help="Fit a monotonic mapping from recorded dispositions and write it",
    )
    cal_parser.add_argument(
        "--dispositions",
        type=str,
        default=".council/calibration/dispositions.jsonl",
        help="JSONL of {verification_id, upheld} human dispositions",
    )
    cal_parser.add_argument(
        "--output",
        type=str,
        default=".council/calibration/mapping.json",
        help="Where --fit writes the mapping",
    )
    cal_parser.add_argument(
        "--format", choices=["text", "json"], default="text", dest="cal_format"
    )

    # Gate command (CI/CD quality gate)
    gate_parser = subparsers.add_parser(
        "gate",
        help="Run quality gate verification (for CI/CD)",
    )
    gate_parser.add_argument(
        "--snapshot",
        type=str,
        required=True,
        help="Git commit SHA to verify",
    )
    gate_parser.add_argument(
        "--file-paths",
        type=str,
        nargs="*",
        dest="file_paths",
        help="Specific file paths to verify (space-separated)",
    )
    gate_parser.add_argument(
        "--confidence-threshold",
        type=float,
        default=0.7,
        dest="confidence_threshold",
        help="Minimum confidence to pass (0.0-1.0, default: 0.7)",
    )
    gate_parser.add_argument(
        "--tier",
        choices=["quick", "balanced", "high", "reasoning"],
        default="balanced",
        help="Verification tier: models + timeouts + input cap (default: balanced)",
    )
    gate_parser.add_argument(
        "--rubric-focus",
        type=str,
        dest="rubric_focus",
        help="Focus area: Security, Performance, Testing, General",
    )
    gate_parser.add_argument(
        "--output-format",
        choices=["text", "json"],
        default="text",
        dest="output_format",
        help="Output format (default: text)",
    )

    args = parser.parse_args()

    if args.command == "serve":
        serve_http(host=args.host, port=args.port)
    elif args.command == "setup-key":
        setup_key(from_stdin=args.from_stdin)
    elif args.command == "bias-report":
        bias_report(
            input_path=args.input_path,
            max_sessions=args.max_sessions,
            max_days=args.max_days,
            output_format=args.output_format,
            verbose=args.verbose,
            amplification=args.amplification,
        )
    elif args.command == "install-skills":
        install_skills(
            target=args.target,
            force=args.force,
            list_only=args.list_only,
        )
    elif args.command == "bench":
        raise SystemExit(
            bench_command(
                action=args.action,
                dataset=args.dataset,
                items=args.items,
                max_usd=args.max_usd,
                set_flag=args.set_baseline_flag,
                output_format=args.bench_format,
                configs=args.configs,
                publish=args.publish,
            )
        )
    elif args.command == "calibration-report":
        calibration_report(
            logs=args.logs,
            fit=args.fit,
            dispositions=args.dispositions,
            output=args.output,
            output_format=args.cal_format,
        )
    elif args.command == "server-card":
        import json as _json

        from .server_card import build_server_card

        card_json = _json.dumps(build_server_card(), indent=2) + "\n"
        if args.output == "-":
            sys.stdout.write(card_json)
        else:
            with open(args.output, "w") as fh:
                fh.write(card_json)
    elif args.command == "gate":
        exit_code = run_gate(
            snapshot=args.snapshot,
            file_paths=args.file_paths,
            confidence_threshold=args.confidence_threshold,
            rubric_focus=args.rubric_focus,
            output_format=args.output_format,
            tier=args.tier,
        )
        sys.exit(exit_code)
    else:
        # Default: MCP server
        serve_mcp()


def serve_http(host: str = "0.0.0.0", port: int = 8000):
    """Start the HTTP server.

    Requires the [http] extra: pip install 'llm-council-core[http]'
    """
    try:
        from llm_council.http_server import app

        import uvicorn
    except ImportError:
        print("Error: HTTP dependencies not installed.", file=sys.stderr)
        print("\nTo use the HTTP server, install with:", file=sys.stderr)
        print("    pip install 'llm-council-core[http]'", file=sys.stderr)
        sys.exit(1)

    uvicorn.run(app, host=host, port=port)


def serve_mcp():
    """Start the MCP server.

    Requires the [mcp] extra: pip install 'llm-council-core[mcp]'
    """
    try:
        from llm_council.mcp_server import mcp
    except ImportError as e:
        print(f"Error importing MCP server: {e}", file=sys.stderr)
        print("\nTo use the MCP server, install with:", file=sys.stderr)
        print("    pip install 'llm-council-core[mcp]'", file=sys.stderr)
        print("\nFor library-only usage, import directly:", file=sys.stderr)
        print("    from llm_council import run_full_council", file=sys.stderr)
        sys.exit(1)

    mcp.run()


def setup_key(from_stdin: bool = False):
    """Securely store API key in system keychain (ADR-013).

    Args:
        from_stdin: If True, read key from stdin (for CI/CD automation).
                   If False, prompt interactively using getpass.
    """
    # Check if keyring is available
    if keyring is None:
        print("Error: keyring package not installed.", file=sys.stderr)
        print("\nInstall with: pip install 'llm-council-core[secure]'", file=sys.stderr)
        sys.exit(1)

    # Check for fail backend (headless/Docker)
    if _is_fail_backend():
        print("Error: No keychain backend available.", file=sys.stderr)
        print("On headless servers, use environment variables instead.", file=sys.stderr)
        print("\nSet OPENROUTER_API_KEY in your environment or .env file.", file=sys.stderr)
        sys.exit(1)

    import getpass

    # Get the key
    if from_stdin:
        key = sys.stdin.read().strip()
    else:
        key = getpass.getpass("Enter your OpenRouter API key: ")

    if not key:
        print("Error: No key provided.", file=sys.stderr)
        sys.exit(1)

    # Validate format (warning only, not blocking)
    if not key.startswith("sk-or-"):
        print("Warning: Key doesn't look like an OpenRouter key (expected sk-or-...)")
        if not from_stdin:
            confirm = input("Store anyway? [y/N]: ")
            if confirm.lower() != "y":
                print("Aborted.")
                sys.exit(1)

    # Store the key
    try:
        keyring.set_password("llm-council", "openrouter_api_key", key)
        print("API key stored securely in system keychain.")
    except Exception as e:
        print(f"Error storing key: {e}", file=sys.stderr)
        sys.exit(1)


def bias_report(
    input_path: str = None,
    max_sessions: int = None,
    max_days: int = None,
    output_format: str = "text",
    verbose: bool = False,
    amplification: bool = False,
):
    """Generate cross-session bias analysis report (ADR-018).

    Args:
        input_path: Path to JSONL store (default: ~/.llm-council/bias_metrics.jsonl)
        max_sessions: Limit to last N sessions
        max_days: Limit to last N days
        output_format: 'text' or 'json'
        verbose: Include detailed reviewer profiles
    """
    from pathlib import Path

    from llm_council.bias_aggregation import (
        generate_bias_report_text,
        generate_bias_report_json,
        generate_bias_report_csv,
    )

    store_path = Path(input_path) if input_path else None

    if output_format == "json":
        output = generate_bias_report_json(
            store_path=store_path,
            max_sessions=max_sessions,
            max_days=max_days,
        )
    elif output_format == "csv":
        output = generate_bias_report_csv(
            store_path=store_path,
            max_sessions=max_sessions,
            max_days=max_days,
        )
    else:
        output = generate_bias_report_text(
            store_path=store_path,
            max_sessions=max_sessions,
            max_days=max_days,
            verbose=verbose,
        )

    # ADR-047 P4 (#416): append the reviewer-agreement decomposition.
    # Report-only — pure analysis over the same store, no gating.
    if amplification:
        import json as _json

        from llm_council.bias_amplification import (
            amplification_report,
            format_amplification_report,
        )
        from llm_council.bias_persistence import read_bias_records

        records = read_bias_records(
            store_path=store_path, max_sessions=max_sessions, max_days=max_days
        )
        report = amplification_report(records)
        if output_format == "json":
            output = output.rstrip() + "\n" + _json.dumps(
                {"amplification": report}, indent=2
            )
        else:
            output = output.rstrip() + "\n\n" + format_amplification_report(report)

    print(output)


def install_skills(
    target: str = ".github/skills",
    force: bool = False,
    list_only: bool = False,
):
    """Install bundled skills to a target directory.

    Args:
        target: Target directory for skills (default: .github/skills)
        force: Overwrite existing skills
        list_only: List available skills without installing
    """
    import shutil
    from pathlib import Path
    from importlib.resources import files, as_file

    # Expand user home directory in target path
    target = str(Path(target).expanduser())

    # Get bundled skills location (Python 3.10+ required)
    bundled_ref = files("llm_council.skills") / "bundled"

    # Use context manager for traversable resources
    with as_file(bundled_ref) as bundled_path:
        if not bundled_path.exists():
            print("Error: Bundled skills not found in package.", file=sys.stderr)
            print("This may indicate a packaging issue.", file=sys.stderr)
            sys.exit(1)

        # Find available skills
        skills = []
        for item in bundled_path.iterdir():
            if item.is_dir() and (item / "SKILL.md").exists():
                skills.append(item.name)

        if list_only:
            print("Available bundled skills:")
            for skill in sorted(skills):
                print(f"  - {skill}")
            return

        if not skills:
            print("No bundled skills found.", file=sys.stderr)
            sys.exit(1)

        # Create target directory
        target_path = Path(target)
        target_path.mkdir(parents=True, exist_ok=True)

        # Copy skills
        installed = []
        skipped = []
        for skill in skills:
            src = bundled_path / skill
            dst = target_path / skill

            if dst.exists() and not force:
                skipped.append(skill)
                continue

            if dst.exists():
                shutil.rmtree(dst)

            shutil.copytree(src, dst)
            installed.append(skill)

        # Copy marketplace.json if it exists
        marketplace_src = bundled_path / "marketplace.json"
        marketplace_dst = target_path / "marketplace.json"
        if marketplace_src.exists():
            if not marketplace_dst.exists() or force:
                shutil.copy2(marketplace_src, marketplace_dst)

        # Report results
        if installed:
            print(f"Installed {len(installed)} skill(s) to {target}:")
            for skill in installed:
                print(f"  + {skill}")

        if skipped:
            print(f"\nSkipped {len(skipped)} existing skill(s) (use --force to overwrite):")
            for skill in skipped:
                print(f"  - {skill}")

        if not installed and not skipped:
            print("No skills to install.")


def run_gate(
    snapshot: str,
    file_paths: list = None,
    confidence_threshold: float = 0.7,
    rubric_focus: str = None,
    output_format: str = "text",
    tier: str = "balanced",
) -> int:
    """Run quality gate verification for CI/CD.

    Args:
        snapshot: Git commit SHA to verify.
        file_paths: Optional list of specific file paths to verify.
        confidence_threshold: Minimum confidence to pass (0.0-1.0).
        rubric_focus: Optional focus area (Security, Performance, etc.).
        output_format: Output format ('text' or 'json').

    Returns:
        Exit code: 0=PASS, 1=FAIL, 2=UNCLEAR
    """
    import asyncio
    import json

    # Check for FastAPI dependency (required for verification module)
    try:
        import fastapi  # noqa: F401
    except ImportError:
        print("Error: FastAPI is required for the gate command.", file=sys.stderr)
        print("\nInstall with: pip install 'llm-council-core[http]'", file=sys.stderr)
        return 2  # UNCLEAR

    try:
        from llm_council.verification.api import run_verification, VerifyRequest
        from llm_council.verification.transcript import create_transcript_store
        from llm_council.verification.formatting import format_verification_result
    except ImportError as e:
        print(f"Error: Verification dependencies not available: {e}", file=sys.stderr)
        print("\nInstall with: pip install 'llm-council-core[http]'", file=sys.stderr)
        return 2  # UNCLEAR

    async def _run():
        request = VerifyRequest(
            snapshot_id=snapshot,
            target_paths=file_paths,
            rubric_focus=rubric_focus,
            confidence_threshold=confidence_threshold,
            tier=tier,
        )
        store = create_transcript_store()
        return await run_verification(request, store)

    try:
        result = asyncio.run(_run())

        if output_format == "json":
            print(json.dumps(result, indent=2))
        else:
            formatted = format_verification_result(result)
            print(formatted)

        # Return appropriate exit code
        exit_code = result.get("exit_code", 2)
        return exit_code

    except Exception as e:
        print(f"Error during verification: {e}", file=sys.stderr)
        return 2  # UNCLEAR


if __name__ == "__main__":
    main()
