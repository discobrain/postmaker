"""Minimal Discourse REST client (stdlib only). Discourse is the single source
of truth — this client never caches anything locally."""

import json
import time
import urllib.error
import urllib.parse
import urllib.request


def _retry_after(detail: str) -> float:
    """Seconds to wait on a 429, from Discourse's error body (default 5, cap 30)."""
    try:
        wait = float(json.loads(detail)["extras"]["wait_seconds"])
    except Exception:
        wait = 5.0
    return min(max(wait, 1.0), 30.0) + 1.0


class Discourse:
    def __init__(self, url: str, api_key: str, api_username: str):
        self.url = url.rstrip("/")
        self.headers = {
            "Api-Key": api_key,
            "Api-Username": api_username,
            "Accept": "application/json",
            "User-Agent": "postmaker/0.1",
        }

    def _request(self, method: str, path: str, data: dict | None = None):
        headers = dict(self.headers)
        body = None
        if data is not None:
            body = urllib.parse.urlencode(data, doseq=True).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        for attempt in range(5):
            req = urllib.request.Request(
                self.url + path, data=body, method=method, headers=headers
            )
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    raw = r.read().decode()
                    return json.loads(raw) if raw.strip() else {}
            except urllib.error.HTTPError as e:
                detail = e.read().decode(errors="replace")
                if e.code == 429 and attempt < 4:
                    time.sleep(_retry_after(detail))
                    continue
                raise RuntimeError(
                    f"{method} {path} -> HTTP {e.code}: {detail}"
                ) from None

    # --- reads -------------------------------------------------------------

    def topics_with_tag(self, tag: str) -> list[dict]:
        """All topics carrying `tag`, across pages."""
        topics: list[dict] = []
        page = 0
        while page <= 50:
            data = self._request(
                "GET", f"/tag/{urllib.parse.quote(tag)}.json?page={page}"
            )
            batch = (data.get("topic_list") or {}).get("topics") or []
            if not batch:
                break
            topics.extend(batch)
            page += 1
        return topics

    def get_topic(self, topic_id: int) -> dict:
        return self._request("GET", f"/t/{topic_id}.json")

    def get_post_raw(self, post_id: int) -> str:
        return self._request("GET", f"/posts/{post_id}.json").get("raw", "") or ""

    def all_posts(self, topic: dict) -> list[dict]:
        """Every post in a topic, in order. `/t/{id}.json` only returns a window
        of ~20; fetch the rest by id from post_stream.stream."""
        stream = topic.get("post_stream") or {}
        have = {p["id"]: p for p in (stream.get("posts") or [])}
        order = stream.get("stream") or list(have)
        missing = [i for i in order if i not in have]
        tid = topic["id"]
        for i in range(0, len(missing), 50):
            chunk = missing[i : i + 50]
            q = "&".join(f"post_ids[]={pid}" for pid in chunk)
            data = self._request("GET", f"/t/{tid}/posts.json?{q}")
            for p in (data.get("post_stream") or {}).get("posts") or []:
                have[p["id"]] = p
        return [have[i] for i in order if i in have]

    def probe(self, path: str, auth: bool = True) -> dict:
        """Non-raising GET for diagnostics: returns {status, body}."""
        headers = (
            dict(self.headers)
            if auth
            else {"Accept": "application/json", "User-Agent": "postmaker/0.1"}
        )
        req = urllib.request.Request(self.url + path, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                body = r.read().decode()
                return {"status": r.status, "body": json.loads(body) if body.strip() else {}}
        except urllib.error.HTTPError as e:
            return {"status": e.code, "body": e.read().decode(errors="replace")}
        except Exception as e:  # network/DNS/TLS
            return {"status": None, "body": str(e)}

    # --- writes ------------------------------------------------------------

    def create_post(self, topic_id: int, raw: str) -> dict:
        return self._request("POST", "/posts.json", {"topic_id": topic_id, "raw": raw})

    def set_tags(self, topic_id: int, tags: list[str]) -> None:
        """Replace the topic's full tag set (Discourse expects the complete list).

        Verify it actually took: Discourse silently drops tags past
        max_tags_per_topic and still returns 200, so re-read and raise if any
        requested tag is missing rather than let the drop pass unnoticed."""
        self._request("PUT", f"/t/-/{topic_id}.json", {"tags[]": tags})
        applied = set(self.get_topic(topic_id).get("tags") or [])
        missing = set(tags) - applied
        if missing:
            raise RuntimeError(
                f"tags not applied to topic {topic_id}: {sorted(missing)} "
                f"(hit max_tags_per_topic?)"
            )

    def delete_post(self, post_id: int) -> dict:
        return self._request("DELETE", f"/posts/{post_id}.json")
