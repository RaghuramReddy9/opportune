import assert from 'node:assert/strict';
import test from 'node:test';

import {
  normalizeWorkFocuses,
  parseLocationDraft,
  toggleCappedSelection,
} from '../.test-dist/formState.js';

test('work focus choices can add and remove up to three selections', () => {
  let choices = toggleCappedSelection([], 'ai_product_engineering', 3);
  choices = toggleCappedSelection(choices, 'customer_facing', 3);
  choices = toggleCappedSelection(choices, 'platform_infrastructure', 3);

  assert.deepEqual(choices, [
    'ai_product_engineering',
    'customer_facing',
    'platform_infrastructure',
  ]);
  assert.deepEqual(toggleCappedSelection(choices, 'model_engineering', 3), choices);
  assert.deepEqual(toggleCappedSelection(choices, 'customer_facing', 3), [
    'ai_product_engineering',
    'platform_infrastructure',
  ]);
});

test('legacy single work focus is normalized without losing compatibility', () => {
  assert.deepEqual(normalizeWorkFocuses('ai_product_engineering'), ['ai_product_engineering']);
  assert.deepEqual(normalizeWorkFocuses(['ai_product_engineering', 'customer_facing']), [
    'ai_product_engineering',
    'customer_facing',
  ]);
});

test('location parsing preserves spaces within names and supports comma-separated places', () => {
  assert.deepEqual(parseLocationDraft('United States'), ['United States']);
  assert.deepEqual(parseLocationDraft('United States, Dallas, Texas'), [
    'United States',
    'Dallas',
    'Texas',
  ]);
});
