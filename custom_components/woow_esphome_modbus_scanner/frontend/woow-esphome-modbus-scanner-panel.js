/**
 * @license
 * Copyright 2019 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */
const t$1=globalThis,e$2=t$1.ShadowRoot&&(void 0===t$1.ShadyCSS||t$1.ShadyCSS.nativeShadow)&&"adoptedStyleSheets"in Document.prototype&&"replace"in CSSStyleSheet.prototype,s$2=Symbol(),o$3=new WeakMap;let n$2 = class n{constructor(t,e,o){if(this._$cssResult$=true,o!==s$2)throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");this.cssText=t,this.t=e;}get styleSheet(){let t=this.o;const s=this.t;if(e$2&&void 0===t){const e=void 0!==s&&1===s.length;e&&(t=o$3.get(s)),void 0===t&&((this.o=t=new CSSStyleSheet).replaceSync(this.cssText),e&&o$3.set(s,t));}return t}toString(){return this.cssText}};const r$2=t=>new n$2("string"==typeof t?t:t+"",void 0,s$2),i$3=(t,...e)=>{const o=1===t.length?t[0]:e.reduce((e,s,o)=>e+(t=>{if(true===t._$cssResult$)return t.cssText;if("number"==typeof t)return t;throw Error("Value passed to 'css' function must be a 'css' function result: "+t+". Use 'unsafeCSS' to pass non-literal values, but take care to ensure page security.")})(s)+t[o+1],t[0]);return new n$2(o,t,s$2)},S$1=(s,o)=>{if(e$2)s.adoptedStyleSheets=o.map(t=>t instanceof CSSStyleSheet?t:t.styleSheet);else for(const e of o){const o=document.createElement("style"),n=t$1.litNonce;void 0!==n&&o.setAttribute("nonce",n),o.textContent=e.cssText,s.appendChild(o);}},c$2=e$2?t=>t:t=>t instanceof CSSStyleSheet?(t=>{let e="";for(const s of t.cssRules)e+=s.cssText;return r$2(e)})(t):t;

/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */const{is:i$2,defineProperty:e$1,getOwnPropertyDescriptor:h$1,getOwnPropertyNames:r$1,getOwnPropertySymbols:o$2,getPrototypeOf:n$1}=Object,a$1=globalThis,c$1=a$1.trustedTypes,l$1=c$1?c$1.emptyScript:"",p$1=a$1.reactiveElementPolyfillSupport,d$1=(t,s)=>t,u$1={toAttribute(t,s){switch(s){case Boolean:t=t?l$1:null;break;case Object:case Array:t=null==t?t:JSON.stringify(t);}return t},fromAttribute(t,s){let i=t;switch(s){case Boolean:i=null!==t;break;case Number:i=null===t?null:Number(t);break;case Object:case Array:try{i=JSON.parse(t);}catch(t){i=null;}}return i}},f$1=(t,s)=>!i$2(t,s),b$1={attribute:true,type:String,converter:u$1,reflect:false,useDefault:false,hasChanged:f$1};Symbol.metadata??=Symbol("metadata"),a$1.litPropertyMetadata??=new WeakMap;let y$1 = class y extends HTMLElement{static addInitializer(t){this._$Ei(),(this.l??=[]).push(t);}static get observedAttributes(){return this.finalize(),this._$Eh&&[...this._$Eh.keys()]}static createProperty(t,s=b$1){if(s.state&&(s.attribute=false),this._$Ei(),this.prototype.hasOwnProperty(t)&&((s=Object.create(s)).wrapped=true),this.elementProperties.set(t,s),!s.noAccessor){const i=Symbol(),h=this.getPropertyDescriptor(t,i,s);void 0!==h&&e$1(this.prototype,t,h);}}static getPropertyDescriptor(t,s,i){const{get:e,set:r}=h$1(this.prototype,t)??{get(){return this[s]},set(t){this[s]=t;}};return {get:e,set(s){const h=e?.call(this);r?.call(this,s),this.requestUpdate(t,h,i);},configurable:true,enumerable:true}}static getPropertyOptions(t){return this.elementProperties.get(t)??b$1}static _$Ei(){if(this.hasOwnProperty(d$1("elementProperties")))return;const t=n$1(this);t.finalize(),void 0!==t.l&&(this.l=[...t.l]),this.elementProperties=new Map(t.elementProperties);}static finalize(){if(this.hasOwnProperty(d$1("finalized")))return;if(this.finalized=true,this._$Ei(),this.hasOwnProperty(d$1("properties"))){const t=this.properties,s=[...r$1(t),...o$2(t)];for(const i of s)this.createProperty(i,t[i]);}const t=this[Symbol.metadata];if(null!==t){const s=litPropertyMetadata.get(t);if(void 0!==s)for(const[t,i]of s)this.elementProperties.set(t,i);}this._$Eh=new Map;for(const[t,s]of this.elementProperties){const i=this._$Eu(t,s);void 0!==i&&this._$Eh.set(i,t);}this.elementStyles=this.finalizeStyles(this.styles);}static finalizeStyles(s){const i=[];if(Array.isArray(s)){const e=new Set(s.flat(1/0).reverse());for(const s of e)i.unshift(c$2(s));}else void 0!==s&&i.push(c$2(s));return i}static _$Eu(t,s){const i=s.attribute;return  false===i?void 0:"string"==typeof i?i:"string"==typeof t?t.toLowerCase():void 0}constructor(){super(),this._$Ep=void 0,this.isUpdatePending=false,this.hasUpdated=false,this._$Em=null,this._$Ev();}_$Ev(){this._$ES=new Promise(t=>this.enableUpdating=t),this._$AL=new Map,this._$E_(),this.requestUpdate(),this.constructor.l?.forEach(t=>t(this));}addController(t){(this._$EO??=new Set).add(t),void 0!==this.renderRoot&&this.isConnected&&t.hostConnected?.();}removeController(t){this._$EO?.delete(t);}_$E_(){const t=new Map,s=this.constructor.elementProperties;for(const i of s.keys())this.hasOwnProperty(i)&&(t.set(i,this[i]),delete this[i]);t.size>0&&(this._$Ep=t);}createRenderRoot(){const t=this.shadowRoot??this.attachShadow(this.constructor.shadowRootOptions);return S$1(t,this.constructor.elementStyles),t}connectedCallback(){this.renderRoot??=this.createRenderRoot(),this.enableUpdating(true),this._$EO?.forEach(t=>t.hostConnected?.());}enableUpdating(t){}disconnectedCallback(){this._$EO?.forEach(t=>t.hostDisconnected?.());}attributeChangedCallback(t,s,i){this._$AK(t,i);}_$ET(t,s){const i=this.constructor.elementProperties.get(t),e=this.constructor._$Eu(t,i);if(void 0!==e&&true===i.reflect){const h=(void 0!==i.converter?.toAttribute?i.converter:u$1).toAttribute(s,i.type);this._$Em=t,null==h?this.removeAttribute(e):this.setAttribute(e,h),this._$Em=null;}}_$AK(t,s){const i=this.constructor,e=i._$Eh.get(t);if(void 0!==e&&this._$Em!==e){const t=i.getPropertyOptions(e),h="function"==typeof t.converter?{fromAttribute:t.converter}:void 0!==t.converter?.fromAttribute?t.converter:u$1;this._$Em=e;const r=h.fromAttribute(s,t.type);this[e]=r??this._$Ej?.get(e)??r,this._$Em=null;}}requestUpdate(t,s,i,e=false,h){if(void 0!==t){const r=this.constructor;if(false===e&&(h=this[t]),i??=r.getPropertyOptions(t),!((i.hasChanged??f$1)(h,s)||i.useDefault&&i.reflect&&h===this._$Ej?.get(t)&&!this.hasAttribute(r._$Eu(t,i))))return;this.C(t,s,i);} false===this.isUpdatePending&&(this._$ES=this._$EP());}C(t,s,{useDefault:i,reflect:e,wrapped:h},r){i&&!(this._$Ej??=new Map).has(t)&&(this._$Ej.set(t,r??s??this[t]),true!==h||void 0!==r)||(this._$AL.has(t)||(this.hasUpdated||i||(s=void 0),this._$AL.set(t,s)),true===e&&this._$Em!==t&&(this._$Eq??=new Set).add(t));}async _$EP(){this.isUpdatePending=true;try{await this._$ES;}catch(t){Promise.reject(t);}const t=this.scheduleUpdate();return null!=t&&await t,!this.isUpdatePending}scheduleUpdate(){return this.performUpdate()}performUpdate(){if(!this.isUpdatePending)return;if(!this.hasUpdated){if(this.renderRoot??=this.createRenderRoot(),this._$Ep){for(const[t,s]of this._$Ep)this[t]=s;this._$Ep=void 0;}const t=this.constructor.elementProperties;if(t.size>0)for(const[s,i]of t){const{wrapped:t}=i,e=this[s];true!==t||this._$AL.has(s)||void 0===e||this.C(s,void 0,i,e);}}let t=false;const s=this._$AL;try{t=this.shouldUpdate(s),t?(this.willUpdate(s),this._$EO?.forEach(t=>t.hostUpdate?.()),this.update(s)):this._$EM();}catch(s){throw t=false,this._$EM(),s}t&&this._$AE(s);}willUpdate(t){}_$AE(t){this._$EO?.forEach(t=>t.hostUpdated?.()),this.hasUpdated||(this.hasUpdated=true,this.firstUpdated(t)),this.updated(t);}_$EM(){this._$AL=new Map,this.isUpdatePending=false;}get updateComplete(){return this.getUpdateComplete()}getUpdateComplete(){return this._$ES}shouldUpdate(t){return  true}update(t){this._$Eq&&=this._$Eq.forEach(t=>this._$ET(t,this[t])),this._$EM();}updated(t){}firstUpdated(t){}};y$1.elementStyles=[],y$1.shadowRootOptions={mode:"open"},y$1[d$1("elementProperties")]=new Map,y$1[d$1("finalized")]=new Map,p$1?.({ReactiveElement:y$1}),(a$1.reactiveElementVersions??=[]).push("2.1.2");

/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */
const t=globalThis,i$1=t=>t,s$1=t.trustedTypes,e=s$1?s$1.createPolicy("lit-html",{createHTML:t=>t}):void 0,h="$lit$",o$1=`lit$${Math.random().toFixed(9).slice(2)}$`,n="?"+o$1,r=`<${n}>`,l=document,c=()=>l.createComment(""),a=t=>null===t||"object"!=typeof t&&"function"!=typeof t,u=Array.isArray,d=t=>u(t)||"function"==typeof t?.[Symbol.iterator],f="[ \t\n\f\r]",v=/<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g,_=/-->/g,m=/>/g,p=RegExp(`>|${f}(?:([^\\s"'>=/]+)(${f}*=${f}*(?:[^ \t\n\f\r"'\`<>=]|("|')|))|$)`,"g"),g=/'/g,$=/"/g,y=/^(?:script|style|textarea|title)$/i,x=t=>(i,...s)=>({_$litType$:t,strings:i,values:s}),b=x(1),E=Symbol.for("lit-noChange"),A=Symbol.for("lit-nothing"),C=new WeakMap,P=l.createTreeWalker(l,129);function V(t,i){if(!u(t)||!t.hasOwnProperty("raw"))throw Error("invalid template strings array");return void 0!==e?e.createHTML(i):i}const N=(t,i)=>{const s=t.length-1,e=[];let n,l=2===i?"<svg>":3===i?"<math>":"",c=v;for(let i=0;i<s;i++){const s=t[i];let a,u,d=-1,f=0;for(;f<s.length&&(c.lastIndex=f,u=c.exec(s),null!==u);)f=c.lastIndex,c===v?"!--"===u[1]?c=_:void 0!==u[1]?c=m:void 0!==u[2]?(y.test(u[2])&&(n=RegExp("</"+u[2],"g")),c=p):void 0!==u[3]&&(c=p):c===p?">"===u[0]?(c=n??v,d=-1):void 0===u[1]?d=-2:(d=c.lastIndex-u[2].length,a=u[1],c=void 0===u[3]?p:'"'===u[3]?$:g):c===$||c===g?c=p:c===_||c===m?c=v:(c=p,n=void 0);const x=c===p&&t[i+1].startsWith("/>")?" ":"";l+=c===v?s+r:d>=0?(e.push(a),s.slice(0,d)+h+s.slice(d)+o$1+x):s+o$1+(-2===d?i:x);}return [V(t,l+(t[s]||"<?>")+(2===i?"</svg>":3===i?"</math>":"")),e]};class S{constructor({strings:t,_$litType$:i},e){let r;this.parts=[];let l=0,a=0;const u=t.length-1,d=this.parts,[f,v]=N(t,i);if(this.el=S.createElement(f,e),P.currentNode=this.el.content,2===i||3===i){const t=this.el.content.firstChild;t.replaceWith(...t.childNodes);}for(;null!==(r=P.nextNode())&&d.length<u;){if(1===r.nodeType){if(r.hasAttributes())for(const t of r.getAttributeNames())if(t.endsWith(h)){const i=v[a++],s=r.getAttribute(t).split(o$1),e=/([.?@])?(.*)/.exec(i);d.push({type:1,index:l,name:e[2],strings:s,ctor:"."===e[1]?I:"?"===e[1]?L:"@"===e[1]?z:H}),r.removeAttribute(t);}else t.startsWith(o$1)&&(d.push({type:6,index:l}),r.removeAttribute(t));if(y.test(r.tagName)){const t=r.textContent.split(o$1),i=t.length-1;if(i>0){r.textContent=s$1?s$1.emptyScript:"";for(let s=0;s<i;s++)r.append(t[s],c()),P.nextNode(),d.push({type:2,index:++l});r.append(t[i],c());}}}else if(8===r.nodeType)if(r.data===n)d.push({type:2,index:l});else {let t=-1;for(;-1!==(t=r.data.indexOf(o$1,t+1));)d.push({type:7,index:l}),t+=o$1.length-1;}l++;}}static createElement(t,i){const s=l.createElement("template");return s.innerHTML=t,s}}function M(t,i,s=t,e){if(i===E)return i;let h=void 0!==e?s._$Co?.[e]:s._$Cl;const o=a(i)?void 0:i._$litDirective$;return h?.constructor!==o&&(h?._$AO?.(false),void 0===o?h=void 0:(h=new o(t),h._$AT(t,s,e)),void 0!==e?(s._$Co??=[])[e]=h:s._$Cl=h),void 0!==h&&(i=M(t,h._$AS(t,i.values),h,e)),i}class R{constructor(t,i){this._$AV=[],this._$AN=void 0,this._$AD=t,this._$AM=i;}get parentNode(){return this._$AM.parentNode}get _$AU(){return this._$AM._$AU}u(t){const{el:{content:i},parts:s}=this._$AD,e=(t?.creationScope??l).importNode(i,true);P.currentNode=e;let h=P.nextNode(),o=0,n=0,r=s[0];for(;void 0!==r;){if(o===r.index){let i;2===r.type?i=new k(h,h.nextSibling,this,t):1===r.type?i=new r.ctor(h,r.name,r.strings,this,t):6===r.type&&(i=new Z(h,this,t)),this._$AV.push(i),r=s[++n];}o!==r?.index&&(h=P.nextNode(),o++);}return P.currentNode=l,e}p(t){let i=0;for(const s of this._$AV) void 0!==s&&(void 0!==s.strings?(s._$AI(t,s,i),i+=s.strings.length-2):s._$AI(t[i])),i++;}}class k{get _$AU(){return this._$AM?._$AU??this._$Cv}constructor(t,i,s,e){this.type=2,this._$AH=A,this._$AN=void 0,this._$AA=t,this._$AB=i,this._$AM=s,this.options=e,this._$Cv=e?.isConnected??true;}get parentNode(){let t=this._$AA.parentNode;const i=this._$AM;return void 0!==i&&11===t?.nodeType&&(t=i.parentNode),t}get startNode(){return this._$AA}get endNode(){return this._$AB}_$AI(t,i=this){t=M(this,t,i),a(t)?t===A||null==t||""===t?(this._$AH!==A&&this._$AR(),this._$AH=A):t!==this._$AH&&t!==E&&this._(t):void 0!==t._$litType$?this.$(t):void 0!==t.nodeType?this.T(t):d(t)?this.k(t):this._(t);}O(t){return this._$AA.parentNode.insertBefore(t,this._$AB)}T(t){this._$AH!==t&&(this._$AR(),this._$AH=this.O(t));}_(t){this._$AH!==A&&a(this._$AH)?this._$AA.nextSibling.data=t:this.T(l.createTextNode(t)),this._$AH=t;}$(t){const{values:i,_$litType$:s}=t,e="number"==typeof s?this._$AC(t):(void 0===s.el&&(s.el=S.createElement(V(s.h,s.h[0]),this.options)),s);if(this._$AH?._$AD===e)this._$AH.p(i);else {const t=new R(e,this),s=t.u(this.options);t.p(i),this.T(s),this._$AH=t;}}_$AC(t){let i=C.get(t.strings);return void 0===i&&C.set(t.strings,i=new S(t)),i}k(t){u(this._$AH)||(this._$AH=[],this._$AR());const i=this._$AH;let s,e=0;for(const h of t)e===i.length?i.push(s=new k(this.O(c()),this.O(c()),this,this.options)):s=i[e],s._$AI(h),e++;e<i.length&&(this._$AR(s&&s._$AB.nextSibling,e),i.length=e);}_$AR(t=this._$AA.nextSibling,s){for(this._$AP?.(false,true,s);t!==this._$AB;){const s=i$1(t).nextSibling;i$1(t).remove(),t=s;}}setConnected(t){ void 0===this._$AM&&(this._$Cv=t,this._$AP?.(t));}}class H{get tagName(){return this.element.tagName}get _$AU(){return this._$AM._$AU}constructor(t,i,s,e,h){this.type=1,this._$AH=A,this._$AN=void 0,this.element=t,this.name=i,this._$AM=e,this.options=h,s.length>2||""!==s[0]||""!==s[1]?(this._$AH=Array(s.length-1).fill(new String),this.strings=s):this._$AH=A;}_$AI(t,i=this,s,e){const h=this.strings;let o=false;if(void 0===h)t=M(this,t,i,0),o=!a(t)||t!==this._$AH&&t!==E,o&&(this._$AH=t);else {const e=t;let n,r;for(t=h[0],n=0;n<h.length-1;n++)r=M(this,e[s+n],i,n),r===E&&(r=this._$AH[n]),o||=!a(r)||r!==this._$AH[n],r===A?t=A:t!==A&&(t+=(r??"")+h[n+1]),this._$AH[n]=r;}o&&!e&&this.j(t);}j(t){t===A?this.element.removeAttribute(this.name):this.element.setAttribute(this.name,t??"");}}class I extends H{constructor(){super(...arguments),this.type=3;}j(t){this.element[this.name]=t===A?void 0:t;}}class L extends H{constructor(){super(...arguments),this.type=4;}j(t){this.element.toggleAttribute(this.name,!!t&&t!==A);}}class z extends H{constructor(t,i,s,e,h){super(t,i,s,e,h),this.type=5;}_$AI(t,i=this){if((t=M(this,t,i,0)??A)===E)return;const s=this._$AH,e=t===A&&s!==A||t.capture!==s.capture||t.once!==s.once||t.passive!==s.passive,h=t!==A&&(s===A||e);e&&this.element.removeEventListener(this.name,this,s),h&&this.element.addEventListener(this.name,this,t),this._$AH=t;}handleEvent(t){"function"==typeof this._$AH?this._$AH.call(this.options?.host??this.element,t):this._$AH.handleEvent(t);}}class Z{constructor(t,i,s){this.element=t,this.type=6,this._$AN=void 0,this._$AM=i,this.options=s;}get _$AU(){return this._$AM._$AU}_$AI(t){M(this,t);}}const B=t.litHtmlPolyfillSupport;B?.(S,k),(t.litHtmlVersions??=[]).push("3.3.3");const D=(t,i,s)=>{const e=s?.renderBefore??i;let h=e._$litPart$;if(void 0===h){const t=s?.renderBefore??null;e._$litPart$=h=new k(i.insertBefore(c(),t),t,void 0,s??{});}return h._$AI(t),h};

/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */const s=globalThis;class i extends y$1{constructor(){super(...arguments),this.renderOptions={host:this},this._$Do=void 0;}createRenderRoot(){const t=super.createRenderRoot();return this.renderOptions.renderBefore??=t.firstChild,t}update(t){const r=this.render();this.hasUpdated||(this.renderOptions.isConnected=this.isConnected),super.update(t),this._$Do=D(r,this.renderRoot,this.renderOptions);}connectedCallback(){super.connectedCallback(),this._$Do?.setConnected(true);}disconnectedCallback(){super.disconnectedCallback(),this._$Do?.setConnected(false);}render(){return E}}i._$litElement$=true,i["finalized"]=true,s.litElementHydrateSupport?.({LitElement:i});const o=s.litElementPolyfillSupport;o?.({LitElement:i});(s.litElementVersions??=[]).push("4.2.2");

const panelStyles = i$3`
  :host{--brand:#6183FC;--quiet:var(--secondary-background-color,#f5f7fa);--surface:var(--card-background-color,#fff);--ink:var(--primary-text-color,#172033);--muted:var(--secondary-text-color,#5e6879);--line:var(--divider-color,#dfe3eb);--control-line:var(--outline-color,var(--primary-text-color,#5e6879));display:block;min-height:100%;color:var(--ink);background:var(--primary-background-color,#eef1f5);font-family:Outfit,var(--paper-font-body1_-_font-family),system-ui,sans-serif;line-height:1.45}*{box-sizing:border-box}.sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}h1,h2,h3{font-family:Poppins,Outfit,var(--paper-font-headline_-_font-family),system-ui,sans-serif}.top>ha-icon{color:var(--brand)}button ha-icon{color:currentColor}.top{height:64px;display:flex;align-items:center;gap:8px;padding:0 16px;background:var(--app-header-background-color,var(--surface));color:var(--app-header-text-color,var(--ink));box-shadow:0 1px 4px rgba(0,0,0,.16);position:sticky;top:0;z-index:2}.top h1{font-size:20px;margin:0}.menu{display:none}.narrow .menu{display:inline-flex}.shell{max-width:1200px;margin:auto;padding:20px}.banner{border-radius:28px;padding:20px;background:#172033;color:#fff;margin-bottom:20px;display:flex;justify-content:space-between;gap:16px;align-items:center}.banner p{margin:5px 0}.banner strong,.banner a{color:#e9edff}.banner nav{display:flex;gap:8px;flex:0 0 auto}.banner a{min-height:44px;display:inline-flex;align-items:center;padding:8px 12px;border:2px solid #e9edff;border-radius:12px;font-weight:700;text-align:center}.grid{display:grid;grid-template-columns:minmax(0,1.15fr) minmax(280px,.85fr);gap:20px}.card{min-width:0;background:var(--surface);border:1px solid var(--line);border-radius:20px;padding:20px;margin-bottom:20px;box-shadow:var(--ha-card-box-shadow,0 8px 24px rgba(28,39,64,.07))}.card h2{font-size:20px;margin:0 0 12px}.fields{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.field{min-width:0}.field.full{grid-column:1/-1}label{display:block;font-weight:650;margin-bottom:5px}small{display:block;color:var(--muted);margin-top:4px}input,select,button{font:inherit;min-height:44px;border-radius:12px}input,select{width:100%;padding:8px 10px;color:var(--ink);background:var(--surface);border:2px solid var(--control-line)}input[type=checkbox]{width:24px;min-height:24px;vertical-align:middle;margin-right:8px;accent-color:var(--brand)}.check label{display:flex;align-items:center;min-height:44px}.error{color:var(--error-color,#b42318);font-weight:700}.actions,.profiles{display:flex;flex-wrap:wrap;gap:10px;margin-top:16px}button{display:inline-flex;align-items:center;justify-content:center;gap:7px;border:2px solid var(--control-line);padding:7px 15px;cursor:pointer;font-weight:700;background:var(--brand);color:#0c1839}button.secondary{background:var(--quiet);color:var(--ink)}button.danger{background:#8f1d1d;color:#fff;border-color:#fff}button:disabled,input:disabled,select:disabled{opacity:.55;cursor:not-allowed}a{color:var(--primary-color,#2347bd)}a:focus-visible,button:focus-visible,input:focus-visible,select:focus-visible,summary:focus-visible,[tabindex]:focus-visible{outline:3px solid var(--brand);outline-offset:2px}details{border-radius:12px;background:var(--quiet);padding:10px;margin-top:14px}summary{min-height:44px;display:flex;align-items:center;cursor:pointer;font-weight:700}.profiles button{border-radius:999px}.profiles button.selected{border:4px solid var(--ink);padding:5px 13px;box-shadow:0 0 0 2px var(--surface)}.profile-description{margin-top:12px;padding:12px;border:2px solid var(--control-line);border-radius:12px;background:var(--quiet)}.profile-description p{margin:4px 0 0}.progress{height:12px;border-radius:999px;background:var(--quiet);overflow:hidden;border:1px solid var(--line)}.progress span{display:block;height:100%;background:var(--brand)}.counts{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:14px 0}.count{padding:10px;border-radius:12px;background:var(--quiet);overflow-wrap:anywhere}.count strong{display:block;font-size:20px}.notice{padding:12px;border-left:4px solid var(--brand);border-radius:12px;background:var(--quiet);margin:12px 0;overflow-wrap:anywhere}.notice.failure{border-color:var(--error-color,#b42318);color:var(--error-color,#b42318)}code{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;overflow-wrap:anywhere}.table-wrap{max-width:100%;overflow:auto;border:2px solid var(--control-line);border-radius:12px}table{border-collapse:collapse;width:100%;min-width:760px}th,td{text-align:left;padding:10px;border-bottom:1px solid var(--line);vertical-align:top}th button{padding:4px 6px;min-height:44px;background:transparent;color:var(--ink);border-color:transparent}.future select{cursor:not-allowed}.tutorial{columns:2;column-gap:28px}.tutorial section{break-inside:avoid}.tutorial h3{font-size:16px;margin-bottom:5px}
  @media(max-width:900px){.banner{align-items:stretch;flex-direction:column}.banner nav{flex-wrap:wrap}.banner a{flex:1 1 220px}.grid{grid-template-columns:1fr}}
  @media(max-width:760px){.shell{padding:12px}.fields{grid-template-columns:1fr}.card{padding:16px;border-radius:20px}.banner{border-radius:28px}.banner nav{flex-direction:column}.banner a{flex-basis:auto;width:100%}.tutorial{columns:1}.counts{grid-template-columns:repeat(2,1fr)}}
  @media(max-width:360px){.shell{padding:8px}.card{padding:12px;border-radius:12px}.banner{padding:14px;border-radius:20px}.actions button{width:100%}.top{padding:0 8px}.top h1{font-size:18px}.counts{grid-template-columns:1fr 1fr}}
`;

const hardeningText = {
  en: {
    timeline:"Recent operation events (last 8; API retains at most 32)",
    exportEvidence:"Download redacted evidence JSON",
    firmwareFault:"Firmware blocked further reads because transport state is uncertain. Arrange manual maintenance, then check API health again.",
    checkGateway:"Check API only", apiOnly:"Checks API identity and bridge capabilities. Does not issue a Modbus read.",
    healthTitle:"Last observed gateway health", apiEvidence:"API verification", busEvidence:"Last fresh bus response", encryption:"API encryption configured", yes:"Yes", no:"No",
    unchecked:"Not checked", healthChecked:"API check finished. This is not a fresh bus probe.",
    readOnly:"HA identity is inactive or unavailable; reconnect. All active HA users and internal automations may operate physical gateways.", unsupportedProfile:"Unknown or mismatched capability profile. Reload the integration and panel; physical operations are blocked.",
    recovery:"Normal polling recovery", cleanup:"Connection cleanup", attempt:"Attempt", operation:"Operation", budget:"Execution budget (not ETA)", elapsed:"Elapsed", rawRegister:"Register / raw value", rawHelp:"Raw FC03 values are evidence only; engineering-unit decoding is not implied.",
    recoveryStates:{unknown:"Not verified",pending:"Awaiting fresh normal polling",verified:"Fresh normal core polling verified",failed:"Recovery check failed"},
    operationStates:{queued:"Queued",connect:"Connecting",verify_identity:"Checking identity",verify_bridge:"Checking bridge",probe:"Read-only probe",inter_request_delay:"Waiting between reads",recovery:"Checking normal polling",finished:"Finished"},
    history:"Load saved history", historyHelp:"At most 20 terminal snapshots are retained in HA. Interrupted checkpoints are marked failed, never resumed automatically.", yaml:"Generate service YAML", yamlLabel:"Validated range-scan YAML (generation does not execute it)",
    recentSelected:"History selected. Refresh status or results; no scan will be started.",
    checkpoint:"Interrupted checkpoint: subsequent progress is unknown. No scan was resumed.", attention:"Probe processing ended; normal polling recovery is not verified. Inspect the recovery status before another operation.",
    errorCode:"Error code", timeoutMeaning:"Empty addresses normally time out; this does not establish a gateway fault.",
  },
  "zh-Hant": {
    timeline:"近期操作事件（最近 8 筆，API 最多保留 32 筆）",
    exportEvidence:"下載去識別證據 JSON",
    firmwareFault:"韌體因傳輸狀態不明而阻擋後續讀取。請安排人工維護，完成後重新檢查 API 健康。",
    checkGateway:"只檢查 API", apiOnly:"核對 API 身分與橋接能力，不發出 Modbus 讀取。",
    healthTitle:"上次觀測的閘道健康", apiEvidence:"API 身分核對", busEvidence:"最近有效匯流排回應", encryption:"已設定 API 加密", yes:"是", no:"否",
    unchecked:"尚未檢查", healthChecked:"API 檢查完成；這不是新的匯流排探測證據。",
    readOnly:"HA 身分已停用或無法使用，請重新連線。所有啟用中的 HA 使用者及內部自動化皆可操作實機。", unsupportedProfile:"能力設定未知或版本不符。請重載整合與面板；實機操作已阻擋。",
    recovery:"正常輪詢復原", cleanup:"連線清理", attempt:"嘗試次數", operation:"目前操作", budget:"操作時間上限（非預計完成時間）", elapsed:"已耗時", rawRegister:"暫存器／原始值", rawHelp:"原始 FC03 數值僅作證據，並不代表已轉換為工程單位。",
    recoveryStates:{unknown:"尚未驗證",pending:"等待新的正常輪詢",verified:"已驗證新的核心正常輪詢",failed:"復原檢查失敗"},
    operationStates:{queued:"排程中",connect:"連線中",verify_identity:"核對身分",verify_bridge:"核對橋接",probe:"唯讀探測",inter_request_delay:"等候下一次讀取",recovery:"確認正常輪詢",finished:"已結束"},
    history:"載入保存歷程", historyHelp:"HA 最多保存 20 筆終止快照。中斷檢查點會標為失敗，絕不自動重播掃描。", yaml:"產生服務 YAML", yamlLabel:"通過檢查的範圍掃描 YAML（產生不會執行）",
    recentSelected:"已選擇歷程。請重新整理狀態或結果；不會因此開始掃描。",
    checkpoint:"這是中斷檢查點，之後的進度未知；未自動重播任何掃描。", attention:"探測處理已結束，但尚未證實正常輪詢復原；再次操作前請先檢查復原狀態。",
    errorCode:"錯誤代碼", timeoutMeaning:"空位址逾時是正常現象，不足以判定閘道故障。",
  },
};

const en = {
  title: "Modbus Scanner", menu: "Open Home Assistant menu", mock: "SIMULATION — MOCK ONLY",
  physicalTitle: "EXPERIMENTAL — PHYSICAL MODBUS",
  physicalBanner: "This gateway sends real read-only Modbus requests through ESPHome. Scanning pauses polling and can make normal entities temporarily stale. Test address also performs a real read; no registers are written.",
  physicalHelp: "Bridge v1: FC03 holding register, count 1, fixed 700 ms timeout, polling pause required.",
  physicalRange: "This physical bridge supports slave IDs 1–32, inclusive.",
  physicalRegisters: "Enter decimal: 0x6201 = 25089. Allowed: 24833–24838, 24849, 24850, 25089–25091, 25093, 25094.",
  physicalProfiles: "Mock profiles do not apply to physical gateways. Results below must identify their actual provider and gateway.",
  physicalPause: "Required. Firmware drains the current transaction, reads once, then automatically restores polling even if the client disconnects.",
  missingGateway: "Saved gateway is unavailable. Explicitly select an available gateway; no automatic fallback to mock.",
  resultGateway: "Result source (may differ from the next scan selection)",
  banner: "This selected simulated gateway never contacts ESPHome or physical Modbus hardware. Its results are training evidence, not an inventory. Explicitly select an enrolled ESPHome gateway for physical reads.",
  tutorial: "View mock tutorial source", download: "Download mock tutorial", tutorialLinks:"Tutorial and download links", gateway: "Gateway", availableGateway: "Available gateway",
  simulated: "simulated", simulatedGateway:"Simulated RS-485 Gateway", notRefreshed: "not refreshed", gatewayHelp:"Choose a simulated or enrolled physical gateway. A physical selection applies safe bridge defaults and clears old results.", futureDevice: "Selected ESPHome gateway (read-only)", futureUnavailable: "Not applicable to the simulated gateway",
  futureHelp: "This identity summary is intentionally disabled; choose the transport using Available gateway above. The backend verifies the enrolled MAC before any read.", refreshGateways: "Refresh gateways",
  scanRange: "Scan range", startId: "Start Slave ID", startHelp: "Inclusive; Modbus unicast addresses are 1–247.", endId: "End Slave ID", endHelp: "Inclusive and not lower than Start ID.",
  address: "Single test address", addressHelp: "Used only by Test address.", profile: "Mock quick profile", profileHelp: "Choose a deterministic fixture. The selected profile's addresses, outcomes, and terminal state are described below.", quickProfiles: "Mock quick profiles",
  advanced: "Advanced read-only probe settings", probe: "Probe type", deviceIdentification: "Device identification (optional Modbus capability)", holdingRegister: "Holding register read", inputRegister: "Input register read",
  probeHelp: "In simulated mode these probe options do not change the fixture outcome.", registerAddress: "Register address", registerAddressHelp: "Zero-based; relevant to register probes only.", registerCount: "Register count", registerCountHelp: "Number of registers read.",
  timeout: "Timeout (ms)", timeoutHelp: "Per attempt; mock uses it only for the worst-case estimate.", retries: "Retries", retriesHelp: "Additional attempts after the first; mock does not retry.", delay: "Inter-request delay (ms)", delayHelp: "Minimum requested gap; mock has a built-in 10 ms minimum.",
  pause: "Pause normal polling", pauseHelp: "Mock mode has no normal polling. Physical mode requires automatic polling suspension and restoration.", safety: "I understand scans are best-effort and a physical scan can disrupt polling.", start: "Start scan", test: "Test address", cancel: "Cancel",
  statusTitle: "Status and progress", recent: "Recent scan ID (this browser only)", storage: "Preferences and IDs stay in localStorage. Tokens, hosts, frames, replies, and credentials are never stored.", phase: "Phase", noRecent: "No recent scan", noScanId: "No scan ID", progress: "Scan progress", addresses: "addresses", responders: "responders", terminalError: "Terminal error", refreshStatus: "Refresh status", refreshResults: "Refresh results",
  evidence: "Responder evidence", evidenceHelp: "Timeouts are counted but intentionally omitted. A response is not proof of a unique physical device.", tableLabel: "Sortable responder evidence table", noEvidence: "No responder evidence loaded.",
  columns: {address:"Address",outcome:"Outcome",latency_ms:"Latency ms",exception_code:"Exception",vendor:"Vendor",product:"Product",detail:"Detail"},
  interpretation: "Interpretation and troubleshooting", ready: "Ready. Refresh gateways to verify service availability.", correcting: "Correct the highlighted fields.", started: "Scan started.", testStarted: "Address test started.", statusRefreshed: "Status refreshed.", resultsRefreshed: "Results refreshed.", cancelRequested: "Cancellation requested; the current transaction may finish first.", recentSelected: "Recent scan selected. Refresh status or results; server history is memory-only.", serviceUnavailable:"Home Assistant connection is unavailable. Reconnect and retry.", invalidResponse:"Home Assistant returned an empty or invalid service response.", startMissing:"The start response did not include a scan ID.",
  noChosen: "Start a scan or choose a recent scan ID first.", noResultsId: "No scan ID is available for results.", noCancel: "No active scan to cancel.", unknownState: "Unknown or expired scan ID. Stale status and results were cleared; start a new scan or choose another recent ID.",
  gatewayCount: (n)=>`${n} gateway${n===1?"":"s"} available.`, noGateway: "No gateway is available. Reload the integration and inspect Home Assistant logs.", finished: (status)=>`Scan ${status}; results loaded automatically.`, pollingStopped: (error)=>`Status polling stopped: ${error} Use Refresh status to retry.`, terminalLoadFailed: (error)=>`Terminal results failed to load: ${error}`,
  invalidInteger: (a,b)=>`Enter a whole number from ${a} to ${b}.`, orderError: "End ID must be at least Start ID.", safetyError: "Confirm the best-effort scan warning before starting.", gatewayError: "Select an available gateway.",
  sort: (label,direction)=>`Sort by ${label}; ${direction}.`, ascending:"currently ascending, activate for descending", descending:"currently descending, activate for ascending", unsorted:"not sorted, activate for ascending", selected:"Selected",
  statuses:{idle:"idle",running:"running",completed:"completed",cancelled:"cancelled",failed:"failed",unknown:"unknown"},
  outcomes: {identified:"identified",responded:"responded",modbus_exception:"modbus exception",timeout:"timeout",possible_collision:"possible collision",gateway_error:"gateway error"},
  details:{"Valid Modbus response without identity details":"Valid Modbus response without identity details","Valid device-identification response":"Valid device-identification response","CRC-valid Modbus exception; a responder exists but rejected the probe":"CRC-valid Modbus exception; a responder exists but rejected the probe","Inconsistent CRC/framing; duplicate IDs or bus noise are possible":"Inconsistent CRC/framing; duplicate IDs or bus noise are possible"},
  profileNames: {found_default:"Found default",all_offline:"All offline",partial_timeout:"Partial timeout",modbus_exception:"Modbus exception",possible_collision:"Possible collision",gateway_disconnect:"Gateway disconnect"},
  profiles: {
    found_default:"Fixture range 1–12: address 1 identified as WOOWTECH WT-RS485-01; 3 responds; 5 returns exception code 2; 12 identified as Acme Controls ACM-12; all others time out. Expected terminal state: completed.",
    all_offline:"Every address in the selected range times out and no responder row is retained. A timeout never proves absence. Expected terminal state: completed.",
    partial_timeout:"Known fixtures: 2, 11, and 42 respond; 7 and 21 identify as Mock Industries MI-007/MI-021; all other selected addresses time out. Expected terminal state: completed.",
    modbus_exception:"Known fixtures: addresses 4 and 17 return exception code 2; address 9 returns exception code 3; all others time out. Expected terminal state: completed.",
    possible_collision:"Known fixture: address 7 reports inconsistent CRC/framing as possible_collision; all other selected addresses time out. Expected terminal state: completed; uniqueness remains unguaranteed.",
    gateway_disconnect:"Address 1 identifies as WOOWTECH, address 3 responds, other earlier addresses time out, then the gateway disconnects at max(start + 3, 4). Expected terminal state: failed with partial evidence.",
  },
  help: {
    identified:"Valid device-identification evidence, not guaranteed uniqueness.", responded:"A generic valid response proves activity at that moment only.", modbus_exception:"A CRC-valid exception is responder evidence; check function and register support.", timeout:"Could mean offline, wrong serial settings, unsupported probe, wiring, latency, or congestion—never proven absence.", possible_collision:"Inconsistent framing may indicate duplicate IDs, noise, termination, or bias problems.", gateway_error:"Refresh gateways, inspect integration logs, then retry. A busy error means another scan owns this provider/gateway pair.", unknown:"Server history is memory-only and bounded to recent terminal scans. Reload/restart can invalidate browser-stored IDs.", network:"Reconnect Home Assistant, verify the config entry is loaded, and use manual refresh. Polling never overlaps and stops after disconnection."
  }, unknownHeading:"Unknown scan ID", networkHeading:"Network/service errors", dash:"—"
};

const zh = {
  ...en, title:"Modbus 掃描器",menu:"開啟 Home Assistant 選單",mock:"模擬模式 — 僅限模擬",
  physicalTitle:"實驗功能 — 實體 MODBUS",
  physicalBanner:"目前會透過 ESPHome 發送真實的 Modbus 唯讀請求。掃描會暫停輪詢，可能使一般實體資料暫時過期。「測試位址」也會發出真實讀取；不寫入暫存器。",
  physicalHelp:"橋接 v1：FC03 保持暫存器、數量固定 1、逾時固定 700 毫秒、必須暫停輪詢。",
  physicalRange:"此實體橋接支援從站 1–32，包含起訖位址。",
  physicalRegisters:"請輸入十進位：0x6201 = 25089。允許：24833–24838、24849、24850、25089–25091、25093、25094。",
  physicalProfiles:"模擬情境不適用於實體閘道。下方結果會另行標明實際提供者與閘道。",
  physicalPause:"必要設定。韌體等候當前交易結束，單次讀取後自動恢復輪詢；客戶端斷線也會恢復。",
  missingGateway:"儲存的閘道目前無法使用。請明確選擇可用閘道，不會自動退回模擬。",
  resultGateway:"結果來源（可能與下一次掃描選擇不同）",
  banner:"目前選取的是模擬閘道，不會連線 ESPHome 或實體 Modbus。這些是訓練資料，不是設備清冊。若要真實讀取，請明確選擇已登錄的 ESPHome 閘道。",tutorial:"查看模擬版教學原始檔",download:"下載模擬版教學",tutorialLinks:"教學與下載連結",
  gateway:"閘道",availableGateway:"可用閘道",simulated:"模擬",simulatedGateway:"模擬 RS-485 閘道",notRefreshed:"尚未重新整理",gatewayHelp:"選擇模擬或已登錄的實體閘道。選擇真機會帶入橋接預設值並清除舊結果。",futureDevice:"已選 ESPHome 閘道（唯讀）",futureUnavailable:"模擬閘道不適用",futureHelp:"此處只顯示識別資訊，請在上方「可用閘道」選擇連線對象。後端會在讀取前核對登錄的 MAC。",refreshGateways:"重新整理閘道",
  scanRange:"掃描範圍",startId:"起始從站 ID",startHelp:"包含此值；Modbus 單播位址為 1–247。",endId:"結束從站 ID",endHelp:"包含此值，且不得小於起始 ID。",address:"單一測試位址",addressHelp:"僅供「測試位址」使用。",profile:"模擬快速情境",profileHelp:"選擇固定測試情境；下方會詳述所選情境的位址、結果及預期終止狀態。",quickProfiles:"模擬快速情境",
  advanced:"進階唯讀探測設定",probe:"探測類型",deviceIdentification:"裝置識別（選用的 Modbus 能力）",holdingRegister:"讀取保持暫存器",inputRegister:"讀取輸入暫存器",probeHelp:"在模擬模式中，選擇不同探測類型不會改變固定情境的結果。",registerAddress:"暫存器位址",registerAddressHelp:"從零起算；僅適用暫存器探測。",registerCount:"暫存器數量",registerCountHelp:"要讀取的暫存器數量。",timeout:"逾時（毫秒）",timeoutHelp:"每次嘗試的期限；模擬僅用於最壞時間估算。",retries:"重試次數",retriesHelp:"第一次之後的額外嘗試；模擬不會重試。",delay:"請求間隔（毫秒）",delayHelp:"要求的最短間隔；模擬內建至少 10 毫秒。",pause:"暫停一般輪詢",pauseHelp:"模擬模式沒有一般輪詢；實體模式必須自動暫停及恢復輪詢。",safety:"我了解掃描僅提供盡力而為的結果，且實體掃描可能干擾輪詢。",start:"開始掃描",test:"測試位址",cancel:"取消",
  statusTitle:"狀態與進度",recent:"最近掃描 ID（僅此瀏覽器）",storage:"偏好設定和 ID 保留在 localStorage。永不儲存權杖、主機、訊框、回覆或認證資料。",phase:"階段",noRecent:"沒有最近掃描",noScanId:"沒有掃描 ID",progress:"掃描進度",addresses:"個位址",responders:"個回應者",terminalError:"終止錯誤",refreshStatus:"重新整理狀態",refreshResults:"重新整理結果",
  evidence:"回應者證據",evidenceHelp:"逾時會計數但刻意不列入表格。收到回應並不能證明是唯一的實體裝置。",tableLabel:"可排序的回應者證據表格",noEvidence:"尚未載入回應者證據。",columns:{address:"位址",outcome:"結果",latency_ms:"延遲（毫秒）",exception_code:"例外",vendor:"廠商",product:"產品",detail:"詳細資料"},interpretation:"判讀與疑難排解",
  ready:"準備就緒。請重新整理閘道以確認服務可用。",correcting:"請修正標示的欄位。",started:"掃描已開始。",testStarted:"位址測試已開始。",statusRefreshed:"狀態已重新整理。",resultsRefreshed:"結果已重新整理。",cancelRequested:"已要求取消；目前交易可能會先完成。",recentSelected:"已選擇最近掃描。請重新整理狀態或結果；伺服器歷程僅存於記憶體。",serviceUnavailable:"Home Assistant 連線無法使用。請重新連線後再試。",invalidResponse:"Home Assistant 回傳空白或無效的服務回應。",startMissing:"開始回應未包含掃描 ID。",noChosen:"請先開始掃描或選擇最近的掃描 ID。",noResultsId:"沒有可用於結果的掃描 ID。",noCancel:"沒有可取消的進行中掃描。",unknownState:"掃描 ID 未知或已過期。已清除舊狀態與結果；請開始新掃描或選擇其他最近 ID。",gatewayCount:(n)=>`有 ${n} 個閘道可用。`,noGateway:"沒有可用閘道。請重新載入整合並檢查 Home Assistant 記錄。",finished:(status)=>`掃描已${status === "completed" ? "完成" : "終止"}；已自動載入結果。`,pollingStopped:(error)=>`狀態輪詢已停止：${error} 請用「重新整理狀態」重試。`,terminalLoadFailed:(error)=>`無法載入終止結果：${error}`,
  invalidInteger:(a,b)=>`請輸入 ${a} 到 ${b} 的整數。`,orderError:"結束 ID 必須大於或等於起始 ID。",safetyError:"開始前請確認盡力而為掃描警告。",gatewayError:"請選擇可用閘道。",sort:(label,direction)=>`依${label}排序；${direction}。`,ascending:"目前升冪，啟用後改為降冪",descending:"目前降冪，啟用後改為升冪",unsorted:"尚未排序，啟用後使用升冪",selected:"已選取",
  statuses:{idle:"閒置",running:"執行中",completed:"已完成",cancelled:"已取消",failed:"失敗",unknown:"未知"},outcomes:{identified:"已識別",responded:"有回應",modbus_exception:"Modbus 例外",timeout:"逾時",possible_collision:"可能衝突",gateway_error:"閘道錯誤"},details:{"Valid Modbus response without identity details":"有效的 Modbus 回應，但沒有識別詳細資料","Valid device-identification response":"有效的裝置識別回應","CRC-valid Modbus exception; a responder exists but rejected the probe":"CRC 有效的 Modbus 例外；有回應者，但拒絕此探測","Inconsistent CRC/framing; duplicate IDs or bus noise are possible":"CRC／訊框不一致；可能是 ID 重複或匯流排雜訊"},profileNames:{found_default:"預設找到裝置",all_offline:"全部離線",partial_timeout:"部分逾時",modbus_exception:"Modbus 例外",possible_collision:"可能衝突",gateway_disconnect:"閘道中斷"},
  profiles:{found_default:"測試範圍 1–12：位址 1 識別為 WOOWTECH WT-RS485-01；3 有回應；5 回傳例外碼 2；12 識別為 Acme Controls ACM-12；其餘逾時。預期終止狀態：完成。",all_offline:"所選範圍的每個位址都逾時，且不保留任何回應者資料列。逾時絕不證明裝置不存在。預期終止狀態：完成。",partial_timeout:"固定資料：2、11、42 有回應；7、21 識別為 Mock Industries MI-007／MI-021；其餘所選位址逾時。預期終止狀態：完成。",modbus_exception:"固定資料：位址 4、17 回傳例外碼 2；位址 9 回傳例外碼 3；其餘逾時。預期終止狀態：完成。",possible_collision:"固定資料：位址 7 因 CRC／訊框不一致回報「可能衝突」；其餘所選位址逾時。預期終止狀態：完成，但不保證唯一性。",gateway_disconnect:"位址 1 識別為 WOOWTECH、位址 3 有回應、前面的其他位址逾時，接著閘道於 max(起始 + 3, 4) 中斷。預期終止狀態：失敗，並保留部分證據。"},
  help:{identified:"有效的裝置識別證據，但不保證唯一性。",responded:"一般有效回應只證明該時刻有活動。",modbus_exception:"CRC 有效的例外也是回應者證據；請檢查功能碼與暫存器支援。",timeout:"可能是離線、序列設定錯誤、不支援探測、配線、延遲或壅塞，絕不代表已證明不存在。",possible_collision:"訊框不一致可能表示 ID 重複、雜訊、終端電阻或偏壓問題。",gateway_error:"重新整理閘道、檢查整合記錄後再試。忙碌錯誤表示另一掃描占用同一提供者／閘道。",unknown:"伺服器歷程只存於記憶體，並僅保留有限的最近終止掃描。重新載入或重啟會使瀏覽器儲存的 ID 失效。",network:"重新連線 Home Assistant、確認設定項目已載入，再手動重新整理。輪詢不會重疊，且中斷連線後會停止。"},unknownHeading:"未知掃描 ID",networkHeading:"網路／服務錯誤"
};

function languageFor(hass) {
  const language = hass?.locale?.language || hass?.language || "en";
  return String(language).toLowerCase().startsWith("zh") ? "zh-Hant" : "en";
}
function stringsFor(hass) {
  const language = languageFor(hass);
  const base = language === "zh-Hant" ? zh : en;
  const additions = hardeningText[language];
  return {...base, ...additions, help:{...base.help, unknown:additions.historyHelp}};
}

// Generated by tools/generate_profiles.py; do not edit.
const freeze = value => { if (value && typeof value === "object") {Object.values(value).forEach(freeze); Object.freeze(value);} return value; };
const PHYSICAL_PROFILE = freeze({
  "profile_id": "guanjie-ind17-fc03",
  "profile_version": 1,
  "bridge_version": 1,
  "read_only": true,
  "limits": {
    "slave_min": 1,
    "slave_max": 32,
    "register_count": 1,
    "timeout_ms": 700,
    "retries_max": 5,
    "inter_request_delay_max_ms": 5000,
    "polling_pause_required": true
  },
  "allowed_registers": [
    25089,
    25090,
    25091,
    25093,
    25094,
    24837,
    24833,
    24834,
    24835,
    24836,
    24838,
    24849,
    24850
  ],
  "defaults": {
    "start_id": 1,
    "end_id": 3,
    "address": 1,
    "probe_type": "holding_register",
    "register_address": 25089,
    "register_count": 1,
    "timeout_ms": 700,
    "retries": 0,
    "inter_request_delay_ms": 250,
    "pause_normal_polling": true
  },
  "profile_hash": "1620942b806d6d958a6989d0c96c1a6a349887014d821c1b4336a95717269b85"
});

const DOMAIN = "woow_esphome_modbus_scanner";
const SERVICES = Object.freeze([
  "check_gateway", "get_history",
  "list_gateways",
  "start_scan",
  "get_scan_status",
  "get_scan_results",
  "cancel_scan",
  "test_address",
]);
const PROFILES = Object.freeze([
  "found_default", "all_offline", "partial_timeout", "modbus_exception",
  "possible_collision", "gateway_disconnect",
]);
const OUTCOMES = Object.freeze([
  "identified", "responded", "modbus_exception", "timeout",
  "possible_collision", "gateway_error",
]);
const PROBE_TYPES = Object.freeze(["device_identification", "holding_register", "input_register"]);
const DEFAULTS = Object.freeze({
  provider: "mock", gateway_id: "mock:rs485-gateway", start_id: 1, end_id: 12,
  address: 1, probe_type: "device_identification", register_address: 0,
  register_count: 1, timeout_ms: 500, retries: 1,
  inter_request_delay_ms: 100, pause_normal_polling: false,
  mock_profile: "found_default", safety_confirmed: false,
});
const INTEGER_BOUNDS = Object.freeze({
  start_id: [1, 247], end_id: [1, 247], address: [1, 247],
  register_address: [0, 65535], register_count: [1, 125],
  timeout_ms: [10, 10000], retries: [0, 5], inter_request_delay_ms: [0, 5000],
});
const PHYSICAL_REGISTERS = PHYSICAL_PROFILE.allowed_registers;
const PHYSICAL_DEFAULTS = PHYSICAL_PROFILE.defaults;
const PHYSICAL_GATEWAY = /^esphome:[0-9a-f]{12}$/;
function boundsFor(form) {
  const l = PHYSICAL_PROFILE.limits;
  return form.provider === "esphome" ? {...INTEGER_BOUNDS, start_id:[l.slave_min,l.slave_max], end_id:[l.slave_min,l.slave_max], address:[l.slave_min,l.slave_max], register_count:[l.register_count,l.register_count], timeout_ms:[l.timeout_ms,l.timeout_ms], retries:[0,l.retries_max], inter_request_delay_ms:[0,l.inter_request_delay_max_ms]} : INTEGER_BOUNDS;
}
function selectGateway(form, gateway) {
  const defaults = gateway.provider === "esphome" ? PHYSICAL_DEFAULTS : DEFAULTS;
  return {...form, ...defaults, provider:gateway.provider, gateway_id:gateway.gateway_id, safety_confirmed:false};
}
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

function normalizeResponse(value) {
  if (value && typeof value === "object" && value.response && typeof value.response === "object") return value.response;
  return value;
}

function validateForm(form, single = false, text = {}) {
  const errors = {};
  const names = single ? ["address", "register_address", "register_count", "timeout_ms", "retries", "inter_request_delay_ms"] : Object.keys(INTEGER_BOUNDS).filter((name) => name !== "address");
  for (const name of names) {
    const number = Number(form[name]);
    const [minimum, maximum] = boundsFor(form)[name];
    const raw = form[name];
    const integer = typeof raw === "number" || (typeof raw === "string" && /^[+-]?\d+$/.test(raw));
    if (!integer || !Number.isInteger(number) || number < minimum || number > maximum) {
      errors[name] = text.integer ? text.integer(minimum, maximum) : `Enter a whole number from ${minimum} to ${maximum}.`;
    }
  }
  if (form.provider === "esphome") {
    const message = text.physical || "Physical bridge requires FC03, one allowed register, 700 ms timeout and polling pause.";
    if (form.probe_type !== "holding_register") errors.probe_type = message;
    if (!PHYSICAL_REGISTERS.includes(Number(form.register_address))) errors.register_address = message;
    if (form.pause_normal_polling !== true) errors.pause_normal_polling = message;
  }
  if (!single && Number(form.start_id) > Number(form.end_id)) errors.end_id = text.order || "End ID must be at least Start ID.";
  if (!single && form.safety_confirmed !== true) errors.safety_confirmed = text.safety || "Confirm the best-effort scan warning before starting.";
  if (!form.gateway_id) errors.gateway_id = text.gateway || "Select an available gateway.";
  return errors;
}

function sharedPayload(form) {
  return {
    provider: form.provider, gateway_id: form.gateway_id, probe_type: form.probe_type,
    register_address: Number(form.register_address), register_count: Number(form.register_count),
    timeout_ms: Number(form.timeout_ms), retries: Number(form.retries),
    inter_request_delay_ms: Number(form.inter_request_delay_ms),
    pause_normal_polling: form.pause_normal_polling === true,
    ...(form.provider === "mock" ? {mock_profile: form.mock_profile} : {}),
  };
}
function startPayload(form) {
  return {...sharedPayload(form), start_id: Number(form.start_id), end_id: Number(form.end_id), safety_confirmed: true};
}
function testPayload(form) { return {...sharedPayload(form), address: Number(form.address)}; }
function supportedGateway(gateway) {
  return gateway?.provider === "mock" || (gateway?.provider === "esphome" && gateway.profile?.profile_hash === PHYSICAL_PROFILE.profile_hash);
}
function serviceYaml(form) {
  if (Object.keys(validateForm(form)).length) throw new Error("Confirm the warning and correct the scan parameters first.");
  const lines = Object.entries(startPayload(form)).map(([key, value]) => `  ${key}: ${JSON.stringify(value)}`);
  return `action: ${DOMAIN}.start_scan\ndata:\n${lines.join("\n")}\n`;
}

/** Deliberately excludes gateway identity, vendor strings, free text and credentials. */
function evidenceExport(status, results) {
  const integer = (value, max) => Number.isInteger(value) && value >= 0 && value <= max ? value : null;
  return {
    schema_version:1, source:DOMAIN, best_effort:true, uniqueness_guaranteed:false,
    provider:["mock","esphome"].includes(results?.provider) ? results.provider : "unknown",
    status:["running","completed","cancelled","failed"].includes(results?.status) ? results.status : "unknown",
    recovery_status:["unknown","pending","verified","failed"].includes(status?.recovery_status) ? status.recovery_status : "unknown",
    outcome_counts:Object.fromEntries(OUTCOMES.map((name) => [name,integer(results?.outcome_counts?.[name],247) ?? 0])),
    responders:(results?.responders || []).slice(0,247).map((row) => ({
      address:integer(row.address,247), outcome:OUTCOMES.includes(row.outcome) ? row.outcome : "unknown",
      latency_ms:integer(row.latency_ms,10000), exception_code:integer(row.exception_code,255),
      register_address:integer(row.register_address,65535), raw_value:integer(row.raw_value,65535),
      attempts:integer(row.attempts,6),
    })),
    privacy:"Identities and free-text fields omitted; numeric register evidence retained.",
  };
}

/** Return only validated, non-secret preferences from untrusted browser storage. */
function sanitizePreferences(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {form: {...DEFAULTS}, advancedOpen: false};
  const source = value.form;
  if (!source || typeof source !== "object" || Array.isArray(source) || Object.getPrototypeOf(source) !== Object.prototype) {
    return {form: {...DEFAULTS}, advancedOpen: value.advancedOpen === true};
  }
  const form = {...DEFAULTS};
  for (const [name, [minimum, maximum]] of Object.entries(INTEGER_BOUNDS)) {
    if (typeof source[name] === "number" && Number.isInteger(source[name]) && source[name] >= minimum && source[name] <= maximum) form[name] = source[name];
  }
  if (PROBE_TYPES.includes(source.probe_type)) form.probe_type = source.probe_type;
  if (PROFILES.includes(source.mock_profile)) form.mock_profile = source.mock_profile;
  if (source.pause_normal_polling === true || source.pause_normal_polling === false) form.pause_normal_polling = source.pause_normal_polling;
  // A stored acknowledgement is not consent for a new browser session.
  form.safety_confirmed = false;
  if (source.provider === "esphome") {
    form.provider = "esphome";
    form.gateway_id = typeof source.gateway_id === "string" && PHYSICAL_GATEWAY.test(source.gateway_id) ? source.gateway_id : "";
    // Migrate old incompatible preferences, without silently changing provider.
    for (const key of ["probe_type", "register_count", "timeout_ms", "pause_normal_polling"]) form[key] = PHYSICAL_DEFAULTS[key];
    if (!PHYSICAL_REGISTERS.includes(form.register_address)) form.register_address = PHYSICAL_DEFAULTS.register_address;
    for (const key of ["start_id", "end_id", "address"]) if (form[key] > PHYSICAL_PROFILE.limits.slave_max) form[key] = PHYSICAL_DEFAULTS[key];
    if (form.start_id > form.end_id) {form.start_id = PHYSICAL_DEFAULTS.start_id; form.end_id = PHYSICAL_DEFAULTS.end_id;}
  }
  return {form, advancedOpen: value.advancedOpen === true};
}

function sanitizeRecent(value) {
  if (!Array.isArray(value)) return [];
  return [...new Set(value.filter((item) => typeof item === "string" && UUID.test(item)))].slice(0, 10);
}

function safePreferences(form, advancedOpen = false) {
  const values = Object.fromEntries(Object.keys(DEFAULTS).map((key) => {
    const value = form[key];
    return [key, key in INTEGER_BOUNDS && typeof value === "string" && /^[+-]?\d+$/.test(value) ? Number(value) : value];
  }));
  return sanitizePreferences({form: values, advancedOpen});
}

function errorMessage(error) {
  if (!error) return "Unknown error.";
  if (typeof error === "string") return error;
  return error.message || error.body?.message || error.error?.message || "Home Assistant did not return a usable response.";
}

const STORAGE_KEY = "woow-esphome-modbus-scanner.preferences.v1";
const RECENT_KEY = "woow-esphome-modbus-scanner.recent.v1";
const TERMINAL = new Set(["completed", "cancelled", "failed"]);
const TUTORIAL = "https://github.com/WOOWTECH/Woow_ha_esphome_modbus_scanner/blob/main/docs/tutorial/woow-esphome-modbus-scanner-v0.2.0-zh-TW.html";
const DOWNLOAD = "https://github.com/WOOWTECH/Woow_ha_esphome_modbus_scanner/releases/download/v0.2.0/woow-esphome-modbus-scanner-v0.2.0-zh-TW.html";

class WoowEsphomeModbusScannerPanel extends i {
  static styles = panelStyles;
  static properties = {
    hass: {attribute: false}, narrow: {type: Boolean}, panel: {attribute: false},
    _form: {state: true}, _gateways: {state: true}, _status: {state: true},
    _results: {state: true}, _errors: {state: true}, _message: {state: true},
    _busy: {state: true}, _recent: {state: true}, _sort: {state: true},
    _advancedOpen: {state: true}, _yaml: {state: true}, _savedHistory: {state: true},
  };

  constructor() {
    super();
    const saved = sanitizePreferences(this._read(STORAGE_KEY, {}));
    this._form = saved.form;
    this._advancedOpen = saved.advancedOpen;
    this._recent = sanitizeRecent(this._read(RECENT_KEY, []));
    this._gateways = [];
    this._yaml = "";
    this._savedHistory = [];
    this._status = null;
    this._results = null;
    this._errors = {};
    this._message = "";
    this._busy = "";
    this._sort = {key: "address", direction: 1};
    this._timer = undefined;
    this._pollToken = 0;
    this._operationGeneration = 0;
    this._currentScanId = "";
    this._loaded = false;
  }

  get _text() { return stringsFor(this.hass); }
  connectedCallback() {
    super.connectedCallback();
    if (this.hass && !this._loaded) this._loadGateways();
  }
  disconnectedCallback() {
    this._operationGeneration += 1;
    this._currentScanId = "";
    this._stopPolling();
    super.disconnectedCallback();
  }
  updated(changed) {
    if (changed.has("hass")) {
      if (!this.hass) {
        this._operationGeneration += 1;
        this._currentScanId = "";
        this._stopPolling();
      } else if (!this._loaded) this._loadGateways();
    }
  }
  _read(key, fallback) {
    try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch (_error) { return fallback; }
  }
  _persist() {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(safePreferences(this._form, this._advancedOpen))); } catch (_error) { /* optional */ }
  }
  _remember(scanId) {
    this._recent = sanitizeRecent([scanId, ...this._recent]);
    try { localStorage.setItem(RECENT_KEY, JSON.stringify(this._recent)); } catch (_error) { /* optional */ }
  }
  _selectGateway(gatewayId) {
    if (this._busy || this._status?.status === "running") return;
    const gateway = this._gateways.find((item) => item.gateway_id === gatewayId);
    if (!gateway) return;
    this._operationGeneration += 1;
    this._stopPolling();
    this._currentScanId = "";
    this._status = null;
    this._results = null;
    this._message = "";
    this._errors = {};
    this._yaml = "";
    this._form = selectGateway(this._form, gateway);
    if (gateway.provider === "esphome") this._advancedOpen = true;
    this._persist();
  }
  _set(name, value) {
    this._yaml = "";
    this._form = {...this._form, [name]: value};
    this._errors = {...this._errors, [name]: undefined};
    this._persist();
  }
  async _call(service, data = {}) {
    if (!SERVICES.includes(service)) throw new Error(`Unsupported scanner service: ${service}`);
    if (!this.hass?.callService) throw new Error(this._text.serviceUnavailable);
    const response = await this.hass.callService(DOMAIN, service, data, undefined, undefined, true);
    const normalized = normalizeResponse(response);
    if (!normalized || typeof normalized !== "object") throw new Error(this._text.invalidResponse);
    return normalized;
  }
  async _action(name, work) {
    if (this._busy) return;
    this._busy = name;
    this._message = "";
    try { await work(); }
    catch (error) { this._message = this._localError(error); }
    finally { this._busy = ""; }
  }
  _localError(error) {
    const message = errorMessage(error);
    const t = this._text;
    if (/unauthorized|permission denied/i.test(message)) return t.readOnly;
    if (/Bridge v1 supports|ESPHome bridge v1/i.test(message)) return t.physicalHelp;
    if (/connection lost/i.test(message)) return `${t.networkHeading}: ${t.help.network}`;
    if (/unknown scan id/i.test(message)) return t.unknownState;
    if (/simulated gateway disconnected| is busy/i.test(message)) return t.help.gateway_error;
    return message;
  }
  async _loadGateways() {
    return this._action("gateways", async () => {
      const payload = await this._call("list_gateways");
      if (!Array.isArray(payload.gateways)) throw new Error(this._text.noGateway);
      this._gateways = payload.gateways;
      this._loaded = true;
      // Never silently replace a saved physical gateway with mock mode.
      const available = this._gateways.some((item) => item.gateway_id === this._form.gateway_id && item.provider === this._form.provider);
      this._message = !available ? this._text.missingGateway : this._text.gatewayCount(this._gateways.length);
    });
  }
  async _checkGateway() {
    if (this._status?.status === "running") return;
    const gateway = this._gateways.find((g) => g.gateway_id === this._form.gateway_id);
    if (gateway?.provider !== "esphome" || gateway.can_operate !== true) return;
    const generation = this._operationGeneration;
    return this._action("check", async () => {
      const result = await this._call("check_gateway", {gateway_id:gateway.gateway_id});
      if (generation !== this._operationGeneration || !this.isConnected) return;
      this._gateways = this._gateways.map((g) => g.gateway_id === gateway.gateway_id ? {...g, health:result.health} : g);
      this._message = this._text.healthChecked;
    });
  }
  async _loadHistory() {
    const generation = this._operationGeneration;
    return this._action("history", async () => {
      const result = await this._call("get_history");
      if (generation !== this._operationGeneration || !this.isConnected) return;
      if (!Array.isArray(result.scans)) throw new Error(this._text.invalidResponse);
      this._savedHistory = result.scans.slice(0,20);
      for (const status of [...this._savedHistory].reverse()) this._remember(status.scan_id);
      this._message = this._text.historyHelp;
    });
  }
  _downloadEvidence() {
    if (!this._results) return;
    const blob = new Blob([JSON.stringify(evidenceExport(this._status, this._results), null, 2)], {type:"application/json"});
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url; link.download = "modbus-scan-evidence.json";
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  _showYaml() {
    try { this._yaml = serviceYaml(this._form); }
    catch (_error) { this._message = this._text.correcting + " " + this._text.safetyError; }
  }
  async _start(single = false) {
    if (this._busy || this._status?.status === "running") return;
    const t = this._text;
    const errors = validateForm(this._form, single, {integer:t.invalidInteger, order:t.orderError, safety:t.safetyError, gateway:t.gatewayError, physical:t.physicalHelp});
    if (!this._gateways.some((item) => item.gateway_id === this._form.gateway_id && item.provider === this._form.provider)) errors.gateway_id = t.missingGateway;
    const gateway = this._gateways.find((g) => g.gateway_id === this._form.gateway_id);
    if (gateway && !supportedGateway(gateway)) errors.gateway_id = t.unsupportedProfile;
    if (gateway?.health?.firmware_state?.fault) errors.gateway_id = t.firmwareFault;
    if (gateway?.provider === "esphome" && gateway.can_operate !== true) errors.gateway_id = t.readOnly;
    this._errors = errors;
    if (Object.keys(errors).length) {
      this._message = t.correcting;
      await this.updateComplete;
      const order = ["gateway", "start_id", "end_id", "address", "register_address", "register_count", "timeout_ms", "retries", "inter_request_delay_ms", "safety"];
      this.renderRoot.querySelector(`#${order.find((id) => errors[id === "gateway" ? "gateway_id" : id === "safety" ? "safety_confirmed" : id])}`)?.focus();
      return;
    }
    const generation = ++this._operationGeneration;
    this._currentScanId = "";
    this._stopPolling();
    return this._action(single ? "test" : "start", async () => {
      this._results = null;
      const payload = await this._call(single ? "test_address" : "start_scan", single ? testPayload(this._form) : startPayload(this._form));
      if (generation !== this._operationGeneration || !this.isConnected) return;
      if (!payload.scan_id) throw new Error(t.startMissing);
      this._currentScanId = payload.scan_id;
      this._status = payload;
      this._remember(payload.scan_id);
      this._message = single ? t.testStarted : t.started;
      if (TERMINAL.has(payload.status || payload.phase)) await this._loadResults(payload.scan_id, true, generation);
      else this._schedulePoll(payload.scan_id, generation);
    });
  }
  _stopPolling() {
    this._pollToken += 1;
    if (this._timer !== undefined) clearTimeout(this._timer);
    this._timer = undefined;
  }
  _isCurrent(scanId, generation) { return generation === this._operationGeneration && scanId === this._currentScanId && this.isConnected; }
  _schedulePoll(scanId, generation = this._operationGeneration) {
    if (!this._isCurrent(scanId, generation)) return;
    const token = ++this._pollToken;
    this._timer = setTimeout(() => this._poll(scanId, token, generation), 1000);
  }
  _isUnknown(error) { return /unknown(?: or expired)? scan(?: id)?/i.test(errorMessage(error)); }
  _handleUnknown(error, scanId, generation) {
    if (!this._isUnknown(error) || !this._isCurrent(scanId, generation)) return false;
    this._stopPolling();
    this._status = {scan_id: scanId, status: "unknown", phase: "unknown", progress_percent: 0, outcome_counts: {}};
    this._results = null;
    this._message = this._text.unknownState;
    return true;
  }
  async _poll(scanId, token, generation) {
    this._timer = undefined;
    if (token !== this._pollToken || !this._isCurrent(scanId, generation) || !this.hass) return;
    try {
      const status = await this._call("get_scan_status", {scan_id: scanId});
      if (token !== this._pollToken || !this._isCurrent(scanId, generation) || status.scan_id && status.scan_id !== scanId) return;
      this._status = status;
      if (TERMINAL.has(status.status || status.phase)) {
        this._stopPolling();
        await this._loadResults(scanId, true, generation);
      } else this._timer = setTimeout(() => this._poll(scanId, token, generation), 1000);
    } catch (error) {
      if (this._handleUnknown(error, scanId, generation)) return;
      if (token === this._pollToken && this._isCurrent(scanId, generation)) {
        this._stopPolling();
        this._message = this._text.pollingStopped(this._localError(error));
      }
    }
  }
  _chosenId() { return this._currentScanId || this._status?.scan_id || this._recent[0] || ""; }
  async _refreshStatus() {
    const scanId = this._chosenId();
    if (!scanId) { this._message = this._text.noChosen; return; }
    this._stopPolling();
    if (!this._currentScanId) this._currentScanId = scanId;
    const generation = this._operationGeneration;
    return this._action("status", async () => {
      try {
        const payload = await this._call("get_scan_status", {scan_id: scanId});
        if (!this._isCurrent(scanId, generation) || payload.scan_id && payload.scan_id !== scanId) return;
        this._status = payload;
        this._message = this._text.statusRefreshed;
        if (TERMINAL.has(payload.status || payload.phase)) await this._loadResults(scanId, true, generation);
        else this._schedulePoll(scanId, generation);
      } catch (error) {
        if (!this._isCurrent(scanId, generation)) return;
        if (!this._handleUnknown(error, scanId, generation)) throw error;
      }
    });
  }
  async _loadResults(scanId = this._chosenId(), automatic = false, generation = this._operationGeneration) {
    if (!scanId) { this._message = this._text.noResultsId; return; }
    if (!this._currentScanId) this._currentScanId = scanId;
    const load = async () => {
      try {
        const results = await this._call("get_scan_results", {scan_id: scanId});
        if (!this._isCurrent(scanId, generation) || results.scan_id && results.scan_id !== scanId) return;
        this._results = results;
        this._message = automatic ? this._text.finished(results.status || "finished") : this._text.resultsRefreshed;
      } catch (error) {
        if (!this._isCurrent(scanId, generation)) return;
        if (!this._handleUnknown(error, scanId, generation)) throw error;
      }
    };
    if (automatic) return load().catch((error) => { if (this._isCurrent(scanId, generation)) this._message = this._text.terminalLoadFailed(this._localError(error)); });
    return this._action("results", load);
  }
  async _cancel() {
    const scanId = this._chosenId();
    if (!scanId) { this._message = this._text.noCancel; return; }
    this._stopPolling();
    const generation = this._operationGeneration;
    return this._action("cancel", async () => {
      try {
        const status = await this._call("cancel_scan", {scan_id: scanId});
        if (!this._isCurrent(scanId, generation) || status.scan_id && status.scan_id !== scanId) return;
        this._status = status;
        this._message = this._text.cancelRequested;
        if (!TERMINAL.has(status.status || status.phase)) this._schedulePoll(scanId, generation);
        else await this._loadResults(scanId, true, generation);
      } catch (error) {
        if (!this._isCurrent(scanId, generation)) return;
        if (!this._handleUnknown(error, scanId, generation)) throw error;
      }
    });
  }
  _selectRecent(event) {
    const scanId = event.target.value;
    if (!scanId) return;
    this._operationGeneration += 1;
    this._stopPolling();
    this._currentScanId = scanId;
    this._status = {scan_id: scanId, status: "unknown", phase: "unknown"};
    this._results = null;
    this._message = this._text.recentSelected;
  }
  _sortBy(key) { this._sort = this._sort.key === key ? {key, direction: -this._sort.direction} : {key, direction: 1}; }
  _detail(value) { return this._text.details[value] || value; }
  _responders() {
    const rows = [...(this._results?.responders || [])];
    const {key, direction} = this._sort;
    return rows.sort((a, b) => {
      const value = (row) => key === "vendor" || key === "product" ? row.identity?.[key] || "" : row[key] ?? "";
      return String(value(a)).localeCompare(String(value(b)), undefined, {numeric: true}) * direction;
    });
  }
  _field(name, label, min, max, help) {
    [min, max] = boundsFor(this._form)[name] || [min, max];
    const fixed = this._form.provider === "esphome" && (name === "register_count" || name === "timeout_ms");
    const invalid = Boolean(this._errors[name]);
    return b`<div class="field"><label for=${name}>${label}</label><input id=${name} type="number" min=${min} max=${max} ?readonly=${fixed} .value=${String(this._form[name])} @input=${(event) => this._set(name, event.target.value)} aria-describedby="${name}-help${invalid ? ` ${name}-error` : ""}" aria-invalid=${invalid ? "true" : "false"}><small id="${name}-help">${help}</small>${invalid ? b`<small class="error" id="${name}-error">${this._errors[name]}</small>` : A}</div>`;
  }
  _sortHeader(key, label) {
    const active = this._sort.key === key;
    const direction = active ? (this._sort.direction > 0 ? this._text.ascending : this._text.descending) : this._text.unsorted;
    return b`<th scope="col" aria-sort=${active ? (this._sort.direction > 0 ? "ascending" : "descending") : "none"}><button @click=${() => this._sortBy(key)} aria-label=${this._text.sort(label, direction)}>${label}${active ? (this._sort.direction > 0 ? " ↑" : " ↓") : ""}</button></th>`;
  }
  _menu() { this.dispatchEvent(new CustomEvent("hass-toggle-menu", {bubbles: true, composed: true})); }

  render() {
    const t = this._text;
    const phase = this._status?.status || this._status?.phase || "idle";
    const running = phase === "running";
    const counts = this._status?.outcome_counts || this._results?.outcome_counts || {};
    const progress = Number(this._status?.progress_percent || 0);
    const selectedProfile = this._form.mock_profile;
    const physical = this._form.provider === "esphome";
    const gatewayAvailable = this._gateways.some((item) => item.gateway_id === this._form.gateway_id && item.provider === this._form.provider);
    const gateway = this._gateways.find((g) => g.gateway_id === this._form.gateway_id);
    const compatible = supportedGateway(gateway);
    const canOperate = !physical || gateway?.can_operate === true;
    const transportFault = Boolean(gateway?.health?.firmware_state?.fault);
    const canCancel = this._status?.provider !== "esphome" || this._gateways.find((g) => g.gateway_id === this._status?.gateway_id)?.can_operate === true;
    const health = gateway?.health || {};
    const historyIds = [...new Set([...this._savedHistory.map((s) => s.scan_id), ...this._recent])];
    return b`
      <header class="top ${this.narrow ? "narrow" : ""}"><button class="menu secondary" @click=${this._menu} aria-label=${t.menu}><ha-icon icon="mdi:menu"></ha-icon></button><ha-icon icon="mdi:radar"></ha-icon><h1>${t.title}</h1></header>
      <main class="shell">
        <aside class="banner"><div><strong>${physical ? t.physicalTitle : t.mock}</strong><p>${physical ? t.physicalBanner : t.banner}</p></div><nav aria-label=${t.tutorialLinks}><a href=${TUTORIAL} target="_blank" rel="noopener">${t.tutorial}</a><a href=${DOWNLOAD}>${t.download}</a></nav></aside>
        <div class="grid"><div>
          <section class="card" aria-labelledby="gateway-title"><h2 id="gateway-title">${t.gateway}</h2>
            <div class="fields"><div class="field full"><label for="gateway">${t.availableGateway}</label><select id="gateway" .value=${this._form.gateway_id} ?disabled=${Boolean(this._busy) || running} @change=${(event) => this._selectGateway(event.target.value)} aria-invalid=${this._errors.gateway_id ? "true" : "false"} aria-describedby="gateway-help${this._errors.gateway_id ? " gateway-error" : ""}">${!gatewayAvailable ? b`<option value=${this._form.gateway_id} .selected=${true}>${this._form.gateway_id || t.gatewayError} (${this._loaded ? t.missingGateway : t.notRefreshed})</option>` : A}${this._gateways.map((item) => b`<option value=${item.gateway_id} .selected=${item.gateway_id === this._form.gateway_id}>${item.simulated ? t.simulatedGateway : item.name} — ${item.simulated ? t.simulated : item.provider}</option>`)}</select><small id="gateway-help">${t.gatewayHelp}</small>${this._errors.gateway_id ? b`<small class="error" id="gateway-error">${this._errors.gateway_id}</small>` : A}</div>
            <div class="field full future"><label for="future-device">${t.futureDevice}</label><select id="future-device" disabled><option>${physical ? this._form.gateway_id : t.futureUnavailable}</option></select><small>${t.futureHelp}</small></div></div>
            <div class="actions"><button class="secondary" @click=${this._loadGateways} ?disabled=${Boolean(this._busy)}><ha-icon icon="mdi:refresh"></ha-icon>${t.refreshGateways}</button></div>
          </section>
          ${physical ? b`<section class="card" aria-labelledby="health-title"><h2 id="health-title">${t.healthTitle}</h2><p>${t.apiOnly}</p><dl><dt>${t.apiEvidence}</dt><dd>${health.api_status || t.unchecked} · ${health.checked_at || t.dash}</dd><dt>${t.busEvidence}</dt><dd>${health.last_bus_response_at || t.unchecked}</dd><dt>${t.encryption}</dt><dd>${health.encrypted ? t.yes : t.no}</dd></dl>${transportFault ? b`<p class="notice failure" role="status">${t.firmwareFault}</p>` : A}${!compatible ? b`<p class="notice failure">${t.unsupportedProfile}</p>` : A}${!canOperate ? b`<p class="notice">${t.readOnly}</p>` : A}<button class="secondary" @click=${this._checkGateway} ?disabled=${Boolean(this._busy) || running || !canOperate || !gatewayAvailable}>${t.checkGateway}</button></section>` : A}
          <section class="card" aria-labelledby="scan-title"><h2 id="scan-title">${t.scanRange}</h2><div class="fields">
            ${this._field("start_id", t.startId, 1, 247, physical ? t.physicalRange : t.startHelp)}${this._field("end_id", t.endId, 1, 247, physical ? t.physicalRange : t.endHelp)}${this._field("address", t.address, 1, 247, physical ? t.physicalRange : t.addressHelp)}
            <div class="field"><label for="profile">${t.profile}</label><select id="profile" ?disabled=${physical} .value=${selectedProfile} @change=${(event) => this._set("mock_profile", event.target.value)} aria-describedby="profile-help">${PROFILES.map((profile) => b`<option value=${profile} .selected=${profile === selectedProfile}>${t.profileNames[profile]}</option>`)}</select><small id="profile-help">${physical ? t.physicalProfiles : t.profileHelp}</small></div>
          </div><div class="profiles" aria-label=${t.quickProfiles}>${PROFILES.map((profile) => { const selected = selectedProfile === profile; return b`<button class="secondary ${selected ? "selected" : ""}" ?disabled=${physical} @click=${() => this._set("mock_profile", profile)} aria-pressed=${selected}><ha-icon icon=${selected ? "mdi:check-circle" : "mdi:circle-outline"}></ha-icon>${t.profileNames[profile]}${selected ? b`<span class="sr-only">${t.selected}</span>` : A}</button>`; })}</div>
          <div class="profile-description" role="note"><strong>${physical ? t.physicalTitle : t.profileNames[selectedProfile]}</strong><p>${physical ? t.physicalProfiles : t.profiles[selectedProfile]}</p></div>
          <details ?open=${this._advancedOpen} @toggle=${(event) => { this._advancedOpen = event.target.open; this._persist(); }}><summary>${t.advanced}</summary><div class="fields">
            <div class="field full"><label for="probe">${t.probe}</label><select id="probe" .value=${this._form.probe_type} @change=${(event) => this._set("probe_type", event.target.value)}><option value="device_identification" ?disabled=${physical}>${t.deviceIdentification}</option><option value="holding_register">${t.holdingRegister}</option><option value="input_register" ?disabled=${physical}>${t.inputRegister}</option></select><small>${physical ? t.physicalHelp : t.probeHelp}</small></div>
            ${this._field("register_address", t.registerAddress, 0, 65535, physical ? t.physicalRegisters : t.registerAddressHelp)}${this._field("register_count", t.registerCount, 1, 125, physical ? t.physicalHelp : t.registerCountHelp)}${this._field("timeout_ms", t.timeout, 10, 10000, physical ? t.physicalHelp : t.timeoutHelp)}${this._field("retries", t.retries, 0, 5, t.retriesHelp)}${this._field("inter_request_delay_ms", t.delay, 0, 5000, t.delayHelp)}
            <div class="field check"><label><input type="checkbox" ?disabled=${physical} .checked=${this._form.pause_normal_polling} @change=${(event) => this._set("pause_normal_polling", event.target.checked)}>${t.pause}</label><small>${physical ? t.physicalPause : t.pauseHelp}</small></div>
          </div></details>
          <div class="field check"><label><input id="safety" type="checkbox" .checked=${this._form.safety_confirmed} @change=${(event) => this._set("safety_confirmed", event.target.checked)} aria-invalid=${this._errors.safety_confirmed ? "true" : "false"} aria-describedby="safety-help${this._errors.safety_confirmed ? " safety-error" : ""}">${t.safety}</label><small id="safety-help">${t.help.timeout}</small>${this._errors.safety_confirmed ? b`<small class="error" id="safety-error">${this._errors.safety_confirmed}</small>` : A}</div>
          <div class="actions"><button @click=${() => this._start(false)} ?disabled=${Boolean(this._busy) || running || !gatewayAvailable || !compatible || !canOperate || transportFault}><ha-icon icon="mdi:play"></ha-icon>${t.start}</button><button class="secondary" @click=${() => this._start(true)} ?disabled=${Boolean(this._busy) || running || !gatewayAvailable || !compatible || !canOperate || transportFault}><ha-icon icon="mdi:crosshairs-gps"></ha-icon>${t.test}</button><button class="danger" @click=${this._cancel} ?disabled=${Boolean(this._busy) || !running || !canCancel}><ha-icon icon="mdi:stop"></ha-icon>${t.cancel}</button></div>
          <div class="actions"><button class="secondary" @click=${this._showYaml} ?disabled=${!gatewayAvailable || !compatible || Boolean(this._busy) || running}>${t.yaml}</button></div>
          ${this._yaml ? b`<label for="service-yaml">${t.yamlLabel}</label><textarea id="service-yaml" readonly rows="16" style="width:100%;box-sizing:border-box" .value=${this._yaml}></textarea>` : A}
          </section>
        </div><div>
          <section class="card" aria-labelledby="status-title"><h2 id="status-title">${t.statusTitle}</h2><div class="notice ${phase === "failed" ? "failure" : ""}" role="status" aria-live="polite">${this._message || (phase === "idle" ? t.ready : `${t.statuses[phase] || phase}…`)}</div>
            <div class="field"><label for="recent">${t.recent}</label><select id="recent" @change=${this._selectRecent}><option value="">${this._chosenId() || t.noRecent}</option>${historyIds.map((id) => { const saved = this._savedHistory.find((s) => s.scan_id === id); return b`<option value=${id}>${saved ? `${saved.provider} · ${t.statuses[saved.status] || saved.status} · ` : ""}${id}</option>`; })}</select><small>${t.storage}</small></div>
            <div class="actions"><button class="secondary" @click=${this._loadHistory} ?disabled=${Boolean(this._busy) || running}>${t.history}</button></div><small>${t.historyHelp}</small>
            ${this._status ? b`<p>${t.operation}: ${t.operationStates[this._status.operation_phase] || this._status.operation_phase || t.dash} · ${t.attempt}: ${this._status.attempt || 0}<br>${t.elapsed}: ${Math.round((this._status.elapsed_ms || 0)/1000)}s · ${t.budget}: ${Math.ceil((this._status.execution_budget_ms || 0)/1000)}s</p><p>${t.recovery}: ${t.recoveryStates[this._status.recovery_status] || t.recoveryStates.unknown} ${this._status.recovery_error_code || ""}<br>${t.cleanup}: ${this._status.cleanup_status || t.unchecked}</p>${this._status.error_info ? b`<p>${t.errorCode}: <code>${this._status.error_info.code}</code></p>` : A}${this._status.progress_is_checkpoint ? b`<p class="notice failure">${t.checkpoint}</p>` : A}${TERMINAL.has(phase) && this._status.provider === "esphome" && this._status.recovery_status !== "verified" ? b`<p class="notice failure" role="status">${t.attention}</p>` : A}` : A}
            <p><strong>${t.phase}:</strong> ${t.statuses[phase] || phase} ${this._status?.current_address ? b`· ${t.columns.address} ${this._status.current_address}` : A}<br><code>${this._chosenId() || t.noScanId}</code></p>
            <div class="progress" role="progressbar" aria-label=${t.progress} aria-valuemin="0" aria-valuemax="100" aria-valuenow=${progress}><span style="width:${Math.min(100, Math.max(0, progress))}%"></span></div><small>${this._status?.completed_addresses || 0} / ${this._status?.total_addresses || 0} ${t.addresses} · ${progress}% · ${this._status?.responder_count || 0} ${t.responders}</small>
            ${this._status?.events?.length ? b`<section aria-label=${t.timeline}><strong>${t.timeline}</strong><ol>${this._status.events.slice(-8).map((event) => b`<li>${Math.round(event.elapsed_ms/1000)}s · ${t.operationStates[event.phase] || t.statuses[event.phase] || t.dash}</li>`)}</ol></section>` : A}
            <div class="counts">${OUTCOMES.map((outcome) => b`<div class="count"><strong>${counts[outcome] || 0}</strong>${t.outcomes[outcome]}</div>`)}</div>
            ${this._status?.error ? b`<div class="notice failure"><strong>${t.terminalError}:</strong> ${this._localError(this._status.error)}</div>` : A}
            <div class="actions"><button class="secondary" @click=${this._refreshStatus} ?disabled=${Boolean(this._busy)}><ha-icon icon="mdi:refresh"></ha-icon>${t.refreshStatus}</button><button class="secondary" @click=${() => this._loadResults()} ?disabled=${Boolean(this._busy)}><ha-icon icon="mdi:table-refresh"></ha-icon>${t.refreshResults}</button></div>
          </section>
        </div></div>
        <section class="card"><h2>${t.evidence}</h2><p>${t.evidenceHelp} ${t.rawHelp}</p><button class="secondary" @click=${this._downloadEvidence} ?disabled=${!this._results || Boolean(this._busy)}>${t.exportEvidence}</button>${this._results ? b`<p class="evidence-source"><strong>${t.resultGateway}:</strong> ${this._results.provider || t.simulated} · ${this._results.gateway_id || this._chosenId()}</p>` : A}<div class="table-wrap" tabindex="0" role="region" aria-label=${t.tableLabel}><table><thead><tr>${this._sortHeader("address", t.columns.address)}${this._sortHeader("outcome", t.columns.outcome)}${this._sortHeader("latency_ms", t.columns.latency_ms)}${this._sortHeader("exception_code", t.columns.exception_code)}${this._sortHeader("vendor", t.columns.vendor)}${this._sortHeader("product", t.columns.product)}${this._sortHeader("raw_value", t.rawRegister)}${this._sortHeader("detail", t.columns.detail)}</tr></thead><tbody>${this._responders().length ? this._responders().map((row) => b`<tr><td>${row.address}</td><td>${t.outcomes[row.outcome] || row.outcome}</td><td>${row.latency_ms}</td><td>${row.exception_code ?? t.dash}</td><td>${row.identity?.vendor || t.dash}</td><td>${row.identity?.product || t.dash}</td><td>${Number.isInteger(row.register_address) ? `0x${row.register_address.toString(16)}` : t.dash} / ${Number.isInteger(row.raw_value) ? row.raw_value : t.dash}</td><td>${row.detail ? this._detail(row.detail) : t.dash}</td></tr>`) : b`<tr><td colspan="8">${t.noEvidence}</td></tr>`}</tbody></table></div></section>
        <section class="card tutorial"><h2>${t.interpretation}</h2>${OUTCOMES.map((outcome) => b`<section><h3>${t.outcomes[outcome]}</h3><p>${t.help[outcome]}</p></section>`)}<section><h3>${t.unknownHeading}</h3><p>${t.help.unknown}</p></section><section><h3>${t.networkHeading}</h3><p>${t.help.network}</p></section></section>
      </main>`;
  }
}
if (!customElements.get("woow-esphome-modbus-scanner-panel")) customElements.define("woow-esphome-modbus-scanner-panel", WoowEsphomeModbusScannerPanel);

export { WoowEsphomeModbusScannerPanel };
