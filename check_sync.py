"""Checks that the defaults in recipes.py and svgfx.js agree. Run: python check_sync.py (needs Node)."""
import json, subprocess, sys, os
here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, here)
import recipes
js = subprocess.run(["node", "-e", "const fs=require('fs');eval(fs.readFileSync('svgfx.js','utf8')+';console.log(JSON.stringify({d:DEFAULT_RECIPES,f:FACE}))')"],
                    cwd=here, capture_output=True, text=True, check=True).stdout
data = json.loads(js)
ok = True
for theme, py in recipes.DEFAULT_RECIPES.items():
    if data["d"].get(theme) != py:
        ok = False
        for k in sorted(set(py) | set(data["d"].get(theme, {}))):
            if py.get(k) != data["d"].get(theme, {}).get(k):
                print(f"MISMATCH {theme}.{k}: python={py.get(k)!r} js={data['d'].get(theme, {}).get(k)!r}")
if data["f"] != recipes.FACE:
    ok = False; print("MISMATCH FACE", recipes.FACE, data["f"])
print("recipes.py and svgfx.js agree" if ok else "OUT OF SYNC")
sys.exit(0 if ok else 1)
