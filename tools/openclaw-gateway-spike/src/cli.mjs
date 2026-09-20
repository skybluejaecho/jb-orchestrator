import { randomUUID } from "node:crypto";
import process from "node:process";

import { GatewayRunCoordinator } from "./gateway-runner.mjs";
import { connectGateway } from "./live-client.mjs";

function parseOptions(args) {
  const options = new Map();
  for (let index = 0; index < args.length; index += 2) {
    const name = args[index];
    const value = args[index + 1];
    if (!name?.startsWith("--") || value === undefined) {
      throw new Error(`invalid option near ${name ?? "<end>"}`);
    }
    options.set(name.slice(2), value);
  }
  return options;
}

function required(options, name) {
  const value = options.get(name)?.trim();
  if (!value) {
    throw new Error(`--${name} is required`);
  }
  return value;
}

function positiveInteger(options, name, fallback) {
  const raw = options.get(name);
  if (raw === undefined) {
    return fallback;
  }
  const value = Number(raw);
  if (!Number.isSafeInteger(value) || value <= 0) {
    throw new Error(`--${name} must be a positive integer`);
  }
  return value;
}

async function main() {
  const [command = "inspect", ...args] = process.argv.slice(2);
  const options = parseOptions(args);
  const client = await connectGateway();
  const coordinator = new GatewayRunCoordinator(client);
  let activeRunId;
  let interrupted = false;

  const cancelActiveRun = async () => {
    if (activeRunId && !interrupted) {
      interrupted = true;
      await coordinator.cancel(activeRunId);
    }
  };
  process.once("SIGINT", cancelActiveRun);
  process.once("SIGTERM", cancelActiveRun);

  try {
    if (command === "inspect") {
      console.log(JSON.stringify(await coordinator.inspect(), null, 2));
      return;
    }
    if (command !== "run") {
      throw new Error(`unknown command: ${command}`);
    }

    const waitTimeoutMs = positiveInteger(options, "wait-timeout-ms", 120_000);
    const started = await coordinator.start({
      message: required(options, "message"),
      sessionKey: required(options, "session-key"),
      idempotencyKey: options.get("idempotency-key") || randomUUID(),
      agentId: options.get("agent-id"),
      cwd: options.get("cwd"),
      timeoutSeconds: positiveInteger(options, "run-timeout-seconds", 300),
    });
    activeRunId = started.runId;
    const terminal = await coordinator.wait(activeRunId, waitTimeoutMs);
    console.log(JSON.stringify({ ...started, terminal }, null, 2));
  } finally {
    process.removeListener("SIGINT", cancelActiveRun);
    process.removeListener("SIGTERM", cancelActiveRun);
    await client.stopAndWait({ timeoutMs: 2_000 });
  }
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exitCode = 1;
});
