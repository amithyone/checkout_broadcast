/**
 * Checkout Broadcast Web SDK (browser bundle)
 * Mirrors sdk/typescript/src for environments without a build step.
 */

const MAX_AGE_MS = 600_000;
const globalListeners = [];

export class RoleNotAllowedError extends Error {
  constructor(message) {
    super(message);
    this.name = "RoleNotAllowedError";
  }
}

export class VerificationError extends Error {
  constructor(message) {
    super(message);
    this.name = "VerificationError";
  }
}

function sortKeys(value) {
  if (Array.isArray(value)) return value.map(sortKeys);
  if (value !== null && typeof value === "object") {
    return Object.keys(value)
      .sort()
      .reduce((acc, key) => {
        acc[key] = sortKeys(value[key]);
        return acc;
      }, {});
  }
  return value;
}

export async function hashBankName(bankName) {
  const normalized = bankName.trim().toLowerCase();
  const enc = new TextEncoder();
  const digest = await crypto.subtle.digest("SHA-256", enc.encode(normalized));
  const hex = [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
  return `sha256:${hex}`;
}

export async function signPayload(payload, signingKey) {
  const canonical = JSON.stringify(sortKeys(payload));
  const enc = new TextEncoder();
  const key = await crypto.subtle.importKey(
    "raw",
    enc.encode(signingKey),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const sig = await crypto.subtle.sign("HMAC", key, enc.encode(canonical));
  return btoa(String.fromCharCode(...new Uint8Array(sig)));
}

function buildPayload({ terminalId, amountNgn, itemCount, bankName, maskedAccountSuffix }) {
  return {
    protocol_version: 2.0,
    timestamp_ms: Date.now(),
    session_uuid_v4: crypto.randomUUID(),
    terminal_id: terminalId,
    transaction_details: {
      currency_code: "NGN",
      total_amount_ngn: amountNgn,
      item_count: itemCount,
    },
    account_info_public_display: {
      bank_name_hash: hashBankName(bankName),
      masked_account_suffix: maskedAccountSuffix,
    },
  };
}

class SimulatedTransport {
  constructor() {
    this.onPacket = null;
    this.sending = false;
  }
  startSend() {
    this.sending = true;
  }
  startReceive(onPacket) {
    this.onPacket = onPacket;
    globalListeners.push(onPacket);
  }
  broadcast(packet) {
    if (!this.sending) return;
    for (const listener of [...globalListeners]) listener(packet);
    this.onPacket?.(packet);
  }
  stop() {
    if (this.onPacket) {
      const idx = globalListeners.indexOf(this.onPacket);
      if (idx >= 0) globalListeners.splice(idx, 1);
    }
    this.onPacket = null;
    this.sending = false;
  }
}

export class CheckoutBroadcastAddon {
  constructor(config) {
    this.config = config;
    this.transport = new SimulatedTransport();
    this.started = false;
    this.seenSessions = new Set();
  }

  canSend() {
    return this.config.role === "send" || this.config.role === "both";
  }

  canReceive() {
    return this.config.role === "receive" || this.config.role === "both";
  }

  async start() {
    if (this.started) return;
    if (this.canSend()) this.transport.startSend();
    if (this.canReceive()) {
      this.onPacketHandler = (packet) => this.handlePacket(packet);
      if (this.config.transport !== "ble") {
        this.transport.startReceive(this.onPacketHandler);
      }
    }
    this.started = true;
  }

  async stop() {
    this.transport.stop();
    this.started = false;
  }

  async sendCheckout(data) {
    if (!this.canSend()) {
      throw new RoleNotAllowedError("sendCheckout is not allowed when role is 'receive'");
    }
    const { terminalId, signingKey } = this.config;
    if (!terminalId || !signingKey) {
      throw new RoleNotAllowedError("terminalId and signingKey are required for send/both roles");
    }
    const payload = buildPayload({
      terminalId,
      amountNgn: data.amountNgn,
      itemCount: data.itemCount ?? 1,
      bankName: this.config.bankName ?? "kuda",
      maskedAccountSuffix: this.config.maskedAccountSuffix ?? "***9876",
    });
    payload.account_info_public_display.bank_name_hash = await hashBankName(
      this.config.bankName ?? "kuda",
    );
    const packet = {
      payload,
      signature_alg: "HMAC-SHA256",
      signature: await signPayload(payload, signingKey),
    };
    if (!this.started) await this.start();
    this.transport.broadcast(packet);
    this.config.onSendComplete?.(payload.session_uuid_v4);
    return packet;
  }

  async requestBleDevice() {
    if (!navigator.bluetooth) {
      throw new Error("Web Bluetooth is not available.");
    }
    if (!this.started) throw new Error("Call start() first.");
    const SERVICE_UUID = "cbbc0001-0000-4000-8000-000000000001";
    const PACKET_CHAR_UUID = "cbbc0002-0000-4000-8000-000000000001";
    const device = await navigator.bluetooth.requestDevice({
      filters: [{ services: [SERVICE_UUID] }],
      optionalServices: [SERVICE_UUID],
    });
    const server = await device.gatt.connect();
    const service = await server.getPrimaryService(SERVICE_UUID);
    const characteristic = await service.getCharacteristic(PACKET_CHAR_UUID);
    const value = await characteristic.readValue();
    const text = new TextDecoder().decode(value.buffer);
    const packet = JSON.parse(text);
    await this.handlePacket(packet);
  }

  async handlePacket(packet) {
    try {
      const payment = await this.verifyLocallyAndWithBank(packet);
      this.config.onPaymentReceived?.(payment);
    } catch (error) {
      if (this.config.onError) this.config.onError(error);
      else throw error;
    }
  }

  async verifyLocallyAndWithBank(packet) {
    const { payload } = packet;
    if (Math.abs(Date.now() - payload.timestamp_ms) > MAX_AGE_MS) {
      throw new VerificationError("Packet timestamp is outside the 10-minute window");
    }
    if (this.seenSessions.has(payload.session_uuid_v4)) {
      throw new VerificationError("Session UUID already consumed (replay detected)");
    }
    this.seenSessions.add(payload.session_uuid_v4);

    const response = await fetch(`${this.config.bankApiUrl.replace(/\/$/, "")}/verify-broadcast`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(packet),
    });
    const body = await response.json();
    if (!response.ok || !body.valid) {
      throw new VerificationError(body.error ?? "Bank verification failed");
    }
    return {
      merchantName: body.merchant_name,
      amountNgn: body.amount_ngn,
      maskedAccountSuffix: body.masked_account_suffix,
      sessionUuid: body.session_uuid,
      terminalId: body.terminal_id,
    };
  }
}
