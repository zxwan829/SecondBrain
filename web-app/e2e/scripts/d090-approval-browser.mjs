import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { createServer } from 'node:http';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createInterface } from 'node:readline';
import { once } from 'node:events';
import { fileURLToPath } from 'node:url';
import { chromium } from '@playwright/test';

const root = await mkdtemp(join(tmpdir(), 'd090-browser-'));
const helper = fileURLToPath(new URL('../../secondbrain-core/tests/d090_http_probe.py', import.meta.url));
const coreRoot = fileURLToPath(new URL('../../secondbrain-core/', import.meta.url));
const authority = spawn(process.env.PYTHON_BIN || 'python3', [helper, root, 'localhost'], {
  env: { ...process.env, PYTHONPATH: coreRoot }, stdio: ['ignore', 'pipe', 'inherit'],
});
const lines = createInterface({ input: authority.stdout });
const coreCookies = [];
const core = createServer((request, response) => {
  coreCookies.push(request.headers.cookie || '');
  response.setHeader('Content-Type', 'text/html');
  response.end('<title>Core fixture</title>');
});
let browser;
try {
  const port = await Promise.race([
    once(lines, 'line').then(([line]) => Number(line)),
    once(authority, 'exit').then(() => { throw new Error('Authority exited before readiness'); }),
  ]);
  core.listen(0, '127.0.0.1');
  await once(core, 'listening');
  const coreOrigin = `http://127.0.0.1:${core.address().port}`;
  const authorityOrigin = `http://localhost:${port}`;
  browser = await chromium.launch(process.env.D090_EDGE ? { channel: 'msedge' } : {});
  const context = await browser.newContext();
  const approval = await context.newPage();
  const entry = await approval.goto(authorityOrigin);
  assert.equal(entry.headers()['content-security-policy'], "frame-ancestors 'none'");
  const login = await approval.evaluate(password => fetch('/login', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ password }),
  }).then(response => response.status), await readFile(join(root, 'password'), 'utf8'));
  assert.equal(login, 200);
  const cookies = await context.cookies(authorityOrigin);
  assert.equal(cookies.length, 1);
  assert.equal(cookies[0].domain, 'localhost');
  assert.equal(cookies[0].httpOnly, true);
  const corePage = await context.newPage();
  await corePage.goto(coreOrigin);
  assert.ok(coreCookies.length > 0);
  assert.ok(coreCookies.every(cookie => cookie === ''));
  assert.deepEqual(await context.cookies(coreOrigin), []);
  assert.equal(await corePage.evaluate(url => fetch(url + '/preview', {
    method: 'POST', credentials: 'include',
  }).then(() => false, () => true), authorityOrigin), true);
  assert.equal(await approval.evaluate(() => document.cookie), '');
  const denial = await corePage.evaluate(url => new Promise(resolve => {
    const iframe = document.createElement('iframe');
    iframe.onload = () => {
      try { void iframe.contentWindow.document; resolve(false); }
      catch (error) { resolve(error.name === 'SecurityError'); }
    };
    iframe.src = url;
    document.body.append(iframe);
  }), authorityOrigin);
  assert.equal(denial, true);
  assert.equal(await approval.evaluate(async () => {
    const preview = await fetch('/preview', { method: 'POST' }).then(response => response.json());
    const confirmation = await fetch('/confirm', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ intent: 'promote_exact_preview', binding: preview.binding }),
    });
    return (await confirmation.json()).status;
  }), 'issued');
  assert.ok(coreCookies.every(cookie => cookie === ''));
  console.log('Chromium verified host-only approval cookie and cross-origin DOM isolation');
} finally {
  await browser?.close();
  core.close();
  if (authority.exitCode === null) {
    authority.kill();
    await once(authority, 'exit');
  }
  await rm(root, { recursive: true, force: true });
}
