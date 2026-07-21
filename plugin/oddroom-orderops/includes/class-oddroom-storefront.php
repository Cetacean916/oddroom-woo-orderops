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
        add_filter('woocommerce_price_trim_zeros', '__return_true');
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
            '0.6.0'
        );
        wp_enqueue_script(
            'oddroom-orderops-storefront',
            self::assetUrl('js/storefront.js'),
            [],
            '0.6.0',
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
                'Shop' => wc_get_page_permalink('shop'),
                'Objects' => home_url('/#offset-objects'),
                'Order system' => home_url('/#offset-system'),
            ]
            : [
                '스토어' => wc_get_page_permalink('shop'),
                '오브젝트' => home_url('/#offset-objects'),
                '주문 시스템' => home_url('/#offset-system'),
            ];
        echo '<a class="oddroom-skip" href="#oddroom-main">' . esc_html(self::text('본문으로 건너뛰기', 'Skip to content')) . '</a>';
        echo '<aside class="oddroom-announcement"><span>OFFSET / ORDEROPS</span><p>'
            . esc_html(self::text('실제 결제 없이 전체 주문 흐름을 실행하는 포트폴리오 데모', 'A complete order-flow portfolio demo with no real payment'))
            . '</p><span>DEMO · 0 KRW</span></aside>';
        echo '<header class="oddroom-frontbar"><nav class="oddroom-nav-primary" aria-label="' . esc_attr(self::text('주요 탐색', 'Primary navigation')) . '"><ul>';
        foreach ($primary as $label => $url) {
            echo '<li><a href="' . esc_url($url) . '">' . esc_html($label) . '</a></li>';
        }
        echo '</ul></nav>';
        echo '<a class="oddroom-wordmark" href="' . esc_url(home_url('/')) . '" aria-label="OFFSET ' . esc_attr(self::text('홈', 'home')) . '"><strong>OFFSET</strong><span>OBJECTS / ORDER SYSTEM</span></a>';
        echo '<nav class="oddroom-nav-utility" aria-label="' . esc_attr(self::text('계정과 장바구니', 'Account and cart')) . '"><ul>';
        echo '<li><a href="' . esc_url(wc_get_page_permalink('myaccount')) . '">' . esc_html(self::text('주문 조회', 'Account')) . '</a></li>';
        echo '<li><a href="' . esc_url(wc_get_cart_url()) . '">' . esc_html(self::text('장바구니', 'Cart')) . '</a></li>';
        echo '</ul></nav></header>';
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
                <figure class="oddroom-hero-visual">
                    <picture>
                        <source media="(max-width: 640px)" srcset="<?php echo esc_url($heroMobile); ?>">
                        <img src="<?php echo esc_url($heroDesktop); ?>" width="1920" height="1280" alt="<?php echo esc_attr(self::text('오프셋 독과 폴드라인 테크 케이스가 놓인 데스크 장면', 'A desk with an Offset Dock and Foldline Tech Case')); ?>">
                    </picture>
                    <div class="oddroom-hero-copy">
                        <p class="oddroom-kicker">OFFSET OBJECTS · ORDEROPS EDITION</p>
                        <h1 id="oddroom-hero-title"><?php echo wp_kses_post(self::text('일의 흐름을<br><span>정돈하는 물건.</span>', 'Objects that bring<br><span>work into order.</span>')); ?></h1>
                        <p class="oddroom-lead"><?php echo esc_html(self::text('책상 위의 두 오브젝트에서 시작해 주문 기록과 복구까지 이어지는 실제 커머스 데모.', 'A working commerce demo that begins with two desk objects and continues through order records and recovery.')); ?></p>
                        <div class="oddroom-hero-actions">
                            <a class="oddroom-button oddroom-button-primary" href="<?php echo esc_url($shop); ?>"><?php echo esc_html(self::text('컬렉션 보기', 'Shop the collection')); ?></a>
                            <a class="oddroom-button oddroom-button-ghost" href="#offset-system"><?php echo esc_html(self::text('시스템 살펴보기', 'Explore the system')); ?></a>
                        </div>
                    </div>
                    <figcaption><span>01 / 02</span><strong>OFFSET DOCK + FOLDLINE CASE</strong><span><?php echo esc_html(self::text('합성 주문 전용', 'SYNTHETIC ORDERS ONLY')); ?></span></figcaption>
                </figure>
            </section>

            <section class="oddroom-manifesto" aria-labelledby="offset-manifesto-title">
                <p class="oddroom-kicker">DESIGNED FOR ORDER</p>
                <h2 id="offset-manifesto-title"><?php echo wp_kses_post(self::text('좋은 물건은 공간을 정돈하고,<br>좋은 시스템은 <span>실패 뒤의 일을 정돈합니다.</span>', 'Good objects organize a space.<br>Good systems organize <span>what happens after failure.</span>')); ?></h2>
                <p><?php echo esc_html(self::text('OFFSET은 제품을 고르고 주문하는 고객 화면과, 주문을 기록하고 전달하고 복구하는 운영 화면을 하나의 작동하는 경험으로 연결합니다.', 'OFFSET connects the customer experience of choosing and ordering a product with the operator experience of recording, delivering, and recovering that order.')); ?></p>
            </section>

            <section id="offset-objects" class="oddroom-section oddroom-collection" aria-labelledby="oddroom-shop-title">
                <header><p class="oddroom-kicker">THE OFFSET COLLECTION · 01—02</p><h2 id="oddroom-shop-title"><?php echo esc_html(self::text('매일 쓰는 두 가지 오브젝트.', 'Two objects for everyday work.')); ?></h2><p><?php echo esc_html(self::text('정리와 이동을 위한 제품을 고른 뒤, 실제 결제 없이 주문·취소·환불 흐름까지 직접 실행할 수 있습니다.', 'Choose an object for order or mobility, then run the order, cancellation, and refund paths without a real payment.')); ?></p></header>
                <?php echo wp_kses_post(self::productCards()); ?>
                <p class="oddroom-collection-link"><a class="oddroom-text-link" href="<?php echo esc_url($shop); ?>"><?php echo esc_html(self::text('전체 컬렉션 보기', 'View the full collection')); ?><span aria-hidden="true">↗</span></a></p>
            </section>

            <section class="oddroom-story-grid" aria-label="<?php echo esc_attr(self::text('상품에서 운영까지 이어지는 장면', 'Scenes from product to operations')); ?>">
                <article class="oddroom-story-order"><img src="<?php echo esc_url($packing); ?>" width="1600" height="1200" alt="<?php echo esc_attr(self::text('합성 주문 상품을 포장하는 장면', 'Packing a synthetic order')); ?>"><div><p class="oddroom-kicker">FROM OBJECT TO ORDER · 01</p><h2><?php echo esc_html(self::text('구매의 순간을 잃지 않는 기록으로.', 'Keep the purchase moment as a durable record.')); ?></h2><p><?php echo esc_html(self::text('고객이 주문을 마치면 원본 주문 정보와 발생 시각을 먼저 보존합니다.', 'When a customer completes an order, the original order data and occurrence time are preserved first.')); ?></p></div></article>
                <article class="oddroom-story-operator"><img src="<?php echo esc_url($operator); ?>" width="1600" height="1200" alt="<?php echo esc_attr(self::text('주문 상태를 확인하는 운영자 장면', 'An operator reviewing order state')); ?>"><div><p class="oddroom-kicker">FROM ORDER TO RECOVERY · 02</p><h2><?php echo esc_html(self::text('운영자가 다음 행동을 결정할 수 있는 상태.', 'A state that lets the operator decide what comes next.')); ?></h2><p><?php echo esc_html(self::text('성공, 재시도, 확인 필요를 구분해 중복 처리 없이 운영을 이어갑니다.', 'Separate success, retry, and review-required states so work can continue without duplication.')); ?></p></div></article>
            </section>

            <section id="offset-system" class="oddroom-section oddroom-flow" aria-labelledby="oddroom-flow-title">
                <header><p class="oddroom-kicker">THE ORDER SYSTEM</p><h2 id="oddroom-flow-title"><?php echo esc_html(self::text('기록. 전달. 복구.', 'Record. Deliver. Recover.')); ?></h2><p><?php echo esc_html(self::text('정상 흐름만 보여주는 모형이 아니라, 실패 뒤에도 실제로 이어지는 운영 데모입니다.', 'This is not a happy-path mockup. It is a working operations demo that continues after failure.')); ?></p></header>
                <ol>
                    <li><span>01</span><div><p class="oddroom-flow-label">CAPTURE</p><h3><?php echo esc_html(self::text('기록', 'Record')); ?></h3><p><?php echo esc_html(self::text('WooCommerce 주문을 변경되지 않는 이벤트로 먼저 저장합니다.', 'Store the WooCommerce order as an immutable event first.')); ?></p></div></li>
                    <li><span>02</span><div><p class="oddroom-flow-label">HANDOFF</p><h3><?php echo esc_html(self::text('전달', 'Deliver')); ?></h3><p><?php echo esc_html(self::text('주문별 작업 ID로 CRM과 Slack 전달의 중복을 차단합니다.', 'Use an order-specific action identity to prevent duplicate CRM and Slack handoffs.')); ?></p></div></li>
                    <li><span>03</span><div><p class="oddroom-flow-label">CONTINUE</p><h3><?php echo esc_html(self::text('복구', 'Recover')); ?></h3><p><?php echo esc_html(self::text('실패 유형을 나누고 필요한 지점에서 안전하게 다시 시작합니다.', 'Classify the failure and resume safely from the required point.')); ?></p></div></li>
                </ol>
            </section>

            <section class="oddroom-cta" aria-labelledby="oddroom-cta-title">
                <img src="<?php echo esc_url($cta); ?>" width="1600" height="1200" alt="<?php echo esc_attr(self::text('OFFSET 컬렉션 상품 정물', 'OFFSET collection product still life')); ?>">
                <div class="oddroom-cta-copy"><p class="oddroom-kicker">START WITH AN OBJECT</p>
                <h2 id="oddroom-cta-title"><?php echo esc_html(self::text('직접 고르고, 주문하고, 운영을 확인하세요.', 'Choose it. Order it. Follow the operation.')); ?></h2>
                <p><?php echo esc_html(self::text('합성 구매자 정보와 비금전 결제 수단만 사용합니다. 실제 결제·이메일·외부 전송은 발생하지 않습니다.', 'The demo uses synthetic buyer information and a non-monetary payment method. No real payment, email, or external delivery occurs.')); ?></p>
                <div class="oddroom-hero-actions"><a class="oddroom-button oddroom-button-primary" href="<?php echo esc_url($shop); ?>"><?php echo esc_html(self::text('컬렉션에서 시작', 'Start with the collection')); ?></a><a class="oddroom-button oddroom-button-ghost" href="<?php echo esc_url($account); ?>"><?php echo esc_html(self::text('주문 기록 보기', 'View order records')); ?></a></div></div>
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
        $product = is_product() ? wc_get_product(get_queried_object_id()) : null;
        $title = is_shop() ? self::text('직접 실행하는 데모 상품', 'Demo products you can run')
            : (is_product() && $product instanceof WC_Product ? $product->get_name()
                : (is_cart() ? self::text('합성 주문 장바구니', 'Synthetic order cart')
                    : (is_checkout() ? self::text('실제 결제 없는 주문서', 'Checkout with no real payment') : self::text('합성 주문 조회', 'Synthetic order history'))));
        $classes = 'oddroom-commerce-intro';
        if (!is_shop()) {
            $classes .= ' oddroom-commerce-intro--compact';
        }
        if (is_product()) {
            $classes .= ' oddroom-commerce-intro--product';
        }
        $marker = is_product() && $product instanceof WC_Product
            ? ($product->get_sku() === 'OFFSET-DOCK' ? 'OBJECT 01' : 'OBJECT 02')
            : '01—02';
        echo '<section id="oddroom-main" class="' . esc_attr($classes) . '" aria-label="' . esc_attr(self::text('OFFSET 데모 화면 안내', 'OFFSET demo screen guidance')) . '">';
        echo '<p class="oddroom-kicker">OFFSET / WORKING COMMERCE DEMO</p><p class="oddroom-commerce-title"><strong>' . esc_html($title) . '</strong><span>01—02</span></p>';
        echo '<p class="oddroom-commerce-marker">' . esc_html($marker) . '</p>';
        echo '<p class="oddroom-commerce-copy">' . esc_html(self::text('제품 선택부터 주문 기록과 복구까지 실제로 이어지는 비금전 커머스 화면입니다.', 'A non-monetary commerce surface that runs from product selection through order records and recovery.'));
        if (is_checkout()) {
            echo ' ' . esc_html(self::text('이름은 Synthetic / Buyer, 이메일은 소문자 @example.com 주소를 입력하세요.', 'Use Synthetic / Buyer and a lowercase @example.com email address.'));
        }
        echo '</p>';
        if (is_shop()) {
            echo '<aside class="oddroom-coupon-banner"><span>' . esc_html(self::text('데모 주문 혜택', 'Demo order benefit')) . '</span><strong>OFFSET10</strong><span>'
                . esc_html(self::text('결제 단계에서 10% 쿠폰 적용', 'Apply 10% at checkout'))
                . '</span></aside>';
        }
        echo '</section>';
    }

    public static function emptyCartMessage(string $message): string
    {
        return self::text('아직 담은 상품이 없습니다. OFFSET 컬렉션 제품으로 합성 주문 흐름을 시작해 보세요.', 'Your cart is empty for now. Choose an OFFSET collection product to start a synthetic order flow.');
    }

    public static function footer(): void
    {
        if (is_admin()) {
            return;
        }
        echo '<footer class="oddroom-demo-footer" aria-label="' . esc_attr(self::text('데모 이용 범위', 'Demo usage boundary')) . '"><div class="oddroom-footer-brand"><strong>OFFSET</strong><span>OBJECTS / ORDER SYSTEM</span></div><div><strong>' . esc_html(self::text('스토어', 'Store')) . '</strong><a href="' . esc_url(wc_get_page_permalink('shop')) . '">' . esc_html(self::text('전체 컬렉션', 'Full collection')) . '</a><a href="' . esc_url(wc_get_cart_url()) . '">' . esc_html(self::text('장바구니', 'Cart')) . '</a></div><div><strong>' . esc_html(self::text('운영', 'Operations')) . '</strong><a href="' . esc_url(wc_get_page_permalink('myaccount')) . '">' . esc_html(self::text('주문 기록', 'Order records')) . '</a><a href="' . esc_url(home_url('/#offset-system')) . '">' . esc_html(self::text('시스템 구조', 'System flow')) . '</a></div><div class="oddroom-footer-boundary"><strong>DEMO BOUNDARY</strong><span>' . esc_html(self::text('실제 결제 없음', 'No real payment')) . '</span><span>' . esc_html(self::text('합성 데이터 전용', 'Synthetic data only')) . '</span><span>0 KRW</span></div><p>© OFFSET / ORDEROPS PORTFOLIO DEMO</p></footer>';
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
        update_option('blogname', self::text('OFFSET 주문 시스템', 'OFFSET Order System'));
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
        foreach (['OFFSET-DOCK', 'OFFSET-FOLDLINE'] as $sku) {
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
        foreach ($products as $index => $product) {
            if (!$product instanceof WC_Product) {
                continue;
            }
            $isSimple = $product->get_sku() === 'OFFSET-DOCK';
            $image = '<img src="' . esc_url(self::assetUrl($isSimple
                    ? 'images/quiet-utility/simple/shop-card.webp'
                    : 'images/quiet-utility/variable/shop-card.webp'))
                . '" loading="lazy" width="1200" height="960" alt="'
                . esc_attr($isSimple
                    ? self::text('Offset Dock 상품 카드', 'Offset Dock product card')
                    : self::text('Graphite Foldline Tech Case 상품 카드', 'Graphite Foldline Tech Case product card')) . '">';
            $objectLabel = $isSimple ? self::text('데스크 오브젝트', 'DESK OBJECT') : self::text('캐리 오브젝트', 'CARRY OBJECT');
            $html .= '<article><a href="' . esc_url($product->get_permalink()) . '">'
                . $image
                . '<div class="oddroom-product-info"><span class="oddroom-product-index">0' . esc_html((string) ($index + 1)) . '</span><span class="oddroom-product-tag">' . esc_html($objectLabel) . '</span><h3>' . esc_html($product->get_name()) . '</h3>'
                . '<p class="price">' . wp_kses_post($product->get_price_html()) . '</p><span class="oddroom-card-link">' . esc_html(self::text('제품 살펴보기', 'Explore object')) . '<span aria-hidden="true">↗</span></span></div></a></article>';
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
            'post_title' => self::text('OFFSET 주문 시스템', 'OFFSET Order System'),
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
        $product->set_image_id($images['simple_main']);
        $product->set_gallery_image_ids([
            $images['simple_flatlay'],
            $images['simple_material'],
            $images['simple_in_use'],
            $images['simple_packaging'],
        ]);
        $product->set_category_ids([$categoryId]);
        $product->set_short_description(self::text('선을 조용히 정리하는 오프셋 데스크 독. 이 단순 상품으로 주문 기록부터 CRM 전달과 복구까지 확인합니다.', 'An offset desktop dock that quietly organizes cables. Use this simple product to follow the record, CRM delivery, and recovery path.'));
        $product->set_description(self::text('OFFSET 컬렉션의 Offset Dock입니다. 실제 결제 없이 WooCommerce 주문 이벤트를 만들고 OFFSET의 기록·전달·복구 흐름을 실행합니다.', 'The Offset Dock from the OFFSET collection. Create a WooCommerce order event without real payment and run the OFFSET record, delivery, and recovery flow.'));
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
        $product->set_description(self::text('OFFSET 컬렉션의 Foldline Tech Case입니다. 두 가지 마감을 가진 테스트 전용 가변 상품으로, 모든 주문은 실제 자금을 수집하지 않습니다.', 'The Foldline Tech Case from the OFFSET collection. This test-only variable product has two distinct finishes and never collects real funds.'));
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
        $coupon->set_description(self::text('OFFSET 합성 주문 검증용 10% 할인 쿠폰입니다.', 'A 10% coupon for synthetic OFFSET order validation.'));
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
