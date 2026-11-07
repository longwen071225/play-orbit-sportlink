import test from "node:test";
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { once } from "node:events";

const root = new URL("..", import.meta.url);
async function start(dbPath) {
  const process = spawn(globalThis.process.execPath, ["api/server.mjs"], {
    cwd: root,
    env: {
      ...globalThis.process.env,
      API_PORT: "0",
      DEMO_DB_PATH: dbPath,
      DEMO_OPERATOR_CODE: "isolated-test-code",
    },
    stdio: ["ignore", "pipe", "pipe"],
  });
  const base = await new Promise((resolve, reject) => {
    let output = "";
    const timer = setTimeout(
      () => reject(new Error("API did not start")),
      5000,
    );
    process.once("exit", (code) => {
      clearTimeout(timer);
      reject(new Error("API exited " + code));
    });
    process.stdout.on("data", (chunk) => {
      output += chunk;
      const match = output.match(/http:\/\/127\.0\.0\.1:(\d+)/);
      if (match) {
        clearTimeout(timer);
        resolve("http://127.0.0.1:" + match[1] + "/api");
      }
    });
    process.stderr.on("data", (chunk) => {
      output += chunk;
    });
  });
  return {
    base,
    async stop() {
      process.kill("SIGTERM");
      await once(process, "exit");
    },
  };
}
test("persistent demo flow: access, idempotent booking, trusted completion, event consumption and child isolation", async () => {
  const folder = await mkdtemp(path.join(os.tmpdir(), "play-orbit-api-"));
  const dbPath = path.join(folder, "demo.json");
  let server = await start(dbPath);
  let parent = "",
    operator = "";
  const request = async (
    route,
    { method = "GET", body, role = "parent" } = {},
  ) => {
    const res = await fetch(server.base + route, {
      method,
      headers: {
        "Content-Type": "application/json",
        Cookie: role === "operator" ? operator : parent,
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    return {
      status: res.status,
      body: await res.json(),
      cookie: res.headers.get("set-cookie")?.split(";")[0],
    };
  };
  try {
    assert.equal((await request("/state")).body.loggedIn, false);
    const login = await request("/login", { method: "POST" });
    parent = login.cookie;
    assert.ok(parent.includes("orbit_session="));
    assert.equal(login.body.stars.length, 3);
    const chat = await request("/chat", {
      method: "POST",
      body: { childId: "child-1", message: "想体验篮球" },
    });
    assert.deepEqual(chat.body.messages.at(-1).coachIds, ["chen"]);
    const date = new Intl.DateTimeFormat("en-CA", {
      timeZone: "Asia/Shanghai",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).format(new Date(Date.now() + 2 * 86400000));
    const body = {
      childId: "child-1",
      coachId: "chen",
      lesson: "篮球兴趣启蒙",
      date,
      time: "10:30",
      requestId: "one-logical-request",
    };
    const booked = await request("/bookings", { method: "POST", body });
    assert.equal(booked.status, 201);
    const id = booked.body.order.id;
    assert.equal(booked.body.stars.length, 3);
    assert.equal(booked.body.events.length, 0);
    assert.equal(booked.body.order.paymentStatus, "demo-unpaid");
    assert.equal(
      (await request("/bookings", { method: "POST", body })).body.order.id,
      id,
    );
    assert.equal(
      (
        await request("/bookings", {
          method: "POST",
          body: { ...body, requestId: "different-request" },
        })
      ).status,
      409,
    );
    assert.equal(
      (await request(`/bookings/${id}/complete`, { method: "POST" })).status,
      403,
    );
    assert.equal(
      (
        await request("/demo/login", {
          method: "POST",
          body: { code: "wrong" },
        })
      ).status,
      403,
    );
    operator = (
      await request("/demo/login", {
        method: "POST",
        body: { code: "isolated-test-code" },
      })
    ).cookie;
    const complete = () =>
      request(`/bookings/${id}/complete`, {
        method: "POST",
        role: "operator",
        body: { feedback: "完成一次测试训练。" },
      });
    assert.equal((await complete()).status, 200);
    assert.equal((await complete()).status, 200);
    let state = (await request("/state")).body;
    assert.equal(state.stars.length, 4);
    assert.equal(state.events.length, 1);
    assert.equal(
      state.stars.find((s) => s.orderId === id).description,
      "完成一次测试训练。",
    );
    const event = state.events[0];
    assert.equal(event.nodeId, state.stars.find((s) => s.orderId === id).id);
    await request("/active-child", {
      method: "PUT",
      body: { childId: "child-2" },
    });
    state = (await request("/state")).body;
    assert.equal(state.stars.length, 0);
    assert.equal(state.orders.length, 0);
    assert.equal(state.messages.length, 0);
    assert.equal(
      (
        await request(`/growth-events/${event.eventId}/seen`, {
          method: "POST",
        })
      ).status,
      404,
    );
    assert.equal(
      (
        await request("/bookings", {
          method: "POST",
          body: { ...body, requestId: "wrong-child" },
        })
      ).status,
      409,
    );
    await request("/active-child", {
      method: "PUT",
      body: { childId: "child-1" },
    });
    assert.equal(
      (
        await request(`/growth-events/${event.eventId}/seen`, {
          method: "POST",
        })
      ).status,
      200,
    );
    assert.equal(
      (
        await request(`/growth-events/${event.eventId}/seen`, {
          method: "POST",
        })
      ).status,
      200,
    );
    await server.stop();
    server = await start(dbPath);
    state = (await request("/state")).body;
    assert.equal(state.loggedIn, true);
    assert.equal(state.stars.length, 4);
    assert.equal(state.events.length, 0);
    assert.equal(state.orders.find((o) => o.id === id).status, "completed");
  } finally {
    await server.stop();
    await rm(folder, { recursive: true, force: true });
  }
});
