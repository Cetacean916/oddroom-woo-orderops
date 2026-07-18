(() => {
  'use strict';

  const normalizeOwnedSurface = () => {
    const email = document.querySelector('#email[autocomplete]');
    if (email && email.getAttribute('autocomplete') !== 'email') {
      email.setAttribute('autocomplete', 'email');
    }
    document.querySelectorAll('.wc-block-components-drawer__screen-overlay').forEach((overlay) => {
      if (overlay.querySelector('.wc-block-mini-cart__drawer')) {
        overlay.remove();
      }
    });
  };

  normalizeOwnedSurface();
  const observer = new MutationObserver(normalizeOwnedSurface);
  observer.observe(document.documentElement, { childList: true, subtree: true });
})();
