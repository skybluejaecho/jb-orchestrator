import assert from "node:assert/strict";
import test from "node:test";

import { selectGatewayConnectAuth } from "@openclaw/gateway-client/browser";

import { connectionAuth } from "../src/live-client.mjs";

test("sends the shared Gateway token through auth.token on first connect", () => {
  const auth = connectionAuth({ OPENCLAW_GATEWAY_TOKEN: " gateway-token " }, null);
  const selected = selectGatewayConnectAuth(auth);

  assert.deepEqual(auth, {
    token: "gateway-token",
    password: undefined,
  });
  assert.equal(selected.authToken, "gateway-token");
  assert.equal(selected.authBootstrapToken, undefined);
});

test("official auth selection prefers a stored device token after pairing", () => {
  const stored = { token: "device-token", scopes: ["operator.read", "operator.write"] };
  const auth = connectionAuth({ OPENCLAW_GATEWAY_TOKEN: "gateway-token" }, stored);
  const selected = selectGatewayConnectAuth({
    ...auth,
    storedToken: stored.token,
    storedScopes: stored.scopes,
  });

  assert.equal(auth.token, undefined);
  assert.equal(selected.resolvedDeviceToken, "device-token");
  assert.equal(selected.authBootstrapToken, undefined);
});

test("allows steady-state connection with only a stored device token", () => {
  const auth = connectionAuth({}, { token: "device-token", scopes: ["operator.read"] });

  assert.deepEqual(auth, {
    token: undefined,
    password: undefined,
  });
});

test("rejects connection without shared or stored credentials", () => {
  assert.throws(() => connectionAuth({}, null), /stored device token/);
});
