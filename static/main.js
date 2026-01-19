const containerMap = new Map();
const selectedInstances = new Set();
const connectSent = new Map(); // Track if "connect" command was sent
const codeIntervals = new Map(); // Track code polling intervals
const statusIntervals = new Map(); // Track status polling intervals

// Cookie utilities
function setCookie(name, value, days) {
  const d = new Date();
  d.setTime(d.getTime() + days * 24 * 60 * 60 * 1000);
  document.cookie =
    name +
    "=" +
    encodeURIComponent(value) +
    ";expires=" +
    d.toUTCString() +
    ";path=/";
}

function getCookie(name) {
  const v = document.cookie.match("(^|;) ?" + name + "=([^;]*)(;|$)");
  return v ? decodeURIComponent(v[2]) : null;
}

async function fetchContainers() {
  const res = await fetch("/api/containers");
  const data = await res.json();
  const list = document.getElementById("instances");

  data.sort((a, b) => a.instance - b.instance);
  const names = new Set(data.map((c) => c.name));

  // Remove deleted containers
  for (const [name, el] of containerMap.entries()) {
    if (!names.has(name)) {
      el.remove();
      containerMap.delete(name);
      selectedInstances.delete(name);
      if (codeIntervals.has(name)) {
        clearInterval(codeIntervals.get(name));
        codeIntervals.delete(name);
      }
      if (statusIntervals.has(name)) {
        clearInterval(statusIntervals.get(name));
        statusIntervals.delete(name);
      }
    }
  }

  data.forEach((c) => {
    if (containerMap.has(c.name)) {
      updateInstanceUI(c);
    } else {
      createInstanceUI(c);
    }
  });

  // Reorder in DOM
  data.forEach((c) => {
    const el = containerMap.get(c.name);
    if (el) list.appendChild(el);
  });
}

function createInstanceUI(c) {
  const li = document.createElement("li");
  li.className = "instance";

  li.innerHTML = `
        <h1 class="instance-number">${c.instance}</h1>
        <div class="separator"></div>
        <span data-account>Loading...</span>
        <div class="spacer"></div>
        <div class="other-info">
        <span data-status>${c.status} <i class="mdi mdi-information-box"></i></span>
        <span data-port>Port ${c.port} <i class="mdi mdi-server"></i></span>
        </div>
        <div class="actions-btn">
        <button><i class="mdi mdi-dots-vertical"></i></button>
        <div class="context-menu">
            <span onclick="start('${c.name}')"><i class="mdi mdi-play"></i> Start</span>
            <span onclick="stop('${c.name}')"><i class="mdi mdi-stop"></i> Stop</span>
            <span onclick="restart('${c.name}')"><i class="mdi mdi-refresh"></i> Restart</span>
            <span class="delete-btn" onclick="del('${c.name}')"><i class="mdi mdi-delete"></i> Delete</span>
        </div>
        </div>
    `;

  containerMap.set(c.name, li);
  document.getElementById("instances").appendChild(li);

  // Actions menu toggle
  const btn = li.querySelector(".actions-btn button");
  const menu = li.querySelector(".context-menu");
  btn.addEventListener("click", (e) => {
    e.stopPropagation();
    document.querySelectorAll(".context-menu").forEach((m) => {
      if (m !== menu) m.style.display = "none";
    });
    menu.style.display = menu.style.display === "block" ? "none" : "block";
  });

  // Instance number selection
  const instanceNumberEl = li.querySelector(".instance-number");
  instanceNumberEl.style.cursor = "pointer";
  instanceNumberEl.style.color = selectedInstances.has(c.name)
    ? "#29e026"
    : "#888";
  instanceNumberEl.onclick = () => {
    if (selectedInstances.has(c.name)) {
      selectedInstances.delete(c.name);
      instanceNumberEl.style.color = "#888";
    } else {
      selectedInstances.add(c.name);
      instanceNumberEl.style.color = "#29e026";
    }
  };

  startStatusPolling(c.name, c.status);
}

function updateInstanceUI(c) {
  const el = containerMap.get(c.name);
  if (!el) return;
  el.querySelector("[data-status]").innerHTML =
    `${c.status} <i class="mdi mdi-information-box"></i>`;
  el.querySelector("[data-port]").innerHTML =
    `Port ${c.port} <i class="mdi mdi-server"></i>`;
}

function startStatusPolling(name, initialStatus) {
  if (statusIntervals.has(name)) return;
  const el = containerMap.get(name);
  const accountSpan = el.querySelector("[data-account]");

  async function pollStatus() {
    try {
      const res = await fetch(`/api/containers/${name}/zenith-status`);

      if (!res.ok) {
        // Container offline / not started
        const lastUser = getCookie(`container_${name}_user`);
        accountSpan.textContent = lastUser || "Unknown";
        return; // skip all further logic
      }

      const data = await res.json();
      const account = data?.response_body?.Account || "Unknown";
      const status = data?.response_body?.Status || initialStatus || "Offline";

      if (status !== "Running") {
        // container is offline
        const lastUser = getCookie(`container_${name}_user`);
        accountSpan.textContent = lastUser || "Unknown";
        return;
      }

      // container is online
      if (account && account !== "Unknown") {
        accountSpan.textContent = account;
        setCookie(`container_${name}_user`, account, 7);

        if (codeIntervals.has(name)) {
          clearInterval(codeIntervals.get(name));
          codeIntervals.delete(name);
        }
      } else {
        if (!connectSent.get(name)) {
          accountSpan.textContent = "Connect";
          accountSpan.onclick = async () => {
            await sendCommand(name, "connect");
            connectSent.set(name, true);
            startCodePolling(name);
            accountSpan.textContent = "Loading...";
          };
        }
      }
    } catch (err) {
      // network or parsing error → container likely offline
      const lastUser = getCookie(`container_${name}_user`);
      accountSpan.textContent = lastUser || "Unknown";
    }
  }

  pollStatus(); // initial call
  const interval = setInterval(pollStatus, 2000);
  statusIntervals.set(name, interval);
}

function startCodePolling(name) {
  if (codeIntervals.has(name)) return;
  const el = containerMap.get(name);
  const accountSpan = el.querySelector("[data-account]");

  async function pollCode() {
    try {
      const res = await fetch(`/api/containers/${name}/code`);
      const data = await res.json();
      const code = data.code;

      if (!code) {
        accountSpan.textContent = "Loading...";
      } else {
        accountSpan.innerHTML = `<a href="https://www.microsoft.com/link?otc=${code}" target="_blank">${code}</a>`;
        clearInterval(codeIntervals.get(name));
        codeIntervals.delete(name);
      }
    } catch (err) {
      console.error("Code poll failed:", err);
    }
  }

  pollCode();
  const interval = setInterval(pollCode, 2000);
  codeIntervals.set(name, interval);
}

async function sendCommand(name, command) {
  try {
    await fetch(`/api/containers/${name}/send_command`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ command }),
    });
  } catch (err) {
    console.error(`Failed to send command to ${name}:`, err);
  }
}

async function start(name) {
  await fetch(`/api/containers/${name}/start`, { method: "POST" });
}
async function stop(name) {
  await fetch(`/api/containers/${name}/stop`, { method: "POST" });
}
async function restart(name) {
  await fetch(`/api/containers/${name}/restart`, { method: "POST" });
}

async function del(name) {
  if (confirm(`Delete ${name}?`)) {
    await fetch(`/api/containers/${name}/delete`, { method: "POST" });
    const el = containerMap.get(name);
    if (el) {
      el.remove();
      containerMap.delete(name);
      selectedInstances.delete(name);
      if (codeIntervals.has(name)) clearInterval(codeIntervals.get(name));
      if (statusIntervals.has(name)) clearInterval(statusIntervals.get(name));
    }
  }
}

// Command input
document
  .getElementById("commandInput")
  .addEventListener("keydown", async (e) => {
    if (e.key !== "Enter") return;
    const commandInput = e.target;
    const responseDiv = document.getElementById("commandResponse");
    const command = commandInput.value.trim();
    if (!command) return;
    if (selectedInstances.size === 0) {
      responseDiv.textContent = "No instances selected!";
      return;
    }
    responseDiv.textContent = "Sending command...";
    commandInput.value = "";
    const results = [];
    for (const name of selectedInstances) {
      try {
        const res = await fetch(`/api/containers/${name}/send_command`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ command }),
        });
        const data = await res.json();
        if (res.ok) {
          results.push(
            `${name} → ${JSON.stringify(data.response_body, null, 2)}`,
          );
        } else {
          results.push(
            `${name} → ERROR: ${data.message || JSON.stringify(data)}`,
          );
        }
      } catch (err) {
        results.push(`${name} → Request failed: ${err.message}`);
      }
    }
    responseDiv.textContent = results.join("\n\n");
  });

document.getElementById("addBtn").onclick = async () => {
  await fetch("/api/containers/add", { method: "POST" });
};

document.addEventListener("click", () => {
  document.querySelectorAll(".context-menu").forEach((m) => {
    m.style.display = "none";
  });
});

setInterval(fetchContainers, 1000);
fetchContainers();
