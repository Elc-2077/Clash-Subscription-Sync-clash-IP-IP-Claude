# Contributing

Use synthetic proxy nodes and reserved example domains in tests. Never commit
real subscription URLs, node credentials, user-specific paths, logs or IP reports.

Install development dependencies:

```sh
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

Windows-specific scripts require Windows PowerShell 5.1 or later. A passing unit
test suite does not replace a real TUN and exit-connectivity test on Windows.
Describe the environment and validation performed in pull requests without
including personal connection information.

An optional GitHub Actions example is provided in `ci/checks.yml.example`.
Maintainers may enable it by copying it to `.github/workflows/checks.yml`
using an account or token with workflow-write permission. The initial source
publication includes the test suite and template without enabling a workflow.

By contributing, you agree that your original contributions are licensed under
the project's MIT license. Third-party code must retain compatible attribution.
