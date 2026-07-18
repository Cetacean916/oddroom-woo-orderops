<?php

defined('ABSPATH') || exit;

final class OddRoom_Storefront
{
    private const HOME_SHORTCODE = 'oddroom_orderops_home';
    private const CHECKOUT_MODE = 'ON_DEMAND_ONLY';

    public static function boot(): void
    {
        add_shortcode(self::HOME_SHORTCODE, [self::class, 'home']);
        add_action('wp_enqueue_scripts', [self::class, 'assets']);
        add_action('wp_body_open', [self::class, 'navigation']);
        add_action('wp_footer', [self::class, 'footer']);
        add_action('woocommerce_before_main_content', [self::class, 'commerceIntro'], 5);
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
            '0.2.0'
        );
        wp_enqueue_script(
            'oddroom-orderops-storefront',
            self::assetUrl('js/storefront.js'),
            [],
            '0.2.0',
            ['in_footer' => true, 'strategy' => 'defer']
        );
    }

    public static function navigation(): void
    {
        if (is_admin()) {
            return;
        }
        $links = [
            'Home' => home_url('/'),
            'Shop' => wc_get_page_permalink('shop'),
            'Cart' => wc_get_cart_url(),
            'Checkout' => wc_get_checkout_url(),
            'Account' => wc_get_page_permalink('myaccount'),
        ];
        echo '<a class="oddroom-skip" href="#oddroom-main">Skip to content</a>';
        echo '<div class="oddroom-frontbar"><a class="oddroom-wordmark" href="' . esc_url(home_url('/')) . '" aria-label="OddRoom OrderOps home">ODDROOM<span>!</span></a>';
        echo '<nav aria-label="Store navigation"><ul>';
        foreach ($links as $label => $url) {
            echo '<li><a href="' . esc_url($url) . '">' . esc_html($label) . '</a></li>';
        }
        echo '</ul></nav><p>ON-DEMAND SYNTHETIC LAB</p></div>';
    }

    public static function home(): string
    {
        $shop = wc_get_page_permalink('shop');
        $account = wc_get_page_permalink('myaccount');
        $image = self::assetUrl('images/shopping-bags-commons.jpg');
        ob_start();
        ?>
        <div id="oddroom-main" class="oddroom-home">
            <section class="oddroom-hero" aria-labelledby="oddroom-hero-title">
                <div class="oddroom-hero-copy">
                    <p class="oddroom-kicker">WooCommerce → HubSpot → Slack</p>
                    <h1 id="oddroom-hero-title">주문은 들어오고,<br><span>복구 경로</span>는 남는다.</h1>
                    <p class="oddroom-lead">OddRoom OrderOps는 합성 주문 이벤트를 불변 outbox에 기록하고, 주문별 직렬화·제한 재시도·운영자 확인 경로로 CRM과 알림 전달을 설명하는 온디맨드 스테이징 데모입니다.</p>
                    <div class="oddroom-hero-actions">
                        <a class="oddroom-button oddroom-button-primary" href="<?php echo esc_url($shop); ?>">데모 상품 보기</a>
                        <a class="oddroom-button" href="<?php echo esc_url($account); ?>">주문 계정 열기</a>
                    </div>
                    <p class="oddroom-disclaimer">합성 데이터 전용 · 실제 결제 없음 · 프로덕션 규모 주장 아님</p>
                </div>
                <figure class="oddroom-hero-visual">
                    <img src="<?php echo esc_url($image); ?>" width="1920" height="1280" alt="색색의 쇼핑백을 든 합성 상거래 캠페인 장면">
                    <figcaption><strong>01 / CAPTURE</strong><span>구매 순간을 재현 가능한 운영 사실로</span></figcaption>
                </figure>
            </section>

            <section class="oddroom-proof-strip" aria-label="Implementation facts">
                <article><strong>4</strong><span>정의된 주문 이벤트</span></article>
                <article><strong>6</strong><span>자동 시도 상한</span></article>
                <article><strong>1</strong><span>주문별 실행 lease</span></article>
                <article><strong>HMAC</strong><span>원문 바이트 서명</span></article>
            </section>

            <section class="oddroom-section" aria-labelledby="oddroom-shop-title">
                <header><p class="oddroom-kicker">SYNTHETIC CATALOG</p><h2 id="oddroom-shop-title">실제 WooCommerce 표면에서 확인하세요.</h2><p>단순 상품, 두 가지 옵션의 가변 상품, 쿠폰 경로가 같은 설치형 데모 안에서 동작합니다.</p></header>
                <?php echo wp_kses_post(self::productCards()); ?>
                <p><a class="oddroom-text-link" href="<?php echo esc_url($shop); ?>">전체 Shop으로 이동 →</a></p>
            </section>

            <section class="oddroom-section oddroom-flow" aria-labelledby="oddroom-flow-title">
                <header><p class="oddroom-kicker">RECOVERY BY DESIGN</p><h2 id="oddroom-flow-title">성공처럼 보이는 대신, 상태를 증명합니다.</h2></header>
                <ol>
                    <li><span>01</span><div><h3>Capture</h3><p>WooCommerce 사실 시각에서 정규화한 payload와 hash를 한 번만 저장합니다.</p></div></li>
                    <li><span>02</span><div><h3>Deliver</h3><p>주문 단위 lease와 정확한 Action Scheduler ID로 외부 효과를 직렬화합니다.</p></div></li>
                    <li><span>03</span><div><h3>Recover</h3><p>재시도 가능한 실패와 결과 불명 상태를 나누고, 후자는 보호된 운영자 결정으로만 해소합니다.</p></div></li>
                </ol>
            </section>

            <section class="oddroom-cta" aria-labelledby="oddroom-cta-title">
                <p class="oddroom-kicker">BUYER FIT</p>
                <h2 id="oddroom-cta-title">맞는 일과, 증명하지 않는 일을 함께 보여줍니다.</h2>
                <p>맞는 범위: 맞춤 WooCommerce 주문→CRM 운영 및 복구. 비적합/비주장: 실제 결제, 모든 WooCommerce 엣지 케이스, 프로덕션 규모, 형식적 exactly-once 전달.</p>
                <a class="oddroom-button oddroom-button-primary" href="<?php echo esc_url($shop); ?>">합성 checkout 시작</a>
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
        $title = is_shop() ? 'Synthetic catalog'
            : (is_product() ? 'Product proof surface'
                : (is_cart() ? 'Cart rehearsal'
                    : (is_checkout() ? 'No-funds checkout' : 'Synthetic order account')));
        echo '<section id="oddroom-main" class="oddroom-commerce-intro" aria-label="OddRoom page context">';
        echo '<p class="oddroom-kicker">ODDROOM ORDEROPS</p><p><strong>' . esc_html($title) . '</strong></p>';
        echo '<p>합성 데이터와 비금전 결제 경로만 허용되는 온디맨드 스테이징 화면입니다.</p></section>';
    }

    public static function footer(): void
    {
        if (is_admin()) {
            return;
        }
        echo '<aside class="oddroom-demo-footer" aria-label="Demonstration boundary"><strong>ODDROOM ORDEROPS</strong><span>ON_DEMAND_ONLY · NO REAL PAYMENT · SYNTHETIC DATA</span></aside>';
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
        if (!self::consumeCheckoutAllowance()) {
            $errors->add('oddroom_checkout_rate_limited', 'Synthetic checkout limit reached. Try again later.');
        }
    }

    public static function rateLimitStoreApiCheckout(mixed $result, WP_REST_Server $server, WP_REST_Request $request): mixed
    {
        if ($result !== null
            || strtoupper($request->get_method()) !== 'POST'
            || !preg_match('#^/wc/store(?:/v\d+)?/checkout$#', $request->get_route())) {
            return $result;
        }
        if (self::consumeCheckoutAllowance()) {
            return $result;
        }
        return new WP_Error(
            'oddroom_checkout_rate_limited',
            'Synthetic checkout limit reached. Try again later.',
            ['status' => 429]
        );
    }

    public static function installDemoStore(): array
    {
        if (!class_exists('WooCommerce')) {
            throw new RuntimeException('WooCommerce is unavailable.');
        }
        $attachmentId = self::ensureStoreImage();
        $simpleId = self::ensureSimpleProduct($attachmentId);
        $variable = self::ensureVariableProduct($attachmentId);
        $couponId = self::ensureCoupon();
        $homeId = self::ensureHomePage();

        update_option('show_on_front', 'page');
        update_option('page_on_front', $homeId);
        update_option('blog_public', '0');
        update_option('blogname', 'OddRoom OrderOps Lab');
        update_option('blogdescription', 'Synthetic WooCommerce recovery demonstration');
        update_option('timezone_string', 'UTC');
        update_option('woocommerce_currency', 'KRW');
        update_option('woocommerce_enable_guest_checkout', 'yes');
        update_option('woocommerce_coming_soon', 'no');
        update_option('woocommerce_store_pages_only', 'no');
        update_option('oddroom_orderops_checkout_control_mode', self::CHECKOUT_MODE, false);
        update_option('woocommerce_cod_settings', [
            'enabled' => 'yes',
            'title' => 'Synthetic acceptance — no funds',
            'description' => 'Test-only acceptance. No card, bank transfer, cash, or other funds are collected.',
            'instructions' => 'Synthetic staging order only. No payment is due.',
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
            'image_attachment_id' => $attachmentId,
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
            return '<p>Store fixtures are being prepared.</p>';
        }
        $html = '<div class="oddroom-product-grid">';
        foreach ($products as $product) {
            if (!$product instanceof WC_Product) {
                continue;
            }
            $image = $product->get_image('woocommerce_thumbnail', ['loading' => 'lazy']);
            $html .= '<article><a href="' . esc_url($product->get_permalink()) . '">'
                . wp_kses_post($image)
                . '<span class="oddroom-product-tag">SYNTHETIC PRODUCT</span><h3>' . esc_html($product->get_name()) . '</h3>'
                . '<p class="price">' . wp_kses_post($product->get_price_html()) . '</p><span class="oddroom-card-link">상품 표면 열기 →</span></a></article>';
        }
        return $html . '</div>';
    }

    private static function consumeCheckoutAllowance(): bool
    {
        if (!OddRoom_Repository::testMode()) {
            return false;
        }
        $address = isset($_SERVER['REMOTE_ADDR']) ? (string) $_SERVER['REMOTE_ADDR'] : 'unknown';
        $key = 'oddroom_checkout_' . hash_hmac('sha256', $address, wp_salt('nonce'));
        $count = (int) get_transient($key);
        if ($count >= 10) {
            return false;
        }
        set_transient($key, $count + 1, 15 * MINUTE_IN_SECONDS);
        return true;
    }

    private static function assetUrl(string $path): string
    {
        return plugins_url('assets/' . ltrim($path, '/'), dirname(__DIR__) . '/oddroom-orderops.php');
    }

    private static function ensureHomePage(): int
    {
        $existing = get_page_by_path('oddroom-home', OBJECT, 'page');
        $post = [
            'post_title' => 'OddRoom OrderOps',
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

    private static function ensureStoreImage(): int
    {
        $existing = (int) get_option('oddroom_orderops_store_image_id', 0);
        if ($existing > 0 && get_post($existing) instanceof WP_Post) {
            return $existing;
        }
        $bytes = file_get_contents(dirname(__DIR__) . '/assets/images/shopping-bags-commons.jpg');
        if (!is_string($bytes) || hash('sha256', $bytes) !== '23e9e11f5ad747c6885c731d5fca553c5acdc6a9697449979297c61ce71344cd') {
            throw new RuntimeException('Store image integrity check failed.');
        }
        $upload = wp_upload_bits('oddroom-shopping-bags-commons.jpg', null, $bytes);
        if (!empty($upload['error'])) {
            throw new RuntimeException('Store image upload failed.');
        }
        $attachmentId = wp_insert_attachment([
            'post_mime_type' => 'image/jpeg',
            'post_title' => 'OddRoom synthetic shopping scene',
            'post_content' => '',
            'post_status' => 'inherit',
        ], $upload['file']);
        if (!is_int($attachmentId) || $attachmentId < 1) {
            throw new RuntimeException('Store image attachment failed.');
        }
        require_once ABSPATH . 'wp-admin/includes/image.php';
        wp_update_attachment_metadata($attachmentId, wp_generate_attachment_metadata($attachmentId, $upload['file']));
        update_post_meta($attachmentId, '_wp_attachment_image_alt', 'Colorful shopping bags in a synthetic commerce scene');
        update_option('oddroom_orderops_store_image_id', $attachmentId, false);
        return $attachmentId;
    }

    private static function ensureSimpleProduct(int $imageId): int
    {
        $id = wc_get_product_id_by_sku('ODDROOM-DROP-KIT');
        $product = $id > 0 ? wc_get_product($id) : new WC_Product_Simple();
        if (!$product instanceof WC_Product_Simple) {
            throw new RuntimeException('Simple product SKU conflicts with another product type.');
        }
        $product->set_name('OddRoom Drop Kit');
        $product->set_sku('ODDROOM-DROP-KIT');
        $product->set_regular_price('39000');
        $product->set_virtual(true);
        $product->set_status('publish');
        $product->set_catalog_visibility('visible');
        $product->set_image_id($imageId);
        $product->set_short_description('A synthetic storefront kit used to prove immutable order capture and recoverable delivery.');
        $product->set_description('This test-only product creates WooCommerce domain facts without collecting real funds. It is part of the OddRoom OrderOps acceptance storefront.');
        return (int) $product->save();
    }

    private static function ensureVariableProduct(int $imageId): array
    {
        $id = wc_get_product_id_by_sku('ODDROOM-CAMPAIGN-PACK');
        $product = $id > 0 ? wc_get_product($id) : new WC_Product_Variable();
        if (!$product instanceof WC_Product_Variable) {
            throw new RuntimeException('Variable product SKU conflicts with another product type.');
        }
        $attribute = new WC_Product_Attribute();
        $attribute->set_name('Edition');
        $attribute->set_options(['Core', 'Plus']);
        $attribute->set_visible(true);
        $attribute->set_variation(true);
        $product->set_name('OddRoom Campaign Pack');
        $product->set_sku('ODDROOM-CAMPAIGN-PACK');
        $product->set_status('publish');
        $product->set_catalog_visibility('visible');
        $product->set_image_id($imageId);
        $product->set_attributes([$attribute]);
        $product->set_short_description('Choose Core or Plus to exercise real variation identifiers in the recoverable event path.');
        $product->set_description('A test-only variable product. Both editions use synthetic checkout and never collect funds.');
        $productId = (int) $product->save();
        $variationIds = [];
        foreach (['Core' => '79000', 'Plus' => '129000'] as $edition => $price) {
            $sku = 'ODDROOM-CAMPAIGN-' . strtoupper($edition);
            $variationId = wc_get_product_id_by_sku($sku);
            $variation = $variationId > 0 ? wc_get_product($variationId) : new WC_Product_Variation();
            if (!$variation instanceof WC_Product_Variation) {
                throw new RuntimeException('Variation SKU conflicts with another product type.');
            }
            $variation->set_parent_id($productId);
            $variation->set_sku($sku);
            $variation->set_attributes(['edition' => $edition]);
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
        $coupon->set_description('Synthetic acceptance coupon for the OddRoom OrderOps storefront.');
        return (int) $coupon->save();
    }
}
