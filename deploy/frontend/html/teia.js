(function (global) {
  "use strict";

  const COLORS = {
    issue: "#E35A5A",
    pr: "#8FBF9A",
    note: "#C4A484",
    vault: "#D0D0D0",
    file: "#D4B46A",
    module: "#D4A0A8",
    class: "#E38A8A",
    function: "#E8C989",
  };
  const BG = "#0E0E10";
  const EDGE = "rgba(180,180,186,0.22)";
  const EDGE_DIM = "rgba(180,180,186,0.05)";
  const EDGE_HOT = "rgba(227,90,90,0.45)";
  const LABEL = "rgba(244,244,244,0.94)";
  const HALO = "rgba(10,10,12,0.88)";
  const WINE = "#990000";
  const MIN_K = 0.08;
  const MAX_K = 8;
  const ZOOM_LABELS = 1.35;

  function colorOf(type) {
    return COLORS[type] || "#B0B0B0";
  }

  function clamp(v, lo, hi) {
    return Math.max(lo, Math.min(hi, v));
  }

  function uniqueRepos(nodes) {
    const seen = {};
    const out = [];
    nodes.forEach(function (n) {
      const repo = n.repo || "";
      if (!seen[repo]) {
        seen[repo] = true;
        out.push(repo);
      }
    });
    out.sort();
    return out;
  }

  function degreeMap(nodes, edges) {
    const deg = {};
    nodes.forEach(function (n) { deg[n.id] = 0; });
    edges.forEach(function (e) {
      if (deg[e.source] !== undefined) { deg[e.source] += 1; }
      if (deg[e.target] !== undefined) { deg[e.target] += 1; }
    });
    return deg;
  }

  function adjacency(edges) {
    const adj = {};
    function add(a, b) {
      if (!adj[a]) { adj[a] = {}; }
      adj[a][b] = true;
    }
    edges.forEach(function (e) {
      add(e.source, e.target);
      add(e.target, e.source);
    });
    return adj;
  }

  function create(canvas, options) {
    const opts = options || {};
    const onSelect = typeof opts.onSelect === "function" ? opts.onSelect : function () {};
    const ctx = canvas.getContext("2d");
    const cam = { x: 0, y: 0, k: 1 };
    let dpr = 1;
    let cssW = 0;
    let cssH = 0;
    let nodes = [];
    let links = [];
    let adj = {};
    let sim = null;
    let selectedId = null;
    let hoverId = null;
    let hubIds = {};
    let frame = 0;
    let running = false;
    let interacting = false;
    let fitOnce = false;
    let drag = null;
    let moved = false;
    const prevPos = {};

    function kick() {
      if (frame) {
        return;
      }
      frame = global.requestAnimationFrame(function () {
        frame = 0;
        draw();
        if (running || interacting) {
          kick();
        }
      });
    }

    function resize() {
      const rect = canvas.getBoundingClientRect();
      cssW = Math.max(1, rect.width);
      cssH = Math.max(1, rect.height);
      dpr = global.devicePixelRatio || 1;
      const pw = Math.max(1, Math.floor(cssW * dpr));
      const ph = Math.max(1, Math.floor(cssH * dpr));
      if (canvas.width !== pw) {
        canvas.width = pw;
      }
      if (canvas.height !== ph) {
        canvas.height = ph;
      }
      kick();
    }

    function toWorld(clientX, clientY) {
      const rect = canvas.getBoundingClientRect();
      return {
        x: (clientX - rect.left - cam.x) / cam.k,
        y: (clientY - rect.top - cam.y) / cam.k,
      };
    }

    function hitNode(wx, wy) {
      let best = null;
      let bestD = Infinity;
      for (let i = nodes.length - 1; i >= 0; i -= 1) {
        const n = nodes[i];
        const dx = wx - n.x;
        const dy = wy - n.y;
        const r = n.r + 4 / cam.k;
        const d2 = dx * dx + dy * dy;
        if (d2 <= r * r && d2 < bestD) {
          best = n;
          bestD = d2;
        }
      }
      return best;
    }

    function zoomToFit() {
      if (!nodes.length || cssW < 2 || cssH < 2) {
        return;
      }
      let minX = Infinity;
      let minY = Infinity;
      let maxX = -Infinity;
      let maxY = -Infinity;
      nodes.forEach(function (n) {
        const pad = n.r + 18;
        if (n.x - pad < minX) { minX = n.x - pad; }
        if (n.y - pad < minY) { minY = n.y - pad; }
        if (n.x + pad > maxX) { maxX = n.x + pad; }
        if (n.y + pad > maxY) { maxY = n.y + pad; }
      });
      const bw = Math.max(40, maxX - minX);
      const bh = Math.max(40, maxY - minY);
      const k = clamp(Math.min((cssW - 48) / bw, (cssH - 48) / bh), 0.12, 2.8);
      cam.k = k;
      cam.x = cssW / 2 - k * (minX + maxX) / 2;
      cam.y = cssH / 2 - k * (minY + maxY) / 2;
    }

    function place(list, cluster) {
      const repos = uniqueRepos(list);
      const many = cluster && repos.length > 1;
      const radius = 260 + repos.length * 90;
      const byRepo = {};
      repos.forEach(function (repo, i) {
        const ang = (i / repos.length) * Math.PI * 2 - Math.PI / 2;
        byRepo[repo] = {
          x: many ? Math.cos(ang) * radius : 0,
          y: many ? Math.sin(ang) * radius : 0,
        };
      });
      list.forEach(function (n, j) {
        const c = byRepo[n.repo || ""] || { x: 0, y: 0 };
        n.cx = c.x;
        n.cy = c.y;
        const old = prevPos[n.id];
        if (old && Number.isFinite(old.x) && Number.isFinite(old.y)) {
          n.x = old.x;
          n.y = old.y;
          return;
        }
        const jitter = 36 + (j % 11) * 7;
        const ja = (j / Math.max(list.length, 1)) * Math.PI * 2;
        n.x = c.x + Math.cos(ja) * jitter;
        n.y = c.y + Math.sin(ja) * jitter;
      });
    }

    function stopSim() {
      if (sim) {
        sim.on("tick", null).on("end", null).stop();
        sim = null;
      }
      running = false;
    }

    function setData(rawNodes, rawEdges, settings) {
      const cfg = settings || {};
      stopSim();
      const engine = global.d3force;
      if (!engine) {
        return;
      }
      const deg = degreeMap(rawNodes || [], rawEdges || []);
      const ranked = (rawNodes || []).slice().sort(function (a, b) {
        return (deg[b.id] || 0) - (deg[a.id] || 0);
      });
      const hubN = Math.min(18, Math.max(6, Math.ceil(ranked.length * 0.045)));
      hubIds = {};
      ranked.slice(0, hubN).forEach(function (n) { hubIds[n.id] = true; });
      nodes = (rawNodes || []).map(function (item) {
        const d = deg[item.id] || 0;
        return {
          id: item.id,
          type: item.type || "file",
          label: item.label || item.id,
          repo: item.repo || "",
          degree: d,
          r: clamp(3.2 + Math.sqrt(d) * 1.7, 3.2, 14),
        };
      });
      const byId = {};
      nodes.forEach(function (n) { byId[n.id] = n; });
      links = [];
      (rawEdges || []).forEach(function (e) {
        const a = byId[e.source];
        const b = byId[e.target];
        if (a && b && a !== b) {
          links.push({ source: a, target: b, type: e.type || "rel" });
        }
      });
      adj = adjacency((rawEdges || []).map(function (e) {
        return { source: e.source, target: e.target };
      }));
      place(nodes, !!cfg.clusterByRepo);
      const n = nodes.length;
      const charge = n > 280 ? -22 : n > 120 ? -38 : -62;
      const clusterStrength = cfg.clusterByRepo && uniqueRepos(nodes).length > 1 ? 0.09 : 0;
      sim = engine.forceSimulation(nodes)
        .force("link", engine.forceLink(links).distance(function (d) {
          return 26 + d.source.r + d.target.r;
        }).strength(0.42))
        .force("charge", engine.forceManyBody().strength(charge).distanceMax(420))
        .force("center", engine.forceCenter(0, 0).strength(0.035))
        .force("collide", engine.forceCollide().radius(function (d) {
          return d.r + 3.5;
        }).iterations(2))
        .force("x", engine.forceX(function (d) { return d.cx || 0; }).strength(clusterStrength))
        .force("y", engine.forceY(function (d) { return d.cy || 0; }).strength(clusterStrength))
        .velocityDecay(0.32)
        .alpha(1)
        .alphaDecay(n > 300 ? 0.028 : 0.0228)
        .alphaMin(0.001);
      fitOnce = true;
      running = true;
      sim.on("tick", function () {
        running = true;
        if (fitOnce && sim.alpha() < 0.12) {
          fitOnce = false;
          zoomToFit();
        }
        nodes.forEach(function (n) {
          prevPos[n.id] = { x: n.x, y: n.y };
        });
        kick();
      });
      sim.on("end", function () {
        running = false;
        if (fitOnce) {
          fitOnce = false;
          zoomToFit();
        }
        kick();
      });
      resize();
      if (fitOnce) {
        zoomToFit();
      }
      kick();
    }

    function addAround(originId, rawNodes, rawEdges) {
      const engine = global.d3force;
      if (!engine || !originId) {
        return;
      }
      let origin = null;
      const existing = {};
      nodes.forEach(function (n) {
        existing[n.id] = n;
        if (n.id === originId) {
          origin = n;
        }
      });
      if (!origin) {
        return;
      }
      const incoming = rawNodes || [];
      incoming.forEach(function (item, i) {
        if (!item || !item.id || existing[item.id]) {
          return;
        }
        const ang = (i / Math.max(incoming.length, 1)) * Math.PI * 2;
        const dist = 32 + (i % 6) * 7;
        const node = {
          id: item.id,
          type: item.type || "function",
          label: item.label || item.id,
          repo: item.repo || origin.repo,
          degree: 1,
          r: item.type === "class" ? 5.5 : 4.2,
          x: origin.x + Math.cos(ang) * dist,
          y: origin.y + Math.sin(ang) * dist,
          cx: origin.cx,
          cy: origin.cy,
        };
        nodes.push(node);
        existing[item.id] = node;
        prevPos[node.id] = { x: node.x, y: node.y };
      });
      (rawEdges || []).forEach(function (e) {
        const a = existing[e.source];
        const b = existing[e.target];
        if (!a || !b || a === b) {
          return;
        }
        let found = false;
        for (let i = 0; i < links.length; i += 1) {
          if (links[i].source.id === a.id && links[i].target.id === b.id) {
            found = true;
            break;
          }
        }
        if (!found) {
          links.push({ source: a, target: b, type: e.type || "contains" });
        }
      });
      const adjSrc = {};
      links.forEach(function (e) {
        const s = e.source.id;
        const t = e.target.id;
        if (!adjSrc[s]) { adjSrc[s] = {}; }
        if (!adjSrc[t]) { adjSrc[t] = {}; }
        adjSrc[s][t] = true;
        adjSrc[t][s] = true;
      });
      adj = adjSrc;
      if (!sim) {
        return;
      }
      sim.nodes(nodes);
      const linkF = sim.force("link");
      if (linkF) {
        linkF.links(links);
      }
      sim.alpha(0.38).restart();
      running = true;
      kick();
    }

    function focusSet() {
      const seed = selectedId || hoverId;
      if (!seed) {
        return null;
      }
      const set = {};
      set[seed] = true;
      const neigh = adj[seed];
      if (neigh) {
        Object.keys(neigh).forEach(function (id) { set[id] = true; });
      }
      return set;
    }

    function shouldLabel(n, focus) {
      if (n.id === selectedId || n.id === hoverId) {
        return true;
      }
      if (hubIds[n.id]) {
        return true;
      }
      if (cam.k >= ZOOM_LABELS && (!focus || focus[n.id])) {
        return n.degree >= 1 || cam.k >= 2;
      }
      return false;
    }

    function draw() {
      if (!ctx) {
        return;
      }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.fillStyle = BG;
      ctx.fillRect(0, 0, cssW, cssH);
      ctx.save();
      ctx.translate(cam.x, cam.y);
      ctx.scale(cam.k, cam.k);
      const focus = focusSet();
      ctx.lineCap = "round";
      links.forEach(function (e) {
        const hot = focus && focus[e.source.id] && focus[e.target.id];
        const dim = focus && !hot;
        ctx.strokeStyle = hot ? EDGE_HOT : dim ? EDGE_DIM : EDGE;
        ctx.lineWidth = (hot ? 1.15 : 0.7) / cam.k;
        ctx.beginPath();
        ctx.moveTo(e.source.x, e.source.y);
        ctx.lineTo(e.target.x, e.target.y);
        ctx.stroke();
      });
      const labels = [];
      nodes.forEach(function (n) {
        const inFocus = !focus || focus[n.id];
        const isSel = n.id === selectedId;
        const isHov = n.id === hoverId;
        ctx.globalAlpha = inFocus ? 1 : 0.16;
        ctx.beginPath();
        ctx.arc(n.x, n.y, n.r, 0, Math.PI * 2);
        ctx.fillStyle = colorOf(n.type);
        ctx.fill();
        if (isSel) {
          ctx.lineWidth = 2.4 / cam.k;
          ctx.strokeStyle = WINE;
          ctx.stroke();
        } else if (isHov) {
          ctx.lineWidth = 1.6 / cam.k;
          ctx.strokeStyle = "rgba(255,255,255,0.7)";
          ctx.stroke();
        }
        ctx.globalAlpha = 1;
        if (shouldLabel(n, focus)) {
          labels.push(n);
        }
      });
      if (labels.length) {
        const fontPx = clamp(11 / cam.k, 11 / MAX_K, 14);
        ctx.font = "600 " + fontPx + "px Inter, system-ui, sans-serif";
        ctx.textBaseline = "middle";
        ctx.lineJoin = "round";
        ctx.lineWidth = 3.2 / cam.k;
        labels.forEach(function (n) {
          const text = String(n.label || n.id).slice(0, 32);
          const x = n.x + n.r + 5 / cam.k;
          const y = n.y;
          ctx.strokeStyle = HALO;
          ctx.strokeText(text, x, y);
          ctx.fillStyle = LABEL;
          ctx.fillText(text, x, y);
        });
      }
      ctx.restore();
    }

    function setSelected(id) {
      selectedId = id || null;
      kick();
    }

    function pointerDown(ev) {
      if (ev.button !== 0) {
        return;
      }
      canvas.setPointerCapture(ev.pointerId);
      const w = toWorld(ev.clientX, ev.clientY);
      const node = hitNode(w.x, w.y);
      moved = false;
      if (node) {
        drag = { kind: "node", node: node, x: ev.clientX, y: ev.clientY };
        interacting = true;
        if (sim) {
          sim.alphaTarget(0.28).restart();
          running = true;
        }
        node.fx = node.x;
        node.fy = node.y;
      } else {
        drag = { kind: "pan", x: ev.clientX, y: ev.clientY };
        interacting = true;
        canvas.classList.add("dragging");
      }
      kick();
    }

    function pointerMove(ev) {
      const w = toWorld(ev.clientX, ev.clientY);
      if (!drag) {
        const node = hitNode(w.x, w.y);
        const next = node ? node.id : null;
        if (next !== hoverId) {
          hoverId = next;
          canvas.style.cursor = next ? "pointer" : "grab";
          kick();
        }
        return;
      }
      const dx = ev.clientX - drag.x;
      const dy = ev.clientY - drag.y;
      if (Math.abs(dx) + Math.abs(dy) > 3) {
        moved = true;
      }
      if (drag.kind === "pan") {
        cam.x += dx;
        cam.y += dy;
        drag.x = ev.clientX;
        drag.y = ev.clientY;
        kick();
        return;
      }
      const node = drag.node;
      node.fx = w.x;
      node.fy = w.y;
      node.x = w.x;
      node.y = w.y;
      drag.x = ev.clientX;
      drag.y = ev.clientY;
      kick();
    }

    function pointerUp(ev) {
      if (!drag) {
        return;
      }
      const kind = drag.kind;
      const node = drag.node;
      drag = null;
      interacting = false;
      canvas.classList.remove("dragging");
      if (kind === "node" && node) {
        if (sim) {
          sim.alphaTarget(0);
        }
        global.setTimeout(function () {
          if (node.fx !== null) {
            node.fx = null;
            node.fy = null;
          }
        }, 700);
        if (!moved) {
          selectedId = node.id;
          onSelect(node.id);
        }
      } else if (kind === "pan" && !moved) {
        selectedId = null;
        onSelect(null);
      }
      kick();
      if (ev && canvas.hasPointerCapture && canvas.hasPointerCapture(ev.pointerId)) {
        canvas.releasePointerCapture(ev.pointerId);
      }
    }

    function wheel(ev) {
      ev.preventDefault();
      const rect = canvas.getBoundingClientRect();
      const mx = ev.clientX - rect.left;
      const my = ev.clientY - rect.top;
      const wx = (mx - cam.x) / cam.k;
      const wy = (my - cam.y) / cam.k;
      const factor = ev.deltaY < 0 ? 1.12 : 0.89;
      cam.k = clamp(cam.k * factor, MIN_K, MAX_K);
      cam.x = mx - wx * cam.k;
      cam.y = my - wy * cam.k;
      kick();
    }

    canvas.addEventListener("pointerdown", pointerDown);
    canvas.addEventListener("pointermove", pointerMove);
    canvas.addEventListener("pointerup", pointerUp);
    canvas.addEventListener("pointercancel", pointerUp);
    canvas.addEventListener("wheel", wheel, { passive: false });
    canvas.addEventListener("contextmenu", function (ev) { ev.preventDefault(); });

    let ro = null;
    if (global.ResizeObserver) {
      ro = new global.ResizeObserver(function () { resize(); });
      ro.observe(canvas);
    }
    global.addEventListener("resize", resize);

    resize();

    return {
      setData: setData,
      addAround: addAround,
      setSelected: setSelected,
      resize: resize,
      zoomToFit: function () { zoomToFit(); kick(); },
      destroy: function () {
        stopSim();
        if (ro) { ro.disconnect(); }
        global.removeEventListener("resize", resize);
      },
    };
  }

  global.ForgeTeia = { create: create, COLORS: COLORS };
})(typeof window !== "undefined" ? window : globalThis);
