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
    document.querySelectorAll('td[scope]').forEach((cell) => cell.removeAttribute('scope'));
    document.querySelectorAll('.woocommerce-billing-fields > h3').forEach((heading) => {
      const replacement = document.createElement('h2');
      for (const attribute of heading.attributes) {
        replacement.setAttribute(attribute.name, attribute.value);
      }
      replacement.innerHTML = heading.innerHTML;
      heading.replaceWith(replacement);
    });
  };

  normalizeOwnedSurface();
  const observer = new MutationObserver(normalizeOwnedSurface);
  observer.observe(document.documentElement, { childList: true, subtree: true });
})();
