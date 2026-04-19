# Copilot Security Instructions for Memory Tree

## Purpose
This repository is a private production web app called Memory Tree.
All code generation, refactoring, and feature work must preserve and strengthen security, reliability, and Raspberry Pi Zero 2 W compatibility.

## Project context
- FastAPI + SQLAlchemy 2.0 + SQLite
- Jinja2 SSR + Tailwind CSS + Vanilla JS + D3.js + Leaflet.js
- JWT auth in HttpOnly cookies
- Raspberry Pi Zero 2 W deployment target
- Docker Compose deployment
- Private 2-user app
- Secure-by-default and low-resource operation are mandatory

## Always-on security rules
- Never hardcode secrets, tokens, API keys, passwords, or credentials.
- Never store JWTs in localStorage, sessionStorage, or JS-readable cookies.
- Keep auth cookie-based with HttpOnly, Secure, and SameSite flags.
- State-changing endpoints that rely on cookies must include CSRF protection.
- Never use wildcard CORS in production with credentials.
- Never weaken CSP, security headers, or cookie flags unless explicitly asked and after explaining the risk.
- Never render untrusted HTML with Jinja2 `|safe`.
- Sanitize rich text with an allowlist.
- Use SQLAlchemy ORM or parameterized queries only.
- Never build SQL using f-strings or string concatenation with user input.
- Validate all user input server-side.
- Validate uploads using content inspection / magic bytes, not extension alone.
- Never store uploads directly in `static/`.
- Never trust user-controlled filenames or paths.
- Do not log secrets, passwords, raw cookies, or JWTs.
- Keep the app compatible with Raspberry Pi Zero 2 W resource limits.
- Prefer low-memory, low-complexity solutions.

## Feature implementation guardrails
Before implementing a feature:
1. Identify affected security controls.
2. Note risks briefly.
3. Implement the safest practical version.
4. Prefer the option with the best tradeoff between security, simplicity, and low resource usage.

After implementing a feature:
1. Re-check auth flow.
2. Re-check CSRF implications.
3. Re-check XSS/template safety.
4. Re-check input validation.
5. Re-check SQL safety.
6. Re-check upload safety.
7. Re-check logs for sensitive data leakage.
8. Re-check CSP/security headers if frontend behavior changed.
9. Re-check resource impact on Pi Zero 2 W.

## Production constraints
- SQLite remains the default database.
- Use 1 app worker by default on Pi Zero 2 W.
- Avoid adding heavy services or background components.
- Prefer Caddy for reverse proxy if public HTTPS is used.
- Keep Docker images small and run containers as non-root.
- New features must not assume x86-only tooling or abundant RAM.

## Response behavior
If a requested implementation would compromise security, do not proceed silently.
Explain the risk and propose a safer alternative.