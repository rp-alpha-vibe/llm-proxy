// Stateful mask -> unmask. One HTTP call is one operation.
// Warmup is tagged and is not the measurement window.
// Thresholds are REQUIREMENTS.md §7.1. Do not relax them after a run.
import http from "k6/http";
import { check } from "k6";
import { Counter } from "k6/metrics";

const status429 = new Counter("status_429");
const unexpected = new Counter("unexpected_status");
const baseUrl = __ENV.BASE_URL || "http://host.docker.internal:8000";
const warmupDuration = __ENV.WARMUP_DURATION || "15s";
const baselineDuration = __ENV.BASELINE_DURATION || "300s";
const rate = Number(__ENV.RATE || 1000);

const pending = {};

export const options = {
  scenarios: {
    warmup: {
      executor: "constant-arrival-rate",
      rate: Math.max(1, Math.floor(rate / 5)),
      timeUnit: "1s",
      duration: warmupDuration,
      preAllocatedVUs: 50,
      maxVUs: 400,
      exec: "maskUnmask",
      tags: { phase: "warmup" },
    },
    baseline: {
      executor: "constant-arrival-rate",
      rate: rate,
      timeUnit: "1s",
      duration: baselineDuration,
      startTime: warmupDuration,
      preAllocatedVUs: 800,
      maxVUs: 5000,
      exec: "maskUnmask",
      tags: { phase: "baseline" },
    },
  },
  summaryTrendStats: ["avg", "min", "med", "max", "p(90)", "p(95)", "p(99)"],
  thresholds: {
    "http_req_duration{phase:baseline}": ["p(95)<1000"],
    "http_req_failed{phase:baseline}": ["rate==0"],
    "checks{phase:baseline}": ["rate==1"],
    "status_429{phase:baseline}": ["count==0"],
    "unexpected_status{phase:baseline}": ["count==0"],
    "dropped_iterations{scenario:baseline}": ["count==0"],
  },
};

export function maskUnmask() {
  const slot = pending[__VU];
  if (slot) {
    const response = http.post(
      `${baseUrl}/process`,
      JSON.stringify({ payload: slot.masked, payload_id: slot.id }),
      { headers: { "Content-Type": "application/json" }, timeout: "10s" },
    );
    delete pending[__VU];
    record(response, (body) => body.result === slot.original);
    return;
  }

  const original = "клиент Иван Петров тел +7 900 111-22-33 synthetic@example.test";
  const id = `vu-${__VU}-iter-${__ITER}`;
  const response = http.post(
    `${baseUrl}/process`,
    JSON.stringify({ payload: original, payload_id: id }),
    { headers: { "Content-Type": "application/json" }, timeout: "10s" },
  );
  const ok = record(response, (body) => typeof body.result === "string" && body.result !== original);
  if (ok) {
    pending[__VU] = { id, masked: response.json().result, original };
  }
}

function record(response, accept) {
  if (response.status === 429) {
    status429.add(1);
  } else if (response.status !== 200) {
    unexpected.add(1);
  }
  return check(response, {
    "valid operation": (item) => {
      if (item.status !== 200) {
        return false;
      }
      try {
        return accept(item.json());
      } catch (_error) {
        return false;
      }
    },
  });
}
