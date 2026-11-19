/* AQ EduUAI — FRONTEND-ONLY learning starter.
   No API, authentication, provider calls or production database is implemented.
   Sample non-secret data is stored locally in the browser for convenience. */
'use strict';

const STORAGE_KEY = 'aq_uai-demo-v1';
const nf = new Intl.NumberFormat('en-US');
const fmtVN = n => Number(n || 0).toLocaleString('vi-VN');
const monthLabel = new Intl.DateTimeFormat('vi-VN', {month:'2-digit', year:'numeric'}).format(new Date());
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt = n => nf.format(Number(n || 0));
const todayStamp = () => new Date().toLocaleString('vi-VN');
const uid = prefix => `${prefix}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2,6)}`;
const defaultData = () => ({
  providers:[
    {id:'p_openai',name:'OpenAI LLC (Enterprise Edu)',type:'Bên ngoài',endpoint:'https://api.openai.com/v1',agreement:'VB-2026/DPA-01',approved:true,dpaCommitment:'Zero Data Retention (ZDR) & Không huấn luyện mô hình',dpaSignedAt:'15/01/2026',dpaRepresentative:'Hiệu trưởng phê duyệt',dpaStatus:'Đang hiệu lực'},
    {id:'p_google',name:'Google Cloud (Vertex AI)',type:'Bên ngoài',endpoint:'https://aiplatform.googleapis.com',agreement:'VB-2026/DPA-02',approved:true,dpaCommitment:'Bảo mật chuẩn ISO 27018 & Lưu trữ dữ liệu vùng APAC',dpaSignedAt:'20/02/2026',dpaRepresentative:'P.Hiệu trưởng phụ trách CNTT',dpaStatus:'Đang hiệu lực'},
    {id:'p_anthropic',name:'Anthropic PBC (Commercial)',type:'Bên ngoài',endpoint:'https://api.anthropic.com',agreement:'VB-2026/DPA-03',approved:true,dpaCommitment:'Dữ liệu học thuật không chuyển giao cho bên thứ ba',dpaSignedAt:'01/03/2026',dpaRepresentative:'Trưởng phòng KHCN',dpaStatus:'Chờ gia hạn'},
    {id:'p_local',name:'AQ On-Premise',type:'Nội bộ',endpoint:'http://localhost:11434',agreement:'',approved:true}
  ],
  models:[
    {id:'m_gpt',name:'GPT-4 Omni (Đa nhiệm)',code:'gpt-4o',providerId:'p_openai',capability:'Đa phương thức',maxOutput:4096,temperature:0.7,risk:'Trung bình',active:true,tested:true,testedAt:'17/11/2026 08:30'},
    {id:'m_gemini',name:'Gemini 1.5 Pro (Dự phòng)',code:'gemini-1.5-pro',providerId:'p_google',capability:'Đa phương thức',maxOutput:8192,temperature:0.5,risk:'Trung bình',active:true,tested:true,testedAt:'17/11/2026 07:15'},
    {id:'m_llama',name:'Llama-3.3-70B-VN (On-premise)',code:'llama-3.3-70b-local',providerId:'p_local',capability:'Văn bản',maxOutput:4096,temperature:0.3,risk:'Thấp',active:true,tested:true,testedAt:'17/11/2026 08:05'},
    {id:'m_claude',name:'Claude 3.5 Sonnet',code:'claude-3-5-sonnet',providerId:'p_anthropic',capability:'Văn bản + hình ảnh',maxOutput:8192,temperature:0.4,risk:'Trung bình',active:true,tested:true,testedAt:'17/11/2026 09:10'},
    {id:'m_deepseek',name:'DeepSeek R1 (On-premise)',code:'deepseek-r1-local',providerId:'p_local',capability:'Văn bản',maxOutput:8192,temperature:0.2,risk:'Cao',active:true,tested:true,testedAt:'17/11/2026 08:42'},
    {id:'m_gemini_flash',name:'Gemini 1.5 Flash',code:'gemini-1.5-flash',providerId:'p_google',capability:'Đa phương thức',maxOutput:4096,temperature:0.6,risk:'Thấp',active:true,tested:true,testedAt:'17/11/2026 07:45'},
    {id:'m_gpt_mini',name:'GPT-4o Mini (Tiết kiệm)',code:'gpt-4o-mini',providerId:'p_openai',capability:'Văn bản + hình ảnh',maxOutput:8192,temperature:0.7,risk:'Thấp',active:true,tested:true,testedAt:'17/11/2026 08:50'},
    {id:'m_llama_small',name:'Llama 3.1 8B (Nội bộ)',code:'llama-3.1-8b-local',providerId:'p_local',capability:'Văn bản',maxOutput:4096,temperature:0.4,risk:'Thấp',active:true,tested:true,testedAt:'17/11/2026 08:20'}
  ],
  route:{primary:'m_gpt',backup:'m_gemini'},
  routeHistory:[{at:'17/11/2026 09:00',before:'Chưa cấu hình',after:'GPT-4o Mini → Gemini 1.5 Pro',by:'Admin demo'}],
  users:[
    {id:'u1',code:'NS001',name:'Nguyễn Văn A',title:'TS. Nguyễn Văn A',role:'Giảng viên chính & QL Chương trình',unit:'Khoa Công nghệ Thông tin',email:'vana@uni.edu.vn'},
    {id:'u2',code:'NS002',name:'Trần Thị B',title:'ThS. Trần Thị B',role:'Giảng viên',unit:'Khoa Công nghệ Thông tin',email:'b@uni.edu.vn'},
    {id:'u3',code:'NS003',name:'Lê Minh T',title:'Lê Minh T',role:'Chuyên viên quản lý chương trình',unit:'Phòng Đào tạo',email:'minht@uni.edu.vn'},
    {id:'u4',code:'SV004',name:'Phạm Anh K',title:'Phạm Anh K',role:'Sinh viên',unit:'Khoa Công nghệ Thông tin',email:'sv004@uni.edu.vn'},
    {id:'u5',code:'NS005',name:'Võ Thị M',title:'ThS. Võ Thị M',role:'Giảng viên',unit:'Khoa Khoa học Dữ liệu',email:'vom@uni.edu.vn'},
    {id:'u6',code:'NS006',name:'Đỗ Văn N',title:'Đỗ Văn N',role:'Cán bộ khảo thí',unit:'Phòng Khảo thí',email:'dovn@uni.edu.vn'}
  ],
  groups:[
    {id:'G_GV',name:'Giảng viên',description:'Toàn bộ giảng viên cơ hữu và thỉnh giảng tham gia giảng dạy',source:'Hệ thống',members:['u1','u2','u5'],quotas:{m_gpt:2000,m_gemini:5000,m_claude:0,m_deepseek:10000}},
    {id:'G_QLCT',name:'Quản lý chương trình',description:'Giảng viên và chuyên viên phụ trách thiết kế, kiểm định chương trình',source:'Hệ thống',members:['u1','u3'],quotas:{m_gpt:5000,m_gemini:10000,m_claude:3000,m_deepseek:20000}},
    {id:'G_SV',name:'Sinh viên',description:'Người học đang có tài khoản hoạt động',source:'Hệ thống',members:['u4'],quotas:{m_gpt:500,m_gemini:1000,m_claude:0,m_deepseek:0}},
    {id:'G_KT',name:'Cán bộ khảo thí',description:'Chuyên viên phụ trách đánh giá, khảo thí và đảm bảo chất lượng',source:'Hệ thống',members:['u6'],quotas:{m_gpt:1000,m_gemini:3000,m_claude:0,m_deepseek:0}},
    {id:'AI_NCKH_GENOM',name:'Đề tài NCKH Genom & AI (KC.01)',description:'Nhóm nghiên cứu AI và dữ liệu Genom thuộc đề tài KC.01',source:'AI chuyên biệt',members:['u1','u2'],quotas:{m_gpt:10000,m_gemini:25000,m_claude:15000,m_deepseek:50000}},
    {id:'AI_LAB',name:'AI Lab Thử nghiệm',description:'Nhóm AI chuyên biệt cho nghiên cứu và thử nghiệm nội bộ',source:'AI chuyên biệt',members:['u5'],quotas:{m_gpt:3000,m_gemini:5000,m_claude:1000,m_deepseek:0}}
  ],
  tokenUsed:{u1:{m_gpt:5950,m_gemini:14000,m_claude:6300,m_deepseek:28000},u2:{m_gpt:500,m_gemini:1500},u3:{m_gpt:600,m_gemini:1000}},
  schoolBudget:{amount:25000000,decision:'QD-2026-019',decisionDate:'2026-11-01'},
  suspensions:[],
  events:[],
  creditBase:{u1:500000,u2:600000,u3:300000,u4:200000,u5:100000,u6:100000},
  creditUsed:{u1:820000,u2:200000,u3:0,u4:0,u5:0,u6:0},
  epoch:0,
  ledger:[
    {id:'GD-001',type:'Cấp bổ sung',userId:'u1',amount:1500000,doc:'TT-2026-121',by:'Admin demo',at:'17/11/2026 10:00',epoch:0},
    {id:'GD-002',type:'Cấp bổ sung',userId:'u2',amount:600000,doc:'QD-2026-122',by:'Admin demo',at:'17/11/2026 10:20',epoch:0}
  ]
});
function loadData(){
  try {
    const obj=JSON.parse(localStorage.getItem(STORAGE_KEY));
    return obj && Array.isArray(obj.models) && Array.isArray(obj.groups) && Array.isArray(obj.ledger) ? obj : defaultData();
  } catch { return defaultData(); }
}
let db=loadData();
const ui={page:(location.hash==='#module2'?'quotas':location.hash==='#module3'?'credits':'models'),tab:{models:'list',quotas:'groups',credits:'recipients'},modal:null,selectedUser:'u1',search:{models:'',groups:'',credits:''},groupFilter:'all',groupStatusFilter:'all',creditCategory:'all',creditStatus:'all',sidebarOpen:location.hash==='#module2',modelView:'grid',modelFilters:{provider:'all',platform:'all',risk:'all'},modelModalTab:'connection',modelDraftTested:false,showSecret:false};
function save(){localStorage.setItem(STORAGE_KEY,JSON.stringify(db));}
function user(id){return db.users.find(x=>x.id===id);}
function provider(id){return db.providers.find(x=>x.id===id);}
function model(id){return db.models.find(x=>x.id===id);}
function groupForUser(id){return db.groups.filter(g=>g.members.includes(id));}
function isSuspended(id){return db.suspensions.find(s=>s.userId===id&&s.active);}
function epochLedger(){return db.ledger.filter(x=>x.epoch===db.epoch);}
function totals(id){
  const entries=epochLedger().filter(x=>x.userId===id);
  const base=Number(db.creditBase[id]||0), used=db.epoch===0?Number(db.creditUsed[id]||0):0;
  const grants=entries.filter(x=>x.type==='Cấp bổ sung').reduce((s,x)=>s+x.amount,0);
  const revoked=entries.filter(x=>x.type==='Thu hồi').reduce((s,x)=>s+x.amount,0);
  return {base,grants,revoked,used,balance:Math.max(0,base+grants-revoked-used)};
}
const totalAllocated=()=>db.users.reduce((s,u)=>s+totals(u.id).base+totals(u.id).grants-totals(u.id).revoked,0);
function getQuota(userId,modelId){
  const details=groupForUser(userId).map(g=>({group:g,amount:Number(g.quotas[modelId]||0)})).filter(x=>x.amount>0);
  return {details,total:details.reduce((sum,x)=>sum+x.amount,0)};
}
function toast(message,type='success'){
  const el=document.createElement('div');el.className=`toast ${type}`;el.textContent=message;
  document.getElementById('toast-region').appendChild(el);
  setTimeout(()=>el.remove(),4700);
}
function badge(text,kind='gray'){return `<span class="tag ${kind}">${esc(text)}</span>`;}
function button(label,action,variant='secondary',extra=''){return `<button class="btn ${variant}" type="button" data-action="${esc(action)}" ${extra}>${label}</button>`;}
function head(title,description,icon,actions){return `<div class="heading-row"><div><div class="heading-title"><span class="heading-icon">${icon}</span><div><h1>${title}</h1><div class="subtitle">${description}</div></div></div><div class="breadcrumbs"><strong>Quản trị AI & Dữ liệu</strong> › <strong>Quản lý AI & Chi phí</strong> › ${title}</div></div><div class="actions">${actions||''}</div></div>`;}
function tabs(page,items){return `<div class="section-tabs">${items.map(([id,label])=>`<button class="tab ${ui.tab[page]===id?'active':''}" data-action="tab" data-page="${page}" data-tab="${id}">${label}</button>`).join('')}</div>`;}
function nav(){return `<aside class="sidebar"><div class="brand"><span class="brand-symbol">✦</span><span class="brand-text">AQ<br>EDU UAI<small>UNIFIED AI</small></span></div><input class="nav-search" disabled placeholder="⌕  Tìm menu (Ctrl + K)"/><div class="nav-header">Ứng dụng <span>⌄</span></div><button class="nav-link"><span class="nav-ico">◈</span>Tiện ích chung (AI Tools)</button><button class="nav-link"><span class="nav-ico">☁</span>SaaS</button><button class="nav-link"><span class="nav-ico">▤</span>SaaT</button><button class="nav-link"><span class="nav-ico">▦</span>Quản trị AI & Dữ liệu</button><div class="nav-caption">▸ Quản lý AI & Chi phí</div><div class="nav-sub"><button class="nav-link sub ${ui.page==='models'?'active':''}" data-action="nav" data-page="models"><span class="nav-ico">◉</span>Cấu hình Nhà cung cấp & Mô hình AI</button><button class="nav-link sub ${ui.page==='quotas'?'active':''}" data-action="nav" data-page="quotas"><span class="nav-ico">◈</span>Hạn mức AI theo Nhóm tài khoản</button><button class="nav-link sub ${ui.page==='credits'?'active':''}" data-action="nav" data-page="credits"><span class="nav-ico">⇆</span>Cấp / Thu hồi Hạn mức</button></div><div class="nav-caption">▸ Bảo mật & Tri thức</div><div class="sidebar-spacer"></div><div class="user-box"><span class="avatar">HU</span><div><div class="user-name">Tài khoản demo</div><div class="user-desc">demo@aq.local (không đăng nhập)</div></div></div><div class="sidebar-note">● Frontend demo — không dùng dữ liệu thật</div></aside>`;}
function render(){
 const pageTitle=ui.page==='models'?'Cấu hình Nhà cung cấp & Mô hình AI':ui.page==='quotas'?'Hạn mức AI theo Nhóm tài khoản':'Cấp / Thu hồi Hạn mức';
 document.getElementById('app').innerHTML=`<div class="app-shell ${ui.sidebarOpen?'':'sidebar-collapsed'} ${ui.page==='models'?'model-shell':ui.page==='quotas'?'quota-shell':'credits-shell'}">${nav()}<div class="workspace"><header class="topbar"><button class="burger" type="button" data-action="toggle-sidebar" aria-label="Mở hoặc đóng menu">☰</button><div class="topbar-title"><span class="topbar-blue-icon">◧</span> ${esc(pageTitle)}</div><div class="topbar-right"><span>NĂM LÀM VIỆC</span><span class="topbar-select">2026 <span>⌄</span></span><button type="button" class="topbar-utility" data-action="nav" data-page="models" aria-label="Trang chủ">⌂</button><button type="button" class="topbar-utility" data-action="notice" aria-label="Thông báo">♟</button></div></header><main class="content ${ui.page==='models'?'models-content':ui.page==='quotas'?'quota-content':'credits-content'}">${ui.page==='models'?renderModels():ui.page==='quotas'?renderQuotas():renderCredits()}<div class="footer-note">AQ EduUAI • Bản demo frontend • Không có API / DB / đăng nhập / gọi AI thực tế</div></main></div></div>${ui.modal?renderModal():''}`;
}
