// M6: "Cấu hình Nhà cung cấp & Mô hình AI" (AQ-FRD-UAI-MDL-001).
// The server is the authority for every rule; this page only explains and collects input.
// Stored secrets are never received from the API, so they can never be shown or prefilled.
import { permission, RequestError } from './api.mjs';
import { actions, badge, button, dateLabel, el, facts, field, formDialog, link, listing, panel, showError, table } from './ui.mjs';

export const tabs = {
  routing: 'Mô hình chính & dự phòng',
  providers: 'Nhà cung cấp',
  models: 'Mô hình',
  agreements: 'Thỏa thuận dữ liệu',
  history: 'Lịch sử thay đổi',
};

const providerTypes = { EXTERNAL: 'Bên ngoài', INTERNAL: 'Nội bộ' };
const apiStyles = {
  OPENAI_COMPATIBLE: 'Tương thích OpenAI (max_tokens)',
  OPENAI_COMPATIBLE_V2: 'Tương thích OpenAI (max_completion_tokens)',
};
const authSchemes = { BEARER: 'Bearer token', HEADER_KEY: 'Khóa trong header riêng', NONE: 'Không xác thực' };
const credentialStates = {
  NOT_REQUIRED: ['Không cần', 'neutral'], MISSING: ['Chưa có', 'amber'],
  STORED: ['Đã lưu (được ẩn)', 'green'], UNREADABLE: ['Không đọc được', 'amber'],
};
const risks = { HIGH: 'Cao', MEDIUM: 'Trung bình', LOW: 'Thấp' };
const capabilities = { TEXT: 'Văn bản', IMAGE: 'Hình ảnh', VOICE: 'Giọng nói' };
const bases = {
  NO_TRAINING_COMMITMENT: 'Cam kết không dùng dữ liệu nhà trường để huấn luyện',
  SCHOOL_WRITTEN_AUTHORIZATION: 'Nhà trường cho phép bằng văn bản',
};
const testResults = {
  PASSED: ['Thử thành công', 'green'], FAILED: ['Thử thất bại', 'amber'], RUNNING: ['Đang thử', 'blue'],
  OUTDATED: ['Kết quả đã cũ', 'amber'], NOT_TESTED: ['Chưa thử', 'neutral'],
  UNSUPPORTED: ['Không hỗ trợ thử', 'neutral'],
};
const testErrors = {
  AUTH_FAILED: 'Nhà cung cấp từ chối thông tin xác thực', MODEL_NOT_FOUND: 'Không tìm thấy mô hình',
  RATE_LIMITED: 'Nhà cung cấp giới hạn tần suất', REQUEST_REJECTED: 'Nhà cung cấp từ chối yêu cầu',
  PROVIDER_ERROR: 'Nhà cung cấp gặp lỗi', REDIRECT_REFUSED: 'Nhà cung cấp chuyển hướng (không được theo)',
  BAD_RESPONSE: 'Phản hồi không đúng định dạng', RESPONSE_TOO_LARGE: 'Phản hồi quá lớn',
  TIMEOUT: 'Quá thời gian chờ', DNS_FAILED: 'Không phân giải được tên máy chủ',
  TLS_ERROR: 'Lỗi chứng chỉ TLS', NETWORK_ERROR: 'Lỗi kết nối mạng',
  ENDPOINT_BLOCKED: 'Địa chỉ bị chính sách mạng chặn', TEST_ERROR: 'Lỗi nội bộ khi thử',
  STALE_CONFIGURATION: 'Cấu hình đã đổi trong lúc thử', ABORTED: 'Người thử mất quyền giữa chừng',
  EXPIRED: 'Lượt thử bị gián đoạn',
};
// Eligibility codes from the API (queries.ROUTING_ISSUE_CODES).
const issues = {
  model_inactive: 'Mô hình đang ngừng hoạt động', provider_inactive: 'Nhà cung cấp đang ngừng hoạt động',
  text_unsupported: 'Không có khả năng văn bản', risk_unclassified: 'Chưa phân loại rủi ro',
  not_tested: 'Chưa thử kết nối', test_outdated: 'Kết quả thử đã cũ (địa chỉ, kiểu API hoặc bí mật đã đổi)',
  test_failed: 'Lần thử gần nhất thất bại', dpa_missing: 'Chưa có thỏa thuận dữ liệu còn hiệu lực',
  credential_unavailable: 'Bí mật kết nối không dùng được', endpoint_blocked: 'Địa chỉ bị chính sách mạng chặn',
};
const slots = { primary: 'Mô hình chính', fallback: 'Mô hình dự phòng' };
const usedIn = { 'routing.primary': 'mô hình chính', 'routing.fallback': 'mô hình dự phòng' };
const effectiveStates = {
  PRIMARY: ['Đang dùng mô hình chính', 'green'], FALLBACK: ['Đang dùng mô hình dự phòng', 'amber'],
  UNAVAILABLE: ['Không có mô hình nào được phép dùng', 'amber'], NOT_CONFIGURED: ['Chưa cấu hình', 'neutral'],
};
const errorMessages = {
  MDL_DPA_REQUIRED: 'Nhà cung cấp bên ngoài cần một thỏa thuận bảo vệ dữ liệu còn hiệu lực trước khi thử kết nối hoặc đưa vào dùng.',
  MDL_CREDENTIAL_REQUIRED: 'Cần nhập bí mật kết nối: bắt buộc khi tạo nhà cung cấp có xác thực, khi đổi máy chủ hoặc khi đổi kiểu xác thực.',
  MDL_CREDENTIAL_UNAVAILABLE: 'Không dùng được bí mật kết nối đã lưu (khóa mã hóa chưa được cấu hình hoặc không khớp). Hãy liên hệ người vận hành.',
  MDL_ENDPOINT_BLOCKED: 'Địa chỉ kết nối không được chính sách mạng cho phép. Nhà cung cấp bên ngoài phải dùng https, cổng 443 và tên miền công khai; nhà cung cấp gửi bí mật phải dùng https.',
  MDL_MODEL_IN_USE: 'Không thể thực hiện vì mô hình đang được dùng.',
  MDL_ROUTING_CONFLICT: 'Cấu hình vừa được người khác thay đổi. Hãy tải lại trang, kiểm tra rồi lưu lại.',
  MDL_FALLBACK_EQUALS_PRIMARY: 'Mô hình dự phòng phải khác mô hình chính.',
  MDL_TEST_IN_PROGRESS: 'Đang có một lượt thử kết nối cho mô hình này.',
  MDL_DUPLICATE: 'Tên nhà cung cấp hoặc mã kỹ thuật của mô hình đã tồn tại.',
  MDL_RISK_REQUIRED: 'Mô hình đang được dùng phải có mức rủi ro.',
  MDL_TEST_UNSUPPORTED: 'Chỉ mô hình có khả năng văn bản mới thử kết nối được.',
  MDL_TEST_COOLDOWN: 'Mô hình vừa được thử với cùng cấu hình. Hãy đợi khoảng 30 giây rồi thử lại.',
  MDL_CHARGES_NOT_ACKNOWLEDGED: 'Hãy xác nhận đã đọc thông báo chi phí trước khi thử.',
  RATE_LIMITED: 'Đang có quá nhiều lượt thử kết nối. Hãy thử lại sau ít phút.',
};
const COST_NOTICE = 'Nhà cung cấp bên ngoài có thể tính phí lượt thử này vào tài khoản API của nhà trường. '
  + 'Lượt thử gửi đúng một yêu cầu cố định, rất ngắn, không chứa dữ liệu của nhà trường, và không trừ hạn mức AQ EduUAI của bất kỳ ai.';
const LEGAL_NOTICE = 'Hệ thống chỉ ghi nhận căn cứ và số văn bản. Hệ thống không thẩm định giá trị pháp lý của thỏa thuận.';
// D6: internal operational guidance, not a legal classification (OQ-09-01 is still open).
const RISK_GUIDANCE = [
  ['Cao', 'kết quả có thể ảnh hưởng đáng kể đến người học hoặc nhân sự (đánh giá, xếp loại, tuyển sinh, kỷ luật), hoặc mô hình xử lý dữ liệu cá nhân nhạy cảm, hoặc nhà cung cấp không công bố đủ thông tin về mô hình.'],
  ['Trung bình', 'mô hình tạo nội dung hỗ trợ mà con người kiểm tra trước khi dùng (soạn thảo, tóm tắt, hỏi đáp chung) và có thể gặp dữ liệu cá nhân thông thường.'],
  ['Thấp', 'tác vụ không dùng dữ liệu cá nhân và kết quả không trực tiếp tác động đến quyền lợi của ai (định dạng văn bản, gợi ý từ ngữ, thử nghiệm nội bộ).'],
];

function issueLabel(code) {
  const [slot, issue] = code.includes('.') ? code.split('.', 2) : [undefined, code];
  const text = issues[issue] ?? issue;
  return slot ? `${slots[slot] ?? slot}: ${text}` : text;
}

function translate(error) {
  if (!(error instanceof RequestError) || !error.code) return error;
  let message = errorMessages[error.code];
  if (error.code === 'MDL_NOT_ELIGIBLE') {
    message = `Không đủ điều kiện: ${(error.details?.reasons ?? []).map(issueLabel).join('; ') || 'xem lý do trên từng mô hình'}.`;
  } else if (error.code === 'MDL_MODEL_IN_USE' && error.details?.used_in) {
    message = `${message} Đang dùng làm ${error.details.used_in.map(code => usedIn[code] ?? code).join(' và ')}. Hãy đổi cấu hình mô hình chính / dự phòng trước.`;
  }
  return message ? new RequestError(error.status, error.requestId, message, error.code) : error;
}

async function write(context, path, options) {
  try {
    return await context.write(`/mdl${path}`, options);
  } catch (error) {
    throw translate(error);
  }
}

const read = (context, path, query) => context.read(`/mdl${path}`, query);

// Pickers need every entry, not only the first API page (the API caps `limit` at 100).
// M7 fix: with more than 100 providers or eligible models the earlier single request
// silently omitted entries, and a preselected provider beyond the first page fell back
// to the first option. Registries are small; paging stops at the API's offset ceiling.
const PICKER_PAGE = 100;
async function readAll(context, path, query = {}) {
  const items = [];
  for (let offset = 0; offset <= 100000; offset += PICKER_PAGE) {
    const result = await read(context, path, { ...query, limit: PICKER_PAGE, offset });
    items.push(...result.items);
    if (!context.current() || !result.items.length || offset + PICKER_PAGE >= result.total) break;
  }
  return { items };
}
const optionsOf = map => Object.entries(map);
const riskBadge = level => badge(risks[level] ?? 'Chưa phân loại', level ? (level === 'HIGH' ? 'amber' : 'blue') : 'neutral');
const activeBadge = active => badge(active ? 'Đang hoạt động' : 'Ngừng hoạt động', active ? 'green' : 'neutral');
const pair = ([text, theme]) => badge(text, theme);

function testBadge(state) {
  const [text, theme] = testResults[state.result];
  return el('span', {}, badge(text, theme), state.running && ' ', state.running && badge('Đang thử', 'blue'),
    state.error_code && el('small', { class: 'hint' }, ` ${testErrors[state.error_code] ?? state.error_code}`));
}

function eligibility(routing) {
  return routing.eligible ? badge('Đủ điều kiện', 'green')
    : el('span', {}, badge('Chưa đủ điều kiện', 'amber'), el('ul', { class: 'plain-list issue-list' }, routing.issues.map(code => el('li', {}, issueLabel(code)))));
}

function dialog(context, settings) {
  formDialog(context, { ...settings, save: async (values, form) => settings.save(values, form) });
}

function confirmAction(context, label, path, { description, danger, submit, notice, body }) {
  return button(label, () => dialog(context, {
    title: label, description, danger, submit: submit ?? label,
    save: async () => {
      const result = await write(context, path, { method: 'POST', body });
      return notice?.(result);
    },
  }), danger ? 'danger-outline' : 'secondary');
}

function stateAction(context, path, active, subject) {
  return confirmAction(context, active ? 'Ngừng hoạt động' : 'Kích hoạt', `${path}/${active ? 'deactivate' : 'activate'}`, {
    danger: active,
    description: active
      ? `Ngừng hoạt động ${subject}? Bản ghi và lịch sử vẫn được giữ. Không thể ngừng khi đang được dùng làm mô hình chính hoặc dự phòng.`
      : `Cho ${subject} hoạt động trở lại? Việc đưa vào dùng vẫn cần đủ điều kiện.`,
  });
}

// ------------------------------------------------------------------ providers

function providerFields(provider) {
  const create = !provider;
  const scheme = field({ name: 'auth_scheme', label: 'Kiểu xác thực', options: optionsOf(authSchemes), value: provider?.auth_scheme ?? 'BEARER', required: true });
  const header = field({ name: 'auth_header_name', label: 'Tên header chứa khóa', value: provider?.auth_header_name ?? '', max: 64,
    pattern: '[A-Za-z0-9][A-Za-z0-9\\-]{0,63}', hint: 'Ví dụ: X-Api-Key. Không dùng các header như Host, Cookie, Content-Length.' });
  const secret = field({ name: 'secret', label: 'Bí mật kết nối', type: 'password', max: 4096, autocomplete: 'new-password',
    hint: create ? 'Bắt buộc khi có xác thực. Sau khi lưu, bí mật không bao giờ được hiển thị lại.'
      : 'Để trống để giữ bí mật đã lưu. Bắt buộc nhập lại khi đổi máy chủ hoặc đổi kiểu xác thực. Bí mật đã lưu không bao giờ được hiển thị lại.' });
  const schemeInput = scheme.querySelector('select');
  function update() {
    const keyed = schemeInput.value === 'HEADER_KEY';
    header.hidden = header.querySelector('input').disabled = !keyed;
    header.querySelector('input').required = keyed;
    secret.hidden = secret.querySelector('input').disabled = schemeInput.value === 'NONE';
  }
  schemeInput.addEventListener('change', update);
  update();
  return [
    field({ name: 'name', label: 'Tên nhà cung cấp', value: provider?.name ?? '', required: true, max: 255 }),
    create && field({ name: 'provider_type', label: 'Loại', options: optionsOf(providerTypes), value: 'EXTERNAL', required: true,
      hint: 'Không đổi được sau khi tạo. Bên ngoài cần thỏa thuận dữ liệu trước khi thử hoặc dùng.' }),
    field({ name: 'api_style', label: 'Kiểu API', options: optionsOf(apiStyles), value: provider?.api_style ?? 'OPENAI_COMPATIBLE', required: true }),
    field({ name: 'endpoint', label: 'Địa chỉ kết nối (URL gốc của API)', value: provider?.endpoint ?? '', required: true, max: 2048,
      hint: 'Ví dụ: https://api.nha-cung-cap.vn/v1. Bên ngoài: https, cổng 443. Nội bộ: phải nằm trong danh sách được người vận hành cho phép.' }),
    scheme, header, secret,
  ];
}

function providerBody(values, provider) {
  const body = {};
  for (const key of ['name', 'provider_type', 'api_style', 'endpoint', 'auth_scheme', 'auth_header_name']) {
    const value = values[key]?.trim();
    if (value === undefined || value === '') continue;
    if (!provider || provider[key] !== value) body[key] = value;
  }
  if (provider && values.auth_scheme !== 'HEADER_KEY' && provider.auth_header_name) delete body.auth_header_name;
  if (values.secret) body.secret = values.secret;
  return body;
}

function createProvider(context) {
  return button('Thêm nhà cung cấp', () => dialog(context, {
    title: 'Thêm nhà cung cấp', submit: 'Thêm nhà cung cấp', fields: providerFields(),
    save: values => write(context, '/providers', { method: 'POST', body: providerBody(values) }),
  }), 'primary');
}

function credentialBadge(provider) {
  return pair(credentialStates[provider.credential_status]);
}

function agreementSummary(provider) {
  if (provider.provider_type !== 'EXTERNAL') return badge('Không yêu cầu', 'neutral');
  const agreement = provider.agreement_in_force;
  return agreement ? el('span', {}, badge('Còn hiệu lực', 'green'), ' ', agreement.document_number)
    : badge('Chưa có — chưa thử / dùng được', 'amber');
}

function providers(context, manage) {
  return listing(context, {
    path: '/mdl/providers', toolbar: manage ? [createProvider(context)] : [],
    filters: [
      field({ name: 'provider_type', label: 'Loại', options: [['', 'Tất cả'], ...optionsOf(providerTypes)] }),
      field({ name: 'active', label: 'Trạng thái', options: [['', 'Tất cả'], ['true', 'Đang hoạt động'], ['false', 'Ngừng hoạt động']] }),
    ],
    headers: ['Tên', 'Loại', 'Địa chỉ', 'Bí mật kết nối', 'Thỏa thuận dữ liệu', 'Trạng thái'],
    row: provider => [link(provider.name, `mdl/providers/${provider.id}`), providerTypes[provider.provider_type],
      el('code', {}, provider.endpoint), credentialBadge(provider), agreementSummary(provider), activeBadge(provider.active)],
  });
}

function agreementStatus(agreement) {
  if (agreement.withdrawn_at) return badge(`Đã thu hồi ${dateLabel(agreement.withdrawn_at)}`, 'neutral');
  return agreement.in_force ? badge('Còn hiệu lực', 'green') : badge('Đã được thay thế', 'neutral');
}

function agreements(context, provider, manage, routedHere) {
  const path = `/providers/${provider.id}/agreements`;
  const record = manage && button('Ghi nhận thỏa thuận', () => dialog(context, {
    title: 'Ghi nhận thỏa thuận bảo vệ dữ liệu', submit: 'Ghi nhận', description: LEGAL_NOTICE,
    fields: [
      field({ name: 'basis', label: 'Căn cứ', options: optionsOf(bases), value: 'NO_TRAINING_COMMITMENT', required: true }),
      field({ name: 'document_number', label: 'Số văn bản thỏa thuận', required: true, max: 128 }),
      field({ name: 'signed_on', label: 'Ngày ký (nếu có)', type: 'date' }),
    ],
    save: values => write(context, path, { method: 'POST', body: {
      basis: values.basis, document_number: values.document_number.trim(), ...(values.signed_on ? { signed_on: values.signed_on } : {}),
    } }),
  }), 'primary');
  const warning = routedHere.length
    ? `Mô hình của nhà cung cấp này đang là ${routedHere.join(' và ')}. Sau khi thu hồi, mô hình đó vẫn nằm trong cấu hình và lịch sử nhưng sẽ KHÔNG được dùng cho đến khi có thỏa thuận còn hiệu lực mới; mô hình dự phòng (nếu đủ điều kiện) sẽ được dùng thay.`
    : 'Sau khi thu hồi, mô hình của nhà cung cấp này không thể thử kết nối hoặc đưa vào dùng cho đến khi có thỏa thuận còn hiệu lực mới.';
  return listing(context, {
    path: `/mdl${path}`, heading: 'Thỏa thuận bảo vệ dữ liệu', toolbar: [el('p', { class: 'hint' }, LEGAL_NOTICE), record].filter(Boolean),
    headers: ['Căn cứ', 'Số văn bản', 'Ngày ký', 'Ghi nhận lúc', 'Trạng thái', 'Thao tác'],
    row: agreement => [bases[agreement.basis], agreement.document_number, agreement.signed_on ?? '—', dateLabel(agreement.recorded_at),
      agreementStatus(agreement), manage && !agreement.withdrawn_at ? confirmAction(context, 'Thu hồi', `${path}/${agreement.id}/withdraw`, {
        danger: true, submit: 'Thu hồi thỏa thuận', description: `Thu hồi thỏa thuận số ${agreement.document_number}? ${warning}`,
        notice: result => result.affected_routing.length
          ? `Đã thu hồi. ${result.affected_routing.map(code => usedIn[code] ?? code).join(' và ')} hiện không được dùng cho đến khi có thỏa thuận mới.`
          : 'Đã thu hồi thỏa thuận.',
      }) : '—'],
  });
}

async function providerDetail(context, id, manage) {
  const [provider, routing] = await Promise.all([read(context, `/providers/${id}`), read(context, '/routing')]);
  if (!context.current()) return;
  const routedHere = ['primary', 'fallback'].filter(slot => routing[slot]?.provider_id === provider.id).map(slot => slots[slot].toLowerCase());
  const controls = manage ? actions(button('Sửa nhà cung cấp', () => dialog(context, {
    title: 'Sửa nhà cung cấp', fields: providerFields(provider),
    description: 'Đổi địa chỉ, kiểu API, kiểu xác thực hoặc bí mật sẽ làm kết quả thử trước đó trở nên cũ; mô hình cần được thử lại trước khi dùng.',
    save: async values => {
      const body = providerBody(values, provider);
      if (Object.keys(body).length) await write(context, `/providers/${provider.id}`, { method: 'PATCH', body });
    },
  }), 'primary'), stateAction(context, `/providers/${provider.id}`, provider.active, 'nhà cung cấp')) : null;
  return [link('← Danh sách nhà cung cấp', 'mdl/providers'), panel(provider.name, actions(badge(providerTypes[provider.provider_type]), activeBadge(provider.active)), facts([
    ['Kiểu API', apiStyles[provider.api_style]], ['Địa chỉ kết nối', el('code', {}, provider.endpoint)],
    ['Kiểu xác thực', provider.auth_header_name ? `${authSchemes[provider.auth_scheme]} · ${provider.auth_header_name}` : authSchemes[provider.auth_scheme]],
    ['Bí mật kết nối', el('span', {}, credentialBadge(provider), provider.credential_updated_at && ` cập nhật ${dateLabel(provider.credential_updated_at)}`)],
    ['Phiên bản kết nối', String(provider.connection_version)], ['Thỏa thuận dữ liệu', agreementSummary(provider)],
    ['Đang dùng trong định tuyến', routedHere.length ? routedHere.join(', ') : 'Không'], ['Cập nhật', dateLabel(provider.updated_at)],
  ]), controls),
  provider.provider_type === 'EXTERNAL' ? agreements(context, provider, manage, routedHere)
    : panel('Thỏa thuận bảo vệ dữ liệu', el('p', { class: 'muted' }, 'Nhà cung cấp nội bộ không cần thỏa thuận này.')),
  models(context, manage, { provider_id: provider.id }, 'Mô hình của nhà cung cấp'),
  configurationHistory(context, { target_id: provider.id }, 'Lịch sử cấu hình nhà cung cấp')];
}

// --------------------------------------------------------------------- models

function capabilityField(selected = ['TEXT']) {
  return el('fieldset', { class: 'field choice-group' }, el('legend', {}, 'Khả năng'),
    optionsOf(capabilities).map(([value, title]) => el('label', { class: 'choice' },
      el('input', { type: 'checkbox', name: 'capabilities', value, checked: selected.includes(value) }), ` ${title}`)),
    el('small', { class: 'hint' }, 'Chỉ khả năng văn bản được thử kết nối; mô hình không có văn bản không thể đưa vào dùng.'));
}

function riskGuidance() {
  return el('details', { class: 'guidance' }, el('summary', {}, 'Tiêu chí phân loại rủi ro (hướng dẫn nội bộ)'),
    el('ul', { class: 'plain-list' }, RISK_GUIDANCE.map(([level, rule]) => el('li', {}, el('strong', {}, `${level}: `), rule))),
    el('p', { class: 'hint' }, 'Đây là hướng dẫn vận hành nội bộ, không phải phân loại pháp lý. Mô hình chưa phân loại không được đưa vào dùng. Khi nhà trường ban hành tiêu chí chính thức, tiêu chí đó được ưu tiên.'));
}

function riskField(value) {
  return field({ name: 'risk_level', label: 'Mức rủi ro', options: [['', 'Chưa phân loại'], ...optionsOf(risks)], value: value ?? '' });
}

function capabilityValues(form) {
  const selected = new FormData(form).getAll('capabilities');
  if (!selected.length) throw new RequestError(422, null, 'Hãy chọn ít nhất một khả năng.');
  return selected;
}

function tokensValue(text) {
  if (!text) return null;
  const tokens = Number(text);
  if (!Number.isInteger(tokens) || tokens < 1 || tokens > 1000000) throw new RequestError(422, null, 'Độ dài tối đa phải là số nguyên từ 1 đến 1.000.000.');
  return tokens;
}

function createModel(context, providerId) {
  return button('Thêm mô hình', async () => {
    const loading = el('p', { class: 'field', role: 'status' }, 'Đang tải nhà cung cấp…');
    dialog(context, {
      title: 'Thêm mô hình', submit: 'Thêm mô hình', fields: [loading, riskGuidance()],
      save: async (values, form) => {
        const body = { provider_id: values.provider_id, technical_id: values.technical_id.trim(), display_name: values.display_name.trim(),
          capabilities: capabilityValues(form) };
        const tokens = tokensValue(values.max_output_tokens);
        if (tokens) body.max_output_tokens = tokens;
        if (values.risk_level) body.risk_level = values.risk_level;
        await write(context, '/models', { method: 'POST', body });
      },
    });
    const submit = loading.closest('form').querySelector('[type="submit"]');
    submit.disabled = true;
    try {
      const result = await readAll(context, '/providers');
      if (!loading.isConnected || !context.current()) return;
      if (!result.items.length) {
        loading.textContent = 'Chưa có nhà cung cấp. Hãy thêm nhà cung cấp trước.';
        return;
      }
      loading.replaceWith(
        field({ name: 'provider_id', label: 'Nhà cung cấp', required: true, value: providerId ?? result.items[0].id,
          options: result.items.map(item => [item.id, `${item.name} · ${providerTypes[item.provider_type]}`]) }),
        field({ name: 'technical_id', label: 'Mã kỹ thuật của mô hình', required: true, max: 255, hint: 'Đúng tên mô hình nhà cung cấp dùng trong API. Không đổi được sau khi tạo.' }),
        field({ name: 'display_name', label: 'Tên hiển thị', required: true, max: 255 }),
        capabilityField(),
        field({ name: 'max_output_tokens', label: 'Độ dài tối đa kết quả (token, nếu áp dụng)', type: 'number', min: 1, max: 7 }),
        riskField());
      submit.disabled = false;
    } catch (error) {
      if (loading.isConnected) showError(loading, error);
    }
  }, 'primary');
}

function models(context, manage, query = {}, heading) {
  return listing(context, {
    path: '/mdl/models', heading, query,
    toolbar: manage ? [createModel(context, query.provider_id)] : [],
    filters: [
      field({ name: 'routing_eligible', label: 'Điều kiện đưa vào dùng', options: [['', 'Tất cả'], ['true', 'Đủ điều kiện'], ['false', 'Chưa đủ điều kiện']] }),
      field({ name: 'risk_level', label: 'Mức rủi ro', options: [['', 'Tất cả'], ...optionsOf(risks), ['UNCLASSIFIED', 'Chưa phân loại']] }),
      field({ name: 'active', label: 'Trạng thái', options: [['', 'Tất cả'], ['true', 'Đang hoạt động'], ['false', 'Ngừng hoạt động']] }),
    ],
    headers: ['Tên hiển thị', 'Mã kỹ thuật', 'Khả năng', 'Rủi ro', 'Thử kết nối', 'Đưa vào dùng', 'Trạng thái'],
    row: model => [link(model.display_name, `mdl/models/${model.id}`), el('code', {}, model.technical_id),
      model.capabilities.map(code => capabilities[code]).join(', '), riskBadge(model.risk_level),
      testBadge(model.connection_test), eligibility(model.routing), activeBadge(model.active)],
  });
}

function connectionTest(context, model, provider) {
  if (!model.capabilities.includes('TEXT')) {
    const blocked = button('Thử kết nối', () => {});
    blocked.disabled = true;
    blocked.title = 'Chỉ mô hình có khả năng văn bản mới thử kết nối được.';
    return blocked;
  }
  const external = provider.provider_type === 'EXTERNAL';
  return button('Thử kết nối', () => dialog(context, {
    title: `Thử kết nối ${model.display_name}`, submit: 'Thử kết nối',
    description: external ? null : 'Hệ thống gửi một yêu cầu cố định, ngắn, không chứa dữ liệu nhà trường và không trừ hạn mức của ai.',
    fields: external ? [el('div', { class: 'cost-notice', role: 'note' }, el('strong', {}, 'Thông báo chi phí'), el('p', {}, COST_NOTICE)),
      el('label', { class: 'choice' }, el('input', { type: 'checkbox', name: 'acknowledge', value: 'yes', required: true }),
        ' Tôi đã đọc và đồng ý rằng nhà cung cấp có thể tính phí cho lượt thử này.')] : [],
    save: async values => {
      if (external && values.acknowledge !== 'yes') throw new RequestError(422, null, errorMessages.MDL_CHARGES_NOT_ACKNOWLEDGED);
      const result = await write(context, `/models/${model.id}/connection-tests`, {
        method: 'POST', body: external ? { acknowledge_provider_charges: true } : {},
      });
      return result.status === 'PASSED' ? 'Thử kết nối thành công.'
        : `Thử kết nối thất bại: ${testErrors[result.error_code] ?? result.error_code}.`;
    },
  }), 'primary');
}

function testHistory(context, model) {
  return listing(context, {
    path: `/mdl/models/${model.id}/connection-tests`, heading: 'Lịch sử thử kết nối',
    headers: ['Bắt đầu', 'Kết quả', 'Lỗi', 'Nhóm mã HTTP', 'Thời gian (ms)', 'Còn áp dụng'],
    row: test => [dateLabel(test.started_at), pair(testResults[test.status]), test.error_code ? testErrors[test.error_code] ?? test.error_code : '—',
      test.http_status_class ? `${test.http_status_class}xx` : '—', test.latency_ms ?? '—',
      test.status === 'RUNNING' ? '—' : test.current ? 'Có' : 'Không (cấu hình đã đổi)'],
  });
}

async function modelDetail(context, id, manage) {
  const model = await read(context, `/models/${id}`);
  if (!context.current()) return;
  const provider = await read(context, `/providers/${model.provider_id}`);
  if (!context.current()) return;
  const path = `/models/${model.id}`;
  const controls = manage ? actions(connectionTest(context, model, provider),
    button('Sửa mô hình', () => dialog(context, {
      title: 'Sửa mô hình', fields: [
        field({ name: 'display_name', label: 'Tên hiển thị', value: model.display_name, required: true, max: 255 }),
        capabilityField(model.capabilities),
        field({ name: 'max_output_tokens', label: 'Độ dài tối đa kết quả (token, để trống nếu không áp dụng)', type: 'number', value: model.max_output_tokens ?? '', min: 1, max: 7 }),
      ],
      save: async (values, form) => write(context, path, { method: 'PATCH', body: {
        display_name: values.display_name.trim(), capabilities: capabilityValues(form), max_output_tokens: tokensValue(values.max_output_tokens),
      } }),
    })),
    button('Phân loại rủi ro', () => dialog(context, {
      title: 'Phân loại rủi ro mô hình', fields: [riskField(model.risk_level), riskGuidance()],
      description: 'Mức rủi ro do nhà trường xác định cho mô hình này; hệ thống không gán mặc định theo nhà cung cấp.',
      save: values => write(context, path, { method: 'PATCH', body: { risk_level: values.risk_level || null } }),
    })),
    stateAction(context, path, model.active, 'mô hình')) : null;
  return [link('← Danh sách mô hình', 'mdl/models'), panel(model.display_name, actions(activeBadge(model.active), riskBadge(model.risk_level)), facts([
    ['Nhà cung cấp', link(provider.name, `mdl/providers/${provider.id}`)], ['Mã kỹ thuật', el('code', {}, model.technical_id)],
    ['Khả năng', model.capabilities.map(code => capabilities[code]).join(', ')],
    ['Độ dài tối đa kết quả', model.max_output_tokens ? `${model.max_output_tokens} token` : 'Không áp dụng'],
    ['Mức rủi ro', riskBadge(model.risk_level)], ['Thử kết nối', testBadge(model.connection_test)],
    ['Lần thử áp dụng', dateLabel(model.connection_test.finished_at)], ['Đưa vào dùng', eligibility(model.routing)],
  ]), controls), testHistory(context, model), configurationHistory(context, { target_id: model.id }, 'Lịch sử cấu hình mô hình')];
}

// -------------------------------------------------------------------- routing

function slotRows(routing) {
  return Object.entries(slots).map(([key, title]) => {
    const slot = routing[key];
    if (!slot) return [title, 'Chưa chọn', '—', '—', '—'];
    return [title, link(slot.display_name, `mdl/models/${slot.model_id}`), link(slot.provider_name, `mdl/providers/${slot.provider_id}`),
      slot.usable ? badge('Được dùng', 'green') : badge('Không được dùng', 'amber'),
      slot.issues.length ? el('ul', { class: 'plain-list issue-list' }, slot.issues.map(code => el('li', {}, issueLabel(code)))) : '—'];
  });
}

function modelChoice(model, providersById) {
  return [model.id, `${model.display_name} · ${model.technical_id} · ${providersById[model.provider_id] ?? ''}`];
}

function routingDialog(context, routing) {
  const loading = el('p', { class: 'field', role: 'status' }, 'Đang tải danh sách mô hình đủ điều kiện…');
  dialog(context, {
    title: 'Đổi mô hình chính / dự phòng', submit: 'Lưu cấu hình', fields: [loading],
    description: 'Chỉ mô hình đủ điều kiện (đã thử kết nối thành công, đã phân loại rủi ro, có thỏa thuận dữ liệu nếu là nhà cung cấp bên ngoài) mới được chọn. Mô hình đang ở vị trí cũ được giữ nguyên nếu bạn không đổi.',
    save: async values => {
      const primary = values.primary_model_id || null;
      const fallback = values.fallback_model_id || null;
      if (fallback && fallback === primary) throw new RequestError(422, null, errorMessages.MDL_FALLBACK_EQUALS_PRIMARY);
      if (fallback && !primary) throw new RequestError(422, null, 'Hãy chọn mô hình chính trước khi chọn mô hình dự phòng.');
      const reference = values.decision_reference?.trim();
      await write(context, '/routing', { method: 'PUT', body: {
        expected_revision: routing.revision, primary_model_id: primary, fallback_model_id: fallback,
        ...(reference ? { decision_reference: reference } : {}),
      } });
    },
  });
  const submit = loading.closest('form').querySelector('[type="submit"]');
  submit.disabled = true;
  Promise.all([readAll(context, '/models', { routing_eligible: true }), readAll(context, '/providers')]).then(([eligible, providerList]) => {
    if (!loading.isConnected || !context.current()) return;
    const providersById = Object.fromEntries(providerList.items.map(item => [item.id, item.name]));
    const choices = eligible.items.map(model => modelChoice(model, providersById));
    const keep = slot => routing[slot] && !eligible.items.some(model => model.id === routing[slot].model_id)
      ? [[routing[slot].model_id, `${routing[slot].display_name} · giữ nguyên (hiện ${routing[slot].usable ? 'được dùng' : 'không đủ điều kiện'})`]] : [];
    loading.replaceWith(
      field({ name: 'primary_model_id', label: 'Mô hình chính', value: routing.primary?.model_id ?? '',
        options: [['', '— Không cấu hình —'], ...keep('primary'), ...choices] }),
      field({ name: 'fallback_model_id', label: 'Mô hình dự phòng', value: routing.fallback?.model_id ?? '',
        options: [['', '— Không dùng dự phòng —'], ...keep('fallback'), ...choices] }),
      field({ name: 'decision_reference', label: 'Số văn bản quyết định (nếu có)', max: 128,
        hint: 'Ví dụ số quyết định của Ban Giám hiệu. Được lưu cùng phiên bản cấu hình và không sửa được.' }),
      !choices.length && el('p', { class: 'hint' }, 'Chưa có mô hình nào đủ điều kiện. Hãy thử kết nối và phân loại rủi ro trước.'));
    submit.disabled = false;
  }).catch(error => {
    if (loading.isConnected && context.current()) showError(loading, error);
  });
}

async function routingTab(context, manage) {
  const [routing, status] = await Promise.all([read(context, '/routing'), read(context, '/status')]);
  if (!context.current()) return;
  const effective = routing.effective;
  const effectiveModel = [routing.primary, routing.fallback].find(slot => slot?.model_id === effective.model_id);
  const allowlist = { EMPTY: 'Chưa cho phép địa chỉ nội bộ nào', CONFIGURED: `${status.egress.internal_allowlist_entries} địa chỉ được cho phép`, INVALID: 'Cấu hình không hợp lệ — không cho phép địa chỉ nội bộ nào' };
  return [panel('Mô hình đang được dùng', actions(pair(effectiveStates[effective.state])), facts([
    ['Mô hình thực tế', effectiveModel ? link(effectiveModel.display_name, `mdl/models/${effectiveModel.model_id}`) : 'Không có'],
    ['Phiên bản cấu hình', routing.revision ? String(routing.revision) : 'Chưa cấu hình'],
    ['Cập nhật', dateLabel(routing.updated_at)],
  ]), table(['Vai trò', 'Mô hình', 'Nhà cung cấp', 'Sử dụng', 'Lý do không được dùng'], slotRows(routing)),
  el('p', { class: 'hint' }, 'Cấu hình chỉ thay đổi khi quản trị viên lưu. Mỗi lần xem, hệ thống kiểm tra lại từng mô hình; mô hình không còn đủ điều kiện (thử thất bại, cấu hình đổi, thu hồi thỏa thuận…) sẽ không được dùng, và mô hình dự phòng đủ điều kiện được dùng thay.'),
  manage && actions(button('Đổi mô hình chính / dự phòng', () => routingDialog(context, routing), 'primary'))),
  panel('Trạng thái hệ thống', facts([
    ['Khóa mã hóa bí mật', status.credential_keys === 'AVAILABLE' ? badge('Sẵn sàng', 'green') : badge('Chưa sẵn sàng — không lưu hay dùng được bí mật', 'amber')],
    ['Nhà cung cấp bên ngoài', 'Chỉ https, cổng 443, tên miền công khai'],
    ['Địa chỉ nội bộ', allowlist[status.egress.internal_allowlist]],
    ['Chứng chỉ nội bộ bổ sung', { NONE: 'Không', CONFIGURED: 'Đã cấu hình', UNREADABLE: 'Không đọc được' }[status.egress.internal_ca]],
    ['Giới hạn mỗi lượt thử', `${status.egress.timeout_seconds} giây, không chuyển hướng, không thử lại`],
  ]))];
}

// ------------------------------------------------------------ other tabs

function agreementsTab(context) {
  return [el('p', { class: 'notice' }, `Nhà cung cấp bên ngoài cần thỏa thuận bảo vệ dữ liệu còn hiệu lực trước khi thử kết nối hoặc đưa mô hình vào dùng. ${LEGAL_NOTICE}`),
    listing(context, {
      path: '/mdl/providers', query: { provider_type: 'EXTERNAL' }, heading: 'Nhà cung cấp bên ngoài',
      headers: ['Nhà cung cấp', 'Thỏa thuận đang hiệu lực', 'Căn cứ', 'Trạng thái'],
      row: provider => [link(provider.name, `mdl/providers/${provider.id}`), agreementSummary(provider),
        provider.agreement_in_force ? bases[provider.agreement_in_force.basis] : '—', activeBadge(provider.active)],
    })];
}

// M7 (FRD section 6 "Should"): configuration history with a field-by-field comparison.
// Values come from the typed audit payloads, which never contain a secret, ciphertext or
// the endpoint path (only its origin, plus a flag when the path changed).
const eventLabels = {
  'mdl.provider_created': 'Thêm nhà cung cấp', 'mdl.provider_updated': 'Sửa nhà cung cấp',
  'mdl.provider_state_changed': 'Đổi trạng thái nhà cung cấp', 'mdl.provider_credential_rotated': 'Thay bí mật kết nối',
  'mdl.agreement_recorded': 'Ghi nhận thỏa thuận', 'mdl.agreement_withdrawn': 'Thu hồi thỏa thuận',
  'mdl.model_created': 'Thêm mô hình', 'mdl.model_updated': 'Sửa mô hình', 'mdl.model_state_changed': 'Đổi trạng thái mô hình',
  'mdl.model_risk_changed': 'Đổi mức rủi ro', 'mdl.routing_changed': 'Đổi mô hình chính / dự phòng',
  'mdl.credential_rewrapped': 'Mã hóa lại bí mật (xoay khóa)',
};
const fieldLabels = {
  name: 'Tên', provider_type: 'Loại', api_style: 'Kiểu API', endpoint_origin: 'Máy chủ', auth_scheme: 'Kiểu xác thực',
  auth_header_name: 'Header chứa khóa', has_credential: 'Có bí mật kết nối', technical_id: 'Mã kỹ thuật',
  display_name: 'Tên hiển thị', capabilities: 'Khả năng', max_output_tokens: 'Độ dài tối đa kết quả', risk_level: 'Mức rủi ro',
  basis: 'Căn cứ', document_number: 'Số văn bản', signed_on: 'Ngày ký', credential_version: 'Phiên bản bí mật',
  revision: 'Phiên bản cấu hình', decision_reference: 'Số văn bản quyết định', key_id_before: 'Khóa trước', key_id_after: 'Khóa sau',
};
const valueLabels = { provider_type: providerTypes, api_style: apiStyles, auth_scheme: authSchemes, risk_level: risks, basis: bases };

function valueText(key, value) {
  if (value === null || value === undefined || value === '') return '—';
  if (key === 'capabilities') return value.map(code => capabilities[code] ?? code).join(', ');
  if (key === 'active') return value ? 'Đang hoạt động' : 'Ngừng hoạt động';
  if (typeof value === 'boolean') return value ? 'Có' : 'Không';
  return String(valueLabels[key]?.[value] ?? value);
}

function changeLines(event) {
  const { changes } = event;
  const line = (key, text) => el('li', {}, el('strong', {}, `${fieldLabels[key] ?? key}: `), text);
  const diff = (key, before, after) => line(key, `${valueText(key, before)} → ${valueText(key, after)}`);
  if (event.action === 'mdl.routing_changed') {
    return [line('revision', String(changes.revision)), changes.decision_reference && line('decision_reference', changes.decision_reference),
      el('li', { class: 'hint' }, 'Tên mô hình trước / sau: xem bảng lịch sử mô hình chính / dự phòng.')];
  }
  if ('before' in changes && 'after' in changes && (typeof changes.before !== 'object' || changes.before === null)) {
    return [diff(event.action.endsWith('risk_changed') ? 'risk_level' : 'active', changes.before, changes.after)];
  }
  if (changes.before && changes.after) {
    const keys = [...new Set([...Object.keys(changes.before), ...Object.keys(changes.after)])];
    const lines = keys.filter(key => JSON.stringify(changes.before[key]) !== JSON.stringify(changes.after[key]))
      .map(key => diff(key, changes.before[key], changes.after[key]));
    if (changes.endpoint_changed && !lines.some(item => item.textContent.startsWith(fieldLabels.endpoint_origin))) {
      lines.push(el('li', {}, 'Đường dẫn địa chỉ kết nối đã đổi'));
    }
    return lines.length ? lines : [el('li', { class: 'muted' }, 'Không đổi giá trị hiển thị')];
  }
  return Object.entries(changes).filter(([key]) => key !== 'provider_id').map(([key, value]) => line(key, valueText(key, value)));
}

function eventTarget(event) {
  if (event.target_type === 'mdl_provider') return link('Nhà cung cấp', `mdl/providers/${event.target_id}`);
  if (event.target_type === 'mdl_model') return link('Mô hình', `mdl/models/${event.target_id}`);
  if (event.target_type === 'mdl_agreement') return link('Thỏa thuận', `mdl/providers/${event.changes.provider_id}`);
  return 'Mô hình chính / dự phòng';
}

function configurationHistory(context, query = {}, heading = 'Lịch sử cấu hình (so sánh trước / sau)') {
  return listing(context, {
    path: '/mdl/history', heading, query,
    headers: ['Thời điểm', 'Thao tác', 'Đối tượng', 'Thay đổi', 'Người thực hiện'],
    row: event => [dateLabel(event.occurred_at), eventLabels[event.action] ?? event.action, eventTarget(event),
      el('ul', { class: 'plain-list change-list' }, changeLines(event)),
      event.actor_id ? el('code', {}, event.actor_id) : 'Người vận hành (dòng lệnh)'],
  });
}

function historyTab(context) {
  const slotText = (name, id) => (id ? name : '—');
  return [routingHistory(context, slotText), configurationHistory(context)];
}

function routingHistory(context, slotText) {
  return listing(context, {
    path: '/mdl/routing/revisions', heading: 'Lịch sử mô hình chính / dự phòng',
    headers: ['Phiên bản', 'Thời điểm', 'Trước (chính / dự phòng)', 'Sau (chính / dự phòng)', 'Số văn bản', 'Người thay đổi'],
    row: revision => [String(revision.revision), dateLabel(revision.changed_at),
      `${slotText(revision.before_primary_name, revision.before_primary_model_id)} / ${slotText(revision.before_fallback_name, revision.before_fallback_model_id)}`,
      `${slotText(revision.after_primary_name, revision.after_primary_model_id)} / ${slotText(revision.after_fallback_name, revision.after_fallback_model_id)}`,
      revision.decision_reference ?? '—', el('code', {}, revision.changed_by)],
  });
}

export async function mdlPage(context, tab = 'routing', id) {
  const manage = permission(context.caps, 'mdl.manage');
  const nav = el('nav', { class: 'tabs', 'aria-label': 'Mục cấu hình AI' }, Object.entries(tabs).map(([key, title]) =>
    el('a', { href: key === 'routing' ? '#mdl' : `#mdl/${key}`, 'aria-current': key === tab ? 'page' : undefined }, title)));
  let body;
  if (tab === 'providers') body = id ? await providerDetail(context, id, manage) : providers(context, manage);
  else if (tab === 'models') body = id ? await modelDetail(context, id, manage) : models(context, manage);
  else if (tab === 'agreements') body = agreementsTab(context);
  else if (tab === 'history') body = historyTab(context);
  else body = await routingTab(context, manage);
  if (!context.current()) return;
  return [nav, body];
}
