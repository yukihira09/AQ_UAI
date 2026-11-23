import { RequestError } from './api.mjs';

let fieldId = 0;

export function el(tag, attributes = {}, ...children) {
  const node = document.createElement(tag);
  for (const [name, value] of Object.entries(attributes)) {
    if (value === undefined || value === null || value === false) continue;
    if (name.startsWith('on')) node.addEventListener(name.slice(2), value);
    else node.setAttribute(name, value === true ? '' : value);
  }
  node.append(...children.flat(Infinity).filter(value => value !== undefined && value !== null && value !== false));
  return node;
}

export function button(title, action, kind = 'secondary') {
  return el('button', { type: 'button', class: `button ${kind}`, onclick: action }, title);
}

export function link(title, route) {
  return el('a', { href: `#${route}`, class: 'record-link' }, title);
}

export function panel(title, ...content) {
  return el('section', { class: 'panel' }, el('h2', {}, title), content);
}

export function actions(...items) {
  return el('div', { class: 'actions' }, items);
}

export function facts(rows) {
  return el('dl', { class: 'facts' }, rows.flatMap(([key, value]) => [
    el('dt', {}, key), el('dd', {}, value ?? '—'),
  ]));
}

export function table(headers, rows) {
  if (rows.length === 0) return el('p', { class: 'empty' }, 'Không tìm thấy bản ghi phù hợp.');
  return el('div', { class: 'table-scroll', tabindex: '0', role: 'region', 'aria-label': 'Bảng kết quả' },
    el('table', {}, el('thead', {}, el('tr', {}, headers.map(title => el('th', { scope: 'col' }, title)))),
      el('tbody', {}, rows.map(row => el('tr', {}, row.map(value => el('td', {}, value ?? '—')))))));
}

export function badge(text, theme = 'blue') {
  return el('span', { class: `badge ${theme}` }, text);
}

const localTime = new Intl.DateTimeFormat('vi-VN', { dateStyle: 'medium', timeStyle: 'medium' });
export function dateLabel(value) {
  return value ? localTime.format(new Date(value)) : '—';
}

export function showError(target, error, conflict) {
  const message = error.status === 409 && conflict ? conflict
    : error instanceof RequestError ? error.message : 'Không thể hoàn thành thao tác.';
  target.replaceChildren(el('p', {}, message));
  if (error.requestId) target.append(el('small', {}, `Mã yêu cầu ${error.requestId}`));
  target.hidden = false;
}

export function option(value, label) {
  return el('option', { value }, label);
}

export function field({ name, label, type = 'text', value = '', options, required, max, min, pattern, autocomplete, hint }) {
  const id = `field-${++fieldId}`;
  const common = { id, name, required, autocomplete, 'aria-describedby': hint ? `${id}-hint` : undefined };
  const input = options
    ? el('select', common, options.map(([key, title]) => option(key, title)))
    : el('input', { ...common, type, maxlength: max, minlength: min, pattern });
  input.value = value ?? '';
  return el('div', { class: 'field' }, el('label', { for: id }, label), input,
    hint && el('small', { id: `${id}-hint`, class: 'hint' }, hint));
}

export function submitForm(form, submit, errorBox, onSubmit, conflict) {
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (submit.disabled) return;
    const payload = Object.fromEntries(new FormData(form));
    submit.disabled = true;
    form.setAttribute('aria-busy', 'true');
    errorBox.hidden = true;
    try {
      await onSubmit(payload, form);
    } catch (error) {
      if (error.name !== 'AbortError') showError(errorBox, error, conflict);
    } finally {
      delete payload.password;
      delete payload.current_password;
      delete payload.new_password;
      delete payload.confirmation;
      delete payload.temporary_password;
      form.querySelectorAll('input[type="password"]').forEach(input => { input.value = ''; });
      form.removeAttribute('aria-busy');
      submit.disabled = false;
    }
  });
}

export function formDialog(context, { title, description, fields = [], submit = 'Lưu thay đổi', danger, conflict, save }) {
  const error = el('div', { class: 'alert', role: 'alert', hidden: true });
  const submitButton = el('button', { type: 'submit', class: `button ${danger ? 'danger' : 'primary'}` }, submit);
  const dialog = el('dialog', { 'aria-labelledby': 'dialog-title' });
  const cancel = button('Hủy', () => dialog.close());
  const form = el('form', { class: 'dialog-content' }, el('h2', { id: 'dialog-title' }, title),
    description && el('p', { class: 'muted' }, description), fields, error, actions(cancel, submitButton));
  dialog.append(form);
  dialog.addEventListener('close', () => dialog.remove());
  dialog.addEventListener('cancel', event => { if (form.hasAttribute('aria-busy')) event.preventDefault(); });
  submitForm(form, submitButton, error, async values => {
    cancel.disabled = true;
    try {
      await save(values);
      dialog.close();
      if (context.current()) await context.updated();
    } finally {
      cancel.disabled = false;
    }
  }, conflict);
  context.content.append(dialog);
  dialog.showModal();
}

export function pager(result, change) {
  const { total, limit, offset, items } = result;
  const label = items.length ? `${offset + 1}–${offset + items.length} / ${total} bản ghi` : `0 / ${total} bản ghi`;
  const previous = button('Trang trước', () => change(Math.max(0, offset - limit)));
  const next = button('Trang sau', () => change(offset + limit));
  previous.disabled = offset === 0;
  next.disabled = offset + limit >= total || offset + limit > 100000;
  return el('div', { class: 'pagination' }, el('p', {}, label), actions(previous, next));
}

export function listing(context, { path, heading, filters = [], headers, row, query = {}, toolbar = [] }) {
  const area = el('div', { class: 'list-results' });
  const apply = el('button', { type: 'submit', class: 'button secondary' }, 'Áp dụng');
  const filterForm = el('form', { class: 'filters' }, filters, apply);
  const section = el('section', { class: 'panel' }, heading && el('h2', {}, heading),
    toolbar.length > 0 && actions(toolbar), filters.length > 0 && filterForm, area);
  let latest = 0;
  let activeQuery = query;

  async function load(targetOffset) {
    const sequence = ++latest;
    area.setAttribute('aria-busy', 'true');
    area.replaceChildren(el('p', { role: 'status', class: 'muted' }, 'Đang tải dữ liệu…'));
    try {
      const result = await context.read(path, { ...activeQuery, limit: 10, offset: targetOffset });
      if (sequence !== latest || !context.current()) return;
      area.replaceChildren(table(headers, result.items.map(row)), pager(result, load));
    } catch (error) {
      if (sequence !== latest || !context.current() || error.name === 'AbortError') return;
      const alert = el('div', { class: 'alert', role: 'alert' });
      showError(alert, error);
      area.replaceChildren(alert, button('Thử tải lại', () => load(targetOffset)));
    } finally {
      if (sequence === latest) area.removeAttribute('aria-busy');
    }
  }

  filterForm.addEventListener('submit', event => {
    event.preventDefault();
    activeQuery = { ...query, ...Object.fromEntries(new FormData(filterForm)) };
    for (const input of filterForm.querySelectorAll('input[type="datetime-local"]')) {
      if (!input.value) continue;
      const time = new Date(input.value);
      if (!Number.isFinite(time.getTime()) || !/^\d{4}-/.test(input.value)) {
        latest += 1;
        area.removeAttribute('aria-busy');
        area.replaceChildren(el('p', { class: 'alert', role: 'alert' }, 'Hãy chọn thời điểm có năm từ 0001 đến 9999.'));
        return;
      }
      activeQuery[input.name] = time.toISOString();
    }
    load(0);
  });
  load(0);
  return section;
}

export function reference(context, { name, label, resource, query = {}, title, required = true }) {
  const wrapper = field({ name, label, options: [['', '— Chọn —']], required });
  const select = wrapper.querySelector('select');
  const searchField = field({ name: '', label: `Tìm trong ${label.toLowerCase()}`, type: 'search', max: 128 });
  const search = searchField.querySelector('input');
  const status = el('p', { class: 'hint', role: 'status' });
  let offset = 0;
  let sequence = 0;
  let selected;
  const previous = button('Trước', () => load(Math.max(0, offset - 10)));
  const next = button('Sau', () => load(offset + 10));
  const find = button('Tìm', () => load(0));
  const lookup = el('details', { class: 'reference-options' },
    el('summary', {}, 'Tìm hoặc xem thêm'),
    el('div', { class: 'reference-search' }, searchField, find),
    actions(previous, next, status));
  wrapper.append(lookup);

  select.addEventListener('change', () => {
    selected = select.value ? [select.value, select.selectedOptions[0].textContent] : undefined;
  });
  search.addEventListener('keydown', event => {
    if (event.key === 'Enter') {
      event.preventDefault();
      load(0);
    }
  });

  async function load(targetOffset) {
    const current = ++sequence;
    previous.disabled = next.disabled = true;
    status.textContent = 'Đang tải lựa chọn…';
    try {
      const result = await context.read(resource, { ...query, q: search.value, limit: 10, offset: targetOffset });
      if (current !== sequence || !context.current()) return;
      offset = result.offset;
      const options = result.items.map(item => option(item.id, title(item)));
      if (selected && !result.items.some(item => item.id === selected[0])) options.unshift(option(...selected));
      select.replaceChildren(option('', required ? '— Chọn —' : 'Tất cả'), ...options);
      select.value = selected?.[0] ?? '';
      previous.disabled = offset === 0;
      next.disabled = offset + result.limit >= result.total || offset + result.limit > 100000;
      status.textContent = `${result.total} lựa chọn`;
    } catch (error) {
      if (current === sequence && context.current() && error.name !== 'AbortError') {
        lookup.open = true;
        showError(status, error);
      }
    }
  }

  load(0);
  return wrapper;
}
