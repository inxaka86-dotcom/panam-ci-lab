'use strict';

const DEFAULT_MAX_INPUT_BYTES = 2 * 1024 * 1024;

function nonempty(value) {
  return typeof value === 'string' && value.trim().length > 0;
}

function safeErrorMessage(error) {
  return String(error && error.message ? error.message : error || 'runtime error')
    .replace(/(Bearer\s+)[^\s]+/gi, '$1[REDACTED]')
    .replace(/\b(api[_-]?key|token|secret)=([^\s&]+)/gi, '$1=[REDACTED]')
    .replace(/[\r\n]+/g, ' ')
    .trim()
    .slice(0, 500) || 'runtime error';
}

function validateEnvelope(command) {
  if (!command || typeof command !== 'object' || Array.isArray(command)) throw new Error('runtime command must be object');
  if (command.schema_version !== 1) throw new Error('unsupported runtime command schema');
  if (!['generate', 'store'].includes(command.operation)) throw new Error('unsupported runtime operation');
  if (!command.payload || typeof command.payload !== 'object' || Array.isArray(command.payload)) throw new Error('runtime payload must be object');
  return command;
}

async function handleRuntimeCommand(command, { generator, writer }) {
  validateEnvelope(command);
  if (command.operation === 'generate') {
    if (typeof generator !== 'function') throw new Error('generator unavailable');
    const { prompt, model, generation_operation } = command.payload;
    if (!nonempty(prompt) || !nonempty(generation_operation)) throw new Error('generate payload incomplete');
    const result = await generator(prompt, model || null, generation_operation);
    if (!result || typeof result !== 'object' || !nonempty(result.text)) throw new Error('generator result invalid');
    return { schema_version: 1, ok: true, operation: 'generate', result };
  }
  if (typeof writer !== 'function') throw new Error('writer unavailable');
  const { request, text } = command.payload;
  if (!request || typeof request !== 'object' || Array.isArray(request) || !nonempty(text)) throw new Error('store payload incomplete');
  const result = await writer(request, text);
  if (!result || typeof result !== 'object' || Array.isArray(result)) throw new Error('writer result invalid');
  return { schema_version: 1, ok: true, operation: 'store', result };
}

async function readBoundedJson(input, maxBytes = DEFAULT_MAX_INPUT_BYTES) {
  const chunks = [];
  let total = 0;
  for await (const chunk of input) {
    const buffer = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk);
    total += buffer.length;
    if (total > maxBytes) throw new Error('runtime command exceeds input size limit');
    chunks.push(buffer);
  }
  const raw = Buffer.concat(chunks).toString('utf8').trim();
  if (!raw) throw new Error('runtime command empty');
  const lines = raw.split(/\r?\n/).filter(line => line.trim());
  if (lines.length !== 1) throw new Error('runtime worker accepts exactly one JSON command');
  try {
    return JSON.parse(lines[0]);
  } catch {
    throw new Error('runtime command invalid JSON');
  }
}

async function runJsonWorkerOnce({ input, output, generator, writer, maxInputBytes = DEFAULT_MAX_INPUT_BYTES }) {
  let response;
  try {
    const command = await readBoundedJson(input, maxInputBytes);
    response = await handleRuntimeCommand(command, { generator, writer });
  } catch (error) {
    response = { schema_version: 1, ok: false, error: { code: 'RUNTIME_ERROR', message: safeErrorMessage(error) } };
  }
  output.write(`${JSON.stringify(response)}\n`);
  return response.ok ? 0 : 1;
}

module.exports = { DEFAULT_MAX_INPUT_BYTES, handleRuntimeCommand, readBoundedJson, runJsonWorkerOnce, safeErrorMessage, validateEnvelope };
