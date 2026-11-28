import { permission, RequestError } from './api.mjs';
import {
  actions, badge, button, dateLabel, el, facts, field, formDialog,
  link, listing, option, panel, reference, showError, submitForm, table,
} from './ui.mjs';

export const tabs = {
  groups: 'Nhóm & Hạn mức',
  lookup: 'Tra cứu cá nhân & tạm ngưng',
  ledger: 'Lịch sử & Làm mới tháng',
};

const UNIT_LABEL = 'đơn vị hạn mức';
const CONSUMPTION_NOTICE = 'Chưa tích hợp đo tiêu thụ thực tế';
const viNumber = new Intl.NumberFormat('vi-VN');
const fmtInt = value => viNumber.format(value);
const fmtUnits = value => `${viNumber.format(value)} ${UNIT_LABEL}`;

const groupKindLabels = { SYSTEM: 'Hệ thống', AI_SPECIALIST: 'AI chuyên biệt' };
const originLabels = { SYNC: 'Đồng bộ danh bạ', SPECIALIST: 'Tạo trong QTA' };
const providerTypeLabels = { EXTERNAL: 'Ngoài trường', INTERNAL: 'Nội bộ' };
const accountStateLabels = { ACTIVE: 'Đang hoạt động', PENDING: 'Chờ kích hoạt', DISABLED: 'Đã vô hiệu hóa' };
const quotaStatusLabels = { ACTIVE: 'Được dùng AI', SUSPENDED: 'ĐÃ CẮT' };
const scopeLabels = {
  ALL_MODELS: 'Toàn bộ mô hình AI',
  PAID_EXTERNAL_ONLY: 'Chỉ mô hình ngoài trường (trả phí)',
};
const suspensionStatusLabels = {
  ACTIVE: 'Đang hiệu lực',
  RESTORED: 'Đã khôi phục',
  EXPIRED: 'Đã hết hạn',
};
const exclusionLabels = {
  NOT_ENROLLED: 'Chưa đưa vào quản lý hạn mức',
  RETIRED: 'Đã rút khỏi danh bạ',
  GROUP_INACTIVE: 'Nhóm ngừng hoạt động',
  USER_NOT_ACTIVE: 'Tài khoản chưa hoạt động',
};
const accessReasonLabels = {
  USER_NOT_FOUND: 'Không tìm thấy tài khoản',
  USER_NOT_ACTIVE: 'Tài khoản chưa hoạt động',
  MODEL_UNAVAILABLE: 'Mô hình không khả dụng',
  SUSPENDED_ALL_MODELS: 'Tạm ngưng toàn bộ mô hình',
  SUSPENDED_PAID_EXTERNAL: 'Tạm ngưng mô hình ngoài trường',
  NO_ENTITLEMENT: 'Không có hạn mức',
};
const eventTypeLabels = {
  MONTHLY_REFRESH: 'Làm mới đầu tháng',
  SUSPEND: 'Tạm ngưng quyền AI',
  RESTORE: 'Khôi phục quyền AI',
};
const triggerModeLabels = {
  SCHEDULED: 'Tự động theo lịch',
  MANUAL_SIMULATION: 'Mô phỏng thủ công',
};

const errorMessages = {
  QTA_BUDGET_BELOW_ALLOCATED: 'Tổng hạn mức tháng không thể nhỏ hơn tổng đang phân bổ hiện tại.',
  QTA_INVALID_PERIOD: 'Tháng áp dụng phải có định dạng hợp lệ (YYYY-MM).',
  QTA_PERIOD_NOT_OPEN: 'Chỉ được thao tác trong tháng hiện tại hoặc tháng kế tiếp.',
  QTA_GROUP_NOT_ELIGIBLE: 'Nhóm tài khoản này không thuộc phạm vi quản lý hạn mức AI.',
  QTA_MODEL_NOT_ELIGIBLE: 'Mô hình AI này hiện không đủ điều kiện cấu hình hạn mức.',
  QTA_USER_ALREADY_SUSPENDED: 'Tài khoản này hiện đang bị tạm ngưng quyền AI.',
  QTA_USER_NOT_SUSPENDED: 'Tài khoản này hiện không có lệnh tạm ngưng đang hiệu lực.',
  QTA_RESET_ALREADY_EXECUTED: 'Tháng hiện tại đã được ghi nhận làm mới hạn mức.',
  QTA_DUPLICATE: 'Mã nhóm hoặc bản ghi hạn mức đã tồn tại.',
  NOT_FOUND: 'Không tìm thấy bản ghi phù hợp hoặc ngoài phạm vi quyền xem.',
  VALIDATION_FAILED: 'Dữ liệu nhập chưa hợp lệ. Vui lòng kiểm tra lại các trường bắt buộc.',
};

// Preserve selected user/months across context.updated() refreshes within one signed-in session.
let sessionViewerId;
let selectedBudgetMonth;
let selectedLookupMonth;
let selectedLookupUserId;
let selectedLedgerMonth;

function syncSessionState(context) {
  const viewerId = context.me?.id;
  if (sessionViewerId !== viewerId) {
    sessionViewerId = viewerId;
    selectedBudgetMonth = undefined;
    selectedLookupMonth = undefined;
    selectedLookupUserId = undefined;
    selectedLedgerMonth = undefined;
  }
}

function currentAndNextMonths() {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Ho_Chi_Minh', year: 'numeric', month: '2-digit', day: '2-digit',
  }).formatToParts(new Date());
  const year = Number(parts.find(part => part.type === 'year').value);
  const month = Number(parts.find(part => part.type === 'month').value);
  const day = Number(parts.find(part => part.type === 'day').value);
  const pad = value => String(value).padStart(2, '0');
  const current = `${year}-${pad(month)}`;
  const nextYear = month === 12 ? year + 1 : year;
  const nextMonth = month === 12 ? 1 : month + 1;
  const next = `${nextYear}-${pad(nextMonth)}`;
  const today = `${year}-${pad(month)}-${pad(day)}`;
  return { current, next, today };
}

function localizeError(error) {
  if (!(error instanceof RequestError)) return error;
  if (error.code === 'QTA_BUDGET_BELOW_ALLOCATED') {
    const allocated = error.details?.allocated;
    const deficit = error.details?.deficit;
    if (typeof allocated === 'number' && typeof deficit === 'number') {
      const msg = `Tổng hạn mức tháng không thể nhỏ hơn tổng đang phân bổ hiện tại (${fmtUnits(allocated)}; thiếu ${fmtUnits(deficit)}). Hãy giảm hạn mức nhóm hoặc tăng tổng hạn mức tháng.`;
      return new RequestError(error.status, error.requestId, msg, error.code, error.details);
    }
  }
  const mapped = errorMessages[error.code];
  return mapped ? new RequestError(error.status, error.requestId, mapped, error.code, error.details) : error;
}

async function qtaWrite(context, path, options) {
  try {
    return await context.write(path, options);
  } catch (error) {
    throw localizeError(error);
  }
}

async function qtaRead(context, path, query) {
  try {
    return await context.read(path, query);
  } catch (error) {
    throw localizeError(error);
  }
}

function actorLabel(context, actorId, fallback = 'Hệ thống') {
  if (!actorId) return fallback;
  if (context.me?.id && actorId === context.me.id) {
    return el('span', {}, el('code', {}, actorId), ' ', badge('Bạn', 'blue'));
  }
  return el('code', {}, actorId);
}

function stateBadge(state) {
  const theme = state === 'ACTIVE' ? 'green' : state === 'PENDING' ? 'amber' : 'neutral';
  return badge(accountStateLabels[state] ?? state, theme);
}

function quotaStatusBadge(status) {
  return badge(quotaStatusLabels[status] ?? status, status === 'SUSPENDED' ? 'red' : 'green');
}

function suspensionStatusBadge(status) {
  const theme = status === 'ACTIVE' ? 'red' : status === 'RESTORED' ? 'green' : 'neutral';
  return badge(suspensionStatusLabels[status] ?? status, theme);
}

function activeBadge(active) {
  return badge(active ? 'Đang hoạt động' : 'Ngừng hoạt động', active ? 'green' : 'neutral');
}

function intField({ name, label, value = '', min = 0, max, required = false, hint, placeholder }) {
  const id = `qta-int-${Math.random().toString(36).slice(2, 9)}`;
  const input = el('input', {
    id, name, type: 'number', min: String(min), max: max !== undefined ? String(max) : undefined,
    step: '1', required, placeholder, inputmode: 'numeric',
    'aria-describedby': hint ? `${id}-hint` : undefined,
  });
  input.value = value === null || value === undefined ? '' : String(value);
  return el('div', { class: 'field' }, el('label', { for: id }, label), input,
    hint && el('small', { id: `${id}-hint`, class: 'hint' }, hint));
}

function dateField({ name, label, value = '', required = false, hint }) {
  const id = `qta-date-${Math.random().toString(36).slice(2, 9)}`;
  const input = el('input', {
    id, name, type: 'date', required, 'aria-describedby': hint ? `${id}-hint` : undefined,
  });
  input.value = value ?? '';
  return el('div', { class: 'field' }, el('label', { for: id }, label), input,
    hint && el('small', { id: `${id}-hint`, class: 'hint' }, hint));
}

function parseNonNegativeInt(raw, label) {
  const text = String(raw ?? '').trim();
  if (!/^\d+$/.test(text)) throw new RequestError(422, null, `${label} phải là số nguyên không âm.`);
  const parsed = Number(text);
  if (!Number.isSafeInteger(parsed)) throw new RequestError(422, null, `${label} vượt quá giới hạn số nguyên an toàn.`);
  return parsed;
}

// ---------------------------------------------------------------------------
// School Monthly Budget Header (GLOBAL qta.read only)
// ---------------------------------------------------------------------------

function openBudgetDialog(context, month, currentBudget, today) {
  formDialog(context, {
    title: `Cập nhật tổng hạn mức tháng ${month}`,
    description: 'Mỗi lần lưu sẽ ghi nhận thêm một phiên bản quyết định mới (chỉ ghi thêm, không ghi đè lịch sử).',
    submit: 'Ghi nhận tổng hạn mức',
    fields: [
      intField({
        name: 'total_limit',
        label: `Tổng hạn mức tháng (${UNIT_LABEL})`,
        value: currentBudget?.total_limit ?? '',
        min: 1,
        required: true,
        hint: `Nhập số nguyên dương tính theo ${UNIT_LABEL}.`,
      }),
      field({
        name: 'decision_number',
        label: 'Số quyết định',
        value: '',
        required: true,
        max: 128,
        hint: 'Ví dụ: QD-2026-11',
      }),
      dateField({
        name: 'decision_date',
        label: 'Ngày ban hành quyết định',
        value: today,
        required: true,
      }),
    ],
    save: async values => {
      const totalLimit = parseNonNegativeInt(values.total_limit, 'Tổng hạn mức tháng');
      if (totalLimit < 1) throw new RequestError(422, null, 'Tổng hạn mức tháng phải lớn hơn hoặc bằng 1.');
      const decisionNumber = String(values.decision_number ?? '').trim();
      const decisionDate = String(values.decision_date ?? '').trim();
      if (!decisionNumber) throw new RequestError(422, null, 'Vui lòng nhập số quyết định.');
      await qtaWrite(context, `/qta/budgets/${encodeURIComponent(month)}`, {
        method: 'PUT',
        body: {
          total_limit: totalLimit,
          decision_number: decisionNumber,
          decision_date: decisionDate,
        },
      });
      return `Đã ghi nhận tổng hạn mức tháng ${month}.`;
    },
  });
}

function budgetHeaderPanel(context, manage) {
  const { current, next, today } = currentAndNextMonths();
  if (!selectedBudgetMonth) selectedBudgetMonth = current;

  const container = el('section', { class: 'panel', 'aria-label': 'Tổng hạn mức AI theo tháng của trường' });
  const heading = el('h2', {}, 'Tổng hạn mức AI toàn trường theo tháng');
  const monthInput = el('input', {
    id: 'qta-budget-month',
    name: 'budget_month',
    type: 'month',
    'aria-label': 'Chọn tháng tổng hạn mức',
  });
  monthInput.value = selectedBudgetMonth;

  const actionSlot = el('div', { class: 'actions' });
  const body = el('div', { class: 'qta-budget-body' }, el('p', { class: 'empty' }, 'Đang tải tổng hạn mức tháng…'));
  const alertBox = el('div', { class: 'alert', role: 'alert', hidden: true });
  const headerBar = el(
    'div',
    { class: 'qta-header-bar' },
    el('div', { class: 'field' }, el('label', { for: 'qta-budget-month' }, 'Tháng áp dụng'), monthInput),
    actionSlot,
  );
  container.append(heading, headerBar, alertBox, body);

  // Same stale-response guard as the lookup: only the newest month request may render.
  let loadSequence = 0;
  async function loadBudget(month) {
    const load = ++loadSequence;
    const isLatest = () => load === loadSequence && context.current();
    alertBox.hidden = true;
    actionSlot.replaceChildren();
    body.replaceChildren(el('p', { class: 'empty' }, 'Đang tải tổng hạn mức tháng…'));
    try {
      const budget = await qtaRead(context, '/qta/budgets', { month });
      if (!isLatest()) return;

      const isOpen = budget.month === current || budget.month === next;
      if (manage) {
        if (isOpen) {
          actionSlot.append(
            button('Cập nhật tổng hạn mức tháng', () => openBudgetDialog(context, budget.month, budget.current, today), 'primary'),
          );
        } else {
          actionSlot.append(badge('Tháng đã đóng — chỉ xem', 'neutral'));
        }
      }

      const isLive = budget.allocation_status === 'LIVE';
      const allocatedText = isLive ? fmtUnits(budget.allocated) : 'Chưa chụp ảnh lịch sử';
      const remainingText = isLive && budget.current ? fmtUnits(budget.remaining) : '—';
      const overAllocatedNode = isLive && budget.current
        ? (budget.over_allocated > 0 ? badge(`Vượt trần ${fmtUnits(budget.over_allocated)}`, 'red') : fmtUnits(0))
        : '—';
      const decisionText = budget.current
        ? `${budget.current.decision_number} (${budget.current.decision_date}) · Phiên bản #${budget.current.revision}`
        : 'Chưa có quyết định';

      const metrics = el(
        'div',
        { class: 'qta-metrics' },
        el('div', { class: 'qta-metric' }, el('div', { class: 'qta-metric-label' }, 'Trạng thái ghi nhận'),
          el('div', { class: 'qta-metric-value' }, badge(budget.status_label, budget.status === 'RECORDED' ? 'green' : 'amber'))),
        el('div', { class: 'qta-metric' }, el('div', { class: 'qta-metric-label' }, 'Tổng hạn mức tháng'),
          el('div', { class: 'qta-metric-value' }, budget.current ? fmtUnits(budget.current.total_limit) : 'Chưa ghi nhận')),
        el('div', { class: 'qta-metric' }, el('div', { class: 'qta-metric-label' }, 'Đang phân bổ hiện tại'),
          el('div', { class: 'qta-metric-value' }, allocatedText)),
        el('div', { class: 'qta-metric' }, el('div', { class: 'qta-metric-label' }, 'Chưa phân bổ / Vượt trần'),
          el('div', { class: 'qta-metric-value' },
            isLive && budget.current && budget.over_allocated > 0 ? overAllocatedNode : remainingText)),
      );

      const summaryNote = el(
        'p',
        { class: 'muted' },
        `Quyết định hiện hành: ${decisionText}. Đo tiêu thụ thực tế: ${CONSUMPTION_NOTICE}.`,
      );

      const revisionTable = budget.revisions.length
        ? el(
          'details',
          { class: 'guidance qta-revisions', open: true },
          el('summary', {}, `Lịch sử phiên bản tổng hạn mức tháng ${budget.month} (${budget.revisions.length})`),
          table(
            ['Phiên bản', 'Tổng hạn mức', 'Số quyết định', 'Ngày quyết định', 'Người ghi nhận', 'Thời điểm ghi nhận'],
            budget.revisions.map(rev => [
              `#${rev.revision}`,
              fmtUnits(rev.total_limit),
              el('code', {}, rev.decision_number),
              rev.decision_date,
              actorLabel(context, rev.recorded_by),
              dateLabel(rev.recorded_at),
            ]),
          ),
        )
        : el('p', { class: 'muted' }, `Chưa có phiên bản tổng hạn mức nào được ghi nhận cho tháng ${budget.month}.`);

      body.replaceChildren(metrics, summaryNote, revisionTable);
    } catch (error) {
      if (error.name === 'AbortError' || !isLatest()) return;
      showError(alertBox, error);
      body.replaceChildren();
    }
  }

  monthInput.addEventListener('change', () => {
    if (!monthInput.value) return;
    selectedBudgetMonth = monthInput.value;
    loadBudget(selectedBudgetMonth);
  });

  loadBudget(selectedBudgetMonth);
  return container;
}

// ---------------------------------------------------------------------------
// Tab 1: Nhóm & Hạn mức (#qta / #qta/groups & #qta/groups/<uuid>)
// ---------------------------------------------------------------------------

function summarizeQuotas(quotas) {
  if (!quotas || quotas.length === 0) return 'Chưa cấu hình';
  const enabled = quotas.filter(q => q.enabled);
  if (enabled.length === 0) return `${quotas.length} quy tắc (đang tắt)`;
  const preview = enabled.slice(0, 2).map(q => `${q.model_display_name}: ${fmtUnits(q.monthly_limit)}`).join('; ');
  return enabled.length > 2 ? `${preview} (+${enabled.length - 2})` : preview;
}

function groupsTab(context, manage) {
  const syncAlert = el('div', { class: 'alert', role: 'alert', hidden: true });
  const syncButton = button('Đồng bộ nhóm từ Hệ thống', async () => {
    syncButton.disabled = true;
    syncAlert.hidden = true;
    try {
      const run = await qtaWrite(context, '/qta/groups/sync', { method: 'POST' });
      await context.updated(
        `Đã đồng bộ nhóm hệ thống: ${fmtInt(run.system_group_count)} nhóm hệ thống, ${fmtInt(run.active_member_count)} thành viên hoạt động (thêm mới ${fmtInt(run.groups_added)}, rút khỏi danh bạ ${fmtInt(run.groups_retired)}).`,
      );
    } catch (error) {
      if (error.name !== 'AbortError') showError(syncAlert, error);
    } finally {
      syncButton.disabled = false;
    }
  }, 'secondary');

  const createButton = button('Tạo nhóm AI chuyên biệt', () => formDialog(context, {
    title: 'Tạo nhóm AI chuyên biệt',
    description: 'Nhóm AI chuyên biệt được tạo trực tiếp tại QTA để cộng dồn thêm hạn mức cho các nhóm đặc thù (ví dụ: phòng thí nghiệm, nhóm nghiên cứu).',
    submit: 'Tạo nhóm',
    fields: [
      field({ name: 'code', label: 'Mã nhóm', required: true, max: 64, hint: 'Mã duy nhất trong trường, ví dụ: AI_LAB.' }),
      field({ name: 'name', label: 'Tên nhóm', required: true, max: 255 }),
    ],
    save: async values => {
      await qtaWrite(context, '/qta/groups', {
        method: 'POST',
        body: { code: values.code.trim(), name: values.name.trim() },
      });
      return 'Đã tạo nhóm AI chuyên biệt.';
    },
  }), 'primary');

  const topActions = manage ? [syncButton, createButton] : [];

  const groupsListing = listing(context, {
    path: '/qta/groups',
    heading: 'Danh sách nhóm áp dụng hạn mức AI',
    toolbar: topActions,
    filters: [
      field({ name: 'q', label: 'Tìm kiếm nhóm', type: 'search', max: 128 }),
      field({
        name: 'kind', label: 'Loại nhóm',
        options: [['', 'Tất cả'], ['SYSTEM', 'Hệ thống'], ['AI_SPECIALIST', 'AI chuyên biệt']],
      }),
      field({
        name: 'active', label: 'Trạng thái',
        options: [['', 'Tất cả'], ['true', 'Đang hoạt động'], ['false', 'Ngừng hoạt động']],
      }),
      field({
        name: 'in_directory', label: 'Danh bạ',
        options: [['', 'Tất cả'], ['true', 'Còn trong danh bạ'], ['false', 'Đã rút khỏi danh bạ']],
      }),
    ],
    headers: ['Mã nhóm', 'Tên nhóm', 'Loại', 'Nguồn', 'Trạng thái', 'Thành viên hoạt động', 'Hạn mức mô hình'],
    row: group => [
      el('code', {}, group.code),
      link(group.name, `qta/groups/${group.id}`),
      badge(groupKindLabels[group.kind] ?? group.kind, group.kind === 'AI_SPECIALIST' ? 'blue' : 'neutral'),
      originLabels[group.origin] ?? group.origin,
      el('span', {}, activeBadge(group.active), !group.in_directory && ' ', !group.in_directory && badge('Đã rút khỏi danh bạ', 'amber')),
      fmtInt(group.active_member_count),
      summarizeQuotas(group.quotas),
    ],
  });

  const syncRunsListing = listing(context, {
    path: '/qta/groups/sync-runs',
    heading: 'Lịch sử đồng bộ nhóm hệ thống',
    headers: ['Thời điểm đồng bộ', 'Nhóm hệ thống', 'Thành viên hoạt động', 'Nhóm AI chuyên biệt', 'Thêm mới', 'Rút khỏi danh bạ', 'Người thực hiện'],
    row: run => [
      dateLabel(run.synced_at),
      fmtInt(run.system_group_count),
      fmtInt(run.active_member_count),
      fmtInt(run.specialist_group_count),
      fmtInt(run.groups_added),
      fmtInt(run.groups_retired),
      actorLabel(context, run.synced_by),
    ],
  });

  return el('div', { class: 'qta-section-stack' }, syncAlert, groupsListing, syncRunsListing);
}

async function groupDetailView(context, groupId, manage) {
  const [group, modelsPage] = await Promise.all([
    qtaRead(context, `/qta/groups/${groupId}`),
    qtaRead(context, '/qta/models', { limit: 100 }),
  ]);
  if (!context.current()) return;

  const isSpecialist = group.kind === 'AI_SPECIALIST';
  const specialistActions = [];
  if (manage && isSpecialist) {
    specialistActions.push(
      button('Đổi tên nhóm', () => formDialog(context, {
        title: 'Đổi tên nhóm AI chuyên biệt',
        fields: [field({ name: 'name', label: 'Tên nhóm mới', value: group.name, required: true, max: 255 })],
        save: async values => {
          await qtaWrite(context, `/qta/groups/${group.id}`, {
            method: 'PATCH',
            body: { name: values.name.trim() },
          });
          return 'Đã cập nhật tên nhóm AI chuyên biệt.';
        },
      })),
    );
    if (group.active) {
      specialistActions.push(
        button('Ngừng hoạt động', () => formDialog(context, {
          title: 'Ngừng hoạt động nhóm AI chuyên biệt',
          description: 'Nhóm ngừng hoạt động sẽ không còn cộng dồn hạn mức cho thành viên và tổng phân bổ trường sẽ tự cập nhật ngay.',
          submit: 'Xác nhận ngừng hoạt động',
          danger: true,
          save: async () => {
            await qtaWrite(context, `/qta/groups/${group.id}/deactivate`, { method: 'POST' });
            return 'Đã ngừng hoạt động nhóm AI chuyên biệt.';
          },
        }), 'danger-outline'),
      );
    } else {
      specialistActions.push(
        button('Kích hoạt lại', () => formDialog(context, {
          title: 'Kích hoạt lại nhóm AI chuyên biệt',
          description: 'Nhóm sẽ tiếp tục cộng dồn hạn mức đã cấu hình cho các thành viên đang hoạt động.',
          submit: 'Xác nhận kích hoạt',
          save: async () => {
            await qtaWrite(context, `/qta/groups/${group.id}/activate`, { method: 'POST' });
            return 'Đã kích hoạt lại nhóm AI chuyên biệt.';
          },
        }), 'primary'),
      );
    }
  }

  const summaryPanel = panel(
    `${group.name} (${group.code})`,
    specialistActions.length ? actions(...specialistActions) : undefined,
    !isSpecialist && el('p', { class: 'qta-banner-info' }, 'Nhóm Hệ thống được đồng bộ từ danh bạ trường; thành viên và trạng thái kích hoạt được quản lý tại mục Nhóm tài khoản.'),
    facts([
      ['Mã nhóm', el('code', {}, group.code)],
      ['Loại nhóm', badge(groupKindLabels[group.kind] ?? group.kind, isSpecialist ? 'blue' : 'neutral')],
      ['Nguồn quản lý', originLabels[group.origin] ?? group.origin],
      ['Trạng thái nhóm', activeBadge(group.active)],
      ['Trạng thái danh bạ', badge(group.in_directory ? 'Còn trong danh bạ' : 'Đã rút khỏi danh bạ', group.in_directory ? 'green' : 'amber')],
      ['Thành viên đang hoạt động', fmtInt(group.active_member_count)],
      ['Đồng bộ gần nhất', dateLabel(group.last_synced_at)],
      ['Người đưa vào QTA', actorLabel(context, group.enrolled_by)],
    ]),
  );

  // Build per-model quota configuration panel.
  const existingByModel = new Map(group.quotas.map(rule => [rule.model_id, rule]));
  const usableModels = modelsPage.items;
  // Classify by the server's model_active flag (model AND provider active), not by absence
  // from the first page of /qta/models, so a large catalog never mislabels a live rule.
  const inactiveRules = group.quotas.filter(rule => rule.model_active === false);

  const quotaSection = el('section', { class: 'panel' },
    el('h2', {}, 'Cấu hình hạn mức theo mô hình AI'),
    el('p', { class: 'muted' }, `Hạn mức áp dụng cho từng thành viên đang hoạt động mỗi tháng, tính theo ${UNIT_LABEL} (cộng dồn giữa các nhóm).`),
  );

  if (usableModels.length === 0 && inactiveRules.length === 0) {
    quotaSection.append(el('p', { class: 'empty' }, 'Chưa có mô hình AI nào đang hoạt động trong mục Cấu hình Nhà cung cấp & Mô hình AI.'));
  } else if (manage && usableModels.length > 0) {
    const quotaAlert = el('div', { class: 'alert', role: 'alert', hidden: true });
    const rowControls = usableModels.map(model => {
      const rule = existingByModel.get(model.id);
      const enabledBox = el('input', {
        type: 'checkbox',
        'aria-label': `Bật hạn mức cho ${model.display_name}`,
        checked: rule ? rule.enabled : false,
      });
      const limitInput = el('input', {
        type: 'number',
        class: 'qta-quota-input',
        min: '0',
        step: '1',
        inputmode: 'numeric',
        'aria-label': `Hạn mức tháng cho ${model.display_name} (${UNIT_LABEL})`,
      });
      limitInput.value = String(rule ? rule.monthly_limit : 0);
      const warnInput = el('input', {
        type: 'number',
        class: 'qta-pct-input',
        min: '1',
        max: '100',
        step: '1',
        placeholder: 'Tùy chọn',
        inputmode: 'numeric',
        'aria-label': `Ngưỡng cảnh báo (%) cho ${model.display_name}`,
      });
      warnInput.value = rule && rule.warning_threshold_pct !== null ? String(rule.warning_threshold_pct) : '';
      return { model, rule, enabledBox, limitInput, warnInput };
    });

    const saveBtn = el('button', { type: 'submit', class: 'button primary' }, 'Lưu cấu hình hạn mức');
    const quotaForm = el(
      'form',
      {},
      table(
        ['Mô hình AI', 'Nhà cung cấp', 'Bật áp dụng', `Hạn mức tháng (${UNIT_LABEL})`, 'Ngưỡng cảnh báo (%)'],
        rowControls.map(({ model, enabledBox, limitInput, warnInput }) => [
          el('div', {}, el('strong', {}, model.display_name), el('div', { class: 'muted' }, el('code', {}, model.technical_id))),
          el('span', {}, model.provider_name, ' ', badge(providerTypeLabels[model.provider_type] ?? model.provider_type, model.provider_type === 'EXTERNAL' ? 'amber' : 'blue')),
          enabledBox,
          limitInput,
          warnInput,
        ]),
      ),
      quotaAlert,
      actions(saveBtn),
    );

    submitForm(quotaForm, saveBtn, quotaAlert, async () => {
      const quotasPayload = rowControls.map(({ model, rule, enabledBox, limitInput, warnInput }) => {
        const monthlyLimit = parseNonNegativeInt(limitInput.value, `Hạn mức tháng của ${model.display_name}`);
        const warnRaw = warnInput.value.trim();
        let warnPct = null;
        if (warnRaw !== '') {
          warnPct = parseNonNegativeInt(warnRaw, `Ngưỡng cảnh báo của ${model.display_name}`);
          if (warnPct < 1 || warnPct > 100) {
            throw new RequestError(422, null, `Ngưỡng cảnh báo của ${model.display_name} phải từ 1 đến 100.`);
          }
        }
        const item = {
          model_id: model.id,
          enabled: Boolean(enabledBox.checked),
          monthly_limit: monthlyLimit,
          warning_threshold_pct: warnPct,
        };
        // Quota rows are never deleted, so only send a model the admin actually configured:
        // an existing rule, or a new one that is enabled or has a limit/threshold.
        const untouched = !rule && !item.enabled && monthlyLimit === 0 && warnPct === null;
        return untouched ? null : item;
      }).filter(Boolean);
      if (quotasPayload.length === 0) {
        throw new RequestError(422, null, 'Chưa có mô hình nào được cấu hình. Hãy bật hoặc nhập hạn mức cho ít nhất một mô hình.');
      }
      await qtaWrite(context, `/qta/groups/${group.id}/quotas`, {
        method: 'PUT',
        body: { quotas: quotasPayload },
      });
      await context.updated('Đã lưu cấu hình hạn mức cho nhóm.');
    });

    quotaSection.append(quotaForm);
  } else {
    // Read-only view for viewers without qta.manage (or when no usable models remain).
    const readRows = usableModels.map(model => {
      const rule = existingByModel.get(model.id);
      return [
        el('div', {}, el('strong', {}, model.display_name), el('div', { class: 'muted' }, el('code', {}, model.technical_id))),
        el('span', {}, model.provider_name, ' ', badge(providerTypeLabels[model.provider_type] ?? model.provider_type, model.provider_type === 'EXTERNAL' ? 'amber' : 'blue')),
        rule ? badge(rule.enabled ? 'Đang bật' : 'Đang tắt', rule.enabled ? 'green' : 'neutral') : badge('Chưa cấu hình', 'neutral'),
        rule ? fmtUnits(rule.monthly_limit) : '—',
        rule && rule.warning_threshold_pct !== null ? `${rule.warning_threshold_pct}%` : '—',
      ];
    });
    quotaSection.append(
      table(['Mô hình AI', 'Nhà cung cấp', 'Trạng thái', 'Hạn mức tháng', 'Ngưỡng cảnh báo (%)'], readRows),
    );
  }

  if (inactiveRules.length > 0) {
    quotaSection.append(
      el('h3', {}, 'Quy tắc của mô hình đã ngừng hoạt động (không còn tính phân bổ)'),
      table(
        ['Mô hình AI', 'Nhà cung cấp', 'Trạng thái quy tắc', 'Hạn mức đã ghi'],
        inactiveRules.map(rule => [
          el('div', {}, el('strong', {}, rule.model_display_name), ' ', badge('Mô hình ngừng hoạt động', 'neutral')),
          rule.provider_name,
          badge(rule.enabled ? 'Đã bật trước đây' : 'Đang tắt', 'neutral'),
          fmtUnits(rule.monthly_limit),
        ]),
      ),
    );
  }

  // Group members panel.
  const memberActions = [];
  if (manage && isSpecialist) {
    memberActions.push(
      button('Thêm thành viên', () => formDialog(context, {
        title: 'Thêm thành viên vào nhóm AI chuyên biệt',
        submit: 'Thêm thành viên',
        fields: [
          reference(context, {
            name: 'user_id',
            label: 'Tài khoản',
            resource: '/qta/users',
            title: user => `${user.display_name} (${user.username} · ${user.institutional_code})`,
            required: true,
          }),
        ],
        save: async values => {
          await qtaWrite(context, `/qta/groups/${group.id}/members/${values.user_id}`, { method: 'PUT' });
          return 'Đã thêm thành viên vào nhóm AI chuyên biệt.';
        },
      }), 'primary'),
    );
  }

  const memberHeaders = ['Tên đăng nhập', 'Họ và tên', 'Mã định danh', 'Trạng thái tài khoản', 'Thành viên'];
  if (manage && isSpecialist) memberHeaders.push('Thao tác');

  const membersPanel = listing(context, {
    path: `/qta/groups/${group.id}/members`,
    heading: 'Thành viên trong nhóm',
    query: { active: 'true' },
    toolbar: memberActions,
    filters: [
      field({ name: 'q', label: 'Tìm thành viên', type: 'search', max: 128 }),
      field({
        name: 'active', label: 'Trạng thái thành viên', value: 'true',
        options: [['', 'Tất cả'], ['true', 'Đang trong nhóm'], ['false', 'Đã rời nhóm']],
      }),
    ],
    headers: memberHeaders,
    row: member => {
      const user = member.user;
      const cells = [
        el('code', {}, user.username),
        user.display_name,
        el('code', {}, user.institutional_code),
        stateBadge(user.state),
        badge(member.active ? 'Đang trong nhóm' : 'Đã rời nhóm', member.active ? 'green' : 'neutral'),
      ];
      if (manage && isSpecialist) {
        cells.push(
          member.active
            ? button('Gỡ thành viên', () => formDialog(context, {
              title: 'Gỡ thành viên khỏi nhóm AI chuyên biệt',
              description: `Gỡ tài khoản ${user.display_name} (${user.username}) khỏi nhóm ${group.name}?`,
              submit: 'Xác nhận gỡ',
              danger: true,
              save: async () => {
                await qtaWrite(context, `/qta/groups/${group.id}/members/${user.id}`, { method: 'DELETE' });
                return 'Đã gỡ thành viên khỏi nhóm AI chuyên biệt.';
              },
            }), 'danger-outline')
            : '—',
        );
      }
      return cells;
    },
  });

  return el('div', { class: 'qta-section-stack' },
    link('← Quay lại danh sách nhóm hạn mức', 'qta/groups'),
    summaryPanel,
    quotaSection,
    membersPanel,
  );
}

// ---------------------------------------------------------------------------
// Tab 2: Tra cứu cá nhân & tạm ngưng (#qta/lookup)
// ---------------------------------------------------------------------------

function openSuspendDialog(context, user) {
  const operatorDisplay = `${context.me.display_name} (${context.me.username})`;
  const expiresId = `qta-exp-${Math.random().toString(36).slice(2, 9)}`;
  const expiresInput = el('input', {
    id: expiresId,
    name: 'expires_at',
    type: 'datetime-local',
    'aria-describedby': `${expiresId}-hint`,
  });

  formDialog(context, {
    title: `Cắt / tạm ngưng quyền AI — ${user.display_name}`,
    description: 'Tạm ngưng quyền truy cập AI ngay lập tức. Hạn mức nhóm và tổng phân bổ của trường không bị xóa về 0.',
    submit: 'Xác nhận tạm ngưng',
    danger: true,
    fields: [
      el(
        'div',
        { class: 'field' },
        el('label', {}, 'Người thực hiện (tự động từ phiên đăng nhập)'),
        el('div', { class: 'qta-readonly-box', 'data-testid': 'qta-suspend-operator' }, operatorDisplay),
      ),
      field({
        name: 'scope',
        label: 'Phạm vi tạm ngưng',
        required: true,
        value: 'PAID_EXTERNAL_ONLY',
        options: [
          ['PAID_EXTERNAL_ONLY', scopeLabels.PAID_EXTERNAL_ONLY],
          ['ALL_MODELS', scopeLabels.ALL_MODELS],
        ],
      }),
      field({
        name: 'reason',
        label: 'Lý do tạm ngưng',
        required: true,
        max: 500,
      }),
      field({
        name: 'ordered_by',
        label: 'Người ra lệnh',
        required: true,
        max: 255,
        hint: 'Nhập tên hoặc chức danh người yêu cầu tạm ngưng (khác với Người thực hiện thao tác).',
      }),
      el(
        'div',
        { class: 'field' },
        el('label', { for: expiresId }, 'Thời hạn tạm ngưng (tùy chọn)'),
        expiresInput,
        el('small', { id: `${expiresId}-hint`, class: 'hint' }, 'Để trống nếu tạm ngưng không thời hạn. Nếu đặt thời hạn, thời điểm phải ở tương lai.'),
      ),
    ],
    save: async values => {
      const body = {
        scope: values.scope,
        reason: values.reason.trim(),
        ordered_by: values.ordered_by.trim(),
      };
      const rawExp = String(values.expires_at ?? '').trim();
      if (rawExp) {
        const parsed = new Date(rawExp);
        if (Number.isNaN(parsed.getTime())) {
          throw new RequestError(422, null, 'Thời điểm hết hạn không hợp lệ.');
        }
        body.expires_at = parsed.toISOString();
      }
      await qtaWrite(context, `/qta/users/${user.id}/suspensions`, { method: 'POST', body });
      return `Đã tạm ngưng quyền AI của ${user.display_name}.`;
    },
  });
}

function openRestoreDialog(context, user) {
  formDialog(context, {
    title: `Khôi phục quyền AI — ${user.display_name}`,
    description: 'Khôi phục quyền truy cập AI cho tài khoản này; hạn mức nhóm và tổng phân bổ không bị thay đổi.',
    submit: 'Xác nhận khôi phục',
    fields: [
      field({
        name: 'note',
        label: 'Ghi chú khôi phục (tùy chọn)',
        max: 500,
      }),
    ],
    save: async values => {
      const note = String(values.note ?? '').trim();
      await qtaWrite(context, `/qta/users/${user.id}/restore`, {
        method: 'POST',
        body: note ? { note } : {},
      });
      return `Đã khôi phục quyền AI của ${user.display_name}.`;
    },
  });
}

function contributionBreakdown(model) {
  if (!model.contributions || model.contributions.length === 0) {
    return `Không có nhóm đóng góp (${fmtUnits(0)})`;
  }
  const activeParts = model.contributions
    .filter(c => c.contributes > 0)
    .map(c => `${fmtInt(c.contributes)} (${c.code})`);
  const formula = activeParts.length > 0
    ? `${activeParts.join(' + ')} = ${fmtUnits(model.base_entitlement)}`
    : fmtUnits(model.base_entitlement);

  return el(
    'div',
    {},
    el('div', {}, el('strong', {}, formula)),
    el(
      'ul',
      { class: 'qta-contrib-list' },
      model.contributions.map(c => el(
        'li',
        {},
        `${c.code} (${c.name}): `,
        c.enabled
          ? fmtUnits(c.contributes)
          : `${fmtUnits(0)} (quy tắc đang tắt; mức cấu hình ${fmtUnits(c.monthly_limit)})`,
      )),
    ),
  );
}

function lookupTab(context, manage) {
  const { current, next } = currentAndNextMonths();
  if (selectedLookupMonth !== current && selectedLookupMonth !== next) {
    selectedLookupMonth = current;
  }

  const monthSelect = el(
    'select',
    { id: 'qta-lookup-month', name: 'month', 'aria-label': 'Tháng tra cứu hạn mức cá nhân' },
    option(current, `Tháng hiện tại (${current})`),
    option(next, `Tháng kế tiếp (${next})`),
  );
  monthSelect.value = selectedLookupMonth;

  const detailHost = el('div', { class: 'qta-section-stack' },
    panel('Chi tiết hạn mức cá nhân', el('p', { class: 'empty' }, 'Chọn một tài khoản ở danh sách trên để xem hạn mức cộng dồn theo nhóm và trạng thái truy cập AI.')),
  );

  // Only the newest request may render: a slower earlier response (another user or month)
  // must never replace it, or the panel and its suspend/restore buttons would show the wrong user.
  let loadSequence = 0;
  async function loadUserDetail(userId) {
    const load = ++loadSequence;
    const isLatest = () => load === loadSequence && context.current();
    selectedLookupUserId = userId;
    detailHost.replaceChildren(panel('Chi tiết hạn mức cá nhân', el('p', { class: 'empty' }, 'Đang tải hạn mức cá nhân…')));
    try {
      const [ent, suspensionsPage] = await Promise.all([
        qtaRead(context, `/qta/users/${userId}/entitlements`, { month: selectedLookupMonth }),
        qtaRead(context, `/qta/users/${userId}/suspensions`, { limit: 50 }),
      ]);
      if (!isLatest()) return;

      const userActions = [];
      if (manage) {
        if (ent.quota_status === 'ACTIVE') {
          userActions.push(button('Cắt / tạm ngưng quyền AI', () => openSuspendDialog(context, ent.user), 'danger-outline'));
        } else {
          userActions.push(button('Khôi phục quyền AI', () => openRestoreDialog(context, ent.user), 'primary'));
        }
      }

      const suspensionBanner = ent.suspension && el(
        'div',
        { class: 'qta-banner-danger', role: 'status' },
        el('strong', {}, `Đang tạm ngưng quyền AI — ${scopeLabels[ent.suspension.scope] ?? ent.suspension.scope}`),
        el('div', {}, `Lý do: ${ent.suspension.reason}`),
        el('div', {}, `Người ra lệnh: ${ent.suspension.ordered_by}`),
        el('div', {}, 'Người thực hiện: ', actorLabel(context, ent.suspension.suspended_by), ` · Thời điểm: ${dateLabel(ent.suspension.suspended_at)}`),
        el('div', {}, `Thời hạn: ${ent.suspension.expires_at ? dateLabel(ent.suspension.expires_at) : 'Không thời hạn'}`),
      );

      const overviewPanel = panel(
        `Hạn mức cá nhân — ${ent.user.display_name} (${ent.user.username})`,
        userActions.length ? actions(...userActions) : undefined,
        suspensionBanner,
        facts([
          ['Tài khoản', el('code', {}, ent.user.username)],
          ['Trạng thái tài khoản', stateBadge(ent.user.state)],
          ['Tháng tra cứu', el('code', {}, ent.month)],
          ['Trạng thái hạn mức AI', quotaStatusBadge(ent.quota_status)],
          ['Tổng hạn mức cơ sở tháng', fmtUnits(ent.base_entitlement_total)],
          ['Tiêu thụ thực tế', CONSUMPTION_NOTICE],
        ]),
      );

      const membershipsPanel = panel(
        'Nhóm tài khoản của cá nhân',
        ent.memberships.length === 0
          ? el('p', { class: 'empty' }, `Tài khoản chưa thuộc nhóm hạn mức AI nào (hạn mức cơ sở: ${fmtUnits(0)}).`)
          : table(
            ['Mã nhóm', 'Tên nhóm', 'Loại', 'Trạng thái nhóm', 'Áp dụng tính hạn mức'],
            ent.memberships.map(m => [
              el('code', {}, m.code),
              m.name,
              groupKindLabels[m.kind] ?? m.kind,
              activeBadge(m.active),
              m.qualifies
                ? badge('Đủ điều kiện cộng dồn', 'green')
                : badge(exclusionLabels[m.excluded_reason] ?? m.excluded_reason ?? 'Không áp dụng', 'amber'),
            ]),
          ),
      );

      const modelsPanel = panel(
        `Hạn mức cơ sở theo mô hình AI (tháng ${ent.month})`,
        el('p', { class: 'muted' }, `Cộng dồn từ mọi nhóm đủ điều kiện. ${CONSUMPTION_NOTICE}.`),
        table(
          ['Mô hình AI', 'Hạn mức cơ sở tháng', 'Chi tiết cộng dồn theo nhóm', 'Trạng thái truy cập', 'Tiêu thụ thực tế'],
          ent.models.map(m => [
            el('div', {},
              el('strong', {}, m.display_name),
              ' ',
              badge(providerTypeLabels[m.provider_type] ?? m.provider_type, m.provider_type === 'EXTERNAL' ? 'amber' : 'blue'),
              el('div', { class: 'muted' }, el('code', {}, m.technical_id)),
            ),
            el('strong', {}, fmtUnits(m.base_entitlement)),
            contributionBreakdown(m),
            m.access.allowed
              ? badge('Được phép', 'green')
              : badge(accessReasonLabels[m.access.reason] ?? m.access.reason ?? 'Bị chặn', 'red'),
            CONSUMPTION_NOTICE,
          ]),
        ),
      );

      const suspensionsPanel = panel(
        'Lịch sử tạm ngưng & khôi phục quyền AI',
        suspensionsPage.items.length === 0
          ? el('p', { class: 'empty' }, 'Tài khoản này chưa có lịch sử tạm ngưng quyền AI.')
          : table(
            ['Trạng thái', 'Phạm vi', 'Lý do', 'Người ra lệnh', 'Người thực hiện', 'Thời điểm cắt', 'Hết hạn', 'Khôi phục'],
            suspensionsPage.items.map(s => [
              suspensionStatusBadge(s.status),
              scopeLabels[s.scope] ?? s.scope,
              s.reason,
              s.ordered_by,
              actorLabel(context, s.suspended_by),
              dateLabel(s.suspended_at),
              s.expires_at ? dateLabel(s.expires_at) : 'Không thời hạn',
              s.restoration
                ? el('div', {},
                  actorLabel(context, s.restoration.restored_by),
                  el('div', { class: 'muted' }, dateLabel(s.restoration.restored_at)),
                  s.restoration.note && el('div', {}, `Ghi chú: ${s.restoration.note}`),
                )
                : '—',
            ]),
          ),
      );

      detailHost.replaceChildren(overviewPanel, membershipsPanel, modelsPanel, suspensionsPanel);
    } catch (error) {
      if (error.name === 'AbortError' || !isLatest()) return;
      if (error.status === 404) {
        selectedLookupUserId = undefined;
      }
      const alertBox = el('div', { class: 'alert', role: 'alert' });
      showError(alertBox, error);
      detailHost.replaceChildren(panel('Chi tiết hạn mức cá nhân', alertBox));
    }
  }

  monthSelect.addEventListener('change', () => {
    selectedLookupMonth = monthSelect.value;
    if (selectedLookupUserId) loadUserDetail(selectedLookupUserId);
  });

  const controlsPanel = panel(
    'Chọn tháng tra cứu cá nhân',
    el('div', { class: 'qta-inline-controls' },
      el('div', { class: 'field' }, el('label', { for: 'qta-lookup-month' }, 'Tháng áp dụng'), monthSelect),
    ),
    el('p', { class: 'muted' }, 'Chỉ hỗ trợ tra cứu hạn mức theo tháng hiện tại hoặc tháng kế tiếp.'),
  );

  const userPicker = listing(context, {
    path: '/qta/users',
    heading: 'Danh sách tài khoản trong phạm vi tra cứu',
    filters: [field({ name: 'q', label: 'Tìm tài khoản (tên, username, mã)', type: 'search', max: 128 })],
    headers: ['Tên đăng nhập', 'Họ và tên', 'Mã định danh', 'Trạng thái tài khoản', 'Trạng thái hạn mức AI', 'Thao tác'],
    row: user => [
      el('code', {}, user.username),
      user.display_name,
      el('code', {}, user.institutional_code),
      stateBadge(user.state),
      quotaStatusBadge(user.quota_status),
      button('Xem hạn mức', () => loadUserDetail(user.id), 'secondary'),
    ],
  });

  if (selectedLookupUserId) {
    loadUserDetail(selectedLookupUserId);
  }

  return el('div', { class: 'qta-section-stack' }, controlsPanel, userPicker, detailHost);
}

// ---------------------------------------------------------------------------
// Tab 3: Lịch sử & Làm mới tháng (#qta/ledger — GLOBAL qta.read only)
// ---------------------------------------------------------------------------

async function ledgerTab(context, manage) {
  const { current } = currentAndNextMonths();
  if (!selectedLedgerMonth) selectedLedgerMonth = current;

  const resets = await qtaRead(context, '/qta/monthly-resets', { limit: 50 });
  if (!context.current()) return;

  const isCompleted = resets.current.status === 'COMPLETED';
  const resetActions = [];
  if (manage) {
    const simButton = button(
      'Mô phỏng làm mới tháng hiện tại',
      () => formDialog(context, {
        title: `Mô phỏng làm mới hạn mức tháng ${resets.current.month}`,
        description: 'Ghi nhận mốc làm mới đầu tháng cho tháng hiện tại. Không cộng dồn dư tháng trước; mỗi tháng chỉ thực hiện một lần.',
        submit: 'Xác nhận làm mới tháng',
        save: async () => {
          await qtaWrite(context, '/qta/monthly-resets', { method: 'POST' });
          return `Đã ghi nhận làm mới hạn mức tháng ${resets.current.month}.`;
        },
      }),
      'primary',
    );
    if (isCompleted) {
      simButton.disabled = true;
      simButton.title = 'Tháng hiện tại đã được làm mới.';
    }
    resetActions.push(simButton);
  }

  const resetPanel = panel(
    'Làm mới hạn mức đầu tháng',
    resetActions.length ? actions(...resetActions) : undefined,
    facts([
      ['Tháng hiện tại', el('code', {}, resets.current.month)],
      ['Trạng thái làm mới', badge(isCompleted ? 'Đã làm mới' : 'Chưa làm mới', isCompleted ? 'green' : 'amber')],
      ['Hình thức', resets.current.reset ? (triggerModeLabels[resets.current.reset.trigger_mode] ?? resets.current.reset.trigger_mode) : '—'],
      ['Thời điểm thực hiện', resets.current.reset ? dateLabel(resets.current.reset.executed_at) : '—'],
      ['Nguyên tắc chuyển kỳ', 'Làm mới về hạn mức tháng đã cấu hình, không cộng dồn phần dư tháng trước.'],
    ]),
    el('h3', {}, 'Lịch sử các lần làm mới đầu tháng'),
    resets.items.length === 0
      ? el('p', { class: 'empty' }, 'Chưa có bản ghi làm mới đầu tháng nào.')
      : table(
        ['Tháng', 'Hình thức', 'Người thực hiện', 'Thời điểm thực hiện'],
        resets.items.map(item => [
          el('code', {}, item.month),
          triggerModeLabels[item.trigger_mode] ?? item.trigger_mode,
          actorLabel(context, item.triggered_by, 'Tự động (lịch hệ thống)'),
          dateLabel(item.executed_at),
        ]),
      ),
  );

  const monthFilter = el('input', {
    id: 'qta-events-month',
    name: 'month',
    type: 'month',
    'aria-label': 'Tháng lọc nhật ký sự kiện QTA',
  });
  monthFilter.value = selectedLedgerMonth;
  monthFilter.addEventListener('change', () => {
    if (monthFilter.value) selectedLedgerMonth = monthFilter.value;
  });

  const eventsListing = listing(context, {
    path: '/qta/events',
    heading: 'Nhật ký sự kiện hạn mức AI (chỉ ghi thêm)',
    query: { month: selectedLedgerMonth },
    filters: [
      el('div', { class: 'field' }, el('label', { for: 'qta-events-month' }, 'Tháng'), monthFilter),
      field({
        name: 'event_type',
        label: 'Loại sự kiện',
        options: [
          ['', 'Tất cả'],
          ['MONTHLY_REFRESH', eventTypeLabels.MONTHLY_REFRESH],
          ['SUSPEND', eventTypeLabels.SUSPEND],
          ['RESTORE', eventTypeLabels.RESTORE],
        ],
      }),
    ],
    headers: ['Thời điểm', 'Tháng', 'Loại sự kiện', 'Tài khoản liên quan', 'Người thực hiện', 'Tóm tắt'],
    row: event => [
      dateLabel(event.occurred_at),
      el('code', {}, event.month),
      badge(
        eventTypeLabels[event.event_type] ?? event.event_type,
        event.event_type === 'SUSPEND' ? 'red' : event.event_type === 'RESTORE' ? 'green' : 'blue',
      ),
      event.user_id ? el('code', {}, event.user_id) : 'Toàn trường',
      actorLabel(context, event.actor_id, 'Tự động (lịch hệ thống)'),
      event.summary,
    ],
  });

  return el('div', { class: 'qta-section-stack' }, resetPanel, eventsListing);
}

// ---------------------------------------------------------------------------
// Main #qta page entry point
// ---------------------------------------------------------------------------

export async function qtaPage(context, tab = 'groups', id) {
  syncSessionState(context);
  const globalRead = permission(context.caps, 'qta.read');
  const manage = permission(context.caps, 'qta.manage');

  if (!globalRead) {
    // R14: UNIT-scoped qta.read viewer sees ONLY the personal lookup tab (zero GLOBAL calls).
    const unitNav = el(
      'nav',
      { class: 'tabs', 'aria-label': 'Mục hạn mức AI' },
      el('a', { href: '#qta/lookup', 'aria-current': 'page' }, tabs.lookup),
    );
    return [unitNav, lookupTab(context, false)];
  }

  const activeTab = Object.hasOwn(tabs, tab) ? tab : 'groups';
  const nav = el(
    'nav',
    { class: 'tabs', 'aria-label': 'Mục hạn mức AI' },
    Object.entries(tabs).map(([key, title]) => el(
      'a',
      { href: key === 'groups' ? '#qta' : `#qta/${key}`, 'aria-current': key === activeTab ? 'page' : undefined },
      title,
    )),
  );

  const budgetHeader = budgetHeaderPanel(context, manage);
  let body;
  if (activeTab === 'groups') {
    body = id ? await groupDetailView(context, id, manage) : groupsTab(context, manage);
  } else if (activeTab === 'lookup') {
    body = lookupTab(context, manage);
  } else {
    body = await ledgerTab(context, manage);
  }
  if (!context.current()) return;
  return [budgetHeader, nav, body];
}
