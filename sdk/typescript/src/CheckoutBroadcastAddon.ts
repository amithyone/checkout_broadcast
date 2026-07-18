import { createSignedPacket, isTimestampValid } from "./protocol.js";
import { signPayload } from "./signing.js";
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
  private seenSessions = new Set<string>();
  private bleTransport: import("./transport/ble.js").BleTransport | null = null;

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

    const packet = createSignedPacket(
      data,
      terminalId,
      signingKey,
      this.config.bankName ?? "kuda",
      this.config.maskedAccountSuffix ?? "***9876",
      signPayload,
    );

    if (!this.started) await this.start();
    this.transport.broadcast(packet);
    this.config.onSendComplete?.(packet.payload.session_uuid_v4);
    return packet;
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
    if (!isTimestampValid(payload.timestamp_ms)) {
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
