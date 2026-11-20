# AQ-FRD-UAI-QTA-001 — Hạn mức AI theo Nhóm tài khoản

| Mục | Nội dung |
| :--- | :--- |
| Mã tài liệu | `AQ-FRD-UAI-QTA-001` |
| Sản phẩm | AQ EduUAI |
| Menu | Quản trị AI & Dữ liệu → Quản lý AI & Chi phí → **Hạn mức AI theo Nhóm tài khoản** |
| Phiên bản | 1.0 |
| Ngày | 17/11/2026 |
| Trạng thái | Dự thảo — bàn giao kèm biên bản giao việc TTS |
| Nguồn nghiệp vụ | BRD UAI v1.1 · **BR-26.01** · INV-17, INV-18 |
| Actor chính | Người phụ trách quản trị AI |
| Actor phụ | Ban Giám hiệu (xem tổng hạn mức); trưởng đơn vị (xem phạm vi đơn vị — Should) |
| Ưu tiên tổng | Must (giai đoạn prototype khung) |

> FRD = cam kết chức năng. Prototype: framework nền liên hệ Tech lead. Không ghi path kho code.

---

## 1. Thông tin chung & mục đích

### 1.1. Mục đích chức năng

Hệ thống SHALL cho phép đặt **tổng hạn mức nhà trường**, cấu hình **hạn mức theo nhóm tài khoản × từng mô hình**, đồng bộ nhóm từ quản lý nhóm tài khoản, tạo nhóm AI chuyên biệt, **cộng dồn** hạn mức khi một người thuộc nhiều nhóm, tra cứu hạn mức thực hưởng cá nhân, và **cắt / ngưng / khôi phục** hạn mức cá nhân đột xuất. Chu kỳ hạn mức **duy nhất là tháng**.

### 1.2. Trong phạm vi

- Ghi nhận tổng hạn mức tháng (kèm căn cứ quyết định).
- Đồng bộ nhóm & thành viên từ chức năng quản lý nhóm tài khoản.
- Cấu hình hạn mức / tháng theo từng mô hình cho từng nhóm.
- Nhóm AI chuyên biệt + quản lý thành viên.
- Tra cứu cộng dồn cá nhân theo mô hình.
- Cắt / ngưng và khôi phục hạn mức cá nhân (kill-switch).
- Ngoại lệ hạn mức có ngày hết hạn (Should nếu thời gian cho phép; Must nếu đã có trên prototype nghiệm thu).
- Đơn giá quy đổi theo mô hình (Should — có thể stub trên prototype nếu chưa trừ thật).

### 1.3. Ngoài phạm vi

- Cấp bổ sung / thu hồi hạn mức có căn cứ tờ trình (FRD CRT).
- Gọi mô hình thật / thanh toán nhà cung cấp.
- Sửa / xóa giao dịch hạn mức đã ghi (cấm theo INV-18).
- Chu kỳ Học kỳ / Đề tài / Đợt thi cho hạn mức AI.

---

## 2. Mô tả tổng quan

Người phụ trách quản trị AI SHALL:

1. Mở **Hạn mức AI theo Nhóm tài khoản**.
2. Ghi tổng hạn mức tháng của nhà trường.
3. Đồng bộ nhóm từ hệ thống phân quyền; cấu hình hạn mức theo mô hình.
4. (Tuỳ chọn) Tạo nhóm AI chuyên biệt và gán thành viên.
5. Tra cứu một người để xem phép tính cộng dồn.
6. Khi cần: cắt / ngưng hạn mức một người; sau đó khôi phục.

---

## 3. Yêu cầu chức năng chi tiết (FR)

### 3.1. Truy cập & tổng hạn mức

#### FR-QTA-001 — Truy cập theo quyền
- **BR:** BR-26.01 · **Ưu tiên:** Must
- **Mô tả:** Hệ thống SHALL chỉ cho tài khoản có quyền xem/sửa hạn mức mở chức năng này đúng phạm vi quyền.
- **Tiêu chí chấp nhận:**
  - [ ] Không đủ quyền → không sửa được hạn mức nhóm.
  - [ ] Đủ quyền → mở được danh sách nhóm (kể cả trống sau khi chưa đồng bộ).

#### FR-QTA-010 — Tổng hạn mức nhà trường theo tháng
- **BR:** BR-26.01 · INV-18 · **Ưu tiên:** Must
- **Mô tả:** Hệ thống SHALL cho ghi nhận tổng hạn mức của **tháng** hiện hành (hoặc tháng kế tiếp) kèm số / ngày quyết định căn cứ. Chu kỳ SHALL cố định **Tháng**; hệ thống SHALL NOT cho chọn Học kỳ, Đề tài hay Đợt thi làm chu kỳ hạn mức.
- **Tiêu chí chấp nhận:**
  - [ ] Lưu được tổng hạn mức kèm số quyết định.
  - [ ] Thiếu số quyết định → không lưu.
  - [ ] Không có lựa chọn chu kỳ ngoài Tháng trên UI nghiệm thu.

#### FR-QTA-011 — Không giảm tổng dưới phần đã phân bổ
- **BR:** BR-26.01 · **Ưu tiên:** Must
- **Mô tả:** Hệ thống SHALL từ chối giảm tổng hạn mức xuống dưới tổng đã phân bổ / đã cấp trong tháng và SHALL nêu số cần thu hồi trước.
- **Tiêu chí chấp nhận:**
  - [ ] Tổng mới < đã phân bổ → từ chối kèm số chênh lệch.

### 3.2. Hạn mức theo nhóm × mô hình

#### FR-QTA-020 — Đồng bộ nhóm & người dùng từ hệ thống
- **BR:** BR-26.01 · **Ưu tiên:** Must
- **Mô tả:** Hệ thống SHALL cung cấp thao tác đồng bộ nhóm tài khoản và thành viên từ chức năng quản lý nhóm tài khoản, để không phải nhập lại toàn bộ cơ cấu.
- **Tiêu chí chấp nhận:**
  - [ ] Sau đồng bộ, danh sách nhóm hệ thống xuất hiện trên màn hình hạn mức.
  - [ ] Đồng bộ không xóa mất nhóm AI chuyên biệt đã tạo (nếu có).

#### FR-QTA-021 — Cấu hình hạn mức theo từng mô hình của nhóm
- **BR:** BR-26.01 · **Ưu tiên:** Must
- **Mô tả:** Với mỗi nhóm, hệ thống SHALL cho bật/tắt quyền dùng và đặt hạn mức **theo tháng** cho **từng mô hình** đang được phép cấu hình. Một dòng cấu hình = một cặp (nhóm × mô hình).
- **Tiêu chí chấp nhận:**
  - [ ] Cùng một nhóm đặt được hai mức khác nhau cho hai mô hình.
  - [ ] Tắt quyền mô hình → người chỉ thuộc nhóm đó không còn hạn mức cơ sở cho mô hình đó (sau làm mới / áp dụng).

#### FR-QTA-022 — Nhóm AI chuyên biệt
- **BR:** BR-26.01 · **Ưu tiên:** Must
- **Mô tả:** Hệ thống SHALL cho tạo nhóm AI ngoài danh mục hệ thống, gán thành viên, và đặt hạn mức theo mô hình như nhóm hệ thống.
- **Tiêu chí chấp nhận:**
  - [ ] Tạo nhóm chuyên biệt + thêm ít nhất một thành viên thành công.
  - [ ] Thành viên đó xuất hiện trong tra cứu cộng dồn với hạn mức nhóm này.

### 3.3. Cộng dồn & làm mới

#### FR-QTA-030 — Quy tắc cộng dồn đa nhóm
- **BR:** BR-26.01 · INV-18 · **Ưu tiên:** Must
- **Mô tả:** Khi một người thuộc nhiều nhóm có hạn mức cùng một mô hình, hạn mức cơ sở của người đó với mô hình đó SHALL bằng **tổng** các hạn mức nhóm (cộng dồn), **không** lấy giá trị lớn nhất.
- **Tiêu chí chấp nhận:**
  - [ ] Thuộc nhóm 1 000 + nhóm 3 000 cùng mô hình → cơ sở = **4 000**.
  - [ ] Tra cứu cá nhân hiện đúng danh sách nhóm và phép cộng.

#### FR-QTA-031 — Tra cứu hạn mức thực hưởng cá nhân
- **BR:** BR-26.01 · **Ưu tiên:** Must
- **Mô tả:** Hệ thống SHALL cho chọn / tìm một người và hiển thị các nhóm đang thuộc cùng bảng hạn mức theo mô hình (cộng dồn + trạng thái cắt/ngưng nếu có).
- **Tiêu chí chấp nhận:**
  - [ ] Chọn được một người cụ thể và thấy bảng cộng dồn.
  - [ ] Người không thuộc nhóm nào → hạn mức cơ sở 0 hoặc trạng thái bị chặn theo chính sách.

#### FR-QTA-032 — Làm mới đầu tháng
- **BR:** BR-26.01 · INV-17 · **Ưu tiên:** Must
- **Mô tả:** Hệ thống SHALL làm mới hạn mức cơ sở vào **00:00 ngày 01** hằng tháng (hoặc cung cấp thao tác giả lập tương đương trên prototype). Số dư tháng trước và cấp bổ sung tháng trước SHALL NOT cộng dồn sang tháng mới. Giao dịch làm mới SHALL chỉ ghi thêm.
- **Tiêu chí chấp nhận:**
  - [ ] Giả lập / chạy làm mới → có giao dịch “Làm mới”.
  - [ ] Dư tháng trước không làm tăng hạn mức tháng mới.

### 3.4. Cắt / ngưng đột xuất

#### FR-QTA-040 — Cắt / ngưng hạn mức cá nhân
- **BR:** BR-26.01 · INV-17 · **Ưu tiên:** Must
- **Mô tả:** Hệ thống SHALL cho cắt / ngưng ngay hạn mức AI của **một người** với: phạm vi cắt (toàn bộ mô hình / chỉ mô hình bên ngoài mất phí), lý do, thời hạn, người ra lệnh. Tài khoản đang bị cắt SHALL bị chặn dùng AI theo phạm vi đã chọn. Hệ thống SHALL NOT xóa số dư bằng thao tác “đặt về 0” thay cho cắt.
- **Tiêu chí chấp nhận:**
  - [ ] Sau cắt → trạng thái / huy hiệu ĐÃ CẮT (hoặc tương đương); không gọi AI được trong phạm vi cắt.
  - [ ] Có giao dịch / nhật ký Cắt chỉ ghi thêm.
  - [ ] Thiếu lý do hoặc người ra lệnh → không cắt được.

#### FR-QTA-041 — Khôi phục hạn mức
- **BR:** BR-26.01 · **Ưu tiên:** Must
- **Mô tả:** Hệ thống SHALL cho khôi phục / mở lại hạn mức đã cắt. Khôi phục SHALL trả trạng thái hoạt động; SHALL NOT tự cộng thêm hạn mức mới ngoài số dư còn lại trong tháng.
- **Tiêu chí chấp nhận:**
  - [ ] Khôi phục → trạng thái hoạt động lại.
  - [ ] Có giao dịch / nhật ký Khôi phục.

### 3.5. Việc chức năng không được làm

#### FR-QTA-050 — Không chu kỳ ngoài tháng; không sửa giao dịch cũ
- **BR:** BR-26.01 · INV-17, INV-18 · **Ưu tiên:** Must
- **Mô tả:** Hệ thống SHALL NOT cho đặt chu kỳ hạn mức ngoài tháng. Hệ thống SHALL NOT cho sửa hoặc xóa giao dịch hạn mức đã ghi; sai sót xử lý bằng giao dịch điều chỉnh mới (nếu có ở menu liên quan).
- **Tiêu chí chấp nhận:**
  - [ ] Không còn UI chọn Học kỳ/Đề tài/Đợt thi cho hạn mức.
  - [ ] Không có nút Sửa/Xóa trên dòng giao dịch đã ghi (trên phạm vi menu này).

---

## 4. Thuộc tính tối thiểu (mức FR)

| Thuộc tính | Bắt buộc | Ghi chú |
| --- | --- | --- |
| Tổng hạn mức tháng | Có | > 0; kèm số quyết định |
| Nhóm tài khoản | Có | Hệ thống hoặc AI chuyên biệt |
| Mô hình áp dụng | Có | Một dòng = một mô hình |
| Hạn mức / tháng | Có | ≥ 0 |
| Ngưỡng cảnh báo | Không | % hoặc ngưỡng tuyệt đối |
| Trạng thái hạn mức cá nhân | Hệ thống | ACTIVE / SUSPENDED |
| Phạm vi cắt | Có khi cắt | Toàn bộ / chỉ mô hình ngoài mất phí |
| Lý do cắt | Có khi cắt | Không trống |

---

## 5. RULE tổng hợp

| Mã | Quy tắc |
| --- | --- |
| RULE-QTA-01 | Chu kỳ hạn mức chỉ Tháng |
| RULE-QTA-02 | Cộng dồn = tổng các nhóm (không max) |
| RULE-QTA-03 | SUSPENDED chặn gọi AI theo phạm vi cắt |
| RULE-QTA-04 | Giao dịch chỉ ghi thêm |
| RULE-QTA-05 | Đồng bộ không xóa nhóm AI chuyên biệt |

---

## 6. MoSCoW & điểm mở

| Hạng mục | MoSCoW |
| --- | --- |
| Tổng hạn mức, nhóm × mô hình, cộng dồn, tra cứu, cắt/ngưng, làm mới tháng | Must |
| Ngoại lệ hạn mức có ngày hết hạn | Should |
| Đơn giá quy đổi đầy đủ + trừ thật theo đơn giá | Should / sau khi có gọi mô hình |
| Phân bổ nhà trường → đơn vị chi tiết hai sổ | Could (đã có ở BRD; prototype có thể đơn giản hóa nếu ghi rõ trong báo cáo TTS) |

**Open points:** Độ chi tiết sổ đơn vị vs sổ cá nhân trên prototype — TTS ghi trong báo cáo; FRD Must tập trung nhóm × mô hình + cộng dồn + cắt/ngưng + chu kỳ tháng.
