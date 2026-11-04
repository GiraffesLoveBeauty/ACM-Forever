"""Compile and exercise the bundled original C++ snippets, entirely locally."""
import ast
import json
from pathlib import Path
import shutil
import subprocess

root = Path(__file__).resolve().parents[1]
entries = json.loads((root / "app/app/src/main/assets/templates/catalog.json").read_text(encoding="utf-8"))
compiler = shutil.which("g++")
if not compiler:
    raise SystemExit("未找到本地 g++；不下载编译器。")
out = root / "app/app/build/policy-check"
out.mkdir(parents=True, exist_ok=True)
snippets = {item["title"]: item["code"] for item in entries}
for entry in entries:
    if entry["language"] == "python":
        ast.parse(entry["code"])
source = "#include <bits/stdc++.h>\n#include <cassert>\nusing namespace std;\n" + "\n".join(
    entry["code"] for entry in entries if entry["language"] == "cpp" and entry["title"] != "快速 IO"
)
source += """
int main() {
    DSU d(4); assert(d.unite(0,1)); assert(!d.unite(1,0)); assert(d.find(0)==d.find(1));
    vector<vector<pair<int,long long>>> g(4); g[0]={{1,4},{2,1}}; g[2]={{1,1}};
    auto dist=dijkstra(g,0); assert(dist[1]==2 && dist[3]==INF);
    vector<vector<int>> graph={{1,2},{3},{3},{},{}};
    auto levels=bfs(graph,0); assert(levels[3]==2 && levels[4]==-1);
    Fenwick f(5); f.add(1,2); f.add(3,4); assert(f.sum(3)==6 && f.sum(0)==0);
    assert(modpow(-2,3,5)==2 && modpow(99,0,1)==0);
    assert(first_true(0,10,[](int n){return n>=7;})==7);
    assert(first_true(0,10,[](int){return false;})==10);
    assert(first_true(5,5,[](int){return true;})==5);
    assert(first_true(INT_MIN,INT_MAX,[](int n){return n>=0;})==0);
}
"""
cpp, binary = out / "templates-check.cpp", out / "templates-check.exe"
cpp.write_text(source, encoding="utf-8")
subprocess.run([compiler, "-std=c++17", "-Wall", "-Wextra", cpp.name, "-o", binary.name], cwd=out, check=True)
subprocess.run([str(binary)], check=True)
fast = out / "template-io.cpp"
fast.write_text(snippets["快速 IO"], encoding="utf-8")
subprocess.run([compiler, "-std=c++17", "-fsyntax-only", fast.name], cwd=out, check=True)
print("PASS: 7 C++ templates compiled; DSU/Dijkstra/BFS/Fenwick/modpow/binary-search checks passed; Python syntax accepted")
