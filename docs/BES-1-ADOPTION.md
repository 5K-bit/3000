# BES-1 adoption: 3000

**State:** Proposed, documentation-only adoption. **Not a certification** of any release or live runtime.  
**Ownership boundary:** OBEOS integration candidate.  
**Project role:** Python component with OBEOS manifest.  
**Canonical policy:** [Blackfong Engineering Standard BES-1](https://github.com/5K-bit/O.B.E.O.S/blob/main/docs/standards/BES-1.md).

## Baseline reviewed

The inspected default branch contains GitHub workflow file(s): `ci.yml`. This confirms the files exist, **not** that their latest runs passed or that a deployed application works. Existing workflow and release behavior remain authoritative.

## Evidence gates for this project

- **Built:** record changed code/interfaces, exact commit, risk and recovery notes.
- **Verified:** link the relevant existing CI run and exact commands, results and skipped tests at that commit. Explicitly separate mocks from actual dependencies.
- **Released:** identify a tested installable artifact or deployed revision, supported environment, version, release notes, and rollback path.
- **Operational:** obtain dated acceptance evidence from the actual target environment; capture failure and recovery behavior before claiming readiness.

### Project-specific acceptance

Deterministic Python tests, public interface/manifest contract checks, safe failure, integration in the actual parent OBEOS environment.

**Critical boundary:** An OBEOS submodule pin is not runtime integration acceptance.

## Next adoption actions

1. Inventory actual CI jobs and link their current result; retain existing checks.
2. Capture one repeatable acceptance scenario and one failure/recovery scenario appropriate to this project.
3. Add reproducible optional task aliases only after their underlying commands are inspected, then test aliases on the supported operating systems.
4. Evaluate scanners, dependency automation and observability separately: no new runtime dependency or production permission is authorized by this document.

**AI assistance:** scope must be declared in substantive PRs.  
**Human verification:** record what an operator actually ran and observed; mark unrun hardware, browser or deploy tests **not verified**.
