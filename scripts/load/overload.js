// Separate overload profile. 429 is allowed here and does not replace the baseline.
// Recovery must return to HTTP 200 after the burst. Thresholds are not §7.1.
import http from "k6/http";
import { check } from "k6";
import { Counter } from "k6/metrics";

const status429 = new Counter("status_429");
const baseUrl = __ENV.BASE_URL || "http://host.docker.internal:8000";

export const options = {
  scenarios: {
    burst: {
      executor: "constant-arrival-rate",
      rate: 400,
      timeUnit: "1s",
      duration: "10s",
      preAllocatedVUs: 50,
      maxVUs: 400,
      exec: "once",
      tags: { phase: "burst" },
    },
    recovery: {
      executor: "constant-arrival-rate",
      rate: 20,
      timeUnit: "1s",
      duration: "10s",
      startTime: "12s",
      preAllocatedVUs: 10,
      maxVUs: 40,
      exec: "once",
      tags: { phase: "recovery" },
    },
  },
  thresholds: {
    "status_429{phase:burst}": ["count>0"],
    "http_req_failed{phase:recovery}": ["rate==0"],
    "checks{phase:recovery}": ["rate==1"],
    "status_429{phase:recovery}": ["count==0"],
  },
};

export function once() {
  const id = `over-${__VU}-${__ITER}`;
  const response = http.post(
    `${baseUrl}/process`,
    JSON.stringify({
      payload: "synthetic@example.test",
      payload_id: id,
    }),
    { headers: { "Content-Type": "application/json" }, timeout: "10s" },
  );
  if (response.status === 429) {
    status429.add(1);
    check(response, {
      "retry-after present": (item) => Boolean(item.headers["Retry-After"]),
    });
    return;
  }
  check(response, {
    "mask accepted": (item) => item.status === 200 && item.json("result") !== undefined,
  });
}
