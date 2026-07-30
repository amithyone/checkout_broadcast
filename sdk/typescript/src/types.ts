export type SignatureAlg = "HMAC-SHA256" | "ed25519" | "ED25519";
export type TransportKind = "ble" | "simulated";

export interface TransactionDetails {
  currency_code: "NGN";
  total_amount_ngn: number;
  item_count: number;
}

export interface AccountInfoPublicDisplay {
  bank_name_hash: string;
  masked_account_suffix: string;
}

export interface Payload {
  protocol_version: 2.0;
  timestamp_ms: number;
  session_uuid_v4: string;
  terminal_id: string;
  transaction_details: TransactionDetails;
  account_info_public_display: AccountInfoPublicDisplay;
}

export interface SignedPacket {
  payload: Payload;
  signature_alg: SignatureAlg;
  signature: string;
}

export interface CheckoutData {
  amountNgn: number;
  itemCount?: number;
}

export interface VerifiedPayment {
  merchantName: string;
  amountNgn: number;
  maskedAccountSuffix: string;
  sessionUuid: string;
  terminalId: string;
  sessionStatus?: "open" | "paid" | "cancelled";
}

export interface CheckoutBroadcastConfig {
  role: BroadcastRole;
  bankApiUrl: string;
  terminalId?: string;
  signingKey?: string;
  merchantName?: string;
  bankName?: string;
  maskedAccountSuffix?: string;
  signatureAlg?: SignatureAlg;
  transport?: TransportKind;
  onPaymentReceived?: (payment: VerifiedPayment) => void;
  onSendComplete?: (sessionId: string) => void;
  onError?: (error: Error) => void;
}

export class RoleNotAllowedError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "RoleNotAllowedError";
  }
}

export class VerificationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "VerificationError";
  }
}

export const MAX_AGE_MS = 600_000;
