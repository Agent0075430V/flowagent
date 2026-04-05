const els = {
  apiStatus: document.getElementById("apiStatus"),
  userId: document.getElementById("userId"),
  saveUserBtn: document.getElementById("saveUserBtn"),
  connectCalendarBtn: document.getElementById("connectCalendarBtn"),
  chatLog: document.getElementById("chatLog"),
  chatForm: document.getElementById("chatForm"),
  messageInput: document.getElementById("messageInput"),
  confirmBar: document.getElementById("confirmBar"),
  confirmActionBtn: document.getElementById("confirmActionBtn"),
  taskForm: document.getElementById("taskForm"),
  taskTitle: document.getElementById("taskTitle"),
  taskPriority: document.getElementById("taskPriority"),
  taskTag: document.getElementById("taskTag"),
  taskList: document.getElementById("taskList"),
  refreshTasksBtn: document.getElementById("refreshTasksBtn"),
  taskItemTemplate: document.getElementById("taskItemTemplate"),
};

let pendingAction = null;

function getUserId() {
  return els.userId.value.trim();
}

function saveUserId() {
  const userId = getUserId();
  if (!userId) {
    alert("Enter a user ID first.");
    return;
  }
  localStorage.setItem("flowagent.userId", userId);
  pushBot(`Saved user ID: ${userId}`);
}

function loadUserId() {
  const saved = localStorage.getItem("flowagent.userId");
  if (saved) {
    els.userId.value = saved;
  }
}

function pushMessage(text, kind) {
  const div = document.createElement("div");
  div.className = `msg ${kind}`;
  div.textContent = text;
  els.chatLog.appendChild(div);
  els.chatLog.scrollTop = els.chatLog.scrollHeight;
}

function pushUser(text) {
  pushMessage(text, "user");
}

function pushBot(text) {
  pushMessage(text, "bot");
}

async function checkHealth() {
  try {
    const res = await fetch("/health");
    if (!res.ok) {
      throw new Error("Health check failed");
    }
    const data = await res.json();
    els.apiStatus.textContent = `API: ${data.ok ? "Online" : "Issue"}`;
  } catch {
    els.apiStatus.textContent = "API: Offline";
  }
}

async function connectCalendar() {
  const userId = getUserId();
  if (!userId) {
    alert("Enter a user ID first.");
    return;
  }

  const res = await fetch(`/auth/url?user_id=${encodeURIComponent(userId)}`);
  const data = await res.json();
  if (!res.ok) {
    alert(data.detail || "Unable to start auth flow.");
    return;
  }
  window.location.href = data.auth_url;
}

async function sendMessage(event) {
  event.preventDefault();
  const userId = getUserId();
  const message = els.messageInput.value.trim();

  if (!userId || !message) {
    alert("Enter user ID and message.");
    return;
  }

  pushUser(message);
  els.messageInput.value = "";

  try {
    const res = await fetch("/flow/message", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: userId, message }),
    });
    const data = await res.json();
    if (!res.ok) {
      pushBot(data.detail || "Something went wrong.");
      return;
    }

    pushBot(data.response);
    if (data.requires_confirmation) {
      pendingAction = data.proposed_action;
      els.confirmBar.classList.remove("hidden");
    } else {
      pendingAction = null;
      els.confirmBar.classList.add("hidden");
    }
  } catch {
    pushBot("Unable to reach API.");
  }
}

async function confirmPendingAction() {
  const userId = getUserId();
  if (!userId || !pendingAction) {
    return;
  }

  const res = await fetch("/flow/confirm", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      user_id: userId,
      action: pendingAction,
    }),
  });

  const data = await res.json();
  if (!res.ok) {
    pushBot(data.detail || "Confirmation failed.");
    return;
  }

  pushBot(data.message || "Action completed.");
  pendingAction = null;
  els.confirmBar.classList.add("hidden");
  await loadTasks();
}

function renderTasks(tasks) {
  els.taskList.innerHTML = "";

  if (!tasks.length) {
    const empty = document.createElement("li");
    empty.className = "task-item";
    empty.innerHTML = "<p class='task-title'>No pending tasks</p>";
    els.taskList.appendChild(empty);
    return;
  }

  for (const task of tasks) {
    const node = els.taskItemTemplate.content.firstElementChild.cloneNode(true);
    node.querySelector(".task-title").textContent = task.title;
    node.querySelector(".task-meta").textContent = `${task.priority} • ${task.tag}`;

    node.querySelector("[data-action='complete']").addEventListener("click", () => completeTask(task.id));
    node.querySelector("[data-action='delete']").addEventListener("click", () => deleteTask(task.id));

    els.taskList.appendChild(node);
  }
}

async function loadTasks() {
  const userId = getUserId();
  if (!userId) {
    return;
  }

  const res = await fetch(`/users/${encodeURIComponent(userId)}/tasks?status=pending`);
  const data = await res.json();
  if (!res.ok) {
    pushBot(data.detail || "Could not load tasks.");
    return;
  }

  renderTasks(data);
}

async function createTask(event) {
  event.preventDefault();
  const userId = getUserId();
  const title = els.taskTitle.value.trim();
  if (!userId || !title) {
    alert("Enter user ID and task title.");
    return;
  }

  const payload = {
    title,
    priority: els.taskPriority.value,
    tag: els.taskTag.value,
    estimated_minutes: 60,
  };

  const res = await fetch(`/users/${encodeURIComponent(userId)}/tasks`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  const data = await res.json();
  if (!res.ok) {
    pushBot(data.detail || "Failed to create task.");
    return;
  }

  els.taskTitle.value = "";
  pushBot(`Added task: ${data.title}`);
  await loadTasks();
}

async function completeTask(taskId) {
  const userId = getUserId();
  if (!userId) {
    return;
  }

  const res = await fetch(`/users/${encodeURIComponent(userId)}/tasks/${encodeURIComponent(taskId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status: "completed" }),
  });

  const data = await res.json();
  if (!res.ok) {
    pushBot(data.detail || "Unable to mark task complete.");
    return;
  }

  pushBot(`Completed: ${data.title}`);
  await loadTasks();
}

async function deleteTask(taskId) {
  const userId = getUserId();
  if (!userId) {
    return;
  }

  const res = await fetch(`/users/${encodeURIComponent(userId)}/tasks/${encodeURIComponent(taskId)}`, {
    method: "DELETE",
  });

  const data = await res.json();
  if (!res.ok) {
    pushBot(data.detail || "Unable to delete task.");
    return;
  }

  pushBot("Task deleted.");
  await loadTasks();
}

function wireEvents() {
  els.saveUserBtn.addEventListener("click", saveUserId);
  els.connectCalendarBtn.addEventListener("click", connectCalendar);
  els.chatForm.addEventListener("submit", sendMessage);
  els.confirmActionBtn.addEventListener("click", confirmPendingAction);
  els.taskForm.addEventListener("submit", createTask);
  els.refreshTasksBtn.addEventListener("click", loadTasks);
}

async function boot() {
  loadUserId();
  wireEvents();
  await checkHealth();
  await loadTasks();
  pushBot("FlowAgent is ready. Ask me to schedule, optimize, or manage tasks.");
}

boot();
