(() => {
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  // ----- View tab switching
  const viewBtns = $$('.vt');
  const viewSecs = $$('.view');
  viewBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      const target = btn.dataset.view;
      viewBtns.forEach(b => b.classList.toggle('active', b === btn));
      viewSecs.forEach(s => s.classList.toggle('active', s.dataset.view === target));
    });
  });

  // ----- Day toggle (Day 1 / Day 2)
  const dayBtns = $$('.day-btn');
  function setDay(day) {
    dayBtns.forEach(b => b.classList.toggle('active', b.dataset.day === day));
    // Toggle .post-body[data-day]
    $$('[data-day]').forEach(el => {
      if (!el.dataset.day) return;
      el.hidden = el.dataset.day !== day;
    });
    // Toggle [data-day-only]
    $$('[data-day-only]').forEach(el => {
      el.hidden = el.dataset.dayOnly !== day;
    });
  }
  dayBtns.forEach(btn => btn.addEventListener('click', () => setDay(btn.dataset.day)));

  // ----- Diff line coloring on .code-pre.diff
  // Wrap leading +/-/space lines with span classes.
  $$('.code-pre.diff').forEach(pre => {
    const html = pre.innerHTML;
    const lines = html.split('\n').map(line => {
      // skip if already wrapped
      if (/^<span/.test(line)) return line;
      const m = line.match(/^(\s*)([-+])(.*)$/);
      if (!m) return line;
      const [, lead, sign, rest] = m;
      const cls = sign === '+' ? 'diff-add' : 'diff-del';
      return `${lead}<span class="${cls}">${sign}${rest}</span>`;
    });
    pre.innerHTML = lines.join('\n');
  });
})();
