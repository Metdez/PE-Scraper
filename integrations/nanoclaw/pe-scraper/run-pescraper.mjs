import { readFile } from 'node:fs/promises';

const tokenPath = '/workspace/agent/.pe-scraper-bridge-token';
const token = (await readFile(tokenPath, 'utf8')).trim();
const response = await fetch('http://host.docker.internal:8765/run', {
  method: 'POST',
  headers: {
    'content-type': 'application/json',
    'x-pe-scraper-token': token,
  },
  body: JSON.stringify({ args: process.argv.slice(2) }),
});

const result = await response.json();
if (result.stdout) process.stdout.write(result.stdout);
if (result.stderr) process.stderr.write(result.stderr);

if (!response.ok) {
  if (result.error) process.stderr.write(`${result.error}\n`);
  process.exit(1);
}

process.exit(Number.isInteger(result.returncode) ? result.returncode : 1);
