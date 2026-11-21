(() => {
  const root = document.documentElement;
  const preferenceKey = 'bird-archive-theme';

  function savedTheme() {
    try {
      return localStorage.getItem(preferenceKey) === 'light' ? 'light' : 'dark';
    } catch {
      return 'dark';
    }
  }

  function applyTheme(theme) {
    root.dataset.theme = theme;
    const color = document.querySelector('meta[name="theme-color"]');
    if (color?.dataset[theme]) color.content = color.dataset[theme];
  }

  // Set the palette before the browser reads the stylesheets.
  applyTheme(savedTheme());

  function bindToggle() {
    const button = document.getElementById('theme-toggle');
    if (!button) return;

    function updateButton() {
      const dark = root.dataset.theme === 'dark';
      const english = root.lang.toLowerCase().startsWith('en');
      button.setAttribute('aria-label', english ? 'Dark mode' : '深色模式');
      button.setAttribute('aria-pressed', String(dark));
      button.title = english
        ? (dark ? 'Switch to light mode' : 'Switch to dark mode')
        : (dark ? '切换为浅色模式' : '切换为深色模式');
    }

    button.addEventListener('click', () => {
      const next = root.dataset.theme === 'dark' ? 'light' : 'dark';
      applyTheme(next);
      try {
        localStorage.setItem(preferenceKey, next);
      } catch {
        // The current page can still switch when storage is unavailable.
      }
      updateButton();
    });
    window.addEventListener('storage', event => {
      if (event.key !== preferenceKey && event.key !== null) return;
      applyTheme(savedTheme());
      updateButton();
    });
    new MutationObserver(updateButton).observe(root, {
      attributes: true, attributeFilter: ['lang']
    });
    updateButton();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bindToggle, {once: true});
  } else {
    bindToggle();
  }
})();
