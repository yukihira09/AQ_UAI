# AQ-FRD-UAI-MDL-001 — Cấu hình Nhà cung cấp & Mô hình AI

| Mục | Nội dung |
| :--- | :--- |
| Mã tài liệu | `AQ-FRD-UAI-MDL-001` |
| Sản phẩm | AQ EduUAI |
| Menu | Quản trị AI & Dữ liệu → Quản lý AI & Chi phí → **Cấu hình Nhà cung cấp & Mô hình AI** |
| Phiên bản | 1.0 |
| Ngày | 17/11/2026 |
| Trạng thái | Dự thảo — bàn giao kèm biên bản giao việc TTS |
| Nguồn nghiệp vụ | BRD UAI v1.1 · **BR-25.01** · INV-11, INV-21, INV-22 |
| Actor chính | Người phụ trách quản trị AI |
| Actor phụ | Ban Giám hiệu (xem / quyết định ngoài hệ thống, ghi số văn bản trên hệ thống) |
| Ưu tiên tổng | Must (giai đoạn prototype khung) |

> FRD = cam kết chức năng có ID (SHALL + AC). **Không** thay FSD (luồng UI từng bước). Prototype: liên hệ Tech lead nhận framework nền.

---

## 1. Thông tin chung & mục đích

### 1.1. Mục đích chức năng

Hệ thống SHALL cho phép khai báo nhà cung cấp mô hình (bên ngoài hoặc hạ tầng nội bộ), khai báo mô hình, thử kết nối, chọn mô hình chính / dự phòng, ghi nhận thỏa thuận bảo vệ dữ liệu và phân loại rủi ro mô hình — làm nền để các trợ lý / phân hệ khác gọi AI có kiểm soát.

### 1.2. Trong phạm vi

- Thêm / sửa / ngừng dùng nhà cung cấp và mô hình.
- Thử kết nối (không trừ hạn mức).
- Cấu hình mô hình chính và mô hình dự phòng.
- Ghi nhận thỏa thuận không dùng dữ liệu nhà trường để huấn luyện (nhà cung cấp bên ngoài).
- Ghi nhận phân loại rủi ro mô hình (Cao / Trung bình / Thấp).
- Nhật ký nghiệp vụ tối thiểu (ai làm gì, khi nào) — không chứa bí mật kết nối.

### 1.3. Ngoài phạm vi

- Lời nhắc hệ thống, độ sáng tạo, mẫu đầu ra của **từng trợ lý** (thuộc cấu hình trợ lý / menu khác).
- Hạn mức, cấp / thu hồi credit (FRD QTA / CRT).
- Kho tri thức, che thông tin, nhật ký nội dung phiên.
- Thanh toán với nhà cung cấp; huấn luyện mô hình nền.
- API payload / schema DB / wireframe pixel (FSD/TDD).

---

## 2. Mô tả tổng quan

Người phụ trách quản trị AI SHALL:

1. Vào menu **Cấu hình Nhà cung cấp & Mô hình AI**.
2. Khai báo nhà cung cấp và mô hình thuộc nhà cung cấp đó.
3. Thử kết nối trước khi đưa mô hình vào dùng làm chính / dự phòng.
4. Ghi thỏa thuận bảo vệ dữ liệu và phân loại rủi ro.
5. Xem được danh sách / trạng thái mô hình; ngừng dùng khi không còn gắn vai trò bắt buộc.

---

## 3. Yêu cầu chức năng chi tiết (FR)

### 3.1. Truy cập

#### FR-MDL-001 — Chỉ người có quyền quản trị AI mới vào được
- **BR:** BR-25.01 · **Ưu tiên:** Must
- **Mô tả:** Hệ thống SHALL chỉ cho tài khoản có quyền Sửa (hoặc tương đương) trên chức năng cấu hình mô hình mở và thay đổi dữ liệu màn hình này. Người không đủ quyền SHALL NOT thấy thao tác ghi hoặc SHALL bị từ chối kèm thông báo phù hợp.
- **Tiêu chí chấp nhận:**
  - [ ] Chưa đăng nhập / không đủ quyền → không sửa được nhà cung cấp hoặc mô hình.
  - [ ] Tài khoản đủ quyền mở được màn hình và thấy danh sách hiện có (kể cả danh sách trống).

### 3.2. Nhà cung cấp & mô hình

#### FR-MDL-010 — Khai báo nhà cung cấp
- **BR:** BR-25.01 · **Ưu tiên:** Must
- **Mô tả:** Hệ thống SHALL cho phép thêm và sửa nhà cung cấp với tối thiểu: Tên, Loại (**Bên ngoài** / **Nội bộ**), thông tin kết nối. Bí mật kết nối SHALL được lưu an toàn; khi mở lại form, hệ thống SHALL NOT hiển thị lại giá trị bí mật đã lưu; để trống khi sửa nghĩa là giữ giá trị cũ.
- **Tiêu chí chấp nhận:**
  - [ ] Thêm được nhà cung cấp Bên ngoài và Nội bộ.
  - [ ] Mở lại form sửa: ô bí mật trống; lưu mà không nhập lại vẫn giữ kết nối cũ (kiểm bằng thử kết nối sau đó).

#### FR-MDL-011 — Khai báo mô hình thuộc nhà cung cấp
- **BR:** BR-25.01 · **Ưu tiên:** Must
- **Mô tả:** Hệ thống SHALL cho phép thêm mô hình gắn một nhà cung cấp với tối thiểu: mã hoặc định danh kỹ thuật, tên hiển thị, khả năng (văn bản / hình ảnh / giọng nói — theo sản phẩm), độ dài tối đa kết quả (nếu áp dụng). Hệ thống SHALL NOT đặt trường lời nhắc hệ thống trên màn hình này.
- **Tiêu chí chấp nhận:**
  - [ ] Thêm mô hình dưới nhà cung cấp đã có → xuất hiện trên danh sách.
  - [ ] Không có ô nhập lời nhắc hệ thống / system prompt trên chức năng này.

#### FR-MDL-012 — Ngừng dùng mô hình đang được gắn vai trò
- **BR:** BR-25.01 · INV-21 · **Ưu tiên:** Must
- **Mô tả:** Hệ thống SHALL từ chối ngừng dùng mô hình đang là mô hình chính, mô hình dự phòng, hoặc đang được cấu hình bắt buộc khác nêu rõ trên màn hình, và SHALL nêu nơi đang dùng. Mô hình đã có lịch sử sử dụng SHALL NOT bị xóa cứng chỉ vì ngừng dùng.
- **Tiêu chí chấp nhận:**
  - [ ] Ngừng dùng mô hình đang là chính → bị từ chối, có thông báo.
  - [ ] Sau khi đổi chính sang mô hình khác, mới ngừng dùng được mô hình cũ (nếu không còn gắn chỗ khác).

### 3.3. Thử kết nối & cấu hình chung

#### FR-MDL-020 — Thử kết nối mô hình
- **BR:** BR-25.01 · **Ưu tiên:** Must
- **Mô tả:** Hệ thống SHALL cho phép thử kết nối mô hình đã khai báo đủ điều kiện. Lượt thử SHALL dùng yêu cầu cố định không chứa dữ liệu nhà trường; SHALL NOT trừ hạn mức; SHALL ghi kết quả thử gần nhất (thành công / lỗi).
- **Tiêu chí chấp nhận:**
  - [ ] Thử thành công → trạng thái cho phép chọn làm chính / dự phòng.
  - [ ] Thử lỗi → không chọn được làm chính / dự phòng.
  - [ ] Số dư hạn mức của người thử không đổi sau lần thử.

#### FR-MDL-021 — Chọn mô hình chính và dự phòng
- **BR:** BR-25.01 · INV-21 · **Ưu tiên:** Must
- **Mô tả:** Hệ thống SHALL chỉ cho chọn mô hình đã thử thành công (hoặc đang dùng hợp lệ) làm mô hình chính hoặc dự phòng. Dự phòng SHALL khác chính. Mỗi lần lưu thay đổi cấu hình chung SHALL tạo dấu vết phiên bản (người, thời điểm, giá trị trước / sau) đủ để đối chiếu.
- **Tiêu chí chấp nhận:**
  - [ ] Mô hình chưa thử thành công không nằm trong danh sách chọn chính.
  - [ ] Chọn dự phòng trùng chính → bị từ chối.
  - [ ] Sau hai lần đổi chính, vẫn xem được lịch sử đủ hai phiên bản (hoặc tương đương).

### 3.4. Bảo vệ dữ liệu & rủi ro

#### FR-MDL-030 — Thỏa thuận bảo vệ dữ liệu với nhà cung cấp bên ngoài
- **BR:** BR-25.01 · INV-11 · **Ưu tiên:** Must
- **Mô tả:** Với nhà cung cấp **Bên ngoài**, hệ thống SHALL yêu cầu ghi nhận thỏa thuận không dùng dữ liệu nhà trường để huấn luyện (hoặc ghi nhận khi nhà trường cho phép bằng văn bản) kèm số văn bản thỏa thuận trước khi thử kết nối hoặc đưa mô hình vào dùng.
- **Tiêu chí chấp nhận:**
  - [ ] Thiếu số văn bản thỏa thuận → không thử kết nối / không đưa vào dùng được.
  - [ ] Có đủ thỏa thuận + số văn bản → thử kết nối được (nếu thông tin kết nối đúng).

#### FR-MDL-031 — Phân loại rủi ro mô hình
- **BR:** BR-25.01 · INV-22 · **Ưu tiên:** Must
- **Mô tả:** Hệ thống SHALL cho ghi nhận phân loại rủi ro của từng mô hình (Cao / Trung bình / Thấp) theo văn bản pháp luật hiện hành mà nhà trường áp dụng. Hệ thống SHALL NOT lấy tên nhà cung cấp thương mại làm giá trị mặc định bắt buộc của sản phẩm.
- **Tiêu chí chấp nhận:**
  - [ ] Mỗi mô hình đang dùng hiển thị được mức rủi ro đã ghi nhận.
  - [ ] Dữ liệu mẫu demo không bị khóa thành cấu hình bắt buộc duy nhất.

### 3.5. Việc chức năng không được làm

#### FR-MDL-040 — Không cấu hình lời nhắc trợ lý tại đây
- **BR:** BR-25.01 · **Ưu tiên:** Must
- **Mô tả:** Hệ thống SHALL NOT cho phép cấu hình lời nhắc hệ thống, độ sáng tạo, mẫu đầu ra của trợ lý trên menu này.
- **Tiêu chí chấp nhận:**
  - [ ] Không có trường / tab cấu hình lời nhắc trợ lý trên màn hình nghiệm thu.

---

## 4. Thuộc tính tối thiểu (mức FR)

| Thuộc tính | Bắt buộc | Ghi chú validation |
| --- | --- | --- |
| Tên nhà cung cấp | Có | Không trống |
| Loại nhà cung cấp | Có | Bên ngoài / Nội bộ |
| Bí mật kết nối | Có khi tạo (Bên ngoài/Nội bộ cần kết nối) | Không hiển thị lại |
| Số văn bản thỏa thuận | Có khi Bên ngoài để thử/dùng | Không trống |
| Tên hiển thị mô hình | Có | Không trống |
| Phân loại rủi ro | Có khi đưa vào dùng | Cao / TB / Thấp |
| Mô hình chính | Có khi vận hành gọi AI | Phải thử thành công |
| Mô hình dự phòng | Không | ≠ chính; thử thành công |

---

## 5. RULE tổng hợp

| Mã | Quy tắc |
| --- | --- |
| RULE-MDL-01 | Chỉ mô hình thử thành công mới làm chính / dự phòng |
| RULE-MDL-02 | Bên ngoài: đủ thỏa thuận + số văn bản trước khi thử / dùng |
| RULE-MDL-03 | Không lời nhắc hệ thống trên menu này |
| RULE-MDL-04 | Bí mật kết nối không hiển thị lại, không xuất nhật ký |

---

## 6. MoSCoW & điểm mở

| Hạng mục | MoSCoW |
| --- | --- |
| Khai báo NCC / mô hình, thử kết nối, chính–dự phòng, DPA, rủi ro | Must |
| Lịch sử phiên bản cấu hình đầy đủ so sánh diff | Should |
| Nhiều mô hình dự phòng theo hàng đợi | Could / sau |

**Open points:** Danh mục mức rủi ro chi tiết theo nghị định hướng dẫn — theo dõi OQ-09-01 trên BRD; FRD này chỉ yêu cầu ba mức Cao/TB/Thấp đã ghi nhận.
