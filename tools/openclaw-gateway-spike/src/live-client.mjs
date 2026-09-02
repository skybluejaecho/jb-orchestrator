import { GatewayClient } from "@openclaw/gateway-client";
import {
  GATEWAY_CLIENT_MODES,
  GATEWAY_CLIENT_NAMES,
} from "@openclaw/gateway-protocol/client-info";
import {
  MIN_CLIENT_PROTOCOL_VERSION,
  PROTOCOL_VERSION,
} from "@openclaw/gateway-protocol/version";

const DEFAULT_GATEWAY_URL = "ws://127.0.0.1:18789";
const CONNECT_TIMEOUT_MS = 20_000;

function requiredCredential(env) {
  const token = env.OPENCLAW_GATEWAY_TOKEN?.trim();
  const password = env.OPENCLAW_GATEWAY_PASSWORD?.trim();
  if (!token && !password) {
    throw new Error(
      "OPENCLAW_GATEWAY_TOKEN or OPENCLAW_GATEWAY_PASSWORD is required for this spike",
    );
  }
  return { token: token || undefined, password: password || undefined };
}

export async function connectGateway(env = process.env) {
  const credential = requiredCredential(env);
  let resolveReady;
  let rejectReady;
  const ready = new Promise((resolve, reject) => {
    resolveReady = resolve;
    rejectReady = reject;
  });

  const client = new GatewayClient({
    url: env.OPENCLAW_GATEWAY_URL?.trim() || DEFAULT_GATEWAY_URL,
    ...credential,
    clientName: GATEWAY_CLIENT_NAMES.GATEWAY_CLIENT,
    clientDisplayName: "jb-orchestrator gateway spike",
    clientVersion: "0.0.0",
    platform: process.platform,
    mode: GATEWAY_CLIENT_MODES.BACKEND,
    role: "operator",
    scopes: ["operator.read", "operator.write"],
    minProtocol: MIN_CLIENT_PROTOCOL_VERSION,
    maxProtocol: PROTOCOL_VERSION,
    // This spike uses shared Gateway auth without persisting a device key or token.
    // The production adapter must provide host-owned device identity/token storage.
    deviceIdentity: null,
    onHelloOk: resolveReady,
    onConnectError: rejectReady,
  });

  client.start();
  const timeout = setTimeout(
    () => rejectReady(new Error(`Gateway connection timed out after ${CONNECT_TIMEOUT_MS} ms`)),
    CONNECT_TIMEOUT_MS,
  );
  try {
    await ready;
    return client;
  } catch (error) {
    await client.stopAndWait({ timeoutMs: 2_000 });
    throw error;
  } finally {
    clearTimeout(timeout);
  }
}
