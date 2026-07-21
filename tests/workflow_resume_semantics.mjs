import assert from 'node:assert/strict';
import { createHmac } from 'node:crypto';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';

const require = createRequire(new URL('../infra/task-runner-deps/package.json', import.meta.url));
const workflow = JSON.parse(readFileSync(new URL('../workflow/oddroom-orderops-vsl.json', import.meta.url), 'utf8'));
const codeByName = new Map(
  workflow.nodes
    .filter((node) => typeof node.parameters?.jsCode === 'string')
    .map((node) => [node.name, node.parameters.jsCode]),
);

function execute(name, nodes, input, env = {}, binary = null) {
  const source = codeByName.get(name);
  assert.equal(typeof source, 'string', `${name}: Code node source is missing`);
  const lookup = (nodeName) => ({
    first() {
      if (!Object.hasOwn(nodes, nodeName)) throw new Error(`${nodeName}: node was not executed`);
      return { json: nodes[nodeName] };
    },
  });
  const inputApi = { first: () => ({ json: input, ...(binary ? { binary } : {}) }) };
  return new Function('$', '$input', '$env', 'require', source)(lookup, inputApi, env, require);
}

const verifySecret = 'pf07-synthetic-semantic-hmac-secret';

function rawPayload({ orderId = '42', eventKeyOrderId = orderId, itemId = '1', productId = '2', variationId = '0', firstName = 'Resume' } = {}) {
  const shopInstanceId = 'pf07-00000000-0000-4000-8000-000000000000';
  const eventKey = `v1:${shopInstanceId}:${eventKeyOrderId}:ORDER_CREATED`;
  const payload = {
    schema_version: '1',
    event_key: eventKey,
    shop_instance_id: shopInstanceId,
    run_id: '00000000-0000-4000-8000-000000000001',
    event_type: 'ORDER_CREATED',
    occurred_at_utc: '2026-07-19T00:00:00Z',
    occurred_at_source: 'date_created',
    state_rank: 10,
    order: {
      id: '__ORDER_ID__',
      number: eventKeyOrderId,
      currency: 'KRW',
      total: '18700.00',
      customer: { email: 'pf07+verify@example.com', first_name: firstName, last_name: 'Fixture' },
      items: [{
        item_id: '__ITEM_ID__',
        product_id: '__PRODUCT_ID__',
        variation_id: '__VARIATION_ID__',
        sku: 'PF07-SKU',
        name: 'OddRoom fixture',
        quantity: 1,
        line_total: '18700.00',
      }],
      coupon_codes: [],
    },
  };
  const text = JSON.stringify(payload)
    .replace('"__ORDER_ID__"', orderId)
    .replace('"__ITEM_ID__"', itemId)
    .replace('"__PRODUCT_ID__"', productId)
    .replace('"__VARIATION_ID__"', variationId);
  return { eventKey, raw: Buffer.from(text, 'utf8') };
}

function verifyRaw(raw, eventKey) {
  const timestamp = String(Math.floor(Date.now() / 1000));
  const phase = 'created';
  const base = Buffer.concat([Buffer.from(`${timestamp}.${eventKey}.${phase}.`, 'utf8'), raw]);
  const signature = `v1=${createHmac('sha256', verifySecret).update(base).digest('hex')}`;
  return execute(
    'Verify HMAC Then Decode',
    {},
    { headers: {
      'x-oddroom-event-key': eventKey,
      'x-oddroom-timestamp': timestamp,
      'x-oddroom-resume-phase': phase,
      'x-oddroom-signature': signature,
    } },
    { ODDROOM_WEBHOOK_HMAC_KEY: verifySecret },
    { data: { data: raw.toString('base64') } },
  )[0].json;
}

const signed64Max = rawPayload({
  orderId: '9223372036854775807',
  itemId: '9223372036854775807',
  productId: '9223372036854775807',
  variationId: '9223372036854775807',
});
const signed64MaxResult = verifyRaw(signed64Max.raw, signed64Max.eventKey);
assert.equal(signed64MaxResult.authorized, true, 'signed 64-bit maximum IDs must be accepted exactly');
assert.equal(signed64MaxResult.payload.order.id, '9223372036854775807');
assert.equal(signed64MaxResult.payload.order.items[0].product_id, '9223372036854775807');
assert.equal(signed64MaxResult.order_key, 'pf07-00000000-0000-4000-8000-000000000000:9223372036854775807');

const zeroOrderId = rawPayload({ orderId: '0' });
const zeroOrderIdResult = verifyRaw(zeroOrderId.raw, zeroOrderId.eventKey);
assert.equal(zeroOrderIdResult.authorized, true, 'the contracted non-negative order-ID boundary must be accepted');
assert.equal(zeroOrderIdResult.payload.order.id, 0);

const signed64MaxExponent = rawPayload({ orderId: '9.223372036854775807e18', eventKeyOrderId: '9223372036854775807' });
const signed64MaxExponentResult = verifyRaw(signed64MaxExponent.raw, signed64MaxExponent.eventKey);
assert.equal(signed64MaxExponentResult.authorized, true, 'an exact integer exponent representation at signed-64 maximum must be accepted');
assert.equal(signed64MaxExponentResult.payload.order.id, '9223372036854775807');

const signed64Overflow = rawPayload({ orderId: '9223372036854775808' });
assert.equal(verifyRaw(signed64Overflow.raw, signed64Overflow.eventKey).error.error_code, 'PAYLOAD_INVALID');

const negativeItem = rawPayload({ itemId: '-1' });
assert.equal(verifyRaw(negativeItem.raw, negativeItem.eventKey).error.error_code, 'PAYLOAD_INVALID');

const codePointBoundary = rawPayload({ firstName: '😀'.repeat(255) });
assert.equal(verifyRaw(codePointBoundary.raw, codePointBoundary.eventKey).authorized, true, '255 astral Unicode code points must be accepted');
const codePointOverflow = rawPayload({ firstName: '😀'.repeat(256) });
assert.equal(verifyRaw(codePointOverflow.raw, codePointOverflow.eventKey).error.error_code, 'PAYLOAD_INVALID');

const invalidUtf8 = rawPayload();
const invalidOffset = invalidUtf8.raw.indexOf(Buffer.from('Resume', 'utf8'));
assert.notEqual(invalidOffset, -1);
invalidUtf8.raw[invalidOffset] = 0xff;
assert.equal(verifyRaw(invalidUtf8.raw, invalidUtf8.eventKey).error.error_code, 'PAYLOAD_INVALID');

const currencyMismatch = rawPayload();
currencyMismatch.raw = Buffer.from(currencyMismatch.raw.toString('utf8').replace('"currency":"KRW"', '"currency":"USD"'), 'utf8');
assert.equal(verifyRaw(currencyMismatch.raw, currencyMismatch.eventKey).error.error_code, 'PAYLOAD_INVALID');
const precisionMismatch = rawPayload();
precisionMismatch.raw = Buffer.from(precisionMismatch.raw.toString('utf8').replace('"total":"18700.00"', '"total":"18700.0"'), 'utf8');
assert.equal(verifyRaw(precisionMismatch.raw, precisionMismatch.eventKey).error.error_code, 'PAYLOAD_INVALID');

const emptySku = rawPayload();
emptySku.raw = Buffer.from(emptySku.raw.toString('utf8').replace('"sku":"PF07-SKU"', '"sku":""'), 'utf8');
assert.equal(verifyRaw(emptySku.raw, emptySku.eventKey).authorized, true, 'an empty WooCommerce SKU must remain valid');

const invalidCalendarDate = rawPayload();
invalidCalendarDate.raw = Buffer.from(invalidCalendarDate.raw.toString('utf8').replace('2026-07-19T00:00:00Z', '2026-02-30T00:00:00Z'), 'utf8');
assert.equal(verifyRaw(invalidCalendarDate.raw, invalidCalendarDate.eventKey).error.error_code, 'PAYLOAD_INVALID');

for (const [label, needle, replacement] of [
  ['top-level', '"order":{', '"unexpected":true,"order":{'],
  ['order', '"currency":"KRW"', '"unexpected":true,"currency":"KRW"'],
  ['customer', '"email":"pf07+verify@example.com"', '"unexpected":true,"email":"pf07+verify@example.com"'],
  ['item', '"item_id":__ITEM_ID__', '"unexpected":true,"item_id":__ITEM_ID__'],
]) {
  const fixture = rawPayload();
  const source = fixture.raw.toString('utf8');
  const actualNeedle = needle.replace('__ITEM_ID__', '1');
  const actualReplacement = replacement.replace('__ITEM_ID__', '1');
  assert.notEqual(source.indexOf(actualNeedle), -1, `${label} mutation anchor must exist`);
  fixture.raw = Buffer.from(source.replace(actualNeedle, actualReplacement), 'utf8');
  assert.equal(verifyRaw(fixture.raw, fixture.eventKey).error.error_code, 'PAYLOAD_INVALID', `${label} additional property must be rejected`);
}

function context(eventType = 'ORDER_CREATED', phase = 'created') {
  const ranks = { ORDER_CREATED: 10, PAYMENT_CONFIRMED: 20, ORDER_CANCELLED: 30, ORDER_REFUNDED: 40 };
  const sources = { ORDER_CREATED: 'date_created', PAYMENT_CONFIRMED: 'date_paid', ORDER_CANCELLED: '_oddroom_orderops_cancelled_at_utc', ORDER_REFUNDED: 'full_refund_completion' };
  const eventKey = `v1:shop-fixture:42:${eventType}`;
  return {
    authorized: true,
    event_key: eventKey,
    resume_phase: phase,
    order_key: 'shop-fixture:42',
    payload: {
      schema_version: '1',
      event_key: eventKey,
      shop_instance_id: 'shop-fixture',
      run_id: '00000000-0000-4000-8000-000000000001',
      event_type: eventType,
      state_rank: ranks[eventType],
      occurred_at_utc: '2026-07-19T00:00:00Z',
      occurred_at_source: sources[eventType],
      order: {
        id: 42,
        number: '42',
        currency: 'KRW',
        total: '18700.00',
        customer: { email: 'pf07+resume@example.com', first_name: 'Resume', last_name: 'Fixture' },
      },
    },
    deal_read_body: { idProperty: 'oddroom_wc_order_key', inputs: [{ id: 'shop-fixture:42' }] },
  };
}

function existingDeal(ctx, rank = ctx.payload.state_rank, eventKey = ctx.event_key) {
  return {
    id: 'deal-fixture-1',
    properties: {
      oddroom_wc_order_key: ctx.order_key,
      oddroom_order_state: rank === ctx.payload.state_rank ? ctx.payload.event_type : 'PAYMENT_CONFIRMED',
      oddroom_order_state_rank: String(rank),
      oddroom_last_event_at: ctx.payload.occurred_at_utc,
      oddroom_last_event_key: eventKey,
      dealname: `OFFSET order ${ctx.payload.order.number}`,
      pipeline: 'default',
      dealstage: 'appointmentscheduled',
    },
  };
}

function dealReadResponse(existing = null) {
  return { statusCode: 200, body: { status: 'COMPLETE', results: existing ? [existing] : [] } };
}

function resolve(ctx, existing = null) {
  return execute(
    'Resolve Monotonic Deal State',
    { 'Verify HMAC Then Decode': ctx },
    dealReadResponse(existing),
    { HUBSPOT_PIPELINE_ID: 'default', HUBSPOT_INITIAL_STAGE_ID: 'appointmentscheduled' },
  )[0].json;
}

const created = context();
const createdRoute = resolve(created);
assert.equal(createdRoute.mode, 'advance');
assert.deepEqual(
  [createdRoute.contact_mutation_required, createdRoute.deal_mutation_required, createdRoute.association_mutation_required],
  [true, true, true],
  'A new created event must execute the complete mutation path',
);

const contactResume = context('PAYMENT_CONFIRMED', 'contact_upserted');
const contactResumeRoute = resolve(contactResume);
assert.equal(contactResumeRoute.continue_work, true);
assert.deepEqual(
  [contactResumeRoute.contact_mutation_required, contactResumeRoute.deal_mutation_required, contactResumeRoute.association_mutation_required],
  [false, true, true],
  'contact_upserted must read Contact and resume at Deal mutation',
);

const missingAdvanced = context('PAYMENT_CONFIRMED', 'deal_upserted');
const missingAdvancedRoute = resolve(missingAdvanced);
assert.equal(missingAdvancedRoute.response_code, 409);
assert.equal(missingAdvancedRoute.envelope.result, 'operator_review');
assert.equal(missingAdvancedRoute.envelope.error_code, 'RESUME_PHASE_CONFLICT');

const duplicateContext = context('ORDER_CREATED', 'created');
const duplicateRoute = resolve(duplicateContext, existingDeal(duplicateContext));
assert.equal(duplicateRoute.mode, 'duplicate');
assert.deepEqual(
  [duplicateRoute.contact_mutation_required, duplicateRoute.deal_mutation_required, duplicateRoute.association_mutation_required],
  [false, false, false],
  'created ORDER_CREATED replay must be entirely read-only',
);

const slackCreated = context('PAYMENT_CONFIRMED', 'created');
const slackCreatedRoute = resolve(slackCreated, existingDeal(slackCreated));
assert.equal(slackCreatedRoute.response_code, 409);
assert.equal(slackCreatedRoute.envelope.error_code, 'RESUME_PHASE_CONFLICT');

const slackPending = context('PAYMENT_CONFIRMED', 'slack_pending');
const slackPendingRoute = resolve(slackPending, existingDeal(slackPending));
assert.equal(slackPendingRoute.mode, 'resume');
assert.deepEqual(
  [slackPendingRoute.contact_mutation_required, slackPendingRoute.deal_mutation_required, slackPendingRoute.association_mutation_required],
  [false, false, false],
  'slack_pending must verify all CRM facts without repeating mutations',
);

const staleContext = context('ORDER_CREATED', 'created');
const higherKey = 'v1:shop-fixture:42:PAYMENT_CONFIRMED';
const staleRoute = resolve(staleContext, existingDeal(staleContext, 20, higherKey));
assert.equal(staleRoute.continue_work, false);
assert.equal(staleRoute.response_code, 200);
assert.equal(staleRoute.envelope.result, 'stale_ignored');
assert.equal(staleRoute.envelope.remote_contact_id, null);
assert.equal(staleRoute.envelope.remote_deal_id, 'deal-fixture-1');

const malformedStaleState = existingDeal(staleContext, 20, higherKey);
malformedStaleState.properties.oddroom_order_state = 'ORDER_REFUNDED';
assert.equal(resolve(staleContext, malformedStaleState).envelope.error_code, 'HUBSPOT_SCHEMA');
const malformedStaleTime = existingDeal(staleContext, 20, higherKey);
malformedStaleTime.properties.oddroom_last_event_at = '2026-02-30T00:00:00Z';
assert.equal(resolve(staleContext, malformedStaleTime).envelope.error_code, 'HUBSPOT_SCHEMA');

const conflictingEqual = resolve(duplicateContext, existingDeal(duplicateContext, 10, 'v1:shop-fixture:42:OTHER'));
assert.equal(conflictingEqual.response_code, 422);
assert.equal(conflictingEqual.envelope.result, 'terminal_error');

function contactRead(route, ctx, properties = ctx.payload.order.customer) {
  const contactResponse = {
    statusCode: 200,
    body: {
      status: 'COMPLETE',
      results: [{ id: 'contact-fixture-1', properties: { email: ctx.payload.order.customer.email, firstname: properties.first_name, lastname: properties.last_name } }],
    },
  };
  return execute(
    'Validate Contact Read',
    { 'Verify HMAC Then Decode': ctx, 'Resolve Monotonic Deal State': route },
    contactResponse,
  )[0].json;
}

const duplicateContact = contactRead(duplicateRoute, duplicateContext);
assert.equal(duplicateContact.continue_deal_stage, true);

const contactUpsertCandidate = execute(
  'Validate Contact Upsert',
  { 'Verify HMAC Then Decode': created, 'Resolve Monotonic Deal State': createdRoute },
  { statusCode: 200, body: { status: 'COMPLETE', results: [{ id: 'contact-candidate-1' }] } },
)[0].json;
const contactReadUnavailable = execute(
  'Validate Contact Read',
  {
    'Verify HMAC Then Decode': created,
    'Resolve Monotonic Deal State': createdRoute,
    'Validate Contact Upsert': contactUpsertCandidate,
  },
  { statusCode: 503, body: {} },
)[0].json;
assert.equal(contactReadUnavailable.envelope.processing_phase, 'deal_resolved');
assert.equal(contactReadUnavailable.envelope.remote_contact_id, null, 'an unverified upsert candidate must not become a Contact checkpoint');

const missingContact = execute(
  'Validate Contact Read',
  { 'Verify HMAC Then Decode': contactResume, 'Resolve Monotonic Deal State': contactResumeRoute },
  { statusCode: 200, body: { status: 'COMPLETE', results: [] } },
)[0].json;
assert.equal(missingContact.response_code, 409);
assert.equal(missingContact.envelope.error_code, 'RESUME_PHASE_CONFLICT');
assert.equal(missingContact.envelope.processing_phase, 'contact_upserted');

const duplicateDeal = execute(
  'Validate Deal Readback',
  { 'Verify HMAC Then Decode': duplicateContext, 'Validate Contact Read': duplicateContact },
  dealReadResponse(existingDeal(duplicateContext)),
  { HUBSPOT_PIPELINE_ID: 'default', HUBSPOT_INITIAL_STAGE_ID: 'appointmentscheduled' },
)[0].json;
assert.equal(duplicateDeal.continue_association_stage, true);

const driftedPresentation = existingDeal(duplicateContext);
driftedPresentation.properties.dealstage = 'closedwon';
const driftedDealResult = execute(
  'Validate Deal Readback',
  { 'Verify HMAC Then Decode': duplicateContext, 'Validate Contact Read': duplicateContact },
  dealReadResponse(driftedPresentation),
  { HUBSPOT_PIPELINE_ID: 'default', HUBSPOT_INITIAL_STAGE_ID: 'appointmentscheduled' },
)[0].json;
assert.equal(driftedDealResult.response_code, 409, 'a read-only duplicate must reject drifted Deal presentation');
assert.equal(driftedDealResult.envelope.error_code, 'RESUME_PHASE_CONFLICT');

const createdContact = contactRead(createdRoute, created);
const dealUpsertCandidate = execute(
  'Validate Deal Upsert',
  { 'Verify HMAC Then Decode': created, 'Validate Contact Read': createdContact },
  { statusCode: 200, body: { status: 'COMPLETE', results: [{ id: 'deal-candidate-1' }] } },
)[0].json;
const dealReadUnavailable = execute(
  'Validate Deal Readback',
  {
    'Verify HMAC Then Decode': created,
    'Validate Contact Read': createdContact,
    'Validate Deal Upsert': dealUpsertCandidate,
  },
  { statusCode: 503, body: {} },
  { HUBSPOT_PIPELINE_ID: 'default', HUBSPOT_INITIAL_STAGE_ID: 'appointmentscheduled' },
)[0].json;
assert.equal(dealReadUnavailable.envelope.processing_phase, 'contact_upserted');
assert.equal(dealReadUnavailable.envelope.remote_deal_id, null, 'an unverified upsert candidate must not become a Deal checkpoint');

const duplicateFinal = execute(
  'Prepare Slack Or Complete',
  { 'Verify HMAC Then Decode': duplicateContext, 'Validate Deal Readback': duplicateDeal },
  { statusCode: 200, body: { results: [{ toObjectId: duplicateDeal.deal_id }] } },
)[0].json;
assert.equal(duplicateFinal.response_code, 200);
assert.equal(duplicateFinal.envelope.result, 'duplicate_noop');

const pendingAssociation = execute(
  'Prepare Slack Or Complete',
  { 'Verify HMAC Then Decode': duplicateContext, 'Validate Deal Readback': duplicateDeal },
  { statusCode: 200, body: { status: 'PENDING', results: [{ toObjectId: duplicateDeal.deal_id }] } },
)[0].json;
assert.notEqual(pendingAssociation.envelope.result, 'duplicate_noop', 'a PENDING association read must not advance or complete');

const missingReadOnlyAssociation = execute(
  'Prepare Slack Or Complete',
  { 'Verify HMAC Then Decode': duplicateContext, 'Validate Deal Readback': duplicateDeal },
  { statusCode: 200, body: { results: [] } },
)[0].json;
assert.equal(missingReadOnlyAssociation.response_code, 409);
assert.equal(missingReadOnlyAssociation.envelope.error_code, 'RESUME_PHASE_CONFLICT');

const slackPrepared = {
  contact_id: 'contact-fixture-1',
  deal_id: 'deal-fixture-1',
  slack_body: { channel: 'channel-fixture', text: 'synthetic' },
  trace: ['associated', 'slack_pending'],
};
const unavailableFaultStatus = execute(
  'Slack Pre-Post Fault Gate',
  { 'Verify HMAC Then Decode': slackPending, 'Prepare Fault Lookup': slackPrepared },
  { statusCode: 503, body: {} },
)[0].json;
assert.equal(unavailableFaultStatus.send_slack, false, 'Slack must fail closed when pre-post authorization is unavailable');
assert.equal(unavailableFaultStatus.envelope.error_code, 'SLACK_RETRYABLE_BEFORE_POST');

const inactiveFaultStatus = execute(
  'Slack Pre-Post Fault Gate',
  { 'Verify HMAC Then Decode': slackPending, 'Prepare Fault Lookup': slackPrepared },
  { statusCode: 200, body: { authorized: true, active: false } },
)[0].json;
assert.equal(inactiveFaultStatus.send_slack, true);
const exponentRetryAfter = execute(
  'Validate Slack Result',
  { 'Verify HMAC Then Decode': slackPending, 'Slack Pre-Post Fault Gate': inactiveFaultStatus },
  { statusCode: 429, headers: { 'retry-after': '1e5' }, body: { ok: false, error: 'ratelimited' } },
  { SLACK_CHANNEL_ID: 'channel-fixture' },
)[0].json;
assert.equal(exponentRetryAfter.envelope.retry_after_seconds, null, 'scientific-notation Retry-After must be rejected');
const exactRetryAfter = execute(
  'Validate Slack Result',
  { 'Verify HMAC Then Decode': slackPending, 'Slack Pre-Post Fault Gate': inactiveFaultStatus },
  { statusCode: 429, headers: { 'retry-after': '90001' }, body: { ok: false, error: 'ratelimited' } },
  { SLACK_CHANNEL_ID: 'channel-fixture' },
)[0].json;
assert.equal(exactRetryAfter.envelope.retry_after_seconds, 90001, 'exact delta-seconds Retry-After was not preserved');

console.log('PASS: workflow exact-resource and resume-phase semantic branches');
