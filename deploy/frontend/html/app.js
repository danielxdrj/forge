(function () {
  "use strict";

  const MAX_CONTEXT = 64 * 1024;
  const state = {
    who: null,
    pending: null,
    pollTimer: null,
    repos: [],
    fields: { tipo: [], prioridade: [], size: [] },
    draft: null,
    tasks: [],
    form: { repo: "", context: "", tipo: "", prioridade: "", size: "" },
    error: "",
    notice: "",
    busy: false,
  };

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

  function githubHref(url) {
    try {
      const parsed = new URL(url);
      if (parsed.protocol === "https:" && (parsed.hostname === "github.com" || parsed.hostname.endsWith(".github.com"))) {
        return parsed.toString();
      }
    } catch (err) {
      return "";
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

  function safeLink(url, label) {
    const href = githubHref(url || "");
    if (!href) {
      return el("span", { class: "muted", text: "—" });
    }
    return el("a", { href: href, rel: "noopener noreferrer", text: label || href });
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
        data = { error: "malformed" };
      }
    }
    return { ok: response.ok, status: response.status, data: data };
  }

  function setError(code) {
    state.error = code || "";
    render();
  }

  async function loadWhoami() {
    const res = await api("/api/auth/whoami");
    if (res.status === 401) {
      state.who = null;
      return;
    }
    if (res.ok) {
      state.who = res.data;
    }
  }

  async function startLogin() {
    state.error = "";
    const res = await api("/api/auth/login/start", { method: "POST", body: {} });
    if (!res.ok) {
      setError(res.data.error || "login");
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
      setError(res.data.status || "login");
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
    if (isEditor()) {
      await loadEditorData();
    }
    render();
  }

  function isEditor() {
    return !!(state.who && Array.isArray(state.who.roles) && state.who.roles.indexOf("editor") !== -1);
  }

  async function loadEditorData() {
    const repos = await api("/api/repos");
    if (repos.ok) {
      state.repos = repos.data.repos || [];
    }
    const fields = await api("/api/board/fields");
    if (fields.ok) {
      state.fields = fields.data;
    }
    const tasks = await api("/api/tasks");
    if (tasks.ok) {
      state.tasks = tasks.data.tasks || [];
    }
  }

  async function logout() {
    await api("/api/auth/logout", { method: "POST", body: {} });
    stopPoll();
    state.who = null;
    state.pending = null;
    state.draft = null;
    state.tasks = [];
    render();
  }

  async function generateDraft() {
    const repo = document.getElementById("repo").value;
    const context = document.getElementById("context").value;
    state.form.repo = repo;
    state.form.context = context;
    if (context.length > MAX_CONTEXT) {
      setError("context_too_large");
      return;
    }
    state.busy = true;
    state.error = "";
    render();
    const res = await api("/api/tasks/generate", { method: "POST", body: { repo: repo, context: context } });
    state.busy = false;
    if (!res.ok) {
      setError(res.data.error || "generate");
      return;
    }
    state.draft = res.data;
    state.notice = "Rascunho gerado. Escolha tipo, prioridade e size e confirme.";
    await loadEditorData();
    render();
  }

  async function saveFields() {
    if (!state.draft) {
      return;
    }
    const tipo = document.getElementById("tipo").value;
    const prioridade = document.getElementById("prioridade").value;
    const size = document.getElementById("size").value;
    state.form.tipo = tipo;
    state.form.prioridade = prioridade;
    state.form.size = size;
    if (!tipo || !prioridade || !size) {
      return;
    }
    state.busy = true;
    state.error = "";
    render();
    const res = await api("/api/tasks/" + encodeURIComponent(state.draft.task_id) + "/draft", {
      method: "POST",
      body: { tipo: tipo, prioridade: prioridade, size: size },
    });
    state.busy = false;
    if (!res.ok) {
      setError(res.data.error || "pending_required");
      return;
    }
    state.draft.preview = res.data.preview;
    state.draft.preview_hash = res.data.preview_hash;
    state.notice = "Campos atualizados.";
    render();
  }

  async function confirmDraft() {
    if (!state.draft) {
      return;
    }
    state.busy = true;
    state.error = "";
    render();
    const res = await api("/api/tasks/" + encodeURIComponent(state.draft.task_id) + "/confirm", {
      method: "POST",
      body: { preview_hash: state.draft.preview_hash },
    });
    state.busy = false;
    if (!res.ok) {
      setError(res.data.error || "confirm");
      return;
    }
    state.draft.links = res.data;
    state.notice = "Tarefa publicada.";
    await loadEditorData();
    render();
  }

  function errorMessage(code) {
    const map = {
      csrf: "CSRF recusado. Recarregue a página.",
      forbidden: "Sem papel editor. O owner não implica editor.",
      invalid_session: "Sessão inválida. Entre de novo.",
      context_too_large: "Contexto maior que 64 KiB.",
      empty_context: "Informe o contexto escrito.",
      repo_not_allowed: "Repositório fora da allowlist.",
      invalid_repo: "Repositório inválido.",
      pending_required: "Preencha tipo, prioridade e size (sem [PENDENTE]).",
      diff_changed: "A pré-visualização mudou. Atualize os campos e confirme de novo.",
      denied: "Autorização negada no GitHub.",
      expired: "O código expirou. Comece de novo.",
    };
    return map[code] || code;
  }

  function renderSession(target) {
    target.replaceChildren();
    if (state.who) {
      target.appendChild(el("span", { text: "Login: " + state.who.login + " · papéis: " + (state.who.roles.join(", ") || "nenhum") }));
      target.appendChild(el("button", { type: "button", text: "Sair", onClick: function () { logout(); } }));
      return;
    }
    target.appendChild(el("span", { class: "muted", text: "Não autenticado" }));
  }

  function renderLogin(root) {
    const box = el("section", null, [el("h2", { text: "Entrar" })]);
    if (state.pending && state.pending.user_code) {
      box.appendChild(el("p", { text: "Abra o GitHub e informe o código:" }));
      const href = githubHref(state.pending.verification_uri);
      if (href) {
        box.appendChild(el("p", null, [el("a", { href: href, rel: "noopener noreferrer", text: href })]));
      }
      box.appendChild(el("p", { class: "code", text: state.pending.user_code }));
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

  function fillSelect(select, options, placeholder, selected) {
    select.replaceChildren();
    select.appendChild(el("option", { value: "", text: placeholder }));
    (options || []).forEach(function (name) {
      const opt = el("option", { value: name, text: name });
      if (selected && selected === name) {
        opt.selected = true;
      }
      select.appendChild(opt);
    });
  }

  function renderEditor(root) {
    if (!isEditor()) {
      root.appendChild(el("section", null, [
        el("p", { class: "error", text: "Só quem tem o papel editor pode criar tarefas. O owner não implica editor; peça grant --role editor." }),
      ]));
      return;
    }

    const form = el("section", null, [el("h2", { text: "Nova tarefa" })]);
    const repo = el("select", { id: "repo" });
    state.repos.forEach(function (item) {
      const opt = el("option", { value: item.full_name, text: item.full_name });
      if (state.form.repo === item.full_name) {
        opt.selected = true;
      }
      repo.appendChild(opt);
    });
    form.appendChild(el("label", { text: "Repositório", for: "repo" }));
    form.appendChild(repo);
    form.appendChild(el("label", { text: "Contexto escrito (máx. 64 KiB). Sem imagem.", for: "context" }));
    const context = el("textarea", { id: "context", maxlength: String(MAX_CONTEXT) });
    context.value = state.form.context || "";
    form.appendChild(context);
    form.appendChild(el("button", {
      type: "button",
      class: "primary",
      text: state.busy ? "Aguarde…" : "Gerar rascunho",
      disabled: state.busy ? "disabled" : null,
      onClick: function () { generateDraft(); },
    }));
    root.appendChild(form);

    if (state.draft) {
      const preview = el("section", null, [el("h2", { text: "Pré-visualização" })]);
      const pre = el("pre", { class: "preview" });
      pre.textContent = state.draft.preview || "";
      preview.appendChild(pre);
      const row = el("div", { class: "row" });
      const tipo = el("select", { id: "tipo", onChange: function () { saveFields(); } });
      const prioridade = el("select", { id: "prioridade", onChange: function () { saveFields(); } });
      const size = el("select", { id: "size", onChange: function () { saveFields(); } });
      fillSelect(tipo, state.fields.tipo, "Tipo", state.form.tipo);
      fillSelect(prioridade, state.fields.prioridade, "Prioridade", state.form.prioridade);
      fillSelect(size, state.fields.size, "Size", state.form.size);
      row.appendChild(el("div", null, [el("label", { text: "Tipo", for: "tipo" }), tipo]));
      row.appendChild(el("div", null, [el("label", { text: "Prioridade", for: "prioridade" }), prioridade]));
      row.appendChild(el("div", null, [el("label", { text: "Size", for: "size" }), size]));
      preview.appendChild(row);
      preview.appendChild(el("button", {
        type: "button",
        class: "primary",
        text: "Confirmar e publicar",
        disabled: state.busy ? "disabled" : null,
        onClick: function () { confirmDraft(); },
      }));
      if (state.draft.links) {
        const links = state.draft.links;
        preview.appendChild(el("p", { class: "ok", text: "Publicado." }));
        preview.appendChild(el("p", null, [el("span", { text: "Issue: " }), safeLink(links.issue_url)]));
        preview.appendChild(el("p", null, [el("span", { text: "Branch: " }), el("span", { text: links.branch || "—" })]));
        preview.appendChild(el("p", null, [el("span", { text: "PR: " }), safeLink(links.pr_url)]));
        preview.appendChild(el("p", null, [el("span", { text: "Board: " }), el("span", { text: links.board_item_id || "—" })]));
      }
      root.appendChild(preview);
    }

    const list = el("section", null, [el("h2", { text: "Tarefas" })]);
    if (!state.tasks.length) {
      list.appendChild(el("p", { class: "muted", text: "Nenhuma tarefa ainda." }));
    } else {
      const table = el("table");
      table.appendChild(el("thead", null, [el("tr", null, [
        el("th", { text: "Repositório" }),
        el("th", { text: "Título" }),
        el("th", { text: "Status" }),
        el("th", { text: "Issue" }),
        el("th", { text: "PR" }),
      ])]));
      const tbody = el("tbody");
      state.tasks.forEach(function (task) {
        tbody.appendChild(el("tr", null, [
          el("td", { text: task.repo || "" }),
          el("td", { text: task.title || "" }),
          el("td", { text: (task.draft_status || "") + " / " + (task.status || "") }),
          el("td", null, [safeLink(task.issue_url, "issue")]),
          el("td", null, [safeLink(task.pr_url, "PR")]),
        ]));
      });
      table.appendChild(tbody);
      list.appendChild(table);
    }
    root.appendChild(list);
  }

  function render() {
    const session = document.getElementById("session");
    const app = document.getElementById("app");
    renderSession(session);
    app.replaceChildren();
    if (state.error) {
      app.appendChild(el("p", { class: "error", text: errorMessage(state.error) }));
    }
    if (state.notice) {
      app.appendChild(el("p", { class: "ok", text: state.notice }));
    }
    if (!state.who) {
      renderLogin(app);
      return;
    }
    renderEditor(app);
  }

  async function boot() {
    await api("/api/health");
    await loadWhoami();
    if (isEditor()) {
      await loadEditorData();
    }
    render();
  }

  boot();
})();
