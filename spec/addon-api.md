# Checkout Broadcast — Unified Addon API

Drop-in SDK for Android, iOS, Web, and Windows host apps.

**Integration guides:** [POS apps](../docs/pos-app-integration.md) · [Banking apps](../docs/banking-app-integration.md) · [Overview](../docs/README.md)

## Roles

| Role | Send | Receive | Who may use it |
|------|------|---------|----------------|
| `send` | yes | no | POS terminal apps only |
| `receive` | no | yes | Banking / wallet apps |
| `both` | yes | yes | POS apps that also listen (e.g. waiter phone). **Not** retail banking APKs |

Consumer bank apps must ship `receive` only. Do not advertise checkout from Kuda / GTBank / OPay-style customer apps.

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
  signatureAlg?: "HMAC-SHA256" | "ed25519" | "ED25519";
  transport?: "ble" | "simulated"; // default: simulated
  onPaymentReceived?: (payment: VerifiedPayment) => void;
  onSendComplete?: (sessionId: string) => void;
  onError?: (error: BroadcastError) => void;
}
```

## Platform Defaults (overridable)

- Windows POS (Cheko) → `send`
- Android / iOS **POS / handheld till** → `send`
- Android / iOS **wallet / retail banking** → `receive` only
- Web → `receive`

## Methods

- `start()` — enable transport per role
- `stop()` — tear down transport
- `sendCheckout({ amountNgn, itemCount })` — send | both only

## Errors

- `RoleNotAllowedError` — e.g. sendCheckout on receive-only config
- `VerificationError` — signature, timestamp, or replay failure
- `TransportError` — BLE unavailable
