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
    issueQuery: "",
    issueRepoFilter: "",
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
    teiaFull: false,
    relatedIssues: [],
    invest: {
      repos: [],
      connections: [],
      list: [],
      current: null,
      form: { mode: "manual", description: "", repos: [], connectionIds: [], issueKey: "" },
      preview: null,
      previewKey: "",
      previewBusy: false,
      previewError: "",
      busy: false,
      error: "",
      notice: "",
    },
    ai: {
      data: null,
      form: null,
      saving: false,
      error: "",
      modal: null,
    },
    radar: {
      overview: null,
      report: null,
      history: [],
      selectedId: "",
      busy: false,
      error: "",
      pollTimer: null,
      modal: null,
    },
    areas: { catalog: null, error: "", modal: null },
    agentes: {
      filter: { status: "", query: "" },
      items: [],
      metrics: null,
      approvals: [],
      selectedId: "",
      selected: null,
      executions: [],
      detail: null,
      detailModal: null,
      openExec: {},
      configForm: null,
      configSaving: false,
      configError: "",
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

  function pageHeader(title, subtitle, actions) {
    return el("header", { class: "page-header" }, [
      el("div", { class: "page-header-text" }, [
        el("h2", { class: "page-title", text: title }),
        subtitle ? el("p", { class: "page-subtitle", text: subtitle }) : null,
      ]),
      actions && actions.length ? el("div", { class: "page-actions" }, actions) : null,
    ]);
  }

  function cardHead(title, extra) {
    return el("div", { class: "card-head" }, [el("h2", { text: title })].concat(extra || []));
  }

  function countLabel(n) {
    return el("span", { class: "count", text: String(n) });
  }

  function actionsRow(children, cls) {
    return el("div", { class: "actions" + (cls ? " " + cls : "") }, children);
  }

  function emptyState(title, detail) {
    return el("div", { class: "empty" }, [
      el("strong", { text: title }),
      detail ? el("span", { text: detail }) : null,
    ]);
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

  function strokeIcon(d) {
    const ns = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(ns, "svg");
    svg.setAttribute("viewBox", "0 0 16 16");
    svg.setAttribute("width", "16");
    svg.setAttribute("height", "16");
    svg.setAttribute("aria-hidden", "true");
    const path = document.createElementNS(ns, "path");
    path.setAttribute("fill", "none");
    path.setAttribute("stroke", "currentColor");
    path.setAttribute("stroke-width", "1.5");
    path.setAttribute("stroke-linecap", "round");
    path.setAttribute("stroke-linejoin", "round");
    path.setAttribute("d", d);
    svg.appendChild(path);
    return svg;
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
    const sheet = opts.variant === "sheet";
    const overlay = el("div", { class: "modal-overlay" + (sheet ? " sheet-overlay" : "") });
    function close() {
      document.removeEventListener("keydown", onKey);
      overlay.remove();
      if (typeof opts.onClose === "function") {
        opts.onClose();
      }
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
      class: "modal-dialog" + (sheet ? " sheet" : ""), role: "dialog", "aria-modal": "true", "aria-labelledby": titleId,
    });
    const head = el("div", { class: "modal-head" }, [
      el("div", { class: "modal-head-text" }, [
        el("h2", { id: titleId, text: opts.title }),
        opts.subtitle ? el("p", { class: "modal-subtitle", text: opts.subtitle }) : null,
      ]),
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
    const focusable = sheet
      ? dialog.querySelector(".modal-close")
      : dialog.querySelector("input, textarea, select, button:not(.modal-close)");
    if (focusable) {
      focusable.focus();
    }
    return { close: close, body: body };
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

  function safeLink(url, label) {
    const href = githubHref(url || "");
    if (!href) {
      return el("span", { class: "muted", text: "—" });
    }
    return el("a", { href: href, target: "_blank", rel: "noopener noreferrer", text: label || href });
  }

  function publishedIssueLink(url) {
    const node = safeLink(url, "Issue");
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
    await loadEditorAndTab();
  }

  // Dados de Tarefas (dependem do GitHub e podem demorar) não seguram a aba aberta.
  async function loadEditorAndTab() {
    await Promise.all([
      isEditor() ? loadEditorData().then(function () { render(); }) : null,
      loadForTab(),
    ]);
  }

  async function loadForTab() {
    if (!canEditNotes()) {
      return;
    }
    const tab = activeTab();
    if (tab === "investigacao") {
      await loadInvestigacao();
    } else if (tab === "teia") {
      await loadTeia();
    } else if (tab === "agentes") {
      await Promise.all([loadAgentes(), loadAreas()]);
    } else if (tab === "soon") {
      await loadAreas();
    } else {
      return;
    }
    render();
  }

  async function loadAreas() {
    if (state.areas.catalog) {
      return;
    }
    const res = await api("/api/areas");
    if (res.ok) {
      state.areas.catalog = res.data;
      state.areas.error = "";
    } else {
      state.areas.error = (res.data && res.data.error) || "error";
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
      issue_required: "Escolha a issue que vira o pedido.",
      project_scope: "O gh do servidor não tem acesso ao board. Rode gh auth refresh -s project no container.",
      project_schema: "Não foi possível ler o board Backlog de TI.",
      busy: "Já existe uma análise em andamento.",
      anthropic_not_configured: "A chave da API da Anthropic não está configurada no servidor.",
      anthropic_auth: "A chave da API da Anthropic foi recusada. Confira a chave no .env.",
      anthropic_rate_limit: "Limite de uso da API da Anthropic atingido. Tente mais tarde.",
      invalid_time: "Horário inválido. Use HH:MM.",
      invalid_model: "Modelo inválido.",
      invalid_engine: "Motor inválido.",
      invalid_mode: "Modo de pedido inválido.",
      issue_unavailable: "Não foi possível ler a issue no GitHub agora.",
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

  // Rota "area/aba" (nav.js). activeTab() devolve o que a tela desenha:
  // tarefas, investigacao, teia, agentes (de qualquer área), soon ("em breve") ou config.
  function route() {
    if (window.ForgeNav) {
      return window.ForgeNav.parse(window.location.hash);
    }
    return { key: "dev/tarefas", area: "dev", tab: "tarefas", item: null };
  }

  function activeTab() {
    const r = route();
    if (r.area === "configuracoes") {
      return "config";
    }
    if (r.item && r.item.soon) {
      return "soon";
    }
    return r.tab;
  }

  function routeSector() {
    return window.ForgeNav ? window.ForgeNav.sectorOf(route().area) : "desenvolvimento";
  }

  function redirectLegacyHash() {
    const raw = (window.location.hash || "").replace(/^#/, "");
    if (window.ForgeNav && raw && Object.prototype.hasOwnProperty.call(window.ForgeNav.legacy, raw)) {
      window.history.replaceState(null, "", "#" + window.ForgeNav.legacy[raw]);
    }
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
    const issueQuery = document.getElementById("issue-filter-text");
    const issueRepoFilter = document.getElementById("issue-filter-repo");
    if (issueQuery) {
      state.issueQuery = issueQuery.value;
    }
    if (issueRepoFilter) {
      state.issueRepoFilter = issueRepoFilter.value;
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
    if (!window.ForgeNav) {
      return;
    }
    window.ForgeNav.render(document.getElementById("nav"), route().key, {
      loggedIn: !!state.who,
      owner: isOwner(),
      reader: canEditNotes(),
    });
  }


  function statusPill(draftStatus, status) {
    const left = draftStatus || "";
    const right = status || "";
    const label = left && right ? left + " · " + right : (left || right || "—");
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
    const text = label.charAt(0).toUpperCase() + label.slice(1);
    return el("span", { class: "status status-" + kind, text: text });
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
      box.appendChild(el("p", { text: "Abra o endereço abaixo no GitHub e informe o código para autorizar este painel." }));
      box.appendChild(el("p", null, [safeLink(state.pending.verification_uri)]));
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
    return el("div", { class: "pending-box" }, [
      el("p", { class: "warn", text: "Seções com [PENDENTE]:" }),
      el("ul", { class: "pending" }, items),
      el("p", { class: "muted", text: "Edite o corpo abaixo ou complemente o contexto e gere de novo." }),
    ]);
  }

  function renderEditor(root) {
    root.appendChild(pageHeader("Tarefas", "Gere, revise e publique tarefas a partir de um contexto escrito, para os repositórios da allowlist."));
    if (!isEditor()) {
      root.appendChild(el("p", { class: "banner banner-warn", text: "Só quem tem o papel editor pode criar tarefas. O owner não implica editor; peça grant --role editor." }));
      return;
    }

    const form = el("section", { class: "card" }, [cardHead("Nova tarefa")]);
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
    form.appendChild(el("label", { text: "Contexto", for: "context" }));
    const context = el("textarea", {
      id: "context",
      maxlength: String(MAX_CONTEXT),
      placeholder: "Descreva o problema, o comportamento esperado e o que já se sabe.",
    });
    context.value = state.form.context || "";
    form.appendChild(context);
    form.appendChild(el("p", { class: "field-hint", text: "Texto livre, até 64 KiB. Imagens não são aceitas." }));
    form.appendChild(actionsRow([el("button", {
      type: "button",
      class: "primary",
      text: state.busy ? "Aguarde…" : (state.draft ? "Gerar de novo" : "Gerar rascunho"),
      disabled: state.busy ? "disabled" : null,
      onClick: function () { generateDraft(); },
    })]));
    root.appendChild(form);

    if (state.draft) {
      const preview = el("section", { class: "card" }, [cardHead("Rascunho")]);
      const pending = pendingList(state.draft.pending);
      if (pending) {
        preview.appendChild(pending);
      }
      preview.appendChild(el("label", { text: "Corpo da issue", for: "draft-body" }));
      const body = el("textarea", { id: "draft-body", class: "preview" });
      body.value = state.draft.body || "";
      preview.appendChild(body);
      if (state.fieldsError) {
        preview.appendChild(el("p", { class: "field-hint field-error", text: state.fieldsError }));
      }
      const row = el("div", { class: "field-grid" });
      const tipo = el("select", { id: "tipo", onChange: function () { saveDraft(); } });
      const prioridade = el("select", { id: "prioridade", onChange: function () { saveDraft(); } });
      const size = el("select", { id: "size", onChange: function () { saveDraft(); } });
      fillSelect(tipo, state.fields.tipo, "Selecione", state.form.tipo);
      fillSelect(prioridade, state.fields.prioridade, "Selecione", state.form.prioridade);
      fillSelect(size, state.fields.size, "Selecione", state.form.size);
      row.appendChild(el("div", { class: "field" }, [el("label", { text: "Tipo", for: "tipo" }), tipo]));
      row.appendChild(el("div", { class: "field" }, [el("label", { text: "Prioridade", for: "prioridade" }), prioridade]));
      row.appendChild(el("div", { class: "field" }, [el("label", { text: "Size", for: "size" }), size]));
      preview.appendChild(row);
      preview.appendChild(actionsRow([
        el("button", {
          type: "button",
          class: "primary",
          text: "Confirmar e publicar",
          disabled: state.busy ? "disabled" : null,
          onClick: function () { confirmDraft(); },
        }),
        el("button", {
          type: "button",
          text: "Salvar rascunho",
          disabled: state.busy ? "disabled" : null,
          onClick: function () { saveDraft(); },
        }),
      ]));
      if (state.draft.links) {
        const links = state.draft.links;
        preview.appendChild(el("div", { class: "publish-result" }, [
          el("p", { class: "status status-ok", text: "Publicado." }),
          el("dl", { class: "meta-list" }, [
            el("dt", { text: "Issue" }), el("dd", null, [safeLink(links.issue_url)]),
            el("dt", { text: "Branch" }), el("dd", { class: "mono", text: links.branch || "—" }),
            el("dt", { text: "PR" }), el("dd", null, [safeLink(links.pr_url)]),
            el("dt", { text: "Board" }), el("dd", { class: "mono", text: links.board_item_id || "—" }),
          ]),
        ]));
      }
      root.appendChild(preview);
    }

    root.appendChild(renderTaskView("Publicadas", state.published, "published"));
    root.appendChild(renderTaskView("Rascunhos", state.drafts, "drafts"));
  }

  function renderTaskView(title, tasks, kind) {
    const list = el("section", { class: "card task-view" }, [cardHead(title, [countLabel(tasks.length)])]);
    if (!tasks.length) {
      list.appendChild(el("p", {
        class: "muted",
        text: kind === "published"
          ? "Nenhuma tarefa publicada. Ao confirmar um rascunho, ele aparece aqui com os links da issue e do PR."
          : "Nenhum rascunho salvo.",
      }));
      return list;
    }
    const cols = [
      el("th", { text: "Título" }),
      el("th", { text: "Repositório" }),
      el("th", { text: "Status" }),
    ];
    if (kind === "published") {
      cols.push(el("th", { text: "Links" }), el("th", { text: "", "aria-label": "Ações" }));
    } else {
      cols.push(el("th", { text: "", "aria-label": "Ações" }));
    }
    const table = el("table");
    table.appendChild(el("thead", null, [el("tr", null, cols)]));
    const tbody = el("tbody");
    tasks.forEach(function (task) {
      const cells = [
        el("td", { class: "cell-strong", text: task.title || "" }),
        el("td", { class: "cell-repo", text: task.repo || "" }),
        el("td", null, [statusPill(task.draft_status, task.status)]),
      ];
      if (kind === "published") {
        const pr = safeLink(task.pr_url, "PR");
        cells.push(el("td", { class: "cell-links" }, [publishedIssueLink(task.issue_url), pr.tagName === "A" ? pr : null]));
        const parts = splitOwnerRepo(task.repo);
        const number = issueNumberFromUrl(task.issue_url);
        const del = deleteIssueButton(parts.owner, parts.repo, number, async function () {
          state.notice = "Issue apagada.";
          await loadEditorData();
          render();
        });
        cells.push(el("td", { class: "cell-actions" }, [del]));
      } else {
        cells.push(el("td", { class: "cell-actions" }, [el("button", {
          type: "button",
          class: "quiet danger sm",
          text: "Descartar",
          disabled: state.busy ? "disabled" : null,
          onClick: function () { discardDraft(task.id); },
        })]));
      }
      tbody.appendChild(el("tr", null, cells));
    });
    table.appendChild(tbody);
    list.appendChild(el("div", { class: "table-wrap" }, [table]));
    return list;
  }

  function sourceRow(name, detail) {
    return el("li", { class: "source-row" }, [
      el("span", null, [
        el("span", { class: "source-name", text: name }),
        el("span", { class: "muted", text: " · " + detail }),
      ]),
      el("span", { class: "status status-muted", text: "Planejada" }),
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
    return el("p", { class: "seal-readonly" }, [
      lockIcon(),
      el("strong", { text: "Somente leitura." }),
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

  function setInvestMode(mode) {
    snapshotInvestForm();
    state.invest.form.mode = mode === "issue" ? "issue" : "manual";
    state.invest.error = "";
    render();
    if (state.invest.form.mode === "issue" && state.invest.form.issueKey) {
      loadIssuePreview(state.invest.form.issueKey);
    }
  }

  async function loadIssuePreview(key) {
    const issueKey = String(key || "").trim();
    state.invest.previewKey = issueKey;
    state.invest.preview = null;
    state.invest.previewError = "";
    if (!issueKey) {
      render();
      return;
    }
    state.invest.previewBusy = true;
    render();
    const res = await api("/api/investigations/issue-preview?issue=" + encodeURIComponent(issueKey));
    if (state.invest.previewKey !== issueKey) {
      return;
    }
    state.invest.previewBusy = false;
    if (res.ok) {
      state.invest.preview = res.data;
      const repo = res.data.repo;
      if (repo && state.invest.form.repos.indexOf(repo) === -1) {
        state.invest.form.repos.push(repo);
      }
    } else {
      state.invest.previewError = (res.data && res.data.error) || "issue_unavailable";
    }
    render();
  }

  function ensureIssueOption(key, title) {
    if (!key) {
      return;
    }
    const exists = state.issues.some(function (item) { return item.issue_key === key; });
    if (!exists) {
      const parts = key.split("#");
      state.issues.push({
        issue_key: key,
        repo: parts[0] || "",
        number: Number(parts[1]) || null,
        title: title || "",
        url: "",
      });
    }
  }

  function investigateIssue(key, title) {
    snapshotForm();
    ensureIssueOption(key, title);
    state.invest.form.mode = "issue";
    state.invest.form.issueKey = key;
    state.invest.form.description = "";
    state.invest.error = "";
    render({ keepState: true });
    loadIssuePreview(key);
    const target = document.getElementById("invest-form");
    if (target) {
      target.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }

  async function runInvestigation() {
    snapshotInvestForm();
    const form = state.invest.form;
    const auto = form.mode === "issue";
    if (auto && !(form.issueKey || "").trim()) {
      state.invest.error = "issue_required";
      render();
      return;
    }
    if (!auto && !form.description.trim()) {
      state.invest.error = "invalid_description";
      render();
      return;
    }
    state.invest.busy = true;
    state.invest.error = "";
    state.invest.notice = "";
    render();
    const body = {
      mode: auto ? "issue" : "manual",
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
    await loadRadarOverview();
    await loadAiSettings();
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
      const row = actionsRow([el("button", { type: "button", text: "Cancelar", onClick: function () { modal.close(); } })]);
      if (form.error === "issue_delete_forbidden") {
        row.appendChild(el("button", {
          type: "button",
          text: form.busy ? "Aguarde…" : "Fechar como não planejada",
          disabled: form.busy ? "disabled" : null,
          onClick: function () { submit(body, "close"); },
        }));
      }
      row.appendChild(el("button", {
        type: "button",
        class: "danger-solid",
        text: form.busy ? "Aguarde…" : "Apagar issue",
        disabled: (!matches || form.busy) ? "disabled" : null,
        onClick: function () { submit(body, "delete"); },
      }));
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

  function trashIcon() {
    const ns = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(ns, "svg");
    svg.setAttribute("viewBox", "0 0 16 16");
    svg.setAttribute("width", "15");
    svg.setAttribute("height", "15");
    svg.setAttribute("aria-hidden", "true");
    const path = document.createElementNS(ns, "path");
    path.setAttribute("fill", "none");
    path.setAttribute("stroke", "currentColor");
    path.setAttribute("stroke-width", "1.5");
    path.setAttribute("stroke-linecap", "round");
    path.setAttribute("stroke-linejoin", "round");
    path.setAttribute("d", "M5.5 6.2v5M8 6.2v5M10.5 6.2v5M3.5 4.3h9M6.2 4.3V3.2h3.6v1.1M4.2 4.3l.5 8.2h6.6l.5-8.2");
    svg.appendChild(path);
    return svg;
  }

  function deleteIssueButton(owner, repoName, number, onDeleted, compact) {
    if (!owner || !repoName || !number || !isOwner()) {
      return null;
    }
    const key = owner + "/" + repoName + "#" + number;
    const btn = el("button", {
      type: "button",
      class: "quiet danger sm icon-only" + (compact ? " issue-delete-btn" : ""),
      title: "Apagar issue " + key,
      "aria-label": "Apagar issue " + key,
      onClick: function (ev) {
        ev.stopPropagation();
        openDeleteIssueModal(owner, repoName, number, onDeleted);
      },
    });
    btn.appendChild(trashIcon());
    return btn;
  }

  function issueRowKey(item) {
    if (item.repo && item.number) {
      const repo = String(item.repo);
      const slash = repo.lastIndexOf("/");
      const short = slash >= 0 ? repo.slice(slash + 1) : repo;
      return short + "#" + item.number;
    }
    return item.issue_key || "";
  }

  function uniqueIssueRepos() {
    const seen = {};
    const out = [];
    state.issues.forEach(function (item) {
      const repo = item.repo || "";
      if (repo && !seen[repo]) {
        seen[repo] = true;
        out.push(repo);
      }
    });
    out.sort();
    return out;
  }

  function filteredIssues() {
    const q = (state.issueQuery || "").trim().toLowerCase();
    const repo = state.issueRepoFilter || "";
    return state.issues.filter(function (item) {
      if (repo && item.repo !== repo) {
        return false;
      }
      if (!q) {
        return true;
      }
      const hay = [item.issue_key, item.title, item.repo, item.number].join(" ").toLowerCase();
      return hay.indexOf(q) !== -1;
    });
  }

  function onIssueDeleted(item) {
    return async function () {
      state.notice = "Issue " + item.issue_key + " apagada.";
      await loadInvestigacao();
      render();
    };
  }

  function paintIssueRows(list) {
    list.replaceChildren();
    const items = filteredIssues();
    if (!items.length) {
      list.appendChild(el("p", {
        class: "muted issue-list-empty",
        text: state.issues.length ? "Nenhuma issue corresponde ao filtro." : "Nenhuma issue carregada.",
      }));
      return;
    }
    items.forEach(function (item) {
      const parts = splitOwnerRepo(item.repo);
      const row = el("div", {
        class: "issue-row" + (state.selectedIssue === item.issue_key ? " active" : ""),
      });
      const pick = el("button", {
        type: "button",
        class: "issue-row-pick",
        onClick: function () { selectIssue(item.issue_key); },
      }, [
        el("span", { class: "issue-row-key", text: issueRowKey(item) }),
        el("span", { class: "issue-row-title", text: item.title || item.issue_key || "(sem título)" }),
      ]);
      row.appendChild(pick);
      const del = deleteIssueButton(parts.owner, parts.repo, item.number, onIssueDeleted(item), true);
      if (del) {
        row.appendChild(del);
      }
      list.appendChild(row);
    });
  }

  function renderIssuePicker() {
    const issueBox = el("section", { class: "card" }, [
      cardHead("Issues", [countLabel(state.issues.length)]),
    ]);
    if (state.issuesError) {
      issueBox.appendChild(el("p", { class: "banner banner-warn", text: state.issuesError }));
    }
    const repoWrap = el("div", null, [
      el("label", { text: "Repositório", for: "issue-filter-repo" }),
    ]);
    const toolbar = el("div", { class: "issue-toolbar" }, [
      el("div", null, [
        el("label", { text: "Buscar", for: "issue-filter-text" }),
        el("input", {
          id: "issue-filter-text",
          type: "search",
          value: state.issueQuery || "",
          placeholder: "Título, repositório ou número",
          onInput: function (ev) {
            state.issueQuery = ev.target.value;
            const list = document.getElementById("issue-list-scroll");
            if (list) {
              paintIssueRows(list);
            }
          },
        }),
      ]),
      repoWrap,
    ]);
    const repoSel = el("select", {
      id: "issue-filter-repo",
      onChange: function (ev) {
        state.issueRepoFilter = ev.target.value;
        const list = document.getElementById("issue-list-scroll");
        if (list) {
          paintIssueRows(list);
        }
      },
    });
    repoSel.appendChild(el("option", { value: "", text: "Todos os repositórios" }));
    uniqueIssueRepos().forEach(function (repo) {
      const opt = el("option", { value: repo, text: repo });
      if (state.issueRepoFilter === repo) {
        opt.selected = true;
      }
      repoSel.appendChild(opt);
    });
    repoWrap.appendChild(repoSel);
    issueBox.appendChild(toolbar);
    const list = el("div", { class: "issue-list-scroll", id: "issue-list-scroll" });
    paintIssueRows(list);
    issueBox.appendChild(list);
    if (isOwner()) {
      issueBox.appendChild(el("div", { class: "issue-list-actions" }, [
        el("button", {
          type: "button",
          text: state.busy ? "Aguarde…" : "Importar issues concluídas",
          disabled: state.busy ? "disabled" : null,
          onClick: function () { importCompletedIssues(); },
        }),
      ]));
    }
    return issueBox;
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
      return { cls: "status-warn", text: "Indexando" };
    }
    const hasData = (state.teia.nodes || []).length > 0 || (state.graphs || []).length > 0;
    if (hasData) {
      return { cls: "status-ok", text: "Ativo" };
    }
    return { cls: "status-muted", text: "Desligado" };
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
    if (!panel) {
      const float = document.getElementById("teia-float");
      if (float) {
        float.hidden = !teiaNodeById(state.teiaSelected);
        fillTeiaDetail(float);
      }
    }
    const host = panel || document.getElementById("teia-detail");
    if (!host) {
      return;
    }
    host.replaceChildren();
    const selected = teiaNodeById(state.teiaSelected);
    if (!selected) {
      host.appendChild(el("h2", { text: "Detalhe" }));
      host.appendChild(el("p", { class: "muted", text: "Selecione um nó na teia para ver a origem, os links e os vizinhos." }));
      return;
    }
    host.appendChild(el("p", { class: "teia-k", text: teiaTypeLabel(selected.type) + (selected.repo ? " · " + selected.repo : "") }));
    host.appendChild(el("h3", { text: selected.label || selected.id }));
    if (selected.path) {
      host.appendChild(el("p", { class: "teia-path", text: selected.path }));
    }
    if (selected.url) {
      host.appendChild(el("p", null, [safeLink(selected.url, teiaLinkLabel(selected) + " ↗")]));
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
        row.appendChild(el("span", { class: "pill pill-outline", text: String(name) }));
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
    host.appendChild(el("p", { class: "teia-k", text: "Vizinhos (" + neighbors.length + ")" }));
    if (!neighbors.length) {
      host.appendChild(el("p", { class: "muted", text: "Sem vizinhos neste recorte." }));
      return;
    }
    const nlist = el("div", { class: "teia-nlist" });
    neighbors.forEach(function (node) {
      nlist.appendChild(el("button", {
        type: "button",
        class: "teia-neighbor",
        onClick: function () { selectTeiaNode(node.id); },
      }, [
        el("span", { class: "muted", text: teiaTypeLabel(node.type) }),
        el("span", { text: node.label || node.id }),
      ]));
    });
    host.appendChild(nlist);
  }

  function setTeiaFull(on) {
    state.teiaFull = !!on;
    render({ keepState: true });
    if (state.teiaFull) {
      fillTeiaDetail();
    }
    const btn = document.querySelector(".teia-full-btn");
    if (btn) {
      btn.focus();
    }
  }

  function teiaFullButton() {
    const full = state.teiaFull;
    const label = full ? "Sair da tela cheia (Esc)" : "Tela cheia";
    return el("button", {
      type: "button",
      class: "teia-full-btn",
      "aria-label": label,
      "aria-pressed": full ? "true" : "false",
      title: label,
      onClick: function () { setTeiaFull(!state.teiaFull); },
    }, [strokeIcon(full
      ? "M6 2.5V6H2.5M10 2.5V6h3.5M6 13.5V10H2.5M10 13.5V10h3.5"
      : "M2.5 6V2.5H6M13.5 6V2.5H10M2.5 10v3.5H6M13.5 10v3.5H10")]);
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
      host.appendChild(el("div", { class: "teia-empty" }, [emptyState("Nenhum nó neste recorte", "Ajuste os filtros, importe issues ou aguarde o índice Graphify.")]));
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

  function modeSwitch() {
    const current = state.invest.form.mode === "issue" ? "issue" : "manual";
    const options = [
      ["manual", "Escrever o pedido", "Você descreve o que investigar."],
      ["issue", "Usar uma issue", "A issue vira o pedido."],
    ];
    return el("div", { class: "segmented", role: "radiogroup", "aria-label": "Tipo de pedido" }, options.map(function (opt) {
      const active = current === opt[0];
      return el("button", {
        type: "button",
        role: "radio",
        "aria-checked": active ? "true" : "false",
        class: "segmented-option" + (active ? " active" : ""),
        onClick: function () {
          if (!active) {
            setInvestMode(opt[0]);
          }
        },
      }, [
        el("span", { class: "segmented-title", text: opt[1] }),
        el("span", { class: "segmented-sub", text: opt[2] }),
      ]);
    }));
  }

  function issueSelect(id, placeholder, onChange) {
    const sel = el("select", { id: id, onChange: onChange || null });
    sel.appendChild(el("option", { value: "", text: placeholder }));
    state.issues.forEach(function (item) {
      const label = item.issue_key + (item.title ? " — " + item.title : "");
      const opt = el("option", { value: item.issue_key, text: label });
      if (state.invest.form.issueKey === item.issue_key) {
        opt.selected = true;
      }
      sel.appendChild(opt);
    });
    return sel;
  }

  function requestPreview() {
    const box = el("div", { class: "request-preview", "aria-live": "polite" });
    if (!state.invest.form.issueKey) {
      box.appendChild(el("p", { class: "muted", text: "Escolha uma issue para ver o pedido que será enviado." }));
      return box;
    }
    if (state.invest.previewBusy) {
      box.appendChild(el("p", { class: "login-wait muted" }, [
        el("span", { class: "spinner", "aria-hidden": "true" }),
        el("span", { text: "Lendo a issue no GitHub…" }),
      ]));
      return box;
    }
    if (state.invest.previewError) {
      box.appendChild(el("p", { class: "field-hint field-error", text: errorMessage(state.invest.previewError) }));
      return box;
    }
    const p = state.invest.preview;
    if (!p) {
      return box;
    }
    box.appendChild(el("p", { class: "teia-k", text: "Pedido que será enviado" }));
    box.appendChild(el("div", { class: "request-preview-title" }, [
      el("strong", { text: p.title || p.issue_key }),
      p.url ? safeLink(p.url, "Abrir ↗") : null,
    ]));
    const meta = el("div", { class: "request-preview-meta" }, [
      el("span", { class: "mono muted", text: p.issue_key }),
      p.state ? el("span", { class: "status " + (p.state === "OPEN" ? "status-ok" : "status-muted"), text: p.state === "OPEN" ? "Aberta" : "Fechada" }) : null,
    ]);
    (p.labels || []).forEach(function (name) {
      meta.appendChild(el("span", { class: "pill pill-outline", text: name }));
    });
    box.appendChild(meta);
    box.appendChild(el("p", { class: "request-preview-body", text: p.body_excerpt || "(issue sem descrição)" }));
    const comments = p.comments_total
      ? (p.comments_used + " de " + p.comments_total + " comentário(s) entram no pedido.")
      : "Sem comentários.";
    box.appendChild(el("p", { class: "field-hint", text: comments + " Junto vai o pedido padrão: entender o problema, apontar causas e pontos do código, dizer o que falta saber e sugerir próximos passos." }));
    return box;
  }

  function renderInvestForm(root) {
    const auto = state.invest.form.mode === "issue";
    const engineLabel = state.ai.data ? modelLabel(state.ai.data, state.ai.data.investigation) : "";
    const card = el("section", { class: "card", id: "invest-form" }, [
      cardHead("Nova investigação", [engineLabel ? el("div", { class: "card-actions" }, [el("button", {
        type: "button",
        class: "sm quiet",
        title: "Configurar o agente de investigação (aba Agentes)",
        text: "Motor: " + engineLabel,
        onClick: function () { openAgentByName("Agente de investigação"); },
      })]) : null]),
      el("p", { class: "card-desc", text: "Descreva o problema ou use uma issue existente como pedido. A investigação roda em modo somente leitura." }),
    ]);
    card.appendChild(el("label", { text: "Pedido" }));
    card.appendChild(modeSwitch());

    if (auto) {
      card.appendChild(el("label", { text: "Issue", for: "invest-issue-key" }));
      card.appendChild(issueSelect("invest-issue-key", "Selecione a issue", function (ev) {
        snapshotInvestForm();
        loadIssuePreview(ev.target.value);
      }));
      card.appendChild(requestPreview());
      card.appendChild(el("label", { text: "Complemento (opcional)", for: "invest-description" }));
      const extra = el("textarea", {
        id: "invest-description",
        class: "compact",
        rows: "3",
        placeholder: "Ex.: foque no fluxo de pagamento; o erro só acontece em produção.",
      });
      extra.value = state.invest.form.description || "";
      card.appendChild(extra);
    } else {
      card.appendChild(el("label", { text: "Descrição", for: "invest-description" }));
      const desc = el("textarea", {
        id: "invest-description",
        rows: "6",
        placeholder: "Ex.: a segunda via do boleto é gerada em dobro quando o cliente clica duas vezes em Reemitir.",
      });
      desc.value = state.invest.form.description || "";
      card.appendChild(desc);
    }

    card.appendChild(el("label", { text: "Repositórios" }));
    if (!state.invest.repos.length) {
      card.appendChild(el("p", { class: "field-hint", text: "Nenhum repositório elegível." }));
    } else {
      const reposBox = el("div", { class: "check-group" });
      state.invest.repos.forEach(function (repo) {
        const id = "invest-repo-" + repo.replace(/[^a-z0-9]/gi, "-");
        const box = el("input", { id: id, type: "checkbox", onChange: function (ev) { toggleInvestRepo(repo, ev.target.checked); } });
        if (state.invest.form.repos.indexOf(repo) !== -1) {
          box.checked = true;
        }
        reposBox.appendChild(el("label", { class: "check", for: id }, [box, el("span", { text: repo })]));
      });
      card.appendChild(reposBox);
      if (auto) {
        card.appendChild(el("p", { class: "field-hint", text: "O repositório da issue entra automaticamente." }));
      }
    }

    if (state.invest.connections.length) {
      card.appendChild(el("label", { text: "Conexões" }));
      const connBox = el("div", { class: "check-group" });
      state.invest.connections.forEach(function (conn) {
        const id = "invest-conn-" + conn.id;
        const box = el("input", { id: id, type: "checkbox", onChange: function (ev) { toggleInvestConnection(conn.id, ev.target.checked); } });
        if (state.invest.form.connectionIds.indexOf(conn.id) !== -1) {
          box.checked = true;
        }
        connBox.appendChild(el("label", { class: "check", for: id }, [
          box,
          el("span", { text: conn.name }),
          el("span", { class: "muted", text: conn.type }),
        ]));
      });
      card.appendChild(connBox);
      card.appendChild(el("p", { class: "field-hint", text: "Só metadados das conexões entram no contexto; segredos nunca." }));
    }

    if (!auto) {
      card.appendChild(el("label", { text: "Issue relacionada (opcional)", for: "invest-issue-key" }));
      card.appendChild(issueSelect("invest-issue-key", "Nenhuma"));
    }

    if (state.invest.error) {
      card.appendChild(el("p", { class: "banner banner-error", text: errorMessage(state.invest.error) }));
    }
    card.appendChild(actionsRow([el("button", {
      type: "button",
      class: "primary",
      text: state.invest.busy ? "Investigando…" : (auto ? "Investigar esta issue" : "Rodar investigação"),
      disabled: state.invest.busy ? "disabled" : null,
      onClick: function () { runInvestigation(); },
    })]));
    root.appendChild(card);
  }

  function renderInvestResult(root) {
    const view = state.invest.current;
    if (!view) {
      return;
    }
    const card = el("section", { class: "card invest-result" }, [
      cardHead(view.title || "Resultado"),
      el("div", { class: "result-meta" }, [
        el("span", { text: (view.repos || []).join(", ") || "Sem repositório associado" }),
        view.engine ? el("span", { text: "Motor: " + view.engine }) : null,
      ]),
    ]);
    if (state.invest.notice) {
      card.appendChild(el("p", { class: "banner banner-ok", text: state.invest.notice }));
    }
    card.appendChild(el("div", { class: "markdown-body" }, renderMarkdownNodes(view.result)));
    card.appendChild(actionsRow([el("button", {
      type: "button",
      class: "primary",
      text: state.invest.busy ? "Aguarde…" : "Gerar tarefa a partir desta investigação",
      disabled: state.invest.busy ? "disabled" : null,
      onClick: function () { investigationToTask(view.id, (view.repos || [])[0] || ""); },
    })]));
    root.appendChild(card);
  }

  function renderInvestHistory(root) {
    const card = el("section", { class: "card" }, [
      cardHead("Histórico", [countLabel(state.invest.list.length)]),
    ]);
    if (!state.invest.list.length) {
      card.appendChild(el("p", { class: "muted", text: "Nenhuma investigação ainda. As que você rodar ficam guardadas aqui." }));
      root.appendChild(card);
      return;
    }
    const list = el("div", { class: "list" });
    state.invest.list.forEach(function (item) {
      const active = state.invest.current && state.invest.current.id === item.id;
      list.appendChild(el("button", {
        type: "button",
        class: "list-item note-item" + (active ? " active" : ""),
        "aria-current": active ? "true" : null,
        onClick: function () { openInvestigation(item.id); },
      }, [
        el("span", { class: "list-item-title", text: item.title || "(sem título)" }),
        el("span", { class: "list-item-meta", text: (item.repos || []).join(", ") || "sem repositório" }),
      ]));
    });
    card.appendChild(list);
    root.appendChild(card);
  }

  function renderNotesCard() {
    const selected = state.issues.filter(function (item) { return item.issue_key === state.selectedIssue; })[0];
    const notesCard = el("section", { class: "card" }, [
      cardHead("Notas", [selected ? el("span", { class: "count mono", text: issueRowKey(selected) }) : null]),
      el("p", { class: "card-desc", text: "Notas manuais por issue, guardadas no banco do Forge e independentes do vault Obsidian. O corpo não vai para o log." }),
    ]);
    if (!state.selectedIssue) {
      notesCard.appendChild(el("p", { class: "muted", text: "Selecione uma issue na lista para ver e escrever notas." }));
      return notesCard;
    }
    const list = el("div", { class: "list" });
    if (!state.notes.length) {
      list.appendChild(el("p", { class: "list-empty", text: "Nenhuma nota nesta issue." }));
    }
    state.notes.forEach(function (note) {
      const active = state.selectedNoteId === note.id;
      list.appendChild(el("button", {
        type: "button",
        class: "list-item note-item" + (active ? " active" : ""),
        onClick: function () { openNote(note.id); },
      }, [
        el("span", { class: "list-item-title", text: note.title || "(sem título)" }),
        el("span", { class: "list-item-meta", text: note.size + " B" }),
      ]));
    });
    const editor = el("div", null, [
      el("label", { text: "Título", for: "note-title" }),
      el("input", { id: "note-title", type: "text", maxlength: "200", value: state.noteForm.title || "" }),
      el("label", { text: "Corpo", for: "note-body" }),
    ]);
    const noteBody = el("textarea", { id: "note-body", class: "preview" });
    noteBody.value = state.noteForm.body || "";
    editor.appendChild(noteBody);
    editor.appendChild(el("p", { class: "field-hint", text: "Markdown é exibido como texto." }));
    editor.appendChild(actionsRow([
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
      el("span", { class: "spacer" }),
      state.selectedNoteId ? el("button", {
        type: "button",
        class: "quiet danger",
        text: "Apagar",
        disabled: state.busy ? "disabled" : null,
        onClick: function () { deleteNote(); },
      }) : null,
    ]));
    notesCard.appendChild(el("div", { class: "notes-grid" }, [list, editor]));
    return notesCard;
  }

  function renderRelatedCard() {
    const relatedCard = el("section", { class: "card" }, [
      cardHead("Issues relacionadas"),
      el("p", { class: "card-desc", text: "Issues concluídas parecidas com a selecionada, com os PRs e arquivos que as resolveram." }),
    ]);
    if (!state.selectedIssue) {
      relatedCard.appendChild(el("p", { class: "muted", text: "Selecione uma issue para ver concluídas semelhantes." }));
    } else if (!state.relatedIssues.length) {
      relatedCard.appendChild(el("p", { class: "muted", text: "Nenhuma issue concluída semelhante. Owner pode importar o board." }));
    } else {
      const relatedList = el("div", null);
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
    return relatedCard;
  }

  function renderSourcesCard() {
    return el("section", { class: "card" }, [
      cardHead("Fontes"),
      el("p", { class: "card-desc", text: "Em construção: as outras fontes ainda não consultam a API. Todas serão somente leitura." }),
      el("ul", { class: "source-list" }, [
        sourceRow("Código", "Repositório Git"),
        sourceRow("Portainer", "Containers"),
        sourceRow("Banco", "MySQL / PostgreSQL"),
        sourceRow("FTP", "FTP / SFTP"),
        sourceRow("Obsidian", "Vault (aba Teia)"),
      ]),
    ]);
  }

  // --- Motor e modelo (componentes compartilhados) ------------------------------------------

  function engineChoice(form, meta, locked, repaint) {
    const apiReady = !!(meta.api && meta.api.configured);
    const serverEngine = meta.server_engine === "cursor" ? "Cursor CLI" : "Claude Code CLI";
    const options = [
      ["cli", serverEngine, "Pela assinatura. Cada chamada carrega o contexto da CLI (~25 mil tokens)."],
      ["api", "API da Anthropic", apiReady ? "Só o pedido e a resposta; cobrado por token na conta da API." : "Desligada: falta configurar a chave da API no servidor."],
    ];
    return el("div", { class: "segmented", role: "radiogroup", "aria-label": "Motor" }, options.map(function (opt) {
      const active = form.engine === opt[0];
      const blocked = locked || (opt[0] === "api" && !apiReady);
      return el("button", {
        type: "button",
        role: "radio",
        "aria-checked": active ? "true" : "false",
        class: "segmented-option" + (active ? " active" : ""),
        disabled: blocked ? "disabled" : null,
        onClick: function () {
          form.engine = opt[0];
          repaint();
        },
      }, [
        el("span", { class: "segmented-title", text: opt[1] }),
        el("span", { class: "segmented-sub", text: opt[2] }),
      ]);
    }));
  }

  function modelSelect(form, meta, id, locked) {
    const sel = el("select", {
      id: id,
      disabled: locked ? "disabled" : null,
      onChange: function (ev) { form.model = ev.target.value; },
    });
    sel.appendChild(el("option", { value: "", text: form.engine === "api" ? "Padrão (Claude Opus 5.5)" : "Padrão do motor" }));
    (meta.models || []).forEach(function (m) {
      const opt = el("option", { value: m.id, text: m.label + " — " + m.hint });
      if (form.model === m.id) {
        opt.selected = true;
      }
      sel.appendChild(opt);
    });
    return el("div", { class: "field" }, [el("label", { text: "Modelo", for: id }), sel]);
  }

  function apiStatusBlock(meta) {
    const apiReady = !!(meta.api && meta.api.configured);
    return el("p", { class: "field-hint" }, [
      el("span", { class: "status " + (apiReady ? "status-ok" : "status-muted"), text: apiReady ? "API da Anthropic configurada" : "API da Anthropic não configurada" }),
      el("span", { text: apiReady
        ? " — a chave fica no servidor e nunca é exibida."
        : " — para liberar, coloque FORGE_ANTHROPIC_API_KEY no .env do Forge e recrie o backend." }),
    ]);
  }

  function modelLabel(meta, form) {
    const found = (meta.models || []).filter(function (m) { return m.id === form.model; })[0];
    const engine = form.engine === "api" ? "API da Anthropic" : (meta.server_engine === "cursor" ? "Cursor CLI" : "Claude Code CLI");
    return engine + " · " + (found ? found.label : (form.engine === "api" ? "Claude Opus 5.5" : "modelo padrão"));
  }

  // --- Configuração do agente (detalhe na aba Agentes) ---------------------------------------

  function agentConfigSection() {
    const data = state.agentes.detail;
    const cfg = data && data.config;
    if (!cfg || (cfg.kind !== "radar" && cfg.kind !== "investigation")) {
      return null;
    }
    const isRadar = cfg.kind === "radar";
    if (!state.agentes.configForm) {
      state.agentes.configForm = { auto: !!cfg.auto, time: cfg.time || "13:00", engine: cfg.engine, model: cfg.model || "" };
    }
    const form = state.agentes.configForm;
    const locked = !cfg.can_edit;
    const section = el("div", { class: "agent-section agent-config" }, [
      el("div", { class: "radar-section-head" }, [
        el("h3", { text: "Configuração do agente" }),
        locked ? el("span", { class: "count", text: "só o owner altera" }) : null,
      ]),
    ]);
    const autoBox = el("input", {
      id: "agent-cfg-auto",
      type: "checkbox",
      disabled: locked ? "disabled" : null,
      onChange: function (ev) { form.auto = ev.target.checked; paintAgentDetail(); },
    });
    autoBox.checked = !!form.auto;
    if (isRadar) {
    section.appendChild(el("label", { text: "Agenda" }));
    section.appendChild(el("div", { class: "toggle-row" }, [
      el("label", { class: "check toggle-check", for: "agent-cfg-auto" }, [
        autoBox,
        el("span", { text: "Rodar automaticamente uma vez por dia" }),
      ]),
      el("div", { class: "toggle-time" }, [
        el("label", { text: "às", for: "agent-cfg-time" }),
        el("input", {
          id: "agent-cfg-time",
          type: "time",
          value: form.time || "13:00",
          disabled: (locked || !form.auto) ? "disabled" : null,
          onChange: function (ev) { form.time = ev.target.value; },
        }),
      ]),
    ]));
    section.appendChild(el("p", { class: "field-hint", text: form.auto
      ? "Roda sozinho todo dia nesse horário (Brasília). \"Analisar agora\" continua no painel do radar."
      : "Desligado: só roda quando alguém clicar em \"Analisar agora\" no painel do radar." }));
    }
    section.appendChild(el("label", { text: "Motor" }));
    section.appendChild(engineChoice(form, cfg, locked, paintAgentDetail));
    section.appendChild(modelSelect(form, cfg, "agent-cfg-model", locked));
    section.appendChild(el("p", { class: "field-hint", text: isRadar
      ? "O resumo do radar é curto: Haiku 5.5 costuma bastar. Se o board não mudou desde a última rodada, o resumo é reaproveitado sem chamar modelo."
      : "A investigação lê o grafo de código e escreve hipóteses: Sonnet 5.5 ou Opus 5.5 são as escolhas mais seguras." }));
    section.appendChild(apiStatusBlock(cfg));
    if (state.agentes.configError) {
      section.appendChild(el("p", { class: "banner banner-error", text: errorMessage(state.agentes.configError) }));
    }
    if (!locked) {
      section.appendChild(actionsRow([el("button", {
        type: "button",
        class: "primary",
        text: state.agentes.configSaving ? "Salvando…" : "Salvar configuração",
        disabled: state.agentes.configSaving ? "disabled" : null,
        onClick: function () { saveAgentConfig(); },
      })]));
    }
    return section;
  }

  async function saveAgentConfig() {
    const data = state.agentes.detail;
    const form = state.agentes.configForm;
    const time = document.getElementById("agent-cfg-time");
    if (time && time.value) {
      form.time = time.value;
    }
    state.agentes.configSaving = true;
    state.agentes.configError = "";
    paintAgentDetail();
    const res = await api("/api/agents/" + encodeURIComponent(data.agent.id) + "/config", { method: "POST", body: form });
    state.agentes.configSaving = false;
    if (!res.ok) {
      state.agentes.configError = (res.data && res.data.error) || "error";
      paintAgentDetail();
      return;
    }
    const fresh = await api("/api/agents/" + encodeURIComponent(data.agent.id));
    if (fresh.ok) {
      state.agentes.detail = fresh.data;
      state.agentes.selected = fresh.data.agent;
    }
    state.agentes.configForm = null;
    showToast("Configuração do agente salva.");
    paintAgentDetail();
    if (activeTab() === "agentes") {
      await loadAgentes();
      render();
    }
  }

  async function openAgentByName(name) {
    if (state.radar.modal) {
      state.radar.modal.close();
    }
    const res = await api("/api/agents");
    const agent = res.ok ? (res.data.agents || []).filter(function (a) { return a.name === name; })[0] : null;
    if (!agent) {
      showToast("Agente ainda não cadastrado. Recrie o backend para registrá-lo.");
      return;
    }
    openAgentDetail(agent.id);
  }

  function openRadarAgent() {
    openAgentByName("Radar de prioridades");
  }

  // --- Motor da investigação (fica na Investigação: não é um agente) -------------------------

  async function loadAiSettings() {
    const res = await api("/api/ai-settings");
    if (res.ok) {
      state.ai.data = res.data;
    }
    return res.ok;
  }

  // --- Radar de prioridades ------------------------------------------------------------------

  function fmtDateTime(iso) {
    if (!iso) {
      return "—";
    }
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) {
      return "—";
    }
    const today = new Date();
    const sameDay = d.toDateString() === today.toDateString();
    const time = d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
    if (sameDay) {
      return "hoje, " + time;
    }
    return d.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" }) + ", " + time;
  }

  async function loadRadarOverview() {
    const res = await api("/api/radar");
    if (!res.ok) {
      return;
    }
    state.radar.overview = res.data;
    state.radar.busy = !!res.data.busy;
    if (!state.radar.selectedId && res.data.latest) {
      state.radar.report = res.data.latest;
    }
  }

  async function loadRadarHistory() {
    const res = await api("/api/radar/reports");
    state.radar.history = res.ok ? (res.data.reports || []) : [];
  }

  function radarButton() {
    const latest = state.radar.overview && state.radar.overview.latest;
    const count = latest && latest.status === "ok" ? (latest.stats && latest.stats.now) || 0 : 0;
    return el("button", {
      type: "button",
      class: "radar-trigger",
      onClick: function () { openRadar(); },
    }, [
      el("span", { text: "Radar de prioridades" }),
      count ? el("span", { class: "radar-trigger-count", "aria-label": count + " para concluir já", text: String(count) }) : null,
    ]);
  }

  function stopRadarPoll() {
    if (state.radar.pollTimer) {
      window.clearInterval(state.radar.pollTimer);
      state.radar.pollTimer = null;
    }
  }

  function startRadarPoll() {
    if (state.radar.pollTimer) {
      return;
    }
    state.radar.pollTimer = window.setInterval(async function () {
      await loadRadarOverview();
      if (!state.radar.busy) {
        stopRadarPoll();
        state.radar.selectedId = "";
        state.radar.report = state.radar.overview && state.radar.overview.latest;
        await loadRadarHistory();
        const report = state.radar.report;
        if (report && report.status === "ok") {
          showToast("Radar atualizado.");
        }
        render();
      }
      paintRadar();
    }, 3000);
  }

  async function runRadarNow() {
    state.radar.error = "";
    const res = await api("/api/radar/run", { method: "POST", body: {} });
    if (!res.ok && res.status !== 409) {
      state.radar.error = (res.data && res.data.error) || "error";
      paintRadar();
      return;
    }
    state.radar.busy = true;
    paintRadar();
    startRadarPoll();
  }

  async function selectRadarReport(id) {
    state.radar.selectedId = id;
    const res = await api("/api/radar/reports/" + encodeURIComponent(id));
    if (res.ok) {
      state.radar.report = res.data;
    } else {
      state.radar.error = (res.data && res.data.error) || "error";
    }
    paintRadar();
  }

  async function openRadar() {
    if (state.radar.modal) {
      return;
    }
    state.radar.error = "";
    state.radar.modal = openModal({
      title: "Radar de prioridades",
      subtitle: "Backlog de TI · o que concluir já, o que está parado e o que vale investigar",
      variant: "sheet",
      build: function () { paintRadar(); },
      onClose: function () {
        state.radar.modal = null;
      },
    });
    await loadRadarOverview();
    await loadRadarHistory();
    if (state.radar.busy) {
      startRadarPoll();
    }
    paintRadar();
  }

  function radarEntry(entry, kind) {
    const meta = el("div", { class: "radar-item-meta" }, [
      el("span", { class: "mono", text: entry.key.split("/").pop() }),
      entry.status ? el("span", { text: entry.status }) : null,
      entry.prioridade ? el("span", { class: "pill " + priorityPill(entry.prioridade), text: entry.prioridade }) : null,
      entry.sprint ? el("span", { text: entry.sprint }) : null,
      el("span", { text: (entry.assignees && entry.assignees.length) ? "@" + entry.assignees.join(", @") : "sem responsável" }),
    ]);
    const reasons = (kind === "investigate" ? (entry.investigate_reasons || []) : entry.reasons) || [];
    const action = entry.investigable
      ? el("button", {
        type: "button",
        class: "sm",
        text: "Investigar",
        onClick: function () {
          if (state.radar.modal) {
            state.radar.modal.close();
          }
          investigateIssue(entry.key, entry.title);
        },
      })
      : el("span", { class: "radar-item-note", title: "O repositório desta issue não está na allowlist do Forge.", text: "Fora da allowlist" });
    return el("li", { class: "radar-item" }, [
      el("div", { class: "radar-item-main" }, [
        el("div", { class: "radar-item-title" }, [
          entry.url ? safeLink(entry.url, entry.title || entry.key) : el("span", { text: entry.title || entry.key }),
        ]),
        meta,
        reasons.length ? el("p", { class: "radar-item-reasons", text: reasons.join(" · ") }) : null,
      ]),
      el("div", { class: "radar-item-side" }, [
        el("span", { class: "radar-score", title: "Pontuação do radar", text: String(entry.score) }),
        action,
      ]),
    ]);
  }

  function priorityPill(name) {
    const key = String(name || "").toLowerCase();
    if (key.indexOf("urgente") === 0) {
      return "pill-danger";
    }
    if (key.indexOf("alta") === 0) {
      return "pill-warn";
    }
    return "pill-outline";
  }

  function radarSection(title, hint, entries, kind, emptyText) {
    const section = el("div", { class: "radar-section" }, [
      el("div", { class: "radar-section-head" }, [
        el("h3", { text: title }),
        el("span", { class: "count", text: String(entries.length) }),
      ]),
      hint ? el("p", { class: "radar-section-hint", text: hint }) : null,
    ]);
    if (!entries.length) {
      section.appendChild(el("p", { class: "radar-empty", text: emptyText }));
      return section;
    }
    section.appendChild(el("ol", { class: "radar-list" }, entries.map(function (entry) {
      return radarEntry(entry, kind);
    })));
    return section;
  }

  function paintRadar() {
    const modal = state.radar.modal;
    if (!modal) {
      return;
    }
    const body = modal.body;
    body.replaceChildren();
    const ov = state.radar.overview || {};
    const report = state.radar.report;

    const scheduleText = ov.auto
      ? "Automático todo dia às " + (ov.time || "13:00") + (ov.next_run ? " · próxima " + fmtDateTime(ov.next_run) : "")
      : "Automático desligado: rode com \"Analisar agora\".";
    const toolbar = el("div", { class: "radar-toolbar" }, [el("p", { class: "radar-schedule" }, [
      el("span", { class: "status " + (ov.auto ? "status-ok" : "status-muted"), text: scheduleText }),
      el("button", { type: "button", class: "sm quiet", text: "Configurar agente", onClick: function () { openRadarAgent(); } }),
    ])]);
    const controls = el("div", { class: "radar-controls" });
    if (state.radar.history.length) {
      const sel = el("select", {
        id: "radar-history",
        "aria-label": "Relatório",
        onChange: function (ev) { selectRadarReport(ev.target.value); },
      });
      state.radar.history.forEach(function (item) {
        const label = fmtDateTime(item.created_at) + " · " + (item.reason === "manual" ? "manual" : "agendado")
          + (item.status === "ok" ? "" : " · falhou");
        const opt = el("option", { value: item.id, text: label });
        if (report && report.id === item.id) {
          opt.selected = true;
        }
        sel.appendChild(opt);
      });
      controls.appendChild(sel);
    }
    controls.appendChild(el("button", {
      type: "button",
      class: "primary",
      disabled: state.radar.busy ? "disabled" : null,
      onClick: function () { runRadarNow(); },
    }, state.radar.busy
      ? [el("span", { class: "spinner spinner-on-accent", "aria-hidden": "true" }), el("span", { text: "Analisando…" })]
      : [el("span", { text: "Analisar agora" })]));
    toolbar.appendChild(controls);
    body.appendChild(toolbar);

    if (state.radar.error) {
      body.appendChild(el("p", { class: "banner banner-error", text: errorMessage(state.radar.error) }));
    }
    if (state.radar.busy) {
      body.appendChild(el("p", { class: "banner banner-info", text: "Lendo o board e calculando prioridades. Leva cerca de um minuto; pode fechar o painel." }));
    }
    if (!report) {
      body.appendChild(el("div", { class: "empty" }, [
        el("strong", { text: "Nenhum relatório ainda" }),
        el("span", { text: "Use \"Analisar agora\" ou espere o próximo horário da agenda." }),
      ]));
      return;
    }
    if (report.status !== "ok") {
      body.appendChild(el("p", {
        class: "banner banner-error",
        text: "A rodada de " + fmtDateTime(report.created_at) + " falhou: " + errorMessage(report.error || "error"),
      }));
      return;
    }

    const stats = report.stats || {};
    const staleDays = report.stale_days || ov.stale_days || 14;
    body.appendChild(el("div", { class: "metric-grid radar-stats" }, [
      metricCard("core", stats.open || 0, null, "Abertas"),
      metricCard("danger", stats.now || 0, null, "Concluir agora"),
      metricCard("warn", stats.stale || 0, null, "Paradas há " + staleDays + "+ dias"),
      metricCard("core", stats.unassigned || 0, null, "Sem responsável"),
    ]));

    if (report.summary) {
      body.appendChild(el("div", { class: "radar-summary" }, [
        el("p", { class: "teia-k", text: "Resumo" }),
        el("div", { class: "markdown-body" }, renderMarkdownNodes(report.summary)),
      ]));
    } else if (report.summary_error) {
      body.appendChild(el("p", { class: "field-hint", text: "Resumo indisponível nesta rodada (motor: " + report.summary_error + "). A ordem abaixo não depende dele." }));
    }

    body.appendChild(radarSection(
      "Concluir agora",
      "Prioridade alta, segurança, prazo ou sprint vencidos, ou reaberta.",
      report.now || [], "now", "Nada urgente no momento.",
    ));
    body.appendChild(radarSection(
      "Paradas há mais de " + staleDays + " dias",
      "Sem atividade na issue nem no board.",
      report.stale || [], "stale", "Nenhuma issue parada.",
    ));
    body.appendChild(radarSection(
      "Vale investigar",
      "Pouca definição para andar: triagem longa, sem prioridade ou sem estimativa.",
      report.investigate || [], "investigate", "Nada pendente de definição.",
    ));
    body.appendChild(el("p", {
      class: "radar-footnote",
      text: "Relatório de " + fmtDateTime(report.created_at) + ". A ordem vem de uma regra fixa (prioridade, segurança, tempo parado, prazos e sprint); o resumo é escrito pelo motor. Nada é alterado no GitHub.",
    }));
  }

  function renderInvestigacao(root) {
    root.appendChild(pageHeader(
      "Investigação",
      "Descreva um problema, erro ou sintoma; o agente investiga os repositórios em modo somente leitura e sugere próximos passos.",
      canEditNotes() ? [radarButton()] : null,
    ));
    root.appendChild(readonlySeal());
    if (!canEditNotes()) {
      root.appendChild(el("p", { class: "banner banner-warn", text: "Só editor ou owner vê as notas da investigação." }));
      return;
    }
    const mainCol = el("div", { class: "investigacao-col-main" });
    renderInvestForm(mainCol);
    renderInvestResult(mainCol);
    const sideCol = el("aside", { class: "investigacao-col-side" });
    renderInvestHistory(sideCol);
    sideCol.appendChild(renderSourcesCard());
    root.appendChild(el("div", { class: "investigacao-cols" }, [mainCol, sideCol]));

    root.appendChild(el("h2", { class: "section-title", text: "Notas por issue" }));
    root.appendChild(el("p", { class: "section-desc", text: "Contexto manual que você anexa às issues do GitHub, mais as concluídas que se parecem com elas." }));
    root.appendChild(el("div", { class: "notes-section" }, [
      renderIssuePicker(),
      el("div", null, [renderNotesCard(), renderRelatedCard()]),
    ]));
  }

  function renderTeia(root) {
    const vaultEnabled = !!(state.teia && state.teia.vault);
    const indexing = !!state.graphBusy;
    const status = teiaStatus();
    if (!canEditNotes()) {
      root.appendChild(el("p", { class: "banner banner-warn", text: "Só editor ou owner lê o vault e o grafo." }));
      return;
    }
    if (state.graphNotice || indexing) {
      const prog = el("ul", { class: "teia-progress" });
      (state.graphIndex.repos || []).forEach(function (row) {
        const reason = row.error || row.hint || "";
        prog.appendChild(el("li", {
          text: (row.repo || "") + " · " + (row.status || "queued") + (reason ? " (" + reason + ")" : ""),
        }));
      });
      root.appendChild(el("div", { class: "banner banner-info" }, [
        el("div", null, [
          el("p", { class: "login-wait" }, [
            el("span", { class: "spinner", "aria-hidden": "true" }),
            el("span", { text: state.graphNotice || "Indexando…" }),
          ]),
          (state.graphIndex.repos || []).length ? prog : null,
        ]),
      ]));
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
      placeholder: "Nome, arquivo ou issue",
      onKeydown: function (ev) {
        if (ev.key === "Enter") {
          applyTeiaFilters();
        }
      },
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
        el("strong", { text: "Teia de contexto" }),
        el("span", { class: "status " + status.cls, text: status.text }),
        vaultEnabled ? el("span", { class: "status status-ok", text: "Vault conectado" }) : null,
        el("span", { class: "muted teia-count", text: teiaCountText() }),
      ]),
      el("div", { class: "teia-filter-row" }, [
        el("div", null, [el("label", { text: "Repositório", for: "teia-repo" }), repoSelect]),
        el("div", null, [el("label", { text: "Busca", for: "teia-query" }), q]),
        el("button", {
          type: "button",
          text: "Aplicar filtros",
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

    const graphCard = el("section", { class: "card teia-graphs" }, [
      cardHead("Índice de código", [
        isOwner() ? el("div", { class: "card-actions" }, [el("button", {
          type: "button",
          class: "sm",
          text: indexing ? "Indexando…" : "Atualizar grafo",
          disabled: indexing ? "disabled" : null,
          onClick: function () { refreshGraph(state.teiaRepo || state.graphRepo); },
        })]) : null,
      ]),
      el("p", { class: "card-desc", text: "Grafos Graphify dos repositórios da allowlist, gerados offline, sem LLM." }),
    ]);
    if (!state.graphs.length) {
      graphCard.appendChild(el("p", { class: "muted", text: "Nenhum grafo ainda." }));
    } else {
      const table = el("table");
      table.appendChild(el("thead", null, [el("tr", null, [
        el("th", { text: "Repositório" }),
        el("th", { text: "Ref" }),
        el("th", { class: "num", text: "Nós" }),
        el("th", { class: "num", text: "Arestas" }),
      ])]));
      const tbody = el("tbody");
      state.graphs.forEach(function (g) {
        const ref = g.tag || (g.source === "head" ? ("HEAD " + (g.ref || "")) : (g.ref || g.error || "—"));
        tbody.appendChild(el("tr", null, [
          el("td", { text: g.repo || "" }),
          el("td", { class: "mono", text: ref }),
          el("td", { class: "num", text: String(g.nodes || 0) }),
          el("td", { class: "num", text: String(g.edges || 0) }),
        ]));
      });
      table.appendChild(tbody);
      graphCard.appendChild(el("div", { class: "table-wrap" }, [table]));
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

    const web = el("div", { class: "teia-web" + (state.teiaFull ? " is-full" : "") });
    web.appendChild(legend);
    web.appendChild(teiaFullButton());
    if (state.teiaFull) {
      const float = el("aside", { class: "teia-float", id: "teia-float", "aria-label": "Nó selecionado" });
      web.appendChild(float);
    }
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
      const descInput = el("textarea", { id: "agent-description", rows: "3" });
      descInput.value = form.description;
      body.appendChild(descInput);
      const scopeSel = el("select", { id: "agent-scope" });
      [["development", "Desenvolvimento"], ["company_system", "Sistema da empresa"]].forEach(function (pair) {
        const opt = el("option", { value: pair[0], text: pair[1] });
        if (pair[0] === form.scope) {
          opt.selected = true;
        }
        scopeSel.appendChild(opt);
      });
      const engineInput = el("input", { id: "agent-engine", type: "text", value: form.engine, placeholder: "ex.: claude-code" });
      body.appendChild(el("div", { class: "field-grid" }, [
        el("div", { class: "field" }, [el("label", { text: "Escopo", for: "agent-scope" }), scopeSel]),
        el("div", { class: "field" }, [el("label", { text: "Motor", for: "agent-engine" }), engineInput]),
      ]));
      body.appendChild(el("label", { text: "Gatilho", for: "agent-trigger" }));
      const triggerInput = el("input", { id: "agent-trigger", type: "text", value: form.trigger, placeholder: "ex.: issue nova no GitHub" });
      body.appendChild(triggerInput);
      body.appendChild(el("label", { text: "Pode ler", for: "agent-read" }));
      const readInput = el("input", { id: "agent-read", type: "text", value: form.permissions_read, placeholder: "issues, prs, notas do obsidian" });
      body.appendChild(readInput);
      body.appendChild(el("label", { text: "Pode alterar", for: "agent-write" }));
      const writeInput = el("input", { id: "agent-write", type: "text", value: form.permissions_write, placeholder: "etiquetas, rascunhos de issue" });
      body.appendChild(writeInput);
      body.appendChild(el("p", { class: "field-hint", text: "Separe os itens por vírgula. Banco de dados, FTP/SFTP e Portainer nunca recebem escrita, mesmo com aprovação." }));
      if (form.error) {
        body.appendChild(el("p", { class: "banner banner-error", text: errorMessage(form.error) }));
      }
      body.appendChild(actionsRow([
        el("button", { type: "button", text: "Cancelar", onClick: function () { modal.close(); } }),
        el("button", {
          type: "button", class: "primary",
          text: form.busy ? "Criando…" : "Criar agente",
          disabled: form.busy ? "disabled" : null,
          onClick: function () { submit(body); },
        }),
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
      return el("span", { class: "pill pill-danger-outline", text: "Sistema da empresa" });
    }
    return el("span", { class: "pill pill-outline", text: "Desenvolvimento" });
  }

  function agentStatusPill(status) {
    const map = {
      active: { cls: "status-ok", text: "Ativo" },
      paused: { cls: "status-muted", text: "Pausado" },
      error: { cls: "status-danger", text: "Com erro" },
    };
    const info = map[status] || { cls: "status-muted", text: status || "—" };
    return el("span", { class: "status " + info.cls, text: info.text });
  }

  function successMeter(rate) {
    if (rate === null || rate === undefined) {
      return el("span", { class: "muted", text: "—" });
    }
    const pct = Math.max(0, Math.min(100, Number(rate) || 0));
    const level = pct >= 90 ? "" : (pct >= 70 ? " is-mid" : " is-low");
    const fill = el("span");
    fill.style.width = pct + "%";
    return el("div", { class: "success-cell", title: "Taxa de sucesso: " + pct + "%" }, [
      el("span", { class: "success-value", text: pct + "%" }),
      el("span", { class: "success-bar" + level, "aria-hidden": "true" }, [fill]),
    ]);
  }

  function metricCard(kind, value, total, label) {
    const valueChildren = [el("span", { text: String(value) })];
    if (total !== null && total !== undefined) {
      valueChildren.push(el("span", { class: "metric-total", text: "de " + total }));
    }
    const nonzero = Number(value) > 0 ? " is-nonzero" : "";
    return el("div", { class: "metric-card metric-" + kind + nonzero }, [
      el("p", { class: "metric-label", text: label }),
      el("div", { class: "metric-value" }, valueChildren),
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

  function renderAgentsTable(root, items) {
    const count = countLabel(items.length);
    count.id = "agent-count";
    const card = el("section", { class: "card" }, [
      cardHead("Ativos", [count]),
    ]);
    if (!items.length) {
      card.appendChild(emptyState(
        "Nenhum agente ativo neste setor",
        routeSector() === "desenvolvimento" ? "Use \"Novo agente\" para criar o primeiro." : "Os agentes planejados estão logo abaixo.",
      ));
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
    items.forEach(function (agent) {
      const selected = agent.id === state.agentes.selectedId;
      tbody.appendChild(el("tr", {
        class: "agent-row" + (selected ? " selected" : ""),
        "data-agent-row": "",
        "data-status": agent.status || "",
        "data-search": ((agent.name || "") + " " + (agent.description || "")).toLocaleLowerCase("pt-BR"),
        tabindex: "0",
        "aria-selected": selected ? "true" : "false",
        title: "Ver detalhes do agente",
        onClick: function () { openAgentDetail(agent.id); },
        onKeydown: function (ev) {
          if (ev.key === "Enter" || ev.key === " ") {
            ev.preventDefault();
            openAgentDetail(agent.id);
          }
        },
      }, [
        el("td", null, [el("div", { class: "agent-name-cell" }, [
          el("strong", { text: agent.name }),
          el("span", { text: agent.description || "" }),
        ])]),
        el("td", { "data-label": "Escopo" }, [scopeChip(agent.scope)]),
        el("td", { "data-label": "Status" }, [agentStatusPill(agent.status)]),
        el("td", { class: "muted", "data-label": "Última execução", text: relativeTime(agent.last_execution_at) }),
        el("td", { "data-label": "Sucesso" }, [successMeter(agent.success_rate)]),
      ]));
    });
    table.appendChild(tbody);
    card.appendChild(el("div", { class: "table-wrap" }, [table]));
    card.appendChild(el("p", { class: "muted agent-none", id: "agent-none", hidden: "hidden", text: "Nenhum agente com esses filtros." }));
    card.appendChild(el("p", { class: "table-foot", text: "Agentes do sistema da empresa rodam isolados e só alteram dados com aprovação humana." }));
    root.appendChild(card);
  }

  // --- Detalhe do agente (painel lateral) ---------------------------------------------------

  function fmtInt(n) {
    if (n === null || n === undefined) {
      return "—";
    }
    return Number(n).toLocaleString("pt-BR");
  }

  function fmtTokensShort(n) {
    if (n === null || n === undefined) {
      return "—";
    }
    const v = Number(n);
    if (v >= 1000000) {
      return (v / 1000000).toLocaleString("pt-BR", { maximumFractionDigits: 1 }) + " mi";
    }
    if (v >= 1000) {
      return (v / 1000).toLocaleString("pt-BR", { maximumFractionDigits: 1 }) + " mil";
    }
    return v.toLocaleString("pt-BR");
  }

  function fmtUsd(n) {
    if (n === null || n === undefined) {
      return "—";
    }
    const v = Number(n);
    const digits = v > 0 && v < 1 ? 3 : 2;
    return "US$ " + v.toLocaleString("pt-BR", { minimumFractionDigits: digits, maximumFractionDigits: digits });
  }

  function fmtDuration(ms) {
    if (ms === null || ms === undefined) {
      return "—";
    }
    const sec = Number(ms) / 1000;
    if (sec < 60) {
      return sec.toLocaleString("pt-BR", { maximumFractionDigits: 1 }) + " s";
    }
    const min = Math.floor(sec / 60);
    return min + " min " + Math.round(sec - min * 60) + " s";
  }

  function scopeLabel(scope) {
    return scope === "company_system" ? "Sistema da empresa" : "Desenvolvimento";
  }

  async function openAgentDetail(id) {
    const res = await api("/api/agents/" + encodeURIComponent(id));
    if (!res.ok) {
      state.agentes.error = (res.data && res.data.error) || "error";
      render();
      return;
    }
    state.agentes.selectedId = id;
    state.agentes.selected = res.data.agent;
    state.agentes.executions = res.data.executions || [];
    state.agentes.detail = res.data;
    state.agentes.openExec = {};
    state.agentes.configForm = null;
    state.agentes.configError = "";
    render();
    if (state.agentes.detailModal) {
      state.agentes.detailModal.close();
    }
    state.agentes.detailModal = openModal({
      title: res.data.agent.name,
      subtitle: res.data.agent.description || "",
      variant: "sheet",
      build: function () {},
      onClose: function () { state.agentes.detailModal = null; },
    });
    paintAgentDetail();
  }

  function usageBar(stats) {
    const parts = [
      ["in", "Entrada", stats.input_tokens],
      ["out", "Saída", stats.output_tokens],
      ["cr", "Cache lido", stats.cache_read_tokens],
      ["cw", "Cache gravado", stats.cache_write_tokens],
    ];
    const total = parts.reduce(function (acc, p) { return acc + Number(p[2] || 0); }, 0);
    const bar = el("div", { class: "usage-bar", "aria-hidden": "true" });
    const legend = el("dl", { class: "usage-legend" });
    parts.forEach(function (p) {
      const seg = el("span", { class: "usage-seg usage-" + p[0] });
      seg.style.width = (total ? (100 * Number(p[2] || 0) / total) : 0) + "%";
      bar.appendChild(seg);
      legend.appendChild(el("div", null, [
        el("dt", null, [el("span", { class: "usage-dot usage-" + p[0], "aria-hidden": "true" }), el("span", { text: p[1] })]),
        el("dd", { text: fmtInt(p[2]) }),
      ]));
    });
    return el("div", { class: "usage-block" }, [bar, legend]);
  }

  function executionRow(execu) {
    const u = execu.usage || {};
    const open = !!(state.agentes.openExec && state.agentes.openExec[execu.id]);
    const statusMap = { ok: ["status-ok", "Sucesso"], error: ["status-danger", "Erro"], running: ["status-warn", "Rodando"] };
    const st = statusMap[execu.status] || ["status-muted", execu.status || "—"];
    const row = el("tr", {
      class: "exec-row" + (open ? " open" : ""),
      tabindex: "0",
      "aria-expanded": open ? "true" : "false",
      onClick: function () { toggleExec(execu.id); },
      onKeydown: function (ev) {
        if (ev.key === "Enter" || ev.key === " ") {
          ev.preventDefault();
          toggleExec(execu.id);
        }
      },
    }, [
      el("td", null, [
        el("span", { class: "cell-strong exec-event", text: execu.event || "—" }),
        el("span", { class: "exec-when", text: fmtDateTime(execu.started_at) }),
      ]),
      el("td", null, [el("span", { class: "status " + st[0], text: st[1] })]),
      el("td", { class: "num", text: fmtDuration(execu.duration_ms) }),
      el("td", { class: "num", title: u.total_tokens != null ? fmtInt(u.total_tokens) + " tokens" : "Motor não informou uso", text: fmtTokensShort(u.total_tokens) }),
      el("td", { class: "num", text: fmtUsd(u.cost_usd) }),
    ]);
    const rows = [row];
    if (open) {
      const detail = el("div", { class: "exec-detail" }, [
        el("dl", { class: "exec-usage" }, [
          el("div", null, [el("dt", { text: "Entrada" }), el("dd", { text: fmtInt(u.input_tokens) })]),
          el("div", null, [el("dt", { text: "Saída" }), el("dd", { text: fmtInt(u.output_tokens) })]),
          el("div", null, [el("dt", { text: "Cache lido" }), el("dd", { text: fmtInt(u.cache_read_tokens) })]),
          el("div", null, [el("dt", { text: "Cache gravado" }), el("dd", { text: fmtInt(u.cache_write_tokens) })]),
          el("div", null, [el("dt", { text: "Turnos" }), el("dd", { text: fmtInt(u.turns) })]),
          el("div", { class: "exec-only-mobile" }, [el("dt", { text: "Status · duração" }), el("dd", { text: st[1] + " · " + fmtDuration(execu.duration_ms) })]),
          el("div", null, [el("dt", { text: "Modelo" }), el("dd", { class: "mono", text: u.model || "—" })]),
        ]),
        u.total_tokens == null ? el("p", { class: "field-hint", text: "O motor não informou uso nesta execução (execução antiga, sem chamada ao motor ou motor sem esse dado)." }) : null,
        execu.log ? el("div", { class: "agent-log", text: execu.log }) : null,
      ]);
      rows.push(el("tr", { class: "exec-detail-row" }, [el("td", { colspan: "5" }, [detail])]));
    }
    return rows;
  }

  function toggleExec(id) {
    state.agentes.openExec = state.agentes.openExec || {};
    state.agentes.openExec[id] = !state.agentes.openExec[id];
    paintAgentDetail();
  }

  function paintAgentDetail() {
    const modal = state.agentes.detailModal;
    const data = state.agentes.detail;
    if (!modal || !data) {
      return;
    }
    const body = modal.body;
    body.replaceChildren();
    const agent = data.agent;
    const stats = data.stats || {};

    body.appendChild(el("div", { class: "agent-facts" }, [
      agentStatusPill(agent.status),
      scopeChip(agent.scope),
      agent.trigger ? el("span", { text: "Gatilho: " + agent.trigger }) : null,
      agent.engine ? el("span", { text: "Motor: " + agent.engine }) : null,
      el("span", { text: "Criado " + fmtDateTime(agent.created_at) }),
    ]));

    const config = agentConfigSection();
    if (config) {
      body.appendChild(config);
    }

    body.appendChild(el("div", { class: "metric-grid agent-stats" }, [
      metricCard("core", stats.executions || 0, null, "Execuções"),
      metricCard("ok", stats.success_rate == null ? "—" : stats.success_rate + "%", null, "Sucesso"),
      metricCard("core", fmtDuration(stats.avg_duration_ms), null, "Duração média"),
      metricCard("core", fmtUsd(stats.cost_usd), null, "Custo estimado total"),
    ]));

    const usageSection = el("div", { class: "agent-section" }, [
      el("div", { class: "radar-section-head" }, [
        el("h3", { text: "Consumo do motor" }),
        el("span", { class: "count", text: stats.total_tokens == null ? "sem dado" : fmtInt(stats.total_tokens) + " tokens" }),
      ]),
    ]);
    if (stats.total_tokens == null) {
      usageSection.appendChild(el("p", { class: "radar-empty", text: "Nenhuma execução deste agente informou uso do motor ainda." }));
    } else {
      usageSection.appendChild(usageBar(stats));
      usageSection.appendChild(el("dl", { class: "meta-list agent-cost" }, [
        el("dt", { text: "Média por execução" }), el("dd", { text: fmtUsd(stats.avg_cost_usd) + " · " + fmtInt(stats.executions_with_usage) + (stats.executions_with_usage === 1 ? " execução" : " execuções") + " com uso informado" }),
        el("dt", { text: "Últimos 30 dias" }), el("dd", { text: fmtUsd(stats.cost_usd_30d) + " em " + fmtInt(stats.executions_30d) + " execuções" }),
      ]));
    }
    usageSection.appendChild(el("p", { class: "field-hint", text: "Custo estimado pelo Claude Code a preço de lista da API. Com assinatura, não é cobrança por chamada; serve para comparar consumo. Cache gravado costuma pesar mais: é o contexto da CLI guardado na primeira chamada." }));
    body.appendChild(usageSection);

    const execs = data.executions || [];
    const execSection = el("div", { class: "agent-section" }, [
      el("div", { class: "radar-section-head" }, [
        el("h3", { text: "Execuções" }),
        el("span", { class: "count", text: String(execs.length) + (stats.executions > execs.length ? " de " + stats.executions : "") }),
      ]),
      el("p", { class: "radar-section-hint", text: "Clique numa execução para ver tokens por tipo, modelo e log." }),
    ]);
    if (!execs.length) {
      execSection.appendChild(el("p", { class: "radar-empty", text: "Sem execuções registradas." }));
    } else {
      const table = el("table", { class: "exec-table" });
      table.appendChild(el("thead", null, [el("tr", null, [
        el("th", { text: "Execução" }),
        el("th", { text: "Status" }),
        el("th", { class: "num", text: "Duração" }),
        el("th", { class: "num", text: "Tokens" }),
        el("th", { class: "num", text: "Custo" }),
      ])]));
      const tbody = el("tbody");
      execs.forEach(function (execu) {
        executionRow(execu).forEach(function (tr) { tbody.appendChild(tr); });
      });
      table.appendChild(tbody);
      execSection.appendChild(el("div", { class: "exec-table-wrap" }, [table]));
    }
    body.appendChild(execSection);

    const perms = el("div", { class: "agent-section" });
    renderPermissions(perms);
    if (perms.firstChild) {
      perms.firstChild.className = "";
      perms.replaceChild(el("div", { class: "radar-section-head" }, [el("h3", { text: "Permissões" })]), perms.firstChild);
      body.appendChild(perms);
    }

    const approvals = data.approvals || [];
    if (approvals.length) {
      const list = el("div", { class: "agent-section" }, [
        el("div", { class: "radar-section-head" }, [el("h3", { text: "Aprovações" }), el("span", { class: "count", text: String(approvals.length) })]),
      ]);
      approvals.forEach(function (ap) {
        const map = { pending: ["status-warn", "Pendente"], approved: ["status-ok", "Aprovada"], rejected: ["status-danger", "Recusada"] };
        const st = map[ap.status] || ["status-muted", ap.status];
        list.appendChild(el("div", { class: "approval-item" }, [
          el("div", { class: "approval-info" }, [
            el("strong", { text: ap.action === "write_access" ? "Acesso de escrita" : ap.action }),
            el("span", { text: "Pedida " + fmtDateTime(ap.requested_at) + (ap.decided_at ? " · decidida " + fmtDateTime(ap.decided_at) : "") }),
          ]),
          el("span", { class: "status " + st[0], text: st[1] }),
        ]));
      });
      body.appendChild(list);
    }
  }

  function renderSelectedAgent(root) {
    const agent = state.agentes.selected;
    const card = el("section", { class: "card" });
    if (!agent) {
      card.appendChild(cardHead("Detalhe"));
      card.appendChild(el("p", { class: "muted", text: "Selecione um agente na lista." }));
      root.appendChild(card);
      return;
    }
    card.appendChild(el("div", { class: "selected-agent-head" }, [
      el("strong", { text: agent.name }),
      agentStatusPill(agent.status),
      el("button", {
        type: "button",
        class: "sm quiet selected-agent-more",
        text: "Ver detalhes",
        onClick: function () { openAgentDetail(agent.id); },
      }),
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
        el("span", { class: "exec-dot exec-dot-" + (execu.status || "running"), "aria-hidden": "true" }),
        el("span", { text: execu.event || execu.status }),
        el("span", { class: "exec-time", text: relativeTime(execu.started_at) }),
      ]));
    });
    card.appendChild(execList);
    const lastLog = state.agentes.executions.length ? state.agentes.executions[0].log : "";
    if (lastLog) {
      card.appendChild(el("div", { class: "agent-log", text: lastLog }));
    }
    renderPermissions(card);
    root.appendChild(card);
  }

  function renderApprovals(root, approvals) {
    const pending = (approvals || state.agentes.approvals).filter(function (a) { return a.status === "pending"; });
    const card = el("section", { class: "card" }, [
      cardHead("Aprovações pendentes", [countLabel(pending.length)]),
    ]);
    if (state.agentes.error) {
      card.appendChild(el("p", { class: "banner banner-error", text: errorMessage(state.agentes.error) }));
    }
    if (!pending.length) {
      card.appendChild(el("p", { class: "muted", text: "Nada aguardando decisão." }));
      root.appendChild(card);
      return;
    }
    pending.forEach(function (item) {
      card.appendChild(el("div", { class: "approval-item" }, [
        el("div", { class: "approval-info" }, [
          el("strong", { text: item.action === "write_access" ? "Acesso de escrita" : item.agent_name }),
          el("span", { text: item.agent_name + " · " + relativeTime(item.requested_at) }),
        ]),
        el("div", { class: "approval-actions" }, [
          el("button", {
            type: "button", class: "sm", text: "Recusar",
            disabled: state.agentes.busy ? "disabled" : null,
            onClick: function () { decideApproval(item.id, "reject"); },
          }),
          el("button", {
            type: "button", class: "primary sm", text: "Aprovar",
            disabled: state.agentes.busy ? "disabled" : null,
            onClick: function () { decideApproval(item.id, "approve"); },
          }),
        ]),
      ]));
    });
    root.appendChild(card);
  }

  function renderPermissions(root) {
    const agent = state.agentes.selected;
    if (!agent) {
      return;
    }
    root.appendChild(el("p", { class: "teia-k", text: "Permissões" }));
    const perms = agent.permissions || { read: [], write: [], denied: [] };
    const rows = [
      ["read", "Pode ler", perms.read],
      ["write", "Pode alterar", perms.write],
      ["denied", "Sem acesso", perms.denied],
    ];
    rows.forEach(function (row) {
      root.appendChild(el("div", { class: "permission-row" }, [
        el("strong", null, [
          el("span", { class: "permission-dot permission-dot-" + row[0], "aria-hidden": "true" }),
          el("span", { text: row[1] }),
        ]),
        el("span", { text: (row[2] && row[2].length) ? row[2].join(", ") : "—" }),
      ]));
    });
  }

  function renderAgentes(root) {
    const canCreate = canEditNotes();
    const sector = routeSector();
    const isDev = sector === "desenvolvimento";
    root.appendChild(pageHeader(
      isDev ? "Agentes" : "Agentes · " + window.ForgeNav.areaLabel(route().area),
      isDev
        ? "Agentes que trabalham no desenvolvimento e no sistema da empresa, com permissões explícitas e aprovação humana para escrita."
        : "Os agentes deste setor ainda estão no plano. Abra um para ver o que ele vai fazer.",
      canCreate && isDev ? [el("button", {
        type: "button", class: "primary", text: "Novo agente",
        onClick: function () { openNewAgentModal(); },
      })] : null,
    ));
    if (!canCreate) {
      root.appendChild(el("p", { class: "banner banner-warn", text: "Só editor ou owner vê a aba Agentes." }));
      return;
    }
    if (state.agentes.notice) {
      showToast(state.agentes.notice);
      state.agentes.notice = "";
    }
    const items = state.agentes.items.filter(function (agent) { return agentSector(agent) === sector; });
    if (isDev) {
      renderAgentMetrics(root);
    }
    root.appendChild(agentFilters(sector));
    const left = el("div", null, []);
    renderAgentsTable(left, items);
    const ids = {};
    items.forEach(function (agent) { ids[agent.id] = true; });
    const approvals = state.agentes.approvals.filter(function (a) { return ids[a.agent_id]; });
    if (isDev || approvals.length) {
      const right = el("div", { class: "agents-right" }, []);
      renderApprovals(right, approvals);
      renderSelectedAgent(right);
      root.appendChild(el("div", { class: "agents-layout" }, [left, right]));
    } else {
      root.appendChild(left);
    }
    root.appendChild(plannedAgentsCard(sector));
    applyAgentFilter();
  }

  // Setor do agente. Até a coluna própria (Fase 1), todo agente cadastrado é de Desenvolvimento.
  function agentSector(agent) {
    return agent.sector || "desenvolvimento";
  }

  function agentFilters(sector) {
    const f = state.agentes.filter;
    const sectorSel = el("select", {
      id: "agent-filter-sector",
      onChange: function (ev) {
        const area = window.ForgeNav.areaOfSector(ev.target.value);
        if (area) {
          window.location.hash = area + "/agentes";
        }
      },
    }, window.ForgeNav.areas().map(function (a) {
      return el("option", { value: a.sector, selected: a.sector === sector ? "selected" : null, text: a.label });
    }));
    const statusSel = el("select", {
      id: "agent-filter-status",
      onChange: function (ev) {
        f.status = ev.target.value;
        applyAgentFilter();
      },
    }, [["", "Todos"], ["active", "Ativo"], ["paused", "Pausado"], ["error", "Com erro"]].map(function (opt) {
      return el("option", { value: opt[0], selected: f.status === opt[0] ? "selected" : null, text: opt[1] });
    }));
    const query = el("input", {
      id: "agent-filter-query",
      type: "search",
      placeholder: "Nome ou descrição",
      value: f.query,
      autocomplete: "off",
      onInput: function (ev) {
        f.query = ev.target.value;
        applyAgentFilter();
      },
    });
    return el("div", { class: "filter-bar", role: "search", "aria-label": "Filtrar agentes" }, [
      el("div", { class: "filter-field" }, [el("label", { for: "agent-filter-sector", text: "Setor" }), sectorSel]),
      el("div", { class: "filter-field" }, [el("label", { for: "agent-filter-status", text: "Status" }), statusSel]),
      el("div", { class: "filter-field filter-grow" }, [el("label", { for: "agent-filter-query", text: "Buscar" }), query]),
    ]);
  }

  // Filtra no DOM, sem re-render: a busca não perde o foco a cada tecla.
  function applyAgentFilter() {
    const f = state.agentes.filter;
    const q = f.query.trim().toLocaleLowerCase("pt-BR");
    let shown = 0;
    let total = 0;
    document.querySelectorAll("[data-agent-row]").forEach(function (row) {
      total += 1;
      const okStatus = !f.status || row.getAttribute("data-status") === f.status;
      const okQuery = !q || (row.getAttribute("data-search") || "").indexOf(q) !== -1;
      row.hidden = !(okStatus && okQuery);
      if (!row.hidden) {
        shown += 1;
      }
    });
    document.querySelectorAll("[data-planned-row]").forEach(function (row) {
      row.hidden = !!q && (row.getAttribute("data-search") || "").indexOf(q) === -1;
    });
    const count = document.getElementById("agent-count");
    if (count) {
      count.textContent = shown === total ? String(total) : shown + " de " + total;
    }
    const none = document.getElementById("agent-none");
    if (none) {
      none.hidden = shown > 0 || total === 0;
    }
  }

  function engineLabel(code) {
    const cat = state.areas.catalog;
    return (cat && cat.engines && cat.engines[code]) || code;
  }

  function plannedFor(ids) {
    const cat = state.areas.catalog;
    if (!cat) {
      return [];
    }
    return ids.map(function (id) {
      return cat.planned.find(function (a) { return a.id === id; });
    }).filter(Boolean);
  }

  function plannedAgentsCard(sector) {
    const card = el("section", { class: "card" }, [cardHead("Planejados")]);
    const cat = state.areas.catalog;
    if (!cat) {
      card.appendChild(el("p", { class: "muted", text: state.areas.error ? "Não foi possível carregar o catálogo." : "Carregando o catálogo…" }));
      return card;
    }
    const own = cat.planned.filter(function (a) { return a.sector === sector; });
    const common = cat.planned.filter(function (a) { return a.sector === cat.common; });
    card.appendChild(plannedList(own));
    if (common.length) {
      card.appendChild(el("p", { class: "teia-k planned-sub", text: "Comuns a todos os setores" }));
      card.appendChild(plannedList(common));
    }
    return card;
  }

  function plannedList(agents) {
    return el("ul", { class: "planned-list" }, agents.map(function (agent) {
      const search = (agent.name + " " + agent.summary).toLocaleLowerCase("pt-BR");
      return el("li", { "data-planned-row": "", "data-search": search }, [el("button", {
        type: "button",
        class: "planned-row",
        onClick: function () { openPlannedAgent(agent); },
      }, [
        el("span", { class: "planned-main" }, [
          el("strong", { text: agent.name }),
          el("span", { class: "muted", text: agent.summary }),
        ]),
        el("span", { class: "planned-meta" }, [
          el("span", { text: agent.trigger }),
          el("span", { text: engineLabel(agent.engine) }),
          el("span", { class: "pill pill-outline", text: "Fase " + agent.phase }),
        ]),
      ])]);
    }));
  }

  function sectorLabel(sector) {
    const cat = state.areas.catalog;
    if (cat && sector === cat.common) {
      return "Comum a todos os setores";
    }
    const area = window.ForgeNav.areaOfSector(sector);
    return area ? window.ForgeNav.areaLabel(area) : sector;
  }

  function openPlannedAgent(agent) {
    state.areas.modal = openModal({
      onClose: function () { state.areas.modal = null; },
      title: agent.name,
      subtitle: sectorLabel(agent.sector) + " · planejado",
      variant: "sheet",
      build: function (body) {
        body.appendChild(el("p", { class: "planned-desc", text: agent.description }));
        body.appendChild(el("dl", { class: "meta-list" }, [
          el("dt", { text: "Gatilho" }), el("dd", { text: agent.trigger }),
          el("dt", { text: "Motor" }), el("dd", { text: engineLabel(agent.engine) }),
          el("dt", { text: "Escreve fora do Forge" }), el("dd", { text: agent.writes }),
          el("dt", { text: "Previsto para" }), el("dd", { text: "Fase " + agent.phase + " do plano mestre" }),
        ]));
        body.appendChild(el("p", { class: "muted planned-note", text: "Toda escrita fora do Forge passa por aprovação humana. O resultado fica registrado com tokens e custo." }));
      },
    });
  }

  // --- Telas "em breve" ---------------------------------------------------------------------
  function renderSoon(root) {
    const r = route();
    const sector = routeSector();
    const cat = state.areas.catalog;
    const info = cat ? cat.tabs.find(function (t) { return t.sector === sector && t.id === r.tab; }) : null;
    root.appendChild(pageHeader(r.item.label, window.ForgeNav.areaLabel(r.area), [
      el("span", { class: "pill pill-outline", text: info ? "Em breve · Fase " + info.phase : "Em breve" }),
    ]));
    const card = el("section", { class: "card soon-card" });
    if (!cat) {
      card.appendChild(el("p", { class: "muted", text: state.areas.error ? "Não foi possível carregar o catálogo." : "Carregando…" }));
      root.appendChild(card);
      return;
    }
    card.appendChild(el("p", { class: "soon-lead", text: info ? info.summary : "Esta tela ainda não tem conteúdo." }));
    const agents = info ? plannedFor(info.agents || []) : [];
    if (agents.length) {
      card.appendChild(el("p", { class: "teia-k planned-sub", text: "Agentes planejados para esta tela" }));
      card.appendChild(plannedList(agents));
    }
    root.appendChild(card);
  }

  // --- Configurações ------------------------------------------------------------------------
  const CONFIG_SECTIONS = [
    ["conta", "Conta"],
    ["lembretes", "Lembretes"],
    ["usuarios", "Usuários e permissões"],
    ["ia", "IA e custos"],
    ["aparencia", "Aparência"],
  ];

  function settingRow(title, desc, control) {
    return el("div", { class: "setting-row" }, [
      el("div", { class: "setting-text" }, [
        el("strong", { text: title }),
        desc ? el("span", { class: "muted", text: desc }) : null,
      ]),
      el("div", { class: "setting-control" }, [control]),
    ]);
  }

  function soonButton(label, phase) {
    return el("button", { type: "button", disabled: "disabled", title: "Disponível na Fase " + phase, text: label });
  }

  function soonNote(phase, text) {
    return el("p", { class: "setting-note", text: (text ? text + " " : "") + "Disponível na Fase " + phase + "." });
  }

  function renderConfig(root) {
    const current = route().tab;
    root.appendChild(pageHeader("Configurações", "Conta, lembretes, usuários, IA e aparência."));
    const menu = el("nav", { class: "settings-menu", "aria-label": "Seções de configurações" }, CONFIG_SECTIONS.map(function (sec) {
      return el("a", {
        href: "#configuracoes/" + sec[0],
        class: "settings-link" + (sec[0] === current ? " current" : ""),
        "aria-current": sec[0] === current ? "page" : null,
        text: sec[1],
      });
    }));
    const body = el("section", { class: "card settings-body" });
    const label = (CONFIG_SECTIONS.find(function (sec) { return sec[0] === current; }) || CONFIG_SECTIONS[0])[1];
    body.appendChild(cardHead(label));
    if (current === "conta") {
      const who = state.who || {};
      body.appendChild(settingRow("Identidade", "Hoje o acesso é pela conta do GitHub.", el("span", { class: "mono", text: who.login || "—" })));
      body.appendChild(settingRow("Senha", "Login próprio com e-mail e senha.", soonButton("Trocar senha", 2)));
      body.appendChild(settingRow("Verificação em duas etapas", "Código de um app autenticador a cada login.", soonButton("Ativar", 2)));
      body.appendChild(settingRow("Sessões ativas", "Ver e encerrar sessões abertas em outros navegadores.", soonButton("Ver sessões", 2)));
      body.appendChild(soonNote(2, "Senha, verificação em duas etapas e sessões chegam com o login próprio."));
    } else if (current === "lembretes") {
      [["Prazos e vencimentos", "Aviso antes de um prazo ou conta vencer."],
        ["Resumo do dia", "Um resumo curto pela manhã."],
        ["Aprovações pendentes", "Quando um agente pede aprovação."]].forEach(function (row) {
        body.appendChild(settingRow(row[0], row[1], el("input", { type: "checkbox", disabled: "disabled", "aria-label": row[0] })));
      });
      body.appendChild(soonNote(5, "Os avisos chegam no sistema e, se você quiser, por e-mail."));
    } else if (current === "usuarios") {
      if (!isOwner()) {
        body.appendChild(el("p", { class: "muted", text: "Só master gerencia usuários e permissões." }));
      } else {
        const roles = (state.who && state.who.roles) || [];
        body.appendChild(settingRow("Seus papéis", "Hoje os papéis são concedidos pela linha de comando.", el("span", { text: roles.join(", ") || "—" })));
        body.appendChild(settingRow("Convidar pessoa", "Convite por e-mail, com papel e setores.", soonButton("Convidar", 2)));
        body.appendChild(settingRow("Setores", "Desenvolvimento, Jurídico e Financeiro: cada pessoa vê os seus.", soonButton("Gerenciar", 2)));
      }
    } else if (current === "ia") {
      body.appendChild(settingRow("Motor e agenda", "Ficam na configuração de cada agente.", el("a", { href: "#dev/agentes", text: "Abrir Agentes" })));
      body.appendChild(settingRow("Tetos de custo", "Limite por execução, por agente por dia e por mês.", soonButton("Definir", 1)));
      body.appendChild(settingRow("Consumo do mês", "Tokens e custo somados de todos os agentes.", soonButton("Ver", 1)));
    } else {
      body.appendChild(settingRow("Tema", "Claro, escuro ou igual ao do sistema.", themeChoice()));
    }
    root.appendChild(el("div", { class: "settings-layout" }, [menu, body]));
  }

  function themeChoice() {
    const current = window.ForgeTheme ? window.ForgeTheme.preference() : "system";
    const options = [["light", "Claro"], ["dark", "Escuro"], ["system", "Sistema"]];
    const group = el("div", { class: "segmented segmented-compact", role: "radiogroup", "aria-label": "Tema" });
    options.forEach(function (opt) {
      const active = current === opt[0];
      group.appendChild(el("button", {
        type: "button",
        role: "radio",
        "aria-checked": active ? "true" : "false",
        class: "segmented-option" + (active ? " active" : ""),
        onClick: function () {
          if (window.ForgeTheme) {
            window.ForgeTheme.set(opt[0]);
          }
          render({ keepState: true });
        },
      }, [el("span", { class: "segmented-title", text: opt[1] })]));
    });
    return group;
  }

  function render(opts) {
    if (!(opts && opts.keepState)) {
      snapshotForm();
    }
    const session = document.getElementById("session");
    const app = document.getElementById("app");
    renderSession(session);
    renderNav();
    app.replaceChildren();
    const teiaOpen = !state.loading && !!state.who && activeTab() === "teia";
    const investOpen = !state.loading && !!state.who && activeTab() === "investigacao";
    app.classList.toggle("teia-layout", teiaOpen);
    app.classList.toggle("investigacao-layout", investOpen);
    document.body.classList.toggle("teia-open", teiaOpen);
    if (!teiaOpen) {
      state.teiaFull = false;
    }
    document.body.classList.toggle("teia-full", teiaOpen && state.teiaFull);
    if (state.loading) {
      setPageTitle("Forge");
      app.appendChild(stateCard("loading", "Carregando…"));
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
      setPageTitle(route().area === "dev" ? "Agentes" : "Agentes · " + window.ForgeNav.areaLabel(route().area));
      renderAgentes(app);
      return;
    }
    if (tab === "soon") {
      setPageTitle(route().item.label);
      renderSoon(app);
      return;
    }
    if (tab === "config") {
      setPageTitle("Configurações");
      renderConfig(app);
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
      await loadEditorAndTab();
    } catch (err) {
      state.error = "api_unreachable";
      state.loading = false;
      render();
    }
  }

  document.addEventListener("keydown", function (ev) {
    if (ev.key !== "Escape" || !state.teiaFull || document.querySelector(".modal-overlay")) {
      return;
    }
    setTeiaFull(false);
  });

  window.addEventListener("hashchange", async function () {
    [state.agentes.detailModal, state.radar.modal, state.ai.modal, state.areas.modal].forEach(function (modal) {
      if (modal) {
        modal.close();
      }
    });
    state.error = "";
    state.errorDetail = null;
    redirectLegacyHash();
    render();
    await loadForTab();
  });
  redirectLegacyHash();
  boot();
})();
