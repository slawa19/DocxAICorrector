## Summary

- What changed?
- Why was it needed?

## Verification

- [ ] `bash scripts/test.sh tests/test_script_workflow_smoke.py -q`
- [ ] `bash scripts/test.sh tests/test_startup_performance_contract.py -q` when startup-sensitive files changed
- [ ] `bash scripts/test.sh tests/ -q`
- [ ] Manual smoke-test completed when relevant

## Contract Checks

- [ ] Test workflow contract files were updated together when relevant: `scripts/test.sh`, `.vscode/tasks.json`, `tests/test_script_workflow_smoke.py`, docs, CI
- [ ] Startup performance contract files were updated together when relevant: `app.py`, `config.py`, `generation.py`, `.streamlit/config.toml`, docs, startup tests
- [ ] Final test verification was performed through a visible user-facing path in VS Code or foreground WSL terminal

## Notes

- Risks, follow-up work, or rollout notes