(function () {
  "use strict";

  const MAX_CONTEXT = 64 * 1024;
  const FIELD_LABELS = {
    title: "Título",
    solicitado_por: "Solicitado por",
    objetivo: "Objetivo",
    contexto: "Contexto",
    problemas: "Problemas",
    novos_problemas: "Novos problemas",
    situacao_atual: "Situação atual",
    comportamento_esperado: "Comportamento esperado",
    criterios: "Critérios de aceite",
    observacoes: "Observações",
    tipo: "Tipo",
    prioridade: "Prioridade",
    size: "Size",
  };
  const state = {
    who: null,
    pending: null,
    pollTimer: null,
    repos: [],
    fields: { tipo: [], prioridade: [], size: [] },
    fieldsError: "",
    draft: null,
    tasks: [],
    published: [],
    drafts: [],
    form: { repo: "", context: "", tipo: "", prioridade: "", size: "" },
    error: "",
    errorDetail: null,
    notice: "",
    busy: false,
    loading: true,
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
    return el("a", { href: href, target: "_blank", rel: "noopener noreferrer", text: label || href });
  }

  function publishedIssueLink(url) {
    const node = safeLink(url, "issue");
    if (node.tagName === "A") {
      node.setAttribute("target", "_blank");
    }
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
        data = { error: response.status === 504 ? "gateway_timeout" : "http_" + response.status };
      }
    }
    return { ok: response.ok, status: response.status, data: data };
  }

  function setError(code, detail) {
    state.error = code || "";
    state.errorDetail = detail || null;
    render();
  }

  function setErrorFromResponse(data) {
    setError((data && data.error) || "error", data);
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
    state.errorDetail = null;
    const res = await api("/api/auth/login/start", { method: "POST", body: {} });
    if (!res.ok) {
      setErrorFromResponse(res.data);
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
    if (isEditor()) {
      await loadEditorData();
    }
    render();
  }

  function isEditor() {
    return !!(state.who && Array.isArray(state.who.roles) && state.who.roles.indexOf("editor") !== -1);
  }

  function isOwner() {
    return !!(state.who && Array.isArray(state.who.roles) && state.who.roles.indexOf("owner") !== -1);
  }

  async function loadEditorData() {
    const repos = await api("/api/repos");
    if (repos.ok) {
      state.repos = repos.data.repos || [];
    }
    const fields = await api("/api/board/fields");
    if (fields.ok) {
      state.fields = fields.data;
      state.fieldsError = "";
    } else {
      state.fields = { tipo: [], prioridade: [], size: [] };
      state.fieldsError = errorMessage(fields.data.error || "board_fields", fields.data);
    }
    const tasks = await api("/api/tasks");
    if (tasks.ok) {
      state.published = tasks.data.published || [];
      state.drafts = tasks.data.drafts || [];
      state.tasks = tasks.data.tasks || state.published.concat(state.drafts);
    }
  }

  async function logout() {
    await api("/api/auth/logout", { method: "POST", body: {} });
    stopPoll();
    state.who = null;
    state.pending = null;
    state.draft = null;
    state.tasks = [];
    state.published = [];
    state.drafts = [];
    render();
  }

  function applyDraft(data) {
    state.draft = data;
    state.form.tipo = data.tipo || "";
    state.form.prioridade = data.prioridade || "";
    state.form.size = data.size || "";
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
    state.errorDetail = null;
    render();
    const res = await api("/api/tasks/generate", { method: "POST", body: { repo: repo, context: context } });
    state.busy = false;
    if (!res.ok) {
      setErrorFromResponse(res.data);
      return;
    }
    applyDraft(res.data);
    if (res.data.pending && res.data.pending.length) {
      state.notice = "Rascunho gerado com seções [PENDENTE]. Edite o corpo ou complemente o contexto e gere de novo.";
    } else {
      state.notice = "Rascunho gerado. Tipo, prioridade e size vêm sugeridos; troque só se quiser e confirme.";
    }
    await loadEditorData();
    render();
  }

  function currentDraftPayload() {
    const tipoEl = document.getElementById("tipo");
    const priEl = document.getElementById("prioridade");
    const sizeEl = document.getElementById("size");
    const bodyEl = document.getElementById("draft-body");
    const tipo = tipoEl ? tipoEl.value : (state.form.tipo || "");
    const prioridade = priEl ? priEl.value : (state.form.prioridade || "");
    const size = sizeEl ? sizeEl.value : (state.form.size || "");
    const body_md = bodyEl ? bodyEl.value : (state.draft && state.draft.body) || "";
    state.form.tipo = tipo;
    state.form.prioridade = prioridade;
    state.form.size = size;
    return { tipo: tipo, prioridade: prioridade, size: size, body_md: body_md };
  }

  async function saveDraft() {
    if (!state.draft) {
      return false;
    }
    const payload = currentDraftPayload();
    state.busy = true;
    state.error = "";
    state.errorDetail = null;
    render();
    const res = await api("/api/tasks/" + encodeURIComponent(state.draft.task_id) + "/draft", {
      method: "POST",
      body: payload,
    });
    state.busy = false;
    if (!res.ok) {
      setErrorFromResponse(res.data);
      return false;
    }
    applyDraft(Object.assign({}, state.draft, res.data));
    state.notice = "Rascunho atualizado.";
    render();
    return true;
  }

  async function confirmDraft() {
    if (!state.draft) {
      return;
    }
    const saved = await saveDraft();
    if (!saved) {
      return;
    }
    state.busy = true;
    state.error = "";
    state.errorDetail = null;
    render();
    const res = await api("/api/tasks/" + encodeURIComponent(state.draft.task_id) + "/confirm", {
      method: "POST",
      body: { preview_hash: state.draft.preview_hash },
    });
    state.busy = false;
    if (!res.ok) {
      setErrorFromResponse(res.data);
      return;
    }
    state.draft.links = res.data;
    state.notice = "Tarefa publicada.";
    await loadEditorData();
    render();
  }

  async function discardDraft(taskId) {
    state.busy = true;
    state.error = "";
    state.errorDetail = null;
    render();
    const res = await api("/api/tasks/" + encodeURIComponent(taskId) + "/discard", {
      method: "POST",
      body: {},
    });
    state.busy = false;
    if (!res.ok) {
      setErrorFromResponse(res.data);
      return;
    }
    if (state.draft && state.draft.task_id === taskId) {
      state.draft = null;
    }
    state.notice = "Rascunho descartado.";
    await loadEditorData();
    render();
  }

  function fieldLabel(name) {
    return FIELD_LABELS[name] || name;
  }

  function errorMessage(code, detail) {
    const map = {
      csrf: "CSRF recusado. Recarregue a página.",
      gateway_timeout: "A geração demorou demais e o proxy desistiu. Tente de novo.",
      forbidden: "Sem papel editor. O owner não implica editor.",
      invalid_session: "Sessão inválida. Entre de novo.",
      context_too_large: "Contexto maior que 64 KiB.",
      empty_context: "Informe o contexto escrito.",
      repo_not_allowed: "Repositório fora da allowlist.",
      invalid_repo: "Repositório inválido.",
      pending_required: "Preencha tipo, prioridade e size (sem [PENDENTE]).",
      pending_fields: "Ainda há [PENDENTE] no rascunho.",
      draft_cancelled: "Este rascunho foi descartado.",
      draft_published: "Tarefa já publicada; não dá para descartar.",
      invalid_board_option: "Tipo, prioridade ou size não existe no board.",
      diff_changed: "A pré-visualização mudou. Atualize os campos e confirme de novo.",
      denied: "Autorização negada no GitHub.",
      expired: "O código expirou. Comece de novo.",
      project_scope: "O gh não tem escopo project.",
      gh_error: "Falha no GitHub CLI (gh).",
      gh_missing: "gh não está disponível no container.",
      gh_not_logged: "gh não está autenticado no container.",
      board_fields: "Não foi possível ler as opções do board.",
      api_unreachable: "Não foi possível falar com a API. Recarregue a página.",
    };
    let text = map[code] || code;
    const fields = detail && Array.isArray(detail.fields) ? detail.fields : [];
    if (fields.length && (code === "pending_fields" || code === "pending_required" || code === "invalid_board_option")) {
      text += " Seções: " + fields.map(fieldLabel).join(", ") + ".";
    }
    if (detail && detail.hint) {
      text += " " + detail.hint;
    }
    return text;
  }

  function activeTab() {
    const hash = (window.location.hash || "").replace(/^#/, "");
    if (hash === "investigacao" || hash === "teia") {
      return hash;
    }
    return "tarefas";
  }

  function setPageTitle(text) {
    const node = document.getElementById("page-title");
    if (node) {
      node.textContent = text;
    }
    document.title = text === "FORGE" ? "FORGE" : "FORGE · " + text;
  }

  function snapshotForm() {
    const repo = document.getElementById("repo");
    const context = document.getElementById("context");
    if (repo) {
      state.form.repo = repo.value;
    }
    if (context) {
      state.form.context = context.value;
    }
    if (state.draft && document.getElementById("draft-body")) {
      const payload = currentDraftPayload();
      state.draft.body = payload.body_md;
    }
  }

  function renderNav() {
    const tab = activeTab();
    document.querySelectorAll("[data-nav]").forEach(function (link) {
      const name = link.getAttribute("data-nav");
      link.classList.toggle("current", name === tab);
    });
    const conn = document.getElementById("nav-conexoes");
    if (conn) {
      if (isOwner()) {
        conn.removeAttribute("hidden");
      } else {
        conn.setAttribute("hidden", "");
      }
    }
  }

  function rolePill(role) {
    const cls = "pill pill-role pill-role-" + role;
    return el("span", { class: cls, text: role });
  }

  function statusPill(draftStatus, status) {
    const left = draftStatus || "";
    const right = status || "";
    const label = left && right ? left + " / " + right : (left || right || "—");
    const key = (left || right).toLowerCase();
    let kind = "muted";
    if (key.indexOf("publicado") !== -1) {
      kind = "ok";
    } else if (key.indexOf("rascunho") !== -1) {
      kind = "warn";
    } else if (key.indexOf("confirmado") !== -1) {
      kind = "ok";
    } else if (key.indexOf("cancelado") !== -1) {
      kind = "danger";
    }
    return el("span", { class: "pill pill-" + kind, text: label });
  }

  function stateCard(kind, title, detail) {
    const cls = kind === "error" ? "banner banner-error" : "card state-card";
    const children = [el("p", { class: kind === "error" ? "" : "muted", text: title })];
    if (detail) {
      children.push(el("p", { class: "muted", text: detail }));
    }
    return el("section", { class: cls }, children);
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
      box.appendChild(el("p", null, [safeLink(state.pending.verification_uri)]));
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

  function fillSelect(select, options, placeholder, selected) {
    select.replaceChildren();
    select.appendChild(el("option", { value: "", text: placeholder }));
    const names = (options || []).slice();
    if (selected && names.indexOf(selected) === -1) {
      names.push(selected);
    }
    names.forEach(function (name) {
      const opt = el("option", { value: name, text: name });
      if (selected && selected === name) {
        opt.selected = true;
      }
      select.appendChild(opt);
    });
  }

  function pendingList(keys) {
    const items = (keys || []).map(function (key) {
      return el("li", { text: fieldLabel(key) });
    });
    if (!items.length) {
      return null;
    }
    return el("div", null, [
      el("p", { class: "warn", text: "Seções com [PENDENTE]:" }),
      el("ul", { class: "pending" }, items),
      el("p", { class: "muted", text: "Edite o corpo abaixo ou complemente o contexto e gere de novo." }),
    ]);
  }

  function renderEditor(root) {
    if (!isEditor()) {
      root.appendChild(el("section", { class: "card" }, [
        el("p", { class: "error", text: "Só quem tem o papel editor pode criar tarefas. O owner não implica editor; peça grant --role editor." }),
      ]));
      return;
    }

    const form = el("section", { class: "card card-tasks" }, [
      el("div", { class: "card-head" }, [
        el("span", { class: "icon-box icon-tasks", text: "A" }),
        el("h2", { text: "Nova tarefa" }),
        el("span", { class: "pill pill-tasks", text: "GESTÃO DE TAREFAS" }),
      ]),
    ]);
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
      text: state.busy ? "Aguarde…" : (state.draft ? "Gerar de novo" : "Gerar rascunho"),
      disabled: state.busy ? "disabled" : null,
      onClick: function () { generateDraft(); },
    }));
    root.appendChild(form);

    if (state.draft) {
      const preview = el("section", { class: "card card-tasks" }, [
        el("div", { class: "card-head" }, [
          el("span", { class: "icon-box icon-tasks", text: "A" }),
          el("h2", { text: "Pré-visualização" }),
        ]),
      ]);
      const pending = pendingList(state.draft.pending);
      if (pending) {
        preview.appendChild(pending);
      }
      preview.appendChild(el("label", { text: "Corpo do rascunho", for: "draft-body" }));
      const body = el("textarea", { id: "draft-body", class: "preview" });
      body.value = state.draft.body || "";
      preview.appendChild(body);
      if (state.fieldsError) {
        preview.appendChild(el("p", { class: "error", text: state.fieldsError }));
      }
      const row = el("div", { class: "row" });
      const tipo = el("select", { id: "tipo", onChange: function () { saveDraft(); } });
      const prioridade = el("select", { id: "prioridade", onChange: function () { saveDraft(); } });
      const size = el("select", { id: "size", onChange: function () { saveDraft(); } });
      fillSelect(tipo, state.fields.tipo, "Tipo", state.form.tipo);
      fillSelect(prioridade, state.fields.prioridade, "Prioridade", state.form.prioridade);
      fillSelect(size, state.fields.size, "Size", state.form.size);
      row.appendChild(el("div", null, [el("label", { text: "Tipo", for: "tipo" }), tipo]));
      row.appendChild(el("div", null, [el("label", { text: "Prioridade", for: "prioridade" }), prioridade]));
      row.appendChild(el("div", null, [el("label", { text: "Size", for: "size" }), size]));
      preview.appendChild(row);
      preview.appendChild(el("button", {
        type: "button",
        text: "Salvar rascunho",
        disabled: state.busy ? "disabled" : null,
        onClick: function () { saveDraft(); },
      }));
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

    root.appendChild(renderTaskView("Publicadas", state.published, "published"));
    root.appendChild(renderTaskView("Rascunhos", state.drafts, "drafts"));
  }

  function renderTaskView(title, tasks, kind) {
    const list = el("section", { class: "card task-view card-tasks" }, [
      el("div", { class: "card-head" }, [
        el("span", { class: "icon-box icon-delivery", text: "C" }),
        el("h2", { text: title }),
      ]),
    ]);
    if (!tasks.length) {
      list.appendChild(el("p", {
        class: "muted",
        text: kind === "published" ? "Nenhuma tarefa publicada." : "Nenhum rascunho.",
      }));
      return list;
    }
    const cols = [
      el("th", { text: "Repositório" }),
      el("th", { text: "Título" }),
      el("th", { text: "Status" }),
    ];
    if (kind === "published") {
      cols.push(el("th", { text: "Issue" }), el("th", { text: "PR" }));
    } else {
      cols.push(el("th", { text: "" }));
    }
    const table = el("table");
    table.appendChild(el("thead", null, [el("tr", null, cols)]));
    const tbody = el("tbody");
    tasks.forEach(function (task) {
      const cells = [
        el("td", { text: task.repo || "" }),
        el("td", { text: task.title || "" }),
        el("td", null, [statusPill(task.draft_status, task.status)]),
      ];
      if (kind === "published") {
        cells.push(el("td", null, [publishedIssueLink(task.issue_url)]));
        cells.push(el("td", null, [safeLink(task.pr_url, "PR")]));
      } else {
        cells.push(el("td", null, [el("button", {
          type: "button",
          class: "danger",
          text: "Descartar",
          disabled: state.busy ? "disabled" : null,
          onClick: function () { discardDraft(task.id); },
        })]));
      }
      tbody.appendChild(el("tr", null, cells));
    });
    table.appendChild(tbody);
    list.appendChild(table);
    return list;
  }

  function sourceCard(letter, iconClass, name, detail) {
    return el("button", {
      type: "button",
      class: "source-card",
      disabled: "disabled",
    }, [
      el("span", { class: "icon-box " + iconClass, text: letter }),
      el("span", { class: "source-name", text: name }),
      el("span", { class: "muted", text: detail }),
      el("span", { class: "pill pill-planned", text: "INTEGRAÇÃO PLANEJADA" }),
    ]);
  }

  function renderInvestigacao(root) {
    root.appendChild(el("section", { class: "card card-eng" }, [
      el("div", { class: "card-head" }, [
        el("span", { class: "icon-box icon-eng", text: "B" }),
        el("h2", { text: "Investigação" }),
        el("span", { class: "pill pill-proposed", text: "EM CONSTRUÇÃO" }),
      ]),
      el("p", { text: "Esta área vai reunir evidências de uma issue sem alterar os sistemas consultados." }),
      el("p", { class: "muted", text: "Em construção. O seletor e as fontes ainda não consultam a API." }),
    ]));
    root.appendChild(el("section", { class: "card" }, [
      el("h2", { text: "Issue" }),
      el("label", { text: "Issue do GitHub", for: "issue-select" }),
      el("select", { id: "issue-select", disabled: "disabled" }, [
        el("option", { value: "", text: "Selecione uma issue" }),
      ]),
      el("p", { class: "muted", text: "O seletor fica desligado até a etapa de investigação." }),
    ]));
    const sources = el("section", { class: "card" }, [
      el("div", { class: "card-head" }, [
        el("h2", { text: "Fontes" }),
        el("span", { class: "pill pill-planned", text: "SOMENTE LEITURA" }),
      ]),
      el("div", { class: "source-grid" }, [
        sourceCard("B", "icon-eng", "Código", "Repositório Git"),
        sourceCard("D", "icon-ops", "Portainer", "Containers"),
        sourceCard("F", "icon-core", "Banco", "MySQL / PostgreSQL"),
        sourceCard("F", "icon-core", "FTP", "FTP / SFTP"),
      ]),
    ]);
    root.appendChild(sources);
  }

  function renderTeia(root) {
    root.appendChild(el("section", { class: "card card-core" }, [
      el("div", { class: "card-head" }, [
        el("span", { class: "icon-box icon-core", text: "F" }),
        el("h2", { text: "Teia de contexto" }),
        el("span", { class: "pill pill-proposed", text: "EM CONSTRUÇÃO" }),
      ]),
      el("p", { text: "O vault Obsidian vai guardar notas, vínculos e o mapa de contexto da investigação." }),
      el("p", { class: "muted", text: "As notas ficam fora do Git e não substituem o banco do Forge. Esta tela ainda não está ligada ao vault." }),
    ]));
  }

  function render() {
    snapshotForm();
    const session = document.getElementById("session");
    const app = document.getElementById("app");
    renderSession(session);
    renderNav();
    app.replaceChildren();
    if (state.loading) {
      setPageTitle("Forge");
      app.appendChild(stateCard("loading", "Carregando…"));
      return;
    }
    if (state.error) {
      app.appendChild(el("p", { class: "banner banner-error error", text: errorMessage(state.error, state.errorDetail) }));
    }
    if (state.notice) {
      app.appendChild(el("p", { class: "banner banner-ok ok", text: state.notice }));
    }
    if (!state.who) {
      setPageTitle("Entrar");
      renderLogin(app);
      return;
    }
    const tab = activeTab();
    if (tab === "investigacao") {
      setPageTitle("Investigação");
      renderInvestigacao(app);
      return;
    }
    if (tab === "teia") {
      setPageTitle("Teia de contexto");
      renderTeia(app);
      return;
    }
    setPageTitle("Tarefas");
    renderEditor(app);
  }

  async function boot() {
    state.loading = true;
    render();
    try {
      await api("/api/health");
      await loadWhoami();
      if (isEditor()) {
        await loadEditorData();
      }
    } catch (err) {
      state.error = "api_unreachable";
    }
    state.loading = false;
    render();
  }

  window.addEventListener("hashchange", function () { render(); });
  boot();
})();
