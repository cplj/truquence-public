# Contributing to Truquence

Open an issue with a small synthetic reproduction, or discuss a proposed change
before starting a large patch. Keep real customer data, credentials and private
logs out of issues and pull requests. Use [SECURITY.md](SECURITY.md) for vulnerabilities.

Install from the repository root:

```sh
python -m pip install .
```

Run the tests:

```sh
python -m unittest discover -s tests/product -v
python -m unittest discover -s tests/actioncontract -v
```

## Test policy

New behavior must come with tests that cover it, and bug fixes must come with a
test that fails before the fix. CI runs the same command on every pull request.
Describe limitations and keep unfavorable comparison results.

## Coding style

Keep the standard library as the only runtime dependency unless a change says why.
Follow the style of the surrounding code. CodeQL runs on the main branch; fix its
findings or explain why one does not apply.

## Developer Certificate of Origin

Every commit must include a `Signed-off-by` trailer under the
[Developer Certificate of Origin 1.1](https://developercertificate.org/).
Use `git commit -s` to certify that you have the right to submit the contribution
under this project's Apache-2.0 license. Commit metadata and sign-offs are public.
