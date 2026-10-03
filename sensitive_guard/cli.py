"""CLI: scan a string or file, serve the HTTP API, or run the company network gate."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .layer import SensitiveDataLayer
from .laya_backend import laya_available


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "serve":
        return _serve(argv[1:])
    if argv and argv[0] == "net":
        return _net(argv[1:])
    return _scan(argv)


def _scan(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="sensitive-guard",
        description="Detect and categorize sensitive data with Laya (or a heuristic fallback).",
    )
    parser.add_argument("text", nargs="?", help="Text to scan. Omit when using --file or stdin.")
    parser.add_argument("-f", "--file", type=Path, help="Read text from a file.")
    parser.add_argument("--backend", choices=("auto", "laya", "heuristic"), default="auto")
    parser.add_argument("--region", default="PL")
    parser.add_argument("--locale", default="pl", choices=("pl", "en"))
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--strict", action="store_true", help="Redact even low-risk spans.")
    parser.add_argument("--policy", action="store_true", help="Also run Laya document-level policy.")
    parser.add_argument("--json", action="store_true", help="Print the full ScanResult as JSON.")
    parser.add_argument("--protect", action="store_true", help="Apply the gate and print outbound text.")
    parser.add_argument("--device", default=None, help="cpu, cuda or mps")
    args = parser.parse_args(argv)

    text = _read_text(args)
    if text is None:
        parser.print_help()
        print("\nHTTP: python -m sensitive_guard serve --port 8080", file=sys.stderr)
        print("Sieć / agenci: python -m sensitive_guard net --proxy-port 8888", file=sys.stderr)
        return 2

    layer = SensitiveDataLayer(
        backend=args.backend,
        device=args.device,
        region=args.region,
        locale=args.locale,
        threshold=args.threshold,
        strict=args.strict,
        use_policy=args.policy,
    )
    if args.protect:
        result = layer.protect(text)
        if args.json:
            print(result.model_dump_json(indent=2))
            return 0
        print(f"action={result.action.value} risk={result.scan.risk.value} backend={result.scan.backend}")
        if result.outbound is None:
            print(result.blocked_reason or "blocked")
            return 1
        print(result.outbound)
        return 0

    scan = layer.scan(text)
    if args.json:
        print(scan.model_dump_json(indent=2))
        return 0
    _print_scan(scan)
    return 0


def _read_text(args: argparse.Namespace) -> str | None:
    if args.file:
        return args.file.read_text(encoding="utf-8")
    if args.text:
        return args.text
    if not sys.stdin.isatty():
        return sys.stdin.read()
    return None


def _print_scan(scan) -> None:
    print(
        f"backend={scan.backend}  document={scan.document_type}  "
        f"risk={scan.risk.value}  action={scan.action.value}  candidates={scan.candidates}"
    )
    if not scan.entities:
        print("no sensitive spans")
        return
    print()
    print(f"{'span':<32} {'label':<22} {'category':<16} {'risk':<10} score")
    print("-" * 92)
    for entity in scan.entities:
        snippet = entity.text.replace("\n", " ")
        if len(snippet) > 30:
            snippet = snippet[:27] + "..."
        print(
            f"{snippet:<32} {entity.label:<22} {entity.category.value:<16} "
            f"{entity.risk.value:<10} {entity.score:.3f}"
        )
    print()
    print("categories:")
    for summary in scan.categories:
        print(
            f"  - {summary.category.value}: {summary.count}  "
            f"max_risk={summary.max_risk.value}  {', '.join(summary.labels)}"
        )
    print()
    print("redacted:")
    print(scan.redacted)


def _serve(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="sensitive-guard serve")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--backend", choices=("auto", "laya", "heuristic"), default="auto")
    parser.add_argument("--policy", action="store_true")
    parser.add_argument("--device", default=None)
    args = parser.parse_args(argv)
    try:
        import uvicorn
    except ImportError:
        print("Install the server extra: pip install fastapi uvicorn", file=sys.stderr)
        return 2
    from .serve import create_app

    app = create_app(backend=args.backend, use_policy=args.policy, device=args.device)
    print(
        f"sensitive-guard listening on http://{args.host}:{args.port}  "
        f"laya={laya_available()}  backend={args.backend}"
    )
    uvicorn.run(app, host=args.host, port=args.port)
    return 0


def _net(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="sensitive-guard net",
        description="Bramka dla agentów AI + HTTP proxy firmowe.",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080, help="API + /net/{openai,anthropic,...}")
    parser.add_argument("--proxy-port", type=int, default=8888, help="HTTP_PROXY / HTTPS_PROXY")
    parser.add_argument("--no-proxy", action="store_true")
    parser.add_argument("--ai-hosts-only", action="store_true")
    parser.add_argument("--no-mitm", action="store_true", help="Nie deszyfruj HTTPS (tylko CONNECT).")
    parser.add_argument("--backend", choices=("auto", "laya", "heuristic"), default="heuristic")
    parser.add_argument("--policy", action="store_true")
    parser.add_argument("--device", default=None)
    args = parser.parse_args(argv)
    try:
        import uvicorn
    except ImportError:
        print("pip install fastapi uvicorn", file=sys.stderr)
        return 2
    from .fwdproxy import start_proxy
    from .gate import execute_gated_scan
    from .layer import SensitiveDataLayer
    from .netgate import inspect_and_maybe_redact
    from .serve import create_app

    app = create_app(backend=args.backend, use_policy=args.policy, device=args.device)
    if not args.no_proxy:
        ctx = app.state.gate_ctx
        store = app.state.store
        layer = SensitiveDataLayer(backend=args.backend, device=args.device, use_policy=args.policy)

        def proxy_scan(body):
            return execute_gated_scan(layer, store, body, ctx)

        start_proxy(
            args.host,
            args.proxy_port,
            lambda body, ctype, emp, host: inspect_and_maybe_redact(
                body, ctype, proxy_scan, emp, host, policy=ctx.policy.load(), store=store
            ),
            allow_all=not args.ai_hosts_only,
            mitm=not args.no_mitm,
        )
        app.state.proxy_port = args.proxy_port
        app.state.mitm = not args.no_mitm
        print(f"HTTP proxy   http://{args.host}:{args.proxy_port}  (HTTP_PROXY / HTTPS_PROXY)")
        if not args.no_mitm:
            from .tlsca import CA_CERT_PATH, ensure_ca

            ensure_ca()
            print(f"TLS MITM     ON  CA={CA_CERT_PATH}")
            print(f"  certutil -user -addstore Root \"{CA_CERT_PATH}\"")

    print(f"API+bramka   http://{args.host}:{args.port}/net/health")
    print(f"  OPENAI_BASE_URL=http://{args.host}:{args.port}/net/openai/v1")
    print(f"laya={laya_available()}  backend={args.backend}")
    uvicorn.run(app, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
