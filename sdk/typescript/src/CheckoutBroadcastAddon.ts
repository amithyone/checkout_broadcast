import { createSignedPacket, isTimestampValid, parseTimestampMs } from "./protocol.js";
import { createTransport } from "./transport/simulated.js";
import type {
  CheckoutBroadcastConfig,
  CheckoutData,
  SignedPacket,
  VerifiedPayment,
} from "./types.js";
import { RoleNotAllowedError, VerificationError } from "./types.js";

export class CheckoutBroadcastAddon {
  private transport = createTransport(this.config.transport ?? "simulated");
  private started = false;
  private bleTransport: import("./transport/ble.js").BleTransport | null = null;
  private activeCheckout: { sessionUuidV4: string; amountNgn: number; itemCount: number } | null = null;

  constructor(private config: CheckoutBroadcastConfig) {
    if (config.transport === "ble") {
      this.bleTransport = this.transport as import("./transport/ble.js").BleTransport;
    }
  }

  async start(): Promise<void> {
    if (this.started) return;
    if (this.canSend()) this.transport.startSend();
    if (this.canReceive()) this.transport.startReceive((packet) => this.handlePacket(packet));
    this.started = true;
  }

  async stop(): Promise<void> {
    this.transport.stop();
    this.started = false;
  }

  async sendCheckout(data: CheckoutData): Promise<SignedPacket> {
    if (!this.canSend()) {
      throw new RoleNotAllowedError("sendCheckout is not allowed when role is 'receive'");
    }
    const terminalId = this.config.terminalId;
    const signingKey = this.config.signingKey;
    if (!terminalId || !signingKey) {
      throw new RoleNotAllowedError("terminalId and signingKey are required for send/both roles");
    }

    const itemCount = data.itemCount ?? 1;
    const reuseSession =
      this.activeCheckout &&
      this.activeCheckout.amountNgn === data.amountNgn &&
      this.activeCheckout.itemCount === itemCount
        ? this.activeCheckout.sessionUuidV4
        : undefined;

    const packet = createSignedPacket(
      data,
      terminalId,
      signingKey,
      this.config.bankName ?? "kuda",
      this.config.maskedAccountSuffix ?? "***9876",
      this.config.signatureAlg ?? "HMAC-SHA256",
      reuseSession,
    );

    if (!reuseSession) {
      this.activeCheckout = {
        sessionUuidV4: packet.payload.session_uuid_v4,
        amountNgn: data.amountNgn,
        itemCount,
      };
    }

    if (!this.started) await this.start();
    this.transport.broadcast(packet);
    this.config.onSendComplete?.(packet.payload.session_uuid_v4);
    return packet;
  }

  /** Re-sign and broadcast the active checkout (same session UUID, fresh timestamp). */
  async refreshCheckout(): Promise<SignedPacket | null> {
    if (!this.activeCheckout) {
      return null;
    }
    return this.sendCheckout({
      amountNgn: this.activeCheckout.amountNgn,
      itemCount: this.activeCheckout.itemCount,
    });
  }

  async cancelCheckout(): Promise<void> {
    if (!this.activeCheckout || !this.config.terminalId) {
      this.activeCheckout = null;
      return;
    }
    const sessionUuid = this.activeCheckout.sessionUuidV4;
    const terminalId = this.config.terminalId;
    this.activeCheckout = null;
    try {
      await fetch(`${this.config.bankApiUrl.replace(/\/$/, "")}/sessions/cancel`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_uuid_v4: sessionUuid,
          terminal_id: terminalId,
        }),
      });
    } catch {
      // Best-effort — POS UI should still close the payment screen.
    }
  }

  private canSend(): boolean {
    return this.config.role === "send" || this.config.role === "both";
  }

  private canReceive(): boolean {
    return this.config.role === "receive" || this.config.role === "both";
  }

  private async handlePacket(packet: SignedPacket): Promise<void> {
    try {
      const payment = await this.verifyLocallyAndWithBank(packet);
      this.config.onPaymentReceived?.(payment);
    } catch (error) {
      const err = error instanceof Error ? error : new Error(String(error));
      if (this.config.onError) this.config.onError(err);
      else throw err;
    }
  }

  private async verifyLocallyAndWithBank(packet: SignedPacket): Promise<VerifiedPayment> {
    const { payload } = packet;
    const timestampMs = parseTimestampMs(payload as unknown as Record<string, unknown>);
    if (timestampMs === null) {
      throw new VerificationError("Missing timestamp_ms in payload");
    }
    if (!isTimestampValid(timestampMs)) {
      throw new VerificationError("Packet timestamp is outside the 10-minute window");
    }

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
      sessionStatus: body.session_status,
    };
  }
  async requestBleDevice(): Promise<void> {
    if (!this.bleTransport) {
      throw new Error("requestBleDevice requires transport='ble'");
    }
    await this.bleTransport.requestDeviceAndReceive();
  }
}

export * from "./types.js";
export * from "./signing.js";
export * from "./protocol.js";
