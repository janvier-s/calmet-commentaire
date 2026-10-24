"""Time each rule of clean_mechanical.fix_spelling on real pages.

  python3 profile_rules.py <volume|book> ... [--top N]

The rules are read from the source of fix_spelling (every `s = ...` step, with its `if`
guard), then run one after another over every French string of the pages, as fix_spelling
runs them, so each rule sees what the earlier ones made of the text. Prints the slowest
rules with their line in clean_mechanical.py, and the rules that still change the text
(on pages already cleaned there should be none: a hit means a rule undoes another, or the
pages were edited since). Checks that the steps give what fix_spelling gives. Changes no page.
"""
import ast
import signal
import sys
from pathlib import Path
from time import perf_counter

import clean_mechanical
from paths import load, pages
from spellcheck import french_texts, volumes_of


def steps():
    """(line, source, function s -> (new s, hits)) for each step of fix_spelling, in order."""
    src = Path(clean_mechanical.__file__).read_text(encoding="utf-8")
    fn = next(n for n in ast.parse(src).body
              if isinstance(n, ast.FunctionDef) and n.name == "fix_spelling")
    env = vars(clean_mechanical)
    out = []

    def step(node):
        call = node.value
        if isinstance(call, ast.Call) and ast.unparse(call.func) == "_sub":
            flags = next((eval(ast.unparse(k.value), env) for k in call.keywords if k.arg == "flags"), 0)
            rx, lit = clean_mechanical._rule(call.args[0].value, flags)
            repl = eval(ast.unparse(call.args[1]), env)
            return call.args[0].value, lambda s: (s, 0) if lit and lit not in s else rx.subn(repl, s)
        f = eval("lambda s: " + ast.unparse(call), env)    # any other step: hits = 1 if it changed s
        return ast.unparse(call), lambda s: (lambda t: (t, t != s))(f(s))

    def walk(body, guard):
        for node in body:
            if isinstance(node, ast.If) and node.lineno == fn.body[0].lineno:
                continue                                   # the `if not s: return s` at the top
            if isinstance(node, ast.If):
                test = eval("lambda s: " + ast.unparse(node.test), env)
                walk(node.body, test)
            elif isinstance(node, ast.Assign) and ast.unparse(node.targets[0]) == "s":
                label, f = step(node)
                if guard:
                    f = (lambda f, g: lambda s: f(s) if g(s) else (s, 0))(f, guard)
                out.append((node.lineno, label, f))
            elif not isinstance(node, ast.Return):
                sys.exit(f"profile_rules: line {node.lineno} of fix_spelling is not a rule: "
                         f"{ast.unparse(node)[:80]}")

    walk(fn.body, None)
    return out


def main(argv):
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)    # quiet when piped into head
    top = 20
    if "--top" in argv:
        i = argv.index("--top")
        top = int(argv[i + 1])
        del argv[i:i + 2]
    vols = volumes_of(argv)
    if not vols:
        sys.exit(__doc__)

    texts = [t for v in vols for p in pages(v) for t in french_texts(load(p))
             if t and isinstance(t, str)]
    print(f"{', '.join(vols)}: {len(texts)} strings, {sum(map(len, texts)):,} characters")

    rules = steps()
    t0 = perf_counter()
    expected = [clean_mechanical.fix_spelling(t) for t in texts]
    whole = perf_counter() - t0

    timings = []
    for line, label, f in rules:
        hits = 0
        t0 = perf_counter()
        for i, s in enumerate(texts):
            texts[i], n = f(s)
            hits += n
        timings.append((perf_counter() - t0, hits, line, label))
    total = sum(t for t, *_ in timings)

    off = sum(a != b for a, b in zip(texts, expected))
    if off:
        print(f"WARNING: the steps differ from fix_spelling on {off} strings; "
              "profile_rules.py misreads a rule")
    timings.sort(reverse=True)
    median = timings[len(timings) // 2][0]
    print(f"fix_spelling: {whole:.2f} s; {len(rules)} steps: {total:.2f} s "
          f"(median step {median * 1000:.1f} ms)\n")
    shown = timings[:top]
    print(f"Slowest {len(shown)} ({sum(t for t, *_ in shown) / total:.0%} of the time):")
    print("     ms  share  line  rule")
    for t, _, line, label in shown:
        print(f"{t * 1000:7.1f}  {t / total:5.1%}  {line:4}  {label[:90]}")

    fired = sorted((line, hits, label) for _, hits, line, label in timings if hits)
    print(f"\nRules that still change the text: {len(fired) or 'none'}")
    for line, hits, label in fired:
        print(f"  {hits:5} x  line {line:4}  {label[:90]}")


if __name__ == "__main__":
    main(sys.argv[1:])
