<?php
/**
 * Plugin Name: OddRoom OrderOps
 * Description: Recoverable WooCommerce order delivery to a signed n8n adapter.
 * Version: 0.1.0
 * Requires PHP: 8.1
 * Requires Plugins: woocommerce
 * License: GPL-2.0-or-later
 */

defined('ABSPATH') || exit;

require_once __DIR__ . '/includes/class-oddroom-canonical-payload.php';
require_once __DIR__ . '/includes/class-oddroom-signature.php';
require_once __DIR__ . '/includes/class-oddroom-state-machine.php';
require_once __DIR__ . '/includes/class-oddroom-retry-policy.php';

