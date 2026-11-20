# AQ-FRD-UAI-CRT-001 — Cấp / Thu hồi Hạn mức

| Mục | Nội dung |
| :--- | :--- |
| Mã tài liệu | `AQ-FRD-UAI-CRT-001` |
| Sản phẩm | AQ EduUAI |
| Menu | Quản trị AI & Dữ liệu → Quản lý AI & Chi phí → **Cấp / Thu hồi Hạn mức** |
| Phiên bản | 1.0 |
| Ngày | 17/11/2026 |
| Trạng thái | Dự thảo — bàn giao kèm biên bản giao việc TTS |
| Nguồn nghiệp vụ | BRD UAI v1.1 · **BR-26.02** · INV-17, INV-18 |
| Actor chính | Người phụ trách quản trị AI |
| Actor phụ | Trưởng đơn vị (cấp / thu hồi trong phạm vi đơn vị); người dùng (xem số dư của mình — Should) |
| Ưu tiên tổng | Must (giai đoạn prototype khung) |

> FRD = cam kết chức năng. **Không** dùng chữ “Nạp credit”. Prototype; framework nền liên hệ Tech lead.

---

## 1. Thông tin chung & mục đích

### 1.1. Mục đích chức năng

Hệ thống SHALL cho phép **cấp bổ sung** và **thu hồi** hạn mức AI cho **một người cụ thể** trong **tháng hiện tại**, bắt buộc có **căn cứ** (tờ trình / quyết định), ghi **sổ cái chỉ thêm** (append-only), để điều phối hạn mức ngoài định mức nhóm mà vẫn đối chiếu được.

### 1.2. Trong phạm vi

- Cấp bổ sung hạn mức gắn họ tên, mã nhân sự/học viên, đơn vị.
- Thu hồi hạn mức gắn một người; mặc định điền toàn bộ số dư còn lại; cho phép thu hồi một phần.
- Hiệu lực cấp bổ sung cố định trong tháng hiện tại (reset ngày 01).
- Sổ cái giao dịch: Cấp bổ sung, Thu hồi (+ điều chỉnh nếu có) — không sửa/xóa dòng cũ.
- Xem danh sách đối tượng đang có hạn mức mở rộng / số dư liên quan.

### 1.3. Ngoài phạm vi

- Cấu hình hạn mức theo nhóm × mô hình (FRD QTA).
- Cắt / ngưng đột xuất (FRD QTA).
- Cổng thanh toán, ví coin, nạp tiền fintech.
- Chọn thời hạn theo Học kỳ / Đề tài / Đợt thi.
- Sửa nội dung giao dịch đã ghi.

---

## 2. Mô tả tổng quan

Người đủ quyền SHALL:

1. Mở **Cấp / Thu hồi Hạn mức**.
2. Cấp bổ sung cho một người cụ thể kèm căn cứ và số lượng.
3. Thu hồi từ một người cụ thể; hệ thống điền sẵn số dư còn lại.
4. Xem sổ cái các giao dịch đã ghi (chỉ đọc / xuất — Should).

---

## 3. Yêu cầu chức năng chi tiết (FR)

### 3.1. Truy cập & nhãn chức năng

#### FR-CRT-001 — Truy cập theo quyền
- **BR:** BR-26.02 · **Ưu tiên:** Must
- **Mô tả:** Hệ thống SHALL chỉ cho tài khoản có quyền Thêm (cấp / thu hồi) hoặc Xem trên chức năng này thực hiện đúng thao tác được cấp.
- **Tiêu chí chấp nhận:**
  - [ ] Không đủ quyền → không cấp / không thu hồi được.
  - [ ] Đủ quyền Xem → xem được danh sách / sổ cái trong phạm vi.

#### FR-CRT-002 — Không dùng mô hình “Nạp credit”
- **BR:** BR-26.02 · INV-18 · **Ưu tiên:** Must
- **Mô tả:** Hệ thống SHALL trình bày chức năng là cấp / thu hồi hạn mức nội bộ. Hệ thống SHALL NOT dùng nhãn hoặc luồng “Nạp credit”, “nạp tiền”, cổng thanh toán cá nhân.
- **Tiêu chí chấp nhận:**
  - [ ] Trên UI nghiệm thu không còn chữ “Nạp credit” / “Nạp tiền”.
  - [ ] Có đủ hai thao tác Cấp bổ sung và Thu hồi (hoặc tương đương rõ nghĩa).

### 3.2. Cấp bổ sung

#### FR-CRT-010 — Đối tượng cấp là một người cụ thể
- **BR:** BR-26.02 · INV-18 · **Ưu tiên:** Must
- **Mô tả:** Khi cấp bổ sung, hệ thống SHALL bắt buộc định danh **một con người**: họ tên, mã nhân sự hoặc mã học viên, đơn vị. Hệ thống SHALL NOT cho chọn tên dự án, tên khoa/phòng chung làm đối tượng thụ hưởng duy nhất thay cho người.
- **Tiêu chí chấp nhận:**
  - [ ] Thiếu họ tên hoặc mã → không lưu.
  - [ ] Bản ghi cấp sau khi lưu gắn đúng một người cụ thể trên danh sách.

#### FR-CRT-011 — Căn cứ pháp lý bắt buộc
- **BR:** BR-26.02 · **Ưu tiên:** Must
- **Mô tả:** Hệ thống SHALL yêu cầu căn cứ khi cấp bổ sung: tối thiểu số tờ trình / quyết định, và các trường người duyệt / nguồn quỹ nếu sản phẩm đã chốt trên đặc tả. Thiếu căn cứ → không lưu.
- **Tiêu chí chấp nhận:**
  - [ ] Bỏ trống số tờ trình / quyết định → không cấp được.
  - [ ] Có đủ căn cứ + số lượng hợp lệ → có giao dịch “Cấp bổ sung” trên sổ cái.

#### FR-CRT-012 — Hiệu lực trong tháng hiện tại
- **BR:** BR-26.02 · INV-17 · **Ưu tiên:** Must
- **Mô tả:** Hiệu lực cấp bổ sung SHALL cố định **trong tháng hiện tại** (hết hiệu lực khi reset ngày 01 tháng sau). Hệ thống SHALL NOT cho chọn thời hạn Học kỳ / Đề tài / Đợt thi.
- **Tiêu chí chấp nhận:**
  - [ ] Trên form cấp, hiệu lực thể hiện là tháng hiện tại / reset ngày 01.
  - [ ] Không có dropdown chu kỳ ngoài tháng.

#### FR-CRT-013 — Không vượt phần được giao
- **BR:** BR-26.02 · INV-18 · **Ưu tiên:** Must
- **Mô tả:** Hệ thống SHALL từ chối cấp vượt phần còn được phân bổ / còn của sổ người cấp đang thao tác, và SHALL nêu phần còn lại.
- **Tiêu chí chấp nhận:**
  - [ ] Cấp vượt phần còn → từ chối kèm số còn được cấp.
  - [ ] Trưởng đơn vị (nếu được cấp quyền) không cấp được cho người ngoài đơn vị mình.

### 3.3. Thu hồi

#### FR-CRT-020 — Thu hồi gắn một người cụ thể
- **BR:** BR-26.02 · INV-18 · **Ưu tiên:** Must
- **Mô tả:** Hệ thống SHALL chỉ cho thu hồi từ danh sách / lựa chọn **người cụ thể** đang có số dư khả dụng > 0. Hệ thống SHALL NOT thu hồi theo tên dự án hoặc đơn vị chung chung thay cho người.
- **Tiêu chí chấp nhận:**
  - [ ] Danh sách đối tượng thu hồi chỉ gồm người cụ thể (có mã).
  - [ ] Không xuất hiện dòng chỉ có tên dự án/khoa không gắn người.

#### FR-CRT-021 — Tự điền số dư còn lại; cho thu hồi một phần
- **BR:** BR-26.02 · INV-17 · **Ưu tiên:** Must
- **Mô tả:** Khi chọn người, hệ thống SHALL hiển thị tóm tắt tối thiểu: hạn mức gốc (hoặc cơ sở), cấp bổ sung, đã dùng, **số dư tối đa có thể thu hồi**. Trường số lượng thu hồi SHALL **mặc định bằng toàn bộ số dư còn lại**; người thao tác được giảm xuống để thu hồi một phần; hệ thống SHALL từ chối số lượng > số dư còn lại.
- **Tiêu chí chấp nhận:**
  - [ ] Chọn người có dư 1 300 → ô số lượng mặc định 1 300.
  - [ ] Nhập vượt dư → từ chối.
  - [ ] Thu hồi một phần thành công → số dư giảm đúng phần đã thu.

#### FR-CRT-022 — Căn cứ khi thu hồi
- **BR:** BR-26.02 · **Ưu tiên:** Must
- **Mô tả:** Hệ thống SHALL yêu cầu căn cứ thu hồi (biên bản / quyết định hoặc trường tương đương đã chốt). Thiếu căn cứ → không thu hồi.
- **Tiêu chí chấp nhận:**
  - [ ] Thiếu căn cứ → không lưu thu hồi.
  - [ ] Thu hồi thành công → có dòng “Thu hồi” trên sổ cái kèm căn cứ.

### 3.4. Sổ cái

#### FR-CRT-030 — Giao dịch chỉ ghi thêm
- **BR:** BR-26.02 · INV-18 · **Ưu tiên:** Must
- **Mô tả:** Mọi giao dịch Cấp bổ sung và Thu hồi SHALL chỉ ghi thêm. Hệ thống SHALL NOT cung cấp sửa hoặc xóa dòng giao dịch đã ghi. Số dư SHALL tính từ giao dịch, không nhập tay số dư.
- **Tiêu chí chấp nhận:**
  - [ ] Không có nút Sửa / Xóa trên dòng giao dịch.
  - [ ] Không có ô nhập trực tiếp “số dư = …” để ghi đè.

#### FR-CRT-031 — Thu hồi khi nghỉ việc / thôi học (Should trên prototype)
- **BR:** BR-26.02 · **Ưu tiên:** Should
- **Mô tả:** Khi tài khoản bị khóa do nghỉ việc / thôi học theo quy tắc quản trị tài khoản, hệ thống SHOULD thu hồi toàn bộ số dư cá nhân còn lại bằng giao dịch Thu hồi có lý do tương ứng.
- **Tiêu chí chấp nhận:**
  - [ ] Nếu triển khai trên prototype: khóa tài khoản mẫu → có giao dịch thu hồi hết dư.
  - [ ] Nếu chưa làm: ghi rõ trong báo cáo TTS là Should chưa đạt — không chặn Must khác.

### 3.5. Việc chức năng không được làm

#### FR-CRT-040 — Không fintech / không chu kỳ ngoài tháng
- **BR:** BR-26.02 · **Ưu tiên:** Must
- **Mô tả:** Hệ thống SHALL NOT triển khai ví coin, confetti nạp tiền, hay chọn hiệu lực ngoài tháng hiện tại trên menu này.
- **Tiêu chí chấp nhận:**
  - [ ] Không còn UI ví / nạp tiền cá nhân.
  - [ ] Không chọn được hiệu lực Học kỳ/Đề tài.

---

## 4. Thuộc tính tối thiểu (mức FR)

| Thuộc tính | Bắt buộc | Ghi chú |
| --- | --- | --- |
| Họ tên người thụ hưởng / bị thu hồi | Có | Một người cụ thể |
| Mã nhân sự / học viên | Có | Khớp tài khoản đang hoạt động |
| Đơn vị | Có | |
| Số lượng credit / hạn mức | Có | > 0; thu hồi ≤ dư còn lại |
| Số tờ trình / quyết định (căn cứ) | Có | Không trống |
| Hiệu lực | Hệ thống | Tháng hiện tại |
| Loại giao dịch | Hệ thống | Cấp bổ sung / Thu hồi |

---

## 5. RULE tổng hợp

| Mã | Quy tắc |
| --- | --- |
| RULE-CRT-01 | Đối tượng cấp / thu hồi = một người cụ thể |
| RULE-CRT-02 | Có căn cứ mới ghi giao dịch |
| RULE-CRT-03 | Hiệu lực cấp = trong tháng; chu kỳ không ngoài tháng |
| RULE-CRT-04 | Thu hồi mặc định = toàn bộ dư; không vượt dư |
| RULE-CRT-05 | Giao dịch chỉ ghi thêm; không “Nạp credit” |

---

## 6. MoSCoW & điểm mở

| Hạng mục | MoSCoW |
| --- | --- |
| Cấp / thu hồi một người, căn cứ, hiệu lực tháng, sổ cái append-only, tự điền dư | Must |
| Thu hồi tự động khi nghỉ việc | Should |
| Xuất sổ cái Excel / PDF | Should |
| Điều chỉnh giao dịch sai bằng dòng mới | Could / theo FSD đầy đủ |

**Open points:** Bộ trường căn cứ tối thiểu (người duyệt, nguồn quỹ) — giữ khớp BRD; prototype Must ít nhất **số tờ trình/quyết định**.
