const preferenceKey = 'bird-archive-language';

function known(value) {
  return value === 'en' || value === 'zh' ? value : '';
}
function savedLanguage() {
  try { return known(localStorage.getItem(preferenceKey)); } catch { return ''; }
}
const sharedLanguage = known(new URL(location.href).searchParams.get('lang'));
export let language = sharedLanguage || savedLanguage() || 'zh';
export const t = (zh, en) => language === 'en' ? en : zh;
export const count = value => value.toLocaleString(t('zh-CN', 'en'));

const staticFields = [
  ['data-en', null], ['data-en-aria', 'aria-label'],
  ['data-en-placeholder', 'placeholder'], ['data-en-content', 'content']
].flatMap(([key, attribute]) => Array.from(document.querySelectorAll(`[${key}]`), node => ({
  node, attribute, zh: attribute ? node.getAttribute(attribute) : node.textContent,
  en: node.getAttribute(key)
})));

export function syncLanguageUrl() {
  const url = new URL(location.href);
  if (url.searchParams.get('lang') === language || (language === 'zh' && !url.searchParams.has('lang'))) return;
  url.searchParams.set('lang', language);
  history.replaceState(history.state, '', url);
}
function paintLanguage() {
  document.documentElement.lang = t('zh-CN', 'en');
  for (const {node, attribute, zh, en} of staticFields) {
    if (attribute) node.setAttribute(attribute, t(zh, en));
    else node.textContent = t(zh, en);
  }
  for (const button of document.querySelectorAll('button[data-lang]')) {
    button.setAttribute('aria-pressed', String(button.dataset.lang === language));
  }
}
export function chooseLanguage(value) {
  if (!known(value)) return;
  language = value;
  try { localStorage.setItem(preferenceKey, value); } catch { /* Storage may be disabled. */ }
  const url = new URL(location.href);
  url.searchParams.set('lang', value);
  history.replaceState(history.state, '', url);
  paintLanguage();
}
paintLanguage();
syncLanguageUrl();
