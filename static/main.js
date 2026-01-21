const containerMap = new Map(); // name -> DOM element
const containerStatusMap = new Map(); // name -> latest c.status
const selectedInstances = new Set(); // selected instances
const connectSent = new Map(); // track if "connect" was sent
const codeIntervals = new Map(); // track code polling intervals
const statusIntervals = new Map(); // track status polling intervals

function updateConnectCursor(span) {
  if (span.textContent.trim() === "Connect") {
    span.style.cursor = "pointer";
  } else {
    span.style.cursor = "";
  }
}

document.querySelectorAll("span[data-account]").forEach(updateConnectCursor);

const observer = new MutationObserver((mutationsList) => {
  for (const mutation of mutationsList) {
    if (mutation.type === "characterData") {
      updateConnectCursor(mutation.target.parentNode);
    }
    if (mutation.type === "childList") {
      mutation.addedNodes.forEach((node) => {
        if (node.nodeType === 1 && node.matches("span[data-account]")) {
          updateConnectCursor(node);
        }
        node
          .querySelectorAll?.("span[data-account]")
          .forEach(updateConnectCursor);
      });
    }
  }
});

observer.observe(document.body, {
  childList: true,
  subtree: true,
  characterData: true,
});

// ---- Cookie utilities ----
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

// ---- Fetch container list ----
async function fetchContainers() {
  const res = await fetch("/api/containers");
  if (!res.ok) return;
  const data = await res.json();
  const list = document.getElementById("instances");

  data.sort((a, b) => a.instance - b.instance);
  const names = new Set(data.map((c) => c.name));

  // Remember focused element
  const activeEl = document.activeElement;
  const selectionStart = activeEl?.selectionStart;
  const selectionEnd = activeEl?.selectionEnd;

  // Remove deleted containers
  for (const [name, el] of containerMap.entries()) {
    if (!names.has(name)) {
      el.remove();
      containerMap.delete(name);
      containerStatusMap.delete(name);
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

  // Update or create containers
  data.forEach((c) => {
    containerStatusMap.set(c.name, c.status);

    if (containerMap.has(c.name)) {
      updateInstanceUI(c); // safe update
    } else {
      createInstanceUI(c); // only create new elements
    }
  });

  // Reorder DOM without destroying focus
  data.forEach((c) => {
    const el = containerMap.get(c.name);
    if (el && el.parentNode !== list) {
      list.appendChild(el);
    }
  });

  // Restore focus
  if (activeEl && selectionStart != null && selectionEnd != null) {
    activeEl.focus();
    activeEl.setSelectionRange(selectionStart, selectionEnd);
  }
}

// ---- Create container DOM ----
function createInstanceUI(c) {
  const li = document.createElement("li");
  li.className = "instance";

  // Determine initial account display
  const lastUser = getCookie(`container_${c.name}_user`);
  const accountText =
    c.status === "Running"
      ? "Loading..." // will poll zenith-status
      : lastUser || "Unknown"; // container offline

  li.innerHTML = `
    <div class="top">
        <h1 class="instance-number">${c.instance}</h1>
        <div class="separator"></div>
            <span data-account>${accountText}</span>
        <div class="spacer"></div>
        <div class="other-info">
            <span data-status>${c.status} <i class="mdi mdi-information-box"></i></span>
            <span data-port>Port ${c.port} <i class="mdi mdi-server"></i></span>
            <span data-ip>IP ${c.ip} <i class="mdi mdi-web"></i></span>
        </div>
        <div class="actions-btn">
            <button><i class="mdi mdi-dots-vertical"></i></button>
            <div class="context-menu">
                <span onclick="start('${c.name}')"><i class="mdi mdi-play"></i> Start</span>
                <span onclick="stop('${c.name}')"><i class="mdi mdi-stop"></i> Stop</span>
                <span onclick="restart('${c.name}')"><i class="mdi mdi-restart"></i> Restart</span>
                <span class="delete-btn" onclick="del('${c.name}')"><i class="mdi mdi-delete"></i> Delete</span>
            </div>
        </div>
    </div>
    <div class="bottom">
        <form action="/api/containers/${c.name}/update-discord" method="POST">
            <input type="text" id="token" name="token" placeholder="Bot Token">
            <input type="text" id="channel" name="channel" placeholder="Channel ID">
            <input type="text" id="role" name="role" placeholder="Role ID">
            <button type="submit">Update</button>
        </form>
        <input
          type="text"
          class="super-command-input"
          data-container="${c.name}"
          placeholder="Super cmd"
        />
    </div>
  `;

  containerMap.set(c.name, li);
  document.getElementById("instances").appendChild(li);

  const superInput = li.querySelector(".super-command-input");

  superInput.addEventListener("keydown", async (e) => {
    if (e.key !== "Enter") return;

    const command = superInput.value.trim();
    if (!command) return;

    superInput.value = "";

    try {
      const res = await fetch(`/api/containers/${c.name}/send_super_command`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ command }),
      });

      const data = await res.json();

      if (!res.ok) {
        console.error(`${c.name} super command error`, data);
      }
    } catch (err) {
      console.error(`${c.name} super command failed`, err);
    }
  });

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

  startStatusPolling(c.name); // start polling for this container
}

// ---- Update existing container UI ----
function updateInstanceUI(c) {
  const el = containerMap.get(c.name);
  if (!el) return;

  const statusEl = el.querySelector("[data-status]");
  const portEl = el.querySelector("[data-port]");
  const ipEl = el.querySelector("[data-ip]");

  // Update text without replacing icons
  statusEl.childNodes[0].textContent = c.status + " ";
  portEl.childNodes[0].textContent = "Port " + c.port + " ";
  ipEl.childNodes[0].textContent = "IP " + c.ip + " ";
}

// ---- Poll container status ----
function startStatusPolling(name) {
  if (statusIntervals.has(name)) return;
  const el = containerMap.get(name);
  const accountSpan = el.querySelector("[data-account]");

  async function pollStatus() {
    // Remember currently focused input and cursor
    const activeEl = document.activeElement;
    const selectionStart = activeEl?.selectionStart;
    const selectionEnd = activeEl?.selectionEnd;

    try {
      const currentStatus = containerStatusMap.get(name);
      const lastUser = getCookie(`container_${name}_user`);

      if (currentStatus !== "Running") {
        accountSpan.textContent = lastUser || "Unknown";
        accountSpan.onclick = null;

        if (codeIntervals.has(name)) {
          clearInterval(codeIntervals.get(name));
          codeIntervals.delete(name);
        }
      } else {
        // Container is running → check zenith-status
        const res = await fetch(`/api/containers/${name}/zenith-status`);
        if (!res.ok) {
          accountSpan.textContent = lastUser || "Unknown";
          accountSpan.onclick = null;
          return;
        }

        const data = await res.json();
        const account = data?.response_body?.Account || "Unknown";
        accountSpan.onclick = null;

        if (account !== "Unknown") {
          accountSpan.textContent = account;
          setCookie(`container_${name}_user`, account, 7);

          if (codeIntervals.has(name)) {
            clearInterval(codeIntervals.get(name));
            codeIntervals.delete(name);
          }
        } else {
          // Show Connect if not already sent
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
      }
    } catch (err) {
      const lastUser = getCookie(`container_${name}_user`);
      accountSpan.textContent = lastUser || "Unknown";
    }

    // Restore focus and cursor if typing in input
    if (
      activeEl &&
      activeEl.tagName === "INPUT" &&
      selectionStart != null &&
      selectionEnd != null
    ) {
      activeEl.focus();
      activeEl.setSelectionRange(selectionStart, selectionEnd);
    }
  }

  pollStatus(); // initial call
  const interval = setInterval(pollStatus, 2000);
  statusIntervals.set(name, interval);
}

// ---- Poll code after connect ----
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
        accountSpan.onclick = null;
      } else {
        accountSpan.onclick = null;
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

// ---- Send command ----
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

// ---- Start / Stop / Restart / Delete ----
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
      containerStatusMap.delete(name);
      selectedInstances.delete(name);
      if (codeIntervals.has(name)) clearInterval(codeIntervals.get(name));
      if (statusIntervals.has(name)) clearInterval(statusIntervals.get(name));

      setCookie(`container_${name}_user`, "", -1);
    }
  }
}

// ---- Command input ----
const commandInput = document.getElementById("commandInput");
if (commandInput) {
  commandInput.addEventListener("keydown", async (e) => {
    if (e.key !== "Enter") return;
    const command = e.target.value.trim();
    if (!command) return;
    const responseDiv = document.getElementById("commandResponse");
    if (selectedInstances.size === 0) {
      responseDiv.textContent = "No instances selected!";
      return;
    }
    responseDiv.textContent = "Sending command...";
    e.target.value = "";

    const results = [];
    for (const name of selectedInstances) {
      try {
        const res = await fetch(`/api/containers/${name}/send_command`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ command }),
        });
        const data = await res.json();
        if (res.ok)
          results.push(
            `${name} → ${JSON.stringify(data.response_body, null, 2)}`,
          );
        else
          results.push(
            `${name} → ERROR: ${data.message || JSON.stringify(data)}`,
          );
      } catch (err) {
        results.push(`${name} → Request failed: ${err.message}`);
      }
    }
    responseDiv.textContent = results.join("\n\n");
  });
}

// ---- Add container button ----
const addBtn = document.getElementById("addBtn");
if (addBtn) {
  addBtn.onclick = async () => {
    await fetch("/api/containers/add", { method: "POST" });
  };
}

// ---- Hide context menus ----
document.addEventListener("click", () => {
  document
    .querySelectorAll(".context-menu")
    .forEach((m) => (m.style.display = "none"));
});

// ---- Start polling containers ----
setInterval(fetchContainers, 1000);
fetchContainers();

const backgroundDiv = document.querySelector(".background");
const fileInput = document.getElementById("imageInput");
const resetBtn = document.getElementById("resetBackgroundBtn");

function refreshBackground() {
  const newImageUrl = `/background?ts=${Date.now()}`;
  backgroundDiv.style.backgroundImage = `url('${newImageUrl}')`;
}

refreshBackground();

fileInput.addEventListener("change", async (event) => {
  const file = event.target.files[0];
  if (!file) return;

  if (!file.type.startsWith("image/")) {
    alert("Please upload an image file.");
    return;
  }

  const formData = new FormData();
  formData.append("background", file);

  try {
    const response = await fetch("/api/ui/background/change", {
      method: "POST",
      body: formData,
    });

    if (!response.ok) throw new Error("Upload failed");

    console.log("Background updated");
  } catch (err) {
    console.error("Error uploading background:", err);
  }

  fileInput.value = "";

  setTimeout(refreshBackground, 250);
});

resetBtn.addEventListener("click", async () => {
  try {
    const res = await fetch("/api/ui/background/reset", { method: "POST" });
    if (!res.ok) throw new Error("Reset failed");

    console.log("Background reset");
  } catch (err) {
    console.error(err);
  }

  setTimeout(refreshBackground, 250);
});
