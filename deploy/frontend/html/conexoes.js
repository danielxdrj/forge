(function () {
  "use strict";

  const TYPES = [
    { id: "postgres", label: "PostgreSQL" },
    { id: "mysql", label: "MySQL" },
    { id: "ftp", label: "FTP" },
    { id: "sftp", label: "SFTP" },
    { id: "portainer", label: "Portainer" },
  ];
  const TYPE_LABEL = {};
  TYPES.forEach(function (t) { TYPE_LABEL[t.id] = t.label; });

  const WHO_CACHE_KEY = "forge-who";

  function cacheWho(who) {
    try {
      window.sessionStorage.setItem(WHO_CACHE_KEY, JSON.stringify(who));
    } catch (err) {
      /* quota ou modo privado: segue sem cache */
    }
  }

  function readCachedWho() {
    try {
      const raw = window.sessionStorage.getItem(WHO_CACHE_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch (err) {
      return null;
    }
  }

  function clearCachedWho() {
    try {
      window.sessionStorage.removeItem(WHO_CACHE_KEY);
    } catch (err) {
      /* ignore */
    }
  }

  const state = {
    who: readCachedWho(),
    pending: null,
    pollTimer: null,
    enabled: true,
    disabledMessage: "",
    connections: [],
    editing: null,
    form: emptyForm(),
    error: "",
    errorDetail: null,
    notice: "",
    busy: false,
    testResult: null,
    loading: true,
  };

  function emptyForm() {
    return {
      id: "",
      name: "",
      type: "postgres",
      user: "",
      port: "5432",
      database: "",
      path: "",
      secret: "",
      preferred_index: 0,
      hosts: [{ label: "principal", host: "", order: 0 }],
    };
  }

  function csrfToken() {
    const parts = document.cookie.split(";");
    for (let i = 0; i < parts.length; i += 1) {
      const part = parts[i].trim();
      if (part.startsWith("forge_csrf=")) {
        return decodeURIComponent(part.slice("forge_csrf=".length));
      }
    }
    return "";
  }

  function el(tag, attrs, children) {
    const node = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (key) {
        const value = attrs[key];
        if (value === null || value === undefined || value === false) {
          return;
        }
        if (key === "text") {
          node.textContent = value;
          return;
        }
        if (key.slice(0, 2) === "on" && typeof value === "function") {
          node.addEventListener(key.slice(2).toLowerCase(), value);
          return;
        }
        node.setAttribute(key, value === true ? "" : String(value));
      });
    }
    (children || []).forEach(function (child) {
      if (child) {
        node.appendChild(child);
      }
    });
    return node;
  }

  async function api(path, options) {
    const opts = options || {};
    const headers = Object.assign({}, opts.headers || {});
    if (opts.method && opts.method !== "GET") {
      headers["X-CSRF-Token"] = csrfToken();
      headers["Content-Type"] = "application/json";
    }
    const response = await fetch(path, {
      method: opts.method || "GET",
      credentials: "same-origin",
      headers: headers,
      body: opts.body ? JSON.stringify(opts.body) : undefined,
    });
    const text = await response.text();
    let data = {};
    if (text) {
      try {
        data = JSON.parse(text);
      } catch (err) {
        data = { error: "http_" + response.status };
      }
    }
    return { ok: response.ok, status: response.status, data: data };
  }

  function isOwner() {
    return !!(state.who && Array.isArray(state.who.roles) && state.who.roles.indexOf("owner") !== -1);
  }

  function isReader() {
    if (!state.who || !Array.isArray(state.who.roles)) {
      return false;
    }
    return state.who.roles.indexOf("editor") !== -1 || state.who.roles.indexOf("owner") !== -1;
  }

  function errorMessage(code, detail) {
    const map = {
      csrf: "CSRF recusado. Recarregue a página.",
      forbidden: "Sem permissão. Criar/editar/apagar exige owner; listar e testar exige editor ou owner.",
      invalid_session: "Sessão inválida. Entre de novo.",
      vault_disabled: "Área Conexões desligada: falta a chave de cifração.",
      vault_invalid: "Chave de cifração inválida. Gere outra e recadastre os segredos.",
      vault_unavailable: "Biblioteca de cifração ausente no backend.",
      not_found: "Conexão não encontrada.",
      invalid_name: "Informe um nome.",
      invalid_type: "Tipo inválido.",
      invalid_user: "Informe o usuário.",
      invalid_port: "Porta inválida.",
      invalid_hosts: "Informe ao menos um host.",
      invalid_host: "Host inválido (sem URL, usuário ou caminho).",
      invalid_host_label: "Cada host precisa de um rótulo.",
      invalid_preferred: "Host preferido inválido.",
      invalid_secret: "Segredo inválido.",
      denied: "Autorização negada no GitHub.",
      expired: "O código expirou. Comece de novo.",
      api_unreachable: "Não foi possível falar com a API. Recarregue a página.",
    };
    let text = map[code] || (detail && detail.message) || code;
    if (detail && detail.hint) {
      text += " " + detail.hint;
    }
    return text;
  }

  function setError(code, detail) {
    state.error = code || "";
    state.errorDetail = detail || null;
    render();
  }

  async function loadWhoami() {
    const res = await api("/api/auth/whoami");
    if (res.status === 401) {
      state.who = null;
      clearCachedWho();
      return;
    }
    if (res.ok) {
      state.who = res.data;
      cacheWho(res.data);
    }
  }

  async function startLogin() {
    state.error = "";
    const res = await api("/api/auth/login/start", { method: "POST", body: {} });
    if (!res.ok) {
      setError((res.data && res.data.error) || "error", res.data);
      return;
    }
    state.pending = res.data;
    render();
    startPoll();
  }

  function startPoll() {
    stopPoll();
    state.pollTimer = window.setInterval(async function () {
      const res = await api("/api/auth/login/status");
      if (!res.ok) {
        return;
      }
      if (res.data.status === "authorized") {
        stopPoll();
        state.pending = null;
        await afterLogin();
        return;
      }
      if (res.data.status === "pending") {
        state.pending = res.data;
        render();
        return;
      }
      stopPoll();
      state.pending = null;
      setError(res.data.status || "login", res.data);
    }, 2000);
  }

  function stopPoll() {
    if (state.pollTimer) {
      window.clearInterval(state.pollTimer);
      state.pollTimer = null;
    }
  }

  async function afterLogin() {
    await loadWhoami();
    render();
    if (isReader()) {
      await loadConnections();
      render();
    }
  }

  async function logout() {
    await api("/api/auth/logout", { method: "POST", body: {} });
    stopPoll();
    state.who = null;
    clearCachedWho();
    state.pending = null;
    state.connections = [];
    render();
  }

  async function loadConnections() {
    const res = await api("/api/connections");
    if (res.status === 401) {
      state.who = null;
      return;
    }
    if (res.status === 403) {
      state.enabled = true;
      state.connections = [];
      state.error = "forbidden";
      state.errorDetail = res.data;
      return;
    }
    if (!res.ok && res.data && (res.data.error === "vault_disabled" || res.data.error === "vault_invalid")) {
      state.enabled = false;
      state.disabledMessage = res.data.message || errorMessage(res.data.error, res.data);
      state.connections = [];
      return;
    }
    if (res.data && res.data.enabled === false) {
      state.enabled = false;
      state.disabledMessage = res.data.message || errorMessage(res.data.error, res.data);
      state.connections = [];
      return;
    }
    if (!res.ok) {
      state.error = (res.data && res.data.error) || "error";
      state.errorDetail = res.data;
      return;
    }
    state.enabled = true;
    state.disabledMessage = "";
    state.connections = res.data.connections || [];
  }

  function readForm() {
    const typeEl = document.getElementById("conn-type");
    const hosts = [];
    const rows = document.querySelectorAll(".host-row");
    rows.forEach(function (row, idx) {
      const label = row.querySelector("[data-host=label]");
      const host = row.querySelector("[data-host=host]");
      const order = row.querySelector("[data-host=order]");
      hosts.push({
        label: label ? label.value : "",
        host: host ? host.value : "",
        order: order ? Number(order.value || idx) : idx,
      });
    });
    const pref = document.getElementById("conn-preferred");
    const secretEl = document.getElementById("conn-secret");
    return {
      id: state.form.id,
      name: (document.getElementById("conn-name") || {}).value || "",
      type: typeEl ? typeEl.value : state.form.type,
      user: (document.getElementById("conn-user") || {}).value || "",
      port: (document.getElementById("conn-port") || {}).value || "",
      database: (document.getElementById("conn-database") || {}).value || "",
      path: (document.getElementById("conn-path") || {}).value || "",
      secret: secretEl ? secretEl.value : "",
      preferred_index: pref ? Number(pref.value || 0) : 0,
      hosts: hosts.length ? hosts : state.form.hosts,
    };
  }

  function payloadFromForm(form) {
    const body = {
      name: form.name,
      type: form.type,
      user: form.user,
      port: Number(form.port),
      hosts: form.hosts,
      preferred_index: form.preferred_index,
    };
    if (form.type === "mysql" || form.type === "postgres") {
      body.database = form.database;
    }
    if (form.type === "ftp" || form.type === "sftp") {
      body.path = form.path;
    }
    if (form.secret) {
      body.secret = form.secret;
    }
    return body;
  }

  function fillForm(conn) {
    state.form = {
      id: conn.id,
      name: conn.name,
      type: conn.type,
      user: conn.user,
      port: String(conn.port),
      database: conn.database || "",
      path: conn.path || "",
      secret: "",
      preferred_index: Math.max(0, (conn.hosts || []).findIndex(function (h) { return h.id === conn.preferred_host_id; })),
      hosts: (conn.hosts || []).map(function (h) {
        return { label: h.label, host: h.host, order: h.order };
      }),
    };
    if (!state.form.hosts.length) {
      state.form.hosts = [{ label: "principal", host: "", order: 0 }];
    }
    state.editing = conn.id;
    state.testResult = null;
  }

  async function saveConnection() {
    if (!isOwner()) {
      return;
    }
    const form = readForm();
    state.form = form;
    state.busy = true;
    state.error = "";
    state.notice = "";
    render();
    const body = payloadFromForm(form);
    const path = form.id ? "/api/connections/" + encodeURIComponent(form.id) : "/api/connections";
    const res = await api(path, { method: "POST", body: body });
    state.busy = false;
    if (!res.ok) {
      setError((res.data && res.data.error) || "error", res.data);
      return;
    }
    state.notice = form.id ? "Conexão atualizada. O segredo não é exibido." : "Conexão criada. O segredo não é exibido.";
    fillForm(res.data);
    await loadConnections();
    render();
  }

  async function deleteConnection(id) {
    if (!isOwner()) {
      return;
    }
    state.busy = true;
    state.error = "";
    render();
    const res = await api("/api/connections/" + encodeURIComponent(id) + "/delete", { method: "POST", body: {} });
    state.busy = false;
    if (!res.ok) {
      setError((res.data && res.data.error) || "error", res.data);
      return;
    }
    if (state.form.id === id) {
      state.form = emptyForm();
      state.editing = null;
    }
    state.notice = "Conexão removida.";
    await loadConnections();
    render();
  }

  async function testConnection(id) {
    state.busy = true;
    state.error = "";
    state.testResult = null;
    render();
    const res = await api("/api/connections/" + encodeURIComponent(id) + "/test", { method: "POST", body: {} });
    state.busy = false;
    if (!res.ok) {
      setError((res.data && res.data.error) || "error", res.data);
      return;
    }
    state.testResult = res.data;
    render();
  }

  function renderNav() {
    document.querySelectorAll("[data-nav]").forEach(function (link) {
      link.classList.toggle("current", link.getAttribute("data-nav") === "conexoes");
    });
    const conn = document.getElementById("nav-conexoes");
    if (conn) {
      if (isOwner()) {
        conn.removeAttribute("hidden");
      } else {
        conn.setAttribute("hidden", "");
      }
    }
    const agentes = document.getElementById("nav-agentes");
    if (agentes) {
      if (isReader()) {
        agentes.removeAttribute("hidden");
      } else {
        agentes.setAttribute("hidden", "");
      }
    }
  }

  function pageHeader(eyebrow, title, subtitle) {
    return el("header", { class: "page-header" }, [
      el("p", { class: "page-eyebrow", text: eyebrow }),
      el("h2", { class: "page-title", text: title }),
      subtitle ? el("p", { class: "page-subtitle", text: subtitle }) : null,
    ]);
  }

  function readonlySeal() {
    return el("p", { class: "banner banner-info seal-readonly" }, [
      el("span", { class: "pill pill-ok", text: "SOMENTE LEITURA" }),
      el("span", { text: "Agentes não alteram dados nem recebem suas credenciais de escrita." }),
    ]);
  }

  function rolePill(role) {
    return el("span", { class: "pill pill-role pill-role-" + role, text: role });
  }

  function typePill(type) {
    const map = {
      postgres: "core",
      mysql: "core",
      ftp: "ops",
      sftp: "ops",
      portainer: "ops",
    };
    return el("span", { class: "pill pill-" + (map[type] || "muted"), text: TYPE_LABEL[type] || type });
  }

  function renderSession(target) {
    target.replaceChildren();
    if (state.who) {
      target.appendChild(el("span", { class: "session-login", text: state.who.login }));
      const roles = (state.who.roles || []).map(rolePill);
      if (!roles.length) {
        roles.push(el("span", { class: "pill pill-muted", text: "nenhum" }));
      }
      target.appendChild(el("span", { class: "session-roles" }, roles));
      target.appendChild(el("button", { type: "button", class: "btn-sair", text: "Sair", onClick: function () { logout(); } }));
      return;
    }
    target.appendChild(el("span", { class: "muted", text: "Não autenticado" }));
  }

  function renderLogin(root) {
    const box = el("section", { class: "card card-core" }, [
      el("div", { class: "card-head" }, [
        el("span", { class: "icon-box icon-core", text: "F" }),
        el("h2", { text: "Entrar" }),
        el("span", { class: "pill pill-existing", text: "INTEGRAÇÃO EXISTENTE" }),
      ]),
    ]);
    if (state.pending && state.pending.user_code) {
      box.appendChild(el("p", { text: "Abra o GitHub e informe o código:" }));
      box.appendChild(el("p", { class: "code login-code", text: state.pending.user_code }));
      box.appendChild(el("p", { class: "muted", text: "Aguardando autorização no GitHub…" }));
    } else {
      box.appendChild(el("button", {
        type: "button",
        class: "primary",
        text: "Entrar com GitHub",
        onClick: function () { startLogin(); },
      }));
    }
    root.appendChild(box);
  }

  function defaultPort(type) {
    return { postgres: "5432", mysql: "3306", ftp: "21", sftp: "22", portainer: "9000" }[type] || "";
  }

  function addHostRow() {
    state.form = readForm();
    state.form.hosts.push({ label: "host " + (state.form.hosts.length + 1), host: "", order: state.form.hosts.length });
    render();
  }

  function removeHostRow(index) {
    state.form = readForm();
    if (state.form.hosts.length <= 1) {
      return;
    }
    state.form.hosts.splice(index, 1);
    if (state.form.preferred_index >= state.form.hosts.length) {
      state.form.preferred_index = 0;
    }
    render();
  }

  function snapshotForm() {
    if (!document.getElementById("conn-name")) {
      return;
    }
    state.form = readForm();
  }

  function renderForm(root) {
    const form = el("section", { class: "card card-ops" }, [
      el("div", { class: "card-head" }, [
        el("span", { class: "icon-box icon-ops", text: "D" }),
        el("h2", { text: state.form.id ? "Editar conexão" : "Nova conexão" }),
        el("span", { class: "pill pill-ops", text: "OPERAÇÕES" }),
      ]),
    ]);
    if (!isOwner()) {
      form.appendChild(el("p", { class: "muted", text: "Só o papel owner cria, edita ou apaga conexões." }));
      root.appendChild(form);
      return;
    }
    form.appendChild(el("label", { text: "Nome", for: "conn-name" }));
    form.appendChild(el("input", { id: "conn-name", type: "text", value: state.form.name }));
    form.appendChild(el("label", { text: "Tipo", for: "conn-type" }));
    const typeSel = el("select", { id: "conn-type", onChange: function () {
      state.form = readForm();
      if (!state.form.id) {
        state.form.port = defaultPort(state.form.type);
      }
      render();
    } });
    TYPES.forEach(function (t) {
      const opt = el("option", { value: t.id, text: t.label });
      if (t.id === state.form.type) {
        opt.selected = true;
      }
      typeSel.appendChild(opt);
    });
    form.appendChild(typeSel);
    form.appendChild(el("label", { text: "Usuário", for: "conn-user" }));
    form.appendChild(el("input", { id: "conn-user", type: "text", value: state.form.user, autocomplete: "off" }));
    form.appendChild(el("label", { text: "Porta", for: "conn-port" }));
    form.appendChild(el("input", { id: "conn-port", type: "text", value: state.form.port }));
    if (state.form.type === "mysql" || state.form.type === "postgres") {
      form.appendChild(el("label", { text: "Banco", for: "conn-database" }));
      form.appendChild(el("input", { id: "conn-database", type: "text", value: state.form.database }));
    }
    if (state.form.type === "ftp" || state.form.type === "sftp") {
      form.appendChild(el("label", { text: "Caminho", for: "conn-path" }));
      form.appendChild(el("input", { id: "conn-path", type: "text", value: state.form.path }));
    }
    form.appendChild(el("label", { text: state.form.id ? "Substituir segredo (deixe em branco para manter)" : "Segredo (senha ou token Portainer)", for: "conn-secret" }));
    form.appendChild(el("input", {
      id: "conn-secret",
      type: "password",
      value: "",
      autocomplete: "new-password",
      placeholder: state.form.id ? "não é exibido; preencha só para trocar" : "",
    }));
    form.appendChild(el("p", { class: "muted", text: "Hosts (rótulo + endereço). O teste tenta o preferido e depois a ordem." }));
    const hostBox = el("div", { class: "hosts" });
    state.form.hosts.forEach(function (h, idx) {
      const row = el("div", { class: "host-row" }, [
        el("div", null, [
          el("label", { text: "Rótulo" }),
          el("input", { type: "text", "data-host": "label", value: h.label }),
        ]),
        el("div", null, [
          el("label", { text: "Host" }),
          el("input", { type: "text", "data-host": "host", value: h.host, placeholder: "100.x.x.x ou empresa.example.invalid" }),
        ]),
        el("div", null, [
          el("label", { text: "Ordem" }),
          el("input", { type: "text", "data-host": "order", value: String(h.order) }),
        ]),
        el("button", { type: "button", text: "Remover", onClick: function () { removeHostRow(idx); } }),
      ]);
      hostBox.appendChild(row);
    });
    form.appendChild(hostBox);
    form.appendChild(el("button", { type: "button", text: "Adicionar host", onClick: addHostRow }));
    form.appendChild(el("label", { text: "Host preferido", for: "conn-preferred" }));
    const pref = el("select", { id: "conn-preferred" });
    state.form.hosts.forEach(function (h, idx) {
      const opt = el("option", { value: String(idx), text: (h.label || "host") + " · " + (h.host || "(vazio)") });
      if (idx === Number(state.form.preferred_index || 0)) {
        opt.selected = true;
      }
      pref.appendChild(opt);
    });
    form.appendChild(pref);
    form.appendChild(el("button", {
      type: "button",
      class: "primary",
      text: state.busy ? "Aguarde…" : "Salvar",
      disabled: state.busy ? "disabled" : null,
      onClick: saveConnection,
    }));
    if (state.form.id) {
      form.appendChild(el("button", {
        type: "button",
        text: "Nova conexão",
        onClick: function () {
          state.form = emptyForm();
          state.editing = null;
          state.testResult = null;
          render();
        },
      }));
    }
    root.appendChild(form);
  }

  function renderList(root) {
    const box = el("section", { class: "card card-ops" }, [
      el("div", { class: "card-head" }, [
        el("span", { class: "icon-box icon-ops", text: "D" }),
        el("h2", { text: "Conexões" }),
        el("span", { class: "pill pill-existing", text: "INTEGRAÇÃO EXISTENTE" }),
      ]),
    ]);
    if (!state.connections.length) {
      box.appendChild(el("p", { class: "muted", text: "Nenhuma conexão cadastrada." }));
      root.appendChild(box);
      return;
    }
    const table = el("table");
    table.appendChild(el("thead", null, [el("tr", null, [
      el("th", { text: "Nome" }),
      el("th", { text: "Tipo" }),
      el("th", { text: "Usuário" }),
      el("th", { text: "Hosts" }),
      el("th", { text: "Segredo" }),
      el("th", { text: "" }),
    ])]));
    const tbody = el("tbody");
    state.connections.forEach(function (conn) {
      const hosts = (conn.hosts || []).map(function (h) { return h.label + " (" + h.host + ")"; }).join(", ");
      const actions = [
        el("button", {
          type: "button",
          text: "Testar conexão",
          disabled: state.busy ? "disabled" : null,
          onClick: function () { testConnection(conn.id); },
        }),
      ];
      if (isOwner()) {
        actions.push(el("button", { type: "button", text: "Editar", onClick: function () { fillForm(conn); render(); } }));
        actions.push(el("button", {
          type: "button",
          class: "danger",
          text: "Apagar",
          disabled: state.busy ? "disabled" : null,
          onClick: function () { deleteConnection(conn.id); },
        }));
      }
      tbody.appendChild(el("tr", null, [
        el("td", { text: conn.name || "" }),
        el("td", null, [typePill(conn.type)]),
        el("td", { text: conn.user || "" }),
        el("td", { text: hosts }),
        el("td", null, [el("span", {
          class: "pill " + (conn.secret_set ? "pill-ok" : "pill-muted"),
          text: conn.secret_set ? "•••• definido" : "ausente",
        })]),
        el("td", null, actions),
      ]));
    });
    table.appendChild(tbody);
    box.appendChild(table);
    root.appendChild(box);
  }

  function renderTest(root) {
    if (!state.testResult) {
      return;
    }
    const box = el("section", { class: "card" }, [
      el("div", { class: "card-head" }, [
        el("h2", { text: "Resultado do teste" }),
      ]),
    ]);
    box.appendChild(el("p", { class: state.testResult.ok ? "ok" : "error", text: state.testResult.message || "" }));
    (state.testResult.attempts || []).forEach(function (a) {
      const line = a.label + " (" + a.host + "): " + (a.ok ? "ok" : (a.message || a.error || "falhou"));
      box.appendChild(el("p", { class: a.ok ? "ok" : "error", text: line }));
    });
    root.appendChild(box);
  }

  function render() {
    snapshotForm();
    const session = document.getElementById("session");
    const app = document.getElementById("app");
    renderSession(session);
    renderNav();
    app.replaceChildren();
    if (state.loading) {
      app.appendChild(el("section", { class: "card state-card" }, [
        el("p", { class: "muted", text: "Carregando…" }),
      ]));
      return;
    }
    if (state.error) {
      app.appendChild(el("p", { class: "banner banner-error error", text: errorMessage(state.error, state.errorDetail) }));
    }
    if (state.notice) {
      app.appendChild(el("p", { class: "banner banner-ok ok", text: state.notice }));
    }
    if (!state.who) {
      renderLogin(app);
      return;
    }
    app.appendChild(pageHeader("04 — CONEXÕES", "Conexões", "Conectores somente leitura para banco de dados, FTP/SFTP e Portainer."));
    app.appendChild(readonlySeal());
    if (!isReader()) {
      app.appendChild(el("section", { class: "card" }, [
        el("p", { class: "error", text: "Só owner ou editor acessam Conexões. Owner cria/edita/apaga; editor lista e testa." }),
      ]));
      return;
    }
    if (!state.enabled) {
      app.appendChild(el("section", { class: "card" }, [
        el("h2", { text: "Conexões desligada" }),
        el("p", { class: "error", text: state.disabledMessage || errorMessage("vault_disabled") }),
      ]));
      return;
    }
    renderList(app);
    renderTest(app);
    renderForm(app);
  }

  async function boot() {
    state.loading = true;
    render();
    try {
      await api("/api/health");
      await loadWhoami();
      state.loading = false;
      render();
      if (isReader()) {
        await loadConnections();
        render();
      }
    } catch (err) {
      state.error = "api_unreachable";
      state.loading = false;
      render();
    }
  }

  boot();
})();
