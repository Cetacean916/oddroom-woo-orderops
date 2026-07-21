<?php

defined('ABSPATH') || defined('ODDROOM_ORDEROPS_TESTING') || exit;

final class OddRoom_Storefront
{
    private const HOME_SHORTCODE = 'oddroom_orderops_home';
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
        add_action('woocommerce_after_checkout_validation', [self::class, 'rateLimitClassicCheckout'], 10, 2);
        add_filter('rest_pre_dispatch', [self::class, 'rateLimitStoreApiCheckout'], 10, 3);
        add_action('wp_head', [self::class, 'favicon']);
        add_filter('render_block', [self::class, 'removeThemeChrome'], 10, 2);
    }

    public static function assets(): void
    {
        wp_enqueue_style(
            'oddroom-orderops-storefront',
            self::assetUrl('css/storefront.css'),
            [],
            '0.5.0'
        );
        wp_enqueue_script(
            'oddroom-orderops-storefront',
            self::assetUrl('js/storefront.js'),
            [],
            '0.5.0',
            ['in_footer' => true, 'strategy' => 'defer']
        );
    }

    public static function navigation(): void
    {
        if (is_admin()) {
            return;
        }
        $links = self::isEnglish()
            ? [
                'Home' => home_url('/'),
                'Demo shop' => wc_get_page_permalink('shop'),
                'Cart' => wc_get_cart_url(),
                'Checkout' => wc_get_checkout_url(),
                'Orders' => wc_get_page_permalink('myaccount'),
            ]
            : [
                '홈' => home_url('/'),
                '데모 상품' => wc_get_page_permalink('shop'),
                '장바구니' => wc_get_cart_url(),
                '합성 주문' => wc_get_checkout_url(),
                '주문 조회' => wc_get_page_permalink('myaccount'),
            ];
        echo '<a class="oddroom-skip" href="#oddroom-main">' . esc_html(self::text('본문으로 건너뛰기', 'Skip to content')) . '</a>';
        echo '<div class="oddroom-frontbar"><a class="oddroom-wordmark" href="' . esc_url(home_url('/')) . '" aria-label="OddRoom OrderOps ' . esc_attr(self::text('홈', 'home')) . '"><img src="' . esc_url(self::assetUrl('images/brand/symbol.svg')) . '" width="30" height="30" alt="">ODDROOM <span>/ ORDEROPS</span></a>';
        echo '<nav aria-label="' . esc_attr(self::text('데모 상점 탐색', 'Demo store navigation')) . '"><ul>';
        foreach ($links as $label => $url) {
            echo '<li><a href="' . esc_url($url) . '">' . esc_html($label) . '</a></li>';
        }
        echo '</ul></nav><p>DEMO MODE · 0 KRW</p></div>';
        self::commerceIntro();
    }

    public static function home(): string
    {
        $shop = wc_get_page_permalink('shop');
        $account = wc_get_page_permalink('myaccount');
        $heroDesktop = self::assetUrl('images/quiet-utility/home/hero-desktop.webp');
        $heroMobile = self::assetUrl('images/quiet-utility/home/hero-mobile.webp');
        $packing = self::assetUrl('images/quiet-utility/home/order-packing.webp');
        $operator = self::assetUrl('images/quiet-utility/home/operator-scene.webp');
        $cta = self::assetUrl('images/quiet-utility/home/cta-still.webp');
        ob_start();
        ?>
        <div id="oddroom-main" class="oddroom-home">
            <section class="oddroom-hero" aria-labelledby="oddroom-hero-title">
                <div class="oddroom-hero-copy">
                    <p class="oddroom-kicker">QUIET UTILITY · ORDER OPERATIONS DEMO</p>
                    <h1 id="oddroom-hero-title"><?php echo wp_kses_post(self::text('조용한 화면, <span>끊기지 않는 주문 운영.</span>', 'A quieter surface for <span>resilient order operations.</span>')); ?></h1>
                    <p class="oddroom-lead"><?php echo esc_html(self::text('주문을 먼저 기록하고 CRM과 Slack 전달을 추적합니다. 실패해도 중복 처리 없이 이어갈 수 있는 WooCommerce 운영 흐름을 실제 상점과 관리자 화면에서 직접 확인하세요.', 'Record the order first, trace every CRM and Slack handoff, and continue safely after failure without duplicate work. Explore the real WooCommerce storefront and operator path in one package-owned demo.')); ?></p>
                    <div class="oddroom-hero-actions">
                        <a class="oddroom-button oddroom-button-primary" href="<?php echo esc_url($shop); ?>"><?php echo esc_html(self::text('상품과 주문 흐름 보기', 'Explore products and orders')); ?></a>
                        <a class="oddroom-button" href="<?php echo esc_url($account); ?>"><?php echo esc_html(self::text('운영 기록 확인', 'View order history')); ?></a>
                    </div>
                    <p class="oddroom-disclaimer"><?php echo esc_html(self::text('합성 구매 데이터만 사용 · 실제 결제·이메일·외부 전달 없음', 'Synthetic buyer data only · no real payment, email, or external delivery')); ?></p>
                </div>
                <figure class="oddroom-hero-visual">
                    <picture>
                        <source media="(max-width: 640px)" srcset="<?php echo esc_url($heroMobile); ?>">
                        <img src="<?php echo esc_url($heroDesktop); ?>" width="1920" height="1280" alt="<?php echo esc_attr(self::text('오프셋 독과 폴드라인 테크 케이스가 놓인 조용한 데스크 장면', 'A quiet desk with an Offset Dock and Foldline Tech Case')); ?>">
                    </picture>
                    <figcaption><strong>QUIET UTILITY / LIVE DEMO</strong><span><?php echo esc_html(self::text('상품, 주문, 복구가 하나의 흐름으로 연결됩니다.', 'Products, orders, and recovery share one continuous flow.')); ?></span></figcaption>
                </figure>
            </section>

            <section class="oddroom-proof-strip" aria-label="<?php echo esc_attr(self::text('구현 검증 항목', 'Implementation proof points')); ?>">
                <article><strong>4</strong><span><?php echo esc_html(self::text('주문 이벤트 유형', 'order event types')); ?></span></article>
                <article><strong>6</strong><span><?php echo esc_html(self::text('자동 전달 시도 상한', 'automatic delivery attempts')); ?></span></article>
                <article><strong>1</strong><span><?php echo esc_html(self::text('주문별 동시 실행', 'worker per order')); ?></span></article>
                <article><strong>HMAC</strong><span><?php echo esc_html(self::text('요청 원문 서명 검증', 'signed request bodies')); ?></span></article>
            </section>

            <section class="oddroom-section" aria-labelledby="oddroom-shop-title">
                <header><p class="oddroom-kicker">THE QUIET UTILITY EDIT</p><h2 id="oddroom-shop-title"><?php echo esc_html(self::text('필요한 것만 남긴 두 가지 상품.', 'Two useful objects, nothing extra.')); ?></h2><p><?php echo esc_html(self::text('Offset Dock 단순 상품과 Foldline Tech Case 가변 상품으로 결제 없는 주문·취소·환불 운영을 직접 실행합니다.', 'Use a simple Offset Dock and a variable Foldline Tech Case to run payment-free order, cancellation, and refund operations.')); ?></p></header>
                <?php echo wp_kses_post(self::productCards()); ?>
                <p><a class="oddroom-text-link" href="<?php echo esc_url($shop); ?>"><?php echo esc_html(self::text('전체 데모 상품 보기 →', 'View the complete demo shop →')); ?></a></p>
            </section>

            <section class="oddroom-story-grid" aria-label="<?php echo esc_attr(self::text('상품과 운영 장면', 'Product and operations scenes')); ?>">
                <article><img src="<?php echo esc_url($packing); ?>" width="1600" height="1200" alt="<?php echo esc_attr(self::text('합성 주문을 포장하는 Quiet Utility 장면', 'Packing a synthetic Quiet Utility order')); ?>"><div><p class="oddroom-kicker">ORDER MOMENT</p><h2><?php echo esc_html(self::text('구매 순간을 운영 기록으로.', 'Turn each purchase moment into an operating record.')); ?></h2></div></article>
                <article><img src="<?php echo esc_url($operator); ?>" width="1600" height="1200" alt="<?php echo esc_attr(self::text('주문 상태를 확인하는 운영자 작업 장면', 'An operator reviewing order state')); ?>"><div><p class="oddroom-kicker">OPERATOR VIEW</p><h2><?php echo esc_html(self::text('실패 뒤에도 판단할 수 있는 상태.', 'Keep enough state to decide what happens after failure.')); ?></h2></div></article>
            </section>

            <section class="oddroom-section oddroom-flow" aria-labelledby="oddroom-flow-title">
                <header><p class="oddroom-kicker">RECOVERY BY DESIGN</p><h2 id="oddroom-flow-title"><?php echo esc_html(self::text('성공보다 먼저, 이어갈 수 있는 상태를 남깁니다.', 'Before celebrating success, preserve a state you can continue.')); ?></h2></header>
                <ol>
                    <li><span>01</span><div><h3><?php echo esc_html(self::text('기록', 'Record')); ?></h3><p><?php echo esc_html(self::text('WooCommerce의 실제 발생 시각과 주문 내용을 정규화해 변경되지 않는 이벤트로 저장합니다.', 'Normalize the real WooCommerce occurrence time and order contents into an immutable event.')); ?></p></div></li>
                    <li><span>02</span><div><h3><?php echo esc_html(self::text('전달', 'Deliver')); ?></h3><p><?php echo esc_html(self::text('같은 주문의 외부 작업은 한 번에 하나만 실행하고, 정확한 작업 ID로 중복을 차단합니다.', 'Run one external task per order at a time and block duplicates with an exact action identity.')); ?></p></div></li>
                    <li><span>03</span><div><h3><?php echo esc_html(self::text('복구', 'Recover')); ?></h3><p><?php echo esc_html(self::text('재시도 가능한 실패와 결과가 불명확한 상태를 구분해, 잘못된 중복 알림 없이 이어갑니다.', 'Separate retryable failures from ambiguous outcomes, then continue without a duplicate notification.')); ?></p></div></li>
                </ol>
            </section>

            <section class="oddroom-cta" aria-labelledby="oddroom-cta-title">
                <div class="oddroom-cta-copy"><p class="oddroom-kicker"><?php echo esc_html(self::text('이 데모가 맞는 업무', 'WHERE THIS DEMO FITS')); ?></p>
                <h2 id="oddroom-cta-title"><?php echo esc_html(self::text('주문에서 CRM까지, 운영 복구가 필요한 상점.', 'A storefront that needs recovery from order to CRM.')); ?></h2>
                <p><?php echo esc_html(self::text('WooCommerce 주문을 CRM과 Slack으로 연결하고 실패를 추적·복구해야 하는 맞춤 업무에 적합합니다. 실제 결제, 모든 WooCommerce 예외, 대규모 트래픽, 형식적 exactly-once 전달을 증명하는 데모는 아닙니다.', 'Built for custom operations that connect WooCommerce orders to CRM and Slack with traceable recovery. It does not claim real payments, every WooCommerce edge case, high-scale traffic, or formal exactly-once delivery.')); ?></p>
                <a class="oddroom-button oddroom-button-primary" href="<?php echo esc_url($shop); ?>"><?php echo esc_html(self::text('합성 주문 시작하기', 'Start a synthetic order')); ?></a></div>
                <img src="<?php echo esc_url($cta); ?>" width="1600" height="1200" alt="<?php echo esc_attr(self::text('Quiet Utility 상품 정물', 'Quiet Utility product still life')); ?>">
            </section>
        </div>
        <?php
        return (string) ob_get_clean();
    }

    public static function commerceIntro(): void
    {
        if (!(is_shop() || is_product() || is_cart() || is_checkout() || is_account_page())) {
            return;
        }
        $title = is_shop() ? self::text('직접 실행하는 데모 상품', 'Demo products you can run')
            : (is_product() ? self::text('주문 흐름을 시작할 상품', 'Choose a product to start the flow')
                : (is_cart() ? self::text('합성 주문 장바구니', 'Synthetic order cart')
                    : (is_checkout() ? self::text('실제 결제 없는 주문서', 'Checkout with no real payment') : self::text('합성 주문 조회', 'Synthetic order history'))));
        echo '<section id="oddroom-main" class="oddroom-commerce-intro" aria-label="' . esc_attr(self::text('OddRoom 데모 화면 안내', 'OddRoom demo screen guidance')) . '">';
        echo '<p class="oddroom-kicker">ODDROOM ORDEROPS · ' . esc_html(self::text('실행형 데모', 'WORKING DEMO')) . '</p><p><strong>' . esc_html($title) . '</strong></p>';
        echo '<p>' . esc_html(self::text('합성 구매 데이터와 비금전 결제 수단만 사용하는 패키지 소유 데모 화면입니다.', 'This package-owned demo uses synthetic buyer data and a non-monetary checkout only.'));
        if (is_checkout()) {
            echo ' ' . esc_html(self::text('이름은 Synthetic / Buyer, 이메일은 소문자 @example.com 주소를 입력하세요.', 'Use Synthetic / Buyer and a lowercase @example.com email address.'));
        }
        echo '</p>';
        if (is_shop()) {
            echo '<aside class="oddroom-coupon-banner"><strong>ODDROOM10</strong><span>'
                . esc_html(self::text('합성 주문에 10% 데모 쿠폰을 적용하세요.', 'Apply a 10% demo coupon to a synthetic order.'))
                . '</span></aside>';
        }
        echo '</section>';
    }

    public static function emptyCartMessage(string $message): string
    {
        return self::text('아직 담은 상품이 없습니다. Quiet Utility 상품으로 합성 주문 흐름을 시작해 보세요.', 'Your cart is quiet for now. Choose a Quiet Utility product to start a synthetic order flow.');
    }

    public static function footer(): void
    {
        if (is_admin()) {
            return;
        }
        echo '<aside class="oddroom-demo-footer" aria-label="' . esc_attr(self::text('데모 이용 범위', 'Demo usage boundary')) . '"><strong>ODDROOM ORDEROPS</strong><span>' . esc_html(self::text('패키지 소유 데모 · 실제 결제 없음 · 합성 데이터 전용', 'Package-owned demo · no real payment · synthetic data only')) . '</span></aside>';
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
                self::text('이 데모에서는 이름 Synthetic / Buyer와 소문자 @example.com 이메일만 사용할 수 있습니다.', 'This demo accepts only Synthetic / Buyer with a lowercase @example.com email.')
            );
            return;
        }
        if ($errors->has_errors()) {
            return;
        }
        if (!self::consumeCheckoutAllowance()) {
            $errors->add('oddroom_checkout_rate_limited', self::text('합성 주문 허용 횟수에 도달했습니다. 잠시 후 다시 시도하세요.', 'The synthetic checkout limit was reached. Please try again later.'));
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
                self::text('이 데모에서는 이름 Synthetic / Buyer와 소문자 @example.com 이메일만 사용할 수 있습니다.', 'This demo accepts only Synthetic / Buyer with a lowercase @example.com email.'),
                ['status' => 422]
            );
        }
        if (self::consumeCheckoutAllowance()) {
            return $result;
        }
        return new WP_Error(
            'oddroom_checkout_rate_limited',
            self::text('합성 주문 허용 횟수에 도달했습니다. 잠시 후 다시 시도하세요.', 'The synthetic checkout limit was reached. Please try again later.'),
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
        self::localizeCommercePages();

        update_option('show_on_front', 'page');
        update_option('page_on_front', $homeId);
        update_option('blog_public', '0');
        update_option('blogname', self::text('OddRoom OrderOps 데모', 'OddRoom OrderOps Demo'));
        update_option('blogdescription', self::text('WooCommerce 주문 전달과 복구를 직접 실행하는 합성 데모', 'A synthetic demo for WooCommerce order delivery and recovery'));
        update_option('timezone_string', 'UTC');
        update_option('woocommerce_currency', 'KRW');
        update_option('woocommerce_price_num_decimals', '2');
        update_option('woocommerce_default_country', 'KR');
        update_option('woocommerce_enable_guest_checkout', 'yes');
        update_option('woocommerce_coming_soon', 'no');
        update_option('woocommerce_store_pages_only', 'no');
        update_option(
            'woocommerce_checkout_privacy_policy_text',
            self::text(
                '입력한 합성 구매 정보는 이 패키지 안에서 주문 흐름을 실행하는 데만 사용됩니다. 실제 결제·이메일·외부 전달은 발생하지 않습니다.',
                'Synthetic buyer information is used only to run the order flow inside this package. No real payment, email, or external delivery occurs.'
            )
        );
        update_option(
            'woocommerce_registration_privacy_policy_text',
            self::text(
                '이 데모는 합성 데이터만 사용하며 외부로 전송하지 않습니다.',
                'This demo uses synthetic data only and does not transmit it externally.'
            )
        );
        update_option('oddroom_orderops_checkout_control_mode', self::CHECKOUT_MODE, false);
        update_option('woocommerce_cod_settings', [
            'enabled' => 'yes',
            'title' => self::text('합성 주문 승인 — 실제 결제 없음', 'Approve synthetic order — no real payment'),
            'description' => self::text('테스트 전용 결제 수단입니다. 카드·계좌이체·현금 등 어떤 자금도 수집하지 않습니다.', 'A test-only payment method. It collects no card, bank, cash, or other funds.'),
            'instructions' => self::text('합성 데모 주문입니다. 결제할 금액은 없습니다.', 'This is a synthetic demo order. No funds are due.'),
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
        foreach (['ODDROOM-DROP-KIT', 'ODDROOM-CAMPAIGN-PACK'] as $sku) {
            $productId = wc_get_product_id_by_sku($sku);
            $product = $productId > 0 ? wc_get_product($productId) : null;
            if ($product instanceof WC_Product && $product->is_visible()) {
                $products[] = $product;
            }
        }
        if ($products === []) {
            return '<p>' . esc_html(self::text('데모 상품을 준비하고 있습니다.', 'Preparing demo products.')) . '</p>';
        }
        $html = '<div class="oddroom-product-grid">';
        foreach ($products as $product) {
            if (!$product instanceof WC_Product) {
                continue;
            }
            $isSimple = $product->get_sku() === 'ODDROOM-DROP-KIT';
            $image = '<img src="' . esc_url(self::assetUrl($isSimple
                    ? 'images/quiet-utility/simple/shop-card.webp'
                    : 'images/quiet-utility/variable/shop-card.webp'))
                . '" loading="lazy" width="1200" height="960" alt="'
                . esc_attr($isSimple
                    ? self::text('Offset Dock 상품 카드', 'Offset Dock product card')
                    : self::text('Graphite Foldline Tech Case 상품 카드', 'Graphite Foldline Tech Case product card')) . '">';
            $html .= '<article><a href="' . esc_url($product->get_permalink()) . '">'
                . $image
                . '<span class="oddroom-product-tag">' . esc_html(self::text('합성 데모 상품', 'SYNTHETIC DEMO PRODUCT')) . '</span><h3>' . esc_html($product->get_name()) . '</h3>'
                . '<p class="price">' . wp_kses_post($product->get_price_html()) . '</p><span class="oddroom-card-link">' . esc_html(self::text('상품 상세 보기 →', 'View product details →')) . '</span></a></article>';
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
            'post_title' => self::text('OddRoom OrderOps 데모', 'OddRoom OrderOps Demo'),
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
        $id = wc_get_product_id_by_sku('ODDROOM-DROP-KIT');
        $product = $id > 0 ? wc_get_product($id) : new WC_Product_Simple();
        if (!$product instanceof WC_Product_Simple) {
            throw new RuntimeException('Simple product SKU conflicts with another product type.');
        }
        $product->set_name(self::text('Offset Dock · 오프셋 데스크 독', 'Offset Dock'));
        $product->set_slug('oddroom-drop-kit');
        $product->set_sku('ODDROOM-DROP-KIT');
        $product->set_regular_price('39000');
        $product->set_virtual(true);
        $product->set_status('publish');
        $product->set_catalog_visibility('visible');
        $product->set_image_id($images['simple_main']);
        $product->set_gallery_image_ids([
            $images['simple_flatlay'],
            $images['simple_material'],
            $images['simple_in_use'],
            $images['simple_packaging'],
        ]);
        $product->set_category_ids([$categoryId]);
        $product->set_short_description(self::text('선을 조용히 정리하는 오프셋 데스크 독. 이 단순 상품으로 주문 기록부터 CRM 전달과 복구까지 확인합니다.', 'An offset desktop dock that quietly organizes cables. Use this simple product to follow the record, CRM delivery, and recovery path.'));
        $product->set_description(self::text('Quiet Utility 콜렉션의 Offset Dock입니다. 실제 결제 없이 WooCommerce 주문 이벤트를 만들고 OddRoom OrderOps의 기록·전달·복구 흐름을 실행합니다.', 'The Offset Dock from the Quiet Utility collection. Create a WooCommerce order event without real payment and run the OddRoom OrderOps record, delivery, and recovery flow.'));
        return (int) $product->save();
    }

    private static function ensureVariableProduct(array $images, int $categoryId): array
    {
        $id = wc_get_product_id_by_sku('ODDROOM-CAMPAIGN-PACK');
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
        $product->set_slug('oddroom-campaign-pack');
        $product->set_sku('ODDROOM-CAMPAIGN-PACK');
        $product->set_status('publish');
        $product->set_catalog_visibility('visible');
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
        $product->set_short_description(self::text('Graphite 또는 Sandstone 마감을 선택하고 variation ID와 옵션 이미지가 복구 가능한 주문 경로로 이어지는지 확인합니다.', 'Choose Graphite or Sandstone and verify that the variation identity and image continue through the recoverable order path.'));
        $product->set_description(self::text('Quiet Utility 콜렉션의 Foldline Tech Case입니다. 두 가지 마감을 가진 테스트 전용 가변 상품으로, 모든 주문은 실제 자금을 수집하지 않습니다.', 'The Foldline Tech Case from the Quiet Utility collection. This test-only variable product has two distinct finishes and never collects real funds.'));
        $productId = (int) $product->save();
        $variationIds = [];
        foreach ([
            'Graphite' => ['79000', 'ODDROOM-CAMPAIGN-CORE', $images['variable_graphite']],
            'Sandstone' => ['129000', 'ODDROOM-CAMPAIGN-PLUS', $images['variable_sandstone']],
        ] as $finish => [$price, $sku, $variationImage]) {
            $variationId = wc_get_product_id_by_sku($sku);
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
        $couponId = wc_get_coupon_id_by_code('ODDROOM10');
        $coupon = $couponId > 0 ? new WC_Coupon($couponId) : new WC_Coupon();
        $coupon->set_code('ODDROOM10');
        $coupon->set_discount_type('percent');
        $coupon->set_amount('10');
        $coupon->set_individual_use(true);
        $coupon->set_description(self::text('OddRoom OrderOps 합성 주문 검증용 10% 할인 쿠폰입니다.', 'A 10% coupon for synthetic OddRoom OrderOps validation.'));
        return (int) $coupon->save();
    }

    private static function ensureProductCategory(): int
    {
        $existing = term_exists('demo-products', 'product_cat');
        if (is_array($existing)) {
            wp_update_term((int) $existing['term_id'], 'product_cat', ['name' => self::text('데모 상품', 'Demo products')]);
            return (int) $existing['term_id'];
        }
        if (is_int($existing) && $existing > 0) {
            wp_update_term($existing, 'product_cat', ['name' => self::text('데모 상품', 'Demo products')]);
            return $existing;
        }
        $created = wp_insert_term(self::text('데모 상품', 'Demo products'), 'product_cat', ['slug' => 'demo-products']);
        if (is_wp_error($created) || !is_array($created) || (int) ($created['term_id'] ?? 0) < 1) {
            throw new RuntimeException('Product category setup failed.');
        }
        return (int) $created['term_id'];
    }

    private static function localizeCommercePages(): void
    {
        foreach (self::isEnglish() ? [
            'woocommerce_shop_page_id' => ['Demo shop', ''],
            'woocommerce_cart_page_id' => ['Cart', '[woocommerce_cart]'],
            'woocommerce_checkout_page_id' => ['Synthetic checkout', '[woocommerce_checkout]'],
            'woocommerce_myaccount_page_id' => ['Orders', '[woocommerce_my_account]'],
        ] : [
            'woocommerce_shop_page_id' => ['데모 상품', ''],
            'woocommerce_cart_page_id' => ['장바구니', '[woocommerce_cart]'],
            'woocommerce_checkout_page_id' => ['합성 주문', '[woocommerce_checkout]'],
            'woocommerce_myaccount_page_id' => ['주문 조회', '[woocommerce_my_account]'],
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
