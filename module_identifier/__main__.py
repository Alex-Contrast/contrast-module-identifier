"""CLI entry point: python -m module_identifier /path/to/repo"""

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from mcp import McpError

from .config import ContrastConfig
from .identify import identify_repo
from .llm import LLMConfig
from .pipeline import run

log = logging.getLogger(__name__)


def main():
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Discover modules in a repo and resolve them to Contrast app IDs.",
    )
    parser.add_argument(
        "repo_path",
        nargs="?",
        default=".",
        help="Path to repository to scan (default: current directory)",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=None,
        help="Confidence threshold (default: 0.7 for --single, 0.5 for module-level)",
    )
    parser.add_argument(
        "--depth",
        type=int,
        default=4,
        help="Max directory depth for module discovery (default: 4)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "--single",
        action="store_true",
        help="EA mode: resolve repo to a single app_id (default: module-level)",
    )
    parser.add_argument(
        "-o", "--output",
        help="Write JSON details to file (for debugging)",
    )
    parser.add_argument(
        "--output-env",
        help="Write CONTRAST_APP_ID=<value> to file (for CI consumption)",
    )
    args = parser.parse_args()

    if args.output_env and not args.single:
        print("Error: --output-env requires --single mode", file=sys.stderr)
        sys.exit(1)

    level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(name)s %(levelname)s %(message)s",
        stream=sys.stderr,
    )

    repo_path = str(Path(args.repo_path).resolve())

    try:
        contrast_config = ContrastConfig.from_env()
    except ValueError as e:
        print(f"Contrast config error: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        llm_config = LLMConfig.from_env()
    except ValueError as e:
        print(f"LLM config error: {e}", file=sys.stderr)
        sys.exit(1)

    t0 = time.time()

    if args.single:
        threshold = args.threshold if args.threshold is not None else 0.7
        try:
            match = asyncio.run(identify_repo(
                repo_path=repo_path,
                config=contrast_config,
                llm_config=llm_config,
                confidence_threshold=threshold,
            ))
        except PermissionError:
            print(f"Cannot read repository at {repo_path}.", file=sys.stderr)
            log.debug("PermissionError for %s", repo_path, exc_info=True)
            sys.exit(1)
        except McpError as e:
            print(f"Contrast API error: {e}", file=sys.stderr)
            log.debug("McpError detail", exc_info=True)
            sys.exit(1)
        except TimeoutError:
            print("Timeout connecting to Contrast.", file=sys.stderr)
            log.debug("TimeoutError", exc_info=True)
            sys.exit(1)
        except ConnectionError as e:
            print("Cannot connect to Contrast MCP server.", file=sys.stderr)
            log.debug("ConnectionError detail: %s", e, exc_info=True)
            sys.exit(1)
        except OSError as e:
            print(
                "Cannot start Contrast MCP server. "
                "Verify MCP_CONTRAST_JAR_PATH or that Java/Docker is installed.",
                file=sys.stderr,
            )
            log.debug("OSError detail: %s", e, exc_info=True)
            sys.exit(1)
        except Exception as e:
            print(f"Unexpected error: {type(e).__name__}: {e}", file=sys.stderr)
            log.debug("Unexpected exception", exc_info=True)
            sys.exit(1)

        elapsed_ms = (time.time() - t0) * 1000

        output = {
            "repo_path": repo_path,
            "app_id": match.app_id if match else None,
            "app_name": match.app_name if match else None,
            "confidence": match.confidence if match else None,
            "source": match.source if match else None,
            "execution_time_ms": round(elapsed_ms, 1),
        }
    else:
        threshold = args.threshold if args.threshold is not None else 0.5
        result = asyncio.run(run(
            repo_path=repo_path,
            config=contrast_config,
            llm_config=llm_config,
            confidence_threshold=threshold,
            depth=args.depth,
        ))
        elapsed_ms = (time.time() - t0) * 1000

        output = {
            "repo_path": repo_path,
            "total_modules": result.total,
            "deterministic_matched": {
                path: {
                    "app_id": m.app_id,
                    "app_name": m.app_name,
                    "confidence": m.confidence,
                    "search_term": m.search_term,
                }
                for path, m in result.matched.items()
            },
            "llm_matched": {
                path: {
                    "app_id": m.application_id,
                    "app_name": m.application_name,
                    "confidence": m.confidence,
                    "reasoning": m.reasoning,
                }
                for path, m in result.llm_matched.items()
            },
            "unmatched": result.unmatched,
            "execution_time_ms": round(elapsed_ms, 1),
        }

    if args.output:
        json_str = json.dumps(output, indent=2)
        Path(args.output).write_text(json_str)
        print(f"Results written to {args.output}", file=sys.stderr)

    if args.output_env:
        app_id = output.get("app_id") or ""
        Path(args.output_env).write_text(f"CONTRAST_APP_ID={app_id}\n")
        print(f"Env written to {args.output_env}", file=sys.stderr)

    # Auto-export to GitHub Actions when a match is found
    github_env = os.environ.get("GITHUB_ENV")
    if github_env and args.single and output.get("app_id"):
        with open(github_env, "a") as f:
            f.write(f"CONTRAST_APP_ID={output['app_id']}\n")
        print(f"Exported CONTRAST_APP_ID to $GITHUB_ENV", file=sys.stderr)


if __name__ == "__main__":
    main()
