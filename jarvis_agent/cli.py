"""CLI entrypoint for jarvis_agent."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from jarvis_agent.client import JarvisAgentClient
from jarvis_agent.confirmation import CliConfirmationHandler

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("jarvis_agent")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Jarvis Local Agent Client")
    parser.add_argument(
        "--url",
        default="ws://localhost:8000/ws/jarvis",
        help="WebSocket URL of the Jarvis server",
    )
    parser.add_argument(
        "--session-id",
        required=True,
        help="Session ID to bind this agent to",
    )
    parser.add_argument(
        "--token",
        required=True,
        help="JWT Access Token for authentication",
    )
    parser.add_argument(
        "--refresh-token",
        default=None,
        help="JWT Refresh Token for automatic token renewal",
    )
    parser.add_argument(
        "--device-id",
        default=None,
        help="Explicit device identifier (defaults to persistent device ID in ~/.jarvis/device_id)",
    )
    parser.add_argument(
        "--i-understand-this-disables-safety-prompts",
        action="store_true",
        default=False,
        help="DANGEROUS: Auto-approve all high-risk actions without interactive confirmation",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    if args.i_understand_this_disables_safety_prompts:
        from jarvis_agent.confirmation import AutoApproveConfirmationHandler

        logger.warning(
            "⚠️ DANGER: Safety confirmation prompts disabled via explicit flag! "
            "All destructive actions will execute automatically."
        )
        handler = AutoApproveConfirmationHandler()
    else:
        handler = CliConfirmationHandler()

    client = JarvisAgentClient(
        server_ws_url=args.url,
        session_id=args.session_id,
        access_token=args.token,
        refresh_token=args.refresh_token,
        device_id=args.device_id,
        confirmation_handler=handler,
    )
    logger.info("Connecting to %s for session %s...", args.url, args.session_id)
    # Print connection URL for debugging
    ws_url = client.build_ws_url()
    logger.info("Ready. Connect target: %s", ws_url[:40] + "...")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
