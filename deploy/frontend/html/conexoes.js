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
    fieldErrors: {},
    formWarning: "",
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
      invalid_host: "Host inválido. Preencha o campo Host com o IP ou o hostname. O nome do banco vai no campo Banco.",
      invalid_host_label: "Cada host precisa de um rótulo.",
      invalid_preferred: "Host preferido inválido.",
      form_invalid: "Há campos a corrigir. Veja o destaque no formulário.",
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
    if (code === "invalid_host" || code === "invalid_hosts" || code === "invalid_host_label") {
      const errors = {};
      (state.form.hosts || []).forEach(function (h, idx) {
        if (code === "invalid_host_label" && !String(h.label || "").trim()) {
          errors["conn-host-label-" + idx] = "Informe um rótulo para este host.";
        }
        if (code === "invalid_host" && !String(h.host || "").trim()) {
          errors["conn-host-" + idx] = "Informe o host ou IP neste campo (não use o campo Banco).";
        }
        if (code === "invalid_host" && String(h.host || "").trim()) {
          errors["conn-host-" + idx] = "Este host está inválido. Use IP, hostname ou a URL do Portainer.";
        }
      });
      if (code === "invalid_hosts") {
        errors["conn-hosts"] = "Informe ao menos um host.";
      }
      state.fieldErrors = errors;
    }
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
    const check = validateConnectionForm(form);
    state.fieldErrors = check.errors;
    state.formWarning = check.warning;
    if (Object.keys(check.errors).length) {
      const first = firstFieldError(check.errors);
      state.error = "form_invalid";
      state.errorDetail = { message: check.errors[first] };
      render();
      const node = document.getElementById(first);
      if (node && typeof node.focus === "function") {
        node.focus();
      }
      return;
    }
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
        state.fieldErrors = {};
    state.formWarning = "";
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

  function pageHeader(title, subtitle) {
    return el("header", { class: "page-header" }, [
      el("div", { class: "page-header-text" }, [
        el("h2", { class: "page-title", text: title }),
        subtitle ? el("p", { class: "page-subtitle", text: subtitle }) : null,
      ]),
    ]);
  }

  function cardHead(title, extra) {
    return el("div", { class: "card-head" }, [el("h2", { text: title })].concat(extra || []));
  }

  function actionsRow(children) {
    return el("div", { class: "actions" }, children);
  }

  function lockIcon() {
    const ns = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(ns, "svg");
    svg.setAttribute("viewBox", "0 0 16 16");
    svg.setAttribute("width", "14");
    svg.setAttribute("height", "14");
    svg.setAttribute("aria-hidden", "true");
    const path = document.createElementNS(ns, "path");
    path.setAttribute("fill", "none");
    path.setAttribute("stroke", "currentColor");
    path.setAttribute("stroke-width", "1.5");
    path.setAttribute("stroke-linecap", "round");
    path.setAttribute("stroke-linejoin", "round");
    path.setAttribute("d", "M4 7.2h8v6H4zM5.6 7.2V5.4a2.4 2.4 0 014.8 0v1.8");
    svg.appendChild(path);
    return svg;
  }

  function showToast(text) {
    let region = document.getElementById("toast-region");
    if (!region) {
      region = el("div", { id: "toast-region", class: "toast-region", role: "status", "aria-live": "polite" });
      document.body.appendChild(region);
    }
    const toast = el("div", { class: "toast", text: text });
    region.appendChild(toast);
    window.setTimeout(function () {
      toast.classList.add("toast-out");
      window.setTimeout(function () { toast.remove(); }, 200);
    }, 4500);
  }

  function readonlySeal() {
    return el("p", { class: "seal-readonly" }, [
      lockIcon(),
      el("strong", { text: "Somente leitura." }),
      el("span", { text: "Agentes não alteram dados nem recebem suas credenciais de escrita." }),
    ]);
  }

  function renderSession(target) {
    target.replaceChildren();
    if (state.who) {
      const roles = (state.who.roles || []).join(" · ") || "sem papel";
      target.appendChild(el("div", { class: "session-who" }, [
        el("span", { class: "session-login", text: state.who.login }),
        el("span", { class: "session-roles", text: roles }),
      ]));
      target.appendChild(el("span", { class: "avatar", "aria-hidden": "true", text: String(state.who.login || "?").slice(0, 2) }));
      target.appendChild(el("button", { type: "button", class: "btn-sair", text: "Sair", onClick: function () { logout(); } }));
      return;
    }
    target.appendChild(el("span", { class: "muted", text: "Não autenticado" }));
  }

  function renderLogin(root) {
    const box = el("section", { class: "card login-panel" }, [
      el("h2", { text: "Entrar no Forge" }),
    ]);
    if (state.pending && state.pending.user_code) {
      box.appendChild(el("p", { text: "Abra o GitHub e informe o código para autorizar este painel." }));
      box.appendChild(el("p", { class: "code login-code", text: state.pending.user_code }));
      box.appendChild(el("p", { class: "login-wait muted" }, [
        el("span", { class: "spinner", "aria-hidden": "true" }),
        el("span", { text: "Aguardando autorização no GitHub…" }),
      ]));
    } else {
      box.appendChild(el("p", { text: "Use sua conta do GitHub. O acesso depende dos papéis concedidos a você neste painel." }));
      box.appendChild(el("button", {
        type: "button",
        class: "primary",
        text: "Entrar com GitHub",
        onClick: function () { startLogin(); },
      }));
    }
    root.appendChild(box);
  }

  function hostPlaceholder(type) {
    if (type === "portainer") {
      return "https://IP:9443";
    }
    if (type === "ftp" || type === "sftp") {
      return "host ou IP";
    }
    return "ex.: 100.x.x.x ou db.empresa";
  }

  function hostHint(type) {
    if (type === "portainer") {
      return "URL do Portainer, inclusive o esquema e a porta, por exemplo https://192.168.0.10:9443.";
    }
    if (type === "ftp" || type === "sftp") {
      return "Hostname ou IP do servidor. O caminho remoto vai no campo Caminho, não aqui.";
    }
    return "Hostname ou IP do servidor. Não coloque o IP no campo Banco.";
  }

  function looksLikeHostAddress(value) {
    const v = String(value || "").trim();
    if (!v) {
      return false;
    }
    if (/^https?:\/\//i.test(v)) {
      return true;
    }
    if (/^\d{1,3}(?:\.\d{1,3}){3}(?::\d+)?$/.test(v)) {
      return true;
    }
    return false;
  }

  function fieldError(formEl, fieldId, message) {
    const node = formEl.querySelector("#" + fieldId) || document.getElementById(fieldId);
    if (node) {
      node.classList.add("field-invalid");
      node.setAttribute("aria-invalid", "true");
    }
    if (message) {
      const hint = el("p", { class: "field-hint field-error", id: fieldId + "-error", text: message });
      if (node && node.parentNode) {
        node.parentNode.appendChild(hint);
      }
    }
    return node;
  }

  function validateConnectionForm(form) {
    const errors = {};
    if (!String(form.name || "").trim()) {
      errors["conn-name"] = "Informe um nome.";
    }
    if (!String(form.user || "").trim()) {
      errors["conn-user"] = "Informe o usuário.";
    }
    const port = Number(form.port);
    if (!Number.isInteger(port) || port < 1 || port > 65535) {
      errors["conn-port"] = "Informe uma porta válida (1 a 65535).";
    }
    if (!form.hosts.length) {
      errors["conn-hosts"] = "Informe ao menos um host.";
    }
    form.hosts.forEach(function (h, idx) {
      if (!String(h.label || "").trim()) {
        errors["conn-host-label-" + idx] = "Informe um rótulo para este host.";
      }
      if (!String(h.host || "").trim()) {
        errors["conn-host-" + idx] = "Informe o host ou IP neste campo (não use o campo Banco).";
      }
    });
    let warning = "";
    if ((form.type === "mysql" || form.type === "postgres") && looksLikeHostAddress(form.database)) {
      warning = "O campo Banco parece um IP ou uma URL. Coloque o endereço no campo Host; Banco é o nome do schema e é opcional.";
    }
    return { errors: errors, warning: warning };
  }

  function firstFieldError(errors) {
    const keys = Object.keys(errors);
    return keys.length ? keys[0] : "";
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
    const editing = !!state.form.id;
    const form = el("section", { class: "card", id: "conn-form" }, [
      cardHead(editing ? "Editar conexão" : "Nova conexão"),
    ]);
    if (!isOwner()) {
      form.appendChild(el("p", { class: "muted", text: "Só o papel owner cria, edita ou apaga conexões." }));
      root.appendChild(form);
      return;
    }
    const fieldErrors = state.fieldErrors || {};
    function mark(id, attrs) {
      const next = Object.assign({}, attrs);
      if (fieldErrors[id]) {
        next.class = ((next.class || "") + " field-invalid").trim();
        next["aria-invalid"] = "true";
        next["aria-describedby"] = id + "-error";
      }
      return next;
    }
    function hintFor(id) {
      return fieldErrors[id] ? el("p", { class: "field-hint field-error", id: id + "-error", text: fieldErrors[id] }) : null;
    }
    function field(labelText, id, control, extra) {
      return el("div", { class: "field" }, [
        el("label", { text: labelText, for: id }),
        control,
        hintFor(id),
      ].concat(extra || []));
    }

    const typeSel = el("select", { id: "conn-type", onChange: function () {
      state.form = readForm();
      if (!state.form.id) {
        state.form.port = defaultPort(state.form.type);
      }
      state.fieldErrors = state.fieldErrors || {};
      render();
    } });
    TYPES.forEach(function (t) {
      const opt = el("option", { value: t.id, text: t.label });
      if (t.id === state.form.type) {
        opt.selected = true;
      }
      typeSel.appendChild(opt);
    });

    form.appendChild(el("div", { class: "field-grid" }, [
      field("Nome", "conn-name", el("input", mark("conn-name", { id: "conn-name", type: "text", value: state.form.name }))),
      field("Tipo", "conn-type", typeSel),
      field("Usuário", "conn-user", el("input", mark("conn-user", { id: "conn-user", type: "text", value: state.form.user, autocomplete: "off" }))),
      field("Porta", "conn-port", el("input", mark("conn-port", { id: "conn-port", type: "text", inputmode: "numeric", value: state.form.port }))),
    ]));

    if (state.form.type === "mysql" || state.form.type === "postgres") {
      const dbWarn = el("p", {
        class: "field-hint field-warn",
        id: "conn-database-warn",
        text: "Este valor parece um IP ou uma URL. Mova o endereço para o campo Host e, em Banco, use só o nome do schema (pode ficar em branco).",
      });
      const shouldWarn = !!(state.formWarning || looksLikeHostAddress(state.form.database));
      if (!shouldWarn) {
        dbWarn.hidden = true;
      }
      form.appendChild(field("Banco (opcional)", "conn-database", el("input", mark("conn-database", {
        id: "conn-database",
        type: "text",
        value: state.form.database,
        placeholder: "nome do schema",
        onInput: function (ev) {
          const hint = document.getElementById("conn-database-warn");
          if (hint) {
            hint.hidden = !looksLikeHostAddress(ev.target.value);
          }
        },
      })), [
        el("p", { class: "field-hint", text: "Nome do schema ou do banco. Não coloque IP ou URL aqui." }),
        dbWarn,
      ]));
    }
    if (state.form.type === "ftp" || state.form.type === "sftp") {
      form.appendChild(field("Caminho (opcional)", "conn-path", el("input", { id: "conn-path", type: "text", value: state.form.path, placeholder: "caminho remoto" })));
    }

    const hostsSection = el("div", { class: "form-section" }, [
      el("h3", { text: "Hosts" }),
      el("p", { class: "field-hint", text: hostHint(state.form.type) + " O teste tenta o host preferido e depois segue a ordem." }),
      fieldErrors["conn-hosts"] ? el("p", { class: "field-hint field-error", text: fieldErrors["conn-hosts"] }) : null,
    ]);
    const hostBox = el("div", { class: "hosts", id: "conn-hosts" });
    state.form.hosts.forEach(function (h, idx) {
      const labelId = "conn-host-label-" + idx;
      const hostId = "conn-host-" + idx;
      const orderId = "conn-host-order-" + idx;
      hostBox.appendChild(el("div", { class: "host-row" }, [
        el("div", null, [
          el("label", { text: "Rótulo", for: labelId }),
          el("input", mark(labelId, { id: labelId, type: "text", "data-host": "label", value: h.label })),
          hintFor(labelId),
        ]),
        el("div", null, [
          el("label", { text: "Host", for: hostId }),
          el("input", mark(hostId, {
            id: hostId,
            type: "text",
            "data-host": "host",
            value: h.host,
            placeholder: hostPlaceholder(state.form.type),
          })),
          hintFor(hostId),
        ]),
        el("div", null, [
          el("label", { text: "Ordem", for: orderId }),
          el("input", { id: orderId, type: "text", inputmode: "numeric", "data-host": "order", value: String(h.order) }),
        ]),
        el("button", {
          type: "button",
          class: "quiet",
          text: "Remover",
          disabled: state.form.hosts.length <= 1 ? "disabled" : null,
          onClick: function () { removeHostRow(idx); },
        }),
      ]));
    });
    hostsSection.appendChild(hostBox);
    hostsSection.appendChild(actionsRow([el("button", { type: "button", class: "sm", text: "Adicionar host", onClick: addHostRow })]));
    const pref = el("select", { id: "conn-preferred" });
    state.form.hosts.forEach(function (h, idx) {
      const opt = el("option", { value: String(idx), text: (h.label || "host") + " — " + (h.host || "(vazio)") });
      if (idx === Number(state.form.preferred_index || 0)) {
        opt.selected = true;
      }
      pref.appendChild(opt);
    });
    hostsSection.appendChild(field("Host preferido", "conn-preferred", pref));
    form.appendChild(hostsSection);

    form.appendChild(el("div", { class: "form-section" }, [
      el("h3", { text: "Credencial" }),
      el("p", { class: "field-hint", text: "Guardado cifrado no servidor e nunca exibido de volta." }),
      field(editing ? "Substituir segredo (deixe em branco para manter)" : "Segredo (senha ou token Portainer)", "conn-secret", el("input", {
        id: "conn-secret",
        type: "password",
        value: "",
        autocomplete: "new-password",
        placeholder: editing ? "preencha só para trocar" : "",
      })),
    ]));

    form.appendChild(actionsRow([
      el("button", {
        type: "button",
        class: "primary",
        text: state.busy ? "Aguarde…" : (editing ? "Salvar alterações" : "Salvar conexão"),
        disabled: state.busy ? "disabled" : null,
        onClick: saveConnection,
      }),
      editing ? el("button", {
        type: "button",
        text: "Cancelar edição",
        onClick: function () {
          state.form = emptyForm();
          state.editing = null;
          state.testResult = null;
          state.fieldErrors = {};
          state.formWarning = "";
          render();
        },
      }) : null,
    ]));
    root.appendChild(form);
  }

  function renderList(root) {
    const box = el("section", { class: "card" }, [
      cardHead("Conexões", [el("span", { class: "count", text: String(state.connections.length) })]),
    ]);
    if (!state.connections.length) {
      box.appendChild(el("div", { class: "empty" }, [
        el("strong", { text: "Nenhuma conexão cadastrada" }),
        el("span", { text: isOwner() ? "Cadastre a primeira no formulário abaixo." : "Peça a um owner para cadastrar." }),
      ]));
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
      el("th", { text: "", "aria-label": "Ações" }),
    ])]));
    const tbody = el("tbody");
    state.connections.forEach(function (conn) {
      const hosts = (conn.hosts || []).map(function (h) { return h.label + " (" + h.host + ")"; }).join(", ");
      const actions = [
        el("button", {
          type: "button",
          class: "sm",
          text: "Testar conexão",
          disabled: state.busy ? "disabled" : null,
          onClick: function () { testConnection(conn.id); },
        }),
      ];
      if (isOwner()) {
        actions.push(el("button", {
          type: "button",
          class: "sm quiet",
          text: "Editar",
          onClick: function () {
            fillForm(conn);
            render();
            const target = document.getElementById("conn-form");
            if (target) {
              target.scrollIntoView({ behavior: "smooth", block: "start" });
            }
          },
        }));
        actions.push(el("button", {
          type: "button",
          class: "sm quiet danger",
          text: "Apagar",
          disabled: state.busy ? "disabled" : null,
          onClick: function () { deleteConnection(conn.id); },
        }));
      }
      tbody.appendChild(el("tr", null, [
        el("td", { class: "cell-strong", text: conn.name || "" }),
        el("td", { text: TYPE_LABEL[conn.type] || conn.type || "" }),
        el("td", { text: conn.user || "" }),
        el("td", { class: "muted", text: hosts }),
        el("td", null, [el("span", {
          class: "status " + (conn.secret_set ? "status-ok" : "status-muted"),
          text: conn.secret_set ? "Definido" : "Ausente",
        })]),
        el("td", { class: "cell-actions" }, actions),
      ]));
    });
    table.appendChild(tbody);
    box.appendChild(el("div", { class: "table-wrap" }, [table]));
    root.appendChild(box);
  }

  function renderTest(root) {
    if (!state.testResult) {
      return;
    }
    const ok = !!state.testResult.ok;
    const box = el("section", { class: "card" }, [
      cardHead("Resultado do teste", [el("span", { class: "status " + (ok ? "status-ok" : "status-danger"), text: ok ? "Sucesso" : "Falhou" })]),
    ]);
    if (state.testResult.message) {
      box.appendChild(el("p", { text: state.testResult.message }));
    }
    const attempts = state.testResult.attempts || [];
    if (attempts.length) {
      const list = el("ul", { class: "test-attempts" });
      attempts.forEach(function (a) {
        list.appendChild(el("li", null, [
          el("span", { class: "status " + (a.ok ? "status-ok" : "status-danger"), text: a.label + " (" + a.host + ")" }),
          el("span", { class: "muted", text: " — " + (a.ok ? "ok" : (a.message || a.error || "falhou")) }),
        ]));
      });
      box.appendChild(list);
    }
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
      showToast(state.notice);
      state.notice = "";
    }
    if (!state.who) {
      renderLogin(app);
      return;
    }
    app.appendChild(pageHeader("Conexões", "Conectores somente leitura para banco de dados, FTP/SFTP e Portainer, usados como contexto nas investigações."));
    app.appendChild(readonlySeal());
    if (!isReader()) {
      app.appendChild(el("p", { class: "banner banner-warn", text: "Só owner ou editor acessam Conexões. Owner cria/edita/apaga; editor lista e testa." }));
      return;
    }
    if (!state.enabled) {
      app.appendChild(el("section", { class: "card" }, [
        cardHead("Conexões desligada"),
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
