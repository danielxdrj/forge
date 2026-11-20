// Navegação por área (PLANO_MESTRE, seção 3). Compartilhada por index.html e conexoes.html.
(function (global) {
  "use strict";

  // Ícones de traço 16px, no estilo dos já usados na sidebar: [tag, atributos] por forma.
  var ICONS = {
    tasks: [["rect", { x: 2.5, y: 2.5, width: 11, height: 11, rx: 2 }], ["path", { d: "M5 8.2l2 2 4-4.2" }]],
    search: [["circle", { cx: 7, cy: 7, r: 4.2 }], ["path", { d: "M10.4 10.4L14 14" }]],
    graph: [
      ["circle", { cx: 8, cy: 3.5, r: 1.6 }], ["circle", { cx: 3.5, cy: 12.2, r: 1.6 }],
      ["circle", { cx: 12.5, cy: 12.2, r: 1.6 }], ["path", { d: "M7.2 4.8L4.6 10.6M8.8 4.8l2.6 5.8M5.2 12.2h5.6" }],
    ],
    plug: [["path", { d: "M6 2.5v3.5M10 2.5v3.5M4.5 6h7v2.4a3.5 3.5 0 01-7 0V6zM8 12.2V14" }]],
    bot: [["rect", { x: 3, y: 4.5, width: 10, height: 8, rx: 2 }], ["path", { d: "M6 4.5V3M10 4.5V3M5.5 8h.01M10.5 8h.01M6 10.5h4" }]],
    mail: [["rect", { x: 2, y: 3.5, width: 12, height: 9, rx: 1.5 }], ["path", { d: "M2.6 4.6L8 8.8l5.4-4.2" }]],
    note: [["path", { d: "M4 2.5h5.5L12 5v8.5H4zM9.5 2.5V5H12M6 8.2h4M6 10.7h3" }]],
    scale: [["path", { d: "M8 2.5v11M5 13.5h6M3.5 4.5h9M3.5 4.5L2 8.5h3zM12.5 4.5L11 8.5h3z" }]],
    calendar: [["rect", { x: 2.5, y: 3.5, width: 11, height: 10, rx: 1.5 }], ["path", { d: "M2.5 6.5h11M5.5 2v3M10.5 2v3" }]],
    wallet: [["rect", { x: 2, y: 4, width: 12, height: 8.5, rx: 1.5 }], ["path", { d: "M2 6.5h12M10.5 9.5h1.5" }]],
    chart: [["path", { d: "M2.5 13.5h11M4.5 11V8M8 11V4.5M11.5 11V6.5" }]],
    gear: [
      ["circle", { cx: 8, cy: 8, r: 2.2 }],
      ["path", { d: "M8 1.8v1.7M8 12.5v1.7M1.8 8h1.7M12.5 8h1.7M3.6 3.6l1.2 1.2M11.2 11.2l1.2 1.2M12.4 3.6l-1.2 1.2M4.8 11.2l-1.2 1.2" }],
    ],
    chevron: [["path", { d: "M6 4l4 4-4 4" }]],
  };
  var SVG_NS = "http://www.w3.org/2000/svg";

  // access: "all" (logado), "reader" (editor ou owner), "owner".
  var AREAS = [
    {
      id: "dev", sector: "desenvolvimento", label: "Desenvolvimento",
      items: [
        { tab: "tarefas", label: "Tarefas", icon: "tasks", access: "all" },
        { tab: "investigacao", label: "Investigação", icon: "search", access: "all" },
        { tab: "teia", label: "Teia de contexto", icon: "graph", access: "all" },
        { tab: "conexoes", label: "Conexões", icon: "plug", access: "owner", href: "/conexoes" },
        { tab: "agentes", label: "Agentes", icon: "bot", access: "reader" },
        { tab: "email", label: "E-mail", icon: "mail", access: "reader", soon: true },
        { tab: "notas", label: "Notas", icon: "note", access: "reader", soon: true },
      ],
    },
    {
      id: "juridico", sector: "juridico", label: "Jurídico",
      items: [
        { tab: "agentes", label: "Agentes", icon: "bot", access: "reader" },
        { tab: "pecas", label: "Peças", icon: "scale", access: "reader", soon: true },
        { tab: "prazos", label: "Prazos", icon: "calendar", access: "reader", soon: true },
        { tab: "email", label: "E-mail", icon: "mail", access: "reader", soon: true },
        { tab: "notas", label: "Notas", icon: "note", access: "reader", soon: true },
      ],
    },
    {
      id: "financeiro", sector: "financeiro", label: "Financeiro",
      items: [
        { tab: "agentes", label: "Agentes", icon: "bot", access: "reader" },
        { tab: "contas", label: "Contas", icon: "wallet", access: "reader", soon: true },
        { tab: "relatorios", label: "Relatórios", icon: "chart", access: "reader", soon: true },
        { tab: "email", label: "E-mail", icon: "mail", access: "reader", soon: true },
        { tab: "notas", label: "Notas", icon: "note", access: "reader", soon: true },
      ],
    },
  ];
  var CONFIG = { id: "configuracoes", label: "Configurações", icon: "gear", tab: "conta" };
  var CONFIG_TABS = ["conta", "lembretes", "usuarios", "ia", "aparencia"];

  // Hashes antigos (antes das áreas) continuam funcionando.
  var LEGACY = {
    "": "dev/tarefas",
    tarefas: "dev/tarefas",
    investigacao: "dev/investigacao",
    teia: "dev/teia",
    agentes: "dev/agentes",
  };
  var DEFAULT = "dev/tarefas";
  var COLLAPSE_KEY = "forge-nav-collapsed";

  function areaById(id) {
    for (var i = 0; i < AREAS.length; i += 1) {
      if (AREAS[i].id === id) {
        return AREAS[i];
      }
    }
    return null;
  }

  function itemOf(area, tab) {
    for (var i = 0; i < area.items.length; i += 1) {
      if (area.items[i].tab === tab) {
        return area.items[i];
      }
    }
    return null;
  }

  // Devolve { key, area, tab, item } para um hash qualquer; desconhecido vira a rota padrão.
  function parse(hash) {
    var raw = String(hash || "").replace(/^#/, "");
    if (Object.prototype.hasOwnProperty.call(LEGACY, raw)) {
      raw = LEGACY[raw];
    }
    var parts = raw.split("/");
    if (parts[0] === CONFIG.id) {
      var ctab = CONFIG_TABS.indexOf(parts[1]) >= 0 ? parts[1] : CONFIG.tab;
      return { key: CONFIG.id + "/" + ctab, area: CONFIG.id, tab: ctab, item: null };
    }
    var area = areaById(parts[0]);
    var item = area ? itemOf(area, parts[1]) : null;
    if (!area || !item || item.href) {
      return parse(DEFAULT);
    }
    return { key: area.id + "/" + item.tab, area: area.id, tab: item.tab, item: item };
  }

  function hrefOf(area, item) {
    return item.href || "/#" + area.id + "/" + item.tab;
  }

  function allowed(item, access) {
    if (!access.loggedIn) {
      return false;
    }
    if (item.access === "owner") {
      return !!access.owner;
    }
    if (item.access === "reader") {
      return !!access.reader;
    }
    return true;
  }

  function readCollapsed() {
    try {
      var value = JSON.parse(global.localStorage.getItem(COLLAPSE_KEY) || "{}");
      return value && typeof value === "object" ? value : {};
    } catch (err) {
      return {};
    }
  }

  function writeCollapsed(value) {
    try {
      global.localStorage.setItem(COLLAPSE_KEY, JSON.stringify(value));
    } catch (err) {
      /* modo privado: só não lembra */
    }
  }

  function icon(name) {
    var span = document.createElement("span");
    span.className = "nav-icon";
    span.setAttribute("aria-hidden", "true");
    var svg = document.createElementNS(SVG_NS, "svg");
    var base = {
      viewBox: "0 0 16 16", width: 14, height: 14, fill: "none", stroke: "currentColor",
      "stroke-width": 1.5, "stroke-linecap": "round", "stroke-linejoin": "round",
    };
    Object.keys(base).forEach(function (key) { svg.setAttribute(key, String(base[key])); });
    (ICONS[name] || []).forEach(function (shape) {
      var node = document.createElementNS(SVG_NS, shape[0]);
      Object.keys(shape[1]).forEach(function (key) { node.setAttribute(key, String(shape[1][key])); });
      svg.appendChild(node);
    });
    span.appendChild(svg);
    return span;
  }

  function link(href, label, iconName, current, soon) {
    var a = document.createElement("a");
    a.href = href;
    a.className = "nav-item" + (current ? " current" : "") + (soon ? " nav-soon" : "");
    if (current) {
      a.setAttribute("aria-current", "page");
    }
    a.appendChild(icon(iconName));
    var text = document.createElement("span");
    text.textContent = label;
    a.appendChild(text);
    if (soon) {
      var tag = document.createElement("span");
      tag.className = "nav-soon-tag";
      tag.textContent = "em breve";
      a.appendChild(tag);
      a.title = label + " (em breve)";
    }
    return a;
  }

  // Seletor de área para telas estreitas (≤960px), onde a sidebar vira barra no topo.
  function areaSelect(visibleAreas, currentArea) {
    var select = document.createElement("select");
    select.className = "nav-area-select";
    select.setAttribute("aria-label", "Área");
    visibleAreas.forEach(function (entry) {
      var opt = document.createElement("option");
      opt.value = entry.href;
      opt.textContent = entry.label;
      opt.selected = entry.id === currentArea;
      select.appendChild(opt);
    });
    select.addEventListener("change", function () {
      global.location.href = select.value;
    });
    return select;
  }

  // Desenha a navegação em `nav`. current: chave "area/aba" (ex.: "dev/conexoes").
  function render(nav, current, access) {
    if (!nav) {
      return;
    }
    var parsed = String(current || "");
    var currentArea = parsed.split("/")[0];
    var collapsed = readCollapsed();
    var frag = document.createDocumentFragment();
    var visibleAreas = [];

    AREAS.forEach(function (area) {
      var items = area.items.filter(function (item) { return allowed(item, access); });
      if (!items.length) {
        return;
      }
      visibleAreas.push({ id: area.id, label: area.label, href: hrefOf(area, items[0]) });
      var isCurrent = area.id === currentArea;
      var open = isCurrent || !collapsed[area.id];
      var group = document.createElement("div");
      group.className = "nav-group" + (isCurrent ? " is-current" : "") + (open ? " is-open" : "");
      var head = document.createElement("button");
      head.type = "button";
      head.className = "nav-group-head";
      head.setAttribute("aria-expanded", open ? "true" : "false");
      var label = document.createElement("span");
      label.textContent = area.label;
      head.appendChild(label);
      var chev = icon("chevron");
      chev.className = "nav-group-chev";
      head.appendChild(chev);
      var list = document.createElement("div");
      list.className = "nav-group-items";
      list.id = "nav-group-" + area.id;
      head.setAttribute("aria-controls", list.id);
      head.addEventListener("click", function () {
        var nowOpen = !group.classList.contains("is-open");
        group.classList.toggle("is-open", nowOpen);
        head.setAttribute("aria-expanded", nowOpen ? "true" : "false");
        var state = readCollapsed();
        if (nowOpen) {
          delete state[area.id];
        } else {
          state[area.id] = true;
        }
        writeCollapsed(state);
      });
      items.forEach(function (item) {
        var key = area.id + "/" + item.tab;
        list.appendChild(link(hrefOf(area, item), item.label, item.icon, key === parsed, !!item.soon));
      });
      group.appendChild(head);
      group.appendChild(list);
      frag.appendChild(group);
    });

    if (access.loggedIn) {
      var cfgHref = "/#" + CONFIG.id + "/" + CONFIG.tab;
      visibleAreas.push({ id: CONFIG.id, label: CONFIG.label, href: cfgHref });
      var cfg = document.createElement("div");
      cfg.className = "nav-group nav-group-config" + (currentArea === CONFIG.id ? " is-current is-open" : " is-open");
      var cfgList = document.createElement("div");
      cfgList.className = "nav-group-items";
      cfgList.appendChild(link(cfgHref, CONFIG.label, CONFIG.icon, currentArea === CONFIG.id, false));
      cfg.appendChild(cfgList);
      frag.appendChild(cfg);
      if (visibleAreas.length > 1) {
        frag.insertBefore(areaSelect(visibleAreas, currentArea), frag.firstChild);
      }
    }
    nav.replaceChildren(frag);
  }

  function areaLabel(id) {
    if (id === CONFIG.id) {
      return CONFIG.label;
    }
    var area = areaById(id);
    return area ? area.label : "";
  }

  function sectorOf(id) {
    var area = areaById(id);
    return area ? area.sector : "";
  }

  function areaOfSector(sector) {
    for (var i = 0; i < AREAS.length; i += 1) {
      if (AREAS[i].sector === sector) {
        return AREAS[i].id;
      }
    }
    return "";
  }

  global.ForgeNav = {
    parse: parse,
    render: render,
    areaLabel: areaLabel,
    sectorOf: sectorOf,
    areaOfSector: areaOfSector,
    areas: function () {
      return AREAS.map(function (a) { return { id: a.id, sector: a.sector, label: a.label }; });
    },
    legacy: LEGACY,
  };
})(window);
