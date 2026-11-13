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
    teiaExpanded: {},
    relatedIssues: [],
    invest: {
      repos: [],
      connections: [],
      list: [],
      current: null,
      form: { description: "", repos: [], connectionIds: [], issueKey: "" },
      busy: false,
      error: "",
      notice: "",
    },
    agentes: {
      items: [],
      metrics: null,
      approvals: [],
      selectedId: "",
      selected: null,
      executions: [],
      form: null,
      busy: false,
      error: "",
      notice: "",
    },
  };
  let teiaCtl = null;
  let teiaCanvas = null;
  let teiaKey = "";
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

  state.who = readCachedWho();
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

  function pageHeader(eyebrow, title, subtitle) {
    return el("header", { class: "page-header" }, [
      el("p", { class: "page-eyebrow", text: eyebrow }),
      el("h2", { class: "page-title", text: title }),
      subtitle ? el("p", { class: "page-subtitle", text: subtitle }) : null,
    ]);
  }

  function relativeTime(iso) {
    if (!iso) {
      return "—";
    }
    const then = new Date(iso).getTime();
    if (Number.isNaN(then)) {
      return "—";
    }
    const sec = Math.round((Date.now() - then) / 1000);
    if (sec < 5) {
      return "agora";
    }
    if (sec < 60) {
      return "há " + sec + " s";
    }
    const min = Math.round(sec / 60);
    if (min < 60) {
      return "há " + min + " min";
    }
    const hour = Math.round(min / 60);
    if (hour < 24) {
      return "há " + hour + " h";
    }
    const day = Math.round(hour / 24);
    return "há " + day + " d";
  }

  function splitCsv(text) {
    return String(text || "")
      .split(",")
      .map(function (s) { return s.trim(); })
      .filter(Boolean);
  }

  function openModal(opts) {
    const trigger = document.activeElement;
    const titleId = "modal-title-" + Math.random().toString(36).slice(2, 8);
    const overlay = el("div", { class: "modal-overlay" });
    function close() {
      document.removeEventListener("keydown", onKey);
      overlay.remove();
      if (trigger && typeof trigger.focus === "function") {
        trigger.focus();
      }
    }
    function onKey(ev) {
      if (ev.key === "Escape") {
        close();
      }
    }
    const dialog = el("div", {
      class: "modal-dialog", role: "dialog", "aria-modal": "true", "aria-labelledby": titleId,
    });
    const head = el("div", { class: "modal-head" }, [
      el("h2", { id: titleId, text: opts.title }),
      el("button", { type: "button", class: "modal-close", "aria-label": "Fechar", text: "×", onClick: close }),
    ]);
    const body = el("div", { class: "modal-body" });
    dialog.appendChild(head);
    dialog.appendChild(body);
    overlay.appendChild(dialog);
    document.addEventListener("keydown", onKey);
    overlay.addEventListener("mousedown", function (ev) {
      if (ev.target === overlay) {
        close();
      }
    });
    document.body.appendChild(overlay);
    opts.build(body, close);
    const focusable = dialog.querySelector("input, textarea, select, button:not(.modal-close)");
    if (focusable) {
      focusable.focus();
    }
    return { close: close, body: body };
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
    render();
    if (isEditor()) {
      await loadEditorData();
      render();
    }
    if (canEditNotes() && activeTab() === "investigacao") {
      await loadInvestigacao();
      render();
    }
    if (canEditNotes() && activeTab() === "teia") {
      await loadTeia();
      render();
    }
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
    clearCachedWho();
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
      invalid_description: "Descreva o problema (até 8 KiB).",
      invalid_repos: "Lista de repositórios inválida.",
      invalid_connection_ids: "Lista de conexões inválida.",
      secret_in_prompt: "O contexto tocaria um segredo; ajuste a descrição.",
      repo_required: "Escolha um repositório para a tarefa.",
      provider_missing: "Nenhum motor de LLM configurado no servidor.",
      claude_cli_missing: "Claude Code CLI não está disponível no container.",
      cursor_cli_missing: "Cursor CLI não está disponível no container.",
      claude_cli_error: "Falha ao rodar o Claude Code CLI.",
      provider_error: "Falha no motor de investigação.",
      confirm_mismatch: "Confirmação não bate com owner/repo#número.",
      issue_delete_forbidden: "Sem permissão de admin para apagar; é possível fechar como não planejada.",
      invalid_issue_delete: "Não foi possível identificar a issue.",
      invalid_name: "Informe um nome para o agente.",
      invalid_scope: "Escolha um escopo válido.",
      invalid_status: "Status inválido.",
      invalid_trigger: "Gatilho inválido.",
      invalid_engine: "Motor inválido.",
      invalid_permissions: "Lista de permissões inválida.",
      write_denied_resource: "Banco, FTP/SFTP e Portainer nunca recebem permissão de escrita.",
      name_taken: "Já existe um agente com esse nome.",
      already_decided: "Esta aprovação já foi decidida.",
      invalid_decision: "Decisão inválida.",
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
    if (hash === "investigacao" || hash === "teia" || hash === "agentes") {
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
    snapshotInvestForm();
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
    const agentes = document.getElementById("nav-agentes");
    if (agentes) {
      if (canEditNotes()) {
        agentes.removeAttribute("hidden");
      } else {
        agentes.setAttribute("hidden", "");
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
    root.appendChild(pageHeader("01 — TAREFAS", "Tarefas", "Gere, revise e publique tarefas a partir de um contexto escrito, para os repositórios da allowlist."));
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
      cols.push(el("th", { text: "Issue" }), el("th", { text: "PR" }), el("th", { text: "" }));
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
        const parts = splitOwnerRepo(task.repo);
        const number = issueNumberFromUrl(task.issue_url);
        const del = deleteIssueButton(parts.owner, parts.repo, number, async function () {
          state.notice = "Issue apagada.";
          await loadEditorData();
          render();
        });
        cells.push(el("td", null, [del]));
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

  function mdInline(text, target) {
    const re = /\*\*(.+?)\*\*|`([^`]+)`/g;
    let last = 0;
    let m;
    while ((m = re.exec(text))) {
      if (m.index > last) {
        target.appendChild(document.createTextNode(text.slice(last, m.index)));
      }
      if (m[1] !== undefined) {
        target.appendChild(el("strong", { text: m[1] }));
      } else {
        target.appendChild(el("code", { text: m[2] }));
      }
      last = re.lastIndex;
    }
    if (last < text.length) {
      target.appendChild(document.createTextNode(text.slice(last)));
    }
    return target;
  }

  function renderMarkdownNodes(text) {
    const lines = String(text || "").replace(/\r\n/g, "\n").split("\n");
    const out = [];
    let para = [];
    let i = 0;
    function flushPara() {
      if (para.length) {
        out.push(mdInline(para.join(" "), el("p", null, [])));
        para = [];
      }
    }
    while (i < lines.length) {
      const line = lines[i];
      const heading = /^(#{1,4})\s+(.*)$/.exec(line);
      if (heading) {
        flushPara();
        const tag = "h" + Math.min(6, heading[1].length + 2);
        out.push(mdInline(heading[2], el(tag, null, [])));
        i += 1;
        continue;
      }
      if (/^[-*]\s+/.test(line)) {
        flushPara();
        const ul = el("ul", { class: "markdown-list" }, []);
        while (i < lines.length && /^[-*]\s+/.test(lines[i])) {
          ul.appendChild(mdInline(lines[i].replace(/^[-*]\s+/, ""), el("li", null, [])));
          i += 1;
        }
        out.push(ul);
        continue;
      }
      if (line.trim() === "") {
        flushPara();
        i += 1;
        continue;
      }
      para.push(line.trim());
      i += 1;
    }
    flushPara();
    if (!out.length) {
      out.push(el("p", { class: "muted", text: "Sem resultado." }));
    }
    return out;
  }

  function readonlySeal() {
    return el("p", { class: "banner banner-info seal-readonly" }, [
      el("span", { class: "pill pill-ok", text: "SOMENTE LEITURA" }),
      el("span", { text: "Agentes não alteram dados nem recebem suas credenciais de escrita." }),
    ]);
  }

  async function loadInvestRepos() {
    const res = await api("/api/investigations/repos");
    state.invest.repos = res.ok ? (res.data.repos || []) : [];
  }

  async function loadInvestConnections() {
    const res = await api("/api/connections");
    if (res.ok && res.data.enabled !== false && Array.isArray(res.data.connections)) {
      state.invest.connections = res.data.connections;
    } else {
      state.invest.connections = [];
    }
  }

  async function loadInvestList() {
    const res = await api("/api/investigations");
    state.invest.list = res.ok ? (res.data.investigations || []) : [];
  }

  function toggleInvestRepo(repo, checked) {
    const list = state.invest.form.repos;
    const idx = list.indexOf(repo);
    if (checked && idx === -1) {
      list.push(repo);
    } else if (!checked && idx !== -1) {
      list.splice(idx, 1);
    }
  }

  function toggleInvestConnection(id, checked) {
    const list = state.invest.form.connectionIds;
    const idx = list.indexOf(id);
    if (checked && idx === -1) {
      list.push(id);
    } else if (!checked && idx !== -1) {
      list.splice(idx, 1);
    }
  }

  function snapshotInvestForm() {
    const desc = document.getElementById("invest-description");
    if (desc) {
      state.invest.form.description = desc.value;
    }
    const issueKey = document.getElementById("invest-issue-key");
    if (issueKey) {
      state.invest.form.issueKey = issueKey.value;
    }
  }

  async function runInvestigation() {
    snapshotInvestForm();
    const form = state.invest.form;
    if (!form.description.trim()) {
      state.invest.error = "invalid_description";
      render();
      return;
    }
    state.invest.busy = true;
    state.invest.error = "";
    state.invest.notice = "";
    render();
    const body = {
      description: form.description,
      repos: form.repos.slice(),
      connection_ids: form.connectionIds.slice(),
    };
    if (form.issueKey && form.issueKey.trim()) {
      body.issue_key = form.issueKey.trim();
    }
    const res = await api("/api/investigations/run", { method: "POST", body: body });
    state.invest.busy = false;
    if (!res.ok) {
      state.invest.error = (res.data && res.data.error) || "error";
      render();
      return;
    }
    state.invest.current = res.data;
    state.invest.notice = "Investigação concluída.";
    await loadInvestList();
    render();
  }

  async function openInvestigation(id) {
    const res = await api("/api/investigations/" + encodeURIComponent(id));
    if (!res.ok) {
      state.invest.error = (res.data && res.data.error) || "error";
      render();
      return;
    }
    state.invest.current = res.data;
    state.invest.notice = "";
    render();
  }

  async function investigationToTask(id, repo) {
    state.invest.busy = true;
    state.invest.error = "";
    render();
    const res = await api("/api/investigations/" + encodeURIComponent(id) + "/to-task", {
      method: "POST",
      body: repo ? { repo: repo } : {},
    });
    state.invest.busy = false;
    if (!res.ok) {
      state.invest.error = (res.data && res.data.error) || "error";
      render();
      return;
    }
    state.invest.notice = "Rascunho de tarefa criado a partir da investigação. Veja na aba Tarefas.";
    render();
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
    await loadInvestRepos();
    await loadInvestConnections();
    await loadInvestList();
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

  function splitOwnerRepo(full) {
    const parts = String(full || "").split("/");
    return { owner: parts[0] || "", repo: parts[1] || "" };
  }

  function issueNumberFromUrl(url) {
    const m = /\/issues\/(\d+)/.exec(String(url || ""));
    return m ? parseInt(m[1], 10) : null;
  }

  function openDeleteIssueModal(owner, repoName, number, onDeleted) {
    const expected = owner + "/" + repoName + "#" + number;
    const form = { confirm: "", busy: false, error: "" };
    let modal = null;
    function paint(body) {
      body.replaceChildren();
      body.appendChild(el("p", null, [
        el("span", { text: "Isto apaga a issue " }),
        el("span", { class: "modal-confirm-key", text: expected }),
        el("span", { text: " no GitHub (ou fecha como não planejada) e remove os registros locais no Forge." }),
      ]));
      body.appendChild(el("label", { text: "Digite \"" + expected + "\" para confirmar", for: "delete-issue-confirm" }));
      const input = el("input", {
        id: "delete-issue-confirm", type: "text", value: form.confirm, autocomplete: "off",
        onInput: function (ev) { form.confirm = ev.target.value; paint(body); },
      });
      body.appendChild(input);
      if (form.error === "issue_delete_forbidden") {
        body.appendChild(el("p", { class: "warn", text: errorMessage("issue_delete_forbidden") }));
      } else if (form.error) {
        body.appendChild(el("p", { class: "error", text: errorMessage(form.error) }));
      }
      const matches = form.confirm.trim() === expected;
      const row = el("div", { class: "row" });
      row.appendChild(el("button", {
        type: "button",
        class: "danger",
        text: form.busy ? "Aguarde…" : "Apagar issue",
        disabled: (!matches || form.busy) ? "disabled" : null,
        onClick: function () { submit(body, "delete"); },
      }));
      if (form.error === "issue_delete_forbidden") {
        row.appendChild(el("button", {
          type: "button",
          text: form.busy ? "Aguarde…" : "Fechar como não planejada",
          disabled: form.busy ? "disabled" : null,
          onClick: function () { submit(body, "close"); },
        }));
      }
      row.appendChild(el("button", { type: "button", text: "Cancelar", onClick: function () { modal.close(); } }));
      body.appendChild(row);
      input.focus();
      input.setSelectionRange(input.value.length, input.value.length);
    }
    async function submit(body, mode) {
      if (form.confirm.trim() !== expected) {
        return;
      }
      form.busy = true;
      form.error = "";
      paint(body);
      const payload = { confirm: form.confirm.trim() };
      if (mode === "close") {
        payload.fallback = "close";
      }
      const res = await api(
        "/api/issues/" + encodeURIComponent(owner) + "/" + encodeURIComponent(repoName) + "/" + number + "/delete",
        { method: "POST", body: payload },
      );
      form.busy = false;
      if (!res.ok) {
        form.error = (res.data && res.data.error) || "error";
        paint(body);
        return;
      }
      modal.close();
      if (typeof onDeleted === "function") {
        onDeleted();
      }
    }
    modal = openModal({ title: "Apagar issue", build: paint });
  }

  function deleteIssueButton(owner, repoName, number, onDeleted) {
    if (!owner || !repoName || !number || !isOwner()) {
      return null;
    }
    return el("button", {
      type: "button",
      class: "danger",
      text: "Apagar issue",
      onClick: function () { openDeleteIssueModal(owner, repoName, number, onDeleted); },
    });
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
        aggregated: !!graph.data.aggregated,
        shown: graph.data.shown || (graph.data.nodes || []).length,
        total: graph.data.total || (graph.data.nodes || []).length,
        raw_total: graph.data.raw_total || 0,
        vault: !!graph.data.vault,
      };
      state.teiaExpanded = {};
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
    state.teiaExpanded = {};
    teiaKey = "";
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

  function teiaTypeLabel(type) {
    const map = {
      issue: "Issue", pr: "PR", note: "Nota", vault: "Vault",
      file: "Arquivo", module: "Módulo", class: "Classe", function: "Função",
    };
    return map[type] || type || "";
  }

  function teiaStatus() {
    if (state.graphBusy) {
      return { cls: "pill-warn", text: "INDEXANDO" };
    }
    const hasData = (state.teia.nodes || []).length > 0 || (state.graphs || []).length > 0;
    if (hasData) {
      return { cls: "pill-ok", text: "ATIVO" };
    }
    return { cls: "pill-muted", text: "DESLIGADO" };
  }

  function teiaLegendRepos() {
    const seen = {};
    const out = [];
    (state.teia.nodes || []).forEach(function (n) {
      const repo = n.repo || "";
      if (repo && !seen[repo]) {
        seen[repo] = true;
        out.push(repo);
      }
    });
    if (!out.length) {
      (state.graphs || []).forEach(function (g) {
        if (g.repo && !seen[g.repo]) {
          seen[g.repo] = true;
          out.push(g.repo);
        }
      });
    }
    out.sort();
    return out;
  }

  function teiaCountText() {
    const n = (state.teia.nodes || []).length;
    const raw = state.teia.raw_total || 0;
    const total = state.teia.total || n;
    const m = raw > n ? raw : total;
    if (state.teia.truncated || state.teia.aggregated || m > n) {
      return "Mostrando " + n + " de " + m;
    }
    return n + " nós";
  }

  function teiaNodeById(id) {
    if (!id) {
      return null;
    }
    const nodes = state.teia.nodes || [];
    for (let i = 0; i < nodes.length; i += 1) {
      if (nodes[i].id === id) {
        return nodes[i];
      }
    }
    return null;
  }

  function teiaNeighbors(id) {
    const out = [];
    const seen = {};
    (state.teia.edges || []).forEach(function (edge) {
      let other = null;
      if (edge.source === id) {
        other = edge.target;
      } else if (edge.target === id) {
        other = edge.source;
      }
      if (other && !seen[other]) {
        seen[other] = true;
        const node = teiaNodeById(other);
        if (node) {
          out.push(node);
        }
      }
    });
    out.sort(function (a, b) {
      return String(a.label || a.id).localeCompare(String(b.label || b.id));
    });
    return out;
  }

  function selectTeiaNode(id) {
    state.teiaSelected = id || null;
    if (teiaCtl) {
      teiaCtl.setSelected(id || null);
    }
    fillTeiaDetail();
    const node = teiaNodeById(id);
    if (node && node.type === "file" && node.expandable && node.repo && node.path && !state.teiaExpanded[node.id]) {
      expandTeiaFile(node);
    }
  }

  async function expandTeiaFile(node) {
    const params = new URLSearchParams();
    params.set("repo", node.repo);
    params.set("file", node.path);
    const res = await api("/api/context-graph/expand?" + params.toString());
    if (!res.ok) {
      return;
    }
    state.teiaExpanded[node.id] = true;
    const kids = res.data.nodes || [];
    const extra = res.data.edges || [];
    const seen = {};
    (state.teia.nodes || []).forEach(function (item) { seen[item.id] = true; });
    kids.forEach(function (item) {
      if (!seen[item.id]) {
        state.teia.nodes.push(item);
        seen[item.id] = true;
      }
    });
    extra.forEach(function (edge) {
      state.teia.edges.push(edge);
    });
    if (teiaCtl && teiaCtl.addAround) {
      teiaCtl.addAround(node.id, kids, extra);
    }
    fillTeiaDetail();
  }

  function teiaLinkLabel(node) {
    if (!node) {
      return "Abrir";
    }
    if (node.type === "pr") {
      return "Abrir PR";
    }
    if (node.type === "file" || node.type === "class" || node.type === "module") {
      return "Abrir no GitHub";
    }
    if (node.type === "issue") {
      return "Abrir issue";
    }
    return "Abrir";
  }

  function fillTeiaDetail(panel) {
    const host = panel || document.getElementById("teia-detail");
    if (!host) {
      return;
    }
    host.replaceChildren();
    host.appendChild(el("h2", { text: "Detalhe" }));
    const selected = teiaNodeById(state.teiaSelected);
    if (!selected) {
      host.appendChild(el("p", { class: "muted", text: "Clique num nó para ver o detalhe." }));
      return;
    }
    host.appendChild(el("p", { class: "pill pill-core", text: teiaTypeLabel(selected.type) }));
    host.appendChild(el("h3", { text: selected.label || selected.id }));
    if (selected.repo) {
      host.appendChild(el("p", { text: selected.repo }));
    }
    if (selected.path) {
      host.appendChild(el("p", { class: "muted", text: selected.path }));
    }
    if (selected.url) {
      host.appendChild(safeLink(selected.url, teiaLinkLabel(selected)));
    }
    if (selected.type === "file" && selected.expandable) {
      const n = selected.children || 0;
      host.appendChild(el("p", {
        class: "muted",
        text: state.teiaExpanded[selected.id]
          ? ("Símbolos no ficheiro: " + n)
          : ("Clique para expandir " + n + " símbolos neste ficheiro."),
      }));
    }
    const labels = selected.labels || [];
    if (selected.type === "issue" && labels.length) {
      host.appendChild(el("p", { class: "teia-k", text: "Labels" }));
      const row = el("div", { class: "teia-chips" });
      labels.forEach(function (name) {
        row.appendChild(el("span", { class: "pill pill-tasks", text: String(name) }));
      });
      host.appendChild(row);
    }
    const prs = selected.prs || [];
    if (selected.type === "issue" && prs.length) {
      host.appendChild(el("p", { class: "teia-k", text: "PRs" }));
      const list = el("div", { class: "teia-nlist" });
      prs.forEach(function (pr) {
        const prId = selected.repo ? ("pr:" + selected.repo + "#" + pr.number) : "";
        const label = "PR #" + pr.number;
        if (prId && teiaNodeById(prId)) {
          list.appendChild(el("button", {
            type: "button",
            class: "teia-neighbor",
            text: label,
            onClick: function () { selectTeiaNode(prId); },
          }));
        } else if (pr.url) {
          list.appendChild(safeLink(pr.url, label));
        } else {
          list.appendChild(el("span", { text: label }));
        }
      });
      host.appendChild(list);
    }
    const neighbors = teiaNeighbors(selected.id);
    host.appendChild(el("p", { class: "teia-k", text: "Vizinhos" }));
    if (!neighbors.length) {
      host.appendChild(el("p", { class: "muted", text: "Sem vizinhos neste recorte." }));
      return;
    }
    const nlist = el("div", { class: "teia-nlist" });
    neighbors.forEach(function (node) {
      nlist.appendChild(el("button", {
        type: "button",
        class: "teia-neighbor",
        text: teiaTypeLabel(node.type) + " · " + (node.label || node.id),
        onClick: function () { selectTeiaNode(node.id); },
      }));
    });
    host.appendChild(nlist);
  }

  function teiaDataKey() {
    const nodes = state.teia.nodes || [];
    const types = (!state.teiaTypes.length || state.teiaTypes.length >= TEIA_TYPES.length)
      ? "*"
      : state.teiaTypes.slice().sort().join(",");
    return [
      state.teiaRepo || "*",
      types,
      state.teiaQuery || "",
      String(nodes.length),
      nodes.length ? nodes[0].id : "",
      nodes.length ? nodes[nodes.length - 1].id : "",
      String((state.teia.edges || []).length),
    ].join("|");
  }

  function mountTeiaWeb(host) {
    if (!(state.teia.nodes || []).length) {
      if (teiaCtl) {
        teiaCtl.setData([], [], {});
        teiaKey = "";
      }
      host.appendChild(el("p", { class: "muted teia-empty", text: "Nenhum nó neste recorte. Importe issues ou aguarde o índice Graphify." }));
      return;
    }
    if (!teiaCanvas) {
      teiaCanvas = el("canvas", { class: "teia-canvas", id: "teia-web" });
    }
    host.appendChild(teiaCanvas);
    if (!teiaCtl && window.ForgeTeia) {
      teiaCtl = window.ForgeTeia.create(teiaCanvas, {
        onSelect: function (id) { selectTeiaNode(id); },
      });
    }
    const key = teiaDataKey();
    if (teiaCtl && teiaKey !== key) {
      teiaKey = key;
      teiaCtl.setData(state.teia.nodes, state.teia.edges, {
        clusterByRepo: !state.teiaRepo,
      });
    }
    if (teiaCtl) {
      teiaCtl.setSelected(state.teiaSelected);
      window.requestAnimationFrame(function () {
        if (teiaCtl) {
          teiaCtl.resize();
        }
      });
    }
  }

  function renderInvestForm(root) {
    const card = el("section", { class: "card card-eng" }, [
      el("div", { class: "card-head" }, [
        el("span", { class: "icon-box icon-eng", text: "B" }),
        el("h2", { text: "Nova investigação" }),
        el("span", { class: "pill pill-eng", text: "LIVRE" }),
      ]),
      el("p", { class: "muted", text: "Descreva o problema, erro ou sintoma. Escolha repositórios e, se quiser, conexões e uma issue existente." }),
    ]);
    card.appendChild(el("label", { text: "Descrição", for: "invest-description" }));
    const desc = el("textarea", { id: "invest-description", class: "preview" });
    desc.value = state.invest.form.description || "";
    card.appendChild(desc);

    card.appendChild(el("p", { class: "teia-k", text: "Repositórios" }));
    if (!state.invest.repos.length) {
      card.appendChild(el("p", { class: "muted", text: "Nenhum repositório elegível." }));
    } else {
      const reposBox = el("div", { class: "teia-types" });
      state.invest.repos.forEach(function (repo) {
        const id = "invest-repo-" + repo.replace(/[^a-z0-9]/gi, "-");
        const box = el("input", { id: id, type: "checkbox", onChange: function (ev) { toggleInvestRepo(repo, ev.target.checked); } });
        if (state.invest.form.repos.indexOf(repo) !== -1) {
          box.checked = true;
        }
        reposBox.appendChild(el("label", { class: "teia-type", for: id }, [box, el("span", { text: repo })]));
      });
      card.appendChild(reposBox);
    }

    if (state.invest.connections.length) {
      card.appendChild(el("p", { class: "teia-k", text: "Conexões (metadados; sem segredo)" }));
      const connBox = el("div", { class: "teia-types" });
      state.invest.connections.forEach(function (conn) {
        const id = "invest-conn-" + conn.id;
        const box = el("input", { id: id, type: "checkbox", onChange: function (ev) { toggleInvestConnection(conn.id, ev.target.checked); } });
        if (state.invest.form.connectionIds.indexOf(conn.id) !== -1) {
          box.checked = true;
        }
        connBox.appendChild(el("label", { class: "teia-type", for: id }, [box, el("span", { text: conn.name + " (" + conn.type + ")" })]));
      });
      card.appendChild(connBox);
    }

    card.appendChild(el("label", { text: "Issue existente (opcional)", for: "invest-issue-key" }));
    const issueSel = el("select", { id: "invest-issue-key" });
    issueSel.appendChild(el("option", { value: "", text: "Nenhuma" }));
    state.issues.forEach(function (item) {
      const label = item.issue_key + (item.title ? " — " + item.title : "");
      const opt = el("option", { value: item.issue_key, text: label });
      if (state.invest.form.issueKey === item.issue_key) {
        opt.selected = true;
      }
      issueSel.appendChild(opt);
    });
    card.appendChild(issueSel);

    if (state.invest.error) {
      card.appendChild(el("p", { class: "error", text: errorMessage(state.invest.error) }));
    }
    card.appendChild(el("button", {
      type: "button",
      class: "primary",
      text: state.invest.busy ? "Investigando…" : "Rodar investigação",
      disabled: state.invest.busy ? "disabled" : null,
      onClick: function () { runInvestigation(); },
    }));
    root.appendChild(card);
  }

  function renderInvestResult(root) {
    const view = state.invest.current;
    if (!view) {
      return;
    }
    const card = el("section", { class: "card card-eng" }, [
      el("div", { class: "card-head" }, [
        el("h2", { text: view.title || "Resultado" }),
        el("span", { class: "pill pill-eng", text: view.engine || "motor" }),
      ]),
      el("p", { class: "muted", text: (view.repos || []).join(", ") || "Sem repositório associado." }),
    ]);
    const result = el("div", { class: "markdown-body" }, renderMarkdownNodes(view.result));
    card.appendChild(result);
    if (state.invest.notice) {
      card.appendChild(el("p", { class: "ok", text: state.invest.notice }));
    }
    card.appendChild(el("button", {
      type: "button",
      class: "primary",
      text: state.invest.busy ? "Aguarde…" : "Gerar tarefa a partir desta investigação",
      disabled: state.invest.busy ? "disabled" : null,
      onClick: function () { investigationToTask(view.id, (view.repos || [])[0] || ""); },
    }));
    root.appendChild(card);
  }

  function renderInvestHistory(root) {
    const card = el("section", { class: "card card-eng" }, [
      el("div", { class: "card-head" }, [
        el("h2", { text: "Histórico de investigações" }),
        el("span", { class: "pill pill-eng", text: String(state.invest.list.length) }),
      ]),
    ]);
    if (!state.invest.list.length) {
      card.appendChild(el("p", { class: "muted", text: "Nenhuma investigação ainda." }));
      root.appendChild(card);
      return;
    }
    const list = el("div", { class: "note-list" });
    state.invest.list.forEach(function (item) {
      list.appendChild(el("button", {
        type: "button",
        class: "note-item" + (state.invest.current && state.invest.current.id === item.id ? " active" : ""),
        text: (item.title || "(sem título)") + " · " + (item.repos || []).join(", "),
        onClick: function () { openInvestigation(item.id); },
      }));
    });
    card.appendChild(list);
    root.appendChild(card);
  }

  function renderInvestigacao(root) {
    root.appendChild(pageHeader("02 — INVESTIGAÇÃO", "Investigação", "Descreva um problema, erro ou sintoma; o agente investiga em modo somente leitura e sugere próximos passos."));
    root.appendChild(el("section", { class: "card card-eng" }, [
      el("div", { class: "card-head" }, [
        el("span", { class: "icon-box icon-eng", text: "B" }),
        el("h2", { text: "Investigação" }),
        el("span", { class: "pill pill-eng", text: "NOTAS" }),
      ]),
      el("p", { text: "Notas manuais por issue, no banco do Forge. Independente do vault Obsidian." }),
      el("p", { class: "muted", text: "Markdown aparece como texto. O corpo da nota não vai para o log." }),
    ]));
    root.appendChild(readonlySeal());
    if (!canEditNotes()) {
      root.appendChild(el("section", { class: "card" }, [
        el("p", { class: "error", text: "Só editor ou owner vê as notas da investigação." }),
      ]));
      return;
    }
    renderInvestForm(root);
    renderInvestResult(root);
    renderInvestHistory(root);
    root.appendChild(el("h2", { class: "section-divider", text: "Notas por issue" }));
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
    if (state.issues.length) {
      const issueList = el("div", { class: "note-list" });
      state.issues.forEach(function (item) {
        const parts = splitOwnerRepo(item.repo);
        const row = el("div", { class: "related-item" }, [
          el("span", null, [
            el("strong", { text: item.issue_key }),
            el("span", { text: item.title ? " — " + item.title : "" }),
          ]),
        ]);
        const del = deleteIssueButton(parts.owner, parts.repo, item.number, async function () {
          state.notice = "Issue " + item.issue_key + " apagada.";
          await loadInvestigacao();
          render();
        });
        if (del) {
          row.appendChild(del);
        }
        issueList.appendChild(row);
      });
      issueBox.appendChild(issueList);
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
    const status = teiaStatus();
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
      placeholder: "Buscar",
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
    const filters = el("div", { class: "teia-filters card" }, [
      el("div", { class: "teia-filter-head" }, [
        el("span", { class: "icon-box icon-core", text: "F" }),
        el("strong", { text: "Teia de contexto" }),
        el("span", { class: "pill " + status.cls, text: status.text }),
        vaultEnabled ? el("span", { class: "pill pill-muted", text: "VAULT" }) : null,
        el("span", { class: "muted teia-count", text: teiaCountText() }),
      ]),
      el("div", { class: "graph-query teia-filter-row" }, [
        el("div", null, [el("label", { text: "Repositório", for: "teia-repo" }), repoSelect]),
        el("div", null, [el("label", { text: "Busca", for: "teia-query" }), q]),
        el("button", {
          type: "button",
          text: "Aplicar",
          onClick: function () { applyTeiaFilters(); },
        }),
      ]),
      types,
    ]);
    if (state.teia.truncated || state.teia.aggregated) {
      filters.appendChild(el("p", {
        class: "banner banner-warn teia-trunc",
        text: teiaCountText() + (state.teia.aggregated
          ? ". Agregado por ficheiro; clique num ficheiro para ver classes e funções."
          : ". Recorte pelos nós mais ligados a issues e notas."),
      }));
    }

    const panel = el("aside", { class: "teia-panel card", id: "teia-detail" });
    fillTeiaDetail(panel);

    const graphCard = el("section", { class: "card card-eng teia-graphs" }, [
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
        el("th", { text: "Nós" }),
        el("th", { text: "Arestas" }),
      ])]));
      const tbody = el("tbody");
      state.graphs.forEach(function (g) {
        const ref = g.tag || (g.source === "head" ? ("HEAD " + (g.ref || "")) : (g.ref || g.error || "—"));
        tbody.appendChild(el("tr", null, [
          el("td", { text: g.repo || "" }),
          el("td", { text: ref }),
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

    const legend = el("ul", { class: "teia-legend" });
    const legendRepos = teiaLegendRepos();
    if (!legendRepos.length) {
      legend.appendChild(el("li", null, [
        el("span", { class: "teia-swatch teia-swatch-neutral", "aria-hidden": "true" }),
        el("span", { text: "Sem repositório" }),
      ]));
    }
    legendRepos.forEach(function (repo) {
      const cls = window.ForgeTeia ? window.ForgeTeia.repoSwatchClass(repo) : "teia-swatch-neutral";
      legend.appendChild(el("li", null, [
        el("span", { class: "teia-swatch " + cls, "aria-hidden": "true" }),
        el("span", { text: repo }),
      ]));
    });

    const web = el("div", { class: "teia-web" });
    web.appendChild(legend);
    mountTeiaWeb(web);

    const left = el("div", { class: "teia-left" }, [panel, graphCard]);
    const right = el("div", { class: "teia-right" }, [filters, web]);
    root.appendChild(el("div", { class: "teia-page" }, [left, right]));
  }

  async function loadAgentDetail(id) {
    const res = await api("/api/agents/" + encodeURIComponent(id));
    if (!res.ok) {
      return;
    }
    state.agentes.selectedId = id;
    state.agentes.selected = res.data.agent;
    state.agentes.executions = res.data.executions || [];
  }

  async function loadAgentes() {
    if (!canEditNotes()) {
      return;
    }
    const res = await api("/api/agents");
    if (res.ok) {
      state.agentes.items = res.data.agents || [];
      state.agentes.metrics = res.data.metrics || null;
    }
    const approvals = await api("/api/agents/approvals");
    if (approvals.ok) {
      state.agentes.approvals = approvals.data.approvals || [];
    }
    const stillThere = state.agentes.items.some(function (a) { return a.id === state.agentes.selectedId; });
    if (state.agentes.selectedId && stillThere) {
      await loadAgentDetail(state.agentes.selectedId);
    } else if (state.agentes.items.length) {
      await loadAgentDetail(state.agentes.items[0].id);
    } else {
      state.agentes.selectedId = "";
      state.agentes.selected = null;
      state.agentes.executions = [];
    }
  }

  async function selectAgent(id) {
    await loadAgentDetail(id);
    render();
  }

  async function decideApproval(approvalId, decision) {
    state.agentes.busy = true;
    state.agentes.error = "";
    render();
    const res = await api("/api/agents/approvals/" + encodeURIComponent(approvalId) + "/" + decision, {
      method: "POST", body: {},
    });
    state.agentes.busy = false;
    if (!res.ok) {
      state.agentes.error = (res.data && res.data.error) || "error";
      render();
      return;
    }
    state.agentes.notice = decision === "approve" ? "Aprovação concedida." : "Aprovação recusada.";
    await loadAgentes();
    render();
  }

  function openNewAgentModal() {
    const form = {
      name: "", description: "", scope: "development", trigger: "", engine: "",
      permissions_read: "", permissions_write: "", busy: false, error: "",
    };
    let modal = null;
    function paint(body) {
      body.replaceChildren();
      body.appendChild(el("label", { text: "Nome", for: "agent-name" }));
      const nameInput = el("input", { id: "agent-name", type: "text", value: form.name });
      body.appendChild(nameInput);
      body.appendChild(el("label", { text: "Descrição", for: "agent-description" }));
      const descInput = el("textarea", { id: "agent-description" });
      descInput.value = form.description;
      body.appendChild(descInput);
      body.appendChild(el("label", { text: "Escopo", for: "agent-scope" }));
      const scopeSel = el("select", { id: "agent-scope" });
      [["development", "Desenvolvimento"], ["company_system", "Sistema da empresa"]].forEach(function (pair) {
        const opt = el("option", { value: pair[0], text: pair[1] });
        if (pair[0] === form.scope) {
          opt.selected = true;
        }
        scopeSel.appendChild(opt);
      });
      body.appendChild(scopeSel);
      body.appendChild(el("label", { text: "Gatilho", for: "agent-trigger" }));
      const triggerInput = el("input", { id: "agent-trigger", type: "text", value: form.trigger, placeholder: "ex.: issue nova no GitHub" });
      body.appendChild(triggerInput);
      body.appendChild(el("label", { text: "Motor", for: "agent-engine" }));
      const engineInput = el("input", { id: "agent-engine", type: "text", value: form.engine, placeholder: "ex.: claude-code" });
      body.appendChild(engineInput);
      body.appendChild(el("label", { text: "Pode ler (separado por vírgula)", for: "agent-read" }));
      const readInput = el("input", { id: "agent-read", type: "text", value: form.permissions_read, placeholder: "issues, prs, notas do obsidian" });
      body.appendChild(readInput);
      body.appendChild(el("label", { text: "Pode alterar (separado por vírgula)", for: "agent-write" }));
      const writeInput = el("input", { id: "agent-write", type: "text", value: form.permissions_write, placeholder: "etiquetas, rascunhos de issue" });
      body.appendChild(writeInput);
      body.appendChild(el("p", { class: "muted", text: "Banco de dados, FTP/SFTP e Portainer nunca recebem escrita, mesmo com aprovação." }));
      if (form.error) {
        body.appendChild(el("p", { class: "error", text: errorMessage(form.error) }));
      }
      body.appendChild(el("div", { class: "row" }, [
        el("button", {
          type: "button", class: "primary",
          text: form.busy ? "Criando…" : "Criar agente",
          disabled: form.busy ? "disabled" : null,
          onClick: function () { submit(body); },
        }),
        el("button", { type: "button", text: "Cancelar", onClick: function () { modal.close(); } }),
      ]));
    }
    async function submit(body) {
      form.name = document.getElementById("agent-name").value;
      form.description = document.getElementById("agent-description").value;
      form.scope = document.getElementById("agent-scope").value;
      form.trigger = document.getElementById("agent-trigger").value;
      form.engine = document.getElementById("agent-engine").value;
      form.permissions_read = document.getElementById("agent-read").value;
      form.permissions_write = document.getElementById("agent-write").value;
      form.busy = true;
      form.error = "";
      paint(body);
      const payload = {
        name: form.name,
        description: form.description,
        scope: form.scope,
        trigger: form.trigger,
        engine: form.engine,
        permissions_read: splitCsv(form.permissions_read),
        permissions_write: splitCsv(form.permissions_write),
      };
      const res = await api("/api/agents", { method: "POST", body: payload });
      form.busy = false;
      if (!res.ok) {
        form.error = (res.data && res.data.error) || "error";
        paint(body);
        return;
      }
      modal.close();
      state.agentes.notice = "Agente criado.";
      await loadAgentes();
      render();
    }
    modal = openModal({ title: "Novo agente", build: paint });
  }

  function scopeChip(scope) {
    if (scope === "company_system") {
      return el("span", { class: "chip chip-danger-outline", text: "Sistema da empresa" });
    }
    return el("span", { class: "chip", text: "Desenvolvimento" });
  }

  function agentStatusPill(status) {
    const map = {
      active: { cls: "pill-ok", text: "Ativo" },
      paused: { cls: "pill-muted", text: "Pausado" },
      error: { cls: "pill-danger", text: "Com erro" },
    };
    const info = map[status] || { cls: "pill-muted", text: status || "—" };
    return el("span", { class: "pill " + info.cls, text: info.text });
  }

  function successMeter(rate) {
    if (rate === null || rate === undefined) {
      return el("span", { class: "muted", text: "—" });
    }
    return el("div", { class: "success-cell" }, [
      el("span", { class: "success-value", text: rate + "%" }),
      el("meter", {
        class: "success-meter", min: "0", max: "100", low: "70", high: "90", optimum: "100",
        value: String(rate),
      }),
    ]);
  }

  function metricCard(kind, value, total, label) {
    const valueChildren = [el("span", { text: String(value) })];
    if (total !== null && total !== undefined) {
      valueChildren.push(el("span", { class: "metric-total", text: "/ " + total }));
    }
    return el("div", { class: "metric-card metric-" + kind }, [
      el("div", { class: "metric-value" }, valueChildren),
      el("p", { class: "metric-label", text: label }),
    ]);
  }

  function renderAgentMetrics(root) {
    const m = state.agentes.metrics || { active: 0, total: 0, executions_today: 0, errors_24h: 0, pending_approvals: 0 };
    root.appendChild(el("div", { class: "metric-grid" }, [
      metricCard("ok", m.active, m.total, "Agentes ativos"),
      metricCard("core", m.executions_today, null, "Execuções hoje"),
      metricCard("danger", m.errors_24h, null, "Erros nas últimas 24 h"),
      metricCard("warn", m.pending_approvals, null, "Aprovações pendentes"),
    ]));
  }

  function renderAgentsTable(root) {
    const card = el("section", { class: "card card-auto" }, [
      el("div", { class: "card-head" }, [
        el("h2", { text: "Agentes" }),
        el("span", { class: "pill pill-auto", text: String(state.agentes.items.length) }),
        el("button", {
          type: "button", class: "primary", text: "+ Novo agente",
          onClick: function () { openNewAgentModal(); },
        }),
      ]),
    ]);
    if (!state.agentes.items.length) {
      card.appendChild(el("p", { class: "muted", text: "Nenhum agente cadastrado ainda. Use \"+ Novo agente\" para criar o primeiro." }));
      root.appendChild(card);
      return;
    }
    const table = el("table");
    table.appendChild(el("thead", null, [el("tr", null, [
      el("th", { text: "Agente" }),
      el("th", { text: "Escopo" }),
      el("th", { text: "Status" }),
      el("th", { text: "Última execução" }),
      el("th", { text: "Sucesso" }),
    ])]));
    const tbody = el("tbody");
    state.agentes.items.forEach(function (agent) {
      const selected = agent.id === state.agentes.selectedId;
      tbody.appendChild(el("tr", {
        class: "agent-row" + (selected ? " selected" : ""),
        onClick: function () { selectAgent(agent.id); },
      }, [
        el("td", null, [el("div", { class: "agent-name-cell" }, [
          el("strong", { text: agent.name }),
          el("span", { text: agent.description || "" }),
        ])]),
        el("td", null, [scopeChip(agent.scope)]),
        el("td", null, [agentStatusPill(agent.status)]),
        el("td", { text: relativeTime(agent.last_execution_at) }),
        el("td", null, [successMeter(agent.success_rate)]),
      ]));
    });
    table.appendChild(tbody);
    card.appendChild(table);
    card.appendChild(el("p", { class: "muted", text: "Agentes do sistema da empresa rodam isolados e só alteram dados com aprovação humana." }));
    root.appendChild(card);
  }

  function renderSelectedAgent(root) {
    const card = el("section", { class: "card card-auto" }, [
      el("div", { class: "card-head" }, [
        el("h2", { text: "Agente selecionado" }),
      ]),
    ]);
    const agent = state.agentes.selected;
    if (!agent) {
      card.appendChild(el("p", { class: "muted", text: "Selecione um agente na lista." }));
      root.appendChild(card);
      return;
    }
    card.appendChild(el("div", { class: "selected-agent-head" }, [
      el("strong", { text: agent.name }),
      agentStatusPill(agent.status),
    ]));
    card.appendChild(el("p", { class: "agent-trigger-line" }, [
      el("span", { text: (agent.scope === "company_system" ? "Sistema da empresa" : "Desenvolvimento") + (agent.trigger ? " · gatilho: " + agent.trigger : "") }),
    ]));
    card.appendChild(el("p", { class: "teia-k", text: "Execuções recentes" }));
    const execList = el("div", { class: "exec-list" });
    if (!state.agentes.executions.length) {
      execList.appendChild(el("p", { class: "muted", text: "Sem execuções registradas." }));
    }
    state.agentes.executions.slice(0, 6).forEach(function (execu) {
      execList.appendChild(el("div", { class: "exec-item" }, [
        el("span", { class: "exec-dot exec-dot-" + (execu.status || "running") }),
        el("span", { text: execu.event || execu.status }),
        el("span", { class: "exec-time", text: relativeTime(execu.started_at) }),
      ]));
    });
    card.appendChild(execList);
    const lastLog = state.agentes.executions.length ? state.agentes.executions[0].log : "";
    if (lastLog) {
      card.appendChild(el("div", { class: "agent-log", text: lastLog }));
    }
    root.appendChild(card);
  }

  function renderApprovals(root) {
    const pending = state.agentes.approvals.filter(function (a) { return a.status === "pending"; });
    const card = el("section", { class: "card card-auto" }, [
      el("div", { class: "card-head" }, [
        el("h2", { text: "Aprovações pendentes" }),
        el("span", { class: "pill pill-auto", text: String(pending.length) }),
      ]),
    ]);
    if (state.agentes.error) {
      card.appendChild(el("p", { class: "error", text: errorMessage(state.agentes.error) }));
    }
    if (!pending.length) {
      card.appendChild(el("p", { class: "muted", text: "Nenhuma aprovação pendente." }));
      root.appendChild(card);
      return;
    }
    pending.forEach(function (item) {
      card.appendChild(el("div", { class: "approval-item" }, [
        el("div", { class: "approval-info" }, [
          el("strong", { text: item.action === "write_access" ? "Acesso de escrita · " + item.agent_name : item.agent_name }),
          el("span", { text: item.agent_name + " · " + relativeTime(item.requested_at) }),
        ]),
        el("div", { class: "approval-actions" }, [
          el("button", {
            type: "button", class: "primary", text: "Aprovar",
            disabled: state.agentes.busy ? "disabled" : null,
            onClick: function () { decideApproval(item.id, "approve"); },
          }),
          el("button", {
            type: "button", text: "Recusar",
            disabled: state.agentes.busy ? "disabled" : null,
            onClick: function () { decideApproval(item.id, "reject"); },
          }),
        ]),
      ]));
    });
    root.appendChild(card);
  }

  function renderPermissions(root) {
    const agent = state.agentes.selected;
    const card = el("section", { class: "card card-auto" }, [
      el("div", { class: "card-head" }, [
        el("h2", { text: "Permissões" }),
        agent ? el("span", { class: "muted", text: agent.name }) : null,
      ]),
    ]);
    if (!agent) {
      card.appendChild(el("p", { class: "muted", text: "Selecione um agente para ver as permissões." }));
      root.appendChild(card);
      return;
    }
    const perms = agent.permissions || { read: [], write: [], denied: [] };
    const rows = [
      ["read", "Pode ler", perms.read],
      ["write", "Pode alterar", perms.write],
      ["denied", "Sem acesso", perms.denied],
    ];
    rows.forEach(function (row) {
      card.appendChild(el("div", { class: "permission-row" }, [
        el("span", { class: "permission-dot permission-dot-" + row[0] }),
        el("div", null, [
          el("strong", { text: row[1] }),
          el("span", { text: (row[2] && row[2].length) ? row[2].join(", ") : "—" }),
        ]),
      ]));
    });
    root.appendChild(card);
  }

  function renderAgentes(root) {
    root.appendChild(pageHeader("05 — AGENTES", "Agentes", "Agentes que trabalham no desenvolvimento e no sistema da empresa."));
    if (!canEditNotes()) {
      root.appendChild(el("section", { class: "card" }, [
        el("p", { class: "error", text: "Só editor ou owner vê a aba Agentes." }),
      ]));
      return;
    }
    renderAgentMetrics(root);
    const left = el("div", null, []);
    renderAgentsTable(left);
    const right = el("div", { class: "agents-right" }, []);
    renderSelectedAgent(right);
    renderApprovals(right);
    renderPermissions(right);
    root.appendChild(el("div", { class: "agents-layout" }, [left, right]));
  }

  function render() {
    snapshotForm();
    const session = document.getElementById("session");
    const app = document.getElementById("app");
    renderSession(session);
    renderNav();
    app.replaceChildren();
    const teiaOpen = !state.loading && !!state.who && activeTab() === "teia";
    app.classList.toggle("teia-layout", teiaOpen);
    document.body.classList.toggle("teia-open", teiaOpen);
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
    if (tab === "agentes") {
      setPageTitle("Agentes");
      renderAgentes(app);
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
      state.loading = false;
      render();
      const tab = activeTab();
      if (isEditor()) {
        await loadEditorData();
        render();
      }
      if (canEditNotes() && tab === "investigacao") {
        await loadInvestigacao();
        render();
      }
      if (canEditNotes() && tab === "teia") {
        await loadTeia();
        render();
      }
      if (canEditNotes() && tab === "agentes") {
        await loadAgentes();
        render();
      }
    } catch (err) {
      state.error = "api_unreachable";
      state.loading = false;
      render();
    }
  }

  window.addEventListener("hashchange", async function () {
    const tab = activeTab();
    render();
    if (tab === "investigacao" && canEditNotes()) {
      await loadInvestigacao();
    }
    if (tab === "teia" && canEditNotes()) {
      await loadTeia();
    }
    if (tab === "agentes" && canEditNotes()) {
      await loadAgentes();
    }
    render();
  });
  boot();
})();
