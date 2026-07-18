# Checkout Broadcast — Unified Addon API

Drop-in SDK for Android, iOS, Web, and Windows host apps.

**Integration guides:** [POS apps](../docs/pos-app-integration.md) · [Banking apps](../docs/banking-app-integration.md) · [Overview](../docs/README.md)

## Roles

| Role | Send | Receive |
|------|------|---------|
| `send` | yes | no |
| `receive` | no | yes |
| `both` | yes | yes |

## Config

```typescript
interface CheckoutBroadcastConfig {
  role: "send" | "receive" | "both";
  terminalId?: string;       // required for send | both
  signingKey?: string;       // required for send | both
  merchantName?: string;     // optional display hint for sender
  bankName?: string;         // used to compute bank_name_hash on send
  maskedAccountSuffix?: string; // e.g. "***9876"
  bankApiUrl: string;
  transport?: "ble" | "simulated"; // default: simulated
  onPaymentReceived?: (payment: VerifiedPayment) => void;
  onSendComplete?: (sessionId: string) => void;
  onError?: (error: BroadcastError) => void;
}
```

## Platform Defaults (overridable)

- Windows → `send`
- Android / iOS → `receive`
- Web → `receive`

## Methods

- `start()` — enable transport per role
- `stop()` — tear down transport
- `sendCheckout({ amountNgn, itemCount })` — send | both only

## Errors

- `RoleNotAllowedError` — e.g. sendCheckout on receive-only config
- `VerificationError` — signature, timestamp, or replay failure
- `TransportError` — BLE unavailable
