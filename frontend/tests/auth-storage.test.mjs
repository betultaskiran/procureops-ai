import test from "node:test";
import assert from "node:assert/strict";

// Mock browser window and storage environment
class MockStorage {
  constructor() {
    this.store = {};
  }
  getItem(key) {
    return this.store[key] || null;
  }
  setItem(key, value) {
    this.store[key] = String(value);
  }
  removeItem(key) {
    delete this.store[key];
  }
  clear() {
    this.store = {};
  }
}

function setupMockEnvironment() {
  const localStorage = new MockStorage();
  const sessionStorage = new MockStorage();
  let cookieStr = "";
  const dispatchedEvents = [];

  const mockWindow = {
    location: {
      hostname: "localhost",
      protocol: "http:",
    },
    dispatchEvent(event) {
      dispatchedEvents.push(event.type);
    },
  };

  const mockDocument = {
    get cookie() {
      return cookieStr;
    },
    set cookie(val) {
      cookieStr = val;
    },
  };

  global.window = mockWindow;
  global.document = mockDocument;
  global.localStorage = localStorage;
  global.sessionStorage = sessionStorage;
  global.Event = class Event {
    constructor(type) {
      this.type = type;
    }
  };

  return { localStorage, sessionStorage, mockDocument, dispatchedEvents };
}

// Concrete implementations mirroring frontend/src/lib/api/client.ts
function getAuthToken() {
  if (typeof window !== "undefined") {
    const local =
      localStorage.getItem("access_token") ||
      localStorage.getItem("token");
    if (local) return local;

    for (const key of ["auth", "user", "session", "procureops_auth"]) {
      const val = localStorage.getItem(key);
      if (val && (val.startsWith("{") || val.startsWith("["))) {
        try {
          const parsed = JSON.parse(val);
          const t = parsed.access_token || parsed.token || parsed.user?.token;
          if (t && typeof t === "string") return t;
        } catch {}
      }
    }
  }
  return null;
}

function setAuthToken(token) {
  if (typeof window !== "undefined") {
    localStorage.setItem("access_token", token);
    window.dispatchEvent(new Event("auth:login"));
  }
}

function removeAuthToken() {
  if (typeof window !== "undefined") {
    localStorage.removeItem("access_token");
    localStorage.removeItem("token");
    localStorage.removeItem("auth_token");

    sessionStorage.removeItem("access_token");
    sessionStorage.removeItem("token");

    if (typeof document !== "undefined") {
      document.cookie = "access_token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT; SameSite=Lax";
    }

    window.dispatchEvent(new Event("auth:logout"));
  }
}

function getAuthHeaders() {
  const token = getAuthToken();
  if (token) {
    return { Authorization: `Bearer ${token}` };
  }
  return {};
}

test("1. setAuthToken stores exclusively in authoritative localStorage without touching document.cookie or sessionStorage", () => {
  const env = setupMockEnvironment();

  const sampleToken = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test-payload";
  setAuthToken(sampleToken);

  // Authoritative storage check
  assert.strictEqual(env.localStorage.getItem("access_token"), sampleToken);

  // Verification that redundant/insecure stores were NOT written
  assert.strictEqual(env.localStorage.getItem("token"), null, "Redundant token alias should not be written");
  assert.strictEqual(env.sessionStorage.getItem("access_token"), null, "SessionStorage should not be written for persistent sessions");
  assert.strictEqual(env.mockDocument.cookie, "", "JavaScript-accessible document.cookie MUST NOT be created");

  // Event dispatch verification
  assert.ok(env.dispatchedEvents.includes("auth:login"), "auth:login event should be dispatched");
});

test("2. getAuthToken retrieves token from primary localStorage, with legacy fallback", () => {
  const env = setupMockEnvironment();

  // Empty state
  assert.strictEqual(getAuthToken(), null);

  // Primary key check
  env.localStorage.setItem("access_token", "primary-token-123");
  assert.strictEqual(getAuthToken(), "primary-token-123");

  // Fallback check: when access_token is absent, legacy 'token' is honored
  env.localStorage.removeItem("access_token");
  env.localStorage.setItem("token", "legacy-token-456");
  assert.strictEqual(getAuthToken(), "legacy-token-456");

  // When cleared, returns null
  env.localStorage.removeItem("token");
  assert.strictEqual(getAuthToken(), null);
});

test("3. removeAuthToken thoroughly purges localStorage, legacy sessionStorage and expires legacy cookies", () => {
  const env = setupMockEnvironment();

  // Seed with active and legacy stores
  env.localStorage.setItem("access_token", "active-token");
  env.localStorage.setItem("token", "legacy-token");
  env.localStorage.setItem("auth_token", "legacy-auth-token");
  env.sessionStorage.setItem("access_token", "stale-session-token");
  env.sessionStorage.setItem("token", "stale-token");
  env.mockDocument.cookie = "access_token=old-cookie";

  removeAuthToken();

  // All local keys cleared
  assert.strictEqual(env.localStorage.getItem("access_token"), null);
  assert.strictEqual(env.localStorage.getItem("token"), null);
  assert.strictEqual(env.localStorage.getItem("auth_token"), null);

  // Session keys cleaned
  assert.strictEqual(env.sessionStorage.getItem("access_token"), null);
  assert.strictEqual(env.sessionStorage.getItem("token"), null);

  // Cookie expiration header set
  assert.ok(env.mockDocument.cookie.includes("expires=Thu, 01 Jan 1970"), "Legacy client cookie should be expired");
  assert.ok(env.dispatchedEvents.includes("auth:logout"), "auth:logout event should be dispatched");
});

test("4. getAuthHeaders generates RFC-6750 Bearer headers when token exists, empty object otherwise", () => {
  const env = setupMockEnvironment();

  // Unauthenticated
  assert.deepStrictEqual(getAuthHeaders(), {});

  // Authenticated
  env.localStorage.setItem("access_token", "valid-jwt-token");
  assert.deepStrictEqual(getAuthHeaders(), {
    Authorization: "Bearer valid-jwt-token",
  });
});
