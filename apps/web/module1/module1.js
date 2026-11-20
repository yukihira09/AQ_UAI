// Module 1: provider/model registry, routing & DPA views.
function providerInfo(p){
 if(!p)return {label:'Không rõ',kind:'gray',icon:'◉'};
 if(p.id==='p_openai')return {label:'OpenAI',kind:'openai',icon:'♟'};
 if(p.id==='p_google')return {label:'Gemini',kind:'gemini',icon:'◈'};
 if(p.id==='p_anthropic')return {label:'Anthropic',kind:'anthropic',icon:'▧'};
 if(p.type==='Nội bộ')return {label:'On-premise',kind:'onprem',icon:'▤'};
 return {label:p.name,kind:'gray',icon:'◉'};
}
function renderModels(){
 const actions=`${button('▣  Xuất Danh mục','export-models','secondary')}${button('ϟ  Kiểm tra Gateway Toàn trường','test-gateway','success')}${button('＋  Thêm Mô hình Mới','add-model','primary')}`;
 return `<section class="module-one ${ui.tab.models==='dpa'?'dpa-active':''}">${head('Cấu hình Nhà cung cấp & Mô hình AI','Quản trị AI Gateway, phân loại rủi ro (Luật AI 2025 Điều 9-10), thiết lập mô hình chính/dự phòng và cam kết DPA','▤',actions)}
 ${tabs('models',[['list',`♧ Danh mục Mô hình AI <span class="tab-counter">${db.models.length}</span>`],['routing','♧ Quy tắc Điều phối & Dự phòng (FS-UAI-08)'],['dpa','▤ Hồ sơ Pháp lý & Thỏa thuận DPA (INV-11)']])}
 ${ui.tab.models==='list'?modelsList():ui.tab.models==='routing'?modelsRouting():modelsDpa()}</section>`;
}
function modelsList(){
 const opts=(pairs,sel)=>pairs.map(([v,t])=>`<option value="${esc(v)}" ${sel===v?'selected':''}>${esc(t)}</option>`).join('');
 const mf=ui.modelFilters;
 const entries=db.models.filter(m=>{
   const p=provider(m.providerId);
   const q=ui.search.models.toLowerCase();
   return [m.name,m.code,p?.name,providerInfo(p).label].join(' ').toLowerCase().includes(q)
     &&(mf.provider==='all'||mf.provider===m.providerId)
     &&(mf.platform==='all'||mf.platform===(p?.type==='Nội bộ'?'internal':'cloud'))
     &&(mf.risk==='all'||mf.risk===m.risk);
 });
 const modelCard=m=>{
  const p=provider(m.providerId),pi=providerInfo(p),role=db.route.primary===m.id?'CHÍNH':db.route.backup===m.id?'DỰ PHÒNG':'';
  const stamp=m.testedAt||(m.tested?'17/11/2026 08:30':'Chưa kiểm tra');
  const dpa=p?.type==='Nội bộ'?'Hạ tầng máy chủ trường':p?.agreement||'Chưa có hồ sơ';
  const roleTag=role?`<span class="model-role ${role==='CHÍNH'?'is-primary':'is-backup'}">${role==='CHÍNH'?'★':'⬡'} ${role==='CHÍNH'?'MÔ HÌNH CHÍNH':'DỰ PHÒNG'}</span>`:'';
  return `<article class="model-card source-model-card"><div class="model-top"><div class="model-flags"><span class="provider-tag ${pi.kind}"><span>${pi.icon}</span> ${esc(pi.label)}</span>${roleTag}</div><button class="toggle ${m.active?'on':''}" aria-label="Bật hoặc ngừng dùng ${esc(m.name)}" aria-pressed="${m.active}" data-action="toggle-model" data-id="${esc(m.id)}" title="Bật / ngừng dùng mô hình"></button></div>
  <div class="model-name">${esc(m.name)}</div><div class="model-caption">${esc(m.code)}</div><div class="model-card-separator"></div>
  <div class="model-data"><div><small>MAX TOKENS</small><strong>${Number(m.maxOutput)||0}</strong></div><div><small>TEMPERATURE</small><strong>${Number(m.temperature??0.7).toFixed(1)}</strong></div><div><small>RỦI RO (LUẬT AI)</small><strong>${badge('Rủi ro '+m.risk,m.risk==='Cao'?'red':m.risk==='Thấp'?'green':'amber')}</strong></div><div><small>HỒ SƠ DPA</small><strong class="dpa-reference"><span class="check-glyph">✓</span> ${esc(dpa)}</strong></div></div>
  <div class="model-footer"><span class="tested-date">◷ ${esc(stamp)}</span><div class="list-inline"><button class="btn mini secondary" data-action="test-model" data-id="${esc(m.id)}">⚡ Test</button><button class="btn mini primary" data-action="edit-model" data-id="${esc(m.id)}">☷ Sửa</button></div></div></article>`;
 };
 const listTable=`<div class="table-wrap model-table-wrap"><table class="data-table"><thead><tr><th>Mô hình</th><th>Nhà cung cấp</th><th>Rủi ro</th><th>Max tokens</th><th>Trạng thái</th><th>Thao tác</th></tr></thead><tbody>${entries.map(m=>`<tr><td><strong>${esc(m.name)}</strong><br><span class="code">${esc(m.code)}</span></td><td>${esc(providerInfo(provider(m.providerId)).label)}</td><td>${badge(m.risk)}</td><td>${fmt(m.maxOutput)}</td><td>${m.active?badge('Đang dùng','green'):badge('Đã ngừng','gray')}</td><td><button class="btn mini secondary" data-action="test-model" data-id="${esc(m.id)}">⚡ Test</button> <button class="btn mini primary" data-action="edit-model" data-id="${esc(m.id)}">Sửa</button></td></tr>`).join('')||'<tr><td colspan="6">Không tìm thấy mô hình.</td></tr>'}</tbody></table></div>`;
 return `<div class="model-list-area"><div class="model-filterbar"><div class="model-search-wrap"><span>⌕</span><input class="search-field" data-search="models" placeholder="Tìm theo tên mô hình, model ID, nhà cung cấp..." value="${esc(ui.search.models)}" aria-label="Tìm mô hình" /></div>
 <select class="field-select" data-model-filter="provider" aria-label="Lọc nhà cung cấp">${opts([['all','Tất cả nhà cung cấp'],...db.providers.map(p=>[p.id,providerInfo(p).label])],mf.provider)}</select>
 <select class="field-select" data-model-filter="platform" aria-label="Lọc hạ tầng">${opts([['all','Tất cả hạ tầng'],['cloud','Cloud API'],['internal','On-premise']],mf.platform)}</select>
 <select class="field-select" data-model-filter="risk" aria-label="Lọc rủi ro">${opts([['all','Tất cả mức rủi ro (Luật AI 2025)'],['Cao','Rủi ro Cao'],['Trung bình','Rủi ro Trung bình'],['Thấp','Rủi ro Thấp']],mf.risk)}</select>
 <span class="model-count">Hiển thị <strong>${entries.length}</strong> mô hình</span><div class="view-switch"><button type="button" class="${ui.modelView==='grid'?'active':''}" data-action="view-grid" aria-label="Xem dạng thẻ">▦</button><button type="button" class="${ui.modelView==='list'?'active':''}" data-action="view-list" aria-label="Xem dạng danh sách">☷</button></div></div>
 ${ui.modelView==='grid'?`<div class="model-grid">${entries.map(modelCard).join('')||'<div class="placeholder">Không tìm thấy mô hình phù hợp.</div>'}</div>`:listTable}
 <div class="model-demo-caution">Bản dựng giao diện: thao tác Test chỉ mô phỏng, API key không được lưu; dữ liệu chỉ tồn tại trong trình duyệt.</div></div>`;
}
function modelsRouting(){
 const eligible=db.models.filter(m=>m.active&&m.tested&&((provider(m.providerId)?.type==='Nội bộ')||(provider(m.providerId)?.agreement&&provider(m.providerId)?.approved)));
 const selectOpts=(selected,allowBlank=false)=>`${allowBlank?'<option value="">Không chọn</option>':''}${eligible.map(m=>`<option value="${m.id}" ${selected===m.id?'selected':''}>${esc(m.name)}</option>`).join('')}`;
 return `<div class="cards-row" style="margin-bottom:15px"><div class="info-card"><h3>⏱ Thời gian Timeout</h3><div class="big">30 <span class="text-small muted">giây</span></div><span class="muted text-small">Mô phỏng thông số gateway</span></div><div class="info-card"><h3>⚙ Mã lỗi kích hoạt dự phòng</h3><div class="big" style="font-size:17px">HTTP 500, 502, 503, 429</div><span class="muted text-small">Hiển thị tham khảo prototype</span></div><div class="info-card"><h3>⌂ Dữ liệu nội bộ</h3><div class="big" style="color:var(--purple)">On-premise</div><span class="muted text-small">Chưa có router xử lý dữ liệu thật</span></div></div>
 <div class="panel"><h2>Cấu hình mô hình chính / dự phòng</h2><div class="note warning">Chỉ mô hình <strong>đang hoạt động và đã qua kiểm thử demo</strong> được xuất hiện trong danh sách. Cấu hình thực tế và automatic failover chưa triển khai.</div><form id="route-form"><div class="form-grid"><div class="form-field"><label>Mô hình chính <span class="req">*</span></label><select class="input" name="primary" required>${selectOpts(db.route.primary)}</select></div><div class="form-field"><label>Mô hình dự phòng</label><select class="input" name="backup">${selectOpts(db.route.backup,true)}</select></div></div><button class="btn primary" type="submit">Lưu cấu hình demo</button></form></div>
 <div class="panel"><h2>Lịch sử cấu hình (chỉ thêm trong giao diện)</h2><div class="table-wrap"><table class="data-table"><thead><tr><th>Thời điểm</th><th>Trước</th><th>Sau</th><th>Người thao tác</th></tr></thead><tbody>${db.routeHistory.slice().reverse().map(h=>`<tr><td>${esc(h.at)}</td><td>${esc(h.before)}</td><td>${esc(h.after)}</td><td>${esc(h.by)}</td></tr>`).join('')}</tbody></table></div></div>`;
}
function modelsDpa(){
 // The sample agreements below mirror the user-provided prototype screenshot.
 // They are NOT verified contracts, production provider assurances, or compliance advice.
 const external=db.providers.filter(p=>p.type==='Bên ngoài');
 const rows=external.map(p=>{
   const status=!p.agreement?'Thiếu hồ sơ':(p.dpaStatus||(p.approved?'Đang hiệu lực':'Chờ gia hạn'));
   const statusClass=status==='Đang hiệu lực'?'is-valid':status==='Chờ gia hạn'?'is-pending':'is-missing';
   return `<tr>
      <td><button type="button" class="dpa-document-button" data-action="edit-provider" data-id="${esc(p.id)}" title="Cập nhật hồ sơ nhà cung cấp">${esc(p.agreement||'—')}</button></td>
      <td class="dpa-provider">${esc(p.name)}</td>
      <td class="dpa-commitment">${esc(p.dpaCommitment||'Chưa bổ sung nội dung cam kết')}</td>
      <td class="dpa-date">${esc(p.dpaSignedAt||'—')}</td>
      <td class="dpa-representative">${esc(p.dpaRepresentative||'—')}</td>
      <td class="dpa-status-cell"><span class="dpa-status ${statusClass}">${esc(status)}</span></td>
     </tr>`;
 }).join('');
 return `<div class="dpa-page">
   <div class="dpa-legal-banner">
     <div class="dpa-legal-intro"><span class="dpa-document-icon" aria-hidden="true">▣</span><span>Danh mục Thỏa thuận Bảo vệ Dữ liệu (Data Processing Agreement - DPA) đã ký kết theo Luật Bảo vệ dữ liệu cá nhân số 91/2025/QH15.</span></div>
     <div class="dpa-compliance">Chuẩn tuân thủ: INV-11 &amp; FS-UAI-06</div>
   </div>
   <div class="dpa-table-frame"><div class="dpa-table-scroll"><table class="dpa-legal-table">
     <thead><tr><th>SỐ VĂN BẢN DPA</th><th>NHÀ CUNG CẤP</th><th>CAM KẾT CHÍNH</th><th>NGÀY KÝ KẾT</th><th>NGƯỜI ĐẠI DIỆN TRƯỜNG</th><th>TRẠNG THÁI</th></tr></thead>
     <tbody>${rows||'<tr><td colspan="6" class="dpa-empty">Chưa có thỏa thuận DPA của nhà cung cấp bên ngoài.</td></tr>'}</tbody>
   </table></div></div>
   <div class="dpa-admin-footer"><span>Dữ liệu thỏa thuận và trạng thái trong ảnh là dữ liệu mẫu cho giao diện, không phải hồ sơ pháp lý thực tế.</span><button type="button" data-action="add-provider">+ Thêm nhà cung cấp (demo)</button></div>
 </div>`;
}
