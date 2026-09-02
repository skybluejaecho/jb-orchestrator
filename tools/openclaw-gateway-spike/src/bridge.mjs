import process from "node:process";

import { GatewayRunCoordinator } from "./gateway-runner.mjs";
import { connectGateway } from "./live-client.mjs";

const MAX_REQUEST_BYTES = 1024 * 1024;

async function readRequest() {
  const chunks = [];
  let size = 0;
  for await (const chunk of process.stdin) {
    size += chunk.length;
    if (size > MAX_REQUEST_BYTES) {
      throw new Error("bridge request exceeds 1 MiB");
    }
    chunks.push(chunk);
  }
  const raw = Buffer.concat(chunks).toString("utf8");
  if (!raw.trim()) {
    throw new Error("bridge request is empty");
  }
  return JSON.parse(raw);
}

async function main() {
  const request = await readRequest();
  const client = await connectGateway();
  const coordinator = new GatewayRunCoordinator(client);
  try {
    switch (request.action) {
      case "start":
        return await coordinator.start(request.input ?? {});
      case "wait":
        return await coordinator.wait(request.runId, request.timeoutMs);
      case "cancel":
        return await coordinator.cancel(request.runId);
      case "inspect":
        return await coordinator.inspect();
      default:
        throw new Error(`unsupported bridge action: ${request.action ?? "<missing>"}`);
    }
  } finally {
    await client.stopAndWait({ timeoutMs: 2_000 });
  }
}

main()
  .then((result) => console.log(JSON.stringify(result)))
  .catch((error) => {
    console.error(error instanceof Error ? error.message : String(error));
    process.exitCode = 1;
  });
