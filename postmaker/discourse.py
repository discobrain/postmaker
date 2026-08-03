"""Minimal Discourse REST client (stdlib only). Discourse is the single source
of truth — this client never caches anything locally."""

import json
import urllib.error
import urllib.parse
import urllib.request


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
        req = urllib.request.Request(
            self.url + path, data=body, method=method, headers=headers
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                raw = r.read().decode()
                return json.loads(raw) if raw.strip() else {}
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")
            raise RuntimeError(f"{method} {path} -> HTTP {e.code}: {detail}") from None

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

    # --- writes ------------------------------------------------------------

    def create_post(self, topic_id: int, raw: str) -> dict:
        return self._request("POST", "/posts.json", {"topic_id": topic_id, "raw": raw})

    def set_tags(self, topic_id: int, tags: list[str]) -> dict:
        """Replace the topic's full tag set (Discourse expects the complete list)."""
        return self._request("PUT", f"/t/-/{topic_id}.json", {"tags[]": tags})
