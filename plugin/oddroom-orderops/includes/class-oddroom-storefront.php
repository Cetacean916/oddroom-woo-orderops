<?php

defined('ABSPATH') || defined('ODDROOM_ORDEROPS_TESTING') || exit;

final class OddRoom_Storefront
{
    private const HOME_SHORTCODE = 'oddroom_orderops_home';
    private const ORDER_TRACKING_PAGE_OPTION = 'oddroom_orderops_order_tracking_page_id';
    private const CHECKOUT_MODE = 'ON_DEMAND_ONLY';
    private const CHECKOUT_LIMIT = 10;
    private const CHECKOUT_WINDOW_SECONDS = 900;
    private const CHECKOUT_RATE_OPTION_PREFIX = 'oddroom_checkout_v2_';

    public static function boot(): void
    {
        add_shortcode(self::HOME_SHORTCODE, [self::class, 'home']);
        add_action('wp_enqueue_scripts', [self::class, 'assets']);
        add_action('wp_body_open', [self::class, 'navigation']);
        add_action('wp_footer', [self::class, 'footer']);
        add_filter('wc_empty_cart_message', [self::class, 'emptyCartMessage']);
        add_filter('wp_robots', [self::class, 'robots']);
        add_filter('pre_wp_mail', [self::class, 'captureMail'], 10, 2);
        add_filter('woocommerce_available_payment_gateways', [self::class, 'syntheticGatewayOnly']);
        add_filter('woocommerce_price_trim_zeros', '__return_true');
        add_action('woocommerce_after_checkout_validation', [self::class, 'rateLimitClassicCheckout'], 10, 2);
        add_filter('rest_pre_dispatch', [self::class, 'rateLimitStoreApiCheckout'], 10, 3);
        add_action('wp_head', [self::class, 'favicon']);
        add_action('wp', [self::class, 'removeDuplicateSkipLink']);
        add_filter('render_block', [self::class, 'removeThemeChrome'], 10, 2);
        add_filter('body_class', [self::class, 'bodyClasses']);
    }

    public static function assets(): void
    {
        wp_enqueue_style(
            'oddroom-orderops-storefront',
            self::assetUrl('css/storefront.css'),
            [],
            '0.6.3'
        );
        wp_enqueue_script(
            'oddroom-orderops-storefront',
            self::assetUrl('js/storefront.js'),
            [],
            '0.6.3',
            ['in_footer' => true, 'strategy' => 'defer']
        );
    }

    public static function navigation(): void
    {
        if (is_admin()) {
            return;
        }
        $primary = self::isEnglish()
            ? [
                'Collection' => wc_get_page_permalink('shop'),
                'Objects' => home_url('/#offset-objects'),
                'Ordering' => home_url('/#offset-system'),
            ]
            : [
                '컬렉션' => wc_get_page_permalink('shop'),
                '오브젝트' => home_url('/#offset-objects'),
                '주문 안내' => home_url('/#offset-system'),
            ];
        echo '<a class="oddroom-skip" href="#oddroom-main">' . esc_html(self::text('본문으로 건너뛰기', 'Skip to content')) . '</a>';
        echo '<aside class="oddroom-announcement"><span>OFFSET / OBJECTS</span><p>'
            . esc_html(self::text('책상과 이동의 흐름을 정돈하는 두 가지 오브젝트', 'Two objects designed to bring order to desk and carry'))
            . '</p><span>DEMO · 0 KRW</span></aside>';
        echo '<header class="oddroom-frontbar"><nav class="oddroom-nav-primary" aria-label="' . esc_attr(self::text('주요 탐색', 'Primary navigation')) . '"><ul>';
        foreach ($primary as $label => $url) {
            echo '<li><a href="' . esc_url($url) . '">' . esc_html($label) . '</a></li>';
        }
        echo '</ul></nav>';
        echo '<a class="oddroom-wordmark" href="' . esc_url(home_url('/')) . '" aria-label="OFFSET ' . esc_attr(self::text('홈', 'home')) . '"><strong>OFFSET</strong><span>OBJECTS / QUIET UTILITY</span></a>';
        echo '<nav class="oddroom-nav-utility" aria-label="' . esc_attr(self::text('계정과 장바구니', 'Account and cart')) . '"><ul>';
        echo '<li><a href="' . esc_url(self::orderTrackingUrl()) . '">' . esc_html(self::text('주문 조회', 'Order lookup')) . '</a></li>';
        echo '<li><a href="' . esc_url(wc_get_cart_url()) . '">' . esc_html(self::text('장바구니', 'Cart')) . '</a></li>';
        echo '</ul></nav></header>';
        self::commerceIntro();
    }

    public static function home(): string
    {
        $shop = wc_get_page_permalink('shop');
        $orderTracking = self::orderTrackingUrl();
        $heroDesktop = self::assetUrl('images/quiet-utility/home/hero-desktop.webp');
        $heroMobile = self::assetUrl('images/quiet-utility/home/hero-mobile.webp');
        $packing = self::assetUrl('images/quiet-utility/home/order-packing.webp');
        $operator = self::assetUrl('images/quiet-utility/home/operator-scene.webp');
        $cta = self::assetUrl('images/quiet-utility/home/cta-still.webp');
        ob_start();
        ?>
        <div id="oddroom-main" class="oddroom-home">
            <section class="oddroom-hero" aria-labelledby="oddroom-hero-title">
                <figure class="oddroom-hero-visual">
                    <picture>
                        <source media="(max-width: 640px)" srcset="<?php echo esc_url($heroMobile); ?>">
                        <img src="<?php echo esc_url($heroDesktop); ?>" width="1920" height="1280" alt="<?php echo esc_attr(self::text('오프셋 독과 폴드라인 테크 케이스가 놓인 데스크 장면', 'A desk with an Offset Dock and Foldline Tech Case')); ?>">
                    </picture>
                    <div class="oddroom-hero-copy">
                        <p class="oddroom-kicker">OFFSET OBJECTS · DESK TO CARRY</p>
                        <h1 id="oddroom-hero-title"><?php echo wp_kses_post(self::text('하루의 흐름을<br><span>정돈하는 물건.</span>', 'Objects that bring<br><span>order to the day.</span>')); ?></h1>
                        <p class="oddroom-lead"><?php echo esc_html(self::text('케이블과 작은 도구를 제자리에. 책상 위에서도 이동 중에도 필요한 것만 단정하게 담아보세요.', 'Give cables and small tools a clear place, whether they stay on the desk or travel with you.')); ?></p>
                        <div class="oddroom-hero-actions">
                            <a class="oddroom-button oddroom-button-primary" href="<?php echo esc_url($shop); ?>"><?php echo esc_html(self::text('제품 보러 가기', 'Shop the collection')); ?></a>
                            <a class="oddroom-button oddroom-button-ghost" href="#offset-objects"><?php echo esc_html(self::text('두 제품 비교하기', 'Compare the objects')); ?></a>
                        </div>
                    </div>
                    <figcaption><span>01 / 02</span><strong>OFFSET DOCK + FOLDLINE CASE</strong><span><?php echo esc_html(self::text('주문 체험 · 0 KRW', 'ORDER DEMO · 0 KRW')); ?></span></figcaption>
                </figure>
            </section>

            <section class="oddroom-manifesto" aria-labelledby="offset-manifesto-title">
                <p class="oddroom-kicker">DESIGNED FOR ORDER</p>
                <h2 id="offset-manifesto-title"><?php echo wp_kses_post(self::text('흩어진 작은 것들이<br>제자리를 찾으면, <span>하루가 가벼워집니다.</span>', 'When the small things<br>find their place, <span>the day feels lighter.</span>')); ?></h2>
                <p><?php echo esc_html(self::text('OFFSET은 책상 위의 케이블부터 이동 중 필요한 소형 기기까지, 꺼내기 쉽고 다시 정리하기 좋은 형태를 고민합니다.', 'OFFSET gives desk cables and everyday devices a place that is easy to reach and simple to restore.')); ?></p>
            </section>

            <section id="offset-objects" class="oddroom-section oddroom-collection" aria-labelledby="oddroom-shop-title">
                <header><p class="oddroom-kicker">THE OFFSET COLLECTION · 01—02</p><h2 id="oddroom-shop-title"><?php echo esc_html(self::text('두 가지 오브젝트, 두 가지 쓰임.', 'Two objects, each with a clear purpose.')); ?></h2><p><?php echo esc_html(self::text('Offset Dock은 책상 위를, Foldline Tech Case는 가방 안을 정돈합니다. 지금 필요한 방식에 맞춰 골라보세요.', 'Offset Dock organizes the desk. Foldline Tech Case brings the same calm to your bag. Choose the one that fits today.')); ?></p></header>
                <?php echo wp_kses_post(self::productCards()); ?>
                <p class="oddroom-collection-link"><a class="oddroom-text-link" href="<?php echo esc_url($shop); ?>"><?php echo esc_html(self::text('전체 컬렉션 보기', 'View the full collection')); ?><span aria-hidden="true">↗</span></a></p>
            </section>

            <section class="oddroom-story-grid" aria-label="<?php echo esc_attr(self::text('선택부터 주문 확인까지 이어지는 장면', 'Scenes from selection through order lookup')); ?>">
                <article class="oddroom-story-order"><img src="<?php echo esc_url($packing); ?>" width="1600" height="1200" alt="<?php echo esc_attr(self::text('OFFSET 제품을 단정하게 포장하는 장면', 'An OFFSET object being carefully packed')); ?>"><div><p class="oddroom-kicker">FROM CHOICE TO ORDER · 01</p><h2><?php echo esc_html(self::text('고른 그대로, 주문 끝까지.', 'Your choice, carried through the order.')); ?></h2><p><?php echo esc_html(self::text('선택한 제품과 옵션, 수량을 주문이 완료될 때까지 분명하게 확인할 수 있습니다.', 'The object, finish, and quantity you choose stay clear through every step of the order.')); ?></p></div></article>
                <article class="oddroom-story-operator"><img src="<?php echo esc_url($operator); ?>" width="1600" height="1200" alt="<?php echo esc_attr(self::text('OFFSET 주문을 확인하는 장면', 'Reviewing an OFFSET order')); ?>"><div><p class="oddroom-kicker">AFTER THE ORDER · 02</p><h2><?php echo esc_html(self::text('주문 뒤에도 찾기 쉽게.', 'Easy to find, even after the order.')); ?></h2><p><?php echo esc_html(self::text('완료 화면의 주문 번호로 처리 상태를 확인하고 필요한 기록을 다시 찾아볼 수 있습니다.', 'Use the order number from confirmation to check its status whenever you need it.')); ?></p></div></article>
            </section>

            <section id="offset-system" class="oddroom-section oddroom-flow" aria-labelledby="oddroom-flow-title">
                <header><p class="oddroom-kicker">HOW YOUR ORDER WORKS</p><h2 id="oddroom-flow-title"><?php echo esc_html(self::text('고르고, 주문하고, 확인하세요.', 'Choose. Order. Check in.')); ?></h2><p><?php echo esc_html(self::text('일반 스토어처럼 제품을 고르고 주문을 마친 뒤, 주문 번호로 처리 상태까지 확인할 수 있습니다.', 'Browse and place an order as you would in a store, then use the order number to check its status.')); ?></p></header>
                <ol>
                    <li><span>01</span><div><p class="oddroom-flow-label">CHOOSE</p><h3><?php echo esc_html(self::text('고르기', 'Choose')); ?></h3><p><?php echo esc_html(self::text('제품의 쓰임과 이미지를 살펴보고 원하는 마감과 수량을 선택합니다.', 'Explore each object, then select the finish and quantity that suit you.')); ?></p></div></li>
                    <li><span>02</span><div><p class="oddroom-flow-label">ORDER</p><h3><?php echo esc_html(self::text('주문하기', 'Order')); ?></h3><p><?php echo esc_html(self::text('장바구니와 쿠폰을 확인한 뒤 0원 데모 주문을 완료합니다.', 'Review the cart and coupon, then complete the 0 KRW demo order.')); ?></p></div></li>
                    <li><span>03</span><div><p class="oddroom-flow-label">LOOK UP</p><h3><?php echo esc_html(self::text('확인하기', 'Check in')); ?></h3><p><?php echo esc_html(self::text('완료 화면의 주문 번호로 언제든 처리 상태를 다시 확인합니다.', 'Keep the confirmation number to look up the order whenever you need it.')); ?></p></div></li>
                </ol>
            </section>

            <section class="oddroom-cta" aria-labelledby="oddroom-cta-title">
                <img src="<?php echo esc_url($cta); ?>" width="1600" height="1200" alt="<?php echo esc_attr(self::text('OFFSET 컬렉션 상품 정물', 'OFFSET collection product still life')); ?>">
                <div class="oddroom-cta-copy"><p class="oddroom-kicker">START WITH AN OBJECT</p>
                <h2 id="oddroom-cta-title"><?php echo esc_html(self::text('당신의 자리에 맞는 오브젝트를 골라보세요.', 'Choose the object that fits your place.')); ?></h2>
                <p><?php echo esc_html(self::text('모든 주문은 0 KRW 데모로 진행되며 실제 결제·이메일·배송은 발생하지 않습니다.', 'Every order is a 0 KRW demo. No real payment, email, or delivery takes place.')); ?></p>
                <div class="oddroom-hero-actions"><a class="oddroom-button oddroom-button-primary" href="<?php echo esc_url($shop); ?>"><?php echo esc_html(self::text('제품 보러 가기', 'Shop the collection')); ?></a><a class="oddroom-button oddroom-button-ghost" href="<?php echo esc_url($orderTracking); ?>"><?php echo esc_html(self::text('주문 조회', 'Look up an order')); ?></a></div></div>
            </section>
        </div>
        <?php
        return (string) ob_get_clean();
    }

    public static function commerceIntro(): void
    {
        $isCategory = is_product_category();
        $isTracking = self::isOrderTrackingPage();
        if (!(is_shop() || $isCategory || is_product() || is_cart() || is_checkout() || is_account_page() || $isTracking)) {
            return;
        }
        $product = is_product() ? wc_get_product(get_queried_object_id()) : null;
        $isOrderReceived = is_checkout() && is_order_received_page();
        if (is_shop()) {
            $title = self::text('일과 이동을 위한 오브젝트', 'Objects for desk and carry');
            $kicker = 'OFFSET / OBJECT COLLECTION';
            $copy = self::text(
                '책상 위를 정돈하는 Offset Dock과 이동을 가볍게 만드는 Foldline Tech Case를 만나보세요.',
                'Meet Offset Dock for the desk and Foldline Tech Case for the things that travel with you.'
            );
            $marker = '01—02';
        } elseif ($isCategory) {
            $title = single_term_title('', false);
            $kicker = 'OFFSET / OBJECT COLLECTION';
            $copy = self::text(
                '매일 손이 가는 작은 도구를 더 편하게 꺼내고 정리할 수 있도록 만든 컬렉션입니다.',
                'A collection designed to keep everyday tools close, clear, and easy to put away.'
            );
            $marker = '01—02';
        } elseif ($product instanceof WC_Product) {
            $title = $product->get_name();
            $kicker = 'OFFSET / OBJECT DETAILS';
            $copy = $product->get_sku() === 'OFFSET-DOCK'
                ? self::text(
                    '충전 케이블과 자주 쓰는 작은 도구를 한곳에 모아 책상 위에 여유를 만듭니다.',
                    'Gather charging cables and everyday tools in one place, leaving more calm on the desk.'
                )
                : self::text(
                    '케이블과 소형 기기를 한눈에 정리하고, Graphite와 Sandstone 중 원하는 마감을 선택하세요.',
                    'Keep cables and small devices in view, then choose Graphite or Sandstone to suit your carry.'
                );
            $marker = $product->get_sku() === 'OFFSET-DOCK' ? 'OBJECT 01' : 'OBJECT 02';
        } elseif (is_cart()) {
            $title = self::text('선택한 제품', 'Your selection');
            $kicker = 'OFFSET / YOUR CART';
            $copy = self::text(
                '제품과 옵션, 수량을 확인한 뒤 주문을 이어가세요. 데모 주문이므로 실제 결제 금액은 발생하지 않습니다.',
                'Review the object, finish, and quantity, then continue. This demo order does not create a real charge.'
            );
            $marker = 'CART';
        } elseif ($isTracking) {
            $title = self::text('주문 조회', 'Order lookup');
            $kicker = 'OFFSET / ORDER LOOKUP';
            $copy = self::text(
                '완료한 주문의 번호와 이메일을 입력하면 현재 처리 상태를 다시 확인할 수 있습니다.',
                'Enter the order number and email from confirmation to check the current status.'
            );
            $marker = 'LOOKUP';
        } elseif (is_checkout()) {
            $title = $isOrderReceived
                ? self::text('주문이 완료되었습니다', 'Order complete')
                : self::text('주문하기', 'Checkout');
            $kicker = $isOrderReceived ? 'OFFSET / ORDER COMPLETE' : 'OFFSET / CHECKOUT';
            $copy = $isOrderReceived
                ? self::text(
                    '주문 번호를 보관해 두면 주문 조회에서 처리 상태를 다시 확인할 수 있습니다.',
                    'Keep the order number so you can return to Order lookup and check its status.'
                )
                : self::text(
                    '주문 정보를 입력하고 선택한 제품을 확인하세요. 모든 주문은 0 KRW 데모로 완료됩니다.',
                    'Enter the order details and review your selection. Every order completes as a 0 KRW demo.'
                );
            $marker = $isOrderReceived ? 'COMPLETE' : 'CHECKOUT';
        } else {
            $title = self::text('주문 내역', 'Your orders');
            $kicker = 'OFFSET / ORDER HISTORY';
            $copy = self::text(
                '완료한 주문을 확인하고 필요한 주문 기록을 다시 찾아보세요.',
                'Review completed orders and return to the details you need.'
            );
            $marker = 'ORDERS';
        }
        $classes = 'oddroom-commerce-intro';
        if (!(is_shop() || $isCategory)) {
            $classes .= ' oddroom-commerce-intro--compact';
        }
        if (is_product()) {
            $classes .= ' oddroom-commerce-intro--product';
        }
        $headingTag = is_shop() || $isCategory || is_product() || $isTracking || (is_checkout() && !is_order_received_page()) ? 'h1' : 'p';
        echo '<section id="oddroom-main" class="' . esc_attr($classes) . '" aria-label="' . esc_attr(self::text('OFFSET 상점 안내', 'OFFSET store guidance')) . '">';
        echo '<p class="oddroom-kicker">' . esc_html($kicker) . '</p><' . $headingTag . ' class="oddroom-commerce-title"><strong>' . esc_html($title) . '</strong><span>' . esc_html($marker) . '</span></' . $headingTag . '>';
        echo '<p class="oddroom-commerce-marker">' . esc_html($marker) . '</p>';
        echo '<p class="oddroom-commerce-copy">' . esc_html($copy);
        if (is_checkout() && !$isOrderReceived) {
            echo ' ' . esc_html(self::text('이름은 Synthetic / Buyer, 이메일은 소문자 @example.com 주소를 사용해 주세요.', 'Use Synthetic / Buyer and a lowercase @example.com email address.'));
        } elseif ($isTracking) {
            echo ' ' . esc_html(self::text('주문할 때 사용한 @example.com 이메일을 입력해 주세요.', 'Use the @example.com email entered at checkout.'));
        }
        echo '</p>';
        if (is_shop() || $isCategory) {
            echo '<aside class="oddroom-coupon-banner"><span>' . esc_html(self::text('첫 주문 혜택', 'A welcome benefit')) . '</span><strong>OFFSET10</strong><span>'
                . esc_html(self::text('주문 단계에서 10% 혜택', 'Save 10% at checkout'))
                . '</span></aside>';
        }
        echo '</section>';
    }

    public static function emptyCartMessage(string $message): string
    {
        return self::text('장바구니가 비어 있습니다. 당신의 책상과 이동에 맞는 OFFSET 오브젝트를 만나보세요.', 'Your cart is empty. Find the OFFSET object that fits your desk or carry.');
    }

    public static function footer(): void
    {
        if (is_admin()) {
            return;
        }
        echo '<footer class="oddroom-demo-footer" aria-label="' . esc_attr(self::text('OFFSET 안내', 'OFFSET information')) . '"><div class="oddroom-footer-brand"><strong>OFFSET</strong><span>OBJECTS / QUIET UTILITY</span></div><div><strong>' . esc_html(self::text('컬렉션', 'Collection')) . '</strong><a href="' . esc_url(wc_get_page_permalink('shop')) . '">' . esc_html(self::text('전체 제품', 'All objects')) . '</a><a href="' . esc_url(wc_get_cart_url()) . '">' . esc_html(self::text('장바구니', 'Cart')) . '</a></div><div><strong>' . esc_html(self::text('주문', 'Orders')) . '</strong><a href="' . esc_url(self::orderTrackingUrl()) . '">' . esc_html(self::text('주문 조회', 'Order lookup')) . '</a><a href="' . esc_url(home_url('/#offset-system')) . '">' . esc_html(self::text('주문 방법', 'How to order')) . '</a></div><div class="oddroom-footer-boundary"><strong>DEMO ORDER</strong><span>' . esc_html(self::text('실제 결제 없음', 'No real payment')) . '</span><span>' . esc_html(self::text('실제 배송 없음', 'No real delivery')) . '</span><span>0 KRW</span></div><p>© OFFSET / OBJECTS COLLECTION</p></footer>';
    }

    public static function removeDuplicateSkipLink(): void
    {
        remove_action('wp_enqueue_scripts', 'wp_enqueue_block_template_skip_link');
        remove_action('wp_footer', 'the_block_template_skip_link');
    }

    public static function bodyClasses(array $classes): array
    {
        if (self::isOrderTrackingPage()) {
            $classes[] = 'oddroom-order-tracking';
        }
        return $classes;
    }

    public static function favicon(): void
    {
        echo '<link rel="icon" href="' . esc_url(self::assetUrl('images/favicon.svg')) . '" type="image/svg+xml">';
    }

    public static function removeThemeChrome(string $content, array $block): string
    {
        if (is_admin() || ($block['blockName'] ?? null) !== 'core/template-part') {
            return $content;
        }
        $slug = (string) ($block['attrs']['slug'] ?? '');
        return in_array($slug, ['header', 'footer'], true) ? '' : $content;
    }

    public static function robots(array $robots): array
    {
        $robots['noindex'] = true;
        $robots['nofollow'] = true;
        $robots['noarchive'] = true;
        unset($robots['index'], $robots['follow']);
        return $robots;
    }

    public static function captureMail(mixed $return, array $attributes): mixed
    {
        if (!OddRoom_Repository::testMode()) {
            return $return;
        }
        $record = get_option('oddroom_orderops_mail_capture', ['count' => 0]);
        $count = is_array($record) ? (int) ($record['count'] ?? 0) : 0;
        update_option('oddroom_orderops_mail_capture', [
            'count' => $count + 1,
            'last_subject_sha256' => hash('sha256', (string) ($attributes['subject'] ?? '')),
            'last_captured_at_utc' => gmdate('c'),
        ], false);
        return true;
    }

    public static function syntheticGatewayOnly(array $gateways): array
    {
        if (!OddRoom_Repository::testMode()) {
            return $gateways;
        }
        return isset($gateways['cod']) ? ['cod' => $gateways['cod']] : [];
    }

    public static function rateLimitClassicCheckout(array $data, WP_Error $errors): void
    {
        if (!self::isSyntheticIdentity([
            'first_name' => $data['billing_first_name'] ?? null,
            'last_name' => $data['billing_last_name'] ?? null,
            'email' => $data['billing_email'] ?? null,
        ])) {
            $errors->add(
                'oddroom_checkout_synthetic_identity_required',
                self::text('데모 주문은 이름에 Synthetic / Buyer를, 이메일에는 소문자 @example.com 주소를 입력해 주세요.', 'For a demo order, enter Synthetic / Buyer and a lowercase @example.com email address.')
            );
            return;
        }
        if ($errors->has_errors()) {
            return;
        }
        if (!self::consumeCheckoutAllowance()) {
            $errors->add('oddroom_checkout_rate_limited', self::text('잠시 동안 주문 가능한 횟수를 모두 사용했습니다. 조금 뒤에 다시 시도해 주세요.', 'The order limit for this period has been reached. Please try again shortly.'));
        }
    }

    public static function rateLimitStoreApiCheckout(mixed $result, WP_REST_Server $server, WP_REST_Request $request): mixed
    {
        if ($result !== null
            || strtoupper($request->get_method()) !== 'POST'
            || !preg_match('#^/wc/store(?:/v\d+)?/checkout$#', $request->get_route())) {
            return $result;
        }
        $body = $request->get_json_params();
        $billing = is_array($body) && is_array($body['billing_address'] ?? null)
            ? $body['billing_address']
            : [];
        if (!self::isSyntheticIdentity($billing)) {
            return new WP_Error(
                'oddroom_checkout_synthetic_identity_required',
                self::text('데모 주문은 이름에 Synthetic / Buyer를, 이메일에는 소문자 @example.com 주소를 입력해 주세요.', 'For a demo order, enter Synthetic / Buyer and a lowercase @example.com email address.'),
                ['status' => 422]
            );
        }
        if (self::consumeCheckoutAllowance()) {
            return $result;
        }
        return new WP_Error(
            'oddroom_checkout_rate_limited',
            self::text('잠시 동안 주문 가능한 횟수를 모두 사용했습니다. 조금 뒤에 다시 시도해 주세요.', 'The order limit for this period has been reached. Please try again shortly.'),
            ['status' => 429]
        );
    }

    public static function isSyntheticIdentity(array $value): bool
    {
        if (!is_string($value['first_name'] ?? null)
            || !is_string($value['last_name'] ?? null)
            || !is_string($value['email'] ?? null)) {
            return false;
        }
        $firstName = trim($value['first_name']);
        $lastName = trim($value['last_name']);
        $email = trim($value['email']);
        return $firstName === 'Synthetic'
            && $lastName === 'Buyer'
            && $email === strtolower($email)
            && preg_match('/^[^@\s]+@example\.com$/Du', $email) === 1;
    }

    public static function checkoutRateOptionPrefix(): string
    {
        return self::CHECKOUT_RATE_OPTION_PREFIX;
    }

    public static function installDemoStore(): array
    {
        if (!class_exists('WooCommerce')) {
            throw new RuntimeException('WooCommerce is unavailable.');
        }
        $images = self::ensureStoreImages();
        $categoryId = self::ensureProductCategory();
        $simpleId = self::ensureSimpleProduct($images, $categoryId);
        $variable = self::ensureVariableProduct($images, $categoryId);
        $couponId = self::ensureCoupon();
        $homeId = self::ensureHomePage();
        $orderTrackingId = self::ensureOrderTrackingPage();
        self::localizeCommercePages();

        update_option('show_on_front', 'page');
        update_option('page_on_front', $homeId);
        update_option('blog_public', '0');
        update_option('blogname', 'OFFSET Objects');
        update_option('blogdescription', self::text('책상과 이동의 흐름을 정돈하는 오브젝트 컬렉션', 'Objects designed to bring order to desk and carry'));
        update_option('timezone_string', 'Asia/Seoul');
        update_option('woocommerce_currency', 'KRW');
        update_option('woocommerce_price_num_decimals', '2');
        update_option('woocommerce_default_country', 'KR');
        update_option('woocommerce_enable_guest_checkout', 'yes');
        update_option('woocommerce_coming_soon', 'no');
        update_option('woocommerce_store_pages_only', 'no');
        update_option(
            'woocommerce_checkout_privacy_policy_text',
            self::text(
                '입력한 데모 주문 정보는 이 화면에서 주문을 처리하고 조회하는 데만 사용됩니다. 실제 결제·이메일·배송은 발생하지 않습니다.',
                'Demo order information is used only to process and look up the order on this site. No real payment, email, or delivery occurs.'
            )
        );
        update_option(
            'woocommerce_registration_privacy_policy_text',
            self::text(
                '데모 주문 정보는 이 사이트 안에서만 사용되며 외부로 전송되지 않습니다.',
                'Demo order information remains inside this site and is not sent externally.'
            )
        );
        update_option('oddroom_orderops_checkout_control_mode', self::CHECKOUT_MODE, false);
        update_option('woocommerce_cod_settings', [
            'enabled' => 'yes',
            'title' => self::text('0원 데모 주문', '0 KRW demo order'),
            'description' => self::text('주문 화면을 체험하기 위한 전용 수단입니다. 카드나 계좌 정보는 입력하지 않습니다.', 'This option is provided for the order demo. No card or bank information is requested.'),
            'instructions' => self::text('주문이 접수되었습니다. 결제 금액은 0원입니다.', 'Your order has been received. The amount charged is 0 KRW.'),
            'enable_for_methods' => [],
            'enable_for_virtual' => 'yes',
        ]);
        foreach (['bacs', 'cheque', 'paypal'] as $gateway) {
            $settings = get_option('woocommerce_' . $gateway . '_settings', []);
            if (is_array($settings)) {
                $settings['enabled'] = 'no';
                update_option('woocommerce_' . $gateway . '_settings', $settings);
            }
        }
        flush_rewrite_rules(false);
        return [
            'home_page_id' => $homeId,
            'order_tracking_page_id' => $orderTrackingId,
            'simple_product_id' => $simpleId,
            'variable_product_id' => $variable['product_id'],
            'variation_ids' => $variable['variation_ids'],
            'coupon_id' => $couponId,
            'image_attachment_id' => $images['simple_main'],
            'image_attachment_ids' => $images,
            'checkout_control_mode' => self::CHECKOUT_MODE,
            'blog_public' => (string) get_option('blog_public'),
            'payment_gateway' => 'cod-relabelled-synthetic-no-funds',
        ];
    }

    private static function productCards(): string
    {
        $products = [];
        foreach (['OFFSET-DOCK', 'OFFSET-FOLDLINE'] as $sku) {
            $productId = wc_get_product_id_by_sku($sku);
            $product = $productId > 0 ? wc_get_product($productId) : null;
            if ($product instanceof WC_Product && $product->is_visible()) {
                $products[] = $product;
            }
        }
        if ($products === []) {
            return '<p>' . esc_html(self::text('OFFSET 컬렉션을 준비하고 있습니다.', 'The OFFSET collection is being prepared.')) . '</p>';
        }
        $html = '<div class="oddroom-product-grid">';
        foreach ($products as $index => $product) {
            if (!$product instanceof WC_Product) {
                continue;
            }
            $isSimple = $product->get_sku() === 'OFFSET-DOCK';
            $image = '<img src="' . esc_url(self::assetUrl($isSimple
                    ? 'images/quiet-utility/simple/shop-card.webp'
                    : 'images/quiet-utility/variable/shop-card.webp'))
                . '" width="1200" height="960" alt="'
                . esc_attr($isSimple
                    ? self::text('Offset Dock 상품 카드', 'Offset Dock product card')
                    : self::text('Graphite Foldline Tech Case 상품 카드', 'Graphite Foldline Tech Case product card')) . '">';
            $objectLabel = $isSimple ? self::text('데스크 오거나이저', 'DESK ORGANIZER') : self::text('테크 오거나이저', 'TECH ORGANIZER');
            $html .= '<article><a href="' . esc_url($product->get_permalink()) . '">'
                . $image
                . '<div class="oddroom-product-info"><span class="oddroom-product-index">0' . esc_html((string) ($index + 1)) . '</span><span class="oddroom-product-tag">' . esc_html($objectLabel) . '</span><h3>' . esc_html($product->get_name()) . '</h3>'
                . '<p class="price">' . wp_kses_post($product->get_price_html()) . '</p><span class="oddroom-card-link">' . esc_html(self::text('제품 보기', 'View object')) . '<span aria-hidden="true">↗</span></span></div></a></article>';
        }
        return $html . '</div>';
    }

    private static function consumeCheckoutAllowance(): bool
    {
        if (!OddRoom_Repository::testMode()) {
            return false;
        }
        global $wpdb;
        $address = isset($_SERVER['REMOTE_ADDR']) ? (string) $_SERVER['REMOTE_ADDR'] : 'unknown';
        $bucket = intdiv(time(), self::CHECKOUT_WINDOW_SECONDS);
        $currentPrefix = self::CHECKOUT_RATE_OPTION_PREFIX . $bucket . '_';
        $optionName = $currentPrefix . hash_hmac('sha256', $address, wp_salt('nonce'));

        $allowed = self::incrementCheckoutCounter($optionName);
        $wpdb->query($wpdb->prepare(
            "DELETE FROM {$wpdb->options}
             WHERE option_name LIKE %s AND option_name NOT LIKE %s
             LIMIT 100",
            $wpdb->esc_like(self::CHECKOUT_RATE_OPTION_PREFIX) . '%',
            $wpdb->esc_like($currentPrefix) . '%'
        ));
        return $allowed;
    }

    private static function incrementCheckoutCounter(string $optionName): bool
    {
        global $wpdb;
        $update = static function () use ($wpdb, $optionName): int|false {
            return $wpdb->query($wpdb->prepare(
                "UPDATE {$wpdb->options}
                 SET option_value = CAST(option_value AS UNSIGNED) + 1
                 WHERE option_name = %s
                   AND CAST(option_value AS UNSIGNED) < %d",
                $optionName,
                self::CHECKOUT_LIMIT
            ));
        };

        $updated = $update();
        if ($updated === 1) {
            return true;
        }
        if ($updated === false) {
            return false;
        }

        $inserted = $wpdb->query($wpdb->prepare(
            "INSERT IGNORE INTO {$wpdb->options} (option_name, option_value, autoload)
             VALUES (%s, '1', 'off')",
            $optionName
        ));
        if ($inserted === 1) {
            return true;
        }
        if ($inserted === false) {
            return false;
        }

        return $update() === 1;
    }

    private static function assetUrl(string $path): string
    {
        return plugins_url('assets/' . ltrim($path, '/'), dirname(__DIR__) . '/oddroom-orderops.php');
    }

    private static function isEnglish(): bool
    {
        $locale = function_exists('determine_locale') ? determine_locale() : get_locale();
        return str_starts_with((string) $locale, 'en_');
    }

    private static function text(string $korean, string $english): string
    {
        return self::isEnglish() ? $english : $korean;
    }

    private static function ensureHomePage(): int
    {
        $existing = get_page_by_path('oddroom-home', OBJECT, 'page');
        $post = [
            'post_title' => 'OFFSET Objects',
            'post_name' => 'oddroom-home',
            'post_content' => '[' . self::HOME_SHORTCODE . ']',
            'post_status' => 'publish',
            'post_type' => 'page',
        ];
        if ($existing instanceof WP_Post) {
            $post['ID'] = $existing->ID;
            $result = wp_update_post($post, true);
        } else {
            $result = wp_insert_post($post, true);
        }
        if (is_wp_error($result) || (int) $result < 1) {
            throw new RuntimeException('Home page setup failed.');
        }
        return (int) $result;
    }

    private static function ensureOrderTrackingPage(): int
    {
        $pageId = (int) get_option(self::ORDER_TRACKING_PAGE_OPTION, 0);
        $existing = $pageId > 0 ? get_post($pageId) : get_page_by_path('order-tracking', OBJECT, 'page');
        $post = [
            'post_title' => self::text('주문 조회', 'Order lookup'),
            'post_name' => 'order-tracking',
            'post_content' => '[woocommerce_order_tracking]',
            'post_status' => 'publish',
            'post_type' => 'page',
        ];
        if ($existing instanceof WP_Post) {
            $post['ID'] = $existing->ID;
            $result = wp_update_post($post, true);
        } else {
            $result = wp_insert_post($post, true);
        }
        if (is_wp_error($result) || (int) $result < 1) {
            throw new RuntimeException('Order tracking page setup failed.');
        }
        update_option(self::ORDER_TRACKING_PAGE_OPTION, (int) $result, false);
        return (int) $result;
    }

    private static function isOrderTrackingPage(): bool
    {
        $pageId = (int) get_option(self::ORDER_TRACKING_PAGE_OPTION, 0);
        return $pageId > 0 && is_page($pageId);
    }

    private static function orderTrackingUrl(): string
    {
        $pageId = (int) get_option(self::ORDER_TRACKING_PAGE_OPTION, 0);
        $url = $pageId > 0 ? get_permalink($pageId) : false;
        return is_string($url) && $url !== '' ? $url : wc_get_page_permalink('myaccount');
    }

    private static function ensureStoreImages(): array
    {
        $specs = [
            'simple_main' => ['simple/pdp-main.webp', '8d1d485d433458005bc02d4a34d30cd684fad3ce385b60993e48eb7b8ce17038', 'offset-dock-main.webp', 'Offset Dock', self::text('오프셋 구조의 화이트·세이지 데스크 독', 'White and sage Offset Dock with an asymmetric layout')],
            'simple_flatlay' => ['simple/flatlay.webp', '16644d6ab5b51d795f023b811348fee6c81b315015cb58e455291b356e3beed9', 'offset-dock-flatlay.webp', 'Offset Dock components', self::text('Offset Dock 구성품 플랫레이', 'Offset Dock component flat lay')],
            'simple_material' => ['simple/material-detail.webp', '372e0ad212f5be4b064cba0d82bee5f7e54b6d9365811da92ca32099fc25d15b', 'offset-dock-material.webp', 'Offset Dock material', self::text('Offset Dock 표면과 재질 디테일', 'Offset Dock surface and material detail')],
            'simple_in_use' => ['simple/in-use.webp', '65f3cc0103fc6200c9c3173378bff02c2c2764a8f623a2482f5657a871f34fa4', 'offset-dock-in-use.webp', 'Offset Dock in use', self::text('데스크에서 사용 중인 Offset Dock', 'Offset Dock in use on a desk')],
            'simple_packaging' => ['simple/packaging.webp', 'd489489a8017cdaac355d9f818516ea5903d12bc6461416c740f09c776a900e0', 'offset-dock-packaging.webp', 'Offset Dock packaging', self::text('Offset Dock 포장과 보조 정보', 'Offset Dock packaging and supporting information')],
            'variable_main' => ['variable/pdp-main.webp', '85970a4db7e1456a2b3983d91e9717012a7691021546adb2b751b57d1077d12f', 'foldline-main.webp', 'Foldline Tech Case', self::text('케이블과 소형 기기를 정리한 열린 Foldline Tech Case', 'Open Foldline Tech Case with organized cables and devices')],
            'variable_graphite' => ['variable/graphite.webp', '3647c26b1b5c4bf0204cb7131c13dfda030b60c5b41f51d493087f5cb6a54f8d', 'foldline-graphite.webp', 'Foldline Graphite', self::text('Graphite 옵션의 Foldline Tech Case', 'Foldline Tech Case in Graphite')],
            'variable_sandstone' => ['variable/sandstone.webp', '2e74f5d1d94c3a917ad15bc2089a4757c09fde100fa54730eb56bc75cb6d3132', 'foldline-sandstone.webp', 'Foldline Sandstone', self::text('Sandstone 옵션의 Foldline Tech Case', 'Foldline Tech Case in Sandstone')],
            'variable_comparison' => ['variable/comparison.webp', '96736cd63e7eee6dd7a2c87bb716b2d3bea754a40ef43c45855a3515c4790c88', 'foldline-comparison.webp', 'Foldline finishes', self::text('Graphite와 Sandstone Foldline Tech Case 비교', 'Graphite and Sandstone Foldline Tech Case comparison')],
            'variable_flatlay' => ['variable/flatlay.webp', 'f9190604cc8ebdbb86c2009fda07ceae81e7d882fcfb1d6775492728e8b1c3e1', 'foldline-flatlay.webp', 'Foldline components', self::text('Foldline Tech Case 구성품 플랫레이', 'Foldline Tech Case component flat lay')],
            'variable_zipper' => ['variable/zipper-detail.webp', 'e4cc2144ac64bdaf02a866e54aef361c9c08cb56c8641de9166a32f62addfec4', 'foldline-zipper.webp', 'Foldline zipper', self::text('Foldline Tech Case 지퍼와 재질 디테일', 'Foldline Tech Case zipper and material detail')],
            'variable_in_use' => ['variable/in-use.webp', 'bae416002819cbde522598c370c1a97cce234a33b33d9710434808f63c3f97c3', 'foldline-in-use.webp', 'Foldline in use', self::text('이동 중 사용하는 Foldline Tech Case', 'Foldline Tech Case in use while travelling')],
            'variable_back' => ['variable/back.webp', '7ce0d4a1caa5b67bfbcb1a88796e531fb8513b30f2fb5b00748b1292525bb991', 'foldline-back.webp', 'Foldline back', self::text('Foldline Tech Case 후면과 보조 정보', 'Foldline Tech Case back and supporting information')],
        ];
        $images = [];
        foreach ($specs as $key => [$path, $hash, $upload, $title, $alt]) {
            $images[$key] = self::ensureProductImage(
                'oddroom_orderops_image_' . $key,
                'quiet-utility/' . $path,
                $hash,
                $upload,
                $title,
                $alt
            );
        }
        return $images;
    }

    private static function ensureProductImage(
        string $optionName,
        string $relativePath,
        string $expectedHash,
        string $uploadName,
        string $title,
        string $alt
    ): int
    {
        $bytes = file_get_contents(dirname(__DIR__) . '/assets/images/' . $relativePath);
        if (!is_string($bytes) || hash('sha256', $bytes) !== $expectedHash) {
            throw new RuntimeException('Store image integrity check failed: ' . $relativePath);
        }
        $existing = (int) get_option($optionName, 0);
        if ($existing > 0 && get_post($existing) instanceof WP_Post) {
            wp_update_post(['ID' => $existing, 'post_title' => $title]);
            update_post_meta($existing, '_wp_attachment_image_alt', $alt);
            return $existing;
        }
        $upload = wp_upload_bits($uploadName, null, $bytes);
        if (!empty($upload['error'])) {
            throw new RuntimeException('Store image upload failed.');
        }
        $attachmentId = wp_insert_attachment([
            'post_mime_type' => 'image/webp',
            'post_title' => $title,
            'post_content' => '',
            'post_status' => 'inherit',
        ], $upload['file']);
        if (!is_int($attachmentId) || $attachmentId < 1) {
            throw new RuntimeException('Store image attachment failed.');
        }
        require_once ABSPATH . 'wp-admin/includes/image.php';
        wp_update_attachment_metadata($attachmentId, wp_generate_attachment_metadata($attachmentId, $upload['file']));
        update_post_meta($attachmentId, '_wp_attachment_image_alt', $alt);
        update_option($optionName, $attachmentId, false);
        return $attachmentId;
    }

    private static function ensureSimpleProduct(array $images, int $categoryId): int
    {
        $id = wc_get_product_id_by_sku('OFFSET-DOCK');
        if ($id <= 0) {
            $id = wc_get_product_id_by_sku('ODDROOM-DROP-KIT');
        }
        $product = $id > 0 ? wc_get_product($id) : new WC_Product_Simple();
        if (!$product instanceof WC_Product_Simple) {
            throw new RuntimeException('Simple product SKU conflicts with another product type.');
        }
        $product->set_name(self::text('Offset Dock · 오프셋 데스크 독', 'Offset Dock'));
        $product->set_slug('offset-dock');
        $product->set_sku('OFFSET-DOCK');
        $product->set_regular_price('39000');
        $product->set_virtual(true);
        $product->set_status('publish');
        $product->set_catalog_visibility('visible');
        $product->set_menu_order(0);
        $product->set_image_id($images['simple_main']);
        $product->set_gallery_image_ids([
            $images['simple_flatlay'],
            $images['simple_material'],
            $images['simple_in_use'],
            $images['simple_packaging'],
        ]);
        $product->set_category_ids([$categoryId]);
        $product->set_short_description(self::text(
            '충전 케이블과 자주 쓰는 작은 도구를 한곳에 모아두는 낮고 넓은 데스크 오거나이저입니다.',
            'A low, wide desk organizer that keeps charging cables and everyday tools together.'
        ));
        $product->set_description(self::text(
            '비대칭으로 나뉜 세 개의 트레이가 작은 물건마다 분명한 자리를 만듭니다. 책상 위에서 자주 쓰는 케이블과 액세서리를 손쉽게 꺼내고 다시 정리해 보세요.',
            'Three offset trays give small objects a clear place of their own. Keep frequently used cables and accessories within easy reach, then return them without clutter.'
        ));
        return (int) $product->save();
    }

    private static function ensureVariableProduct(array $images, int $categoryId): array
    {
        $id = wc_get_product_id_by_sku('OFFSET-FOLDLINE');
        if ($id <= 0) {
            $id = wc_get_product_id_by_sku('ODDROOM-CAMPAIGN-PACK');
        }
        $product = $id > 0 ? wc_get_product($id) : new WC_Product_Variable();
        if (!$product instanceof WC_Product_Variable) {
            throw new RuntimeException('Variable product SKU conflicts with another product type.');
        }
        $attribute = new WC_Product_Attribute();
        $attribute->set_name('Finish');
        $attribute->set_options(['Graphite', 'Sandstone']);
        $attribute->set_visible(true);
        $attribute->set_variation(true);
        $product->set_name(self::text('Foldline Tech Case · 폴드라인 테크 케이스', 'Foldline Tech Case'));
        $product->set_slug('foldline-tech-case');
        $product->set_sku('OFFSET-FOLDLINE');
        $product->set_status('publish');
        $product->set_catalog_visibility('visible');
        $product->set_menu_order(1);
        $product->set_image_id($images['variable_main']);
        $product->set_gallery_image_ids([
            $images['variable_comparison'],
            $images['variable_flatlay'],
            $images['variable_zipper'],
            $images['variable_in_use'],
            $images['variable_back'],
        ]);
        $product->set_category_ids([$categoryId]);
        $product->set_attributes([$attribute]);
        $product->set_default_attributes(['finish' => 'Graphite']);
        $product->set_short_description(self::text(
            '케이블과 충전기, 소형 기기를 한눈에 정리하는 테크 케이스입니다. Graphite와 Sandstone 중 원하는 마감을 선택하세요.',
            'A tech case that keeps cables, chargers, and small devices easy to see. Choose Graphite or Sandstone.'
        ));
        $product->set_description(self::text(
            '크기가 다른 포켓과 밴드가 이동 중 흩어지기 쉬운 도구를 제자리에 잡아줍니다. 가방을 열었을 때 필요한 물건을 바로 찾을 수 있도록 가볍고 단정하게 구성했습니다.',
            'A mix of pockets and bands keeps travel essentials in place. Open the case and find what you need without searching through the rest of the bag.'
        ));
        $productId = (int) $product->save();
        $variationIds = [];
        foreach ([
            'Graphite' => ['79000', 'OFFSET-FOLDLINE-GRAPHITE', 'ODDROOM-CAMPAIGN-CORE', $images['variable_graphite']],
            'Sandstone' => ['129000', 'OFFSET-FOLDLINE-SANDSTONE', 'ODDROOM-CAMPAIGN-PLUS', $images['variable_sandstone']],
        ] as $finish => [$price, $sku, $legacySku, $variationImage]) {
            $variationId = wc_get_product_id_by_sku($sku);
            if ($variationId <= 0) {
                $variationId = wc_get_product_id_by_sku($legacySku);
            }
            $variation = $variationId > 0 ? wc_get_product($variationId) : new WC_Product_Variation();
            if (!$variation instanceof WC_Product_Variation) {
                throw new RuntimeException('Variation SKU conflicts with another product type.');
            }
            $variation->set_parent_id($productId);
            $variation->set_sku($sku);
            $variation->set_attributes(['finish' => $finish]);
            $variation->set_image_id($variationImage);
            $variation->set_regular_price($price);
            $variation->set_virtual(true);
            $variation->set_status('publish');
            $variationIds[] = (int) $variation->save();
        }
        WC_Product_Variable::sync($productId);
        return ['product_id' => $productId, 'variation_ids' => $variationIds];
    }

    private static function ensureCoupon(): int
    {
        $couponId = wc_get_coupon_id_by_code('OFFSET10');
        if ($couponId <= 0) {
            $couponId = wc_get_coupon_id_by_code('ODDROOM10');
        }
        $coupon = $couponId > 0 ? new WC_Coupon($couponId) : new WC_Coupon();
        $coupon->set_code('OFFSET10');
        $coupon->set_discount_type('percent');
        $coupon->set_amount('10');
        $coupon->set_individual_use(true);
        $coupon->set_description(self::text('OFFSET 컬렉션 데모 주문에 적용되는 10% 혜택입니다.', 'A 10% benefit for an OFFSET collection demo order.'));
        return (int) $coupon->save();
    }

    private static function ensureProductCategory(): int
    {
        $existing = term_exists('demo-products', 'product_cat');
        if (is_array($existing)) {
            wp_update_term((int) $existing['term_id'], 'product_cat', ['name' => self::text('OFFSET 컬렉션', 'OFFSET Collection')]);
            return (int) $existing['term_id'];
        }
        if (is_int($existing) && $existing > 0) {
            wp_update_term($existing, 'product_cat', ['name' => self::text('OFFSET 컬렉션', 'OFFSET Collection')]);
            return $existing;
        }
        $created = wp_insert_term(self::text('OFFSET 컬렉션', 'OFFSET Collection'), 'product_cat', ['slug' => 'demo-products']);
        if (is_wp_error($created) || !is_array($created) || (int) ($created['term_id'] ?? 0) < 1) {
            throw new RuntimeException('Product category setup failed.');
        }
        return (int) $created['term_id'];
    }

    private static function localizeCommercePages(): void
    {
        foreach (self::isEnglish() ? [
            'woocommerce_shop_page_id' => ['OFFSET Collection', ''],
            'woocommerce_cart_page_id' => ['Cart', '[woocommerce_cart]'],
            'woocommerce_checkout_page_id' => ['Checkout', '[woocommerce_checkout]'],
            'woocommerce_myaccount_page_id' => ['Orders', '[woocommerce_my_account]'],
        ] : [
            'woocommerce_shop_page_id' => ['OFFSET 컬렉션', ''],
            'woocommerce_cart_page_id' => ['장바구니', '[woocommerce_cart]'],
            'woocommerce_checkout_page_id' => ['주문하기', '[woocommerce_checkout]'],
            'woocommerce_myaccount_page_id' => ['주문 내역', '[woocommerce_my_account]'],
        ] as $option => [$title, $content]) {
            $pageId = (int) get_option($option, 0);
            if ($pageId < 1) {
                continue;
            }
            $result = wp_update_post(['ID' => $pageId, 'post_title' => $title, 'post_content' => $content], true);
            if (is_wp_error($result)) {
                throw new RuntimeException('Commerce page localization failed.');
            }
        }
    }
}
