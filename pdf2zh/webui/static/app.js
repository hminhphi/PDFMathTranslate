(function () {
  'use strict';

  var $ = function (id) { return document.getElementById(id); };
  var el = function (tag, cls) { var e = document.createElement(tag); if (cls) e.className = cls; return e; };
  var root = document.documentElement;
  var body = document.body;
  var stage = $('viewerStage');
  var stageInner = $('stageInner');
  var thumbs = $('thumbs');
  var sidebar = $('sidebar');

  var state = {
    sourceMode: 'file', file: null, translating: false, translated: false,
    viewMode: 'single', side: 'source', page: 1, zoom: 1, fitted: null,
    query: '', matches: [], matchIndex: 0, matchCount: 0, focus: false, overlay: 0.65,
    jobId: null, pollTimer: null, outputs: null, isPdf: false, numPages: 0,
    pdf: { source: null, translated: null },
    textCache: { source: {}, translated: {} },
    meta: null, rendered: { source: null, translated: null }
  };

  /* ================= Theme ================= */
  function applyTheme(theme) {
    root.setAttribute('data-theme', theme);
    var dark = theme === 'dark';
    $('themeToggle').setAttribute('aria-pressed', dark ? 'true' : 'false');
    $('themeToggle').setAttribute('aria-label', dark ? 'Switch to light theme' : 'Switch to dark theme');
    try { localStorage.setItem('mipi-theme', theme); } catch (e) {}
  }
  applyTheme(root.getAttribute('data-theme') || 'light');
  $('themeToggle').addEventListener('click', function () {
    applyTheme(root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark');
  });

  /* ================= Sidebar toggle ================= */
  var mqMobile = window.matchMedia('(max-width: 1023px)');
  var scrim = $('scrim');
  function syncScrim() { scrim.hidden = !body.classList.contains('drawer-open'); }
  function syncSidebarExpanded() {
    var expanded = mqMobile.matches ? body.classList.contains('drawer-open') : !body.classList.contains('sidebar-collapsed');
    $('sidebarToggle').setAttribute('aria-expanded', expanded ? 'true' : 'false');
  }
  function sidebarHidden() {
    if (body.classList.contains('focus-mode')) return true;
    if (mqMobile.matches) return !body.classList.contains('drawer-open');
    return body.classList.contains('sidebar-collapsed');
  }
  function syncSidebarA11y() {
    var hidden = sidebarHidden();
    if ('inert' in sidebar) { sidebar.inert = hidden; }
    else { if (hidden) sidebar.setAttribute('aria-hidden', 'true'); else sidebar.removeAttribute('aria-hidden'); }
  }
  function closeDrawer(focusToggle) {
    body.classList.remove('drawer-open');
    syncScrim(); syncSidebarExpanded(); syncSidebarA11y();
    if (focusToggle) $('sidebarToggle').focus();
  }
  function toggleSidebar() {
    if (mqMobile.matches) {
      var open = body.classList.toggle('drawer-open');
      syncScrim(); syncSidebarExpanded(); syncSidebarA11y();
      if (open) requestAnimationFrame(function () { sidebar.focus(); });
    } else {
      body.classList.toggle('sidebar-collapsed');
      syncSidebarExpanded(); syncSidebarA11y();
    }
  }
  $('sidebarToggle').addEventListener('click', toggleSidebar);
  scrim.addEventListener('click', function () { closeDrawer(true); });
  mqMobile.addEventListener('change', function () {
    body.classList.remove('drawer-open');
    body.classList.remove('sidebar-collapsed');
    syncScrim(); syncSidebarExpanded(); syncSidebarA11y();
  });

  /* ================= Source: File / Link ================= */
  var sourceFile = $('sourceFile'), sourceLink = $('sourceLink');
  document.querySelector('.seg[aria-label="Input type"]').addEventListener('click', function (e) {
    var btn = e.target.closest('[data-source]'); if (!btn) return;
    state.sourceMode = btn.getAttribute('data-source');
    btn.parentElement.querySelectorAll('[data-source]').forEach(function (b) { b.setAttribute('aria-checked', b === btn ? 'true' : 'false'); });
    sourceFile.hidden = state.sourceMode !== 'file';
    sourceLink.hidden = state.sourceMode !== 'link';
    refreshReady();
  });

  var fileInput = $('fileInput'), dropzone = $('dropzone'), fileChip = $('fileChip');
  function formatBytes(b) {
    if (b == null) return '';
    var u = ['B', 'KB', 'MB', 'GB'], i = 0, v = b;
    while (v >= 1024 && i < u.length - 1) { v /= 1024; i++; }
    return (i === 0 ? v : v.toFixed(1)) + ' ' + u[i];
  }
  function setFile(f) {
    if (!f) return;
    state.file = f;
    $('fileName').textContent = f.name;
    $('fileSize').textContent = formatBytes(f.size) + ' · ' + (f.type || 'document');
    fileChip.hidden = false; dropzone.hidden = true;
    $('filePillName').textContent = f.name;
    $('filePillDot').hidden = false;
    refreshReady();
  }
  function clearFile() {
    state.file = null; fileInput.value = '';
    fileChip.hidden = true; dropzone.hidden = false;
    $('filePillName').textContent = 'No document selected';
    $('filePillDot').hidden = true;
    refreshReady();
  }
  dropzone.addEventListener('click', function () { fileInput.click(); });
  fileInput.addEventListener('change', function () { if (fileInput.files && fileInput.files[0]) setFile(fileInput.files[0]); });
  $('fileRemove').addEventListener('click', clearFile);
  ['dragenter', 'dragover'].forEach(function (t) { dropzone.addEventListener(t, function (e) { e.preventDefault(); dropzone.classList.add('is-drag'); }); });
  ['dragleave', 'drop'].forEach(function (t) { dropzone.addEventListener(t, function (e) { e.preventDefault(); dropzone.classList.remove('is-drag'); }); });
  dropzone.addEventListener('drop', function (e) { if (e.dataTransfer && e.dataTransfer.files[0]) setFile(e.dataTransfer.files[0]); });

  /* ================= Languages / Service metadata ================= */
  function fillLanguages(select, value) {
    select.innerHTML = '';
    Object.keys(state.meta.languages).forEach(function (name) {
      var option = el('option'); option.textContent = name; option.value = name;
      if (name === value) option.selected = true;
      select.appendChild(option);
    });
  }
  function fillServices() {
    var select = $('serviceSelect');
    select.innerHTML = '';
    state.meta.services.forEach(function (svc) {
      var option = el('option'); option.textContent = svc.label; option.value = svc.label;
      select.appendChild(option);
    });
    var preferred = state.meta.defaults.service;
    if (preferred && state.meta.services.some(function (s) { return s.label === preferred; })) {
      select.value = preferred;
    }
    renderServiceFields();
  }
  function renderServiceFields() {
    var label = $('serviceSelect').value;
    var svc = state.meta.services.find(function (s) { return s.label === label; });
    var host = $('serviceFields');
    host.innerHTML = '';
    if (!svc || !svc.envs.length) {
      $('serviceHelp').textContent = label + ' is ready to use — no key required.';
      return;
    }
    $('serviceHelp').textContent = label + ' needs credentials. They are stored in your local config.';
    svc.envs.forEach(function (env) {
      var wrap = el('div', 'field');
      var fieldId = 'svc_' + env.key;
      var lab = el('label', 'field__label'); lab.setAttribute('for', fieldId); lab.textContent = env.label;
      var input = el('input', 'input');
      input.id = fieldId; input.type = env.secret ? 'password' : 'text';
      input.placeholder = env.default ? String(env.default) : '';
      input.value = env.value || '';
      input.autocomplete = 'off';
      input.setAttribute('data-env-key', env.key);
      wrap.appendChild(lab); wrap.appendChild(input);
      host.appendChild(wrap);
    });
  }
  $('serviceSelect').addEventListener('change', renderServiceFields);

  $('swapBtn').addEventListener('click', function () {
    var a = $('fromLang'), b = $('toLang'), t = a.value; a.value = b.value; b.value = t;
  });

  /* ================= Pages choice ================= */
  var selectedPages = 'All';
  document.querySelector('.choice-group[aria-label="Pages to translate"]').addEventListener('click', function (e) {
    var btn = e.target.closest('[data-pages]'); if (!btn) return;
    selectedPages = btn.getAttribute('data-pages');
    this.querySelectorAll('[data-pages]').forEach(function (b) { b.setAttribute('aria-checked', b === btn ? 'true' : 'false'); });
    $('pageRangeField').hidden = selectedPages !== 'Others';
    if (selectedPages === 'Others') $('pageRange').focus();
    refreshReady();
  });

  var pageRange = $('pageRange'), pageRangeError = $('pageRangeError');
  function validatePageRange() {
    var v = pageRange.value.trim();
    if (!v) { pageRangeError.hidden = true; pageRange.removeAttribute('aria-invalid'); return true; }
    var ok = /^\d+(\s*-\s*\d+)?(\s*,\s*\d+(\s*-\s*\d+)?)*$/.test(v);
    pageRangeError.hidden = ok;
    if (ok) pageRange.removeAttribute('aria-invalid'); else pageRange.setAttribute('aria-invalid', 'true');
    return ok;
  }
  pageRange.addEventListener('input', function () { validatePageRange(); refreshReady(); });
  pageRange.addEventListener('blur', validatePageRange);

  /* ================= Advanced ================= */
  $('advTrigger').addEventListener('click', function () {
    var open = this.getAttribute('aria-expanded') === 'true';
    this.setAttribute('aria-expanded', open ? 'false' : 'true');
    $('advPanel').hidden = open;
  });

  /* ================= Viewer (PDF.js) ================= */
  function emptyStage(message) {
    stageInner.innerHTML = '';
    var p = el('p', 'viewer-empty');
    p.textContent = message || 'Translate a document to preview it here.';
    stageInner.appendChild(p);
  }

  function pdfScale() { return state.zoom * 1.35; }

  function renderPageInto(container, kind, pageNum) {
    var doc = state.pdf[kind];
    if (!doc) return Promise.resolve(null);
    return doc.getPage(pageNum).then(function (page) {
      var viewport = page.getViewport({ scale: pdfScale() });
      var pageWrap = el('div', 'pdf-page');
      var canvas = el('canvas');
      canvas.width = Math.floor(viewport.width);
      canvas.height = Math.floor(viewport.height);
      pageWrap.appendChild(canvas);
      container.appendChild(pageWrap);
      return page.render({ canvasContext: canvas.getContext('2d'), viewport: viewport }).promise.then(function () {
        return { pageWrap: pageWrap, canvas: canvas, page: page, viewport: viewport, kind: kind, num: pageNum };
      });
    });
  }

  function renderViewer() {
    stageInner.innerHTML = '';
    state.rendered = { source: null, translated: null };
    if (!state.translated || !state.isPdf) {
      renderOfficeView();
      return;
    }
    var jobs = [];
    if (state.viewMode === 'compare') {
      var grid = el('div', 'compare-grid');
      var c1 = el('div', 'doc-col'); var l1 = el('p', 'col-label'); l1.textContent = 'Source'; c1.appendChild(l1);
      var c2 = el('div', 'doc-col'); var l2 = el('p', 'col-label'); l2.textContent = 'Translated'; c2.appendChild(l2);
      grid.appendChild(c1); grid.appendChild(c2); stageInner.appendChild(grid);
      jobs.push(renderPageInto(c1, 'source', state.page).then(function (r) { state.rendered.source = r; }));
      jobs.push(renderPageInto(c2, 'translated', state.page).then(function (r) { state.rendered.translated = r; }));
    } else if (state.viewMode === 'overlay') {
      var stack = el('div', 'overlay-stack');
      var layer = el('div', 'overlay-layer pdf-layer');
      layer.style.opacity = String(state.overlay);
      stack.appendChild(layer); stageInner.appendChild(stack);
      jobs.push(renderPageInto(stack, 'source', state.page).then(function (r) { state.rendered.source = r; }));
      jobs.push(renderPageInto(layer, 'translated', state.page).then(function (r) { state.rendered.translated = r; }));
    } else {
      var side = (state.side === 'translated' && state.pdf.translated) ? 'translated' : 'source';
      jobs.push(renderPageInto(stageInner, side, state.page).then(function (r) { state.rendered[side] = r; }));
    }
    Promise.all(jobs).then(function () { applySearch(); });
    renderThumbs();
  }

  function officeFileMeta() {
    var name = (state.outputs && state.outputs.translated) || (state.file && state.file.name) || 'document';
    name = name.split(/[\\/]/).pop();
    return name;
  }

  function renderOfficeView() {
    if (!state.translated) { emptyStage('Translate a document to preview it here.'); renderThumbs(); return; }
    stageInner.innerHTML = '';
    var card = el('div', 'doc-page office-card');
    var eyebrow = el('p', 'doc-page__eyebrow');
    eyebrow.textContent = 'Office document · layout preserved';
    card.appendChild(eyebrow);
    var title = el('h4');
    title.textContent = 'Translation complete';
    card.appendChild(title);
    var p = el('p');
    p.textContent = 'The translated ' + (officeFileMeta().split('.').pop().toUpperCase() || 'document') +
      ' keeps its original formatting, tables, text boxes and charts. Download it below — preview is available for PDF files only.';
    card.appendChild(p);
    var row = el('div', 'office-card__row');
    var icon = el('span', 'office-card__icon');
    icon.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M14 3v4a1 1 0 0 0 1 1h4"/><path d="M6 21h12a2 2 0 0 0 2-2V8l-5-5H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2Z"/></svg>';
    var meta = el('span', 'office-card__meta');
    var nameEl = el('span', 'office-card__name'); nameEl.textContent = officeFileMeta();
    var sub = el('span', 'office-card__sub'); sub.textContent = 'Translated file ready to download';
    meta.appendChild(nameEl); meta.appendChild(sub);
    row.appendChild(icon); row.appendChild(meta);
    card.appendChild(row);
    var btnRow = el('div', 'office-card__row');
    var dl = el('button', 'btn btn--primary');
    dl.type = 'button';
    dl.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v12m0 0 4-4m-4 4-4-4"/><path d="M5 21h14"/></svg><span>Download translation</span>';
    dl.addEventListener('click', function () { downloadOutput('translated'); });
    btnRow.appendChild(dl);
    card.appendChild(btnRow);
    stageInner.appendChild(card);
    renderThumbs();
  }

  function renderThumbs() {
    thumbs.innerHTML = '';
    if (!state.translated || !state.isPdf) { return; }
    var total = Math.min(state.numPages, 80);
    for (var i = 1; i <= total; i++) {
      (function (pageNum) {
        var b = el('button', 'thumb'); b.type = 'button';
        b.setAttribute('data-page', String(pageNum));
        b.setAttribute('aria-current', pageNum === state.page ? 'true' : 'false');
        b.setAttribute('aria-label', 'Go to page ' + pageNum);
        var pg = el('span', 'thumb__page');
        var num = el('span', 'thumb__num'); num.textContent = 'Page ' + pageNum;
        b.appendChild(pg); b.appendChild(num); thumbs.appendChild(b);
        var doc = state.pdf[state.side === 'translated' && state.pdf.translated ? 'translated' : 'source'];
        if (!doc) return;
        doc.getPage(pageNum).then(function (page) {
          var viewport = page.getViewport({ scale: 72 / page.getViewport({ scale: 1 }).width });
          var canvas = el('canvas');
          canvas.width = Math.floor(viewport.width); canvas.height = Math.floor(viewport.height);
          pg.appendChild(canvas);
          return page.render({ canvasContext: canvas.getContext('2d'), viewport: viewport }).promise;
        }).catch(function () {});
      })(i);
    }
  }
  thumbs.addEventListener('click', function (e) {
    var b = e.target.closest('[data-page]'); if (!b) return;
    setPage(parseInt(b.getAttribute('data-page'), 10));
  });

  function setPage(n, skipScroll) {
    state.page = Math.max(1, Math.min(state.numPages || 1, n));
    renderViewer();
    updateToolbar();
    if (!skipScroll) stage.scrollTo({ top: 0, behavior: 'smooth' });
  }

  /* ================= Zoom ================= */
  function applyZoom() {
    $('zoomLabel').textContent = Math.round(state.zoom * 100) + '%';
  }
  function setZoom(z) { state.zoom = Math.max(0.5, Math.min(2, z)); state.fitted = null; applyZoom(); renderViewer(); }
  $('zoomIn').addEventListener('click', function () { setZoom(state.zoom + 0.1); });
  $('zoomOut').addEventListener('click', function () { setZoom(state.zoom - 0.1); });
  $('zoomFit').addEventListener('click', function () { state.fitted = 'width'; fitWidth(); });
  function fitWidth() {
    var avail = stage.clientWidth - 48;
    var doc = state.pdf[state.side === 'translated' && state.pdf.translated ? 'translated' : 'source'];
    if (!doc) return;
    doc.getPage(1).then(function (page) {
      var baseW = page.getViewport({ scale: 1 }).width;
      if (!baseW) return;
      state.zoom = Math.max(0.5, Math.min(2, avail / (baseW * 1.35)));
      applyZoom();
      state.fitted = 'width';
      renderViewer();
    });
  }
  function fitWidthIfActive() { if (state.fitted === 'width') fitWidth(); }
  var resizeTimer;
  window.addEventListener('resize', function () { clearTimeout(resizeTimer); resizeTimer = setTimeout(fitWidthIfActive, 120); });

  /* ================= Page nav ================= */
  function updateToolbar() {
    $('pageLabel').textContent = state.page + ' / ' + (state.numPages || 1);
    $('prevPage').disabled = state.page <= 1;
    $('nextPage').disabled = state.page >= (state.numPages || 1);
  }
  $('prevPage').addEventListener('click', function () { setPage(state.page - 1); });
  $('nextPage').addEventListener('click', function () { setPage(state.page + 1); });

  /* ================= View mode / side ================= */
  function setViewMode(mode) {
    if ((mode === 'compare' || mode === 'overlay') && !state.translated) return;
    state.viewMode = mode;
    body.setAttribute('data-viewmode', mode);
    document.querySelectorAll('[data-view]').forEach(function (b) { b.setAttribute('aria-checked', b.getAttribute('data-view') === mode ? 'true' : 'false'); });
    $('sideSeg').style.display = mode === 'single' ? '' : 'none';
    renderViewer();
  }
  document.querySelector('.seg[aria-label="View mode"]').addEventListener('click', function (e) {
    var b = e.target.closest('[data-view]'); if (b && !b.disabled) setViewMode(b.getAttribute('data-view'));
  });
  $('sideSeg').addEventListener('click', function (e) {
    var b = e.target.closest('[data-side]'); if (!b || b.disabled) return;
    state.side = b.getAttribute('data-side');
    this.querySelectorAll('[data-side]').forEach(function (x) { x.setAttribute('aria-checked', x === b ? 'true' : 'false'); });
    renderViewer();
  });

  $('overlayRange').addEventListener('input', function () {
    state.overlay = parseInt(this.value, 10) / 100;
    var layer = stageInner.querySelector('.overlay-layer');
    if (layer) layer.style.opacity = String(state.overlay);
  });

  /* ================= Search ================= */
  function escapeRegExp(s) { return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }

  function activeSides() {
    if (state.viewMode === 'compare' || state.viewMode === 'overlay') return state.pdf.translated ? ['source', 'translated'] : ['source'];
    return (state.side === 'translated' && state.pdf.translated) ? ['translated'] : ['source'];
  }

  function getPageText(kind, pageNum) {
    if (state.textCache[kind][pageNum]) return Promise.resolve(state.textCache[kind][pageNum]);
    var doc = state.pdf[kind];
    if (!doc) return Promise.resolve([]);
    return doc.getPage(pageNum).then(function (page) {
      return page.getTextContent();
    }).then(function (content) {
      var items = content.items.filter(function (it) { return it.str && it.str.trim(); });
      state.textCache[kind][pageNum] = items;
      return items;
    }).catch(function () { return []; });
  }

  function buildMatches(q) {
    var re = new RegExp(escapeRegExp(q), 'gi');
    var sides = activeSides();
    var tasks = [];
    for (var p = 1; p <= state.numPages; p++) {
      sides.forEach(function (side) {
        tasks.push(getPageText(side, p).then(function (items) {
          var found = [];
          items.forEach(function (item, index) {
            re.lastIndex = 0; var m;
            while ((m = re.exec(item.str)) !== null) {
              found.push({ page: p, side: side, item: index, start: m.index });
              if (m[0] === '') re.lastIndex++;
            }
          });
          return found;
        }));
      });
    }
    return Promise.all(tasks).then(function (lists) {
      return lists.reduce(function (all, list) { return all.concat(list); }, []);
    });
  }

  function drawHighlights() {
    stageInner.querySelectorAll('.pdf-hit').forEach(function (n) { n.remove(); });
    var q = state.query.trim();
    if (!q) return;
    var re = new RegExp(escapeRegExp(q), 'gi');
    var current = state.matches[state.matchIndex];
    ['source', 'translated'].forEach(function (kind) {
      var rendered = state.rendered[kind];
      if (!rendered) return;
      getPageText(kind, rendered.num).then(function (items) {
        var hits = [];
        items.forEach(function (item, index) {
          re.lastIndex = 0; var m;
          while ((m = re.exec(item.str)) !== null) {
            hits.push({ item: index, start: m.index });
            if (m[0] === '') re.lastIndex++;
          }
        });
        hits.forEach(function (hit) {
          var item = items[hit.item];
          var mtx = pdfjsLib.Util.transform(rendered.viewport.transform, item.transform);
          var box = el('span', 'pdf-hit');
          var isCurrent = current && current.page === rendered.num && current.side === kind && current.item === hit.item && current.start === hit.start;
          if (isCurrent) box.classList.add('is-current');
          var fontHeight = Math.hypot(mtx[2], mtx[3]) || 10;
          var startFraction = hit.start / Math.max(1, item.str.length);
          var matchLen = Math.min(item.str.length - hit.start, q.length);
          box.style.left = (mtx[4] + item.width * startFraction * pdfScale()) + 'px';
          box.style.top = (mtx[5] - fontHeight) + 'px';
          box.style.width = Math.max(6, item.width * (matchLen / Math.max(1, item.str.length)) * pdfScale()) + 'px';
          box.style.height = (fontHeight * 1.25) + 'px';
          rendered.pageWrap.appendChild(box);
        });
      });
    });
  }

  function applySearch() {
    var q = state.query.trim();
    if (!q) {
      state.matches = []; state.matchCount = 0; state.matchIndex = 0;
      drawHighlights();
      updateSearchUI();
      return;
    }
    buildMatches(q).then(function (matches) {
      state.matches = matches;
      state.matchCount = matches.length;
      if (state.matchIndex >= state.matchCount) state.matchIndex = 0;
      drawHighlights();
      updateSearchUI();
    });
  }

  function updateSearchUI() {
    var q = state.query.trim();
    if (!q) { $('searchCount').textContent = ''; $('searchPrev').disabled = true; $('searchNext').disabled = true; return; }
    var has = state.matchCount > 0;
    $('searchCount').textContent = (has ? state.matchIndex + 1 : 0) + '/' + state.matchCount;
    $('searchPrev').disabled = !has; $('searchNext').disabled = !has;
  }

  function gotoMatch(dir) {
    if (!state.matchCount) return;
    state.matchIndex = (state.matchIndex + dir + state.matchCount) % state.matchCount;
    var m = state.matches[state.matchIndex];
    if (m.page !== state.page) setPage(m.page, true);
    else drawHighlights();
    updateSearchUI();
    var cur = stageInner.querySelector('.pdf-hit.is-current');
    if (cur) cur.scrollIntoView({ block: 'center', behavior: 'smooth' });
  }

  var searchTimer;
  $('searchInput').addEventListener('input', function () {
    var v = this.value; clearTimeout(searchTimer);
    searchTimer = setTimeout(function () { state.query = v; state.matchIndex = 0; applySearch(); }, 160);
  });
  $('searchInput').addEventListener('keydown', function (e) {
    if (e.key === 'Enter') { e.preventDefault(); clearTimeout(searchTimer); state.query = this.value; applySearch(); setTimeout(function () { gotoMatch(e.shiftKey ? -1 : 1); }, 80); }
  });
  $('searchNext').addEventListener('click', function () { gotoMatch(1); });
  $('searchPrev').addEventListener('click', function () { gotoMatch(-1); });

  /* ================= Focus mode ================= */
  function setFocus(on) {
    state.focus = on;
    body.classList.toggle('focus-mode', on);
    $('focusBtn').setAttribute('aria-pressed', on ? 'true' : 'false');
    if (on) {
      if ($('viewer').requestFullscreen) { $('viewer').requestFullscreen().catch(function () {}); }
    } else if (document.fullscreenElement && document.exitFullscreen) {
      document.exitFullscreen().catch(function () {});
    }
    syncSidebarA11y();
    fitWidthIfActive();
  }
  $('focusBtn').addEventListener('click', function () { setFocus(true); });
  $('focusExit').addEventListener('click', function () { setFocus(false); });
  document.addEventListener('fullscreenchange', function () {
    if (!document.fullscreenElement && state.focus) { state.focus = false; body.classList.remove('focus-mode'); $('focusBtn').setAttribute('aria-pressed', 'false'); syncSidebarA11y(); fitWidthIfActive(); }
  });
  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Escape') return;
    if (body.classList.contains('drawer-open')) { closeDrawer(true); return; }
    if (state.focus && !document.fullscreenElement) setFocus(false);
  });

  /* ================= Readiness ================= */
  var translateBtn = $('translateBtn'), cancelBtn = $('cancelBtn'), actionHint = $('actionHint');
  function sourceReady() { return (state.sourceMode === 'file' && !!state.file) || (state.sourceMode === 'link' && !!$('linkInput').value.trim()); }
  function pagesReady() { return selectedPages !== 'Others' || validatePageRange(); }
  function refreshReady() {
    var ok = sourceReady() && pagesReady();
    translateBtn.disabled = !ok || state.translating;
    if (state.translating) return;
    actionHint.classList.remove('is-error');
    if (ok) actionHint.textContent = 'Ready — press Translate to start.';
    else if (!sourceReady()) actionHint.textContent = state.sourceMode === 'link' ? 'Paste a document URL to start.' : 'Add a document to start.';
    else actionHint.textContent = 'Check the page range format.';
  }
  $('linkInput').addEventListener('input', refreshReady);

  /* ================= Translate flow ================= */
  function setProgress(p) {
    p = Math.max(0, Math.min(100, p));
    $('progressFill').style.transform = 'scaleX(' + (p / 100) + ')';
    $('progressBar').setAttribute('aria-valuenow', String(Math.round(p)));
  }

  function collectEnvs() {
    var envs = {};
    document.querySelectorAll('#serviceFields [data-env-key]').forEach(function (input) {
      if (input.value) envs[input.getAttribute('data-env-key')] = input.value;
    });
    return envs;
  }

  function startTranslate() {
    if (!sourceReady()) { actionHint.textContent = 'Add a document or link first.'; actionHint.classList.add('is-error'); return; }
    if (!pagesReady()) { actionHint.textContent = 'Check the page range format.'; actionHint.classList.add('is-error'); return; }
    state.translating = true;
    translateBtn.disabled = true; cancelBtn.hidden = false;
    if (mqMobile.matches) closeDrawer(false);
    $('stageOverlay').hidden = false;
    setProgress(0);
    $('progressStatus').textContent = 'Uploading document…';

    var form = new FormData();
    if (state.sourceMode === 'file') form.append('file', state.file);
    else form.append('link', $('linkInput').value.trim());
    form.append('service', $('serviceSelect').value);
    form.append('lang_from', $('fromLang').value);
    form.append('lang_to', $('toLang').value);
    form.append('pages', selectedPages);
    form.append('page_input', pageRange.value.trim());
    form.append('threads', $('threads').value || '4');
    form.append('mode', $('transMode').value);
    form.append('skip_fonts', $('skipFont').checked ? '1' : '');
    form.append('ignore_cache', $('ignoreCache').checked ? '1' : '');
    form.append('vfont', $('vfont').value.trim());
    form.append('prompt', $('customPrompt').value);
    form.append('envs', JSON.stringify(collectEnvs()));

    fetch('/api/translate', { method: 'POST', body: form })
      .then(function (r) { return r.json().then(function (data) { return { ok: r.ok, data: data }; }); })
      .then(function (res) {
        if (!res.ok) throw new Error(res.data.error || 'Failed to start translation');
        state.jobId = res.data.job_id;
        pollJob();
      })
      .catch(function (error) { failTranslate(error.message || String(error)); });
  }

  function pollJob() {
    fetch('/api/jobs/' + state.jobId)
      .then(function (r) { return r.json(); })
      .then(function (job) {
        setProgress((job.progress || 0) * 100);
        if (job.status) $('progressStatus').textContent = job.status;
        if (job.state === 'done') { finishTranslate(job); return; }
        if (job.state === 'error') { failTranslate(job.error || 'Translation failed'); return; }
        if (job.state === 'cancelled') { cancelDone(); return; }
        state.pollTimer = setTimeout(pollJob, 600);
      })
      .catch(function () { state.pollTimer = setTimeout(pollJob, 1200); });
  }

  function enableResultControls() {
    document.querySelectorAll('[data-view]').forEach(function (b) { if (b.getAttribute('data-view') !== 'single') b.disabled = !state.isPdf; });
    document.querySelector('[data-side="translated"]').disabled = !state.isPdf;
  }

  function finishTranslate(job) {
    state.translating = false; state.translated = true;
    state.outputs = job.outputs || {};
    translateBtn.disabled = false; cancelBtn.hidden = true;
    $('stageOverlay').hidden = true;
    actionHint.textContent = 'Translation complete — compare or download.';
    actionHint.classList.remove('is-error');
    ensureDownloadButtons();
    var sourceName = (state.file && state.file.name) || (job.source_name || '');
    state.isPdf = /\.pdf$/i.test(sourceName);
    state.page = 1;
    if (!state.isPdf) {
      enableResultControls();
      setViewMode('single');
      renderViewer();
      return;
    }
    Promise.all([loadPdf('source'), loadPdf('translated')]).then(function () {
      enableResultControls();
      state.side = 'translated';
      document.querySelectorAll('[data-side]').forEach(function (x) { x.setAttribute('aria-checked', x.getAttribute('data-side') === 'translated' ? 'true' : 'false'); });
      setViewMode('compare');
      updateToolbar();
    }).catch(function (error) {
      actionHint.textContent = 'Translation finished, but preview failed: ' + error.message;
      actionHint.classList.add('is-error');
    });
  }

  function loadPdf(kind) {
    var url = '/api/jobs/' + state.jobId + '/preview/' + kind;
    return pdfjsLib.getDocument({ url: url }).promise.then(function (doc) {
      state.pdf[kind] = doc;
      if (kind === 'source') { state.numPages = doc.numPages; updateToolbar(); }
      return doc;
    });
  }

  function failTranslate(message) {
    state.translating = false; cancelBtn.hidden = true;
    $('stageOverlay').hidden = true;
    translateBtn.disabled = false;
    actionHint.textContent = message;
    actionHint.classList.add('is-error');
  }
  function cancelDone() {
    state.translating = false; cancelBtn.hidden = true;
    $('stageOverlay').hidden = true;
    refreshReady();
    actionHint.textContent = 'Translation cancelled.';
    actionHint.classList.remove('is-error');
  }
  function cancelTranslate() {
    if (!state.jobId) { cancelDone(); return; }
    fetch('/api/jobs/' + state.jobId + '/cancel', { method: 'POST' }).catch(function () {});
    $('progressStatus').textContent = 'Cancelling…';
  }
  translateBtn.addEventListener('click', startTranslate);
  cancelBtn.addEventListener('click', cancelTranslate);

  /* ================= Downloads ================= */
  function downloadOutput(kind) {
    if (!state.outputs || !state.outputs[kind]) return;
    window.location.href = '/api/jobs/' + state.jobId + '/file/' + kind;
  }
  function ensureDownloadButtons() {
    var existing = document.getElementById('dlGroup');
    if (existing) existing.remove();
    if (!state.outputs || !Object.keys(state.outputs).length) return;
    var group = el('span', 'tool-group');
    group.id = 'dlGroup';
    var labels = { mono: 'Mono', dual: 'Dual', translated: 'Translated' };
    Object.keys(state.outputs).forEach(function (kind) {
      var b = el('button', 'tool-btn'); b.type = 'button'; b.setAttribute('data-download', kind);
      b.setAttribute('aria-label', 'Download ' + (labels[kind] || kind));
      b.title = 'Download (' + (labels[kind] || kind) + ')';
      b.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v12m0 0 4-4m-4 4-4-4"/><path d="M5 21h14"/></svg>';
      b.addEventListener('click', function () { downloadOutput(kind); });
      group.appendChild(b);
    });
    document.querySelector('.viewer__toolbar').appendChild(group);
  }

  /* ================= Radio-group keyboard support ================= */
  function enableRadioKeys(container) {
    if (!container) return;
    container.addEventListener('keydown', function (e) {
      if (['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].indexOf(e.key) === -1) return;
      var btns = Array.prototype.slice.call(container.querySelectorAll('[role="radio"]:not([disabled])'));
      if (!btns.length) return;
      var i = btns.indexOf(document.activeElement);
      if (i === -1) return;
      e.preventDefault();
      var dir = (e.key === 'ArrowRight' || e.key === 'ArrowDown') ? 1 : -1;
      var next = btns[(i + dir + btns.length) % btns.length];
      next.focus(); next.click();
    });
  }
  enableRadioKeys(document.querySelector('.seg[aria-label="Input type"]'));
  enableRadioKeys(document.querySelector('.seg[aria-label="View mode"]'));
  enableRadioKeys($('sideSeg'));
  enableRadioKeys(document.querySelector('.choice-group[aria-label="Pages to translate"]'));

  /* ================= Init ================= */
  fetch('/api/meta').then(function (r) { return r.json(); }).then(function (meta) {
    state.meta = meta;
    $('appVersion').textContent = 'v' + meta.version;
    if (meta.babeldoc_version) $('babeldocVersion').textContent = 'v' + meta.babeldoc_version;
    fillLanguages($('fromLang'), meta.defaults.lang_from);
    fillLanguages($('toLang'), meta.defaults.lang_to);
    fillServices();
    renderViewer();
    refreshReady();
  }).catch(function () {
    actionHint.textContent = 'Cannot reach the pdf2zh server.';
    actionHint.classList.add('is-error');
  });
  applyZoom();
  updateToolbar();
  syncScrim();
  syncSidebarExpanded();
  syncSidebarA11y();
})();
