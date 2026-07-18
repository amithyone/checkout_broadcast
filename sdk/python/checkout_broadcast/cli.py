import json
import os
import sys
import threading
import time
from pathlib import Path

import click
import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "sdk" / "python"))

from checkout_broadcast.addon import CheckoutBroadcastAddon, CheckoutBroadcastConfig
from checkout_broadcast.protocol import CheckoutData

DEFAULT_TERMINAL = os.getenv("CHECKOUT_TERMINAL_ID", "POS-LAG-001")
DEFAULT_KEY = os.getenv("CHECKOUT_SIGNING_KEY", "")
BANK_URL = os.getenv("CHECKOUT_BANK_API_URL", "http://127.0.0.1:8090")
ADMIN_KEY = os.getenv("CHECKOUT_BANK_ADMIN_KEY", "change-me-before-production")


def _admin_headers() -> dict[str, str]:
    return {"X-Admin-Key": ADMIN_KEY}


@click.group()
def cli() -> None:
    """Checkout Broadcast — cross-platform payment broadcast SDK CLI."""


@cli.command("register-terminal")
@click.option("--id", "terminal_id", default=DEFAULT_TERMINAL)
@click.option("--key", "signing_key", default=None, help="Defaults to CHECKOUT_SIGNING_KEY env var")
@click.option("--merchant", default="ABC Enterprises")
@click.option("--bank", default="kuda")
@click.option("--suffix", default="***9876")
@click.option("--account", default=None, help="10-digit NUBAN")
@click.option("--bank-code", default=None, help="Recipient bank code")
@click.option("--bank-url", default=BANK_URL)
def register_terminal(
    terminal_id: str,
    signing_key: str | None,
    merchant: str,
    bank: str,
    suffix: str,
    account: str | None,
    bank_code: str | None,
    bank_url: str,
) -> None:
    """Register a terminal with the reference bank API (requires X-Admin-Key)."""
    key = signing_key or DEFAULT_KEY
    if not key or len(key) < 16:
        raise click.ClickException(
            "Set --key or CHECKOUT_SIGNING_KEY (min 16 characters) before registering."
        )
    body = {
        "terminal_id": terminal_id,
        "signing_key": key,
        "merchant_name": merchant,
        "bank_name": bank,
        "masked_account_suffix": suffix,
        "account_number": account,
        "recipient_bank_code": bank_code,
    }
    response = httpx.post(
        f"{bank_url.rstrip('/')}/terminals/register",
        json=body,
        headers=_admin_headers(),
        timeout=10,
    )
    response.raise_for_status()
    click.echo(json.dumps(response.json(), indent=2))


@cli.command("run-bank")
@click.option("--host", default=None, help="Overrides CHECKOUT_BANK_HOST")
@click.option("--port", default=None, type=int, help="Overrides CHECKOUT_BANK_PORT")
def run_bank(host: str | None, port: int | None) -> None:
    """Start the reference bank verification API."""
    import uvicorn
    from bank_api.config import Settings

    s = Settings.from_env()
    uvicorn.run(
        "bank_api.server:app",
        host=host or s.listen_host,
        port=port or s.port,
        reload=False,
    )


@cli.command("demo-send")
@click.option("--role", default="send", type=click.Choice(["send", "receive", "both"]))
@click.option("--terminal-id", default=DEFAULT_TERMINAL)
@click.option("--key", "signing_key", default=None)
@click.option("--amount", default=2500, type=int)
@click.option("--items", default=3, type=int)
@click.option("--bank-url", default=BANK_URL)
@click.option("--transport", default="simulated", type=click.Choice(["simulated", "ble"]))
def demo_send(
    role: str,
    terminal_id: str,
    signing_key: str | None,
    amount: int,
    items: int,
    bank_url: str,
    transport: str,
) -> None:
    """Send a signed checkout broadcast."""
    key = signing_key or DEFAULT_KEY
    if role in ("send", "both") and (not key or len(key) < 16):
        raise click.ClickException("Set --key or CHECKOUT_SIGNING_KEY for send role.")

    received: list[str] = []

    def on_payment(payment) -> None:
        msg = (
            f"Pay {payment.merchant_name} — "
            f"₦{payment.amount_ngn:,} — {payment.masked_account_suffix}"
        )
        received.append(msg)
        click.echo(f"[receiver] {msg}")

    sender = CheckoutBroadcastAddon(
        CheckoutBroadcastConfig(
            role=role,
            terminal_id=terminal_id,
            signing_key=key,
            bank_api_url=bank_url,
            transport=transport,
        )
    )
    receiver = CheckoutBroadcastAddon(
        CheckoutBroadcastConfig(
            role="receive" if role == "send" else role,
            bank_api_url=bank_url,
            transport=transport,
            on_payment_received=on_payment,
        )
    )

    if transport == "simulated":
        receiver.start()
    sender.start()
    packet = sender.send_checkout(CheckoutData(amount_ngn=amount, item_count=items))
    time.sleep(0.3 if transport == "simulated" else 2.0)

    click.echo(f"Sent session {packet.payload.session_uuid_v4} for ₦{amount:,} (transport={transport})")
    if role == "send" and received:
        click.echo("End-to-end demo succeeded.")
    elif role == "send" and transport == "ble":
        click.echo("BLE packet published. Run demo-receive on another device.")
    elif role == "send":
        click.echo("Packet sent. Start demo-receive to complete the flow.")


@cli.command("demo-receive")
@click.option("--bank-url", default=BANK_URL)
@click.option("--transport", default="simulated", type=click.Choice(["simulated", "ble"]))
@click.option("--timeout", default=30, type=int)
def demo_receive(bank_url: str, transport: str, timeout: int) -> None:
    """Listen for checkout broadcasts."""
    done = threading.Event()

    def on_payment(payment) -> None:
        click.echo(
            f"Pay {payment.merchant_name} — "
            f"₦{payment.amount_ngn:,} — {payment.masked_account_suffix}"
        )
        done.set()

    receiver = CheckoutBroadcastAddon(
        CheckoutBroadcastConfig(
            role="receive",
            bank_api_url=bank_url,
            transport=transport,
            on_payment_received=on_payment,
        )
    )
    receiver.start()
    click.echo(f"Listening (transport={transport}, timeout={timeout}s)...")
    done.wait(timeout=timeout)
    receiver.stop()
    if not done.is_set():
        click.echo("No payment received within timeout.")


@cli.command("demo-replay-attack")
@click.option("--terminal-id", default=DEFAULT_TERMINAL)
@click.option("--key", "signing_key", default=None)
@click.option("--bank-url", default=BANK_URL)
def demo_replay_attack(terminal_id: str, signing_key: str | None, bank_url: str) -> None:
    """Replay the same packet twice — second attempt should fail."""
    key = signing_key or DEFAULT_KEY
    if not key:
        raise click.ClickException("Set --key or CHECKOUT_SIGNING_KEY")

    sender = CheckoutBroadcastAddon(
        CheckoutBroadcastConfig(
            role="send",
            terminal_id=terminal_id,
            signing_key=key,
            bank_api_url=bank_url,
            transport="simulated",
        )
    )
    sender.start()
    packet = sender.send_checkout(CheckoutData(amount_ngn=2500, item_count=3))
    body = packet.model_dump()

    first = httpx.post(f"{bank_url.rstrip('/')}/verify-broadcast", json=body, timeout=10)
    second = httpx.post(f"{bank_url.rstrip('/')}/verify-broadcast", json=body, timeout=10)

    click.echo(f"First verify:  {first.json()}")
    click.echo(f"Second verify: {second.json()}")
    if not second.json().get("valid"):
        click.echo("Replay attack correctly rejected.")


if __name__ == "__main__":
    cli()
