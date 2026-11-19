/* runtime.js：深藍暖米殼的頁面互動。由 shell.py 讀檔內嵌進 md-to-preview.py 產的頁，不要手抄。
   不含評論系統，評論一律由 inject.py 注入正典 overlay。
   管五件事：題目卡作答、訊息卡通過／要改／不發、底部進度列、浮動目錄、把結果交給評論工具的「複製全部」。
   狀態存 localStorage（key 取 body 的 data-pv-key），讀寫都包 try/catch。
   注意：這個檔不能出現直接賦值給評論設定物件的寫法，inject.py 會把它誤讀成設定（所以下面用字串拼出設定名稱）。 */
(function(){
  var doc=document.getElementById('doc'); if(!doc) return;
  var body=document.body, root=document.documentElement;
  var KEY=(body.getAttribute('data-pv-key')||('pv2_'+location.pathname))+'__state';
  var TITLE=body.getAttribute('data-pv-title')||document.title;
  var ROUND=parseInt(body.getAttribute('data-pv-round')||'1',10);
  function $$(sel,scope){ return Array.prototype.slice.call((scope||document).querySelectorAll(sel)); }
  function load(){ try{ return JSON.parse(localStorage.getItem(KEY)||'{}')||{}; }catch(e){ return {}; } }
  function save(){ try{ localStorage.setItem(KEY,JSON.stringify(S)); }catch(e){} }
  function txt(el){ return el?String(el.textContent||'').replace(/\s+/g,' ').trim():''; }
  var S=load(); S.q=S.q||{}; S.t=S.t||{}; S.m=S.m||{};

  var qs=$$('.pv-q',doc), todos=$$('input[data-todo]',doc), msgs=$$('.pv-msg',doc), followers=$$('.pv-var[data-follow]',doc);
  var bar=document.querySelector('.pv-bar'), barCount=document.querySelector('.pv-bar-count'), meter=document.querySelector('.pv-meter i');

  /* 沒有題目也沒有訊息要審的頁（原文審稿、純說明）不放進度列，目錄入口改成右下角浮動鈕 */
  var hasBar=!!bar&&(qs.length+msgs.length>0);
  body.classList.toggle('pv-nobar',!hasBar);
  function syncBar(){ root.style.setProperty('--pv-bar-real',(hasBar?bar.offsetHeight:0)+'px'); }

  /* ---- 題目卡 ---- */
  function qValues(q){ return $$('input[data-opt]',q).filter(function(i){return i.checked;}).map(function(i){return i.value;}); }
  function paintQ(q){
    var v=S.q[q.dataset.q]||[];
    $$('input[data-opt]',q).forEach(function(i){ i.checked=v.indexOf(i.value)>=0; });
    q.classList.toggle('is-done',v.length>0);
    var st=q.querySelector('.pv-q-state'); if(st) st.textContent=v.length?'已答':'還沒答';
  }
  qs.forEach(function(q){
    var one=q.dataset.kind==='one';
    $$('input[data-opt]',q).forEach(function(i){
      i.addEventListener('change',function(){
        if(i.checked && (one || i.hasAttribute('data-x'))){ $$('input[data-opt]',q).forEach(function(o){ if(o!==i) o.checked=false; }); }
        if(i.checked && !one && !i.hasAttribute('data-x')){ $$('input[data-x]',q).forEach(function(o){ o.checked=false; }); }
        S.q[q.dataset.q]=qValues(q); save(); paintQ(q); progress();
      });
    });
    var all=q.querySelector('[data-checkall]');
    if(all) all.addEventListener('click',function(){
      $$('input[data-opt]',q).forEach(function(o){ o.checked=!o.hasAttribute('data-x'); });
      S.q[q.dataset.q]=qValues(q); save(); paintQ(q); progress();
    });
    paintQ(q);
  });
  todos.forEach(function(i){
    i.checked=!!S.t[i.getAttribute('data-todo')];
    i.addEventListener('change',function(){ S.t[i.getAttribute('data-todo')]=i.checked; save(); paintToc(); });
  });
  /* 框選選項裡的文字留評論時，放開滑鼠不要順便勾到 */
  document.addEventListener('click',function(e){
    var lab=e.target.closest&&e.target.closest('label.pv-opt, .pv-todo-col label');
    if(!lab) return;
    var sel=window.getSelection&&window.getSelection();
    if(sel && String(sel).trim().length>0 && e.target.tagName!=='INPUT'){ e.preventDefault(); }
  },true);

  /* ---- 訊息卡 ----
     按「要改」的訊息，改完一律再給審稿的人看一次才發，沒有「改完直接發」這條路。 */
  var LABEL={pass:'通過',edit:'要改',skip:'不發'};
  function mState(id){ return S.m[id]||(S.m[id]={}); }
  function paintMsg(el){
    var st=S.m[el.dataset.id]||{};
    ['pass','edit','skip'].forEach(function(k){ el.classList.toggle('is-'+k,st.s===k); });
    $$('[data-act]',el).forEach(function(b){ b.setAttribute('aria-pressed',String(b.getAttribute('data-act')===st.s)); });
    var chip=el.querySelector('.pv-status');
    if(chip){ chip.textContent=st.s?LABEL[st.s]:'還沒審'; chip.className='pv-chip pv-status '+(st.s==='pass'?'ok':st.s==='edit'?'look':''); }
    var note=el.querySelector('.pv-note'); if(note && note.value!==(st.note||'')) note.value=st.note||'';
    var tg=el.querySelector('.pv-msg-toggle'); if(tg) tg.textContent=el.classList.contains('is-folded')?'展開':'收起';
    if(st.s!=='pass' && st.s!=='skip') el.classList.remove('is-folded');
  }
  function setMsg(el,act,byUser){
    var st=mState(el.dataset.id);
    st.s=(byUser && st.s===act)?'':act;
    save(); paintMsg(el); progress(); applyFilter();
    if(byUser && (st.s==='pass'||st.s==='skip')){
      setTimeout(function(){
        if((S.m[el.dataset.id]||{}).s!==st.s) return;
        el.classList.add('is-folded'); paintMsg(el);
        var top=el.getBoundingClientRect().top+window.scrollY-topGap();
        if(el.getBoundingClientRect().top<topGap()) window.scrollTo(0,top);
      },220);
    }
    if(byUser && st.s==='edit'){ var n=el.querySelector('.pv-note'); if(n) setTimeout(function(){ try{ n.focus({preventScroll:true}); }catch(e){} },50); }
  }
  function topGap(){ var h=parseInt(getComputedStyle(root).getPropertyValue('--pco-bar-h'),10)||0; return h+16; }
  msgs.forEach(function(el){
    $$('[data-act]',el).forEach(function(b){ b.addEventListener('click',function(){ setMsg(el,b.getAttribute('data-act'),true); }); });
    var note=el.querySelector('.pv-note');
    if(note) note.addEventListener('input',function(){ mState(el.dataset.id).note=note.value; save(); });
    var tg=el.querySelector('.pv-msg-toggle');
    if(tg) tg.addEventListener('click',function(){ el.classList.toggle('is-folded'); paintMsg(el); });
    var st=S.m[el.dataset.id]||{}; if(st.s==='pass'||st.s==='skip') el.classList.add('is-folded');
    paintMsg(el);
  });
  $$('[data-passall]',doc).forEach(function(btn){
    btn.addEventListener('click',function(){
      var g=btn.getAttribute('data-passall'), n=0;
      msgs.forEach(function(el){
        if(g!=='*' && el.dataset.group!==g) return;
        var st=mState(el.dataset.id); if(st.s) return;
        st.s='pass'; n++; el.classList.add('is-folded'); paintMsg(el);
      });
      save(); progress(); applyFilter(); toast(n?('已把還沒審的 '+n+' 則標成通過'):'這批沒有還沒審的了');
    });
  });

  /* ---- 篩選：全部、還沒審、要改 ---- */
  var filter='all';
  function applyFilter(){
    msgs.forEach(function(el){
      var s=(S.m[el.dataset.id]||{}).s||'';
      var show=filter==='all'||(filter==='todo'&&!s)||(filter==='edit'&&s==='edit');
      el.classList.toggle('pv-hide',!show);
    });
  }
  $$('.pv-filter button',doc).forEach(function(b){
    b.addEventListener('click',function(){
      filter=b.getAttribute('data-filter');
      $$('.pv-filter button',doc).forEach(function(o){ o.setAttribute('aria-pressed',String(o.getAttribute('data-filter')===filter)); });
      applyFilter();
    });
  });

  /* ---- 收件人視角的分頁 ---- */
  function showLane(id){
    $$('.pv-lane',doc).forEach(function(l){ l.classList.toggle('is-on',l.getAttribute('data-lane')===id); });
    $$('.pv-tabs button',doc).forEach(function(b){ b.setAttribute('aria-pressed',String(b.getAttribute('data-lane')===id)); });
  }
  $$('.pv-tabs button',doc).forEach(function(b){ b.addEventListener('click',function(){ showLane(b.getAttribute('data-lane')); }); });
  doc.addEventListener('click',function(e){
    var a=e.target.closest&&e.target.closest('a[href^="#"]'); if(!a) return;
    var t=document.getElementById(decodeURIComponent(a.getAttribute('href').slice(1))); if(!t) return;
    open(t);
  });

  /* ---- 進度 ---- */
  function qLeft(q){ return !(S.q[q.dataset.q]||[]).length; }
  function mLeft(el){ return !(S.m[el.dataset.id]||{}).s; }
  function undecided(){
    var list=qs.filter(qLeft).concat(msgs.filter(mLeft));
    return list.sort(function(a,b){ return (a.compareDocumentPosition(b)&Node.DOCUMENT_POSITION_FOLLOWING)?-1:1; });
  }
  function progress(){
    var total=qs.length+msgs.length, left=undecided().length, done=total-left;
    if(barCount){
      var edits=msgs.filter(function(el){ return (S.m[el.dataset.id]||{}).s==='edit'; }).length;
      barCount.innerHTML=left?('還剩 <b>'+left+'</b> 件'+(edits?'，要改 '+edits:'')):('<b>'+total+' 件都看完了</b>'+(edits?'，要改 '+edits:''));
    }
    if(meter) meter.style.width=(total?Math.round(done/total*100):0)+'%';
    $$('.pv-group-count',doc).forEach(function(c){
      var g=c.getAttribute('data-group'), all=msgs.filter(function(el){ return el.dataset.group===g; });
      var d=all.filter(function(el){ return (S.m[el.dataset.id]||{}).s; }).length;
      c.textContent='已審 '+d+'/'+all.length;
    });
    paintToc();
  }
  function jumpTo(target){
    open(target);
    window.scrollTo({top:target.getBoundingClientRect().top+window.scrollY-topGap(),behavior:'smooth'});
  }
  var nextBtn=document.querySelector('[data-next]');
  if(nextBtn) nextBtn.addEventListener('click',function(){
    var list=undecided(); if(!list.length){ toast('都看完了，按「複製結果」貼回對話'); return; }
    var gap=topGap(), target=null;
    for(var i=0;i<list.length;i++){ if(list[i].getBoundingClientRect().top>gap+8){ target=list[i]; break; } }
    jumpTo(target||list[0]);
  });

  /* ---- 浮動目錄 ----
     入口：有進度列就是進度列最左邊的「目錄」鈕，沒有進度列就是右下角浮動鈕。
     點開是浮層（手機是從進度列上方升起的底部抽屜）；點項目跳段，點外面、按 Esc、再點一次都收起。
     不固定左欄、不壓內文寬度；疊在進度列之上、評論工具之下，不蓋住「下一件」。 */
  var toc=null, tocBtn=null, tocItems=[];
  function buildToc(){
    var secs=$$('.pv-sec',doc), list=[];
    if(secs.length){
      secs.forEach(function(sec,i){
        list.push({el:sec,lv:2,n:sec.getAttribute('data-n')||String(i+1),small:sec.getAttribute('data-label')||'',title:txt(sec.querySelector('h2'))});
      });
    }else{
      var hs=$$('.pv-paper h2[id], .pv-paper h3[id]',doc), h2=hs.filter(function(h){ return h.tagName==='H2'; });
      if(hs.length>30 && h2.length>1) hs=h2;
      var k=0;
      hs.forEach(function(h){ var top=h.tagName==='H2'||!h2.length; if(top) k++; list.push({el:h,lv:top?2:3,n:top?String(k):'',small:'',title:txt(h)}); });
    }
    if(list.length<2) return;
    tocItems=list;
    tocBtn=document.createElement('button');
    tocBtn.type='button'; tocBtn.className='pv-tocbtn'; tocBtn.textContent='目錄';
    tocBtn.setAttribute('aria-expanded','false'); tocBtn.setAttribute('aria-controls','pv-toc');
    var holder=hasBar&&bar.querySelector('.pv-bar-in');
    if(holder) holder.insertBefore(tocBtn,holder.firstChild); else { tocBtn.classList.add('is-fab'); body.appendChild(tocBtn); }
    toc=document.createElement('div');
    toc.className='pv-toc'; toc.id='pv-toc'; toc.setAttribute('role','dialog'); toc.setAttribute('aria-label','目錄');
    var head=document.createElement('div'); head.className='pv-toc-head';
    head.innerHTML='<b>目錄</b><span class="pv-toc-sum"></span><button type="button" class="pv-toc-x">收起</button>';
    var ol=document.createElement('ol'); ol.className='pv-toc-list';
    list.forEach(function(it,i){
      var li=document.createElement('li'), a=document.createElement('a');
      a.href='#'+(it.el.id||''); a.setAttribute('data-i',String(i)); if(it.lv===3) a.className='lv3';
      if(it.lv!==3){ var n=document.createElement('span'); n.className='pv-toc-n'; n.textContent=it.n.length<2?('0'+it.n):it.n; a.appendChild(n); }
      var t=document.createElement('span'); t.className='pv-toc-t';
      if(it.small){ var sm=document.createElement('small'); sm.textContent=it.small; t.appendChild(sm); }
      t.appendChild(document.createTextNode(it.title)); a.appendChild(t);
      var s=document.createElement('span'); s.className='pv-toc-s'; a.appendChild(s);
      li.appendChild(a); ol.appendChild(li); it.a=a; it.s=s;
    });
    toc.appendChild(head); toc.appendChild(ol); body.appendChild(toc);
    tocBtn.addEventListener('click',function(e){ e.stopPropagation(); toggleToc(); });
    head.querySelector('.pv-toc-x').addEventListener('click',function(){ toggleToc(false); });
    ol.addEventListener('click',function(e){
      var a=e.target.closest&&e.target.closest('a[data-i]'); if(!a) return;
      e.preventDefault();
      var it=tocItems[+a.getAttribute('data-i')]; toggleToc(false); if(it) jumpTo(it.el);
    });
    document.addEventListener('click',function(e){
      if(!toc.classList.contains('is-on')) return;
      if(toc.contains(e.target)||tocBtn.contains(e.target)) return;
      toggleToc(false);
    });
    document.addEventListener('keydown',function(e){ if(e.key==='Escape'&&toc.classList.contains('is-on')){ toggleToc(false); try{ tocBtn.focus(); }catch(err){} } });
    var ticking=false;
    window.addEventListener('scroll',function(){
      if(!toc.classList.contains('is-on')||ticking) return;
      ticking=true; requestAnimationFrame(function(){ ticking=false; paintToc(); });
    },{passive:true});
    window.addEventListener('resize',function(){ syncBar(); if(toc.classList.contains('is-on')) placeToc(); });
  }
  function placeToc(){
    syncBar();
    toc.style.left=toc.style.right=toc.style.bottom='';
    if(window.matchMedia&&window.matchMedia('(max-width:640px)').matches) return;   /* 手機位置由樣式固定成底部抽屜 */
    var r=tocBtn.getBoundingClientRect(), vw=root.clientWidth, w=toc.offsetWidth||340;
    if(tocBtn.classList.contains('is-fab')){
      toc.style.left='auto'; toc.style.right=Math.max(12,vw-r.right)+'px'; toc.style.bottom=(window.innerHeight-r.top+10)+'px';
    }else{
      toc.style.left=Math.max(12,Math.min(r.left,vw-w-12))+'px';
    }
  }
  function toggleToc(on){
    if(!toc) return;
    var next=typeof on==='boolean'?on:!toc.classList.contains('is-on');
    toc.classList.toggle('is-on',next); tocBtn.setAttribute('aria-expanded',String(next));
    if(next){ paintToc(); placeToc(); var cur=toc.querySelector('a[aria-current="true"]'); if(cur&&cur.scrollIntoView) cur.scrollIntoView({block:'nearest'}); }
  }
  function secStatus(it){
    var q=$$('.pv-q',it.el), m=$$('.pv-msg',it.el), t=$$('input[data-todo]',it.el), left;
    if(q.length&&m.length){ left=q.filter(qLeft).length+m.filter(mLeft).length; return left?['還剩 '+left+' 件','todo']:['看完了','ok']; }
    if(q.length){ left=q.filter(qLeft).length; return left?['要答 '+left+' 題','todo']:['已答','ok']; }
    if(m.length){ left=m.filter(mLeft).length; return left?['還剩 '+left+' 則','todo']:['審完了','ok']; }
    if(t.length){ left=t.filter(function(i){ return !i.checked; }).length; return left?['待辦 '+left+' 件','']:['做完了','ok']; }
    return ['',''];
  }
  function paintToc(){
    if(!toc) return;
    var gap=topGap()+40, cur=0;
    tocItems.forEach(function(it,i){
      if(it.el.getClientRects().length && it.el.getBoundingClientRect().top<=gap) cur=i;
      var st=secStatus(it); it.s.textContent=st[0]; it.s.className='pv-toc-s'+(st[1]?' '+st[1]:'');
    });
    tocItems.forEach(function(it,i){ if(i===cur) it.a.setAttribute('aria-current','true'); else it.a.removeAttribute('aria-current'); });
    var sum=toc.querySelector('.pv-toc-sum'), total=qs.length+msgs.length, left=total?undecided().length:0;
    if(sum) sum.textContent=total?(left?('還剩 '+left+' 件'):'都看完了'):('共 '+tocItems.filter(function(it){ return it.lv===2; }).length+' 段');
  }

  /* ---- 匯出：人看得懂的摘要，加一段給 AI 直接存檔的機器碼 ---- */
  function exportMd(){
    if(!qs.length&&!todos.length&&!msgs.length) return '';   /* 純閱讀的頁沒有作答，不多塞一段空的機器碼 */
    var L=[], j={page:KEY.replace(/__state$/,''),round:ROUND};
    if(qs.length){
      var done=qs.filter(function(q){ return (S.q[q.dataset.q]||[]).length; }).length;
      L.push('## 決定（已答 '+done+'/'+qs.length+' 題）',''); j.questions={};
      qs.forEach(function(q){ var v=S.q[q.dataset.q]||[]; j.questions[q.dataset.q]=v; L.push('- '+q.dataset.title+'：'+(v.length?v.join('；'):'未答')); });
      L.push('');
    }
    if(todos.length){
      var did=todos.filter(function(i){ return i.checked; });
      j.done=did.map(function(i){ return i.getAttribute('data-todo'); });
      if(did.length){ L.push('## 你標記做完的事',''); did.forEach(function(i){ L.push('- '+i.value); }); L.push(''); }
    }
    if(msgs.length){
      var by={pass:[],edit:[],skip:[],'':[]};
      msgs.forEach(function(el){ by[(S.m[el.dataset.id]||{}).s||''].push(el); });
      L.push('## 審稿結果（通過 '+by.pass.length+'、要改 '+by.edit.length+'、不發 '+by.skip.length+'、還沒審 '+by[''].length+(followers.length?'；另有 '+followers.length+' 則只換日期，跟著母稿走':'')+'）','');
      if(by.edit.length){ L.push('### 要改（改完一律再給我看一次才發）'); by.edit.forEach(function(el){ var st=S.m[el.dataset.id]; L.push('- '+el.dataset.label+'：改完再給我看'+(st.note?'｜意見：'+st.note.replace(/\s*\n\s*/g,' '):'')+(+el.dataset.cmt?'｜有 '+el.dataset.cmt+' 則框選評論':'')); }); L.push(''); }
      if(by.skip.length){ L.push('### 不發'); by.skip.forEach(function(el){ L.push('- '+el.dataset.label); }); L.push(''); }
      if(by[''].length){ L.push('### 還沒審（不會發）'); L.push('- 第 '+by[''].map(function(el){ return el.dataset.n; }).join('、')+' 則'); L.push(''); }
      var edit={}; by.edit.forEach(function(el){ var st=S.m[el.dataset.id]; edit[el.dataset.id]={recheck:true,note:st.note||'',comments:+el.dataset.cmt||0}; });
      var follow={}; followers.forEach(function(f){ (follow[f.getAttribute('data-follow')]=follow[f.getAttribute('data-follow')]||[]).push(f.getAttribute('data-id')); });
      j.messages={pass:by.pass.map(id),edit:edit,skip:by.skip.map(id),undecided:by[''].map(id),follow:follow};
    }
    L.push('```pv-decisions',JSON.stringify(j),'```','');
    return L.join('\n');
    function id(el){ return el.dataset.id; }
  }
  window.previewExtraMd=exportMd;
  window.PreviewPage={exportMd:exportMd,state:function(){ return JSON.parse(JSON.stringify(S)); },toc:toggleToc};

  var copyBtn=document.querySelector('[data-copy]');
  if(copyBtn) copyBtn.addEventListener('click',function(){
    scanComments();
    var api=window.PreviewComments||window.PreviewOnline, text;
    try{ text=(api&&api.exportMd)?api.exportMd():''; }catch(e){ text=''; }
    if(!text) text='# 評論彙整：'+TITLE+'\n\n'+exportMd();
    else if(text.indexOf('```pv-decisions')<0) text=exportMd()+'\n'+text;   /* 舊版評論模組沒有匯出掛鉤時，由這裡補在前面 */
    function fail(){ var box=document.querySelector('.pv-fallback'); if(!box) return; toggleToc(false); box.classList.add('is-on'); var ta=box.querySelector('textarea'); ta.value=text; ta.focus(); ta.select(); }
    try{ navigator.clipboard.writeText(text).then(function(){ toast('已複製，貼回對話就好'); },fail); }catch(e){ fail(); }
  });
  var closeFb=document.querySelector('[data-close-fallback]');
  if(closeFb) closeFb.addEventListener('click',function(){ document.querySelector('.pv-fallback').classList.remove('is-on'); });
  var toastEl=document.querySelector('.pv-toast'), toastT;
  function toast(t){ if(!toastEl) return; toastEl.textContent=t; toastEl.classList.add('is-on'); clearTimeout(toastT); toastT=setTimeout(function(){ toastEl.classList.remove('is-on'); },2600); }

  /* ---- 跟框選評論接起來 ----
     1. 在某則訊息裡留了評論，那則自動標成「要改」，不用再按一次。
     2. 點評論要捲過去時，先把收起來的卡或明細打開。 */
  function norm(t){ return String(t||'').replace(/\s+/g,''); }
  function scanComments(){
    var pc=window.PreviewComments||window.PreviewOnline; if(!pc||!pc.data||!msgs.length) return;
    var list; try{ list=pc.data(); }catch(e){ return; }
    var counts={}, texts=msgs.map(function(el){ return norm(el.textContent); });
    list.forEach(function(c){
      var q=norm(c.quote); if(!q) return;
      var hits=[]; texts.forEach(function(t,i){ if(t.indexOf(q)>=0) hits.push(i); });
      if(hits.length>1){
        var b=norm(c.contextBefore||c.context_before).slice(-10), a=norm(c.contextAfter||c.context_after).slice(0,10);
        var better=hits.filter(function(i){ return texts[i].indexOf(b+q)>=0||texts[i].indexOf(q+a)>=0; });
        if(better.length) hits=better;
      }
      if(hits.length){ var id=msgs[hits[0]].dataset.id; counts[id]=(counts[id]||0)+1; }
    });
    var changed=false;
    msgs.forEach(function(el){
      var id=el.dataset.id, n=counts[id]||0, st=S.m[id]||{};
      el.dataset.cmt=n; el.classList.toggle('has-cmt',n>0);
      var chip=el.querySelector('.pv-cmt'); if(chip) chip.textContent='有 '+n+' 則評論';
      if(n>(st.c||0) && st.s!=='skip' && st.s!=='edit'){ mState(id).s='edit'; paintMsg(el); changed=true; }
      if((st.c||0)!==n){ mState(id).c=n; changed=true; }
    });
    if(changed){ save(); progress(); applyFilter(); }
  }
  if(msgs.length) setInterval(scanComments,1500);
  function open(node){
    var el=node&&node.nodeType===3?node.parentNode:node;
    while(el&&el!==document.body){
      if(el.tagName==='DETAILS') el.open=true;
      if(el.classList){
        if(el.classList.contains('is-folded')){ el.classList.remove('is-folded'); paintMsg(el); }
        if(el.classList.contains('pv-hide')) el.classList.remove('pv-hide');
        if(el.classList.contains('pv-lane')) showLane(el.getAttribute('data-lane'));
      }
      el=el.parentNode;
    }
  }
  ['PREVIEW_'+'CONFIG','PREVIEW_ONLINE_'+'CONFIG'].forEach(function(name){
    var cur=window[name];
    if(cur&&typeof cur==='object'){ if(!cur.onBeforeScroll) cur.onBeforeScroll=open; return; }
    var store;
    try{ Object.defineProperty(window,name,{configurable:true,enumerable:true,
      get:function(){ return store; },
      set:function(v){ if(v&&typeof v==='object'&&!v.onBeforeScroll) v.onBeforeScroll=open; store=v; }}); }catch(e){}
  });

  buildToc(); syncBar(); progress(); applyFilter();
  window.addEventListener('load',syncBar);
})();
