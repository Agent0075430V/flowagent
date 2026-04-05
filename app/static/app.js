const PAGE = document.body?.dataset.page || "landing";

const STORAGE_KEYS = {
  accessToken: "flowagent.accessToken",
  currentUser: "flowagent.currentUser",
};

function getAccessToken() {
  return localStorage.getItem(STORAGE_KEYS.accessToken) || "";
}

function getCurrentUser() {
  const raw = localStorage.getItem(STORAGE_KEYS.currentUser);
  if (!raw) {
    return null;
  }
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function setCurrentUserSession(data) {
  localStorage.setItem(STORAGE_KEYS.accessToken, data.access_token || "");
  localStorage.setItem(
    STORAGE_KEYS.currentUser,
    JSON.stringify({ user_id: data.user_id, email: data.email })
  );
}

function clearCurrentUserSession() {
  localStorage.removeItem(STORAGE_KEYS.accessToken);
  localStorage.removeItem(STORAGE_KEYS.currentUser);
}

function navigateTo(path) {
  if (!path) {
    return;
  }

  if (!document.body) {
    window.location.href = path;
    return;
  }

  document.body.classList.add("page-leave");
  setTimeout(() => {
    window.location.href = path;
  }, 170);
}

function enablePageTransitions() {
  if (!document.body) {
    return;
  }
  requestAnimationFrame(() => {
    document.body.classList.add("page-ready");
  });
}

async function apiFetch(url, options = {}) {
  const headers = { ...(options.headers || {}) };
  const token = getAccessToken();
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  const response = await fetch(url, { ...options, headers });
  const isAuthEndpoint = url.startsWith("/auth/login") || url.startsWith("/auth/signup");
  if (response.status === 401 && !isAuthEndpoint) {
    clearCurrentUserSession();
  }
  return response;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function parseQueryMode() {
  const params = new URLSearchParams(window.location.search);
  const mode = (params.get("mode") || "").toLowerCase();
  return mode === "signup" ? "signup" : "login";
}

async function readApiPayload(response) {
  const raw = await response.text();
  if (!raw) {
    return {};
  }

  try {
    return JSON.parse(raw);
  } catch {
    return { detail: raw };
  }
}

function initLandingPage() {
  const signupLink = document.getElementById("goSignupBtn");
  const loginLink = document.getElementById("goLoginBtn");

  if (signupLink) {
    signupLink.addEventListener("click", (event) => {
      event.preventDefault();
      navigateTo(signupLink.getAttribute("href") || "/static/auth.html?mode=signup");
    });
  }
  if (loginLink) {
    loginLink.addEventListener("click", (event) => {
      if ((loginLink.getAttribute("href") || "").startsWith("#")) {
        return;
      }
      event.preventDefault();
      navigateTo(loginLink.getAttribute("href") || "/static/auth.html?mode=login");
    });
  }

  const user = getCurrentUser();
  if (user?.email) {
    if (signupLink) {
      signupLink.textContent = "Open Dashboard";
      signupLink.href = "/static/dashboard.html";
    }
    if (loginLink) {
      loginLink.textContent = "Log Out";
      loginLink.href = "#";
      loginLink.addEventListener("click", (event) => {
        event.preventDefault();
        clearCurrentUserSession();
        window.location.reload();
      });
    }
  }
}

function initAuthPage() {
  if (getAccessToken()) {
    navigateTo("/static/dashboard.html");
    return;
  }

  const backHomeLink = document.querySelector(".back-home");
  if (backHomeLink) {
    backHomeLink.addEventListener("click", (event) => {
      event.preventDefault();
      navigateTo(backHomeLink.getAttribute("href") || "/");
    });
  }

  const authForm = document.getElementById("authForm");
  const authMessage = document.getElementById("authMessage");
  const authSubmitBtn = document.getElementById("authSubmitBtn");
  const authEmail = document.getElementById("authEmail");
  const authPassword = document.getElementById("authPassword");
  const authConfirmPassword = document.getElementById("authConfirmPassword");
  const confirmWrap = document.getElementById("confirmPasswordWrap");
  const tabs = Array.from(document.querySelectorAll(".auth-tab"));

  let mode = parseQueryMode();

  const setMode = (nextMode) => {
    mode = nextMode;
    tabs.forEach((tab) => {
      tab.classList.toggle("active", tab.dataset.authMode === mode);
    });

    const isSignup = mode === "signup";
    if (confirmWrap) {
      confirmWrap.classList.toggle("hidden", !isSignup);
    }
    if (authConfirmPassword) {
      authConfirmPassword.required = isSignup;
      if (!isSignup) {
        authConfirmPassword.value = "";
      }
    }
    if (authSubmitBtn) {
      authSubmitBtn.textContent = isSignup ? "Sign Up" : "Log In";
    }
    if (authMessage) {
      authMessage.textContent = "";
      authMessage.className = "auth-message";
    }
  };

  tabs.forEach((tab) => {
    tab.addEventListener("click", () => setMode(tab.dataset.authMode || "login"));
  });

  if (!authForm || !authEmail || !authPassword) {
    return;
  }

  authForm.addEventListener("submit", async (event) => {
    event.preventDefault();

    const email = (authEmail.value || "").trim();
    const password = (authPassword.value || "").trim();

    if (!email || !password) {
      if (authMessage) {
        authMessage.textContent = "Please enter email and password.";
        authMessage.className = "auth-message error";
      }
      return;
    }

    if (mode === "signup") {
      const confirmValue = (authConfirmPassword?.value || "").trim();
      if (password !== confirmValue) {
        if (authMessage) {
          authMessage.textContent = "Passwords do not match.";
          authMessage.className = "auth-message error";
        }
        return;
      }
    }

    try {
      const endpoint = mode === "signup" ? "/auth/signup" : "/auth/login";
      const response = await apiFetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      const data = await readApiPayload(response);

      if (!response.ok) {
        if (authMessage) {
          authMessage.textContent = data.detail || `Authentication failed (${response.status}).`;
          authMessage.className = "auth-message error";
        }
        return;
      }

      setCurrentUserSession(data);
      if (authMessage) {
        authMessage.textContent = mode === "signup" ? "Account created. Redirecting..." : "Logged in. Redirecting...";
        authMessage.className = "auth-message success";
      }
      setTimeout(() => navigateTo("/static/dashboard.html"), 450);
    } catch {
      if (authMessage) {
        authMessage.textContent = "Unable to reach the API.";
        authMessage.className = "auth-message error";
      }
    }
  });

  setMode(mode);
}

function initDashboardPage() {
  if (!getAccessToken()) {
    navigateTo("/static/auth.html?mode=login");
    return;
  }

  const els = {
    apiStatus: document.getElementById("apiStatus"),
    userAvatar: document.getElementById("userAvatar"),
    userName: document.getElementById("userName"),
    userEmail: document.getElementById("userEmail"),
    calendarStatusPill: document.getElementById("calendarStatusPill"),
    logoutBtn: document.getElementById("logoutBtn"),
    calendarConnectWrap: document.getElementById("calendarConnectWrap"),
    connectCalendarBtn: document.getElementById("connectCalendarBtn"),
    taskForm: document.getElementById("taskForm"),
    taskTitle: document.getElementById("taskTitle"),
    taskPriority: document.getElementById("taskPriority"),
    taskTag: document.getElementById("taskTag"),
    refreshTasksBtn: document.getElementById("refreshTasksBtn"),
    taskList: document.getElementById("taskList"),
    calendarMonthLabel: document.getElementById("calendarMonthLabel"),
    calDays: document.getElementById("calDays"),
    freeSlots: document.getElementById("freeSlots"),
    scheduleTitle: document.getElementById("scheduleTitle"),
    timeline: document.getElementById("timeline"),
    addEventBtn: document.getElementById("addEventBtn"),
    viewTabs: document.querySelectorAll(".view-tab"),
    chatLog: document.getElementById("chatLog"),
    quickChips: document.getElementById("quickChips"),
    chatForm: document.getElementById("chatForm"),
    messageInput: document.getElementById("messageInput"),
    confirmBar: document.getElementById("confirmBar"),
    confirmActionBtn: document.getElementById("confirmActionBtn"),
    agentBadges: document.querySelectorAll(".agent-badge"),
  };

  let pendingAction = null;
  let tasksCache = [];
  let timelineEvents = [];
  let calendarConnected = false;

  function setAgentStatus() {
    const states = {
      calendar: calendarConnected,
      task: true,
      optimizer: tasksCache.length > 0,
      scheduling: !!pendingAction,
    };

    els.agentBadges.forEach((badge) => {
      const name = badge.dataset.agent;
      const isActive = !!states[name];
      badge.classList.toggle("active", isActive);
      badge.classList.toggle("inactive", !isActive);
    });
  }

  function addMessage(role, content, isHtml = false) {
    if (!els.chatLog) {
      return;
    }

    const row = document.createElement("div");
    row.className = `msg ${role}`;

    const avatar = role === "ai" ? "FA" : "U";
    const bubble = isHtml ? content : escapeHtml(content).replace(/\n/g, "<br>");

    row.innerHTML = `
      <div class="msg-avatar">${avatar}</div>
      <div class="msg-bubble">${bubble}</div>
    `;

    els.chatLog.appendChild(row);
    els.chatLog.scrollTop = els.chatLog.scrollHeight;
  }

  function addBotMessage(text) {
    addMessage("ai", text);
  }

  function addUserMessage(text) {
    addMessage("user", text);
  }

  function addThinking() {
    addMessage("ai", '<div id="thinking" class="thinking"><span></span><span></span><span></span></div>', true);
  }

  function removeThinking() {
    const thinking = document.getElementById("thinking");
    if (!thinking) {
      return;
    }
    const parent = thinking.closest(".msg");
    if (parent) {
      parent.remove();
    }
  }

  async function checkHealth() {
    if (!els.apiStatus) {
      return;
    }
    try {
      const response = await apiFetch("/health");
      els.apiStatus.textContent = response.ok ? "API online" : "API offline";
    } catch {
      els.apiStatus.textContent = "API offline";
    }
  }

  async function hydrateCurrentUser() {
    try {
      const response = await apiFetch("/auth/me");
      const data = await response.json();
      if (!response.ok) {
        clearCurrentUserSession();
        navigateTo("/static/auth.html?mode=login");
        return;
      }

      const email = data.email || "";
      const firstName = data.first_name || "";
      calendarConnected = !!data.calendar_connected;
      setCurrentUserSession({
        access_token: getAccessToken(),
        user_id: data.user_id,
        email,
      });

      if (els.userEmail) {
        els.userEmail.textContent = email || "-";
      }
      if (els.userName) {
        els.userName.textContent = firstName || (email ? email.split("@")[0] : "FlowAgent User");
      }
      if (els.userAvatar) {
        const source = firstName || email || "FA";
        els.userAvatar.textContent = source.slice(0, 2).toUpperCase();
      }
      if (els.calendarStatusPill) {
        els.calendarStatusPill.classList.toggle("connected", calendarConnected);
        els.calendarStatusPill.classList.toggle("disconnected", !calendarConnected);
        els.calendarStatusPill.textContent = calendarConnected ? "Calendar connected" : "Calendar not connected";
      }
      if (els.calendarConnectWrap) {
        els.calendarConnectWrap.classList.toggle("hidden", calendarConnected);
      }
      setAgentStatus();
    } catch {
      clearCurrentUserSession();
      navigateTo("/static/auth.html?mode=login");
    }
  }

  async function connectCalendar() {
    try {
      const response = await apiFetch("/auth/url");
      const data = await response.json();
      if (!response.ok) {
        addBotMessage(data.detail || "Unable to start calendar auth.");
        return;
      }
      window.location.href = data.auth_url;
    } catch {
      addBotMessage("Unable to reach API.");
    }
  }

  function tagClass(tag, priority) {
    if (priority === "urgent") {
      return "tag-urgent";
    }
    if (tag === "personal") {
      return "tag-personal";
    }
    if (tag === "health") {
      return "tag-health";
    }
    if (tag === "learning") {
      return "tag-learning";
    }
    return "tag-work";
  }

  function renderTasks(tasks) {
    if (!els.taskList) {
      return;
    }

    tasksCache = tasks;
    els.taskList.innerHTML = "";

    if (!tasks.length) {
      const empty = document.createElement("li");
      empty.className = "task-item";
      empty.innerHTML = '<div></div><div class="task-text">No pending tasks</div><div></div>';
      els.taskList.appendChild(empty);
      renderTimeline();
      setAgentStatus();
      return;
    }

    for (const task of tasks) {
      const row = document.createElement("li");
      row.className = "task-item";
      row.innerHTML = `
        <button class="task-check" data-action="complete" data-task-id="${task.id}" title="Mark complete"></button>
        <div class="task-text">${escapeHtml(task.title)} <span class="task-tag ${tagClass(task.tag, task.priority)}">${escapeHtml(task.priority)}</span></div>
        <div class="task-row-actions">
          <button class="tiny-btn" data-action="schedule" data-task-id="${task.id}">Plan</button>
          <button class="tiny-btn danger" data-action="delete" data-task-id="${task.id}">Del</button>
        </div>
      `;
      els.taskList.appendChild(row);
    }

    renderTimeline();
    setAgentStatus();
  }

  async function loadTasks() {
    try {
      const response = await apiFetch("/tasks?status=pending");
      const data = await response.json();
      if (!response.ok) {
        addBotMessage(data.detail || "Could not load tasks.");
        return;
      }
      renderTasks(data);
    } catch {
      addBotMessage("Unable to reach API.");
    }
  }

  async function createTask(event) {
    event.preventDefault();
    const title = (els.taskTitle?.value || "").trim();
    if (!title) {
      alert("Enter a task title.");
      return;
    }

    const response = await apiFetch("/tasks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title,
        priority: els.taskPriority?.value || "medium",
        tag: els.taskTag?.value || "work",
        estimated_minutes: 60,
      }),
    });

    const data = await response.json();
    if (!response.ok) {
      addBotMessage(data.detail || "Failed to create task.");
      return;
    }

    if (els.taskTitle) {
      els.taskTitle.value = "";
    }
    addBotMessage(`Added task: ${data.title}`);
    await loadTasks();
  }

  async function completeTask(taskId) {
    const response = await apiFetch(`/tasks/${encodeURIComponent(taskId)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: "completed" }),
    });

    const data = await response.json();
    if (!response.ok) {
      addBotMessage(data.detail || "Could not mark task complete.");
      return;
    }

    addBotMessage(`Completed: ${data.title}`);
    await loadTasks();
  }

  async function deleteTask(taskId) {
    const response = await apiFetch(`/tasks/${encodeURIComponent(taskId)}`, {
      method: "DELETE",
    });

    const data = await response.json();
    if (!response.ok) {
      addBotMessage(data.detail || "Could not delete task.");
      return;
    }

    addBotMessage("Task deleted.");
    await loadTasks();
  }

  function timeRows() {
    const rows = [];
    for (let hour = 9; hour <= 19; hour += 1) {
      const display = hour === 12 ? "12 PM" : hour > 12 ? `${hour - 12} PM` : `${hour} AM`;
      rows.push({ hour, label: display, events: [] });
    }
    return rows;
  }

  function deriveEventsFromTasks() {
    const rows = timeRows();
    const baseHours = [10, 13, 16, 18];
    const blocks = tasksCache.slice(0, 4);

    for (let index = 0; index < blocks.length; index += 1) {
      const task = blocks[index];
      const row = rows.find((item) => item.hour === baseHours[index]);
      if (!row) {
        continue;
      }

      let cssClass = "ev-work";
      if (task.tag === "personal") {
        cssClass = "ev-personal";
      } else if (task.tag === "health") {
        cssClass = "ev-free";
      } else if (task.tag === "learning") {
        cssClass = "ev-focus";
      }

      row.events.push({
        title: task.title,
        sub: `${task.priority} priority • ${task.tag}`,
        cls: cssClass,
      });
    }

    return rows;
  }

  function renderTimeline() {
    if (!els.timeline) {
      return;
    }

    const rows = timelineEvents.length ? timelineEvents : deriveEventsFromTasks();
    const hasEvents = rows.some((row) => row.events.length > 0);

    if (!hasEvents) {
      els.timeline.innerHTML = '<div class="timeline-empty">No events yet — connect your calendar to get started</div>';
      return;
    }

    els.timeline.innerHTML = rows
      .map(
        (row) => `
          <div class="time-row">
            <div class="time-label">${row.label}</div>
            <div class="time-slot">
              ${row.events
                .map(
                  (event) =>
                    `<div class="event-block ${event.cls}"><div class="ev-title">${escapeHtml(event.title)}</div><div class="ev-sub">${escapeHtml(event.sub)}</div></div>`
                )
                .join("")}
            </div>
          </div>
        `
      )
      .join("");
  }

  function buildCalendar() {
    if (!els.calendarMonthLabel || !els.calDays || !els.scheduleTitle) {
      return;
    }

    const now = new Date();
    const year = now.getFullYear();
    const month = now.getMonth();

    els.calendarMonthLabel.textContent = now.toLocaleString("en-IN", {
      month: "long",
      year: "numeric",
    });

    const firstDay = new Date(year, month, 1);
    const startOffset = firstDay.getDay();
    const daysInMonth = new Date(year, month + 1, 0).getDate();
    const prevMonthDays = new Date(year, month, 0).getDate();

    let html = "";
    for (let i = startOffset - 1; i >= 0; i -= 1) {
      html += `<div class="cal-day other-month">${prevMonthDays - i}</div>`;
    }

    for (let day = 1; day <= daysInMonth; day += 1) {
      const cssClass = day === now.getDate() ? "today" : "";
      html += `<div class="cal-day ${cssClass}">${day}</div>`;
    }

    const currentCount = (html.match(/cal-day/g) || []).length;
    const missing = (7 - (currentCount % 7)) % 7;
    for (let i = 0; i < missing; i += 1) {
      html += '<div class="cal-day other-month"></div>';
    }

    els.calDays.innerHTML = html;
    els.scheduleTitle.textContent = now.toLocaleString("en-IN", {
      weekday: "long",
      month: "long",
      day: "numeric",
    });
  }

  function renderFreeSlotsFromText(text) {
    if (!els.freeSlots) {
      return;
    }

    const matches = [
      ...text.matchAll(/(\d{1,2}:\d{2}\s?[APMapm]{2})\s*(?:to|-|–)\s*(\d{1,2}:\d{2}\s?[APMapm]{2})/g),
    ];

    if (!matches.length) {
      els.freeSlots.innerHTML = '<div class="free-slot"><div class="slot-dot busy"></div><div class="slot-text">Ask "When am I free?" to load availability.</div></div>';
      return;
    }

    els.freeSlots.innerHTML = matches
      .slice(0, 6)
      .map(
        (match) =>
          `<div class="free-slot"><div class="slot-dot free"></div><div class="slot-text">${escapeHtml(match[1])} - ${escapeHtml(match[2])}</div></div>`
      )
      .join("");
  }

  async function refreshAvailability() {
    const response = await apiFetch("/flow/message", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: "When am I free today?" }),
    });

    const data = await response.json();
    if (response.ok && data.response) {
      renderFreeSlotsFromText(data.response);
    }
  }

  async function confirmPendingAction() {
    if (!pendingAction) {
      return;
    }

    const response = await apiFetch("/flow/confirm", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: pendingAction }),
    });

    const data = await response.json();
    if (!response.ok) {
      addBotMessage(data.detail || "Failed to confirm action.");
      return;
    }

    addBotMessage(data.message || "Action executed.");
    pendingAction = null;
    if (els.confirmBar) {
      els.confirmBar.classList.add("hidden");
    }
    setAgentStatus();
    await loadTasks();
    await refreshAvailability();
  }

  async function sendMessage(event) {
    event.preventDefault();
    const message = (els.messageInput?.value || "").trim();
    if (!message) {
      return;
    }

    addUserMessage(message);
    if (els.messageInput) {
      els.messageInput.value = "";
    }
    addThinking();

    try {
      const response = await apiFetch("/flow/message", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message }),
      });
      const data = await response.json();
      removeThinking();

      if (!response.ok) {
        addBotMessage(data.detail || "Something went wrong.");
        return;
      }

      addBotMessage(data.response || "Done.");
      renderFreeSlotsFromText(data.response || "");

      if (data.requires_confirmation) {
        pendingAction = data.proposed_action;
        if (els.confirmBar) {
          els.confirmBar.classList.remove("hidden");
        }
      } else {
        pendingAction = null;
        if (els.confirmBar) {
          els.confirmBar.classList.add("hidden");
        }
      }
      setAgentStatus();
    } catch {
      removeThinking();
      addBotMessage("Unable to reach API.");
    }
  }

  function onQuickChip(event) {
    const target = event.target.closest("[data-chip]");
    if (!target || !els.messageInput || !els.chatForm) {
      return;
    }

    els.messageInput.value = target.getAttribute("data-chip") || "";
    els.chatForm.requestSubmit();
  }

  function onTaskListAction(event) {
    const button = event.target.closest("button[data-action]");
    if (!button) {
      return;
    }

    const taskId = button.getAttribute("data-task-id");
    const action = button.getAttribute("data-action");
    if (!taskId || !action) {
      return;
    }

    if (action === "complete") {
      completeTask(taskId);
      return;
    }
    if (action === "delete") {
      deleteTask(taskId);
      return;
    }
    if (action === "schedule") {
      const task = tasksCache.find((entry) => entry.id === taskId);
      if (task && els.messageInput && els.chatForm) {
        els.messageInput.value = `Schedule ${task.title} today`;
        els.chatForm.requestSubmit();
      }
    }
  }

  function switchView(event) {
    const button = event.target.closest(".view-tab");
    if (!button || !els.messageInput || !els.chatForm) {
      return;
    }

    els.viewTabs.forEach((tab) => tab.classList.remove("active"));
    button.classList.add("active");

    const view = button.getAttribute("data-view");
    if (view === "optimal") {
      els.messageInput.value = "Optimize my day";
      els.chatForm.requestSubmit();
      return;
    }
    if (view === "week") {
      els.messageInput.value = "When am I free this week?";
      els.chatForm.requestSubmit();
      return;
    }

    timelineEvents = [];
    renderTimeline();
  }

  function wireEvents() {
    if (els.logoutBtn) {
      els.logoutBtn.addEventListener("click", () => {
        clearCurrentUserSession();
        navigateTo("/static/auth.html?mode=login");
      });
    }
    if (els.connectCalendarBtn) {
      els.connectCalendarBtn.addEventListener("click", connectCalendar);
    }
    if (els.taskForm) {
      els.taskForm.addEventListener("submit", createTask);
    }
    if (els.refreshTasksBtn) {
      els.refreshTasksBtn.addEventListener("click", loadTasks);
    }
    if (els.taskList) {
      els.taskList.addEventListener("click", onTaskListAction);
    }
    if (els.chatForm) {
      els.chatForm.addEventListener("submit", sendMessage);
    }
    if (els.quickChips) {
      els.quickChips.addEventListener("click", onQuickChip);
    }
    if (els.confirmActionBtn) {
      els.confirmActionBtn.addEventListener("click", confirmPendingAction);
    }
    if (els.addEventBtn && els.messageInput && els.chatForm) {
      els.addEventBtn.addEventListener("click", () => {
        els.messageInput.value = "Add a 2pm meeting";
        els.chatForm.requestSubmit();
      });
    }
    els.viewTabs.forEach((tab) => tab.addEventListener("click", switchView));
  }

  async function boot() {
    buildCalendar();
    renderTimeline();
    wireEvents();
    await checkHealth();
    await hydrateCurrentUser();
    await loadTasks();
    await refreshAvailability();
    addBotMessage("FlowAgent is ready. Ask me to optimize your schedule.");
  }

  boot();
}

function routeApp() {
  enablePageTransitions();
  if (PAGE === "auth") {
    initAuthPage();
    return;
  }
  if (PAGE === "dashboard") {
    initDashboardPage();
    return;
  }
  initLandingPage();
}

routeApp();
