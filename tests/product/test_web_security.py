"""Exercise actual web client code without starting a browser."""
from pathlib import Path
import shutil
import subprocess
import unittest


class WebClientSecurityTests(unittest.TestCase):
    def test_allowlisted_routes_host_and_no_redirects(self):
        from truquence import server
        script = Path(server.__file__).parent / "web/app.js"
        node = shutil.which("node")
        self.assertIsNotNone(node, "Node is required for web client regressions")
        result = subprocess.run([node, "-e", r'''
const fs = require('fs'), vm = require('vm'), assert = require('assert');
const calls = [];
const element = {addEventListener(){}};
const context = {location: {origin:'http://127.0.0.1:8769'},
 document: {getElementById(){return element}, querySelectorAll(){return []}},
 fetch(path, options){calls.push([path, options]);return Promise.resolve({ok:true})}};
vm.createContext(context);
vm.runInContext(fs.readFileSync(process.argv[1], 'utf8'), context);
for(const path of ['/check','/sample/clean','/sample/dirty','/sample/unknown']) {
 context.localFetch(path, {redirect:'follow', mode:'cors', credentials:'include'});
 const [target, options] = calls.at(-1);
 assert.equal(target,path);assert.equal(options.redirect,'error');
 assert.equal(options.mode,'same-origin');assert.equal(options.credentials,'omit');
}
for(const path of ['http://169.254.169.254/latest/meta-data/',
 'http://127.0.0.1:80/check','http://10.0.0.1/check','http://[::1]/check',
 'https://public.example/check','//metadata.google.internal/check','/check?url=x',
 '/sample/../check','/sample/clean/','/sample/%2f%2fmetadata']) {
 assert.throws(()=>context.localFetch(path), /HTTP_TARGET_REJECTED/);
}
for(const origin of ['http://10.0.0.1:8769','http://169.254.169.254:8769',
 'http://metadata.google.internal:8769','https://public.example',
 'http://127.0.0.1:8769.attacker.invalid']) {
 context.location.origin = origin;
 assert.throws(()=>context.localFetch('/check'), /HTTP_TARGET_REJECTED/);
}
assert.equal(calls.length,4);
console.log('web target allowlist and redirect policy PASS');
''', str(script)], capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
