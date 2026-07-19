<?php

defined('ABSPATH') || exit;

/**
 * Keeps WordPress canonical public URLs while permitting loopback-only
 * administrator observation through the separately bound WordPress port.
 */
final class OddRoom_Private_Admin
{
    private const HEADER = 'HTTP_X_ODDROOM_PRIVATE_ADMIN';
    private const HEADER_VALUE = 'loopback';
    private static bool $htmlRewriteStarted = false;

    public static function boot(): void
    {
        if (self::privateOrigin() !== null) {
            force_ssl_admin(false);
        }

        add_filter('option_home', [self::class, 'rewriteOptionUrl'], 100);
        add_filter('option_siteurl', [self::class, 'rewriteOptionUrl'], 100);
        add_filter('rest_post_dispatch', [self::class, 'rewriteRestResponse'], 100, 3);

        foreach ([
            'home_url' => 4,
            'site_url' => 4,
            'network_home_url' => 3,
            'network_site_url' => 3,
            'admin_url' => 3,
            'includes_url' => 2,
            'content_url' => 2,
            'plugins_url' => 3,
            'rest_url' => 4,
        ] as $hook => $acceptedArgs) {
            add_filter($hook, [self::class, 'rewriteUrl'], 100, $acceptedArgs);
        }

        add_filter('wp_redirect', [self::class, 'rewriteUrl'], 100, 2);
        add_filter('login_redirect', [self::class, 'rewriteUrl'], 100, 3);
        add_filter('logout_redirect', [self::class, 'rewriteUrl'], 100, 3);
        add_filter('allowed_redirect_hosts', [self::class, 'allowRedirectHosts'], 100);
        self::startHtmlRewrite();
    }

    public static function rewriteUrl(mixed $url, mixed ...$unused): mixed
    {
        $origin = self::privateOrigin();
        if ($origin === null || !is_string($url) || $url === '') {
            return $url;
        }

        $parts = wp_parse_url($url);
        if (!is_array($parts) || !isset($parts['host']) || !self::isWordPressHost((string) $parts['host'])) {
            return $url;
        }

        return $origin
            . ($parts['path'] ?? '')
            . (isset($parts['query']) ? '?' . $parts['query'] : '')
            . (isset($parts['fragment']) ? '#' . $parts['fragment'] : '');
    }

    public static function allowRedirectHosts(array $hosts): array
    {
        $origin = self::privateOrigin();
        if ($origin === null) {
            return $hosts;
        }

        $host = wp_parse_url($origin, PHP_URL_HOST);
        if (is_string($host) && !in_array($host, $hosts, true)) {
            $hosts[] = $host;
        }

        return $hosts;
    }

    public static function rewriteOptionUrl(mixed $url): mixed
    {
        return self::privateOrigin() ?? $url;
    }

    public static function startHtmlRewrite(): void
    {
        if (self::$htmlRewriteStarted
            || self::privateOrigin() === null
            || strtoupper((string) ($_SERVER['REQUEST_METHOD'] ?? 'GET')) !== 'GET'
            || !str_contains(strtolower((string) ($_SERVER['HTTP_ACCEPT'] ?? '')), 'text/html')
            || (function_exists('wp_doing_ajax') && wp_doing_ajax())
            || (defined('REST_REQUEST') && REST_REQUEST)) {
            return;
        }

        self::$htmlRewriteStarted = true;
        ob_start([self::class, 'rewriteHtml']);
    }

    public static function rewriteHtml(string $html): string
    {
        return self::rewriteCanonicalString($html);
    }

    public static function rewriteRestResponse(mixed $response, mixed ...$unused): mixed
    {
        if (self::privateOrigin() === null || !($response instanceof WP_HTTP_Response)) {
            return $response;
        }

        $response->set_data(self::rewriteValue($response->get_data()));
        return $response;
    }

    private static function privateOrigin(): ?string
    {
        if (!isset($_SERVER[self::HEADER])
            || !hash_equals(self::HEADER_VALUE, (string) $_SERVER[self::HEADER])) {
            return null;
        }

        $host = strtolower(trim((string) ($_SERVER['HTTP_HOST'] ?? '')));
        if (!preg_match('/^(?:127\.0\.0\.1|localhost|\[::1\])(?::(?:[1-9][0-9]{0,4}))?$/', $host)) {
            return null;
        }

        $https = isset($_SERVER['HTTPS']) && !in_array(strtolower((string) $_SERVER['HTTPS']), ['', 'off', '0'], true);
        return ($https ? 'https' : 'http') . '://' . $host;
    }

    private static function isWordPressHost(string $host): bool
    {
        $host = strtolower($host);
        if (in_array($host, ['127.0.0.1', 'localhost', '::1'], true)) {
            return true;
        }

        $urls = [];
        if (defined('WP_HOME')) {
            $urls[] = (string) WP_HOME;
        }
        if (defined('WP_SITEURL')) {
            $urls[] = (string) WP_SITEURL;
        }
        $urls[] = (string) get_option('home', '');
        $urls[] = (string) get_option('siteurl', '');

        foreach ($urls as $url) {
            $knownHost = wp_parse_url($url, PHP_URL_HOST);
            if (is_string($knownHost) && strtolower($knownHost) === $host) {
                return true;
            }
        }

        return false;
    }

    private static function rewriteValue(mixed $value): mixed
    {
        if (is_string($value)) {
            return self::rewriteCanonicalString($value);
        }
        if (is_array($value)) {
            foreach ($value as $key => $item) {
                $value[$key] = self::rewriteValue($item);
            }
        }
        return $value;
    }

    private static function rewriteCanonicalString(string $value): string
    {
        $origin = self::privateOrigin();
        if ($origin === null) {
            return $value;
        }

        $privateAuthority = preg_replace('#^[a-z][a-z0-9+.-]*://#i', '', $origin);
        if (!is_string($privateAuthority) || $privateAuthority === '') {
            return $value;
        }
        $privateProtocolRelative = '//' . $privateAuthority;
        $escapedPrivateProtocolRelative = str_replace('/', '\\/', $privateProtocolRelative);

        foreach (self::canonicalOrigins() as $canonical) {
            $canonicalHost = wp_parse_url($canonical, PHP_URL_HOST);
            $canonicalPort = wp_parse_url($canonical, PHP_URL_PORT);
            $canonicalAuthority = is_string($canonicalHost)
                ? $canonicalHost . (is_int($canonicalPort) ? ':' . $canonicalPort : '')
                : '';
            $protocolRelative = $canonicalAuthority === '' ? '' : '//' . $canonicalAuthority;
            $escapedProtocolRelative = str_replace('/', '\\/', $protocolRelative);
            $value = str_replace(
                array_values(array_filter([
                    $canonical,
                    str_replace('/', '\\/', $canonical),
                    $protocolRelative,
                    $escapedProtocolRelative,
                ], static fn (string $candidate): bool => $candidate !== '')),
                array_values(array_filter([
                    $origin,
                    str_replace('/', '\\/', $origin),
                    $protocolRelative === '' ? '' : $privateProtocolRelative,
                    $escapedProtocolRelative === '' ? '' : $escapedPrivateProtocolRelative,
                ], static fn (string $candidate): bool => $candidate !== '')),
                $value
            );
        }
        return $value;
    }

    private static function canonicalOrigins(): array
    {
        $origins = [];
        foreach (['WP_HOME', 'WP_SITEURL'] as $constant) {
            if (!defined($constant)) {
                continue;
            }
            $url = rtrim((string) constant($constant), '/');
            if ($url !== '' && wp_parse_url($url, PHP_URL_HOST)) {
                $origins[] = $url;
            }
        }
        return array_values(array_unique($origins));
    }
}
