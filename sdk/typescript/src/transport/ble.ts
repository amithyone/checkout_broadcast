import { SERVICE_UUID, PACKET_CHAR_UUID } from "./bleConstants.js";
import type { SignedPacket } from "../types.js";

type PacketListener = (packet: SignedPacket) => void;

export interface BroadcastTransport {
  startSend(): void;
  startReceive(onPacket: PacketListener): void;
  broadcast(packet: SignedPacket): void;
  stop(): void;
}

export class BleTransport implements BroadcastTransport {
  private onPacket: PacketListener | null = null;
  private seenSessions = new Set<string>();

  startSend(): void {
    throw new Error(
      "Web Bluetooth cannot act as a BLE peripheral. Use Windows POS SDK for send, or transport='simulated'.",
    );
  }

  startReceive(onPacket: PacketListener): void {
    if (!navigator.bluetooth) {
      throw new Error("Web Bluetooth is not available in this browser.");
    }
    this.onPacket = onPacket;
  }

  async requestDeviceAndReceive(): Promise<void> {
    if (!navigator.bluetooth || !this.onPacket) {
      throw new Error("Call startReceive() first.");
    }
    const device = await navigator.bluetooth.requestDevice({
      filters: [{ services: [SERVICE_UUID] }],
      optionalServices: [SERVICE_UUID],
    });
    const server = await device.gatt!.connect();
    const service = await server.getPrimaryService(SERVICE_UUID);
    const characteristic = await service.getCharacteristic(PACKET_CHAR_UUID);
    const value = await characteristic.readValue();
    const text = new TextDecoder().decode(value.buffer);
    const packet = JSON.parse(text) as SignedPacket;
    const session = packet.payload.session_uuid_v4;
    if (this.seenSessions.has(session)) return;
    this.seenSessions.add(session);
    this.onPacket(packet);
  }

  broadcast(): void {
    throw new Error("Web cannot broadcast checkout packets via BLE.");
  }

  stop(): void {
    this.onPacket = null;
  }
}
