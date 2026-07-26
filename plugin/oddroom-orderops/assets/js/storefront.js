(() => {
  'use strict';

  const normalizeOwnedSurface = () => {
    const isKorean = document.documentElement.lang.toLowerCase().startsWith('ko');
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
      replacement.textContent = isKorean ? '주문 정보' : 'Order details';
      heading.replaceWith(replacement);
    });
    document.querySelectorAll('.woocommerce-billing-fields > h2').forEach((heading) => {
      const value = isKorean ? '주문 정보' : 'Order details';
      if (heading.textContent !== value) heading.textContent = value;
    });
    document.querySelectorAll('.checkout-button').forEach((button) => {
      const value = isKorean ? '주문 계속하기' : 'Continue to order';
      if (button.textContent !== value) button.textContent = value;
    });
    document.querySelectorAll('.woocommerce-column--billing-address > h2').forEach((heading) => {
      const value = isKorean ? '주문 연락처' : 'Order contact';
      if (heading.textContent !== value) heading.textContent = value;
    });
    document.querySelectorAll('.woocommerce-order-overview__payment-method').forEach((item) => {
      const value = isKorean ? '주문 방식:' : 'Order method:';
      const label = [...item.childNodes].find((node) => (
        node.nodeType === Node.TEXT_NODE && node.nodeValue.trim()
      ));
      if (label && label.nodeValue.trim() !== value) label.nodeValue = `${value}\n`;
    });
  };

  normalizeOwnedSurface();
  document.addEventListener('click', (event) => {
    const link = event.target instanceof Element
      ? event.target.closest('.oddroom-mobile-nav a')
      : null;
    if (link) {
      link.closest('details')?.removeAttribute('open');
    }
  });
  const observer = new MutationObserver(normalizeOwnedSurface);
  observer.observe(document.documentElement, { childList: true, subtree: true });
})();
