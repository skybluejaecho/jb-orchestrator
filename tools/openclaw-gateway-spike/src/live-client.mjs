import { GatewayClient } from "@openclaw/gateway-client";
import {
  GATEWAY_CLIENT_MODES,
  GATEWAY_CLIENT_NAMES,
} from "@openclaw/gateway-protocol/client-info";
import {
  MIN_CLIENT_PROTOCOL_VERSION,
  PROTOCOL_VERSION,
} from "@openclaw/gateway-protocol/version";
import { resolve } from "node:path";

import {
  DeviceStateStore,
  publicKeyRawBase64UrlFromPem,
  signDevicePayload,
} from "./device-state.mjs";

const DEFAULT_GATEWAY_URL = "ws://127.0.0.1:18789";
const CONNECT_TIMEOUT_MS = 20_000;

export function connectionAuth(env, storedToken) {
  const bootstrapToken = env.OPENCLAW_GATEWAY_TOKEN?.trim();
  const password = env.OPENCLAW_GATEWAY_PASSWORD?.trim();
  if (!storedToken && !bootstrapToken && !password) {
    throw new Error(
      "a stored device token, OPENCLAW_GATEWAY_TOKEN, or OPENCLAW_GATEWAY_PASSWORD is required",
    );
  }
  return {
    bootstrapToken: bootstrapToken || undefined,
    password: storedToken ? undefined : password || undefined,
    preferBootstrapToken: Boolean(bootstrapToken && !storedToken),
  };
}

export async function connectGateway(env = process.env) {
  const state = new DeviceStateStore(
    resolve(env.JB_OPENCLAW_DEVICE_STATE_DIR?.trim() || ".jb-orchestrator/openclaw-device"),
  );
  const identity = state.loadOrCreateIdentity();
  const storedToken = state.loadToken({ deviceId: identity.deviceId, role: "operator" });
  const auth = connectionAuth(env, storedToken);
  let resolveReady;
  let rejectReady;
  const ready = new Promise((resolve, reject) => {
    resolveReady = resolve;
    rejectReady = reject;
  });

  const client = new GatewayClient({
    url: env.OPENCLAW_GATEWAY_URL?.trim() || DEFAULT_GATEWAY_URL,
    ...auth,
    clientName: GATEWAY_CLIENT_NAMES.GATEWAY_CLIENT,
    clientDisplayName: "jb-orchestrator gateway spike",
    clientVersion: "0.0.0",
    platform: process.platform,
    mode: GATEWAY_CLIENT_MODES.BACKEND,
    role: "operator",
    scopes: ["operator.read", "operator.write"],
    minProtocol: MIN_CLIENT_PROTOCOL_VERSION,
    maxProtocol: PROTOCOL_VERSION,
    tlsFingerprint: env.OPENCLAW_GATEWAY_TLS_FINGERPRINT?.trim() || undefined,
    deviceIdentity: identity,
    hostDeps: {
      signDevicePayload,
      publicKeyRawBase64UrlFromPem,
      loadDeviceAuthToken: (params) => state.loadToken(params),
      storeDeviceAuthToken: (params) => state.storeToken(params),
      clearDeviceAuthToken: (params) => state.clearToken(params),
      redactForLog: () => "[redacted Gateway client error]",
    },
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
