const messages = {
  401: 'Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.',
  403: 'Bạn không có quyền thực hiện thao tác này hoặc yêu cầu không được xác thực.',
  404: 'Không tìm thấy bản ghi hoặc bản ghi nằm ngoài phạm vi truy cập.',
  409: 'Thay đổi xung đột với dữ liệu hiện tại. Hãy kiểm tra lại bản ghi và thử lại khi phù hợp.',
  422: 'Dữ liệu không hợp lệ. Hãy kiểm tra các trường đã nhập.',
  429: 'Quá nhiều lần thử đăng nhập. Vui lòng đợi rồi thử lại.',
  500: 'Đã xảy ra lỗi khi xử lý yêu cầu.',
  503: 'Dịch vụ tạm thời chưa sẵn sàng.',
};

export class RequestError extends Error {
  constructor(status, requestId, message, code, details) {
    super(message ?? messages[status] ?? 'Không thể xử lý yêu cầu.');
    this.status = status;
    this.requestId = requestId;
    this.code = code;
    this.details = details;
  }
}

// Only the API's allowlisted detail keys: short lists of fixed lowercase identifiers
// (used_in, reasons) or non-negative safe integers (allocated, deficit for QTA budgets).
// Anything else is ignored, never rendered.
function safeDetails(details) {
  const result = {};
  for (const key of ['used_in', 'reasons']) {
    const value = details?.[key];
    if (Array.isArray(value) && value.length <= 48 && value.every(item => typeof item === 'string' && /^[a-z][a-z0-9_.-]{0,63}$/.test(item))) {
      result[key] = value;
    }
  }
  for (const key of ['allocated', 'deficit']) {
    const value = details?.[key];
    if (typeof value === 'number' && Number.isSafeInteger(value) && value >= 0) {
      result[key] = value;
    }
  }
  return Object.keys(result).length ? result : undefined;
}

export function createClient(onExpired) {
  let csrf;
  let sessionVersion = 0;
  return {
    setProof(token) {
      if (csrf !== token) {
        csrf = token;
        sessionVersion += 1;
      }
    },
    async request(path, { method = 'GET', query, body, signal } = {}) {
      const url = new URL(`/api/v1${path}`, location.origin);
      for (const [key, value] of Object.entries(query ?? {})) {
        if (value !== '' && value !== undefined && value !== null) url.searchParams.set(key, value);
      }
      const headers = { Accept: 'application/json' };
      const login = path === '/auth/login';
      const passwordChange = path === '/auth/change-password';
      const write = method !== 'GET';
      const version = sessionVersion;
      if (write && !login && csrf) headers['X-CSRF-Token'] = csrf;
      if (body !== undefined) headers['Content-Type'] = 'application/json';
      let response;
      try {
        response = await fetch(url, {
          method, headers, signal, credentials: 'same-origin', redirect: 'error',
          body: body === undefined ? undefined : JSON.stringify(body),
        });
      } catch (error) {
        if (error.name === 'AbortError') throw error;
        const message = write && !login
          ? 'Mất kết nối. Hãy tải lại dữ liệu để kiểm tra kết quả trước khi gửi lại.'
          : 'Không kết nối được với dịch vụ. Vui lòng kiểm tra kết nối.';
        throw new RequestError(0, null, message);
      }
      const requestId = response.headers.get('X-Request-ID');
      if (!response.ok) {
        if (response.status === 401 && !login && !passwordChange && csrf && version === sessionVersion) onExpired();
        const message = login && response.status === 401 ? 'Tên đăng nhập hoặc mật khẩu không đúng.' : undefined;
        const envelope = await response.json().catch(() => null);
        const echoedId = typeof envelope?.request_id === 'string' &&
          /^[a-f0-9-]{36}$/i.test(envelope.request_id) ? envelope.request_id : null;
        const code = typeof envelope?.code === 'string' && /^[A-Z_]{1,64}$/.test(envelope.code)
          ? envelope.code : undefined;
        throw new RequestError(response.status, requestId ?? echoedId, message, code, safeDetails(envelope?.details));
      }
      if (response.status === 204) return undefined;
      try {
        return await response.json();
      } catch (error) {
        if (error.name === 'AbortError') throw error;
        throw new RequestError(response.status, requestId, 'Phản hồi từ dịch vụ không hợp lệ.');
      }
    },
  };
}

export function permission(capabilities, code, unitId) {
  const scope = capabilities?.permissions[code];
  return Boolean(scope && (scope.institution_wide || (unitId && scope.unit_ids.includes(unitId))));
}

export function hasScope(capabilities, code) {
  return permission(capabilities, code) || Boolean(capabilities?.permissions[code]?.unit_ids.length);
}
