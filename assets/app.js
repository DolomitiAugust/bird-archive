import {language, t, count, chooseLanguage, syncLanguageUrl} from './i18n.js?v=3';

const el = id => document.getElementById(id);
const gallery = 'gallery';
const checklist = 'checklist';
const perPage = 40;
const photosPerPage = 48;
const taxonomyPage = 'https://www.avilist.org/checklist/v2026/';
const attributionLicense = 'https://creativecommons.org/licenses/by/4.0/';
const query = el('query');
const results = el('results');
const photoById = new Map();
const photoByLatin = new Map();
const speciesById = new Map();
const speciesByLatin = new Map();
const observationPhotos = new Map();
const accountShards = new Map();
let photos, historyPhotos, catalog, names, directories, namesWarning = false;
let photoRequest, catalogRequest, namesRequest;
let observationIndex, observationRequest, observationWarning = false, galleryData;
let references, referencesRequest, coverage;
let englishTaxa, englishTaxaRequest;
let revision = 0, currentPage = 1, lastPage = 1;

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}
function external(url, label) {
  const a = element('a', '', label);
  a.href = url;
  a.target = '_blank';
  a.rel = 'noopener noreferrer';
  return a;
}
function normalize(text) {
  return String(text ?? '').normalize('NFKD').toLowerCase().replace(/\p{M}/gu,'').replace(/[-‐‑–]/g,' ').replace(/[‘’]/g,"'").trim();
}
const archiveName = () => t('鸟类档案馆','Bird Archive');
const displayName = row => t(row.name || chinese(row) || row.en, row.en) || row.latin;
const speciesCount = value => t(count(value)+' 种',count(value)+' species');
const curatedTaxa = new Map();
function loadEnglishTaxa() {
  if (!englishTaxaRequest) englishTaxaRequest=optionalJson('data/taxon-labels-en.json').then(data=>{
    englishTaxa=data;
    directories=galleryData=undefined;
  }).catch(()=>{englishTaxaRequest=undefined;});
  return englishTaxaRequest;
}
function taxonTerms(kind,value) {
  const latin=curatedTaxa.get(value) || value;
  const label=names?.[kind]?.[latin];
  return [value,latin,englishTaxa?.[kind]?.[latin],label?.zh,...(label?.aliases || [])].filter(Boolean).join(' ');
}
function indexSelectedTaxa() {
  for (const photo of photos || []) {
    const species=speciesByLatin.get(photo.latin);
    if (species) {
      if (photo.order) curatedTaxa.set(photo.order,species.order);
      if (photo.family) curatedTaxa.set(photo.family,species.family);
    }
    photo.search=normalize([photo.name,photo.aliases,photo.en,photo.latin,taxonTerms('orders',photo.order),taxonTerms('families',photo.family)].join(' '));
  }
}
async function json(path) {
  const response = await fetch(path,{cache:'no-cache'});
  if (!response.ok) throw new Error('HTTP ' + response.status);
  return response.json();
}
function loadPhotos() {
  if (!photoRequest) photoRequest = json('data/photos.json').then(rows => {
    for (const photo of rows) {
      photoById.set(photo.id, photo);
      photoByLatin.set(photo.latin, photo);
    }
    photos = rows;
    historyPhotos = photos.filter(photo => photo.file?.startsWith('history-') && photo.photographed);
    indexSelectedTaxa();
    directories = galleryData = coverage = undefined;
  }).catch(err => { photoRequest = undefined; throw err; });
  return photoRequest;
}
function loadCatalog() {
  if (!catalogRequest) catalogRequest = json('data/checklist.json').then(data => {
    if (!Array.isArray(data.species)) throw new Error('Invalid checklist');
    for (const species of data.species) {
      speciesById.set(species.id, species);
      speciesByLatin.set(species.latin, species);
    }
    catalog = data;
    const totals = {
      'cover-species': data.species.length,
      'cover-orders': new Set(data.species.map(row => row.order).filter(Boolean)).size,
      'cover-families': new Set(data.species.map(row => row.family).filter(Boolean)).size
    };
    for (const [id, total] of Object.entries(totals)) {
      const field = el(id);
      if (field) field.textContent = count(total);
    }
  }).catch(err => { catalogRequest = undefined; throw err; });
  return catalogRequest;
}
function loadNames() {
  if (!namesRequest) namesRequest = json('data/chinese-names.json').then(data => {
    names = data;
    namesWarning = false;
    directories = galleryData = coverage = undefined;
  }).catch(() => { namesRequest = undefined; namesWarning = true; });
  return namesRequest;
}
async function optionalJson(path) {
  const response=await fetch(path,{cache:'no-cache'});
  if (response.status===404) return {};
  if (!response.ok) throw new Error('HTTP '+response.status);
  return response.json();
}
function loadObservations() {
  if (!observationRequest) observationRequest=optionalJson('data/observations.json').then(index=>{
    observationIndex=index.bySpecies || {};
    observationWarning=false;
    galleryData=directories=coverage=undefined;
  }).catch(()=>{observationRequest=undefined;observationWarning=true;});
  return observationRequest;
}
function loadReferences() {
  if (!referencesRequest) referencesRequest=optionalJson('data/references.json').then(data=>{
    references=data.species || {};
  }).catch(()=>{referencesRequest=undefined;});
  return referencesRequest;
}
function secureUrl(value) {
  try {
    const parsed=new URL(value);
    return parsed.protocol==='https:' && !parsed.username && !parsed.password ? parsed.href : '';
  } catch { return ''; }
}
function approvedLicense(label, url) {
  const match=/^CC (BY|BY-SA|BY-NC|BY-NC-SA) (1\.0|2\.0|2\.5|3\.0|4\.0)(?: ([A-Z]{2,3}(?:-[A-Z]{2,3})?))?$/i.exec(label);
  const normalized=(secureUrl(url) || '').replace(/\/$/,'');
  if (/^CC0(?: 1\.0)?$/i.test(label)) return normalized==='https://creativecommons.org/publicdomain/zero/1.0';
  const jurisdiction=match?.[3] ? '/'+match[3].toLowerCase() : '';
  return match && normalized==='https://creativecommons.org/licenses/'+match[1].toLowerCase()+'/'+match[2]+jurisdiction;
}
function buildPhotos() {
  if (galleryData) return galleryData;
  const combined=[];
  const photographed=new Set();
  for (const photo of photos || []) {
    const key=speciesByLatin.get(photo.latin)?.id || photo.latin;
    if (!photographed.has(key)) { combined.push(photo); photographed.add(key); }
  }
  observationPhotos.clear();
  for (const [id,asset] of Object.entries(observationIndex || {})) {
    const species=speciesById.get(id);
    if (!species || photographed.has(id) || !asset || asset.scientificName!==species.latin ||
        !String(asset.author || '').trim() || !approvedLicense(asset.license,asset.licenseUrl) ||
        !secureUrl(asset.imageUrl) || !secureUrl(asset.sourceUrl)) continue;
    const localized=names?.names?.[species.latin];
    const name=localized?.zh || species.en || species.latin;
    const localThumb=/^photos\/archive\/(?:[a-zA-Z\d_-]+\/)*[a-zA-Z\d_-]+\.(?:webp|jpg|jpeg|png)$/i.test(asset.localThumb) ? asset.localThumb : '';
    const photo={
      id,name,en:species.en,latin:species.latin,order:species.order,family:species.family,
      sourceCollection:({avicommons:'Avicommons / iNaturalist','birdnet-inaturalist':'BirdNET+ / iNaturalist','inaturalist-api':'iNaturalist',commons:'Wikimedia Commons','wikimedia-commons':'Wikimedia Commons'})[asset.sourceId || 'avicommons'] || '',
      captive:asset.captive===true || asset.basis==='captive-observation',basis:asset.basis,
      imageUrl:asset.imageUrl,thumbUrl:secureUrl(asset.thumbUrl) || asset.imageUrl,localThumb,
      sourcePhotoUrl:asset.sourceUrl,observationUrl:secureUrl(asset.observationUrl),
      credit:{filePage:secureUrl(asset.filePage) || asset.sourceUrl,author:asset.author,license:asset.license,licenseUrl:asset.licenseUrl},
      changes: localThumb ? '本馆缩略图经缩小并转为 WebP，总览按画框裁切。' : '总览按画框裁切，详情保留来源图像的比例。',
      enChanges:localThumb ? 'Thumbnails are resized, converted to WebP and cropped to fit the gallery.' : 'Gallery thumbnails are cropped. The record shows the original proportions.',
      search:normalize([name,species.en,species.latin,localized?.aliases?.join(' '),taxonTerms('orders',species.order),taxonTerms('families',species.family)].join(' '))
    };
    combined.push(photo);photographed.add(id);observationPhotos.set(id,photo);
  }
  galleryData=combined;
  return combined;
}
function chinese(species) {
  return photoByLatin.get(species.latin)?.name || names?.names?.[species.latin]?.zh || species.zh || '';
}
function taxonLabel(kind, latin) {
  if (!latin) return '';
  latin=curatedTaxa.get(latin) || latin;
  const english=englishTaxa?.[kind]?.[latin];
  if (language==='en') return english && english!==latin ? english+' · '+latin : (/^[a-z]/i.test(latin) ? latin : 'Unclassified');
  const entry = names?.[kind]?.[latin];
  return entry?.zh ? entry.zh + ' · ' + latin : latin;
}
function prepareDirectory() {
  if (directories) return directories;
  buildPhotos();
  directories = catalog.species.map(species => {
    const photo = photoByLatin.get(species.latin) || observationPhotos.get(species.id);
    const localized = names?.names?.[species.latin];
    const search = normalize([species.en,species.latin,chinese(species),species.genus,taxonTerms('orders',species.order),
      taxonTerms('families',species.family),localized?.zh,localized?.aliases?.join(' '),photo?.search].join(' '));
    return {species,photo,search};
  });
  return directories;
}
function readRoute() {
  const [path='', raw=''] = location.hash.slice(1).split('?');
  const params = new URLSearchParams(raw);
  const [section, encoded] = path.split('/');
  let id = '';
  if (section === 'bird' && encoded) {
    try { id = decodeURIComponent(encoded); } catch { id = encoded; }
  }
  const view=section === checklist || (section === 'bird' && (params.get('from') === checklist || (params.get('from')!==gallery && id.startsWith('avibase-')))) ? checklist : gallery;
  const scope=params.get('scope');
  return {
    view,
    scope:view===gallery ? (['selected','history'].includes(scope) ? scope : 'all') : '',
    id, q:params.get('q') || '', order:params.get('order') || '', family:params.get('family') || '',
    media:view===checklist && ['with','missing'].includes(params.get('media')) ? params.get('media') : '',
    page: Math.max(1,parseInt(params.get('page'),10) || 1)
  };
}
function urlFor(route) {
  const params = new URLSearchParams();
  if (route.id && (route.view === checklist || route.id.startsWith('avibase-'))) params.set('from',route.view);
  if (route.view===gallery && ['selected','history'].includes(route.scope)) params.set('scope',route.scope);
  for (const key of ['q','order','family','media']) if (route[key]) params.set(key,route[key]);
  if (route.page > 1) params.set('page',String(route.page));
  const search = params.toString();
  return '#' + (route.id ? 'bird/' + encodeURIComponent(route.id) : route.view) + (search ? '?' + search : '');
}
function navigate(hash, opener) {
  if (location.hash === hash) return;
  history.replaceState({...history.state,scroll:window.scrollY,focusId:opener || null},'');
  history.pushState({entered:true},'',hash);
  routePage();
}
function listRoute() {
  const route = readRoute();
  route.id = '';
  return route;
}
function updateList(changes, pageTop = false) {
  const updated = {...listRoute(),page:1,...changes};
  history.replaceState({...history.state,scroll:null,focusId:null},'',urlFor(updated));
  drawList(updated);
  if (pageTop) el('browse-title').scrollIntoView({block:'start'});
}
function toggle(section, hasDetail) {
  el('browse').hidden = hasDetail;
  el('record').hidden = !hasDetail;
  const cover = el('archive-cover');
  if (cover) cover.hidden = hasDetail || section !== gallery;
  for (const link of document.querySelectorAll('[data-section]')) {
    if (link.dataset.section === section) link.setAttribute('aria-current','page');
    else link.removeAttribute('aria-current');
  }
}
function backButton(route) {
  const labels={
    all:t('返回影像总览','Back to photo gallery'),
    selected:t('返回摄影选集','Back to selected photographs'),
    history:t('返回历史影像','Back to historical photographs')
  };
  const a = element('a','return',labels[route.scope] || t('返回全球名录','Back to world checklist'));
  a.href = urlFor({...route,id:''});
  a.dataset.back = '';
  return a;
}
function statusBox(message, retry) {
  const div = element('div','empty');
  div.setAttribute('role','status');
  div.append(element('p','',message));
  if (retry) {
    const btn=element('button','line-button',t('重新加载','Try again'));
    btn.type='button';
    btn.addEventListener('click',retry);
    div.append(btn);
  }
  return div;
}
function restorePosition(token, detail) {
  requestAnimationFrame(() => {
    if (token !== revision) return;
    const remembered = history.state || {};
    if (remembered.focusId && !detail) {
      document.getElementById('link-'+remembered.focusId)?.focus({preventScroll:true});
    } else if (remembered.entered && detail) {
      el('record-title')?.focus({preventScroll:true});
    }
    window.scrollTo(0,typeof remembered.scroll === 'number' ? remembered.scroll : 0);
  });
}
function optionList(select, values, current, label, kind) {
  const options = [new Option(label,'')];
  for (const value of values) options.push(new Option(taxonLabel(kind,value),value));
  select.replaceChildren(...options);
  select.value = current;
}
function fillFilters(route, rows) {
  const isDirectory = route.view === checklist || route.scope==='all';
  el('photo-filter').hidden = route.view !== checklist;
  el('media').value = route.media || '';
  const tabs = el('paper-tabs');
  tabs.hidden = isDirectory;
  el('taxonomy').hidden = !isDirectory;
  document.querySelector('.index-row').classList.toggle('directory-mode',isDirectory);
  el('index-label').textContent = isDirectory ? t('分类索引','Taxonomy') : t('按目浏览','Browse by order');
  if (!isDirectory) {
    const orders=new Map([['',t('全部','All')]]);
    for (const photo of rows) {
      const latin=speciesByLatin.get(photo.latin)?.order || photo.order;
      if (latin && !orders.has(latin)) orders.set(latin,t(names?.orders?.[latin]?.zh || photo.order,taxonLabel('orders',latin)));
    }
    const labelsChanged=Array.from(tabs.children).some(button=>orders.get(button.dataset.order)!==button.textContent);
    if (tabs.childElementCount !== orders.size || labelsChanged) {
      tabs.replaceChildren(...Array.from(orders,([order,label]) => {
        const btn = element('button','tab',label);
        btn.type='button';
        btn.dataset.order = order;
        return btn;
      }));
    }
    const selected=curatedTaxa.get(route.order) || route.order;
    for (const button of tabs.children) button.setAttribute('aria-pressed', String(selected === button.dataset.order));
    return;
  }
  const order=curatedTaxa.get(route.order) || route.order;
  const family=curatedTaxa.get(route.family) || route.family;
  const key=[route.view,rows.length,Boolean(catalog),Boolean(names),language,Boolean(englishTaxa)].join(':');
  const taxon=row=>row.species || speciesByLatin.get(row.latin) || row;
  if (el('order').dataset.version !== key) {
    const orders = [...new Set(rows.map(r=>taxon(r).order))].filter(Boolean);
    optionList(el('order'),orders,order,t('全部目','All orders'),'orders');
    el('order').dataset.version = key;
    delete el('family').dataset.order;
  }
  el('order').value = order;
  if (el('family').dataset.order !== order) {
    const familyRows = order ? rows.filter(r => taxon(r).order === order) : rows;
    optionList(el('family'), [...new Set(familyRows.map(r=>taxon(r).family))].filter(Boolean), family,t('全部科','All families'),'families');
    el('family').dataset.order = order;
  }
  el('family').value = family;
}
function birdLink(route, id, className, label) {
  const link = element('a',className,label);
  link.href = urlFor({...route,id});
  link.dataset.nav = '';
  link.dataset.bird = id;
  link.id = 'link-'+id;
  return link;
}
function photoFigure(photo, full=false) {
  const img = new Image();
  const src = photo.file ? 'photos/'+photo.file : (full ? photo.imageUrl : photo.localThumb || photo.thumbUrl);
  img.alt = full ? displayName(photo)+t('，摄影：',', photographed by ')+photo.credit.author : '';
  img.decoding = 'async';
  img.loading = full ? 'eager' : 'lazy';
  img.src = src;
  img.addEventListener('error',() => {
    const fallback=photo.localThumb && (full ? photo.localThumb : photo.thumbUrl);
    if (fallback && !img.dataset.fallback) {
      img.dataset.fallback='true';
      img.src=fallback;
      return;
    }
    img.replaceWith(element('span','unavailable-photo',t('照片暂时无法载入','Photo unavailable')));
  });
  return img;
}
function photoCards(rows,route) {
  const grid = element('div','photo-grid');
  grid.dataset.scope=route.scope;
  const firstRow=window.matchMedia('(max-width: 740px)').matches ? 5 : 8;
  for (const [index,photo] of rows.entries()) {
    const link = birdLink(route,photo.id,'bird-card');
    const frame = element('span','image-frame');
    const img=photoFigure(photo);
    if (index < firstRow) img.loading = 'eager';
    frame.append(img);
    const name=displayName(photo);
    const caption=element('span','caption');
    caption.append(element('span','card-name',name));
    if (photo.latin && photo.latin !== name) caption.append(element('i','card-latin',photo.latin));
    if (route.scope==='history') {
      const date=t(photo.photographed,photo.enPhotographed || photo.photographed);
      if (date) caption.append(element('span','plate-date',date));
    }
    link.append(frame,caption);
    grid.append(link);
  }
  return grid;
}
function directoryTable(rows,route) {
  const table = element('table','directory');
  const head = table.createTHead().insertRow();
  for (const label of [t('鸟名','Bird name'),t('学名','Scientific name'),t('科','Family')]) {
    const th = element('th','',label); th.scope='col'; head.append(th);
  }
  const body=table.createTBody();
  for (const {species,photo} of rows) {
    const name=chinese(species);
    const tr=body.insertRow();
    const td=tr.insertCell();
    td.append(birdLink(route,photo?.id || species.id,'',displayName(species)));
    if (language==='zh' && name && species.en) td.append(element('span','secondary',species.en));
    tr.insertCell().append(element('i','scientific',species.latin));
    tr.insertCell().textContent=taxonLabel('families',species.family);
  }
  return table;
}
function navigationLink(text,route) {
  const link=element('a','',text);
  link.href=urlFor(route);
  link.dataset.nav='';
  return link;
}
function showCollectionInfo(route) {
  const info=el('collection-info');
  if (route.view===gallery) {
    const links=[
      ['all',t('全部实拍','All photographs'),observationIndex && galleryData?.length],
      ['selected',t('摄影选集','Selected photographs'),photos?.length],
      ['history',t('历史影像','Historical photographs'),historyPhotos?.length]
    ].map(([scope,label,total])=>{
      const link=navigationLink('',{view:gallery,scope,q:route.q});
      link.append(element('span','collection-label',label));
      if (Number.isInteger(total)) link.append(element('span','collection-count',count(total)));
      if (route.scope===scope) link.setAttribute('aria-current','page');
      return link;
    });
    info.replaceChildren(...links);
    return;
  }
  if (!coverage) {
    const indexed=catalog.species.filter(species=>Boolean(chinese(species))).length;
    const photographed=new Set(buildPhotos().map(p=>speciesByLatin.get(p.latin)?.id).filter(Boolean)).size;
    coverage={indexed,photographed};
  }
  const details=[
    t('全球名录 '+speciesCount(catalog.species.length),speciesCount(catalog.species.length)+' in the checklist'),
    observationWarning || !photos ? t('已载入实拍 '+speciesCount(coverage.photographed),speciesCount(coverage.photographed)+' with photos loaded')
      : t('有实拍 '+speciesCount(coverage.photographed),speciesCount(coverage.photographed)+' photographed'),
    namesWarning ? t('中文索引暂未载入','Chinese name index unavailable')
      : t('有中文名 '+speciesCount(coverage.indexed),speciesCount(coverage.indexed)+' with Chinese names')];
  info.replaceChildren(...details.map(label=>element('span','',label)));
}
function drawList(route) {
  const isDirectory = route.view === checklist;
  const combinedReady=catalog && (observationIndex || observationWarning) && (names || namesWarning);
  const pendingGallery=route.scope==='all' && !combinedReady;
  let sourceRows = photos;
  if (isDirectory) sourceRows=catalog ? prepareDirectory() : null;
  else if (route.scope==='history') sourceRows=historyPhotos;
  else if (route.scope==='all' && combinedReady) sourceRows=buildPhotos();
  if (!sourceRows) return;
  results.setAttribute('aria-busy',String(pendingGallery));
  showCollectionInfo(route);
  query.value = route.q;
  fillFilters(route,sourceRows);
  el('reset').hidden = !(route.q || route.order || route.family || route.media);
  const words = normalize(route.q).split(/\s+/).filter(Boolean);
  const scientificQuery = words.join(' ');
  const exactSpecies = words.length === 2
    ? speciesByLatin.get(scientificQuery.charAt(0).toUpperCase() + scientificQuery.slice(1))
    : undefined;
  const order=curatedTaxa.get(route.order) || route.order;
  const family=curatedTaxa.get(route.family) || route.family;
  const matching = sourceRows.filter(row => {
    const species = isDirectory ? row.species : speciesByLatin.get(row.latin) || row;
    return (!exactSpecies || species.latin === exactSpecies.latin) &&
      (!order || species.order === order) &&
      (!isDirectory || !route.media || Boolean(row.photo) === (route.media === 'with')) &&
      (!family || species.family === family) && words.every(w => row.search.includes(w));
  });
  const limit=isDirectory ? perPage : photosPerPage;
  lastPage = Math.max(1,Math.ceil(matching.length/limit));
  currentPage = pendingGallery ? route.page : Math.min(lastPage,route.page);
  if (route.page !== currentPage) {
    route.page=currentPage;
    history.replaceState(history.state,'',urlFor(route));
  }
  const loadingText=t('正在读取全部实拍…','Loading the complete gallery…');
  el('total').textContent = pendingGallery ? loadingText : speciesCount(matching.length);
  el('status').textContent = pendingGallery ? loadingText : t('找到 '+speciesCount(matching.length)+'鸟',speciesCount(matching.length)+' found');
  el('pager').hidden = pendingGallery || lastPage < 2;
  el('previous').disabled = currentPage===1;
  el('next').disabled = currentPage===lastPage;
  el('page-number').textContent = currentPage+' / '+lastPage;
  el('page-number').setAttribute('aria-label',t('第 '+currentPage+' 页，共 '+lastPage+' 页','Page '+currentPage+' of '+lastPage));
  if (pendingGallery && (!matching.length || currentPage>lastPage)) {
    results.replaceChildren(statusBox(loadingText));
  } else if (!matching.length) {
    const box = statusBox(t('没有找到符合条件的鸟种。','No species match your search.'));
    if (!isDirectory && route.q) {
      const a = element('a','text-button',t('在全球名录中查找','Search the world checklist'));
      a.href=urlFor({view:checklist,q:route.q});a.dataset.nav='';box.append(a);
    }
    results.replaceChildren(box);
  } else {
    const pageRows=matching.slice((currentPage-1)*limit,currentPage*limit);
    results.replaceChildren(isDirectory ? directoryTable(pageRows,route) : photoCards(pageRows,route));
  }
  if (isDirectory && namesWarning) {
    const box=statusBox(t('中文名称暂时未载入，可用英文名和学名检索。','Chinese names are unavailable. Search by English or scientific name.'),routePage);
    results.prepend(box);
  }
  if ((isDirectory || route.scope==='all') && observationWarning) results.append(statusBox(t('扩展实拍索引暂时无法载入，已保留可用档案。','The extended photo index could not load. Available records are shown.'),routePage));
}
function creditLinks(photo) {
  return [external(photo.credit.filePage,photo.credit.author),' · ',external(photo.credit.licenseUrl,t(photo.credit.license,photo.credit.enLicense || photo.credit.license))];
}
function fact(list,label,value) {
  if (!value) return;
  list.append(element('dt','',label),element('dd','',value));
}
function readingLinks(group,species,photo) {
  const item=references?.[species?.id] || {};
  const links=[];
  if (item.ebird && /^[a-z\d_-]+$/i.test(item.ebird)) links.push(external('https://ebird.org/species/'+item.ebird,t('eBird 照片与声音','eBird photos and sounds')));
  if (secureUrl(item.birdlife)) links.push(external(item.birdlife,'BirdLife'));
  if (secureUrl(item.bow)) links.push(external(item.bow,'Birds of the World'));
  if (/^\d+$/.test(item.inat)) links.push(external('https://www.inaturalist.org/taxa/'+item.inat,t('iNaturalist 物种记录','iNaturalist species record')));
  if (/^\d+$/.test(item.gbif)) links.push(external('https://www.gbif.org/species/'+item.gbif,'GBIF'));
  if (!item.inat) {
    const latin=species?.latin || photo?.latin;
    if (latin) links.push(external('https://www.inaturalist.org/observations?taxon_name='+encodeURIComponent(latin),t('按学名搜索 iNaturalist 观测','Search iNaturalist observations by scientific name')));
  }
  group.replaceChildren(element('h2','',t('延伸查阅','Further reading')),...links);
}
async function accountEntry(folder,prefix,id) {
  const path='data/'+folder+'/'+prefix+'.json';
  if (!accountShards.has(path)) {
    const request=optionalJson(path).catch(()=>{
      accountShards.delete(path);
      return {};
    });
    accountShards.set(path,request);
  }
  const entry=(await accountShards.get(path))[id];
  return entry?.text && ['en','zh'].includes(entry.lang) &&
    /^https:\/\/(?:zh|en)\.wikipedia\.org\//i.test(secureUrl(entry.url)) ? entry : null;
}
async function showAccount(group,id) {
  const match=/^avibase-([0-9a-f]{2})[0-9a-f]{6}$/i.exec(id);
  if (!match) return;
  const prefix=match[1].toLowerCase();
  const preferred=language==='en' ? await accountEntry('accounts-en',prefix,id) : null;
  const account=preferred || await accountEntry('accounts',prefix,id);
  if (!group.isConnected || !account) return;
  const paragraph=element('p','note',account.text);
  paragraph.lang=account.lang;
  const direct=account.via==='wiki';
  const sourceName=account.lang==='zh' ? t('中文维基百科','Chinese Wikipedia') : t('英文维基百科','English Wikipedia');
  const heading=account.lang===language ? t('物种简介','Species account') :
    t('物种简介（英文原文）','Species account (original language: Chinese)');
  const credit=element('p','source-link',direct ? t('摘录自','Excerpt from ') : t('摘录自 BirdNET+ 收录的','Excerpt via BirdNET+ from '));
  credit.append(external(account.url,sourceName+t('条目及其贡献者',' and its contributors')+(direct ? t('（固定版本）',' (permanent revision)') : '')),' · ',
    external('https://creativecommons.org/licenses/by-sa/4.0/','CC BY-SA 4.0'));
  group.replaceChildren(element('h2','',heading),paragraph,credit);
  group.hidden=false;
}
function showRecord(route,photo,species) {
  const folio=element('article','record-folio'+(photo?'':' without-photo'));
  const index=element('div','folio-index');
  const identifier=element('span','folio-identifier');
  identifier.append(t('档案编号','Catalogue no.'), element('b','',photo?.id || species.id));
  index.append(element('span','folio-tab',t('物种档案','Species record')),identifier);
  const spread=element('div','folio-spread');
  const heading=element('header','folio-heading');
  const name=displayName(photo || species);
  const title=element('h1','',name);
  title.id='record-title';title.tabIndex=-1;
  document.title=name+' · '+archiveName();
  heading.append(title,element('p','scientific',photo?.latin || species.latin));
  const classification=element('section','folio-classification');
  classification.append(element('h2','',t('分类记录','Classification')));
  const facts=element('dl','facts');
  if (language==='zh') fact(facts,'英文名',photo?.en || species?.en);
  else {
    const known=species ? chinese(species) : photo?.name;
    if (known && /\p{Script=Han}/u.test(known)) fact(facts,'Chinese name',known);
  }
  const localNames=names?.names?.[species?.latin || photo?.latin];
  if (localNames) {
    const primary=photo?.name || (species && chinese(species));
    const alternatives=[...new Set([localNames.zh,...(localNames.aliases || [])])].filter(value=>value && value!==primary);
    fact(facts,t('其他中文名','Other Chinese names'),alternatives.join(t('、',', ')));
  }
  fact(facts,t('目','Order'),species ? taxonLabel('orders',species.order) : t(photo.order,taxonLabel('orders',photo.order)));
  fact(facts,t('科','Family'),species ? taxonLabel('families',species.family) : t(photo.family,taxonLabel('families',photo.family)));
  fact(facts,t('属','Genus'),species?.genus || photo?.latin.split(' ')[0]);
  if (species?.extinction) fact(facts,t('名录状态（原文）','Checklist status'),species.extinction);
  if (!photo) fact(facts,t('影像','Photograph'),t('照片待补','Awaiting a photograph'));
  classification.append(facts);
  const body=element('div','record-body');
  const note=photo && t(photo.note,photo.enNote);
  if (note) {
    const identification=element('section','record-section');
    identification.append(element('h2','',t('辨识要点','Identification')),element('p','note',note));
    const source = element('p','source-link',t('辨识资料 · ','Identification source · '));
    source.append(external(photo.url,t(photo.source,photo.enSource || new URL(photo.url).hostname)));
    identification.append(source);
    body.append(identification);
  }
  const account=element('section','record-section species-account');
  account.hidden=true;
  body.append(account);
  const distribution=element('section','record-section');
  if (species?.range) {
    const heading=element('h2','range-title',t('分布范围（英文原文）','Distribution'));
    const description=element('p','note',species.range);description.lang='en';
    distribution.append(heading,description);
  }
  if (species) {
    const source=element('p','source-link',t('名录与分布资料 · ','Taxonomy and distribution · '));
    source.append(external(taxonomyPage,'AviList '+catalog.version),' · ',external(attributionLicense,'CC BY 4.0'));
    if (species.range) {
      distribution.append(source);
      body.append(distribution);
    } else classification.append(source);
  }
  const referencesPanel=element('aside','folio-references');
  const links=element('div','reading-links');
  readingLinks(links,species,photo);
  referencesPanel.append(links);
  const feedback=element('p','source-link feedback');
  const issue=new URL('https://github.com/DolomitiAugust/bird-archive/issues/new');
  issue.searchParams.set('title',t('档案修订 · ','Record correction · ')+name+' ('+(species?.latin || photo.latin)+')');
  issue.searchParams.set('body',t('档案编号：','Record ID: ')+(species?.id || photo.id)+t('\n原始照片或资料出处：\n建议修改：','\nPhoto or original source: \nSuggested correction: '));
  feedback.append(external(issue.toString(),t('反馈这份档案的图片或资料问题','Report a photo or record issue')));
  referencesPanel.append(feedback);
  if (!references) loadReferences().then(()=>{
    if (links.isConnected) readingLinks(links,species,photo);
  });
  spread.append(heading);
  if (photo) {
    const figure=element('figure','folio-plate');
    const mount=element('div','plate-mount');
    const img=photoFigure(photo,true);img.className='record-photo';
    mount.append(img);
    const caption=element('figcaption');
    const byline=element('p','plate-credit');
    if (photo.sourcePhotoUrl) {
      byline.append(t('摄影 · ','Photo · '),photo.credit.author,' · ',external(photo.credit.licenseUrl,photo.credit.license),
        ' · ',external(photo.sourcePhotoUrl,t('原始照片','Original photograph')));
      if (photo.observationUrl && photo.observationUrl!==photo.sourcePhotoUrl) byline.append(' · ',external(photo.observationUrl,t('原始观测','Original observation')));
      if (photo.sourceCollection) byline.append(' · ',photo.sourceCollection);
      if (photo.credit.license.includes('NC')) byline.append(t(' · 限非商业使用',' · Noncommercial use only'));
    } else {
      byline.append(t('摄影 · ','Photo · '),...creditLinks(photo));
    }
    const date=t(photo.photographed,photo.enPhotographed);
    if (date) byline.append(' · ', date);
    caption.append(byline);
    if (photo.captive) caption.append(element('p','',t('圈养活体摄影','Photograph of a captive bird')));
    const context=t(photo.imageContext,photo.enImageContext);
    if (context) caption.append(element('p','',context));
    const changes=t(photo.changes,photo.enChanges || 'Gallery thumbnails are cropped. The record shows the original proportions.');
    if (changes) {
      const processing=element('details','plate-processing');
      processing.append(element('summary','',t('图像处理说明','Image processing')),element('p','',changes));
      caption.append(processing);
    }
    figure.append(mount,caption);
    spread.append(figure);
  }
  spread.append(classification);
  const notes=element('div','folio-notes');
  notes.append(body,referencesPanel);
  folio.append(index,spread,notes);
  el('record').replaceChildren(backButton(route),folio);
  if (species) showAccount(account,species.id);
}
async function routePage(preserve) {
  const token=++revision;
  syncLanguageUrl();
  const route=readRoute();
  const detail=Boolean(route.id);
  toggle(route.view,detail);
  el('pager').hidden = true;
  const target=detail ? el('record') : results;
  if (!detail) {
    const titles={
      all:t('馆藏影像','Bird photographs'),
      selected:t('摄影选集','Selected photographs'),
      history:t('历史影像','Historical photographs')
    };
    el('browse-title').textContent=titles[route.scope] || t('全球鸟类名录','World bird checklist');
    document.title=el('browse-title').textContent+' · '+archiveName();
    el('total').textContent='';
    if (route.view===gallery) showCollectionInfo(route);
    else el('collection-info').replaceChildren();
    query.value=route.q;
    el('paper-tabs').hidden=route.view!==gallery || route.scope==='all';
    el('taxonomy').hidden=route.view!==checklist && route.scope!=='all';
    results.setAttribute('aria-busy','true');
    el('reset').hidden=true;
  }
  if (!preserve?.languageChange) target.replaceChildren(statusBox(t('正在读取档案…','Loading records…')));
  try {
    const needCatalog = detail ? !route.id.startsWith('BH-') : route.view===checklist || route.scope==='all';
    if (!detail && route.view===gallery && !galleryData) {
      // Offer the local collection and its filters while the global indexes load.
      await loadPhotos().catch(()=>{});
      if (token!==revision) return;
      if (photos) {
        drawList(readRoute());
        await new Promise(resolve=>requestAnimationFrame(resolve));
        if (token!==revision) return;
      }
    }
    if (needCatalog) {
      await Promise.all([loadCatalog(),loadNames(),loadObservations(),loadEnglishTaxa(),loadPhotos().catch(()=>{})]);
      indexSelectedTaxa();
      buildPhotos();
    } else {
      await Promise.all([loadPhotos(),loadEnglishTaxa(),loadCatalog().catch(()=>{}),loadNames()]);
      indexSelectedTaxa();
    }
    if (token!==revision) return;
    if (!detail) {
      drawList(readRoute());
    } else {
      const species=speciesById.get(route.id) || speciesByLatin.get(photoById.get(route.id)?.latin);
      const photo=photoById.get(route.id) || photoByLatin.get(species?.latin) || observationPhotos.get(species?.id);
      if (!species && !photo) {
        target.replaceChildren(backButton(route),statusBox(t('这份物种档案不存在。','This species record could not be found.')));
        document.title=t('未找到档案','Record not found')+' · '+archiveName();
      } else {
        showRecord(route,photo,species);
        if (photo && !species) {
          Promise.all([loadCatalog(),loadNames()]).then(() => {
            const match=speciesByLatin.get(photo.latin);
            if (match && token===revision) showRecord(route,photo,match);
          }).catch(()=>{});
        }
      }
    }
    if (preserve?.languageChange) {
      requestAnimationFrame(()=>{
        if (token!==revision) return;
        if (preserve.focus && !preserve.focus.isConnected && preserve.focus.id) el(preserve.focus.id)?.focus({preventScroll:true});
        window.scrollTo(0,preserve.scroll);
      });
    } else restorePosition(token,detail);
  } catch {
    if (token!==revision) return;
    results.setAttribute('aria-busy','false');
    if (!detail && route.scope==='all' && !photos) {
      await loadPhotos().catch(()=>{});
      if (token!==revision) return;
    }
    if (!detail && route.scope==='all' && photos) {
      const fallback={...readRoute(),view:gallery,scope:'selected',order:'',family:'',page:1};
      history.replaceState(history.state,'',urlFor(fallback));
      el('browse-title').textContent=t('摄影选集','Selected photographs');
      document.title=el('browse-title').textContent+' · '+archiveName();
      drawList(fallback);
      results.append(statusBox(t('扩展名录尚未载入，当前显示摄影选集。','The extended checklist could not load. Showing selected photographs.'),()=>navigate(urlFor({...readRoute(),scope:'all'}))));
      return;
    }
    const box=statusBox(t('资料暂时无法载入，请检查网络后重试。','The data could not load. Check your connection and try again.'),routePage);
    target.replaceChildren(...(detail ? [backButton(route),box] : [box]));
  }
}
function showSources() {
  const content=el('sources-content');
  const text=element('p');
  text.append(t('分类与分布数据取自 AviList Core Team 的 ','Taxonomy and distribution are drawn from the AviList Core Team’s '),
    external(taxonomyPage,'AviList v2026'),t('，按 ', ', licensed under '),external(attributionLicense,'CC BY 4.0'),
    t(' 授权使用。本馆提取种级条目和分类字段，并保留分布原文。','. The archive uses species-level records and preserves the original range descriptions.'));
  const list=element('ul','source-list');
  for (const photo of photos || []) {
    const li=element('li','',displayName(photo)+' · ');li.append(...creditLinks(photo));list.append(li);
  }
  const nameInfo=element('p');
  nameInfo.append(t('中文索引整理自 BirdNET Team 的 ','Chinese names come from the BirdNET Team’s '),
    external(names?.sourceUrl || 'https://birdnet.cornell.edu/taxonomy/about#license','BirdNET+ Taxonomy v0.5-Nov2026'),t('，采用 ', ', licensed under '),
    external(names?.licenseUrl || 'https://creativecommons.org/licenses/by-sa/4.0/','CC BY-SA 4.0'),t(' 许可，并从 Wikidata 贡献者的 ', ', with additions from Wikidata contributors’ '),
    external(names?.wikidataLicense || 'https://www.wikidata.org/wiki/Wikidata:Licensing',t('CC0 数据','CC0 data')),
    t('、IOC、GBIF 和中文维基百科补充名称。按学名与分类阶元匹配，合并地区用名作为别名。详见',', IOC, GBIF and Chinese Wikipedia. Names are matched by scientific name and rank. Regional names are searchable aliases. See '),
    external('https://github.com/DolomitiAugust/bird-archive/blob/main/data/CHINESE-NAMES.md',t('中文名称来源与许可','Chinese name sources and licenses')),t('。','.'));
  const otherPhotos=element('p');
  otherPhotos.append(t('全球图库收录 Adam Jackson 在 ','The gallery includes images curated by Adam Jackson at '),external('https://avicommons.org/','Avicommons'),
    t(' 整理的影像、',', photographs indexed by '),external('https://birdnet.cornell.edu/taxonomy/about','BirdNET+'),
    t(' 关联的摄影，以及直接核对的 ', ', and observations or taxon photographs verified against '),external('https://www.inaturalist.org/','iNaturalist'),
    t(' 观测或物种照片。每张照片都可追溯到原始记录。标为 NC 的照片限非商业使用。','. Individual records link to the original source. Photographs marked NC are licensed for noncommercial use only.'));
  const gaps=element('p');
  const gapLink=element('a','',t('下载待补资料清单（CSV）','Download the list of missing materials (CSV)'));
  gapLink.href=t('data/gaps.csv','data/gaps-en.csv');
  gapLink.download=t('鸟类档案馆-待补资料.csv','bird-archive-missing-materials.csv');
  gaps.append(gapLink);
  content.replaceChildren(text,nameInfo,element('p','',t('摄影选集的照片来自 Wikimedia Commons。选集使用等比例缩小的 WebP，卡片裁切展示，详情保留完整构图。','Selected photographs come from Wikimedia Commons. They are resized proportionally and converted to WebP. Gallery cards crop the image, and each species record shows the full composition.')),list,otherPhotos,gaps);
  if (!el('sources-dialog').open) el('sources-dialog').showModal();
}
const cabinet=el('cabinet-controls');
if (cabinet) {
  const narrow=window.matchMedia('(max-width: 740px)');
  const applySize=()=>{ cabinet.open=!narrow.matches; };
  applySize();
  narrow.addEventListener('change',applySize);
}
for (const button of document.querySelectorAll('button[data-lang]')) {
  button.addEventListener('click',()=>{
    const refresh={languageChange:true, scroll:window.scrollY, focus:document.activeElement};
    const previous=language;
    chooseLanguage(button.dataset.lang);
    if (previous===language) return;
    if (el('sources-dialog').open) showSources();
    routePage(refresh);
  });
}
document.addEventListener('click',event => {
  if (event.button!==0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
  const link=event.target.closest('a[data-nav],a[data-back],a.skip-link');
  if (!link) return;
  event.preventDefault();
  if (link.classList.contains('skip-link')) { el('content').focus(); return; }
  if (link.hasAttribute('data-back') && history.state?.entered) { history.back(); return; }
  navigate(link.hash,link.dataset.opener || link.dataset.bird);
});
el('paper-tabs').addEventListener('click',e => {
  const button=e.target.closest('button[data-order]');
  if (button) updateList({order:button.dataset.order,family:''});
});
el('order').addEventListener('change',e=>updateList({order:e.target.value,family:''}));
el('family').addEventListener('change',e=>updateList({family:e.target.value}));
el('media').addEventListener('change',e=>updateList({media:e.target.value}));
query.addEventListener('input',()=>updateList({q:query.value}));
el('search-form').addEventListener('submit',e=>{
  e.preventDefault();
  if (results.getAttribute('aria-busy')==='true') return;
  const links=results.querySelectorAll('a[data-bird]');
  if (links.length===1) links[0].click();
});
el('reset').addEventListener('click',()=>{updateList({order:'',family:'',media:'',q:''});query.focus();});
el('previous').addEventListener('click',()=>updateList({page:currentPage-1},true));
el('next').addEventListener('click',()=>updateList({page:currentPage+1},true));
el('sources-button').addEventListener('click',showSources);
el('close-sources').addEventListener('click',()=>el('sources-dialog').close());
document.addEventListener('keydown',e=>{
  if (e.key==='Escape' && !el('sources-dialog').open && !el('record').hidden) el('record').querySelector('[data-back]')?.click();
});
history.scrollRestoration='manual';
// A history traversal between different language query strings can omit hashchange.
let traversalHash=null;
window.addEventListener('popstate',()=>{
  traversalHash=location.hash;
  routePage();
});
window.addEventListener('hashchange',()=>{
  if (traversalHash!==location.hash) routePage();
  traversalHash=null;
});
routePage();
