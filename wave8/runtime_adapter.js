'use strict';

const crypto = require('crypto');

const DOCUMENT_TYPE = 'meeting_record';
const STORAGE_PROVIDER = 'synthetic_store';
const GENERATION_OPERATION = 'synthetic_protocol_generation';

function nonempty(value) {
  return typeof value === 'string' && value.trim().length > 0;
}

function sha256Text(text) {
  return crypto.createHash('sha256').update(text, 'utf8').digest('hex');
}

function validateRequest(request, text) {
  if (!request || typeof request !== 'object' || Array.isArray(request)) {
    throw new TypeError('request must be an object');
  }
  for (const field of ['event_id', 'document_type', 'storage_provider', 'draft_id', 'artifact_id', 'text_sha256']) {
    if (!nonempty(request[field])) throw new Error(`request missing ${field}`);
  }
  if (request.document_type !== DOCUMENT_TYPE) throw new Error('unsupported document_type');
  if (request.storage_provider !== STORAGE_PROVIDER) throw new Error('unsupported storage_provider');
  if (!/^[a-f0-9]{64}$/i.test(request.text_sha256)) throw new Error('text_sha256 must be SHA-256 hex');
  if (!nonempty(request.source_id) && !nonempty(request.correlation_id)) {
    throw new Error('request requires source_id or correlation_id');
  }
  if (typeof text !== 'string' || !text.trim()) throw new Error('text must be non-empty');
  if (sha256Text(text).toLowerCase() !== request.text_sha256.toLowerCase()) {
    throw new Error('text_sha256 does not match text');
  }
  return request;
}

function identity(request) {
  return {
    kind: 'synthetic_draft',
    event_id: request.event_id,
    draft_id: request.draft_id,
    artifact_id: request.artifact_id,
    text_sha256: request.text_sha256.toLowerCase(),
    source_id: request.source_id || null,
    correlation_id: request.correlation_id || null,
  };
}

function assertIdentity(record, request) {
  const expected = identity(request);
  const actual = record && record.identity;
  if (!actual || typeof actual !== 'object') throw new Error('existing record missing identity');
  const conflicts = Object.keys(expected).filter(key => actual[key] !== expected[key]);
  if (conflicts.length) throw new Error(`existing record identity conflict: ${conflicts.join(', ')}`);
}

function receipt(request, record) {
  if (!record || !nonempty(record.id)) throw new Error('record missing id');
  if (!nonempty(String(record.revision || ''))) throw new Error('record missing revision');
  assertIdentity(record, request);
  return {
    event_id: request.event_id,
    save_status: 'STORED',
    document_type: DOCUMENT_TYPE,
    storage_provider: STORAGE_PROVIDER,
    draft_id: request.draft_id,
    artifact_id: request.artifact_id,
    store_id: record.id,
    storage_revision: String(record.revision),
    source_id: request.source_id || null,
    correlation_id: request.correlation_id || null,
    text_sha256: request.text_sha256.toLowerCase(),
    display_name: record.name || null,
    stored_at: record.stored_at || null,
  };
}

function createGenerationAdapter({ chat }) {
  if (typeof chat !== 'function') throw new TypeError('generation adapter requires chat callable');
  return async function generate(prompt, model, operation = GENERATION_OPERATION) {
    if (!nonempty(prompt)) throw new Error('prompt is required');
    if (operation !== GENERATION_OPERATION) throw new Error('unexpected generation operation');
    const result = await chat(prompt, model, operation);
    if (typeof result === 'string') {
      if (!result.trim()) throw new Error('generator returned empty text');
      return { text: result, model: model || null, provider: null };
    }
    if (!result || typeof result !== 'object' || !nonempty(result.text)) {
      throw new Error('generator returned invalid result');
    }
    return {
      text: String(result.text),
      model: result.model || model || null,
      provider: result.provider ?? null,
    };
  };
}

function createIdempotentArtifactWriter({ store }) {
  if (!store || typeof store.findByEventId !== 'function' || typeof store.create !== 'function') {
    throw new TypeError('artifact writer requires findByEventId/create store');
  }
  return async function write(request, text) {
    validateRequest(request, text);
    const matches = await store.findByEventId(request.event_id);
    if (!Array.isArray(matches)) throw new Error('store lookup must return array');
    if (matches.length > 1) throw new Error('multiple artifacts found for one event_id');
    if (matches.length === 1) return receipt(request, matches[0]);
    const created = await store.create({
      name: request.display_name || 'synthetic-record.txt',
      identity: identity(request),
      text,
    });
    return receipt(request, created);
  };
}

module.exports = {
  DOCUMENT_TYPE,
  STORAGE_PROVIDER,
  GENERATION_OPERATION,
  createGenerationAdapter,
  createIdempotentArtifactWriter,
  sha256Text,
  validateRequest,
};
