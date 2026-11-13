"""Build public Blazor WASM repositories listed in the tab-delimited apps.txt.

Uses Python's standard library, Git and the installed .NET SDK. The generated
site folder is published only after ALL apps have built successfully.
"""

import csv
import html
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parent.parent


def read_apps(path):
    # utf-8-sig also accepts UTF-8 files with a BOM created by Windows PowerShell.
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        if reader.fieldnames not in (["Repository", "Project", "Folder"],
                                    ["Repository", "Project", "Folder", "DisplayName"]):
            raise ValueError(
                "apps.txt needs the TAB-separated header: Repository, Project, Folder, DisplayName. "
                "The older three-column format is also accepted."
            )
        apps = []
        folders = set()
        for line, raw in enumerate(reader, start=2):
            if None in raw or any(value is None for value in raw.values()):
                raise ValueError(f"apps.txt line {line}: column count does not match the header.")
            app = {key: value.strip() for key, value in raw.items()}
            if not any(app.values()):
                continue
            if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", app["Repository"]):
                raise ValueError(f"apps.txt line {line}: use owner/repository.")
            if not re.fullmatch(r"[A-Za-z0-9_-][A-Za-z0-9_.-]*\.csproj", app["Project"]):
                raise ValueError(f"apps.txt line {line}: use the project filename only.")
            if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", app["Folder"]):
                raise ValueError(f"apps.txt line {line}: use a lowercase folder name.")
            if app["Folder"] in folders:
                raise ValueError(f"apps.txt line {line}: duplicate folder {app['Folder']}.")
            folders.add(app["Folder"])
            apps.append(app)
    return apps


def run(arguments):
    subprocess.run([str(argument) for argument in arguments], check=True)


def build_site():
    apps = read_apps(ROOT / "apps.txt")
    # All intermediate repositories and publish outputs stay outside this repo.
    temporary_parent = os.environ.get("RUNNER_TEMP") or None
    with tempfile.TemporaryDirectory(prefix="combined-pwas-", dir=temporary_parent) as work:
        work = Path(work)
        site = work / "site"
        site.mkdir()
        links = []
        for app in apps:
            repository, filename, folder = (app[key] for key in ("Repository", "Project", "Folder"))
            source = work / "sources" / folder
            source.parent.mkdir(parents=True, exist_ok=True)
            print(f"Building {repository} for /{folder}/", flush=True)
            run(["git", "clone", "--depth", "1", f"https://github.com/{repository}.git", source])
            projects = [
                path for path in source.rglob(filename)
                if not {"bin", "obj", ".git"}.intersection(path.relative_to(source).parts)
            ]
            if len(projects) != 1:
                raise ValueError(f"Expected one {filename} in {repository}, found {len(projects)}.")
            published = work / "published" / folder
            run(["dotnet", "publish", projects[0], "--configuration", "Release",
                 "--output", published, "--nologo"])
            webroot = published / "wwwroot"
            index = webroot / "index.html"
            if not index.is_file():
                raise ValueError(f"No published wwwroot/index.html for {repository}.")
            base = re.search(r'<base\s+href=[\"\x27]([^\"\x27]+)[\"\x27]',
                             index.read_text(encoding="utf-8-sig"), re.IGNORECASE)
            if not base or base.group(1) != f"/{folder}/":
                raise ValueError(f"{repository}: index.html must have <base href=\"/{folder}/\" />.")
            shutil.copytree(webroot, site / folder)
            label = app.get("DisplayName") or repository
            links.append(
                f'<a class="btn btn-primary app-button" href="{folder}/">'
                f'{html.escape(label)}</a>'
            )

        title_file = ROOT / "page-title.txt"
        title = (title_file.read_text(encoding="utf-8-sig").strip()
                 if title_file.is_file() else "Combined PWA Experiment")
        title = html.escape(title or "Combined PWA Experiment")
        (site / "index.html").write_text(
            '<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>{title}</title>'
            '<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.8/dist/css/bootstrap.min.css" '
            'rel="stylesheet" '
            'integrity="sha384-sRIl4kxILFvY47J16cr9ZwB07vP4J8+LH7qKQnuqkuIAvNWLzeN8tE5YBujZqJLB" '
            'crossorigin="anonymous">'
            '<style>'
            '.app-grid{display:flex;flex-wrap:wrap;gap:1rem;align-items:stretch;}'
            '.app-button{box-sizing:border-box;max-width:100%;min-width:0;font-size:2rem;'
            'line-height:1.2;white-space:normal;overflow-wrap:anywhere;'
            'display:flex;align-items:center;justify-content:center;}'
            '</style></head><body>'
            f'<main class="container-fluid px-0 py-4"><h1 class="mb-4">{title}</h1>'
            '<nav class="app-grid" aria-label="Available apps">' + "".join(links) +
            '</nav></main></body></html>',
            encoding="utf-8",
        )
        # Replace generated output only after the complete build has succeeded.
        destination = ROOT / "site"
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(site, destination)
    print(f"Built {len(apps)} apps into {ROOT / 'site'}", flush=True)


if __name__ == "__main__":
    try:
        build_site()
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"Build failed: {error}", file=sys.stderr)
        sys.exit(1)
