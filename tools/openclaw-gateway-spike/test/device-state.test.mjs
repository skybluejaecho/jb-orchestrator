import assert from "node:assert/strict";
import { createPublicKey, verify } from "node:crypto";
import { mkdtempSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import {
  DeviceStateStore,
  deriveDeviceId,
  publicKeyRawBase64UrlFromPem,
  signDevicePayload,
} from "../src/device-state.mjs";

function stateDirectory() {
  return mkdtempSync(join(tmpdir(), "jb-openclaw-device-"));
}

test("creates one stable valid Ed25519 device identity", () => {
  const directory = stateDirectory();
  const first = new DeviceStateStore(directory).loadOrCreateIdentity();
  const second = new DeviceStateStore(directory).loadOrCreateIdentity();

  assert.deepEqual(second, first);
  assert.equal(deriveDeviceId(first.publicKeyPem), first.deviceId);
  assert.equal(Buffer.from(publicKeyRawBase64UrlFromPem(first.publicKeyPem), "base64url").length, 32);
  const signature = signDevicePayload(first.privateKeyPem, "challenge");
  assert.equal(
    verify(
      null,
      Buffer.from("challenge", "utf8"),
      createPublicKey(first.publicKeyPem),
      Buffer.from(signature, "base64url"),
    ),
    true,
  );
  if (process.platform !== "win32") {
    assert.equal(statSync(join(directory, "device-identity.json")).mode & 0o777, 0o600);
  }
});

test("stores, reloads, rotates, and clears scoped device tokens", () => {
  const directory = stateDirectory();
  const state = new DeviceStateStore(directory);
  const identity = state.loadOrCreateIdentity();
  const key = { deviceId: identity.deviceId, role: "operator" };

  assert.equal(state.loadToken(key), null);
  state.storeToken({ ...key, token: "token-one", scopes: ["operator.read"] });
  assert.deepEqual(new DeviceStateStore(directory).loadToken(key), {
    token: "token-one",
    scopes: ["operator.read"],
  });
  state.storeToken({ ...key, token: "token-two", scopes: ["operator.read", "operator.write"] });
  assert.equal(state.loadToken(key).token, "token-two");
  assert.doesNotMatch(readFileSync(join(directory, "device-tokens.json"), "utf8"), /privateKey/);
  state.clearToken(key);
  assert.equal(state.loadToken(key), null);
});

test("rejects a tampered persisted device id", () => {
  const directory = stateDirectory();
  const state = new DeviceStateStore(directory);
  state.loadOrCreateIdentity();
  const path = join(directory, "device-identity.json");
  const stored = JSON.parse(readFileSync(path, "utf8"));
  stored.deviceId = "tampered";
  writeFileSync(path, JSON.stringify(stored));

  assert.throws(() => new DeviceStateStore(directory).loadOrCreateIdentity(), /identity is invalid/);
});
