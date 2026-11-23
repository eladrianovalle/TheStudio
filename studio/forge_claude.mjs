// Claude Code's print-mode wire protocol. Only the terminal result carries the
// validated handoff. Tool input, text, account metadata and stderr stay private.
import { spawn } from 'node:child_process';
import { randomUUID } from 'node:crypto';
import { createInterface } from 'node:readline';

const providerErrors = new Set([
  'authentication_failed', 'oauth_org_not_allowed', 'account_on_hold', 'billing_error',
  'rate_limit', 'overloaded', 'invalid_request', 'model_not_found', 'server_error',
  'cloud_credential_error', 'max_output_tokens',
]);

function modelId(value) {
  return typeof value === 'string' && /^[A-Za-z0-9][A-Za-z0-9._:/[\]-]{0,255}$/.test(value);
}

export async function runClaude({ cwd, prompt, schema, model, execution, commands = [] }) {
  const sessionId = randomUUID();
  const requestId = randomUUID();
  Object.assign(execution, {
    actual_runtime: null, session_id: null, completed: false,
    observed_models: [], reroutes: [], confirmed_aliases: [], refused_commands: 0,
  });
  const args = [
    '--print', '--verbose', '--no-session-persistence', '--session-id', sessionId,
    '--input-format', 'stream-json', '--output-format', 'stream-json',
    '--json-schema', JSON.stringify(schema), '--permission-mode', 'acceptEdits',
    '--strict-mcp-config', '--disable-slash-commands',
    '--tools', 'Read,Edit,Write,Grep,Glob,Bash,StructuredOutput',
    '--allowedTools', 'Bash(git hash-object -- *)',
    ...commands.map(command => `Bash(${command})`),
  ];
  if (model) args.push('--model', model);
  const child = spawn('claude', args, { cwd, stdio: ['pipe', 'pipe', 'ignore'] });
  let launchError;
  child.once('error', error => { launchError = error.code; });
  child.once('spawn', () => { execution.actual_runtime = 'claude'; });
  const closed = new Promise(resolve => child.once('close', resolve));
  // A failed startup can close stdin while the prompt is in flight. The exit
  // status and the terminal result below cover this case without leaking input.
  child.stdin.on('error', () => {});
  const initialize = { type: 'control_request', request_id: requestId, request: { subtype: 'initialize' } };
  const turn = { type: 'user', session_id: sessionId, parent_tool_use_id: null,
    message: { role: 'user', content: prompt } };
  child.stdin.end(JSON.stringify(initialize) + '\n' + JSON.stringify(turn) + '\n');

  const models = new Set();
  let terminal, previousModel, failure, assistantError;
  function reroute(from, to) {
    if (modelId(from) && modelId(to) && from !== to &&
        !execution.reroutes.some(route => route.from === from && route.to === to)) {
      execution.reroutes.push({ from, to });
    }
  }

  try {
    for await (const line of createInterface({ input: child.stdout, crlfDelay: Infinity })) {
      if (!line.trim()) continue;
      const event = JSON.parse(line);
      // Only the reply to this process's initialize request can resolve its pin.
      if (event.type === 'control_response') {
        const reply = event.response;
        if (model && reply?.subtype === 'success' && reply.request_id === requestId) {
          const entries = reply.response?.models;
          const matches = Array.isArray(entries) ? entries.filter(entry => entry?.value === model) : [];
          if (matches.length === 1 && modelId(matches[0].resolvedModel)) {
            execution.confirmed_aliases = [{ alias: model, model: matches[0].resolvedModel }];
          }
        }
        continue;
      }
      if (event.session_id !== sessionId || event.parent_tool_use_id != null || event.agent_id) continue;
      execution.session_id = sessionId;
      if (event.type === 'result') {
        if (terminal) failure = 'Claude returned multiple role results';
        terminal = event;
      } else if (!terminal && event.type === 'assistant' && event.parent_tool_use_id === null) {
        if (event.error) {
          assistantError = providerErrors.has(event.error) ? event.error : 'provider error';
        } else if (!event.aborted && event.message?.role === 'assistant' && modelId(event.message.model)) {
          const current = event.message.model;
          reroute(previousModel, current);
          previousModel = current;
          models.add(current);
        }
      } else if (!terminal && event.type === 'system') {
        if (event.subtype === 'model_refusal_fallback') reroute(event.original_model, event.fallback_model);
      }
    }
  } catch {
    failure = 'Invalid Claude event stream';
    child.kill();
  }
  const code = await closed;
  if (launchError) throw new Error('Claude executable unavailable');
  if (Array.isArray(terminal?.permission_denials)) execution.refused_commands = terminal.permission_denials.length;
  if (failure) throw new Error(failure);
  if (assistantError && (code !== 0 || terminal?.is_error)) throw new Error('Claude: ' + assistantError);
  if (code !== 0) throw new Error('Claude process exited without success');
  if (!terminal || terminal.subtype !== 'success' || terminal.is_error !== false) {
    throw new Error('Claude role result missing or unsuccessful');
  }
  const output = terminal.structured_output;
  if (!output || !output.handoff || typeof output.handoff !== 'object' ||
      Array.isArray(output.handoff) || !Array.isArray(output.changes)) {
    throw new Error('Claude returned an unusable structured handoff');
  }
  execution.observed_models = [...models];
  execution.completed = true;
  return { handoff: output.handoff, changes: output.changes };
}
