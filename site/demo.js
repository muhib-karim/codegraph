// Interactive graph demo for the static site. Reads data/graph.json (exported at build time
// from an index of tests/fixtures) and answers callers / callees / impact from its edges,
// with the same semantics as the CLI. No network beyond the bundled JSON.
'use strict';

const SVG_NS = 'http://www.w3.org/2000/svg';
let WIDTH = 960;
let HEIGHT = 600;
const DEFAULT_SYMBOL = 'web/src/util.ts::scale/1';
const GROUP_TITLES = {
  mini: 'mini/ · Python + Java',
  workflow: 'workflow/ · Python + Java',
  web: 'web/ · TypeScript',
  webjs: 'webjs/ · JavaScript',
};

const $ = (id) => document.getElementById(id);

function svgEl(tag, attrs) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [key, value] of Object.entries(attrs || {})) node.setAttribute(key, String(value));
  return node;
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = String(text);
  return node;
}

// Seeded PRNG so the layout is identical on every load.
function rng(seed) {
  let s = seed >>> 0;
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0;
    return s / 4294967296;
  };
}

function simulate(members, links, rand) {
  // Force layout of one group around the origin.
  const pos = new Map();
  members.forEach((n, i) => {
    const angle = i * 2.39996;
    const radius = 12 * Math.sqrt(i + 1);
    pos.set(n.id, { x: Math.cos(angle) * radius + rand(), y: Math.sin(angle) * radius + rand(), vx: 0, vy: 0 });
  });
  const inside = links.filter((e) => pos.has(e.source) && pos.has(e.target));
  const pts = [...pos.values()];
  for (let step = 0; step < 300; step++) {
    const cap = 10 * (1 - step / 300) + 0.4;
    for (let i = 0; i < pts.length; i++) {
      for (let j = i + 1; j < pts.length; j++) {
        const a = pts[i];
        const b = pts[j];
        let dx = a.x - b.x;
        let dy = a.y - b.y;
        const d2 = dx * dx + dy * dy + 0.01;
        const force = 700 / d2;
        dx *= force; dy *= force;
        a.vx += dx; a.vy += dy; b.vx -= dx; b.vy -= dy;
      }
    }
    for (const e of inside) {
      const a = pos.get(e.source);
      const b = pos.get(e.target);
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      const d = Math.sqrt(dx * dx + dy * dy) || 1;
      const pull = (d - 40) * 0.03;
      a.vx += (dx / d) * pull; a.vy += (dy / d) * pull;
      b.vx -= (dx / d) * pull; b.vy -= (dy / d) * pull;
    }
    for (const p of pts) {
      p.vx -= p.x * 0.01;
      p.vy -= p.y * 0.01;
      p.x += Math.max(-cap, Math.min(cap, p.vx));
      p.y += Math.max(-cap, Math.min(cap, p.vy));
      p.vx *= 0.5; p.vy *= 0.5;
    }
  }
  return pos;
}

function layout(nodes, edges) {
  // One cell per fixture repository; each group is laid out alone, then fitted to its cell.
  const groups = [...new Set(nodes.map((n) => n.group))].sort();
  // Two columns on wide screens, one stacked column on phones.
  const cols = groups.length > 1 && WIDTH > 600 ? 2 : 1;
  const rows = Math.ceil(groups.length / cols);
  const cellW = WIDTH / cols;
  const cellH = HEIGHT / rows;
  const rand = rng(7);
  const pos = new Map();
  const labels = [];
  groups.forEach((g, i) => {
    const members = nodes.filter((n) => n.group === g);
    const local = simulate(members, edges, () => rand() - 0.5);
    const xs = [...local.values()].map((p) => p.x);
    const ys = [...local.values()].map((p) => p.y);
    const [minX, maxX, minY, maxY] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
    const left = (i % cols) * cellW;
    const top = Math.floor(i / cols) * cellH;
    const padX = 70;
    const padTop = 46;
    const padBottom = i >= groups.length - cols ? 64 : 26;
    const scale = Math.min(
      (cellW - 2 * padX) / (maxX - minX || 1),
      (cellH - padTop - padBottom) / (maxY - minY || 1),
      2.2,
    );
    const offX = left + (cellW - (maxX - minX) * scale) / 2;
    const offY = top + padTop + (cellH - padTop - padBottom - (maxY - minY) * scale) / 2;
    for (const [id, p] of local) {
      pos.set(id, { x: offX + (p.x - minX) * scale, y: offY + (p.y - minY) * scale });
    }
    labels.push({ group: g, x: left + 22, y: top + 26 });
  });
  return { pos, labels };
}

class Demo {
  constructor(data) {
    this.nodes = data.nodes;
    this.edges = data.edges;
    this.byId = new Map(this.nodes.map((n) => [n.id, n]));
    this.incoming = new Map();
    this.outgoing = new Map();
    for (const e of this.edges) {
      if (!this.incoming.has(e.target)) this.incoming.set(e.target, []);
      if (!this.outgoing.has(e.source)) this.outgoing.set(e.source, []);
      this.incoming.get(e.target).push(e);
      this.outgoing.get(e.source).push(e);
    }
    this.question = 'impact';
    this.selected = null;
    this.svg = $('graph');
    this.nodeEls = new Map();
    this.edgeEls = [];
  }

  degree(id) {
    return (this.incoming.get(id) || []).length + (this.outgoing.get(id) || []).length;
  }

  render() {
    const groups = new Set(this.nodes.map((n) => n.group)).size;
    if (this.svg.clientWidth && this.svg.clientWidth < 620) {
      WIDTH = 480;
      HEIGHT = 300 * groups;
      this.svg.classList.add('stacked');
      this.svg.style.aspectRatio = `${WIDTH} / ${HEIGHT}`;
    }
    const { pos, labels } = layout(this.nodes, this.edges);
    this.svg.setAttribute('viewBox', `0 0 ${WIDTH} ${HEIGHT}`);
    const defs = svgEl('defs');
    for (const [id, color] of [['arrow', '#4a6270'], ['arrow-lit', '#5eead4']]) {
      const marker = svgEl('marker', {
        id, viewBox: '0 0 10 10', refX: 15, refY: 5, markerWidth: 6, markerHeight: 6, orient: 'auto',
      });
      marker.append(svgEl('path', { d: 'M0 1 L9 5 L0 9 z', fill: color }));
      defs.append(marker);
    }
    this.svg.append(defs);
    for (const l of labels) {
      const t = svgEl('text', { x: l.x, y: l.y, class: 'group-label' });
      t.textContent = GROUP_TITLES[l.group] || `${l.group}/`;
      this.svg.append(t);
    }
    const edgeLayer = svgEl('g');
    const nodeLayer = svgEl('g');
    this.svg.append(edgeLayer, nodeLayer);
    for (const e of this.edges) {
      const a = pos.get(e.source);
      const b = pos.get(e.target);
      if (!a || !b) continue;
      const line = svgEl('line', {
        x1: a.x.toFixed(1), y1: a.y.toFixed(1), x2: b.x.toFixed(1), y2: b.y.toFixed(1),
        class: `edge ${e.type}${e.confidence === 'heuristic' ? ' heuristic' : ''}`,
        'marker-end': 'url(#arrow)',
      });
      line.style.setProperty('--len', Math.hypot(b.x - a.x, b.y - a.y).toFixed(0));
      edgeLayer.append(line);
      this.edgeEls.push({ edge: e, line });
    }
    for (const n of this.nodes) {
      const p = pos.get(n.id);
      const deg = this.degree(n.id);
      const g = svgEl('g', {
        class: `node ${n.lang} ${n.kind}${deg >= 4 ? ' labelled' : ''}`,
        transform: `translate(${p.x.toFixed(1)} ${p.y.toFixed(1)})`,
      });
      const r = n.kind === 'class' || n.kind === 'interface' ? 7.5 : 5 + Math.min(deg, 6) * 0.4;
      const circle = svgEl('circle', { r: r.toFixed(1) });
      const title = svgEl('title');
      title.textContent = `${n.qualname} · ${n.kind} · ${n.file}:${n.line}`;
      circle.append(title);
      const label = svgEl('text', { x: 10, y: 4 });
      label.textContent = n.name;
      g.append(circle, label);
      g.addEventListener('click', () => this.select(n.id));
      nodeLayer.append(g);
      this.nodeEls.set(n.id, g);
    }
  }

  // Same semantics as the CLI: callers = incoming calls and references (one hop),
  // callees = outgoing calls, impact = reverse calls, references and inheritance to depth 3.
  answer(id) {
    if (this.question === 'callees') {
      return (this.outgoing.get(id) || [])
        .filter((e) => e.type === 'call')
        .map((e) => ({ edge: e, other: e.target, depth: 1 }));
    }
    const types = this.question === 'callers' ? ['call', 'ref'] : ['call', 'ref', 'inherits'];
    const maxDepth = this.question === 'callers' ? 1 : 3;
    const rows = [];
    const seen = new Set([id]);
    let frontier = [id];
    for (let depth = 1; depth <= maxDepth && frontier.length; depth++) {
      const next = [];
      for (const target of frontier) {
        for (const e of this.incoming.get(target) || []) {
          if (!types.includes(e.type) || e.source === id) continue;
          rows.push({ edge: e, other: e.source, depth });
          if (!seen.has(e.source)) {
            seen.add(e.source);
            next.push(e.source);
          }
        }
      }
      frontier = next;
    }
    const key = (r) => `${r.edge.file}:${String(r.edge.line).padStart(6, '0')}`;
    return rows.sort((a, b) => (key(a) < key(b) ? -1 : key(a) > key(b) ? 1 : a.depth - b.depth));
  }

  select(id, focusGraph) {
    const n = this.byId.get(id);
    if (!n) return;
    this.selected = id;
    $('sel-name').textContent = n.qualname;
    $('sel-meta').textContent = `${n.kind} · ${n.lang} · defined at ${n.file}:${n.line}`;
    const target = n.kind === 'module' ? n.file.split('/').slice(1).join('/') : n.qualname;
    const depth = this.question === 'impact' ? ' --depth 3' : '';
    $('equiv').textContent = `codegraph ${this.question} ${target}${depth} --repo tests/fixtures/${n.group}`;
    const rows = this.answer(id);
    const list = $('answers');
    list.replaceChildren();
    if (!rows.length) {
      list.append(el('li', 'empty', `No indexed ${this.question} for this symbol. That is not proof of no runtime use.`));
    }
    for (const r of rows) {
      const other = this.byId.get(r.other);
      const li = el('li');
      const button = el('button');
      button.type = 'button';
      const site = r.edge.file.split('/').slice(1).join('/');
      button.append(
        el('span', 'c', `${site}:${r.edge.line}`),
        el('span', 's', `${other ? other.qualname : r.other} · ${r.edge.type}${this.question === 'impact' ? ` · hop ${r.depth}` : ''}`),
        el('span', `b ${r.edge.confidence}`, r.edge.confidence),
      );
      button.addEventListener('click', () => this.select(r.other));
      li.append(button);
      list.append(li);
    }
    this.highlight(id, rows);
    if (focusGraph) $('sel-name').scrollIntoView({ block: 'nearest' });
  }

  highlight(id, rows) {
    this.svg.classList.add('focused');
    const lit = new Set([id, ...rows.map((r) => r.other)]);
    const depthOf = new Map(rows.map((r) => [r.edge, r.depth]));
    for (const [nid, g] of this.nodeEls) {
      g.classList.toggle('sel', nid === id);
      g.classList.toggle('lit', lit.has(nid) && nid !== id);
    }
    for (const { edge, line } of this.edgeEls) {
      const on = depthOf.has(edge);
      line.classList.remove('draw');
      line.classList.toggle('lit', on);
      line.setAttribute('marker-end', on ? 'url(#arrow-lit)' : 'url(#arrow)');
      if (on) {
        line.style.setProperty('--delay', `${(depthOf.get(edge) - 1) * 0.35}s`);
        // Restart the draw-in so each new question replays its own ripple.
        void line.getBoundingClientRect();
        line.classList.add('draw');
      }
    }
  }

  setQuestion(q) {
    this.question = q;
    for (const b of document.querySelectorAll('.seg button')) {
      const on = b.dataset.q === q;
      b.setAttribute('aria-selected', String(on));
      b.tabIndex = on ? 0 : -1;
    }
    if (this.selected) this.select(this.selected);
  }

  search(query) {
    const box = $('matches');
    const q = query.trim().toLowerCase();
    box.replaceChildren();
    if (!q) {
      box.hidden = true;
      return;
    }
    const field = (n) => (q.includes('.') ? n.qualname : n.name).toLowerCase();
    const rank = (n) => (field(n) === q ? 0 : field(n).startsWith(q) ? 1 : 2);
    const hits = this.nodes
      .filter((n) => n.kind !== 'module' && field(n).includes(q))
      .sort((a, b) => rank(a) - rank(b) || a.file.localeCompare(b.file) || a.line - b.line)
      .slice(0, 12);
    box.hidden = false;
    if (!hits.length) {
      box.append(el('p', '', 'No symbol with that name in the sample index.'));
      return;
    }
    for (const n of hits) {
      const b = el('button');
      b.type = 'button';
      b.setAttribute('role', 'option');
      b.append(document.createTextNode(n.qualname), el('span', '', `${n.file}:${n.line}`));
      b.addEventListener('click', () => {
        box.hidden = true;
        $('find').value = n.qualname;
        this.select(n.id, true);
      });
      box.append(b);
    }
  }

  wire() {
    for (const b of document.querySelectorAll('.seg button')) {
      b.addEventListener('click', () => this.setQuestion(b.dataset.q));
      b.addEventListener('keydown', (event) => {
        const tabs = [...document.querySelectorAll('.seg button')];
        const i = tabs.indexOf(b);
        let next = -1;
        if (event.key === 'ArrowRight') next = (i + 1) % tabs.length;
        if (event.key === 'ArrowLeft') next = (i + tabs.length - 1) % tabs.length;
        if (next < 0) return;
        event.preventDefault();
        this.setQuestion(tabs[next].dataset.q);
        tabs[next].focus();
      });
    }
    const input = $('find');
    input.addEventListener('input', () => this.search(input.value));
    input.addEventListener('keydown', (event) => {
      const first = $('matches').querySelector('button');
      if (event.key === 'ArrowDown' && first) {
        event.preventDefault();
        first.focus();
      }
      if (event.key === 'Enter' && first) {
        event.preventDefault();
        first.click();
      }
      if (event.key === 'Escape') $('matches').hidden = true;
    });
    $('matches').addEventListener('keydown', (event) => {
      const items = [...$('matches').querySelectorAll('button')];
      const i = items.indexOf(document.activeElement);
      if (event.key === 'ArrowDown' && i < items.length - 1) { event.preventDefault(); items[i + 1].focus(); }
      if (event.key === 'ArrowUp') { event.preventDefault(); (i > 0 ? items[i - 1] : input).focus(); }
      if (event.key === 'Escape') { $('matches').hidden = true; input.focus(); }
    });
  }
}

async function start() {
  const status = $('graph-status');
  try {
    const response = await fetch('data/graph.json');
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const demo = new Demo(await response.json());
    demo.render();
    demo.wire();
    demo.setQuestion('impact');
    demo.select(demo.byId.has(DEFAULT_SYMBOL) ? DEFAULT_SYMBOL : demo.nodes[0].id);
    status.hidden = true;
  } catch (error) {
    status.textContent = `The sample graph could not be loaded (${error.message}). The CLI output below is unaffected.`;
  }
}

start();
