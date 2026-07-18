import { BleTransport } from "./ble.js";
import type { SignedPacket } from "./types.js";

type PacketListener = (packet: SignedPacket) => void;

const globalListeners: PacketListener[] = [];

export interface BroadcastTransport {
  startSend(): void;
  startReceive(onPacket: PacketListener): void;
  broadcast(packet: SignedPacket): void;
  stop(): void;
}

export class SimulatedTransport implements BroadcastTransport {
  private onPacket: PacketListener | null = null;
  private sending = false;

  startSend(): void {
    this.sending = true;
  }

  startReceive(onPacket: PacketListener): void {
    this.onPacket = onPacket;
    globalListeners.push(onPacket);
  }

  broadcast(packet: SignedPacket): void {
    if (!this.sending) return;
    for (const listener of [...globalListeners]) {
      listener(packet);
    }
    this.onPacket?.(packet);
  }

  stop(): void {
    if (this.onPacket) {
      const idx = globalListeners.indexOf(this.onPacket);
      if (idx >= 0) globalListeners.splice(idx, 1);
    }
    this.onPacket = null;
    this.sending = false;
  }
}

export class BleTransportStub extends BleTransport {}

export function createTransport(kind: "ble" | "simulated"): BroadcastTransport {
  return kind === "ble" ? new BleTransport() : new SimulatedTransport();
}
