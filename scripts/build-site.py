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
        if reader.fieldnames != ["Repository", "Project", "Folder"]:
            raise ValueError(
                "apps.txt needs the TAB-separated header: Repository, Project, Folder."
            )
        apps = []
        folders = set()
        for line, raw in enumerate(reader, start=2):
            if None in raw or any(value is None for value in raw.values()):
                raise ValueError(f"apps.txt line {line}: expected exactly three columns.")
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
    if not apps:
        raise ValueError("apps.txt contains no apps.")
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
            links.append(f'<li><a href="{folder}/">{html.escape(repository)}</a></li>')

        (site / "index.html").write_text(
            '<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            '<title>Combined PWA Experiment</title></head><body>'
            '<h1>Combined PWA Experiment</h1><ul>' + "".join(links) + '</ul></body></html>',
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
