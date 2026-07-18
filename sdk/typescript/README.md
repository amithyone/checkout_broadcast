# @checkout-broadcast/web

Web/Node SDK for receiving signed checkout broadcasts in banking apps.

```bash
npm install @checkout-broadcast/web
```

```typescript
import { CheckoutBroadcastAddon } from "@checkout-broadcast/web";

const addon = new CheckoutBroadcastAddon({
  role: "receive",
  bankApiUrl: "https://api.yourbank.ng/checkout",
  transport: "simulated",
  onPaymentReceived: (payment) => {
    console.log(`Pay ${payment.merchantName} — ₦${payment.amountNgn}`);
  },
});

await addon.start();
```

See [integration docs](https://github.com/checkout-broadcast/checkout-broadcast/tree/main/docs/banking-app-integration.md).
