import { hasScope, permission } from './api.mjs';
import { mdlPage } from './mdl.mjs';
import { qtaPage } from './qta.mjs';
import { actions, badge, button, dateLabel, el, facts, field, formDialog, link, listing, panel, reference, showError } from './ui.mjs';

const labels = {
  PENDING: 'Chờ kích hoạt', ACTIVE: 'Đang hoạt động', DISABLED: 'Đã vô hiệu hóa',
  STAFF: 'Nhân sự', STUDENT: 'Sinh viên', SYSTEM: 'Hệ thống', AUTHORIZATION: 'Phân quyền',
  AI_SPECIALIST: 'AI chuyên biệt', GLOBAL: 'Toàn trường', UNIT: 'Một đơn vị',
  SUCCESS: 'Thành công', FAILURE: 'Thất bại', USER: 'Tài khoản', GROUP: 'Nhóm tài khoản',
};

const actionsLabel = {
  'user.created': 'Tạo tài khoản', 'user.profile_updated': 'Cập nhật hồ sơ',
  'user.identity_updated': 'Cập nhật định danh', 'user.transferred': 'Chuyển đơn vị',
  'user.state_changed': 'Đổi trạng thái tài khoản', 'unit.created': 'Tạo đơn vị',
  'unit.updated': 'Cập nhật đơn vị', 'unit.state_changed': 'Đổi trạng thái đơn vị',
  'group.created': 'Tạo nhóm', 'group.updated': 'Cập nhật nhóm', 'group.state_changed': 'Đổi trạng thái nhóm',
  'membership.state_changed': 'Đổi trạng thái thành viên', 'role_assignment.created': 'Cấp vai trò',
  'role_assignment.removed': 'Thu hồi vai trò', 'auth.login_rejected': 'Đăng nhập bị từ chối',
  'auth.login_succeeded': 'Đăng nhập', 'auth.logout': 'Đăng xuất', 'auth.password_changed': 'Đổi mật khẩu',
  'auth.operator_reset': 'Khôi phục mật khẩu', 'auth.admin_bootstrapped': 'Khởi tạo quản trị viên',
  'mdl.provider_created': 'Thêm nhà cung cấp AI', 'mdl.provider_updated': 'Cập nhật nhà cung cấp AI',
  'mdl.provider_state_changed': 'Đổi trạng thái nhà cung cấp AI', 'mdl.provider_credential_rotated': 'Thay bí mật kết nối',
  'mdl.agreement_recorded': 'Ghi nhận thỏa thuận dữ liệu', 'mdl.agreement_withdrawn': 'Thu hồi thỏa thuận dữ liệu',
  'mdl.model_created': 'Thêm mô hình AI', 'mdl.model_updated': 'Cập nhật mô hình AI',
  'mdl.model_state_changed': 'Đổi trạng thái mô hình AI', 'mdl.model_risk_changed': 'Đổi mức rủi ro mô hình',
  'mdl.model_connection_tested': 'Thử kết nối mô hình AI', 'mdl.routing_changed': 'Đổi mô hình chính / dự phòng',
  'mdl.credential_rewrapped': 'Mã hóa lại bí mật kết nối (xoay khóa)',
  'qta.monthly_budget_set': 'Cập nhật tổng hạn mức tháng', 'qta.groups_synced': 'Đồng bộ nhóm tài khoản vào hạn mức AI',
  'qta.group_quota_updated': 'Cập nhật hạn mức nhóm × mô hình', 'qta.user_suspended': 'Cắt / ngưng hạn mức cá nhân',
  'qta.user_restored': 'Khôi phục hạn mức cá nhân', 'qta.monthly_reset_executed': 'Làm mới hạn mức đầu tháng',
  'qta.monthly_reset_scheduled': 'Làm mới hạn mức đầu tháng (tự động)',
};

const permissions = {
  'directory.read': 'Xem danh bạ', 'directory.profile.update': 'Sửa tên hiển thị',
  'directory.manage': 'Quản lý danh bạ', 'authorization.manage': 'Quản lý phân quyền', 'audit.read': 'Xem nhật ký',
  'mdl.read': 'Xem cấu hình mô hình AI', 'mdl.manage': 'Quản lý nhà cung cấp & mô hình AI',
  'qta.read': 'Xem hạn mức AI theo nhóm', 'qta.manage': 'Quản lý hạn mức AI & cắt / khôi phục',
};

export const sections = {
  home: { title: 'Tổng quan', icon: '⌂', visible: () => true },
  users: { title: 'Tài khoản', icon: '◎', visible: caps => hasScope(caps, 'directory.read') },
  units: { title: 'Đơn vị', icon: '▦', visible: caps => hasScope(caps, 'directory.read') },
  groups: { title: 'Nhóm tài khoản', icon: '◫', visible: caps => permission(caps, 'directory.read') },
  roles: { title: 'Vai trò', icon: '◇', visible: caps => permission(caps, 'authorization.manage') },
  audit: { title: 'Nhật ký', icon: '≡', visible: caps => permission(caps, 'audit.read') },
  mdl: { title: 'Cấu hình Nhà cung cấp & Mô hình AI', icon: '✦', visible: caps => permission(caps, 'mdl.read') },
  qta: { title: 'Hạn mức AI theo Nhóm tài khoản', icon: '◧', visible: caps => hasScope(caps, 'qta.read') },
};

const types = ['STAFF', 'STUDENT'];
const states = ['ACTIVE', 'PENDING', 'DISABLED'];
const kinds = ['SYSTEM', 'AUTHORIZATION', 'AI_SPECIALIST'];
const enumOptions = values => values.map(value => [value, labels[value] ?? value]);
const all = options => [['', 'Tất cả'], ...options];
const activeOptions = all([['true', 'Đang hoạt động'], ['false', 'Ngừng hoạt động']]);
const search = () => field({ name: 'q', label: 'Tìm kiếm', type: 'search', max: 128 });
const nameField = (value, name = 'name', label = 'Tên') => field({ name, label, value, required: true, max: 255 });
const codeField = (value, name = 'code', label = 'Mã') => field({ name, label, value, required: true, max: 64 });
const passwordField = () => field({
  name: 'temporary_password', label: 'Mật khẩu tạm thời', type: 'password', min: 12, max: 128,
  autocomplete: 'new-password', hint: '12–128 ký tự. Chia sẻ riêng với người dùng nếu đã cấp.',
});
const usernameField = value => field({
  name: 'username', label: 'Tên đăng nhập', value, required: true, max: 64,
  pattern: '[a-zA-Z0-9][a-zA-Z0-9._\\-]{0,63}', autocomplete: 'off',
  hint: 'Dùng chữ cái Latin, chữ số, dấu chấm, gạch dưới hoặc gạch nối.',
});
const codeType = value => field({ name: 'code_type', label: 'Loại định danh', options: enumOptions(types), value, required: true });
const activeBadge = active => badge(active ? 'Đang hoạt động' : 'Ngừng hoạt động', active ? 'green' : 'neutral');
const stateBadge = state => badge(labels[state], state === 'ACTIVE' ? 'green' : state === 'PENDING' ? 'amber' : 'neutral');
const unitTitle = unit => `${unit.code} · ${unit.name}`;
const unitSelect = (context, name, label, active = true, required = true) => reference(context, {
  name, label, resource: '/units', title: unitTitle, query: active ? { active: true } : {}, required,
});

function clean(values) {
  return Object.fromEntries(Object.entries(values)
    .map(([key, value]) => [key, key === 'temporary_password' ? value : value.trim()])
    .filter(([, value]) => value !== ''));
}

function formAction(context, label, path, settings = {}) {
  const { method = 'POST', title = label, fields, description, submit, danger, conflict, transform = clean } = settings;
  return button(label, () => formDialog(context, {
    title, description, fields: fields?.(), submit, danger, conflict,
    save: values => context.write(path, { method, body: fields ? transform(values) : undefined }),
  }), danger ? 'danger-outline' : settings.primary ? 'primary' : 'secondary');
}

function accountFields(context, user) {
  return [usernameField(user?.username), codeType(user?.code_type ?? 'STAFF'),
    codeField(user?.institutional_code, 'institutional_code', 'Mã định danh'),
    !user && nameField('', 'display_name', 'Tên hiển thị'),
    !user && unitSelect(context, 'primary_unit_id', 'Đơn vị chính'), !user && passwordField()];
}

function users(context) {
  const create = permission(context.caps, 'directory.manage') && formAction(context, 'Tạo tài khoản', '/users', {
    fields: () => accountFields(context), primary: true, submit: 'Tạo tài khoản',
    description: 'Để trống mật khẩu để tạo tài khoản chờ kích hoạt.',
    conflict: 'Tên đăng nhập hoặc mã định danh đã được sử dụng, hoặc đơn vị không còn hoạt động.',
  });
  return listing(context, {
    path: '/users', toolbar: create ? [create] : [],
    filters: [search(), unitSelect(context, 'primary_unit_id', 'Đơn vị chính', false, false),
      field({ name: 'state', label: 'Trạng thái', options: all(enumOptions(states)) }),
      field({ name: 'code_type', label: 'Loại định danh', options: all(enumOptions(types)) })],
    headers: ['Tên hiển thị', 'Tên đăng nhập', 'Mã định danh', 'Trạng thái'],
    row: user => [link(user.display_name, `users/${user.id}`), user.username,
      `${user.institutional_code} · ${labels[user.code_type]}`, stateBadge(user.state)],
  });
}

async function userDetail(context, id) {
  const path = `/users/${id}`;
  const user = await context.read(path);
  if (!context.current()) return;
  const controls = [];
  if (permission(context.caps, 'directory.profile.update', user.primary_unit_id)) {
    controls.push(formAction(context, 'Sửa hồ sơ', `${path}/profile`, {
      method: 'PATCH', fields: () => [nameField(user.display_name, 'display_name', 'Tên hiển thị')],
    }));
  }
  if (permission(context.caps, 'directory.manage')) {
    controls.push(formAction(context, 'Sửa định danh', `${path}/identity`, {
      method: 'PATCH', fields: () => accountFields(context, user),
      description: 'Đổi tên đăng nhập sẽ kết thúc các phiên đăng nhập hiện tại của tài khoản.',
      conflict: 'Tên đăng nhập hoặc mã định danh đã được sử dụng.',
    }));
    if (user.state !== 'ACTIVE') controls.push(formAction(context, 'Kích hoạt tài khoản', `${path}/activate`, {
      fields: () => [passwordField()], submit: 'Kích hoạt',
      description: 'Nhập mật khẩu tạm nếu tài khoản chưa từng được cấp mật khẩu. Tài khoản đã có mật khẩu sẽ tiếp tục dùng mật khẩu đó.',
      conflict: 'Kiểm tra trạng thái tài khoản, đơn vị chính và việc tài khoản đã được cấp mật khẩu hay chưa.',
    }));
    if (user.state !== 'DISABLED') controls.push(formAction(context, 'Vô hiệu hóa tài khoản', `${path}/disable`, {
      danger: true, submit: 'Vô hiệu hóa', description: 'Kết thúc tất cả phiên đăng nhập và giữ lịch sử của tài khoản này?',
      conflict: 'Không thể vô hiệu hóa tài khoản. Trường phải giữ ít nhất một quản trị viên có thể đăng nhập.',
    }));
    controls.push(formAction(context, 'Chuyển đơn vị', `${path}/transfer`, {
      fields: () => [unitSelect(context, 'primary_unit_id', 'Đơn vị mới')], submit: 'Xác nhận chuyển',
      description: 'Việc chuyển đơn vị giữ nguyên tài khoản, nhóm và phạm vi vai trò đã cấp.',
      conflict: 'Hãy chọn một đơn vị khác đang hoạt động.',
    }));
  }
  return [link('← Danh sách tài khoản', 'users'), panel(user.display_name, stateBadge(user.state), facts([
    ['Tên đăng nhập', user.username], ['Mã định danh', `${user.institutional_code} · ${labels[user.code_type]}`],
    ['Đơn vị chính', link(user.primary_unit_id, `units/${user.primary_unit_id}`)], ['ID tài khoản', user.id],
    ['Cập nhật', dateLabel(user.updated_at)],
  ]), actions(controls)), permission(context.caps, 'authorization.manage') && assignments(context, path)];
}

function nameCodeFields(item) {
  return [codeField(item?.code), nameField(item?.name)];
}

function units(context) {
  const create = permission(context.caps, 'directory.manage') && formAction(context, 'Tạo đơn vị', '/units', {
    fields: () => nameCodeFields(), primary: true, submit: 'Tạo đơn vị', conflict: 'Mã đơn vị đã được sử dụng.',
  });
  return listing(context, {
    path: '/units', filters: [search(), field({ name: 'active', label: 'Trạng thái', options: activeOptions })],
    headers: ['Mã', 'Tên đơn vị', 'Trạng thái'], toolbar: create ? [create] : [],
    row: unit => [unit.code, link(unit.name, `units/${unit.id}`), activeBadge(unit.active)],
  });
}

function activeAction(context, path, active, subject, conflict) {
  return formAction(context, active ? 'Ngừng hoạt động' : 'Kích hoạt', `${path}/${active ? 'deactivate' : 'activate'}`, {
    title: active ? `Ngừng hoạt động ${subject}` : `Kích hoạt ${subject}`,
    description: active ? 'Bản ghi và lịch sử vẫn được giữ lại. Xác nhận ngừng hoạt động?' : 'Xác nhận cho hoạt động trở lại?',
    danger: active, submit: active ? 'Ngừng hoạt động' : 'Kích hoạt', conflict,
  });
}

async function unitDetail(context, id) {
  const path = `/units/${id}`;
  const unit = await context.read(path);
  if (!context.current()) return;
  const manage = permission(context.caps, 'directory.manage');
  return [link('← Danh sách đơn vị', 'units'), panel(unit.name, activeBadge(unit.active),
    facts([['Mã đơn vị', unit.code], ['ID đơn vị', unit.id]]), manage && actions(
      formAction(context, 'Sửa đơn vị', path, { method: 'PATCH', fields: () => nameCodeFields(unit), conflict: 'Mã đơn vị đã được sử dụng.' }),
      activeAction(context, path, unit.active, 'đơn vị', 'Không thể ngừng hoạt động khi đơn vị còn tài khoản hoạt động hoặc vai trò gắn với đơn vị.')) )];
}

function groupPermission(kind) {
  return kind === 'AUTHORIZATION' ? 'authorization.manage' : 'directory.manage';
}

function groups(context) {
  const allowed = kinds.filter(kind => permission(context.caps, groupPermission(kind)));
  const create = allowed.length > 0 && formAction(context, 'Tạo nhóm', '/groups', {
    fields: () => [...nameCodeFields(), field({ name: 'kind', label: 'Loại nhóm', options: enumOptions(allowed), value: allowed[0], required: true })],
    primary: true, submit: 'Tạo nhóm', conflict: 'Mã nhóm đã được sử dụng.',
    description: 'Mã và loại nhóm được giữ cố định sau khi tạo.',
  });
  return listing(context, {
    path: '/groups', toolbar: create ? [create] : [],
    filters: [search(), field({ name: 'kind', label: 'Loại nhóm', options: all(enumOptions(kinds)) }),
      field({ name: 'active', label: 'Trạng thái', options: activeOptions })],
    headers: ['Mã', 'Tên nhóm', 'Loại nhóm', 'Trạng thái'],
    row: group => [group.code, link(group.name, `groups/${group.id}`), badge(labels[group.kind]), activeBadge(group.active)],
  });
}

function memberActions(context, path, group, member, manage) {
  if (!manage || (!member.active && !group.active)) return '—';
  const memberPath = `${path}/members/${member.user.id}`;
  return member.active ? formAction(context, 'Gỡ thành viên', memberPath, {
    method: 'DELETE', danger: true, submit: 'Gỡ thành viên', description: `Gỡ ${member.user.display_name} khỏi nhóm? Lịch sử thành viên vẫn được giữ.`,
  }) : formAction(context, 'Thêm lại', memberPath, { method: 'PUT', submit: 'Thêm lại', description: `Kích hoạt lại tư cách thành viên của ${member.user.display_name}?` });
}

function members(context, path, group, manage) {
  const add = manage && group.active && button('Thêm thành viên', () => formDialog(context, {
    title: 'Thêm thành viên', submit: 'Thêm thành viên', fields: [reference(context, {
      name: 'user_id', label: 'Tài khoản', resource: '/users',
      title: user => `${user.display_name} · ${user.username}`,
    })],
    save: values => context.write(`${path}/members/${values.user_id}`, { method: 'PUT' }),
  }), 'primary');
  return listing(context, {
    path: `${path}/members`, heading: 'Thành viên', toolbar: add ? [add] : [],
    filters: [search(), field({ name: 'active', label: 'Tư cách thành viên', value: 'true',
      options: [['true', 'Đang tham gia'], ['false', 'Đã gỡ']] })],
    headers: ['Tên hiển thị', 'Tên đăng nhập', 'Trạng thái', 'Thao tác'],
    row: member => [link(member.user.display_name, `users/${member.user.id}`), member.user.username,
      badge(member.active ? 'Đang tham gia' : 'Đã gỡ', member.active ? 'green' : 'neutral'),
      memberActions(context, path, group, member, manage)],
  });
}

async function groupDetail(context, id) {
  const path = `/groups/${id}`;
  const group = await context.read(path);
  if (!context.current()) return;
  const manage = permission(context.caps, groupPermission(group.kind));
  return [link('← Danh sách nhóm', 'groups'), panel(group.name, actions(badge(labels[group.kind]), activeBadge(group.active)),
    facts([['Mã nhóm', group.code], ['ID nhóm', group.id], ['Cập nhật', dateLabel(group.updated_at)]]),
    manage && actions(formAction(context, 'Đổi tên nhóm', path, { method: 'PATCH', fields: () => [nameField(group.name)] }),
      activeAction(context, path, group.active, 'nhóm'))), members(context, path, group, manage),
    permission(context.caps, 'authorization.manage') && assignments(context, path, group)];
}

function roles(context) {
  return listing(context, {
    path: '/roles', filters: [search()], headers: ['Vai trò', 'Quyền'],
    row: role => [el('code', {}, role.code), el('ul', { class: 'plain-list' },
      role.permissions.map(code => el('li', {}, permissions[code], ' · ', el('code', {}, code))))],
  });
}

function assignmentFields(context, catalog, group) {
  const choices = catalog.items.map(role => role.code).filter(code => !group || !['FOUNDATION_ADMIN', 'AI_MODEL_ADMIN', 'AI_QUOTA_ADMIN', 'AI_QUOTA_VIEWER'].includes(code));
  const role = field({ name: 'role_code', label: 'Vai trò', required: true, options: choices.map(code => [code, code]) });
  const scopeField = field({ name: 'scope', label: 'Phạm vi', required: true, options: enumOptions(['GLOBAL', 'UNIT']) });
  const unit = unitSelect(context, 'unit_id', 'Đơn vị áp dụng');
  const roleInput = role.querySelector('select');
  const scope = scopeField.querySelector('select');
  const unitInput = unit.querySelector('select');
  roleInput.value = choices[0] ?? '';
  function update() {
    const previous = scope.value;
    const allowed = ['FOUNDATION_ADMIN', 'AI_MODEL_ADMIN', 'AI_QUOTA_ADMIN'].includes(roleInput.value) ? ['GLOBAL']
      : roleInput.value === 'UNIT_DIRECTORY_MANAGER' ? ['UNIT'] : ['GLOBAL', 'UNIT'];
    scope.replaceChildren(...enumOptions(allowed).map(([value, title]) => el('option', { value }, title)));
    scope.value = allowed.includes(previous) ? previous : allowed[0];
    unit.hidden = unitInput.disabled = scope.value !== 'UNIT';
  }
  roleInput.addEventListener('change', update);
  scope.addEventListener('change', update);
  update();
  return [role, scopeField, unit];
}

function assignments(context, subjectPath, group) {
  const path = `${subjectPath}/role-assignments`;
  const grant = (!group || (group.kind === 'AUTHORIZATION' && group.active)) && button('Cấp vai trò', () => {
    const loading = el('div', { role: 'status', class: 'field' }, 'Đang tải vai trò…');
    let fields;
    formDialog(context, {
      title: 'Cấp vai trò', submit: 'Cấp vai trò', fields: [loading],
      description: 'Giới hạn quyền theo toàn trường hoặc theo đúng một đơn vị.',
      conflict: 'Vai trò này đã được cấp trong phạm vi đã chọn.',
      save: values => context.write(path, { method: 'POST', body: clean(values) }),
    });
    const save = loading.closest('form').querySelector('[type="submit"]');
    save.disabled = true;
    context.read('/roles', { limit: 100 }).then(catalog => {
      if (!loading.isConnected || !context.current()) return;
      fields = assignmentFields(context, catalog, group);
      loading.replaceWith(...fields);
      save.disabled = !catalog.items.length;
      fields[0].querySelector('select').focus();
    }).catch(error => {
      if (loading.isConnected && context.current()) {
        loading.setAttribute('role', 'alert');
        showError(loading, error);
      }
    });
  }, 'primary');
  return listing(context, {
    path, heading: group ? 'Vai trò của nhóm' : 'Vai trò trực tiếp', toolbar: grant ? [grant] : [],
    filters: [field({ name: 'role_code', label: 'Mã vai trò', max: 64 }),
      field({ name: 'scope', label: 'Phạm vi', options: all(enumOptions(['GLOBAL', 'UNIT'])) }),
      hasScope(context.caps, 'directory.read') && unitSelect(context, 'unit_id', 'Đơn vị áp dụng', false, false)],
    headers: ['Vai trò', 'Phạm vi', 'Đơn vị', 'Thao tác'],
    row: grant => [el('code', {}, grant.role_code), labels[grant.scope], grant.unit_id && link(grant.unit_id, `units/${grant.unit_id}`),
      formAction(context, 'Thu hồi vai trò', `${path}/${grant.id}`, {
        method: 'DELETE', danger: true, submit: 'Thu hồi', description: `Thu hồi vai trò ${grant.role_code} trong phạm vi ${labels[grant.scope].toLowerCase()}?`,
        conflict: 'Không thể thu hồi vai trò nếu trường sẽ không còn quản trị viên có thể đăng nhập.',
      })],
  });
}

function audit(context) {
  return listing(context, {
    path: '/audit-events', filters: [field({ name: 'action', label: 'Hành động', options: all(Object.entries(actionsLabel).map(([code, title]) => [code, `${title} · ${code}`])) }),
      field({ name: 'outcome', label: 'Kết quả', options: all(enumOptions(['SUCCESS', 'FAILURE'])) }),
      field({ name: 'actor_id', label: 'ID người thực hiện', max: 36 }),
      field({ name: 'target_id', label: 'ID đối tượng', max: 36 }),
      field({ name: 'target_type', label: 'Loại đối tượng', max: 64 }),
      field({ name: 'from_time', label: 'Từ thời điểm', type: 'datetime-local' }),
      field({ name: 'to_time', label: 'Đến trước', type: 'datetime-local' })],
    headers: ['Thời điểm', 'Hành động', 'Người thực hiện', 'Kết quả'],
    row: event => [dateLabel(event.occurred_at), link(actionsLabel[event.action] ?? event.action, `audit/${event.id}`),
      event.actor_id ?? '—', badge(labels[event.outcome], event.outcome === 'SUCCESS' ? 'green' : 'amber')],
  });
}

async function auditDetail(context, id) {
  const event = await context.read(`/audit-events/${id}`);
  return [link('← Nhật ký hoạt động', 'audit'), panel(actionsLabel[event.action] ?? event.action, facts([
    ['Thời điểm', dateLabel(event.occurred_at)], ['Kết quả', labels[event.outcome]],
    ['Hành động', event.action], ['Người thực hiện', event.actor_id ?? 'Không có người thực hiện đã xác thực'],
    ['Loại đối tượng', event.target_type], ['ID đối tượng', event.target_id], ['Mã yêu cầu', event.request_id],
  ]), el('h3', {}, 'Chi tiết thay đổi'), el('pre', {}, JSON.stringify(event.changes, null, 2)))];
}

function home(context) {
  const me = context.me;
  const visible = Object.entries(sections).filter(([key, section]) => key !== 'home' && section.visible(context.caps));
  const grants = Object.entries(context.caps.permissions).filter(([, scope]) => scope.institution_wide || scope.unit_ids.length);
  return [el('div', { class: 'welcome' }, el('h2', {}, `Xin chào, ${me.display_name}`),
    el('p', {}, 'Quản lý danh bạ, quyền truy cập và cấu hình AI của trường theo quyền được cấp.')),
    el('div', { class: 'overview-grid' }, panel('Tài khoản của bạn', facts([
      ['Tên đăng nhập', me.username], ['ID trường', me.institution_id], ['Đơn vị chính', me.primary_unit_id],
    ])), panel('Phạm vi của bạn', grants.length ? facts(grants.map(([code, scope]) => [permissions[code],
      scope.institution_wide ? 'Toàn trường' : `${scope.unit_ids.length} đơn vị được cấp`]))
      : el('p', { class: 'empty' }, 'Tài khoản này chưa được cấp quyền danh bạ.'))),
    visible.length > 0 && panel('Truy cập nhanh', actions(visible.map(([key, section]) => link(section.title, key))))];
}

const pages = { home, users, units, groups, roles, audit };
const details = { users: userDetail, units: unitDetail, groups: groupDetail, audit: auditDetail };

export async function pageContent(context, route, id, detail) {
  if (route === 'mdl') return mdlPage(context, id, detail);
  if (route === 'qta') return qtaPage(context, id, detail);
  if (id && details[route]) return details[route](context, id);
  return pages[route](context);
}
