/* Module 2 — Quota policies and individual cumulative lookup.
   Screens closely follow the supplied AQ prototype. All data is synthetic;
   real quota enforcement and monthly accounting require a backend. */

const quotaModelIds = ['m_gpt','m_gemini','m_claude','m_deepseek'];
const quotaDisplayName = id => ({
  m_gpt:'GPT-4o',m_gemini:'Gemini 1.5 Pro',m_claude:'Claude 3.5 Sonnet',m_deepseek:'DeepSeek R1 / V3'
}[id] || model(id)?.name || id);

function renderQuotas(){
  const actions=`<button type="button" class="btn qta-sync" data-action="sync-groups">⟳ &nbsp;Đồng bộ Nhóm & Người dùng</button>
    <button type="button" class="btn qta-lookup-btn" data-action="tab" data-page="quotas" data-tab="lookup">▦ &nbsp;Tra cứu Cộng dồn Cá nhân</button>
    <button type="button" class="btn qta-add-btn" data-action="add-group">＋ &nbsp;Thêm mới Nhóm AI</button>`;
  return `<section class="quota-module">
    ${head('Hạn mức AI theo Nhóm tài khoản',
      'Đồng bộ nhóm hệ thống, phân bổ quota chi tiết theo từng Model AI và tự động tính tổng hạn mức cộng dồn đa nhóm',
      '♙',actions)}
    ${tabs('quotas',[
      ['groups',`☷ Danh sách Nhóm & Hạn mức Model AI <span class="tab-counter">${db.groups.length}</span>`],
      ['lookup','▦ Tra cứu & Kiểm toán Hạn mức Cộng dồn Cá nhân']
    ])}
    ${ui.tab.quotas==='groups'?quotaGroups():quotaLookup()}
  </section>`;
}

function quotaGroups(){
  const q = ui.search.groups.trim().toLowerCase();
  const groups=db.groups.filter(g =>
    (ui.groupFilter==='all'||g.source===ui.groupFilter) &&
    (ui.groupStatusFilter==='all'||(ui.groupStatusFilter==='active'?(g.active!==false):(g.active===false))) &&
    [g.id,g.name,g.description||''].join(' ').toLowerCase().includes(q)
  );
  const option=(v,text,selected)=>`<option value="${esc(v)}" ${v===selected?'selected':''}>${esc(text)}</option>`;
  const row=(g,index)=>{
    const origin=g.source==='Hệ thống';
    const quotaBadges=quotaModelIds.map(id=>{
      const m=model(id);if(!m)return '';
      const value=Number(g.quotas?.[id]||0);
      return value>0
        ? `<span class="qta-model-chip"><b>${esc(quotaDisplayName(id))}:</b> ${fmtVN(value)} tok</span>`
        : `<span class="qta-model-chip disabled"><s>${esc(quotaDisplayName(id))}: Tắt</s></span>`;
    }).join('');
    return `<tr>
      <td class="qta-order">${index+1}</td>
      <td class="qta-code">${esc(g.id)}</td>
      <td><div class="qta-group-title">${esc(g.name)}
         <button type="button" class="qta-edit-btn" data-action="edit-group" data-id="${esc(g.id)}" aria-label="Cấu hình nhóm ${esc(g.name)}" title="Cấu hình nhóm">✎ Cấu hình</button>
        </div><div class="qta-group-description">${esc(g.description||'Nhóm áp dụng hạn mức AI theo tháng')}</div></td>
      <td><span class="qta-origin ${origin?'system':'special'}">${origin?'☁ Hệ thống đồng bộ':'✧ AI chuyên biệt'}</span></td>
      <td><span class="qta-members"><span>♣</span>${g.members.length}</span></td>
      <td><div class="qta-chips">${quotaBadges}</div></td>
    </tr>`;
  };
  return `<div class="qta-filter-card">
     <div class="qta-search"><span>⌕</span><input class="search-field" data-search="groups" value="${esc(ui.search.groups)}" placeholder="Tìm theo mã nhóm hoặc tên nhóm..." aria-label="Tìm nhóm tài khoản" /></div>
     <select class="field-select" data-change="group-filter" aria-label="Nguồn gốc nhóm">
       ${option('all','Tất cả nguồn gốc',ui.groupFilter)}
       ${option('Hệ thống','Hệ thống đồng bộ',ui.groupFilter)}
       ${option('AI chuyên biệt','AI chuyên biệt',ui.groupFilter)}
     </select>
     <select class="field-select" data-change="group-status-filter" aria-label="Trạng thái nhóm">
       ${option('all','Tất cả trạng thái',ui.groupStatusFilter)}
       ${option('active','Đang hoạt động',ui.groupStatusFilter)}
       ${option('inactive','Ngừng hoạt động',ui.groupStatusFilter)}
     </select>
     <span class="qta-show-count">Hiển thị <b>${groups.length}</b> nhóm</span>
  </div>
  <div class="qta-table-frame"><div class="qta-table-scroll">
    <table class="qta-group-table"><thead><tr>
      <th>STT</th><th>MÃ NHÓM</th><th>TÊN NHÓM & VAI TRÒ</th><th>NGUỒN GỐC</th><th>THÀNH VIÊN</th><th>HẠN MỨC CẤU HÌNH THEO TỪNG MODEL AI</th>
    </tr></thead><tbody>${groups.map(row).join('')||'<tr><td colspan="6" class="qta-empty">Không tìm thấy nhóm tài khoản.</td></tr>'}</tbody></table>
  </div></div>
  <div class="qta-tools-row">
    <button class="btn secondary" data-action="school-budget">▤ Tổng hạn mức Nhà trường (tháng)</button>
    <span>Demo: tokens/model/tháng được minh họa độc lập với credits ở Module 3.</span>
  </div>`;
}

function quotaLookup(){
  const u=user(ui.selectedUser)||db.users[0];
  const groups=groupForUser(u.id);
  const suspended=isSuspended(u.id);
  const profileName=u.title||u.name;
  const initial=u.name?.trim().split(/\s+/).slice(-1)[0]?.[0]||'A';
  const lookupRows=quotaModelIds.map(id=>{
    const m=model(id);if(!m||!m.active)return '';
    const q=getQuota(u.id,id); const p=provider(m.providerId);
    const used=Number(db.tokenUsed?.[u.id]?.[id]||0);
    const percentage=q.total?Math.min(100,Math.round(used/q.total*100)):0;
    const breakdown=q.details.map(x=>`${fmtVN(x.amount)} (${x.group.id})`).join(' + ')||'Không có nhóm cấp hạn mức';
    const tag=p?.type==='Nội bộ'?'On-premise':'Cloud API';
    return `<tr>
       <td><div class="qta-model-title"><span class="qta-model-logo">${id==='m_gpt'?'♟':id==='m_gemini'?'◈':id==='m_claude'?'✳':'◆'}</span><div><strong>${esc(quotaDisplayName(id))}</strong><small>${esc(p?.type==='Nội bộ'?'AQ On-Premise':p?.name||'AI Provider')}</small></div></div></td>
       <td><span class="qta-platform">${esc(tag)}</span></td>
       <td class="qta-group-num">${q.details.length} nhóm</td>
       <td class="qta-formula">${esc(breakdown)}</td>
       <td class="qta-total"><strong>${fmtVN(q.total)}</strong><small> tok</small></td>
       <td><div class="qta-progress-label"><span>Đã dùng: ${fmtVN(used)}</span><b>${percentage}%</b></div><div class="qta-progress-track"><div style="width:${percentage}%"></div></div></td>
    </tr>`;
  }).join('');
  return `<div class="qta-audit-panel">
    <div class="qta-audit-heading">
      <div><h2><span>♟</span> Tra cứu Hạn mức Cá nhân & Kiểm toán Cộng dồn</h2>
        <p>Chọn hoặc tìm kiếm bất kỳ giảng viên, sinh viên hoặc cán bộ để kiểm tra các nhóm họ tham gia và tổng hạn mức hưởng thực tế</p></div>
      <label class="qta-user-picker"><b>Chọn nhân sự tra cứu:</b>
        <select class="input" data-change="selected-user">${db.users.map(x=>`<option value="${esc(x.id)}" ${u.id===x.id?'selected':''}>${esc((x.title||x.name)+' - '+x.code+' ('+x.unit+')')}</option>`).join('')}</select>
      </label>
    </div>
    <div class="qta-profile">
      <div class="qta-profile-person"><span class="qta-profile-avatar">${esc(initial)}</span><div><div class="qta-person-name">${esc(profileName)} <span>(${esc(u.code)})</span></div>
       <p>${esc(u.role||'Người dùng')} • ${esc(u.unit)}</p><a href="mailto:${esc(u.email||'')}" title="Email minh họa">${esc(u.email||'user@uni.edu.vn')}</a></div></div>
      <div class="qta-profile-right"><div class="qta-profile-activity"><span class="qta-state ${suspended?'suspended':'active'}">${suspended?'⊘ Hạn mức ĐÃ CẮT':'✓ Hạn mức Đang Hoạt động'}</span>
       ${suspended?button('Khôi phục hạn mức','restore','success',`data-id="${esc(u.id)}"`):button('⊘ Cắt / Dừng Hạn mức Ngay','suspend','danger',`data-id="${esc(u.id)}"`)}</div>
       <div class="qta-group-count">THUỘC VỀ ${groups.length} NHÓM TÀI KHOẢN:</div>
       <div class="qta-member-chips">${groups.map(g=>`<span>♣ &nbsp;[${esc(g.id)}] ${esc(g.name)}</span>`).join('')||'<span>Chưa thuộc nhóm tài khoản</span>'}</div></div>
    </div>
    ${suspended?`<div class="note warning"><strong>ĐÃ CẮT (mô phỏng):</strong> ${esc(suspended.scope)} · ${esc(suspended.reason)}. Không có backend để chặn API thật.</div>`:''}
    <div class="qta-table-title"><h3>BẢNG CHI TIẾT HẠN MỨC CỘNG DỒN THEO TỪNG MODEL AI (THÁNG ${monthLabel})</h3><span>ĐƠN VỊ: TOKENS / THÁNG</span></div>
    <div class="qta-audit-table-wrap"><table class="qta-audit-table"><thead><tr>
      <th>Mô hình AI<br>(Model)</th><th>Loại hạ tầng</th><th>Các nhóm gán hạn mức</th><th>Chi tiết cộng dồn (Phép tính)</th><th>TỔNG HẠN MỨC HƯỞNG</th><th>Tiến độ tiêu thụ</th>
    </tr></thead><tbody>${lookupRows||'<tr><td colspan="6">Chưa có mô hình hoạt động.</td></tr>'}</tbody></table></div>
  </div>
  <div class="qta-log-panel"><div class="panel-title"><div><h2>Nhật ký cắt / khôi phục / làm mới (demo)</h2><span class="muted text-small">Bản ghi thử nghiệm trong trình duyệt, không phải audit log production.</span></div>${button('⟳ Giả lập làm mới tháng','simulate-reset','secondary')}</div>${eventTable()}</div>
  <div class="qta-tools-row"><button class="btn secondary" data-action="school-budget">▤ Tổng hạn mức Nhà trường (tháng)</button><span>Phần tiêu thụ tokens chỉ là dữ liệu ví dụ, không tích hợp API mô hình.</span></div>`;
}

function eventTable(){
  return `<div class="table-wrap"><table class="data-table"><thead><tr><th>Thời điểm</th><th>Sự kiện</th><th>Người bị ảnh hưởng</th><th>Chi tiết</th></tr></thead><tbody>${db.events.slice().reverse().map(e=>`<tr><td>${esc(e.at)}</td><td>${badge(e.type,e.type==='Cắt hạn mức'?'red':e.type==='Khôi phục'?'green':'purple')}</td><td>${esc(user(e.userId)?.name||'Toàn hệ thống')}</td><td>${esc(e.info)}</td></tr>`).join('')||'<tr><td colspan="4" class="placeholder">Chưa có sự kiện demo.</td></tr>'}</tbody></table></div>`;
}
