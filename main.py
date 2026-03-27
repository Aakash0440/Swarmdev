"""
SwarmDev — Main entry point.

Usage:
  python main.py "Build a Real-Time Distributed Collaborative Code Editor"
  python main.py --demo react
  python main.py --demo fullstack --provider dual
  python main.py --demo ml --provider groq
  python main.py --demo fullstack --provider gemini

Provider modes:
  dual    -> Groq (speed) + Gemini (context) with automatic failover [DEFAULT]
  groq    -> Groq only  (needs GROQ_API_KEY)
  gemini  -> Gemini only (needs GOOGLE_API_KEY)
  openai  -> OpenAI only (needs OPENAI_API_KEY)
  ollama  -> Local Ollama (no key needed)

Keys can be set in .env or as environment variables.
"""
import argparse
import asyncio
import os
import sys

# ── Windows UTF-8 fix ─────────────────────────────────────────────────────────
# Prevents UnicodeEncodeError when printing emoji/unicode on Windows terminals.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from swarm import SwarmConfig, SwarmExecutor

DEMOS = {
    "react": {
        "description": (
            "Build a full React cat food e-commerce store with product listing, "
            "shopping cart, product detail pages, and a checkout form. "
            "Use Tailwind CSS for styling and React Router for navigation."
        ),
        "name": "cat_food_store",
    },
    "fullstack": {
        "description": (
            "Build a full-stack task management app with a React frontend and FastAPI backend. "
            "Features: user authentication with JWT, CRUD tasks with priorities, "
            "real-time updates, SQLite database with SQLAlchemy."
        ),
        "name": "task_manager",
    },
    "ml": {
        "description": (
            "Build a sentiment analysis ML system: custom PyTorch LSTM model, "
            "data preprocessing pipeline, training script with MLflow tracking, "
            "FastAPI serving endpoint, and evaluation metrics."
        ),
        "name": "sentiment_analyzer",
    },
    "python": {
        "description": (
            "Build a Python CLI tool for scraping and summarising Hacker News stories. "
            "Features: fetch top stories, summarise with OpenAI, save to SQLite, "
            "export to CSV/JSON, rich terminal output."
        ),
        "name": "hn_summariser",
    },
    "collab_editor": {
        "description": (
            "Build a Real-Time Distributed Collaborative Code Editor. "
            "Features: WebSocket-based real-time sync, Operational Transformation (OT) "
            "for conflict-free concurrent edits, Monaco Editor frontend (React), "
            "FastAPI backend with Redis pub/sub for message brokering, "
            "JWT authentication, room/session management, syntax highlighting, "
            "cursor presence indicators, and Docker deployment."
        ),
        "name": "collab_editor",
    },
}

PROVIDER_DEFAULTS = {
    "groq":   "llama-3.3-70b-versatile",
    "gemini": "gemini-2.0-flash",
    "openai": "gpt-4o",
    "ollama": "llama3",
    "dual":   "llama-3.3-70b-versatile",
}


async def main():
    parser = argparse.ArgumentParser(
        description="SwarmDev v3 — 1000-agent parallel code generation (Groq + Gemini)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py "Build a real-time collaborative code editor"
  python main.py --demo collab_editor
  python main.py --demo fullstack --provider dual
  python main.py --demo ml --provider groq --agents 500
  python main.py --demo react --provider gemini

Keys (set in .env or environment):
  GROQ_API_KEY    — get free at https://console.groq.com
  GOOGLE_API_KEY  — get free at https://aistudio.google.com/app/apikey
        """
    )
    parser.add_argument("description", nargs="?", help="Project description")
    parser.add_argument("--demo",     choices=list(DEMOS.keys()), help="Use a preset demo")
    parser.add_argument("--name",     default=None,               help="Project name (slug)")
    parser.add_argument("--provider", default="dual",
                        choices=["dual", "groq", "gemini", "openai", "ollama"],
                        help="LLM provider. 'dual' uses Groq+Gemini together (default)")
    parser.add_argument("--groq-model",   default="llama-3.3-70b-versatile")
    parser.add_argument("--gemini-model", default="gemini-2.0-flash")
    parser.add_argument("--model",    default=None,               help="Model override (single-provider)")
    parser.add_argument("--agents",   type=int, default=1000,     help="Total agents in pool")
    parser.add_argument("--output",   default="./output",         help="Output directory")
    parser.add_argument("--no-verify", action="store_true",       help="Skip verification")
    parser.add_argument("--no-chroma", action="store_true",       help="Disable ChromaDB")
    args = parser.parse_args()

    if args.demo:
        preset = DEMOS[args.demo]
        description  = preset["description"]
        project_name = args.name or preset["name"]
        print(f"\n🎯  Demo preset : {args.demo}")
        print(f"📝  Description : {description[:90]}...\n")
    elif args.description:
        description  = args.description
        project_name = args.name
    else:
        parser.print_help()
        print("\n❌  Provide a description or --demo flag.")
        sys.exit(1)

    groq_key   = os.getenv("GROQ_API_KEY")
    gemini_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    provider   = args.provider

    if provider == "dual":
        if not groq_key and not gemini_key:
            print("❌  Dual mode needs at least one key:")
            print("    GROQ_API_KEY   -> https://console.groq.com  (free)")
            print("    GOOGLE_API_KEY -> https://aistudio.google.com/app/apikey  (free)")
            sys.exit(1)
        if not groq_key:
            print("⚠️   GROQ_API_KEY missing — running Gemini-only")
        if not gemini_key:
            print("⚠️   GOOGLE_API_KEY missing — running Groq-only")
    elif provider == "groq" and not groq_key:
        print("❌  GROQ_API_KEY not set. https://console.groq.com")
        sys.exit(1)
    elif provider == "gemini" and not gemini_key:
        print("❌  GOOGLE_API_KEY not set. https://aistudio.google.com/app/apikey")
        sys.exit(1)
    elif provider == "openai" and not os.getenv("OPENAI_API_KEY"):
        print("❌  OPENAI_API_KEY not set.")
        sys.exit(1)

    if provider == "dual":
        active = []
        if groq_key:   active.append(f"Groq ({args.groq_model})")
        if gemini_key: active.append(f"Gemini ({args.gemini_model})")
        print(f"🔀  Dual-provider: {' + '.join(active)}")
        print("    Groq   -> code generation (fast)")
        print("    Gemini -> architecture / docs (long context)\n")

    cfg = SwarmConfig(
        llm_provider=provider,
        model_name=args.model or PROVIDER_DEFAULTS.get(provider, "llama-3.3-70b-versatile"),
        api_key=(
            os.getenv("OPENAI_API_KEY") if provider == "openai" else
            groq_key if provider == "groq" else
            gemini_key if provider == "gemini" else None
        ),
        groq_api_key=groq_key,
        gemini_api_key=gemini_key,
        groq_model=args.groq_model,
        gemini_model=args.gemini_model,
        total_agents=args.agents,
        output_dir=args.output,
        verification_enabled=not args.no_verify,
        use_chroma=not args.no_chroma,
    )

    executor = SwarmExecutor(cfg)
    result   = await executor.run(description, project_name)

    print(f"\n✅  Done! Project at : {result['output_dir']}")
    print(f"   Files generated  : {result['files_created']}")

    if hasattr(executor.llm, "stats"):
        print(f"\n📊  Provider stats:")
        for name, s in executor.llm.stats().items():
            print(f"   {name:8s} -> {s['ok']} ok / {s['failed']} failed / {s['tokens']:,} tokens")

    if result["file_list"]:
        print("\n📂  Generated files:")
        for f in result["file_list"][:20]:
            print(f"   {f}")
        if len(result["file_list"]) > 20:
            print(f"   ... and {len(result['file_list']) - 20} more")


if __name__ == "__main__":
    asyncio.run(main())
