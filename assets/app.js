const el = id => document.getElementById(id);
const gallery = 'gallery';
const checklist = 'checklist';
const perPage = 40;
const taxonomyPage = 'https://www.avilist.org/checklist/v2026/';
const attributionLicense = 'https://creativecommons.org/licenses/by/4.0/';
const number = new Intl.NumberFormat('zh-CN');
const query = el('query');
const results = el('results');
const photoById = new Map();
const photoByLatin = new Map();
const speciesById = new Map();
const speciesByLatin = new Map();
const observationPhotos = new Map();
const accountShards = new Map();
let photos, catalog, names, directories, namesWarning = false;
let photoRequest, catalogRequest, namesRequest;
let observationIndex, observationRequest, observationWarning = false, galleryData;
let references, referencesRequest, coverage;
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
async function json(path) {
  const response = await fetch(path);
  if (!response.ok) throw new Error('HTTP ' + response.status);
  return response.json();
}
function loadPhotos() {
  if (!photoRequest) photoRequest = json('data/photos.json').then(rows => {
    for (const photo of rows) {
      photoById.set(photo.id, photo);
      photoByLatin.set(photo.latin, photo);
      photo.search = normalize([photo.name,photo.aliases,photo.en,photo.latin,photo.order,photo.family].join(' '));
    }
    photos = rows;
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
  const response=await fetch(path);
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
      imageUrl:asset.imageUrl,thumbUrl:secureUrl(asset.thumbUrl) || asset.imageUrl,localThumb,observationUrl:asset.sourceUrl,
      credit:{filePage:secureUrl(asset.filePage) || asset.sourceUrl,author:asset.author,license:asset.license,licenseUrl:asset.licenseUrl},
      changes: localThumb ? '本馆缩略图经缩小并转为 WebP，总览按画框裁切。' : '总览按画框裁切，详情保留来源图像的比例。',
      search:normalize([name,species.en,species.latin,localized?.aliases?.join(' '),taxonLabel('orders',species.order),taxonLabel('families',species.family)].join(' '))
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
  const entry = names?.[kind]?.[latin];
  return entry?.zh ? entry.zh + ' · ' + latin : latin;
}
function prepareDirectory() {
  if (directories) return directories;
  buildPhotos();
  directories = catalog.species.map(species => {
    const photo = photoByLatin.get(species.latin) || observationPhotos.get(species.id);
    const localized = names?.names?.[species.latin];
    const search = normalize([species.en,species.latin,chinese(species),species.genus,taxonLabel('orders',species.order),
      taxonLabel('families',species.family),localized?.zh,localized?.aliases?.join(' '),photo?.search].join(' '));
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
  return {
    view,
    all:view===gallery && params.get('scope')!=='selected',
    id, q:params.get('q') || '', order:params.get('order') || '', family:params.get('family') || '',
    page: Math.max(1,parseInt(params.get('page'),10) || 1)
  };
}
function urlFor(route) {
  const params = new URLSearchParams();
  if (route.id && (route.view === checklist || route.id.startsWith('avibase-'))) params.set('from',route.view);
  if (route.all===false && route.view===gallery) params.set('scope','selected');
  for (const key of ['q','order','family']) if (route[key]) params.set(key,route[key]);
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
  for (const link of document.querySelectorAll('[data-section]')) {
    if (link.dataset.section === section) link.setAttribute('aria-current','page');
    else link.removeAttribute('aria-current');
  }
}
function backButton(route) {
  const a = element('a','return',route.view === checklist ? '返回全球名录' : '返回影像总览');
  a.href = urlFor({...route,id:''});
  a.dataset.back = '';
  return a;
}
function statusBox(message, retry) {
  const div = element('div','empty');
  div.setAttribute('role','status');
  div.append(element('p','',message));
  if (retry) {
    const btn=element('button','line-button','重新加载');
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
  const isDirectory = route.view === checklist || route.all;
  const tabs = el('paper-tabs');
  tabs.hidden = isDirectory;
  el('taxonomy').hidden = !isDirectory;
  document.querySelector('.index-row').classList.toggle('directory-mode',isDirectory);
  el('index-label').textContent = isDirectory ? '分类索引' : '按目浏览';
  if (!isDirectory) {
    const orders = ['',...new Set(rows.map(p => p.order))];
    if (tabs.childElementCount !== orders.length) {
      tabs.replaceChildren(...orders.map(order => {
        const btn = element('button','tab',order || '全部');
        btn.type='button';
        btn.dataset.order = order;
        return btn;
      }));
    }
    for (const button of tabs.children) button.setAttribute('aria-pressed', String(route.order === button.dataset.order));
    return;
  }
  const key=route.view+':'+rows.length+':'+namesWarning;
  const taxon=row=>row.species || speciesByLatin.get(row.latin) || row;
  if (el('order').dataset.version !== key) {
    const orders = [...new Set(rows.map(r=>taxon(r).order))].filter(Boolean);
    optionList(el('order'),orders,route.order,'全部目','orders');
    el('order').dataset.version = key;
    delete el('family').dataset.order;
  }
  el('order').value = route.order;
  if (el('family').dataset.order !== route.order) {
    const familyRows = route.order ? rows.filter(r => taxon(r).order === route.order) : rows;
    optionList(el('family'), [...new Set(familyRows.map(r=>taxon(r).family))].filter(Boolean), route.family, '全部科','families');
    el('family').dataset.order = route.order;
  }
  el('family').value = route.family;
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
  img.alt = full ? photo.name+'，摄影：'+photo.credit.author : '';
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
    img.replaceWith(element('span','unavailable-photo','照片暂时无法载入'));
  });
  return img;
}
function photoCards(rows,route) {
  const grid = element('div','photo-grid');
  for (const [index,photo] of rows.entries()) {
    const link = birdLink(route,photo.id,'bird-card');
    const frame = element('span','image-frame');
    const img=photoFigure(photo);
    if (index < 3) img.loading = 'eager';
    frame.append(img);
    link.append(frame,element('span','caption',photo.name));
    grid.append(link);
  }
  return grid;
}
function directoryTable(rows,route) {
  const table = element('table','directory');
  const head = table.createTHead().insertRow();
  for (const label of ['鸟名','学名','科']) {
    const th = element('th','',label); th.scope='col'; head.append(th);
  }
  const body=table.createTBody();
  for (const {species,photo} of rows) {
    const name=chinese(species);
    const tr=body.insertRow();
    const td=tr.insertCell();
    td.append(birdLink(route,photo?.id || species.id,'',name || species.en || species.latin));
    if (name && species.en) td.append(element('span','secondary',species.en));
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
    const selected=navigationLink('摄影选集',{view:gallery,all:false,q:route.q});
    const all=navigationLink('全部实拍',{view:gallery,all:true,q:route.q});
    (route.all ? all : selected).setAttribute('aria-current','page');
    info.replaceChildren(all,selected,navigationLink('查阅全球名录',{view:checklist,q:route.q}));
    return;
  }
  if (!coverage) {
    const indexed=catalog.species.filter(species=>Boolean(chinese(species))).length;
    const photographed=new Set(buildPhotos().map(p=>speciesByLatin.get(p.latin)?.id).filter(Boolean)).size;
    coverage={indexed,photographed};
  }
  const details=['全球名录 '+number.format(catalog.species.length)+' 种',
    (observationWarning || !photos ? '已载入实拍 ' : '有实拍 ')+number.format(coverage.photographed)+' 种',
    namesWarning ? '中文索引暂未载入' : '有中文名 '+number.format(coverage.indexed)+' 种'];
  info.replaceChildren(...details.map(label=>element('span','',label)));
}
function drawList(route) {
  const isDirectory = route.view === checklist;
  const combinedReady=catalog && (observationIndex || observationWarning) && (names || namesWarning);
  const sourceRows = isDirectory ? (catalog ? prepareDirectory() : null) : (route.all ? (combinedReady ? buildPhotos() : null) : photos);
  if (!sourceRows) return;
  showCollectionInfo(route);
  query.value = route.q;
  fillFilters(route,sourceRows);
  el('reset').hidden = !(route.q || route.order || route.family);
  const words = normalize(route.q).split(/\s+/).filter(Boolean);
  const matching = sourceRows.filter(row => {
    const species = isDirectory ? row.species : (route.all ? speciesByLatin.get(row.latin) || row : row);
    return (!route.order || species.order === route.order) &&
      (!route.family || species.family === route.family) && words.every(w => row.search.includes(w));
  });
  const limit=isDirectory ? perPage : 24;
  lastPage = Math.max(1,Math.ceil(matching.length/limit));
  currentPage = Math.min(lastPage,route.page);
  if (route.page !== currentPage) {
    route.page=currentPage;
    history.replaceState(history.state,'',urlFor(route));
  }
  el('total').textContent = number.format(matching.length)+' 种';
  el('status').textContent = '找到 '+number.format(matching.length)+' 种鸟';
  el('pager').hidden = lastPage < 2;
  el('previous').disabled = currentPage===1;
  el('next').disabled = currentPage===lastPage;
  el('page-number').textContent = currentPage+' / '+lastPage;
  if (!matching.length) {
    const box = statusBox('没有找到符合条件的鸟种。');
    if (!isDirectory && route.q) {
      const a = element('a','text-button','在全球名录中查找');
      a.href=urlFor({view:checklist,q:route.q});a.dataset.nav='';box.append(a);
    }
    results.replaceChildren(box);
  } else {
    const pageRows=matching.slice((currentPage-1)*limit,currentPage*limit);
    results.replaceChildren(isDirectory ? directoryTable(pageRows,route) : photoCards(pageRows,route));
  }
  if (isDirectory && namesWarning) {
    const box=statusBox('中文名称暂时未载入，可用英文名和学名检索。',routePage);
    results.prepend(box);
  }
  if ((isDirectory || route.all) && observationWarning) results.append(statusBox('扩展实拍索引暂时无法载入，已保留可用档案。',routePage));
}
function creditLinks(photo) {
  return [external(photo.credit.filePage,photo.credit.author),' · ',external(photo.credit.licenseUrl,photo.credit.license)];
}
function fact(list,label,value) {
  if (!value) return;
  list.append(element('dt','',label),element('dd','',value));
}
function readingLinks(group,species,photo) {
  const item=references?.[species?.id] || {};
  const links=[];
  if (item.ebird && /^[a-z\d_-]+$/i.test(item.ebird)) links.push(external('https://ebird.org/species/'+item.ebird,'eBird 照片与声音'));
  if (secureUrl(item.birdlife)) links.push(external(item.birdlife,'BirdLife'));
  if (secureUrl(item.bow)) links.push(external(item.bow,'Birds of the World'));
  if (/^\d+$/.test(item.inat)) links.push(external('https://www.inaturalist.org/taxa/'+item.inat,'iNaturalist 物种记录'));
  if (/^\d+$/.test(item.gbif)) links.push(external('https://www.gbif.org/species/'+item.gbif,'GBIF'));
  if (!item.inat) {
    const latin=species?.latin || photo?.latin;
    if (latin) links.push(external('https://www.inaturalist.org/observations?taxon_name='+encodeURIComponent(latin),'按学名搜索 iNaturalist 观测'));
  }
  group.replaceChildren(element('h2','','延伸查阅'),...links);
}
async function showAccount(group,id) {
  const match=/^avibase-([0-9a-f]{2})[0-9a-f]{6}$/i.exec(id);
  if (!match) return;
  const key=match[1].toLowerCase();
  if (!accountShards.has(key)) {
    const request=optionalJson('data/accounts/'+key+'.json').catch(()=>{
      accountShards.delete(key);
      return {};
    });
    accountShards.set(key,request);
  }
  const account=(await accountShards.get(key))[id];
  if (!group.isConnected || !account?.text || !['zh','en'].includes(account.lang) ||
      !/^https:\/\/(?:zh|en)\.wikipedia\.org\//i.test(secureUrl(account.url))) return;
  const paragraph=element('p','note',account.text);
  paragraph.lang=account.lang;
  const credit=element('p','source-link','据 BirdNET+ 收录的');
  credit.append(external(account.url,'维基百科条目及其贡献者'),'摘录 · ',
    external('https://creativecommons.org/licenses/by-sa/4.0/','CC BY-SA 4.0'));
  group.replaceChildren(element('h2','',account.lang==='en' ? '物种简介（英文原文）' : '物种简介'),paragraph,credit);
  group.hidden=false;
}
function showRecord(route,photo,species) {
  const body=element('article','record-body');
  const top=element('div','record-top');
  top.append(element('span','record-stamp','物种档案'),element('span','record-id',photo?.id || species.id));
  const name=photo?.name || chinese(species) || species.en || species.latin;
  const title=element('h1','',name);
  title.id='record-title';title.tabIndex=-1;
  document.title=name+' · 鸟类档案馆';
  body.append(top,title,element('p','scientific',photo?.latin || species.latin));
  const facts=element('dl','facts');
  fact(facts,'英文名',photo?.en || species.en);
  fact(facts,'目',species ? taxonLabel('orders',species.order) : photo.order);
  fact(facts,'科',species ? taxonLabel('families',species.family) : photo.family);
  fact(facts,'属',species?.genus || photo?.latin.split(' ')[0]);
  if (species?.extinction) fact(facts,'名录状态（原文）',species.extinction);
  if (!photo) fact(facts,'影像','照片待补');
  body.append(facts);
  if (photo?.note) {
    body.append(element('h2','','辨识要点'),element('p','note',photo.note));
    const source = element('p','source-link','辨识资料 · ');
    source.append(external(photo.url,photo.source));body.append(source);
  }
  const account=element('section','species-account');
  account.hidden=true;
  body.append(account);
  if (species?.range) {
    const heading=element('h2','range-title','分布范围');
    const description=element('p','note',species.range);description.lang='en';
    body.append(heading,description);
  }
  if (species) {
    const source=element('p','source-link','名录与分布资料 · ');
    source.append(external(taxonomyPage,'AviList '+catalog.version),' · ',external(attributionLicense,'CC BY 4.0'));
    body.append(source);
  }
  const links=element('div','reading-links');
  readingLinks(links,species,photo);
  body.append(links);
  if (!references) loadReferences().then(()=>{
    if (links.isConnected) readingLinks(links,species,photo);
  });
  const folio=element('div','folio'+(photo?'':' no-photo'));
  if (photo) {
    const figure=element('figure');
    const img=photoFigure(photo,true);img.className='record-photo';
    const caption=element('figcaption');
    if (photo.observationUrl) {
      caption.append('摄影 · ',photo.credit.author,' · ',external(photo.credit.licenseUrl,photo.credit.license),
        ' · ',external(photo.observationUrl,'原始照片'),element('br'),'Avicommons / iNaturalist');
      if (photo.credit.license.includes('NC')) caption.append(' · 限非商业使用');
    } else {
      caption.append('摄影 · ',...creditLinks(photo));
    }
    caption.append(element('br'),photo.changes);
    figure.append(img,caption);folio.append(figure);
  }
  folio.append(body);
  el('record').replaceChildren(backButton(route),folio);
  if (species) showAccount(account,species.id);
}
async function routePage() {
  const token=++revision;
  const route=readRoute();
  const detail=Boolean(route.id);
  toggle(route.view,detail);
  el('pager').hidden = true;
  const target=detail ? el('record') : results;
  if (!detail) {
    el('browse-title').textContent=route.view===gallery ? '馆藏影像' : '全球鸟类名录';
    document.title=el('browse-title').textContent+' · 鸟类档案馆';
    el('total').textContent='';
    el('collection-info').replaceChildren();
    query.value=route.q;
    el('paper-tabs').hidden=route.view!==gallery;
    el('taxonomy').hidden=route.view!==checklist;
    el('reset').hidden=true;
  }
  target.replaceChildren(statusBox('正在读取档案…'));
  try {
    const needCatalog = detail ? !route.id.startsWith('BH-') : route.view===checklist || route.all;
    if (needCatalog) {
      // Paint the locally hosted collection before downloading the larger global indexes.
      if (!detail && route.view===gallery && !galleryData) {
        await loadPhotos().catch(()=>{});
        if (token!==revision) return;
        const current=readRoute();
        if (photos && current.page===1 && !current.order && !current.family && !current.q) {
          el('total').textContent='正在读取全部实拍…';
          el('paper-tabs').hidden=true;
          el('taxonomy').hidden=true;
          showCollectionInfo(current);
          results.replaceChildren(photoCards(photos.slice(0,24),current));
          await new Promise(resolve=>requestAnimationFrame(resolve));
          if (token!==revision) return;
        }
      }
      await Promise.all([loadCatalog(),loadNames(),loadObservations(),loadPhotos().catch(()=>{})]);
      buildPhotos();
    } else {
      await loadPhotos();
    }
    if (token!==revision) return;
    if (!detail) {
      drawList(readRoute());
    } else {
      const species=speciesById.get(route.id) || speciesByLatin.get(photoById.get(route.id)?.latin);
      const photo=photoById.get(route.id) || photoByLatin.get(species?.latin) || observationPhotos.get(species?.id);
      if (!species && !photo) {
        target.replaceChildren(backButton(route),statusBox('这份物种档案不存在。'));
        document.title='未找到档案 · 鸟类档案馆';
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
    restorePosition(token,detail);
  } catch {
    if (token!==revision) return;
    if (!detail && route.view===gallery && route.all && !photos) {
      await loadPhotos().catch(()=>{});
      if (token!==revision) return;
    }
    if (!detail && route.view===gallery && route.all && photos) {
      const fallback={...readRoute(),view:gallery,all:false,order:'',family:'',page:1};
      history.replaceState(history.state,'',urlFor(fallback));
      drawList(fallback);
      results.append(statusBox('扩展名录尚未载入，当前显示摄影选集。',()=>navigate(urlFor(route))));
      return;
    }
    const box=statusBox('资料暂时无法载入，请检查网络后重试。',routePage);
    target.replaceChildren(...(detail ? [backButton(route),box] : [box]));
  }
}
function showSources() {
  const content=el('sources-content');
  const text=element('p');
  text.append('分类与分布数据取自 AviList Core Team 的 ',external(taxonomyPage,'AviList v2026'),'，按 ',external(attributionLicense,'CC BY 4.0'),' 授权使用。本馆提取种级条目和分类字段，并保留分布原文。');
  const list=element('ul','source-list');
  for (const photo of photos || []) {
    const li=element('li','',photo.name+'　');li.append(...creditLinks(photo));list.append(li);
  }
  const nameInfo=element('p');
  nameInfo.append('中文索引整理自 BirdNET Team 的 ',external(names?.sourceUrl || 'https://birdnet.cornell.edu/taxonomy/about#license','BirdNET+ Taxonomy v0.5-Nov2026'),'，采用 ',
    external(names?.licenseUrl || 'https://creativecommons.org/licenses/by-sa/4.0/','CC BY-SA 4.0'),' 许可，并从 Wikidata 贡献者的 ',
    external(names?.wikidataLicense || 'https://www.wikidata.org/wiki/Wikidata:Licensing','CC0 数据'),' 补充名称。按学名与分类阶元匹配，合并地区用名作为别名。详见',external('data/chinese-names.json','中文索引来源记录'),'。');
  const otherPhotos=element('p');
  otherPhotos.append('扩展图库采用 Adam Jackson 在 ',external('https://avicommons.org/','Avicommons'),' 整理的 iNaturalist 摄影。每张照片按详情页所列许可展示，标为 NC 的照片限非商业使用。');
  content.replaceChildren(text,nameInfo,element('p','','摄影选集的照片来自 Wikimedia Commons。选集使用等比例缩小的 WebP，卡片裁切展示，详情保留完整构图。'),list,otherPhotos);
  el('sources-dialog').showModal();
}
document.addEventListener('click',event => {
  if (event.button!==0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
  const link=event.target.closest('a[data-nav],a[data-back],a.skip-link');
  if (!link) return;
  event.preventDefault();
  if (link.classList.contains('skip-link')) { el('content').focus(); return; }
  if (link.hasAttribute('data-back') && history.state?.entered) { history.back(); return; }
  navigate(link.hash,link.dataset.bird);
});
el('paper-tabs').addEventListener('click',e => {
  const button=e.target.closest('button[data-order]');
  if (button) updateList({order:button.dataset.order,family:''});
});
el('order').addEventListener('change',e=>updateList({order:e.target.value,family:''}));
el('family').addEventListener('change',e=>updateList({family:e.target.value}));
query.addEventListener('input',()=>updateList({q:query.value}));
el('search-form').addEventListener('submit',e=>{
  e.preventDefault();
  const links=results.querySelectorAll('a[data-bird]');
  if (links.length===1) links[0].click();
});
el('reset').addEventListener('click',()=>{updateList({order:'',family:'',q:''});query.focus();});
el('previous').addEventListener('click',()=>updateList({page:currentPage-1},true));
el('next').addEventListener('click',()=>updateList({page:currentPage+1},true));
el('sources-button').addEventListener('click',showSources);
el('close-sources').addEventListener('click',()=>el('sources-dialog').close());
document.addEventListener('keydown',e=>{
  if (e.key==='Escape' && !el('sources-dialog').open && !el('record').hidden) el('record').querySelector('[data-back]')?.click();
});
history.scrollRestoration='manual';
// Native Back/Forward and manually opened hash URLs both trigger hashchange.
window.addEventListener('hashchange',routePage);
routePage();
