"""Check the deployed API without publishing or changing member data.

python -B Android_APP/tools/check_live_api.py https://your-api-host.example
Optional --login reads ACM_APP_TEST_QQ and ACM_APP_TEST_PASSWORD from this
process environment. Credentials, cookies and response bodies are never saved.
"""
import argparse
import datetime
import http.cookiejar
import json
import os
from pathlib import Path
import ssl
import urllib.error
import urllib.parse
import urllib.request


APP_ROOT = Path(__file__).resolve().parents[1]


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def checked_base(value):
    uri = urllib.parse.urlsplit(value)
    if (uri.scheme != "https" or not uri.hostname or uri.username or uri.password
            or uri.path not in ("", "/") or uri.query or uri.fragment):
        raise argparse.ArgumentTypeError("Use an HTTPS server root without /api, credentials or query parameters.")
    try:
        uri.port
    except ValueError as error:
        raise argparse.ArgumentTypeError("Invalid server port.") from error
    return value.rstrip("/")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_url", type=checked_base)
    parser.add_argument("--proxy", help="Optional HTTP/HTTPS proxy; direct connection is the default.")
    parser.add_argument("--login", action="store_true", help="Use the test account from process environment.")
    parser.add_argument("--mobile", action="store_true", help="Also check the deployed /api/mobile/v1 contracts.")
    parser.add_argument("--output", type=Path, default=APP_ROOT / "docs" / "live-api-result.json")
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(APP_ROOT):
        parser.error("The report must be written inside Android_APP.")
    if args.proxy:
        proxy = urllib.parse.urlsplit(args.proxy)
        if proxy.scheme not in ("http", "https") or not proxy.hostname or proxy.username or proxy.password:
            parser.error("Use an HTTP/HTTPS proxy address without credentials.")
    if args.login and not (os.getenv("ACM_APP_TEST_QQ") and os.getenv("ACM_APP_TEST_PASSWORD")):
        parser.error("Set ACM_APP_TEST_QQ and ACM_APP_TEST_PASSWORD locally for a test account.")
    proxies = {"http": args.proxy, "https": args.proxy} if args.proxy else {}
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler(proxies), NoRedirect(),
        urllib.request.HTTPSHandler(context=ssl.create_default_context()),
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
    )
    rows = []

    def check(path, expected, required=(), method="GET", payload=None, csrf="", authenticated=None):
        row = {"method": method, "path": path, "result": "failed"}
        headers = {"Accept": "application/json", "User-Agent": "ACMforever-api-review/0.1.12"}
        data = None
        if payload is not None:
            headers["Content-Type"] = "application/json; charset=utf-8"
            data = json.dumps(payload).encode("utf-8")
        if csrf:
            headers["X-CSRF-Token"] = csrf
        body = None
        try:
            request = urllib.request.Request(args.base_url + path, data=data, headers=headers, method=method)
            with opener.open(request, timeout=10) as response:
                row["http_status"] = response.status
                raw = response.read(1024 * 1024 + 1)
                if len(raw) > 1024 * 1024:
                    raise ValueError("Response exceeds the review size limit.")
                body = json.loads(raw.decode("utf-8"))
                if not isinstance(body, expected):
                    raise ValueError("Unexpected JSON response type.")
                if expected is dict and not set(required).issubset(body):
                    raise ValueError("Required response fields are missing.")
                if authenticated is not None and body.get("authenticated") is not authenticated:
                    raise ValueError("Session state is unexpected.")
                if path == "/api/auth/login" and not body.get("csrf_token"):
                    raise ValueError("Login response lacks a CSRF token.")
                if path == "/health" and body.get("status") != "ok":
                    raise ValueError("Health status is not ok.")
                if path == "/api/mobile/v1/capabilities" and (body.get("api_version") != 1 or not isinstance(body.get("features"), dict)):
                    raise ValueError("Mobile API version or capabilities schema is unsupported.")
                if expected is list:
                    row["item_count"] = len(body)
                else:
                    for key in ("rows", "items"):
                        if key in body:
                            if not isinstance(body[key], list):
                                raise ValueError("The response collection must be a list.")
                            row["item_count"] = len(body[key])
                row["result"] = "passed"
        except urllib.error.HTTPError as error:
            row["http_status"] = error.code
            row["reason"] = {
                401: "Login required or session expired.",
                403: "Permission or CSRF denied.",
                404: "Path or resource unavailable; verify the deployed API.",
                405: "HTTP method unavailable on this path.",
                410: "Feature retired.",
                428: "Initial password change required.",
            }.get(error.code, "HTTP request failed.")
        except (urllib.error.URLError, OSError):
            row["reason"] = "Connection, DNS or TLS verification failed."
        except (ValueError, UnicodeError) as error:
            row["reason"] = str(error)
        rows.append(row)
        print(f'{method} {path}: {row["result"]} (HTTP {row.get("http_status", "unavailable")})')
        return body if row["result"] == "passed" else None

    check("/health", dict, ("status",))
    check("/api/auth/me", dict, ("authenticated",), authenticated=False)
    check("/api/forum/categories", list)
    for sort in ("latest", "hot", "unanswered"):
        check("/api/forum/posts?page=1&page_size=1&sort=" + sort, dict, ("rows", "total", "page", "page_size"))
    for days in ("7", "30", "all"):
        check("/api/community/leaderboard?page=1&page_size=1&sort=total_count&days=" + days,
              dict, ("rows", "total", "page", "page_size"))
    mobile = None
    if args.mobile:
        mobile = check("/api/mobile/v1/capabilities", dict, ("api_version", "features"))
        if mobile:
            ranked = check("/api/mobile/v1/leaderboard?days=all&page=1&page_size=5", dict, ("rows", "total", "page", "page_size"))
            check("/api/mobile/v1/forum/posts?page=1&page_size=5", dict, ("rows", "total", "page", "page_size"))
            if ranked and ranked["rows"]:
                public_id = ranked["rows"][0].get("public_member_id", "")
                if isinstance(public_id, str) and len(public_id) == 32 and all(c.isascii() and (c.isalnum() or c in "_-") for c in public_id):
                    check("/api/mobile/v1/members/" + public_id, dict, ("public_member_id", "name", "motto", "platform_counts", "total_count"))
                    check("/api/mobile/v1/members/" + public_id + "/posts?page_size=5", dict, ("rows", "total", "page", "page_size"))
                else:
                    rows.append({"method": "GET", "path": "/api/mobile/v1/leaderboard", "result": "failed", "reason": "Public member ID missing or invalid."})
    if args.login:
        login = check("/api/auth/login", dict, ("csrf_token", "role"), "POST",
                      {"qq_id": os.environ["ACM_APP_TEST_QQ"], "password": os.environ["ACM_APP_TEST_PASSWORD"]})
        if login:
            try:
                check("/api/auth/me", dict, ("authenticated", "role"), authenticated=True)
                check("/api/me/profile", dict, ("user", "total_count", "platform_counts", "recent_ac"))
                check("/api/me/problems?page=1&page_size=1", dict, ("items", "total", "page", "page_size"))
                for path in ("/api/forum/mine/posts", "/api/forum/mine/bookmarks", "/api/forum/drafts"):
                    check(path, list)
                if args.mobile and mobile:
                    check("/api/mobile/v1/me/public-profile", dict, ("public_member_id", "motto", "platform_counts", "total_count"))
            finally:
                check("/api/auth/logout", dict, ("success",), "POST", {}, login["csrf_token"])
    result = {
        "checked_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "base_url": args.base_url,
        "connection": "proxy" if args.proxy else "direct",
        "scope": "Deployed API reads and optional test login/logout; no member data changes.",
        "passed": all(row["result"] == "passed" for row in rows),
        "checks": rows,
        "pending_endpoints": ["M0" + str(index + 1) for index, feature in enumerate(
            ("public_member_ids", "member_profiles", "member_posts", "own_public_profile", "edit_motto")
        ) if not mobile or mobile["features"].get(feature) is not True],
        "limits": "No device installation, HTTPS traffic from Android, data writes or APK update installation verified.",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Saved metadata-only report:", output)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
