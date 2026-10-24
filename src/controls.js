/* Accessible pickers share the app-language menu's card and option styles.
   Native selects retain their values and change events as the data model. */
(function () {
  "use strict";
  const pickers=new Map();
  let active=null, popup=null, anchor=null;
  const searchText=value=>String(value).normalize("NFKD").replace(/\p{M}/gu,"").toLocaleLowerCase();
  function sync(picker){
    const {select,button,text}=picker;
    text.textContent=select.selectedOptions[0]?.textContent||"—";
    button.title=text.textContent+(select.selectedOptions[0]?.title?" · "+select.selectedOptions[0].title:"");
    button.disabled=select.disabled||!select.options.length;
    if(active===picker && button.disabled)close();
  }
  function close(restoreFocus=false){
    const previous=active;
    if(previous){previous.button.setAttribute("aria-expanded","false");previous.select.parentElement.removeAttribute("data-open");}
    popup?.remove(); popup=null; active=null; anchor=null;
    if(restoreFocus && previous && !previous.button.disabled)previous.button.focus({preventScroll:true});
  }
  function visibleOptions(){return [...popup.querySelectorAll(".picker-option:not([hidden]):not(:disabled)")];}
  function focusOption(index){
    const list=visibleOptions();
    if(!list.length)return;
    const option=list[(index+list.length)%list.length];
    option.focus({preventScroll:true});
    const box=option.parentElement;
    const top=option.getBoundingClientRect().top-box.getBoundingClientRect().top+box.scrollTop;
    const bottom=top+option.offsetHeight;
    if(top<box.scrollTop)box.scrollTop=top;
    else if(bottom>box.scrollTop+box.clientHeight)box.scrollTop=bottom-box.clientHeight;
  }
  function position(){
    if(!active||!popup)return;
    const rect=active.button.getBoundingClientRect();
    const width=Math.min(Math.max(260,rect.width),window.innerWidth-24);
    popup.style.width=width+"px";
    popup.style.maxHeight=(window.innerHeight-24)+"px";
    popup.style.left=Math.max(12,Math.min(rect.left,window.innerWidth-width-12))+"px";
    const height=popup.getBoundingClientRect().height;
    const below=window.innerHeight-rect.bottom-20, above=rect.top-20;
    const down=below>=height||below>=above;
    popup.style.maxHeight=Math.max(60,down?below:above)+"px";
    const finalHeight=popup.getBoundingClientRect().height;
    popup.style.top=Math.max(12,Math.min(down?rect.bottom+8:rect.top-finalHeight-8,window.innerHeight-finalHeight-12))+"px";
  }
  function open(picker){
    if(picker.select.disabled||!picker.select.options.length)return;
    if(active===picker){close(true);return;}
    close(); window.closeLanguageMenu?.(); window.closeMenu?.();
    active=picker;
    popup=document.createElement("div"); popup.className="picker-popup n-card";
    popup.id="picker-popup"; popup.style.visibility="hidden";
    const heading=document.createElement("b"); heading.id="picker-heading";
    heading.textContent=picker.label.textContent; popup.appendChild(heading);
    popup.setAttribute("role","dialog");popup.setAttribute("aria-labelledby",heading.id);
    let search=null;
    if(picker.select.options.length>8){
      const label=document.createElement("label");label.className="n-field small";
      const caption=document.createElement("span");caption.textContent=I18n.text("Search options");
      search=document.createElement("input");search.type="search";search.id="picker-search";
      search.autocomplete="off";search.spellcheck=false;label.htmlFor=search.id;
      label.append(caption,search);popup.appendChild(label);
    }
    const list=document.createElement("div");list.className="picker-options";
    list.id="picker-options";list.setAttribute("role","listbox");list.setAttribute("aria-labelledby",heading.id);
    for(const option of picker.select.options){
      const button=document.createElement("button");button.type="button";button.className="picker-option";
      button.disabled=option.disabled;button.dataset.value=option.value;
      button.setAttribute("role","option");button.setAttribute("aria-selected",String(option.selected));
      const label=document.createElement("span");label.textContent=option.textContent;
      const dot=document.createElement("span");dot.className="selected";dot.setAttribute("aria-hidden","true");
      button.title=option.title||option.textContent;button.append(label,dot);
      button.addEventListener("click",()=>{
        if(option.disabled||picker.select.disabled)return;
        const changed=picker.select.value!==option.value;
        picker.select.value=option.value;
        sync(picker);close(true);
        if(changed)picker.select.dispatchEvent(new Event("change",{bubbles:true}));
      });
      list.appendChild(button);
    }
    popup.appendChild(list); document.body.appendChild(popup);
    picker.button.setAttribute("aria-expanded","true");picker.select.parentElement.dataset.open="true";
    if(search)search.addEventListener("input",()=>{
      const term=searchText(search.value.trim());
      list.querySelectorAll(".picker-option").forEach(b=>b.hidden=!searchText(b.textContent+" "+b.dataset.value).includes(term));
      position();
    });
    popup.addEventListener("keydown",event=>{
      const options=visibleOptions(), index=options.indexOf(document.activeElement);
      if(event.key==="Escape"){event.preventDefault();event.stopPropagation();close(true);}
      else if(event.key==="ArrowDown"||event.key==="ArrowUp"){
        event.preventDefault();focusOption(index<0?(event.key==="ArrowDown"?0:options.length-1):index+(event.key==="ArrowDown"?1:-1));
      }else if((event.key==="Home"||event.key==="End") && event.target!==search){
        event.preventDefault();focusOption(event.key==="Home"?0:options.length-1);
      }else if(event.key==="Tab"){
        const fields=search?[search,...options]:options;
        const last=fields[fields.length-1];   // no .at(): macOS 11's WebKit lacks it
        if(event.shiftKey && document.activeElement===fields[0]){event.preventDefault();last?.focus({preventScroll:true});}
        else if(!event.shiftKey && document.activeElement===last){event.preventDefault();fields[0]?.focus({preventScroll:true});}
      }
    });
    position();anchor=new Map();
    for(let node=picker.button.parentElement;node;node=node.parentElement)
      anchor.set(node,[node.scrollLeft,node.scrollTop]);
    popup.style.visibility="";
    if(search)search.focus({preventScroll:true});
    else{
      const options=visibleOptions(), chosen=options.findIndex(b=>b.getAttribute("aria-selected")==="true");
      focusOption(Math.max(0,chosen));
    }
  }
  function init(){
    document.querySelectorAll(".dropdown select").forEach(select=>{
      if(pickers.has(select))return;
      const sourceLabel=select.labels[0];
      const label=sourceLabel.querySelector("[data-i18n]")||sourceLabel;
      label.id=label.id||"picker-label-"+select.id;
      const button=document.createElement("button");button.type="button";button.className="picker-trigger";
      button.id=select.id+"-picker";button.setAttribute("role","combobox");
      button.setAttribute("aria-haspopup","listbox");button.setAttribute("aria-expanded","false");
      button.setAttribute("aria-controls","picker-options");button.setAttribute("aria-labelledby",label.id);
      const text=document.createElement("span");button.appendChild(text);
      select.hidden=true;select.tabIndex=-1;select.setAttribute("aria-hidden","true");
      sourceLabel.htmlFor=button.id;
      select.after(button);
      const picker={select,button,text,label};pickers.set(select,picker);
      button.addEventListener("click",()=>open(picker));
      button.addEventListener("keydown",event=>{
        if(event.key==="ArrowDown"||event.key==="ArrowUp"){event.preventDefault();open(picker);}
        else if(event.key==="Escape")close(true);
      });
      select.addEventListener("change",()=>sync(picker));
      new MutationObserver(()=>{
        if(active===picker)close(true);
        sync(picker);
      }).observe(select,{subtree:true,childList:true,characterData:true,attributes:true,attributeFilter:["disabled","selected","title"]});
      sync(picker);
    });
  }
  document.addEventListener("click",event=>{
    if(active && !event.target.closest(".picker-popup") && !active.button.contains(event.target))close();
  });
  document.addEventListener("uilanguagechange",()=>{close();pickers.forEach(sync);});
  document.addEventListener("visibilitychange",()=>{if(document.hidden)close();});
  window.addEventListener("resize",()=>close());
  document.addEventListener("scroll",event=>{
    if(active && !popup.contains(event.target)){
      // Entrance animation may move the trigger without changing scroll offsets.
      const node=event.target===document?document.scrollingElement:event.target;
      const origin=anchor?.get(node);
      if(origin&&(node.scrollLeft!==origin[0]||node.scrollTop!==origin[1]))close();
      else position();
    }
  },true);
  window.AppControls={init,close,refresh:()=>pickers.forEach(sync)};
})();
