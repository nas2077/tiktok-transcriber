"""Exercise all shared controls in WebView2, including focus and viewport regressions."""
import json
import os
import sys
import threading
import time
import traceback
from pathlib import Path

import webview

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import app
from screenshots import Api as DemoApi, capture


class Api(DemoApi):
    def __init__(self):
        self.saved = []

    def initial_state(self):
        state = super().initial_state()
        # The production language list is long; exercise search and scrolling too.
        state["languages"] = [{"id": k, "name": v} for k, v in app.core.LANGUAGES.items()]
        for i, model in enumerate(state["models"]):
            model["gpu"] = i % 2 == 0
        return state

    def save_settings(self, values):
        self.saved.append(values)
        return {"ok": True}


CHECK = r"""
window.__controlsDone=false;window.__controlsFailure=null;
(async()=>{
  const q=s=>document.querySelector(s), all=s=>[...document.querySelectorAll(s)];
  const wait=()=>new Promise(r=>setTimeout(r,25));
  const assert=(ok,message)=>{if(!ok)throw Error(message);};
  const key=(el,k,shiftKey=false)=>el.dispatchEvent(new KeyboardEvent('keydown',{key:k,shiftKey,bubbles:true,cancelable:true}));
  const stable=()=>{
    assert(document.scrollingElement.scrollTop===0,'root scrolled');
    assert(document.body.getBoundingClientRect().top===0,'body displaced');
    assert(q('.toolbar').getBoundingClientRect().top===0,'title bar displaced');
    // macOS and Linux keep the system's frame: the page hides its own buttons
    for(const id of document.body.dataset.frame==='native'?[]:['w-min','w-max','w-close']){
      const r=q('#'+id).getBoundingClientRect();
      assert(r.top>=0&&r.bottom<=innerHeight&&r.width>0,id+' left viewport');
    }
  };
  const fit=()=>{
    const r=q('#picker-popup').getBoundingClientRect();
    assert(r.left>=0&&r.right<=innerWidth+1&&r.top>=0&&r.bottom<=innerHeight+1,'popup outside viewport');
    stable();
  };
  for(const theme of ['dark','light']){
    document.documentElement.dataset.theme=theme;
    for(const locale of __localeCodes){
      I18n.change(locale);q('[data-view=extract]').click();await wait();
      for(const id of ['sw-times','sw-resume']){
        const el=q('#'+id);el.scrollIntoView({block:'center'});el.focus();
        const rect=el.getBoundingClientRect(), label=el.closest('label').getBoundingClientRect();
        assert(Math.abs(rect.top-label.top)<1&&rect.width>40,'checkbox has detached focus target');
        el.click();el.click();stable();
      }
      for(const option of [...q('#model').options]){
        q('#model-picker').scrollIntoView({block:'center'});await wait();q('#model-picker').click();await wait();
        const choice=q('.picker-option[data-value="'+option.value+'"]');
        assert(choice,theme+' '+locale+' '+option.value+' model menu disappeared; scroll='+q('.pane').scrollTop);
        choice.click();await wait();
        const model=S.models.find(x=>x.id===option.value);
        assert(q('#model-note').textContent.includes(model.technical),'missing technical model name');
        assert(q('#model-note').textContent.includes(I18n.text(model.note)),locale+' '+option.value+' model explanation: '+q('#model-note').textContent+' expected '+I18n.text(model.note));
        assert(option.textContent.includes(I18n.text(model.label)),'model choice not localized');
        assert(q('#engine-device').textContent===I18n.text(model.gpu?'GPU':'CPU'),'device badge does not follow the selected model');
      }
      for(const format of ['txt','md']){
        q('#seg-format [data-v='+format+']').click();
        for(const group of ['seg-format','g-format']){
          assert(q('#'+group+' [aria-pressed=true]').dataset.v===format,'format not mirrored');
          const selected=getComputedStyle(q('#'+group+' [aria-pressed=true]'));
          const other=getComputedStyle(q('#'+group+' [aria-pressed=false]'));
          assert(selected.backgroundColor!==other.backgroundColor&&selected.backgroundColor!=='rgba(0, 0, 0, 0)','format not highlighted');
        }
      }
      for(const id of ['how-many','language','model','gal-how-many']){
        q('[data-view='+(id==='gal-how-many'?'gallery':'extract')+']').click();await wait();
        const select=q('#'+id), button=q('#'+id+'-picker');
        button.scrollIntoView({block:'center'});await wait();button.click();await wait();
        assert(q('#picker-popup'),locale+' '+id+' popup missing');fit();
        assert(q('#picker-heading').textContent===q('#'+button.getAttribute('aria-labelledby')).textContent,'untranslated heading');
        const options=all('.picker-option');
        assert(options.length===select.options.length,'missing options');
        assert(q('.picker-option[aria-selected=true]').dataset.value===select.value,'incorrect selection');
        if(q('#picker-search')){
          q('#picker-search').value=select.options[2].textContent;
          q('#picker-search').dispatchEvent(new Event('input',{bubbles:true}));
          assert(!options[2].hidden,'search omitted matching option');
          q('#picker-search').value='';q('#picker-search').dispatchEvent(new Event('input',{bubbles:true}));
        }
        key(document.activeElement,'End');
        if(document.activeElement!==q('#picker-search'))assert(document.activeElement===options.filter(b=>!b.disabled).at(-1),id+' End did not reach last available option');
        key(document.activeElement,'Escape');
        assert(!q('#picker-popup')&&document.activeElement===button,'Escape did not restore focus');stable();
        button.click();await wait();
        const candidate=all('.picker-option:not(:disabled)').find(o=>o.dataset.value!==select.value);
        const value=candidate.dataset.value;candidate.click();await wait();
        assert(select.value===value&&button.textContent===select.selectedOptions[0].textContent,'selection not committed');
        assert(!q('#picker-popup')&&button.getAttribute('aria-expanded')==='false','menu stayed open');
        button.click();await wait();
        const disabled=q('.picker-option:disabled');
        if(disabled){disabled.click();assert(select.value===value,'disabled option selected');}
        key(document.activeElement,'ArrowDown');
        assert(document.activeElement.matches('.picker-option:not(:disabled)'),'arrow did not focus enabled option');
        key(document.activeElement,'Escape');
        button.click();await wait();q('[data-view=history]').click();
        assert(!q('#picker-popup'),'menu survived view switch');stable();
      }
      q('[data-view=gallery]').click();await wait();q('#gal-opts').click();
      const g=q('#g-times');g.focus();g.click();
      assert(g.checked===q('#sw-times').checked,'timestamp twin not synchronized');stable();
      q('#g-format [data-v=txt]').click();
      assert(q('#seg-format [data-v=txt]').getAttribute('aria-pressed')==='true','gallery format not synchronized');
      q('[data-view=extract]').click();q('#model-picker').scrollIntoView({block:'center'});await wait();
      q('#model-picker').click();await wait();q('#ui-language').click();
      assert(!q('#picker-popup')&&!q('#locale-menu').hidden,'menus overlap');closeLanguageMenu();
      q('#model-picker').click();await wait();
      q('#model').disabled=true;await wait();
      assert(q('#model-picker').disabled&&!q('#picker-popup'),'disabled select stayed interactive');
      q('#model').disabled=false;await wait();
      q('#model-picker').click();await wait();
        const pane=q('.pane');pane.dispatchEvent(new Event('scroll'));await wait();
        assert(q('#picker-popup'),'a stale scroll event closed an unmoved menu');
        pane.scrollTop+=pane.scrollTop>30?-30:30;await wait();
      assert(!q('#picker-popup'),'menu detached from scrolling trigger');stable();
    }
  }
  q('[data-view=extract]').click();
  q('#model-picker').scrollIntoView({block:'center'});await wait();q('#model-picker').click();await wait();
  q('#model option').textContent+=' refreshed';await wait();
  assert(!q('#picker-popup'),'stale model options remained open');
  busyMode();await wait();
  assert(all('.options .picker-trigger').every(b=>b.disabled),'busy controls enabled');
  idleMode();await wait();
  assert(all('.options .picker-trigger').every(b=>!b.disabled),'idle controls stayed disabled');
  window.__controlsFocusCount=0;
  for(const theme of ['dark','light']){
    document.documentElement.dataset.theme=theme;
    for(const view of ['extract','gallery','history','about']){
      q('[data-view='+view+']').click();await wait();
      for(const element of all('button,input,a[href]')){
        if(element.disabled||!element.getClientRects().length)continue;
        element.focus();stable();window.__controlsFocusCount++;
      }
    }
  }
  q('[data-view=extract]').click();
  assert(!window.__errors.length,window.__errors.join('; '));
})().catch(e=>window.__controlsFailure=e.stack).finally(()=>window.__controlsDone=true);void 0;
"""

finished = threading.Event()
failed = False


def watchdog():
    if not finished.wait(120):
        print("FAIL: controls window stopped responding", flush=True)
        os._exit(1)


def run(w, api):
    global failed
    try:
        time.sleep(3)
        codes = json.loads((ROOT / "src/locales/languages.json").read_text(encoding="utf-8"))
        w.evaluate_js("window.__localeCodes=" + json.dumps([x["code"] for x in codes]) + ";")
        w.evaluate_js(CHECK)
        for _ in range(400):
            time.sleep(.15)
            if w.evaluate_js("window.__controlsDone"):
                break
        assert w.evaluate_js("window.__controlsDone"), "control checks did not finish"
        assert not w.evaluate_js("window.__controlsFailure"), w.evaluate_js("window.__controlsFailure")
        time.sleep(.3)
        assert any("whisper_model" in v for v in api.saved) and any("language" in v for v in api.saved)
        assert any("format" in v for v in api.saved) and any("timestamps" in v for v in api.saved)
        print("OK: four pickers, three switches, both format controls, 14 locales and two themes at 1000 x 680", flush=True)
        print("OK: search, keyboard, focus, saved changes, menu bounds, scrolling, view switches and busy/idle states", flush=True)
        print(f"OK: {w.evaluate_js('window.__controlsFocusCount')} focus targets across all four views and both themes keep the title bar visible", flush=True)
        for theme in ("dark", "light"):
            w.evaluate_js("I18n.change('it');document.documentElement.dataset.theme=" + json.dumps(theme) + ";document.querySelector('.options').scrollIntoView({block:'start'});")
            time.sleep(.1)
            w.evaluate_js("document.querySelector('#model-picker').click();")
            time.sleep(.3)
            capture(w.native.Handle.ToInt64(), str(ROOT / ("dev/shots/controls-" + theme + ".png")))
            w.evaluate_js("AppControls.close();")
            time.sleep(.1)
            capture(w.native.Handle.ToInt64(), str(ROOT / ("dev/shots/options-" + theme + ".png")))
    except Exception:
        failed = True
        traceback.print_exc()
    finally:
        finished.set()
        w.destroy()


api = Api()
html = app.read_interface().replace('<script>\n"use strict";', '<script>window.__errors=[];window.addEventListener("error",e=>window.__errors.push(e.message));\n"use strict";')
w = webview.create_window("Controls regression check", html=html, js_api=api, width=1000, height=680, frameless=True, easy_drag=False)
threading.Thread(target=watchdog, daemon=True).start()
threading.Thread(target=run, args=(w, api), daemon=True).start()
webview.start(gui="edgechromium", private_mode=True)
sys.exit(1 if failed else 0)
