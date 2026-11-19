/* Module 3 — Screenshot-based grant/reclaim frontend.
   Browser-only demonstration: all amounts, transactions and recipients are synthetic.
   Credit policy cards are reference settings, not actual per-model token conversion. */

const creditCategories = {
  u1:{type:'Đề tài NCKH',context:'Đề tài KC.01/2026 (Genom & AI)',subtitle:'Khoa Công nghệ Thông tin',icon:'T',tone:'violet'},
  u2:{type:'Giảng viên',context:'Nghiên cứu & giảng dạy',subtitle:'Khoa Công nghệ Thông tin',icon:'B',tone:'blue'},
  u3:{type:'Khảo thí',context:'Hội đồng Chấm thi / Đào tạo',subtitle:'Phòng Đào tạo',icon:'M',tone:'amber'},
  u4:{type:'Sinh viên',context:'Học tập & tra cứu tài liệu',subtitle:'Khoa Công nghệ Thông tin',icon:'K',tone:'blue'},
  u5:{type:'Đề tài NCKH',context:'Nghiên cứu AI và dữ liệu',subtitle:'Khoa Khoa học Dữ liệu',icon:'M',tone:'violet'},
  u6:{type:'Khảo thí',context:'Hoạt động khảo thí',subtitle:'Phòng Khảo thí',icon:'N',tone:'amber'}
};
const creditPolicyDefaults = [
  {id:'student',name:'Sinh viên Chính quy',icon:'⚑',tone:'blue',value:20000,description:'≈ 400 lượt hỏi đáp học vụ hoặc tra cứu tài liệu thư viện.'},
  {id:'postgraduate',name:'Học viên Sau đại học / NCS',icon:'♟',tone:'violet',value:150000,description:'≈ 2.500 lượt tóm tắt bài báo khoa học hoặc tổng hợp tài liệu.'},
  {id:'lecturer',name:'Giảng viên / Nghiên cứu viên',icon:'▣',tone:'green',value:500000,description:'≈ 10.000 lượt soạn giáo trình, đề cương môn học và chấm bài test.'},
  {id:'administrator',name:'Quản trị Khoa / Ban Đào tạo',icon:'▥',tone:'amber',value:1500000,description:'Phục vụ chatbot tuyển sinh Khoa và xử lý văn bản hành chính.'}
];
const creditMeta = u => creditCategories[u.id] || {type:'Cá nhân',context:'Hạn mức AI cá nhân',subtitle:u.unit,icon:(u.name||'?').slice(-1),tone:'blue'};
const creditNow = () => `${String(new Date().getMonth()+1).padStart(2,'0')}/${new Date().getFullYear()}`;
const creditStatIcon = (char,kind) => `<span class="crt-stat-icon ${kind}" aria-hidden="true">${char}</span>`;

function renderCredits(){
  const activeEntries=epochLedger();
  const grants=activeEntries.filter(x=>x.type==='Cấp bổ sung').reduce((s,x)=>s+x.amount,0);
  const revoked=activeEntries.filter(x=>x.type==='Thu hồi').reduce((s,x)=>s+x.amount,0);
  const used=db.users.reduce((s,u)=>s+totals(u.id).used,0);
  const grantees=db.users.filter(u=>totals(u.id).grants>0).length;
  const percent=db.schoolBudget.amount?Math.min(100,(used/db.schoolBudget.amount*100)):0;
  return `<section class="credits-module">
    ${head('Cấp / Thu hồi Hạn mức',
      'Quản lý cấp mở rộng hạn mức theo từng cá nhân, có căn cứ phê duyệt và thu hồi hạn mức còn dư khi kết thúc nhiệm vụ.',
      '▤',`<div class="crt-action-grid">
        ${button('▣ Xuất Sổ cái','export-ledger','secondary crt-export-btn')}
        ${button('↶ Thu hồi Hạn mức','reclaim','secondary crt-reclaim-btn')}
        ${button('＋ Cấp bổ sung Hạn mức','grant','primary crt-grant-btn')}
      </div>`)}
    <div class="crt-stats" aria-label="Tổng quan hạn mức tháng">
      <div class="crt-stat"><div><div class="crt-stat-label">QUỸ HẠN MỨC TOÀN TRƯỜNG</div><div class="crt-stat-number">${fmt(db.schoolBudget.amount)}</div><div class="crt-stat-foot">Định mức tháng ${creditNow()}</div></div>${creditStatIcon('▤','indigo')}</div>
      <div class="crt-stat"><div><div class="crt-stat-label">HẠN MỨC CẤP NGOẠI LỆ</div><div class="crt-stat-number indigo">${fmt(grants)}</div><div class="crt-stat-foot">Đang ghi nhận (${grantees} đối tượng)</div></div>${creditStatIcon('↗','purple')}</div>
      <div class="crt-stat"><div><div class="crt-stat-label">ĐÃ TIÊU THỤ THỰC TẾ</div><div class="crt-stat-number green">${fmt(used)}</div><div class="crt-stat-foot">≈ ${percent.toFixed(1)}% quỹ toàn trường (mẫu)</div></div>${creditStatIcon('⌁','green')}</div>
      <div class="crt-stat"><div><div class="crt-stat-label">HẠN MỨC ĐÃ THU HỒI</div><div class="crt-stat-number orange">${fmt(revoked)}</div><div class="crt-stat-foot">Tháng ${creditNow()}</div></div>${creditStatIcon('▣','orange')}</div>
    </div>
    ${tabs('credits',[
      ['recipients',`▧ Danh sách Đối tượng Cấp Mở rộng <span class="crt-tab-count">${db.users.length}</span>`],
      ['ledger','▣ Sổ cái Lịch sử Phân bổ (Audit Log)'],
      ['defaults','☷ Định mức Tiêu chuẩn Mặc định']
    ])}
    ${ui.tab.credits==='recipients'?creditRecipients():ui.tab.credits==='ledger'?creditLedger():creditDefaults()}
  </section>`;
}

function creditRecipients(){
  const query=ui.search.credits.trim().toLocaleLowerCase('vi');
  const type=ui.creditCategory||'all',status=ui.creditStatus||'all';
  const people=db.users.filter(u=>{
    const meta=creditMeta(u),susp=!!isSuspended(u.id);
    return (type==='all'||meta.type===type)&&
      (status==='all'||(status==='active'&&!susp)||(status==='suspended'&&susp))&&
      [u.name,u.title,u.code,u.unit,meta.type,meta.context].join(' ').toLocaleLowerCase('vi').includes(query);
  });
  const types=[...new Set(db.users.map(u=>creditMeta(u).type))];
  return `<div class="crt-filter-card">
    <div class="crt-search"><span aria-hidden="true">⌕</span><input class="search-field" data-search="credits" aria-label="Tìm người thụ hưởng" value="${esc(ui.search.credits)}" placeholder="Tìm theo tên giảng viên, khoa, mã đề tài..." /></div>
    <select class="field-select" data-change="credit-category" aria-label="Lọc loại hình">
      <option value="all">Tất cả phân loại</option>
      ${types.map(t=>`<option value="${esc(t)}" ${type===t?'selected':''}>${esc(t)}</option>`).join('')}
    </select>
    <select class="field-select" data-change="credit-status" aria-label="Lọc trạng thái">
      <option value="all">Tất cả trạng thái</option>
      <option value="active" ${status==='active'?'selected':''}>Đang hiệu lực</option>
      <option value="suspended" ${status==='suspended'?'selected':''}>Tạm ngưng</option>
    </select>
    <span class="crt-result-count">Hiển thị <b>${people.length}</b> đối tượng</span>
  </div>
  <div class="crt-table-panel"><table class="crt-recipient-table"><colgroup><col style="width:19%"><col style="width:8%"><col style="width:9%"><col style="width:10%"><col style="width:10%"><col style="width:16%"><col style="width:13%"><col style="width:8%"><col style="width:7%"></colgroup>
    <thead><tr><th>NHÂN SỰ & ĐỐI TƯỢNG THỤ HƯỞNG</th><th>LOẠI HÌNH</th><th>ĐỊNH MỨC CƠ SỞ</th><th>CẤP BỔ SUNG</th><th>TỔNG KHẢ DỤNG</th><th>TIẾN ĐỘ TIÊU THỤ</th><th>HIỆU LỰC & CĂN CỨ</th><th>TRẠNG THÁI</th><th>THAO TÁC</th></tr></thead>
    <tbody>${people.map(u=>{
      const meta=creditMeta(u),t=totals(u.id),gross=t.base+t.grants-t.revoked;
      const pct=gross?Math.min(100,Math.round(t.used/gross*100)):0;
      const docs=epochLedger().filter(l=>l.userId===u.id&&l.doc).map(l=>l.doc);
      const currentSuspended=!!isSuspended(u.id);
      return `<tr>
        <td data-label="Người thụ hưởng"><div class="crt-person-cell"><span class="crt-avatar ${meta.tone}">${esc(meta.icon)}</span><div class="crt-person-info"><strong>${esc(u.title||u.name)}</strong><span class="crt-id">(${esc(u.code)})</span><div class="crt-person-context">${esc(meta.context)} · <em>${esc(meta.subtitle)}</em></div></div></div></td>
        <td data-label="Loại hình"><span class="crt-category ${meta.tone}">${esc(meta.type)}</span></td>
        <td data-label="Định mức cơ sở" class="crt-amount">${fmt(t.base)}</td>
        <td data-label="Cấp bổ sung" class="crt-amount crt-plus">+${fmt(t.grants)}</td>
        <td data-label="Tổng khả dụng" class="crt-amount crt-gross">${fmt(gross)}</td>
        <td data-label="Tiến độ tiêu thụ"><div class="crt-used-line"><span>${fmt(t.used)}</span><strong>${pct}%</strong></div><div class="crt-progress"><span style="width:${pct}%"></span></div></td>
        <td data-label="Hiệu lực & căn cứ"><div class="crt-validity">Hết tháng ${creditNow()}<br><small>(Reset 01/${new Date().getMonth()===11?'01':String(new Date().getMonth()+2).padStart(2,'0')})</small></div><div class="crt-doc">♟ ${esc(docs.at(-1)||'Theo định mức tháng')}</div></td>
        <td data-label="Trạng thái"><span class="crt-status ${currentSuspended?'paused':'active'}">${currentSuspended?'Tạm ngưng':'Đang hiệu lực'}</span></td>
        <td data-label="Thao tác"><div class="crt-row-actions"><button class="crt-icon-button" title="Cấp bổ sung" aria-label="Cấp bổ sung cho ${esc(u.name)}" data-action="grant" data-id="${esc(u.id)}">⊕</button><button class="crt-icon-button" title="Thu hồi" aria-label="Thu hồi hạn mức của ${esc(u.name)}" data-action="reclaim" data-id="${esc(u.id)}" ${t.balance<=0?'disabled':''}>↶</button></div></td>
      </tr>`;
    }).join('')||'<tr><td class="crt-empty" colspan="9">Không tìm thấy đối tượng phù hợp.</td></tr>'}</tbody>
  </table></div>
  <div class="crt-demo-caption">Giao diện mô phỏng; dữ liệu credits tách biệt với hạn mức tokens/model của Module 2. Chưa có API hoặc cơ sở dữ liệu thực.</div>`;
}

function creditLedger(){
  const rows=db.ledger.slice().reverse();
  return `<div class="crt-ledger-banner"><span class="crt-banner-symbol">◈</span><span>Sổ cái ghi nhận bất biến (Append-only Ledger). Mọi thao tác cấp/thu hồi đều gắn căn cứ phê duyệt.</span><span class="crt-banner-right">Chuẩn kiểm toán: RULE-UAI-18</span></div>
  <div class="crt-table-panel"><table class="crt-ledger-table"><colgroup><col style="width:9%"><col style="width:10%"><col style="width:19%"><col style="width:10%"><col style="width:12%"><col style="width:14%"><col style="width:12%"><col style="width:14%"></colgroup>
    <thead><tr><th>MÃ GIAO DỊCH</th><th>THỜI GIAN</th><th>ĐỐI TƯỢNG THỤ HƯỞNG</th><th>HÀNH ĐỘNG</th><th>SỐ LƯỢNG CREDIT</th><th>CĂN CỨ PHÊ DUYỆT</th><th>NGƯỜI THỰC HIỆN</th><th>GHI CHÚ</th></tr></thead>
    <tbody>${rows.map(l=>{
      const u=user(l.userId),isGrant=l.type==='Cấp bổ sung';
      const meta=u?creditMeta(u):null;
      return `<tr><td data-label="Mã giao dịch" class="crt-ledger-id">${esc(l.id)}</td>
        <td data-label="Thời gian">${esc(l.at)}</td>
        <td data-label="Đối tượng"><strong>${esc(u?.title||u?.name||'Không rõ')}</strong><small>${esc(u?.code||'')} · ${esc(meta?.context||'')}</small></td>
        <td data-label="Hành động"><span class="crt-txn-type ${isGrant?'grant':'reclaim'}">${isGrant?'↓ CẤP BỔ SUNG':'↑ THU HỒI'}</span></td>
        <td data-label="Số lượng" class="crt-txn-amount ${isGrant?'grant':'reclaim'}">${isGrant?'+':'−'}${fmt(l.amount)}</td>
        <td data-label="Căn cứ" class="crt-doc-number">${esc(l.doc)}</td><td data-label="Người thực hiện">${esc(l.by)}</td>
        <td data-label="Ghi chú">${esc(l.note||'Giao dịch hạn mức kỳ '+(Number(l.epoch||0)+1))}</td></tr>`;
    }).join('')||'<tr><td class="crt-empty" colspan="8">Chưa có giao dịch trong sổ cái.</td></tr>'}</tbody>
  </table></div>
  <div class="crt-ledger-tools"><span>Chỉ ghi thêm trong giao diện demo; tính bất biến cần được bảo đảm ở backend/database.</span>${button('↓ Xuất sổ cái CSV','export-ledger','secondary')}</div>`;
}

function creditDefaults(){
  const saved=db.defaultCreditPolicies||{};
  return `<div class="crt-policy-panel"><div class="crt-policy-heading"><div><h2>Bảng Định mức Tài nguyên AI Tự động Hàng Tháng</h2><p>Được tự động nạp mới (reset) vào 00:00 ngày mùng 1 hàng tháng theo vai trò người dùng trong CSDL Nhà trường.</p></div><button type="submit" form="credit-policy-form" class="btn crt-save-policy">Lưu quy chế</button></div>
    <form id="credit-policy-form"><div class="crt-policy-grid">${creditPolicyDefaults.map(p=>`<label class="crt-policy-card"><span class="crt-policy-name"><span class="crt-policy-icon ${p.tone}">${p.icon}</span>${esc(p.name)}</span><span class="crt-policy-value"><input type="text" inputmode="numeric" name="policy_${p.id}" pattern="[0-9,\. ]+" value="${fmt(Number(saved[p.id]??p.value))}" required aria-label="Định mức ${esc(p.name)}"/><span>Credits/tháng</span></span><span class="crt-policy-desc">${esc(p.description)}</span></label>`).join('')}</div></form>
    <div class="crt-policy-note">Các định mức vai trò ở đây mô phỏng tab của prototype; lưu không tự điều chỉnh hạn mức nhóm × mô hình hay số dư của người dùng (cần quy tắc nghiệp vụ chính thức).</div>
  </div>`;
}
