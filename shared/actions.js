// Shared delegated event handlers and demo-only state mutations.
function updatePage(page){if(!['models','quotas','credits'].includes(page))return;ui.page=page;ui.modal=null;ui.sidebarOpen=(page==='quotas');location.hash=page==='models'?'module1':page==='quotas'?'module2':'module3';render();window.scrollTo({top:0,behavior:'instant'});}
function openModal(type,id){if(type==='model'){ui.modelModalTab='connection';ui.modelDraftTested=false;ui.showSecret=false;}ui.modal={type,id};render();}
function closeModal(){ui.modal=null;render();}
function addEvent(type,userId,info){db.events.push({type,userId,info,at:todayStamp()});}
function csvDownload(filename,rows){
 const csv='\ufeff'+rows.map(row=>row.map(v=>`"${String(v??'').replace(/"/g,'""')}"`).join(',')).join('\r\n');
 const href=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8;'}));
 const a=document.createElement('a');a.href=href;a.download=filename;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(href),4000);
}
function dispatch(action,el){
 const id=el.dataset.id;
 switch(action){
  case 'nav':updatePage(el.dataset.page);break;
  case 'toggle-sidebar':ui.sidebarOpen=!ui.sidebarOpen;render();break;
  case 'notice':toast('Không có thông báo mới trong bản demo.');break;
  case 'view-grid':ui.modelView='grid';render();break;
  case 'view-list':ui.modelView='list';render();break;
  case 'model-modal-tab':{
    ui.modelModalTab=el.dataset.tab;
    document.querySelectorAll('.model-modal-tabs button').forEach(btn=>btn.classList.toggle('active',btn.dataset.tab===ui.modelModalTab));
    document.querySelectorAll('.model-modal-pane').forEach(pane=>pane.classList.toggle('active',pane.dataset.pane===ui.modelModalTab));
    const scroll=document.querySelector('.model-config-scroll');if(scroll)scroll.scrollTop=0;
    break;
  }
  case 'toggle-secret':{const inp=document.getElementById('model-secret');if(inp){inp.type=inp.type==='password'?'text':'password';}break;}
  case 'test-model-draft':{
    const form=document.getElementById('model-form');if(!form)break;
    const formValues=Object.fromEntries(new FormData(form).entries());
    const pr=provider(formValues.providerId), status=document.getElementById('model-test-result');
    if(!formValues.name?.trim()||!formValues.code?.trim()){
      if(status){status.textContent='Điền tên và Model ID trước khi thử.';status.className='model-test-result is-error';}break;
    }
    if(pr?.type==='Bên ngoài'&&(!formValues.agreement?.trim()||formValues.dpaApproved!=='on')){
      if(status){status.textContent='Cần số văn bản DPA và xác nhận trước khi thử.';status.className='model-test-result is-error';}break;
    }
    document.getElementById('model-demo-tested').value='1';
    if(status){status.textContent='✓ Mô phỏng thành công — không gửi API request';status.className='model-test-result is-success';}
    break;
  }
  case 'tab':{ui.tab[el.dataset.page]=el.dataset.tab;
    if(el.dataset.page==='quotas')ui.sidebarOpen=(el.dataset.tab==='groups');
    render();break;}
  case 'add-model':openModal('model');break;
  case 'edit-model':openModal('model',id);break;
  case 'add-provider':openModal('provider');break;
  case 'edit-provider':openModal('provider',id);break;
  case 'add-group':ui.tab.quotas='groups';openModal('group');break;
  case 'edit-group':openModal('group',id);break;
  case 'sync-groups':openModal('sync');break;
  case 'school-budget':openModal('budget');break;
  case 'suspend':openModal('suspend',id);break;
  case 'grant':openModal('grant',id);break;
  case 'reclaim':openModal('reclaim',id);break;
  case 'close-modal':closeModal();break;
  case 'toggle-model':{
   const m=model(id);if(!m)return;
   if(m.active&&(db.route.primary===id||db.route.backup===id)){toast('Không được ngừng dùng mô hình đang là Chính / Dự phòng. Hãy đổi cấu hình trước.','error');return;}
   m.active=!m.active;save();render();toast(`Đã ${m.active?'bật':'ngừng'} mô hình trong dữ liệu demo.`);break;
  }
  case 'test-model':{
   const m=model(id),p=m&&provider(m.providerId);
   if(!m||!p)return;
   if(p.type==='Bên ngoài'&&(!p.agreement||!p.approved)){toast('Thiếu DPA / số văn bản. Không thể thử kết nối (FR-MDL-030).','error');return;}
   m.tested=true;m.testedAt=todayStamp();save();render();toast('KẾT QUẢ GIẢ LẬP: Thành công. Chưa thực hiện HTTP request đến nhà cung cấp.');break;
  }
  case 'test-gateway':toast(`MÔ PHỎNG: ${db.models.filter(m=>m.active).length} mô hình hoạt động. Không có kết nối API thật.`);break;
  case 'restore':{
   const s=isSuspended(id);if(s){s.active=false;addEvent('Khôi phục',id,'Khôi phục không tạo quota mới');save();render();toast('Đã khôi phục trạng thái demo; số dư không tăng.');}break;
  }
  case 'simulate-reset':openModal('reset');
   // Confirm reset is handled by a separate button injected below when the modal is opened.
   break;
  case 'confirm-sync':{
    if(!db.groups.find(g=>g.id==='G_BGH'))db.groups.push({id:'G_BGH',name:'Ban Giám hiệu',source:'Hệ thống',members:[],quotas:{}});
    save();closeModal();toast('Đồng bộ dữ liệu nhóm demo thành công, nhóm AI chuyên biệt được giữ nguyên.');break;
  }
  case 'confirm-reset':{
    db.epoch+=1;addEvent('Làm mới',null,`Bắt đầu kỳ demo ${db.epoch+1}; không mang số dư kỳ trước sang`);
    save();closeModal();toast('Đã mô phỏng bắt đầu kỳ mới. Ledger kỳ cũ được giữ lại.');break;
  }
  case 'export-models':csvDownload('aq-models-demo.csv',[['Model ID','Tên','Nhà cung cấp','Rủi ro','Hoạt động'],...db.models.map(m=>[m.code,m.name,provider(m.providerId)?.name,m.risk,m.active?'Có':'Không'])]);toast('Đã tải CSV demo.');break;
  case 'export-ledger':csvDownload('aq-ledger-demo.csv',[['ID','Thời điểm','Mã nhân sự','Người','Loại','Số lượng credits','Căn cứ','Kỳ'],...db.ledger.map(l=>[l.id,l.at,user(l.userId)?.code,user(l.userId)?.name,l.type,l.amount,l.doc,(l.epoch||0)+1])]);toast('Đã tải CSV demo.');break;
  case 'reset-demo':if(confirm('Khôi phục toàn bộ dữ liệu mẫu? Các thay đổi frontend của bạn sẽ bị mất.')){db=defaultData();ui.modal=null;save();render();toast('Đã khôi phục dữ liệu mẫu.');}break;
 }
}
function handleSubmit(e){
 const f=e.target,id=f.getAttribute('id');if(!['model-form','provider-form','group-form','budget-form','suspend-form','grant-form','reclaim-form','route-form','credit-policy-form'].includes(id))return;
 e.preventDefault();const x=Object.fromEntries(new FormData(f).entries());
 try {
  if(id==='credit-policy-form'){
   const next={};
   for(const p of creditPolicyDefaults){const val=Number(String(x['policy_'+p.id]??'').replace(/[,\.\s]/g,''));if(!Number.isSafeInteger(val)||val<0)throw Error('Định mức tham chiếu phải là số nguyên không âm.');next[p.id]=val;}
   db.defaultCreditPolicies=next;
   toast('Đã lưu bảng định mức tham chiếu trong trình duyệt; chưa cập nhật số dư hoặc ledger.');
  } else if(id==='model-form'){
   if(!db.providers.find(p=>p.id===x.providerId))throw Error('Nhà cung cấp không hợp lệ.');
   const old=x.id?model(x.id):null;
   if(!x.name?.trim()||!x.code?.trim())throw Error('Thiếu tên hiển thị hoặc Model ID.');
   const previousProvider=old?.providerId, changed=!!old&&(old.code!==x.code.trim()||previousProvider!==x.providerId);
   const tested=x.demoTested==='1'||(!!old&&old.tested&&!changed);
   if(x.role&&x.role!=='none'&&!tested)throw Error('Cần thử kết nối mô phỏng thành công trước khi gắn vai trò chính hoặc dự phòng.');
   const prov=provider(x.providerId);
   if(x.role&&x.role!=='none'&&prov.type==='Bên ngoài'&&(!x.agreement?.trim()||x.dpaApproved!=='on'))throw Error('Cần số văn bản và xác nhận DPA trước khi đưa mô hình bên ngoài vào dùng.');
   const modelId=old?.id||uid('m');
   if(x.role==='primary'&&db.route.backup===modelId)throw Error('Mô hình chính không được trùng mô hình dự phòng. Hãy bỏ gắn vai trò cũ trên tab Điều phối.');
   if(x.role==='backup'&&db.route.primary===modelId)throw Error('Mô hình dự phòng không được trùng mô hình chính. Hãy bỏ gắn vai trò cũ trên tab Điều phối.');
   const newM={id:modelId,name:x.name.trim(),code:x.code.trim(),providerId:x.providerId,capability:x.capability||'Văn bản',maxOutput:Number(x.maxOutput||4096),temperature:Number(x.temperature??0.7),risk:x.risk||'Trung bình',active:old?.active??true,tested,testedAt:tested?(x.demoTested==='1'?todayStamp():old?.testedAt||todayStamp()):''};
   if(x.agreement?.trim()){prov.agreement=x.agreement.trim();prov.approved=x.dpaApproved==='on';}
   if(old)Object.assign(old,newM);else db.models.push(newM);
   if(x.role==='primary'&&db.route.primary!==modelId){db.routeHistory.push({at:todayStamp(),before:`Chính: ${model(db.route.primary)?.name||'—'}`,after:`Chính: ${newM.name}`,by:'Admin demo'});db.route.primary=modelId;}
   if(x.role==='backup'&&db.route.backup!==modelId){db.routeHistory.push({at:todayStamp(),before:`Dự phòng: ${model(db.route.backup)?.name||'—'}`,after:`Dự phòng: ${newM.name}`,by:'Admin demo'});db.route.backup=modelId;}
   toast('Đã lưu thông tin mô hình trong trình duyệt (không lưu API Key).');
  } else if(id==='provider-form'){
   const p=x.id?provider(x.id):null,record={id:p?.id||uid('p'),name:x.name.trim(),type:x.type,endpoint:x.endpoint.trim(),agreement:x.agreement?.trim()||'',approved:x.approved==='on',dpaCommitment:x.dpaCommitment?.trim()||'',dpaSignedAt:x.dpaSignedAt?.trim()||'',dpaRepresentative:x.dpaRepresentative?.trim()||'',dpaStatus:p?.dpaStatus||((x.approved==='on'&&x.agreement?.trim())?'Đang hiệu lực':'Thiếu hồ sơ')};
   if(p)Object.assign(p,record);else db.providers.push(record);
   toast('Đã lưu nhà cung cấp demo.');
  } else if(id==='group-form'){
   const orig=x.originalId,old=orig?db.groups.find(g=>g.id===orig):null,code=x.id.trim();
   if(!old&&db.groups.some(g=>g.id===code))throw Error('Mã nhóm đã tồn tại.');
   if(old&&orig!==code&&db.groups.some(g=>g.id===code))throw Error('Mã nhóm mới đã tồn tại.');
   const quotas={};db.models.filter(m=>m.active).forEach(m=>{const v=Number(f.elements[`quota_${m.id}`]?.value||0);if(v<0||!Number.isFinite(v))throw Error('Hạn mức không hợp lệ.');quotas[m.id]=v;});
   const members=Array.from(f.querySelectorAll('input[name="members"]:checked')).map(v=>v.value);
   const record={id:code,name:x.name.trim(),description:(x.description||'').trim(),source:old?.source||'AI chuyên biệt',members,quotas};
   if(old)Object.assign(old,record);else db.groups.push(record);
   toast('Đã lưu nhóm và hạn mức mô hình demo.');
  } else if(id==='budget-form'){
   const amount=Number(x.amount),allocated=totalAllocated();
   if(amount<allocated)throw Error(`Tổng mới không được nhỏ hơn phần đã phân bổ. Cần thu hồi ${fmt(allocated-amount)} credits demo trước.`);
   db.schoolBudget={amount,decision:x.decision.trim(),decisionDate:x.decisionDate};
   toast('Đã lưu tổng hạn mức demo theo tháng.');
  } else if(id==='suspend-form'){
   if(!x.reason.trim()||!x.orderedBy.trim())throw Error('Thiếu lý do hoặc người ra lệnh.');
   const active=isSuspended(x.userId);if(active)active.active=false;
   db.suspensions.push({id:uid('s'),userId:x.userId,scope:x.scope,orderedBy:x.orderedBy.trim(),reason:x.reason.trim(),until:x.until,active:true});
   addEvent('Cắt hạn mức',x.userId,`${x.scope}: ${x.reason}`);
   toast('Đã cắt hạn mức trên giao diện demo.');
  } else if(id==='grant-form'){
   const amount=Number(x.amount),remaining=db.schoolBudget.amount-totalAllocated();
   if(!user(x.userId))throw Error('Phải chọn cá nhân có mã nhân sự/học viên.');
   if(!x.doc.trim())throw Error('Thiếu số văn bản quyết định.');
   if(!Number.isInteger(amount)||amount<=0||amount>remaining)throw Error(`Lượng cấp không hợp lệ; quỹ demo còn ${fmt(remaining)} credits.`);
   db.ledger.push({id:uid('GD'),type:'Cấp bổ sung',userId:x.userId,amount,doc:x.doc.trim(),by:'Admin demo',at:todayStamp(),epoch:db.epoch});
   toast(`Đã cấp bổ sung ${fmt(amount)} credits demo cho ${user(x.userId).name}.`);
  } else if(id==='reclaim-form'){
   const amount=Number(x.amount),available=totals(x.userId).balance;
   if(!user(x.userId))throw Error('Phải chọn cá nhân cụ thể.');
   if(!x.doc.trim())throw Error('Thiếu căn cứ thu hồi.');
   if(!Number.isInteger(amount)||amount<=0||amount>available)throw Error(`Không được thu hồi vượt ${fmt(available)} credits còn lại.`);
   db.ledger.push({id:uid('GD'),type:'Thu hồi',userId:x.userId,amount,doc:x.doc.trim(),by:'Admin demo',at:todayStamp(),epoch:db.epoch});
   toast(`Đã thu hồi ${fmt(amount)} credits demo từ ${user(x.userId).name}.`);
  } else if(id==='route-form'){
   if(x.primary&&x.primary===x.backup)throw Error('Mô hình dự phòng phải khác mô hình chính.');
   const chosen=[x.primary,x.backup].filter(Boolean);
   if(chosen.some(id=>{const m=model(id),p=m&&provider(m.providerId);return !m||!m.active||!m.tested||(p.type==='Bên ngoài'&&(!p.agreement||!p.approved));}))throw Error('Chỉ mô hình hoạt động, thử thành công và đủ DPA mới được chọn.');
   const summary=id=>model(id)?.name||'Không chọn';
   db.routeHistory.push({at:todayStamp(),before:`${summary(db.route.primary)} → ${summary(db.route.backup)}`,after:`${summary(x.primary)} → ${summary(x.backup)}`,by:'Admin demo'});
   db.route={primary:x.primary,backup:x.backup};toast('Đã cập nhật cấu hình Chính / Dự phòng demo.');
  }
  save();ui.modal=null;render();
 } catch(error){toast(error.message||'Dữ liệu không hợp lệ.','error');}
}
document.addEventListener('click',e=>{
 const control=e.target.closest('[data-action]');
 if(control){e.preventDefault();dispatch(control.dataset.action,control);return;}
 if(e.target.id==='modal-overlay')closeModal();
});
document.addEventListener('submit',handleSubmit);
document.addEventListener('change',e=>{
 const mode=e.target.dataset.change;
 if(mode==='selected-user'){ui.selectedUser=e.target.value;render();}
 if(mode==='group-filter'){ui.groupFilter=e.target.value;render();}
 if(mode==='group-status-filter'){ui.groupStatusFilter=e.target.value;render();}
 if(mode==='credit-category'){ui.creditCategory=e.target.value;render();}
 if(mode==='credit-status'){ui.creditStatus=e.target.value;render();}
 if(mode==='reclaim-user'){ui.modal={type:'reclaim',id:e.target.value};render();}
 if(e.target.dataset.modelFilter){ui.modelFilters[e.target.dataset.modelFilter]=e.target.value;render();}
 if(e.target.matches('input[name="providerId"]')){
   document.querySelectorAll('.provider-choice').forEach(node=>node.classList.toggle('selected',node.querySelector('input')?.checked));
   const p=provider(e.target.value),agreement=document.getElementById('mdl-agreement');
   if(agreement)agreement.value=p?.agreement||'';
   const confirm=document.querySelector('input[name="dpaApproved"]');if(confirm)confirm.checked=!!p?.approved;
   const doc=document.getElementById('model-demo-tested');if(doc)doc.value='0';
   const status=document.getElementById('model-test-result');if(status){status.textContent='';status.className='model-test-result';}
 }
});
document.addEventListener('input',e=>{
 const which=e.target.dataset.search;if(!which)return;
 const position=e.target.selectionStart;ui.search[which]=e.target.value;render();
 const next=document.querySelector(`[data-search="${which}"]`);if(next){next.focus();next.setSelectionRange(position,position);}
});
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&ui.modal)closeModal();});
render();
