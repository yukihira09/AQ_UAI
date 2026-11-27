import { createClient, RequestError } from './api.mjs';
import { tabs as mdlTabs } from './mdl.mjs';
import { pageContent, sections } from './pages.mjs';
import { tabs as qtaTabs } from './qta.mjs';
import { actions, button, el, field, showError, submitForm } from './ui.mjs';

const root = document.querySelector('#application');
const client = createClient(() => toLogin('Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.'));
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const passwordHint = 'Dùng từ 12 đến 128 ký tự.';
let me;
let shell;
let navigation;
let viewVersion = 0;

function brand() {
  return el('div', { class: 'brand' }, el('span', { class: 'brand-mark', 'aria-hidden': 'true' }, 'AQ'),
    el('div', {}, el('strong', {}, 'AQ EduUAI'), el('small', {}, 'Quản trị hệ thống')));
}

function stopView() {
  viewVersion += 1;
  navigation?.abort();
}

function toLogin(message) {
  stopView();
  client.setProof(undefined);
  me = shell = undefined;
  history.replaceState(null, '', '/');
  authPage(false, message);
}

function logoutControl(onError) {
  const logout = button('Đăng xuất', async () => {
    logout.disabled = true;
    try {
      await client.request('/auth/logout', { method: 'POST' });
      toLogin('Bạn đã đăng xuất.');
    } catch (error) {
      if (error.status !== 401) onError(error);
    } finally {
      logout.disabled = false;
    }
  });
  return logout;
}

function authPage(restricted, message) {
  const error = el('div', { class: 'alert', role: 'alert', hidden: true });
  const title = restricted ? 'Đổi mật khẩu' : 'Đăng nhập';
  const submit = el('button', { type: 'submit', class: 'button primary' }, restricted ? 'Lưu mật khẩu' : 'Đăng nhập');
  const pass = (name, label, autocomplete, min) => field({
    name, label, autocomplete, min, type: 'password', max: 128, required: true,
  });
  const fields = restricted ? [pass('current_password', 'Mật khẩu hiện tại', 'current-password'),
    pass('new_password', 'Mật khẩu mới', 'new-password', 12),
    pass('confirmation', 'Xác nhận mật khẩu mới', 'new-password', 12)] : [
    field({ name: 'username', label: 'Tên đăng nhập', required: true, max: 256, autocomplete: 'username' }),
    pass('password', 'Mật khẩu', 'current-password'),
  ];
  const form = el('form', { class: 'auth-form' }, fields, error, submit);
  submitForm(form, submit, error, async values => {
    if (restricted) {
      if (values.new_password !== values.confirmation) {
        throw new RequestError(422, null, 'Hai mật khẩu mới chưa trùng khớp.');
      }
      try {
        await client.request('/auth/change-password', { method: 'POST', body: {
          current_password: values.current_password, new_password: values.new_password,
        } });
      } catch (error) {
        if (error.status !== 401) throw error;
        // WP3 uses 401 for an incorrect current password and for an invalid session.
        const identity = await client.request('/auth/me');
        if (identity.id !== me?.id || !identity.must_change_password) {
          await presentIdentity(identity, true);
          return;
        }
        updateIdentity(identity);
        throw new RequestError(401, error.requestId, 'Mật khẩu hiện tại không đúng.');
      }
      toLogin('Đã đổi mật khẩu. Hãy đăng nhập bằng mật khẩu mới.');
    } else {
      await client.request('/auth/login', { method: 'POST', body: values });
      await restore();
    }
  });
  root.replaceChildren(el('main', { class: 'auth-screen' }, el('div', { class: 'auth-card' }, brand(),
    el('h1', {}, title), el('p', { class: 'muted' }, restricted
      ? `Bạn cần đổi mật khẩu tạm thời trước khi tiếp tục. ${passwordHint}`
      : 'Đăng nhập bằng tài khoản do trường cấp.'),
    message && el('p', { class: 'notice', role: 'status' }, message), form,
    restricted && actions(logoutControl(failure => showError(error, failure))))));
  document.title = `${title} · AQ EduUAI`;
  fields[0].querySelector('input').focus();
}

function initializeShell() {
  const notice = el('div', { class: 'notice', role: 'status', hidden: true });
  const error = el('div', { class: 'alert', role: 'alert', hidden: true });
  const title = el('h1', { tabindex: '-1' }, 'Tổng quan');
  const content = el('div', { class: 'content' });
  const nav = el('nav', { id: 'main-navigation', 'aria-label': 'Quản trị' });
  const sidebar = el('aside', { class: 'sidebar' }, brand(), nav);
  const menuToggle = button('Danh mục', () => {
    menuToggle.setAttribute('aria-expanded', String(sidebar.classList.toggle('open')));
  });
  menuToggle.classList.add('menu-toggle');
  menuToggle.setAttribute('aria-controls', 'main-navigation');
  menuToggle.setAttribute('aria-expanded', 'false');
  const avatar = el('span', { class: 'avatar', 'aria-hidden': 'true' });
  const sessionName = el('span', { class: 'session-name' });
  const sessionUsername = el('p');
  const session = el('details', { class: 'session' }, el('summary', { 'aria-label': 'Phiên đăng nhập' }, avatar, sessionName),
    el('div', { class: 'session-menu' }, sessionUsername, logoutControl(failure => showError(error, failure))));
  root.replaceChildren(el('div', { class: 'shell' }, sidebar, el('div', { class: 'workspace' },
    el('header', { class: 'topbar' }, el('div', { class: 'topbar-heading' }, menuToggle, title), session),
    el('main', { class: 'main' }, notice, error, content))));
  shell = { nav, content, session, sidebar, menuToggle, title, notice, error, avatar, sessionName, sessionUsername };
  renderIdentity();
}

function currentRoute() {
  const hash = location.hash.slice(1);
  if (!hash) return ['home'];
  const [route, id, ...rest] = hash.split('/');
  if (route === 'mdl') {
    // #mdl, #mdl/<tab>, #mdl/providers/<uuid>, #mdl/models/<uuid>
    const [detail, ...extra] = rest;
    if (extra.length || (id !== undefined && !Object.hasOwn(mdlTabs, id)) ||
      (detail !== undefined && (!['providers', 'models'].includes(id) || !uuid.test(detail)))) return [];
    return [route, id, detail];
  }
  if (route === 'qta') {
    // #qta, #qta/<tab>, #qta/groups/<uuid>
    const [detail, ...extra] = rest;
    if (extra.length || (id !== undefined && !Object.hasOwn(qtaTabs, id)) ||
      (detail !== undefined && (id !== 'groups' || !uuid.test(detail)))) return [];
    return [route, id, detail];
  }
  if (!Object.hasOwn(sections, route) || rest.length || (id !== undefined &&
    (!['users', 'units', 'groups', 'audit'].includes(route) || !uuid.test(id)))) return [];
  return [route, id];
}

async function renderView(focus = false) {
  if (!shell || !me || me.must_change_password) return;
  stopView();
  const version = viewVersion;
  const activeShell = shell;
  const controller = new AbortController();
  navigation = controller;
  const current = () => viewVersion === version && shell === activeShell;
  const read = (path, query) => client.request(path, { query, signal: controller.signal });
  const [route, id, detail] = currentRoute();
  shell.sidebar.classList.remove('open');
  shell.menuToggle.setAttribute('aria-expanded', 'false');
  shell.session.open = false;
  shell.error.hidden = true;
  if (focus) shell.notice.hidden = true;
  shell.content.setAttribute('aria-busy', 'true');
  shell.content.replaceChildren(el('p', { class: 'panel', role: 'status' }, 'Đang tải dữ liệu…'));
  try {
    const identity = await read('/auth/me');
    if (!current()) return;
    if (identity.id !== me.id || identity.must_change_password) {
      await presentIdentity(identity, true);
      return;
    }
    updateIdentity(identity);
    const caps = await read('/directory/capabilities');
    if (!current()) return;
    shell.nav.replaceChildren(...Object.entries(sections).filter(([, section]) => section.visible(caps)).map(([key, section]) =>
      el('a', { href: key === 'home' ? '#home' : `#${key}`, 'aria-current': key === route ? 'page' : undefined },
        el('span', { 'aria-hidden': 'true', class: 'nav-icon' }, section.icon), section.title)));
    if (!route) throw new RequestError(404, null, 'Trang quản trị này không tồn tại.');
    if (!sections[route].visible(caps)) throw new RequestError(403, null);
    shell.title.textContent = sections[route].title;
    document.title = `${sections[route].title} · AQ EduUAI`;
    if (focus) shell.title.focus();
    const rendered = await pageContent({ caps, me, current, read, content: shell.content,
      write: (path, options) => client.request(path, options),
      updated: async message => {
        if (!current()) return;
        shell.notice.textContent = message ?? 'Đã lưu thay đổi.';
        shell.notice.hidden = false;
        await renderView();
      },
    }, route, id, detail);
    if (current()) shell.content.replaceChildren(...[rendered].flat(Infinity).filter(Boolean));
  } catch (error) {
    if (!current() || error.name === 'AbortError') return;
    const alert = el('div', { class: 'alert', role: 'alert' });
    showError(alert, error);
    if (!route) shell.title.textContent = 'Không tìm thấy trang';
    shell.content.replaceChildren(el('div', { class: 'panel' }, alert,
      error.status === 403 || error.status === 404
        ? el('a', { class: 'button secondary', href: '#home' }, 'Về tổng quan')
        : button('Thử tải lại', () => renderView(true))));
  } finally {
    if (current()) shell.content.removeAttribute('aria-busy');
  }
}

function updateIdentity(identity) {
  const { csrf_token: token, ...profile } = identity;
  me = profile;
  client.setProof(token);
  if (shell) renderIdentity();
}

function renderIdentity() {
  shell.avatar.textContent = me.display_name.trim().slice(0, 1).toLocaleUpperCase('vi') || 'A';
  shell.sessionName.textContent = me.display_name;
  shell.sessionUsername.textContent = me.username;
}

async function presentIdentity(identity, resetRoute = false) {
  stopView();
  shell = undefined;
  updateIdentity(identity);
  if (resetRoute || me.must_change_password) history.replaceState(null, '', '/');
  if (me.must_change_password) {
    authPage(true);
  } else {
    initializeShell();
    await renderView();
  }
}

async function restore() {
  let identity;
  try {
    identity = await client.request('/auth/me');
  } catch (error) {
    if (error.status === 401) {
      toLogin();
      return;
    }
    const alert = el('div', { class: 'alert', role: 'alert' });
    showError(alert, error);
    root.replaceChildren(el('main', { class: 'auth-screen' }, el('div', { class: 'auth-card' }, brand(), alert,
      button('Thử tải lại', restore))));
    return;
  }
  await presentIdentity(identity);
}

window.addEventListener('hashchange', () => renderView(true));
document.addEventListener('visibilitychange', async () => {
  if (document.visibilityState !== 'visible' || !me) return;
  const version = viewVersion;
  try {
    const identity = await client.request('/auth/me');
    if (version !== viewVersion) return;
    if (identity.id !== me.id || identity.must_change_password !== me.must_change_password) {
      await presentIdentity(identity, true);
    } else {
      updateIdentity(identity);
    }
  } catch (error) {
    if (version === viewVersion && shell) showError(shell.error, error);
  }
});
window.addEventListener('pageshow', event => {
  if (event.persisted) {
    stopView();
    client.setProof(undefined);
    me = shell = undefined;
    root.replaceChildren(el('p', { class: 'initial-state' }, 'Đang kiểm tra phiên đăng nhập…'));
    restore();
  }
});
restore();
