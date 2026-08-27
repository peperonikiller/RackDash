(() => {
  "use strict";

  const cfg = window.RACKDASH_CONFIG || {plugins:[], rotateSeconds:12};
  const pluginMeta = cfg.plugins || [];
  const pluginIds = pluginMeta.map(p => p.id);
  const pluginById = Object.fromEntries(pluginMeta.map(p => [p.id,p]));

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
  let serverOffline=false;
  let reconnectTimer=null;
  let reconnectCountdownTimer=null;

  const pages = [...document.querySelectorAll(".plugin-page")];
  const tabs = [...document.querySelectorAll(".tab")];
  const rotateBox = document.getElementById("autoRotate");
  const healthTab = document.querySelector('[data-health-tab="true"]');
  const healthPage = document.getElementById("health-page");
  let showingHealth = false;
  let healthRefreshTimer=null;


  function showConnectionLost(){
    if(serverOffline)return;
    serverOffline=true;
    const overlay=document.getElementById("connectionOverlay");
    if(overlay)overlay.hidden=false;
    scheduleReconnectCheck();
  }

  function clearConnectionLost(){
    serverOffline=false;
    if(reconnectTimer){clearTimeout(reconnectTimer);reconnectTimer=null;}
    if(reconnectCountdownTimer){clearInterval(reconnectCountdownTimer);reconnectCountdownTimer=null;}
    const overlay=document.getElementById("connectionOverlay");
    if(overlay)overlay.hidden=true;
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
        if(response.ok){window.location.reload();return;}
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
    const now=Date.now();
    const due=(meta.refresh_seconds||10)*1000;
    if(!force && now-(lastFetched.get(id)||0)<due)return;

    const root=document.getElementById(`plugin-${id}`);
    const error=root?.querySelector('[data-role="plugin-error"]');
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
    }
  }

  function show(index, userInitiated=false){
    if(!pages.length)return;
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

    const id=pluginIds[activeIndex];
    const meta=pluginById[id];
    if(meta)document.documentElement.style.setProperty("--accent",meta.accent||"#dce8ee");
    tabs[activeIndex]?.scrollIntoView({behavior:"smooth",inline:"center",block:"nearest"});
    pages[activeIndex]?.querySelector(".plugin-scroll")?.scrollTo({top:0,behavior:"auto"});
    fetchPlugin(id,true);

    const renderer=window.RackDashPlugins[id];
    if(renderer&&typeof renderer.onShow==="function")renderer.onShow(pages[activeIndex]);

    rotateElapsed=0;
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

  async function loadHealth(){
    if(!healthPage)return;
    try{
      const response=await fetch("/api/health",{cache:"no-store"});
      const data=await response.json();
      window.__RackDashHealth=data;
      healthPage.querySelector('[data-health="app-version"]').textContent=data.app?.version||"--";
      healthPage.querySelector('[data-health="plugin-count"]').textContent=data.app?.plugin_count??"--";
      healthPage.querySelector('[data-health="status"]').textContent="OK";
      const healthyCount=(data.plugins||[]).filter(p=>p.health?.status==="healthy").length;
      const issueCount=(data.plugins||[]).filter(p=>["error","unconfigured"].includes(p.health?.status)).length;
      healthPage.querySelector('[data-health="healthy-count"]').textContent=String(healthyCount);
      healthPage.querySelector('[data-health="issue-count"]').textContent=String(issueCount);
      healthPage.querySelector('[data-health="status"]').textContent=issueCount?"ATTENTION":"OK";

      const list=document.getElementById("healthPluginList");
      list.innerHTML=(data.plugins||[]).map(p=>`
        <div class="health-plugin-row" data-health-plugin="${RackDash.escape(p.id)}">
          <div>
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
          <div class="health-version">v${RackDash.escape(p.version||"0.0.0")}</div>
          <div class="health-update-status" data-update-status>Not checked</div>
          <div class="health-plugin-actions">
            <label class="health-toggle"><input type="checkbox" data-plugin-enabled="${RackDash.escape(p.id)}" ${p.enabled?"checked":""}> ENABLED</label>
            ${(p.config_fields||[]).length?`<button type="button" data-plugin-settings="${RackDash.escape(p.id)}">SETTINGS</button>`:""}
            <button type="button" class="test-button" data-plugin-test="${RackDash.escape(p.id)}" ${p.enabled?"":"disabled"}>TEST</button>
            ${p.github_url?`<a href="${RackDash.escape(p.github_url)}" target="_blank" rel="noopener">GITHUB</a>`:""}
            <button type="button" data-check-update="${RackDash.escape(p.id)}" ${p.github_url?"":"disabled"}>CHECK</button>
            ${p.installer_managed?`<button type="button" data-managed-update="${RackDash.escape(p.id)}">UPDATE</button><button type="button" data-uninstall-plugin="${RackDash.escape(p.id)}">UNINSTALL</button>`:""}
          </div>
        </div>`).join("");

      list.querySelectorAll("[data-plugin-settings]").forEach(btn=>btn.addEventListener("click",()=>{const p=(window.__RackDashHealth?.plugins||[]).find(x=>x.id===btn.dataset.pluginSettings);if(p)openSettings(`${p.name} Settings`,p.config_fields||[],`/api/health/plugin/${encodeURIComponent(p.id)}/config`);}));
      list.querySelectorAll("[data-plugin-enabled]").forEach(toggle=>toggle.addEventListener("change",async()=>{await fetch(`/api/health/plugin/${encodeURIComponent(toggle.dataset.pluginEnabled)}/enabled`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({enabled:toggle.checked})});const st=toggle.closest(".health-plugin-row")?.querySelector("[data-update-status]");if(st){st.textContent="Reload page to apply visibility";st.className="health-update-status ahead";}}));
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
      list.querySelectorAll("[data-managed-update]").forEach(btn=>btn.addEventListener("click",()=>managedPluginUpdate(btn.dataset.managedUpdate,btn)));
      list.querySelectorAll("[data-uninstall-plugin]").forEach(btn=>btn.addEventListener("click",()=>uninstallPlugin(btn.dataset.uninstallPlugin,btn)));
      list.querySelectorAll("[data-check-update]").forEach(btn=>{
        btn.addEventListener("click",()=>checkPluginUpdate(btn.dataset.checkUpdate,btn));
      });
      document.querySelector('[data-health="updates"]').textContent="0";
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
  document.getElementById("healthRestart")?.addEventListener("click",async()=>{
    if(!confirm("Restart the RackDash server now?"))return;
    const button=document.getElementById("healthRestart");
    button.disabled=true;
    button.textContent="RESTARTING...";
    try{
      const response=await fetch("/api/health/restart",{method:"POST"});
      const result=await response.json();
      if(!result.ok)throw new Error(result.error||"Restart failed");
      setTimeout(showConnectionLost,900);
    }catch(e){
      showConnectionLost();
    }
  });

  document.getElementById("healthCoreSettings")?.addEventListener("click",()=>openSettings("RackDash Core Settings",window.__RackDashHealth?.app?.config_fields||[],"/api/health/core/config"));
  document.getElementById("settingsSave")?.addEventListener("click",async()=>{if(!settingsEndpoint)return;const values={};document.querySelectorAll("#settingsFields [data-setting-key]").forEach(el=>values[el.dataset.settingKey]=el.type==="checkbox"?(el.checked?"true":"false"):el.value);const note=document.getElementById("settingsNote");note.textContent="Saving...";try{const r=await fetch(settingsEndpoint,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({values})});const result=await r.json();if(!result.ok)throw new Error(result.error||"Save failed");note.textContent="Saved. Restart RackDash to apply.";}catch(e){note.textContent=e.message;}});

  async function managedPluginUpdate(id,button){button.disabled=true;const st=button.closest(".health-plugin-row")?.querySelector("[data-update-status]");if(st)st.textContent="Updating...";try{const r=await fetch(`/api/health/plugin/${encodeURIComponent(id)}/update-managed`,{method:"POST"});const x=await r.json();if(!x.ok)throw new Error(x.error||"Update failed");if(st){st.textContent=`Installed ${x.plugin.version}. Restart RackDash.`;st.className="health-update-status update_available";}}catch(e){if(st){st.textContent=e.message;st.className="health-update-status error";}}finally{button.disabled=false;}}
  async function uninstallPlugin(id,button){if(!confirm(`Uninstall ${id}? A backup will be kept.`))return;button.disabled=true;const st=button.closest(".health-plugin-row")?.querySelector("[data-update-status]");try{const r=await fetch(`/api/health/plugin/${encodeURIComponent(id)}/uninstall`,{method:"POST"});const x=await r.json();if(!x.ok)throw new Error(x.error||"Uninstall failed");if(st){st.textContent="Uninstalled. Restart RackDash.";st.className="health-update-status update_available";}}catch(e){if(st){st.textContent=e.message;st.className="health-update-status error";}}finally{button.disabled=false;}}

  function refreshHealthUpdateCount(){
    const count=document.querySelectorAll(".health-update-status.update_available").length;
    const target=document.querySelector('[data-health="updates"]');
    if(target)target.textContent=String(count);
  }

  async function showHealth(){
    showingHealth=true;
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
  }

  function scheduleNeighborFetch(){
    if(pluginIds.length<2)return;
    const next=pluginIds[(activeIndex+1)%pluginIds.length];
    setTimeout(()=>fetchPlugin(next),350);
  }

  async function updateSystem(){
    try{
      const systemResponse=await fetch("/api/system",{cache:"no-store"});
      if(!systemResponse.ok)throw new TypeError("RackDash server error");
      const d=await systemResponse.json();
      clearConnectionLost();
      const set=(key,val)=>document.querySelectorAll(`[data-system="${key}"]`).forEach(n=>n.textContent=val);
      set("cpu",`${Math.round(d.cpu||0)}%`);
      set("ram",`${Math.round(d.ram||0)}%`);
      set("temp",d.temp==null?"—":`${d.temp}°C`);
      set("ip",d.ip||"—");
      set("uptime",RackDash.uptime(d.uptime));
    }catch(e){
      showConnectionLost();
    }
  }

  function tick(){
    document.getElementById("clock").textContent=new Date().toLocaleTimeString([],{hour:"2-digit",minute:"2-digit"});
    if(!showingHealth && autoRotate && pluginIds.length>1){
      rotateElapsed++;
      if(rotateElapsed>=Math.max(3,Number(cfg.rotateSeconds||12)))show(activeIndex+1);
    }
  }

  tabs.forEach((tab,i)=>tab.addEventListener("click",()=>show(i,true)));
  healthTab?.addEventListener("click",()=>showHealth());
  document.getElementById("healthInstallButton")?.addEventListener("click",async()=>{const input=document.getElementById("healthInstallUrl"),button=document.getElementById("healthInstallButton"),status=document.getElementById("healthInstallStatus"),github_url=input.value.trim();if(!github_url){status.textContent="Enter a GitHub repository URL.";return;}button.disabled=true;status.textContent="Downloading manifest and validating plugin...";try{const r=await fetch("/api/health/plugins/install",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({github_url})});const x=await r.json();if(!x.ok)throw new Error(x.error||"Install failed");status.textContent=`Installed ${x.plugin.name} v${x.plugin.version}. Restart RackDash to load it.`;input.value="";}catch(e){status.textContent=e.message;}finally{button.disabled=false;}});
  document.getElementById("healthCheckAll")?.addEventListener("click",async e=>{
    const button=e.currentTarget;
    button.disabled=true;
    const buttons=[...document.querySelectorAll("[data-check-update]")].filter(b=>!b.disabled);
    for(const btn of buttons){
      await checkPluginUpdate(btn.dataset.checkUpdate,btn);
    }
    button.disabled=false;
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

  window.addEventListener("resize",()=>{
    setLayoutClass();
    const id=pluginIds[activeIndex];
    const renderer=window.RackDashPlugins[id];
    if(renderer&&typeof renderer.onResize==="function")renderer.onResize(pages[activeIndex]);
  });

  setLayoutClass();
  show(0);
  updateSystem();
  scheduleNeighborFetch();
  setInterval(tick,1000);
  setInterval(updateSystem,2000);
})();
