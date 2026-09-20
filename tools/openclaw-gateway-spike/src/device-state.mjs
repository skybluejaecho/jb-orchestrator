import {
  createHash,
  createPrivateKey,
  createPublicKey,
  generateKeyPairSync,
  randomUUID,
  sign,
} from "node:crypto";
import {
  chmodSync,
  mkdirSync,
  readFileSync,
  renameSync,
  unlinkSync,
  writeFileSync,
} from "node:fs";
import { join, resolve } from "node:path";

const IDENTITY_FILE = "device-identity.json";
const TOKENS_FILE = "device-tokens.json";

function readJson(path, fallback) {
  try {
    return JSON.parse(readFileSync(path, "utf8"));
  } catch (error) {
    if (error?.code === "ENOENT") {
      return fallback;
    }
    throw new Error(`invalid OpenClaw device state: ${path}`, { cause: error });
  }
}

function writePrivateFile(path, value, { exclusive = false } = {}) {
  writeFileSync(path, `${JSON.stringify(value, null, 2)}\n`, {
    encoding: "utf8",
    flag: exclusive ? "wx" : "w",
    mode: 0o600,
  });
  chmodSync(path, 0o600);
}

export function publicKeyRawBase64UrlFromPem(publicKeyPem) {
  const der = createPublicKey(publicKeyPem).export({ format: "der", type: "spki" });
  if (der.length !== 44) {
    throw new Error("unexpected Ed25519 public key encoding");
  }
  return der.subarray(der.length - 32).toString("base64url");
}

export function deriveDeviceId(publicKeyPem) {
  const raw = Buffer.from(publicKeyRawBase64UrlFromPem(publicKeyPem), "base64url");
  return createHash("sha256").update(raw).digest("hex");
}

export function signDevicePayload(privateKeyPem, payload) {
  return sign(null, Buffer.from(payload, "utf8"), createPrivateKey(privateKeyPem)).toString(
    "base64url",
  );
}

function generateIdentity() {
  const { publicKey, privateKey } = generateKeyPairSync("ed25519");
  const publicKeyPem = publicKey.export({ format: "pem", type: "spki" }).toString();
  const privateKeyPem = privateKey.export({ format: "pem", type: "pkcs8" }).toString();
  return {
    version: 1,
    deviceId: deriveDeviceId(publicKeyPem),
    publicKeyPem,
    privateKeyPem,
    createdAt: new Date().toISOString(),
  };
}

function validateIdentity(value) {
  if (
    value?.version !== 1 ||
    typeof value.deviceId !== "string" ||
    typeof value.publicKeyPem !== "string" ||
    typeof value.privateKeyPem !== "string" ||
    deriveDeviceId(value.publicKeyPem) !== value.deviceId
  ) {
    throw new Error("stored OpenClaw device identity is invalid");
  }
  const derivedPublic = createPublicKey(createPrivateKey(value.privateKeyPem));
  if (
    publicKeyRawBase64UrlFromPem(
      derivedPublic.export({ format: "pem", type: "spki" }).toString(),
    ) !== publicKeyRawBase64UrlFromPem(value.publicKeyPem)
  ) {
    throw new Error("stored OpenClaw device key pair does not match");
  }
  return {
    deviceId: value.deviceId,
    publicKeyPem: value.publicKeyPem,
    privateKeyPem: value.privateKeyPem,
  };
}

export class DeviceStateStore {
  constructor(directory) {
    this.directory = resolve(directory);
    mkdirSync(this.directory, { recursive: true, mode: 0o700 });
    chmodSync(this.directory, 0o700);
  }

  loadOrCreateIdentity() {
    const path = join(this.directory, IDENTITY_FILE);
    const existing = readJson(path, null);
    if (existing !== null) {
      return validateIdentity(existing);
    }
    const candidate = generateIdentity();
    try {
      writePrivateFile(path, candidate, { exclusive: true });
      return validateIdentity(candidate);
    } catch (error) {
      if (error?.code !== "EEXIST") {
        throw error;
      }
      return validateIdentity(readJson(path, null));
    }
  }

  loadToken({ deviceId, role }) {
    const entries = readJson(join(this.directory, TOKENS_FILE), {});
    const entry = entries[`${deviceId}:${role}`];
    if (
      entry === undefined ||
      typeof entry.token !== "string" ||
      !Array.isArray(entry.scopes) ||
      !entry.scopes.every((scope) => typeof scope === "string")
    ) {
      return null;
    }
    return { token: entry.token, scopes: entry.scopes };
  }

  storeToken({ deviceId, role, token, scopes }) {
    this.#mutateTokens((entries) => {
      entries[`${deviceId}:${role}`] = { token, scopes: [...scopes] };
    });
  }

  clearToken({ deviceId, role }) {
    this.#mutateTokens((entries) => {
      delete entries[`${deviceId}:${role}`];
    });
  }

  #mutateTokens(mutate) {
    const path = join(this.directory, TOKENS_FILE);
    const entries = readJson(path, {});
    mutate(entries);
    const temporary = `${path}.${process.pid}.${randomUUID()}.tmp`;
    try {
      writePrivateFile(temporary, entries, { exclusive: true });
      renameSync(temporary, path);
      chmodSync(path, 0o600);
    } finally {
      try {
        unlinkSync(temporary);
      } catch (error) {
        if (error?.code !== "ENOENT") {
          throw error;
        }
      }
    }
  }
}
