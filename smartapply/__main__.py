"""Allow launching Élan with ``python -m smartapply``."""

from smartapply.desktop.app import main

if __name__ == "__main__":
    raise SystemExit(main())
