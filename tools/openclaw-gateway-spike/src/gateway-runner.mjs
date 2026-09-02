import {
  validateAgentParams,
  validateAgentWaitParams,
  validateSessionsAbortParams,
} from "@openclaw/gateway-protocol";

export class GatewayContractError extends Error {
  constructor(message) {
    super(message);
    this.name = "GatewayContractError";
  }
}

function assertValid(validate, value, label) {
  if (!validate(value)) {
    throw new GatewayContractError(`${label} does not match OpenClaw protocol v4`);
  }
}

function requireRunId(value) {
  if (
    value === null ||
    typeof value !== "object" ||
    typeof value.runId !== "string" ||
    value.runId.length === 0
  ) {
    throw new GatewayContractError("agent response did not include a runId");
  }
  return value.runId;
}

export class GatewayRunCoordinator {
  constructor(rpc) {
    this.rpc = rpc;
  }

  async inspect() {
    const [health, agents, sessions] = await Promise.all([
      this.rpc.request("health"),
      this.rpc.request("agents.list", {}),
      this.rpc.request("sessions.list", { limit: 20, includeGlobal: false }),
    ]);
    return { health, agents, sessions };
  }

  async start({ message, sessionKey, idempotencyKey, agentId, cwd, timeoutSeconds }) {
    const params = {
      message,
      sessionKey,
      idempotencyKey,
      deliver: false,
      ...(agentId ? { agentId } : {}),
      ...(cwd ? { cwd } : {}),
      ...(timeoutSeconds === undefined ? {} : { timeout: timeoutSeconds }),
    };
    assertValid(validateAgentParams, params, "agent request");
    const accepted = await this.rpc.request("agent", params);
    return { runId: requireRunId(accepted), accepted };
  }

  async wait(runId, timeoutMs) {
    const params = { runId, ...(timeoutMs === undefined ? {} : { timeoutMs }) };
    assertValid(validateAgentWaitParams, params, "agent.wait request");
    return this.rpc.request("agent.wait", params, {
      timeoutMs: timeoutMs === undefined ? undefined : timeoutMs + 5_000,
    });
  }

  async cancel(runId) {
    const params = { runId };
    assertValid(validateSessionsAbortParams, params, "sessions.abort request");
    return this.rpc.request("sessions.abort", params);
  }

  async run(input) {
    const started = await this.start(input);
    const terminal = await this.wait(started.runId, input.waitTimeoutMs);
    return { ...started, terminal };
  }
}
