(() => {
  "use strict";

  const cfg = window.RACKDASH_CONFIG || {plugins:[], rotateSeconds:30};
  const pluginMeta = cfg.plugins || [];
  const pluginById = Object.fromEntries(pluginMeta.map(p => [p.id,p]));
  const tabPluginIds = pluginMeta.map(p => p.id);
  const pluginIds = pluginMeta.filter(p => p.auto_rotate !== false).map(p => p.id);

  window.RackDashPlugins = window.RackDashPlugins || {};

  const RackDash = window.RackDash = {
    formatNumber(v){ return Number(v||0).toLocaleString(); },
    escape(value){
      return String(value ?? "").replace(/[&<>"']/g, ch => ({
        "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"
      }[ch]));
    },
    duration(sec){
      sec=Math.max(0,Number(sec||0));
      const h=Math.floor(sec/3600), m=Math.floor((sec%3600)/60);
      return h ? `${h}h ${m}m` : `${m}m`;
    },
    uptime(sec){
      sec=Math.max(0,Number(sec||0));
      return `${Math.floor(sec/86400)}d ${Math.floor((sec%86400)/3600)}h ${Math.floor((sec%3600)/60)}m`;
    },
    compact(v){
      v=Number(v||0);
      if(v>=1e12)return`${(v/1e12).toFixed(2)}T`;
      if(v>=1e9)return`${(v/1e9).toFixed(2)}G`;
      if(v>=1e6)return`${(v/1e6).toFixed(2)}M`;
      if(v>=1e3)return`${(v/1e3).toFixed(1)}K`;
      return String(Math.round(v));
    },
    progress(percent){
      const p=Math.max(0,Math.min(100,Number(percent||0)));
      return `<div class="progress-track"><div style="width:${p}%"></div></div>`;
    },
    drawLine(canvas, values, color="#52d273"){
      if(!canvas)return;
      const ctx=canvas.getContext("2d");
      const dpr=Math.min(window.devicePixelRatio||1,2);
      const box=canvas.getBoundingClientRect();
      const cssW=Math.max(1,box.width), cssH=Math.max(1,box.height);
      canvas.width=Math.round(cssW*dpr);canvas.height=Math.round(cssH*dpr);
      ctx.setTransform(dpr,0,0,dpr,0,0);
      const w=cssW,h=cssH;
      ctx.clearRect(0,0,w,h);
      ctx.strokeStyle="#26343d";ctx.lineWidth=1;
      for(let i=1;i<4;i++){const y=i*h/4;ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(w,y);ctx.stroke();}
      if(!values||values.length<2)return;
      const max=Math.max(...values,1),min=Math.min(...values,0),span=Math.max(1,max-min);
      ctx.beginPath();ctx.strokeStyle=color;ctx.lineWidth=2;
      values.forEach((v,i)=>{
        const x=i*w/(values.length-1),y=h-5-(v-min)/span*(h-10);
        i?ctx.lineTo(x,y):ctx.moveTo(x,y);
      });
      ctx.stroke();
    }
  };

  let activeIndex = 0;
  let autoRotate = true;
  let rotateElapsed = 0;
  const lastFetched = new Map();
  const pluginFetches = new Set();
  let logoMode = false;
  let autoScrollTimer=null;
  let autoScrollFrame=null;
  let autoScrollStartedAt=0;
  let autoScrollLastFrame=0;
  let autoScrollInterrupted=false;
  let serverOffline=false;
  let reconnectTimer=null;
  let reconnectCountdownTimer=null;

  const pages = [...document.querySelectorAll(".plugin-page[data-plugin]")];
  const tabs = [...document.querySelectorAll(".tab[data-plugin]")];
  const rotateBox = document.getElementById("autoRotate");
  const healthTab = document.querySelector('[data-health-tab="true"]');
  const healthPage = document.getElementById("health-page");
  let showingHealth = false;
  let healthRefreshTimer=null;


  const LOGO_SESSION_STARTED_KEY="rackdash-logo-session-started";
  const LOGO_AWAKE_AFTER_MS=5*60*1000;
  const LOGO_COMPACT_AFTER_MS=10*60*1000;
  let logoStageTimer=null;
  const LAST_PAGE_KEY="rackdash-last-page";
  const ADMIN_CHECK_AT_KEY="rackdash-admin-update-check-at";
  const ADMIN_CHECK_VERSION_KEY="rackdash-admin-update-check-version";
  let pluginDisplayDirty=false;

  function rememberPage(value){
    try{sessionStorage.setItem(LAST_PAGE_KEY,String(value||""))}catch(_e){}
  }

  function rememberedPage(){
    try{return sessionStorage.getItem(LAST_PAGE_KEY)||""}catch(_e){return ""}
  }

  function markPluginDisplayDirty(active=true){
    pluginDisplayDirty=Boolean(active);
    const button=document.getElementById("pluginDisplaySaveAll");
    if(button){
      button.classList.toggle("has-changes",pluginDisplayDirty);
      button.textContent=pluginDisplayDirty?"SAVE SETTINGS":"SETTINGS SAVED";
    }
  }


  function showConnectionLost(){
    if(serverOffline)return;
    serverOffline=true;
    const overlay=document.getElementById("connectionOverlay");
    if(overlay)overlay.hidden=false;
    scheduleReconnectCheck();
  }

  function clearConnectionLost(){
    const recovered=serverOffline;
    serverOffline=false;
    if(reconnectTimer){clearTimeout(reconnectTimer);reconnectTimer=null;}
    if(reconnectCountdownTimer){clearInterval(reconnectCountdownTimer);reconnectCountdownTimer=null;}
    const overlay=document.getElementById("connectionOverlay");
    if(overlay)overlay.hidden=true;

    // A kiosk or other client may still have the old plugin HTML/CSS/JS in
    // memory after RackDash or a plugin was updated elsewhere. If this page
    // actually lost contact with RackDash and then successfully reconnects,
    // force a cache-busted document reload so it receives the current plugin
    // bundle and core frontend immediately.
    if(recovered){
      freshReload();
    }
  }

  function showApplyOverlay(title="Applying changes",message="RackDash will refresh automatically."){
    const overlay=document.getElementById("applyOverlay");
    const heading=document.getElementById("applyTitle");
    const body=document.getElementById("applyMessage");
    if(heading)heading.textContent=title;
    if(body)body.textContent=message;
    if(overlay)overlay.hidden=false;
  }

  function freshReload(){
    const url=new URL(window.location.href);
    url.searchParams.set("rd_refresh",Date.now().toString());
    window.location.replace(url.toString());
  }

  async function reloadAfterRestart(title="Applying changes"){
    showApplyOverlay(title,"Waiting for RackDash to restart. This page will refresh automatically.");
    // Give the scheduled server exit time to occur, then probe quickly instead
    // of making the user wait for the normal 30-second reconnect cycle.
    await new Promise(resolve=>setTimeout(resolve,1300));
    const started=Date.now();
    while(Date.now()-started<90000){
      try{
        const response=await fetch(`/api/system?apply=${Date.now()}`,{cache:"no-store"});
        if(response.ok){freshReload();return;}
      }catch(e){}
      await new Promise(resolve=>setTimeout(resolve,900));
    }
    showConnectionLost();
  }

  async function restartAndReload(title="Applying changes"){
    const response=await adminFetch("/api/health/restart",{method:"POST"});
    const result=await response.json();
    if(!result.ok)throw new Error(result.error||"Restart failed");
    await reloadAfterRestart(title);
  }

  function reloadAfterFrontendChange(title="Refreshing dashboard"){
    showApplyOverlay(title,"Loading the updated dashboard now.");
    setTimeout(freshReload,220);
  }

  function scheduleReconnectCheck(){
    if(reconnectTimer)clearTimeout(reconnectTimer);
    if(reconnectCountdownTimer)clearInterval(reconnectCountdownTimer);
    let seconds=30;
    const label=document.getElementById("connectionCountdown");
    if(label)label.textContent=`Retrying in ${seconds}s...`;
    reconnectCountdownTimer=setInterval(()=>{
      seconds=Math.max(0,seconds-1);
      if(label)label.textContent=`Retrying in ${seconds}s...`;
    },1000);
    reconnectTimer=setTimeout(async()=>{
      if(reconnectCountdownTimer){clearInterval(reconnectCountdownTimer);reconnectCountdownTimer=null;}
      try{
        const response=await fetch("/api/system",{cache:"no-store"});
        if(response.ok){freshReload();return;}
      }catch(e){}
      scheduleReconnectCheck();
    },30000);
  }

  function setLayoutClass(){
    const root=document.getElementById("rackdash");
    const ratio=window.innerWidth/Math.max(1,window.innerHeight);
    root.classList.remove("layout-ultrawide","layout-wide","layout-standard","layout-portrait");
    if(ratio>=2.3)root.classList.add("layout-ultrawide");
    else if(ratio>=1.5)root.classList.add("layout-wide");
    else if(ratio>=.9)root.classList.add("layout-standard");
    else root.classList.add("layout-portrait");
  }

  async function fetchPlugin(id, force=false){
    const meta=pluginById[id];
    if(!meta)return;
    if(!force && (document.hidden || logoMode))return;
    if(pluginFetches.has(id))return;
    const now=Date.now();
    const due=(meta.refresh_seconds||10)*1000;
    if(!force && now-(lastFetched.get(id)||0)<due)return;

    const root=document.getElementById(`plugin-${id}`);
    const error=root?.querySelector('[data-role="plugin-error"]');
    pluginFetches.add(id);
    try{
      const response=await fetch(`/api/plugin/${encodeURIComponent(id)}`,{cache:"no-store"});
      if(!response.ok && response.status>=500)throw new TypeError("RackDash server error");
      const result=await response.json();
      clearConnectionLost();
      lastFetched.set(id,now);
      if(!result.ok)throw new Error(result.error||"Plugin unavailable");
      if(error)error.hidden=true;
      const renderer=window.RackDashPlugins[id];
      if(renderer&&typeof renderer.render==="function"){
        await renderer.render(result.data,root);
      }
    }catch(err){
      if(err instanceof TypeError)showConnectionLost();
      if(error){
        error.textContent=err.message||"Plugin unavailable";
        error.hidden=false;
      }
    }finally{
      pluginFetches.delete(id);
    }
  }

  let autoScrollVisitToken=0;

  function stopAutoScroll(resetInterruption=false){
    autoScrollVisitToken++;

    if(autoScrollTimer){
      clearTimeout(autoScrollTimer);
      autoScrollTimer=null;
    }
    if(autoScrollFrame){
      cancelAnimationFrame(autoScrollFrame);
      autoScrollFrame=null;
    }

    autoScrollStartedAt=0;
    autoScrollLastFrame=0;

    if(resetInterruption){
      autoScrollInterrupted=false;
    }
  }

  function autoScrollSpeed(distance,rotateFor){
    const remaining=Math.max(6,Number(rotateFor||30)-5);
    return Math.max(
      16,
      Math.min(38,Number(distance||0)/remaining)
    );
  }

  function beginAutoScroll(id,visitToken,retry=0){
    if(
      visitToken!==autoScrollVisitToken||
      autoScrollInterrupted||
      showingHealth||
      logoMode||
      document.hidden||
      tabPluginIds[activeIndex]!==id
    ){
      return;
    }

    const page=pages.find(item=>item.dataset.plugin===id);
    const scroller=page?.querySelector(".plugin-scroll");
    if(!scroller)return;

    const bottom=Math.max(
      0,
      scroller.scrollHeight-scroller.clientHeight
    );

    // Plugins can still be rendering when the five-second delay expires.
    // Retry for up to ten seconds so late content does not permanently skip
    // auto-scroll for this tab visit.
    if(bottom<8){
      if(retry<20){
        autoScrollTimer=setTimeout(()=>{
          autoScrollTimer=null;
          beginAutoScroll(id,visitToken,retry+1);
        },500);
      }
      return;
    }

    const meta=pluginById[id]||{};
    const rotateFor=Math.max(
      3,
      Number(meta.rotation_seconds||cfg.rotateSeconds||30)
    );
    const distance=Math.max(0,bottom-scroller.scrollTop);
    const pixelsPerSecond=autoScrollSpeed(distance,rotateFor);

    autoScrollStartedAt=performance.now();
    autoScrollLastFrame=autoScrollStartedAt;

    const frame=now=>{
      if(
        visitToken!==autoScrollVisitToken||
        autoScrollInterrupted||
        showingHealth||
        logoMode||
        document.hidden||
        tabPluginIds[activeIndex]!==id
      ){
        autoScrollFrame=null;
        return;
      }

      const currentBottom=Math.max(
        0,
        scroller.scrollHeight-scroller.clientHeight
      );

      if(scroller.scrollTop>=currentBottom-1){
        scroller.scrollTop=currentBottom;
        autoScrollFrame=null;
        return;
      }

      const dt=Math.min(
        .05,
        Math.max(0,(now-autoScrollLastFrame)/1000)
      );
      autoScrollLastFrame=now;

      scroller.scrollTop=Math.min(
        currentBottom,
        scroller.scrollTop+pixelsPerSecond*dt
      );

      autoScrollFrame=requestAnimationFrame(frame);
    };

    autoScrollFrame=requestAnimationFrame(frame);
  }

  function scheduleAutoScroll(){
    stopAutoScroll(true);

    if(showingHealth||logoMode||document.hidden)return;

    const id=tabPluginIds[activeIndex];
    const meta=pluginById[id]||{};

    if(meta.auto_scroll!==true)return;

    const visitToken=autoScrollVisitToken;
    const page=pages.find(item=>item.dataset.plugin===id);
    const scroller=page?.querySelector(".plugin-scroll");
    if(!scroller)return;

    // Any deliberate user interaction cancels automatic scrolling until this
    // plugin is visited again.
    const interrupt=()=>{
      if(
        visitToken===autoScrollVisitToken&&
        (autoScrollTimer||autoScrollFrame)
      ){
        autoScrollInterrupted=true;
        stopAutoScroll(false);
      }
    };

    scroller.addEventListener(
      "wheel",
      interrupt,
      {once:true,passive:true}
    );
    scroller.addEventListener(
      "touchstart",
      interrupt,
      {once:true,passive:true}
    );
    scroller.addEventListener(
      "pointerdown",
      interrupt,
      {once:true,passive:true}
    );

    // Required behavior: do nothing for five seconds, then begin scrolling.
    autoScrollTimer=setTimeout(()=>{
      autoScrollTimer=null;
      beginAutoScroll(id,visitToken,0);
    },5000);
  }

  function show(index, userInitiated=false){
    if(!pages.length)return;
    stopAutoScroll(true);
    showingHealth=false;
    if(healthRefreshTimer){clearInterval(healthRefreshTimer);healthRefreshTimer=null;}
    healthPage?.classList.remove("active");
    healthTab?.classList.remove("active");
    healthTab?.setAttribute("aria-selected","false");
    activeIndex=(index+pages.length)%pages.length;
    pages.forEach((p,i)=>p.classList.toggle("active",i===activeIndex));
    tabs.forEach((t,i)=>{
      const active=i===activeIndex;
      t.classList.toggle("active",active);
      t.setAttribute("aria-selected",active?"true":"false");
    });

    const id=tabPluginIds[activeIndex];
    rememberPage(id);
    const meta=pluginById[id];
    if(meta)document.documentElement.style.setProperty("--accent",meta.accent||"#dce8ee");
    tabs[activeIndex]?.scrollIntoView({behavior:"smooth",inline:"center",block:"nearest"});
    pages[activeIndex]?.querySelector(".plugin-scroll")?.scrollTo({top:0,behavior:"auto"});
    fetchPlugin(id,true);

    const renderer=window.RackDashPlugins[id];
    if(renderer&&typeof renderer.onShow==="function")renderer.onShow(pages[activeIndex]);

    rotateElapsed=0;
    scheduleAutoScroll();
    if(userInitiated)scheduleNeighborFetch();
  }



  function formatHealthTime(epoch){
    if(!epoch)return"Never";
    const d=new Date(epoch*1000);
    const diff=Math.max(0,Date.now()-d.getTime());
    if(diff<60000)return`${Math.floor(diff/1000)}s ago`;
    if(diff<3600000)return`${Math.floor(diff/60000)}m ago`;
    if(diff<86400000)return`${Math.floor(diff/3600000)}h ago`;
    return d.toLocaleDateString();
  }

  function healthLabel(h){
    const status=h?.status||"waiting";
    if(status==="healthy")return"Healthy";
    if(status==="error")return"Error";
    if(status==="unconfigured")return"Needs setup";
    if(status==="disabled")return"Disabled";
    return"Waiting";
  }


  function renderWLED(s){
    const st=document.getElementById("wledState"); if(!st)return;
    for(const [id,val] of [["wledEnabled",!!s.enabled],["wledUrl",s.url||"http://wled.local"],["wledSegment",s.segment??0],["wledBrightness",s.brightness??35],["wledBreatheSeconds",s.breathe_seconds??96],["wledBreatheSpread",s.breathe_spread??128],["wledTransitionMs",s.transition_ms??700],["wledTimeout",s.timeout??3]]){const e=document.getElementById(id);if(e){if(e.type==="checkbox")e.checked=val;else e.value=val;}}
    document.getElementById("wledBrightnessValue").textContent=`${s.brightness??35}%`; document.getElementById("wledSpeedValue").textContent=s.breathe_seconds??96; document.getElementById("wledIntensityValue").textContent=s.breathe_spread??128;
    const fx=document.getElementById("wledStatusMode"); if(s.status_mode&&fx){if(![...fx.options].some(o=>o.value===s.status_mode))fx.add(new Option(s.status_mode,s.status_mode));fx.value=s.status_mode;}
    st.textContent=!s.enabled?"DISABLED":s.connected?"CONNECTED":"OFFLINE"; st.className=`wled-state ${s.enabled?(s.connected?"online":"error"):""}`;
    const r=document.getElementById("wledRuntime"); if(r)r.innerHTML=[s.device_name&&`DEVICE ${s.device_name}`,s.version&&`WLED ${s.version}`,s.led_count!=null&&`LEDS ${s.led_count}`,s.max_segments!=null&&`MAX SEGMENTS ${s.max_segments}`,s.rssi!=null&&`RSSI ${s.rssi} dBm`,`SOURCE ${s.active_source||"--"}`,`EFFECT ${s.active_effect||"--"}`,s.last_error?`ERROR ${s.last_error}`:"NO ERRORS"].filter(Boolean).map(x=>`<span>${RackDash.escape(x)}</span>`).join("");
  }
  async function loadWLEDOptions(){const m=document.getElementById("wledMessage");try{const r=await fetch("/api/admin/wled/options",{cache:"no-store"}),d=await r.json();if(!d.ok)throw new Error(d.error||"Could not read WLED");const s=document.getElementById("wledStatusMode"),v=s.value||"Breathe";s.innerHTML="";(d.effects||[]).filter(x=>x&&x!=="RSVD"&&x!=="-").forEach(x=>s.add(new Option(x,x)));if([...s.options].some(o=>o.value===v))s.value=v;else if([...s.options].some(o=>o.value==="Breathe"))s.value="Breathe";if(m)m.textContent=`Loaded ${d.effects?.length||0} effects and ${d.palettes?.length||0} palettes.`;}catch(e){if(m)m.textContent=e.message;}}
  async function loadWLED(){try{const r=await fetch("/api/admin/wled",{cache:"no-store"}),d=await r.json();if(d.ok){renderWLED(d.status||{});if(d.status?.enabled)loadWLEDOptions();}}catch(_e){}}

  let i2cDisplaySpecs={};

  function renderI2C(status){
    const state=document.getElementById("i2cState");
    if(!state)return;
    document.getElementById("i2cEnabled").checked=!!status.enabled;
    document.getElementById("i2cMode").value=status.mode||"system";
    document.getElementById("i2cBus").value=status.bus??1;
    document.getElementById("i2cAddress").value=status.address||"0x3C";
    document.getElementById("i2cRotate").value=status.rotate_seconds??8;
    document.getElementById("i2cContrast").value=status.contrast??255;

    if(!status.enabled){state.textContent="DISABLED";state.className="i2c-state";}
    else if(status.connected){state.textContent="CONNECTED";state.className="i2c-state online";}
    else{state.textContent="ERROR";state.className="i2c-state error";}

    const runtime=document.getElementById("i2cRuntime");
    runtime.innerHTML=[
      `DISPLAY ${status.label||"--"}`,
      `SOURCE ${status.active_source||"--"}`,
      `SIZE ${status.width||"--"}×${status.height||"--"}`,
      status.last_error?`ERROR ${status.last_error}`:"NO ERRORS"
    ].map(x=>`<span>${RackDash.escape(x)}</span>`).join("");
    updateI2CIconLimit();
  }

  async function loadI2C(){
    try{
      const r=await fetch("/api/admin/i2c",{cache:"no-store"});
      const data=await r.json();
      if(!data.ok)return;
      i2cDisplaySpecs=data.displays||{};
      const select=document.getElementById("i2cDisplay");
      const current=data.status?.display||"sh1106_128x64";
      select.innerHTML=Object.entries(i2cDisplaySpecs).map(([key,s])=>
        `<option value="${RackDash.escape(key)}">${RackDash.escape(s.label)}</option>`).join("");
      select.value=current;
      renderI2C(data.status||{});
    }catch(e){}
  }

  function updateI2CIconLimit(){
    const key=document.getElementById("i2cDisplay")?.value;
    const spec=i2cDisplaySpecs[key];
    const label=document.getElementById("i2cIconLimit");
    if(label&&spec)label.textContent=`Maximum upload: ${spec.width}×${spec.height}px. RackDash converts it to monochrome automatically.`;
    const panel=document.getElementById("i2cIconPanel");
    if(panel)panel.style.opacity=document.getElementById("i2cMode")?.value==="icon"?"1":".58";
  }


  async function adminFetch(url,options={}){
    const r=await fetch(url,options);
    if(r.status===401){openAdminAuth();throw new Error("Admin authentication required");}
    return r;
  }

  function renderAdminSecurity(auth){
    const box=document.getElementById("adminSecurityStatus");
    if(!box)return;
    box.innerHTML=[
      `Protection ${auth?.enabled?"ENABLED":"DISABLED"}`,
      `Password ${auth?.configured?"SET":"NOT SET"}`,
      `Session ${auth?.authenticated?"UNLOCKED":"LOCKED"}`
    ].map(x=>`<span>${RackDash.escape(x)}</span>`).join("");
    const check=document.getElementById("adminAuthEnabled");
    if(check)check.checked=!!auth?.enabled;
  }
  function openAdminAuth(){document.getElementById("adminAuthModal").hidden=false;document.getElementById("adminAuthNote").textContent="";}
  function closeAdminAuth(){document.getElementById("adminAuthModal").hidden=true;}
  document.querySelectorAll("[data-close-admin-auth]").forEach(el=>el.addEventListener("click",closeAdminAuth));
  document.getElementById("adminAuthButton")?.addEventListener("click",openAdminAuth);
  document.getElementById("adminAuthLogin")?.addEventListener("click",async()=>{
    const password=document.getElementById("adminPassword").value,note=document.getElementById("adminAuthNote");
    try{const r=await fetch("/api/admin/auth/login",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({password})});const x=await r.json();if(!x.ok)throw new Error(x.error||"Login failed");renderAdminSecurity(x);note.textContent="Admin unlocked.";setTimeout(closeAdminAuth,500);}catch(e){note.textContent=e.message;}
  });
  document.getElementById("adminAuthSave")?.addEventListener("click",async()=>{
    const password=document.getElementById("adminPassword").value,enabled=document.getElementById("adminAuthEnabled").checked,note=document.getElementById("adminAuthNote");
    try{const r=await fetch("/api/admin/auth/config",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({password,enabled})});const x=await r.json();if(!x.ok)throw new Error(x.error||"Save failed");renderAdminSecurity(x);note.textContent="Security settings saved.";}catch(e){note.textContent=e.message;}
  });
  document.getElementById("adminLogoutButton")?.addEventListener("click",async()=>{await fetch("/api/admin/auth/logout",{method:"POST"});await loadHealth();});

  async function rollbackPlugin(id){
    const p=(window.__RackDashHealth?.plugins||[]).find(x=>x.id===id),rows=p?.backups||[];
    if(!rows.length){alert("No plugin backups available.");return;}
    const choice=prompt(`Choose backup number:\n${rows.map((b,i)=>`${i+1}: ${b.name}`).join("\n")}`,"1");
    const selected=rows[Number(choice)-1];if(!selected)return;
    try{const r=await adminFetch(`/api/admin/plugin/${encodeURIComponent(id)}/rollback`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({backup:selected.name})});const x=await r.json();if(!x.ok)throw new Error(x.error||"Rollback failed");await restartAndReload(`Rolling back ${id}`);}catch(e){alert(e.message);}
  }

  async function debugPlugin(id){
    try{const r=await adminFetch(`/api/admin/plugin/${encodeURIComponent(id)}/debug?fetch=1`);const x=await r.json();document.getElementById("platformOutput").textContent=JSON.stringify(x,null,2);}catch(e){}
  }

  function updateCheckedText(timestamp,automatic=false){
    if(!timestamp)return "Never checked";
    const date=new Date(Number(timestamp)*1000);
    return `${automatic?"Automatic":"Manual"} · ${date.toLocaleString()}`;
  }

  function versionParts(value){
    const matches=String(value||"").match(/\d+/g)||[];
    return matches.map(Number);
  }

  function compareVersions(left,right){
    const a=versionParts(left),b=versionParts(right);
    const width=Math.max(a.length,b.length);
    for(let i=0;i<width;i++){
      const av=a[i]||0,bv=b[i]||0;
      if(av<bv)return -1;
      if(av>bv)return 1;
    }
    return 0;
  }

  function reconcilePersistedUpdate(update,currentVersion){
    if(!update||typeof update!=="object")return update||{};
    const latest=update.latest;
    if(
      update.status==="update_available" &&
      latest &&
      currentVersion &&
      compareVersions(currentVersion,latest)>=0
    ){
      return {
        ...update,
        current:currentVersion,
        status:"current",
        message:"Up to date"
      };
    }
    return update;
  }

  let adminUpdateAttention=false;
  let adminIssueAttention=false;

  function refreshAdminAttention(){
    const adminButton=document.querySelector('[data-health-tab="true"]')||document.querySelector(".tab-health");
    if(!adminButton)return;
    adminButton.classList.toggle(
      "admin-attention",
      Boolean(adminUpdateAttention||adminIssueAttention)
    );
    adminButton.classList.toggle(
      "admin-update-attention",
      Boolean(adminUpdateAttention)
    );
  }

  function setAdminUpdateAttention(active){
    adminUpdateAttention=Boolean(active);
    refreshAdminAttention();
  }

  function setAdminIssueAttention(active){
    adminIssueAttention=Boolean(active);
    refreshAdminAttention();
  }

  function releaseNotesHtml(notes){
    if(!notes||!notes.body)return "";
    const body=String(notes.body)
      .replace(/\r/g,"")
      .split("\n")
      .map(line=>line.trim())
      .filter(Boolean)
      .slice(0,18)
      .map(line=>{
        const cleaned=line
          .replace(/^#{1,6}\s*/,"")
          .replace(/^[-*+]\s+/,"• ");
        return RackDash.escape(cleaned);
      })
      .join("<br>");

    const link=notes.url
      ?`<a href="${RackDash.escape(notes.url)}" target="_blank" rel="noopener">VIEW ON GITHUB</a>`
      :"";

    return `
      <div class="release-notes-title">${RackDash.escape(notes.title||"Release notes")}</div>
      <div class="release-notes-body">${body}</div>
      ${link}
    `;
  }

  function renderReleaseNotes(target,notes){
    if(!target)return;
    const html=releaseNotesHtml(notes);
    target.innerHTML=html;
    target.hidden=!html;
  }


  function renderPersistedUpdates(data){
    const updates=data.updates||{};
    const settings=updates.settings||{};
    const core=updates.core||{};

    const automaticUpdates=document.getElementById("automaticUpdateCheck");
    if(automaticUpdates){
      automaticUpdates.checked=!!settings.core_daily&&!!settings.plugins_daily;
    }

    if(core.ok&&core.result){
      const loadedVersion=data.app?.version||core.result.current||"";
      const u=reconcilePersistedUpdate(core.result,loadedVersion);
      const current=document.querySelector('[data-rackdash-update="current"]');
      const latest=document.querySelector('[data-rackdash-update="latest"]');
      const status=document.querySelector('[data-rackdash-update="status"]');
      if(current)current.textContent=`v${loadedVersion||u.current||"--"}`;
      if(latest)latest.textContent=u.latest||"NO RELEASE/TAG";
      if(status){
        status.textContent=(u.status||"unknown").replaceAll("_"," ").toUpperCase();
        status.className=u.status||"";
      }
      const message=document.getElementById("rackdashUpdateMessage");
      if(message)message.textContent=u.message||"Update status unavailable.";
      renderReleaseNotes(
        document.getElementById("rackdashReleaseNotes"),
        u.status==="update_available"?u.release_notes:null
      );
    }else if(core.checked_at){
      const status=document.querySelector('[data-rackdash-update="status"]');
      if(status){
        status.textContent="ERROR";
        status.className="error";
      }
    }

    let available=0;
    for(const plugin of data.plugins||[]){
      const saved=plugin.update_status||{};
      const row=document.querySelector(
        `[data-health-plugin="${CSS.escape(plugin.id)}"]`
      );
      const status=row?.querySelector("[data-update-status]");
      if(saved.ok&&saved.result&&status){
        const u=reconcilePersistedUpdate(
          saved.result,
          plugin.version||saved.result.current||""
        );
        status.textContent=u.message||"Unknown";
        status.className=`health-update-status ${u.status||""}`;
        renderReleaseNotes(
          row?.querySelector("[data-release-notes]"),
          u.status==="update_available"?u.release_notes:null
        );
        if(u.status==="update_available")available++;
      }else if(saved.checked_at&&status){
        status.textContent=saved.error||"Check failed";
        status.className="health-update-status error";
      }
    }

    const updateCount=document.querySelector('[data-health="updates"]');
    if(updateCount)updateCount.textContent=String(available);

    const last=document.getElementById("updateLastCheck");
    if(last){
      last.textContent=
        `RackDash: ${updateCheckedText(core.checked_at,core.automatic)} · `+
        `Plugins: ${updateCheckedText(
          updates.plugin_batch_checked_at,
          updates.plugin_batch_automatic
        )}`;
    }
  }

  async function savePluginOrder(list){
    const plugin_ids=[...list.querySelectorAll(".health-plugin-row[data-health-plugin]")]
      .map(row=>row.dataset.healthPlugin)
      .filter(Boolean);

    const response=await adminFetch("/api/admin/plugins/order",{
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({plugin_ids})
    });
    const result=await response.json();
    if(!result.ok)throw new Error(result.error||"Unable to save plugin order");
    return result;
  }

  function setupPluginDragOrder(list){
    if(!list)return;

    let dragging=null;
    let pointerId=null;
    let moved=false;

    const placeAtPointer=(clientY)=>{
      if(!dragging)return;
      const rows=[...list.querySelectorAll(".health-plugin-row")]
        .filter(row=>row!==dragging);

      let target=null;
      for(const row of rows){
        const box=row.getBoundingClientRect();
        if(clientY < box.top + box.height/2){
          target=row;
          break;
        }
      }

      if(target){
        if(target!==dragging.nextElementSibling){
          list.insertBefore(dragging,target);
          moved=true;
        }
      }else if(list.lastElementChild!==dragging){
        list.appendChild(dragging);
        moved=true;
      }
    };

    list.querySelectorAll("[data-plugin-drag]").forEach(handle=>{
      handle.addEventListener("pointerdown",event=>{
        if(event.button!==undefined&&event.button!==0)return;
        const row=handle.closest(".health-plugin-row");
        if(!row)return;
        dragging=row;
        pointerId=event.pointerId;
        moved=false;
        row.classList.add("is-dragging");
        list.classList.add("is-reordering");
        handle.setPointerCapture?.(pointerId);
        event.preventDefault();
      });

      handle.addEventListener("pointermove",event=>{
        if(!dragging||event.pointerId!==pointerId)return;
        placeAtPointer(event.clientY);
        event.preventDefault();
      });

      const finish=async event=>{
        if(!dragging||event.pointerId!==pointerId)return;
        const row=dragging;
        dragging=null;
        pointerId=null;
        row.classList.remove("is-dragging");
        list.classList.remove("is-reordering");

        if(!moved)return;

        markPluginDisplayDirty(true);
      };

      handle.addEventListener("pointerup",finish);
      handle.addEventListener("pointercancel",finish);
    });
  }

  async function loadHealth(){
    if(!healthPage)return;
    try{
      const response=await fetch("/api/health",{cache:"no-store"});
      const data=await response.json();
      window.__RackDashHealth=data;
      healthPage.querySelector('[data-health="app-version"]').textContent=data.app?.version||"--";
      healthPage.querySelector('[data-health="plugin-count"]').textContent=data.app?.plugin_discovered_count??data.app?.plugin_count??"--";
      healthPage.querySelector('[data-health="status"]').textContent="OK";
      const healthyCount=(data.plugins||[]).filter(p=>p.health?.status==="healthy").length;
      const failedPlugins=data.plugin_failures||[];
      const issueCount=(data.plugins||[]).filter(p=>["error","unconfigured"].includes(p.health?.status)).length+failedPlugins.length;
      healthPage.querySelector('[data-health="healthy-count"]').textContent=String(healthyCount);
      healthPage.querySelector('[data-health="issue-count"]').textContent=String(issueCount);
      healthPage.querySelector('[data-health="status"]').textContent=issueCount?"ATTENTION":"OK";

      const coreUpdateRaw=(data.updates?.core?.ok&&data.updates?.core?.result)
        ?data.updates.core.result
        :null;
      const coreUpdate=coreUpdateRaw
        ?reconcilePersistedUpdate(coreUpdateRaw,data.app?.version||coreUpdateRaw.current||"")
        :null;

      const pluginUpdateRows=data.updates?.plugins||{};
      const pluginUpdatesAvailable=(data.plugins||[]).some(plugin=>{
        const saved=pluginUpdateRows[plugin.id];
        if(!saved?.ok||!saved.result)return false;
        const reconciled=reconcilePersistedUpdate(
          saved.result,
          plugin.version||saved.result.current||""
        );
        return reconciled.status==="update_available";
      });

      setAdminIssueAttention(issueCount>0);
      setAdminUpdateAttention(
        coreUpdate?.status==="update_available" ||
        pluginUpdatesAvailable
      );

      const failedPanel=document.getElementById("failedPluginPanel");
      const failedList=document.getElementById("failedPluginList");
      const failedCount=document.getElementById("failedPluginCount");
      if(failedPanel&&failedList&&failedCount){
        failedPanel.hidden=!failedPlugins.length;
        failedCount.textContent=`${failedPlugins.length} FAILED`;
        failedList.innerHTML=failedPlugins.map(f=>`
          <div class="failed-plugin-row">
            <div class="failed-plugin-main">
              <div class="failed-plugin-name"><span class="health-dot error"></span>${RackDash.escape(f.filename||"Unknown plugin")}</div>
              <div class="failed-plugin-meta">
                <span>STAGE <b>${RackDash.escape((f.stage||"load").toUpperCase())}</b></span>
                <span>TYPE <b>${RackDash.escape(f.error_type||"Error")}</b></span>
              </div>
              <div class="failed-plugin-error">${RackDash.escape(f.error||"Plugin failed to load")}</div>
            </div>
            <div class="failed-plugin-badge">QUARANTINED</div>
          </div>
        `).join("");
      }

      const list=document.getElementById("healthPluginList");
      list.innerHTML=(data.plugins||[]).map(p=>`
        <div class="health-plugin-row" data-health-plugin="${RackDash.escape(p.id)}">
          <button
            type="button"
            class="plugin-drag-handle"
            data-plugin-drag="${RackDash.escape(p.id)}"
            aria-label="Drag ${RackDash.escape(p.name)} to reorder"
            title="Drag to reorder"
          ><span></span><span></span><span></span></button>

          <div class="plugin-admin-identity">
            <div class="health-plugin-name"><span class="health-dot ${RackDash.escape(p.health?.status||"waiting")}"></span>${RackDash.escape(p.name)}</div>
            <div class="health-plugin-id">${RackDash.escape(p.id)}</div>
            <div class="health-runtime">
              <span>STATE <b>${RackDash.escape(healthLabel(p.health))}</b></span>
              <span>LATENCY <b>${p.health?.response_ms!=null?`${Number(p.health.response_ms).toFixed(0)} ms`:"--"}</b></span>
              <span>LAST OK <b>${RackDash.escape(formatHealthTime(p.health?.last_success))}</b></span>
              <span>LAST POLL <b>${RackDash.escape(formatHealthTime(p.health?.last_attempt))}</b></span>
              ${p.health?.last_error?`<span class="health-runtime-error">LAST ERROR · ${RackDash.escape(p.health.last_error)}</span>`:""}
              ${p.health?.missing_config?.length?`<span class="health-runtime-error">MISSING CONFIG · ${RackDash.escape(p.health.missing_config.join(", "))}</span>`:""}
            </div>
          </div>

          <div class="plugin-admin-version">
            <span class="admin-field-label">VERSION</span>
            <div class="health-version">v${RackDash.escape(p.version||"0.0.0")}${p.official?` <span class="official-chip">OFFICIAL</span>`:""}</div>
          </div>

          <div class="plugin-admin-update">
            <span class="admin-field-label">UPDATE STATUS</span>
            <div class="health-update-status" data-update-status>Not checked</div>
            <div class="health-release-notes" data-release-notes hidden></div>
          </div>

          <div class="health-plugin-actions">
            <label class="health-toggle"><input type="checkbox" data-plugin-enabled="${RackDash.escape(p.id)}" ${p.enabled?"checked":""}> ENABLED</label>
            ${(p.config_fields||[]).length?`<button type="button" data-plugin-settings="${RackDash.escape(p.id)}">SETTINGS</button>`:""}
            <button type="button" class="test-button" data-plugin-test="${RackDash.escape(p.id)}" ${p.enabled?"":"disabled"}>TEST</button>
            ${p.github_url?`<a href="${RackDash.escape(p.official&&p.source_path?`${p.github_url}/blob/main/${p.source_path}`:p.github_url)}" target="_blank" rel="noopener">GITHUB</a>`:""}
            <button type="button" data-check-update="${RackDash.escape(p.id)}" ${p.github_url?"":"disabled"}>CHECK</button>
            ${p.official?`<button type="button" data-official-update="${RackDash.escape(p.id)}">UPDATE OFFICIAL</button>`:""}${p.installer_managed&&!p.official?`<button type="button" data-managed-update="${RackDash.escape(p.id)}">UPDATE</button><button type="button" data-uninstall-plugin="${RackDash.escape(p.id)}">UNINSTALL</button>`:""}
            ${(p.backups||[]).length?`<button type="button" data-plugin-rollback="${RackDash.escape(p.id)}">ROLLBACK</button>`:""}
            <button type="button" data-plugin-debug="${RackDash.escape(p.id)}">DEBUG</button>
            <button type="button" data-plugin-reload="${RackDash.escape(p.id)}">RELOAD</button>
          </div>

          <div class="plugin-display-controls">
            <label><span>REFRESH</span><input type="number" min="1" data-display-refresh="${RackDash.escape(p.id)}" value="${p.display?.refresh_seconds??p.refresh_seconds??10}"></label>
            <label><span>ROTATE</span><input type="number" min="3" data-display-duration="${RackDash.escape(p.id)}" value="${p.display?.rotation_seconds??30}"></label>
            <label class="plugin-display-check"><input type="checkbox" data-display-tab="${RackDash.escape(p.id)}" ${p.display?.show_tab!==false?"checked":""}><span>TAB</span></label>
            <label class="plugin-display-check"><input type="checkbox" data-display-auto="${RackDash.escape(p.id)}" ${p.display?.auto_rotate!==false?"checked":""}><span>AUTO</span></label>
            <label class="plugin-display-check"><input type="checkbox" data-display-scroll="${RackDash.escape(p.id)}" ${p.display?.auto_scroll===true?"checked":""}><span>AUTO SCROLL</span></label>
          </div>

          <div class="plugin-capabilities">${(p.capabilities||[]).map(c=>`<span class="capability-chip">${RackDash.escape(c)}</span>`).join("")}</div>
        </div>`).join("");

      list.querySelectorAll("[data-plugin-settings]").forEach(btn=>btn.addEventListener("click",()=>{const p=(window.__RackDashHealth?.plugins||[]).find(x=>x.id===btn.dataset.pluginSettings);if(p)openSettings(`${p.name} Settings`,p.config_fields||[],`/api/health/plugin/${encodeURIComponent(p.id)}/config`);}));
      list.querySelectorAll("[data-plugin-enabled]").forEach(toggle=>toggle.addEventListener("change",async()=>{
        try{
          const r=await adminFetch(`/api/health/plugin/${encodeURIComponent(toggle.dataset.pluginEnabled)}/enabled`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({enabled:toggle.checked})});
          const x=await r.json();
          if(!x.ok)throw new Error(x.error||"Unable to change plugin state");
          reloadAfterFrontendChange("Updating plugin visibility");
        }catch(e){toggle.checked=!toggle.checked;alert(e.message);}
      }));
      list.querySelectorAll(
        "[data-display-refresh],[data-display-duration],[data-display-tab],[data-display-auto],[data-display-scroll]"
      ).forEach(control=>{
        control.addEventListener("change",()=>markPluginDisplayDirty(true));
        control.addEventListener("input",()=>markPluginDisplayDirty(true));
      });
      setupPluginDragOrder(list);
      list.querySelectorAll("[data-plugin-rollback]").forEach(btn=>btn.addEventListener("click",()=>rollbackPlugin(btn.dataset.pluginRollback)));
      list.querySelectorAll("[data-plugin-debug]").forEach(btn=>btn.addEventListener("click",()=>debugPlugin(btn.dataset.pluginDebug)));
      list.querySelectorAll("[data-plugin-reload]").forEach(btn=>btn.addEventListener("click",async()=>{
        const id=btn.dataset.pluginReload;
        try{
          const r=await adminFetch(`/api/admin/plugin/${encodeURIComponent(id)}/reload`,{method:"POST"});
          const x=await r.json();
          if(!x.ok)throw new Error(x.error||"Reload failed");
          if(x.plugin?.restart_required){
            await restartAndReload(`Reloading ${x.plugin.name}`);
          }else{
            reloadAfterFrontendChange(`Reloaded ${x.plugin.name}`);
          }
        }catch(e){alert(e.message);}
      }));
      list.querySelectorAll("[data-plugin-test]").forEach(btn=>btn.addEventListener("click",async()=>{
        btn.disabled=true;
        const original=btn.textContent;
        btn.textContent="TESTING...";
        try{
          await fetch(`/api/health/plugin/${encodeURIComponent(btn.dataset.pluginTest)}/test`,{method:"POST"});
          await loadHealth();
        }finally{
          btn.disabled=false;
          btn.textContent=original;
        }
      }));
      list.querySelectorAll("[data-official-update]").forEach(btn=>btn.addEventListener("click",()=>officialPluginUpdate(btn.dataset.officialUpdate,btn)));
      list.querySelectorAll("[data-managed-update]").forEach(btn=>btn.addEventListener("click",()=>managedPluginUpdate(btn.dataset.managedUpdate,btn)));
      list.querySelectorAll("[data-uninstall-plugin]").forEach(btn=>btn.addEventListener("click",()=>uninstallPlugin(btn.dataset.uninstallPlugin,btn)));
      list.querySelectorAll("[data-check-update]").forEach(btn=>{
        btn.addEventListener("click",()=>checkPluginUpdate(btn.dataset.checkUpdate,btn));
      });
      renderI2C(data.i2c||{});renderAdminSecurity(data.admin_auth||{});
      renderPersistedUpdates(data);
      markPluginDisplayDirty(false);
      await loadWLED();
      if(!Object.keys(i2cDisplaySpecs).length)await loadI2C();
    }catch(e){
      healthPage.querySelector('[data-health="status"]').textContent="ERROR";
    }
  }

  async function checkPluginUpdate(id,button=null){
    const row=document.querySelector(`[data-health-plugin="${CSS.escape(id)}"]`);
    const status=row?.querySelector("[data-update-status]");
    if(button)button.disabled=true;
    if(status){status.textContent="Checking...";status.className="health-update-status";}
    try{
      const response=await fetch(`/api/health/plugin/${encodeURIComponent(id)}/update`,{cache:"no-store"});
      const result=await response.json();
      if(!result.ok)throw new Error(result.error||"Update check failed");
      const u=result.update||{};
      if(status){
        status.textContent=u.message||"Unknown";
        status.className=`health-update-status ${u.status||""}`;
      }
      renderReleaseNotes(
        row?.querySelector("[data-release-notes]"),
        u.status==="update_available"?u.release_notes:null
      );
      if(data.update_attention)setAdminUpdateAttention(!!data.update_attention.available);else if(result.update_attention)setAdminUpdateAttention(!!result.update_attention.available);else if(u.status==="update_available")setAdminUpdateAttention(true);
      refreshHealthUpdateCount();
    }catch(e){
      if(status){status.textContent="Check failed";status.className="health-update-status error";}
    }finally{
      if(button)button.disabled=false;
    }
  }


  let settingsEndpoint=null;
  function fieldHtml(field){
    const type=field.type||"text",key=RackDash.escape(field.key||""),label=RackDash.escape(field.label||field.key||"Setting"),help=RackDash.escape(field.help||""),value=field.value??field.default??"";
    if(type==="select"){const options=(field.options||[]).map(o=>{const ov=typeof o==="string"?o:o.value,ol=typeof o==="string"?o:(o.label??o.value);return `<option value="${RackDash.escape(ov)}" ${String(ov)===String(value)?"selected":""}>${RackDash.escape(ol)}</option>`}).join("");return `<div class="settings-field"><label>${label}</label><select data-setting-key="${key}">${options}</select>${help?`<small>${help}</small>`:""}</div>`;}
    if(type==="checkbox"){const checked=["1","true","yes","on"].includes(String(value).toLowerCase());return `<div class="settings-field"><label>${label}</label><label class="settings-checkbox"><input type="checkbox" data-setting-key="${key}" ${checked?"checked":""}> Enabled</label>${help?`<small>${help}</small>`:""}</div>`;}
    const htmlType=["password","token","secret"].includes(type)?"password":(type==="number"?"number":"text");
    return `<div class="settings-field"><label>${label}</label><input type="${htmlType}" data-setting-key="${key}" value="${RackDash.escape(value)}">${help?`<small>${help}</small>`:""}</div>`;
  }
  function openSettings(title,fields,endpoint){settingsEndpoint=endpoint;document.getElementById("settingsTitle").textContent=title;document.getElementById("settingsFields").innerHTML=(fields||[]).map(fieldHtml).join("")||`<div class="muted">No configurable settings.</div>`;document.getElementById("settingsNote").textContent="";document.getElementById("settingsModal").hidden=false;}
  function closeSettings(){document.getElementById("settingsModal").hidden=true;settingsEndpoint=null;}
  document.querySelectorAll("[data-close-settings]").forEach(el=>el.addEventListener("click",closeSettings));

  async function checkRackDashUpdate(){
    const button=document.getElementById("rackdashUpdateCheck");
    const current=document.querySelector('[data-rackdash-update="current"]');
    const latest=document.querySelector('[data-rackdash-update="latest"]');
    const status=document.querySelector('[data-rackdash-update="status"]');
    const message=document.getElementById("rackdashUpdateMessage");
    if(button){button.disabled=true;button.textContent="CHECKING...";}
    if(status){status.textContent="CHECKING";status.className="";}
    if(message)message.textContent="Contacting GitHub...";
    try{
      const response=await fetch("/api/health/rackdash/update",{cache:"no-store"});
      const data=await response.json();
      if(!data.ok)throw new Error(data.error||"Update check failed");
      const u=data.update||{};
      if(current)current.textContent=`v${data.current||"--"}`;
      if(latest)latest.textContent=u.latest||"NO RELEASE/TAG";
      if(status){
        status.textContent=(u.status||"unknown").replaceAll("_"," ").toUpperCase();
        status.className=u.status||"";
      }
      if(message)message.textContent=u.message||"Update status unavailable.";
      renderReleaseNotes(document.getElementById("rackdashReleaseNotes"),u.status==="update_available"?u.release_notes:null);
      if(u.status==="update_available")setAdminUpdateAttention(true);
      const last=document.getElementById("updateLastCheck");
      if(last){
        const pluginBatch=window.__RackDashHealth?.updates||{};
        last.textContent=
          `RackDash: ${updateCheckedText(data.checked_at,false)} · `+
          `Plugins: ${updateCheckedText(
            pluginBatch.plugin_batch_checked_at,
            pluginBatch.plugin_batch_automatic
          )}`;
      }
    }catch(e){
      if(status){status.textContent="ERROR";status.className="error";}
      if(message)message.textContent=e.message;
    }finally{
      if(button){button.disabled=false;button.textContent="CHECK RACKDASH UPDATE";}
    }
  }

  document.getElementById("rackdashUpdateCheck")?.addEventListener("click",checkRackDashUpdate);


  document.getElementById("backupDownload")?.addEventListener("click",async()=>{
    try{const r=await adminFetch("/api/admin/backup");if(!r.ok)throw new Error("Backup failed");const blob=await r.blob();const a=document.createElement("a");a.href=URL.createObjectURL(blob);a.download="rackdash-backup.zip";a.click();URL.revokeObjectURL(a.href);}catch(e){alert(e.message);}
  });
  document.getElementById("backupRestore")?.addEventListener("click",async()=>{
    const file=document.getElementById("backupRestoreFile").files?.[0];if(!file){alert("Choose a backup zip.");return;}
    if(!confirm("Restore this backup? Current config and plugins may be overwritten."))return;
    const body=new FormData();body.append("backup",file);
    try{const r=await adminFetch("/api/admin/restore",{method:"POST",body});const x=await r.json();alert(x.ok?"Backup restored. Restart RackDash.":x.error);}catch(e){}
  });
  document.getElementById("adminDiagnostics")?.addEventListener("click",async()=>{
    const r=await fetch("/api/admin/diagnostics");const x=await r.json();x.browser={width:innerWidth,height:innerHeight,dpr:devicePixelRatio,userAgent:navigator.userAgent};document.getElementById("platformOutput").textContent=JSON.stringify(x,null,2);
  });
  document.getElementById("adminLogs")?.addEventListener("click",async()=>{
    try{const r=await adminFetch("/api/admin/logs?lines=300");const x=await r.json();document.getElementById("platformOutput").textContent=(x.lines||[]).join("\\n");}catch(e){}
  });
  document.getElementById("saveUpdateCheckSettings")?.addEventListener("click",async()=>{
    const button=document.getElementById("saveUpdateCheckSettings");
    const message=document.getElementById("rackdashUpdateMessage");
    button.disabled=true;
    try{
      const response=await adminFetch("/api/admin/update-settings",{
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify({
          core_daily:!!document.getElementById("automaticUpdateCheck")?.checked,
          plugins_daily:!!document.getElementById("automaticUpdateCheck")?.checked
        })
      });
      const result=await response.json();
      if(!result.ok)throw new Error(
        result.error||"Unable to save update settings"
      );
      message.textContent=
        result.settings.core_daily&&result.settings.plugins_daily
          ?"Automatic update checks enabled. RackDash will check the core and supported plugins every 30 minutes."
          :"Automatic update checks disabled. Manual update checks remain available.";
    }catch(error){
      message.textContent=error.message;
    }finally{
      button.disabled=false;
    }
  });

  document.getElementById("rackdashUpdateNow")?.addEventListener("click",async()=>{
    if(!confirm("Download and install the latest RackDash GitHub release? A backup will be created first."))return;
    try{const r=await adminFetch("/api/admin/core/update",{method:"POST"});const x=await r.json();if(!x.ok)throw new Error(x.error||"Update failed");document.getElementById("rackdashUpdateMessage").textContent=`Installed ${x.update.version}. Restarting...`;await reloadAfterRestart(`Updating RackDash to ${x.update.version}`);}catch(e){document.getElementById("rackdashUpdateMessage").textContent=e.message;}
  });

  document.getElementById("healthRestart")?.addEventListener("click",async()=>{
    if(!confirm("Restart the RackDash server now?"))return;
    const button=document.getElementById("healthRestart");
    button.disabled=true;
    button.textContent="RESTARTING...";
    try{
      const response=await adminFetch("/api/health/restart",{method:"POST"});
      const result=await response.json();
      if(!result.ok)throw new Error(result.error||"Restart failed");
      await reloadAfterRestart("Restarting RackDash");
    }catch(e){
      button.disabled=false;
      button.textContent="RESTART";
      alert(e.message||"Restart failed");
    }
  });

  document.getElementById("healthCoreSettings")?.addEventListener("click",()=>openSettings("RackDash Core Settings",window.__RackDashHealth?.app?.config_fields||[],"/api/health/core/config"));
  async function saveSettings(restart=false){
    if(!settingsEndpoint)return;
    const values={};
    document.querySelectorAll("#settingsFields [data-setting-key]").forEach(el=>values[el.dataset.settingKey]=el.type==="checkbox"?(el.checked?"true":"false"):el.value);
    const note=document.getElementById("settingsNote");note.textContent=restart?"Saving and restarting...":"Saving...";
    try{
      const r=await adminFetch(settingsEndpoint,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({values,restart})});
      const result=await r.json();if(!result.ok)throw new Error(result.error||"Save failed");
      if(restart){
        note.textContent="Saved. Applying changes...";
        closeSettings();
        await reloadAfterRestart("Applying settings");
      }else{
        note.textContent="Saved to config.env. Use SAVE & APPLY when you want the running dashboard updated.";
      }
    }catch(e){note.textContent=e.message;}
  }
  document.getElementById("settingsSave")?.addEventListener("click",()=>saveSettings(false));
  document.getElementById("settingsSaveRestart")?.addEventListener("click",()=>saveSettings(true));

  async function officialPluginUpdate(id,button){
    if(!confirm(`Update official RackDash plugin '${id}' from the main/plugins source file? A rollback backup will be kept.`))return;
    button.disabled=true;
    const st=button.closest(".health-plugin-row")?.querySelector("[data-update-status]");
    if(st)st.textContent="Downloading official plugin...";
    try{
      const r=await adminFetch(`/api/health/plugin/${encodeURIComponent(id)}/update-official`,{method:"POST"});
      const x=await r.json();
      if(!x.ok)throw new Error(x.error||"Official update failed");
      if(st){
        st.textContent=`Installed official v${x.plugin.version}. Applying...`;
        st.className="health-update-status current";
      }
      await restartAndReload(`Updating ${id} to v${x.plugin.version}`);
    }catch(e){
      if(st){st.textContent=e.message;st.className="health-update-status error";}
    }finally{button.disabled=false;}
  }

  async function managedPluginUpdate(id,button){button.disabled=true;const st=button.closest(".health-plugin-row")?.querySelector("[data-update-status]");if(st)st.textContent="Updating...";try{const r=await adminFetch(`/api/health/plugin/${encodeURIComponent(id)}/update-managed`,{method:"POST"});const x=await r.json();if(!x.ok)throw new Error(x.error||"Update failed");if(st){st.textContent=`Installed ${x.plugin.version}. Applying...`;st.className="health-update-status current";}await restartAndReload(`Updating ${id} to ${x.plugin.version}`);}catch(e){if(st){st.textContent=e.message;st.className="health-update-status error";}}finally{button.disabled=false;}}
  async function uninstallPlugin(id,button){if(!confirm(`Uninstall ${id}? A backup will be kept.`))return;button.disabled=true;const st=button.closest(".health-plugin-row")?.querySelector("[data-update-status]");try{const r=await adminFetch(`/api/health/plugin/${encodeURIComponent(id)}/uninstall`,{method:"POST"});const x=await r.json();if(!x.ok)throw new Error(x.error||"Uninstall failed");if(st){st.textContent="Uninstalled. Applying...";st.className="health-update-status current";}await restartAndReload(`Removing ${id}`);}catch(e){if(st){st.textContent=e.message;st.className="health-update-status error";}}finally{button.disabled=false;}}

  function refreshHealthUpdateCount(){
    const count=document.querySelectorAll(".health-update-status.update_available").length;
    const target=document.querySelector('[data-health="updates"]');
    if(target)target.textContent=String(count);
  }

  async function saveAllPluginDisplaySettings(){
    const list=document.getElementById("healthPluginList");
    const button=document.getElementById("pluginDisplaySaveAll");
    if(!list||!button)return;

    const plugin_ids=[...list.querySelectorAll(".health-plugin-row[data-health-plugin]")]
      .map(row=>row.dataset.healthPlugin)
      .filter(Boolean);

    const pluginsPayload={};
    plugin_ids.forEach(id=>{
      const escaped=CSS.escape(id);
      pluginsPayload[id]={
        refresh_seconds:Number(list.querySelector(`[data-display-refresh="${escaped}"]`)?.value||10),
        rotation_seconds:Number(list.querySelector(`[data-display-duration="${escaped}"]`)?.value||30),
        show_tab:!!list.querySelector(`[data-display-tab="${escaped}"]`)?.checked,
        auto_rotate:!!list.querySelector(`[data-display-auto="${escaped}"]`)?.checked,
        auto_scroll:!!list.querySelector(`[data-display-scroll="${escaped}"]`)?.checked
      };
    });

    button.disabled=true;
    button.textContent="SAVING...";
    try{
      const response=await adminFetch("/api/admin/plugins/display-settings",{
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify({
          plugin_ids,
          plugins:pluginsPayload
        })
      });
      const result=await response.json();
      if(!result.ok)throw new Error(result.error||"Unable to save plugin settings");
      markPluginDisplayDirty(false);
      rememberPage("admin");
      reloadAfterFrontendChange("Applying plugin settings");
    }catch(error){
      alert(error.message);
      button.disabled=false;
      markPluginDisplayDirty(true);
    }
  }

  document.getElementById("pluginDisplaySaveAll")?.addEventListener(
    "click",
    saveAllPluginDisplaySettings
  );


  async function refreshUpdatesOnAdminOpen(force=false){
    const now=Date.now();
    let lastAt=0;
    let lastVersion="";
    try{
      lastAt=Number(sessionStorage.getItem(ADMIN_CHECK_AT_KEY)||0);
      lastVersion=sessionStorage.getItem(ADMIN_CHECK_VERSION_KEY)||"";
    }catch(_e){}

    const version=String(cfg.appVersion||"");
    const versionChanged=version&&lastVersion!==version;
    if(!force&&!versionChanged&&now-lastAt<60000)return;

    try{
      const response=await adminFetch(
        "/api/admin/plugin-updates/check-all",
        {method:"POST"}
      );
      const result=await response.json();
      if(!result.ok)throw new Error(result.error||"Update check failed");
      try{
        sessionStorage.setItem(ADMIN_CHECK_AT_KEY,String(Date.now()));
        sessionStorage.setItem(ADMIN_CHECK_VERSION_KEY,version);
      }catch(_e){}
      await loadHealth();
    }catch(error){
      // Admin content is still usable if GitHub is unavailable.
      console.warn("Admin update refresh failed:",error);
    }
  }


  async function showHealth(){
    stopAutoScroll(true);
    showingHealth=true;
    rememberPage("admin");
    pages.forEach(p=>p.classList.remove("active"));
    tabs.forEach(t=>{
      t.classList.remove("active");
      t.setAttribute("aria-selected","false");
    });
    healthPage?.classList.add("active");
    healthTab?.classList.add("active");
    healthTab?.setAttribute("aria-selected","true");
    document.documentElement.style.setProperty("--accent","#9aa9b2");
    rotateElapsed=0;
    await loadHealth();
    refreshUpdatesOnAdminOpen(false);
  }

  function scheduleNeighborFetch(){
    if(pluginIds.length<2 || document.hidden || logoMode)return;
    const next=tabPluginIds[(activeIndex+1)%tabPluginIds.length];
    setTimeout(()=>fetchPlugin(next),350);
  }

  async function updateSystem(){
    if(document.hidden)return;
    try{
      const systemResponse=await fetch("/api/system",{cache:"no-store"});
      if(!systemResponse.ok)throw new TypeError("RackDash server error");
      const d=await systemResponse.json();
      clearConnectionLost();
      const set=(key,val)=>document.querySelectorAll(`[data-system="${key}"]`).forEach(n=>n.textContent=val);
      set("cpu",`${Math.round(d.cpu||0)}%`);
      set("ram",`${Math.round(d.ram||0)}%`);
      set("temp",d.temp==null?"—":`${d.temp}°C`);
      if(d.update_attention){
        setAdminUpdateAttention(!!d.update_attention.available);
      }
      set("ip",d.ip||"—");
      set("uptime",RackDash.uptime(d.uptime));
    }catch(e){
      showConnectionLost();
    }
  }

  function nextAutoIndex(){
    if(!pluginIds.length)return activeIndex;
    const currentId=tabPluginIds[activeIndex];
    let pos=pluginIds.indexOf(currentId);
    if(pos<0)pos=-1;
    const nextId=pluginIds[(pos+1)%pluginIds.length];
    const nextIndex=tabPluginIds.indexOf(nextId);
    return nextIndex>=0?nextIndex:activeIndex;
  }

  function tick(){
    document.getElementById("clock").textContent=new Date().toLocaleTimeString([],{hour:"2-digit",minute:"2-digit"});
    if(!showingHealth && !logoMode && autoRotate && pluginIds.length>1){
      rotateElapsed++;
      const activeId=tabPluginIds[activeIndex];
      const activeMeta=pluginById[activeId]||{};
      const rotateFor=Math.max(3,Number(activeMeta.rotation_seconds||cfg.rotateSeconds||30));
      if(rotateElapsed>=rotateFor)show(nextAutoIndex());
    }
  }

  tabs.forEach((tab,i)=>tab.addEventListener("click",()=>show(i,true)));
  healthTab?.addEventListener("click",()=>showHealth());
  document.getElementById("wledBrightness")?.addEventListener("input",e=>document.getElementById("wledBrightnessValue").textContent=`${e.currentTarget.value}%`);
  document.getElementById("wledBreatheSeconds")?.addEventListener("input",e=>document.getElementById("wledSpeedValue").textContent=e.currentTarget.value);
  document.getElementById("wledBreatheSpread")?.addEventListener("input",e=>document.getElementById("wledIntensityValue").textContent=e.currentTarget.value);
  document.getElementById("wledSave")?.addEventListener("click",async()=>{const m=document.getElementById("wledMessage");m.textContent="Saving...";const q={enabled:document.getElementById("wledEnabled").checked,url:document.getElementById("wledUrl").value,segment:document.getElementById("wledSegment").value,brightness:document.getElementById("wledBrightness").value,status_mode:document.getElementById("wledStatusMode").value,breathe_seconds:document.getElementById("wledBreatheSeconds").value,breathe_spread:document.getElementById("wledBreatheSpread").value,
      breathe_floor:document.getElementById("wledBreatheFloor").value,transition_ms:document.getElementById("wledTransitionMs").value,timeout:document.getElementById("wledTimeout").value};try{const r=await adminFetch("/api/admin/wled",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(q)}),d=await r.json();if(!d.ok)throw new Error(d.error||"Save failed");renderWLED(d.status);m.textContent=d.status.connected?"WLED connected.":"Saved, but WLED is unreachable.";if(d.status.connected)await loadWLEDOptions();}catch(e){m.textContent=e.message;}});
  document.getElementById("wledRefresh")?.addEventListener("click",async()=>{await loadWLED();await loadWLEDOptions();});
  document.getElementById("wledTest")?.addEventListener("click",async()=>{const m=document.getElementById("wledMessage");m.textContent="Testing...";try{const r=await adminFetch("/api/admin/wled/test",{method:"POST"}),d=await r.json();if(!d.ok)throw new Error(d.error||"Test failed");renderWLED(d.status);m.textContent="8-second status-color test running.";}catch(e){m.textContent=e.message;}});

  document.getElementById("i2cDisplay")?.addEventListener("change",updateI2CIconLimit);
  document.getElementById("i2cMode")?.addEventListener("change",updateI2CIconLimit);

  document.getElementById("i2cSave")?.addEventListener("click",async()=>{
    const message=document.getElementById("i2cMessage");message.textContent="Saving...";
    const payload={
      enabled:document.getElementById("i2cEnabled").checked,
      display:document.getElementById("i2cDisplay").value,
      mode:document.getElementById("i2cMode").value,
      bus:document.getElementById("i2cBus").value,
      address:document.getElementById("i2cAddress").value,
      rotate_seconds:document.getElementById("i2cRotate").value,
      contrast:document.getElementById("i2cContrast").value
    };
    try{
      const r=await adminFetch("/api/admin/i2c",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
      const x=await r.json();if(!x.ok)throw new Error(x.error||"Save failed");
      renderI2C(x.status);message.textContent=x.status.connected?"Connected.":"Saved. Check I2C wiring/address if not connected.";
    }catch(e){message.textContent=e.message;}
  });

  document.getElementById("i2cTest")?.addEventListener("click",async()=>{
    const message=document.getElementById("i2cMessage");message.textContent="Testing...";
    try{
      const r=await adminFetch("/api/admin/i2c/test",{method:"POST"});const x=await r.json();
      if(!x.ok)throw new Error(x.error||"Test failed");renderI2C(x.status);message.textContent="Test frame sent.";
    }catch(e){message.textContent=e.message;}
  });

  document.getElementById("i2cUploadIcon")?.addEventListener("click",async()=>{
    const file=document.getElementById("i2cIconFile").files?.[0];
    const message=document.getElementById("i2cMessage");
    if(!file){message.textContent="Choose an image first.";return;}
    const body=new FormData();body.append("icon",file);
    message.textContent="Converting image...";
    try{
      const r=await adminFetch("/api/admin/i2c/icon",{method:"POST",body});const x=await r.json();
      if(!x.ok)throw new Error(x.error||"Upload failed");renderI2C(x.status);
      message.textContent=`Icon stored (${x.image.width}×${x.image.height}) and converted to monochrome.`;
    }catch(e){message.textContent=e.message;}
  });

  document.getElementById("healthInstallButton")?.addEventListener("click",async()=>{const input=document.getElementById("healthInstallUrl"),button=document.getElementById("healthInstallButton"),status=document.getElementById("healthInstallStatus"),github_url=input.value.trim();if(!github_url){status.textContent="Enter a GitHub repository URL.";return;}button.disabled=true;status.textContent="Downloading manifest and validating plugin...";try{const pr=await adminFetch(`/api/admin/plugins/preview?github_url=${encodeURIComponent(github_url)}`);const preview=await pr.json();if(!preview.ok)throw new Error(preview.error||"Preview failed");const caps=(preview.plugin.capabilities||[]).join(", ")||"none declared";if(!confirm(`Install ${preview.plugin.name} v${preview.plugin.version}?\nCapabilities: ${caps}`)){button.disabled=false;status.textContent="Install cancelled.";return;}const r=await adminFetch("/api/health/plugins/install",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({github_url})});const x=await r.json();if(!x.ok)throw new Error(x.error||"Install failed");status.textContent=`Installed ${x.plugin.name} v${x.plugin.version}. Applying...`;input.value="";await restartAndReload(`Installing ${x.plugin.name}`);}catch(e){status.textContent=e.message;}finally{button.disabled=false;}});
  document.getElementById("healthCheckAll")?.addEventListener("click",async e=>{
    const button=e.currentTarget;
    button.disabled=true;
    button.textContent="CHECKING...";
    try{
      const response=await adminFetch(
        "/api/admin/plugin-updates/check-all",
        {method:"POST"}
      );
      const result=await response.json();
      if(!result.ok)throw new Error(
        result.error||"Update check failed"
      );
      const coreResult=result.core?.result||{};
      const pluginResults=Object.values(result.plugins||{})
        .map(row=>row?.result||{});
      if(
        coreResult.status==="update_available"||
        pluginResults.some(row=>row.status==="update_available")
      ){
        setAdminUpdateAttention(true);
      }
      try{
        sessionStorage.setItem(ADMIN_CHECK_AT_KEY,String(Date.now()));
        sessionStorage.setItem(ADMIN_CHECK_VERSION_KEY,String(cfg.appVersion||""));
      }catch(_e){}
      await loadHealth();
    }catch(error){
      alert(error.message);
    }finally{
      button.disabled=false;
      button.textContent="CHECK ALL UPDATES";
    }
  });

  const stored=localStorage.getItem("rackdash-auto-rotate");
  if(stored!==null)rotateBox.checked=stored==="true";
  autoRotate=rotateBox.checked;
  rotateBox.addEventListener("change",()=>{
    autoRotate=rotateBox.checked;
    localStorage.setItem("rackdash-auto-rotate",String(autoRotate));
    rotateElapsed=0;
  });

  // Touch support:
  // Vertical swipes remain native scrolling inside .plugin-scroll.
  // A clearly horizontal swipe changes tabs.
  let touchStart=null;
  document.getElementById("pages").addEventListener("pointerdown",e=>{
    if(e.pointerType!=="touch")return;
    touchStart={x:e.clientX,y:e.clientY,t:Date.now()};
  },{passive:true});
  document.getElementById("pages").addEventListener("pointerup",e=>{
    if(!touchStart||e.pointerType!=="touch")return;
    const dx=e.clientX-touchStart.x,dy=e.clientY-touchStart.y,dt=Date.now()-touchStart.t;
    touchStart=null;
    if(!showingHealth && dt<700 && Math.abs(dx)>65 && Math.abs(dx)>Math.abs(dy)*1.25)show(activeIndex+(dx<0?1:-1),true);
  },{passive:true});


  function logoSessionStartedAt(){
    const now=Date.now();
    try{
      const stored=Number(sessionStorage.getItem(LOGO_SESSION_STARTED_KEY)||0);
      if(Number.isFinite(stored)&&stored>0&&stored<=now){
        return stored;
      }
      sessionStorage.setItem(LOGO_SESSION_STARTED_KEY,String(now));
    }catch(_e){}
    return now;
  }

  function applyHeaderLogoStage(){
    const button=document.getElementById("rackdashLogoButton");
    if(!button)return;

    const elapsed=Math.max(0,Date.now()-logoSessionStartedAt());
    const awake=elapsed>=LOGO_AWAKE_AFTER_MS&&elapsed<LOGO_COMPACT_AFTER_MS;
    const compact=elapsed>=LOGO_COMPACT_AFTER_MS;

    button.classList.toggle("logo-awake",awake);
    button.classList.toggle("logo-compact",compact);
    button.setAttribute(
      "aria-label",
      compact
        ?"RackDash — show fullscreen logo"
        :"Show RackDash fullscreen logo"
    );

    if(logoStageTimer){
      clearTimeout(logoStageTimer);
      logoStageTimer=null;
    }

    let nextAt=null;
    if(elapsed<LOGO_AWAKE_AFTER_MS){
      nextAt=LOGO_AWAKE_AFTER_MS-elapsed;
    }else if(elapsed<LOGO_COMPACT_AFTER_MS){
      nextAt=LOGO_COMPACT_AFTER_MS-elapsed;
    }

    if(nextAt!=null){
      logoStageTimer=setTimeout(
        applyHeaderLogoStage,
        Math.max(50,nextAt+25)
      );
    }
  }

  function enterLogoMode(){
    if(logoMode)return;
    stopAutoScroll(true);
    logoMode=true;
    rotateElapsed=0;
    const overlay=document.getElementById("logoShowcase");
    if(overlay){overlay.hidden=false;overlay.setAttribute("aria-hidden","false");}
    document.documentElement.classList.add("logo-mode");
  }

  function exitLogoMode(){
    if(!logoMode)return;
    logoMode=false;
    const overlay=document.getElementById("logoShowcase");
    if(overlay){overlay.hidden=true;overlay.setAttribute("aria-hidden","true");}
    document.documentElement.classList.remove("logo-mode");
    rotateElapsed=0;
    const id=tabPluginIds[activeIndex];
    if(id)fetchPlugin(id,true);
    updateSystem();
    scheduleAutoScroll();
    scheduleNeighborFetch();
  }

  document.getElementById("rackdashLogoButton")?.addEventListener("click",enterLogoMode);
  document.getElementById("logoShowcaseMark")?.addEventListener("click",exitLogoMode);

  document.addEventListener("visibilitychange",()=>{
    if(!document.hidden){
      applyHeaderLogoStage();
      updateSystem();
      const id=tabPluginIds[activeIndex];
      if(id&&!logoMode)fetchPlugin(id,true);
      if(!logoMode&&!showingHealth)scheduleAutoScroll();
    }
  });

  window.addEventListener("keydown",e=>{
    if(logoMode){
      if(e.key==="Escape"||e.key==="Enter"||e.key===" ")exitLogoMode();
      return;
    }
    if(showingHealth)return;
    if(e.key==="ArrowRight")show(activeIndex+1,true);
    if(e.key==="ArrowLeft")show(activeIndex-1,true);
  });

  function applyUiPreferences(){
    const ui=cfg.ui||{};
    document.documentElement.dataset.theme=ui.theme||"dark";
    if(ui.large_touch)document.documentElement.classList.add("large-touch");
    const scale=Math.max(.7,Math.min(1.5,Number(ui.scale||1)));
    document.documentElement.style.fontSize=`${scale*100}%`;
    const safe=Math.max(0,Math.min(80,Number(ui.safe_area||0)));
    document.body.style.padding=`${safe}px`;
    if(safe)document.body.style.background="#000";
    if(ui.burn_in){
      const root=document.getElementById("rackdash");root.classList.add("burn-shift");
      const shifts=[[0,0],[1,0],[0,1],[-1,0],[0,-1],[1,1],[-1,-1]];let i=0;
      setInterval(()=>{i=(i+1)%shifts.length;root.style.setProperty("--burn-x",`${shifts[i][0]}px`);root.style.setProperty("--burn-y",`${shifts[i][1]}px`);},Math.max(30,Number(ui.burn_in_seconds||90))*1000);
    }
    const dimMinutes=Number(ui.dim_minutes||0);
    if(dimMinutes>0){
      let timer;const root=document.getElementById("rackdash");
      const reset=()=>{root.classList.remove("idle-dim");clearTimeout(timer);timer=setTimeout(()=>root.classList.add("idle-dim"),dimMinutes*60000);};
      ["pointerdown","keydown","touchstart"].forEach(ev=>window.addEventListener(ev,reset,{passive:true}));reset();
    }
  }

  applyUiPreferences();

  window.addEventListener("resize",()=>{
    setLayoutClass();
    const id=tabPluginIds[activeIndex];
    const renderer=window.RackDashPlugins[id];
    if(renderer&&typeof renderer.onResize==="function")renderer.onResize(pages[activeIndex]);
  });

  setLayoutClass();
  applyHeaderLogoStage();
  const restore=rememberedPage();
  if(restore==="admin"&&healthPage&&healthTab){
    showHealth();
  }else{
    const restoreIndex=tabPluginIds.indexOf(restore);
    show(restoreIndex>=0?restoreIndex:0);
  }
  updateSystem();
  scheduleNeighborFetch();
  setInterval(tick,1000);
  setInterval(updateSystem,3000);
})();
