#!/usr/bin/env python3
"""Build and validate both distribution paths, using only stdlib orchestration.

By default downloads build tooling and ALL declared dependencies into private
venvs. Optional explicit reuse retains full dependencies, not old artifacts.
Never installs into the invoking interpreter. See docs/DISTRIBUTION_VALIDATION.md.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from email.parser import BytesParser
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import traceback
import zipfile

ASSETS = ("dashboard.css", "dashboard.js", "sessions.js", "shell.html")
MODULES = ("reference.py", "session.py", "figures.py", "production.py")
B2_FIXTURE_FILES = ("README.md", "manifest.json", "references.json", "query-groups.json")
SDIST_FILES = (
    "pyproject.toml", "README.md", "LICENSE", "PKG-INFO",
    "docs/COMPARISON_RELEASE_A.md", "docs/COMPARISON_SCHEMA_V1.md",
    "docs/DISTRIBUTION_VALIDATION.md", "examples/compare_saved_results.py",
    "examples/inspect_comparison_inputs.py", "tools/validate_distribution.py",
    "tools/distribution_smoke.py", "tools/distribution_browser.py",
    "tests/comparison/chrome_cdp.py", "docs/COMPARISON_FIGURES.md",
    "docs/COMPARISON_PRODUCTION.md", "examples/export_comparison_sidecar.py",
    "tools/benchmark_comparison.py",
)
FIXTURE_FILES = (
    "README.md", "manifest.json", "manifest-with-profiles.json", "profiles.json",
    "metadata.json", "expected.json", "pearson-run.csv", "ae-seed-42.csv", "ae-seed-123.csv",
    "manifest-with-b1.json", "sample-metadata.json", "b1-profiles.json", "manifest-with-b2.json",
)


def clean_environment():
    env = dict(os.environ)
    for key in list(env):
        if key.startswith(("PYTHON", "PIP_", "HATCH_", "SETUPTOOLS_SCM_")) or key in (
            "VIRTUAL_ENV", "__PYVENV_LAUNCHER__", "GIT_DIR", "GIT_WORK_TREE",
        ):
            env.pop(key, None)
    # Ignore user pip configuration and installation redirections. The standard
    # pip download cache is shared, never site-packages. Proxies/certificates stay.
    env.update(PYTHONNOUSERSITE="1", PIP_CONFIG_FILE=os.devnull,
               PIP_DISABLE_PIP_VERSION_CHECK="1", PIP_NO_INPUT="1")
    return env


def digest(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def inspect_wheel(path):
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        for asset in ASSETS:
            require(bool(archive.read("valpas/comparison/assets/" + asset)), "empty asset " + asset)
        for module in MODULES:
            require(bool(archive.read("valpas/comparison/" + module)), "empty module " + module)
        metadata_names = [n for n in names if n.endswith(".dist-info/METADATA")]
        require(len(metadata_names) == 1, "expected one wheel METADATA")
        metadata = BytesParser().parsebytes(archive.read(metadata_names[0]))
        require(metadata["Name"].lower() == "valpas", "wrong distribution")
        requirements = metadata.get_all("Requires-Dist", [])
        require(bool(requirements), "wheel has no declared dependencies")
        return {"path": str(path), "sha256": digest(path), "size_bytes": path.stat().st_size,
                "version": metadata["Version"], "requires_python": metadata["Requires-Python"],
                "requires_dist": requirements, "members": names}


def extract_sdist(path, destination):
    """Preflight entire tar: no links, special files, traversal or duplicate names."""
    with tarfile.open(path, "r:gz") as archive:
        members = archive.getmembers()
        seen, roots = set(), set()
        for member in members:
            name = PurePosixPath(member.name)
            require(not name.is_absolute() and ".." not in name.parts and "\\" not in member.name
                    and bool(name.parts), "unsafe sdist path: " + member.name)
            require(member.isfile() or member.isdir(), "nonregular sdist member: " + member.name)
            require(name.as_posix() not in seen, "duplicate sdist member: " + member.name)
            seen.add(name.as_posix())
            roots.add(name.parts[0])
        require(len(roots) == 1, "sdist must have one root")
        root = next(iter(roots))
        files = {PurePosixPath(m.name).relative_to(root).as_posix() for m in members if m.isfile()}
        required = set(SDIST_FILES)
        required.update("src/valpas/comparison/assets/" + a for a in ASSETS)
        required.update("tests/comparison/fixtures/demo-01/" + f for f in FIXTURE_FILES)
        required.update("tests/comparison/fixtures/b2-reference/" + f for f in B2_FIXTURE_FILES)
        required.update("src/valpas/comparison/" + m for m in MODULES)
        require(required <= files, "sdist missing documented files: " + str(sorted(required - files)))
        require(not any(".git" in PurePosixPath(m.name).parts for m in members), "sdist contains .git")
        # Destination is exclusively owned by this run. Python's data filter is
        # defense in depth after rejecting all link/special members above.
        destination.mkdir()
        archive.extractall(destination, filter="data")
    source = destination / root
    metadata = BytesParser().parsebytes((source / "PKG-INFO").read_bytes())
    return source, {"path": str(path), "sha256": digest(path), "size_bytes": path.stat().st_size,
                    "version": metadata["Version"], "members": sorted(files)}


class Runner:
    def __init__(self, workspace, timeout):
        self.workspace = workspace
        self.timeout = timeout
        self.env = clean_environment()
        self.summary = {"schema_version": 1, "status": "running", "mode": "full-dependencies",
                        "started_at": datetime.now(timezone.utc).isoformat(),
                        "workspace": str(workspace), "host_python": sys.version,
                        "platform": platform.platform(), "commands": [], "artifacts": {}, "checks": {}}
        (workspace / "logs").mkdir()
        self.save()

    def save(self):
        target = self.workspace / "summary.json"
        pending = target.with_suffix(".tmp")
        pending.write_text(json.dumps(self.summary, indent=2) + "\n", encoding="utf-8")
        pending.replace(target)

    def run(self, args, *, cwd=None, timeout=None):
        args = [str(a) for a in args]
        cwd = cwd or self.workspace
        index = len(self.summary["commands"]) + 1
        log = self.workspace / "logs" / f"{index:03d}.log"
        record = {"argv": args, "cwd": str(cwd), "log": str(log), "status": "running"}
        self.summary["commands"].append(record)
        self.save()
        print(f"[{index}] {args[0]} {' '.join(args[1:])}", flush=True)
        start = time.monotonic()
        try:
            with log.open("w", encoding="utf-8") as output:
                process = subprocess.Popen(args, cwd=cwd, env=self.env, stdout=output,
                                           stderr=subprocess.STDOUT, start_new_session=(os.name == "posix"))
                try:
                    code = process.wait(timeout=timeout or self.timeout)
                except subprocess.TimeoutExpired:
                    if os.name == "posix":
                        import signal
                        os.killpg(process.pid, signal.SIGKILL)
                    else:
                        process.kill()
                    process.wait()
                    record["status"] = "timeout"
                    raise
            record.update(returncode=code, status="passed" if code == 0 else "failed")
            if code:
                raise RuntimeError(f"command {index} exited {code}; see {log}")
            return log.read_text(encoding="utf-8")
        except BaseException:
            if record["status"] == "running":
                record["status"] = "error"
            raise
        finally:
            record["elapsed_seconds"] = round(time.monotonic() - start, 3)
            self.save()

    def venv(self, name):
        path = self.workspace / name
        self.run([sys.executable, "-I", "-m", "venv", path])
        python = path / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        self.run([python, "-I", "-m", "pip", "--version"])
        self.run([python, "-I", "-c", "import sys; assert sys.prefix != sys.base_prefix; print(sys.version); print(sys.prefix)"])
        return python


def retained_python(root, name):
    """Reuse only explicitly supplied isolated venvs; never the host interpreter."""
    env = (root / name).resolve()
    config = env / "pyvenv.cfg"
    require(config.is_file() and "include-system-site-packages = false" in config.read_text(),
            "retained environment must be isolated: " + str(env))
    python = env / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    require(python.is_file(), "missing retained interpreter: " + str(python))
    return python


def find_chrome(explicit=None):
    candidate = explicit or shutil.which("chromium") or shutil.which("chromium-browser") or shutil.which("google-chrome")
    if not candidate:
        candidate = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    path = Path(candidate).resolve()
    require(path.is_file(), "Chrome/Chromium is required; supply --chrome PATH (no browser skip in full validation)")
    return path


# The probe is appended only to a disposable COPY of the installed-package report.
# It uses the existing test_a3_browser.py direct-file/DOM approach, not source imports.
BROWSER_PROBE = r"""
<script>
try {
  const check=(v,m)=>{if(!v)throw Error(m);};
  check(document.documentElement.dataset.reportReady==='true','initial render');
  check(!document.querySelector('script[src],link[href],img,iframe'),'external resources');
  document.querySelector('.heat button').click();
  check(document.body.textContent.includes('Selected output pair:'),'heat drilldown');
  const sections=[...document.querySelectorAll('main > section')];
  const queries=sections.find(s=>s.querySelector('h2').textContent.startsWith('4'));
  const workspace=sections.find(s=>s.querySelector('h2').textContent.startsWith('5'));
  const click=(p,id)=>{const r=[...p.querySelectorAll('tr.selectable')].find(r=>r.cells[0].textContent===id);check(r,'row '+id);r.click();};
  click(queries,'M01'); click(workspace,'P01');
  check(workspace.querySelectorAll('svg').length===2,'profile plots');
  check(workspace.querySelectorAll('circle.imputed').length===2,'original masks');
  check(workspace.textContent.includes('Jointly observed finite points: 4'),'observed denominator');
  check([...workspace.querySelectorAll('svg title')].some(t=>t.textContent.includes('S01')),'hover IDs');
  [...workspace.querySelectorAll('button')].find(b=>b.textContent==='Pin candidate in this view').click();
  check(workspace.textContent.includes('Unpin candidate'),'pin');
  const search=document.getElementById('candidate-search');search.value='synthetic annotation';search.dispatchEvent(new Event('input'));
  check(workspace.querySelectorAll('tr.selectable').length===3,'annotation search');
  const q=document.getElementById('query-search');q.value='M02';q.dispatchEvent(new Event('input'));
  check(queries.querySelectorAll('tr.selectable').length===1,'query search');
  queries.querySelector('th button').click();
  const depth=document.getElementById('depth');depth.value=1;depth.dispatchEvent(new Event('change'));
  check(document.querySelector('.heat').textContent.includes('evaluable'),'depth');
  const toggle=document.querySelector('.controls input[type=checkbox]');toggle.checked=false;toggle.dispatchEvent(new Event('change'));
  check(document.querySelectorAll('.heat button').length===1,'output visibility');
  document.body.setAttribute('data-distribution-smoke','passed');
} catch(e) {document.body.setAttribute('data-distribution-smoke','FAILED: '+e.message);}
</script>
"""


B1_BROWSER_PROBE = r"""
<script>
try {
  const check=(v,m)=>{if(!v)throw Error(m);};
  const compare=(a,b,p='result')=>{
    if(typeof b==='number')check(typeof a==='number'&&Number.isFinite(a)&&Math.abs(a-b)<=Math.max(1e-12*Math.abs(b),1e-300),p+' number');
    else if(b===null||typeof b!=='object')check(a===b,p+' value');
    else {check(a!==null&&typeof a==='object',p+' object');check(JSON.stringify(Object.keys(a).sort())===JSON.stringify(Object.keys(b).sort()),p+' keys');Object.keys(b).forEach(k=>compare(a[k],b[k],p+'.'+k));}
  };
  const inputs=__EXPECTED__;
  const section=n=>[...document.querySelectorAll('main > section')].find(s=>s.querySelector('h2').textContent.startsWith(n));
  const click=(p,id)=>{const row=[...p.querySelectorAll('tr.selectable')].find(r=>r.cells[0].textContent===id);check(row,'row '+id);row.click();};
  const change=(node,value)=>{check(node,'control exists');node.value=value;node.dispatchEvent(new Event('change'));};
  const option=(select,label)=>[...select.options].find(o=>o.textContent===label||o.textContent.startsWith(label+' (')).value;
  const exact=selector=>JSON.parse(document.querySelector(selector+' pre').textContent);
  check(document.documentElement.dataset.reportReady==='true','initial render');
  check(!document.querySelector('.covariance-diagnostics'),'no eager diagnostics');
  check(!window.b1Pwned,'hostile data executed');
  const payloadText=document.getElementById('comparison-data').textContent;
  const overview=section('2').innerHTML;
  click(section('4'),'M01');const workspace=section('5');click(workspace,'P01');
  const rankMarkup=()=>[...workspace.querySelectorAll('table')].filter(t=>!t.closest('.profile-layer')).map(t=>t.innerHTML).join('');
  const ranks=rankMarkup();
  if(inputs.mode==='no-profile') {
    check(workspace.textContent.includes('No profile layers embedded'),'explicit no-profile reason');
    check(!workspace.querySelector('svg')&&!document.querySelector('.diagnostic-exact'),'no fallback plots/diagnostics');
  } else {
    check(workspace.querySelectorAll('svg').length===2,'B1 profiles');
    const color=document.querySelector('.metadata-color'),group=document.querySelector('.metadata-group'),order=document.querySelector('.sample-order');
    const positions=()=>Object.fromEntries([...document.querySelectorAll('[data-profile-role="query"]')].map(n=>[n.dataset.observationId,Number(n.getAttribute('cx'))]));
    const original=positions();check(order.value==='dataset'&&original.S01===60&&original.S06===670,'dataset order');
    check(document.querySelector('.diagnostic-h').value==='5','default h');
    check(exact('.diagnostic-exact').remaining.reason==='not_requested','omission opt-in');
    change(color,option(color,'condition'));
    check(document.querySelector('.metadata-legend').textContent.includes('Missing metadata'),'categorical legend');
    check(document.querySelectorAll('circle.metadata-missing').length>0,'missing metadata marks');
    change(group,option(group,'condition'));
    check(document.querySelectorAll('.group-exact pre').length===2,'two marginal groups');
    if(inputs.mode==='b1') [...document.querySelectorAll('.group-exact pre')].forEach((n,i)=>compare(JSON.parse(n.textContent),inputs.groups[i],'group '+i));
    check(document.querySelector('.group-summaries').textContent.includes('Missing group excluded: 2'),'group denominator');
    const groups=document.querySelector('.group-summaries').textContent;
    change(color,option(color,'time_hours'));
    check(document.querySelector('.metadata-legend').textContent.includes('0 (blue) → 6 (red)'),'continuous legend');
    check(document.querySelector('.group-summaries').textContent===groups,'color independent of grouping');
    change(order,'metadata');check(positions().S01<positions().S04,'continuous metadata order');
    change(color,option(color,'batch'));
    check(positions().S03<positions().S02,'categorical metadata order actually changes positions');
    change(order,'id');compare(positions(),original,'ID order');
    change(order,'dataset');compare(positions(),original,'restored dataset order');
    const h=document.querySelector('.diagnostic-h');change(h,'1');
    check(exact('.diagnostic-exact').remaining.reason==='not_requested','h does not request omission');
    document.querySelector('.omission-preview').click();
    compare(exact('.diagnostic-exact'),inputs.diagnostic,'installed Python/JS diagnostic');
    change(h,'2');check(exact('.diagnostic-exact').remaining.reason==='not_requested','h clears preview');
    change(h,'0');check(document.querySelector('.omission-preview').disabled,'invalid h blocked');change(h,'1');
    const fraction=document.querySelector('.group-fraction');fraction.checked=false;fraction.dispatchEvent(new Event('change'));
    check([...document.querySelectorAll('.group-exact pre')].every(n=>JSON.parse(n.textContent).fraction_status==='not_requested'),'fraction toggle');
    check([...workspace.querySelectorAll('svg title')].some(n=>n.textContent.includes('S06')&&n.textContent.includes('time_hours=missing')),'missing metadata hover');
    if(inputs.mode==='hostile') {
      check([...workspace.querySelectorAll('svg title')].some(n=>n.textContent.includes('<\/script><script>globalThis.b1Pwned=true')),'hostile hover rendered as text');
      check(document.querySelector('.group-summaries').textContent.includes('<\/script>'),'hostile group rendered as text');
    }
    check(rankMarkup()===ranks,'diagnostics changed rank DOM');
  }
  check(section('2').innerHTML===overview,'diagnostics changed overview');
  check(document.getElementById('comparison-data').textContent===payloadText,'diagnostics mutated saved scientific payload');
  check(!window.b1Pwned&&!document.querySelector('script[src],link[href],img,iframe'),'inert data and no external resources');
  document.body.setAttribute('data-distribution-smoke','passed');
} catch(e) {document.body.setAttribute('data-distribution-smoke','FAILED: '+e.stack);}
</script>
"""


def browser_check(runner, chrome, report, directory, *, mode="a3", expected=None):
    directory.mkdir()
    page = directory / "standalone.html"
    probe = BROWSER_PROBE
    if mode != "a3":
        data = json.dumps({**(expected or {}), "mode": mode}, ensure_ascii=True).replace("<", "\\u003c")
        probe = B1_BROWSER_PROBE.replace("__EXPECTED__", data)
    page.write_text(report.read_text(encoding="utf-8").replace("</body>", probe + "</body>"), encoding="utf-8")
    output = runner.run([chrome, "--headless", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
                         "--disable-background-networking", "--disable-component-update", "--disable-sync",
                         "--host-resolver-rules=MAP * ~NOTFOUND", "--user-data-dir=" + str(directory / "chrome"),
                         "--dump-dom", page.as_uri()], cwd=directory, timeout=90)
    require('data-distribution-smoke="passed"' in output, "browser interaction failed; see last command log")
    return {"status": "passed", "case": mode, "uri": page.as_uri(), "report_sha256": digest(report),
            "probe_sha256": hashlib.sha256(probe.encode()).hexdigest(),
            "actions": (["heat drilldown", "search/sort", "pins", "depth/output visibility", "profiles/masks/hovers"]
                        if mode == "a3" else ["select M01/P01", "no-profile reason/no fallback"] if mode == "no-profile"
                        else ["categorical/continuous color", "missing metadata", "dataset/ID/metadata order",
                              "condition groups", "fraction toggle", "h/omission/reset/invalid h",
                              "installed Python diagnostic parity", "unchanged ranks/overview/payload", "inert hostile text"]),
            "transport": "file://; hostname resolution disabled; report CSP connect-src none",
            "probe": "disposable HTML copy with appended interaction assertions"}


def validate_install(runner, label, wheel, fixture, helper, chrome, reuse=None):
    python = retained_python(reuse, label + "-env") if reuse else runner.venv(label + "-env")
    report = runner.workspace / (label + "-pip-install.json")
    options = ["--no-deps", "--force-reinstall"] if reuse else []
    runner.run([python, "-I", "-m", "pip", "install", *options, "--report", report, wheel])
    runner.run([python, "-I", "-m", "pip", "check"])
    runner.run([python, "-I", "-m", "pip", "list", "--format=json"])
    work = runner.workspace / label
    work.mkdir()
    runner.run([python, "-I", helper, "environment", wheel, work / "environment.json"], cwd=work)
    cli = python.parent / ("valpas.exe" if os.name == "nt" else "valpas")
    for args in ([cli, "--help"], [cli, "compare", "--help"], [python, "-I", "-m", "valpas.cli", "--help"]):
        output = runner.run(args, cwd=work)
        require("usage:" in output and "compare" in output, "missing CLI help")
    for command in ([cli], [python, "-I", "-m", "valpas.cli"]):
        output = runner.run([*command, "export-query", "--help"], cwd=work)
        require("--bundle" in output and "--candidate" in output, "missing figure CLI help")
    examples = work / "installed-examples"
    (examples / "examples").mkdir(parents=True)
    shutil.copytree(fixture, examples / "tests/comparison/fixtures/demo-01")
    example_checks = {}
    for name in ("compare_saved_results.py", "inspect_comparison_inputs.py", "export_comparison_sidecar.py"):
        script = examples / "examples" / name
        shutil.copy2(fixture.parents[3] / "examples" / name, script)
        runner.run([python, "-I", script], cwd=examples)
        example_checks[name] = {"status": "passed", "script_sha256": digest(script),
                                "command_log": runner.summary["commands"][-1]["log"]}
    shutil.rmtree(examples / "tests")
    copied = work / "inputs"
    shutil.copytree(fixture, copied)
    for name, manifest, extra in (
        ("html", "manifest-with-profiles.json", []),
        ("tables", "manifest-with-profiles.json", ["--tables-only"]),
        ("no-profile", "manifest.json", []),
        ("b1-html", "manifest-with-b1.json", []),
        ("b1-tables", "manifest-with-b1.json", ["--tables-only"]),
        ("b2-html", "manifest-with-b2.json", []),
        ("b2-tables", "manifest-with-b2.json", ["--tables-only"]),
    ):
        runner.run([cli, "compare", "--manifest", copied / manifest, "--outdir", work / name,
                    "--pool", "common", "--depths", "1", "2", "5", *extra], cwd=work)
    reference_inputs = work / "reference-inputs"
    shutil.copytree(fixture.parent / "b2-reference", reference_inputs)
    runner.run([cli, "compare", "--manifest", reference_inputs / "manifest.json",
                "--outdir", work / "reference-only"], cwd=work)
    shutil.rmtree(reference_inputs)
    runner.run([python, "-I", helper, "session", work, work / "session-api.json"], cwd=work)
    # Change only disposable fixture metadata, not source inputs or emitted HTML.
    hostile = '</script><script>globalThis.b1Pwned=true</script>\u2028Ω'
    metadata_path = copied / "sample-metadata.json"
    doc = json.loads(metadata_path.read_text())
    doc["records"][0]["values"]["condition"] = hostile
    metadata_path.write_text(json.dumps(doc), encoding="utf-8")
    runner.run([cli, "compare", "--manifest", copied / "manifest-with-b1.json", "--outdir", work / "b1-hostile",
                "--pool", "common", "--depths", "1", "2", "5"], cwd=work)
    shutil.rmtree(copied)
    for name in ("html", "tables", "b1-html", "b1-tables", "b2-html", "b2-tables", "b2-session", "b2-session-tables", "reference-only"):
        runner.run([cli, "compare", "--bundle", work / name, "--outdir", work / (name + "-regenerated")], cwd=work)
    for suffix in ("svg", "pdf"):
        runner.run([cli, "export-query", "--bundle", work / "b2-session-regenerated",
                    "--query", "M01", "--candidate", "P01", "--layer", "b1-observed",
                    "--color", "condition", "--group", "condition", "--h", "1", "--omission",
                    "--output", work / ("cli-figure." + suffix)], cwd=work)
    runner.run([python, "-I", helper, "bundles", work, work / "bundles.json"], cwd=work)
    runner.run([python, "-I", helper, "figures", work, work / "figures.json"], cwd=work)
    expected = json.loads((work / "browser-expected.json").read_text())
    runner.summary["checks"][label] = {
        "dependency_installation": "retained full dependencies; new wheel force-reinstalled without dependency resolution" if reuse else "fresh full dependencies",
        "environment": json.loads((work / "environment.json").read_text()),
        "installed_examples": example_checks,
        "bundles": json.loads((work / "bundles.json").read_text()),
        "session_api": json.loads((work / "session-api.json").read_text()),
        "figures": json.loads((work / "figures.json").read_text()),
        "inputs_removed_before_regeneration": not copied.exists(),
        "browser": {},
    }
    runner.save()
    for mode, bundle, directory in (("a3", "html-regenerated", "browser"),
                                    ("b1", "b1-html-regenerated", "browser-b1"),
                                    ("hostile", "b1-hostile", "browser-hostile"),
                                    ("no-profile", "no-profile", "browser-no-profile")):
        runner.summary["checks"][label]["browser"][mode] = browser_check(
            runner, chrome, work / bundle / "report.html", work / directory, mode=mode, expected=expected)
        runner.save()
    browser_helper = helper.with_name("distribution_browser.py")
    runner.run([python, "-I", browser_helper, chrome, work / "b2-session-regenerated",
                work / "browser-b2", work / "browser-b2.json"], cwd=work)
    runner.summary["checks"][label]["browser"]["b2"] = json.loads((work / "browser-b2.json").read_text())
    runner.save()
    # Separate process: resolving legacy public exports imports torch but never
    # invokes training, scoring, model loading or GPU operations.
    runner.run([python, "-I", helper, "legacy", work / "legacy.json"], cwd=work)
    runner.summary["checks"][label]["legacy"] = json.loads((work / "legacy.json").read_text())
    runner.save()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--work-parent", type=Path, help="existing external directory for a new private workspace")
    parser.add_argument("--chrome", help="existing Chrome/Chromium executable")
    parser.add_argument("--timeout", type=int, default=1200, help="per-command timeout in seconds (default: 1200)")
    parser.add_argument("--keep-envs", action="store_true", help="retain large environments for diagnosis/regressions")
    parser.add_argument("--reuse-envs", type=Path, help="explicit retained workspace containing isolated build/full-dependency venvs; builds remain fresh")
    args = parser.parse_args(argv)
    if sys.version_info < (3, 12):
        parser.error("Python 3.12+ is required")
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    source = args.source.resolve()
    parent = (args.work_parent or Path(tempfile.gettempdir())).resolve()
    if parent.is_relative_to(source):
        parser.error("workspace must be outside source checkout")
    workspace = Path(tempfile.mkdtemp(prefix="valpas-distribution-", dir=parent)).resolve()
    print("Validation workspace: " + str(workspace), flush=True)
    runner = Runner(workspace, args.timeout)
    runner.summary["source"] = str(source)
    reuse = args.reuse_envs.resolve() if args.reuse_envs else None
    if reuse:
        runner.summary.update(mode="retained-full-dependencies", retained_environment_root=str(reuse),
                              fresh_dependency_installation=False, build_isolation=False)
    # hatch-vcs writes this generated file during checkout builds. Restore any
    # pre-existing contents even on failure; do not reset or clean user changes.
    version_file = source / "src/valpas/_version.py"
    original_version = version_file.read_bytes() if version_file.exists() else None
    try:
        chrome = find_chrome(args.chrome)
        runner.summary["chrome_version"] = runner.run([chrome, "--version"]).strip()
        if shutil.which("git") and (source / ".git").exists():
            runner.summary["git_head"] = runner.run(["git", "rev-parse", "HEAD"], cwd=source).strip()
            runner.summary["git_status"] = runner.run(["git", "status", "--porcelain=v1"], cwd=source)
            runner.run(["git", "diff", "--binary", "HEAD"], cwd=source)
        build_python = retained_python(reuse, "build-env") if reuse else runner.venv("build-env")
        if reuse:
            for label in ("checkout-wheel-env", "sdist-wheel-env"):
                retained_python(reuse, label)
            # Probe first: avoid even a pip index request when tooling is present.
            probe = subprocess.run([str(build_python), "-I", "-c", "import build, hatchling, hatch_vcs"],
                                   env=runner.env, capture_output=True)
            if probe.returncode:
                runner.run([build_python, "-I", "-m", "pip", "install", "build", "hatchling", "hatch-vcs"])
            else:
                runner.run([build_python, "-I", "-c", "import build, hatchling, hatch_vcs; print('retained tooling available')"])
        else:
            runner.run([build_python, "-I", "-m", "pip", "install", "build"])
        isolation = ["--no-isolation"] if reuse else []
        runner.run([build_python, "-I", "-m", "pip", "list", "--format=json"])
        dist = workspace / "checkout-dist"
        runner.run([build_python, "-I", "-m", "build", *isolation, "--wheel", "--sdist", "--outdir", dist, source])
        wheels, sdists = list(dist.glob("*.whl")), list(dist.glob("*.tar.gz"))
        require(len(wheels) == len(sdists) == 1, "expected one checkout wheel and sdist")
        wheel, sdist = wheels[0], sdists[0]
        runner.summary["artifacts"]["checkout_wheel"] = inspect_wheel(wheel)
        extracted, record = extract_sdist(sdist, workspace / "extracted")
        runner.summary["artifacts"]["sdist"] = record
        rebuilt = workspace / "sdist-dist"
        # CWD and source are both outside checkout; extracted sdist has no .git.
        runner.run([build_python, "-I", "-m", "build", *isolation, "--wheel", "--outdir", rebuilt, extracted], cwd=extracted)
        rebuilt_wheels = list(rebuilt.glob("*.whl"))
        require(len(rebuilt_wheels) == 1, "expected one sdist-built wheel")
        runner.summary["artifacts"]["sdist_wheel"] = inspect_wheel(rebuilt_wheels[0])
        versions = {r["version"] for r in runner.summary["artifacts"].values()}
        require(len(versions) == 1, "wheel/sdist versions differ: " + str(versions))
        require(runner.summary["artifacts"]["checkout_wheel"]["requires_dist"] ==
                runner.summary["artifacts"]["sdist_wheel"]["requires_dist"], "wheel dependencies differ")
        # Tie both new artifact paths to the current checkout resource bytes.
        current_assets = {name: digest(source / "src/valpas/comparison/assets" / name) for name in ASSETS}
        for artifact in (wheel, rebuilt_wheels[0]):
            with zipfile.ZipFile(artifact) as archive:
                require({name: hashlib.sha256(archive.read("valpas/comparison/assets/" + name)).hexdigest()
                         for name in ASSETS} == current_assets, "wheel assets differ from current source")
        runner.summary["current_source_asset_sha256"] = current_assets
        runner.save()
        helper = workspace / "distribution_smoke.py"
        shutil.copy2(extracted / "tools/distribution_smoke.py", helper)
        shutil.copy2(extracted / "tools/distribution_browser.py", workspace / "distribution_browser.py")
        shutil.copy2(extracted / "tests/comparison/chrome_cdp.py", workspace / "chrome_cdp.py")
        fixture = extracted / "tests/comparison/fixtures/demo-01"
        for label, artifact in (("checkout-wheel", wheel), ("sdist-wheel", rebuilt_wheels[0])):
            validate_install(runner, label, artifact, fixture, helper, chrome, reuse)
        runner.summary["status"] = "passed"
    except BaseException as exc:
        runner.summary.update(status="failed", error=f"{type(exc).__name__}: {exc}", traceback=traceback.format_exc())
        print(runner.summary["error"], file=sys.stderr)
    finally:
        if original_version is None:
            version_file.unlink(missing_ok=True)
        else:
            version_file.write_bytes(original_version)
        runner.summary["generated_version_restored"] = (
            version_file.read_bytes() == original_version if original_version is not None else not version_file.exists())
        cleanup_errors = []
        if not args.keep_envs:
            # Delete only fixed children of our newly allocated private workspace.
            for name in ("build-env", "checkout-wheel-env", "sdist-wheel-env",
                         *(f"{label}/{browser}/chrome" for label in ("checkout-wheel", "sdist-wheel")
                           for browser in ("browser", "browser-b1", "browser-hostile", "browser-no-profile", "browser-b2"))):
                path = workspace / name
                if path.exists():
                    try:
                        shutil.rmtree(path)
                    except OSError as exc:
                        cleanup_errors.append(str(exc))
        runner.summary.update(finished_at=datetime.now(timezone.utc).isoformat(),
                              environments_retained=args.keep_envs, cleanup_errors=cleanup_errors)
        runner.save()
        print(f"{runner.summary['status'].upper()}: {workspace / 'summary.json'}", flush=True)
    return 0 if runner.summary["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
