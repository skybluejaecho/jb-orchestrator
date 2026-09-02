import assert from "node:assert/strict";
import test from "node:test";

import { selectGatewayConnectAuth } from "@openclaw/gateway-client/browser";

import { connectionAuth } from "../src/live-client.mjs";

test("uses the shared token only as first-connect bootstrap auth", () => {
  const auth = connectionAuth({ OPENCLAW_GATEWAY_TOKEN: " bootstrap " }, null);

  assert.deepEqual(auth, {
    bootstrapToken: "bootstrap",
    password: undefined,
    preferBootstrapToken: true,
  });
});

test("official auth selection prefers a stored device token after pairing", () => {
  const stored = { token: "device-token", scopes: ["operator.read", "operator.write"] };
  const auth = connectionAuth({ OPENCLAW_GATEWAY_TOKEN: "bootstrap" }, stored);
  const selected = selectGatewayConnectAuth({
    ...auth,
    storedToken: stored.token,
    storedScopes: stored.scopes,
  });

  assert.equal(auth.preferBootstrapToken, false);
  assert.equal(selected.resolvedDeviceToken, "device-token");
  assert.equal(selected.authBootstrapToken, undefined);
});

test("allows steady-state connection with only a stored device token", () => {
  const auth = connectionAuth({}, { token: "device-token", scopes: ["operator.read"] });

  assert.deepEqual(auth, {
    bootstrapToken: undefined,
    password: undefined,
    preferBootstrapToken: false,
  });
});

test("rejects connection without bootstrap or stored credentials", () => {
  assert.throws(() => connectionAuth({}, null), /stored device token/);
});
