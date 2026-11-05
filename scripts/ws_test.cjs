/** Test rápido del WebSocket /ws/telemetry (handshake manual). */
const http = require("http");
const crypto = require("crypto");

const key = crypto.randomBytes(16).toString("base64");
const req = http.request({
  port: 8000,
  host: "127.0.0.1",
  path: "/ws/telemetry",
  headers: {
    Upgrade: "websocket",
    Connection: "Upgrade",
    "Sec-WebSocket-Key": key,
    "Sec-WebSocket-Version": "13",
  },
});
req.end();

req.on("upgrade", (res, socket) => {
  console.log("WS 101 OK");
  const sizes = [];
  socket.on("data", (d) => {
    sizes.push(d.length);
    if (sizes.length === 3) {
      console.log("3 frames recibidos, bytes por paquete:", sizes.join(","));
      socket.destroy();
      process.exit(0);
    }
  });
  socket.on("error", () => undefined);
  socket.on("close", () => process.exit(0));
  setTimeout(() => {
    if (sizes.length >= 2) {
      console.log("framesres:", sizes.length);
      process.exit(0);
    }
    console.log("frames insuficientes:", sizes.length);
    process.exit(1);
  }, 7000);
});
req.on("error", (e) => {
  console.log("WS ERROR", e.message);
  process.exit(1);
});
