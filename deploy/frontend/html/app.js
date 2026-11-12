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
    issues: [],
    issuesError: "",
    selectedIssue: "",
    notes: [],
    selectedNoteId: "",
    noteForm: { title: "", body: "" },
    vault: { enabled: false, notes: [], error: "", message: "" },
    vaultNote: null,
    graphs: [],
    graphBusy: false,
    graphQuery: "",
    graphRepo: "",
    graphNodes: [],
    graphIndex: { state: "idle", busy: false, reason: "", repos: [] },
    graphNotice: "",
    graphPollTimer: null,
    teia: { nodes: [], edges: [], truncated: false, vault: false },
    teiaRepo: "",
    teiaTypes: [],
    teiaQuery: "",
    teiaSelected: null,
    teiaCam: { x: 0, y: 0, k: 1 },
    teiaPos: {},
    teiaLayoutKey: "",
    relatedIssues: [],
  };
  const TEIA_TYPES = [
    { id: "issue", label: "Issues" },
    { id: "pr", label: "PRs" },
    { id: "note", label: "Notas" },
    { id: "vault", label: "Vault" },
    { id: "file", label: "Arquivos" },
    { id: "module", label: "Módulos" },
    { id: "class", label: "Classes" },
  ];

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
    if (canEditNotes() && activeTab() === "investigacao") {
      await loadInvestigacao();
    }
    if (canEditNotes() && activeTab() === "teia") {
      await loadTeia();
    }
    render();
  }

  function isEditor() {
    return !!(state.who && Array.isArray(state.who.roles) && state.who.roles.indexOf("editor") !== -1);
  }

  function isOwner() {
    return !!(state.who && Array.isArray(state.who.roles) && state.who.roles.indexOf("owner") !== -1);
  }

  function canEditNotes() {
    return isEditor() || isOwner();
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
      vault_disabled: "Vault Obsidian desligado: defina FORGE_OBSIDIAN_VAULT e FORGE_OBSIDIAN_ALLOW.",
      invalid_issue: "Issue inválida. Use owner/repo#número da allowlist.",
      invalid_title: "Título da nota inválido (1 a 200 caracteres).",
      invalid_body: "Corpo da nota inválido.",
      body_too_large: "Nota maior que 64 KiB.",
      not_found: "Registro não encontrado.",
      busy: "O índice do grafo já está em execução.",
      not_indexed: "Este repositório ainda não tem grafo.",
      no_release: "O repositório não tem release no GitHub.",
      graphify_missing: "graphify não está na imagem.",
      extract_failed: "Falha ao extrair o grafo (modo offline).",
      missing_output: "Graphify não gravou graph.json.",
      invalid_json: "graph.json inválido.",
      schema: "graph.json sem o formato de grafo.",
      too_large: "Grafo maior que o limite.",
      clone_failed: "Falha ao clonar o repositório para indexar.",
      path_forbidden: "Caminho fora da allowlist do vault.",
      file_too_large: "Arquivo do vault acima do limite.",
      issues_import: "Falha ao importar issues concluídas.",
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
    const issue = document.getElementById("issue-select");
    if (issue) {
      state.selectedIssue = issue.value;
    }
    const noteTitle = document.getElementById("note-title");
    const noteBody = document.getElementById("note-body");
    if (noteTitle) {
      state.noteForm.title = noteTitle.value;
    }
    if (noteBody) {
      state.noteForm.body = noteBody.value;
    }
    const graphRepo = document.getElementById("graph-repo");
    const graphQuery = document.getElementById("graph-query");
    if (graphRepo) {
      state.graphRepo = graphRepo.value;
    }
    if (graphQuery) {
      state.graphQuery = graphQuery.value;
    }
    const teiaRepo = document.getElementById("teia-repo");
    const teiaQuery = document.getElementById("teia-query");
    if (teiaRepo) {
      state.teiaRepo = teiaRepo.value;
    }
    if (teiaQuery) {
      state.teiaQuery = teiaQuery.value;
    }
    const types = [];
    TEIA_TYPES.forEach(function (item) {
      const box = document.getElementById("teia-type-" + item.id);
      if (box && box.checked) {
        types.push(item.id);
      }
    });
    if (document.getElementById("teia-type-issue")) {
      state.teiaTypes = types;
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

  async function loadInvestigacao() {
    if (!canEditNotes()) {
      return;
    }
    const issues = await api("/api/issues");
    if (issues.ok) {
      state.issues = issues.data.issues || [];
      state.issuesError = issues.data.error ? errorMessage(issues.data.error, issues.data) : "";
    } else {
      state.issues = [];
      state.issuesError = errorMessage((issues.data && issues.data.error) || "gh_error", issues.data);
    }
    if (state.selectedIssue) {
      const found = state.issues.some(function (item) { return item.issue_key === state.selectedIssue; });
      if (!found) {
        state.selectedIssue = "";
      }
    }
    await loadNotes();
    await loadRelated();
  }

  async function loadNotes() {
    if (!canEditNotes()) {
      return;
    }
    const path = state.selectedIssue
      ? "/api/notes?issue=" + encodeURIComponent(state.selectedIssue)
      : "/api/notes";
    const res = await api(path);
    if (res.ok) {
      state.notes = res.data.notes || [];
    } else {
      state.notes = [];
    }
  }

  async function selectIssue(value) {
    state.selectedIssue = value;
    state.selectedNoteId = "";
    state.noteForm = { title: "", body: "" };
    await loadNotes();
    await loadRelated();
    render();
  }

  async function loadRelated() {
    if (!canEditNotes() || !state.selectedIssue) {
      state.relatedIssues = [];
      return;
    }
    const res = await api("/api/completed-issues?issue=" + encodeURIComponent(state.selectedIssue));
    if (res.ok) {
      state.relatedIssues = res.data.issues || [];
    } else {
      state.relatedIssues = [];
    }
  }

  async function importCompletedIssues() {
    state.busy = true;
    state.error = "";
    render();
    const res = await api("/api/completed-issues/import", { method: "POST", body: {} });
    state.busy = false;
    if (!res.ok) {
      setErrorFromResponse(res.data);
      return;
    }
    const imported = res.data.imported || 0;
    const updated = res.data.updated || 0;
    state.notice = "Issues concluídas: " + imported + " novas, " + updated + " atualizadas.";
    await loadInvestigacao();
    render();
  }

  async function openNote(noteId) {
    const res = await api("/api/notes/" + encodeURIComponent(noteId));
    if (!res.ok) {
      setErrorFromResponse(res.data);
      return;
    }
    state.selectedNoteId = noteId;
    state.selectedIssue = res.data.issue_key || state.selectedIssue;
    state.noteForm.title = res.data.title || "";
    state.noteForm.body = res.data.body || "";
    render();
  }

  function newNote() {
    state.selectedNoteId = "";
    state.noteForm = { title: "", body: "" };
    render();
  }

  async function saveNote() {
    if (!state.selectedIssue) {
      setError("invalid_issue");
      return;
    }
    const titleEl = document.getElementById("note-title");
    const bodyEl = document.getElementById("note-body");
    const title = titleEl ? titleEl.value : state.noteForm.title;
    const body = bodyEl ? bodyEl.value : state.noteForm.body;
    state.noteForm.title = title;
    state.noteForm.body = body;
    state.busy = true;
    state.error = "";
    render();
    const payload = { issue_key: state.selectedIssue, title: title, body: body };
    const path = state.selectedNoteId
      ? "/api/notes/" + encodeURIComponent(state.selectedNoteId)
      : "/api/notes";
    const res = await api(path, { method: "POST", body: payload });
    state.busy = false;
    if (!res.ok) {
      setErrorFromResponse(res.data);
      return;
    }
    state.selectedNoteId = res.data.id;
    state.noteForm.title = res.data.title || title;
    state.noteForm.body = res.data.body || body;
    state.notice = "Nota salva.";
    await loadNotes();
    render();
  }

  async function deleteNote() {
    if (!state.selectedNoteId) {
      return;
    }
    state.busy = true;
    state.error = "";
    render();
    const res = await api("/api/notes/" + encodeURIComponent(state.selectedNoteId) + "/delete", {
      method: "POST",
      body: {},
    });
    state.busy = false;
    if (!res.ok) {
      setErrorFromResponse(res.data);
      return;
    }
    state.selectedNoteId = "";
    state.noteForm = { title: "", body: "" };
    state.notice = "Nota apagada.";
    await loadNotes();
    render();
  }

  function stopGraphPoll() {
    if (state.graphPollTimer) {
      window.clearInterval(state.graphPollTimer);
      state.graphPollTimer = null;
    }
  }

  function startGraphPoll() {
    if (state.graphPollTimer) {
      return;
    }
    state.graphPollTimer = window.setInterval(async function () {
      const res = await api("/api/graphs/status");
      if (!res.ok) {
        return;
      }
      state.graphIndex = res.data;
      const running = !!(res.data.busy || res.data.state === "running");
      state.graphBusy = running;
      if (!running) {
        stopGraphPoll();
        state.graphNotice = "";
        state.notice = "Índice atualizado.";
        await loadTeia();
      }
      render();
    }, 2000);
  }

  async function loadTeia() {
    if (!canEditNotes()) {
      return;
    }
    const params = new URLSearchParams();
    if (state.teiaRepo) {
      params.set("repo", state.teiaRepo);
    }
    if (state.teiaTypes && state.teiaTypes.length && state.teiaTypes.length < TEIA_TYPES.length) {
      params.set("types", state.teiaTypes.join(","));
    }
    if (state.teiaQuery) {
      params.set("q", state.teiaQuery);
    }
    const graph = await api("/api/context-graph?" + params.toString());
    if (graph.ok) {
      state.teia = {
        nodes: graph.data.nodes || [],
        edges: graph.data.edges || [],
        truncated: !!graph.data.truncated,
        vault: !!graph.data.vault,
      };
      state.vault.enabled = !!graph.data.vault;
    } else if (graph.status === 401 || graph.status === 403) {
      setErrorFromResponse(graph.data);
    }
    const graphs = await api("/api/graphs");
    if (graphs.ok) {
      state.graphs = graphs.data.graphs || [];
      state.graphIndex = {
        state: graphs.data.state || "idle",
        busy: !!graphs.data.busy,
        reason: graphs.data.reason || "",
        repos: graphs.data.repos || [],
      };
      state.graphBusy = !!(graphs.data.busy || graphs.data.state === "running");
      if (!state.teiaRepo && state.graphs.length) {
        state.graphRepo = state.graphs[0].repo;
      }
      if (state.graphBusy) {
        state.graphNotice = "Indexando…";
        startGraphPoll();
      }
    }
  }

  async function applyTeiaFilters() {
    snapshotForm();
    state.teiaSelected = null;
    state.teiaLayoutKey = "";
    await loadTeia();
    render();
  }

  async function refreshGraph(repo) {
    state.error = "";
    const body = repo ? { repo: repo } : {};
    const res = await api("/api/graphs/refresh", { method: "POST", body: body });
    if (!res.ok) {
      setErrorFromResponse(res.data);
      return;
    }
    state.graphIndex = res.data;
    state.graphBusy = !!(res.data.busy || res.data.state === "running");
    if (state.graphBusy) {
      state.graphNotice = "Indexando…";
      startGraphPoll();
    } else {
      state.graphNotice = "";
      state.notice = "Índice atualizado.";
      await loadTeia();
    }
    render();
  }

  function svgEl(tag, attrs, children) {
    const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
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

  function layoutTeia(nodes, edges) {
    const n = nodes.length;
    if (!n) {
      return;
    }
    const W = 1200;
    const H = 800;
    const key = nodes.map(function (item) { return item.id; }).join("|");
    if (state.teiaLayoutKey === key && Object.keys(state.teiaPos).length) {
      nodes.forEach(function (item) {
        const pos = state.teiaPos[item.id];
        if (pos) {
          item.x = pos.x;
          item.y = pos.y;
        }
      });
      return;
    }
    const iters = n > 350 ? 24 : n > 150 ? 36 : 48;
    nodes.forEach(function (item, i) {
      const angle = (i / n) * Math.PI * 2;
      const radius = 160 + (i % 7) * 18;
      item.x = W / 2 + Math.cos(angle) * radius;
      item.y = H / 2 + Math.sin(angle) * radius;
      item.vx = 0;
      item.vy = 0;
    });
    const index = {};
    nodes.forEach(function (item, i) { index[item.id] = i; });
    const links = [];
    edges.forEach(function (edge) {
      const a = index[edge.source];
      const b = index[edge.target];
      if (a !== undefined && b !== undefined) {
        links.push([a, b]);
      }
    });
    const cell = 48;
    for (let t = 0; t < iters; t += 1) {
      const grid = {};
      nodes.forEach(function (item, i) {
        const cx = Math.floor(item.x / cell);
        const cy = Math.floor(item.y / cell);
        const gk = cx + "," + cy;
        if (!grid[gk]) {
          grid[gk] = [];
        }
        grid[gk].push(i);
      });
      nodes.forEach(function (item, i) {
        const cx = Math.floor(item.x / cell);
        const cy = Math.floor(item.y / cell);
        let fx = (W / 2 - item.x) * 0.002;
        let fy = (H / 2 - item.y) * 0.002;
        for (let dx = -1; dx <= 1; dx += 1) {
          for (let dy = -1; dy <= 1; dy += 1) {
            const bucket = grid[(cx + dx) + "," + (cy + dy)] || [];
            bucket.forEach(function (j) {
              if (j <= i) {
                return;
              }
              const other = nodes[j];
              let diffX = item.x - other.x;
              let diffY = item.y - other.y;
              let dist2 = diffX * diffX + diffY * diffY || 0.01;
              const force = 220 / dist2;
              const dist = Math.sqrt(dist2);
              diffX /= dist;
              diffY /= dist;
              item.vx += diffX * force;
              item.vy += diffY * force;
              other.vx -= diffX * force;
              other.vy -= diffY * force;
            });
          }
        }
        item.vx += fx;
        item.vy += fy;
      });
      links.forEach(function (pair) {
        const a = nodes[pair[0]];
        const b = nodes[pair[1]];
        const diffX = b.x - a.x;
        const diffY = b.y - a.y;
        a.vx += diffX * 0.012;
        a.vy += diffY * 0.012;
        b.vx -= diffX * 0.012;
        b.vy -= diffY * 0.012;
      });
      nodes.forEach(function (item) {
        item.vx *= 0.72;
        item.vy *= 0.72;
        item.x += item.vx;
        item.y += item.vy;
      });
    }
    const pos = {};
    nodes.forEach(function (item) {
      pos[item.id] = { x: item.x, y: item.y };
    });
    state.teiaPos = pos;
    state.teiaLayoutKey = key;
  }

  function attachTeiaPan(svg, inner) {
    let dragging = false;
    let moved = false;
    let lastX = 0;
    let lastY = 0;
    function apply() {
      inner.setAttribute(
        "transform",
        "translate(" + state.teiaCam.x + " " + state.teiaCam.y + ") scale(" + state.teiaCam.k + ")",
      );
    }
    apply();
    svg.addEventListener("wheel", function (ev) {
      ev.preventDefault();
      const rect = svg.getBoundingClientRect();
      const mx = ((ev.clientX - rect.left) / rect.width) * 1200;
      const my = ((ev.clientY - rect.top) / rect.height) * 800;
      const factor = ev.deltaY < 0 ? 1.12 : 0.9;
      const next = Math.max(0.25, Math.min(4, state.teiaCam.k * factor));
      const zx = (mx - state.teiaCam.x) / state.teiaCam.k;
      const zy = (my - state.teiaCam.y) / state.teiaCam.k;
      state.teiaCam.k = next;
      state.teiaCam.x = mx - zx * next;
      state.teiaCam.y = my - zy * next;
      apply();
    }, { passive: false });
    svg.addEventListener("pointerdown", function (ev) {
      if (ev.button !== 0) {
        return;
      }
      dragging = true;
      moved = false;
      lastX = ev.clientX;
      lastY = ev.clientY;
      svg.classList.add("dragging");
      svg.setPointerCapture(ev.pointerId);
    });
    svg.addEventListener("pointermove", function (ev) {
      if (!dragging) {
        return;
      }
      const dx = ev.clientX - lastX;
      const dy = ev.clientY - lastY;
      if (Math.abs(dx) + Math.abs(dy) > 3) {
        moved = true;
      }
      lastX = ev.clientX;
      lastY = ev.clientY;
      state.teiaCam.x += dx;
      state.teiaCam.y += dy;
      apply();
    });
    function endDrag() {
      dragging = false;
      svg.classList.remove("dragging");
      svg._teiaMoved = moved;
    }
    svg.addEventListener("pointerup", endDrag);
    svg.addEventListener("pointercancel", endDrag);
  }

  function renderTeiaCanvas() {
    const nodes = (state.teia.nodes || []).map(function (item) { return Object.assign({}, item); });
    const edges = state.teia.edges || [];
    layoutTeia(nodes, edges);
    const svg = svgEl("svg", {
      class: "teia-svg",
      viewBox: "0 0 1200 800",
      role: "img",
    });
    const inner = svgEl("g", { class: "teia-world" });
    const needle = (state.teiaQuery || "").trim().toLowerCase();
    edges.forEach(function (edge) {
      const a = nodes.find(function (n) { return n.id === edge.source; });
      const b = nodes.find(function (n) { return n.id === edge.target; });
      if (!a || !b) {
        return;
      }
      inner.appendChild(svgEl("line", {
        x1: String(a.x), y1: String(a.y), x2: String(b.x), y2: String(b.y),
        class: "teia-edge teia-edge-" + (edge.type || "rel"),
      }));
    });
    nodes.forEach(function (item) {
      const hay = ((item.label || "") + " " + (item.path || "") + " " + (item.id || "")).toLowerCase();
      const hit = needle && hay.indexOf(needle) !== -1;
      const dim = needle && !hit;
      const g = svgEl("g", {
        class: "teia-node teia-n-" + (item.type || "file") + (hit ? " teia-hit" : "") + (dim ? " teia-dim" : ""),
      });
      g.appendChild(svgEl("circle", { cx: String(item.x), cy: String(item.y), r: item.type === "issue" ? "9" : "7" }));
      g.appendChild(svgEl("text", {
        x: String(item.x + 12), y: String(item.y + 4),
        text: String(item.label || item.id || "").slice(0, 42),
      }));
      g.addEventListener("click", function (ev) {
        if (svg._teiaMoved) {
          return;
        }
        ev.stopPropagation();
        state.teiaSelected = item;
        render();
      });
      inner.appendChild(g);
    });
    svg.appendChild(inner);
    svg.addEventListener("click", function () {
      if (svg._teiaMoved) {
        return;
      }
      state.teiaSelected = null;
      render();
    });
    attachTeiaPan(svg, inner);
    return svg;
  }

  function renderInvestigacao(root) {
    root.appendChild(el("section", { class: "card card-eng" }, [
      el("div", { class: "card-head" }, [
        el("span", { class: "icon-box icon-eng", text: "B" }),
        el("h2", { text: "Investigação" }),
        el("span", { class: "pill pill-eng", text: "NOTAS" }),
      ]),
      el("p", { text: "Notas manuais por issue, no banco do Forge. Independente do vault Obsidian." }),
      el("p", { class: "muted", text: "Markdown aparece como texto. O corpo da nota não vai para o log." }),
    ]));
    if (!canEditNotes()) {
      root.appendChild(el("section", { class: "card" }, [
        el("p", { class: "error", text: "Só editor ou owner vê as notas da investigação." }),
      ]));
      return;
    }
    const issueBox = el("section", { class: "card" }, [
      el("h2", { text: "Issue" }),
      el("label", { text: "Issue do GitHub", for: "issue-select" }),
    ]);
    const select = el("select", {
      id: "issue-select",
      onChange: function (ev) { selectIssue(ev.target.value); },
    });
    select.appendChild(el("option", { value: "", text: "Selecione uma issue" }));
    state.issues.forEach(function (item) {
      const label = item.issue_key + (item.title ? " — " + item.title : "");
      const opt = el("option", { value: item.issue_key, text: label });
      if (state.selectedIssue === item.issue_key) {
        opt.selected = true;
      }
      select.appendChild(opt);
    });
    issueBox.appendChild(select);
    if (state.issuesError) {
      issueBox.appendChild(el("p", { class: "muted", text: state.issuesError }));
    }
    if (isOwner()) {
      issueBox.appendChild(el("div", { class: "row" }, [
        el("button", {
          type: "button",
          class: "primary",
          text: state.busy ? "Aguarde…" : "Importar issues concluídas",
          disabled: state.busy ? "disabled" : null,
          onClick: function () { importCompletedIssues(); },
        }),
      ]));
    }
    root.appendChild(issueBox);

    const notesCard = el("section", { class: "card card-eng" }, [
      el("div", { class: "card-head" }, [
        el("h2", { text: "Notas" }),
        el("span", { class: "pill pill-eng", text: "FORGE" }),
      ]),
    ]);
    const list = el("div", { class: "note-list" });
    if (!state.notes.length) {
      list.appendChild(el("p", { class: "muted", text: "Nenhuma nota nesta issue." }));
    }
    state.notes.forEach(function (note) {
      list.appendChild(el("button", {
        type: "button",
        class: "note-item" + (state.selectedNoteId === note.id ? " active" : ""),
        text: (note.title || "(sem título)") + " · " + note.size + " B",
        onClick: function () { openNote(note.id); },
      }));
    });
    const editor = el("div", null, [
      el("label", { text: "Título", for: "note-title" }),
      el("input", { id: "note-title", type: "text", maxlength: "200", value: state.noteForm.title || "" }),
      el("label", { text: "Corpo (markdown, exibido como texto)", for: "note-body" }),
    ]);
    const noteBody = el("textarea", { id: "note-body", class: "preview" });
    noteBody.value = state.noteForm.body || "";
    editor.appendChild(noteBody);
    editor.appendChild(el("div", { class: "row" }, [
      el("button", {
        type: "button",
        class: "primary",
        text: state.busy ? "Aguarde…" : (state.selectedNoteId ? "Salvar nota" : "Criar nota"),
        disabled: state.busy ? "disabled" : null,
        onClick: function () { saveNote(); },
      }),
      el("button", {
        type: "button",
        text: "Nova nota",
        disabled: state.busy ? "disabled" : null,
        onClick: function () { newNote(); },
      }),
      state.selectedNoteId ? el("button", {
        type: "button",
        class: "danger",
        text: "Apagar",
        disabled: state.busy ? "disabled" : null,
        onClick: function () { deleteNote(); },
      }) : null,
    ]));
    notesCard.appendChild(el("div", { class: "notes-grid" }, [list, editor]));
    const relatedCard = el("section", { class: "card card-eng" }, [
      el("div", { class: "card-head" }, [
        el("h2", { text: "Issues relacionadas" }),
        el("span", { class: "pill pill-eng", text: "CONCLUÍDAS" }),
      ]),
    ]);
    if (!state.selectedIssue) {
      relatedCard.appendChild(el("p", { class: "muted", text: "Selecione uma issue para ver concluídas semelhantes." }));
    } else if (!state.relatedIssues.length) {
      relatedCard.appendChild(el("p", { class: "muted", text: "Nenhuma issue concluída semelhante. Owner pode importar o board." }));
    } else {
      const relatedList = el("div", { class: "note-list" });
      state.relatedIssues.forEach(function (item) {
        const key = item.issue_key || ((item.repo || "") + "#" + item.number);
        const title = item.title || key;
        const block = el("div", { class: "related-item" }, [
          safeLink(item.url, key + " — " + title),
        ]);
        (item.prs || []).forEach(function (pr) {
          if (!pr) {
            return;
          }
          const files = (pr.files || []).slice(0, 6).join(", ");
          block.appendChild(safeLink(pr.url, "PR #" + pr.number + (files ? ": " + files : "")));
        });
        (item.nodes || []).slice(0, 6).forEach(function (node) {
          block.appendChild(el("p", {
            class: "muted",
            text: (node.label || node.id || "") + (node.file ? " · " + node.file : ""),
          }));
        });
        relatedList.appendChild(block);
      });
      relatedCard.appendChild(relatedList);
    }
    root.appendChild(el("div", { class: "investigacao-split" }, [notesCard, relatedCard]));

    const sources = el("section", { class: "card" }, [
      el("div", { class: "card-head" }, [
        el("h2", { text: "Fontes" }),
        el("span", { class: "pill pill-planned", text: "SOMENTE LEITURA" }),
      ]),
      el("p", { class: "muted", text: "Em construção: as outras fontes ainda não consultam a API." }),
      el("div", { class: "source-grid" }, [
        sourceCard("B", "icon-eng", "Código", "Repositório Git"),
        sourceCard("D", "icon-ops", "Portainer", "Containers"),
        sourceCard("F", "icon-core", "Banco", "MySQL / PostgreSQL"),
        sourceCard("F", "icon-core", "FTP", "FTP / SFTP"),
        sourceCard("F", "icon-core", "Obsidian", "Vault (aba Teia)"),
      ]),
    ]);
    root.appendChild(sources);
  }

  function renderTeia(root) {
    const vaultEnabled = !!(state.teia && state.teia.vault);
    const indexing = !!state.graphBusy;
    root.appendChild(el("section", { class: "card card-core" }, [
      el("div", { class: "card-head" }, [
        el("span", { class: "icon-box icon-core", text: "F" }),
        el("h2", { text: "Teia de contexto" }),
        el("span", {
          class: vaultEnabled ? "pill pill-ok" : "pill pill-proposed",
          text: vaultEnabled ? "VAULT" : "DESLIGADO",
        }),
      ]),
      el("p", { text: "Grafo combinado: código Graphify, issues, PRs, notas manuais e vault (se ligado)." }),
      el("p", { class: "muted", text: "O corpo das notas não entra no payload nem no log. Zoom com a roda; arraste para pan." }),
    ]));
    if (!canEditNotes()) {
      root.appendChild(el("section", { class: "card" }, [
        el("p", { class: "error", text: "Só editor ou owner lê o vault e o grafo." }),
      ]));
      return;
    }
    if (state.graphNotice || indexing) {
      root.appendChild(el("p", { class: "banner banner-info", text: state.graphNotice || "Indexando…" }));
      const prog = el("ul", { class: "teia-progress" });
      (state.graphIndex.repos || []).forEach(function (row) {
        const reason = row.error || row.hint || "";
        prog.appendChild(el("li", {
          text: (row.repo || "") + " · " + (row.status || "queued") + (reason ? " (" + reason + ")" : ""),
        }));
      });
      if ((state.graphIndex.repos || []).length) {
        root.appendChild(prog);
      }
    }
    const filters = el("section", { class: "card" }, [
      el("div", { class: "card-head" }, [
        el("h2", { text: "Filtros" }),
        el("span", { class: "pill pill-core", text: "TEIA" }),
      ]),
    ]);
    const repoSelect = el("select", { id: "teia-repo" });
    repoSelect.appendChild(el("option", { value: "", text: "Todos os repositórios" }));
    state.graphs.forEach(function (g) {
      const opt = el("option", { value: g.repo, text: g.repo });
      if (state.teiaRepo === g.repo) {
        opt.selected = true;
      }
      repoSelect.appendChild(opt);
    });
    const q = el("input", {
      id: "teia-query", type: "search", value: state.teiaQuery || "",
      placeholder: "Buscar e destacar",
    });
    const types = el("div", { class: "teia-types" });
    TEIA_TYPES.forEach(function (item) {
      const checked = !state.teiaTypes.length || state.teiaTypes.indexOf(item.id) !== -1;
      const box = el("input", {
        id: "teia-type-" + item.id, type: "checkbox",
      });
      if (checked) {
        box.checked = true;
      }
      types.appendChild(el("label", { class: "teia-type", for: "teia-type-" + item.id }, [
        box,
        el("span", { text: item.label }),
      ]));
    });
    filters.appendChild(el("div", { class: "graph-query" }, [
      el("div", null, [el("label", { text: "Repositório", for: "teia-repo" }), repoSelect]),
      el("div", null, [el("label", { text: "Busca", for: "teia-query" }), q]),
      el("button", {
        type: "button",
        text: "Aplicar",
        onClick: function () { applyTeiaFilters(); },
      }),
    ]));
    filters.appendChild(types);
    root.appendChild(filters);

    if (state.teia.truncated) {
      root.appendChild(el("p", {
        class: "banner banner-warn teia-trunc",
        text: "Grafo truncado: mostrando os nós mais ligados a issues e notas.",
      }));
    }

    const wrap = el("div", { class: "teia-wrap" });
    const canvas = el("div", { class: "teia-canvas" });
    if (!(state.teia.nodes || []).length) {
      canvas.appendChild(el("p", { class: "muted", text: "Nenhum nó neste recorte. Importe issues ou aguarde o índice Graphify." }));
    } else {
      canvas.appendChild(renderTeiaCanvas());
    }
    wrap.appendChild(canvas);
    const panel = el("aside", { class: "teia-panel card" }, [
      el("h2", { text: "Detalhe" }),
    ]);
    const selected = state.teiaSelected;
    if (!selected) {
      panel.appendChild(el("p", { class: "muted", text: "Clique num nó para ver o detalhe." }));
    } else {
      panel.appendChild(el("p", { class: "pill pill-core", text: selected.type || "" }));
      panel.appendChild(el("h3", { text: selected.label || selected.id }));
      if (selected.repo) {
        panel.appendChild(el("p", { text: selected.repo }));
      }
      if (selected.path) {
        panel.appendChild(el("p", { class: "muted", text: selected.path }));
      }
      if (selected.url) {
        panel.appendChild(safeLink(selected.url, selected.type === "pr" ? "Abrir PR" : selected.type === "file" || selected.type === "class" ? "Abrir no GitHub" : "Abrir issue"));
      }
    }
    wrap.appendChild(panel);
    root.appendChild(wrap);

    const graphCard = el("section", { class: "card card-eng" }, [
      el("div", { class: "card-head" }, [
        el("h2", { text: "Grafos Graphify" }),
        el("span", { class: "pill pill-eng", text: "OFFLINE" }),
      ]),
      el("p", { class: "muted", text: "Índice de código dos 5 repositórios da allowlist. Sem LLM." }),
    ]);
    if (!state.graphs.length) {
      graphCard.appendChild(el("p", { class: "muted", text: "Nenhum grafo ainda." }));
    } else {
      const table = el("table");
      table.appendChild(el("thead", null, [el("tr", null, [
        el("th", { text: "Repositório" }),
        el("th", { text: "Ref" }),
        el("th", { text: "Data" }),
        el("th", { text: "Nós" }),
        el("th", { text: "Arestas" }),
      ])]));
      const tbody = el("tbody");
      state.graphs.forEach(function (g) {
        const ref = g.tag || (g.source === "head" ? ("HEAD " + (g.ref || "")) : (g.ref || g.error || "—"));
        tbody.appendChild(el("tr", null, [
          el("td", { text: g.repo || "" }),
          el("td", { text: ref }),
          el("td", { text: g.indexed_at || "—" }),
          el("td", { text: String(g.nodes || 0) }),
          el("td", { text: String(g.edges || 0) }),
        ]));
      });
      table.appendChild(tbody);
      graphCard.appendChild(table);
    }
    if (isOwner()) {
      graphCard.appendChild(el("button", {
        type: "button",
        class: "primary",
        text: indexing ? "Indexando…" : "Atualizar grafo",
        disabled: indexing ? "disabled" : null,
        onClick: function () { refreshGraph(state.teiaRepo || state.graphRepo); },
      }));
    }
    root.appendChild(graphCard);
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
      if (canEditNotes() && activeTab() === "investigacao") {
        await loadInvestigacao();
      }
      if (canEditNotes() && activeTab() === "teia") {
        await loadTeia();
      }
    } catch (err) {
      state.error = "api_unreachable";
    }
    state.loading = false;
    render();
  }

  window.addEventListener("hashchange", async function () {
    const tab = activeTab();
    if (tab === "investigacao" && canEditNotes()) {
      await loadInvestigacao();
    }
    if (tab === "teia" && canEditNotes()) {
      await loadTeia();
    }
    render();
  });
  boot();
})();
