"""Direct script target keeps hooks independent of cwd and site initialization."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if len(sys.argv) == 3 and sys.argv[1] == '--worker':
    from truquence_recorder.worker import serve
    try:
        serve(sys.argv[2])
    except (ValueError, OSError, TypeError, KeyError, RecursionError):
        raise SystemExit(1)
else:
    from truquence_recorder.hook import main
    raise SystemExit(main())
