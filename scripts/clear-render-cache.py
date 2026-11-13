import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request


def required_environment(name):
    value = os.environ.get(name, "").strip()

    if not value:
        raise RuntimeError(f"Required environment variable is missing: {name}")

    return value


def render_request(url, api_key, payload=None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(
        url,
        data=data,
        method="GET" if payload is None else "POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        raise RuntimeError(
            f"Render API request failed with HTTP {error.code}."
        ) from None


def main():
    api_key = required_environment("RENDER_API_KEY")
    service_id = required_environment("RENDER_SERVICE_ID")
    repository = required_environment("GITHUB_REPOSITORY")

    if not re.fullmatch(r"srv-[A-Za-z0-9]+", service_id):
        raise RuntimeError("Invalid Render service ID.")

    branch = os.environ.get("RENDER_PUBLISH_BRANCH", "render").strip()

    # This script runs AFTER the workflow publishes the website branch.
    result = subprocess.run(
        [
            "git",
            "ls-remote",
            f"https://github.com/{repository}.git",
            f"refs/heads/{branch}",
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )

    entries = result.stdout.strip().splitlines()

    if len(entries) != 1:
        raise RuntimeError("Could not identify the published website commit.")

    commit_id = entries[0].split()[0]

    if not re.fullmatch(r"[0-9a-fA-F]{40,64}", commit_id):
        raise RuntimeError("Invalid published commit ID.")

    deploys_url = (
        f"https://api.render.com/v1/services/{service_id}/deploys"
    )

    deployment = render_request(
        deploys_url,
        api_key,
        {
            "clearCache": "clear",
            "commitId": commit_id,
        },
    )

    deploy_id = deployment.get("id")

    if not deploy_id:
        raise RuntimeError("Render did not return a deployment ID.")

    print(
        f"Requested cache-clearing deployment {deploy_id} "
        f"for published commit {commit_id}.",
        flush=True,
    )

    deadline = time.monotonic() + 15 * 60
    previous_status = None

    failed_statuses = {
        "build_failed",
        "pre_deploy_failed",
        "update_failed",
        "canceled",
        "deactivated",
    }

    while time.monotonic() < deadline:
        deployment = render_request(
            f"{deploys_url}/{deploy_id}",
            api_key,
        )

        status = deployment.get("status")

        if status != previous_status:
            print(f"Render deployment status: {status}", flush=True)
            previous_status = status

        if status == "live":
            print("Cache-clearing deployment is live.", flush=True)
            return

        if status in failed_statuses:
            raise RuntimeError(
                f"Cache-clearing deployment failed: {status}"
            )

        time.sleep(10)

    raise RuntimeError(
        "Timed out waiting for the cache-clearing deployment."
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Cleanup failed: {error}", file=sys.stderr)
        sys.exit(1)