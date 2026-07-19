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
            '0.3.0'
        );
        wp_enqueue_script(
            'oddroom-orderops-storefront',
            self::assetUrl('js/storefront.js'),
            [],
            '0.3.0',
            ['in_footer' => true, 'strategy' => 'defer']
        );
    }

    public static function navigation(): void
    {
        if (is_admin()) {
            return;
        }
        $links = [
            '홈' => home_url('/'),
            '데모 상품' => wc_get_page_permalink('shop'),
            '장바구니' => wc_get_cart_url(),
            '합성 주문' => wc_get_checkout_url(),
            '주문 조회' => wc_get_page_permalink('myaccount'),
        ];
        echo '<a class="oddroom-skip" href="#oddroom-main">본문으로 건너뛰기</a>';
        echo '<div class="oddroom-frontbar"><a class="oddroom-wordmark" href="' . esc_url(home_url('/')) . '" aria-label="OddRoom OrderOps 홈">ODDROOM<span>!</span></a>';
        echo '<nav aria-label="데모 상점 탐색"><ul>';
        foreach ($links as $label => $url) {
            echo '<li><a href="' . esc_url($url) . '">' . esc_html($label) . '</a></li>';
        }
        echo '</ul></nav><p>합성 주문 · 실제 결제 없음</p></div>';
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
                    <p class="oddroom-kicker">WooCommerce 주문 → HubSpot CRM → Slack 알림</p>
                    <h1 id="oddroom-hero-title">주문 운영을 놓치지 않는 <span>복구 설계.</span></h1>
                    <p class="oddroom-lead">결제·취소·환불 이벤트를 먼저 기록하고, 중복 실행을 막고, 실패 지점에서 안전하게 이어갑니다. 실제 WooCommerce 화면과 운영자 복구 화면을 한 흐름으로 확인하는 설치형 데모입니다.</p>
                    <div class="oddroom-hero-actions">
                        <a class="oddroom-button oddroom-button-primary" href="<?php echo esc_url($shop); ?>">상품으로 주문 흐름 보기</a>
                        <a class="oddroom-button" href="<?php echo esc_url($account); ?>">테스트 주문 조회</a>
                    </div>
                    <p class="oddroom-disclaimer">합성 구매 데이터만 사용 · 실제 결제 및 이메일 발송 없음 · 온디맨드 스테이징</p>
                </div>
                <figure class="oddroom-hero-visual">
                    <img src="<?php echo esc_url($image); ?>" width="1920" height="1280" alt="색색의 쇼핑백을 든 합성 상거래 캠페인 장면">
                    <figcaption><strong>실행 화면 01 / 주문 캡처</strong><span>구매 순간을 재현 가능한 운영 기록으로 남깁니다.</span></figcaption>
                </figure>
            </section>

            <section class="oddroom-proof-strip" aria-label="구현 검증 항목">
                <article><strong>4</strong><span>주문 이벤트 유형</span></article>
                <article><strong>6</strong><span>자동 전달 시도 상한</span></article>
                <article><strong>1</strong><span>주문별 동시 실행</span></article>
                <article><strong>HMAC</strong><span>요청 원문 서명 검증</span></article>
            </section>

            <section class="oddroom-section" aria-labelledby="oddroom-shop-title">
                <header><p class="oddroom-kicker">직접 실행하는 데모 상품</p><h2 id="oddroom-shop-title">실제 주문 화면에서 작동 방식을 확인하세요.</h2><p>단순 상품, 두 가지 옵션의 가변 상품, 할인 쿠폰이 같은 설치형 WooCommerce 환경에서 동작합니다.</p></header>
                <?php echo wp_kses_post(self::productCards()); ?>
                <p><a class="oddroom-text-link" href="<?php echo esc_url($shop); ?>">전체 데모 상품 보기 →</a></p>
            </section>

            <section class="oddroom-section oddroom-flow" aria-labelledby="oddroom-flow-title">
                <header><p class="oddroom-kicker">실패를 전제로 한 복구 흐름</p><h2 id="oddroom-flow-title">성공 화면보다, 이어갈 수 있는 상태를 남깁니다.</h2></header>
                <ol>
                    <li><span>01</span><div><h3>기록</h3><p>WooCommerce의 실제 발생 시각과 주문 내용을 정규화해 변경되지 않는 이벤트로 저장합니다.</p></div></li>
                    <li><span>02</span><div><h3>전달</h3><p>같은 주문의 외부 작업은 한 번에 하나만 실행하고, 정확한 작업 ID로 중복을 차단합니다.</p></div></li>
                    <li><span>03</span><div><h3>복구</h3><p>재시도 가능한 실패와 결과가 불명확한 상태를 구분해, 잘못된 중복 알림 없이 이어갑니다.</p></div></li>
                </ol>
            </section>

            <section class="oddroom-cta" aria-labelledby="oddroom-cta-title">
                <p class="oddroom-kicker">이 데모가 맞는 업무</p>
                <h2 id="oddroom-cta-title">주문에서 CRM까지, 운영 복구가 필요한 상점.</h2>
                <p>WooCommerce 주문을 CRM과 Slack으로 연결하고 실패를 추적·복구해야 하는 맞춤 업무에 적합합니다. 실제 결제, 모든 WooCommerce 예외, 대규모 트래픽, 형식적 exactly-once 전달을 증명하는 데모는 아닙니다.</p>
                <a class="oddroom-button oddroom-button-primary" href="<?php echo esc_url($shop); ?>">합성 주문 시작하기</a>
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
        $title = is_shop() ? '직접 실행하는 데모 상품'
            : (is_product() ? '주문 흐름을 시작할 상품'
                : (is_cart() ? '합성 주문 장바구니'
                    : (is_checkout() ? '실제 결제 없는 주문서' : '합성 주문 조회')));
        echo '<section id="oddroom-main" class="oddroom-commerce-intro" aria-label="OddRoom 데모 화면 안내">';
        echo '<p class="oddroom-kicker">ODDROOM ORDEROPS · 실행형 데모</p><p><strong>' . esc_html($title) . '</strong></p>';
        echo '<p>합성 구매 데이터와 비금전 결제 수단만 사용하는 온디맨드 스테이징 화면입니다.';
        if (is_checkout()) {
            echo ' 이름은 Synthetic / Buyer, 이메일은 소문자 @example.com 주소를 입력하세요.';
        }
        echo '</p></section>';
    }

    public static function footer(): void
    {
        if (is_admin()) {
            return;
        }
        echo '<aside class="oddroom-demo-footer" aria-label="데모 이용 범위"><strong>ODDROOM ORDEROPS</strong><span>온디맨드 스테이징 · 실제 결제 없음 · 합성 데이터 전용</span></aside>';
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
                '이 데모에서는 이름 Synthetic / Buyer와 소문자 @example.com 이메일만 사용할 수 있습니다.'
            );
            return;
        }
        if ($errors->has_errors()) {
            return;
        }
        if (!self::consumeCheckoutAllowance()) {
            $errors->add('oddroom_checkout_rate_limited', '합성 주문 허용 횟수에 도달했습니다. 잠시 후 다시 시도하세요.');
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
                '이 데모에서는 이름 Synthetic / Buyer와 소문자 @example.com 이메일만 사용할 수 있습니다.',
                ['status' => 422]
            );
        }
        if (self::consumeCheckoutAllowance()) {
            return $result;
        }
        return new WP_Error(
            'oddroom_checkout_rate_limited',
            '합성 주문 허용 횟수에 도달했습니다. 잠시 후 다시 시도하세요.',
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
        $attachmentId = self::ensureStoreImage();
        $categoryId = self::ensureProductCategory();
        $simpleId = self::ensureSimpleProduct($attachmentId, $categoryId);
        $variable = self::ensureVariableProduct($attachmentId, $categoryId);
        $couponId = self::ensureCoupon();
        $homeId = self::ensureHomePage();
        self::localizeCommercePages();

        update_option('show_on_front', 'page');
        update_option('page_on_front', $homeId);
        update_option('blog_public', '0');
        update_option('blogname', 'OddRoom OrderOps Lab');
        update_option('blogdescription', 'WooCommerce 주문 전달과 복구를 직접 실행하는 합성 데모');
        update_option('timezone_string', 'UTC');
        update_option('woocommerce_currency', 'KRW');
        update_option('woocommerce_price_num_decimals', '2');
        update_option('woocommerce_default_country', 'KR');
        update_option('woocommerce_enable_guest_checkout', 'yes');
        update_option('woocommerce_coming_soon', 'no');
        update_option('woocommerce_store_pages_only', 'no');
        update_option('oddroom_orderops_checkout_control_mode', self::CHECKOUT_MODE, false);
        update_option('woocommerce_cod_settings', [
            'enabled' => 'yes',
            'title' => '합성 주문 승인 — 실제 결제 없음',
            'description' => '테스트 전용 결제 수단입니다. 카드·계좌이체·현금 등 어떤 자금도 수집하지 않습니다.',
            'instructions' => '합성 스테이징 주문입니다. 결제할 금액은 없습니다.',
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
            return '<p>데모 상품을 준비하고 있습니다.</p>';
        }
        $html = '<div class="oddroom-product-grid">';
        foreach ($products as $product) {
            if (!$product instanceof WC_Product) {
                continue;
            }
            $image = $product->get_image('woocommerce_thumbnail', ['loading' => 'lazy']);
            $html .= '<article><a href="' . esc_url($product->get_permalink()) . '">'
                . wp_kses_post($image)
                . '<span class="oddroom-product-tag">합성 데모 상품</span><h3>' . esc_html($product->get_name()) . '</h3>'
                . '<p class="price">' . wp_kses_post($product->get_price_html()) . '</p><span class="oddroom-card-link">상품 상세 보기 →</span></a></article>';
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
            wp_update_post(['ID' => $existing, 'post_title' => 'OddRoom 합성 쇼핑 장면']);
            update_post_meta($existing, '_wp_attachment_image_alt', '쇼핑백을 든 인물이 있는 OddRoom 합성 상거래 장면');
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
            'post_title' => 'OddRoom 합성 쇼핑 장면',
            'post_content' => '',
            'post_status' => 'inherit',
        ], $upload['file']);
        if (!is_int($attachmentId) || $attachmentId < 1) {
            throw new RuntimeException('Store image attachment failed.');
        }
        require_once ABSPATH . 'wp-admin/includes/image.php';
        wp_update_attachment_metadata($attachmentId, wp_generate_attachment_metadata($attachmentId, $upload['file']));
        update_post_meta($attachmentId, '_wp_attachment_image_alt', '쇼핑백을 든 인물이 있는 OddRoom 합성 상거래 장면');
        update_option('oddroom_orderops_store_image_id', $attachmentId, false);
        return $attachmentId;
    }

    private static function ensureSimpleProduct(int $imageId, int $categoryId): int
    {
        $id = wc_get_product_id_by_sku('ODDROOM-DROP-KIT');
        $product = $id > 0 ? wc_get_product($id) : new WC_Product_Simple();
        if (!$product instanceof WC_Product_Simple) {
            throw new RuntimeException('Simple product SKU conflicts with another product type.');
        }
        $product->set_name('OddRoom 드롭 키트');
        $product->set_slug('oddroom-drop-kit');
        $product->set_sku('ODDROOM-DROP-KIT');
        $product->set_regular_price('39000');
        $product->set_virtual(true);
        $product->set_status('publish');
        $product->set_catalog_visibility('visible');
        $product->set_image_id($imageId);
        $product->set_category_ids([$categoryId]);
        $product->set_short_description('주문 기록부터 CRM 전달, 실패 복구까지 한 번에 확인하는 합성 데모 상품입니다.');
        $product->set_description('실제 결제 없이 WooCommerce 주문 이벤트를 만들고 OddRoom OrderOps의 기록·전달·복구 흐름을 확인합니다. 모든 구매 정보는 합성 데이터만 사용합니다.');
        return (int) $product->save();
    }

    private static function ensureVariableProduct(int $imageId, int $categoryId): array
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
        $product->set_name('OddRoom 캠페인 팩');
        $product->set_slug('oddroom-campaign-pack');
        $product->set_sku('ODDROOM-CAMPAIGN-PACK');
        $product->set_status('publish');
        $product->set_catalog_visibility('visible');
        $product->set_image_id($imageId);
        $product->set_category_ids([$categoryId]);
        $product->set_attributes([$attribute]);
        $product->set_short_description('Core 또는 Plus 구성을 선택해 실제 variation ID가 복구 가능한 주문 경로로 전달되는지 확인합니다.');
        $product->set_description('두 가지 구성을 가진 테스트 전용 가변 상품입니다. 모든 주문은 합성 checkout을 사용하며 실제 자금을 수집하지 않습니다.');
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
        $coupon->set_description('OddRoom OrderOps 합성 주문 검증용 10% 할인 쿠폰입니다.');
        return (int) $coupon->save();
    }

    private static function ensureProductCategory(): int
    {
        $existing = term_exists('demo-products', 'product_cat');
        if (is_array($existing)) {
            return (int) $existing['term_id'];
        }
        if (is_int($existing) && $existing > 0) {
            return $existing;
        }
        $created = wp_insert_term('데모 상품', 'product_cat', ['slug' => 'demo-products']);
        if (is_wp_error($created) || !is_array($created) || (int) ($created['term_id'] ?? 0) < 1) {
            throw new RuntimeException('Product category setup failed.');
        }
        return (int) $created['term_id'];
    }

    private static function localizeCommercePages(): void
    {
        foreach ([
            'woocommerce_shop_page_id' => '데모 상품',
            'woocommerce_cart_page_id' => '장바구니',
            'woocommerce_checkout_page_id' => '합성 주문',
            'woocommerce_myaccount_page_id' => '주문 조회',
        ] as $option => $title) {
            $pageId = (int) get_option($option, 0);
            if ($pageId < 1) {
                continue;
            }
            $result = wp_update_post(['ID' => $pageId, 'post_title' => $title], true);
            if (is_wp_error($result)) {
                throw new RuntimeException('Commerce page localization failed.');
            }
        }
    }
}
